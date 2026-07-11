"use client";

import {
  buildUserConfirmedReplacementFromSwap,
  type CommittedSwapLike,
  type UserConfirmedReplacementLike,
} from "@/components/trip/tripSwapState";
import {
  buildEffectivePreferences,
  normalizeComparisonName,
  uniquePreserveOrder,
  type PreferenceSignals,
} from "@/components/trip/tripSwapPolicy";

type ReplaceablePoiType = "scenic" | "restaurant";

type UserIntentStateLike = {
  original_scenic: string[];
  original_restaurants: string[];
  confirmed_scenic: string[];
  confirmed_restaurants: string[];
  rejected_scenic: string[];
  rejected_restaurants: string[];
};

type FixedEventLike = {
  name: string;
  category?: string | null;
};

type AvailabilityWindowLike = unknown;

type RegenerationIntentLike<TFixedEvent, TAvailabilityWindow, TTravelMode> = {
  city: string | null;
  travel_mode: TTravelMode | null;
  hotel: string | null;
  arrival_anchor: string | null;
  departure_anchor: string | null;
  availability_windows: TAvailabilityWindow[];
  trip_days: number | null;
  trip_days_basis: string;
  carry_forward_scenic_spots: string[];
  carry_forward_restaurants: string[];
  fixed_events: TFixedEvent[];
  preferences: string[];
  rejected_scenic_spots: string[];
  rejected_restaurants: string[];
  confirmed_replacements: UserConfirmedReplacementLike<string>[];
};

type TripIntentEnvelopeLike<TFixedEvent, TAvailabilityWindow, TTravelMode> = {
  current_intent: RegenerationIntentLike<TFixedEvent, TAvailabilityWindow, TTravelMode>;
};

type GenerationContextLike<TFixedEvent, TAvailabilityWindow, TPacingProfile, TTripDaysSource, TTripScopeEstimate, TTravelMode> = {
  city?: string | null;
  scenic_spots: string[];
  restaurants: string[];
  fixed_events: TFixedEvent[];
  preferences: string[];
  pacing_profile: TPacingProfile;
  trip_days_source?: TTripDaysSource;
  trip_scope_estimate?: TTripScopeEstimate | null;
  hotel: string | null;
  arrival_anchor: string | null;
  departure_anchor: string | null;
  availability_windows: TAvailabilityWindow[];
};

type ParsedIntentLike<TTravelMode, TTripScopeEstimate> = {
  city: string | null;
  hotel: string | null;
  arrival_anchor: string | null;
  departure_anchor: string | null;
  trip_scope_estimate?: TTripScopeEstimate | null;
  travel_mode?: TTravelMode | null;
};

type PlanningStateLike<TTripScopeEstimate> = {
  city: string | null;
  trip_scope_estimate?: TTripScopeEstimate | null;
};

type ItineraryWithRegenerationIntent<TFixedEvent, TAvailabilityWindow, TTravelMode> = {
  planning_assumptions: {
    regeneration_intent: RegenerationIntentLike<TFixedEvent, TAvailabilityWindow, TTravelMode> | null;
  } | null;
};

export function buildEffectiveIntentPoisFromState(
  state: UserIntentStateLike,
): { scenic: string[]; restaurants: string[] } {
  return {
    scenic: uniquePreserveOrder(
      [...state.original_scenic, ...state.confirmed_scenic].filter(
        (name) => !state.rejected_scenic.includes(name),
      ),
    ),
    restaurants: uniquePreserveOrder(
      [...state.original_restaurants, ...state.confirmed_restaurants].filter(
        (name) => !state.rejected_restaurants.includes(name),
      ),
    ),
  };
}

export function buildEffectiveIntentPoisFromRegenerationIntent<
  TFixedEvent,
  TAvailabilityWindow,
  TTravelMode,
>(
  regenerationIntent: RegenerationIntentLike<TFixedEvent, TAvailabilityWindow, TTravelMode>,
  state: UserIntentStateLike,
): { scenic: string[]; restaurants: string[] } {
  const rejectedScenic = new Set(
    [...(regenerationIntent.rejected_scenic_spots ?? []), ...state.rejected_scenic].map(
      normalizeComparisonName,
    ),
  );
  const rejectedRestaurants = new Set(
    [...(regenerationIntent.rejected_restaurants ?? []), ...state.rejected_restaurants].map(
      normalizeComparisonName,
    ),
  );

  return {
    scenic: uniquePreserveOrder([
      ...regenerationIntent.carry_forward_scenic_spots,
      ...state.original_scenic,
      ...state.confirmed_scenic,
    ]).filter((name) => !rejectedScenic.has(normalizeComparisonName(name))),
    restaurants: uniquePreserveOrder([
      ...regenerationIntent.carry_forward_restaurants,
      ...state.original_restaurants,
      ...state.confirmed_restaurants,
    ]).filter((name) => !rejectedRestaurants.has(normalizeComparisonName(name))),
  };
}

export function buildTripIntentPatchFromCurrentState<
  TFixedEvent,
  TAvailabilityWindow,
  TTravelMode,
  TPacingProfile extends "relaxed" | "balanced" | "packed",
>(args: {
  tripIntent: TripIntentEnvelopeLike<TFixedEvent, TAvailabilityWindow, TTravelMode>;
  userIntentState: UserIntentStateLike;
  scenicSpots: string;
  restaurants: string;
  hotel: string;
  arrivalAnchor: string;
  departureAnchor: string;
  availabilityWindowsText: string;
  preferencesText: string;
  tripDays: string;
  fixedEventsText: string;
  travelMode: TTravelMode | null;
  committedSwaps: CommittedSwapLike[];
  preferenceSignals: PreferenceSignals;
  pacingProfile: TPacingProfile;
  splitLines: (value: string) => string[];
  parseFixedEventLines: (value: string) => TFixedEvent[];
  parseAvailabilityWindowLines: (value: string) => TAvailabilityWindow[];
}) {
  const currentIntent = args.tripIntent.current_intent;
  const effectiveIntent = buildEffectiveIntentPoisFromRegenerationIntent(
    currentIntent,
    args.userIntentState,
  );
  const typedScenic = args.splitLines(args.scenicSpots);
  const typedRestaurants = args.splitLines(args.restaurants);
  const scenicSeeds = typedScenic.length > 0 ? typedScenic : effectiveIntent.scenic;
  const restaurantSeeds =
    typedRestaurants.length > 0 ? typedRestaurants : effectiveIntent.restaurants;
  const parsedFixedEvents = args.parseFixedEventLines(args.fixedEventsText);
  const parsedAvailabilityWindows = args.parseAvailabilityWindowLines(
    args.availabilityWindowsText,
  );
  const typedPreferences = args.splitLines(args.preferencesText);

  return {
    city: currentIntent.city,
    travel_mode: args.travelMode ?? currentIntent.travel_mode,
    hotel: args.hotel.trim() || currentIntent.hotel,
    arrival_anchor: args.arrivalAnchor.trim() || currentIntent.arrival_anchor,
    departure_anchor: args.departureAnchor.trim() || currentIntent.departure_anchor,
    availability_windows:
      parsedAvailabilityWindows.length > 0
        ? parsedAvailabilityWindows
        : currentIntent.availability_windows,
    trip_days: args.tripDays.trim() ? Number(args.tripDays.trim()) : currentIntent.trip_days,
    flexible_scenic_spots: scenicSeeds,
    flexible_restaurants: restaurantSeeds,
    fixed_events: parsedFixedEvents.length > 0 ? parsedFixedEvents : currentIntent.fixed_events,
    preferences: buildEffectivePreferences(
      typedPreferences.length > 0 ? typedPreferences : currentIntent.preferences,
      args.preferenceSignals,
      args.pacingProfile,
    ),
    rejected_scenic_spots: uniquePreserveOrder([
      ...currentIntent.rejected_scenic_spots,
      ...args.userIntentState.rejected_scenic,
    ]),
    rejected_restaurants: uniquePreserveOrder([
      ...currentIntent.rejected_restaurants,
      ...args.userIntentState.rejected_restaurants,
    ]),
    confirmed_replacements: uniqueConfirmedReplacements([
      ...currentIntent.confirmed_replacements,
      ...args.committedSwaps.map(buildUserConfirmedReplacementFromSwap),
    ]),
  };
}

function uniqueConfirmedReplacements<TReplacement extends UserConfirmedReplacementLike<string>>(
  replacements: TReplacement[],
): TReplacement[] {
  const seen = new Set<string>();
  const result: TReplacement[] = [];
  for (const replacement of replacements) {
    const key = [
      normalizeComparisonName(replacement.original_name),
      replacement.original_type,
      normalizeComparisonName(replacement.replacement_name),
      replacement.replacement_type,
    ].join("|");
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(replacement);
  }
  return result;
}

export function buildRegenerateValuesFromCurrentState<
  TResult extends ItineraryWithRegenerationIntent<TFixedEvent, TAvailabilityWindow, TTravelMode>,
  TFixedEvent,
  TAvailabilityWindow,
  TTravelMode,
  TPacingProfile,
  TTripDaysSource,
  TTripScopeEstimate,
>(args: {
  result: TResult | null;
  generationContext:
    | GenerationContextLike<
        TFixedEvent,
        TAvailabilityWindow,
        TPacingProfile,
        TTripDaysSource,
        TTripScopeEstimate,
        TTravelMode
      >
    | null;
  userIntentState: UserIntentStateLike;
  regenerationIntentOverride:
    | RegenerationIntentLike<TFixedEvent, TAvailabilityWindow, TTravelMode>
    | null;
  parsedIntent: ParsedIntentLike<TTravelMode, TTripScopeEstimate> | null;
  planningState: PlanningStateLike<TTripScopeEstimate> | null;
  scenicSpots: string;
  restaurants: string;
  hotel: string;
  arrivalAnchor: string;
  departureAnchor: string;
  availabilityWindowsText: string;
  preferencesText: string;
  tripDays: string;
  fixedEventsText: string;
  travelMode: TTravelMode | null;
  splitLines: (value: string) => string[];
  parseFixedEventLines: (value: string) => TFixedEvent[];
  parseAvailabilityWindowLines: (value: string) => TAvailabilityWindow[];
  schedulerEstimatedTripDaysSource: TTripDaysSource;
  explicitTripDaysSource: TTripDaysSource;
}) {
  const regenerationIntent =
    args.regenerationIntentOverride ??
    args.result?.planning_assumptions?.regeneration_intent ??
    null;
  const parsedFixedEvents = args.parseFixedEventLines(args.fixedEventsText);
  const parsedAvailabilityWindows = args.parseAvailabilityWindowLines(
    args.availabilityWindowsText,
  );
  const typedPreferences = args.splitLines(args.preferencesText);
  const effectiveIntent = regenerationIntent
    ? buildEffectiveIntentPoisFromRegenerationIntent(regenerationIntent, args.userIntentState)
    : buildEffectiveIntentPoisFromState(args.userIntentState);
  const fixedEvents =
    parsedFixedEvents.length > 0 ? parsedFixedEvents : regenerationIntent?.fixed_events ?? [];
  const availabilityWindows =
    parsedAvailabilityWindows.length > 0
      ? parsedAvailabilityWindows
      : regenerationIntent?.availability_windows ?? [];
  const mergedPreferences = regenerationIntent
    ? uniquePreserveOrder([...regenerationIntent.preferences, ...typedPreferences])
    : typedPreferences;
  const tripDayCount = args.tripDays.trim()
    ? Number(args.tripDays.trim())
    : regenerationIntent?.trip_days ?? undefined;
  const tripDaysSource = args.tripDays.trim()
    ? args.explicitTripDaysSource
    : regenerationIntent?.trip_days_basis === "explicit" && regenerationIntent.trip_days
      ? args.explicitTripDaysSource
      : args.generationContext?.trip_days_source ?? args.schedulerEstimatedTripDaysSource;

  return {
    cityName:
      regenerationIntent?.city ??
      args.generationContext?.city ??
      args.parsedIntent?.city ??
      args.planningState?.city ??
      null,
    scenicSpotNames: effectiveIntent.scenic,
    restaurantNames: effectiveIntent.restaurants,
    fixedEvents,
    availabilityWindows,
    preferences: mergedPreferences,
    hotelName:
      args.hotel.trim() ||
      regenerationIntent?.hotel ||
      args.generationContext?.hotel ||
      args.parsedIntent?.hotel ||
      "",
    arrivalAnchorName:
      args.arrivalAnchor.trim() ||
      regenerationIntent?.arrival_anchor ||
      args.generationContext?.arrival_anchor ||
      args.parsedIntent?.arrival_anchor ||
      "",
    departureAnchorName:
      args.departureAnchor.trim() ||
      regenerationIntent?.departure_anchor ||
      args.generationContext?.departure_anchor ||
      args.parsedIntent?.departure_anchor ||
      "",
    tripDayCount,
    tripDaysSource,
    tripScopeEstimate:
      args.generationContext?.trip_scope_estimate ??
      args.planningState?.trip_scope_estimate ??
      null,
    travelModeValue: args.travelMode ?? regenerationIntent?.travel_mode ?? null,
  };
}

export function buildGenerateItineraryPayload<
  TFixedEvent extends FixedEventLike,
  TAvailabilityWindow,
  TTravelMode,
  TPacingProfile extends "relaxed" | "balanced" | "packed",
  TTripDaysSource extends string,
  TTripScopeEstimate,
>(args: {
  values: {
    cityName: string | null;
    scenicSpotNames: string[];
    restaurantNames: string[];
    fixedEvents: TFixedEvent[];
    availabilityWindows: TAvailabilityWindow[];
    preferences: string[];
    hotelName: string;
    arrivalAnchorName: string;
    departureAnchorName: string;
    tripDayCount: number | undefined;
    tripDaysSource: TTripDaysSource;
    tripScopeEstimate: TTripScopeEstimate | null;
    travelModeValue: TTravelMode | null;
  };
  userIntentState: UserIntentStateLike;
  committedSwaps: CommittedSwapLike[];
  preferenceSignals: PreferenceSignals;
  pacingProfile: TPacingProfile;
}) {
  const fixedScenicSpots = args.values.fixedEvents
    .filter((event) => event.category !== "restaurant")
    .map(({ category: _category, ...event }) => event);
  const fixedRestaurants = args.values.fixedEvents
    .filter((event) => event.category === "restaurant")
    .map(({ category: _category, ...event }) => event);
  const effectivePreferences = buildEffectivePreferences(
    args.values.preferences,
    args.preferenceSignals,
    args.pacingProfile,
  );

  return {
    payload: {
      city: args.values.cityName?.trim() || undefined,
      scenic_spots: [
        ...args.values.scenicSpotNames.map((name) => ({ name })),
        ...fixedScenicSpots,
      ],
      restaurants: [
        ...args.values.restaurantNames.map((name) => ({ name })),
        ...fixedRestaurants,
      ],
      hotel: { name: args.values.hotelName.trim() },
      travel_mode: args.values.travelModeValue ?? undefined,
      arrival_anchor: args.values.arrivalAnchorName.trim() || undefined,
      departure_anchor: args.values.departureAnchorName.trim() || undefined,
      availability_windows: args.values.availabilityWindows,
      preferences: effectivePreferences,
      rejected_scenic_spots: args.userIntentState.rejected_scenic,
      rejected_restaurants: args.userIntentState.rejected_restaurants,
      confirmed_replacements: args.committedSwaps.map(buildUserConfirmedReplacementFromSwap),
      trip_days: args.values.tripDayCount,
      trip_days_source: args.values.tripDayCount
        ? args.values.tripDaysSource === "explicit"
          ? "explicit"
          : args.values.tripDaysSource === "scheduler_estimated"
            ? undefined
            : "interaction_estimated"
        : undefined,
      auto_fill_sparse_days: true,
    },
    generationContextSnapshot: {
      city: args.values.cityName?.trim() || null,
      scenic_spots: args.values.scenicSpotNames,
      restaurants: args.values.restaurantNames,
      fixed_events: args.values.fixedEvents,
      preferences: effectivePreferences,
      pacing_profile: args.pacingProfile,
      trip_days_source: args.values.tripDaysSource,
      trip_scope_estimate: args.values.tripScopeEstimate,
      hotel: args.values.hotelName.trim() || null,
      arrival_anchor: args.values.arrivalAnchorName.trim() || null,
      departure_anchor: args.values.departureAnchorName.trim() || null,
      availability_windows: args.values.availabilityWindows,
    },
  };
}
