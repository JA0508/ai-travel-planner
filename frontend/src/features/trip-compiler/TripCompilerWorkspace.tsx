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

const EDITORIAL_HERO_IMAGE = "/editorial/shanghai-street-hero.png";

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

  if (state.kind === "route") return <RouteScreen {...state.saved} intent={state.intent} onApplied={(response) => setState({ kind: "route", saved: response, intent: state.intent })} />;
  if (state.kind === "candidates" || state.kind === "selecting") return <><PlanCandidateComparison response={state.run} selectedId={state.selectedId} busy={state.kind === "selecting"} error={state.kind === "candidates" ? state.error : null} onSelect={(selectedId) => state.kind === "candidates" && setState({ ...state, selectedId, error: null })} onConfirm={() => void select(state.run, state.selectedId)} onBack={() => state.latest ? setState({ kind: "confirm", latest: state.latest, message: null }) : setState({ kind: "input" })} /><Styles /></>;
  if (state.kind === "confirm" || state.kind === "planning") return <Confirmation latest={state.latest} busy={state.kind === "planning"} message={state.kind === "confirm" ? state.message : null} onConfirmPlace={confirmPlace} onPlan={plan} onBack={() => setState({ kind: "input" })} />;
  if (state.kind === "error") return <main className="tc-page" data-visual-shell="road-movie-v0"><section className="tc-card" role="alert"><h1>暂时没能继续</h1><p>{state.message}</p><button type="button" onClick={() => setState({ kind: "input" })}>重新开始</button></section><Styles /></main>;
  return <Input text={text} busy={state.kind === "working"} onText={setText} onSubmit={start} />;
}

function Input({ text, busy, onText, onSubmit }: { text: string; busy: boolean; onText: (value: string) => void; onSubmit: (event: FormEvent) => void }) {
  return <main className="tc-page tc-input" data-visual-shell="road-movie-v0">
    <section className="tc-cover-copy">
      <div className="tc-cover-nav"><span className="tc-wordmark"><i aria-hidden="true">✦</i> 旅程编辑部</span><span>FIELD NOTES / 01</span></div>
      <p className="tc-eyebrow">AI Trip Compiler</p>
      <h1>把旅行想法，<em>变成一份看得懂的路线。</em></h1>
      <p className="tc-cover-lead">不是填表。先说说你想逃去哪里，我们会把想去的地方、时间边界和固定安排，串成一条能走的路。</p>
      <form className="tc-composer" onSubmit={onSubmit}>
        <div className="tc-composer-heading"><label htmlFor="trip-compiler-input">这一趟，你已经知道些什么？</label><span>随便说，剩下的我们来整理。</span></div>
        <textarea id="trip-compiler-input" value={text} onChange={(event) => onText(event.target.value)} rows={7} disabled={busy} autoFocus placeholder={EXAMPLES[0][1]} />
        <div className="tc-composer-footer"><div className="tc-examples" aria-label="旅行灵感示例">{EXAMPLES.map(([label, value], index) => <button type="button" key={label} onClick={() => onText(value)}><b>0{index + 1}</b>{label}</button>)}</div><button className="tc-primary" type="submit" disabled={busy || !text.trim()}><span>{busy ? "正在整理" : "开始编排行程"}</span><i aria-hidden="true">→</i></button></div>
      </form>
      <p className="tc-cover-note"><span aria-hidden="true">↳</span> 不用一次规划完。路上还可以改变主意。</p>
    </section>
    <section className="tc-cover-image" aria-label="雨后上海街头旅行场景">
      <img src={EDITORIAL_HERO_IMAGE} alt="雨后上海街头的咖啡馆与自行车" />
      <div className="tc-cover-city" aria-hidden="true">ADVENTURE</div>
      <div className="tc-cover-stamp"><b>02—03</b><span>DAYS TO<br />GET LOST</span></div>
      <div className="tc-cover-caption"><span>SHANGHAI FIELD NOTE</span><b>从街角开始，<br />让路线自己长出来。</b></div>
    </section>
    <Styles />
  </main>;
}

function Confirmation({ latest, busy, message, onConfirmPlace, onPlan, onBack }: { latest: Latest; busy: boolean; message: string | null; onConfirmPlace: (latest: Latest, identity: PlaceIdentity, option: PlaceOption) => void; onPlan: (latest: Latest) => void; onBack: () => void }) {
  const formal = latest.envelope.formal_contract;
  const city = formal.destinations[0]?.city_name ?? "下一站";
  const required = formal.place_identities.filter((item) => item.ownership === "must" || item.ownership === "fixed");
  const unresolved = required.filter((item) => item.resolution_status !== "verified");
  const unresolvedFixed = unresolved.filter((item) => item.ownership === "fixed");
  const canPlan = latest.envelope.planner_ready_status === "ready" || latest.envelope.planner_ready_status === "ready_for_planning";
  const confirmationHint = unresolvedFixed.length
    ? `固定安排“${unresolvedFixed.map((item) => item.original_name).join("、")}”的地点还需要确认。`
    : `确认 ${unresolved.length} 个必去地点后即可生成路线。`;
  const paceLabel = { relaxed: "慢一点", balanced: "刚刚好", intensive: "走多一点" }[formal.pace?.value ?? "balanced"];
  return <main className="tc-page tc-confirm-page" data-visual-shell="road-movie-v0">
    <header className="tc-confirm-hero">
      <img src={EDITORIAL_HERO_IMAGE} alt="雨后上海街头的旅行氛围" />
      <div className="tc-confirm-hero-shade" />
      <div className="tc-confirm-hero-top"><span className="tc-wordmark"><i aria-hidden="true">✦</i> 旅程编辑部</span><button type="button" className="tc-link" onClick={onBack} disabled={busy}>重新描述 ↗</button></div>
      <div className="tc-confirm-city"><span>DESTINATION / {formal.date_policy?.trip_days ?? "?"} DAYS</span><b>{city}</b></div>
      <div className="tc-confirm-hero-copy"><p className="tc-eyebrow">旅行简报</p><h1>这些是我理解到的旅行安排。</h1><p>确认几个关键点，我们就开始把这段时间串起来。</p></div>
    </header>
    <section className="tc-trip-strip" aria-label="旅行概览"><div><small>目的地</small><strong>{city}</strong></div><i aria-hidden="true" /><div><small>时间</small><strong>{formal.date_policy?.trip_days ? `${formal.date_policy.trip_days} DAYS` : "待确认"}</strong></div><i aria-hidden="true" /><div><small>节奏</small><strong>{paceLabel}</strong></div><i aria-hidden="true" /><div><small>固定安排</small><strong>{formal.fixed_events.length ? `${formal.fixed_events.length} LOCKED` : "自由安排"}</strong></div></section>
    {message ? <p className="tc-notice" role="status">{message}</p> : null}
    <div className="tc-confirm-layout">
      <section className="tc-confirm-main">
        {formal.fixed_events.length ? <section className="tc-ticket-section"><p className="tc-eyebrow">DON'T MOVE THIS ONE</p><h2>已经留好的时间</h2><div className="tc-ticket-stack">{formal.fixed_events.map((event) => <article className="tc-fixed-ticket" key={event.title}><div className="tc-ticket-day"><span>DAY</span><b>{String(event.fixed_day ?? 0).padStart(2, "0")}</b></div><div className="tc-ticket-content"><span>FIXED ARRANGEMENT</span><strong>{event.title}</strong><small>这段安排已固定，不会被随意改动。</small></div><span className="tc-ticket-lock">LOCKED</span></article>)}</div></section> : null}
        <section className="tc-place-ledger"><div className="tc-ledger-title"><div><p className="tc-eyebrow">PLACE CHECK</p><h2>这些地方，想和你确认一下。</h2></div><span>{required.length ? `${required.length} PLACES` : "OPEN ROUTE"}</span></div>{required.length ? required.map((identity, index) => <div className="tc-place" key={identity.stable_id}><span className="tc-place-index">0{index + 1}</span><div className="tc-place-copy"><strong>{identity.canonical_name ?? identity.original_name}</strong><small>{identity.ownership === "fixed" ? "固定安排地点" : "想去的地方"}</small>{identity.resolution_status === "verified" ? <span className="tc-verified">已确认</span> : identity.confirmation_options.length ? <div className="tc-place-options"><p>请选择具体地点：</p>{identity.confirmation_options.map((option) => <button key={option.provider_place_id} type="button" disabled={busy} onClick={() => onConfirmPlace(latest, identity, option)}><span><strong>{option.canonical_name}</strong><small>{option.address_summary ?? option.category ?? "地点信息"}</small></span><b aria-hidden="true">↗</b></button>)}</div> : <p className="tc-warning">暂时无法确认这个地点，请返回补充更具体的名称。</p>}</div></div>) : <div className="tc-open-slot"><b>ONE PLACE MISSING</b><p>还没有一定要去的地点。也很好，路线会为临时起意留一个空位。</p></div>}</section>
      </section>
      <aside className="tc-confirm-aside"><div className={`tc-readiness-note${unresolved.length ? " is-pending" : ""}`}><span>{unresolved.length ? "还差一点" : "READY TO GO"}</span><strong>{unresolved.length ? "先确认地点，路线才能真的属于你。" : "关键信息已经齐全。"}</strong><p>{unresolved.length ? confirmationHint : "固定安排和已确认地点都会被完整带进路线。"}</p><i aria-hidden="true">↘</i></div><button className="tc-primary tc-plan" type="button" disabled={busy || !canPlan} onClick={() => onPlan(latest)}><span>{busy ? "正在生成路线" : "生成我的路线"}</span><i aria-hidden="true">→</i></button><p className="tc-plan-note">确认后才会开始生成路线方案，还不会保存为最终行程。</p><details className="tc-source"><summary>为什么这样安排？ <span>↓</span></summary><p>每项安排都来自你确认的地点、时间和固定安排；系统补充会明确标为建议。</p></details></aside>
    </div>
    <Styles />
  </main>;
}

function RouteScreen({ trip, current_revision, itinerary, intent, onApplied }: SavedTrip & { intent: TravelIntent; onApplied: (response: SavedTrip) => void }) {
  return <main className="tc-page tc-route-page" data-visual-shell="living-roadbook"><ExecutableRoutePreview itinerary={itinerary} variant="saved" destination={intent.destination} tripId={trip.id} baseRevisionId={current_revision.id} onApplied={onApplied} /><Styles /></main>;
}

function Styles() { return <style>{`.tc-page{--ink:#141313;--muted:#647079;--line:rgba(20,19,19,.14);--paper:#f4eee4;--paper-light:#fffdf8;--sunset:#f26b38;--lake:#407c92;--moss:#66715b;--sand:#c89d60;position:relative;max-width:1480px;margin:0 auto;padding:28px 28px 104px;color:var(--ink);font-family:"Avenir Next","Noto Sans SC","PingFang SC",sans-serif}.tc-page:before{position:fixed;z-index:-1;inset:0;content:"";pointer-events:none;background-image:linear-gradient(rgba(20,19,19,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(20,19,19,.025) 1px,transparent 1px);background-size:32px 32px;mask-image:linear-gradient(180deg,rgba(0,0,0,.7),transparent 80%)}.tc-page h1,.tc-page h2,.tc-page h3{margin:0;font-family:"Iowan Old Style","Songti SC","STSong",Georgia,serif;color:var(--ink)}.tc-page h1{font-size:clamp(3.4rem,7.2vw,7.8rem);line-height:.86;letter-spacing:-.045em}.tc-page h1 em{display:block;color:var(--sunset);font-style:normal}.tc-page p{line-height:1.65}.tc-eyebrow{margin:0 0 11px;color:var(--sunset);font-size:11px;font-weight:900;letter-spacing:.15em;text-transform:uppercase}.tc-wordmark{font-weight:900;letter-spacing:-.03em}.tc-wordmark i{color:var(--sunset);font-style:normal}.tc-primary{display:inline-flex;align-items:center;justify-content:space-between;gap:22px;min-height:52px;border:0;border-radius:999px;background:var(--ink);color:var(--paper-light);padding:12px 20px 12px 23px;font:inherit;font-weight:900;cursor:pointer;transition:transform 180ms ease,background 180ms ease}.tc-primary i{color:var(--sunset);font-size:20px;font-style:normal}.tc-primary:hover:not(:disabled){transform:translateY(-2px);background:#000}.tc-primary:focus-visible,.tc-link:focus-visible,.tc-place-options button:focus-visible,.tc-examples button:focus-visible{outline:3px solid rgba(242,107,56,.4);outline-offset:3px}.tc-primary:disabled{cursor:not-allowed;opacity:.45}.tc-input{display:grid;min-height:calc(100vh - 56px);grid-template-columns:minmax(0,.96fr) minmax(440px,1.04fr);gap:clamp(28px,4.5vw,72px);align-items:center}.tc-cover-copy{display:grid;align-content:center;gap:22px;max-width:620px;padding:20px 0 20px clamp(0px,3vw,38px)}.tc-cover-nav{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid var(--line);padding-bottom:14px;color:var(--muted);font-size:11px;font-weight:800;letter-spacing:.11em}.tc-cover-copy h1{max-width:600px}.tc-cover-lead{max-width:430px;margin:0;color:var(--muted);font-size:16px}.tc-composer{display:grid;gap:14px;border:1px solid var(--line);border-radius:2px;background:rgba(255,253,248,.86);padding:18px 20px 18px;box-shadow:0 1px 0 rgba(0,0,0,.05),0 18px 46px rgba(38,29,19,.07)}.tc-composer-heading{display:flex;justify-content:space-between;gap:20px;align-items:baseline}.tc-composer label{font-weight:900}.tc-composer-heading span{color:var(--muted);font-size:12px}.tc-composer textarea{box-sizing:border-box;width:100%;resize:vertical;border:0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);outline:none;background:transparent;padding:16px 0;font:inherit;font-size:16px;line-height:1.72;color:var(--ink)}.tc-composer textarea:focus{border-color:var(--sunset)}.tc-composer-footer{display:flex;justify-content:space-between;gap:16px;align-items:flex-end}.tc-examples{display:flex;flex-wrap:wrap;gap:7px}.tc-examples button{display:inline-flex;gap:5px;border:0;background:transparent;color:var(--muted);padding:0;font:inherit;font-size:11px;font-weight:800;cursor:pointer}.tc-examples button b{color:var(--sunset)}.tc-examples button:hover{color:var(--ink)}.tc-cover-note{margin:0;color:var(--moss);font-family:"STKaiti","KaiTi",serif;font-size:16px}.tc-cover-note span{margin-right:7px;color:var(--sunset)}.tc-cover-image{position:relative;isolation:isolate;min-height:680px;overflow:hidden;background:#c9bfae}.tc-cover-image:after{position:absolute;z-index:1;inset:0;content:"";background:linear-gradient(180deg,rgba(20,19,19,.01) 35%,rgba(20,19,19,.32))}.tc-cover-image img{width:100%;height:100%;object-fit:cover;position:absolute;inset:0;filter:saturate(.85) contrast(1.03)}.tc-cover-city{position:absolute;z-index:2;top:4%;left:4%;font-size:clamp(4.6rem,10vw,11rem);font-weight:950;letter-spacing:-.09em;line-height:.8;color:var(--sunset);mix-blend-mode:multiply}.tc-cover-stamp{position:absolute;z-index:3;top:32%;right:0;display:grid;gap:2px;min-width:152px;background:var(--sunset);color:#fff;padding:20px}.tc-cover-stamp b{font-size:36px;line-height:.9;letter-spacing:-.08em}.tc-cover-stamp span{font-size:11px;font-weight:900;line-height:1.25;letter-spacing:.09em}.tc-cover-caption{position:absolute;z-index:3;bottom:32px;left:30px;display:grid;gap:8px;max-width:210px;color:#fff}.tc-cover-caption span{font-size:10px;font-weight:900;letter-spacing:.14em}.tc-cover-caption b{font-family:"Iowan Old Style","Songti SC",serif;font-size:24px;line-height:1.1}.tc-confirm-page{max-width:1320px;padding-top:0}.tc-confirm-hero{position:relative;display:grid;min-height:450px;overflow:hidden;margin:0 -28px 0}.tc-confirm-hero>img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center 56%;filter:saturate(.76)}.tc-confirm-hero-shade{position:absolute;inset:0;background:linear-gradient(90deg,rgba(14,13,12,.74),rgba(14,13,12,.2) 58%,rgba(14,13,12,.5)),linear-gradient(0deg,rgba(14,13,12,.55),transparent 50%)}.tc-confirm-hero-top,.tc-confirm-hero-copy,.tc-confirm-city{position:relative;z-index:1}.tc-confirm-hero-top{display:flex;justify-content:space-between;align-items:center;align-self:start;padding:26px 34px;color:#fff;font-size:12px;letter-spacing:.06em}.tc-link{border:0;border-bottom:1px solid currentColor;background:transparent;padding:0;color:inherit;font:inherit;font-weight:800;cursor:pointer}.tc-confirm-city{position:absolute;right:2.4%;bottom:20px;display:grid;justify-items:end;color:var(--sunset);line-height:.8}.tc-confirm-city span{margin-bottom:5px;color:#fff;font-size:11px;font-weight:900;letter-spacing:.14em}.tc-confirm-city b{font-size:clamp(5rem,15vw,14rem);letter-spacing:-.11em;white-space:nowrap}.tc-confirm-hero-copy{align-self:end;max-width:480px;padding:0 34px 36px;color:#fff}.tc-confirm-hero-copy h1{font-size:clamp(2.5rem,4.5vw,4.4rem);letter-spacing:-.055em;color:#fff}.tc-confirm-hero-copy h1 em{display:inline;color:#fff}.tc-confirm-hero-copy p:last-child{max-width:360px;margin:14px 0 0;color:rgba(255,255,255,.8)}.tc-trip-strip{display:flex;align-items:stretch;gap:16px;margin:0 0 42px;padding:18px 0;border-bottom:1px solid var(--line);background:var(--paper)}.tc-trip-strip div{display:grid;gap:4px;min-width:0;padding:0 18px}.tc-trip-strip small{color:var(--muted);font-size:10px;font-weight:900;letter-spacing:.12em}.tc-trip-strip strong{font-size:14px;overflow-wrap:anywhere}.tc-trip-strip i{width:1px;background:var(--line)}.tc-notice{margin:20px 0;padding:12px 14px;border-left:4px solid var(--sunset);background:#fff5ee;color:#73311b}.tc-confirm-layout{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(260px,.55fr);gap:clamp(30px,5vw,76px)}.tc-confirm-main{display:grid;gap:42px}.tc-ticket-section h2,.tc-place-ledger h2{font-size:clamp(1.9rem,3.2vw,2.75rem);line-height:1}.tc-ticket-stack{display:grid;gap:12px;margin-top:18px}.tc-fixed-ticket{position:relative;display:grid;grid-template-columns:112px 1fr auto;min-height:124px;overflow:hidden;border:1px dashed rgba(20,19,19,.35);border-radius:2px;background:var(--paper-light)}.tc-fixed-ticket:before,.tc-fixed-ticket:after{position:absolute;left:102px;width:18px;height:18px;content:"";border-radius:50%;background:var(--paper);transform:translateX(-50%)}.tc-fixed-ticket:before{top:-9px}.tc-fixed-ticket:after{bottom:-9px}.tc-ticket-day{display:grid;align-content:center;justify-items:center;gap:3px;border-right:1px dashed rgba(20,19,19,.3);background:var(--sunset);color:#fff}.tc-ticket-day span,.tc-ticket-content>span,.tc-ticket-lock{font-size:10px;font-weight:900;letter-spacing:.15em}.tc-ticket-day b{font-size:42px;line-height:.8;letter-spacing:-.1em}.tc-ticket-content{display:grid;align-content:center;gap:6px;padding:18px 24px}.tc-ticket-content>span{color:var(--sunset)}.tc-ticket-content strong{font-family:"Iowan Old Style","Songti SC",serif;font-size:22px}.tc-ticket-content small{color:var(--muted);line-height:1.45}.tc-ticket-lock{align-self:start;margin:16px;color:var(--moss);writing-mode:vertical-rl}.tc-place-ledger{border-top:1px solid var(--ink)}.tc-ledger-title{display:flex;justify-content:space-between;gap:20px;align-items:end;padding:20px 0}.tc-ledger-title>span{color:var(--sunset);font-size:11px;font-weight:900;letter-spacing:.12em}.tc-place{display:grid;grid-template-columns:52px 1fr;gap:14px;border-top:1px solid var(--line);padding:20px 0}.tc-place-index{color:var(--sunset);font-size:18px;font-weight:900;letter-spacing:-.08em}.tc-place-copy{display:grid;gap:5px}.tc-place-copy>strong{font-family:"Iowan Old Style","Songti SC",serif;font-size:24px;line-height:1.05}.tc-place-copy>small{color:var(--muted)}.tc-verified{justify-self:start;display:inline-flex;border-radius:999px;background:#e7ece8;color:#3e5d3a;padding:4px 8px;font-size:11px;font-weight:900}.tc-place-options{display:grid;gap:8px;margin-top:8px}.tc-place-options p{margin:0;color:var(--muted);font-size:13px}.tc-place-options button{display:flex;justify-content:space-between;align-items:center;gap:16px;width:100%;border:1px solid var(--line);border-radius:0;background:var(--paper-light);padding:12px 14px;text-align:left;color:var(--ink);cursor:pointer;transition:transform 160ms ease,border-color 160ms ease}.tc-place-options button:hover:not(:disabled){border-color:var(--sunset);transform:translateX(4px)}.tc-place-options button span{display:grid;gap:2px}.tc-place-options button small{color:var(--muted)}.tc-place-options button>b{color:var(--sunset);font-size:18px}.tc-warning{margin:3px 0 0;color:#9c3829!important}.tc-open-slot{position:relative;min-height:140px;padding:28px 0 8px}.tc-open-slot:before{position:absolute;left:0;top:18px;width:128px;height:58px;content:"";background:repeating-linear-gradient(-45deg,rgba(242,107,56,.18),rgba(242,107,56,.18) 1px,transparent 1px,transparent 8px)}.tc-open-slot b{position:relative;color:var(--sunset);font-size:11px;letter-spacing:.14em}.tc-open-slot p{max-width:360px;color:var(--muted)}.tc-confirm-aside{display:grid;align-content:start;gap:16px;padding-top:2px}.tc-readiness-note{position:relative;display:grid;gap:10px;min-height:220px;overflow:hidden;background:var(--moss);padding:24px;color:#fff;transform:rotate(1deg);box-shadow:0 14px 30px rgba(41,54,35,.16)}.tc-readiness-note:after{position:absolute;right:-26px;bottom:-32px;width:150px;height:150px;content:"";border:1px solid rgba(255,255,255,.25);border-radius:50%}.tc-readiness-note.is-pending{background:var(--sunset)}.tc-readiness-note span{font-size:11px;font-weight:900;letter-spacing:.14em}.tc-readiness-note strong{max-width:230px;font-family:"Iowan Old Style","Songti SC",serif;font-size:28px;line-height:1.05}.tc-readiness-note p{z-index:1;margin:0;color:rgba(255,255,255,.83);font-size:13px}.tc-readiness-note i{position:absolute;right:20px;bottom:16px;font-size:30px;font-style:normal}.tc-plan{width:100%}.tc-plan-note{margin:0;color:var(--muted);font-size:12px}.tc-source{border-top:1px solid var(--line);padding-top:16px}.tc-source summary{display:flex;justify-content:space-between;cursor:pointer;font-weight:900}.tc-source summary span{color:var(--sunset)}.tc-source p{color:var(--muted);font-size:13px}.tc-route-page{padding-top:54px}.tc-route-hero{display:flex;justify-content:space-between;align-items:end;gap:24px;padding-bottom:28px;border-bottom:1px solid var(--line);margin-bottom:28px}.tc-route-hero h1{font-size:clamp(3.2rem,7vw,7rem)}.tc-route-hero h1 em{display:inline;font-family:"Avenir Next","Noto Sans SC",sans-serif;font-size:.23em;letter-spacing:.04em}.tc-route-hero p{margin:14px 0 0;color:var(--muted)}.tc-card{border:1px solid var(--line);border-radius:3px;background:var(--paper-light);padding:20px}.tc-header,.tc-grid,.tc-stack{display:grid;gap:16px}.tc-candidate-page{max-width:1320px;padding-top:54px}.tc-confirm-header{display:flex;justify-content:space-between;gap:20px;align-items:end;padding-bottom:28px;border-bottom:1px solid var(--line)}.tc-confirm-header h1{font-size:clamp(3rem,5vw,5.6rem);max-width:720px}.tc-confirm-header h1 em{display:inline}.tc-confirm-header p{max-width:580px;color:var(--muted)}.tc-link-button{border:0;border-bottom:1px solid var(--ink);background:transparent;padding:0 0 3px;color:var(--ink);font:inherit;font-weight:900;white-space:nowrap;cursor:pointer}.tc-candidate-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:28px 0}.tc-candidate-card{display:grid;align-content:start;gap:11px;min-height:260px;border:1px solid var(--line);border-radius:2px;background:var(--paper-light);padding:19px;text-align:left;color:var(--ink);cursor:pointer;transition:transform 160ms ease,background 160ms ease,box-shadow 160ms ease}.tc-candidate-card:hover:not(:disabled),.tc-candidate-card.is-selected{transform:translateY(-4px);border-color:var(--ink);box-shadow:0 16px 32px rgba(40,28,18,.1)}.tc-candidate-card.is-selected{background:var(--sunset);color:#fff}.tc-candidate-tag{font-size:10px;font-weight:900;letter-spacing:.13em;color:var(--sunset)}.tc-candidate-card.is-selected .tc-candidate-tag{color:var(--ink)}.tc-candidate-card>strong{font-family:"Iowan Old Style","Songti SC",serif;font-size:29px;line-height:1}.tc-candidate-card>span{line-height:1.55}.tc-candidate-card dl{display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin:8px 0 0}.tc-candidate-card dl div{border-top:1px solid currentColor;padding-top:6px}.tc-candidate-card dt{font-size:10px;opacity:.72}.tc-candidate-card dd{margin:2px 0 0;font-weight:900}.tc-candidate-card ul{margin:0;padding-left:15px;font-size:12px;line-height:1.55}.tc-selected-route{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(250px,.55fr);gap:28px;border-top:1px solid var(--ink);padding-top:22px}.tc-selected-route h2{font-size:40px}.tc-day-route{position:relative;margin-top:28px;padding-left:82px}.tc-day-route:before{position:absolute;left:30px;top:36px;bottom:-18px;width:2px;content:"";background:var(--lake)}.tc-day-route h3{position:absolute;left:0;top:0;width:62px;color:var(--sunset);font-family:"Avenir Next","Noto Sans SC",sans-serif;font-size:11px;letter-spacing:.09em}.tc-route-item{position:relative;display:grid;grid-template-columns:58px 1fr;gap:14px;padding:12px 0;border-bottom:1px solid var(--line)}.tc-route-item:before{position:absolute;left:-58px;top:18px;width:10px;height:10px;content:"";border:2px solid var(--paper);border-radius:50%;background:var(--lake)}.tc-route-item time{font-size:12px;font-weight:900}.tc-route-item span{display:grid;gap:3px}.tc-route-item strong{font-family:"Iowan Old Style","Songti SC",serif;font-size:20px}.tc-route-item small{color:var(--muted)}.tc-selected-route aside{display:grid;align-content:start;gap:14px}.tc-planning-record{border-left:3px solid var(--sunset);padding-left:13px}.tc-planning-record h3{font-size:20px}.tc-planning-record p{margin:8px 0;color:var(--muted);font-size:13px}.tc-record-evidence{font-family:"STKaiti","KaiTi",serif}.tc-candidate-error{border-left:4px solid #9c3829;background:#fff1ef;padding:12px;color:#7c2f28}.tc-confirm-footer{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-top:32px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}@media(max-width:860px){.tc-page{padding:18px 18px 84px}.tc-input{grid-template-columns:1fr;min-height:auto;padding-top:8px}.tc-cover-copy{padding:8px 0}.tc-cover-image{min-height:480px;order:-1}.tc-cover-city{font-size:clamp(4rem,18vw,8rem)}.tc-cover-stamp{top:auto;bottom:0}.tc-confirm-page{padding-top:0}.tc-confirm-hero{min-height:410px;margin:0 -18px}.tc-confirm-hero-top{padding:18px}.tc-confirm-city{right:16px;bottom:14px}.tc-confirm-hero-copy{padding:0 18px 28px}.tc-trip-strip{overflow-x:auto;gap:10px;margin:0 -18px 30px;padding:14px 18px}.tc-trip-strip div{min-width:118px;padding:0 9px}.tc-confirm-layout,.tc-selected-route{grid-template-columns:1fr;gap:32px}.tc-confirm-aside{order:-1}.tc-readiness-note{min-height:150px;transform:none}.tc-candidate-grid{grid-template-columns:1fr}.tc-confirm-header{display:grid;align-items:start}.tc-confirm-footer{position:sticky;bottom:0;z-index:3;display:grid;padding:14px 0 max(12px,env(safe-area-inset-bottom));background:var(--paper)}}@media(max-width:560px){.tc-page h1{font-size:clamp(3rem,15vw,4.3rem)}.tc-cover-nav{font-size:9px}.tc-cover-lead{font-size:15px}.tc-composer{padding:15px}.tc-composer-heading{display:grid;gap:4px}.tc-composer-footer{display:grid;align-items:stretch}.tc-composer-footer .tc-primary{width:100%}.tc-cover-image{min-height:400px}.tc-cover-caption{left:18px;bottom:20px}.tc-cover-stamp{min-width:126px;padding:16px}.tc-cover-stamp b{font-size:30px}.tc-confirm-hero{min-height:370px}.tc-confirm-city b{font-size:clamp(4.2rem,23vw,7rem)}.tc-confirm-hero-copy h1{font-size:2.45rem}.tc-fixed-ticket{grid-template-columns:84px 1fr}.tc-fixed-ticket:before,.tc-fixed-ticket:after{left:84px}.tc-ticket-content{padding:16px}.tc-ticket-content strong{font-size:19px}.tc-ticket-lock{display:none}.tc-ledger-title{display:grid;align-items:start}.tc-place{grid-template-columns:38px 1fr}.tc-place-copy>strong{font-size:21px}.tc-day-route{padding-left:66px}.tc-day-route:before{left:22px}.tc-route-item:before{left:-51px}.tc-confirm-footer .tc-primary{width:100%}}@media(prefers-reduced-motion:reduce){.tc-primary,.tc-place-options button,.tc-candidate-card{transition:none}.tc-candidate-card:hover:not(:disabled),.tc-primary:hover:not(:disabled),.tc-place-options button:hover:not(:disabled){transform:none}}`}</style>; }
