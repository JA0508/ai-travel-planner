"use client";

import React, { useEffect, useState } from "react";
import { getTripJson, postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import type { TripMetadata, TripRevisionMetadata } from "@/features/trip-workspace/tripPersistence";
import { ImportReviewWorkspace } from "@/features/imports/ImportReviewWorkspace";

// The route workspace owns the rich itinerary view model. This boundary only transports
// the server-authoritative snapshot back to that owner after the first apply.
type ItineraryResponse = any;

type DraftIntentResponse = {
  envelope: { id: string; planner_ready_status: string; clarification_queue: unknown[]; formal_contract: unknown };
  revision: { id: string; revision_number: number };
};

type PreviewResponse = {
  handoff: { id: string; trace_digest: string; status: string; result_content_digest: string };
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

type Props = {
  tripId: string;
  directUserText: string;
  onApplied: (response: ApplyResponse) => void;
  onCancel: () => void;
};

export function PrePlanIntentWorkspace({ tripId, directUserText, onApplied, onCancel }: Props) {
  const [intent, setIntent] = useState<DraftIntentResponse | null>(null);
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [operation, setOperation] = useState<"idle" | "compiling" | "previewing" | "applying">("idle");
  const [candidates, setCandidates] = useState<CandidateListResponse["candidates"]>([]);
  const [selectedCandidateIds, setSelectedCandidateIds] = useState<string[]>([]);

  async function refreshCandidates() {
    const result = await getTripJson<CandidateListResponse>(
      TRIP_API_ENDPOINTS.listTripCandidates(tripId),
      "刷新审核地点失败",
    );
    if (result.ok) {
      setCandidates(result.data.candidates.filter((candidate) => candidate.workflow_state === "pending"));
    }
  }

  useEffect(() => {
    void refreshCandidates();
  }, [tripId]);

  async function compile() {
    setOperation("compiling");
    setStatus("正在编译来源可追溯的意图合同...");
    const result = await postTripJson<DraftIntentResponse>(
      TRIP_API_ENDPOINTS.compilePrePlanIntent(tripId),
      { base_trip_revision_id: null, base_intent_revision_id: intent?.revision.id ?? null, direct_user_text: directUserText, candidate_ids: selectedCandidateIds, use_llm_proposal_adapter: true },
      "编译行程意图失败",
      undefined,
      { headers: { "X-Idempotency-Key": `draft-intent:${tripId}:${intent?.revision.id ?? "root"}` } },
    );
    setOperation("idle");
    if (!result.ok) {
      setStatus(result.message);
      return;
    }
    setIntent(result.data);
    setPreview(null);
    setStatus(result.data.envelope.clarification_queue.length ? "意图合同仍有需要确认的边界。" : "意图合同已编译，可生成可执行路线预览。");
  }

  async function buildPreview() {
    if (!intent) return;
    setOperation("previewing");
    setStatus("正在根据确认的意图生成冻结预览...");
    const result = await postTripJson<PreviewResponse>(
      TRIP_API_ENDPOINTS.previewPrePlanHandoff(tripId),
      { draft_intent_revision_id: intent.revision.id },
      "生成路线预览失败",
    );
    setOperation("idle");
    if (!result.ok) {
      setStatus(result.message);
      return;
    }
    setPreview(result.data);
    setStatus("预览已冻结。确认后才会写入 Revision 1。");
  }

  async function apply() {
    if (!intent || !preview) return;
    setOperation("applying");
    const result = await postTripJson<ApplyResponse>(
      TRIP_API_ENDPOINTS.applyPrePlanHandoff(tripId, preview.handoff.id),
      { draft_intent_revision_id: intent.revision.id, handoff_digest: preview.handoff.trace_digest },
      "应用路线预览失败",
      undefined,
      { headers: { "X-Idempotency-Key": `draft-handoff:${preview.handoff.id}:${preview.handoff.trace_digest.slice(0, 16)}` } },
    );
    setOperation("idle");
    if (!result.ok) {
      setStatus(result.message);
      return;
    }
    onApplied(result.data);
  }

  const busy = operation !== "idle";
  return (
    <section data-preplan-intent-workspace="true" style={{ maxWidth: 1120, margin: "32px auto", padding: 24, border: "1px solid var(--ec-line-soft)", background: "var(--ec-paper)", display: "grid", gap: 18 }}>
      <div style={{ display: "grid", gap: 6 }}>
        <p style={{ margin: 0, fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", color: "var(--ec-slate)" }}>DRAFT TRIP · PRE-PLAN INTENT</p>
        <h2 style={{ margin: 0 }}>先确认意图与来源，再生成第一版路线</h2>
        <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.6 }}>这份草稿尚未创建行程 Revision。系统会先编译你的文字与已审核来源，预览确定性计划结果；只有确认应用后，才写入 Revision 1。</p>
      </div>
      <div style={{ padding: 14, border: "1px solid var(--ec-line-soft)", whiteSpace: "pre-wrap", lineHeight: 1.65 }}>{directUserText}</div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button type="button" onClick={() => void compile()} disabled={busy}>{operation === "compiling" ? "编译中…" : "编译意图合同"}</button>
        <button type="button" onClick={() => void buildPreview()} disabled={busy || !intent}>生成路线预览</button>
        <button type="button" onClick={() => void apply()} disabled={busy || !preview}>{operation === "applying" ? "应用中…" : "确认并创建 Revision 1"}</button>
        <button type="button" onClick={onCancel} disabled={busy}>返回修改输入</button>
      </div>
      {intent ? <div style={{ display: "grid", gap: 4, borderLeft: "3px solid var(--ec-olive)", paddingLeft: 12 }}><strong>意图合同 v{intent.revision.revision_number}</strong><span>状态：{intent.envelope.planner_ready_status}；待澄清：{intent.envelope.clarification_queue.length}</span></div> : null}
      {preview ? <div style={{ display: "grid", gap: 4, borderLeft: "3px solid var(--ec-blue)", paddingLeft: 12 }}><strong>冻结路线预览</strong><span>运行 {preview.handoff.id.slice(-10)}；内容摘要 {preview.handoff.result_content_digest.slice(0, 12)}</span></div> : null}
      {candidates.length ? <fieldset style={{ border: "1px solid var(--ec-line-soft)", padding: 14, display: "grid", gap: 8 }}><legend>已审核来源候选</legend>{candidates.map((candidate) => <label key={candidate.id} style={{ display: "flex", gap: 8, alignItems: "center" }}><input type="checkbox" checked={selectedCandidateIds.includes(candidate.id)} onChange={(event) => { setSelectedCandidateIds((current) => event.target.checked ? [...current, candidate.id] : current.filter((id) => id !== candidate.id)); setPreview(null); }} />{candidate.display_name}</label>)}</fieldset> : null}
      <ImportReviewWorkspace
        tripPersistence={{ status: "draft", tripId }}
        onCandidatesChanged={() => {
          void refreshCandidates();
          setPreview(null);
          setStatus("已更新来源候选；请重新编译意图合同以纳入审核结果。");
        }}
      />
      {status ? <p role="status" style={{ margin: 0, color: "var(--ec-slate)" }}>{status}</p> : null}
    </section>
  );
}
