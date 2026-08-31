import { getTripJson, postTripJson, type TripApiResult } from "@/components/trip/tripApiClient";
import { getTripApiBaseUrl, TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import type { BinaryImportCreateResponse, BinaryInspectionView, DocumentExtractionCreateResponse, DocumentExtractionEvidenceResponse, ImportCapabilityPack, ImportCommitResult, ImportReviewResponse, TextImportCreateResponse, URLImportCreateResponse } from "./importTypes";

export async function fetchImportCapabilities(tripId: string, signal?: AbortSignal) {
  return getTripJson<ImportCapabilityPack>(
    importCapabilitiesEndpoint(tripId),
    "检查导入能力失败",
    undefined,
    { signal },
  );
}

function importCapabilitiesEndpoint(tripId: string): string {
  return `${getTripApiBaseUrl()}/trips/${encodeURIComponent(tripId)}/imports/capabilities`;
}

export async function submitTextImport(tripId: string, text: string, idempotencyKey: string) {
  return postTripJson<TextImportCreateResponse>(
    TRIP_API_ENDPOINTS.createTextImport(tripId),
    { text, original_label: "Pasted text" },
    "导入文本失败",
    undefined,
    { headers: { "X-Idempotency-Key": idempotencyKey } },
  );
}

export async function submitUrlImport(tripId: string, url: string, idempotencyKey: string) {
  return postTripJson<URLImportCreateResponse>(
    TRIP_API_ENDPOINTS.createUrlImport(tripId),
    { url },
    "导入 URL 失败",
    undefined,
    { headers: { "X-Idempotency-Key": idempotencyKey } },
  );
}

export async function submitBinaryImport(
  tripId: string,
  file: File,
  declaredKind: "image" | "pdf",
  idempotencyKey: string,
) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("declared_kind", declaredKind);
  formData.append("original_label", declaredKind === "image" ? "Image artifact" : "PDF artifact");
  return postTripForm<BinaryImportCreateResponse>(
    TRIP_API_ENDPOINTS.createBinaryImport(tripId),
    formData,
    "导入图片或 PDF 失败",
    { "X-Idempotency-Key": idempotencyKey },
  );
}

export async function fetchBinaryInspection(tripId: string, importJobId: string) {
  return getTripJson<BinaryInspectionView>(
    TRIP_API_ENDPOINTS.getBinaryInspection(tripId, importJobId),
    "刷新 artifact inspection 失败",
  );
}

export async function fetchSanitizedImageBlob(tripId: string, importJobId: string) {
  const response = await fetch(TRIP_API_ENDPOINTS.getSanitizedImage(tripId, importJobId), {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await readJsonSafely(response);
    const error = extractTripError(payload);
    return {
      ok: false as const,
      code: error?.code ?? "import_artifact_fetch_failed",
      message: error?.message ?? "获取 metadata-stripped preview 失败",
    };
  }
  return { ok: true as const, data: await response.blob() };
}

export async function extractDocumentImport(tripId: string, importJobId: string, idempotencyKey: string) {
  return postTripJson<DocumentExtractionCreateResponse>(
    TRIP_API_ENDPOINTS.extractDocumentImport(tripId, importJobId),
    {},
    "抽取文档文本失败",
    undefined,
    { headers: { "X-Idempotency-Key": idempotencyKey } },
  );
}

export async function fetchDocumentExtractionEvidence(tripId: string, importJobId: string) {
  return getTripJson<DocumentExtractionEvidenceResponse>(
    TRIP_API_ENDPOINTS.getDocumentExtractionEvidence(tripId, importJobId),
    "刷新文档抽取证据失败",
  );
}

export async function fetchDocumentPagePreviewBlob(tripId: string, importJobId: string, pageNumber: number) {
  const response = await fetch(TRIP_API_ENDPOINTS.getDocumentPagePreview(tripId, importJobId, pageNumber), {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    const payload = await readJsonSafely(response);
    const error = extractTripError(payload);
    return {
      ok: false as const,
      code: error?.code ?? "import_document_page_preview_fetch_failed",
      message: error?.message ?? "获取文档页面预览失败",
    };
  }
  return { ok: true as const, data: await response.blob() };
}

export async function retryDocumentPageExtraction(
  tripId: string,
  importJobId: string,
  pageNumber: number,
  idempotencyKey: string,
) {
  return postTripJson<DocumentExtractionCreateResponse>(
    TRIP_API_ENDPOINTS.retryDocumentPageExtraction(tripId, importJobId, pageNumber),
    {},
    "重试文档页面抽取失败",
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

async function postTripForm<TData>(
  url: string,
  formData: FormData,
  fallbackMessage: string,
  headers: Record<string, string>,
): Promise<TripApiResult<TData>> {
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      body: formData,
      credentials: "include",
      headers,
    });
  } catch {
    return { ok: false, message: "无法连接后端接口。" };
  }
  const data = await readJsonSafely(response);
  if (!response.ok) {
    const error = extractTripError(data);
    return {
      ok: false,
      message: error?.message ?? fallbackMessage,
      code: error?.code,
      recoverable: true,
    };
  }
  return { ok: true, data: data as TData };
}

async function readJsonSafely(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function extractTripError(data: unknown): { code?: string; message?: string } | null {
  if (typeof data !== "object" || data === null || !("error" in data)) {
    return null;
  }
  const error = (data as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) {
    return null;
  }
  return {
    code: "code" in error ? String((error as { code?: unknown }).code ?? "") : undefined,
    message: "message" in error ? String((error as { message?: unknown }).message ?? "") : undefined,
  };
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
