"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";
import type { TripPersistenceState } from "@/features/trip-workspace/tripPersistence";
import {
  answerIntentClarification,
  compileTripIntentEnvelope,
  editTripIntentEnvelope,
  getTripIntentEnvelope,
  listTripIntentEnvelopes,
  restoreTripIntentEnvelope,
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

type IntentEditForm = {
  city: string;
  tripDays: string;
  pace: "" | "relaxed" | "balanced" | "intensive";
  transportPreferences: string;
};

export function IntentConfirmationWorkspace({ tripPersistence, directUserText }: Props) {
  const [envelope, setEnvelope] = useState<SourceLinkedTripIntentEnvelope | null>(null);
  const [history, setHistory] = useState<TripIntentRevisionMetadata[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const [editForm, setEditForm] = useState<IntentEditForm>({
    city: "",
    tripDays: "",
    pace: "",
    transportPreferences: "",
  });
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

  useEffect(() => {
    if (!envelope) {
      setEditForm({ city: "", tripDays: "", pace: "", transportPreferences: "" });
      return;
    }
    setEditForm({
      city: envelope.planner_ready_intent.city ?? "",
      tripDays: envelope.planner_ready_intent.trip_days
        ? String(envelope.planner_ready_intent.trip_days)
        : "",
      pace: isPace(envelope.planner_ready_intent.pace) ? envelope.planner_ready_intent.pace : "",
      transportPreferences: envelope.planner_ready_intent.transport_preferences.join(", "),
    });
  }, [envelope]);

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

  async function handleLoadRevision(intentRevisionId: string) {
    if (!saved) {
      return;
    }
    const result = await getTripIntentEnvelope(saved.tripId, intentRevisionId);
    if (!result.ok) {
      setStatus(result.message);
      return;
    }
    setEnvelope(result.data.envelope);
    setStatus(`Loaded intent revision ${result.data.revision.revision_number}.`);
  }

  async function handleEditIntent() {
    if (!saved || !envelope) {
      return;
    }
    const tripDays = editForm.tripDays.trim() ? Number(editForm.tripDays.trim()) : null;
    if (tripDays !== null && (!Number.isInteger(tripDays) || tripDays < 1)) {
      setStatus("Trip days must be a positive whole number.");
      return;
    }
    const transportPreferences = editForm.transportPreferences
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const result = await editTripIntentEnvelope(
      saved.tripId,
      envelope.id,
      {
        base_revision_id: saved.currentRevisionId,
        field_updates: {
          city: editForm.city.trim() || null,
          trip_days: tripDays,
          pace: editForm.pace || null,
          transport_preferences: transportPreferences,
        },
      },
      `intent-edit:${envelope.id}:${saved.currentRevisionId}:${editForm.city}:${editForm.tripDays}:${editForm.pace}:${transportPreferences.join("|")}`,
    );
    if (!result.ok) {
      setStatus(result.message);
      return;
    }
    setEnvelope(result.data.envelope);
    setStatus("Saved edit as a new intent revision.");
    await refreshHistory(saved.tripId);
  }

  async function handleRestoreIntent(intentRevisionId: string) {
    if (!saved) {
      return;
    }
    const result = await restoreTripIntentEnvelope(
      saved.tripId,
      intentRevisionId,
      { base_revision_id: saved.currentRevisionId },
      `intent-restore:${intentRevisionId}:${saved.currentRevisionId}`,
    );
    if (!result.ok) {
      setStatus(result.message);
      return;
    }
    setEnvelope(result.data.envelope);
    setStatus(`Restored intent revision as revision ${result.data.revision.revision_number}.`);
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
          <TypedIntentPreview envelope={envelope} />
          <ReadinessEvidence envelope={envelope} />
          <IntentEditPanel
            form={editForm}
            onChange={setEditForm}
            onSave={() => void handleEditIntent()}
          />
          <FieldList title="Selected fields" fields={summary.selectedFields} />
          <ProvenanceList envelope={envelope} />
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
              <p>
                {question.blocking ? "Blocking" : "Non-blocking"} · {question.impact} · {question.answer_field_path}
              </p>
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
              {envelope.typed_assumptions.map((item) => (
                <p key={item.assumption_id}>
                  {item.field_path}: {item.reason_code} · {item.has_assumed_value ? "valued" : "unresolved"} ·{" "}
                  {item.blocks_planner_ready ? "blocks planner handoff" : "allowed"}
                </p>
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
            <button
              type="button"
              key={revision.id}
              onClick={() => void handleLoadRevision(revision.id)}
            >
              Intent rev {revision.revision_number}
            </button>
          ))}
          {envelope ? (
            <button type="button" onClick={() => void handleRestoreIntent(envelope.id)}>
              Restore loaded
            </button>
          ) : null}
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
        .intent-confirmation-workspace__answer input,
        .intent-confirmation-workspace__edit-grid input,
        .intent-confirmation-workspace__edit-grid select {
          min-width: 0;
          border: 1px solid rgba(21,21,21,0.12);
          border-radius: 12px;
          padding: 8px 10px;
          background: rgba(255,253,249,0.86);
          color: var(--ec-ink);
          font-size: 13px;
        }
        .intent-confirmation-workspace__edit-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 8px;
        }
        .intent-confirmation-workspace__edit-grid label {
          display: grid;
          gap: 4px;
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 800;
        }
      `}</style>
    </section>
  );
}

function IntentEditPanel({
  form,
  onChange,
  onSave,
}: {
  form: IntentEditForm;
  onChange: (form: IntentEditForm) => void;
  onSave: () => void;
}) {
  return (
    <div className="intent-confirmation-workspace__panel">
      <strong>Revision edit</strong>
      <div className="intent-confirmation-workspace__edit-grid">
        <label>
          City
          <input value={form.city} onChange={(event) => onChange({ ...form, city: event.target.value })} />
        </label>
        <label>
          Trip days
          <input value={form.tripDays} onChange={(event) => onChange({ ...form, tripDays: event.target.value })} />
        </label>
        <label>
          Pace
          <select
            value={form.pace}
            onChange={(event) => onChange({ ...form, pace: event.target.value as IntentEditForm["pace"] })}
          >
            <option value="">Unset</option>
            <option value="relaxed">Relaxed</option>
            <option value="balanced">Balanced</option>
            <option value="intensive">Intensive</option>
          </select>
        </label>
        <label>
          Transport
          <input
            value={form.transportPreferences}
            onChange={(event) => onChange({ ...form, transportPreferences: event.target.value })}
          />
        </label>
      </div>
      <button type="button" onClick={onSave}>
        Save revision
      </button>
    </div>
  );
}

function FieldList({ title, fields }: { title: string; fields: SourceLinkedTripIntentEnvelope["fields"] }) {
  return (
    <div className="intent-confirmation-workspace__panel">
      <strong>{title}</strong>
      {fields.map((field) => (
        <p key={field.field_id}>
          {field.field_path}: {formatValue(field.value)} · {field.kind} · {field.semantic_type} ·{" "}
          {field.source_refs[0]?.source_type}
        </p>
      ))}
    </div>
  );
}

function TypedIntentPreview({ envelope }: { envelope: SourceLinkedTripIntentEnvelope }) {
  const destination = envelope.typed_intent.destinations[0];
  const tripDays = envelope.typed_intent.date_policy.trip_days;
  const pace = envelope.typed_intent.pace;
  return (
    <div className="intent-confirmation-workspace__panel">
      <strong>Typed intent preview</strong>
      <p>Destination: {destination ? formatValue(destination.value) : "unresolved"}</p>
      <p>Trip days: {tripDays ? formatValue(tripDays.value) : "assumption needed"}</p>
      <p>Must places: {envelope.typed_intent.poi_preferences.must_candidates.length}</p>
      <p>Fixed events: {envelope.typed_intent.fixed_events.length}</p>
      <p>Transport: {envelope.typed_intent.transport_preferences.map((item) => formatValue(item.value)).join(", ") || "none"}</p>
      <p>Pace: {pace ? formatValue(pace.value) : "unset"}</p>
    </div>
  );
}

function ReadinessEvidence({ envelope }: { envelope: SourceLinkedTripIntentEnvelope }) {
  return (
    <div className="intent-confirmation-workspace__panel">
      <strong>Contract evidence</strong>
      <p>Semantic digest: {envelope.semantic_digest?.slice(0, 16) ?? "missing"}</p>
      <p>
        Parser: {envelope.parser_result.parser_name} · {envelope.parser_result.status} ·{" "}
        {envelope.parser_result.extracted_field_paths.length} fields
      </p>
      <p>
        Readiness: {envelope.readiness_policy?.status ?? envelope.planner_ready_status} · blockers{" "}
        {envelope.readiness_policy?.blocking_reason_codes.join(", ") || "none"}
      </p>
      <p>
        Provenance graph: {envelope.provenance_graph.nodes.length} nodes · {envelope.provenance_graph.edges.length} edges
      </p>
    </div>
  );
}

function ProvenanceList({ envelope }: { envelope: SourceLinkedTripIntentEnvelope }) {
  if (!envelope.provenance_summary.length) {
    return null;
  }
  return (
    <div className="intent-confirmation-workspace__panel">
      <strong>Source evidence</strong>
      {envelope.provenance_summary.map((item) => (
        <p key={item.field_path}>
          {item.field_path}: {item.source_types.join(", ")} · {item.confirmed ? "confirmed" : "unconfirmed"} · evidence{" "}
          {item.evidence_refs.length || "none"}
        </p>
      ))}
    </div>
  );
}

function isPace(value: string | null): value is IntentEditForm["pace"] {
  return value === "relaxed" || value === "balanced" || value === "intensive";
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
