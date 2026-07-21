import { getTripJson, postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import type { CompileTripIntentResponse, TripIntentRevisionListResponse } from "./intentTypes";

export function compileTripIntentEnvelope(
  tripId: string,
  payload: {
    base_revision_id: string;
    direct_user_text?: string | null;
    use_llm_proposal_adapter?: boolean;
  },
  idempotencyKey: string,
) {
  return postTripJson<CompileTripIntentResponse>(
    TRIP_API_ENDPOINTS.compileTripIntentEnvelope(tripId),
    payload,
    "编译意图合同失败",
    undefined,
    { headers: { "X-Idempotency-Key": idempotencyKey } },
  );
}

export function listTripIntentEnvelopes(tripId: string) {
  return getTripJson<TripIntentRevisionListResponse>(
    TRIP_API_ENDPOINTS.listTripIntentEnvelopes(tripId),
    "刷新意图合同历史失败",
  );
}

export function answerIntentClarification(
  tripId: string,
  intentRevisionId: string,
  questionId: string,
  payload: { base_revision_id: string; answer: string },
  idempotencyKey: string,
) {
  return postTripJson<CompileTripIntentResponse>(
    TRIP_API_ENDPOINTS.answerTripIntentClarification(tripId, intentRevisionId, questionId),
    payload,
    "保存澄清答案失败",
    undefined,
    { headers: { "X-Idempotency-Key": idempotencyKey } },
  );
}
