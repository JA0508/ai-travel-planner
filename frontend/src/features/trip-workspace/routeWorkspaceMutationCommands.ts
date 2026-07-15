import type {
  EditableRouteDay,
  EditableRouteStop,
  ItineraryLike,
  TimelineBlockType,
} from "@/components/trip/MobileEditRouteWorkspace";

type RouteEditCommand =
  | {
      type: "remove_stop";
      stop_id: string;
    }
  | {
      type: "move_stop";
      stop_id: string;
      target_day: number;
      target_block: TimelineBlockType;
      placement: StopPlacement;
    }
  | {
      type: "reorder_day";
      day: number;
      ordered_stop_ids: string[];
    };

type StopPlacement =
  | { before_stop_id: string }
  | { after_stop_id: string }
  | { at_end: true };

export type TripMutationCommandEnvelope =
  | {
      schema_version: "1.0";
      base_revision_id: string;
      mutation_kind: "route_edit";
      commands: RouteEditCommand[];
    }
  | {
      schema_version: "1.0";
      base_revision_id: string;
      mutation_kind: "swap";
      commands: Array<{
        type: "replace_stop";
        stop_id: string;
        replacement: {
          name: string;
          type: "scenic" | "restaurant";
          reasoning_summary: string;
          itinerary_relation_summary: string;
        };
      }>;
    };

type SwapTargetLike = {
  stable_id?: string | null;
};

type SwapOptionLike = {
  name: string;
  type: "scenic" | "restaurant";
  reasoning_summary: string;
  itinerary_relation_summary: string;
};

export function buildRouteEditCommandEnvelope(
  itinerary: ItineraryLike,
  baseRevisionId: string,
  editedDays: EditableRouteDay[],
  unplannedStops: EditableRouteStop[] = [],
): TripMutationCommandEnvelope | null {
  if (unplannedStops.length > 0) {
    return null;
  }
  const originalIdsByDay = buildOriginalIdsByDay(itinerary);
  const finalIdsByDay = buildFinalIdsByDay(editedDays);
  if (!originalIdsByDay || !finalIdsByDay) {
    return null;
  }

  const commands: RouteEditCommand[] = [];
  const originalIds = new Set([...originalIdsByDay.values()].flat());
  const finalIds = new Set([...finalIdsByDay.values()].flat());
  for (const stopId of originalIds) {
    if (!finalIds.has(stopId)) {
      commands.push({ type: "remove_stop", stop_id: stopId });
    }
  }

  for (const stop of editedDays.flatMap((day) => day.stops)) {
    const stopId = stop.item.stable_id;
    if (!stopId || stop.originalDay < 1) {
      return null;
    }
    if (stop.day === stop.originalDay && stop.blockType === stop.originalBlockType) {
      continue;
    }
    const placement = buildPlacement(stop, editedDays);
    if (!placement) {
      return null;
    }
    commands.push({
      type: "move_stop",
      stop_id: stopId,
      target_day: stop.day,
      target_block: stop.blockType,
      placement,
    });
  }

  for (const [day, finalIds] of finalIdsByDay.entries()) {
    if (finalIds.length === 0) {
      continue;
    }
    const originalIds = originalIdsByDay.get(day) ?? [];
    if (!sameStringList(originalIds, finalIds)) {
      commands.push({ type: "reorder_day", day, ordered_stop_ids: finalIds });
    }
  }

  if (commands.length === 0) {
    return null;
  }
  return {
    schema_version: "1.0",
    base_revision_id: baseRevisionId,
    mutation_kind: "route_edit",
    commands,
  };
}

export function buildSwapReplaceCommandEnvelope(
  baseRevisionId: string,
  target: SwapTargetLike,
  option: SwapOptionLike,
): TripMutationCommandEnvelope | null {
  if (!target.stable_id) {
    return null;
  }
  return {
    schema_version: "1.0",
    base_revision_id: baseRevisionId,
    mutation_kind: "swap",
    commands: [
      {
        type: "replace_stop",
        stop_id: target.stable_id,
        replacement: {
          name: option.name,
          type: option.type,
          reasoning_summary: option.reasoning_summary,
          itinerary_relation_summary: option.itinerary_relation_summary,
        },
      },
    ],
  };
}

function buildOriginalIdsByDay(itinerary: ItineraryLike): Map<number, string[]> | null {
  const result = new Map<number, string[]>();
  for (const day of itinerary.days) {
    const ids: string[] = [];
    for (const block of day.blocks) {
      for (const item of block.items) {
        if (!item.stable_id) {
          return null;
        }
        ids.push(item.stable_id);
      }
    }
    result.set(day.day, ids);
  }
  return result;
}

function buildFinalIdsByDay(editedDays: EditableRouteDay[]): Map<number, string[]> | null {
  const result = new Map<number, string[]>();
  for (const day of editedDays) {
    const ids: string[] = [];
    for (const stop of day.stops) {
      if (!stop.item.stable_id) {
        return null;
      }
      ids.push(stop.item.stable_id);
    }
    result.set(day.day, ids);
  }
  return result;
}

function buildPlacement(
  stop: EditableRouteStop,
  editedDays: EditableRouteDay[],
): StopPlacement | null {
  const targetDay = editedDays.find((day) => day.day === stop.day);
  if (!targetDay) {
    return null;
  }
  const sameBlockStops = targetDay.stops.filter((entry) => entry.blockType === stop.blockType);
  const index = sameBlockStops.findIndex((entry) => entry.item.stable_id === stop.item.stable_id);
  if (index < 0) {
    return null;
  }
  const next = sameBlockStops[index + 1]?.item.stable_id;
  if (next) {
    return { before_stop_id: next };
  }
  const previous = sameBlockStops[index - 1]?.item.stable_id;
  if (previous) {
    return { after_stop_id: previous };
  }
  return { at_end: true };
}

function sameStringList(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}
