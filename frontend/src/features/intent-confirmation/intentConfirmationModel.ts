import type { IntentField, SourceLinkedTripIntentEnvelope } from "./intentTypes";

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

function hashText(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}
