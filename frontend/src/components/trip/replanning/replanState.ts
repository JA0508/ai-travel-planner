"use client";

import type {
  ReplanChangeSet,
  ReplanExecutionResult,
  ReplanHistoryEntry,
  ReplanItineraryLike,
  ReplanMutationPlan,
} from "./replanTypes";

export type ReplanWorkflowStatus =
  | "idle"
  | "interpreted"
  | "needs_confirmation"
  | "executing"
  | "review"
  | "blocked"
  | "error";

export type ReplanWorkflowState<TItinerary extends ReplanItineraryLike = ReplanItineraryLike> = {
  status: ReplanWorkflowStatus;
  draftText: string;
  activePlan: ReplanMutationPlan | null;
  lastResult: ReplanExecutionResult<TItinerary> | null;
  changeSet: ReplanChangeSet | null;
  history: ReplanHistoryEntry<TItinerary>[];
  errorMessage: string | null;
  executedPlanIds: string[];
};

export type ReplanWorkflowEvent<TItinerary extends ReplanItineraryLike = ReplanItineraryLike> =
  | { type: "draft_changed"; text: string }
  | { type: "interpreted"; plan: ReplanMutationPlan }
  | { type: "confirmed" }
  | { type: "execute_started" }
  | {
      type: "execute_finished";
      result: ReplanExecutionResult<TItinerary>;
      changeSet: ReplanChangeSet | null;
    }
  | { type: "execute_failed"; message: string }
  | { type: "undo_last" };

export function createInitialReplanWorkflowState<
  TItinerary extends ReplanItineraryLike = ReplanItineraryLike,
>(): ReplanWorkflowState<TItinerary> {
  return {
    status: "idle",
    draftText: "",
    activePlan: null,
    lastResult: null,
    changeSet: null,
    history: [],
    errorMessage: null,
    executedPlanIds: [],
  };
}

export function reduceReplanWorkflowState<TItinerary extends ReplanItineraryLike>(
  state: ReplanWorkflowState<TItinerary>,
  event: ReplanWorkflowEvent<TItinerary>,
): ReplanWorkflowState<TItinerary> {
  switch (event.type) {
    case "draft_changed":
      return {
        ...state,
        draftText: event.text,
        errorMessage: null,
      };
    case "interpreted":
      return {
        ...state,
        status: event.plan.executable ? "needs_confirmation" : "blocked",
        activePlan: event.plan,
        changeSet: null,
        lastResult: null,
        errorMessage: event.plan.executable ? null : "这次调整还没有可安全执行的计划。",
      };
    case "confirmed":
      if (!state.activePlan?.executable) {
        return {
          ...state,
          status: "blocked",
          errorMessage: "当前计划没有通过约束检查，不能执行。",
        };
      }
      if (state.executedPlanIds.includes(state.activePlan.id)) {
        return {
          ...state,
          status: "review",
          errorMessage: "这次调整已经执行过，已阻止重复提交。",
        };
      }
      return {
        ...state,
        status: "executing",
        errorMessage: null,
      };
    case "execute_started":
      return {
        ...state,
        status: "executing",
        errorMessage: null,
      };
    case "execute_finished": {
      if (!event.result.ok) {
        return {
          ...state,
          status: "error",
          lastResult: event.result,
          errorMessage: event.result.message,
        };
      }
      const activePlan = state.activePlan;
      const historyEntry =
        activePlan && event.changeSet
          ? {
              id: `${activePlan.id}-history`,
              createdAt: new Date().toISOString(),
              plan: activePlan,
              beforeItinerary: event.result.beforeItinerary,
              afterItinerary: event.result.afterItinerary,
              changeSet: event.changeSet,
              usedBackend: event.result.usedBackend,
            }
          : null;
      return {
        ...state,
        status: "review",
        lastResult: event.result,
        changeSet: event.changeSet,
        history: historyEntry ? [historyEntry, ...state.history].slice(0, 8) : state.history,
        executedPlanIds: activePlan
          ? [...state.executedPlanIds, activePlan.id]
          : state.executedPlanIds,
        errorMessage: null,
      };
    }
    case "execute_failed":
      return {
        ...state,
        status: "error",
        errorMessage: event.message,
      };
    case "undo_last":
      return {
        ...state,
        status: "idle",
        activePlan: null,
        lastResult: null,
        changeSet: null,
        history: state.history.slice(1),
        errorMessage: null,
      };
    default:
      return state;
  }
}
