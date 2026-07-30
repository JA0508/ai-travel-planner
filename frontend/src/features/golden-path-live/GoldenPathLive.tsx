"use client";

import { useState } from "react";
import { postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import { formatDuration, ownershipFor, type AppliedHandoff, type HandoffPreview, type LiveItinerary, type RepairApplied, type RepairPreview } from "./goldenPathTypes";

type State =
  | { kind: "idle" }
  | { kind: "compiling_intent" }
  | { kind: "confirming"; tripId: string; intentId: string; text: string }
  | { kind: "planning"; tripId: string; intentId: string }
  | { kind: "route_ready"; tripId: string; revisionId: string; itinerary: LiveItinerary }
  | { kind: "repair_loading"; tripId: string; revisionId: string; itinerary: LiveItinerary; day: number }
  | { kind: "repair_review"; tripId: string; revisionId: string; itinerary: LiveItinerary; repair: RepairPreview }
  | { kind: "repair_applying"; tripId: string; revisionId: string; itinerary: LiveItinerary; repair: RepairPreview }
  | { kind: "repair_applied"; tripId: string; revisionId: string; itinerary: LiveItinerary }
  | { kind: "hard_conflict"; message: string }
  | { kind: "stale"; message: string }
  | { kind: "error"; message: string };

const initialText = "周末去杭州玩两天，轻松一点，想去西湖和灵隐寺。";

export function GoldenPathLive() {
  const [text, setText] = useState(initialText);
  const [state, setState] = useState<State>({ kind: "idle" });

  async function begin() {
    setState({ kind: "compiling_intent" });
    const draftKey = `golden-draft:${crypto.randomUUID()}`;
    const created = await postTripJson<{ trip: { id: string } }>(TRIP_API_ENDPOINTS.createDraftTrip, { direct_user_text: text }, "暂时无法保存这次旅行想法。", "无法连接后端接口。", { headers: { "X-Idempotency-Key": draftKey } });
    if (!created.ok) return setState({ kind: "error", message: created.message });
    const compiled = await postTripJson<{ revision: { id: string } }>(TRIP_API_ENDPOINTS.compilePrePlanIntent(created.data.trip.id), { base_trip_revision_id: null, base_intent_revision_id: null, direct_user_text: text, use_llm_proposal_adapter: true }, "暂时无法理解这次旅行。", "无法连接后端接口。", { headers: { "X-Idempotency-Key": `golden-intent:${created.data.trip.id}` } });
    if (!compiled.ok) return setState({ kind: "error", message: compiled.message });
    setState({ kind: "confirming", tripId: created.data.trip.id, intentId: compiled.data.revision.id, text });
  }

  async function plan(current: Extract<State, { kind: "confirming" }>) {
    setState({ kind: "planning", tripId: current.tripId, intentId: current.intentId });
    const preview = await postTripJson<HandoffPreview>(TRIP_API_ENDPOINTS.previewPrePlanHandoff(current.tripId), { draft_intent_revision_id: current.intentId }, "暂时无法生成路线预览。");
    if (!preview.ok) return setState(preview.code === "planner_handoff_blocked" ? { kind: "hard_conflict", message: preview.message } : { kind: "error", message: preview.message });
    const applied = await postTripJson<AppliedHandoff>(TRIP_API_ENDPOINTS.applyPrePlanHandoff(current.tripId, preview.data.handoff.id), { draft_intent_revision_id: current.intentId, handoff_digest: preview.data.handoff.trace_digest }, "暂时无法保存这版路线。", "无法连接后端接口。", { headers: { "X-Idempotency-Key": `golden-plan:${preview.data.handoff.id}` } });
    if (!applied.ok) return setState({ kind: "error", message: applied.message });
    setState({ kind: "route_ready", tripId: current.tripId, revisionId: applied.data.current_revision.id, itinerary: applied.data.itinerary });
  }

  async function repair(tripId: string, revisionId: string, itinerary: LiveItinerary, day: number) {
    setState({ kind: "repair_loading", tripId, revisionId, itinerary, day });
    const response = await postTripJson<RepairPreview>(TRIP_API_ENDPOINTS.previewGoldenPathRepair(tripId), { base_revision: revisionId, target_day: day, goal: "relax_day" }, "暂时无法评估这一小段调整。");
    if (!response.ok) return setState(response.code?.includes("stale") ? { kind: "stale", message: response.message } : { kind: "error", message: response.message });
    setState({ kind: "repair_review", tripId, revisionId, itinerary, repair: response.data });
  }

  async function applyRepair(current: Extract<State, { kind: "repair_review" }>) {
    setState({ ...current, kind: "repair_applying" });
    const proposal = current.repair.proposal;
    const response = await postTripJson<RepairApplied>(TRIP_API_ENDPOINTS.applyGoldenPathRepair(current.tripId, proposal.proposal_id), { base_revision: current.revisionId, proposal_digest: proposal.proposal_digest }, "暂时无法应用这次调整。当前路线没有变。", "无法连接后端接口。", { headers: { "X-Idempotency-Key": `golden-repair:${proposal.proposal_id}` } });
    if (!response.ok) return setState(response.code?.includes("stale") ? { kind: "stale", message: response.message } : { kind: "error", message: response.message });
    setState({ kind: "repair_applied", tripId: current.tripId, revisionId: response.data.current_revision.id, itinerary: response.data.itinerary });
  }

  if (state.kind === "idle" || state.kind === "compiling_intent") return <main className="gp-page"><section className="gp-intro"><p>行程草图</p><h1>这趟旅行，<br />你想怎么过？</h1><label>你的旅行想法<textarea aria-label="你的旅行想法" value={text} onChange={(event) => setText(event.target.value)} /></label><button type="button" onClick={() => void begin()} disabled={state.kind === "compiling_intent"}>{state.kind === "compiling_intent" ? "正在理解……" : "看看我理解得对不对"}</button></section><GoldenStyles /></main>;
  if (state.kind === "confirming") return <main className="gp-page"><section className="gp-card"><p>确认行程信息</p><h1>这次旅行，我这样理解。</h1><dl><div><dt>你的原话</dt><dd>{state.text}</dd></div><div><dt>接下来</dt><dd>生成前会按目的地、时间和固定安排进行确定性校验。</dd></div></dl><button type="button" onClick={() => void plan(state)}>生成我的路线</button></section><GoldenStyles /></main>;
  if (state.kind === "planning") return <main className="gp-page"><section className="gp-card"><h1>正在生成路线</h1><p>先按已确认的信息安排，再保存第一版行程。</p></section><GoldenStyles /></main>;
  if (isRouteState(state)) {
    const current = state;
    return <main className="gp-page"><Route itinerary={current.itinerary} onRepair={(day) => void repair(current.tripId, current.revisionId, current.itinerary, day)} disabled={current.kind === "repair_loading" || current.kind === "repair_applying"} applied={current.kind === "repair_applied"} />{(current.kind === "repair_review" || current.kind === "repair_applying") ? <RepairDialog repair={current.repair} applying={current.kind === "repair_applying"} onCancel={() => setState({ kind: "route_ready", tripId: current.tripId, revisionId: current.revisionId, itinerary: current.itinerary })} onApply={() => void applyRepair(current as Extract<State, { kind: "repair_review" }>)} /> : null}<GoldenStyles /></main>;
  }
  return <main className="gp-page"><section className="gp-card" role="alert"><h1>{state.kind === "hard_conflict" ? "这版路线还不能生成" : "暂时没有完成"}</h1><p>{state.message}</p><button type="button" onClick={() => setState({ kind: "idle" })}>重新开始</button></section><GoldenStyles /></main>;
}

function isRouteState(state: State): state is Extract<State, { itinerary: LiveItinerary }> {
  return state.kind === "route_ready" || state.kind === "repair_loading" || state.kind === "repair_review" || state.kind === "repair_applying" || state.kind === "repair_applied";
}

function Route({ itinerary, onRepair, disabled, applied }: { itinerary: LiveItinerary; onRepair: (day: number) => void; disabled: boolean; applied: boolean }) { return <section className="gp-route" aria-label="可执行路线"><header><p>你的路线</p><h1>{itinerary.trip_days} 天行程</h1>{applied ? <strong>已保存为新版本</strong> : null}</header>{itinerary.planner_realism?.issues.filter((issue) => issue.severity === "high").map((issue) => <aside key={issue.code}>{issue.title}：{issue.detail}</aside>)}{itinerary.days.map((day) => { const load = itinerary.planner_realism?.daily_loads.find((entry) => entry.day === day.day); return <article className="gp-day" key={day.day}><header><p>DAY {day.day}</p><h2>{load?.classification === "rushed" ? "这一天偏赶" : load?.classification === "relaxed" ? "这一天比较轻松" : "这一天节奏合适"}</h2><span>{load?.explanation}</span></header>{day.blocks.flatMap((block) => block.items).map((item) => <div className="gp-stop" key={item.stable_id ?? `${item.name}-${item.start_time}`}><time>{item.start_time}–{item.end_time}</time><div><span className={`gp-source gp-${ownershipFor(item)}`}>{({ user_must: "你想去", user_fixed: "已预约", user_optional: "你的备选", system_suggested: "顺路建议" } as const)[ownershipFor(item)]}</span><h3>{item.name}</h3>{item.travel_from_name ? <p>从 {item.travel_from_name} 出发 · {formatDuration(item.travel_duration_s)}</p> : null}{item.placement_reason ? <p>{item.placement_reason}</p> : <p>暂无明确安排依据</p>}</div></div>)}{load?.classification === "rushed" ? <button type="button" disabled={disabled} onClick={() => onRepair(day.day)}>{disabled ? "正在评估……" : "让这一天轻松一些"}</button> : null}</article>; })}</section>; }

function RepairDialog({ repair, applying, onCancel, onApply }: { repair: RepairPreview; applying: boolean; onCancel: () => void; onApply: () => void }) { const proposal = repair.proposal; const before = proposal.before.planner_realism?.daily_loads.find((load) => load.day === proposal.from_day); const after = proposal.after.planner_realism?.daily_loads.find((load) => load.day === proposal.from_day); return <section className="gp-dialog" role="dialog" aria-label="调整前后对比"><p>只调整一小段</p><h2>让第 {proposal.from_day} 天轻松一些</h2><div><article><strong>调整前</strong><span>{before?.activity_count} 个安排 · 移动 {before?.travel_minutes} 分钟</span></article><article><strong>调整后</strong><span>{after?.activity_count} 个安排 · 移动 {after?.travel_minutes} 分钟</span></article></div><p>“{proposal.moved_activity_name}”将从第 {proposal.from_day} 天移到第 {proposal.to_day} 天。</p><p>{proposal.protection_summary}</p><footer><button type="button" onClick={onCancel} disabled={applying}>暂不调整</button><button type="button" onClick={onApply} disabled={applying}>{applying ? "正在保存……" : "应用这次调整"}</button></footer></section>; }

function GoldenStyles() { return <style>{`.gp-page{min-height:100vh;padding:clamp(24px,6vw,88px);background:#f7f3eb;color:#171717;font-family:Arial,"PingFang SC",sans-serif}.gp-intro,.gp-card,.gp-route{max-width:940px;margin:auto}.gp-intro{display:grid;gap:18px;max-width:720px}.gp-intro>p,.gp-card>p,.gp-route header>p,.gp-dialog>p{font-size:12px;font-weight:800;color:#416764}.gp-page h1,.gp-page h2,.gp-page h3{font-family:Georgia,"Songti SC",serif;margin:0;letter-spacing:0}.gp-intro h1{font-size:clamp(42px,7vw,72px);line-height:.98}.gp-page label{display:grid;gap:8px;font-weight:800}.gp-page textarea{min-height:160px;padding:16px;border:1px solid #d8d0c3;border-radius:10px;font:inherit;line-height:1.7;background:#fffdfa}.gp-page button{border:0;border-radius:9px;background:#1d2b2a;color:#fff;padding:12px 17px;font-weight:800;cursor:pointer;width:max-content}.gp-page button:disabled{opacity:.6}.gp-card{padding:36px;border:1px solid #d8d0c3;background:#fffdfa;border-radius:12px;display:grid;gap:18px}.gp-card dl{display:grid;gap:14px;margin:0}.gp-card dl div{padding:14px;background:#f5f0e7}.gp-card dt{font-weight:800}.gp-card dd{margin:7px 0 0;line-height:1.65}.gp-route{display:grid;gap:18px}.gp-route>header{padding-bottom:18px;border-bottom:1px solid #d8d0c3}.gp-route>header strong{display:inline-block;margin-top:10px;color:#416764}.gp-route aside{padding:14px;border:1px solid #d99b93;background:#fff4f2;color:#7f302a;border-radius:8px}.gp-day{padding:24px;border:1px solid #d8d0c3;border-radius:12px;background:#fffdfa;display:grid;gap:13px}.gp-day>header{display:grid;gap:5px}.gp-day header span,.gp-stop p{color:#64706e;line-height:1.5;margin:0}.gp-stop{display:grid;grid-template-columns:108px 1fr;gap:12px;padding:14px 0;border-top:1px solid #ebe5da}.gp-stop time{font-weight:800;color:#416764}.gp-stop h3{display:inline;margin-left:8px;font-size:19px}.gp-source{font-size:11px;padding:4px 7px;border-radius:99px;font-weight:800}.gp-user_must{background:#e9f0ed;color:#355d56}.gp-user_fixed{background:#f4e9dc;color:#76531f}.gp-user_optional{background:#eceff2;color:#56616e}.gp-system_suggested{background:#e8eff8;color:#355d83}.gp-dialog{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);width:min(640px,calc(100vw - 32px));padding:23px;border:1px solid #d8d0c3;border-radius:12px;background:#fffdfa;box-shadow:0 18px 70px #0003;z-index:2}.gp-dialog h2{font-size:28px}.gp-dialog>div{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:16px 0}.gp-dialog article{padding:12px;background:#f5f0e7;display:grid;gap:5px}.gp-dialog footer{display:flex;justify-content:flex-end;gap:10px}.gp-dialog footer button:first-child{background:#fff;color:#1d2b2a;border:1px solid #bfb5a4}@media(max-width:640px){.gp-page{padding:28px 16px}.gp-stop{grid-template-columns:1fr}.gp-dialog>div{grid-template-columns:1fr}.gp-intro h1{font-size:46px}}`}</style>; }
