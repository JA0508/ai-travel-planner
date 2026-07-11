"use client";

import type {
  ReplanBlockType,
  ReplanChange,
  ReplanChangeSet,
  ReplanItineraryLike,
  ReplanItemType,
  ReplanScheduledItemLike,
  ReplanStopRef,
} from "./replanTypes";

const BLOCK_LABELS: Record<ReplanBlockType, string> = {
  morning: "上午",
  afternoon: "下午",
  evening: "晚上",
};

export function buildStopRefs(itinerary: ReplanItineraryLike): ReplanStopRef[] {
  return itinerary.days.flatMap((day) =>
    day.blocks.flatMap((block) =>
      block.items.map((item, index) =>
        buildStopRef(day.day, block.block_type, index, item),
      ),
    ),
  );
}

export function buildItineraryChangeSet(
  before: ReplanItineraryLike,
  after: ReplanItineraryLike,
): ReplanChangeSet {
  const beforeStops = buildStopRefs(before);
  const afterStops = buildStopRefs(after);
  const beforeByKey = new Map(beforeStops.map((stop) => [buildSemanticStopKey(stop), stop]));
  const afterByKey = new Map(afterStops.map((stop) => [buildSemanticStopKey(stop), stop]));

  const removed: ReplanChange[] = [];
  const added: ReplanChange[] = [];
  const moved: ReplanChange[] = [];
  const retimed: ReplanChange[] = [];
  const routeChanged: ReplanChange[] = [];

  for (const beforeStop of beforeStops) {
    const afterStop = afterByKey.get(buildSemanticStopKey(beforeStop));
    if (!afterStop) {
      removed.push({
        key: `removed-${beforeStop.id}`,
        kind: "removed",
        title: `移除 ${beforeStop.name}`,
        detail: `原位于第 ${beforeStop.day} 天${beforeStop.blockLabel}。`,
        stopName: beforeStop.name,
        before: beforeStop,
      });
      continue;
    }
    if (beforeStop.day !== afterStop.day || beforeStop.blockType !== afterStop.blockType) {
      moved.push({
        key: `moved-${beforeStop.id}`,
        kind: "moved",
        title: `移动 ${beforeStop.name}`,
        detail: `从第 ${beforeStop.day} 天${beforeStop.blockLabel}调整到第 ${afterStop.day} 天${afterStop.blockLabel}。`,
        stopName: beforeStop.name,
        before: beforeStop,
        after: afterStop,
      });
    }
    if (
      beforeStop.startTime !== afterStop.startTime ||
      beforeStop.endTime !== afterStop.endTime
    ) {
      retimed.push({
        key: `retimed-${beforeStop.id}`,
        kind: "retimed",
        title: `时间变化 ${beforeStop.name}`,
        detail: `${beforeStop.startTime}-${beforeStop.endTime} -> ${afterStop.startTime}-${afterStop.endTime}`,
        stopName: beforeStop.name,
        before: beforeStop,
        after: afterStop,
      });
    }
    if (
      beforeStop.travelDurationSeconds !== afterStop.travelDurationSeconds ||
      beforeStop.travelDistanceMeters !== afterStop.travelDistanceMeters
    ) {
      routeChanged.push({
        key: `route-${beforeStop.id}`,
        kind: "route_changed",
        title: `路线段变化 ${beforeStop.name}`,
        detail: "前序交通距离或时长发生变化，已标记为需要路线表面刷新。",
        stopName: beforeStop.name,
        before: beforeStop,
        after: afterStop,
      });
    }
  }

  for (const afterStop of afterStops) {
    if (!beforeByKey.has(buildSemanticStopKey(afterStop))) {
      added.push({
        key: `added-${afterStop.id}`,
        kind: "added",
        title: `新增 ${afterStop.name}`,
        detail: `位于第 ${afterStop.day} 天${afterStop.blockLabel}。`,
        stopName: afterStop.name,
        after: afterStop,
      });
    }
  }

  return {
    added,
    removed,
    moved,
    retimed,
    routeChanged,
    summary: buildChangeSummary({ added, removed, moved, retimed, routeChanged }),
  };
}

export function buildSemanticStopKey(stop: Pick<ReplanStopRef, "name" | "type">): string {
  return `${normalizeStopName(stop.name)}::${stop.type}`;
}

export function buildStopRef(
  day: number,
  blockType: ReplanBlockType,
  index: number,
  item: ReplanScheduledItemLike,
): ReplanStopRef {
  const protectionReasons = getProtectionReasons(item);
  return {
    id: buildStableStopId(day, blockType, index, item),
    day,
    blockType,
    blockLabel: BLOCK_LABELS[blockType],
    index,
    name: item.name,
    type: item.type,
    startTime: item.start_time,
    endTime: item.end_time,
    isProtected: protectionReasons.length > 0,
    protectionReasons,
    sourceType: item.source_type ?? null,
    travelDurationSeconds: item.travel_duration_s,
    travelDistanceMeters: item.travel_distance_m,
  };
}

export function normalizeStopName(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, "");
}

function getProtectionReasons(item: ReplanScheduledItemLike): string[] {
  const reasons: string[] = [];
  if (item.is_fixed) {
    reasons.push("固定时间");
  }
  if (item.source_type === "user_fixed") {
    reasons.push("用户硬约束");
  }
  if (item.source_label?.includes("锁定")) {
    reasons.push(item.source_label);
  }
  if (item.source_reason?.includes("锁定") || item.source_reason?.includes("固定")) {
    reasons.push("来源说明包含锁定/固定");
  }
  return unique(reasons);
}

function buildStableStopId(
  day: number,
  blockType: ReplanBlockType,
  index: number,
  item: Pick<ReplanScheduledItemLike, "name" | "type" | "start_time" | "end_time">,
): string {
  return [
    day,
    blockType,
    index,
    item.type,
    normalizeStopName(item.name),
    item.start_time,
    item.end_time,
  ].join("__");
}

function buildChangeSummary(changeSet: Omit<ReplanChangeSet, "summary">): string {
  const parts = [
    changeSet.added.length > 0 ? `${changeSet.added.length} 个新增` : null,
    changeSet.removed.length > 0 ? `${changeSet.removed.length} 个移除` : null,
    changeSet.moved.length > 0 ? `${changeSet.moved.length} 个移动` : null,
    changeSet.retimed.length > 0 ? `${changeSet.retimed.length} 个时间变化` : null,
    changeSet.routeChanged.length > 0 ? `${changeSet.routeChanged.length} 个路线段变化` : null,
  ].filter((part): part is string => Boolean(part));
  return parts.length > 0 ? parts.join("，") : "没有检测到可见行程变化";
}

function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}

export function formatBlockLabel(blockType: ReplanBlockType): string {
  return BLOCK_LABELS[blockType];
}

export function formatItemType(type: ReplanItemType): string {
  if (type === "restaurant") {
    return "餐食";
  }
  if (type === "hotel") {
    return "住宿";
  }
  return "景点";
}
