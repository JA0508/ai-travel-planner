"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { getTripJson, postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import { ImportReviewWorkspace } from "@/features/imports/ImportReviewWorkspace";
import type { SourceLinkedTripIntentEnvelope } from "@/features/intent-confirmation/intentTypes";
import { buildPrePlanConfirmationViewModel } from "./prePlanConfirmationModel";
import type { TripMetadata, TripRevisionMetadata } from "@/features/trip-workspace/tripPersistence";

type ItineraryResponse = any;

type DraftIntentResponse = {
  envelope: SourceLinkedTripIntentEnvelope;
  revision: { id: string; revision_number: number };
};

type PreviewResponse = {
  handoff: { id: string; trace_digest: string };
  itinerary: ItineraryResponse;
};

type ApplyResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  itinerary: ItineraryResponse;
};

type CandidateListResponse = {
  candidates: Array<{ id: string; display_name: string; workflow_state: string }>;
};

type BootstrapState = "idle" | "compiling" | "ready" | "failed";
type Feedback = { tone: "info" | "error"; message: string } | null;

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
  const [sourcesChanged, setSourcesChanged] = useState(false);
  const autoCompileTripRef = useRef<string | null>(null);
  const compileInFlightRef = useRef(false);

  const view = useMemo(
    () => (intent ? buildPrePlanConfirmationViewModel(intent.envelope) : null),
    [intent],
  );
  const busy = bootstrap === "compiling" || operation !== "idle";
  const canGeneratePreview = Boolean(view?.canGeneratePreview && !sourcesChanged && !preview);
  const canApplyPreview = Boolean(preview && intent && !sourcesChanged);

  useEffect(() => {
    void refreshCandidates();
  }, [tripId]);

  useEffect(() => {
    if (autoCompileTripRef.current === tripId || compileInFlightRef.current) return;
    autoCompileTripRef.current = tripId;
    void compileIntent();
  }, [tripId]);

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
    setPreview(null);
    setSourcesChanged(false);
    setBootstrap("ready");
    setFeedback(null);
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
      setFeedback({ tone: "error", message: userFacingRequestError(result.code, "暂时无法生成路线预览，你确认的信息已经保留。") });
      return;
    }
    setPreview(result.data);
    setFeedback({ tone: "info", message: "第一版路线已准备好，请确认后生成正式行程。" });
  }

  async function apply() {
    if (!intent || !preview || sourcesChanged) return;
    setOperation("applying");
    setFeedback({ tone: "info", message: "正在保存第一版行程……" });
    const result = await postTripJson<ApplyResponse>(
      TRIP_API_ENDPOINTS.applyPrePlanHandoff(tripId, preview.handoff.id),
      { draft_intent_revision_id: intent.revision.id, handoff_digest: preview.handoff.trace_digest },
      "暂时无法保存行程，你确认的信息已经保留。",
      "服务暂时不可用，你确认的信息不会丢失。",
      { headers: { "X-Idempotency-Key": `draft-handoff:${preview.handoff.id}:${preview.handoff.trace_digest.slice(0, 16)}` } },
    );
    setOperation("idle");
    if (!result.ok) {
      setFeedback({ tone: "error", message: userFacingRequestError(result.code, "暂时无法保存行程，你确认的信息已经保留。") });
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

  const primaryLabel = preview ? "确认并生成行程" : "生成路线预览";
  const primaryDisabled = busy || (!preview && !canGeneratePreview) || (Boolean(preview) && !canApplyPreview);
  const primaryHint = sourcesChanged
    ? "导入资料已更新，请先重新整理旅行信息。"
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
          <div className="uc-intent-summary">{view.summary.map((item) => <div key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}</div>
        </section>

        {view.blockers.length ? <section className="uc-intent-card uc-intent-card--attention" aria-label="还需要你补充"><div className="uc-intent-section-heading"><div><p>还需要你补充</p><h2>确认后才能生成路线</h2></div></div><div className="uc-intent-list">{view.blockers.map((item) => <article key={item.title}><strong>{item.title}</strong><span>{item.detail}</span></article>)}</div></section> : null}

        <FixedArrangementSummary arrangements={view.fixedArrangements} />
        <PlacePreferenceSummary envelope={intent.envelope} sourceLines={view.sourceLines} />

        {view.assumptions.length ? <details className="uc-intent-card uc-intent-details"><summary><span><strong>系统暂时这样理解</strong><small>{view.assumptions.length} 项暂定设置</small></span><span aria-hidden="true">展开</span></summary><div className="uc-intent-list">{view.assumptions.map((item) => <article key={item.title}><strong>{item.title}</strong><span>{item.detail}</span></article>)}</div></details> : null}

        <details className="uc-intent-card uc-intent-details"><summary><span><strong>查看依据</strong><small>按需查看输入和导入资料</small></span><span aria-hidden="true">展开</span></summary><SourceDetails directUserText={directUserText} sourceLines={view.sourceLines} candidates={candidates} selectedCandidateIds={selectedCandidateIds} onSelectCandidate={selectCandidate} onRefresh={() => void compileIntent()} onImportChanged={() => { void refreshCandidates(); setSourcesChanged(true); setPreview(null); setFeedback({ tone: "info", message: "已更新导入资料；重新整理后会纳入行程信息。" }); }} busy={busy} tripId={tripId} /></details>
      </> : null}

      {preview ? <RoutePreviewSummary preview={preview} /> : null}

      {feedback ? <p role={feedback.tone === "error" ? "alert" : "status"} className={feedback.tone === "error" ? "uc-intent-feedback uc-intent-feedback--error" : "uc-intent-feedback"}>{feedback.message}</p> : null}

      {view ? <footer className="uc-intent-actions"><button type="button" className="uc-intent-secondary" onClick={onCancel} disabled={busy}>返回修改需求</button><div><p>{primaryHint}</p><button type="button" className="uc-intent-primary" onClick={() => { if (preview) void apply(); else void buildPreview(); }} disabled={primaryDisabled}>{operation === "previewing" ? "正在生成预览……" : operation === "applying" ? "正在保存行程……" : primaryLabel}</button></div></footer> : null}
    </main>
  );
}

function LoadingState() {
  return <section className="uc-intent-card uc-intent-loading" aria-live="polite"><strong>正在整理你的旅行需求……</strong><span>很快会把重要信息整理成一份可确认的行程概览。</span></section>;
}

function RetryState({ onRetry }: { onRetry: () => void }) {
  return <section className="uc-intent-card uc-intent-card--attention" role="alert"><strong>暂时无法整理旅行信息，你的输入已经保留。</strong><span>服务恢复后可以重新识别，无需重新填写。</span><button type="button" className="uc-intent-secondary" onClick={onRetry}>重新识别</button></section>;
}

function FixedArrangementSummary({ arrangements }: { arrangements: Array<{ title: string; detail: string }> }) {
  return <section className="uc-intent-card"><div className="uc-intent-section-heading"><div><p>固定安排</p><h2>{arrangements.length ? `${arrangements.length} 个已安排` : "暂时没有固定安排"}</h2></div></div>{arrangements.length ? <div className="uc-intent-list">{arrangements.map((arrangement, index) => <article key={`${arrangement.title}-${index}`}><strong>{arrangement.title}</strong><span>{arrangement.detail}</span></article>)}</div> : <p className="uc-intent-muted">之后有预约、演出或见面安排时，可以在修改需求中补充。</p>}</section>;
}

function PlacePreferenceSummary({ envelope, sourceLines }: { envelope: SourceLinkedTripIntentEnvelope; sourceLines: Array<{ label: string; source: string }> }) {
  const places = envelope.formal_contract.must_visit_places;
  return <section className="uc-intent-card"><div className="uc-intent-section-heading"><div><p>想去的地方</p><h2>{places.length ? "一定想去" : "暂未指定"}</h2></div></div>{places.length ? <div className="uc-intent-place-list">{places.map((place) => <div key={place.trip_candidate_id}><strong>{place.display_name ?? "已确认地点"}</strong><span>来自：{sourceForField(sourceLines, "想去的地方")}</span></div>)}</div> : <p className="uc-intent-muted">还没有确定必须到达的地点，路线会先围绕你的时间和旅行节奏安排。</p>}</section>;
}

function SourceDetails({ directUserText, sourceLines, candidates, selectedCandidateIds, onSelectCandidate, onRefresh, onImportChanged, busy, tripId }: { directUserText: string; sourceLines: Array<{ label: string; source: string }>; candidates: CandidateListResponse["candidates"]; selectedCandidateIds: string[]; onSelectCandidate: (id: string, checked: boolean) => void; onRefresh: () => void; onImportChanged: () => void; busy: boolean; tripId: string }) {
  return <div className="uc-intent-details-body"><div><strong>这份行程信息来自</strong>{sourceLines.length ? <div className="uc-intent-source-list">{sourceLines.map((item) => <p key={item.label}>{item.label}<span>{item.source}</span></p>)}</div> : <p className="uc-intent-muted">目前主要依据你的输入整理。</p>}</div><details><summary>查看原始需求</summary><p className="uc-intent-raw-text">{directUserText}</p></details>{candidates.length ? <div><strong>从导入资料补充地点</strong><div className="uc-intent-candidate-list">{candidates.map((candidate) => <label key={candidate.id}><input type="checkbox" checked={selectedCandidateIds.includes(candidate.id)} onChange={(event) => onSelectCandidate(candidate.id, event.target.checked)} />{candidate.display_name}</label>)}</div><button type="button" className="uc-intent-secondary" onClick={onRefresh} disabled={busy}>重新整理旅行信息</button></div> : null}<details><summary>添加或审核导入资料</summary><ImportReviewWorkspace tripPersistence={{ status: "draft", tripId }} onCandidatesChanged={onImportChanged} /></details></div>;
}

function RoutePreviewSummary({ preview }: { preview: PreviewResponse }) {
  const days = Array.isArray(preview.itinerary?.days) ? preview.itinerary.days : [];
  return <section className="uc-intent-card" aria-label="路线预览"><div className="uc-intent-section-heading"><div><p>第一版路线预览</p><h2>确认后生成正式行程</h2></div></div><div className="uc-intent-preview-days">{days.map((day: any, index: number) => <article key={day.day ?? index}><strong>第 {day.day ?? day.day_number ?? index + 1} 天</strong><span>{Array.isArray(day.items) ? day.items.map((item: any) => item.name ?? item.title).filter(Boolean).slice(0, 4).join("、") || "待安排" : "待安排"}</span></article>)}</div></section>;
}

function sourceForField(lines: Array<{ label: string; source: string }>, label: string): string {
  return lines.find((line) => line.label === label)?.source ?? "已确认信息";
}

function userFacingRequestError(code?: string, fallback = "暂时无法整理旅行信息，你的输入已经保留。"): string {
  if (code === "stale_intent_revision" || code === "stale_base_revision") return "行程信息已经在其他页面更新，请返回后重新进入确认页面。";
  if (code === "intent_parser_unavailable" || code === "intent_parser_timeout" || code === "intent_parser_invalid_output") return "部分内容未能自动识别，请检查关键信息。";
  return fallback;
}
