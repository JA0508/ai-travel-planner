"use client";

import { type CSSProperties, useEffect, useReducer, useRef, useState } from "react";
import type { TripPersistenceState } from "@/features/trip-workspace/tripPersistence";
import {
  commitImport,
  decideImportMention,
  extractDocumentImport,
  fetchBinaryInspection,
  fetchDocumentExtractionEvidence,
  fetchDocumentPagePreviewBlob,
  fetchImportArtifact,
  fetchImportReview,
  fetchSanitizedImageBlob,
  retryDocumentPageExtraction,
  submitBinaryImport,
  submitUrlImport,
  submitTextImport,
} from "./importApi";
import { BinaryImportComposer } from "./BinaryImportComposer";
import { BinaryInspectionResult } from "./BinaryInspectionResult";
import {
  type BinaryImportState,
  binaryImportIdempotencyKey,
  binaryImportReducer,
  binaryImportStorageValue,
  parseBinaryImportStorageValue,
} from "./binaryImportState";
import { importIdempotencyKey, importWorkspaceReducer } from "./importState";
import type { DocumentExtractionEvidenceResponse, DocumentExtractionGeneration, ImportMention, URLFetchSnapshot } from "./importTypes";
import { buildDocumentEvidenceSummary, mapNormalizedBoxToOverlay, mentionEvidenceBoxes, toNormalizedDocumentBox } from "./documentEvidenceViewModel";
import { buildImportSummary, selectedResolutionId, sourceSegments } from "./importViewModel";

type ImportReviewWorkspaceProps = {
  tripPersistence: TripPersistenceState;
  onCandidatesChanged: (tripId: string) => void;
};

type IntentEvidenceFocus = {
  tripId: string;
  importJobId: string;
  mentionId?: string | null;
  pageNumber?: number | null;
};

export function ImportReviewWorkspace({
  tripPersistence,
  onCandidatesChanged,
}: ImportReviewWorkspaceProps) {
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"text" | "url" | "binary">("text");
  const [state, dispatch] = useReducer(importWorkspaceReducer, { status: "idle" });
  const [binaryState, binaryDispatch] = useReducer(binaryImportReducer, { status: "idle" });
  const [documentExtraction, setDocumentExtraction] = useState<
    | { status: "idle" }
    | { status: "extracting" }
    | { status: "ready"; generation: DocumentExtractionGeneration; spanCount: number; evidence: DocumentExtractionEvidenceResponse }
    | { status: "error"; code: string; message: string }
  >({ status: "idle" });
  const binaryInputRef = useRef<HTMLInputElement | null>(null);
  const workspaceRef = useRef<HTMLElement | null>(null);
  const previewUrlRef = useRef<string | null>(null);
  const byteCount = utf8ByteLength(text);
  const normalizedUrl = url.trim();
  const urlValidation = validateBrowserUrl(normalizedUrl);
  const savedTripId = tripPersistence.status === "saved" ? tripPersistence.tripId : null;

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!savedTripId || typeof window === "undefined") {
      return;
    }
    const stored = parseBinaryImportStorageValue(window.localStorage.getItem(BINARY_IMPORT_STORAGE_KEY));
    if (!stored || stored.tripId !== savedTripId) {
      return;
    }
    void hydrateBinaryInspection(savedTripId, stored.jobId, stored.declaredKind);
  }, [savedTripId]);

  useEffect(() => {
    if (!savedTripId || typeof window === "undefined") {
      return;
    }
    const handleIntentEvidenceRecovery = (event: Event) => {
      const detail = (event as CustomEvent<{ tripId?: string }>).detail;
      if (!detail || detail.tripId !== savedTripId) {
        return;
      }
      workspaceRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      setMode("text");
    };
    window.addEventListener("trip-import-workspace-request", handleIntentEvidenceRecovery);
    return () => window.removeEventListener("trip-import-workspace-request", handleIntentEvidenceRecovery);
  }, [savedTripId]);

  useEffect(() => {
    if (!savedTripId || typeof window === "undefined") {
      return;
    }
    const handleIntentEvidenceFocus = (event: Event) => {
      const detail = (event as CustomEvent<IntentEvidenceFocus>).detail;
      if (!detail || detail.tripId !== savedTripId) {
        return;
      }
      void loadIntentEvidence(detail);
    };
    window.addEventListener("trip-import-evidence-focus", handleIntentEvidenceFocus);
    return () => window.removeEventListener("trip-import-evidence-focus", handleIntentEvidenceFocus);
  }, [savedTripId]);

  async function loadIntentEvidence(detail: IntentEvidenceFocus) {
    if (!savedTripId) {
      return;
    }
    const review = await fetchImportReview(savedTripId, detail.importJobId);
    if (!review.ok) {
      dispatch({ type: "error", code: review.code ?? "intent_evidence_review_fetch_failed", message: review.message, recoverable: true });
      return;
    }
    const artifact = await fetchImportArtifact(savedTripId, detail.importJobId);
    dispatch({
      type: "review",
      artifact: review.data.artifact,
      job: review.data.job,
      mentions: review.data.mentions,
      sourceText: artifact.ok ? artifact.data : "",
      sourceFetch: review.data.source_fetch,
      derivation: review.data.derivation,
    });
    if (detail.pageNumber) {
      const evidence = await fetchDocumentExtractionEvidence(savedTripId, detail.importJobId);
      if (evidence.ok) {
        setMode("binary");
        setDocumentExtraction({
          status: "ready",
          generation: evidence.data.generation,
          spanCount: evidence.data.span_map.length,
          evidence: evidence.data,
        });
      }
    }
  }

  async function handleSubmit() {
    if (!savedTripId) {
      dispatch({
        type: "error",
        code: "trip_not_saved",
        message: "Text import needs a saved TripRevision before it can create reviewable evidence.",
      });
      return;
    }
    dispatch({ type: "submit" });
    const key = importIdempotencyKey("text-import", savedTripId, `${byteCount}:${text.slice(0, 40)}`);
    const response = await submitTextImport(savedTripId, text, key);
    if (!response.ok) {
      dispatch({
        type: "error",
        code: response.code ?? "text_import_failed",
        message: response.message,
        recoverable: true,
      });
      return;
    }
    const artifact = await fetchImportArtifact(savedTripId, response.data.job.id);
    if (!artifact.ok) {
      dispatch({ type: "error", code: artifact.code, message: artifact.message, recoverable: true });
      return;
    }
    dispatch({
      type: "review",
      artifact: response.data.artifact,
      job: response.data.job,
      mentions: response.data.mentions,
      sourceText: artifact.data,
    });
  }

  async function handleSubmitUrl() {
    if (!savedTripId) {
      dispatch({
        type: "error",
        code: "trip_not_saved",
        message: "URL import needs a saved TripRevision before it can create reviewable evidence.",
      });
      return;
    }
    if (urlValidation) {
      dispatch({ type: "error", code: "import_url_invalid", message: urlValidation, recoverable: true });
      return;
    }
    dispatch({ type: "submit" });
    const key = importIdempotencyKey("url-import", savedTripId, `${normalizedUrl.length}:${normalizedUrl.slice(0, 64)}`);
    const response = await submitUrlImport(savedTripId, normalizedUrl, key);
    if (!response.ok) {
      dispatch({
        type: "error",
        code: response.code ?? "url_import_failed",
        message: recoveryMessage(response.code, response.message),
        recoverable: true,
      });
      return;
    }
    const artifact = await fetchImportArtifact(savedTripId, response.data.job.id);
    if (!artifact.ok) {
      dispatch({ type: "error", code: artifact.code, message: artifact.message, recoverable: true });
      return;
    }
    dispatch({
      type: "review",
      artifact: response.data.artifact,
      job: response.data.job,
      mentions: response.data.mentions,
      sourceText: artifact.data,
      sourceFetch: response.data.source_fetch,
      derivation: response.data.derivation,
    });
  }

  async function handleBinaryUpload() {
    if (!savedTripId) {
      binaryDispatch({
        type: "error",
        code: "trip_not_saved",
        message: "Image/PDF import needs a saved TripRevision before it can create reviewable evidence.",
      });
      return;
    }
    if (binaryState.status !== "selected") {
      return;
    }
    binaryDispatch({ type: "uploading" });
    setDocumentExtraction({ status: "idle" });
    const response = await submitBinaryImport(
      savedTripId,
      binaryState.file,
      binaryState.declaredKind,
      binaryImportIdempotencyKey(savedTripId, binaryState.file, binaryState.declaredKind),
    );
    if (!response.ok) {
      binaryDispatch({
        type: "error",
        code: response.code ?? "import_binary_failed",
        message: response.message,
        recoverable: true,
      });
      return;
    }
    rememberBinaryImport(savedTripId, response.data.job.id, response.data.inspection.declared_kind === "pdf" ? "pdf" : "image");
    binaryDispatch({
      type: "uploaded",
      artifact: response.data.artifact,
      job: response.data.job,
      inspection: response.data.inspection,
    });
    if (response.data.job.status === "artifact_ready" && response.data.inspection.detected_kind === "image") {
      await loadSanitizedPreview(savedTripId, response.data.job.id);
    }
  }

  async function hydrateBinaryInspection(tripId: string, jobId: string, declaredKind: "image" | "pdf") {
    const response = await fetchBinaryInspection(tripId, jobId);
    if (!response.ok) {
      return;
    }
    binaryDispatch({
      type: "uploaded",
      artifact: {
        id: response.data.artifact_id,
        trip_id: response.data.trip_id,
        artifact_type: declaredKind === "pdf" ? "uploaded_pdf" : "uploaded_image",
        mime_type: response.data.detected_mime_type,
        content_checksum: response.data.content_checksum,
        byte_size: response.data.byte_size,
        charset: "binary",
        privacy_level: "private",
        created_at: response.data.started_at,
      },
      job: {
        id: response.data.import_job_id,
        trip_id: response.data.trip_id,
        artifact_id: response.data.artifact_id,
        input_type: response.data.detected_kind,
        status: response.data.status,
        extraction_schema_version: response.data.schema_version,
        extractor_version: response.data.inspector_version,
        resolver_version: "none",
        review_version: 0,
        mention_count: 0,
        warning_codes: response.data.warning_codes,
        error_code: response.data.error_code,
        created_at: response.data.started_at,
        updated_at: response.data.completed_at,
      },
      inspection: response.data,
    });
    if (response.data.status === "artifact_ready" && response.data.detected_kind === "image") {
      await loadSanitizedPreview(tripId, jobId);
    }
  }

  async function handleDocumentExtraction() {
    if (!savedTripId || binaryState.status !== "artifact_ready") {
      return;
    }
    setDocumentExtraction({ status: "extracting" });
    const key = importIdempotencyKey(
      "document-extraction",
      savedTripId,
      `${binaryState.job.id}:${binaryState.result.content_checksum}`,
    );
    const response = await extractDocumentImport(savedTripId, binaryState.job.id, key);
    if (!response.ok || !response.data.job || !response.data.artifact) {
      setDocumentExtraction({
        status: "error",
        code: response.ok ? "import_document_extraction_incomplete" : response.code ?? "import_document_extraction_failed",
        message: response.ok ? "Document extraction did not return a reviewable import." : response.message,
      });
      return;
    }
    const artifact = await fetchImportArtifact(savedTripId, response.data.job.id);
    if (!artifact.ok) {
      setDocumentExtraction({ status: "error", code: artifact.code, message: artifact.message });
      return;
    }
    const evidence = await fetchDocumentExtractionEvidence(savedTripId, response.data.job.id);
    if (!evidence.ok) {
      setDocumentExtraction({
        status: "error",
        code: evidence.code ?? "import_document_evidence_failed",
        message: evidence.message,
      });
      return;
    }
    setDocumentExtraction({
      status: "ready",
      generation: response.data.generation,
      spanCount: response.data.spans.length,
      evidence: evidence.data,
    });
    dispatch({
      type: "review",
      artifact: response.data.artifact,
      job: response.data.job,
      mentions: response.data.mentions,
      sourceText: artifact.data,
      derivation: response.data.derivation,
    });
  }

  async function handleDocumentPageRetry(pageNumber: number) {
    if (!savedTripId || documentExtraction.status !== "ready") {
      return;
    }
    const sourceImportJobId = documentExtraction.evidence.generation.source_import_job_id;
    const key = importIdempotencyKey(
      "document-page-retry",
      savedTripId,
      `${documentExtraction.evidence.generation.id}:${pageNumber}`,
    );
    setDocumentExtraction({ ...documentExtraction, status: "ready" });
    const response = await retryDocumentPageExtraction(savedTripId, sourceImportJobId, pageNumber, key);
    if (!response.ok || !response.data.job || !response.data.artifact) {
      setDocumentExtraction({
        status: "error",
        code: response.ok ? "import_document_retry_incomplete" : response.code ?? "import_document_retry_failed",
        message: response.ok ? "Document page retry did not return a reviewable import." : response.message,
      });
      return;
    }
    const artifact = await fetchImportArtifact(savedTripId, response.data.job.id);
    if (!artifact.ok) {
      setDocumentExtraction({ status: "error", code: artifact.code, message: artifact.message });
      return;
    }
    const evidence = await fetchDocumentExtractionEvidence(savedTripId, response.data.job.id);
    if (!evidence.ok) {
      setDocumentExtraction({
        status: "error",
        code: evidence.code ?? "import_document_evidence_failed",
        message: evidence.message,
      });
      return;
    }
    setDocumentExtraction({
      status: "ready",
      generation: response.data.generation,
      spanCount: response.data.spans.length,
      evidence: evidence.data,
    });
    dispatch({
      type: "review",
      artifact: response.data.artifact,
      job: response.data.job,
      mentions: response.data.mentions,
      sourceText: artifact.data,
      derivation: response.data.derivation,
    });
  }

  async function loadSanitizedPreview(tripId: string, jobId: string) {
    const preview = await fetchSanitizedImageBlob(tripId, jobId);
    if (!preview.ok) {
      binaryDispatch({ type: "error", code: preview.code, message: preview.message, recoverable: true });
      return;
    }
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
    }
    const previewUrl = URL.createObjectURL(preview.data);
    previewUrlRef.current = previewUrl;
    binaryDispatch({ type: "preview", previewUrl });
  }

  async function handleDecision(mention: ImportMention, action: "confirm" | "ignore" | "mark_as_note") {
    if (state.status !== "reviewing" || !savedTripId) {
      return;
    }
    const selectedId = selectedResolutionId(mention);
    const response = await decideImportMention(
      savedTripId,
      state.job.id,
      mention.id,
      {
        base_review_version: state.reviewVersion,
        action,
        selected_resolution_candidate_id: action === "confirm" ? selectedId : undefined,
        cross_city_confirmed: true,
      },
      importIdempotencyKey("import-decision", savedTripId, `${state.job.id}:${mention.id}:${state.reviewVersion}:${action}`),
    );
    if (!response.ok) {
      if (response.code === "stale_import_review") {
        dispatch({ type: "conflict", jobId: state.job.id });
        return;
      }
      dispatch({
        type: "error",
        code: response.code ?? "import_decision_failed",
        message: response.message,
        recoverable: true,
      });
      return;
    }
    const artifact = await fetchImportArtifact(savedTripId, response.data.job.id);
    dispatch({
      type: "review",
      artifact: response.data.artifact,
      job: response.data.job,
      mentions: response.data.mentions,
      sourceText: artifact.ok ? artifact.data : state.sourceText,
      sourceFetch: response.data.source_fetch,
      derivation: response.data.derivation,
    });
  }

  async function handleRefresh() {
    if (state.status !== "conflict" || !savedTripId) {
      return;
    }
    const response = await fetchImportReview(savedTripId, state.jobId);
    if (!response.ok) {
      dispatch({
        type: "error",
        code: response.code ?? "import_refresh_failed",
        message: response.message,
        recoverable: true,
      });
      return;
    }
    const artifact = await fetchImportArtifact(savedTripId, response.data.job.id);
    dispatch({
      type: "review",
      artifact: response.data.artifact,
      job: response.data.job,
      mentions: response.data.mentions,
      sourceText: artifact.ok ? artifact.data : "",
      sourceFetch: response.data.source_fetch,
      derivation: response.data.derivation,
    });
  }

  async function handleCommit() {
    if (state.status !== "reviewing" || !savedTripId) {
      return;
    }
    const key = importIdempotencyKey("import-commit", savedTripId, `${state.job.id}:${state.reviewVersion}`);
    dispatch({ type: "committing", jobId: state.job.id, idempotencyKey: key });
    const response = await commitImport(savedTripId, state.job.id, state.reviewVersion, key);
    if (!response.ok) {
      dispatch({
        type: "error",
        code: response.code ?? "import_commit_failed",
        message: response.message,
        recoverable: true,
      });
      return;
    }
    dispatch({ type: "committed", result: response.data });
    onCandidatesChanged(savedTripId);
  }

  return (
    <section ref={workspaceRef} style={panelStyle} data-import-workspace>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "start" }}>
        <div>
          <p style={eyebrowStyle}>Source import</p>
          <h3 style={titleStyle}>
            {mode === "text" ? "Text to review inbox" : mode === "url" ? "URL to review inbox" : "Image / PDF artifact inspection"}
          </h3>
        </div>
        <span style={statusPillStyle}>{state.status}</span>
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        <div style={segmentStyle} role="tablist" aria-label="Import source type">
          <button type="button" onClick={() => setMode("text")} style={mode === "text" ? segmentActiveStyle : segmentButtonStyle}>
            Text
          </button>
          <button type="button" onClick={() => setMode("url")} style={mode === "url" ? segmentActiveStyle : segmentButtonStyle}>
            URL
          </button>
          <button type="button" onClick={() => setMode("binary")} style={mode === "binary" ? segmentActiveStyle : segmentButtonStyle}>
            Image / PDF
          </button>
        </div>
        {mode === "text" ? (
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="Paste a guide, note, or group-chat excerpt."
            disabled={!savedTripId || state.status === "submitting"}
            style={textareaStyle}
          />
        ) : mode === "url" ? (
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://example.com/travel-guide"
            disabled={!savedTripId || state.status === "submitting"}
            style={inputStyle}
          />
        ) : (
          <BinaryImportComposer
            state={binaryState}
            inputRef={binaryInputRef}
            disabled={!savedTripId || binaryState.status === "uploading"}
            onFileSelected={(file, declaredKind) => binaryDispatch({ type: "select", file, declaredKind })}
            onUpload={() => void handleBinaryUpload()}
            onReset={() => {
              binaryDispatch({ type: "reset" });
              setDocumentExtraction({ status: "idle" });
            }}
            onError={(code, message) => binaryDispatch({ type: "error", code, message, recoverable: true })}
          />
        )}
        {mode !== "binary" ? <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <span style={hintStyle}>
            {mode === "text"
              ? `${byteCount} bytes · private artifact · no itinerary mutation`
              : "public static HTML/plain text · robots respected · paste text fallback"}
          </span>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" onClick={() => (mode === "text" ? setText("") : setUrl(""))} style={secondaryButtonStyle}>
              Clear
            </button>
            <button
              type="button"
              onClick={() => void (mode === "text" ? handleSubmit() : handleSubmitUrl())}
              disabled={!savedTripId || state.status === "submitting" || (mode === "text" ? !text.trim() : !normalizedUrl || Boolean(urlValidation))}
              style={primaryButtonStyle}
            >
              {state.status === "submitting" ? "Importing..." : mode === "text" ? "Import text" : "Import URL"}
            </button>
          </div>
        </div> : null}
        {mode === "url" && urlValidation ? <p style={errorStyle}>{urlValidation}</p> : null}
      </div>

      {!savedTripId ? (
        <p style={noticeStyle}>Save or restore a trip before importing source evidence.</p>
      ) : null}

      {state.status === "reviewing" ? (
        <ReviewPane
          tripId={savedTripId}
          sourceText={state.sourceText}
          mentions={state.mentions}
          activeMentionId={state.activeMentionId}
          reviewVersion={state.reviewVersion}
          onSelect={(mentionId) => dispatch({ type: "select", mentionId })}
          onDecision={(mention, action) => void handleDecision(mention, action)}
          onCommit={() => void handleCommit()}
          sourceFetch={state.sourceFetch}
          documentEvidence={documentExtraction.status === "ready" ? documentExtraction.evidence : null}
          onRetryDocumentPage={(pageNumber) => handleDocumentPageRetry(pageNumber)}
        />
      ) : null}

      {state.status === "committing" ? <p style={noticeStyle}>Adding confirmed places to candidate pool...</p> : null}
      {state.status === "committed" ? (
        <p style={noticeStyle}>
          Added {state.result.place_candidates_created} new candidate(s), reused {state.result.place_candidates_reused}.
        </p>
      ) : null}
      {state.status === "conflict" ? (
        <div style={noticeStyle}>
          Review version changed in another tab.
          <button type="button" onClick={() => void handleRefresh()} style={{ ...secondaryButtonStyle, marginLeft: 8 }}>
            Refresh review
          </button>
        </div>
      ) : null}
      {state.status === "error" ? <p style={errorStyle}>{state.code}: {state.message}</p> : null}
      {mode === "binary" ? (
        <>
          <BinaryInspectionResult state={binaryState} />
          <DocumentExtractionAction
            binaryState={binaryState}
            extraction={documentExtraction}
            onExtract={() => void handleDocumentExtraction()}
          />
        </>
      ) : null}
    </section>
  );
}

const BINARY_IMPORT_STORAGE_KEY = "ai-travel-planner:last-binary-import";
const DOCUMENT_EVIDENCE_MAX_SURFACE = { width: 180, height: 240 };

function rememberBinaryImport(tripId: string, jobId: string, declaredKind: "image" | "pdf") {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(BINARY_IMPORT_STORAGE_KEY, binaryImportStorageValue(tripId, jobId, declaredKind));
}

function pagePreviewSurface(page: DocumentExtractionEvidenceResponse["pages"][number] | null): { width: number; height: number } {
  return fitPreviewSurface(
    numericMetadata(page?.metadata.image_width) ?? DOCUMENT_EVIDENCE_MAX_SURFACE.width,
    numericMetadata(page?.metadata.image_height) ?? DOCUMENT_EVIDENCE_MAX_SURFACE.height,
  );
}

function fitPreviewSurface(width: number, height: number): { width: number; height: number } {
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return DOCUMENT_EVIDENCE_MAX_SURFACE;
  }
  const scale = Math.min(
    DOCUMENT_EVIDENCE_MAX_SURFACE.width / width,
    DOCUMENT_EVIDENCE_MAX_SURFACE.height / height,
  );
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

function numericMetadata(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}

function DocumentExtractionAction({
  binaryState,
  extraction,
  onExtract,
}: {
  binaryState: BinaryImportState;
  extraction:
    | { status: "idle" }
    | { status: "extracting" }
    | { status: "ready"; generation: DocumentExtractionGeneration; spanCount: number; evidence: DocumentExtractionEvidenceResponse }
    | { status: "error"; code: string; message: string };
  onExtract: () => void;
}) {
  if (binaryState.status !== "artifact_ready") {
    return null;
  }
  return (
    <div style={documentExtractionStyle} data-document-extraction-action>
      <div>
        <strong style={{ color: "var(--ec-ink)", fontSize: 13 }}>Document text extraction</strong>
        <p style={hintBlockStyle}>
          Inspection-gated extraction creates a derived text artifact and review inbox. Original binary is not rendered inline.
        </p>
      </div>
      <button
        type="button"
        onClick={onExtract}
        disabled={extraction.status === "extracting"}
        style={secondaryButtonStyle}
      >
        {extraction.status === "extracting" ? "Extracting..." : "Extract text"}
      </button>
      {extraction.status === "ready" ? (
        <p style={noticeStyle}>
          {extraction.generation.strategy} · {extraction.generation.page_count} page(s) · {extraction.spanCount} provenance span(s)
        </p>
      ) : null}
      {extraction.status === "error" ? <p style={errorStyle}>{extraction.code}: {extraction.message}</p> : null}
    </div>
  );
}

function ReviewPane({
  tripId,
  sourceText,
  mentions,
  activeMentionId,
  reviewVersion,
  onSelect,
  onDecision,
  onCommit,
  sourceFetch,
  documentEvidence,
  onRetryDocumentPage,
}: {
  tripId: string | null;
  sourceText: string;
  mentions: ImportMention[];
  activeMentionId: string | null;
  reviewVersion: number;
  onSelect: (mentionId: string) => void;
  onDecision: (mention: ImportMention, action: "confirm" | "ignore" | "mark_as_note") => void;
  onCommit: () => void;
  sourceFetch?: URLFetchSnapshot | null;
  documentEvidence?: DocumentExtractionEvidenceResponse | null;
  onRetryDocumentPage: (pageNumber: number) => Promise<void>;
}) {
  const activeMention = mentions.find((mention) => mention.id === activeMentionId) ?? mentions[0] ?? null;
  const summary = buildImportSummary(mentions);
  const confirmedPlaces = mentions.filter((mention) => mention.review_state === "confirmed" && mention.entity_type === "place").length;
  return (
    <div style={reviewGridStyle}>
      <div style={sourcePaneStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <strong style={{ fontSize: 13 }}>Source</strong>
          <span style={hintStyle}>review v{reviewVersion}</span>
        </div>
        {sourceFetch ? <URLProvenance sourceFetch={sourceFetch} /> : null}
        {documentEvidence && tripId ? (
          <DocumentEvidencePanel
            tripId={tripId}
            evidence={documentEvidence}
            activeMentionId={activeMention?.id ?? null}
            onRetryPage={onRetryDocumentPage}
          />
        ) : null}
        <pre style={sourceTextStyle}>
          {sourceSegments(sourceText, activeMention).map((segment, index) =>
            segment.active ? (
              <mark key={index} style={markStyle}>{segment.text}</mark>
            ) : (
              <span key={index}>{segment.text}</span>
            ),
          )}
        </pre>
      </div>
      <div style={{ display: "grid", gap: 10 }}>
        <div style={summaryStyle}>
          {summary.confirmedCount} confirmed · {summary.ignoredCount} ignored · {summary.unresolvedCount} unresolved · {summary.preservedContextCount} preserved context
        </div>
        <div style={{ display: "grid", gap: 8, maxHeight: 420, overflow: "auto" }}>
          {mentions.map((mention) => (
            <MentionCard
              key={mention.id}
              mention={mention}
              active={mention.id === activeMention?.id}
              onSelect={() => onSelect(mention.id)}
              onDecision={(action) => onDecision(mention, action)}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={onCommit}
          disabled={confirmedPlaces === 0}
          style={primaryButtonStyle}
        >
          Add confirmed places to candidate pool
        </button>
      </div>
    </div>
  );
}

function DocumentEvidencePanel({
  tripId,
  evidence,
  activeMentionId,
  onRetryPage,
}: {
  tripId: string;
  evidence: DocumentExtractionEvidenceResponse;
  activeMentionId: string | null;
  onRetryPage: (pageNumber: number) => Promise<void>;
}) {
  const summary = buildDocumentEvidenceSummary(evidence);
  const activeEvidence = evidence.mention_evidence.find((mention) => mention.mention_id === activeMentionId) ?? null;
  const pageNumbers = evidence.pages.map((page) => page.page_number).sort((first, second) => first - second);
  const suggestedPageNumber = activeEvidence?.box_evidence?.[0]?.page_number ?? activeEvidence?.page_numbers[0] ?? pageNumbers[0] ?? null;
  const [selectedPageNumber, setSelectedPageNumber] = useState<number | null>(suggestedPageNumber);
  const [zoom, setZoom] = useState(1);
  const [retryingPage, setRetryingPage] = useState<number | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);
  const activePageNumber = selectedPageNumber ?? suggestedPageNumber;
  const activePage = activePageNumber
    ? evidence.pages.find((page) => page.page_number === activePageNumber) ?? null
    : null;
  const [preview, setPreview] = useState<
    | { status: "idle" }
    | { status: "loading"; pageNumber: number }
    | { status: "ready"; pageNumber: number; url: string; width: number; height: number }
    | { status: "error"; pageNumber: number }
  >({ status: "idle" });
  const previewUrlRef = useRef<string | null>(null);
  const surface = preview.status === "ready"
    ? fitPreviewSurface(preview.width, preview.height)
    : pagePreviewSurface(activePage);
  const zoomedSurface = { width: Math.round(surface.width * zoom), height: Math.round(surface.height * zoom) };
  const boxes = activeEvidence ? mentionEvidenceBoxesForPage(activeEvidence, activePageNumber) : [];
  const overlayBoxes = boxes
    .map((box) => mapNormalizedBoxToOverlay(box, zoomedSurface));

  useEffect(() => {
    setSelectedPageNumber(suggestedPageNumber);
  }, [suggestedPageNumber]);

  useEffect(() => {
    if (!activePageNumber || !activePage?.preview_artifact_id) {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = null;
      }
      setPreview({ status: "idle" });
      return;
    }
    let cancelled = false;
    setPreview({ status: "loading", pageNumber: activePageNumber });
    void fetchDocumentPagePreviewBlob(tripId, evidence.job.id, activePageNumber).then((response) => {
      if (cancelled) {
        return;
      }
      if (!response.ok) {
        if (previewUrlRef.current) {
          URL.revokeObjectURL(previewUrlRef.current);
          previewUrlRef.current = null;
        }
        setPreview({ status: "error", pageNumber: activePageNumber });
        return;
      }
      const url = URL.createObjectURL(response.data);
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
      previewUrlRef.current = url;
      setPreview({
        status: "ready",
        pageNumber: activePageNumber,
        url,
        width: numericMetadata(activePage.metadata.image_width) ?? DOCUMENT_EVIDENCE_MAX_SURFACE.width,
        height: numericMetadata(activePage.metadata.image_height) ?? DOCUMENT_EVIDENCE_MAX_SURFACE.height,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [activePage?.metadata, activePage?.preview_artifact_id, activePageNumber, evidence.job.id, tripId]);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
    };
  }, []);

  if (!summary) {
    return null;
  }
  return (
    <div style={documentEvidenceStyle} data-document-evidence>
      <div style={provenanceRowStyle}>
        <span>Document</span>
        <span>{evidence.generation.strategy} · {summary.pageCount} page(s)</span>
      </div>
      <div style={provenanceRowStyle}>
        <span>Lineage</span>
        <span>{summary.layoutArtifactId ? "layout" : "no layout"} · {summary.spanMapArtifactId ? "span map" : "no span map"}</span>
      </div>
      <div style={provenanceRowStyle}>
        <span>Geometry</span>
        <span>{summary.geometryMentionCount}/{summary.mentionCount} mention(s) · {summary.spanMapCount} span(s)</span>
      </div>
      <div style={provenanceRowStyle}>
        <span>Reading</span>
        <span>{summary.readingOrderAlgorithm ?? "unknown"}</span>
      </div>
      {pageNumbers.length ? (
        <div style={documentEvidenceControlsStyle} data-document-page-controls>
          <button
            type="button"
            onClick={() => setSelectedPageNumber(previousPageNumber(pageNumbers, activePageNumber))}
            disabled={pageNumbers.length <= 1}
            style={miniButtonStyle}
            aria-label="Previous document page"
          >
            Prev
          </button>
          <span style={hintStyle}>Page {activePageNumber ?? "-"} / {pageNumbers.length}</span>
          <button
            type="button"
            onClick={() => setSelectedPageNumber(nextPageNumber(pageNumbers, activePageNumber))}
            disabled={pageNumbers.length <= 1}
            style={miniButtonStyle}
            aria-label="Next document page"
          >
            Next
          </button>
          <button type="button" onClick={() => setZoom((value) => Math.max(0.75, Math.round((value - 0.25) * 100) / 100))} style={miniButtonStyle} aria-label="Zoom document page out">-</button>
          <span style={hintStyle}>{Math.round(zoom * 100)}%</span>
          <button type="button" onClick={() => setZoom((value) => Math.min(2, Math.round((value + 0.25) * 100) / 100))} style={miniButtonStyle} aria-label="Zoom document page in">+</button>
          {activePage?.retryable ? (
            <button
              type="button"
              disabled={retryingPage === activePage.page_number}
              onClick={() => {
                setRetryError(null);
                setRetryingPage(activePage.page_number);
                Promise.resolve(onRetryPage(activePage.page_number))
                  .catch((error: unknown) => setRetryError(error instanceof Error ? error.message : "Retry failed"))
                  .finally(() => setRetryingPage(null));
              }}
              style={miniButtonStyle}
              data-document-page-retry
            >
              {retryingPage === activePage.page_number ? "Retrying" : "Retry page"}
            </button>
          ) : null}
        </div>
      ) : null}
      {retryError ? <p style={errorStyle}>{retryError}</p> : null}
      {activeEvidence ? (
        <div style={documentEvidenceOverlayRowStyle}>
          <span style={hintStyle}>
            {activeEvidence.mention_text} · {activeEvidence.geometry_available ? `page ${activeEvidence.page_numbers.join(", ")}` : "geometry unavailable"}
          </span>
          <div style={{ ...documentPageSurfaceStyle, width: zoomedSurface.width, height: zoomedSurface.height }} aria-label="Active mention document geometry">
            {preview.status === "ready" ? (
              <img
                src={preview.url}
                alt=""
                style={documentPagePreviewImageStyle}
                onLoad={(event) => {
                  const image = event.currentTarget;
                  if (image.naturalWidth > 0 && image.naturalHeight > 0) {
                    setPreview((current) =>
                      current.status === "ready" && current.pageNumber === preview.pageNumber
                        ? { ...current, width: image.naturalWidth, height: image.naturalHeight }
                        : current,
                    );
                  }
                }}
              />
            ) : null}
            {overlayBoxes.map((box, index) => (
              <span
                key={`${box.left}:${box.top}:${index}`}
                data-document-evidence-box
                style={{
                  ...documentBoxStyle,
                  left: box.left,
                  top: box.top,
                  width: box.pixelWidth,
                  height: box.pixelHeight,
                }}
              />
            ))}
            {preview.status === "loading" ? <span style={documentPreviewStatusStyle}>Loading preview</span> : null}
            {preview.status === "error" || !activePage?.preview_artifact_id ? (
              <span style={documentPreviewStatusStyle}>Preview unavailable</span>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function mentionEvidenceBoxesForPage(
  activeEvidence: DocumentExtractionEvidenceResponse["mention_evidence"][number],
  pageNumber: number | null,
) {
  const linkedBoxes = (activeEvidence.box_evidence ?? [])
    .filter((box) => pageNumber === null || box.page_number === pageNumber)
    .flatMap((box) => {
      const normalized = toNormalizedDocumentBox(box.bbox);
      return normalized ? [normalized] : [];
    });
  if (linkedBoxes.length) {
    return linkedBoxes;
  }
  return mentionEvidenceBoxes(activeEvidence);
}

function previousPageNumber(pageNumbers: number[], current: number | null): number {
  if (!pageNumbers.length) {
    return 1;
  }
  const index = Math.max(0, pageNumbers.indexOf(current ?? pageNumbers[0]));
  return pageNumbers[Math.max(0, index - 1)] ?? pageNumbers[0];
}

function nextPageNumber(pageNumbers: number[], current: number | null): number {
  if (!pageNumbers.length) {
    return 1;
  }
  const index = Math.max(0, pageNumbers.indexOf(current ?? pageNumbers[0]));
  return pageNumbers[Math.min(pageNumbers.length - 1, index + 1)] ?? pageNumbers[pageNumbers.length - 1];
}

function URLProvenance({ sourceFetch }: { sourceFetch: URLFetchSnapshot }) {
  return (
    <div style={provenanceStyle} data-url-provenance>
      <div style={provenanceRowStyle}>
        <span>Source</span>
        {sourceFetch.final_url_sanitized ? (
          <a href={sourceFetch.final_url_sanitized} target="_blank" rel="noopener noreferrer" style={sourceLinkStyle}>
            {sourceFetch.final_host ?? sourceFetch.source_host ?? "open source"}
          </a>
        ) : (
          <span>{sourceFetch.source_host ?? "verified URL"}</span>
        )}
      </div>
      <div style={provenanceRowStyle}>
        <span>Robots</span>
        <span>{sourceFetch.robots_status}</span>
      </div>
      <div style={provenanceRowStyle}>
        <span>Redirects</span>
        <span>{sourceFetch.redirect_chain.length}</span>
      </div>
      <div style={provenanceRowStyle}>
        <span>Content</span>
        <span>{sourceFetch.content_type} · {sourceFetch.decoded_bytes} bytes</span>
      </div>
      {sourceFetch.page_title ? (
        <div style={provenanceRowStyle}>
          <span>Title</span>
          <span>{sourceFetch.page_title}</span>
        </div>
      ) : null}
    </div>
  );
}

function MentionCard({
  mention,
  active,
  onSelect,
  onDecision,
}: {
  mention: ImportMention;
  active: boolean;
  onSelect: () => void;
  onDecision: (action: "confirm" | "ignore" | "mark_as_note") => void;
}) {
  const selected = selectedResolutionId(mention);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          onSelect();
        }
      }}
      style={{ ...mentionCardStyle, borderColor: active ? "#7ba07f" : "rgba(21,21,21,0.1)" }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <strong style={{ color: "var(--ec-ink)", fontSize: 13 }}>{mention.raw_text}</strong>
        <span style={smallPillStyle}>{mention.entity_type}</span>
      </div>
      <p style={{ margin: 0, fontSize: 12, color: "var(--ec-slate)", lineHeight: 1.45 }}>
        {mention.review_state} · confidence {Math.round(mention.confidence * 100)}%
      </p>
      {mention.resolution_candidates.length ? (
        <div style={{ display: "grid", gap: 6 }}>
          {mention.resolution_candidates.slice(0, 3).map((candidate) => (
            <div key={candidate.id} style={candidateRowStyle}>
              <span>{candidate.canonical_name}</span>
              <span>{candidate.data_state}</span>
            </div>
          ))}
        </div>
      ) : null}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {mention.entity_type === "place" && selected ? (
          <span role="button" tabIndex={0} onClick={(event) => { event.stopPropagation(); onDecision("confirm"); }} style={miniActionStyle}>
            Confirm
          </span>
        ) : null}
        <span role="button" tabIndex={0} onClick={(event) => { event.stopPropagation(); onDecision("ignore"); }} style={miniActionStyle}>
          Ignore
        </span>
        {mention.entity_type !== "place" ? (
          <span role="button" tabIndex={0} onClick={(event) => { event.stopPropagation(); onDecision("mark_as_note"); }} style={miniActionStyle}>
            Preserve note
          </span>
        ) : null}
      </div>
    </div>
  );
}

function utf8ByteLength(value: string): number {
  return new TextEncoder().encode(value).length;
}

function validateBrowserUrl(value: string): string | null {
  if (!value) {
    return null;
  }
  try {
    const parsed = new URL(value);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return "Only http:// and https:// URLs are supported.";
    }
    if (value.length > 2048) {
      return "URL is too long.";
    }
    return null;
  } catch {
    return "Enter a valid URL.";
  }
}

function recoveryMessage(code: string | undefined, fallback: string): string {
  switch (code) {
    case "import_url_robots_disallowed":
      return "该网站不允许自动获取此页面。请复制正文后使用 Text Import。";
    case "import_url_access_required":
    case "import_url_login_wall_detected":
      return "该页面需要登录，系统不会绕过登录限制。请复制正文或稍后上传截图。";
    case "import_url_dynamic_rendering_required":
      return "该页面依赖浏览器脚本，当前安全导入器不执行 JavaScript。请粘贴正文。";
    case "import_url_unsupported_content_type":
      return "该链接不是网页文本。本轮不处理 PDF/图片。";
    case "import_url_robots_unavailable":
      return "robots.txt 暂时不可验证，系统按 fail-closed 处理。请粘贴正文。";
    default:
      return fallback;
  }
}

const panelStyle = {
  display: "grid",
  gap: 14,
  padding: 16,
  borderRadius: 18,
  border: "1px solid rgba(21,21,21,0.1)",
  background: "rgba(255,253,249,0.95)",
} satisfies CSSProperties;

const eyebrowStyle = { margin: 0, fontSize: 11, fontWeight: 900, color: "#6c7f5f", textTransform: "uppercase" } satisfies CSSProperties;
const titleStyle = { margin: "3px 0 0", fontSize: 18, color: "var(--ec-ink)" } satisfies CSSProperties;
const hintStyle = { fontSize: 12, color: "var(--ec-slate)" } satisfies CSSProperties;
const statusPillStyle = { ...hintStyle, padding: "5px 8px", borderRadius: 999, background: "rgba(21,21,21,0.05)" } satisfies CSSProperties;
const textareaStyle = { width: "100%", minHeight: 116, resize: "vertical", borderRadius: 12, border: "1px solid rgba(21,21,21,0.12)", padding: 12, font: "inherit", lineHeight: 1.5, background: "white", color: "var(--ec-ink)" } satisfies CSSProperties;
const inputStyle = { width: "100%", borderRadius: 12, border: "1px solid rgba(21,21,21,0.12)", padding: 12, font: "inherit", lineHeight: 1.5, background: "white", color: "var(--ec-ink)" } satisfies CSSProperties;
const segmentStyle = { display: "inline-flex", width: "fit-content", padding: 3, gap: 2, borderRadius: 999, background: "rgba(21,21,21,0.06)" } satisfies CSSProperties;
const segmentButtonStyle = { border: 0, borderRadius: 999, padding: "7px 11px", background: "transparent", color: "var(--ec-slate)", fontWeight: 900, cursor: "pointer" } satisfies CSSProperties;
const segmentActiveStyle = { ...segmentButtonStyle, background: "white", color: "var(--ec-ink)", boxShadow: "0 1px 4px rgba(21,21,21,0.08)" } satisfies CSSProperties;
const primaryButtonStyle = { border: 0, borderRadius: 999, padding: "9px 13px", background: "#151515", color: "white", fontWeight: 900, cursor: "pointer" } satisfies CSSProperties;
const secondaryButtonStyle = { border: "1px solid rgba(21,21,21,0.14)", borderRadius: 999, padding: "8px 12px", background: "rgba(255,255,255,0.8)", color: "var(--ec-ink)", fontWeight: 800, cursor: "pointer" } satisfies CSSProperties;
const noticeStyle = { margin: 0, fontSize: 12, color: "#5f6f54", lineHeight: 1.5 } satisfies CSSProperties;
const errorStyle = { margin: 0, fontSize: 12, color: "#9d302a", lineHeight: 1.5 } satisfies CSSProperties;
const documentExtractionStyle = { display: "grid", gap: 8, padding: 12, borderRadius: 12, border: "1px solid rgba(21,21,21,0.08)", background: "rgba(255,255,255,0.82)" } satisfies CSSProperties;
const hintBlockStyle = { ...hintStyle, margin: "4px 0 0", lineHeight: 1.5 } satisfies CSSProperties;
const reviewGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))", gap: 12 } satisfies CSSProperties;
const sourcePaneStyle = { display: "grid", gap: 8, minWidth: 0 } satisfies CSSProperties;
const provenanceStyle = { display: "grid", gap: 5, padding: 10, borderRadius: 12, border: "1px solid rgba(21,21,21,0.08)", background: "rgba(255,255,255,0.8)", fontSize: 12, color: "var(--ec-slate)" } satisfies CSSProperties;
const provenanceRowStyle = { display: "flex", justifyContent: "space-between", gap: 10, overflowWrap: "anywhere" } satisfies CSSProperties;
const documentEvidenceStyle = { ...provenanceStyle, background: "rgba(255,255,255,0.9)" } satisfies CSSProperties;
const documentEvidenceControlsStyle = { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" } satisfies CSSProperties;
const documentEvidenceOverlayRowStyle = { display: "grid", gap: 8, justifyItems: "start" } satisfies CSSProperties;
const documentPageSurfaceStyle = { position: "relative", borderRadius: 8, border: "1px solid rgba(21,21,21,0.12)", background: "rgba(21,21,21,0.035)", overflow: "hidden" } satisfies CSSProperties;
const documentPagePreviewImageStyle = { position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "fill" } satisfies CSSProperties;
const documentBoxStyle = { position: "absolute", display: "block", border: "1px solid #48673f", background: "rgba(123,160,127,0.28)", borderRadius: 2, pointerEvents: "none" } satisfies CSSProperties;
const miniButtonStyle = { border: "1px solid rgba(21,21,21,0.12)", borderRadius: 8, padding: "4px 7px", background: "white", color: "var(--ec-ink)", fontSize: 11, fontWeight: 800, cursor: "pointer" } satisfies CSSProperties;
const documentPreviewStatusStyle = { position: "absolute", inset: 0, display: "grid", placeItems: "center", fontSize: 11, color: "var(--ec-slate)", background: "rgba(255,255,255,0.7)" } satisfies CSSProperties;
const sourceLinkStyle = { color: "#48673f", fontWeight: 900, textDecoration: "none" } satisfies CSSProperties;
const sourceTextStyle = { margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 420, overflow: "auto", padding: 12, borderRadius: 12, border: "1px solid rgba(21,21,21,0.08)", background: "rgba(21,21,21,0.035)", color: "var(--ec-ink)", fontFamily: "inherit", lineHeight: 1.6 } satisfies CSSProperties;
const markStyle = { background: "rgba(247,208,138,0.85)", color: "inherit", borderRadius: 4, padding: "1px 2px" } satisfies CSSProperties;
const summaryStyle = { fontSize: 12, color: "var(--ec-slate)", padding: 10, borderRadius: 10, background: "rgba(239,248,243,0.9)" } satisfies CSSProperties;
const mentionCardStyle = { textAlign: "left", display: "grid", gap: 8, padding: 10, borderRadius: 12, border: "1px solid rgba(21,21,21,0.1)", background: "white", cursor: "pointer" } satisfies CSSProperties;
const smallPillStyle = { fontSize: 11, color: "var(--ec-slate)", padding: "3px 7px", borderRadius: 999, background: "rgba(21,21,21,0.05)" } satisfies CSSProperties;
const candidateRowStyle = { display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12, color: "var(--ec-slate)", padding: "6px 8px", borderRadius: 8, background: "rgba(21,21,21,0.035)" } satisfies CSSProperties;
const miniActionStyle = { fontSize: 12, fontWeight: 900, color: "#48673f", cursor: "pointer" } satisfies CSSProperties;
