import type { TimelineBlockType } from "@/components/trip/MobileEditRouteWorkspace";

export type TripCandidate = {
  id: string;
  trip_id: string;
  candidate_type: "place" | "meal" | "activity" | string;
  display_name: string;
  normalized_name: string;
  category?: string | null;
  coordinates?: { latitude: number; longitude: number } | null;
  address_summary?: string | null;
  estimated_duration_minutes?: number | null;
  preferred_time_block?: string | null;
  explicit_day_reference?: string | null;
  source_kind: "manual_entry" | "completion" | "place_intelligence" | string;
  source_ref?: string | null;
  evidence_refs: string[];
  location_state: "known" | "missing" | "failed" | "assumed" | "not_requested" | string;
  route_state: "known" | "missing" | "failed" | "assumed" | "not_requested" | string;
  duration_state: "known" | "missing" | "failed" | "assumed" | "not_requested" | string;
  confidence: "high" | "medium" | "low" | "unknown" | string;
  content_digest: string;
  workflow_state: "pending" | "rejected" | "deferred" | "scheduled" | string;
  latest_decision_id?: string | null;
  created_at: string;
};

export type CandidateWorkspaceState =
  | { status: "idle" }
  | { status: "loading" }
  | {
      status: "ready";
      pending: TripCandidate[];
      rejected: TripCandidate[];
      deferred: TripCandidate[];
      scheduled: TripCandidate[];
    }
  | { status: "error"; code: string; message: string };

export type CandidateRegistrationResponse = {
  candidate: TripCandidate;
  deduplicated: boolean;
  idempotent_replay: boolean;
};

export type CandidateListResponse = {
  candidates: TripCandidate[];
};

export type CandidateDecisionResponse = {
  decision: {
    id: string;
    candidate_id: string;
    decision_type: string;
    reason_code: string;
  };
  candidate: TripCandidate;
  idempotent_replay: boolean;
};

export type CandidateAdmissionCommandEnvelope = {
  schema_version: "1.0";
  base_revision_id: string;
  mutation_kind: "candidate_admission";
  commands: Array<{
    type: "add_candidate_stop";
    candidate_id: string;
    target_day: number;
    target_block: TimelineBlockType;
    placement: { at_end: true } | { before_stop_id: string } | { after_stop_id: string };
  }>;
};

export function groupCandidates(candidates: TripCandidate[]): CandidateWorkspaceState {
  return {
    status: "ready",
    pending: candidates.filter((candidate) => candidate.workflow_state === "pending"),
    rejected: candidates.filter((candidate) => candidate.workflow_state === "rejected"),
    deferred: candidates.filter((candidate) => candidate.workflow_state === "deferred"),
    scheduled: candidates.filter((candidate) => candidate.workflow_state === "scheduled"),
  };
}

export function buildManualCandidatePayload(name: string, type: "scenic" | "restaurant") {
  const trimmed = name.trim();
  return {
    candidate_type: type === "restaurant" ? "meal" : "place",
    display_name: trimmed,
    category: type,
    source_kind: "manual_entry",
  };
}

export function buildCompletionCandidatePayload(option: {
  name: string;
  type: "scenic" | "restaurant";
  suggested_day?: number | null;
  suggested_block?: string | null;
  reasoning_summary?: string | null;
}) {
  return {
    candidate_type: option.type === "restaurant" ? "meal" : "place",
    display_name: option.name,
    category: option.type,
    preferred_time_block: option.suggested_block ?? null,
    explicit_day_reference: option.suggested_day ? String(option.suggested_day) : null,
    source_kind: "completion",
    source_ref: option.reasoning_summary ?? null,
    evidence_refs: [],
  };
}

export function buildCandidateAdmissionEnvelope(
  baseRevisionId: string,
  candidate: TripCandidate,
  targetDay: number,
  targetBlock: TimelineBlockType,
): CandidateAdmissionCommandEnvelope {
  return {
    schema_version: "1.0",
    base_revision_id: baseRevisionId,
    mutation_kind: "candidate_admission",
    commands: [
      {
        type: "add_candidate_stop",
        candidate_id: candidate.id,
        target_day: targetDay,
        target_block: targetBlock,
        placement: { at_end: true },
      },
    ],
  };
}

export function candidateIdempotencyKey(prefix: string, tripId: string, stablePart: string): string {
  return `${prefix}:${tripId}:${stablePart}`.slice(0, 180);
}
