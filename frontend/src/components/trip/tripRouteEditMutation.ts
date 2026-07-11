"use client";

type TimelineItemType = "scenic" | "restaurant" | "hotel";
type TimelineBlockType = "morning" | "afternoon" | "evening";

type ScheduledItemLike = {
  name: string;
  type: TimelineItemType;
  latitude?: number | null;
  longitude?: number | null;
  day?: number;
  start_time: string;
  end_time: string;
  is_fixed: boolean;
  placement_reason: string | null;
  source_type?:
    | "user_seed"
    | "user_fixed"
    | "auto_seeded_poi"
    | "auto_seeded_meal"
    | "auto_filled";
  source_label?: string | null;
  source_reason?: string | null;
  travel_from_name: string | null;
  travel_distance_m: number | null;
  travel_duration_s: number | null;
  poi_research?: {
    overview: string;
    access_tip: string;
    practical_tip: string;
    best_for: string;
    source: string;
  } | null;
  local_edit?: {
    previous_name: string;
    source: "completion_recommendation";
    status: "committed";
    reasoning_summary: string;
    itinerary_relation_summary: string;
    original_type: TimelineItemType;
    original_placement_reason?: string | null;
    original_source_type?: ScheduledItemLike["source_type"];
    original_source_label?: string | null;
    original_source_reason?: string | null;
  } | null;
};

type DayBlockLike = {
  block_type: TimelineBlockType;
  start_time: string;
  end_time: string;
  items: ScheduledItemLike[];
};

type DayAvailabilitySummaryLike = {
  was_trimmed: boolean;
  effective_start: string | null;
  effective_end: string | null;
  remaining_blocks: Array<{
    block_type: TimelineBlockType;
    start_time: string;
    end_time: string;
  }>;
};

type DayItineraryLike = {
  day: number;
  availability_summary?: DayAvailabilitySummaryLike;
  blocks: DayBlockLike[];
};

type EditableRouteStopLike = {
  id: string;
  day: number;
  originalDay: number;
  originalIndex: number;
  originalIsFixed?: boolean;
  blockType: TimelineBlockType;
  originalBlockType: TimelineBlockType;
  item: ScheduledItemLike;
};

type EditableRouteDayLike = {
  day: number;
  label: string;
  originalStopCount?: number;
  stops: EditableRouteStopLike[];
};

type RoutePreviewMapLike = Record<
  string,
  {
    distance_m: number;
    duration_s: number;
  }
>;

type ItineraryLike = {
  planning_anchor_source: {
    source_type: string;
    source_name: string;
  };
  days: DayItineraryLike[];
};

const BLOCK_ORDER: TimelineBlockType[] = ["morning", "afternoon", "evening"];

export function hasEditedRouteChanges(
  days: EditableRouteDayLike[],
  unplannedStops: EditableRouteStopLike[] = [],
): boolean {
  if (unplannedStops.length > 0) {
    return true;
  }
  return days.some((day) =>
    day.stops.length !== (day.originalStopCount ?? day.stops.length) ||
      day.stops.some(
        (stop, index) =>
          stop.originalDay < 0 ||
          stop.day !== stop.originalDay ||
          stop.blockType !== stop.originalBlockType ||
          stop.originalDay !== day.day ||
          stop.originalIndex !== index ||
          stop.item.is_fixed !== (stop.originalIsFixed ?? stop.item.is_fixed) ||
          stop.item.source_reason?.includes("编辑路线") === true,
      ),
  );
}

export function applyRouteEditsToItinerary<TItinerary extends ItineraryLike>(
  itinerary: TItinerary,
  editedDays: EditableRouteDayLike[],
  routePreviewMap: RoutePreviewMapLike = {},
): TItinerary {
  const routeOrigins = buildRouteOrigins(itinerary, editedDays);

  return {
    ...itinerary,
    days: itinerary.days.map((day) => {
      const editedDay = editedDays.find((entry) => entry.day === day.day);
      if (!editedDay) {
        return day;
      }

      const blockMap = new Map(day.blocks.map((block) => [block.block_type, block]));
      const routeOrigin = routeOrigins.get(day.day) ?? itinerary.planning_anchor_source.source_name;

      const nextBlocks = BLOCK_ORDER.map((blockType) => {
        const baseBlock = blockMap.get(blockType);
        if (!baseBlock) {
          return null;
        }

        const blockStops = editedDay.stops.filter((stop) => stop.blockType === blockType);
        const nextItems = blockStops.map((stop, index) =>
          buildPatchedScheduledItem(
            stop,
            index > 0 ? blockStops[index - 1] : null,
            routeOrigin,
            day.day,
            routePreviewMap,
          ),
        );

        return {
          ...baseBlock,
          items: nextItems,
        };
      }).filter((block): block is DayBlockLike => block !== null);

      return {
        ...day,
        blocks: nextBlocks,
      };
    }),
  };
}

function buildRouteOrigins(
  itinerary: ItineraryLike,
  editedDays: EditableRouteDayLike[],
): Map<number, string> {
  const origins = new Map<number, string>();
  let currentOrigin = itinerary.planning_anchor_source.source_name;

  for (const day of editedDays) {
    origins.set(day.day, currentOrigin);
    currentOrigin = day.stops.at(-1)?.item.name ?? currentOrigin;
  }

  return origins;
}

function buildPatchedScheduledItem(
  stop: EditableRouteStopLike,
  previousStop: EditableRouteStopLike | null,
  routeOrigin: string,
  targetDay: number,
  routePreviewMap: RoutePreviewMapLike,
): ScheduledItemLike {
  const routeChanged = hasStopRouteChanged(stop, previousStop, targetDay);
  const nextTravelFromName = previousStop ? previousStop.item.name : routeOrigin;
  const originalReason = stop.item.local_edit?.original_placement_reason ?? stop.item.placement_reason;
  const estimatedSegment = previousStop
    ? estimateRouteSegment(previousStop.item, stop.item)
    : null;
  const previewSegment = previousStop
    ? routePreviewMap[buildRouteSegmentKey(previousStop, stop)]
    : null;

  if (!routeChanged) {
    return {
      ...stop.item,
      day: targetDay,
    };
  }

  return {
    ...stop.item,
    day: targetDay,
    travel_from_name: nextTravelFromName,
    travel_distance_m: previewSegment?.distance_m ?? estimatedSegment?.distanceMeters ?? null,
    travel_duration_s: previewSegment?.duration_s ?? estimatedSegment?.durationSeconds ?? null,
    placement_reason: buildEditedPlacementReason(stop, previousStop, originalReason),
  };
}

function hasStopRouteChanged(
  stop: EditableRouteStopLike,
  previousStop: EditableRouteStopLike | null,
  targetDay: number,
): boolean {
  if (stop.day !== stop.originalDay || stop.blockType !== stop.originalBlockType) {
    return true;
  }

  if (targetDay !== stop.originalDay) {
    return true;
  }

  if (!previousStop) {
    return stop.originalIndex !== 0;
  }

  return (
    previousStop.day !== previousStop.originalDay ||
    previousStop.blockType !== previousStop.originalBlockType ||
    previousStop.originalDay !== stop.originalDay ||
    stop.originalIndex !== previousStop.originalIndex + 1
  );
}

function buildEditedPlacementReason(
  stop: EditableRouteStopLike,
  previousStop: EditableRouteStopLike | null,
  originalReason: string | null,
): string {
  const editSummary =
    stop.day !== stop.originalDay && stop.blockType !== stop.originalBlockType
      ? `你把这一站从第 ${stop.originalDay} 天的${formatBlockLabel(stop.originalBlockType)}挪到了第 ${stop.day} 天的${formatBlockLabel(stop.blockType)}。`
      : stop.day !== stop.originalDay
        ? `你把这一站从第 ${stop.originalDay} 天挪到了第 ${stop.day} 天。`
        : stop.blockType !== stop.originalBlockType
          ? `你把这一站改到了${formatBlockLabel(stop.blockType)}。`
          : previousStop
            ? "你手动调整了这一天的路线顺序。"
            : "你手动调整了这一天的起点顺序。";

  if (originalReason) {
    return `${editSummary} 当前衔接会以下一次规划结果为准。原始安排原因：${originalReason}`;
  }

  return `${editSummary} 当前衔接会以下一次规划结果为准。`;
}

function estimateRouteSegment(
  fromItem: ScheduledItemLike,
  toItem: ScheduledItemLike,
): { distanceMeters: number; durationSeconds: number } | null {
  if (
    typeof fromItem.latitude !== "number" ||
    typeof fromItem.longitude !== "number" ||
    typeof toItem.latitude !== "number" ||
    typeof toItem.longitude !== "number"
  ) {
    return null;
  }

  const directDistanceMeters = haversineDistanceMeters(
    fromItem.latitude,
    fromItem.longitude,
    toItem.latitude,
    toItem.longitude,
  );
  if (!Number.isFinite(directDistanceMeters) || directDistanceMeters <= 0) {
    return null;
  }

  const walkingDistanceMeters = Math.round(directDistanceMeters * 1.35);
  const walkingMetersPerSecond = 1.15;
  return {
    distanceMeters: walkingDistanceMeters,
    durationSeconds: Math.max(300, Math.round(walkingDistanceMeters / walkingMetersPerSecond)),
  };
}

function haversineDistanceMeters(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const earthRadiusMeters = 6371000;
  const toRadians = (value: number) => (value * Math.PI) / 180;
  const dLat = toRadians(lat2 - lat1);
  const dLon = toRadians(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRadians(lat1)) *
      Math.cos(toRadians(lat2)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  return earthRadiusMeters * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function buildRouteSegmentKey(
  fromStop: EditableRouteStopLike,
  toStop: EditableRouteStopLike,
): string {
  return `${fromStop.id}->${toStop.id}`;
}

function formatBlockLabel(blockType: TimelineBlockType): string {
  if (blockType === "morning") {
    return "上午";
  }
  if (blockType === "afternoon") {
    return "下午";
  }
  return "晚上";
}
