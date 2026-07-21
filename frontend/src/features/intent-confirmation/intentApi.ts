import { getTripJson, postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import type {
  CompileTripIntentResponse,
  TripIntentRevisionDetailResponse,
  TripIntentRevisionListResponse,
} from "./intentTypes";

export function compileTripIntentEnvelope(
  tripId: string,
  payload: {
    base_revision_id: string;
    base_intent_revision_id?: string | null;
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

export function getTripIntentEnvelope(tripId: string, intentRevisionId: string) {
  return getTripJson<TripIntentRevisionDetailResponse>(
    TRIP_API_ENDPOINTS.getTripIntentEnvelope(tripId, intentRevisionId),
    "读取意图合同详情失败",
  );
}

export function editTripIntentEnvelope(
  tripId: string,
  intentRevisionId: string,
  payload: {
    base_revision_id: string;
    field_updates: {
      city?: string | null;
      trip_days?: number | null;
      pace?: "relaxed" | "balanced" | "intensive" | null;
      transport_preferences?: string[];
    };
  },
  idempotencyKey: string,
) {
  return postTripJson<CompileTripIntentResponse>(
    TRIP_API_ENDPOINTS.editTripIntentEnvelope(tripId, intentRevisionId),
    payload,
    "保存意图合同修改失败",
    undefined,
    { headers: { "X-Idempotency-Key": idempotencyKey } },
  );
}

export function restoreTripIntentEnvelope(
  tripId: string,
  intentRevisionId: string,
  payload: { base_revision_id: string; base_intent_revision_id?: string | null },
  idempotencyKey: string,
) {
  return postTripJson<CompileTripIntentResponse>(
    TRIP_API_ENDPOINTS.restoreTripIntentEnvelope(tripId, intentRevisionId),
    payload,
    "恢复意图合同版本失败",
    undefined,
    { headers: { "X-Idempotency-Key": idempotencyKey } },
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
