"use client";

import {
  buildUserConfirmedReplacementFromSwap,
  type CommittedSwapLike,
  type UserConfirmedReplacementLike,
} from "@/components/trip/tripSwapState";
import {
  normalizeComparisonName,
  uniquePreserveOrder,
} from "@/components/trip/tripSwapPolicy";

type ReplaceablePoiType = "scenic" | "restaurant";

type RegenerationIntentLike = {
  city: string | null;
  trip_days: number | null;
  suggested_trip_days: number;
  trip_days_basis: string;
  fixed_events: unknown[];
  availability_windows: unknown[];
  flexible_scenic_spots: string[];
  flexible_restaurants: string[];
  auto_seeded_scenic_spots: string[];
  auto_seeded_restaurants: string[];
  carry_forward_scenic_spots: string[];
  carry_forward_restaurants: string[];
  rejected_scenic_spots: string[];
  rejected_restaurants: string[];
  confirmed_replacements: UserConfirmedReplacementLike<string>[];
  notes: string[];
};

type TripIntentCompileSummaryLike = {
  city: string | null;
  trip_days_mode: string;
  scenic_seed_count: number;
  restaurant_seed_count: number;
  fixed_event_count: number;
  availability_window_count: number;
  rejected_poi_count: number;
  confirmed_replacement_count: number;
  needs_auto_completion: boolean;
  summary_lines: string[];
};

type ItineraryWithTripIntent<TIntent extends RegenerationIntentLike> = {
  trip_intent?: {
    current_intent: TIntent;
    compile_summary?: TripIntentCompileSummaryLike | null;
    summary_lines: string[];
  } | null;
  planning_assumptions: {
    regeneration_intent: TIntent | null;
  } | null;
};

type GenerationContextLike = {
  scenic_spots: string[];
  restaurants: string[];
};

type CompletionTaskIntentItemLike = {
  name: string;
  type: "scenic" | "restaurant" | "hotel";
};

type RouteEditedStopLike = {
  day: number;
  blockType: "morning" | "afternoon" | "evening";
  item: {
    name: string;
    type: "scenic" | "restaurant" | "hotel";
    start_time: string;
    end_time: string;
    is_fixed: boolean;
    source_reason?: string | null;
  };
  originalIsFixed?: boolean;
};

type RouteEditedDayLike = {
  day: number;
  stops: RouteEditedStopLike[];
};

export function applySwapToTripIntentEnvelope<
  TItinerary extends ItineraryWithTripIntent<TIntent>,
  TIntent extends RegenerationIntentLike,
>(itinerary: TItinerary, swap: CommittedSwapLike): TItinerary {
  return updateItineraryTripIntent(itinerary, (intent) =>
    applySwapToRegenerationIntent(intent, swap),
  );
}

export function undoSwapFromTripIntentEnvelope<
  TItinerary extends ItineraryWithTripIntent<TIntent>,
  TIntent extends RegenerationIntentLike,
>(itinerary: TItinerary, swap: CommittedSwapLike): TItinerary {
  return updateItineraryTripIntent(itinerary, (intent) =>
    undoSwapFromRegenerationIntent(intent, swap),
  );
}

export function applyCompletionTaskItemToTripIntentEnvelope<
  TItinerary extends ItineraryWithTripIntent<TIntent>,
  TIntent extends RegenerationIntentLike,
>(itinerary: TItinerary, item: CompletionTaskIntentItemLike): TItinerary {
  return updateItineraryTripIntent(itinerary, (intent) =>
    applyCompletionTaskItemToRegenerationIntent(intent, item),
  );
}

export function undoCompletionTaskItemFromTripIntentEnvelope<
  TItinerary extends ItineraryWithTripIntent<TIntent>,
  TIntent extends RegenerationIntentLike,
>(itinerary: TItinerary, item: CompletionTaskIntentItemLike): TItinerary {
  return updateItineraryTripIntent(itinerary, (intent) =>
    undoCompletionTaskItemFromRegenerationIntent(intent, item),
  );
}

export function applyRouteEditsToTripIntentEnvelope<
  TItinerary extends ItineraryWithTripIntent<TIntent>,
  TIntent extends RegenerationIntentLike,
>(
  itinerary: TItinerary,
  editedDays: RouteEditedDayLike[],
  unplannedStops: RouteEditedStopLike[] = [],
): TItinerary {
  return updateItineraryTripIntent(itinerary, (intent) =>
    applyRouteEditsToRegenerationIntent(intent, editedDays, unplannedStops),
  );
}

function updateItineraryTripIntent<
  TItinerary extends ItineraryWithTripIntent<TIntent>,
  TIntent extends RegenerationIntentLike,
>(
  itinerary: TItinerary,
  updateIntent: (intent: TIntent) => TIntent,
): TItinerary {
  const currentIntent =
    itinerary.trip_intent?.current_intent ??
    itinerary.planning_assumptions?.regeneration_intent ??
    null;
  if (!currentIntent) {
    return itinerary;
  }

  const nextIntent = updateIntent(currentIntent);
  const nextTripIntent = itinerary.trip_intent
    ? {
        ...itinerary.trip_intent,
        current_intent: nextIntent,
        compile_summary: buildLocalTripIntentCompileSummary(nextIntent),
        summary_lines: uniquePreserveOrder([
          ...itinerary.trip_intent.summary_lines,
          ...nextIntent.notes,
        ]).slice(0, 8),
      }
    : itinerary.trip_intent;
  const nextPlanningAssumptions = itinerary.planning_assumptions
    ? {
        ...itinerary.planning_assumptions,
        regeneration_intent: nextIntent,
      }
    : itinerary.planning_assumptions;

  return {
    ...itinerary,
    trip_intent: nextTripIntent,
    planning_assumptions: nextPlanningAssumptions,
  };
}

export function buildLocalTripIntentCompileSummary(
  intent: RegenerationIntentLike,
): TripIntentCompileSummaryLike {
  const scenicSeedCount = intent.carry_forward_scenic_spots.length;
  const restaurantSeedCount = intent.carry_forward_restaurants.length;
  const rejectedPoiCount =
    intent.rejected_scenic_spots.length + intent.rejected_restaurants.length;
  const confirmedReplacementCount = intent.confirmed_replacements.length;
  const targetSeedCount = Math.max(intent.suggested_trip_days * 2, 1);
  const needsAutoCompletion =
    scenicSeedCount === 0 ||
    restaurantSeedCount === 0 ||
    scenicSeedCount + restaurantSeedCount < targetSeedCount;

  const summaryLines = [
    `当前 brief 会带着 ${scenicSeedCount} 个景点种子和 ${restaurantSeedCount} 个餐食种子重新生成。`,
    intent.trip_days !== null
      ? `行程天数已固定为 ${intent.trip_days} 天。`
      : `行程天数仍保持弹性，下一次可沿用当前 ${intent.suggested_trip_days} 天的可执行范围。`,
  ];

  if (intent.fixed_events.length > 0 || intent.availability_windows.length > 0) {
    summaryLines.push(
      `${intent.fixed_events.length} 个固定事件和 ${intent.availability_windows.length} 段可用时间会继续作为时间约束。`,
    );
  }
  if (rejectedPoiCount > 0 || confirmedReplacementCount > 0) {
    summaryLines.push(
      `${confirmedReplacementCount} 个已确认替换会被当成用户意图，${rejectedPoiCount} 个被换掉的点会被降权/排除。`,
    );
  }
  summaryLines.push(
    needsAutoCompletion
      ? "当前输入仍偏稀疏，系统会继续自动补齐能跑起来的空档。"
      : "当前计划已经有足够用户确认的点，下一版会更偏向用户自己塑形的路线。",
  );

  return {
    city: intent.city,
    trip_days_mode:
      intent.trip_days !== null ? "explicit" : intent.trip_days_basis || "flexible",
    scenic_seed_count: scenicSeedCount,
    restaurant_seed_count: restaurantSeedCount,
    fixed_event_count: intent.fixed_events.length,
    availability_window_count: intent.availability_windows.length,
    rejected_poi_count: rejectedPoiCount,
    confirmed_replacement_count: confirmedReplacementCount,
    needs_auto_completion: needsAutoCompletion,
    summary_lines: summaryLines,
  };
}

export function applyCompletionTaskItemToRegenerationIntent<
  TIntent extends RegenerationIntentLike,
>(intent: TIntent, item: CompletionTaskIntentItemLike): TIntent {
  const poiType = completionTaskItemToPoiType(item);
  if (!poiType) {
    return intent;
  }

  return addPoiToRegenerationIntent(
    intent,
    item.name,
    poiType,
    `User accepted completion task item: ${item.name}. Future regeneration treats it as user-owned trip skeleton intent.`,
  );
}

export function undoCompletionTaskItemFromRegenerationIntent<
  TIntent extends RegenerationIntentLike,
>(intent: TIntent, item: CompletionTaskIntentItemLike): TIntent {
  const poiType = completionTaskItemToPoiType(item);
  if (!poiType) {
    return intent;
  }

  return {
    ...removePoiFromRegenerationIntent(intent, item.name, poiType),
    notes: uniquePreserveOrder([
      `User undid accepted completion task item: ${item.name}. Future regeneration should not carry it as confirmed trip skeleton intent.`,
      ...intent.notes,
    ]),
  };
}

export function applyRouteEditsToRegenerationIntent<TIntent extends RegenerationIntentLike>(
  intent: TIntent,
  editedDays: RouteEditedDayLike[],
  unplannedStops: RouteEditedStopLike[] = [],
): TIntent {
  const orderedPois = buildOrderedPoisFromEditedDays(editedDays, unplannedStops);
  const activeScenic = new Set(orderedPois.scenic.map(normalizeComparisonName));
  const activeRestaurants = new Set(orderedPois.restaurants.map(normalizeComparisonName));

  return {
    ...intent,
    flexible_scenic_spots: orderedPois.scenic,
    flexible_restaurants: orderedPois.restaurants,
    fixed_events: buildFixedEventsWithRouteLocks(intent.fixed_events, editedDays),
    carry_forward_scenic_spots: orderedPois.scenic,
    carry_forward_restaurants: orderedPois.restaurants,
    rejected_scenic_spots: (intent.rejected_scenic_spots ?? []).filter(
      (name) => !activeScenic.has(normalizeComparisonName(name)),
    ),
    rejected_restaurants: (intent.rejected_restaurants ?? []).filter(
      (name) => !activeRestaurants.has(normalizeComparisonName(name)),
    ),
    notes: uniquePreserveOrder([
      "用户手动调整了当前旅行骨架顺序。后续再生成应把已编辑的景点与餐食顺序作为新的行程 brief 基线。",
      ...intent.notes,
    ]),
  };
}

export function applySwapToRegenerationIntent<TIntent extends RegenerationIntentLike>(
  intent: TIntent,
  swap: CommittedSwapLike,
): TIntent {
  const note = `用户确认替换：${swap.original_name} -> ${swap.replacement_name}。后续再生成应把 ${swap.replacement_name} 视为用户已接受意图，并降低 ${swap.original_name} 的优先级。`;
  const nextIntent = addPoiToRegenerationIntent(
    removePoiFromRegenerationIntent(intent, swap.original_name, swap.original_type),
    swap.replacement_name,
    swap.replacement_type,
    note,
  );
  const rejectedField =
    swap.original_type === "restaurant" ? "rejected_restaurants" : "rejected_scenic_spots";
  return {
    ...nextIntent,
    [rejectedField]: uniquePreserveOrder([
      ...(nextIntent[rejectedField] ?? []),
      swap.original_name,
    ]),
    confirmed_replacements: upsertUserConfirmedReplacement(
      nextIntent.confirmed_replacements ?? [],
      buildUserConfirmedReplacementFromSwap(swap),
    ),
  };
}

export function undoSwapFromRegenerationIntent<TIntent extends RegenerationIntentLike>(
  intent: TIntent,
  swap: CommittedSwapLike,
): TIntent {
  const note = `User undid replacement: ${swap.replacement_name} -> ${swap.original_name}. Future regeneration can consider the original stop again.`;
  const nextIntent = addPoiToRegenerationIntent(
    removePoiFromRegenerationIntent(intent, swap.replacement_name, swap.replacement_type),
    swap.original_name,
    swap.original_type,
    note,
  );
  const rejectedField =
    swap.original_type === "restaurant" ? "rejected_restaurants" : "rejected_scenic_spots";
  return {
    ...nextIntent,
    [rejectedField]: (nextIntent[rejectedField] ?? []).filter(
      (name) => normalizeComparisonName(name) !== normalizeComparisonName(swap.original_name),
    ),
    confirmed_replacements: (nextIntent.confirmed_replacements ?? []).filter(
      (replacement) =>
        normalizeComparisonName(replacement.original_name) !==
          normalizeComparisonName(swap.original_name) ||
        normalizeComparisonName(replacement.replacement_name) !==
          normalizeComparisonName(swap.replacement_name),
    ),
  };
}

function upsertUserConfirmedReplacement<TReplacement extends UserConfirmedReplacementLike<string>>(
  current: TReplacement[],
  next: TReplacement,
): TReplacement[] {
  return [
    ...current.filter(
      (replacement) =>
        normalizeComparisonName(replacement.original_name) !==
          normalizeComparisonName(next.original_name) ||
        normalizeComparisonName(replacement.replacement_name) !==
          normalizeComparisonName(next.replacement_name),
    ),
    next,
  ];
}

function removePoiFromRegenerationIntent<TIntent extends RegenerationIntentLike>(
  intent: TIntent,
  poiName: string,
  poiType: ReplaceablePoiType,
): TIntent {
  const removeByName = (values: string[]) =>
    values.filter((value) => normalizeComparisonName(value) !== normalizeComparisonName(poiName));

  if (poiType === "restaurant") {
    return {
      ...intent,
      flexible_restaurants: removeByName(intent.flexible_restaurants),
      auto_seeded_restaurants: removeByName(intent.auto_seeded_restaurants),
      carry_forward_restaurants: removeByName(intent.carry_forward_restaurants),
    };
  }

  return {
    ...intent,
    flexible_scenic_spots: removeByName(intent.flexible_scenic_spots),
    auto_seeded_scenic_spots: removeByName(intent.auto_seeded_scenic_spots),
    carry_forward_scenic_spots: removeByName(intent.carry_forward_scenic_spots),
  };
}

function addPoiToRegenerationIntent<TIntent extends RegenerationIntentLike>(
  intent: TIntent,
  poiName: string,
  poiType: ReplaceablePoiType,
  note: string,
): TIntent {
  if (poiType === "restaurant") {
    return {
      ...intent,
      flexible_restaurants: uniquePreserveOrder([...intent.flexible_restaurants, poiName]),
      carry_forward_restaurants: uniquePreserveOrder([...intent.carry_forward_restaurants, poiName]),
      notes: uniquePreserveOrder([note, ...intent.notes]),
    };
  }

  return {
    ...intent,
    flexible_scenic_spots: uniquePreserveOrder([...intent.flexible_scenic_spots, poiName]),
    carry_forward_scenic_spots: uniquePreserveOrder([...intent.carry_forward_scenic_spots, poiName]),
    notes: uniquePreserveOrder([note, ...intent.notes]),
  };
}

export function applySwapToGenerationContext<TContext extends GenerationContextLike>(
  context: TContext,
  swap: CommittedSwapLike,
): TContext {
  return addPoiToGenerationContext(
    removePoiFromGenerationContext(context, swap.original_name, swap.original_type),
    swap.replacement_name,
    swap.replacement_type,
  );
}

export function undoSwapFromGenerationContext<TContext extends GenerationContextLike>(
  context: TContext,
  swap: CommittedSwapLike,
): TContext {
  return addPoiToGenerationContext(
    removePoiFromGenerationContext(context, swap.replacement_name, swap.replacement_type),
    swap.original_name,
    swap.original_type,
  );
}

export function applyCompletionTaskItemToGenerationContext<TContext extends GenerationContextLike>(
  context: TContext,
  item: CompletionTaskIntentItemLike,
): TContext {
  const poiType = completionTaskItemToPoiType(item);
  if (!poiType) {
    return context;
  }
  return addPoiToGenerationContext(context, item.name, poiType);
}

export function undoCompletionTaskItemFromGenerationContext<TContext extends GenerationContextLike>(
  context: TContext,
  item: CompletionTaskIntentItemLike,
): TContext {
  const poiType = completionTaskItemToPoiType(item);
  if (!poiType) {
    return context;
  }
  return removePoiFromGenerationContext(context, item.name, poiType);
}

export function applyRouteEditsToGenerationContext<TContext extends GenerationContextLike>(
  context: TContext,
  editedDays: RouteEditedDayLike[],
  unplannedStops: RouteEditedStopLike[] = [],
): TContext {
  const orderedPois = buildOrderedPoisFromEditedDays(editedDays, unplannedStops);
  return {
    ...context,
    scenic_spots: orderedPois.scenic,
    restaurants: orderedPois.restaurants,
  };
}

function removePoiFromGenerationContext<TContext extends GenerationContextLike>(
  context: TContext,
  poiName: string,
  poiType: ReplaceablePoiType,
): TContext {
  const removeByName = (values: string[]) =>
    values.filter((value) => normalizeComparisonName(value) !== normalizeComparisonName(poiName));

  return poiType === "restaurant"
    ? { ...context, restaurants: removeByName(context.restaurants) }
    : { ...context, scenic_spots: removeByName(context.scenic_spots) };
}

function addPoiToGenerationContext<TContext extends GenerationContextLike>(
  context: TContext,
  poiName: string,
  poiType: ReplaceablePoiType,
): TContext {
  return poiType === "restaurant"
    ? { ...context, restaurants: uniquePreserveOrder([...context.restaurants, poiName]) }
    : { ...context, scenic_spots: uniquePreserveOrder([...context.scenic_spots, poiName]) };
}

function completionTaskItemToPoiType(
  item: CompletionTaskIntentItemLike,
): ReplaceablePoiType | null {
  if (item.type === "restaurant") {
    return "restaurant";
  }
  if (item.type === "scenic") {
    return "scenic";
  }
  return null;
}

function buildOrderedPoisFromEditedDays(
  editedDays: RouteEditedDayLike[],
  unplannedStops: RouteEditedStopLike[] = [],
): { scenic: string[]; restaurants: string[] } {
  const scenic: string[] = [];
  const restaurants: string[] = [];

  for (const day of editedDays) {
    for (const stop of day.stops) {
      if (stop.item.type === "restaurant") {
        restaurants.push(stop.item.name);
      } else if (stop.item.type === "scenic") {
        scenic.push(stop.item.name);
      }
    }
  }
  for (const stop of unplannedStops) {
    if (stop.item.type === "restaurant") {
      restaurants.push(stop.item.name);
    } else if (stop.item.type === "scenic") {
      scenic.push(stop.item.name);
    }
  }

  return {
    scenic: uniquePreserveOrder(scenic),
    restaurants: uniquePreserveOrder(restaurants),
  };
}

function buildFixedEventsWithRouteLocks(
  currentFixedEvents: unknown[],
  editedDays: RouteEditedDayLike[],
): unknown[] {
  const preservedEvents = currentFixedEvents.filter(
    (event) => !isRouteLockFixedEvent(event),
  );
  const routeLocks = editedDays.flatMap((day) =>
    day.stops
      .filter(
        (stop) =>
          stop.item.is_fixed &&
          stop.item.type !== "hotel" &&
          (stop.originalIsFixed !== true ||
            stop.item.source_reason?.includes("编辑路线里锁定") === true),
      )
      .map((stop) => ({
        name: stop.item.name,
        fixed_day: stop.day || day.day,
        fixed_time_start: stop.item.start_time,
        fixed_time_end: stop.item.end_time,
        category: "route_lock",
      })),
  );

  const seen = new Set<string>();
  return [...preservedEvents, ...routeLocks].filter((event) => {
    const key = buildFixedEventKey(event);
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function isRouteLockFixedEvent(event: unknown): boolean {
  return (
    typeof event === "object" &&
    event !== null &&
    "category" in event &&
    (event as { category?: unknown }).category === "route_lock"
  );
}

function buildFixedEventKey(event: unknown): string {
  if (typeof event !== "object" || event === null) {
    return String(event);
  }
  const value = event as {
    name?: unknown;
    fixed_day?: unknown;
    fixed_time_start?: unknown;
    fixed_time_end?: unknown;
    category?: unknown;
  };
  return [
    value.name,
    value.fixed_day,
    value.fixed_time_start,
    value.fixed_time_end,
    value.category,
  ]
    .map((part) => String(part ?? ""))
    .join("|");
}
