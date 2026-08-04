"use client";

import React, { FormEvent, useEffect, useState } from "react";

import { getTripJson, postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import { ExecutableRoutePreview } from "@/features/executable-route-preview/ExecutableRoutePreview";
import type { RoutePreviewItinerary } from "@/features/executable-route-preview/routePreviewModel";
import type { TripMetadata, TripRevisionMetadata } from "@/features/trip-workspace/tripPersistence";
import { PlanCandidateComparison, type PlanCandidateResponse } from "./PlanCandidateComparison";

type PlaceOption = { provider_place_id: string; canonical_name: string; address_summary?: string | null; category?: string | null };
type PlaceIdentity = { stable_id: string; original_name: string; canonical_name?: string | null; ownership: "must" | "optional" | "fixed"; resolution_status: "verified" | "ambiguous" | "unresolved"; confirmation_options: PlaceOption[] };
type FormalIntent = { destinations: Array<{ city_name: string }>; date_policy?: { trip_days?: number | null } | null; pace?: { value: "relaxed" | "balanced" | "intensive" } | null; fixed_events: Array<{ title: string; fixed_day?: number | null }>; place_identities: PlaceIdentity[] };
type Envelope = { planner_ready_status: "ready" | "ready_for_planning" | "needs_clarification" | "blocked" | "ready_with_assumptions"; formal_contract: FormalIntent; clarification_queue: Array<{ question: string; blocking: boolean }> };
type Revision = { id: string };
type Draft = { id: string; draft_version: number };
type Latest = { trip: Draft; envelope: Envelope; revision: Revision };
type EditResponse = { draft_trip_id: string; draft_version: number; envelope: Envelope; revision: Revision; changed: boolean; idempotent_replay: boolean; latest_intent_revision_id: string };
type TravelIntent = { destination: string | null; trip_days: number | null; pace: "relaxed" | "balanced" | "intensive"; must_visit_places: Array<{ name: string }>; fixed_events: Array<{ name: string }> };
type PlanningRun = PlanCandidateResponse & { confirmed_intent: TravelIntent; trip_id: string | null };
type SavedTrip = { trip: TripMetadata; current_revision: TripRevisionMetadata; itinerary: RoutePreviewItinerary };

type State =
  | { kind: "input" }
  | { kind: "working" }
  | { kind: "confirm"; latest: Latest; message: string | null }
  | { kind: "planning"; latest: Latest }
  | { kind: "candidates"; latest: Latest | null; run: PlanningRun; selectedId: string; error: string | null }
  | { kind: "selecting"; latest: Latest | null; run: PlanningRun; selectedId: string }
  | { kind: "route"; saved: SavedTrip; intent: TravelIntent }
  | { kind: "error"; message: string };

const EXAMPLES = [
  ["杭州两日轻松游", "周末去杭州玩两天，想去西湖和灵隐寺。朋友推荐龙井村，但不是必须。不想太赶，想吃本地小吃。"],
  ["上海固定预约", "去上海玩三天，想去上海博物馆、外滩和武康路。第二天下午两点到四点有固定活动，不能改。喜欢城市散步和本地小吃，不要太赶。"],
  ["西安历史文化", "我想去西安玩三天，已经想去兵马俑、陕西历史博物馆、大雁塔和西安城墙。希望白天看景点，晚上安排吃饭和夜游，不要太赶。"],
] as const;

export function TripCompilerWorkspace() {
  const [text, setText] = useState("");
  const [state, setState] = useState<State>({ kind: "input" });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tripId = params.get("trip");
    const planningRunId = params.get("planning_run");
    if (tripId) void loadSavedTrip(tripId);
    else if (planningRunId) void loadPlanningRun(planningRunId);
  }, []);

  async function loadSavedTrip(tripId: string) {
    const result = await getTripJson<SavedTrip>(TRIP_API_ENDPOINTS.getTrip(tripId), "暂时无法打开这份行程。", "无法连接后端接口。");
    setState(result.ok ? { kind: "route", saved: result.data, intent: { destination: null, trip_days: result.data.itinerary.trip_days, pace: "balanced", must_visit_places: [], fixed_events: [] } } : { kind: "error", message: result.message });
  }

  async function loadPlanningRun(runId: string) {
    setState({ kind: "working" });
    const result = await getTripJson<PlanningRun>(TRIP_API_ENDPOINTS.getTripCompilerPlanningRun(runId), "暂时无法恢复这批路线方案。", "无法连接后端接口。");
    if (!result.ok) return setState({ kind: "error", message: result.message });
    if (result.data.status === "expired") return setState({ kind: "error", message: "这批路线方案已经过期，请重新生成。" });
    setState({ kind: "candidates", latest: null, run: result.data, selectedId: result.data.candidates[0]?.id ?? "", error: null });
  }

  async function start(event: FormEvent) {
    event.preventDefault();
    const directUserText = text.trim();
    if (!directUserText) return;
    setState({ kind: "working" });
    const key = `trip-compiler-draft:${crypto.randomUUID()}`;
    const created = await postTripJson<{ trip: Draft }>(TRIP_API_ENDPOINTS.createDraftTrip, { direct_user_text: directUserText }, "暂时无法保存你的旅行想法。", "无法连接后端接口。", { headers: { "X-Idempotency-Key": key } });
    if (!created.ok) return setState({ kind: "error", message: created.message });
    const compiled = await postTripJson<{ revision: Revision }>(TRIP_API_ENDPOINTS.compilePrePlanIntent(created.data.trip.id), { base_intent_revision_id: null, use_llm_proposal_adapter: false }, "暂时无法整理旅行信息。", "无法连接后端接口。", { headers: { "X-Idempotency-Key": `${key}:intent` } });
    if (!compiled.ok) return setState({ kind: "error", message: compiled.message });
    await refreshLatest(created.data.trip.id);
  }

  async function refreshLatest(tripId: string, message: string | null = null) {
    const latest = await getTripJson<Latest>(TRIP_API_ENDPOINTS.getLatestPrePlanIntent(tripId), "暂时无法刷新旅行信息。", "无法连接后端接口。");
    setState(latest.ok ? { kind: "confirm", latest: latest.data, message } : { kind: "error", message: latest.message });
  }

  async function confirmPlace(latest: Latest, identity: PlaceIdentity, option: PlaceOption) {
    setState({ kind: "working" });
    const result = await postTripJson<EditResponse>(TRIP_API_ENDPOINTS.editPrePlanIntent(latest.trip.id), {
      base_intent_revision_id: latest.revision.id,
      base_draft_version: latest.trip.draft_version,
      operations: [{ operation: "confirm_place_identity", place_stable_id: identity.stable_id, provider_place_id: option.provider_place_id }],
    }, "暂时无法确认这个地点。", "无法连接后端接口。", { headers: { "X-Idempotency-Key": `place-confirm:${crypto.randomUUID()}` } });
    if (!result.ok) return setState({ kind: "error", message: result.message });
    setState({ kind: "confirm", latest: { trip: { id: result.data.draft_trip_id, draft_version: result.data.draft_version }, envelope: result.data.envelope, revision: result.data.revision }, message: "地点已确认。" });
  }

  async function plan(latest: Latest) {
    setState({ kind: "planning", latest });
    const result = await postTripJson<PlanningRun>(TRIP_API_ENDPOINTS.createPrePlanIntentPlanningRun(latest.trip.id), { draft_intent_revision_id: latest.revision.id }, "暂时无法生成路线方案。", "无法连接后端接口。");
    if (!result.ok) return setState({ kind: "confirm", latest, message: result.message });
    window.history.replaceState({}, "", `/trip-compiler?planning_run=${encodeURIComponent(result.data.planning_run_id)}`);
    setState({ kind: "candidates", latest, run: result.data, selectedId: result.data.candidates[0]?.id ?? "", error: null });
  }

  async function select(run: PlanningRun, selectedId: string) {
    const candidate = run.candidates.find((item) => item.id === selectedId);
    if (!candidate) return;
    setState((current) => current.kind === "candidates" ? { kind: "selecting", latest: current.latest, run, selectedId } : current);
    const result = await postTripJson<SavedTrip>(TRIP_API_ENDPOINTS.selectTripCompilerCandidate(run.planning_run_id, candidate.id), { candidate_hash: candidate.candidate_hash, intent_digest: run.intent_digest }, "暂时无法保存这条路线。", "无法连接后端接口。", { headers: { "X-Idempotency-Key": `trip-candidate:${crypto.randomUUID()}` } });
    if (!result.ok) return setState((current) => current.kind === "selecting" ? { kind: "candidates", latest: current.latest, run, selectedId, error: result.message } : current);
    window.history.replaceState({}, "", `/trip-compiler?trip=${encodeURIComponent(result.data.trip.id)}`);
    setState({ kind: "route", saved: result.data, intent: run.confirmed_intent });
  }

  if (state.kind === "route") return <RouteScreen {...state.saved} intent={state.intent} />;
  if (state.kind === "candidates" || state.kind === "selecting") return <><PlanCandidateComparison response={state.run} selectedId={state.selectedId} busy={state.kind === "selecting"} error={state.kind === "candidates" ? state.error : null} record={null} onSelect={(selectedId) => state.kind === "candidates" && setState({ ...state, selectedId, error: null })} onConfirm={() => void select(state.run, state.selectedId)} onBack={() => state.latest ? setState({ kind: "confirm", latest: state.latest, message: null }) : setState({ kind: "input" })} onViewRecord={() => undefined} /><Styles /></>;
  if (state.kind === "confirm" || state.kind === "planning") return <Confirmation latest={state.latest} busy={state.kind === "planning"} message={state.kind === "confirm" ? state.message : null} onConfirmPlace={confirmPlace} onPlan={plan} onBack={() => setState({ kind: "input" })} />;
  if (state.kind === "error") return <main className="tc-page"><section className="tc-card" role="alert"><h1>暂时没能继续</h1><p>{state.message}</p><button type="button" onClick={() => setState({ kind: "input" })}>重新开始</button></section><Styles /></main>;
  return <Input text={text} busy={state.kind === "working"} onText={setText} onSubmit={start} />;
}

function Input({ text, busy, onText, onSubmit }: { text: string; busy: boolean; onText: (value: string) => void; onSubmit: (event: FormEvent) => void }) {
  return <main className="tc-page tc-input"><section><p className="tc-eyebrow">AI Trip Compiler</p><h1>把旅行想法，变成一份看得懂的路线。</h1><p>告诉我想去哪里、玩几天、想去的地点和固定安排。</p></section><form className="tc-card tc-composer" onSubmit={onSubmit}><label htmlFor="trip-compiler-input">这趟旅行，你已经知道些什么？</label><textarea id="trip-compiler-input" value={text} onChange={(event) => onText(event.target.value)} rows={12} disabled={busy} autoFocus placeholder={EXAMPLES[0][1]} /><button className="tc-primary" type="submit" disabled={busy || !text.trim()}>{busy ? "正在整理" : "继续"}</button><div className="tc-examples">{EXAMPLES.map(([label, value]) => <button type="button" key={label} onClick={() => onText(value)}>{label}</button>)}</div></form><Styles /></main>;
}

function Confirmation({ latest, busy, message, onConfirmPlace, onPlan, onBack }: { latest: Latest; busy: boolean; message: string | null; onConfirmPlace: (latest: Latest, identity: PlaceIdentity, option: PlaceOption) => void; onPlan: (latest: Latest) => void; onBack: () => void }) {
  const formal = latest.envelope.formal_contract;
  const required = formal.place_identities.filter((item) => item.ownership === "must" || item.ownership === "fixed");
  const unresolved = required.filter((item) => item.resolution_status !== "verified");
  const canPlan = latest.envelope.planner_ready_status === "ready" || latest.envelope.planner_ready_status === "ready_for_planning";
  return <main className="tc-page"><header className="tc-header"><div><p className="tc-eyebrow">确认行程信息</p><h1>这些是我理解到的旅行安排。</h1><p>先确认具体地点，再生成路线。</p></div><button type="button" className="tc-link" onClick={onBack} disabled={busy}>重新描述</button></header>{message ? <p className="tc-notice" role="status">{message}</p> : null}<div className="tc-grid"><section className="tc-stack"><section className="tc-card"><h2>旅行安排</h2><dl><div><dt>目的地</dt><dd>{formal.destinations[0]?.city_name ?? "还没有"}</dd></div><div><dt>天数</dt><dd>{formal.date_policy?.trip_days ?? "还没有"}</dd></div><div><dt>节奏</dt><dd>{{ relaxed: "轻松", balanced: "均衡", intensive: "紧凑" }[formal.pace?.value ?? "balanced"]}</dd></div></dl></section><section className="tc-card"><h2>地点确认</h2>{required.length ? required.map((identity) => <div className="tc-place" key={identity.stable_id}><strong>{identity.canonical_name ?? identity.original_name}</strong>{identity.resolution_status === "verified" ? <span className="tc-verified">已确认</span> : identity.confirmation_options.length ? <div><p>请选择具体地点：</p>{identity.confirmation_options.map((option) => <button key={option.provider_place_id} type="button" disabled={busy} onClick={() => onConfirmPlace(latest, identity, option)}><strong>{option.canonical_name}</strong><small>{option.address_summary ?? option.category ?? "地点信息"}</small></button>)}</div> : <p className="tc-warning">暂时无法确认这个地点，请返回补充更具体的名称。</p>}</div>) : <p>还没有明确的必去地点，也可以先生成路线骨架。</p>}</section>{formal.fixed_events.length ? <section className="tc-card"><h2>固定安排</h2>{formal.fixed_events.map((event) => <p key={event.title}>{event.title}{event.fixed_day ? ` · 第 ${event.fixed_day} 天` : ""}</p>)}</section> : null}</section><aside className="tc-stack"><section className="tc-card"><h2>还需要确认</h2>{unresolved.length ? <p>确认 {unresolved.length} 个必去地点后即可生成路线。</p> : latest.envelope.clarification_queue.filter((item) => item.blocking).length ? <ul>{latest.envelope.clarification_queue.filter((item) => item.blocking).map((item) => <li key={item.question}>{item.question}</li>)}</ul> : <p>关键信息已经齐全。</p>}</section><button className="tc-primary tc-plan" type="button" disabled={busy || !canPlan} onClick={() => onPlan(latest)}>{busy ? "正在生成路线" : "生成路线"}</button></aside></div><Styles /></main>;
}

function RouteScreen({ trip, current_revision, itinerary, intent }: SavedTrip & { intent: TravelIntent }) {
  return <main className="tc-page"><header className="tc-header"><div><p className="tc-eyebrow">你的行程</p><h1>{intent.destination ?? "这次旅行"} · {itinerary.trip_days} 天</h1><p>路线已保存，可以继续调整。</p></div><span className="tc-verified">已保存</span></header><ExecutableRoutePreview itinerary={itinerary} variant="saved" tripId={trip.id} baseRevisionId={current_revision.id} onApplied={() => undefined} /><Styles /></main>;
}

function Styles() { return <style>{`.tc-page{--ink:#182126;--muted:#637078;--line:#d9ded8;--paper:#fffefa;--warm:#f5f1e8;--accent:#356f62;max-width:1120px;margin:0 auto;padding:68px 24px 100px;color:var(--ink)}.tc-input{min-height:calc(100vh - 72px);display:grid;grid-template-columns:minmax(0,.9fr) minmax(460px,1.1fr);align-items:center;gap:60px}.tc-eyebrow{margin:0 0 10px;color:var(--accent);font-size:12px;font-weight:800;letter-spacing:.1em;text-transform:uppercase}.tc-page h1{margin:0;font-family:Georgia,"Times New Roman",serif;font-size:clamp(38px,4vw,60px);line-height:1.06}.tc-page p{color:var(--muted);line-height:1.6}.tc-card{border:1px solid var(--line);border-radius:8px;background:var(--paper);padding:20px}.tc-composer{box-shadow:0 18px 40px rgba(37,44,38,.07)}.tc-composer label,.tc-card h2{display:block;margin:0 0 12px;font-size:16px}.tc-composer textarea{box-sizing:border-box;width:100%;border:0;border-bottom:1px solid var(--line);background:transparent;padding:8px 0 16px;font:inherit;font-size:16px;line-height:1.65;outline:none}.tc-primary{border:0;border-radius:7px;background:var(--ink);color:#fff;padding:13px 18px;font:inherit;font-weight:800;cursor:pointer}.tc-primary:disabled{opacity:.5;cursor:wait}.tc-composer .tc-primary{margin-top:17px}.tc-examples{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}.tc-examples button,.tc-link{border:0;background:none;color:var(--accent);font:inherit;font-size:13px;font-weight:700;cursor:pointer}.tc-header{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:24px}.tc-link{border-bottom:1px solid currentColor}.tc-notice{border-left:3px solid var(--accent);padding-left:12px}.tc-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(260px,.7fr);gap:16px}.tc-stack{display:grid;align-content:start;gap:16px}.tc-card dl{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:0}.tc-card dl div{background:var(--warm);padding:12px}.tc-card dt{color:var(--muted);font-size:12px}.tc-card dd{margin:5px 0 0;font-weight:800}.tc-place{padding:14px 0;border-top:1px solid #edf0ec}.tc-place>strong{display:block}.tc-place button{display:grid;width:100%;margin-top:8px;padding:10px;border:1px solid var(--line);border-radius:6px;background:#fff;text-align:left;color:var(--ink);cursor:pointer}.tc-place button:hover,.tc-place button:focus-visible{border-color:var(--accent)}.tc-place small{margin-top:3px;color:var(--muted)}.tc-verified{display:inline-block;margin-top:8px;border-radius:999px;background:#edf6ef;color:#386347;padding:5px 9px;font-size:13px;font-weight:800}.tc-warning{color:#943b32!important}.tc-plan{width:100%}@media(max-width:760px){.tc-page{padding:38px 16px 88px}.tc-input,.tc-grid{grid-template-columns:1fr;gap:28px}.tc-header{display:grid;align-items:start}.tc-card dl{grid-template-columns:1fr}.tc-page h1{font-size:39px}}`}</style>; }
