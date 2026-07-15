import { getTripJson, postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import type { ImportCommitResult, ImportReviewResponse, TextImportCreateResponse } from "./importTypes";

export async function submitTextImport(tripId: string, text: string, idempotencyKey: string) {
  return postTripJson<TextImportCreateResponse>(
    TRIP_API_ENDPOINTS.createTextImport(tripId),
    { text, original_label: "Pasted text" },
    "导入文本失败",
    undefined,
    { headers: { "X-Idempotency-Key": idempotencyKey } },
  );
}

export async function fetchImportArtifact(tripId: string, importJobId: string) {
  const response = await fetch(TRIP_API_ENDPOINTS.getTextImportArtifact(tripId, importJobId), {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    return { ok: false as const, code: "import_artifact_fetch_failed", message: await response.text() };
  }
  return { ok: true as const, data: await response.text() };
}

export async function fetchImportReview(tripId: string, importJobId: string) {
  return getTripJson<ImportReviewResponse>(
    TRIP_API_ENDPOINTS.getTextImport(tripId, importJobId),
    "刷新导入审阅失败",
  );
}

export async function decideImportMention(
  tripId: string,
  importJobId: string,
  mentionId: string,
  payload: {
    base_review_version: number;
    action: "confirm" | "ignore" | "mark_as_note";
    selected_resolution_candidate_id?: string | null;
    cross_city_confirmed?: boolean;
  },
  idempotencyKey: string,
) {
  return postTripJson<ImportReviewResponse>(
    TRIP_API_ENDPOINTS.recordTextImportDecision(tripId, importJobId, mentionId),
    payload,
    "保存导入审阅失败",
    undefined,
    { headers: { "X-Idempotency-Key": idempotencyKey } },
  );
}

export async function commitImport(tripId: string, importJobId: string, baseReviewVersion: number, idempotencyKey: string) {
  return postTripJson<ImportCommitResult>(
    TRIP_API_ENDPOINTS.commitTextImport(tripId, importJobId),
    { base_review_version: baseReviewVersion },
    "提交导入候选失败",
    undefined,
    { headers: { "X-Idempotency-Key": idempotencyKey } },
  );
}
