import type { SourceLinkedTripIntentEnvelope } from "./intentTypes";

export function canPreviewPlannerHandoff(
  envelope: SourceLinkedTripIntentEnvelope | null,
  loadedLatest: boolean,
): boolean {
  if (!envelope || !loadedLatest) {
    return false;
  }
  return ["ready_for_planning", "ready_with_assumptions"].includes(
    envelope.formal_contract.readiness.status,
  );
}

export function buildPlannerHandoffApplyIdempotencyKey(
  proposalId: string,
  proposalDigest: string,
): string {
  return `planner-handoff:${proposalId}:${proposalDigest.slice(0, 16)}`;
}
