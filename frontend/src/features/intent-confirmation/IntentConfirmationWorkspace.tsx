"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";
import type { TripPersistenceState } from "@/features/trip-workspace/tripPersistence";
import {
  answerIntentClarification,
  compileTripIntentEnvelope,
  listTripIntentEnvelopes,
} from "./intentApi";
import {
  buildIntentCompileIdempotencyKey,
  summarizeIntentEnvelope,
} from "./intentConfirmationModel";
import type { SourceLinkedTripIntentEnvelope, TripIntentRevisionMetadata } from "./intentTypes";

type Props = {
  tripPersistence: TripPersistenceState;
  directUserText: string;
};

export function IntentConfirmationWorkspace({ tripPersistence, directUserText }: Props) {
  const [envelope, setEnvelope] = useState<SourceLinkedTripIntentEnvelope | null>(null);
  const [history, setHistory] = useState<TripIntentRevisionMetadata[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const summary = useMemo(() => summarizeIntentEnvelope(envelope), [envelope]);
  const saved = tripPersistence.status === "saved" ? tripPersistence : null;

  useEffect(() => {
    if (!saved) {
      setHistory([]);
      setEnvelope(null);
      return;
    }
    void refreshHistory(saved.tripId);
  }, [saved?.tripId, saved?.currentRevisionId]);

  async function refreshHistory(tripId: string) {
    const result = await listTripIntentEnvelopes(tripId);
    if (result.ok) {
      setHistory(result.data.revisions);
    }
  }

  async function handleCompile() {
    if (!saved) {
      setStatus("Save the trip before compiling an intent contract.");
      return;
    }
    setStatus("Compiling intent contract...");
    const result = await compileTripIntentEnvelope(
      saved.tripId,
      {
        base_revision_id: saved.currentRevisionId,
        direct_user_text: directUserText,
        use_llm_proposal_adapter: true,
      },
      buildIntentCompileIdempotencyKey(saved.tripId, saved.currentRevisionId, directUserText),
    );
    if (!result.ok) {
      setStatus(result.message);
      return;
    }
    setEnvelope(result.data.envelope);
    setStatus(result.data.idempotent_replay ? "Loaded existing compiled contract." : "Compiled immutable intent contract.");
    await refreshHistory(saved.tripId);
  }

  async function handleAnswerClarification(questionId: string) {
    if (!saved || !envelope || !clarificationAnswer.trim()) {
      return;
    }
    const result = await answerIntentClarification(
      saved.tripId,
      envelope.id,
      questionId,
      { base_revision_id: saved.currentRevisionId, answer: clarificationAnswer.trim() },
      `intent-clarify:${envelope.id}:${questionId}:${saved.currentRevisionId}`,
    );
    if (!result.ok) {
      setStatus(result.message);
      return;
    }
    setEnvelope(result.data.envelope);
    setClarificationAnswer("");
    setStatus("Saved clarification as a new intent revision.");
    await refreshHistory(saved.tripId);
  }

  return (
    <section className="intent-confirmation-workspace" aria-label="Intent Confirmation Workspace">
      <div className="intent-confirmation-workspace__header">
        <div>
          <p>Intent contract</p>
          <h3>Source-linked confirmation</h3>
        </div>
        <button type="button" onClick={handleCompile} disabled={!saved}>
          Compile
        </button>
      </div>
      <div className="intent-confirmation-workspace__stats">
        <span>{summary.statusLabel}</span>
        <span>{summary.selectedFields.length} selected</span>
        <span>{summary.blockingConflictCount} blocking</span>
        <span>{summary.clarificationCount} questions</span>
      </div>
      {status ? <p className="intent-confirmation-workspace__status">{status}</p> : null}
      {envelope ? (
        <div className="intent-confirmation-workspace__body">
          <FieldList title="Selected fields" fields={summary.selectedFields} />
          {envelope.conflicts.length ? (
            <div className="intent-confirmation-workspace__panel">
              <strong>Conflicts</strong>
              {envelope.conflicts.map((conflict) => (
                <p key={conflict.conflict_id}>
                  {conflict.severity}: {conflict.reason_code} · {conflict.explanation}
                </p>
              ))}
            </div>
          ) : null}
          {envelope.clarification_queue.map((question) => (
            <div className="intent-confirmation-workspace__panel" key={question.question_id}>
              <strong>{question.question}</strong>
              <div className="intent-confirmation-workspace__answer">
                <input
                  value={clarificationAnswer}
                  onChange={(event) => setClarificationAnswer(event.target.value)}
                  placeholder="Answer clarification"
                />
                <button type="button" onClick={() => void handleAnswerClarification(question.question_id)}>
                  Save answer
                </button>
              </div>
            </div>
          ))}
          {envelope.assumptions.length ? (
            <div className="intent-confirmation-workspace__panel">
              <strong>Assumptions</strong>
              {envelope.assumptions.map((item) => (
                <p key={item}>{item}</p>
              ))}
            </div>
          ) : null}
        </div>
      ) : (
        <p className="intent-confirmation-workspace__empty">
          Compile the saved trip inputs into a reviewable intent contract before planner handoff.
        </p>
      )}
      {history.length ? (
        <div className="intent-confirmation-workspace__history">
          {history.slice(0, 4).map((revision) => (
            <span key={revision.id}>Intent rev {revision.revision_number}</span>
          ))}
        </div>
      ) : null}
      <style>{`
        .intent-confirmation-workspace {
          display: grid;
          gap: 12px;
          padding: 16px;
          border: 1px solid var(--ec-line-soft);
          border-radius: 24px;
          background: linear-gradient(180deg, rgba(255,253,249,0.92), rgba(247,244,238,0.72));
          box-shadow: 0 12px 32px rgba(21,21,21,0.035);
        }
        .intent-confirmation-workspace__header {
          display: flex;
          align-items: start;
          justify-content: space-between;
          gap: 12px;
        }
        .intent-confirmation-workspace__header p {
          margin: 0 0 4px;
          color: #557060;
          font-size: 11px;
          font-weight: 900;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }
        .intent-confirmation-workspace__header h3 {
          margin: 0;
          color: var(--ec-ink);
          font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
          font-size: 22px;
          line-height: 1.12;
        }
        .intent-confirmation-workspace button {
          border: 1px solid rgba(21,21,21,0.12);
          border-radius: 999px;
          padding: 8px 11px;
          background: var(--ec-night);
          color: #fffdf9;
          font-size: 12px;
          font-weight: 900;
          cursor: pointer;
        }
        .intent-confirmation-workspace button:disabled {
          cursor: not-allowed;
          opacity: 0.45;
        }
        .intent-confirmation-workspace__stats,
        .intent-confirmation-workspace__history {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .intent-confirmation-workspace__stats span,
        .intent-confirmation-workspace__history span {
          border: 1px solid rgba(21,21,21,0.08);
          border-radius: 999px;
          padding: 6px 8px;
          background: rgba(255,253,249,0.74);
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 900;
        }
        .intent-confirmation-workspace__status,
        .intent-confirmation-workspace__empty,
        .intent-confirmation-workspace__panel p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.55;
        }
        .intent-confirmation-workspace__body {
          display: grid;
          gap: 10px;
        }
        .intent-confirmation-workspace__panel {
          display: grid;
          gap: 7px;
          padding: 10px;
          border: 1px solid rgba(21,21,21,0.08);
          border-radius: 16px;
          background: rgba(255,253,249,0.66);
        }
        .intent-confirmation-workspace__panel strong {
          color: var(--ec-ink);
          font-size: 12px;
        }
        .intent-confirmation-workspace__answer {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 8px;
        }
        .intent-confirmation-workspace__answer input {
          min-width: 0;
          border: 1px solid rgba(21,21,21,0.12);
          border-radius: 12px;
          padding: 8px 10px;
          background: rgba(255,253,249,0.86);
          color: var(--ec-ink);
          font-size: 13px;
        }
      `}</style>
    </section>
  );
}

function FieldList({ title, fields }: { title: string; fields: SourceLinkedTripIntentEnvelope["fields"] }) {
  return (
    <div className="intent-confirmation-workspace__panel">
      <strong>{title}</strong>
      {fields.map((field) => (
        <p key={field.field_id}>
          {field.field_path}: {formatValue(field.value)} · {field.kind} · {field.source_refs[0]?.source_type}
        </p>
      ))}
    </div>
  );
}

function formatValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value == null) {
    return "empty";
  }
  return JSON.stringify(value);
}
