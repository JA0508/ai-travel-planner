"use client";

import React, { FormEvent, useEffect, useMemo, useState } from "react";

import { getTripJson, postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import { ExecutableRoutePreview } from "@/features/executable-route-preview/ExecutableRoutePreview";
import type { RoutePreviewItinerary } from "@/features/executable-route-preview/routePreviewModel";
import type { TripMetadata, TripRevisionMetadata } from "@/features/trip-workspace/tripPersistence";
import { PlanCandidateComparison, type PlanCandidateResponse, type PlanningRecord } from "./PlanCandidateComparison";

type Ownership = "user_fixed" | "user_must" | "user_optional" | "system_suggested";
type Pace = "relaxed" | "balanced" | "intensive";
type TripCompilerTripDays = 1 | 2 | 3;

type SourceFragment = { stable_id: string; text: string; source_type: "direct_user_text" | "user_confirmation"; start_offset?: number | null; end_offset?: number | null };
type Place = { stable_id: string; name: string; ownership: Ownership; confidence: number; source_fragment_ids: string[] };
type FixedEvent = { stable_id: string; name: string; day: number | null; start_time: string | null; end_time: string | null; fixed_reason: string; confidence: number; source_fragment_ids: string[] };
type Preference = { stable_id: string; value: string; confidence: number; source_fragment_ids: string[] };
type Constraint = { stable_id: string; value: string; kind: "availability" | "arrival" | "departure" | "avoid"; hard: boolean; source_fragment_ids: string[] };
type Unresolved = { stable_id: string; field: string; question: string; blocking: boolean; source_fragment_ids: string[] };
type TravelIntent = {
  contract_version: "1";
  destination: string | null;
  date_window: { start_date?: string | null; end_date?: string | null; arrival_time?: string | null; departure_time?: string | null };
  trip_days: TripCompilerTripDays | null;
  pace: Pace;
  must_visit_places: Place[];
  optional_places: Place[];
  fixed_events: FixedEvent[];
  preferences: Preference[];
  constraints: Constraint[];
  avoid_items: Constraint[];
  unresolved_items: Unresolved[];
  source_fragments: SourceFragment[];
  travel_mode: string | null;
};
type CompileResponse = { intent: TravelIntent; status: "ready" | "needs_confirmation" | "hard_conflict"; conflicts: string[]; conflict_cores: unknown[] };
type PlanResponse = { trip: TripMetadata; current_revision: TripRevisionMetadata; itinerary: RoutePreviewItinerary };
type CurrentTripResponse = { trip: TripMetadata; current_revision: TripRevisionMetadata; itinerary: RoutePreviewItinerary };
type PersistedPlanningRunResponse = PlanCandidateResponse & { confirmed_intent: TravelIntent; trip_id: string | null };

type WorkspaceState =
  | { status: "input" }
  | { status: "compiling" }
  | { status: "confirm"; intent: TravelIntent }
  | { status: "planning"; intent: TravelIntent }
  | { status: "restoring_run" }
  | { status: "expired_run" }
  | { status: "saved_run"; tripId: string }
  | { status: "candidates"; intent: TravelIntent; response: PlanCandidateResponse; selectedId: string; error: string | null; record: PlanningRecord | null }
  | { status: "selecting_candidate"; intent: TravelIntent; response: PlanCandidateResponse; selectedId: string; record: PlanningRecord | null }
  | { status: "route"; trip: TripMetadata; revision: TripRevisionMetadata; itinerary: RoutePreviewItinerary; intent: TravelIntent | null }
  | { status: "hard_conflict"; intent: TravelIntent; conflicts: string[] }
  | { status: "network_error"; message: string; returnTo: "input" | "confirm"; intent?: TravelIntent };

const EXAMPLES = [
  ["杭州两日轻松游", "周末去杭州玩两天，想去西湖和灵隐寺。朋友推荐龙井村，但不是必须。周六下午两点预约了中国茶叶博物馆。不想太赶，想吃本地小吃。周日晚上六点前要到杭州东站。"],
  ["上海固定预约", "去上海玩三天，想去上海博物馆、外滩和武康路。第二天下午两点到四点预约了上海博物馆，不能改。喜欢城市散步和本地小吃，不要太赶。"],
  ["西安景点较多", "我想去西安玩三天，主要想看历史文化。已经想去兵马俑、陕西历史博物馆、大雁塔和西安城墙。第一天中午到，第三天晚上坐火车离开，希望白天看景点，晚上安排吃饭和夜游，不要太赶。"],
] as const;

function asTripCompilerTripDays(value: number): TripCompilerTripDays | null {
  return value === 1 || value === 2 || value === 3 ? value : null;
}

export function TripCompilerWorkspace() {
  const [text, setText] = useState("");
  const [state, setState] = useState<WorkspaceState>({ status: "input" });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tripId = params.get("trip");
    const planningRunId = params.get("planning_run");
    if (tripId) void loadSavedTrip(tripId);
    else if (planningRunId) void loadPlanningRun(planningRunId);
  }, []);

  async function loadSavedTrip(tripId: string) {
    const result = await getTripJson<CurrentTripResponse>(TRIP_API_ENDPOINTS.getTrip(tripId), "暂时无法加载这份行程。", "无法连接后端接口。");
    if (!result.ok) {
      setState({ status: "network_error", message: result.message, returnTo: "input" });
      return;
    }
    setState({ status: "route", trip: result.data.trip, revision: result.data.current_revision, itinerary: result.data.itinerary, intent: null });
  }

  async function loadPlanningRun(runId: string) {
    setState({ status: "restoring_run" });
    const result = await getTripJson<PersistedPlanningRunResponse>(TRIP_API_ENDPOINTS.getTripCompilerPlanningRun(runId), "暂时无法恢复这批路线方案。", "无法连接后端接口。");
    if (!result.ok) {
      setState({ status: "network_error", message: result.message, returnTo: "input" });
      return;
    }
    if (result.data.status === "expired") {
      setState({ status: "expired_run" });
      return;
    }
    if (result.data.status === "selected" && result.data.trip_id) {
      setState({ status: "saved_run", tripId: result.data.trip_id });
      return;
    }
    setState({ status: "candidates", intent: result.data.confirmed_intent, response: result.data, selectedId: result.data.candidates[0]?.id ?? "", error: null, record: null });
  }

  async function compile(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    setState({ status: "compiling" });
    const result = await postTripJson<CompileResponse>(TRIP_API_ENDPOINTS.compileTripCompilerIntent, { text: text.trim() }, "暂时无法整理旅行想法。", "无法连接后端接口。");
    if (!result.ok) {
      setState({ status: "network_error", message: result.message, returnTo: "input" });
      return;
    }
    if (result.data.status === "hard_conflict") {
      setState({ status: "hard_conflict", intent: result.data.intent, conflicts: result.data.conflicts });
      return;
    }
    setState({ status: "confirm", intent: result.data.intent });
  }

  async function plan(intent: TravelIntent) {
    setState({ status: "planning", intent });
    const result = await postTripJson<PlanCandidateResponse>(
      TRIP_API_ENDPOINTS.generateTripCompilerCandidates,
      { intent },
      "暂时无法生成路线方案。你的确认信息还在这里。",
      "无法连接后端接口。",
    );
    if (!result.ok) {
      setState({ status: "network_error", message: result.message, returnTo: "confirm", intent });
      return;
    }
    window.history.replaceState({}, "", `/trip-compiler?planning_run=${encodeURIComponent(result.data.planning_run_id)}`);
    setState({ status: "candidates", intent, response: result.data, selectedId: result.data.candidates[0].id, error: null, record: null });
  }

  async function selectCandidate(intent: TravelIntent, response: PlanCandidateResponse, selectedId: string) {
    const candidate = response.candidates.find((item) => item.id === selectedId);
    if (!candidate) return;
    setState({ status: "selecting_candidate", intent, response, selectedId, record: null });
    const result = await postTripJson<PlanResponse>(
      TRIP_API_ENDPOINTS.selectTripCompilerCandidate(response.planning_run_id, candidate.id),
      { candidate_hash: candidate.candidate_hash, intent_digest: response.intent_digest },
      "暂时无法保存这条路线。你的路线方案还在这里。",
      "无法连接后端接口。",
      { headers: { "X-Idempotency-Key": `trip-candidate:${crypto.randomUUID()}` } },
    );
    if (!result.ok) {
      setState({ status: "candidates", intent, response, selectedId, error: result.message, record: null });
      return;
    }
    window.history.replaceState({}, "", `/trip-compiler?trip=${encodeURIComponent(result.data.trip.id)}`);
    setState({ status: "route", trip: result.data.trip, revision: result.data.current_revision, itinerary: result.data.itinerary, intent });
  }

  async function loadPlanningRecord(current: Extract<WorkspaceState, { status: "candidates" | "selecting_candidate" }>) {
    const result = await getTripJson<PlanningRecord>(TRIP_API_ENDPOINTS.getTripCompilerPlanningRecord(current.response.planning_run_id), "暂时无法读取规划记录。", "无法连接后端接口。");
    if (!result.ok) return;
    if (current.status === "candidates") setState({ ...current, record: result.data });
  }

  if (state.status === "route") {
    return <RouteScreen trip={state.trip} revision={state.revision} itinerary={state.itinerary} intent={state.intent} onApplied={(response) => setState({ status: "route", trip: response.trip, revision: response.current_revision, itinerary: response.itinerary, intent: state.intent })} />;
  }
  if (state.status === "restoring_run") {
    return <RunStatusScreen title="正在恢复你刚才比较的路线" detail="路线方案已经保存，不需要重新生成。" />;
  }
  if (state.status === "expired_run") {
    return <RunStatusScreen title="这批路线方案已经过期。" detail="为了避免使用旧数据，请重新生成。" action="重新生成路线方案" onAction={() => setState({ status: "input" })} />;
  }
  if (state.status === "saved_run") {
    return <RunStatusScreen title="这套路线已经保存。" detail="你可以继续查看和调整已保存的行程。" action="打开已保存行程" onAction={() => void loadSavedTrip(state.tripId)} />;
  }
  if (state.status === "candidates" || state.status === "selecting_candidate") {
    return <><PlanCandidateComparison response={state.response} selectedId={state.selectedId} busy={state.status === "selecting_candidate"} error={state.status === "candidates" ? state.error : null} record={state.record} onSelect={(selectedId) => state.status === "candidates" && setState({ ...state, selectedId, error: null })} onConfirm={() => selectCandidate(state.intent, state.response, state.selectedId)} onBack={() => setState({ status: "confirm", intent: state.intent })} onViewRecord={() => void loadPlanningRecord(state)} /><TripCompilerStyles /></>;
  }
  if (state.status === "confirm" || state.status === "planning") {
    return <IntentConfirmation intent={state.intent} busy={state.status === "planning"} onBack={() => setState({ status: "input" })} onPlan={plan} />;
  }
  if (state.status === "hard_conflict") {
    return <main className="tc-page"><section className="tc-conflict" role="alert"><p>暂时无法生成可执行路线</p><h1>当前安排存在冲突。</h1>{state.conflicts.map((conflict) => <p key={conflict}>{conflict}</p>)}<button type="button" onClick={() => setState({ status: "confirm", intent: state.intent })}>修改旅行信息</button></section><TripCompilerStyles /></main>;
  }
  if (state.status === "network_error") {
    return <main className="tc-page"><section className="tc-conflict" role="alert"><p>连接出现问题</p><h1>{state.message}</h1><button type="button" onClick={() => state.returnTo === "confirm" && state.intent ? setState({ status: "confirm", intent: state.intent }) : setState({ status: "input" })}>返回继续修改</button></section><TripCompilerStyles /></main>;
  }
  return <InputScreen text={text} onText={setText} onSubmit={compile} busy={state.status === "compiling"} />;
}

function RunStatusScreen({ title, detail, action, onAction }: { title: string; detail: string; action?: string; onAction?: () => void }) {
  return <main className="tc-page"><section className="tc-conflict tc-run-status" aria-live="polite"><p>路线方案</p><h1>{title}</h1><p>{detail}</p>{action && onAction ? <button type="button" onClick={onAction}>{action}</button> : null}</section><TripCompilerStyles /></main>;
}

function InputScreen({ text, onText, onSubmit, busy }: { text: string; onText: (value: string) => void; onSubmit: (event: FormEvent) => void; busy: boolean }) {
  return <main className="tc-page tc-input-page"><section className="tc-input-copy"><p className="tc-eyebrow">AI Trip Compiler</p><h1>把零散的旅行想法，变成一条能直接执行的路线。</h1><p>粘贴想去的地点、朋友推荐、固定预约和时间要求，系统会先替你整理，再生成行程。</p></section><form className="tc-composer" onSubmit={onSubmit}><label htmlFor="trip-compiler-input">这趟旅行，你已经知道些什么？</label><textarea id="trip-compiler-input" value={text} onChange={(event) => onText(event.target.value)} placeholder={EXAMPLES[0][1]} rows={13} disabled={busy} autoFocus /><button type="submit" disabled={busy || !text.trim()}>{busy ? "正在整理你的旅行想法" : "整理我的旅行想法"}</button><div className="tc-example-row" aria-label="可选示例">{EXAMPLES.map(([label, value]) => <button type="button" key={label} onClick={() => onText(value)} disabled={busy}>{label}</button>)}</div></form><TripCompilerStyles /></main>;
}

function IntentConfirmation({ intent: initialIntent, busy, onBack, onPlan }: { intent: TravelIntent; busy: boolean; onBack: () => void; onPlan: (intent: TravelIntent) => void }) {
  const [intent, setIntent] = useState(initialIntent);
  const [newPlace, setNewPlace] = useState("");
  const unresolvedBlocking = intent.unresolved_items.filter((item) => item.blocking);
  const fixedEventsFitTrip = intent.fixed_events.every((event) => event.day === null || (intent.trip_days !== null && event.day <= intent.trip_days));
  const canPlan = Boolean(intent.destination && intent.trip_days && fixedEventsFitTrip && unresolvedBlocking.length === 0);
  const source = intent.source_fragments[0];
  function updatePlace(place: Place, ownership: Ownership) {
    const confirmation = confirmationFragment(`你确认将“${place.name}”设为${ownership === "user_must" ? "必去" : "可调整"}地点。`);
    const updated = { ...place, ownership, source_fragment_ids: [...place.source_fragment_ids, confirmation.stable_id] };
    setIntent({ ...intent, source_fragments: [...intent.source_fragments, confirmation], must_visit_places: ownership === "user_must" ? [...intent.must_visit_places, updated] : intent.must_visit_places.filter((item) => item.stable_id !== place.stable_id), optional_places: ownership === "user_optional" ? [...intent.optional_places, updated] : intent.optional_places.filter((item) => item.stable_id !== place.stable_id), });
  }
  function removePlace(place: Place) { setIntent({ ...intent, must_visit_places: intent.must_visit_places.filter((item) => item.stable_id !== place.stable_id), optional_places: intent.optional_places.filter((item) => item.stable_id !== place.stable_id) }); }
  function addPlace() {
    const value = newPlace.trim();
    if (!value) return;
    const confirmation = confirmationFragment(`你新增“${value}”为可调整地点。`);
    setIntent({ ...intent, source_fragments: [...intent.source_fragments, confirmation], optional_places: [...intent.optional_places, { stable_id: `manual_${Date.now()}`, name: value, ownership: "user_optional", confidence: 1, source_fragment_ids: [confirmation.stable_id] }] });
    setNewPlace("");
  }
  return <main className="tc-page tc-confirm-page"><header className="tc-confirm-header"><div><p className="tc-eyebrow">确认行程信息</p><h1>这些是我从你的旅行想法里理解到的。</h1><p>确认重要信息，系统会以这些内容为基础规划路线。</p></div><button type="button" className="tc-link-button" onClick={onBack} disabled={busy}>返回修改原始描述</button></header><div className="tc-confirm-grid"><section className="tc-main-column"><section className="tc-section"><h2>基础信息</h2><div className="tc-field-grid"><label>目的地<input value={intent.destination ?? ""} onChange={(event) => setIntent({ ...intent, destination: event.target.value || null })} /></label><label>出行天数<input type="number" min="1" max="3" value={intent.trip_days ?? ""} onChange={(event) => setIntent({ ...intent, trip_days: event.target.value ? asTripCompilerTripDays(Number(event.target.value)) : null })} /><small>当前版本支持 1–3 天。</small></label><label>行程节奏<select value={intent.pace} onChange={(event) => setIntent({ ...intent, pace: event.target.value as Pace })}><option value="relaxed">轻松</option><option value="balanced">均衡</option><option value="intensive">紧凑</option></select></label></div></section><PlaceSection title="必去" subtitle="这些地点会被优先保留。" places={intent.must_visit_places} onMove={(place) => updatePlace(place, "user_optional")} onRemove={removePlace} moveLabel="改为可调整" /><PlaceSection title="想去，但可以调整" subtitle="时间不够时，系统会优先调整这些地点。" places={intent.optional_places} onMove={(place) => updatePlace(place, "user_must")} onRemove={removePlace} moveLabel="设为必去" /><section className="tc-section"><h2>新增地点</h2><div className="tc-inline-form"><input aria-label="新增地点" value={newPlace} onChange={(event) => setNewPlace(event.target.value)} placeholder="例如：龙井村" /><button type="button" onClick={addPlace}>加入为可调整</button></div></section><FixedEvents events={intent.fixed_events} tripDays={intent.trip_days} onChange={(events) => setIntent({ ...intent, fixed_events: events })} /><section className="tc-section"><h2>偏好</h2><div className="tc-token-list">{intent.preferences.map((item) => <span key={item.stable_id}>{item.value}<button aria-label={`删除偏好 ${item.value}`} type="button" onClick={() => setIntent({ ...intent, preferences: intent.preferences.filter((preference) => preference.stable_id !== item.stable_id) })}>×</button></span>) || <p>暂未识别到明确偏好。</p>}</div></section></section><aside className="tc-side-column"><section className="tc-section"><h2>限制条件</h2>{intent.constraints.length ? <ul className="tc-plain-list">{intent.constraints.map((item) => <li key={item.stable_id}>{item.value}</li>)}</ul> : <p>暂未识别到额外时间限制。</p>}</section>{intent.avoid_items.length ? <section className="tc-section"><h2>需要避开</h2><ul className="tc-plain-list">{intent.avoid_items.map((item) => <li key={item.stable_id}>{item.value}</li>)}</ul></section> : null}<section className="tc-section tc-confirm-needed"><h2>还需要你确认</h2>{intent.unresolved_items.length ? <ul>{intent.unresolved_items.map((item) => <li className={item.blocking ? "tc-blocking" : ""} key={item.stable_id}>{item.question}</li>)}</ul> : <p>关键信息已经齐全。</p>}</section>{source ? <details className="tc-source"><summary>查看来源</summary><p>{source.text}</p></details> : null}</aside></div><footer className="tc-confirm-footer"><span>{canPlan ? "确认后会开始计算时间、地点和交通衔接。" : !fixedEventsFitTrip ? "固定安排要落在本次旅行的天数范围内。" : "请先补充标注为必填的信息。"}</span><button type="button" className="tc-primary" onClick={() => onPlan(intent)} disabled={!canPlan || busy}>{busy ? "正在计算时间、地点和交通衔接" : "生成我的行程骨架"}</button></footer><TripCompilerStyles /></main>;
}

function confirmationFragment(text: string): SourceFragment {
  let hash = 2166136261;
  for (const character of text) hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  return { stable_id: `user_confirmation_${(hash >>> 0).toString(16)}`, text, source_type: "user_confirmation" };
}

function PlaceSection({ title, subtitle, places, onMove, onRemove, moveLabel }: { title: string; subtitle: string; places: Place[]; onMove: (place: Place) => void; onRemove: (place: Place) => void; moveLabel: string }) {
  return <section className="tc-section"><h2>{title}</h2><p>{subtitle}</p>{places.length ? <ul className="tc-place-list">{places.map((place) => <li key={place.stable_id}><strong>{place.name}</strong><span><button type="button" onClick={() => onMove(place)}>{moveLabel}</button><button type="button" onClick={() => onRemove(place)}>删除</button></span></li>)}</ul> : <p className="tc-empty">暂未添加。</p>}</section>;
}

function FixedEvents({ events, tripDays, onChange }: { events: FixedEvent[]; tripDays: TripCompilerTripDays | null; onChange: (events: FixedEvent[]) => void }) {
  return <section className="tc-section"><h2>固定安排</h2><p>这些时间不能被系统随意移动。</p>{events.length ? <div className="tc-fixed-list">{events.map((event) => <div key={event.stable_id}><strong>{event.name}</strong><span className="tc-fixed-reason">{event.fixed_reason}</span><label>第几天<input type="number" min="1" max={tripDays ?? 3} value={event.day ?? ""} onChange={(change) => onChange(events.map((item) => item.stable_id === event.stable_id ? { ...item, day: change.target.value ? Number(change.target.value) : null } : item))} /></label><label>开始<input type="time" value={event.start_time ?? ""} onChange={(change) => onChange(events.map((item) => item.stable_id === event.stable_id ? { ...item, start_time: change.target.value || null } : item))} /></label><label>结束<input type="time" value={event.end_time ?? ""} onChange={(change) => onChange(events.map((item) => item.stable_id === event.stable_id ? { ...item, end_time: change.target.value || null } : item))} /></label><button type="button" onClick={() => onChange(events.filter((item) => item.stable_id !== event.stable_id))}>删除</button></div>)}</div> : <p className="tc-empty">暂未识别到固定安排。</p>}</section>;
}

function RouteScreen({ trip, revision, itinerary, intent, onApplied }: { trip: TripMetadata; revision: TripRevisionMetadata; itinerary: RoutePreviewItinerary; intent: TravelIntent | null; onApplied: (response: { trip: TripMetadata; current_revision: TripRevisionMetadata; itinerary: RoutePreviewItinerary }) => void }) {
  const summary = useMemo(() => ({ must: intent?.must_visit_places.length ?? 0, fixed: intent?.fixed_events.length ?? 0, additions: itinerary.days.flatMap((day) => day.blocks.flatMap((block) => block.items)).filter((item) => item.source_type === "auto_seeded_meal" || item.source_type === "auto_seeded_poi" || item.source_type === "auto_filled").length }), [intent, itinerary]);
  return <main className="tc-page tc-route-page"><header className="tc-route-header"><div><p className="tc-eyebrow">行程骨架</p><h1>{intent?.destination ?? "这次旅行"} · {itinerary.trip_days} 天</h1><p>{intent?.pace === "relaxed" ? "轻松节奏" : intent?.pace === "intensive" ? "紧凑节奏" : "均衡节奏"}</p><span>{summary.must} 个必去地点 · {summary.fixed} 个固定安排 · {summary.additions} 个系统补充</span></div><button type="button" className="tc-saved" disabled>行程已保存</button></header><ExecutableRoutePreview itinerary={itinerary} variant="saved" tripId={trip.id} baseRevisionId={revision.id} onApplied={onApplied} /><TripCompilerStyles /></main>;
}

function TripCompilerStyles() {
  return <style>{`
    .tc-page{--tc-ink:#182126;--tc-muted:#637078;--tc-line:#d9ded8;--tc-paper:#fffefa;--tc-warm:#f5f1e8;--tc-accent:#356f62;max-width:1120px;margin:0 auto;padding:72px 28px 112px;color:var(--tc-ink)}.tc-input-page{min-height:calc(100vh - 78px);display:grid;grid-template-columns:minmax(0,.9fr) minmax(460px,1.1fr);align-items:center;gap:62px}.tc-eyebrow{margin:0 0 12px;color:var(--tc-accent);font-size:12px;font-weight:800;letter-spacing:.1em;text-transform:uppercase}.tc-input-copy h1,.tc-confirm-header h1,.tc-route-header h1,.tc-conflict h1{margin:0;font-family:Georgia,"Times New Roman",serif;font-size:clamp(38px,4vw,61px);line-height:1.05;letter-spacing:0}.tc-input-copy>p:not(.tc-eyebrow),.tc-confirm-header>div>p:not(.tc-eyebrow),.tc-route-header p{color:var(--tc-muted);font-size:17px;line-height:1.7}.tc-composer,.tc-section,.tc-conflict,.tc-route-header,.tc-candidate-card,.tc-selected-route{border:1px solid var(--tc-line);border-radius:8px;background:var(--tc-paper)}.tc-composer{padding:22px;box-shadow:0 18px 40px rgba(37,44,38,.07)}.tc-composer label,.tc-section h2{display:block;margin:0 0 10px;font-size:15px;font-weight:800}.tc-composer textarea{width:100%;min-height:300px;box-sizing:border-box;resize:vertical;border:0;border-bottom:1px solid var(--tc-line);background:transparent;padding:8px 0 17px;color:var(--tc-ink);font:inherit;font-size:16px;line-height:1.65;outline:none}.tc-composer textarea:focus{border-color:var(--tc-accent)}.tc-primary,.tc-composer>button{margin-top:18px;border:0;border-radius:7px;background:var(--tc-ink);color:white;padding:14px 18px;font:inherit;font-weight:800;cursor:pointer}.tc-primary:disabled,.tc-composer>button:disabled{opacity:.5;cursor:wait}.tc-example-row{display:flex;flex-wrap:wrap;gap:8px;margin-top:17px}.tc-example-row button,.tc-link-button,.tc-place-list button,.tc-fixed-list button,.tc-inline-form button{border:0;background:none;color:var(--tc-accent);font:inherit;font-size:13px;font-weight:700;cursor:pointer;padding:3px}.tc-confirm-page,.tc-route-page{max-width:1160px}.tc-confirm-header,.tc-route-header{display:flex;justify-content:space-between;gap:28px;align-items:flex-end;margin-bottom:26px}.tc-confirm-header{padding:0 0 26px;border-bottom:1px solid var(--tc-line)}.tc-confirm-header h1{font-size:42px}.tc-link-button{white-space:nowrap;border-bottom:1px solid currentColor}.tc-confirm-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(260px,.7fr);gap:18px}.tc-main-column,.tc-side-column{display:grid;align-content:start;gap:16px}.tc-section{padding:20px}.tc-section>p{margin:0 0 14px;color:var(--tc-muted);line-height:1.55}.tc-field-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.tc-field-grid label,.tc-fixed-list label{display:grid;gap:6px;color:var(--tc-muted);font-size:12px;font-weight:700}.tc-field-grid input,.tc-field-grid select,.tc-inline-form input,.tc-fixed-list input{box-sizing:border-box;min-width:0;width:100%;border:1px solid var(--tc-line);border-radius:5px;background:#fff;padding:9px;color:var(--tc-ink);font:inherit}.tc-place-list,.tc-plain-list{list-style:none;margin:0;padding:0}.tc-place-list{display:grid;gap:8px}.tc-place-list li{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-top:1px solid #edf0ec}.tc-place-list span{display:flex;gap:8px}.tc-empty{color:var(--tc-muted)}.tc-inline-form{display:flex;gap:8px}.tc-inline-form button{border:1px solid var(--tc-line);border-radius:5px;white-space:nowrap;padding:8px 10px}.tc-fixed-list{display:grid;gap:10px}.tc-fixed-list>div{display:grid;grid-template-columns:1.2fr repeat(3,minmax(82px,.55fr)) auto;gap:8px;align-items:end;padding:12px;background:var(--tc-warm);border-radius:6px}.tc-fixed-list strong{padding-bottom:8px}.tc-token-list{display:flex;gap:7px;flex-wrap:wrap}.tc-token-list span{display:flex;gap:6px;align-items:center;border-radius:999px;background:#e7eee9;color:#315e50;padding:6px 9px;font-size:13px}.tc-token-list button{border:0;background:none;color:inherit;cursor:pointer;font-size:16px;line-height:1}.tc-plain-list{display:grid;gap:9px;color:var(--tc-muted);line-height:1.5}.tc-plain-list li{padding-left:12px;border-left:2px solid #c5d8d1}.tc-confirm-needed{background:#fbf7ef}.tc-confirm-needed ul{display:grid;gap:10px;margin:0;padding-left:20px;line-height:1.5}.tc-blocking{color:#9b372f;font-weight:700}.tc-source{font-size:13px;color:var(--tc-muted)}.tc-source summary{cursor:pointer;font-weight:800;color:var(--tc-ink)}.tc-source p{white-space:pre-wrap;line-height:1.6}.tc-confirm-footer{position:sticky;bottom:14px;display:flex;justify-content:space-between;align-items:center;gap:18px;margin-top:22px;padding:14px 16px;border:1px solid var(--tc-line);border-radius:8px;background:rgba(255,254,250,.96);box-shadow:0 12px 28px rgba(24,33,38,.1);color:var(--tc-muted);font-size:14px}.tc-route-header{padding:28px 30px}.tc-route-header h1{font-size:42px}.tc-route-header span{color:var(--tc-muted);font-size:14px}.tc-saved{border:1px solid #bcd0c3;border-radius:999px;background:#edf6ef;color:#386347;padding:9px 12px;font-weight:800;white-space:nowrap}.tc-conflict{max-width:700px;margin:12vh auto;padding:34px}.tc-conflict>p:first-child{margin:0 0 10px;color:#9b372f;font-weight:800}.tc-conflict h1{font-size:42px;margin-bottom:18px}.tc-conflict button{border:0;border-radius:7px;background:var(--tc-ink);color:#fff;padding:12px 15px;font-weight:800;cursor:pointer;margin-top:14px}.tc-candidate-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.tc-candidate-card{display:grid;gap:12px;text-align:left;padding:20px;color:var(--tc-ink);font:inherit;cursor:pointer;transition:border-color .15s,transform .15s}.tc-candidate-card:hover,.tc-candidate-card:focus-visible,.tc-candidate-card.is-selected{border-color:var(--tc-accent);outline:none}.tc-candidate-card.is-selected{box-shadow:inset 0 0 0 1px var(--tc-accent);background:#f5faf7}.tc-candidate-card strong{font-family:Georgia,"Times New Roman",serif;font-size:25px}.tc-candidate-card>span:not(.tc-candidate-tag){color:var(--tc-muted);line-height:1.5}.tc-candidate-tag{width:max-content;color:var(--tc-accent);font-size:12px;font-weight:800}.tc-candidate-card dl{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:4px 0}.tc-candidate-card dl div{background:var(--tc-warm);padding:8px}.tc-candidate-card dt{color:var(--tc-muted);font-size:11px}.tc-candidate-card dd{margin:4px 0 0;font-weight:800}.tc-candidate-card ul{margin:0;padding-left:16px;color:var(--tc-muted);font-size:13px;line-height:1.55}.tc-selected-route{display:grid;gap:14px;margin-top:18px;padding:22px}.tc-selected-route h2{margin:0;font-family:Georgia,"Times New Roman",serif;font-size:29px}.tc-selected-route p{color:var(--tc-muted);line-height:1.6}.tc-candidate-error{margin:14px 0;color:#9b372f;font-weight:700}@media(max-width:760px){.tc-page{padding:38px 16px 92px}.tc-input-page{display:grid;grid-template-columns:1fr;gap:30px;align-content:start}.tc-input-copy h1{font-size:42px}.tc-composer{padding:16px}.tc-composer textarea{min-height:250px}.tc-confirm-header,.tc-route-header{display:grid;align-items:start}.tc-confirm-header h1,.tc-route-header h1{font-size:35px}.tc-confirm-grid,.tc-candidate-grid{grid-template-columns:1fr}.tc-field-grid{grid-template-columns:1fr}.tc-fixed-list>div{grid-template-columns:1fr 1fr}.tc-fixed-list strong{grid-column:1/-1}.tc-confirm-footer{align-items:start;display:grid;bottom:8px}.tc-confirm-footer .tc-primary{width:100%;margin:0}.tc-route-header{padding:21px}.tc-inline-form{display:grid}.tc-inline-form button{width:max-content}.tc-place-list li{display:grid}.tc-place-list span{justify-content:start}.tc-conflict{margin:7vh auto}.tc-conflict h1{font-size:34px}}
  `}</style>;
}
