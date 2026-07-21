"use client";

import React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import type { CandidateListResponse, TripCandidate } from "@/features/trip-workspace/tripCandidates";
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
  compareIntentContracts,
  formatIntentDomainValue,
  summarizeIntentEnvelope,
} from "./intentConfirmationModel";
import {
  canSubmitInlineClarification,
  getClarificationResolutionAction,
} from "./clarificationResolutionModel";
import {
  buildIntentEditIdempotencyKey,
  buildIntentStructuredOverrides,
  emptyIntentEditForm,
  formFromIntentEnvelope,
  type IntentEditForm,
} from "./intentEditorModel";
import type { IntentClarification, SourceLinkedTripIntentEnvelope, TripIntentRevisionMetadata } from "./intentTypes";

type Props = {
  tripPersistence: TripPersistenceState;
  directUserText: string;
};

export function IntentConfirmationWorkspace({ tripPersistence, directUserText }: Props) {
  const [envelope, setEnvelope] = useState<SourceLinkedTripIntentEnvelope | null>(null);
  const [latestEnvelope, setLatestEnvelope] = useState<SourceLinkedTripIntentEnvelope | null>(null);
  const [history, setHistory] = useState<TripIntentRevisionMetadata[]>([]);
  const [latestIntentRevision, setLatestIntentRevision] = useState<TripIntentRevisionMetadata | null>(null);
  const [loadedIntentRevision, setLoadedIntentRevision] = useState<TripIntentRevisionMetadata | null>(null);
  const [editingBaseIntentRevision, setEditingBaseIntentRevision] = useState<TripIntentRevisionMetadata | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [selectedEvidenceNodeId, setSelectedEvidenceNodeId] = useState<string | null>(null);
  const [staleEdit, setStaleEdit] = useState(false);
  const [candidates, setCandidates] = useState<TripCandidate[]>([]);
  const [editForm, setEditForm] = useState<IntentEditForm>(emptyIntentEditForm);
  const editorRef = useRef<HTMLDivElement | null>(null);
  const summary = useMemo(() => summarizeIntentEnvelope(envelope), [envelope]);
  const saved = tripPersistence.status === "saved" ? tripPersistence : null;
  const latestIntentRevisionId = latestIntentRevision?.id ?? latestEnvelope?.id ?? null;
  const loadedLatest = !envelope || !latestIntentRevisionId || loadedIntentRevision?.id === latestIntentRevisionId;

  useEffect(() => {
    if (!saved) {
      setHistory([]);
      setEnvelope(null);
      setLatestEnvelope(null);
      setLatestIntentRevision(null);
      setLoadedIntentRevision(null);
      setEditingBaseIntentRevision(null);
      return;
    }
    void refreshHistory(saved.tripId);
  }, [saved?.tripId, saved?.currentRevisionId]);

  useEffect(() => {
    if (!saved) {
      setCandidates([]);
      return;
    }
    void (async () => {
      const result = await getTripJson<CandidateListResponse>(
        TRIP_API_ENDPOINTS.listTripCandidates(saved.tripId),
        "Refresh confirmed places failed",
      );
      if (result.ok) {
        setCandidates(result.data.candidates);
      }
    })();
  }, [saved?.tripId]);

  async function refreshHistory(tripId: string) {
    const result = await listTripIntentEnvelopes(tripId);
    if (result.ok) {
      setHistory(result.data.revisions);
      const latest = result.data.revisions[0] ?? null;
      setLatestIntentRevision(latest);
      const latestRevisionId = latest?.id;
      if (latestRevisionId) {
        const latest = await getTripIntentEnvelope(tripId, latestRevisionId);
        if (latest.ok) {
          setLatestEnvelope(latest.data.envelope);
        }
      } else {
        setLatestEnvelope(null);
      }
    }
  }

  useEffect(() => {
    if (!envelope) {
      setEditForm(emptyIntentEditForm());
      return;
    }
    setEditForm(formFromIntentEnvelope(envelope));
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
        base_intent_revision_id: latestIntentRevisionId,
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
    setLatestEnvelope(result.data.envelope);
    setLatestIntentRevision(result.data.revision);
    setLoadedIntentRevision(result.data.revision);
    setEditingBaseIntentRevision(result.data.revision);
    setStatus(result.data.idempotent_replay ? "Loaded existing compiled contract." : "Compiled immutable intent contract.");
    await refreshHistory(saved.tripId);
  }

  async function handleAnswerClarification(question: IntentClarification) {
    const rawAnswer = clarificationAnswers[question.question_id]?.trim() ?? "";
    if (!saved || !envelope || !canSubmitInlineClarification(question, rawAnswer)) {
      return;
    }
    if (!loadedLatest) {
      setStatus("Load the latest intent revision before answering a clarification.");
      return;
    }
    const numericAnswer = question.answer_value_type === "integer" ? Number(rawAnswer) : null;
    if (question.answer_value_type === "integer" && (!Number.isInteger(numericAnswer) || numericAnswer === null || numericAnswer < 1)) {
      setStatus("Trip days clarification must be a positive whole number.");
      return;
    }
    const answer = numericAnswer ?? rawAnswer;
    const result = await answerIntentClarification(
      saved.tripId,
      envelope.id,
      question.question_id,
      { base_revision_id: saved.currentRevisionId, base_intent_revision_id: envelope.id, answer },
      `intent-clarify:${envelope.id}:${question.question_id}:${saved.currentRevisionId}`,
    );
    if (!result.ok) {
      if (result.code === "stale_intent_revision") {
        await refreshHistory(saved.tripId);
        setStatus("A newer intent revision exists. Load the latest contract before answering this clarification.");
        return;
      }
      setStatus(result.message);
      return;
    }
    setEnvelope(result.data.envelope);
    setLatestEnvelope(result.data.envelope);
    setLatestIntentRevision(result.data.revision);
    setLoadedIntentRevision(result.data.revision);
    setEditingBaseIntentRevision(result.data.revision);
    setClarificationAnswers((current) => {
      const next = { ...current };
      delete next[question.question_id];
      return next;
    });
    setStatus("Saved clarification as a new intent revision.");
    await refreshHistory(saved.tripId);
  }

  function focusContractEditor(question: IntentClarification) {
    const fieldPath = question.editor_field_path ?? question.field_paths[0];
    const editorPath = fieldPath.startsWith("poi.") ? "poi.must_candidates" : fieldPath;
    const target = editorRef.current?.querySelector<HTMLElement>(`[data-intent-field-path="${editorPath}"]`);
    if (!target) {
      setStatus("This clarification requires a typed contract edit. Review the confirmed trip inputs below.");
      return;
    }
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.querySelector<HTMLElement>("input, select, button")?.focus();
    setStatus("Update the highlighted typed contract field, then save a new intent revision.");
  }

  function openEvidenceRecovery(question: IntentClarification) {
    if (!envelope || typeof window === "undefined") {
      return;
    }
    window.dispatchEvent(new CustomEvent("trip-import-workspace-request", { detail: { tripId: envelope.trip_id } }));
    setStatus("Legacy evidence cannot be confirmed by text. Re-import and review an evidence-backed candidate, or remove it in the contract editor.");
    focusContractEditor(question);
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
    setLoadedIntentRevision(result.data.revision);
    setEditingBaseIntentRevision(result.data.revision);
    setStaleEdit(false);
    setStatus(`Loaded intent revision ${result.data.revision.revision_number}.`);
  }

  async function handleEditIntent(reapplyToLatest = false) {
    if (!saved || !envelope) {
      return;
    }
    const baseEnvelope = reapplyToLatest ? latestEnvelope : envelope;
    if (!baseEnvelope || (!loadedLatest && !reapplyToLatest)) {
      setStatus("Load the latest intent revision before editing the contract.");
      return;
    }
    let fieldUpdates;
    try {
      fieldUpdates = buildIntentStructuredOverrides(editForm);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Intent edit is invalid.");
      return;
    }
    const result = await editTripIntentEnvelope(
      saved.tripId,
      baseEnvelope.id,
      {
        base_revision_id: saved.currentRevisionId,
        base_intent_revision_id: reapplyToLatest
          ? latestIntentRevisionId ?? baseEnvelope.id
          : editingBaseIntentRevision?.id ?? baseEnvelope.id,
        field_updates: fieldUpdates,
      },
      buildIntentEditIdempotencyKey(baseEnvelope.id, saved.currentRevisionId, fieldUpdates),
    );
    if (!result.ok) {
      if (result.code === "stale_intent_revision") {
        await refreshHistory(saved.tripId);
        setStaleEdit(true);
        setStatus("A newer intent revision exists. Your draft is retained; reapply it explicitly to the latest revision.");
        return;
      }
      setStatus(result.message);
      return;
    }
    setEnvelope(result.data.envelope);
    setLatestEnvelope(result.data.envelope);
    setLatestIntentRevision(result.data.revision);
    setLoadedIntentRevision(result.data.revision);
    setEditingBaseIntentRevision(result.data.revision);
    setStaleEdit(false);
    setStatus("Saved edit as a new intent revision.");
    await refreshHistory(saved.tripId);
  }

  async function handleRestoreIntent(intentRevisionId: string) {
    if (!saved) {
      return;
    }
    if (!latestIntentRevisionId) {
      setStatus("Compile an intent contract before restoring a prior revision.");
      return;
    }
    const result = await restoreTripIntentEnvelope(
      saved.tripId,
      intentRevisionId,
      { base_revision_id: saved.currentRevisionId, base_intent_revision_id: latestIntentRevisionId },
      `intent-restore:${intentRevisionId}:${saved.currentRevisionId}`,
    );
    if (!result.ok) {
      setStatus(result.message);
      return;
    }
    setEnvelope(result.data.envelope);
    setLatestEnvelope(result.data.envelope);
    setLatestIntentRevision(result.data.revision);
    setLoadedIntentRevision(result.data.revision);
    setEditingBaseIntentRevision(result.data.revision);
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
          <ReadinessEvidence envelope={envelope} latestRevision={latestIntentRevision} latestEnvelope={latestEnvelope} />
          <div ref={editorRef}>
            <IntentEditPanel
              form={editForm}
              onChange={setEditForm}
              candidates={candidates}
              onSave={() => void handleEditIntent()}
              onReapply={staleEdit && latestEnvelope ? () => void handleEditIntent(true) : null}
              disabled={!loadedLatest && !staleEdit}
            />
          </div>
          <FieldList title="Selected fields" fields={summary.selectedFields} />
          <ProvenanceList
            envelope={envelope}
            selectedNodeId={selectedEvidenceNodeId}
            onSelectNode={setSelectedEvidenceNodeId}
          />
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
            <ClarificationCard
              key={question.question_id}
              question={question}
              answer={clarificationAnswers[question.question_id] ?? ""}
              disabled={!loadedLatest}
              onAnswerChange={(answer) => setClarificationAnswers((current) => ({ ...current, [question.question_id]: answer }))}
              onSaveAnswer={() => void handleAnswerClarification(question)}
              onEdit={() => focusContractEditor(question)}
              onReimport={() => openEvidenceRecovery(question)}
            />
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
        .intent-confirmation-workspace__edit-grid select,
        .intent-confirmation-workspace__item-grid input,
        .intent-confirmation-workspace__item-grid select,
        .intent-confirmation-workspace__event input,
        .intent-confirmation-workspace__event select {
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
        .intent-confirmation-workspace__subsection {
          display: grid;
          gap: 8px;
          padding-top: 10px;
          border-top: 1px solid rgba(21,21,21,0.08);
        }
        .intent-confirmation-workspace__row-header,
        .intent-confirmation-workspace__candidate-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 8px;
        }
        .intent-confirmation-workspace__item-grid,
        .intent-confirmation-workspace__event {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 7px;
          align-items: center;
        }
        .intent-confirmation-workspace__candidate-grid {
          display: grid;
          gap: 6px;
        }
        .intent-confirmation-workspace__candidate-row {
          padding: 7px 0;
          border-bottom: 1px solid rgba(21,21,21,0.06);
          color: var(--ec-ink);
          font-size: 12px;
          font-weight: 800;
        }
        .intent-confirmation-workspace__toggle {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 800;
        }
        @media (max-width: 720px) {
          .intent-confirmation-workspace__edit-grid,
          .intent-confirmation-workspace__item-grid,
          .intent-confirmation-workspace__event {
            grid-template-columns: 1fr;
          }
          .intent-confirmation-workspace__candidate-row {
            align-items: flex-start;
            flex-wrap: wrap;
          }
        }
      `}</style>
    </section>
  );
}

function ClarificationCard({
  question,
  answer,
  disabled,
  onAnswerChange,
  onSaveAnswer,
  onEdit,
  onReimport,
}: {
  question: IntentClarification;
  answer: string;
  disabled: boolean;
  onAnswerChange: (answer: string) => void;
  onSaveAnswer: () => void;
  onEdit: () => void;
  onReimport: () => void;
}) {
  const resolutionAction = getClarificationResolutionAction(question);
  return (
    <div className="intent-confirmation-workspace__panel" data-clarification-kind={question.resolution_kind}>
      <strong>{question.question}</strong>
      <p>
        {question.blocking ? "Blocking" : "Non-blocking"} · {question.impact} · {question.field_paths.join(", ")}
      </p>
      {resolutionAction === "answer_inline" ? (
        <div className="intent-confirmation-workspace__answer">
          <input
            type={question.answer_value_type === "integer" ? "number" : "text"}
            min={question.answer_value_type === "integer" ? 1 : undefined}
            value={answer}
            onChange={(event) => onAnswerChange(event.target.value)}
            placeholder={question.answer_value_type === "integer" ? "Enter a whole number" : "Answer clarification"}
            disabled={disabled}
          />
          <button type="button" onClick={onSaveAnswer} disabled={disabled || !canSubmitInlineClarification(question, answer)}>
            Save answer
          </button>
        </div>
      ) : resolutionAction === "edit_contract" ? (
        <div className="intent-confirmation-workspace__answer">
          <p>This issue needs an explicit typed edit; free text cannot override the contract.</p>
          <button type="button" onClick={onEdit} disabled={disabled}>
            Edit contract field
          </button>
        </div>
      ) : (
        <div className="intent-confirmation-workspace__answer">
          <p>This source has no verifiable lineage. It cannot be confirmed by a text answer.</p>
          <button type="button" onClick={onReimport} disabled={disabled}>
            Open Import Review
          </button>
          <button type="button" onClick={onEdit} disabled={disabled}>
            Remove or replace candidate
          </button>
        </div>
      )}
    </div>
  );
}

function IntentEditPanel({
  form,
  onChange,
  candidates,
  onSave,
  onReapply,
  disabled,
}: {
  form: IntentEditForm;
  onChange: (form: IntentEditForm) => void;
  candidates: TripCandidate[];
  onSave: () => void;
  onReapply: (() => void) | null;
  disabled: boolean;
}) {
  const eligibleCandidates = candidates.filter((candidate) => !["rejected", "deferred"].includes(candidate.workflow_state));
  const updateBoundary = (key: "arrival" | "departure", field: keyof IntentEditForm["arrival"], value: string) => {
    onChange({ ...form, [key]: { ...form[key], [field]: value } });
  };
  const updateWindow = (id: string, field: keyof IntentEditForm["availabilityWindows"][number], value: string | boolean) => {
    onChange({
      ...form,
      availabilityWindows: form.availabilityWindows.map((window) => window.id === id ? { ...window, [field]: value } : window),
    });
  };
  const updateEvent = (id: string, field: keyof IntentEditForm["fixedEvents"][number], value: string) => {
    onChange({
      ...form,
      fixedEvents: form.fixedEvents.map((event) => event.id === id ? { ...event, [field]: value } : event),
    });
  };
  const updateNeed = (id: string, field: keyof IntentEditForm["travelerNeeds"][number], value: string) => {
    onChange({
      ...form,
      travelerNeeds: form.travelerNeeds.map((need) => need.id === id ? { ...need, [field]: value } : need),
    });
  };
  const toggleCandidate = (field: "mustCandidateIds" | "optionalCandidateIds" | "avoidCandidateIds", candidateId: string) => {
    const selected = form[field];
    onChange({ ...form, [field]: selected.includes(candidateId) ? selected.filter((id) => id !== candidateId) : [...selected, candidateId] });
  };

  return (
    <div className="intent-confirmation-workspace__panel">
      <strong>Confirmed trip inputs</strong>
      <div className="intent-confirmation-workspace__edit-grid">
        <label data-intent-field-path="trip.city">
          City
          <input disabled={disabled} value={form.city} onChange={(event) => onChange({ ...form, city: event.target.value })} />
        </label>
        <label data-intent-field-path="trip.trip_days">
          Trip days
          <input disabled={disabled} value={form.tripDays} onChange={(event) => onChange({ ...form, tripDays: event.target.value })} />
        </label>
        <label data-intent-field-path="trip.date_policy">
          Start date
          <input type="date" disabled={disabled} value={form.startDate} onChange={(event) => onChange({ ...form, startDate: event.target.value })} />
        </label>
        <label data-intent-field-path="trip.date_policy">
          End date
          <input type="date" disabled={disabled} value={form.endDate} onChange={(event) => onChange({ ...form, endDate: event.target.value })} />
        </label>
        <label data-intent-field-path="trip.date_policy">
          Timezone
          <input disabled={disabled} value={form.timezone} onChange={(event) => onChange({ ...form, timezone: event.target.value })} />
        </label>
        <label data-intent-field-path="trip.pace">
          Pace
          <select
            value={form.pace}
            disabled={disabled}
            onChange={(event) => onChange({ ...form, pace: event.target.value as IntentEditForm["pace"] })}
          >
            <option value="">Unset</option>
            <option value="relaxed">Relaxed</option>
            <option value="balanced">Balanced</option>
            <option value="intensive">Intensive</option>
          </select>
        </label>
        <label data-intent-field-path="preferences.transport">
          Transport
          <input
            value={form.transportPreferences}
            disabled={disabled}
            onChange={(event) => onChange({ ...form, transportPreferences: event.target.value })}
          />
        </label>
      </div>
      <div className="intent-confirmation-workspace__subsection" data-intent-field-path="trip.arrival_boundary">
        <strong>Arrival boundary</strong>
        <div className="intent-confirmation-workspace__edit-grid">
          <label>Local date and time<input type="datetime-local" disabled={disabled} value={form.arrival.localDatetime} onChange={(event) => updateBoundary("arrival", "localDatetime", event.target.value)} /></label>
          <label>Timezone<input disabled={disabled} value={form.arrival.timezone} onChange={(event) => updateBoundary("arrival", "timezone", event.target.value)} /></label>
          <label>Location<input disabled={disabled} value={form.arrival.locationText} onChange={(event) => updateBoundary("arrival", "locationText", event.target.value)} /></label>
          <label>Flexibility minutes<input inputMode="numeric" disabled={disabled} value={form.arrival.flexibilityMinutes} onChange={(event) => updateBoundary("arrival", "flexibilityMinutes", event.target.value)} /></label>
        </div>
      </div>
      <div className="intent-confirmation-workspace__subsection" data-intent-field-path="trip.departure_boundary">
        <strong>Departure boundary</strong>
        <div className="intent-confirmation-workspace__edit-grid">
          <label>Local date and time<input type="datetime-local" disabled={disabled} value={form.departure.localDatetime} onChange={(event) => updateBoundary("departure", "localDatetime", event.target.value)} /></label>
          <label>Timezone<input disabled={disabled} value={form.departure.timezone} onChange={(event) => updateBoundary("departure", "timezone", event.target.value)} /></label>
          <label>Location<input disabled={disabled} value={form.departure.locationText} onChange={(event) => updateBoundary("departure", "locationText", event.target.value)} /></label>
          <label>Flexibility minutes<input inputMode="numeric" disabled={disabled} value={form.departure.flexibilityMinutes} onChange={(event) => updateBoundary("departure", "flexibilityMinutes", event.target.value)} /></label>
        </div>
      </div>
      <div className="intent-confirmation-workspace__subsection" data-intent-field-path="time.availability_windows">
        <div className="intent-confirmation-workspace__row-header"><strong>Availability windows</strong><button type="button" disabled={disabled} onClick={() => onChange({ ...form, availabilityWindows: [...form.availabilityWindows, { id: `window-${Date.now()}`, date: form.startDate, startTime: "", endTime: "", timezone: form.timezone, crossesMidnight: false }] })}>Add window</button></div>
        {form.availabilityWindows.map((window) => (
          <div className="intent-confirmation-workspace__item-grid" key={window.id}>
            <input type="date" aria-label="Availability date" disabled={disabled} value={window.date} onChange={(event) => updateWindow(window.id, "date", event.target.value)} />
            <input type="time" aria-label="Availability start" disabled={disabled} value={window.startTime} onChange={(event) => updateWindow(window.id, "startTime", event.target.value)} />
            <input type="time" aria-label="Availability end" disabled={disabled} value={window.endTime} onChange={(event) => updateWindow(window.id, "endTime", event.target.value)} />
            <input aria-label="Availability timezone" disabled={disabled} value={window.timezone} onChange={(event) => updateWindow(window.id, "timezone", event.target.value)} placeholder="Timezone" />
            <label className="intent-confirmation-workspace__toggle"><input type="checkbox" disabled={disabled} checked={window.crossesMidnight} onChange={(event) => updateWindow(window.id, "crossesMidnight", event.target.checked)} />Overnight</label>
            <button type="button" disabled={disabled} onClick={() => onChange({ ...form, availabilityWindows: form.availabilityWindows.filter((item) => item.id !== window.id) })}>Remove</button>
          </div>
        ))}
      </div>
      <div className="intent-confirmation-workspace__subsection" data-intent-field-path="time.fixed_events">
        <div className="intent-confirmation-workspace__row-header"><strong>Fixed events</strong><button type="button" disabled={disabled} onClick={() => onChange({ ...form, fixedEvents: [...form.fixedEvents, { id: `event-${Date.now()}`, title: "", startAt: "", endAt: "", timezone: form.timezone, fixedDay: "", locationText: "", flexibility: "fixed" }] })}>Add event</button></div>
        {form.fixedEvents.map((event) => (
          <div className="intent-confirmation-workspace__event" key={event.id}>
            <input aria-label="Fixed event title" disabled={disabled} value={event.title} onChange={(input) => updateEvent(event.id, "title", input.target.value)} placeholder="Event title" />
            <input type="datetime-local" aria-label="Fixed event start" disabled={disabled} value={event.startAt} onChange={(input) => updateEvent(event.id, "startAt", input.target.value)} />
            <input type="datetime-local" aria-label="Fixed event end" disabled={disabled} value={event.endAt} onChange={(input) => updateEvent(event.id, "endAt", input.target.value)} />
            <input aria-label="Fixed event timezone" disabled={disabled} value={event.timezone} onChange={(input) => updateEvent(event.id, "timezone", input.target.value)} placeholder="Timezone" />
            <input inputMode="numeric" aria-label="Fixed event day" disabled={disabled} value={event.fixedDay} onChange={(input) => updateEvent(event.id, "fixedDay", input.target.value)} placeholder="Day" />
            <input aria-label="Fixed event location" disabled={disabled} value={event.locationText} onChange={(input) => updateEvent(event.id, "locationText", input.target.value)} placeholder="Location" />
            <select aria-label="Fixed event flexibility" disabled={disabled} value={event.flexibility} onChange={(input) => updateEvent(event.id, "flexibility", input.target.value)}><option value="fixed">Fixed</option><option value="movable_with_confirmation">Movable with confirmation</option></select>
            <button type="button" disabled={disabled} onClick={() => onChange({ ...form, fixedEvents: form.fixedEvents.filter((item) => item.id !== event.id) })}>Remove</button>
          </div>
        ))}
      </div>
      <CandidatePreferenceEditor candidates={eligibleCandidates} form={form} disabled={disabled} onToggle={toggleCandidate} />
      <div className="intent-confirmation-workspace__subsection" data-intent-field-path="budget">
        <strong>Budget</strong>
        <div className="intent-confirmation-workspace__edit-grid">
          <label>Amount in minor units<input inputMode="numeric" disabled={disabled} value={form.budget.amountMinor} onChange={(event) => onChange({ ...form, budget: { ...form.budget, amountMinor: event.target.value } })} /></label>
          <label>Currency<input disabled={disabled} value={form.budget.currency} onChange={(event) => onChange({ ...form, budget: { ...form.budget, currency: event.target.value } })} /></label>
          <label>Scope<select disabled={disabled} value={form.budget.scope} onChange={(event) => onChange({ ...form, budget: { ...form.budget, scope: event.target.value as IntentEditForm["budget"]["scope"] } })}><option value="">Unset</option><option value="total">Total</option><option value="per_person">Per person</option><option value="per_day">Per day</option></select></label>
          <label>Level<select disabled={disabled} value={form.budget.level} onChange={(event) => onChange({ ...form, budget: { ...form.budget, level: event.target.value as IntentEditForm["budget"]["level"] } })}><option value="">Unset</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>
          <label>Flexibility percent<input inputMode="numeric" disabled={disabled} value={form.budget.flexibilityPercent} onChange={(event) => onChange({ ...form, budget: { ...form.budget, flexibilityPercent: event.target.value } })} /></label>
        </div>
      </div>
      <div className="intent-confirmation-workspace__subsection" data-intent-field-path="travelers.needs">
        <div className="intent-confirmation-workspace__row-header"><strong>Traveler needs</strong><button type="button" disabled={disabled} onClick={() => onChange({ ...form, travelerNeeds: [...form.travelerNeeds, { id: `need-${Date.now()}`, needType: "other", description: "", severity: "preferred" }] })}>Add need</button></div>
        {form.travelerNeeds.map((need) => (
          <div className="intent-confirmation-workspace__item-grid" key={need.id}>
            <select aria-label="Need type" disabled={disabled} value={need.needType} onChange={(event) => updateNeed(need.id, "needType", event.target.value)}>{["mobility", "wheelchair", "child", "elderly", "dietary", "medical", "sensory", "other"].map((kind) => <option key={kind} value={kind}>{kind}</option>)}</select>
            <input aria-label="Need description" disabled={disabled} value={need.description} onChange={(event) => updateNeed(need.id, "description", event.target.value)} placeholder="Description" />
            <select aria-label="Need severity" disabled={disabled} value={need.severity} onChange={(event) => updateNeed(need.id, "severity", event.target.value)}><option value="preferred">Preferred</option><option value="required">Required</option></select>
            <button type="button" disabled={disabled} onClick={() => onChange({ ...form, travelerNeeds: form.travelerNeeds.filter((item) => item.id !== need.id) })}>Remove</button>
          </div>
        ))}
      </div>
      <button type="button" onClick={onSave} disabled={disabled}>
        Save revision
      </button>
      {onReapply ? (
        <button type="button" onClick={onReapply}>
          Reapply to latest
        </button>
      ) : null}
    </div>
  );
}

function CandidatePreferenceEditor({
  candidates,
  form,
  disabled,
  onToggle,
}: {
  candidates: TripCandidate[];
  form: IntentEditForm;
  disabled: boolean;
  onToggle: (field: "mustCandidateIds" | "optionalCandidateIds" | "avoidCandidateIds", candidateId: string) => void;
}) {
  return (
    <div className="intent-confirmation-workspace__subsection" data-intent-field-path="poi.must_candidates">
      <strong>Reviewed place preferences</strong>
      {candidates.length ? (
        <div className="intent-confirmation-workspace__candidate-grid">
          {candidates.map((candidate) => (
            <div key={candidate.id} className="intent-confirmation-workspace__candidate-row">
              <span>{candidate.display_name}</span>
              {(["mustCandidateIds", "optionalCandidateIds", "avoidCandidateIds"] as const).map((field) => (
                <label key={field} className="intent-confirmation-workspace__toggle">
                  <input type="checkbox" disabled={disabled} checked={form[field].includes(candidate.id)} onChange={() => onToggle(field, candidate.id)} />
                  {field === "mustCandidateIds" ? "Must" : field === "optionalCandidateIds" ? "Optional" : "Avoid"}
                </label>
              ))}
            </div>
          ))}
        </div>
      ) : <p>Confirmed places appear here after Import Review or candidate intake.</p>}
    </div>
  );
}

function FieldList({ title, fields }: { title: string; fields: SourceLinkedTripIntentEnvelope["fields"] }) {
  return (
    <div className="intent-confirmation-workspace__panel">
      <strong>{title}</strong>
      {fields.map((field) => (
        <p key={field.field_id}>
          {field.field_path}: {formatIntentDomainValue(field.value)} · {field.kind} · {field.semantic_type} ·{" "}
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
      <p>Destination: {destination ? formatIntentDomainValue(destination.value) : "unresolved"}</p>
      <p>Trip days: {tripDays ? formatIntentDomainValue(tripDays.value) : "assumption needed"}</p>
      <p>Must places: {envelope.typed_intent.poi_preferences.must_candidates.length}</p>
      <p>Fixed events: {envelope.typed_intent.fixed_events.length}</p>
      <p>Transport: {envelope.typed_intent.transport_preferences.map((item) => formatIntentDomainValue(item.value)).join(", ") || "none"}</p>
      <p>Pace: {pace ? formatIntentDomainValue(pace.value) : "unset"}</p>
      <p>Budget: {envelope.typed_intent.budget ? formatIntentDomainValue(envelope.typed_intent.budget.value) : "unset"}</p>
      <p>Traveler needs: {envelope.typed_intent.travelers.map((item) => formatIntentDomainValue(item.value)).join(", ") || "none"}</p>
    </div>
  );
}

function ReadinessEvidence({
  envelope,
  latestRevision,
  latestEnvelope,
}: {
  envelope: SourceLinkedTripIntentEnvelope;
  latestRevision: TripIntentRevisionMetadata | null;
  latestEnvelope: SourceLinkedTripIntentEnvelope | null;
}) {
  const loadedLatest = !latestRevision || latestRevision.id === envelope.id;
  const semanticCompare = compareIntentContracts(latestEnvelope, envelope);
  const semanticCompareLabel = semanticCompare.identical
    ? "semantic fields match latest"
    : `${semanticCompare.changed.length} changed · ${semanticCompare.added.length} added · ${semanticCompare.removed.length} removed`;
  return (
    <div className="intent-confirmation-workspace__panel">
      <strong>Contract evidence</strong>
      <p>Semantic digest: {envelope.semantic_digest?.slice(0, 16) ?? "missing"}</p>
      <p>Lineage digest: {envelope.lineage_digest?.slice(0, 16) ?? "missing"}</p>
      <p>Base state: {loadedLatest ? "loaded revision is latest" : "historical revision loaded"}</p>
      <p>Semantic compare: {semanticCompareLabel}</p>
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

function ProvenanceList({
  envelope,
  selectedNodeId,
  onSelectNode,
}: {
  envelope: SourceLinkedTripIntentEnvelope;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}) {
  if (!envelope.provenance_summary.length) {
    return null;
  }
  const selectedNode = envelope.provenance_graph.nodes.find((node) => node.node_id === selectedNodeId);
  function selectEvidenceNode(node: SourceLinkedTripIntentEnvelope["provenance_graph"]["nodes"][number]) {
    onSelectNode(node.node_id);
    if (typeof window === "undefined" || !node.import_job_id) {
      return;
    }
    window.dispatchEvent(
      new CustomEvent("trip-import-evidence-focus", {
        detail: {
          tripId: envelope.trip_id,
          importJobId: node.import_job_id,
          mentionId: node.mention_id,
          pageNumber: node.page_number,
        },
      }),
    );
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
      <div className="intent-confirmation-workspace__evidence-nodes">
        {envelope.provenance_graph.nodes
          .filter((node) => node.node_type !== "field" && node.node_type !== "envelope_revision")
          .slice(0, 12)
          .map((node) => (
            <button type="button" key={node.node_id} onClick={() => selectEvidenceNode(node)}>
              {node.node_type}
            </button>
          ))}
      </div>
      {selectedNode ? (
        <p>
          {selectedNode.node_type}: {selectedNode.label} ·{" "}
          {selectedNode.artifact_id ? `artifact ${selectedNode.artifact_id}` : selectedNode.source_id ?? "no source id"}
          {selectedNode.mention_id ? ` · mention ${selectedNode.mention_id}` : ""}
          {selectedNode.page_number ? ` · page ${selectedNode.page_number}` : ""}
        </p>
      ) : null}
    </div>
  );
}
