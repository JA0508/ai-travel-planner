import type {
  RoutePreviewItinerary,
  RoutePreviewItem,
} from "./routePreviewModel";

export type LocalRepairImpact = {
  action: "move" | "remove" | "replace" | "shorten";
  stop_id?: string;
  stop_name: string;
  from_day: number;
  to_day?: number | null;
  ownership?: "system_suggested" | string;
  protected?: {
    fixed_mutations?: number;
    must_moves?: number;
    must_deletions?: number;
    full_planner_calls?: number;
  };
};

export type RepairRouteItem = {
  id: string;
  name: string;
  startTime: string;
  endTime: string;
  changed: boolean;
  fixed: boolean;
  mustVisit: boolean;
  travelFromName: string | null;
  travelDurationSeconds: number | null;
  travelDistanceMeters: number | null;
  travelConfirmed: boolean;
};

export type RepairRouteSection = {
  day: number;
  items: RepairRouteItem[];
};

export type ProtectedRepairItem = {
  id: string;
  name: string;
  day: number;
  time: string;
  reason: "你明确说想去" | "已经留好的时间，不会被移动";
};

export type RepairPreviewModel = {
  affectedDays: number[];
  beforeSections: RepairRouteSection[];
  afterSections: RepairRouteSection[];
  change: {
    action: LocalRepairImpact["action"];
    stopName: string;
    fromDay: number;
    toDay: number | null;
  };
  protectedItems: ProtectedRepairItem[];
  quantitativeImpact: {
    activityDelta: number | null;
    travelMinutesSaved: number | null;
  };
  reason: string;
};

type LocatedItem = {
  day: number;
  item: RoutePreviewItem;
};

export function buildRepairPreviewModel(
  before: RoutePreviewItinerary,
  after: RoutePreviewItinerary,
  targetDay: number,
  impact: LocalRepairImpact,
): RepairPreviewModel {
  const beforeItems = flattenItems(before);
  const afterItems = flattenItems(after);
  const changedStableId = findChangedStableId(beforeItems, afterItems, impact);
  const affectedDays = [...new Set([
    targetDay,
    impact.from_day,
    impact.to_day,
  ].filter((day): day is number => typeof day === "number"))].sort((left, right) => left - right);
  const displaySections = buildDisplaySections(
    beforeItems,
    afterItems,
    impact,
    changedStableId,
  );

  return {
    affectedDays,
    beforeSections: displaySections.before,
    afterSections: displaySections.after,
    change: {
      action: impact.action,
      stopName: impact.stop_name,
      fromDay: impact.from_day,
      toDay: impact.to_day ?? null,
    },
    protectedItems: buildProtectedItems(beforeItems, afterItems),
    quantitativeImpact: buildQuantitativeImpact(before, after, targetDay),
    reason: buildReason(impact),
  };
}

export function repairFailureMessage(
  code: string | undefined,
  phase: "preview" | "apply" | "undo",
): string {
  if (isRepairStaleCode(code)) {
    if (phase === "undo") {
      return "路线刚刚发生了变化。这次撤销没有保存。请载入最新路线确认当前安排。";
    }
    return "路线刚刚发生了变化。这次调整没有保存，原路线保持不变。请基于最新版本重新看看调整建议。";
  }
  if (phase === "preview") return "暂时找不到一个安全的小调整。原路线不会被改变。";
  if (phase === "apply") return "这次调整没有保存。你的原路线仍然保持不变。";
  return "暂时无法撤销这次调整。当前保存的路线没有改变。";
}

export function undoRevisionReceipt(
  kind: "relax_day" | "replace_stop",
  revisionNumber: number,
): string {
  if (kind === "replace_stop") {
    return `已撤销这次替换，并保存为新版本 ${revisionNumber}。原来的地点和相邻路线已恢复。`;
  }
  return `已撤销这次调整，并保存为新版本 ${revisionNumber}。调整前的路线已恢复。`;
}

export function latestRouteReloadReceipt(
  kind: "relax_day" | "replace_stop",
  revisionNumber: number,
): string {
  if (kind === "replace_stop") {
    return `已载入最新保存版本 ${revisionNumber}；没有应用刚才的替换。请基于这版路线重新选择地点。`;
  }
  return `已载入最新保存版本 ${revisionNumber}；没有应用刚才的调整。请基于这版路线重新查看当天是否仍然太赶。`;
}

export function latestRouteReloadActionLabel(retry: boolean): string {
  return retry ? "重新载入最新路线" : "载入最新路线";
}

export function isRepairStaleCode(code: string | undefined): boolean {
  return [
    "stale_base_revision",
    "stale_mutation_proposal",
    "mutation_proposal_expired",
    "mutation_proposal_invalidated",
    "undo_target_not_current",
  ].includes(code ?? "");
}

function flattenItems(itinerary: RoutePreviewItinerary): LocatedItem[] {
  return itinerary.days.flatMap((day) =>
    day.blocks.flatMap((block) => block.items.map((item) => ({ day: day.day, item }))),
  );
}

function findChangedStableId(
  beforeItems: LocatedItem[],
  afterItems: LocatedItem[],
  impact: LocalRepairImpact,
): string | null {
  const candidates = beforeItems.filter(
    (entry) => entry.day === impact.from_day && entry.item.name === impact.stop_name,
  );
  const source = impact.stop_id
    ? candidates.find((entry) => entry.item.stable_id === impact.stop_id)
    : candidates.length === 1
      ? candidates[0]
      : candidates.find((entry) => {
          if (!entry.item.stable_id) return false;
          const destination = afterItems.find((candidate) => candidate.item.stable_id === entry.item.stable_id);
          return impact.action === "remove"
            ? !destination
            : impact.action === "move" && destination?.day === (impact.to_day ?? null);
        });
  if (!source?.item.stable_id) return null;
  const destination = afterItems.find((entry) => entry.item.stable_id === source.item.stable_id);
  if (impact.action === "remove") return destination ? null : source.item.stable_id;
  if (impact.action === "move" && destination?.day === (impact.to_day ?? null)) return source.item.stable_id;
  return source.item.stable_id;
}

function buildDisplaySections(
  beforeItems: LocatedItem[],
  afterItems: LocatedItem[],
  impact: LocalRepairImpact,
  changedStableId: string | null,
): { before: RepairRouteSection[]; after: RepairRouteSection[] } {
  const sourceItems = beforeItems.filter((entry) => entry.day === impact.from_day);
  const changedIndex = sourceItems.findIndex((entry) => isChangedEntry(entry, impact, changedStableId));
  const context = changedIndex >= 0
    ? sourceItems.slice(Math.max(0, changedIndex - 1), changedIndex + 2)
    : sourceItems.slice(0, 3);
  const contextIds = new Set(context.map(entryIdentity));
  const afterSource = afterItems.filter(
    (entry) => entry.day === impact.from_day && contextIds.has(entryIdentity(entry)),
  );
  const before = [{ day: impact.from_day, items: context.map((entry) => toRouteItem(entry, impact, changedStableId)) }];
  const after: RepairRouteSection[] = [{
    day: impact.from_day,
    items: afterSource.map((entry) => toRouteItem(entry, impact, changedStableId)),
  }];
  if (impact.to_day && impact.to_day !== impact.from_day) {
    const moved = afterItems.filter(
      (entry) => entry.day === impact.to_day && isChangedEntry(entry, impact, changedStableId),
    );
    if (moved.length) {
      after.push({
        day: impact.to_day,
        items: moved.map((entry) => toRouteItem(entry, impact, changedStableId)),
      });
    }
  }
  return { before, after };
}

function toRouteItem(
  entry: LocatedItem,
  impact: LocalRepairImpact,
  changedStableId: string | null,
): RepairRouteItem {
  const { item } = entry;
  return {
    id: entryIdentity(entry),
    name: item.name,
    startTime: item.start_time,
    endTime: item.end_time,
    changed: isChangedEntry(entry, impact, changedStableId),
    fixed: item.is_fixed,
    mustVisit: item.source_label === "必去",
    travelFromName: item.travel_from_name ?? null,
    travelDurationSeconds: item.travel_duration_s ?? null,
    travelDistanceMeters: item.travel_distance_m ?? null,
    travelConfirmed: item.travel_data_status === "confirmed" && item.travel_duration_s != null,
  };
}

function isChangedEntry(
  entry: LocatedItem,
  impact: LocalRepairImpact,
  changedStableId: string | null,
): boolean {
  return changedStableId ? entry.item.stable_id === changedStableId : false;
}

function entryIdentity(entry: LocatedItem): string {
  return entry.item.stable_id ?? `${entry.day}:${entry.item.name}:${entry.item.start_time}`;
}

function buildProtectedItems(
  beforeItems: LocatedItem[],
  afterItems: LocatedItem[],
): ProtectedRepairItem[] {
  return beforeItems.flatMap((entry) => {
    const stableId = entry.item.stable_id;
    const protectedKind = entry.item.is_fixed
      ? "fixed"
      : entry.item.source_label === "必去"
        ? "must"
        : null;
    if (!stableId || !protectedKind) return [];
    const after = afterItems.find((candidate) => candidate.item.stable_id === stableId);
    if (!after || !samePlacement(entry, after)) return [];
    return [{
      id: stableId,
      name: entry.item.name,
      day: entry.day,
      time: entry.item.start_time,
      reason: protectedKind === "fixed"
        ? "已经留好的时间，不会被移动" as const
        : "你明确说想去" as const,
    }];
  });
}

function samePlacement(before: LocatedItem, after: LocatedItem): boolean {
  return before.day === after.day
    && before.item.name === after.item.name
    && before.item.start_time === after.item.start_time
    && before.item.end_time === after.item.end_time
    && before.item.is_fixed === after.item.is_fixed;
}

function buildQuantitativeImpact(
  before: RoutePreviewItinerary,
  after: RoutePreviewItinerary,
  targetDay: number,
): RepairPreviewModel["quantitativeImpact"] {
  const beforeLoad = before.planner_realism?.daily_loads?.find((load) => load.day === targetDay);
  const afterLoad = after.planner_realism?.daily_loads?.find((load) => load.day === targetDay);
  if (!beforeLoad || !afterLoad) {
    return { activityDelta: null, travelMinutesSaved: null };
  }
  const activityDelta = beforeLoad.activity_count - afterLoad.activity_count;
  const travelMinutesSaved = beforeLoad.travel_minutes - afterLoad.travel_minutes;
  return {
    activityDelta: activityDelta > 0 ? activityDelta : null,
    travelMinutesSaved: travelMinutesSaved > 0 ? travelMinutesSaved : null,
  };
}

function buildReason(impact: LocalRepairImpact): string {
  const stopOrigin = impact.ownership === "system_suggested"
    ? "是系统补充的停留点"
    : "是这次可调整的停留点";
  if (impact.action === "move" && impact.to_day) {
    return `“${impact.stop_name}”${stopOrigin}。这次只把它挪到第 ${impact.to_day} 天，给第 ${impact.from_day} 天留出更多余量。`;
  }
  if (impact.action === "remove") {
    return `“${impact.stop_name}”${stopOrigin}。拿掉这一次停留后，当天会留出更多余量。`;
  }
  if (impact.action === "replace") {
    return `这次只替换“${impact.stop_name}”所在的一段，其他已确认安排按原位置保留。`;
  }
  return `这次只缩短“${impact.stop_name}”所在的一段，其他已确认安排按原位置保留。`;
}
