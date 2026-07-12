import type {
  EditableRouteDay,
  EditableRouteStop,
  ItineraryLike,
  ScheduledItemLike,
  TimelineBlockType,
  TimelineItemType,
} from "@/components/trip/MobileEditRouteWorkspace";

export const ROUTE_WORKSPACE_BLOCK_ORDER: TimelineBlockType[] = [
  "morning",
  "afternoon",
  "evening",
];

export function buildEditableRouteDays(itinerary: ItineraryLike): EditableRouteDay[] {
  return itinerary.days.map((day) => {
    let originalIndex = 0;
    const stops = day.blocks.flatMap((block) =>
      block.items.map((item, index) => {
        const stop: EditableRouteStop = {
          id: buildEditableStopId(day.day, block.block_type, item, index),
          day: day.day,
          originalDay: day.day,
          originalIndex,
          originalIsFixed: item.is_fixed,
          blockType: block.block_type,
          originalBlockType: block.block_type,
          item,
        };
        originalIndex += 1;
        return stop;
      }),
    );
    return {
      day: day.day,
      label: `DAY ${day.day}`,
      originalStopCount: stops.length,
      stops,
    };
  });
}

export function insertPendingStop(
  days: EditableRouteDay[],
  targetDay: number,
  targetBlockType: TimelineBlockType,
  name: string,
  type: TimelineItemType,
): EditableRouteDay[] {
  return days.map((day) => {
    if (day.day !== targetDay) {
      return day;
    }

    const stop = buildManualPendingStop(targetDay, targetBlockType, name, type);
    const insertionIndex = buildBlockInsertionIndex(day.stops, targetBlockType);
    const nextStops = [...day.stops];
    nextStops.splice(insertionIndex, 0, stop);
    return { ...day, stops: nextStops };
  });
}

export function buildManualPendingStop(
  day: number,
  blockType: TimelineBlockType,
  name: string,
  type: TimelineItemType,
): EditableRouteStop {
  const blockTime = getBlockDefaultTime(blockType);
  return {
    id: buildManualStopId(day, blockType, name),
    day,
    originalDay: -1,
    originalIndex: -1,
    originalIsFixed: false,
    blockType,
    originalBlockType: blockType,
    item: {
      name,
      type,
      start_time: blockTime.start,
      end_time: blockTime.end,
      is_fixed: false,
      placement_reason: "你在编辑路线时手动插入了这个待规划点，下一次补全会把它作为当前计划的一部分继续处理。",
      source_type: "user_seed",
      source_label: "手动插入",
      source_reason: "来自路线编辑器里的插入动作。",
      travel_from_name: null,
      travel_distance_m: null,
      travel_duration_s: null,
    },
  };
}

export function insertExistingStop(
  days: EditableRouteDay[],
  stop: EditableRouteStop,
): EditableRouteDay[] {
  return days.map((day) => {
    if (day.day !== stop.day) {
      return day;
    }
    const insertionIndex = buildBlockInsertionIndex(day.stops, stop.blockType);
    const nextStops = [...day.stops];
    nextStops.splice(insertionIndex, 0, stop);
    return { ...day, stops: nextStops };
  });
}

export function toggleRouteStopLock(stop: EditableRouteStop): EditableRouteStop {
  if (isRouteEditLockedStop(stop)) {
    return {
      ...stop,
      item: {
        ...stop.item,
        is_fixed: false,
        source_type: stop.item.source_type === "user_fixed" ? "user_seed" : stop.item.source_type,
        source_label: null,
        source_reason: "你在编辑路线里取消了这个地点的锁定。",
      },
    };
  }

  if (stop.item.is_fixed && !isRouteEditLockedStop(stop)) {
    return stop;
  }

  return {
    ...stop,
    item: {
      ...stop.item,
      is_fixed: true,
      source_type: "user_fixed",
      source_label: "已锁定",
      source_reason: "你在编辑路线里锁定了这个地点，下一次生成会把它作为固定路线意图带入。",
    },
  };
}

export function reorderStops(
  stops: EditableRouteStop[],
  fromId: string,
  toId: string,
): EditableRouteStop[] {
  const fromIndex = stops.findIndex((stop) => stop.id === fromId);
  const toIndex = stops.findIndex((stop) => stop.id === toId);
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) {
    return stops;
  }
  const next = [...stops];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

export function moveStopAcrossTimeline(
  days: EditableRouteDay[],
  stopId: string,
  targetDay: number,
  targetBlockType: TimelineBlockType,
): EditableRouteDay[] {
  let movedStop: EditableRouteStop | null = null;
  const strippedDays = days.map((day) => {
    const index = day.stops.findIndex((stop) => stop.id === stopId);
    if (index < 0) {
      return day;
    }
    const nextStops = [...day.stops];
    const [removed] = nextStops.splice(index, 1);
    movedStop = {
      ...removed,
      day: targetDay,
      blockType: targetBlockType,
    };
    return { ...day, stops: nextStops };
  });

  if (!movedStop) {
    return days;
  }

  const finalMovedStop = movedStop;

  return strippedDays.map((day) => {
    if (day.day !== targetDay) {
      return day;
    }
    const insertionIndex = buildBlockInsertionIndex(day.stops, targetBlockType);
    const nextStops = [...day.stops];
    nextStops.splice(insertionIndex, 0, finalMovedStop);
    return { ...day, stops: nextStops };
  });
}

export function buildBlockInsertionIndex(
  stops: EditableRouteStop[],
  targetBlockType: TimelineBlockType,
): number {
  const targetOrder = ROUTE_WORKSPACE_BLOCK_ORDER.indexOf(targetBlockType);
  let insertionIndex = stops.length;
  for (let index = 0; index < stops.length; index += 1) {
    const stopOrder = ROUTE_WORKSPACE_BLOCK_ORDER.indexOf(stops[index].blockType);
    if (stopOrder > targetOrder) {
      insertionIndex = index;
      break;
    }
    if (stopOrder === targetOrder) {
      insertionIndex = index + 1;
    }
  }
  return insertionIndex;
}

export function sameReferenceList<T>(left: T[], right: T[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

export function buildRouteStopSelector(stopId: string): string {
  const escape =
    typeof window !== "undefined" && window.CSS && typeof window.CSS.escape === "function"
      ? window.CSS.escape
      : (value: string) => value.replace(/["\\]/g, "\\$&");
  return `[data-route-stop-id="${escape(stopId)}"]`;
}

function buildEditableStopId(
  day: number,
  blockType: TimelineBlockType,
  item: ScheduledItemLike,
  index: number,
): string {
  return `${day}-${blockType}-${item.name}-${item.start_time}-${item.end_time}-${index}`;
}

function buildManualStopId(
  day: number,
  blockType: TimelineBlockType,
  name: string,
): string {
  return `manual-${day}-${blockType}-${name}-${Date.now()}`;
}

export function isRouteEditLockedStop(stop: EditableRouteStop): boolean {
  return stop.item.source_label === "已锁定" || stop.item.source_reason?.includes("编辑路线里锁定") === true;
}

function getBlockDefaultTime(blockType: TimelineBlockType): { start: string; end: string } {
  if (blockType === "morning") {
    return { start: "09:00:00", end: "10:15:00" };
  }
  if (blockType === "afternoon") {
    return { start: "13:00:00", end: "14:15:00" };
  }
  return { start: "18:00:00", end: "19:15:00" };
}
