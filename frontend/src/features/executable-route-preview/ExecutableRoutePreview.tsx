"use client";

import React, { useEffect, useMemo, useState } from "react";
import { getTripJson, postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import type { TripMetadata, TripRevisionMetadata } from "@/features/trip-workspace/tripPersistence";
import type { PlannerHandoffReviewSummary } from "@/features/preplan-intent/plannerTraceReviewModel";
import {
  buildDayLoads,
  buildUserFacingRisks,
  formatDistance,
  formatMinutes,
  type DayLoad,
  type RoutePreviewItinerary,
} from "./routePreviewModel";
import { buildFrozenHandoffEvidenceView } from "./frozenHandoffEvidenceModel";

type MutationPreviewResponse = {
  proposal: { id: string; proposal_digest: string };
  itinerary: RoutePreviewItinerary;
  impact_summary: {
    local_repair?: {
      action: "move";
      stop_name: string;
      from_day: number;
      to_day: number;
      ownership: "system_suggested";
      protected: { fixed_mutations: number; must_moves: number; must_deletions: number; full_planner_calls: number };
    };
  };
};

type MutationApplyResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  itinerary: RoutePreviewItinerary;
};

type PrePlanHandoffRunStatusResponse = {
  review_summary: PlannerHandoffReviewSummary;
};

type Props = {
  itinerary: RoutePreviewItinerary;
  variant: "draft" | "saved";
  tripId?: string;
  baseRevisionId?: string;
  plannerRunId?: string | null;
  onApplied?: (response: MutationApplyResponse) => void;
};

type RepairState =
  | { status: "idle" }
  | { status: "previewing"; day: number; before: DayLoad }
  | { status: "review"; day: number; before: DayLoad; preview: MutationPreviewResponse }
  | { status: "applying"; day: number; before: DayLoad; preview: MutationPreviewResponse }
  | { status: "error"; message: string };

export function ExecutableRoutePreview({
  itinerary,
  variant,
  tripId,
  baseRevisionId,
  plannerRunId,
  onApplied,
}: Props) {
  const loads = useMemo(() => buildDayLoads(itinerary), [itinerary]);
  const risks = useMemo(() => buildUserFacingRisks(itinerary, loads), [itinerary, loads]);
  const evidence = useMemo(() => buildRouteEvidence(itinerary), [itinerary]);
  const [repair, setRepair] = useState<RepairState>({ status: "idle" });
  const [frozenSummary, setFrozenSummary] = useState<PlannerHandoffReviewSummary | null>(null);
  const [frozenSummaryUnavailable, setFrozenSummaryUnavailable] = useState(false);
  const canRepair = variant === "saved" && Boolean(tripId && baseRevisionId && onApplied);
  const hasFrozenPrePlanRun = variant === "saved" && Boolean(tripId && plannerRunId?.startsWith("preplan_handoff_"));

  useEffect(() => {
    let active = true;
    if (!hasFrozenPrePlanRun || !tripId || !plannerRunId) {
      setFrozenSummary(null);
      setFrozenSummaryUnavailable(false);
      return () => { active = false; };
    }
    setFrozenSummary(null);
    setFrozenSummaryUnavailable(false);
    void getTripJson<PrePlanHandoffRunStatusResponse>(
      TRIP_API_ENDPOINTS.getPrePlanHandoffRunStatus(tripId, plannerRunId),
      "暂时无法读取这份已保存的规划依据。",
      "服务暂时不可用，路线内容仍可查看。",
    ).then((result) => {
      if (!active) return;
      if (result.ok) setFrozenSummary(result.data.review_summary);
      else setFrozenSummaryUnavailable(true);
    });
    return () => { active = false; };
  }, [hasFrozenPrePlanRun, plannerRunId, tripId]);

  async function previewRelaxation(day: number) {
    if (!tripId || !baseRevisionId) return;
    const before = loads.find((load) => load.day === day);
    if (!before) {
      setRepair({ status: "error", message: "暂时无法读取这一天的行程负载，当前行程没有被修改。" });
      return;
    }
    setRepair({ status: "previewing", day, before });
    const response = await postTripJson<MutationPreviewResponse>(
      TRIP_API_ENDPOINTS.previewLocalRelaxDayRepair(tripId),
      { base_revision_id: baseRevisionId, target_day: day, goal: "relax_day" },
      "暂时无法生成这次调整预览。当前行程没有被修改。",
      "服务暂时不可用，当前行程没有被修改。",
    );
    if (!response.ok) {
      setRepair({ status: "error", message: response.message });
      return;
    }
    setRepair({ status: "review", day, before, preview: response.data });
  }

  async function applyRelaxation(day: number, before: DayLoad, preview: MutationPreviewResponse) {
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
      setRepair({ status: "error", message: response.message });
      return;
    }
    onApplied(response.data);
    setRepair({ status: "idle" });
  }

  return (
    <section className="erp-shell" aria-label="可执行路线预览">
      <header className="erp-header">
        <div>
          <p>路线预览</p>
          <h2>{variant === "draft" ? "你的第一版行程" : "当前可执行路线"}</h2>
          <span>{variant === "draft" ? "确认后才会保存为正式行程。" : "每次确认调整都会保存为一个新版本。"}</span>
        </div>
        <div className="erp-header-summary">
          <strong>{itinerary.trip_days} 天</strong>
          <span>{loads.reduce((total, day) => total + day.activityCount, 0)} 个活动</span>
          <span>{loads.reduce((total, day) => total + day.fixedCount, 0)} 项固定安排</span>
        </div>
      </header>

      {risks.length ? <section className="erp-risks" role="alert"><strong>需要留意</strong>{risks.map((risk) => <p key={risk}>{risk}</p>)}</section> : null}

      <details className="erp-why" data-route-planning-evidence>
        <summary>查看规划依据</summary>
        {frozenSummary ? <FrozenPlanningEvidence summary={frozenSummary} handoffRunId={plannerRunId ?? ""} /> : <div>
          <p><strong>根据已保存路线内容归纳</strong></p>
          <p>{evidence.confirmedCount} 项来自你的地点或固定安排。</p>
          <p>{evidence.suggestedCount} 项系统补充是路线建议，不等同于已确认的事实。</p>
          {evidence.unexplainedCount ? <p>{evidence.unexplainedCount} 项暂时没有可验证的安排说明，已在地点卡片中明确标注。</p> : null}
          {hasFrozenPrePlanRun && frozenSummaryUnavailable ? <p>这份路线关联了冻结规划记录，但暂时无法读取其已保存依据。</p> : null}
        </div>}
      </details>

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
                {item.travel_from_name && item.travel_duration_s != null ? <div className="erp-leg"><span>预计移动</span><strong>{item.travel_from_name} → {item.name}</strong><small>{formatMinutes(Math.round(item.travel_duration_s / 60))}{item.travel_distance_m != null ? ` · ${formatDistance(item.travel_distance_m)}` : ""}</small></div> : null}
                <div className="erp-stop">
                  <time>{item.start_time}–{item.end_time}</time>
                  <div><div className="erp-stop-title"><strong>{item.name}</strong>{item.is_fixed ? <span className="erp-fixed">已预约 · 不可随意移动</span> : <span className="erp-kind">{isSystemSuggested(item) ? "系统补充" : item.source_label === "必去" ? "必去" : item.source_label === "可调整" ? "可调整" : item.type === "restaurant" ? "餐食" : item.type === "hotel" ? "住宿" : "用户地点"}</span>}</div>{item.placement_reason ? <p>{item.placement_reason}</p> : <p>暂时没有可验证的安排说明。</p>}</div>
                </div>
              </div>))}
            </div>
            <details className="erp-why"><summary>为什么这样安排</summary><DayReasons items={day.blocks.flatMap((block) => block.items)} /></details>
            {canRepair && load.pace === "rushed" ? <button className="erp-repair-button" type="button" onClick={() => void previewRelaxation(day.day)} disabled={repair.status === "previewing" || repair.status === "applying"}>{repair.status === "previewing" && repair.day === day.day ? "正在评估调整……" : "让这一天轻松一些"}</button> : null}
          </article>;
        })}
      </div>

      {repair.status === "review" || repair.status === "applying" ? <RepairReview repair={repair} onCancel={() => setRepair({ status: "idle" })} onApply={() => void applyRelaxation(repair.day, repair.before, repair.preview)} /> : null}
      {repair.status === "error" ? <p className="erp-error" role="alert">{repair.message}</p> : null}
      <RoutePreviewStyles />
    </section>
  );
}

function FrozenPlanningEvidence({ summary, handoffRunId }: { summary: PlannerHandoffReviewSummary; handoffRunId: string }) {
  const view = buildFrozenHandoffEvidenceView(summary, handoffRunId);
  return <div data-frozen-handoff-evidence>
    <p><strong>{view.title}</strong></p>
    <p>{view.intentLabel}</p>
    <p>{view.handoffLabel}</p>
    <p>{view.statusLabel}</p>
    <p>{view.readinessLabel}</p>
    <p>{view.traceLabel}</p>
    <p>{view.sourceBoundary}</p>
    <p>{view.heuristicBoundary}</p>
    <p>{view.providerBoundary}</p>
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function isSystemSuggested(item: RoutePreviewItinerary["days"][number]["blocks"][number]["items"][number]) {
  return item.source_type === "auto_seeded_poi" || item.source_type === "auto_seeded_meal" || item.source_type === "auto_filled";
}

function buildRouteEvidence(itinerary: RoutePreviewItinerary) {
  const items = itinerary.days.flatMap((day) => day.blocks.flatMap((block) => block.items));
  return {
    confirmedCount: items.filter((item) => item.is_fixed || item.source_type === "user_seed" || item.source_type === "user_fixed").length,
    suggestedCount: items.filter(isSystemSuggested).length,
    unexplainedCount: items.filter((item) => !item.placement_reason).length,
  };
}

function DayReasons({ items }: { items: RoutePreviewItinerary["days"][number]["blocks"][number]["items"] }) {
  const reasons = items.filter((item) => item.placement_reason).slice(0, 3);
  return <div>{reasons.length ? reasons.map((item) => <p key={item.stable_id ?? item.name}><strong>{item.name}</strong>{item.placement_reason}</p>) : <p>暂时没有可验证的安排说明。</p>}</div>;
}

function RepairReview({ repair, onCancel, onApply }: { repair: Extract<RepairState, { status: "review" | "applying" }>; onCancel: () => void; onApply: () => void }) {
  const afterLoad = buildDayLoads(repair.preview.itinerary).find((entry) => entry.day === repair.day);
  const summary = repair.preview.impact_summary.local_repair;
  return <section className="erp-repair-review" role="dialog" aria-modal="false" aria-label="调整预览"><p>调整预览</p><h3>让第 {repair.day} 天轻松一些</h3><div className="erp-repair-compare"><article><span>调整前</span><strong>{repair.before.activityCount} 个活动 · 移动 {formatMinutes(repair.before.travelMinutes)}</strong></article><article><span>调整后</span><strong>{afterLoad ? `${afterLoad.activityCount} 个活动 · 移动 ${formatMinutes(afterLoad.travelMinutes)}` : "已生成调整后的路线"}</strong></article></div><p>{summary ? `系统建议将“${summary.stop_name}”从第 ${summary.from_day} 天移动到第 ${summary.to_day} 天。` : "系统已生成一个只影响当天的安全调整。"}</p><p className="erp-protection">固定安排没有移动；你明确想去的地点没有删除；没有重新生成全部行程。</p><div><button type="button" onClick={onCancel} disabled={repair.status === "applying"}>取消</button><button type="button" className="erp-repair-button" onClick={onApply} disabled={repair.status === "applying"}>{repair.status === "applying" ? "正在应用……" : "应用这次调整"}</button></div></section>;
}

function RoutePreviewStyles() {
  return <style>{`
    .erp-shell{display:grid;gap:18px;margin:0 0 24px}.erp-header,.erp-day,.erp-repair-review{border:1px solid var(--ec-line);background:rgba(255,253,249,.94);box-shadow:var(--ec-shadow-2)}.erp-header{display:flex;justify-content:space-between;gap:18px;align-items:end;padding:24px 26px;border-radius:20px}.erp-header p,.erp-day-header p,.erp-repair-review>p:first-child{margin:0 0 5px;color:var(--ec-route-blue);font-size:12px;font-weight:900;letter-spacing:.08em}.erp-header h2,.erp-day h3,.erp-repair-review h3{margin:0;font-family:"Iowan Old Style",Georgia,serif;color:var(--ec-ink);letter-spacing:0}.erp-header h2{font-size:30px}.erp-header span,.erp-day-header span{color:var(--ec-slate);font-size:14px;line-height:1.55}.erp-header-summary{display:flex;gap:10px;flex-wrap:wrap;justify-content:end}.erp-header-summary>*{padding:7px 10px;border-radius:999px;background:rgba(21,21,21,.05);font-size:12px}.erp-risks{border:1px solid rgba(185,78,72,.35);background:rgba(255,244,242,.85);padding:16px 18px;border-radius:14px;color:#822b27}.erp-risks p{margin:6px 0 0;line-height:1.5}.erp-days{display:grid;gap:16px}.erp-day{border-radius:18px;padding:22px}.erp-day-header{display:flex;justify-content:space-between;gap:16px;align-items:start;padding-bottom:16px;border-bottom:1px solid var(--ec-line)}.erp-day-header h3{font-size:25px;margin-bottom:4px}.erp-pace{padding:7px 10px;border-radius:999px;font-size:12px;font-weight:900;white-space:nowrap}.erp-pace--relaxed{background:#e9f3e8;color:#3f6c43}.erp-pace--balanced{background:#edf2f7;color:#486273}.erp-pace--rushed{background:#fff1dd;color:#8b5e1f}.erp-pace--infeasible{background:#fde9e6;color:#9d302a}.erp-load-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:16px 0}.erp-load-grid div{padding:11px;border:1px solid var(--ec-line);border-radius:10px;background:rgba(247,244,238,.72)}.erp-load-grid span{display:block;font-size:11px;color:var(--ec-slate);font-weight:800}.erp-load-grid strong{font-size:14px;color:var(--ec-ink)}.erp-timeline{display:grid;gap:10px}.erp-timeline-row{display:grid;gap:8px}.erp-leg{margin-left:26px;padding:8px 10px;border-left:2px solid rgba(37,99,235,.35);display:grid;gap:2px;color:var(--ec-slate);font-size:12px}.erp-leg span{color:var(--ec-route-blue);font-weight:900}.erp-leg strong{color:var(--ec-ink);font-size:13px}.erp-stop{display:grid;grid-template-columns:98px minmax(0,1fr);gap:14px;padding:14px 12px;border-radius:10px;background:rgba(255,255,255,.76);border:1px solid rgba(21,21,21,.08)}.erp-stop time{font-weight:900;color:var(--ec-route-blue);font-size:13px}.erp-stop-title{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.erp-stop strong{color:var(--ec-ink);font-size:17px}.erp-stop p{margin:5px 0 0;color:var(--ec-slate);font-size:13px;line-height:1.55}.erp-fixed,.erp-kind{padding:4px 7px;border-radius:999px;font-size:11px;font-weight:900}.erp-fixed{background:rgba(117,91,40,.12);color:#76531f}.erp-kind{background:rgba(37,99,235,.08);color:#285eae}.erp-why{margin-top:14px;color:var(--ec-slate);font-size:13px}.erp-why summary{cursor:pointer;font-weight:900;color:var(--ec-ink)}.erp-why div{display:grid;gap:6px;margin-top:9px}.erp-why p{margin:0;line-height:1.55}.erp-why p strong{margin-right:5px;color:var(--ec-ink)}.erp-repair-button{border:0;border-radius:10px;padding:10px 13px;background:var(--ec-ink);color:#fff;font-weight:900;cursor:pointer;margin-top:16px}.erp-repair-button:disabled{opacity:.55;cursor:wait}.erp-repair-review{position:sticky;bottom:18px;z-index:4;border-radius:16px;padding:20px;max-width:640px}.erp-repair-review h3{font-size:24px}.erp-repair-compare{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0}.erp-repair-compare article{display:grid;gap:4px;padding:12px;border-radius:10px;background:rgba(247,244,238,.85)}.erp-repair-compare span{font-size:12px;color:var(--ec-slate);font-weight:800}.erp-repair-compare strong{color:var(--ec-ink);font-size:14px}.erp-repair-review>p{color:var(--ec-slate);line-height:1.55}.erp-repair-review .erp-protection{color:#48673f;font-weight:800}.erp-repair-review>div:last-child{display:flex;gap:10px;justify-content:end}.erp-repair-review>div:last-child button:first-child{border:1px solid var(--ec-line);background:#fff;color:var(--ec-ink);border-radius:10px;padding:10px 13px;font-weight:800}.erp-error{margin:0;color:#9d302a;font-weight:800}@media(max-width:720px){.erp-header{display:grid;align-items:start;padding:19px}.erp-header-summary{justify-content:start}.erp-day{padding:16px}.erp-load-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.erp-stop{grid-template-columns:1fr;gap:5px}.erp-day-header{display:grid}.erp-repair-compare{grid-template-columns:1fr}.erp-repair-review{bottom:8px}.erp-header h2{font-size:27px}}
  `}</style>;
}
