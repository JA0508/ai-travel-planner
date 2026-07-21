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
      envelope.planner_ready_status === "ready" ||
      envelope.planner_ready_status === "ready_for_planning" ||
      envelope.planner_ready_status === "ready_with_assumptions"
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

export type IntentContractSemanticChange = {
  fieldPath: string;
  previousValue: string;
  currentValue: string;
};

export type IntentContractSemanticCompare = {
  baseRevisionId: string | null;
  targetRevisionId: string | null;
  changed: IntentContractSemanticChange[];
  added: IntentContractSemanticChange[];
  removed: IntentContractSemanticChange[];
  identical: boolean;
};

export function compareIntentContracts(
  base: SourceLinkedTripIntentEnvelope | null,
  target: SourceLinkedTripIntentEnvelope | null,
): IntentContractSemanticCompare {
  const baseFields = flattenFormalContract(base);
  const targetFields = flattenFormalContract(target);
  const changed: IntentContractSemanticChange[] = [];
  const added: IntentContractSemanticChange[] = [];
  const removed: IntentContractSemanticChange[] = [];
  const fieldPaths = new Set([...Object.keys(baseFields), ...Object.keys(targetFields)]);
  for (const fieldPath of Array.from(fieldPaths).sort()) {
    const previousValue = baseFields[fieldPath];
    const currentValue = targetFields[fieldPath];
    if (previousValue == null && currentValue != null) {
      added.push({ fieldPath, previousValue: "", currentValue });
    } else if (previousValue != null && currentValue == null) {
      removed.push({ fieldPath, previousValue, currentValue: "" });
    } else if (previousValue != null && currentValue != null && previousValue !== currentValue) {
      changed.push({ fieldPath, previousValue, currentValue });
    }
  }
  return {
    baseRevisionId: base?.id ?? null,
    targetRevisionId: target?.id ?? null,
    changed,
    added,
    removed,
    identical: changed.length === 0 && added.length === 0 && removed.length === 0,
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

function flattenFormalContract(envelope: SourceLinkedTripIntentEnvelope | null): Record<string, string> {
  if (!envelope) {
    return {};
  }
  const fields: Record<string, string> = {};
  for (const destination of envelope.formal_contract.destinations) {
    fields[destination.metadata.field_path] = stableSerialize({
      city: destination.city,
      canonical_place_id: destination.canonical_place_id,
    });
  }
  if (envelope.formal_contract.date_policy.metadata) {
    fields[envelope.formal_contract.date_policy.metadata.field_path] = stableSerialize({
      trip_days: envelope.formal_contract.date_policy.trip_days,
      start_date: envelope.formal_contract.date_policy.start_date,
      end_date: envelope.formal_contract.date_policy.end_date,
    });
  }
  for (const section of [
    envelope.formal_contract.fixed_events,
    envelope.formal_contract.must_places,
    envelope.formal_contract.optional_places,
    envelope.formal_contract.exclusions,
    envelope.formal_contract.transport_preferences,
    envelope.formal_contract.meal_preferences,
    envelope.formal_contract.traveler_needs,
  ]) {
    for (const item of section) {
      const metadata = item.metadata as { field_path?: string } | undefined;
      if (metadata?.field_path) {
        fields[metadata.field_path] = stableSerialize(item);
      }
    }
  }
  for (const [fieldPath, value] of Object.entries({
    "trip.pace": envelope.formal_contract.pace,
    "trip.budget": envelope.formal_contract.budget,
  })) {
    if (value) {
      fields[fieldPath] = stableSerialize(value);
    }
  }
  return fields;
}

function stableSerialize(value: unknown): string {
  if (value == null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableSerialize(item)).join(",")}]`;
  }
  const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) =>
    left.localeCompare(right),
  );
  return `{${entries.map(([key, entryValue]) => `${JSON.stringify(key)}:${stableSerialize(entryValue)}`).join(",")}}`;
}
