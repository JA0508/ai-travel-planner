"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import type { TripMetadata, TripRevisionMetadata } from "@/features/trip-workspace/tripPersistence";
import { buildRouteStopSelector } from "@/features/trip-workspace/routeWorkspaceEditModel";
import {
  buildDayLoads,
  buildUserFacingRisks,
  formatDistance,
  formatMinutes,
  type RoutePreviewItinerary,
} from "./routePreviewModel";
import { RoadbookRepairPreview } from "./RoadbookRepairPreview";
import {
  latestRouteReloadActionLabel,
  latestRouteReloadReceipt,
  repairFailureMessage,
  undoRevisionReceipt,
  type LocalRepairImpact,
} from "./repairPreviewModel";
import { SavedLivingRoadbook } from "./SavedLivingRoadbook";
import { SafeReplaceCandidates, SafeReplacePreview } from "./SafeReplaceExperience";
import {
  LatestReplaceRequest,
  buildSafeReplaceCommandEnvelope,
  buildSafeReplacePreviewModel,
  parseSafeReplaceCandidates,
  safeReplaceFailureMessage,
  type SafeReplaceCandidate,
  type SafeReplaceCandidateResponse,
  type SafeReplacePreviewModel,
} from "./safeReplaceModel";
import type { RoutePreviewItem } from "./routePreviewModel";

type MutationPreviewResponse = {
  proposal: {
    id: string;
    proposal_digest: string;
    commands?: Array<{ type: string; stop_id?: string }> | null;
  };
  itinerary: RoutePreviewItinerary;
  impact_summary: {
    local_repair?: LocalRepairImpact;
  };
};

type MutationApplyResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  itinerary: RoutePreviewItinerary;
};

export type LatestRouteReloadResult =
  | { revisionNumber: number }
  | { errorMessage: string };

type Props = {
  itinerary: RoutePreviewItinerary;
  variant: "draft" | "saved";
  tripId?: string;
  baseRevisionId?: string;
  onApplied?: (response: MutationApplyResponse) => void;
  onReloadLatest?: () => Promise<LatestRouteReloadResult>;
  destination?: string | null;
  draftConfirmation?: {
    label: string;
    hint: string;
    recoveryMessage?: string;
    disabled: boolean;
    onConfirm: () => void;
  };
};

type RepairState =
  | { status: "idle" }
  | { status: "previewing"; day: number }
  | { status: "review"; day: number; before: RoutePreviewItinerary; preview: MutationPreviewResponse; applyErrorMessage?: string }
  | { status: "applying"; day: number; before: RoutePreviewItinerary; preview: MutationPreviewResponse }
  | { status: "applied"; day: number; revisionId: string; revisionNumber: number; undoing: boolean; errorMessage?: string; retryUndo?: boolean }
  | { status: "restored"; revisionNumber: number }
  | { status: "reloaded"; revisionNumber: number }
  | { status: "error"; message: string; day?: number; reloadable?: boolean; reloadAttempted?: boolean };

type ReplaceState =
  | { status: "idle" }
  | { status: "candidates"; target: RoutePreviewItem; options: SafeReplaceCandidate[]; loading: boolean; errorMessage?: string }
  | { status: "previewing"; target: RoutePreviewItem; options: SafeReplaceCandidate[]; candidate: SafeReplaceCandidate }
  | { status: "unsafe"; target: RoutePreviewItem; options: SafeReplaceCandidate[]; candidate: SafeReplaceCandidate }
  | { status: "review"; target: RoutePreviewItem; options: SafeReplaceCandidate[]; candidate: SafeReplaceCandidate; before: RoutePreviewItinerary; preview: MutationPreviewResponse; model: SafeReplacePreviewModel; applyErrorMessage?: string }
  | { status: "applying"; target: RoutePreviewItem; options: SafeReplaceCandidate[]; candidate: SafeReplaceCandidate; before: RoutePreviewItinerary; preview: MutationPreviewResponse; model: SafeReplacePreviewModel }
  | { status: "applied"; stopId: string; previousName: string; replacementName: string; revisionId: string; revisionNumber: number; undoing: boolean; errorMessage?: string; retryUndo?: boolean }
  | { status: "restored"; stopId: string; revisionNumber: number }
  | { status: "reloaded"; stopId: string; revisionNumber: number }
  | { status: "error"; message: string; stopId?: string; reloadable?: boolean; reloadAttempted?: boolean };

function replacementFocusStopId(state: ReplaceState): string | null {
  if ("target" in state) return state.target.stable_id ?? null;
  if ("stopId" in state) return state.stopId ?? null;
  return null;
}

export function focusRoadbookStopAfterReplacementDismissal(stopId: string): void {
  if (typeof document === "undefined") return;
  const restoreFocus = () => {
    document.querySelector<HTMLElement>(buildRouteStopSelector(stopId))?.focus();
  };
  if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") {
    restoreFocus();
    return;
  }
  window.requestAnimationFrame(restoreFocus);
}

export function focusRoadbookRelaxDayAfterRepairDismissal(day: number): void {
  if (typeof document === "undefined") return;
  const restoreFocus = () => {
    document.querySelector<HTMLElement>(`[data-roadbook-relax-day="${day}"]`)?.focus();
  };
  if (typeof window === "undefined" || typeof window.requestAnimationFrame !== "function") {
    restoreFocus();
    return;
  }
  window.requestAnimationFrame(restoreFocus);
}

export function ExecutableRoutePreview({
  itinerary,
  variant,
  tripId,
  baseRevisionId,
  onApplied,
  onReloadLatest,
  destination,
  draftConfirmation,
}: Props) {
  const loads = useMemo(() => buildDayLoads(itinerary), [itinerary]);
  const risks = useMemo(() => buildUserFacingRisks(itinerary, loads), [itinerary, loads]);
  const [repair, setRepair] = useState<RepairState>({ status: "idle" });
  const [replace, setReplace] = useState<ReplaceState>({ status: "idle" });
  const [reloadingLatest, setReloadingLatest] = useState(false);
  const previewRequestIdRef = useRef(0);
  const replaceRequestsRef = useRef(new LatestReplaceRequest());
  const replacementDismissFocusStopIdRef = useRef<string | null>(null);
  const repairDismissFocusDayRef = useRef<number | null>(null);
  const canRepair = variant === "saved" && Boolean(tripId && baseRevisionId && onApplied);
  const repairInteractionActive = repair.status === "previewing" || repair.status === "review" || repair.status === "applying";
  const replaceInteractionActive = replace.status === "candidates"
    || replace.status === "previewing"
    || replace.status === "unsafe"
    || replace.status === "review"
    || replace.status === "applying";

  useEffect(() => {
    if (replace.status !== "idle") return;
    const stopId = replacementDismissFocusStopIdRef.current;
    if (!stopId) return;
    replacementDismissFocusStopIdRef.current = null;
    focusRoadbookStopAfterReplacementDismissal(stopId);
  }, [replace.status]);

  useEffect(() => {
    if (repair.status !== "idle") return;
    const day = repairDismissFocusDayRef.current;
    if (day == null) return;
    repairDismissFocusDayRef.current = null;
    focusRoadbookRelaxDayAfterRepairDismissal(day);
  }, [repair.status]);

  async function previewRelaxation(day: number) {
    if (!tripId || !baseRevisionId) return;
    if (repairInteractionActive || replaceInteractionActive) return;
    if (!loads.some((load) => load.day === day)) {
      setRepair({ status: "error", day, message: "暂时无法读取这一天的行程负载，当前行程没有被修改。" });
      return;
    }
    const requestId = ++previewRequestIdRef.current;
    setRepair({ status: "previewing", day });
    const response = await postTripJson<MutationPreviewResponse>(
      TRIP_API_ENDPOINTS.previewLocalRelaxDayRepair(tripId),
      { base_revision_id: baseRevisionId, target_day: day, goal: "relax_day" },
      "暂时无法生成这次调整预览。当前行程没有被修改。",
      "服务暂时不可用，当前行程没有被修改。",
    );
    if (requestId !== previewRequestIdRef.current) return;
    if (!response.ok) {
      setRepair({
        status: "error",
        day,
        message: repairFailureMessage(response.code, "preview"),
        reloadable: isStaleRouteMutation(response.code, response.context),
      });
      return;
    }
    const localRepair = repairImpact(response.data);
    if (!localRepair) {
      setRepair({ status: "error", day, message: "暂时找不到一个有充分证据的安全小调整。原路线不会被改变。" });
      return;
    }
    setRepair({
      status: "review",
      day,
      before: itinerary,
      preview: {
        ...response.data,
        impact_summary: {
          ...response.data.impact_summary,
          local_repair: localRepair,
        },
      },
    });
  }

  function dismissRepair() {
    repairDismissFocusDayRef.current = "day" in repair && typeof repair.day === "number" ? repair.day : null;
    previewRequestIdRef.current += 1;
    setRepair({ status: "idle" });
  }

  async function applyRelaxation(
    day: number,
    before: RoutePreviewItinerary,
    preview: MutationPreviewResponse,
  ) {
    if (!tripId || !baseRevisionId || !onApplied) return;
    setRepair({ status: "applying", day, before, preview });
    const response = await postTripJson<MutationApplyResponse>(
      TRIP_API_ENDPOINTS.applyPersistedMutationProposal(tripId, preview.proposal.id),
      { base_revision_id: baseRevisionId, proposal_digest: preview.proposal.proposal_digest },
      "暂时无法应用这次调整。当前行程没有被修改。",
      "服务暂时不可用，当前行程没有被修改。",
      { headers: { "X-Idempotency-Key": `day-relax:${preview.proposal.id}:${preview.proposal.proposal_digest.slice(0, 16)}` } },
    );
    if (!response.ok) {
      if (hasUnknownMutationOutcome(response)) {
        setRepair({
          status: "review",
          day,
          before,
          preview,
          applyErrorMessage: "暂时无法确认这次调整是否已保存。可重试同一项调整；系统会核对这次操作，不会重复创建版本。",
        });
        return;
      }
      setRepair({
        status: "error",
        day,
        message: repairFailureMessage(response.code, "apply"),
        reloadable: isStaleRouteMutation(response.code, response.context),
      });
      return;
    }
    setReplace({ status: "idle" });
    onApplied(response.data);
    setRepair({
      status: "applied",
      day,
      revisionId: response.data.current_revision.id,
      revisionNumber: response.data.current_revision.revision_number,
      undoing: false,
    });
  }

  async function undoRelaxation(day: number, revisionId: string, revisionNumber: number) {
    if (!tripId || !onApplied) return;
    setRepair({ status: "applied", day, revisionId, revisionNumber, undoing: true });
    const response = await postTripJson<MutationApplyResponse>(
      TRIP_API_ENDPOINTS.undoPersistedRevision(tripId, revisionId),
      { base_revision_id: revisionId },
      "暂时无法撤销这次调整。当前保存的路线没有改变。",
      "服务暂时不可用，当前保存的路线没有改变。",
      { headers: { "X-Idempotency-Key": `undo-day-relax:${revisionId}` } },
    );
    if (!response.ok) {
      const retryUndo = hasUnknownMutationOutcome(response);
      const stale = isStaleRouteMutation(response.code, response.context);
      const message = retryUndo
        ? "暂时无法确认这次撤销是否已保存。可重试撤销；系统会核对这次操作，不会重复创建版本。"
        : repairFailureMessage(stale ? "undo_target_not_current" : response.code, "undo");
      setRepair(stale
        ? { status: "error", day, message, reloadable: true }
        : { status: "applied", day, revisionId, revisionNumber, undoing: false, errorMessage: message, retryUndo });
      return;
    }
    onApplied(response.data);
    setRepair({ status: "restored", revisionNumber: response.data.current_revision.revision_number });
  }

  async function findReplacementCandidates(target: RoutePreviewItem) {
    if (!tripId || !baseRevisionId || !target.stable_id || repairInteractionActive) return;
    const requestId = replaceRequestsRef.current.begin();
    setReplace({ status: "candidates", target, options: [], loading: true });
    const response = await postTripJson<SafeReplaceCandidateResponse>(
      TRIP_API_ENDPOINTS.previewCompletionTaskCandidates,
      {
        itinerary,
        task_id: "replace_stop",
        task_instance_key: `replace:${target.stable_id}`,
        replacement_stop_id: target.stable_id,
      },
      "暂时无法寻找替代地点。",
      "服务暂时不可用，先保留现在这一站。",
    );
    if (!replaceRequestsRef.current.isLatest(requestId)) return;
    if (!response.ok) {
      setReplace({
        status: "candidates",
        target,
        options: [],
        loading: false,
        errorMessage: safeReplaceFailureMessage(response.code, "candidates"),
      });
      return;
    }
    setReplace({
      status: "candidates",
      target,
      options: parseSafeReplaceCandidates(
        response.data.options,
        target.verified_place?.provider_place_id,
      ),
      loading: false,
    });
  }

  async function previewReplacement(
    target: RoutePreviewItem,
    options: SafeReplaceCandidate[],
    candidate: SafeReplaceCandidate,
  ) {
    if (!tripId || !baseRevisionId) return;
    if (!candidate.route_impact.safe_to_apply) {
      setReplace({ status: "unsafe", target, options, candidate });
      return;
    }
    const requestId = replaceRequestsRef.current.begin();
    setReplace({ status: "previewing", target, options, candidate });
    let envelope;
    try {
      envelope = buildSafeReplaceCommandEnvelope(baseRevisionId, target, candidate);
    } catch {
      setReplace({ status: "error", message: "这个地点暂时不能安全替换。原路线没有被改变。", stopId: target.stable_id ?? undefined });
      return;
    }
    const response = await postTripJson<MutationPreviewResponse>(
      TRIP_API_ENDPOINTS.previewPersistedMutation(tripId),
      envelope,
      "暂时无法生成替换预览。",
      "服务暂时不可用，原路线没有被改变。",
    );
    if (!replaceRequestsRef.current.isLatest(requestId)) return;
    if (!response.ok) {
      setReplace({
        status: "error",
        message: safeReplaceFailureMessage(response.code, "preview", response.context),
        stopId: target.stable_id ?? undefined,
        reloadable: isStaleRouteMutation(response.code, response.context),
      });
      return;
    }
    let model: SafeReplacePreviewModel;
    try {
      model = buildSafeReplacePreviewModel(itinerary, response.data.itinerary, target.stable_id!);
    } catch {
      setReplace({ status: "error", message: "替换预览缺少可验证的局部路线。原路线没有被改变。", stopId: target.stable_id ?? undefined });
      return;
    }
    setReplace({ status: "review", target, options, candidate, before: itinerary, preview: response.data, model });
  }

  async function applyReplacement(state: Extract<ReplaceState, { status: "review" | "applying" }>) {
    if (!tripId || !baseRevisionId || !onApplied) return;
    setReplace({ ...state, status: "applying" });
    const response = await postTripJson<MutationApplyResponse>(
      TRIP_API_ENDPOINTS.applyPersistedMutationProposal(tripId, state.preview.proposal.id),
      { base_revision_id: baseRevisionId, proposal_digest: state.preview.proposal.proposal_digest },
      "暂时无法保存这次替换。",
      "服务暂时不可用，原来的地点仍然保留。",
      { headers: { "X-Idempotency-Key": `safe-replace:${state.preview.proposal.id}:${state.preview.proposal.proposal_digest.slice(0, 16)}` } },
    );
    if (!response.ok) {
      if (hasUnknownMutationOutcome(response)) {
        setReplace({
          ...state,
          status: "review",
          applyErrorMessage: "暂时无法确认这次替换是否已保存。可重试同一项替换；系统会核对这次操作，不会重复创建版本。",
        });
        return;
      }
      setReplace({
        status: "error",
        message: safeReplaceFailureMessage(response.code, "apply", response.context),
        stopId: state.target.stable_id ?? undefined,
        reloadable: isStaleRouteMutation(response.code, response.context),
      });
      return;
    }
    setRepair({ status: "idle" });
    onApplied(response.data);
    setReplace({
      status: "applied",
      stopId: state.target.stable_id!,
      previousName: state.target.name,
      replacementName: state.candidate.name,
      revisionId: response.data.current_revision.id,
      revisionNumber: response.data.current_revision.revision_number,
      undoing: false,
    });
  }

  async function undoReplacement(state: Extract<ReplaceState, { status: "applied" }>) {
    if (!tripId || !onApplied) return;
    setReplace({ ...state, undoing: true, errorMessage: undefined });
    const response = await postTripJson<MutationApplyResponse>(
      TRIP_API_ENDPOINTS.undoPersistedRevision(tripId, state.revisionId),
      { base_revision_id: state.revisionId },
      "暂时无法撤销这次替换。",
      "服务暂时不可用，当前路线仍然保留。",
      { headers: { "X-Idempotency-Key": `undo-safe-replace:${state.revisionId}` } },
    );
    if (!response.ok) {
      const retryUndo = hasUnknownMutationOutcome(response);
      const message = retryUndo
        ? "暂时无法确认这次撤销是否已保存。可重试撤销；系统会核对这次操作，不会重复创建版本。"
        : safeReplaceFailureMessage(response.code, "undo", response.context);
      if (isStaleRouteMutation(response.code, response.context)) {
        setReplace({ status: "error", message, stopId: state.stopId, reloadable: true });
      } else {
        setReplace({ ...state, undoing: false, errorMessage: message, retryUndo });
      }
      return;
    }
    onApplied(response.data);
    setReplace({
      status: "restored",
      stopId: state.stopId,
      revisionNumber: response.data.current_revision.revision_number,
    });
  }

  function dismissReplacement() {
    replacementDismissFocusStopIdRef.current = replacementFocusStopId(replace);
    replaceRequestsRef.current.cancel();
    setReplace({ status: "idle" });
  }

  async function reloadLatestRoute(kind: "repair" | "replace", message: string, stopId?: string, repairDay?: number) {
    if (!onReloadLatest || reloadingLatest) return;
    setReloadingLatest(true);
    const reloadResult = await onReloadLatest();
    setReloadingLatest(false);
    if ("errorMessage" in reloadResult) {
      const state = {
        status: "error" as const,
        message: `${message} ${reloadResult.errorMessage}`,
        reloadable: true,
        reloadAttempted: true,
      };
      if (kind === "repair") setRepair({ ...state, day: repairDay });
      else setReplace({ ...state, stopId });
      return;
    }
    if (kind === "repair") setRepair({ status: "reloaded", revisionNumber: reloadResult.revisionNumber });
    else setReplace({ status: "reloaded", stopId: stopId ?? "", revisionNumber: reloadResult.revisionNumber });
  }

  function showOtherCandidates() {
    if (replace.status !== "unsafe" && replace.status !== "review" && replace.status !== "applying") return;
    replaceRequestsRef.current.cancel();
    setReplace({ status: "candidates", target: replace.target, options: replace.options, loading: false });
  }

  if (variant === "saved") {
    return (
      <section className="erp-shell" aria-label="可执行路线预览" data-route-surface="roadbook">
        <SavedLivingRoadbook
          itinerary={itinerary}
          destination={destination}
          loads={loads}
          canRepair={canRepair}
          repairStatus={repair.status === "applied" && repair.undoing ? "undoing" : repair.status}
          repairBlocked={replaceInteractionActive}
          repairDay={"day" in repair ? repair.day : undefined}
          onRelaxDay={(day) => void previewRelaxation(day)}
          replaceControlStatus={
            repairInteractionActive && (replace.status === "idle" || replace.status === "restored")
              ? "blocked"
              : replace.status === "idle" || replace.status === "restored"
              ? "available"
              : replace.status === "applied"
                ? "applied"
                : replace.status === "previewing" || replace.status === "applying"
                  ? "processing"
                  : replace.status === "error"
                    ? "attention"
                    : "choosing"
          }
          focusedStopId={"stopId" in replace ? replace.stopId : undefined}
          onReplaceStop={(target) => void findReplacementCandidates(target)}
        />
        {replace.status === "candidates" ? (
          <SafeReplaceCandidates
            targetName={replace.target.name}
            candidates={replace.options}
            loading={replace.loading}
            errorMessage={replace.errorMessage}
            onSelect={(candidate) => void previewReplacement(replace.target, replace.options, candidate)}
            onKeep={dismissReplacement}
          />
        ) : null}
        {replace.status === "previewing" ? (
          <SafeReplaceCandidates
            targetName={replace.target.name}
            candidates={replace.options}
            loading
            onSelect={() => undefined}
            onKeep={dismissReplacement}
          />
        ) : null}
        {replace.status === "unsafe" ? (
          <SafeReplacePreview
            targetName={replace.target.name}
            candidate={replace.candidate}
            applying={false}
            onApply={() => undefined}
            onKeep={dismissReplacement}
            onOtherCandidates={showOtherCandidates}
          />
        ) : null}
        {replace.status === "review" || replace.status === "applying" ? (
          <SafeReplacePreview
            targetName={replace.target.name}
            candidate={replace.candidate}
            model={replace.model}
            applying={replace.status === "applying"}
            errorMessage={replace.status === "review" ? replace.applyErrorMessage : undefined}
            onApply={() => void applyReplacement(replace)}
            onKeep={dismissReplacement}
            onOtherCandidates={showOtherCandidates}
          />
        ) : null}
        {repair.status === "review" || repair.status === "applying" ? (
          <RoadbookRepairPreview
            before={repair.before}
            after={repair.preview.itinerary}
            targetDay={repair.day}
            impact={repair.preview.impact_summary.local_repair!}
            applying={repair.status === "applying"}
            errorMessage={repair.status === "review" ? repair.applyErrorMessage : undefined}
            onKeep={dismissRepair}
            onApply={() => void applyRelaxation(repair.day, repair.before, repair.preview)}
          />
        ) : null}
        {repair.status === "applied" ? (
          <RepairFeedback
            autoFocus
            message={`这段路线已经松了一点，调整已保存为版本 ${repair.revisionNumber}。`}
            errorMessage={repair.errorMessage}
            actionLabel={repair.undoing ? "正在恢复…" : repair.retryUndo ? "重试撤销" : "撤销刚才的调整"}
            busy={repair.undoing}
            onAction={() => void undoRelaxation(repair.day, repair.revisionId, repair.revisionNumber)}
          />
        ) : null}
        {repair.status === "restored" ? <RepairFeedback autoFocus eyebrow="ROUTE RESTORED" message={undoRevisionReceipt("relax_day", repair.revisionNumber)} /> : null}
        {repair.status === "reloaded" ? <RepairFeedback autoFocus eyebrow="LATEST ROUTE LOADED" message={latestRouteReloadReceipt("relax_day", repair.revisionNumber)} /> : null}
        {repair.status === "error" ? <RepairError message={repair.message} onDismiss={dismissRepair} actionLabel={repair.reloadable ? latestRouteReloadActionLabel(repair.reloadAttempted === true) : undefined} busy={reloadingLatest} onAction={repair.reloadable ? () => void reloadLatestRoute("repair", repair.message, undefined, repair.day) : undefined} /> : null}
        {replace.status === "applied" ? (
          <RepairFeedback
            autoFocus
            message={`这个地点已经从${replace.previousName}换成${replace.replacementName}，并保存为版本 ${replace.revisionNumber}。其他已经确认的安排没有被改动。`}
            errorMessage={replace.errorMessage}
            actionLabel={replace.undoing ? "正在恢复…" : replace.retryUndo ? "重试撤销" : "撤销刚才的替换"}
            busy={replace.undoing}
            onAction={() => void undoReplacement(replace)}
          />
        ) : null}
        {replace.status === "restored" ? <RepairFeedback autoFocus eyebrow="ROUTE RESTORED" message={undoRevisionReceipt("replace_stop", replace.revisionNumber)} /> : null}
        {replace.status === "reloaded" ? <RepairFeedback autoFocus eyebrow="LATEST ROUTE LOADED" message={latestRouteReloadReceipt("replace_stop", replace.revisionNumber)} /> : null}
        {replace.status === "error" ? <RepairError message={replace.message} onDismiss={dismissReplacement} actionLabel={replace.reloadable ? latestRouteReloadActionLabel(replace.reloadAttempted === true) : undefined} busy={reloadingLatest} onAction={replace.reloadable ? () => void reloadLatestRoute("replace", replace.message, replace.stopId) : undefined} /> : null}
        <RoutePreviewStyles />
      </section>
    );
  }

  return (
    <section className="erp-shell" aria-label="可执行路线预览" data-route-surface="roadbook">
      <header className="erp-header">
        <div>
          <p>路线预览</p>
          <h2>你的第一版行程</h2>
          <span>确认后才会保存为正式行程。</span>
        </div>
        <div className="erp-header-actions">
          <div className="erp-header-summary">
            <strong>{itinerary.trip_days} 天</strong>
            <span>{loads.reduce((total, day) => total + day.activityCount, 0)} 个活动</span>
            <span>{loads.reduce((total, day) => total + day.fixedCount, 0)} 项固定安排</span>
          </div>
          {draftConfirmation ? <div className="erp-draft-route-confirmation" data-draft-route-confirmation="true">{draftConfirmation.recoveryMessage ? <p role="alert">{draftConfirmation.recoveryMessage}</p> : <span>{draftConfirmation.hint}</span>}<button type="button" onClick={draftConfirmation.onConfirm} disabled={draftConfirmation.disabled}>{draftConfirmation.label}</button></div> : null}
        </div>
      </header>

      {risks.length ? <section className="erp-risks" role="alert"><strong>需要留意</strong>{risks.map((risk) => <p key={risk}>{risk}</p>)}</section> : null}

      <div className="erp-days">
        {itinerary.days.map((day) => {
          const load = loads.find((entry) => entry.day === day.day);
          if (!load) return null;
          return <article className="erp-day" key={day.day}>
            <header className="erp-day-header">
              <div><p>第 {day.day} 天</p><h3>{load.paceLabel}</h3><span>{load.explanation}</span></div>
              <div className={`erp-pace erp-pace--${load.pace}`}>{load.paceLabel}</div>
            </header>
            <div className="erp-load-grid" aria-label={`第 ${day.day} 天负载`}>
              <Metric label="活动" value={`${load.activityCount} 项`} />
              <Metric label="活动时长" value={formatMinutes(load.activityMinutes)} />
              <Metric label="移动时间" value={formatMinutes(load.travelMinutes)} />
              <Metric label="路线距离" value={formatDistance(load.routeDistanceMeters)} />
            </div>
            <div className="erp-timeline">
              {day.blocks.flatMap((block) => block.items.map((item, index) => <div className="erp-timeline-row" key={`${block.block_type}-${item.stable_id ?? item.name}-${index}`}>
                {item.travel_from_name ? <TravelLeg item={item} /> : null}
                <div className="erp-stop">
                  <time>{item.start_time}–{item.end_time}</time>
                  <div><div className="erp-stop-title"><strong>{item.name}</strong>{item.is_fixed ? <span className="erp-fixed">这段安排已固定，不会被随意改动</span> : <span className="erp-kind">{isSystemSuggested(item) ? "系统补充" : item.source_label === "必去" ? "必去" : item.source_label === "可调整" ? "可调整" : item.type === "restaurant" ? "餐食" : item.type === "hotel" ? "住宿" : "用户地点"}</span>}</div>{item.placement_reason ? <p>{item.placement_reason}</p> : <p>暂时没有可验证的安排说明。</p>}</div>
                </div>
              </div>))}
            </div>
            <details className="erp-why"><summary>为什么这样安排</summary><DayReasons items={day.blocks.flatMap((block) => block.items)} /></details>
            {canRepair ? <button className="erp-repair-button" type="button" onClick={() => void previewRelaxation(day.day)} disabled={repair.status === "previewing" || repair.status === "applying"}>{repair.status === "previewing" && repair.day === day.day ? "正在评估调整……" : "这一天太赶"}</button> : null}
          </article>;
        })}
      </div>

      {repair.status === "review" || repair.status === "applying" ? <RoadbookRepairPreview before={repair.before} after={repair.preview.itinerary} targetDay={repair.day} impact={repair.preview.impact_summary.local_repair!} applying={repair.status === "applying"} onKeep={dismissRepair} onApply={() => void applyRelaxation(repair.day, repair.before, repair.preview)} /> : null}
      {repair.status === "error" ? <p className="erp-error" role="alert">{repair.message}</p> : null}
      <RoutePreviewStyles />
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function TravelLeg({ item }: { item: RoutePreviewItinerary["days"][number]["blocks"][number]["items"][number] }) {
  if (item.travel_data_status === "confirmed" && item.travel_duration_s != null) {
    return <div className="erp-leg"><span>路程已确认 · 预计移动</span><strong>{item.travel_from_name} → {item.name}</strong><small>{formatMinutes(Math.round(item.travel_duration_s / 60))}{item.travel_distance_m != null ? ` · ${formatDistance(item.travel_distance_m)}` : ""}</small></div>;
  }
  return <div className="erp-leg"><span>路线待确认</span><strong>{item.travel_from_name} → {item.name}</strong><small>暂时无法确认这段路程，不会把它当作已验证路线。</small></div>;
}

function isSystemSuggested(item: RoutePreviewItinerary["days"][number]["blocks"][number]["items"][number]) {
  return item.source_type === "auto_seeded_poi" || item.source_type === "auto_seeded_meal" || item.source_type === "auto_filled";
}

function DayReasons({ items }: { items: RoutePreviewItinerary["days"][number]["blocks"][number]["items"] }) {
  const reasons = items.filter((item) => item.placement_reason).slice(0, 3);
  return <div>{reasons.length ? reasons.map((item) => <p key={item.stable_id ?? item.name}><strong>{item.name}</strong>{item.placement_reason}</p>) : <p>暂时没有可验证的安排说明。</p>}</div>;
}

function repairImpact(preview: MutationPreviewResponse): LocalRepairImpact | undefined {
  const impact = preview.impact_summary.local_repair;
  if (!impact) return undefined;
  const stopId = preview.proposal.commands?.find(
    (command) => command.type === "move_stop" && command.stop_id,
  )?.stop_id;
  return stopId ? { ...impact, stop_id: stopId } : impact;
}

function isStaleRouteMutation(code: string | undefined, context?: Record<string, unknown>): boolean {
  const staleCodes = [
    "stale_base_revision",
    "stale_mutation_proposal",
    "mutation_proposal_expired",
    "mutation_proposal_invalidated",
    "proposal_base_revision_mismatch",
    "undo_target_not_current",
  ];
  return [code, context?.reason_code]
    .filter((value): value is string => typeof value === "string")
    .some((value) => staleCodes.includes(value));
}

function hasUnknownMutationOutcome(response: { responseStatus?: number; aborted?: boolean }) {
  return !response.aborted && (response.responseStatus === undefined || response.responseStatus >= 500);
}

function RepairFeedback({
  autoFocus = false,
  eyebrow = "ROUTE SAVED",
  message,
  errorMessage,
  actionLabel,
  busy = false,
  onAction,
}: {
  autoFocus?: boolean;
  eyebrow?: string;
  message: string;
  errorMessage?: string;
  actionLabel?: string;
  busy?: boolean;
  onAction?: () => void;
}) {
  const feedbackRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!autoFocus || typeof window === "undefined") {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      feedbackRef.current?.focus({ preventScroll: true });
    });

    return () => window.cancelAnimationFrame(frame);
  }, [autoFocus]);

  return (
    <aside
      ref={feedbackRef}
      className="erp-repair-feedback"
      role="status"
      tabIndex={autoFocus ? -1 : undefined}
    >
      <div>
        <p>{eyebrow}</p>
        <strong>{message}</strong>
        {errorMessage ? <span className="erp-repair-feedback__error" role="alert">{errorMessage}</span> : null}
      </div>
      {actionLabel && onAction ? <button type="button" onClick={onAction} disabled={busy}>{actionLabel}</button> : null}
    </aside>
  );
}

function RepairError({
  message,
  onDismiss,
  actionLabel,
  busy = false,
  onAction,
}: {
  message: string;
  onDismiss: () => void;
  actionLabel?: string;
  busy?: boolean;
  onAction?: () => void;
}) {
  return <aside className="erp-repair-error" role="alert"><div><p>这次没有改动路线</p><strong>{message}</strong></div><div style={{ display: "flex", alignItems: "center", gap: 16 }}>{actionLabel && onAction ? <button type="button" onClick={onAction} disabled={busy}>{busy ? "正在载入…" : actionLabel}</button> : null}<button type="button" style={{ border: 0, fontSize: 24 }} onClick={onDismiss} aria-label="关闭调整提示">×</button></div></aside>;
}

function RoutePreviewStyles() {
  return <style>{`
    .erp-shell{display:grid;gap:18px;margin:0 0 24px}.erp-header,.erp-day{border:1px solid var(--ec-line);background:rgba(255,253,249,.94);box-shadow:var(--ec-shadow-2)}.erp-header{display:flex;justify-content:space-between;gap:18px;align-items:end;padding:24px 26px;border-radius:20px}.erp-header p,.erp-day-header p{margin:0 0 5px;color:var(--ec-route-blue);font-size:12px;font-weight:900;letter-spacing:.08em}.erp-header h2,.erp-day h3{margin:0;font-family:"Iowan Old Style",Georgia,serif;color:var(--ec-ink);letter-spacing:0}.erp-header h2{font-size:30px}.erp-header span,.erp-day-header span{color:var(--ec-slate);font-size:14px;line-height:1.55}.erp-header-actions{display:grid;justify-items:end;gap:10px}.erp-header-summary{display:flex;gap:10px;flex-wrap:wrap;justify-content:end}.erp-header-summary>*{padding:7px 10px;border-radius:999px;background:rgba(21,21,21,.05);font-size:12px}.erp-draft-route-confirmation{display:grid;justify-items:end;gap:6px}.erp-draft-route-confirmation span{max-width:240px;text-align:right;font-size:12px}.erp-draft-route-confirmation p{max-width:260px;margin:0;padding:8px 10px;border:1px solid rgba(162,61,50,.32);border-radius:8px;background:#fff4f2;color:#8d3028;text-align:right;font-size:12px;font-weight:800;letter-spacing:0;line-height:1.45}.erp-draft-route-confirmation button{min-height:44px;border:1px solid var(--ec-night);border-radius:8px;background:var(--ec-night);padding:10px 14px;color:#fffdf9;font:inherit;font-weight:900;cursor:pointer}.erp-draft-route-confirmation button:focus-visible{outline:3px solid var(--ec-ochre);outline-offset:3px}.erp-draft-route-confirmation button:disabled{cursor:not-allowed;opacity:.52}.erp-risks{border:1px solid rgba(185,78,72,.35);background:rgba(255,244,242,.85);padding:16px 18px;border-radius:14px;color:#822b27}.erp-risks p{margin:6px 0 0;line-height:1.5}.erp-days{display:grid;gap:16px}.erp-day{border-radius:18px;padding:22px}.erp-day-header{display:flex;justify-content:space-between;gap:16px;align-items:start;padding-bottom:16px;border-bottom:1px solid var(--ec-line)}.erp-day-header h3{font-size:25px;margin-bottom:4px}.erp-pace{padding:7px 10px;border-radius:999px;font-size:12px;font-weight:900;white-space:nowrap}.erp-pace--relaxed{background:#e9f3e8;color:#3f6c43}.erp-pace--balanced{background:#edf2f7;color:#486273}.erp-pace--rushed{background:#fff1dd;color:#8b5e1f}.erp-pace--infeasible{background:#fde9e6;color:#9d302a}.erp-load-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:16px 0}.erp-load-grid div{padding:11px;border:1px solid var(--ec-line);border-radius:10px;background:rgba(247,244,238,.72)}.erp-load-grid span{display:block;font-size:11px;color:var(--ec-slate);font-weight:800}.erp-load-grid strong{font-size:14px;color:var(--ec-ink)}.erp-timeline{display:grid;gap:10px}.erp-timeline-row{display:grid;gap:8px}.erp-leg{margin-left:26px;padding:8px 10px;border-left:2px solid rgba(37,99,235,.35);display:grid;gap:2px;color:var(--ec-slate);font-size:12px}.erp-leg span{color:var(--ec-route-blue);font-weight:900}.erp-leg strong{color:var(--ec-ink);font-size:13px}.erp-stop{display:grid;grid-template-columns:98px minmax(0,1fr);gap:14px;padding:14px 12px;border-radius:10px;background:rgba(255,255,255,.76);border:1px solid rgba(21,21,21,.08)}.erp-stop time{font-weight:900;color:var(--ec-route-blue);font-size:13px}.erp-stop-title{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.erp-stop strong{color:var(--ec-ink);font-size:17px}.erp-stop p{margin:5px 0 0;color:var(--ec-slate);font-size:13px;line-height:1.55}.erp-fixed,.erp-kind{padding:4px 7px;border-radius:999px;font-size:11px;font-weight:900}.erp-fixed{background:rgba(117,91,40,.12);color:#76531f}.erp-kind{background:rgba(37,99,235,.08);color:#285eae}.erp-why{margin-top:14px;color:var(--ec-slate);font-size:13px}.erp-why summary{cursor:pointer;font-weight:900;color:var(--ec-ink)}.erp-why div{display:grid;gap:6px;margin-top:9px}.erp-why p{margin:0;line-height:1.55}.erp-why p strong{margin-right:5px;color:var(--ec-ink)}.erp-repair-button{border:0;border-radius:10px;padding:10px 13px;background:var(--ec-ink);color:#fff;font-weight:900;cursor:pointer;margin-top:16px}.erp-repair-button:disabled{opacity:.55;cursor:wait}.erp-repair-feedback,.erp-repair-error{display:flex;justify-content:space-between;align-items:center;gap:18px;border-top:3px solid #5f6859;border-bottom:1px solid rgba(23,22,19,.18);background:#f7f3eb;padding:18px 22px;color:#171613}.erp-repair-feedback p,.erp-repair-error p{margin:0 0 4px;color:#5f6859;font-size:9px;font-weight:900;letter-spacing:.14em}.erp-repair-feedback strong,.erp-repair-error strong{font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:18px}.erp-repair-feedback__error{display:block;margin-top:6px;color:#8d3028;font-size:12px;font-weight:800}.erp-repair-feedback button,.erp-repair-error button{border:0;border-bottom:1px solid currentColor;background:transparent;padding:7px 0;color:#171613;font-weight:900;cursor:pointer}.erp-repair-feedback button:disabled{opacity:.55;cursor:wait}.erp-repair-error{border-top-color:#a23d32}.erp-repair-error p{color:#a23d32}.erp-repair-error>button{border:0;font-size:24px}.erp-error{margin:0;color:#9d302a;font-weight:800}@media(max-width:720px){.erp-header{display:grid;align-items:start;padding:19px}.erp-header-actions,.erp-draft-route-confirmation{justify-items:start}.erp-header-summary{justify-content:start}.erp-draft-route-confirmation span,.erp-draft-route-confirmation p{max-width:none;text-align:left}.erp-draft-route-confirmation button{width:100%}.erp-day{padding:16px}.erp-load-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.erp-stop{grid-template-columns:1fr;gap:5px}.erp-day-header{display:grid}.erp-header h2{font-size:27px}.erp-repair-feedback,.erp-repair-error{display:grid;align-items:start;margin:0 -18px;padding:16px 18px}.erp-repair-feedback button,.erp-repair-error button{justify-self:start}.erp-repair-feedback strong,.erp-repair-error strong{font-size:16px}}
  `}</style>;
}
