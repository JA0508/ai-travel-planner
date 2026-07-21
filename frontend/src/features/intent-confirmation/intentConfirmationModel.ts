import type { IntentDomainValue, IntentField, SourceLinkedTripIntentEnvelope } from "./intentTypes";

export function buildIntentCompileIdempotencyKey(
  tripId: string,
  baseRevisionId: string,
  text: string,
): string {
  return `intent-compile:${tripId}:${baseRevisionId}:${hashText(text)}`.slice(0, 140);
}

export function summarizeIntentEnvelope(envelope: SourceLinkedTripIntentEnvelope | null) {
  if (!envelope) {
    return {
      statusLabel: "No intent contract",
      selectedFields: [] as IntentField[],
      shadowedFields: [] as IntentField[],
      blockingConflictCount: 0,
      clarificationCount: 0,
      assumptionCount: 0,
    };
  }
  return {
    statusLabel:
      envelope.planner_ready_status === "ready"
        ? "Planner-ready"
        : envelope.planner_ready_status === "blocked"
          ? "Blocked"
          : "Needs clarification",
    selectedFields: envelope.fields.filter((field) => field.status === "selected"),
    shadowedFields: envelope.fields.filter((field) => field.status === "shadowed"),
    blockingConflictCount: envelope.conflicts.filter((conflict) => conflict.severity === "blocking").length,
    clarificationCount: envelope.clarification_queue.length,
    assumptionCount: envelope.assumptions.length,
  };
}

export function formatIntentDomainValue(value: IntentDomainValue): string {
  switch (value.type) {
    case "destination_city":
      return value.city;
    case "trip_days":
      return `${value.days} days`;
    case "pace":
      return value.pace;
    case "transport_preference":
      return value.mode;
    case "must_candidate":
      return value.display_name ? `${value.display_name} (${value.candidate_id})` : value.candidate_id;
    case "fixed_event":
      return [value.name, value.fixed_day ? `day ${value.fixed_day}` : null, value.fixed_time_start]
        .filter(Boolean)
        .join(" · ");
    case "general_preference":
      return value.preference;
    case "budget":
      return [value.budget_level, value.amount, value.currency].filter((item) => item != null && item !== "").join(" ");
    case "traveler_need":
      return value.traveler_group ? `${value.traveler_group}: ${value.need}` : value.need;
    case "unknown":
      return value.raw == null ? "empty" : JSON.stringify(value.raw);
  }
}

function hashText(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}
