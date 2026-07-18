"use client";

import { type CSSProperties, useEffect, useReducer, useRef, useState } from "react";
import type { TripPersistenceState } from "@/features/trip-workspace/tripPersistence";
import {
  commitImport,
  decideImportMention,
  fetchBinaryInspection,
  fetchImportArtifact,
  fetchImportReview,
  fetchSanitizedImageBlob,
  submitBinaryImport,
  submitUrlImport,
  submitTextImport,
} from "./importApi";
import { BinaryImportComposer } from "./BinaryImportComposer";
import { BinaryInspectionResult } from "./BinaryInspectionResult";
import {
  binaryImportIdempotencyKey,
  binaryImportReducer,
  binaryImportStorageValue,
  parseBinaryImportStorageValue,
} from "./binaryImportState";
import { importIdempotencyKey, importWorkspaceReducer } from "./importState";
import type { ImportMention, URLFetchSnapshot } from "./importTypes";
import { buildImportSummary, selectedResolutionId, sourceSegments } from "./importViewModel";

type ImportReviewWorkspaceProps = {
  tripPersistence: TripPersistenceState;
  onCandidatesChanged: (tripId: string) => void;
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
  const binaryInputRef = useRef<HTMLInputElement | null>(null);
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
    <section style={panelStyle} data-import-workspace>
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
            onReset={() => binaryDispatch({ type: "reset" })}
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
          sourceText={state.sourceText}
          mentions={state.mentions}
          activeMentionId={state.activeMentionId}
          reviewVersion={state.reviewVersion}
          onSelect={(mentionId) => dispatch({ type: "select", mentionId })}
          onDecision={(mention, action) => void handleDecision(mention, action)}
          onCommit={() => void handleCommit()}
          sourceFetch={state.sourceFetch}
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
      {mode === "binary" ? <BinaryInspectionResult state={binaryState} /> : null}
    </section>
  );
}

const BINARY_IMPORT_STORAGE_KEY = "ai-travel-planner:last-binary-import";

function rememberBinaryImport(tripId: string, jobId: string, declaredKind: "image" | "pdf") {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(BINARY_IMPORT_STORAGE_KEY, binaryImportStorageValue(tripId, jobId, declaredKind));
}

function ReviewPane({
  sourceText,
  mentions,
  activeMentionId,
  reviewVersion,
  onSelect,
  onDecision,
  onCommit,
  sourceFetch,
}: {
  sourceText: string;
  mentions: ImportMention[];
  activeMentionId: string | null;
  reviewVersion: number;
  onSelect: (mentionId: string) => void;
  onDecision: (mention: ImportMention, action: "confirm" | "ignore" | "mark_as_note") => void;
  onCommit: () => void;
  sourceFetch?: URLFetchSnapshot | null;
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
const reviewGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))", gap: 12 } satisfies CSSProperties;
const sourcePaneStyle = { display: "grid", gap: 8, minWidth: 0 } satisfies CSSProperties;
const provenanceStyle = { display: "grid", gap: 5, padding: 10, borderRadius: 12, border: "1px solid rgba(21,21,21,0.08)", background: "rgba(255,255,255,0.8)", fontSize: 12, color: "var(--ec-slate)" } satisfies CSSProperties;
const provenanceRowStyle = { display: "flex", justifyContent: "space-between", gap: 10, overflowWrap: "anywhere" } satisfies CSSProperties;
const sourceLinkStyle = { color: "#48673f", fontWeight: 900, textDecoration: "none" } satisfies CSSProperties;
const sourceTextStyle = { margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 420, overflow: "auto", padding: 12, borderRadius: 12, border: "1px solid rgba(21,21,21,0.08)", background: "rgba(21,21,21,0.035)", color: "var(--ec-ink)", fontFamily: "inherit", lineHeight: 1.6 } satisfies CSSProperties;
const markStyle = { background: "rgba(247,208,138,0.85)", color: "inherit", borderRadius: 4, padding: "1px 2px" } satisfies CSSProperties;
const summaryStyle = { fontSize: 12, color: "var(--ec-slate)", padding: 10, borderRadius: 10, background: "rgba(239,248,243,0.9)" } satisfies CSSProperties;
const mentionCardStyle = { textAlign: "left", display: "grid", gap: 8, padding: 10, borderRadius: 12, border: "1px solid rgba(21,21,21,0.1)", background: "white", cursor: "pointer" } satisfies CSSProperties;
const smallPillStyle = { fontSize: 11, color: "var(--ec-slate)", padding: "3px 7px", borderRadius: 999, background: "rgba(21,21,21,0.05)" } satisfies CSSProperties;
const candidateRowStyle = { display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12, color: "var(--ec-slate)", padding: "6px 8px", borderRadius: 8, background: "rgba(21,21,21,0.035)" } satisfies CSSProperties;
const miniActionStyle = { fontSize: 12, fontWeight: 900, color: "#48673f", cursor: "pointer" } satisfies CSSProperties;
