"use client";

import React, { useEffect, useState } from "react";
import { getTripJson, postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import type { TripMetadata, TripRevisionMetadata } from "@/features/trip-workspace/tripPersistence";
import { ImportReviewWorkspace } from "@/features/imports/ImportReviewWorkspace";
import { formatIntentDomainValue } from "@/features/intent-confirmation/intentConfirmationModel";
import type {
  IntentClarification,
  IntentConflict,
  IntentField,
  SourceLinkedTripIntentEnvelope,
} from "@/features/intent-confirmation/intentTypes";

// The route workspace owns the rich itinerary view model. This boundary only transports
// the server-authoritative snapshot back to that owner after the first apply.
type ItineraryResponse = any;

type DraftIntentResponse = {
  envelope: SourceLinkedTripIntentEnvelope;
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

  function invalidateCompiledContract(message: string) {
    setIntent(null);
    setPreview(null);
    setStatus(message);
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
  const plannerReady = intent?.envelope.planner_ready_status === "ready" || intent?.envelope.planner_ready_status === "ready_for_planning" || intent?.envelope.planner_ready_status === "ready_with_assumptions";
  const selectedFields = intent?.envelope.fields.filter((field) => field.status === "selected") ?? [];
  return (
    <section data-preplan-intent-workspace="true" style={{ maxWidth: 1180, margin: "32px auto", padding: 24, border: "1px solid var(--ec-line-soft)", background: "var(--ec-paper)", display: "grid", gap: 18 }}>
      <div style={{ display: "grid", gap: 6 }}>
        <p style={{ margin: 0, fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", color: "var(--ec-slate)" }}>DRAFT TRIP · PRE-PLAN INTENT</p>
        <h2 style={{ margin: 0 }}>先确认意图与来源，再生成第一版路线</h2>
        <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.6 }}>这份草稿尚未创建行程 Revision。先审阅系统采用了什么、忽略了什么、还缺什么；确认冻结预览后，才会写入 Revision 1。</p>
      </div>
      <ol aria-label="生成前工作流" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10, padding: 0, margin: 0, listStyle: "none" }}>
        <WorkflowStep number="1" title="来源输入" detail="你的文字与已审核候选" active />
        <WorkflowStep number="2" title="意图合同" detail="约束、来源、冲突与假设" active={Boolean(intent)} />
        <WorkflowStep number="3" title="冻结预览" detail="确定性计划尚未写入" active={Boolean(preview)} />
        <WorkflowStep number="4" title="创建 Revision 1" detail="确认后才保存路线" active={false} />
      </ol>
      <section aria-label="直接用户输入" style={{ display: "grid", gap: 8, padding: 14, border: "1px solid var(--ec-line-soft)", background: "rgba(255,255,255,0.55)" }}>
        <strong style={{ fontSize: 14 }}>直接用户输入</strong>
        <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.65 }}>{directUserText}</div>
      </section>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button type="button" onClick={() => void compile()} disabled={busy}>{operation === "compiling" ? "编译中…" : "1. 编译意图合同"}</button>
        <button type="button" onClick={() => void buildPreview()} disabled={busy || !intent || !plannerReady}>2. 生成冻结预览</button>
        <button type="button" onClick={() => void apply()} disabled={busy || !preview}>{operation === "applying" ? "应用中…" : "3. 确认并创建 Revision 1"}</button>
        <button type="button" onClick={onCancel} disabled={busy}>返回修改输入</button>
      </div>
      {intent ? <IntentContractReview envelope={intent.envelope} revisionNumber={intent.revision.revision_number} selectedFields={selectedFields} /> : null}
      {preview ? <FrozenPreview preview={preview} /> : null}
      {candidates.length ? <fieldset style={{ border: "1px solid var(--ec-line-soft)", padding: 14, display: "grid", gap: 8 }}><legend>已审核来源候选</legend><p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13, lineHeight: 1.5 }}>选择后必须重新编译，候选才会进入这份意图合同。</p>{candidates.map((candidate) => <label key={candidate.id} style={{ display: "flex", gap: 8, alignItems: "center" }}><input type="checkbox" checked={selectedCandidateIds.includes(candidate.id)} onChange={(event) => { setSelectedCandidateIds((current) => event.target.checked ? [...current, candidate.id] : current.filter((id) => id !== candidate.id)); invalidateCompiledContract("来源候选已变更。请重新编译意图合同，再生成冻结预览。"); }} />{candidate.display_name}</label>)}</fieldset> : null}
      <ImportReviewWorkspace
        tripPersistence={{ status: "draft", tripId }}
        onCandidatesChanged={() => {
          void refreshCandidates();
          invalidateCompiledContract("已更新 Import Review。请重新编译意图合同以纳入审核结果。");
        }}
      />
      {status ? <p role="status" style={{ margin: 0, color: "var(--ec-slate)" }}>{status}</p> : null}
    </section>
  );
}

function WorkflowStep({ number, title, detail, active }: { number: string; title: string; detail: string; active: boolean }) {
  return (
    <li style={{ display: "grid", gridTemplateColumns: "28px 1fr", gap: 10, padding: 12, border: "1px solid var(--ec-line-soft)", background: active ? "rgba(233, 243, 223, 0.56)" : "rgba(255,255,255,0.4)" }}>
      <span aria-hidden="true" style={{ display: "grid", placeItems: "center", width: 28, height: 28, borderRadius: "50%", background: active ? "var(--ec-olive)" : "var(--ec-line-soft)", color: active ? "white" : "var(--ec-slate)", fontWeight: 800 }}>{number}</span>
      <span style={{ display: "grid", gap: 2 }}><strong style={{ fontSize: 13 }}>{title}</strong><span style={{ color: "var(--ec-slate)", fontSize: 12, lineHeight: 1.4 }}>{detail}</span></span>
    </li>
  );
}

function IntentContractReview({ envelope, revisionNumber, selectedFields }: { envelope: SourceLinkedTripIntentEnvelope; revisionNumber: number; selectedFields: IntentField[] }) {
  const formal = envelope.formal_contract;
  const readiness = formal.readiness;
  return (
    <section aria-label="意图合同审阅" style={{ display: "grid", gap: 14, padding: 16, border: "1px solid var(--ec-line-soft)", background: "rgba(250,250,246,0.72)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
        <div><p style={{ margin: 0, fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", color: "var(--ec-slate)" }}>COMPILED INTENT CONTRACT · v{revisionNumber}</p><h3 style={{ margin: "4px 0 0" }}>这份路线将遵守什么</h3></div>
        <strong style={{ color: readiness.planner_contract_complete ? "var(--ec-moss)" : "#9d302a" }}>{readiness.status}</strong>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
        <ContractMetric label="目的地" value={formal.destinations.map((item) => item.city_name).join(" / ") || "待澄清"} />
        <ContractMetric label="天数" value={formal.date_policy?.trip_days ? `${formal.date_policy.trip_days} 天` : "待澄清"} />
        <ContractMetric label="固定安排" value={`${formal.fixed_events.length} 项`} />
        <ContractMetric label="确认地点" value={`${formal.must_visit_places.length} 个`} />
        <ContractMetric label="计划假设" value={`${formal.assumptions.length} 项`} />
      </div>
      {!readiness.planner_contract_complete ? <p role="alert" style={{ margin: 0, padding: 12, borderLeft: "3px solid #9d302a", background: "rgba(255, 240, 238, 0.7)", lineHeight: 1.55 }}>当前合同不能生成预览。请先查看下面的澄清或冲突项，再返回修改输入；系统不会用猜测替代未确认的硬边界。</p> : null}
      <section style={{ display: "grid", gap: 8 }}>
        <strong style={{ fontSize: 14 }}>采用的字段与来源</strong>
        {selectedFields.length ? <div style={{ overflowX: "auto" }}><table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}><thead><tr><th style={tableHeaderStyle}>字段</th><th style={tableHeaderStyle}>采用值</th><th style={tableHeaderStyle}>约束</th><th style={tableHeaderStyle}>确认与权威来源</th></tr></thead><tbody>{selectedFields.map((field) => <tr key={field.field_id}><td style={tableCellStyle}>{field.field_path}</td><td style={tableCellStyle}>{formatIntentDomainValue(field.value)}</td><td style={tableCellStyle}>{field.kind}</td><td style={tableCellStyle}>{field.confirmed_by_user ? "已确认" : "待确认"} · {field.source_refs.map((source) => `${source.label} (${source.authority})`).join("；") || "无来源"}</td></tr>)}</tbody></table></div> : <p style={{ margin: 0, color: "var(--ec-slate)" }}>编译器尚未采用有效字段。</p>}
      </section>
      <IssueList title="需要澄清" issues={envelope.clarification_queue} emptyLabel="没有阻断性澄清。" render={(item: IntentClarification) => <><strong>{item.question}</strong><span>{item.blocking ? "会阻止生成预览" : "会影响路线质量"} · {item.reason_code}</span></>} />
      <IssueList title="来源冲突" issues={envelope.conflicts} emptyLabel="没有检测到来源冲突。" render={(item: IntentConflict) => <><strong>{item.field_path}</strong><span>{item.explanation} · {item.severity}</span></>} />
      <IssueList title="计划假设" issues={formal.assumptions} emptyLabel="没有使用计划假设。" render={(item) => <><strong>{item.field_path}</strong><span>{item.reason_code} · {item.user_acknowledged ? "已确认" : "尚未确认"}</span></>} />
      <section style={{ display: "grid", gap: 6, borderTop: "1px solid var(--ec-line-soft)", paddingTop: 12 }}>
        <strong style={{ fontSize: 14 }}>来源证据图</strong>
        <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13, lineHeight: 1.5 }}>当前合同有 {envelope.provenance_graph.nodes.length} 个来源节点和 {envelope.provenance_graph.edges.length} 条关联。下面列出直接支撑合同的证据节点。</p>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{envelope.provenance_graph.nodes.filter((node) => node.node_type !== "field" && node.node_type !== "envelope_revision").slice(0, 10).map((node) => <span key={node.node_id} style={{ padding: "5px 8px", border: "1px solid var(--ec-line-soft)", fontSize: 12 }}>{node.label} · {node.confirmed ? "已确认" : "待确认"}</span>)}</div>
      </section>
    </section>
  );
}

function FrozenPreview({ preview }: { preview: PreviewResponse }) {
  const days = Array.isArray(preview.itinerary?.days) ? preview.itinerary.days : [];
  return (
    <section aria-label="冻结路线预览" style={{ display: "grid", gap: 12, padding: 16, border: "1px solid rgba(48, 94, 189, 0.25)", background: "rgba(237, 243, 255, 0.56)" }}>
      <div><p style={{ margin: 0, fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", color: "var(--ec-slate)" }}>FROZEN PLANNER PREVIEW</p><h3 style={{ margin: "4px 0 0" }}>预览已冻结，尚未写入行程版本</h3></div>
      <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13 }}>运行 {preview.handoff.id.slice(-10)} · 内容摘要 {preview.handoff.result_content_digest.slice(0, 12)} · 确认后将以同一份预览创建 Revision 1。</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10 }}>{days.map((day: any, index: number) => <div key={day.day ?? index} style={{ padding: 12, border: "1px solid rgba(48, 94, 189, 0.16)", background: "rgba(255,255,255,0.68)" }}><strong>Day {day.day ?? day.day_number ?? index + 1}</strong><p style={{ margin: "6px 0 0", color: "var(--ec-slate)", fontSize: 13, lineHeight: 1.5 }}>{Array.isArray(day.items) ? day.items.map((item: any) => item.name ?? item.title).filter(Boolean).slice(0, 4).join(" · ") || "无已排项目" : "无已排项目"}</p></div>)}</div>
    </section>
  );
}

function ContractMetric({ label, value }: { label: string; value: string }) {
  return <div style={{ padding: 12, border: "1px solid var(--ec-line-soft)", background: "rgba(255,255,255,0.58)", display: "grid", gap: 4 }}><span style={{ color: "var(--ec-slate)", fontSize: 12 }}>{label}</span><strong>{value}</strong></div>;
}

function IssueList<T>({ title, issues, emptyLabel, render }: { title: string; issues: T[]; emptyLabel: string; render: (item: T) => React.ReactNode }) {
  return <section style={{ display: "grid", gap: 8 }}><strong style={{ fontSize: 14 }}>{title}</strong>{issues.length ? <div style={{ display: "grid", gap: 8 }}>{issues.map((item, index) => <div key={index} style={{ display: "grid", gap: 2, padding: 10, borderLeft: "3px solid var(--ec-ochre)", background: "rgba(255,253,249,0.7)", fontSize: 13, lineHeight: 1.5 }}>{render(item)}</div>)}</div> : <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13 }}>{emptyLabel}</p>}</section>;
}

const tableHeaderStyle: React.CSSProperties = { textAlign: "left", padding: "8px", borderBottom: "1px solid var(--ec-line-soft)", color: "var(--ec-slate)", fontWeight: 800, verticalAlign: "top" };
const tableCellStyle: React.CSSProperties = { padding: "8px", borderBottom: "1px solid var(--ec-line-soft)", verticalAlign: "top", lineHeight: 1.45 };
