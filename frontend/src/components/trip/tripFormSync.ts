import {
  formatAvailabilityWindowsForTextarea,
  formatFixedEventsForTextarea,
  type ParsedAvailabilityWindowInput,
  type ParsedFixedEventInput,
} from "./tripInputParsing";

export type TripFormSyncTravelMode =
  | "airplane"
  | "high_speed_rail"
  | "rail"
  | "car"
  | "undecided";

export type TripDaysSource =
  | "explicit"
  | "estimated"
  | "scheduler_estimated"
  | "interaction_estimated";

export type ParsedTripIntentForFormSync = {
  city: string | null;
  trip_days: number | null;
  hotel: string | null;
  arrival_anchor: string | null;
  departure_anchor: string | null;
  availability_windows: ParsedAvailabilityWindowInput[];
  scenic_spots: string[];
  restaurants: string[];
  fixed_events: ParsedFixedEventInput[];
  preferences: string[];
};

export type PlanningStateForFormSync = {
  trip_scope_estimate?: {
    estimated_trip_days?: number | null;
  } | null;
} | null;

export type RegenerationIntentForFormSync = {
  city: string | null;
  travel_mode: TripFormSyncTravelMode | null;
  hotel: string | null;
  arrival_anchor: string | null;
  departure_anchor: string | null;
  availability_windows: ParsedAvailabilityWindowInput[];
  trip_days: number | null;
  suggested_trip_days: number;
  fixed_events: ParsedFixedEventInput[];
  preferences: string[];
  flexible_scenic_spots: string[];
  flexible_restaurants: string[];
  carry_forward_scenic_spots: string[];
  carry_forward_restaurants: string[];
};

export type TripStructuredFormSync = {
  scenicSpots: string;
  restaurants: string;
  hotel: string;
  arrivalAnchor: string;
  departureAnchor: string;
  availabilityWindowsText: string;
  preferencesText: string;
  tripDays: string;
  fixedEventsText: string;
};

export type TripRegenerationFormSync = TripStructuredFormSync & {
  travelMode: TripFormSyncTravelMode | null;
  originalScenic: string[];
  originalRestaurants: string[];
};

export function buildStructuredFormSyncFromParsedIntent(
  intent: ParsedTripIntentForFormSync,
  planningStateSnapshot?: PlanningStateForFormSync,
): TripStructuredFormSync {
  return {
    scenicSpots: intent.scenic_spots.join("\n"),
    restaurants: intent.restaurants.join("\n"),
    hotel: intent.hotel ?? "",
    arrivalAnchor: intent.arrival_anchor ?? "",
    departureAnchor: intent.departure_anchor ?? "",
    availabilityWindowsText: formatAvailabilityWindowsForTextarea(intent.availability_windows),
    preferencesText: intent.preferences.join("\n"),
    tripDays: String(deriveTripDayCountFromParsing(intent, planningStateSnapshot ?? null) ?? ""),
    fixedEventsText: formatFixedEventsForTextarea(intent.fixed_events),
  };
}

export function buildStructuredFormSyncFromRegenerationIntent(
  regenerationIntent: RegenerationIntentForFormSync,
): TripRegenerationFormSync {
  return {
    scenicSpots: regenerationIntent.flexible_scenic_spots.join("\n"),
    restaurants: regenerationIntent.flexible_restaurants.join("\n"),
    hotel: regenerationIntent.hotel ?? "",
    arrivalAnchor: regenerationIntent.arrival_anchor ?? "",
    departureAnchor: regenerationIntent.departure_anchor ?? "",
    availabilityWindowsText: formatAvailabilityWindowsForTextarea(
      regenerationIntent.availability_windows,
    ),
    preferencesText: regenerationIntent.preferences.join("\n"),
    tripDays:
      regenerationIntent.trip_days !== null ? String(regenerationIntent.trip_days) : "",
    fixedEventsText: formatFixedEventsForTextarea(regenerationIntent.fixed_events),
    travelMode: regenerationIntent.travel_mode ?? null,
    originalScenic: regenerationIntent.flexible_scenic_spots,
    originalRestaurants: regenerationIntent.flexible_restaurants,
  };
}

export function buildParsedIntentFromRegenerationIntent(
  regenerationIntent: RegenerationIntentForFormSync,
): ParsedTripIntentForFormSync {
  return {
    city: regenerationIntent.city,
    trip_days: regenerationIntent.trip_days,
    hotel: regenerationIntent.hotel,
    arrival_anchor: regenerationIntent.arrival_anchor,
    departure_anchor: regenerationIntent.departure_anchor,
    availability_windows: regenerationIntent.availability_windows,
    scenic_spots: regenerationIntent.carry_forward_scenic_spots,
    restaurants: regenerationIntent.carry_forward_restaurants,
    fixed_events: regenerationIntent.fixed_events,
    preferences: regenerationIntent.preferences,
  };
}

export function deriveTripDayCountFromParsing(
  intent: ParsedTripIntentForFormSync,
  planningStateSnapshot: PlanningStateForFormSync,
): number | undefined {
  if (intent.trip_days !== null) {
    return intent.trip_days;
  }
  return planningStateSnapshot?.trip_scope_estimate?.estimated_trip_days ?? undefined;
}

export function deriveTripDaysSourceFromParsing(
  intent: ParsedTripIntentForFormSync,
  planningStateSnapshot: PlanningStateForFormSync,
): TripDaysSource {
  if (intent.trip_days !== null) {
    return "explicit";
  }
  if (planningStateSnapshot?.trip_scope_estimate?.estimated_trip_days) {
    return "interaction_estimated";
  }
  return "scheduler_estimated";
}
