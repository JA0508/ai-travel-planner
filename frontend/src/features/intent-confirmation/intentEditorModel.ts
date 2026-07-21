import type {
  FormalTripIntentContract,
  IntentStructuredOverrides,
  SourceLinkedTripIntentEnvelope,
} from "./intentTypes";

export type BoundaryDraft = {
  localDatetime: string;
  timezone: string;
  flexibilityMinutes: string;
  locationText: string;
};

export type AvailabilityWindowDraft = {
  id: string;
  date: string;
  startTime: string;
  endTime: string;
  timezone: string;
  crossesMidnight: boolean;
};

export type FixedEventDraft = {
  id: string;
  title: string;
  startAt: string;
  endAt: string;
  timezone: string;
  fixedDay: string;
  locationText: string;
  flexibility: "fixed" | "movable_with_confirmation";
};

export type BudgetDraft = {
  amountMinor: string;
  currency: string;
  scope: "" | "total" | "per_person" | "per_day";
  level: "" | "low" | "medium" | "high";
  flexibilityPercent: string;
};

export type TravelerNeedDraft = {
  id: string;
  needType: "mobility" | "wheelchair" | "child" | "elderly" | "dietary" | "medical" | "sensory" | "other";
  description: string;
  severity: "required" | "preferred";
};

export type IntentEditForm = {
  city: string;
  tripDays: string;
  startDate: string;
  endDate: string;
  timezone: string;
  pace: "" | "relaxed" | "balanced" | "intensive";
  transportPreferences: string;
  arrival: BoundaryDraft;
  departure: BoundaryDraft;
  availabilityWindows: AvailabilityWindowDraft[];
  fixedEvents: FixedEventDraft[];
  mustCandidateIds: string[];
  optionalCandidateIds: string[];
  avoidCandidateIds: string[];
  budget: BudgetDraft;
  travelerNeeds: TravelerNeedDraft[];
};

const EMPTY_BOUNDARY: BoundaryDraft = {
  localDatetime: "",
  timezone: "",
  flexibilityMinutes: "0",
  locationText: "",
};

export function emptyIntentEditForm(): IntentEditForm {
  return {
    city: "",
    tripDays: "",
    startDate: "",
    endDate: "",
    timezone: "",
    pace: "",
    transportPreferences: "",
    arrival: { ...EMPTY_BOUNDARY },
    departure: { ...EMPTY_BOUNDARY },
    availabilityWindows: [],
    fixedEvents: [],
    mustCandidateIds: [],
    optionalCandidateIds: [],
    avoidCandidateIds: [],
    budget: { amountMinor: "", currency: "", scope: "", level: "", flexibilityPercent: "0" },
    travelerNeeds: [],
  };
}

export function formFromIntentEnvelope(envelope: SourceLinkedTripIntentEnvelope | null): IntentEditForm {
  if (!envelope) {
    return emptyIntentEditForm();
  }
  const contract = envelope.formal_contract;
  const datePolicy = contract.date_policy;
  return {
    city: contract.destinations[0]?.city_name ?? envelope.planner_ready_intent.city ?? "",
    tripDays: datePolicy?.trip_days ? String(datePolicy.trip_days) : "",
    startDate: datePolicy?.start_date ?? "",
    endDate: datePolicy?.end_date ?? "",
    timezone: normalizeTimezone(datePolicy?.timezone),
    pace: contract.pace?.value ?? "",
    transportPreferences: contract.transport_preferences.map((item) => item.custom_label ?? item.mode).join(", "),
    arrival: boundaryFromContract(contract.arrival_boundary),
    departure: boundaryFromContract(contract.departure_boundary),
    availabilityWindows: contract.availability_windows.map((item, index) => ({
      id: `availability-${index}`,
      date: item.date,
      startTime: item.start_time,
      endTime: item.end_time,
      timezone: item.timezone,
      crossesMidnight: item.crosses_midnight,
    })),
    fixedEvents: contract.fixed_events.map((item) => ({
      id: item.event_id,
      title: item.title,
      startAt: toDateTimeLocal(item.start_at),
      endAt: toDateTimeLocal(item.end_at),
      timezone: item.timezone ?? "",
      fixedDay: item.fixed_day ? String(item.fixed_day) : "",
      locationText: item.location_text ?? "",
      flexibility: item.flexibility,
    })),
    mustCandidateIds: contract.must_visit_places.map((item) => item.trip_candidate_id),
    optionalCandidateIds: contract.optional_places.map((item) => item.trip_candidate_id),
    avoidCandidateIds: contract.avoid_places.map((item) => item.trip_candidate_id),
    budget: budgetFromContract(contract),
    travelerNeeds: contract.traveler_needs.map((item, index) => ({
      id: `need-${index}`,
      needType: item.need_type,
      description: item.description,
      severity: item.severity,
    })),
  };
}

export function buildIntentStructuredOverrides(form: IntentEditForm): IntentStructuredOverrides {
  const tripDays = parseOptionalPositiveInteger(form.tripDays, "Trip days");
  const budgetAmountMinor = parseOptionalPositiveInteger(form.budget.amountMinor, "Budget amount");
  const flexibilityPercent = parseOptionalInteger(form.budget.flexibilityPercent, "Budget flexibility", 0, 100) ?? 0;
  const availabilityWindows = form.availabilityWindows.map((window) => ({
    date: requireText(window.date, "Availability date"),
    start_time: requireText(window.startTime, "Availability start time"),
    end_time: requireText(window.endTime, "Availability end time"),
    timezone: requireText(window.timezone, "Availability timezone"),
    crosses_midnight: window.crossesMidnight,
  }));
  const fixedEvents = form.fixedEvents.map((event) => ({
    event_id: event.id,
    name: requireText(event.title, "Fixed event title"),
    start_at: event.startAt ? toIsoDateTime(event.startAt) : null,
    end_at: event.endAt ? toIsoDateTime(event.endAt) : null,
    timezone: event.timezone.trim() || null,
    fixed_day: parseOptionalPositiveInteger(event.fixedDay, "Fixed event day"),
    location_text: event.locationText.trim() || null,
    flexibility: event.flexibility,
  }));
  const travelerNeeds = form.travelerNeeds
    .filter((need) => need.description.trim())
    .map((need) => ({
      type: "traveler_need" as const,
      need: need.description.trim(),
      need_type: need.needType,
      severity: need.severity,
    }));
  const budget =
    budgetAmountMinor !== null || form.budget.level
      ? {
          type: "budget" as const,
          amount_minor: budgetAmountMinor,
          currency: budgetAmountMinor !== null ? requireText(form.budget.currency, "Budget currency").toUpperCase() : null,
          scope: budgetAmountMinor !== null ? requireBudgetScope(form.budget.scope) : null,
          budget_level: form.budget.level || null,
          flexibility_percent: flexibilityPercent,
        }
      : null;

  return {
    city: form.city.trim() || null,
    trip_days: tripDays,
    start_date: form.startDate || null,
    end_date: form.endDate || null,
    timezone: form.timezone.trim() || null,
    arrival_boundary: boundaryToPayload(form.arrival, "Arrival"),
    departure_boundary: boundaryToPayload(form.departure, "Departure"),
    availability_windows: availabilityWindows,
    fixed_events: fixedEvents,
    must_candidate_ids: form.mustCandidateIds,
    optional_candidate_ids: form.optionalCandidateIds,
    avoid_candidate_ids: form.avoidCandidateIds,
    pace: form.pace || null,
    transport_preferences: form.transportPreferences.split(",").map((item) => item.trim()).filter(Boolean),
    budget,
    traveler_needs: travelerNeeds,
  };
}

export function buildIntentEditIdempotencyKey(
  intentRevisionId: string,
  tripRevisionId: string,
  overrides: IntentStructuredOverrides,
): string {
  return `intent-edit:${intentRevisionId}:${tripRevisionId}:${hashStable(JSON.stringify(overrides))}`.slice(0, 180);
}

function boundaryFromContract(boundary: FormalTripIntentContract["arrival_boundary"]): BoundaryDraft {
  if (!boundary) {
    return { ...EMPTY_BOUNDARY };
  }
  return {
    localDatetime: toDateTimeLocal(boundary.local_datetime),
    timezone: boundary.timezone,
    flexibilityMinutes: String(boundary.flexibility_minutes),
    locationText: boundary.location_text ?? "",
  };
}

function boundaryToPayload(boundary: BoundaryDraft, label: string) {
  if (!boundary.localDatetime && !boundary.timezone && !boundary.locationText) {
    return null;
  }
  return {
    local_datetime: toIsoDateTime(requireText(boundary.localDatetime, `${label} date and time`)),
    timezone: requireText(boundary.timezone, `${label} timezone`),
    flexibility_minutes: parseOptionalInteger(boundary.flexibilityMinutes, `${label} flexibility`, 0, 1440) ?? 0,
    location_text: boundary.locationText.trim() || null,
  };
}

function budgetFromContract(contract: FormalTripIntentContract): BudgetDraft {
  const budget = contract.budget;
  return {
    amountMinor: budget?.amount_minor ? String(budget.amount_minor) : "",
    currency: budget?.currency ?? "",
    scope: budget?.scope ?? "",
    level: budget?.level ?? "",
    flexibilityPercent: String(budget?.flexibility_percent ?? 0),
  };
}

function requireText(value: string, label: string): string {
  const normalized = value.trim();
  if (!normalized) {
    throw new Error(`${label} is required.`);
  }
  return normalized;
}

function parseOptionalPositiveInteger(value: string, label: string): number | null {
  const parsed = parseOptionalInteger(value, label, 1, Number.MAX_SAFE_INTEGER);
  return parsed;
}

function parseOptionalInteger(value: string, label: string, minimum: number, maximum: number): number | null {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`${label} must be a whole number between ${minimum} and ${maximum}.`);
  }
  return parsed;
}

function requireBudgetScope(value: BudgetDraft["scope"]): "total" | "per_person" | "per_day" {
  if (!value) {
    throw new Error("Budget scope is required when an amount is set.");
  }
  return value;
}

function normalizeTimezone(value: string | null | undefined): string {
  return value && value !== "unknown" ? value : "";
}

function toDateTimeLocal(value: string | null | undefined): string {
  return value ? value.replace("Z", "").slice(0, 16) : "";
}

function toIsoDateTime(value: string): string {
  return value.length === 16 ? `${value}:00` : value;
}

function hashStable(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}
