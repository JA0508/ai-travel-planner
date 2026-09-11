"use client";

export type TripReadinessStatus = "ready" | "minor-gaps" | "needs-attention" | "not-ready";

export type ReadinessIssue = {
  key: string;
  source: "realism" | "completion" | "score" | "fallback";
  title: string;
  reason: string;
  impact: string;
  scope?: string;
  severity: "low" | "medium" | "high";
};

export type TripReadinessAction =
  | { kind: "focus-day"; day: number; label: string }
  | { kind: "open-completion"; label: string }
  | { kind: "review-route"; label: string };

export type ProtectedBoundary = {
  key: string;
  label: string;
  detail: string;
};

export type TripReadinessViewModel = {
  status: TripReadinessStatus;
  statusLabel: string;
  headline: string;
  summary: string;
  primaryIssue?: ReadinessIssue;
  secondaryIssues: ReadinessIssue[];
  protectedBoundaries: ProtectedBoundary[];
  priorityAction: TripReadinessAction;
  confidenceLabel: string;
  metrics: Array<{
    label: string;
    value: string;
    tone: "good" | "watch" | "risk" | "neutral";
  }>;
};

type PlannerRealismIssueLike = {
  code?: string;
  severity?: "low" | "medium" | "high" | string;
  title?: string;
  detail?: string;
  day?: number | null;
};

type PlannerRealismLike = {
  status?: "executable" | "needs_repair" | "unstable" | string;
  headline?: string | null;
  issues?: PlannerRealismIssueLike[] | null;
};

type CompletionTaskLike = {
  task_id?: string;
  task_instance_key?: string | null;
  title: string;
  reason: string;
  action_prompt?: string;
  priority?: "high" | "medium" | "low" | string;
};

type CompletionScoreBreakdownLike = {
  density?: number;
  meals?: number;
  evening?: number;
  transport_boundary?: number;
};

type CompletionIntelligenceLike = {
  trip_completeness?: number | null;
  score_breakdown?: CompletionScoreBreakdownLike | null;
  action_tasks?: CompletionTaskLike[] | null;
  sparse_blocks_detected?: string[] | null;
  auto_filled_scenic_count?: number | null;
  auto_filled_meal_count?: number | null;
  auto_filled_evening_count?: number | null;
  auto_fill_attempted?: boolean;
  auto_fill_blocked_reasons?: string[] | null;
  stay_area_recommendation?: string | null;
  departure_hub_recommendation?: string | null;
  why_this_plan_works?: string[] | null;
};

type BoundaryExplanationLike = {
  arrival_anchor_influenced?: boolean;
  arrival_anchor_name?: string | null;
  departure_anchor_influenced?: boolean;
  departure_anchor_name?: string | null;
};

type PlanningAssumptionsLike = {
  fixed_event_count?: number | null;
  availability_window_count?: number | null;
  summary_lines?: string[] | null;
};

type DayLike = {
  day: number;
  blocks: Array<{
    block_type: string;
    items: unknown[];
  }>;
};

export type BuildTripReadinessViewModelInput = {
  city: string;
  tripDays: number;
  completion?: CompletionIntelligenceLike | null;
  plannerRealism?: PlannerRealismLike | null;
  boundaryExplanation?: BoundaryExplanationLike | null;
  planningAssumptions?: PlanningAssumptionsLike | null;
  days: DayLike[];
};

export function buildTripReadinessViewModel({
  city,
  tripDays,
  completion,
  plannerRealism,
  boundaryExplanation,
  planningAssumptions,
  days,
}: BuildTripReadinessViewModelInput): TripReadinessViewModel {
  const completeness = clampPercent(completion?.trip_completeness);
  const sparseBlocks = completion?.sparse_blocks_detected ?? [];
  const tasks = completion?.action_tasks ?? [];
  const realismIssues = plannerRealism?.issues ?? [];
  const issues = [
    ...buildRealismIssues(realismIssues),
    ...buildCompletionIssues(tasks, sparseBlocks),
    ...buildScoreBreakdownIssues(completion?.score_breakdown ?? null),
    ...buildFallbackDensityIssues(days),
  ];
  const sortedIssues = sortIssues(issues);
  const protectedBoundaries = buildProtectedBoundaries(boundaryExplanation, planningAssumptions);
  const highRisk = sortedIssues.some((issue) => issue.severity === "high");
  const mediumRiskCount = sortedIssues.filter((issue) => issue.severity === "medium").length;
  const lowRiskCount = sortedIssues.filter((issue) => issue.severity === "low").length;
  const status = deriveReadinessStatus({
    completeness,
    plannerStatus: plannerRealism?.status,
    highRisk,
    mediumRiskCount,
    lowRiskCount,
    sparseBlockCount: sparseBlocks.length,
    taskCount: tasks.length,
  });
  const primaryIssue = sortedIssues[0];
  const autoFilledCount =
    (completion?.auto_filled_scenic_count ?? 0) +
    (completion?.auto_filled_meal_count ?? 0) +
    (completion?.auto_filled_evening_count ?? 0);

  return {
    status,
    statusLabel: statusLabel(status),
    headline: buildHeadline(status, plannerRealism?.headline, city, tripDays),
    summary: buildSummary(status, primaryIssue, completion),
    primaryIssue,
    secondaryIssues: sortedIssues.slice(1, 4),
    protectedBoundaries,
    priorityAction: buildPriorityAction(primaryIssue, tasks.length),
    confidenceLabel: buildConfidenceLabel(completion, plannerRealism, planningAssumptions),
    metrics: [
      {
        label: "完整度",
        value: completeness === null ? "未评分" : `${completeness}%`,
        tone: completeness === null ? "neutral" : completeness >= 88 ? "good" : completeness >= 72 ? "watch" : "risk",
      },
      {
        label: "待处理",
        value: `${tasks.length}`,
        tone: tasks.length === 0 ? "good" : tasks.some((task) => task.priority === "high") ? "risk" : "watch",
      },
      {
        label: "已补入",
        value: `${autoFilledCount}`,
        tone: autoFilledCount > 0 ? "good" : "neutral",
      },
    ],
  };
}

function deriveReadinessStatus({
  completeness,
  plannerStatus,
  highRisk,
  mediumRiskCount,
  lowRiskCount,
  sparseBlockCount,
  taskCount,
}: {
  completeness: number | null;
  plannerStatus?: string;
  highRisk: boolean;
  mediumRiskCount: number;
  lowRiskCount: number;
  sparseBlockCount: number;
  taskCount: number;
}): TripReadinessStatus {
  if (plannerStatus === "unstable" || highRisk) {
    return "not-ready";
  }
  if (
    plannerStatus === "needs_repair" ||
    (completeness !== null && completeness < 72) ||
    sparseBlockCount >= 3 ||
    mediumRiskCount >= 2
  ) {
    return "needs-attention";
  }
  if (
    (completeness !== null && completeness < 88) ||
    sparseBlockCount > 0 ||
    taskCount > 0 ||
    lowRiskCount > 0
  ) {
    return "minor-gaps";
  }
  return "ready";
}

function buildRealismIssues(issues: PlannerRealismIssueLike[]): ReadinessIssue[] {
  return issues.map((issue, index) => ({
    key: `realism-${issue.code ?? index}`,
    source: "realism",
    title: issue.title ?? "路线现实性需要确认",
    reason: issue.detail ?? "调度器发现当前安排可能影响真实执行。",
    impact: issue.severity === "high" ? "可能阻止直接照走" : "会影响当天节奏和路线可信度",
    scope: issue.day ? `Day ${issue.day}` : "整条路线",
    severity: normalizeSeverity(issue.severity),
  }));
}

function buildCompletionIssues(tasks: CompletionTaskLike[], sparseBlocks: string[]): ReadinessIssue[] {
  const taskIssues = tasks.slice(0, 4).map((task, index) => ({
    key: `completion-${task.task_instance_key ?? task.task_id ?? index}`,
    source: "completion" as const,
    title: normalizeSentence(task.title),
    reason: normalizeSentence(task.reason),
    impact: task.priority === "high" ? "优先处理后，路线更接近可执行版本" : "处理后可提升行程连贯性",
    scope: inferScope(`${task.title} ${task.reason} ${task.action_prompt ?? ""}`),
    severity: normalizeSeverity(task.priority),
  }));

  if (taskIssues.length > 0 || sparseBlocks.length === 0) {
    return taskIssues;
  }

  return [
    {
      key: "completion-sparse-blocks",
      source: "completion",
      title: "存在未补齐时间段",
      reason: sparseBlocks.slice(0, 3).join("、"),
      impact: "用户出行时会遇到需要临时决策的空白段",
      scope: "时间线",
      severity: sparseBlocks.length >= 3 ? "medium" : "low",
    },
  ];
}

function buildScoreBreakdownIssues(score: CompletionScoreBreakdownLike | null): ReadinessIssue[] {
  if (!score) {
    return [];
  }
  const rows = [
    ["density", "行程密度偏低", score.density, "部分游玩时段还不够成形。"],
    ["meals", "餐食结构不稳", score.meals, "午餐或晚餐还没有成为清晰节奏锚点。"],
    ["evening", "夜间安排偏弱", score.evening, "晚上可能缺少可执行的收口安排。"],
    ["transport", "交通边界待确认", score.transport_boundary, "到达、离开或跨点移动仍需要注意。"],
  ] as const;

  return rows.flatMap(([key, title, value, reason]) => {
    if (typeof value !== "number" || value >= 68) {
      return [];
    }
    return [{
      key: `score-${key}`,
      source: "score",
      title,
      reason,
      impact: "补齐这个维度可以提高路线可执行性",
      scope: `${value}%`,
      severity: value < 52 ? "high" : "medium",
    }];
  });
}

function buildFallbackDensityIssues(days: DayLike[]): ReadinessIssue[] {
  return days
    .filter((day) => day.blocks.reduce((sum, block) => sum + block.items.length, 0) <= 1)
    .slice(0, 2)
    .map((day) => ({
      key: `fallback-density-day-${day.day}`,
      source: "fallback" as const,
      title: `Day ${day.day} 内容偏少`,
      reason: "当前天的已排停留点很少，可能需要用户临时补决定。",
      impact: "适合优先查看补全建议或确认是否刻意留白",
      scope: `Day ${day.day}`,
      severity: "low",
    }));
}

function buildProtectedBoundaries(
  boundaryExplanation?: BoundaryExplanationLike | null,
  planningAssumptions?: PlanningAssumptionsLike | null,
): ProtectedBoundary[] {
  const boundaries: ProtectedBoundary[] = [];
  const fixedCount = planningAssumptions?.fixed_event_count ?? 0;
  if (fixedCount > 0) {
    boundaries.push({
      key: "fixed-events",
      label: "固定安排",
      detail: `${fixedCount} 个固定时间点不会被补全任务覆盖。`,
    });
  }
  if (boundaryExplanation?.arrival_anchor_influenced) {
    boundaries.push({
      key: "arrival-anchor",
      label: "到达边界",
      detail: `${boundaryExplanation.arrival_anchor_name ?? "到达点"} 已影响第一天起步节奏。`,
    });
  }
  if (boundaryExplanation?.departure_anchor_influenced) {
    boundaries.push({
      key: "departure-anchor",
      label: "离开边界",
      detail: `${boundaryExplanation.departure_anchor_name ?? "离开点"} 已影响最后一天收口。`,
    });
  }
  if ((planningAssumptions?.availability_window_count ?? 0) > 0) {
    boundaries.push({
      key: "availability",
      label: "可用时间",
      detail: "已按用户给出的可用时间窗口裁剪日程。",
    });
  }
  if (boundaries.length === 0) {
    boundaries.push({
      key: "planner-rules",
      label: "调度边界",
      detail: "固定点、时间窗和路线现实性仍由确定性调度层保护。",
    });
  }
  return boundaries.slice(0, 4);
}

function buildHeadline(
  status: TripReadinessStatus,
  realismHeadline: string | null | undefined,
  city: string,
  tripDays: number,
): string {
  if (realismHeadline) {
    return realismHeadline;
  }
  if (status === "ready") {
    return `${city} ${tripDays} 天路线已经形成可执行骨架。`;
  }
  if (status === "minor-gaps") {
    return "路线可以先照着看，但还有少量信息缺口。";
  }
  if (status === "needs-attention") {
    return "这条路线需要先处理关键空缺再出行。";
  }
  return "当前路线暂不建议直接照走。";
}

function buildSummary(
  status: TripReadinessStatus,
  primaryIssue: ReadinessIssue | undefined,
  completion?: CompletionIntelligenceLike | null,
): string {
  if (primaryIssue) {
    return `${primaryIssue.scope ? `${primaryIssue.scope}：` : ""}${primaryIssue.reason}`;
  }
  const why = completion?.why_this_plan_works?.[0];
  if (why) {
    return why;
  }
  if (status === "ready") {
    return "没有发现明显路线现实性风险或高优先级补全任务。";
  }
  return "系统已经生成路线骨架，但后端没有返回更细的 readiness 证据。";
}

function buildPriorityAction(
  primaryIssue: ReadinessIssue | undefined,
  taskCount: number,
): TripReadinessAction {
  if (primaryIssue?.source === "realism" && primaryIssue.scope) {
    const day = dayFromScope(primaryIssue.scope);
    if (day !== null) {
      return { kind: "focus-day", day, label: `查看 Day ${day} 路线` };
    }
  }
  if (primaryIssue) {
    return { kind: "open-completion", label: `先处理：${primaryIssue.title}` };
  }
  if (taskCount > 0) {
    return { kind: "open-completion", label: "先查看最高优先级补全建议" };
  }
  return { kind: "review-route", label: "进入地图和时间线做最后检查" };
}

function dayFromScope(scope: string): number | null {
  const match = scope.match(/^Day\s+(\d+)$/);
  return match ? Number(match[1]) : null;
}

function buildConfidenceLabel(
  completion?: CompletionIntelligenceLike | null,
  plannerRealism?: PlannerRealismLike | null,
  planningAssumptions?: PlanningAssumptionsLike | null,
): string {
  const evidenceCount = [
    completion?.score_breakdown,
    completion?.why_this_plan_works?.length,
    plannerRealism?.issues,
    planningAssumptions?.summary_lines?.length,
  ].filter(Boolean).length;
  if (evidenceCount >= 3) {
    return "依据充分：补全、现实性和边界信息均已返回";
  }
  if (evidenceCount >= 1) {
    return "依据部分返回：可继续查看地图与时间线确认";
  }
  return "依据有限：当前只按已排时间线做前端 fallback 判断";
}

function sortIssues(issues: ReadinessIssue[]): ReadinessIssue[] {
  const weight = { high: 3, medium: 2, low: 1 };
  return [...issues].sort((left, right) => weight[right.severity] - weight[left.severity]);
}

function normalizeSeverity(value?: string): ReadinessIssue["severity"] {
  if (value === "high") {
    return "high";
  }
  if (value === "medium") {
    return "medium";
  }
  return "low";
}

function statusLabel(status: TripReadinessStatus): string {
  if (status === "ready") {
    return "路线已就绪";
  }
  if (status === "minor-gaps") {
    return "可参考，仍有空缺";
  }
  if (status === "needs-attention") {
    return "需要先处理";
  }
  return "暂不建议照走";
}

function clampPercent(value?: number | null): number | null {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return null;
  }
  return Math.max(0, Math.min(100, Math.round(value)));
}

function normalizeSentence(value: string): string {
  return value.trim().replace(/^Task type:\s*/i, "");
}

function inferScope(text: string): string | undefined {
  const match = text.match(/(?:第\s*)?(\d+)\s*(?:天|day)/i);
  return match ? `Day ${match[1]}` : undefined;
}
