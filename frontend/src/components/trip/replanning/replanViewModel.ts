"use client";

import {
  buildSemanticStopKey,
  buildStopRef,
  buildStopRefs,
  formatBlockLabel,
  normalizeStopName,
} from "./replanDiff";
import type {
  ReplanBlockType,
  ReplanConstraintFinding,
  ReplanExecutionMode,
  ReplanImpactItem,
  ReplanIntentKind,
  ReplanIntentLike,
  ReplanItineraryLike,
  ReplanMutationPlan,
  ReplanOperation,
  ReplanScheduledItemLike,
  ReplanStopRef,
} from "./replanTypes";

const BLOCK_ORDER: ReplanBlockType[] = ["morning", "afternoon", "evening"];

const DAY_WORDS: Record<string, number> = {
  一: 1,
  二: 2,
  两: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
};

export function buildReplanMutationPlan(
  rawText: string,
  itinerary: ReplanItineraryLike,
): ReplanMutationPlan {
  const text = rawText.trim();
  const stops = buildStopRefs(itinerary);
  if (!text) {
    return buildBlockedPlan({
      text,
      intentKind: "unknown",
      title: "等待调整指令",
      summary: "输入一句想调整的路线要求后，系统会先解释再执行。",
      evidence: ["尚未收到 follow-up 文本。"],
      contractGaps: [],
    });
  }

  const intentKind = detectIntentKind(text);
  const targetStops = resolveTargetStops(text, stops);
  const targetDay = resolveTargetDay(text);
  const targetBlock = resolveTargetBlock(text);

  if (intentKind === "weather_adaptation") {
    return buildUnsupportedPlan({
      text,
      intentKind,
      title: "雨天/天气适配需要外部天气与室内外属性",
      summary: "当前行程响应没有天气事实和 POI 室内外可靠字段，因此不能假装自动替换。",
      targetStops,
      evidence: ["识别到天气适配意图。", "当前后端没有天气数据 contract。"],
      contractGaps: ["缺少天气源、POI 室内外属性、天气触发的候选替换 endpoint。"],
    });
  }

  if (intentKind === "remove_stop") {
    return buildRemoveStopPlan(text, stops, targetStops);
  }

  if (intentKind === "move_stop") {
    return buildMoveStopPlan(text, itinerary.trip_days, stops, targetStops, targetDay, targetBlock);
  }

  if (intentKind === "relax_day") {
    return buildRelaxDayPlan(text, itinerary, stops, targetDay);
  }

  if (intentKind === "area_consolidation" || intentKind === "add_preference") {
    return buildBackendReplanPlan({
      text,
      intentKind,
      title:
        intentKind === "area_consolidation"
          ? "按区域/少走路偏好重跑规划"
          : "把新增偏好合并进再规划",
      summary:
        "现有后端可以把这句话合并进 regeneration intent 并重跑确定性规划，但还不能保证只移动某一个 stop。",
      targetStops,
      evidence: [
        "Saved Trip 会通过持久化 replan endpoint 解析 follow-up 文本并创建新 revision。",
        "调度结果仍由 deterministic planner 输出。",
      ],
      contractGaps: [
        "缺少结构化 mutation plan endpoint。",
        "缺少 affected day/block/stop 的后端 preview contract。",
      ],
    });
  }

  return buildBackendReplanPlan({
    text,
    intentKind: "general_replan",
    title: "交给现有 follow-up replan 重跑",
    summary:
      "这条要求没有被解析成安全的局部 mutation，将通过现有后端 follow-up 入口合并并重新生成。",
    targetStops,
    evidence: ["未检测到明确的删除、移动或轻量化目标。"],
    contractGaps: [
      "当前后端 response 没有返回 before/after diff。",
      "非持久化 legacy replan path 仍没有 revision/idempotency contract。",
    ],
  });
}

export function applyReplanMutationPlanToItinerary<TItinerary extends ReplanItineraryLike>(
  itinerary: TItinerary,
  plan: ReplanMutationPlan,
): TItinerary {
  if (plan.executionMode !== "local_mutation" || plan.operations.length === 0) {
    return itinerary;
  }

  let removedStops: ReplanStopRef[] = [];
  let nextDays = itinerary.days.map((day) => ({
    ...day,
    blocks: day.blocks.map((block) => ({
      ...block,
      items: [...block.items],
    })),
  }));

  for (const operation of plan.operations) {
    if (operation.kind === "remove_stop") {
      const removal = removeStopFromDays(nextDays, operation.stopId);
      nextDays = removal.days;
      if (removal.stop) {
        removedStops = [...removedStops, removal.stop];
      }
    }
    if (operation.kind === "move_stop") {
      const movement = moveStopInDays(
        nextDays,
        operation.stopId,
        operation.toDay,
        operation.toBlockType,
      );
      nextDays = movement.days;
    }
  }

  const nextItinerary = {
    ...itinerary,
    days: nextDays,
  };

  return patchIntentForLocalMutation(nextItinerary, plan, removedStops) as TItinerary;
}

function buildRemoveStopPlan(
  text: string,
  stops: ReplanStopRef[],
  targetStops: ReplanStopRef[],
): ReplanMutationPlan {
  if (targetStops.length !== 1) {
    return buildBlockedPlan({
      text,
      intentKind: "remove_stop",
      title: targetStops.length > 1 ? "删除目标不唯一" : "没有找到要删除的地点",
      summary:
        targetStops.length > 1
          ? "这句话命中了多个地点，需要更明确地说明要删哪一个。"
          : "当前行程里没有找到与这句话匹配的 stop。",
      targetStops,
      candidateStops: targetStops.length > 0 ? targetStops : stops.slice(0, 6),
      evidence: ["局部删除必须先解析到唯一 stop。"],
      contractGaps: [],
    });
  }

  const target = targetStops[0];
  const constraints = buildTargetConstraintFindings(target, "remove_stop");
  const blocked = constraints.some((finding) => finding.severity === "blocked");
  return {
    id: buildPlanId(text, "remove_stop", [target.id]),
    rawText: text,
    intentKind: "remove_stop",
    title: `删除 ${target.name}`,
    summary: `将从第 ${target.day} 天${target.blockLabel}移除这个非固定地点，并刷新解释/补全表面。`,
    executionMode: blocked ? "unsupported" : "local_mutation",
    confidence: "high",
    operations: blocked
      ? []
      : [
          {
            kind: "remove_stop",
            stopId: target.id,
            stopName: target.name,
            day: target.day,
            blockType: target.blockType,
          },
        ],
    targetStops: [target],
    candidateStops: [],
    constraints,
    impactPreview: [
      {
        key: "remove-target",
        tone: blocked ? "gap" : "change",
        title: blocked ? "不可直接移除" : "局部移除",
        detail: blocked
          ? "该地点是固定/锁定约束，不能由局部 replan 直接删除。"
          : `第 ${target.day} 天${target.blockLabel}会少一个地点，后续补全评分会刷新。`,
      },
      ...buildProtectedBoundaryImpactItems(),
    ],
    evidence: [
      `命中唯一地点：${target.name}。`,
      blocked ? "约束检查发现硬保护。" : "该地点没有固定时间或锁定来源。",
    ],
    contractGaps: [],
    requiresConfirmation: true,
    executable: !blocked,
  };
}

function buildMoveStopPlan(
  text: string,
  tripDays: number,
  stops: ReplanStopRef[],
  targetStops: ReplanStopRef[],
  targetDay: number | null,
  targetBlock: ReplanBlockType | null,
): ReplanMutationPlan {
  if (targetStops.length !== 1 || targetDay === null || targetBlock === null) {
    return buildBlockedPlan({
      text,
      intentKind: "move_stop",
      title: "移动指令不完整",
      summary: "局部移动需要唯一地点、目标天数和目标时段。",
      targetStops,
      candidateStops: targetStops.length > 0 ? targetStops : stops.slice(0, 6),
      evidence: [
        targetStops.length === 1 ? `已识别地点：${targetStops[0].name}` : "没有唯一地点。",
        targetDay !== null ? `目标天数：第 ${targetDay} 天` : "缺少目标天数。",
        targetBlock !== null ? `目标时段：${formatBlockLabel(targetBlock)}` : "缺少目标时段。",
      ],
      contractGaps: [],
    });
  }

  const target = targetStops[0];
  const constraints = [
    ...buildTargetConstraintFindings(target, "move_stop"),
    ...(targetDay < 1 || targetDay > tripDays
      ? [
          {
            key: "target-day-invalid",
            severity: "blocked" as const,
            title: "目标天数无效",
            detail: `目标天数必须在当前 1-${tripDays} 天范围内。`,
          },
        ]
      : []),
  ];
  const blocked = constraints.some((finding) => finding.severity === "blocked");
  return {
    id: buildPlanId(text, "move_stop", [target.id, String(targetDay), targetBlock]),
    rawText: text,
    intentKind: "move_stop",
    title: `移动 ${target.name}`,
    summary: `把 ${target.name} 从第 ${target.day} 天${target.blockLabel}移动到第 ${targetDay} 天${formatBlockLabel(targetBlock)}。`,
    executionMode: blocked ? "unsupported" : "local_mutation",
    confidence: "medium",
    operations: blocked
      ? []
      : [
          {
            kind: "move_stop",
            stopId: target.id,
            stopName: target.name,
            fromDay: target.day,
            fromBlockType: target.blockType,
            toDay: targetDay,
            toBlockType: targetBlock,
          },
        ],
    targetStops: [target],
    candidateStops: [],
    constraints,
    impactPreview: [
      {
        key: "move-target",
        tone: blocked ? "gap" : "change",
        title: blocked ? "不可直接移动" : "局部移动",
        detail: blocked
          ? "该地点是固定/锁定约束，不能由局部 replan 直接移动。"
          : "会保留地点本身，路线段将以估算方式标记并刷新解释表面。",
      },
      {
        key: "route-estimate",
        tone: "estimate",
        title: "路线影响为估算",
        detail: "本地移动不会调用地图 route preview；执行后会刷新可解释表面，但不是后端级全量重排。",
      },
      ...buildProtectedBoundaryImpactItems(),
    ],
    evidence: [
      `命中唯一地点：${target.name}。`,
      `解析目标：第 ${targetDay} 天${formatBlockLabel(targetBlock)}。`,
    ],
    contractGaps: ["缺少后端 incremental move-stop endpoint 和路线 preview contract。"],
    requiresConfirmation: true,
    executable: !blocked,
  };
}

function buildRelaxDayPlan(
  text: string,
  itinerary: ReplanItineraryLike,
  stops: ReplanStopRef[],
  targetDay: number | null,
): ReplanMutationPlan {
  const day = targetDay ?? inferBusiestDay(stops);
  const candidate = chooseRelaxationCandidate(stops.filter((stop) => stop.day === day));
  if (!candidate) {
    return buildBlockedPlan({
      text,
      intentKind: "relax_day",
      title: `第 ${day} 天没有安全可删的弹性地点`,
      summary: "轻量化只能自动移除非固定、非锁定的弹性 stop。",
      candidateStops: stops.filter((stop) => stop.day === day),
      evidence: ["没有找到可安全移除的 auto-filled 或低约束地点。"],
      contractGaps: [],
    });
  }

  const plan = buildRemoveStopPlan(text, stops, [candidate]);
  return {
    ...plan,
    id: buildPlanId(text, "relax_day", [candidate.id]),
    intentKind: "relax_day",
    title: `让第 ${day} 天轻一点`,
    summary: `建议先移除第 ${day} 天${candidate.blockLabel}的 ${candidate.name}，这是当前最适合局部放松的非固定地点。`,
    confidence: targetDay === null ? "medium" : "high",
    impactPreview: [
      {
        key: "relax-candidate",
        tone: "change",
        title: "减少一个弹性 stop",
        detail: `第 ${day} 天会少去 ${candidate.name}，不移动固定事件和锚点。`,
      },
      {
        key: "density",
        tone: "estimate",
        title: "节奏影响",
        detail: "预计当天密度下降；实际交通和补全建议会在执行后重新刷新。",
      },
      ...buildProtectedBoundaryImpactItems(),
    ],
    evidence: [
      `目标日：第 ${day} 天。`,
      `${candidate.name} 是非固定地点，来源为 ${candidate.sourceType ?? "未标明"}。`,
      itinerary.trip_days ? `当前共 ${itinerary.trip_days} 天，未改变行程天数。` : "未改变行程天数。",
    ],
  };
}

function buildBackendReplanPlan({
  text,
  intentKind,
  title,
  summary,
  targetStops = [],
  evidence,
  contractGaps,
}: {
  text: string;
  intentKind: ReplanIntentKind;
  title: string;
  summary: string;
  targetStops?: ReplanStopRef[];
  evidence: string[];
  contractGaps: string[];
}): ReplanMutationPlan {
  const operation: ReplanOperation = {
    kind: "backend_replan",
    prompt: text,
    capabilityGap: "现有后端执行的是 follow-up merge + deterministic regeneration，不是局部 mutation executor。",
  };
  return {
    id: buildPlanId(text, intentKind, targetStops.map((stop) => stop.id)),
    rawText: text,
    intentKind,
    title,
    summary,
    executionMode: "backend_replan",
    confidence: "medium",
    operations: [operation],
    targetStops,
    candidateStops: [],
    constraints: [
      {
        key: "backend-boundary",
        severity: "watch",
        title: "后端会重跑规划",
        detail: "固定事件、可用时间和锚点仍由后端 deterministic planner 执行，但不保证只有局部变化。",
      },
    ],
    impactPreview: [
      {
        key: "regeneration",
        tone: "estimate",
        title: "影响范围可能超过单个地点",
        detail: "当前 contract 只能在执行后通过 before/after diff 审核实际变化。",
      },
      ...buildProtectedBoundaryImpactItems(),
    ],
    evidence,
    contractGaps,
    requiresConfirmation: true,
    executable: true,
  };
}

function buildUnsupportedPlan({
  text,
  intentKind,
  title,
  summary,
  targetStops = [],
  candidateStops = [],
  evidence,
  contractGaps,
}: {
  text: string;
  intentKind: ReplanIntentKind;
  title: string;
  summary: string;
  targetStops?: ReplanStopRef[];
  candidateStops?: ReplanStopRef[];
  evidence: string[];
  contractGaps: string[];
}): ReplanMutationPlan {
  return {
    id: buildPlanId(text, intentKind, targetStops.map((stop) => stop.id)),
    rawText: text,
    intentKind,
    title,
    summary,
    executionMode: "unsupported",
    confidence: "low",
    operations: [],
    targetStops,
    candidateStops,
    constraints: [
      {
        key: "unsupported-capability",
        severity: "blocked",
        title: "当前 contract 不支持安全执行",
        detail: summary,
      },
    ],
    impactPreview: [
      {
        key: "gap",
        tone: "gap",
        title: "只能记录能力缺口",
        detail: "不会执行会改变行程的请求。",
      },
    ],
    evidence,
    contractGaps,
    requiresConfirmation: false,
    executable: false,
  };
}

function buildBlockedPlan(options: {
  text: string;
  intentKind: ReplanIntentKind;
  title: string;
  summary: string;
  targetStops?: ReplanStopRef[];
  candidateStops?: ReplanStopRef[];
  evidence: string[];
  contractGaps: string[];
}): ReplanMutationPlan {
  return buildUnsupportedPlan({
    ...options,
    contractGaps: options.contractGaps,
  });
}

function detectIntentKind(text: string): ReplanIntentKind {
  if (/(下雨|雨天|天气|室内|避雨)/.test(text)) {
    return "weather_adaptation";
  }
  if (/(挪|移动|移到|放到|安排到|改到|换到)/.test(text)) {
    return "move_stop";
  }
  if (/(删|删除|去掉|移除|取消)/.test(text)) {
    return "remove_stop";
  }
  if (/(轻松|轻一点|少一点|不要太赶|不太赶|放松|留白|空一点)/.test(text)) {
    return "relax_day";
  }
  if (/不要/.test(text)) {
    return "remove_stop";
  }
  if (/(顺路|少走路|近一点|集中|区域|不要绕)/.test(text)) {
    return "area_consolidation";
  }
  if (/(想|希望|偏好|喜欢|多一点|更)/.test(text)) {
    return "add_preference";
  }
  return "unknown";
}

function resolveTargetStops(text: string, stops: ReplanStopRef[]): ReplanStopRef[] {
  const normalizedText = normalizeStopName(text);
  const directMatches = stops.filter((stop) =>
    normalizedText.includes(normalizeStopName(stop.name)),
  );
  if (directMatches.length > 0) {
    return uniqueStops(directMatches);
  }

  const categoryMatches = stops.filter((stop) => matchesCategory(text, stop));
  return uniqueStops(categoryMatches);
}

function matchesCategory(text: string, stop: ReplanStopRef): boolean {
  if (/(博物馆|展馆|馆)/.test(text) && /博物馆|馆|museum/i.test(stop.name)) {
    return true;
  }
  if (/(饭|餐厅|吃|小吃|夜市)/.test(text) && stop.type === "restaurant") {
    return true;
  }
  if (/(夜景|夜游|晚上)/.test(text) && stop.blockType === "evening") {
    return true;
  }
  return false;
}

function resolveTargetDay(text: string): number | null {
  const arabicMatch = text.match(/第\s*(\d+)\s*天/);
  if (arabicMatch) {
    return Number(arabicMatch[1]);
  }
  const chineseMatch = text.match(/第\s*([一二两三四五六七])\s*天/);
  if (chineseMatch) {
    return DAY_WORDS[chineseMatch[1]] ?? null;
  }
  return null;
}

function resolveTargetBlock(text: string): ReplanBlockType | null {
  if (/(早上|上午|早晨)/.test(text)) {
    return "morning";
  }
  if (/(下午|午后)/.test(text)) {
    return "afternoon";
  }
  if (/(晚上|夜里|夜游|晚饭|晚餐)/.test(text)) {
    return "evening";
  }
  return null;
}

function buildTargetConstraintFindings(
  target: ReplanStopRef,
  operation: "remove_stop" | "move_stop",
): ReplanConstraintFinding[] {
  const findings: ReplanConstraintFinding[] = [];
  if (target.isProtected) {
    findings.push({
      key: `protected-${target.id}`,
      severity: "blocked",
      title: operation === "remove_stop" ? "固定地点不可删除" : "固定地点不可移动",
      detail: `${target.name} 被识别为保护项：${target.protectionReasons.join("、")}。`,
      relatedStopIds: [target.id],
    });
  } else {
    findings.push({
      key: `flexible-${target.id}`,
      severity: "ok",
      title: "目标地点可调整",
      detail: `${target.name} 没有固定时间或锁定来源。`,
      relatedStopIds: [target.id],
    });
  }
  return findings;
}

function chooseRelaxationCandidate(stops: ReplanStopRef[]): ReplanStopRef | null {
  const flexible = stops.filter((stop) => !stop.isProtected && stop.type !== "hotel");
  if (flexible.length === 0) {
    return null;
  }
  return [...flexible].sort((a, b) => scoreRelaxCandidate(b) - scoreRelaxCandidate(a))[0] ?? null;
}

function scoreRelaxCandidate(stop: ReplanStopRef): number {
  let score = stop.travelDurationSeconds ?? 0;
  if (stop.sourceType === "auto_filled") {
    score += 2400;
  }
  if (stop.sourceType?.includes("auto_seeded")) {
    score += 900;
  }
  if (stop.type === "restaurant") {
    score -= 1200;
  }
  return score;
}

function inferBusiestDay(stops: ReplanStopRef[]): number {
  const counts = new Map<number, number>();
  for (const stop of stops) {
    counts.set(stop.day, (counts.get(stop.day) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? 1;
}

function removeStopFromDays(
  days: ReplanItineraryLike["days"],
  stopId: string,
): { days: ReplanItineraryLike["days"]; stop: ReplanStopRef | null } {
  let removedStop: ReplanStopRef | null = null;
  const nextDays = days.map((day) => ({
    ...day,
    blocks: day.blocks.map((block) => ({
      ...block,
      items: block.items.filter((item, index) => {
        const ref = buildLocalStopRef(day.day, block.block_type, index, item);
        if (ref.id === stopId) {
          removedStop = ref;
          return false;
        }
        return true;
      }),
    })),
  }));
  return { days: nextDays, stop: removedStop };
}

function moveStopInDays(
  days: ReplanItineraryLike["days"],
  stopId: string,
  targetDay: number,
  targetBlockType: ReplanBlockType,
): { days: ReplanItineraryLike["days"] } {
  let movingItem: ReplanScheduledItemLike | null = null;
  const withoutMovingItem = days.map((day) => ({
    ...day,
    blocks: day.blocks.map((block) => ({
      ...block,
      items: block.items.filter((item, index) => {
        const ref = buildLocalStopRef(day.day, block.block_type, index, item);
        if (ref.id === stopId) {
          movingItem = {
            ...item,
            day: targetDay,
            travel_from_name: null,
            travel_distance_m: null,
            travel_duration_s: null,
            placement_reason: buildLocalMoveReason(item, targetDay, targetBlockType),
          };
          return false;
        }
        return true;
      }),
    })),
  }));

  if (!movingItem) {
    return { days };
  }

  return {
    days: withoutMovingItem.map((day) =>
      day.day === targetDay
        ? {
            ...day,
            blocks: day.blocks.map((block) =>
              block.block_type === targetBlockType
                ? {
                    ...block,
                    items: [...block.items, movingItem as ReplanScheduledItemLike],
                  }
                : block,
            ),
          }
        : day,
    ),
  };
}

function buildLocalStopRef(
  day: number,
  blockType: ReplanBlockType,
  index: number,
  item: ReplanScheduledItemLike,
): ReplanStopRef {
  return buildStopRef(day, blockType, index, item);
}

function buildLocalMoveReason(
  item: ReplanScheduledItemLike,
  targetDay: number,
  targetBlockType: ReplanBlockType,
): string {
  const original = item.placement_reason ? `${item.placement_reason} ` : "";
  return `${original}用户通过 conversational replan 将这一站移动到第 ${targetDay} 天${formatBlockLabel(targetBlockType)}；路线段需重新刷新。`;
}

function patchIntentForLocalMutation<TItinerary extends ReplanItineraryLike>(
  itinerary: TItinerary,
  plan: ReplanMutationPlan,
  removedStops: ReplanStopRef[],
): TItinerary {
  if (removedStops.length === 0) {
    return appendLocalReplanNote(itinerary, plan);
  }

  return updateCurrentIntent(itinerary, (intent) => {
    let nextIntent = { ...intent };
    for (const stop of removedStops) {
      nextIntent = removeStopFromIntent(nextIntent, stop);
    }
    return {
      ...nextIntent,
      notes: [
        ...(nextIntent.notes ?? []),
        `Conversational replan: ${plan.title}。已从 regeneration brief 中排除被移除地点，避免下次重排重新带回。`,
      ],
    };
  });
}

function appendLocalReplanNote<TItinerary extends ReplanItineraryLike>(
  itinerary: TItinerary,
  plan: ReplanMutationPlan,
): TItinerary {
  return updateCurrentIntent(itinerary, (intent) => ({
    ...intent,
    notes: [...(intent.notes ?? []), `Conversational replan: ${plan.title}。`],
  }));
}

function updateCurrentIntent<TItinerary extends ReplanItineraryLike>(
  itinerary: TItinerary,
  update: (intent: ReplanIntentLike) => ReplanIntentLike,
): TItinerary {
  const currentIntent =
    itinerary.trip_intent?.current_intent ??
    itinerary.planning_assumptions?.regeneration_intent ??
    null;
  if (!currentIntent) {
    return itinerary;
  }
  const nextIntent = update(currentIntent);
  return {
    ...itinerary,
    trip_intent: itinerary.trip_intent
      ? {
          ...itinerary.trip_intent,
          current_intent: nextIntent,
          summary_lines: [
            ...(itinerary.trip_intent.summary_lines ?? []),
            ...(nextIntent.notes ?? []).slice(-1),
          ].slice(-8),
        }
      : itinerary.trip_intent,
    planning_assumptions: itinerary.planning_assumptions
      ? {
          ...itinerary.planning_assumptions,
          regeneration_intent: nextIntent,
        }
      : itinerary.planning_assumptions,
  };
}

function removeStopFromIntent(intent: ReplanIntentLike, stop: ReplanStopRef): ReplanIntentLike {
  const semanticKey = buildSemanticStopKey(stop);
  const removeByKey = (values: string[] | undefined) =>
    (values ?? []).filter((value) => `${normalizeStopName(value)}::${stop.type}` !== semanticKey);
  const addRejected = (values: string[] | undefined) =>
    uniqueStrings([...(values ?? []), stop.name]);
  if (stop.type === "restaurant") {
    return {
      ...intent,
      flexible_restaurants: removeByKey(intent.flexible_restaurants),
      carry_forward_restaurants: removeByKey(intent.carry_forward_restaurants),
      auto_seeded_restaurants: removeByKey(intent.auto_seeded_restaurants),
      rejected_restaurants: addRejected(intent.rejected_restaurants),
    };
  }
  if (stop.type === "scenic") {
    return {
      ...intent,
      flexible_scenic_spots: removeByKey(intent.flexible_scenic_spots),
      carry_forward_scenic_spots: removeByKey(intent.carry_forward_scenic_spots),
      auto_seeded_scenic_spots: removeByKey(intent.auto_seeded_scenic_spots),
      rejected_scenic_spots: addRejected(intent.rejected_scenic_spots),
    };
  }
  return intent;
}

function buildProtectedBoundaryImpactItems(): ReplanImpactItem[] {
  return [
    {
      key: "fixed-boundaries",
      tone: "protect",
      title: "保护固定约束",
      detail: "固定事件、锁定地点、酒店/到离站锚点不会被局部 mutation 改写。",
    },
  ];
}

function uniqueStops(stops: ReplanStopRef[]): ReplanStopRef[] {
  const seen = new Set<string>();
  return stops.filter((stop) => {
    if (seen.has(stop.id)) {
      return false;
    }
    seen.add(stop.id);
    return true;
  });
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values));
}

function buildPlanId(text: string, intentKind: ReplanIntentKind, parts: string[]): string {
  return [
    intentKind,
    normalizeStopName(text).slice(0, 30),
    ...parts.map((part) => normalizeStopName(part).slice(0, 24)),
  ].join("--");
}
