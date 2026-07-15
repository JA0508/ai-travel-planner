"use client";

import { type CSSProperties, useReducer, useState } from "react";
import type { TripPersistenceState } from "@/features/trip-workspace/tripPersistence";
import {
  commitImport,
  decideImportMention,
  fetchImportArtifact,
  fetchImportReview,
  submitTextImport,
} from "./importApi";
import { importIdempotencyKey, importWorkspaceReducer } from "./importState";
import type { ImportMention } from "./importTypes";
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
  const [state, dispatch] = useReducer(importWorkspaceReducer, { status: "idle" });
  const byteCount = utf8ByteLength(text);
  const savedTripId = tripPersistence.status === "saved" ? tripPersistence.tripId : null;

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
          <h3 style={titleStyle}>Text to review inbox</h3>
        </div>
        <span style={statusPillStyle}>{state.status}</span>
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Paste a guide, note, or group-chat excerpt. Text only in this foundation slice."
          disabled={!savedTripId || state.status === "submitting"}
          style={textareaStyle}
        />
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
          <span style={hintStyle}>{byteCount} bytes · private artifact · no itinerary mutation</span>
          <div style={{ display: "flex", gap: 8 }}>
            <button type="button" onClick={() => setText("")} style={secondaryButtonStyle}>
              Clear
            </button>
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={!savedTripId || !text.trim() || state.status === "submitting"}
              style={primaryButtonStyle}
            >
              {state.status === "submitting" ? "Importing..." : "Import text"}
            </button>
          </div>
        </div>
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
    </section>
  );
}

function ReviewPane({
  sourceText,
  mentions,
  activeMentionId,
  reviewVersion,
  onSelect,
  onDecision,
  onCommit,
}: {
  sourceText: string;
  mentions: ImportMention[];
  activeMentionId: string | null;
  reviewVersion: number;
  onSelect: (mentionId: string) => void;
  onDecision: (mention: ImportMention, action: "confirm" | "ignore" | "mark_as_note") => void;
  onCommit: () => void;
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
const primaryButtonStyle = { border: 0, borderRadius: 999, padding: "9px 13px", background: "#151515", color: "white", fontWeight: 900, cursor: "pointer" } satisfies CSSProperties;
const secondaryButtonStyle = { border: "1px solid rgba(21,21,21,0.14)", borderRadius: 999, padding: "8px 12px", background: "rgba(255,255,255,0.8)", color: "var(--ec-ink)", fontWeight: 800, cursor: "pointer" } satisfies CSSProperties;
const noticeStyle = { margin: 0, fontSize: 12, color: "#5f6f54", lineHeight: 1.5 } satisfies CSSProperties;
const errorStyle = { margin: 0, fontSize: 12, color: "#9d302a", lineHeight: 1.5 } satisfies CSSProperties;
const reviewGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))", gap: 12 } satisfies CSSProperties;
const sourcePaneStyle = { display: "grid", gap: 8, minWidth: 0 } satisfies CSSProperties;
const sourceTextStyle = { margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 420, overflow: "auto", padding: 12, borderRadius: 12, border: "1px solid rgba(21,21,21,0.08)", background: "rgba(21,21,21,0.035)", color: "var(--ec-ink)", fontFamily: "inherit", lineHeight: 1.6 } satisfies CSSProperties;
const markStyle = { background: "rgba(247,208,138,0.85)", color: "inherit", borderRadius: 4, padding: "1px 2px" } satisfies CSSProperties;
const summaryStyle = { fontSize: 12, color: "var(--ec-slate)", padding: 10, borderRadius: 10, background: "rgba(239,248,243,0.9)" } satisfies CSSProperties;
const mentionCardStyle = { textAlign: "left", display: "grid", gap: 8, padding: 10, borderRadius: 12, border: "1px solid rgba(21,21,21,0.1)", background: "white", cursor: "pointer" } satisfies CSSProperties;
const smallPillStyle = { fontSize: 11, color: "var(--ec-slate)", padding: "3px 7px", borderRadius: 999, background: "rgba(21,21,21,0.05)" } satisfies CSSProperties;
const candidateRowStyle = { display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12, color: "var(--ec-slate)", padding: "6px 8px", borderRadius: 8, background: "rgba(21,21,21,0.035)" } satisfies CSSProperties;
const miniActionStyle = { fontSize: 12, fontWeight: 900, color: "#48673f", cursor: "pointer" } satisfies CSSProperties;
