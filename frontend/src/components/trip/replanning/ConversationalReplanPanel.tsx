"use client";

import { useEffect, useMemo, useReducer, useState } from "react";
import { buildItineraryChangeSet } from "./replanDiff";
import { ReplanChangeReview } from "./ReplanChangeReview";
import { ReplanComposer } from "./ReplanComposer";
import { ReplanConfirmationDialog } from "./ReplanConfirmationDialog";
import { ReplanConstraintSummary } from "./ReplanConstraintSummary";
import { ReplanHistoryRail } from "./ReplanHistoryRail";
import { ReplanImpactPreview } from "./ReplanImpactPreview";
import { ReplanInterpretationCard } from "./ReplanInterpretationCard";
import {
  createInitialReplanWorkflowState,
  reduceReplanWorkflowState,
} from "./replanState";
import type {
  ReplanExecutionResult,
  ReplanHistoryEntry,
  ReplanItineraryLike,
  ReplanMutationPlan,
} from "./replanTypes";
import { buildReplanMutationPlan } from "./replanViewModel";

export function ConversationalReplanPanel<TItinerary extends ReplanItineraryLike>({
  itinerary,
  initialText = "",
  backendInterpretationLines = [],
  executing = false,
  onDraftChange,
  onExecutePlan,
  onUndoSnapshot,
}: {
  itinerary: TItinerary;
  initialText?: string;
  backendInterpretationLines?: string[];
  executing?: boolean;
  onDraftChange?: (value: string) => void;
  onExecutePlan: (
    plan: ReplanMutationPlan,
    rawText: string,
  ) => Promise<ReplanExecutionResult<TItinerary>>;
  onUndoSnapshot?: (entry: ReplanHistoryEntry<TItinerary>) => void;
}) {
  const [state, dispatch] = useReducer(
    reduceReplanWorkflowState<TItinerary>,
    createInitialReplanWorkflowState<TItinerary>(),
  );
  const [confirmationOpen, setConfirmationOpen] = useState(false);

  useEffect(() => {
    if (initialText && initialText !== state.draftText) {
      dispatch({ type: "draft_changed", text: initialText });
    }
  }, [initialText]);

  const canConfirm = state.activePlan?.executable === true && state.status === "needs_confirmation";
  const statusLabel = useMemo(() => formatStatusLabel(state.status), [state.status]);

  function handleDraftChange(value: string) {
    dispatch({ type: "draft_changed", text: value });
    onDraftChange?.(value);
  }

  function handleInterpret() {
    const plan = buildReplanMutationPlan(state.draftText, itinerary);
    dispatch({ type: "interpreted", plan });
  }

  async function handleConfirmExecution() {
    if (!state.activePlan) {
      return;
    }
    const confirmedState = reduceReplanWorkflowState(state, { type: "confirmed" });
    if (confirmedState.status !== "executing") {
      dispatch({ type: "execute_failed", message: confirmedState.errorMessage ?? "执行被阻止。" });
      setConfirmationOpen(false);
      return;
    }

    dispatch({ type: "execute_started" });
    setConfirmationOpen(false);
    try {
      const result = await onExecutePlan(state.activePlan, state.draftText);
      const changeSet = result.ok
        ? buildItineraryChangeSet(result.beforeItinerary, result.afterItinerary)
        : null;
      dispatch({ type: "execute_finished", result, changeSet });
    } catch {
      dispatch({ type: "execute_failed", message: "执行调整失败，请稍后重试。" });
    }
  }

  function handleUndoLast(entry: ReplanHistoryEntry<TItinerary>) {
    onUndoSnapshot?.(entry);
    dispatch({ type: "undo_last" });
  }

  return (
    <section className="conversational-replan-panel">
      <div className="conversational-replan-panel__header">
        <span>Conversational Replanning</span>
        <h3>Constraint-preserving changes</h3>
        <p>
          将自然语言调整拆成意图、约束检查、影响预览和确认执行；当前后端缺失的局部 mutation contract 会直接标出。
        </p>
        <strong>{statusLabel}</strong>
      </div>

      <ReplanComposer
        value={state.draftText}
        disabled={executing || state.status === "executing"}
        onChange={handleDraftChange}
        onInterpret={handleInterpret}
      />

      {state.activePlan ? (
        <div className="conversational-replan-panel__review">
          <ReplanInterpretationCard
            plan={state.activePlan}
            backendLines={backendInterpretationLines}
          />
          <ReplanConstraintSummary
            constraints={state.activePlan.constraints}
            contractGaps={state.activePlan.contractGaps}
          />
          <ReplanImpactPreview items={state.activePlan.impactPreview} />
          <div className="conversational-replan-panel__confirm-row">
            <button
              type="button"
              disabled={!canConfirm || executing || state.status === "executing"}
              onClick={() => setConfirmationOpen(true)}
            >
              进入确认
            </button>
            <span>
              {state.activePlan.executionMode === "backend_replan"
                ? "会调用现有 /replan-itinerary，执行后再审计实际变化。"
                : state.activePlan.executionMode === "local_mutation"
                  ? "会执行本地确定性 mutation，再刷新解释和补全表面。"
                  : "当前能力不足，不会执行。"}
            </span>
          </div>
        </div>
      ) : null}

      <ReplanChangeReview changeSet={state.changeSet} />
      <ReplanHistoryRail history={state.history} onUndoLast={onUndoSnapshot ? handleUndoLast : undefined} />

      {state.errorMessage ? <p className="conversational-replan-panel__error">{state.errorMessage}</p> : null}

      {confirmationOpen ? (
        <ReplanConfirmationDialog
          plan={state.activePlan}
          executing={executing || state.status === "executing"}
          onCancel={() => setConfirmationOpen(false)}
          onConfirm={handleConfirmExecution}
        />
      ) : null}

      <style>{`
        .conversational-replan-panel {
          display: grid;
          gap: 12px;
          padding: 14px;
          border-radius: 20px;
          border: 1px solid var(--ec-line);
          background: linear-gradient(180deg, rgba(255,253,249,0.96), rgba(247,244,238,0.9));
          box-shadow: var(--ec-shadow-1);
        }
        .conversational-replan-panel__header {
          display: grid;
          gap: 6px;
        }
        .conversational-replan-panel__header span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }
        .conversational-replan-panel__header h3 {
          margin: 0;
          color: var(--ec-ink);
          font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
          font-size: 26px;
          line-height: 1.02;
          letter-spacing: 0;
        }
        .conversational-replan-panel__header p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.55;
        }
        .conversational-replan-panel__header strong {
          width: fit-content;
          padding: 5px 8px;
          border-radius: 999px;
          background: rgba(83,112,91,0.12);
          color: var(--ec-moss);
          font-size: 11px;
        }
        .conversational-replan-panel__review {
          display: grid;
          gap: 12px;
        }
        .conversational-replan-panel__confirm-row {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          align-items: center;
        }
        .conversational-replan-panel__confirm-row button {
          min-height: 38px;
          padding: 0 14px;
          border: 1px solid rgba(47,111,168,0.42);
          border-radius: 999px;
          background: var(--ec-route-blue);
          color: #fffdf9;
          font-weight: 900;
          cursor: pointer;
        }
        .conversational-replan-panel__confirm-row button:disabled {
          cursor: not-allowed;
          opacity: 0.58;
        }
        .conversational-replan-panel__confirm-row span,
        .conversational-replan-panel__error {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.5;
        }
        .conversational-replan-panel__error {
          color: #8a6331;
          font-weight: 850;
        }
      `}</style>
    </section>
  );
}

function formatStatusLabel(status: string): string {
  if (status === "needs_confirmation") {
    return "等待确认";
  }
  if (status === "executing") {
    return "执行中";
  }
  if (status === "review") {
    return "已生成变更审计";
  }
  if (status === "blocked") {
    return "被约束阻止";
  }
  if (status === "error") {
    return "执行失败";
  }
  if (status === "interpreted") {
    return "已解释";
  }
  return "等待输入";
}
