import type { PlaceResolutionOption, SourceLinkedTripIntentEnvelope } from "@/features/intent-confirmation/intentTypes";
import type { TripMetadata } from "@/features/trip-workspace/tripPersistence";

type PlacePolicy = "must" | "optional" | "avoid";
type Pace = "relaxed" | "balanced" | "intensive";

type FixedEventInput = {
  title: string;
  fixed_day?: number | null;
  start_at?: string | null;
  end_at?: string | null;
  timezone?: string | null;
  place_candidate_id?: string | null;
  location_text?: string | null;
  flexibility?: "fixed" | "movable_with_confirmation";
};

export type DraftIntentEditOperation =
  | { operation: "update_destination"; city: string; timezone?: string | null }
  | { operation: "update_date_policy"; start_date?: string | null; end_date?: string | null; timezone?: string | null; reference_date?: string | null }
  | { operation: "update_trip_days"; trip_days: number }
  | { operation: "update_pace"; pace: Pace }
  | { operation: "add_fixed_event"; event: FixedEventInput }
  | { operation: "update_fixed_event"; fixed_event_id: string; event: FixedEventInput }
  | { operation: "remove_fixed_event"; fixed_event_id: string }
  | { operation: "confirm_place_identity"; place_stable_id: string; provider_place_id: string; search_query?: string | null }
  | { operation: "add_must_place" | "add_optional_place" | "add_avoid_place"; candidate_id: string }
  | { operation: "move_place_policy"; candidate_id: string; from_policy: PlacePolicy; to_policy: PlacePolicy }
  | { operation: "remove_place"; candidate_id: string; policy: PlacePolicy };

export type DraftIntentEditRequest = {
  base_intent_revision_id: string;
  base_draft_version: number;
  operations: DraftIntentEditOperation[];
};

export type DraftIntentEditResponse = {
  draft_trip_id: string;
  draft_version: number;
  previous_intent_revision_id: string;
  latest_intent_revision_id: string;
  intent_revision_number: number;
  changed: boolean;
  idempotent_replay: boolean;
  readiness: string;
  issue_summary: string[];
  envelope: SourceLinkedTripIntentEnvelope;
  revision: {
    id: string;
    revision_number: number;
    parent_draft_intent_revision_id: string | null;
    content_digest: string;
  };
};

export type LatestPrePlanIntentResponse = {
  trip: TripMetadata & { draft_version: number };
  envelope: SourceLinkedTripIntentEnvelope;
  revision: DraftIntentEditResponse["revision"];
};

export type PrePlanPlaceIdentitySuggestionsResponse = {
  place_stable_id: string;
  query: string;
  options: PlaceResolutionOption[];
  recommended_provider_place_id: string | null;
  recommendation_reason: string | null;
};

export type DraftClarificationAnswer =
  | { answer_type: "destination"; city: string; timezone?: string | null }
  | { answer_type: "trip_days"; trip_days: number }
  | { answer_type: "date_range"; start_date: string; end_date: string; timezone?: string | null }
  | { answer_type: "date_policy_choice"; policy: "trip_days"; trip_days: number }
  | { answer_type: "date_policy_choice"; policy: "date_range"; start_date: string; end_date: string; timezone?: string | null };

export type DraftClarificationResolveRequest = {
  base_intent_revision_id: string;
  base_draft_version: number;
  answer: DraftClarificationAnswer;
};
