"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { getTripJson, postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import { ImportReviewWorkspace } from "@/features/imports/ImportReviewWorkspace";
import type { IntentClarification, SourceLinkedTripIntentEnvelope } from "@/features/intent-confirmation/intentTypes";
import { buildPrePlanConfirmationViewModel, getPrePlanClarificationControl, type PrePlanClarificationControl } from "./prePlanConfirmationModel";
import { buildPrePlanHandoffStatus, userFacingPrePlanHandoffError } from "./plannerHandoffModel";
import { PlannerTraceReviewPanel } from "./PlannerTraceReviewPanel";
import { markPlannerHandoffReviewStale, type PlannerHandoffReviewSummary } from "./plannerTraceReviewModel";
import { ExecutableRoutePreview } from "@/features/executable-route-preview/ExecutableRoutePreview";
import type { TripMetadata, TripRevisionMetadata } from "@/features/trip-workspace/tripPersistence";
import type {
  DraftClarificationAnswer,
  DraftClarificationResolveRequest,
  DraftIntentEditOperation,
  DraftIntentEditRequest,
  DraftIntentEditResponse,
  LatestPrePlanIntentResponse,
} from "./draftIntentEditApi";

type ItineraryResponse = any;

type DraftIntentResponse = {
  envelope: SourceLinkedTripIntentEnvelope;
  revision: { id: string; revision_number: number };
};

type PreviewResponse = {
  draft_intent_revision_id: string;
  handoff: { id: string; trace_digest: string };
  itinerary: ItineraryResponse;
  review_summary: PlannerHandoffReviewSummary;
};

type ApplyResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  itinerary: ItineraryResponse;
  review_summary: PlannerHandoffReviewSummary;
};

type CandidateListResponse = {
  candidates: Array<{ id: string; display_name: string; workflow_state: string }>;
};

type BootstrapState = "idle" | "compiling" | "ready" | "failed";
type Feedback = { tone: "info" | "error"; message: string } | null;
type CriticalEditor = "destination" | "date_policy" | "trip_days" | "pace";
type CriticalIntentFormDraft = {
  city?: string;
  startDate?: string;
  endDate?: string;
  tripDays?: string;
  timeMode?: "dates" | "days";
  pace?: "relaxed" | "balanced" | "intensive";
};
type PendingDraftIntentRequest = {
  endpoint: string;
  payload: DraftIntentEditRequest | DraftClarificationResolveRequest;
  idempotencyKey: string;
  operation: DraftIntentEditOperation;
  formDraft: CriticalIntentFormDraft;
  clarificationId?: string;
  restoreFocusAfterSuccess?: boolean;
};
type DraftIntentStaleConflict = {
  attempted: PendingDraftIntentRequest;
  originalBaseDraftVersion: number;
  originalBaseIntentRevisionId: string;
  latest: LatestPrePlanIntentResponse;
};

type Props = {
  tripId: string;
  directUserText: string;
  onApplied: (response: ApplyResponse) => void;
  onCancel: () => void;
};

export function PrePlanIntentWorkspace({ tripId, directUserText, onApplied, onCancel }: Props) {
  const [intent, setIntent] = useState<DraftIntentResponse | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [bootstrap, setBootstrap] = useState<BootstrapState>("idle");
  const [operation, setOperation] = useState<"idle" | "previewing" | "applying">("idle");
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [candidates, setCandidates] = useState<CandidateListResponse["candidates"]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);
  const [latestIntentRevisionId, setLatestIntentRevisionId] = useState<string | null>(null);
  const [draftVersion, setDraftVersion] = useState<number | null>(null);
  const [sourcesChanged, setSourcesChanged] = useState(false);
  const [activeEditor, setActiveEditor] = useState<CriticalEditor | null>(null);
  const [formDraft, setFormDraft] = useState<CriticalIntentFormDraft | null>(null);
  const [pendingEdit, setPendingEdit] = useState<PendingDraftIntentRequest | null>(null);
  const [retryableRequest, setRetryableRequest] = useState<PendingDraftIntentRequest | null>(null);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [staleConflict, setStaleConflict] = useState<DraftIntentStaleConflict | null>(null);
  const [restorePrimaryFocus, setRestorePrimaryFocus] = useState(false);
  const autoCompileTripRef = useRef<string | null>(null);
  const compileInFlightRef = useRef(false);

  const view = useMemo(
    () => (intent ? buildPrePlanConfirmationViewModel(intent.envelope) : null),
    [intent],
  );
  const busy = bootstrap === "compiling" || operation !== "idle" || pendingEdit !== null;
  const previewStatus = useMemo(
    () => preview ? buildPrePlanHandoffStatus({ previewIntentRevisionId: preview.draft_intent_revision_id, latestIntentRevisionId }) : null,
    [latestIntentRevisionId, preview],
  );
  const reviewSummary = useMemo(
    () => preview ? previewStatus?.kind === "stale" ? markPlannerHandoffReviewStale(preview.review_summary) : preview.review_summary : null,
    [preview, previewStatus?.kind],
  );
  const canGeneratePreview = Boolean(view?.canGeneratePreview && !sourcesChanged && (!preview || previewStatus?.canGenerateReplacement));
  const previewHasExecutionConflict = reviewSummary?.status === "unstable" || preview?.itinerary?.planner_realism?.status === "unstable";
  const canApplyPreview = Boolean(preview && intent && !sourcesChanged && reviewSummary?.can_apply && !previewHasExecutionConflict && previewStatus?.canApply);

  useEffect(() => {
    void refreshCandidates();
  }, [tripId]);

  useEffect(() => {
    if (autoCompileTripRef.current === tripId || compileInFlightRef.current) return;
    autoCompileTripRef.current = tripId;
    void bootstrapIntent();
  }, [tripId]);

  useEffect(() => {
    if (!restorePrimaryFocus) return;
    document.getElementById("preplan-primary-action")?.focus();
    setRestorePrimaryFocus(false);
  }, [restorePrimaryFocus]);

  async function refreshCandidates() {
    const result = await getTripJson<CandidateListResponse>(
      TRIP_API_ENDPOINTS.listTripCandidates(tripId),
      "暂时无法加载已审核地点。",
      "服务暂时不可用，你的输入不会丢失。",
    );
    if (result.ok) {
      setCandidates(result.data.candidates.filter((candidate) => candidate.workflow_state === "pending"));
    }
  }

  async function compileIntent() {
    if (compileInFlightRef.current) return;
    compileInFlightRef.current = true;
    setBootstrap("compiling");
    setFeedback({ tone: "info", message: "正在整理你的旅行需求……" });
    const parentIntentRevisionId = latestIntentRevisionId;
    const result = await postTripJson<DraftIntentResponse>(
      TRIP_API_ENDPOINTS.compilePrePlanIntent(tripId),
      {
        base_trip_revision_id: null,
        base_intent_revision_id: parentIntentRevisionId,
        direct_user_text: directUserText,
        candidate_ids: selectedCandidateIds,
        use_llm_proposal_adapter: true,
      },
      "暂时无法整理旅行信息，你的输入已经保留。",
      "服务暂时不可用，你的输入不会丢失。",
      { headers: { "X-Idempotency-Key": `draft-intent:${tripId}:${parentIntentRevisionId ?? "root"}` } },
    );
    compileInFlightRef.current = false;
    if (!result.ok) {
      setBootstrap("failed");
      setFeedback({ tone: "error", message: userFacingRequestError(result.code) });
      return;
    }
    setIntent(result.data);
    setLatestIntentRevisionId(result.data.revision.id);
    void refreshLatestIntent();
    setSourcesChanged(false);
    setBootstrap("ready");
    setFeedback(null);
  }

  async function bootstrapIntent() {
    setBootstrap("compiling");
    setFeedback({ tone: "info", message: "正在整理你的旅行需求……" });
    const result = await getTripJson<LatestPrePlanIntentResponse>(
      TRIP_API_ENDPOINTS.getLatestPrePlanIntent(tripId),
      "暂时无法获取最新行程信息。",
      "服务暂时不可用，你的输入不会丢失。",
    );
    if (result.ok) {
      hydrateLatestIntent(result.data);
      setBootstrap("ready");
      setFeedback(null);
      return;
    }
    if (result.code === "intent_edit_no_longer_applicable") {
      await compileIntent();
      return;
    }
    setBootstrap("failed");
    setFeedback({ tone: "error", message: userFacingRequestError(result.code) });
  }

  async function refreshLatestIntent(): Promise<LatestPrePlanIntentResponse | null> {
    const result = await getTripJson<LatestPrePlanIntentResponse>(
      TRIP_API_ENDPOINTS.getLatestPrePlanIntent(tripId),
      "暂时无法获取最新行程信息。",
      "服务暂时不可用，你的修改还在这里。",
    );
    if (!result.ok) return null;
    hydrateLatestIntent(result.data);
    return result.data;
  }

  function hydrateLatestIntent(latest: LatestPrePlanIntentResponse) {
    setIntent({ envelope: latest.envelope, revision: latest.revision });
    setLatestIntentRevisionId(latest.revision.id);
    setDraftVersion(latest.trip.draft_version);
    setSourcesChanged(false);
  }

  function openEditor(editor: CriticalEditor) {
    if (!intent) return;
    const datePolicy = intent.envelope.formal_contract.date_policy;
    const formal = intent.envelope.formal_contract;
    setEditorError(null);
    setActiveEditor(editor);
    setFormDraft({
      city: formal.destinations[0]?.city_name ?? "",
      startDate: datePolicy?.start_date ?? "",
      endDate: datePolicy?.end_date ?? "",
      tripDays: datePolicy?.trip_days ? String(datePolicy.trip_days) : "",
      timeMode: datePolicy?.start_date && datePolicy?.end_date ? "dates" : "days",
      pace: formal.pace?.value ?? "relaxed",
    });
  }

  function closeEditor() {
    if (pendingEdit) return;
    setActiveEditor(null);
    setFormDraft(null);
    setEditorError(null);
  }

  function currentBase() {
    if (!intent || draftVersion === null) return null;
    return { base_intent_revision_id: intent.revision.id, base_draft_version: draftVersion };
  }

  async function submitPending(request: PendingDraftIntentRequest) {
    setPendingEdit(request);
    setEditorError(null);
    const result = await postTripJson<DraftIntentEditResponse>(
      request.endpoint,
      request.payload,
      "暂时无法保存这项修改。",
      "网络连接失败，你的修改还在这里。",
      { headers: { "X-Idempotency-Key": request.idempotencyKey } },
    );
    if (result.ok) {
      setIntent({ envelope: result.data.envelope, revision: result.data.revision });
      setLatestIntentRevisionId(result.data.revision.id);
      setDraftVersion(result.data.draft_version);
      setSourcesChanged(false);
      setPendingEdit(null);
      setRetryableRequest(null);
      setActiveEditor(null);
      setFormDraft(null);
      setStaleConflict(null);
      setFeedback({
        tone: "info",
        message: result.data.idempotent_replay
          ? "已确认这项修改已经保存。"
          : result.data.changed
            ? "已更新行程信息。"
            : "最新信息已经包含这项修改。",
      });
      if (request.restoreFocusAfterSuccess) setRestorePrimaryFocus(true);
      return;
    }
    if (result.code === "stale_draft_revision" || result.code === "stale_intent_revision") {
      const latest = await refreshLatestIntent();
      if (latest) {
        setStaleConflict({
          attempted: request,
          originalBaseDraftVersion: request.payload.base_draft_version,
          originalBaseIntentRevisionId: request.payload.base_intent_revision_id,
          latest,
        });
      }
      setPendingEdit(null);
      setRetryableRequest(null);
      setEditorError("行程信息已经在其他页面更新。你的修改仍保留在这里。");
      return;
    }
    setPendingEdit(null);
    setRetryableRequest(result.code ? null : request);
    setEditorError(result.code ? userFacingEditError(result.code) : "网络连接失败，你的修改还在这里。");
  }

  function saveEditor() {
    const base = currentBase();
    if (!base || !activeEditor || !formDraft) return;
    const operation = operationForEditor(activeEditor, formDraft);
    if (!operation) {
      setEditorError("请完整填写这项信息后再保存。");
      return;
    }
    void submitPending({
      endpoint: TRIP_API_ENDPOINTS.editPrePlanIntent(tripId),
      payload: { ...base, operations: [operation] },
      idempotencyKey: createIdempotencyKey("draft-edit"),
      operation,
      formDraft,
    });
  }

  function resolveClarification(questionId: string, answer: DraftClarificationAnswer, draft: CriticalIntentFormDraft) {
    const base = currentBase();
    if (!base) return;
    const operation = operationForClarification(answer);
    void submitPending({
      endpoint: TRIP_API_ENDPOINTS.resolvePrePlanIntentClarification(tripId, questionId),
      payload: { ...base, answer },
      idempotencyKey: createIdempotencyKey("draft-clarification"),
      operation,
      formDraft: draft,
      clarificationId: questionId,
    });
  }

  function retryNetworkRequest() {
    if (pendingEdit || !retryableRequest) return;
    void submitPending(retryableRequest);
  }

  function reapplyStaleEdit() {
    if (!staleConflict) return;
    const current = staleConflict.latest;
    if (operationAlreadyApplied(current.envelope, staleConflict.attempted.operation)) {
      setStaleConflict(null);
      setFeedback({ tone: "info", message: "最新内容已经包含这项修改。" });
      return;
    }
    const retry = {
      ...staleConflict.attempted,
      idempotencyKey: createIdempotencyKey("draft-reapply"),
      payload: withLatestBase(staleConflict.attempted.payload, current),
      restoreFocusAfterSuccess: true,
    };
    void submitPending(retry);
  }

  async function buildPreview() {
    if (!intent || !view?.canGeneratePreview || sourcesChanged) return;
    setOperation("previewing");
    setFeedback({ tone: "info", message: "正在生成第一版路线预览……" });
    const result = await postTripJson<PreviewResponse>(
      TRIP_API_ENDPOINTS.previewPrePlanHandoff(tripId),
      { draft_intent_revision_id: intent.revision.id },
      "暂时无法生成路线预览，你确认的信息已经保留。",
      "服务暂时不可用，你确认的信息不会丢失。",
    );
    setOperation("idle");
    if (!result.ok) {
      setFeedback({ tone: "error", message: userFacingRequestError(result.code, "暂时无法生成路线预览，你确认的信息已经保留。", result.context) });
      return;
    }
    setPreview(result.data);
    setFeedback({ tone: "info", message: "第一版路线已准备好，请确认后生成正式行程。" });
  }

  async function apply() {
    if (!intent || !preview || sourcesChanged || !previewStatus?.canApply) return;
    setOperation("applying");
    setFeedback({ tone: "info", message: "正在保存第一版行程……" });
    const result = await postTripJson<ApplyResponse>(
      TRIP_API_ENDPOINTS.applyPrePlanHandoff(tripId, preview.handoff.id),
      { draft_intent_revision_id: preview.draft_intent_revision_id, handoff_digest: preview.handoff.trace_digest },
      "暂时无法保存行程，你确认的信息已经保留。",
      "服务暂时不可用，你确认的信息不会丢失。",
      { headers: { "X-Idempotency-Key": `draft-handoff:${preview.handoff.id}:${preview.handoff.trace_digest.slice(0, 16)}` } },
    );
    setOperation("idle");
    if (!result.ok) {
      if (result.code === "stale_intent_revision") {
        await refreshLatestIntent();
      }
      setFeedback({ tone: "error", message: userFacingPrePlanHandoffError(result.code) ?? userFacingRequestError(result.code, "暂时无法保存行程，你确认的信息已经保留。") });
      return;
    }
    onApplied(result.data);
  }

  function selectCandidate(candidateId: string, checked: boolean) {
    setSelectedCandidateIds((current) => checked ? [...current, candidateId] : current.filter((id) => id !== candidateId));
    setSourcesChanged(true);
    setPreview(null);
    setFeedback({ tone: "info", message: "已更新导入资料；重新整理后会纳入行程信息。" });
  }

  const primaryLabel = previewStatus?.kind === "stale" ? "重新生成路线预览" : preview ? "确认并生成行程" : "生成路线预览";
  const primaryDisabled = busy || (previewStatus?.canApply ? !canApplyPreview : !canGeneratePreview);
  const primaryHint = sourcesChanged
    ? "导入资料已更新，请先重新整理旅行信息。"
    : previewStatus?.kind === "stale"
      ? previewStatus.message
    : previewHasExecutionConflict
      ? "这版路线仍有执行冲突，请先返回修改旅行信息后再生成。"
    : view?.actionHint ?? "正在整理你的旅行需求。";

  return (
    <main className="uc-intent-shell" data-preplan-intent-workspace="true">
      <header className="uc-intent-header">
        <p className="uc-intent-eyebrow">旅行计划</p>
        <h1>确认行程信息</h1>
        <p>确认几个关键信息后，我们会为你生成第一版行程。</p>
      </header>

      {bootstrap === "compiling" || bootstrap === "idle" ? <LoadingState /> : null}
      {bootstrap === "failed" ? <RetryState onRetry={() => void compileIntent()} /> : null}

      {view && intent ? <>
        <section className="uc-intent-card" aria-label="行程概览">
          <div className="uc-intent-section-heading"><div><p>行程概览</p><h2>{view.heading}</h2></div><span className={view.canGeneratePreview ? "uc-intent-status uc-intent-status--ready" : "uc-intent-status uc-intent-status--blocked"}>{view.canGeneratePreview ? "可以开始规划" : "还需要补充"}</span></div>
          <div className="uc-intent-summary">{view.summary.map((item) => <EditableSummaryItem key={item.label} label={item.label} value={item.value} editable={summaryEditor(item.label)} onEdit={openEditor} disabled={busy || draftVersion === null} />)}</div>
          {activeEditor && formDraft ? <CriticalEditorForm editor={activeEditor} draft={formDraft} pending={Boolean(pendingEdit)} error={editorError} onChange={setFormDraft} onSave={saveEditor} onCancel={closeEditor} /> : null}
        </section>

        {view.blockers.length ? <section className="uc-intent-card uc-intent-card--attention" aria-label="还需要你补充"><div className="uc-intent-section-heading"><div><p>还需要你补充</p><h2>确认后才能生成路线</h2></div></div><div className="uc-intent-list">{intent.envelope.clarification_queue.filter((question) => question.blocking).length ? intent.envelope.clarification_queue.filter((question) => question.blocking).map((question) => <ClarificationCard key={question.question_id} question={question} pending={Boolean(pendingEdit)} onResolve={resolveClarification} />) : view.blockers.map((blocker) => <article key={blocker.title}><strong>{blocker.title}</strong><span>{blocker.detail}</span></article>)}</div></section> : null}

        <FixedArrangementSummary arrangements={view.fixedArrangements} />
        <PlacePreferenceSummary envelope={intent.envelope} sourceLines={view.sourceLines} />

        {view.assumptions.length ? <details className="uc-intent-card uc-intent-details"><summary><span><strong>系统暂时这样理解</strong><small>{view.assumptions.length} 项暂定设置</small></span><span aria-hidden="true">展开</span></summary><div className="uc-intent-list">{view.assumptions.map((item) => <article key={item.title}><strong>{item.title}</strong><span>{item.detail}</span></article>)}</div></details> : null}

        <details className="uc-intent-card uc-intent-details"><summary><span><strong>查看依据</strong><small>按需查看输入和导入资料</small></span><span aria-hidden="true">展开</span></summary><SourceDetails directUserText={directUserText} sourceLines={view.sourceLines} candidates={candidates} selectedCandidateIds={selectedCandidateIds} onSelectCandidate={selectCandidate} onRefresh={() => void compileIntent()} onImportChanged={() => { void refreshCandidates(); setSourcesChanged(true); setPreview(null); setFeedback({ tone: "info", message: "已更新导入资料；重新整理后会纳入行程信息。" }); }} busy={busy} tripId={tripId} /></details>
      </> : null}

      {preview && previewStatus ? <><PrePlanHandoffStatusPanel status={previewStatus} currentRevisionNumber={intent?.revision.revision_number ?? null} />{reviewSummary ? <PlannerTraceReviewPanel summary={reviewSummary} /> : null}<ExecutableRoutePreview itinerary={preview.itinerary} variant="draft" /></> : null}

      {staleConflict ? <StaleConflictPanel conflict={staleConflict} onViewLatest={() => { setFeedback({ tone: "info", message: "已显示最新行程信息；你的修改仍保留，可以重新应用。" }); }} onReapply={reapplyStaleEdit} onDiscard={() => { setStaleConflict(null); setActiveEditor(null); setFormDraft(null); setEditorError(null); setRestorePrimaryFocus(true); }} disabled={Boolean(pendingEdit)} /> : null}

      {feedback ? <p role={feedback.tone === "error" ? "alert" : "status"} className={feedback.tone === "error" ? "uc-intent-feedback uc-intent-feedback--error" : "uc-intent-feedback"}>{feedback.message}</p> : null}
      {retryableRequest && editorError ? <button type="button" className="uc-intent-secondary" onClick={retryNetworkRequest} disabled={Boolean(pendingEdit)}>重新提交</button> : null}

      {view ? <footer className="uc-intent-actions"><button type="button" className="uc-intent-secondary" onClick={onCancel} disabled={busy}>返回修改需求</button><div><p>{primaryHint}</p><button id="preplan-primary-action" type="button" className="uc-intent-primary" onClick={() => { if (previewStatus?.canApply) void apply(); else void buildPreview(); }} disabled={primaryDisabled}>{operation === "previewing" ? "正在生成预览……" : operation === "applying" ? "正在保存行程……" : primaryLabel}</button></div></footer> : null}
    </main>
  );
}

function LoadingState() {
  return <section className="uc-intent-card uc-intent-loading" aria-live="polite"><strong>正在整理你的旅行需求……</strong><span>很快会把重要信息整理成一份可确认的行程概览。</span></section>;
}

function RetryState({ onRetry }: { onRetry: () => void }) {
  return <section className="uc-intent-card uc-intent-card--attention" role="alert"><strong>暂时无法整理旅行信息，你的输入已经保留。</strong><span>服务恢复后可以重新识别，无需重新填写。</span><button type="button" className="uc-intent-secondary" onClick={onRetry}>重新识别</button></section>;
}

function PrePlanHandoffStatusPanel({ status, currentRevisionNumber }: { status: ReturnType<typeof buildPrePlanHandoffStatus>; currentRevisionNumber: number | null }) {
  if (status.kind === "current") return <section className="uc-intent-card" data-preplan-handoff-status="current"><strong>路线预览对应当前草稿</strong><span>{currentRevisionNumber ? `这份预览基于当前第 ${currentRevisionNumber} 版行程信息，可以确认后生成正式行程。` : status.message}</span></section>;
  return <section className="uc-intent-card uc-intent-card--attention" data-preplan-handoff-status="stale" role="status"><strong>路线预览已过期</strong><span>{currentRevisionNumber ? `行程信息已更新为第 ${currentRevisionNumber} 版；旧预览不能保存。请重新生成路线预览。` : status.message}</span></section>;
}

function FixedArrangementSummary({ arrangements }: { arrangements: Array<{ title: string; detail: string }> }) {
  return <section className="uc-intent-card"><div className="uc-intent-section-heading"><div><p>固定安排</p><h2>{arrangements.length ? `${arrangements.length} 个已安排` : "暂时没有固定安排"}</h2></div></div>{arrangements.length ? <div className="uc-intent-list">{arrangements.map((arrangement, index) => <article key={`${arrangement.title}-${index}`}><strong>{arrangement.title}</strong><span>{arrangement.detail}</span></article>)}</div> : <p className="uc-intent-muted">之后有预约、演出或见面安排时，可以在修改需求中补充。</p>}</section>;
}

function PlacePreferenceSummary({ envelope, sourceLines }: { envelope: SourceLinkedTripIntentEnvelope; sourceLines: Array<{ label: string; source: string }> }) {
  const places = envelope.formal_contract.must_visit_places;
  return <section className="uc-intent-card"><div className="uc-intent-section-heading"><div><p>想去的地方</p><h2>{places.length ? "一定想去" : "暂未指定"}</h2></div></div>{places.length ? <div className="uc-intent-place-list">{places.map((place) => <div key={place.trip_candidate_id}><strong>{place.display_name ?? "已确认地点"}</strong><span>来自：{sourceForField(sourceLines, "想去的地方")}</span></div>)}</div> : <p className="uc-intent-muted">还没有确认可排入路线的地点；补充一个想去的地点或固定安排地点后再继续。</p>}</section>;
}

function SourceDetails({ directUserText, sourceLines, candidates, selectedCandidateIds, onSelectCandidate, onRefresh, onImportChanged, busy, tripId }: { directUserText: string; sourceLines: Array<{ label: string; source: string }>; candidates: CandidateListResponse["candidates"]; selectedCandidateIds: string[]; onSelectCandidate: (id: string, checked: boolean) => void; onRefresh: () => void; onImportChanged: () => void; busy: boolean; tripId: string }) {
  return <div className="uc-intent-details-body"><div><strong>这份行程信息来自</strong>{sourceLines.length ? <div className="uc-intent-source-list">{sourceLines.map((item) => <p key={item.label}>{item.label}<span>{item.source}</span></p>)}</div> : <p className="uc-intent-muted">目前主要依据你的输入整理。</p>}</div><details><summary>查看原始需求</summary><p className="uc-intent-raw-text">{directUserText}</p></details>{candidates.length ? <div><strong>从导入资料补充地点</strong><div className="uc-intent-candidate-list">{candidates.map((candidate) => <label key={candidate.id}><input type="checkbox" checked={selectedCandidateIds.includes(candidate.id)} onChange={(event) => onSelectCandidate(candidate.id, event.target.checked)} />{candidate.display_name}</label>)}</div><button type="button" className="uc-intent-secondary" onClick={onRefresh} disabled={busy}>重新整理旅行信息</button></div> : null}<details><summary>添加或审核导入资料</summary><ImportReviewWorkspace tripPersistence={{ status: "draft", tripId }} onCandidatesChanged={onImportChanged} /></details></div>;
}

function sourceForField(lines: Array<{ label: string; source: string }>, label: string): string {
  return lines.find((line) => line.label === label)?.source ?? "已确认信息";
}

function userFacingRequestError(code?: string, fallback = "暂时无法整理旅行信息，你的输入已经保留。", context?: Record<string, unknown>): string {
  if (code === "stale_intent_revision" || code === "stale_base_revision") return "行程信息已经在其他页面更新，请返回后重新进入确认页面。";
  if (code === "intent_parser_unavailable" || code === "intent_parser_timeout" || code === "intent_parser_invalid_output") return "部分内容未能自动识别，请检查关键信息。";
  if (code === "planner_handoff_blocked" && context?.reason_code === "fixed_event_identity_not_verified") return "固定安排的地点还没有确认，暂时不能把它排进可执行路线。请返回修改需求，补充预约地点或从导入资料中确认该地点。";
  return fallback;
}

function summaryEditor(label: string): CriticalEditor | null {
  if (label === "目的地") return "destination";
  if (label === "旅行时间") return "date_policy";
  if (label === "旅行节奏") return "pace";
  return null;
}

function EditableSummaryItem({ label, value, editable, onEdit, disabled }: { label: string; value: string; editable: CriticalEditor | null; onEdit: (editor: CriticalEditor) => void; disabled: boolean }) {
  return <div><span>{label}</span><strong>{value}</strong>{editable ? <button type="button" aria-label={`修改${label}`} className="uc-intent-text-action" onClick={() => onEdit(editable)} disabled={disabled}>修改</button> : null}</div>;
}

function CriticalEditorForm({ editor, draft, pending, error, onChange, onSave, onCancel }: { editor: CriticalEditor; draft: CriticalIntentFormDraft; pending: boolean; error: string | null; onChange: (value: CriticalIntentFormDraft) => void; onSave: () => void; onCancel: () => void }) {
  const title = { destination: "修改目的地", date_policy: "修改旅行日期", trip_days: "修改旅行天数", pace: "修改旅行节奏" }[editor];
  return <form className="uc-intent-editor" onSubmit={(event) => { event.preventDefault(); onSave(); }}><strong>{title}</strong>
    {editor === "destination" ? <label>目的地<input autoFocus value={draft.city ?? ""} onChange={(event) => onChange({ ...draft, city: event.target.value })} placeholder="例如：杭州" disabled={pending} /></label> : null}
    {editor === "date_policy" ? <><div className="uc-intent-choice"><button type="button" className={draft.timeMode === "dates" ? "is-selected" : ""} onClick={() => onChange({ ...draft, timeMode: "dates" })} disabled={pending}>按具体日期</button><button type="button" className={draft.timeMode === "days" ? "is-selected" : ""} onClick={() => onChange({ ...draft, timeMode: "days" })} disabled={pending}>按旅行天数</button></div>{draft.timeMode === "days" ? <label>旅行天数<input inputMode="numeric" type="number" min="1" max="60" value={draft.tripDays ?? ""} onChange={(event) => onChange({ ...draft, tripDays: event.target.value })} disabled={pending} /></label> : <div className="uc-intent-editor-grid"><label>开始日期<input type="date" value={draft.startDate ?? ""} onChange={(event) => onChange({ ...draft, startDate: event.target.value })} disabled={pending} /></label><label>结束日期<input type="date" value={draft.endDate ?? ""} onChange={(event) => onChange({ ...draft, endDate: event.target.value })} disabled={pending} /></label></div>}</> : null}
    {editor === "trip_days" ? <label>旅行天数<input autoFocus inputMode="numeric" type="number" min="1" max="60" value={draft.tripDays ?? ""} onChange={(event) => onChange({ ...draft, tripDays: event.target.value })} disabled={pending} /></label> : null}
    {editor === "pace" ? <label>旅行节奏<select value={draft.pace ?? "relaxed"} onChange={(event) => onChange({ ...draft, pace: event.target.value as CriticalIntentFormDraft["pace"] })} disabled={pending}><option value="relaxed">轻松</option><option value="balanced">适中</option><option value="intensive">紧凑</option></select></label> : null}
    {error ? <p className="uc-intent-feedback uc-intent-feedback--error" role="alert">{error}</p> : null}
    <div className="uc-intent-editor-actions"><button type="button" className="uc-intent-secondary" onClick={onCancel} disabled={pending}>取消</button><button type="submit" className="uc-intent-primary" disabled={pending}>{pending ? "正在保存……" : "保存修改"}</button></div>
  </form>;
}

function ClarificationCard({ question, pending, onResolve }: { question: IntentClarification; pending: boolean; onResolve: (id: string, answer: DraftClarificationAnswer, draft: CriticalIntentFormDraft) => void }) {
  const [draft, setDraft] = useState<CriticalIntentFormDraft>({});
  const [error, setError] = useState<string | null>(null);
  const kind = getPrePlanClarificationControl(question);
  if (!kind) return <article><strong>还需要确认一项信息</strong><span>{question.question}</span><button type="button" className="uc-intent-secondary">返回修改需求</button></article>;
  const submit = () => {
    const answer = clarificationAnswerForKind(kind, draft);
    if (!answer) { setError("请完整填写这项信息后再确认。"); return; }
    setError(null);
    onResolve(question.question_id, answer, draft);
  };
  return <article className="uc-intent-clarification"><strong>{clarificationTitle(kind)}</strong><span>{clarificationDetail(kind)}</span>
    {kind === "destination" ? <label>目的地<input value={draft.city ?? ""} onChange={(event) => setDraft({ ...draft, city: event.target.value })} placeholder="例如：杭州" disabled={pending} /></label> : null}
    {kind === "trip_days" ? <><label>旅行天数<input inputMode="numeric" type="number" min="1" max="60" value={draft.tripDays ?? ""} onChange={(event) => setDraft({ ...draft, tripDays: event.target.value })} disabled={pending} /></label><span>也可以改为填写具体日期。</span></> : null}
    {kind === "pace" ? <label>旅行节奏<select value={draft.pace ?? "relaxed"} onChange={(event) => setDraft({ ...draft, pace: event.target.value as CriticalIntentFormDraft["pace"] })} disabled={pending}><option value="relaxed">轻松</option><option value="balanced">适中</option><option value="intensive">紧凑</option></select></label> : null}
    {kind === "date_range" ? <div className="uc-intent-editor-grid"><label>开始日期<input type="date" value={draft.startDate ?? ""} onChange={(event) => setDraft({ ...draft, startDate: event.target.value })} disabled={pending} /></label><label>结束日期<input type="date" value={draft.endDate ?? ""} onChange={(event) => setDraft({ ...draft, endDate: event.target.value })} disabled={pending} /></label></div> : null}
    {kind === "date_choice" ? <><label>以什么为准<select value={draft.startDate ? "date_range" : "trip_days"} onChange={(event) => setDraft({ ...draft, startDate: event.target.value === "date_range" ? draft.startDate : "" })} disabled={pending}><option value="trip_days">旅行天数</option><option value="date_range">具体日期</option></select></label>{draft.startDate !== "" ? <div className="uc-intent-editor-grid"><label>开始日期<input type="date" value={draft.startDate ?? ""} onChange={(event) => setDraft({ ...draft, startDate: event.target.value })} disabled={pending} /></label><label>结束日期<input type="date" value={draft.endDate ?? ""} onChange={(event) => setDraft({ ...draft, endDate: event.target.value })} disabled={pending} /></label></div> : <label>旅行天数<input type="number" min="1" max="60" value={draft.tripDays ?? ""} onChange={(event) => setDraft({ ...draft, tripDays: event.target.value })} disabled={pending} /></label>}</> : null}
    {error ? <p className="uc-intent-feedback uc-intent-feedback--error" role="alert">{error}</p> : null}
    <button type="button" className="uc-intent-secondary" onClick={submit} disabled={pending}>{pending ? "正在保存……" : "确认"}</button>
  </article>;
}

function StaleConflictPanel({ conflict, onViewLatest, onReapply, onDiscard, disabled }: { conflict: DraftIntentStaleConflict; onViewLatest: () => void; onReapply: () => void; onDiscard: () => void; disabled: boolean }) {
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => { panelRef.current?.focus(); }, []);
  const latest = semanticSummary(conflict.latest.envelope);
  const yours = attemptedSummary(conflict.attempted);
  return <section ref={panelRef} className="uc-intent-card uc-intent-card--attention" role="dialog" aria-modal="true" aria-labelledby="draft-stale-conflict-title" tabIndex={-1}><h2 id="draft-stale-conflict-title">行程信息已经在其他页面更新</h2><span>我们没有自动覆盖最新内容。请先比较，再决定是否重新应用你的修改。</span><div className="uc-intent-stale-diff"><p><b>最新内容</b>{latest}</p><p><b>你的修改</b>{yours}</p></div><div className="uc-intent-editor-actions"><button type="button" className="uc-intent-secondary" onClick={onViewLatest} disabled={disabled}>查看最新内容</button><button type="button" className="uc-intent-secondary" onClick={onDiscard} disabled={disabled}>放弃本次修改</button><button type="button" className="uc-intent-primary" onClick={onReapply} disabled={disabled}>重新应用我的修改</button></div></section>;
}

function operationForEditor(editor: CriticalEditor, draft: CriticalIntentFormDraft): DraftIntentEditOperation | null {
  if (editor === "destination") return draft.city?.trim() ? { operation: "update_destination", city: draft.city.trim() } : null;
  if (editor === "date_policy") { if (draft.timeMode === "days") { const trip_days = Number(draft.tripDays); return Number.isInteger(trip_days) && trip_days > 0 ? { operation: "update_trip_days", trip_days } : null; } return draft.startDate && draft.endDate ? { operation: "update_date_policy", start_date: draft.startDate, end_date: draft.endDate, timezone: "Asia/Shanghai" } : null; }
  if (editor === "trip_days") { const trip_days = Number(draft.tripDays); return Number.isInteger(trip_days) && trip_days > 0 ? { operation: "update_trip_days", trip_days } : null; }
  return draft.pace ? { operation: "update_pace", pace: draft.pace } : null;
}

function clarificationTitle(kind: PrePlanClarificationControl): string { return { destination: "请填写这次旅行的目的地", trip_days: "请填写旅行日期或天数", pace: "请确认旅行节奏", date_range: "请确认具体出发日期", date_choice: "请确认旅行日期或天数" }[kind]; }
function clarificationDetail(kind: PrePlanClarificationControl): string { return { destination: "目的地决定路线范围和可安排的地点。", trip_days: "我们需要知道可用于安排行程的时间。", pace: "旅行节奏会影响每天的安排密度。", date_range: "相对日期需要一个明确的日历参考。", date_choice: "请调整旅行日期或天数，让固定安排能安全纳入路线。" }[kind]; }
function clarificationAnswerForKind(kind: PrePlanClarificationControl, draft: CriticalIntentFormDraft): DraftClarificationAnswer | null {
  if (kind === "destination" && draft.city?.trim()) return { answer_type: "destination", city: draft.city.trim() };
  if (kind === "trip_days") { const trip_days = Number(draft.tripDays); return Number.isInteger(trip_days) && trip_days > 0 ? { answer_type: "trip_days", trip_days } : null; }
  if (kind === "pace" && draft.pace) return { answer_type: "pace", pace: draft.pace };
  if (kind === "date_range" && draft.startDate && draft.endDate) return { answer_type: "date_range", start_date: draft.startDate, end_date: draft.endDate, timezone: "Asia/Shanghai" };
  if (kind === "date_choice") { if (draft.startDate && draft.endDate) return { answer_type: "date_policy_choice", policy: "date_range", start_date: draft.startDate, end_date: draft.endDate, timezone: "Asia/Shanghai" }; const trip_days = Number(draft.tripDays); return Number.isInteger(trip_days) && trip_days > 0 ? { answer_type: "date_policy_choice", policy: "trip_days", trip_days } : null; }
  return null;
}

function operationForClarification(answer: DraftClarificationAnswer): DraftIntentEditOperation {
  if (answer.answer_type === "destination") return { operation: "update_destination", city: answer.city, timezone: answer.timezone };
  if (answer.answer_type === "trip_days") return { operation: "update_trip_days", trip_days: answer.trip_days };
  if (answer.answer_type === "pace") return { operation: "update_pace", pace: answer.pace };
  if (answer.answer_type === "date_range") return { operation: "update_date_policy", start_date: answer.start_date, end_date: answer.end_date, timezone: answer.timezone };
  return answer.policy === "trip_days" ? { operation: "update_trip_days", trip_days: answer.trip_days } : { operation: "update_date_policy", start_date: answer.start_date, end_date: answer.end_date, timezone: answer.timezone };
}

function withLatestBase(payload: DraftIntentEditRequest | DraftClarificationResolveRequest, latest: LatestPrePlanIntentResponse): DraftIntentEditRequest | DraftClarificationResolveRequest { return { ...payload, base_intent_revision_id: latest.revision.id, base_draft_version: latest.trip.draft_version }; }
function operationAlreadyApplied(envelope: SourceLinkedTripIntentEnvelope, operation: DraftIntentEditOperation): boolean { const date = envelope.formal_contract.date_policy; if (operation.operation === "update_destination") return envelope.formal_contract.destinations[0]?.city_name === operation.city; if (operation.operation === "update_trip_days") return date?.trip_days === operation.trip_days; if (operation.operation === "update_date_policy") return date?.start_date === operation.start_date && date?.end_date === operation.end_date; if (operation.operation === "update_pace") return envelope.formal_contract.pace?.value === operation.pace; return false; }
function semanticSummary(envelope: SourceLinkedTripIntentEnvelope): string { const date = envelope.formal_contract.date_policy; return [envelope.formal_contract.destinations[0]?.city_name, date?.start_date && date.end_date ? `${date.start_date} 至 ${date.end_date}` : date?.trip_days ? `${date.trip_days} 天` : null, envelope.formal_contract.pace?.value === "relaxed" ? "轻松" : envelope.formal_contract.pace?.value === "balanced" ? "适中" : envelope.formal_contract.pace?.value === "intensive" ? "紧凑" : null].filter(Boolean).join("，") || "尚未补全"; }
function attemptedSummary(request: PendingDraftIntentRequest): string { const operation = request.operation; if (operation.operation === "update_destination") return `目的地：${operation.city}`; if (operation.operation === "update_trip_days") return `旅行天数：${operation.trip_days} 天`; if (operation.operation === "update_date_policy") return `旅行日期：${operation.start_date ?? ""} 至 ${operation.end_date ?? ""}`; if (operation.operation === "update_pace") return `旅行节奏：${operation.pace === "relaxed" ? "轻松" : operation.pace === "balanced" ? "适中" : "紧凑"}`; return "你刚才的修改"; }
function userFacingEditError(code: string): string { if (code === "invalid_intent_edit") return "日期和天数不一致，请检查后再保存。"; if (code === "clarification_already_resolved") return "这项信息已经在其他页面完成确认。"; return "暂时无法保存这项修改，请检查输入后再试。"; }
function createIdempotencyKey(prefix: string): string { return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" ? `${prefix}:${crypto.randomUUID()}` : `${prefix}:${Date.now().toString(36)}:${Math.random().toString(36).slice(2)}`; }
