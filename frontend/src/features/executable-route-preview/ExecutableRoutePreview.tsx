"use client";

import React, { useMemo, useRef, useState } from "react";
import { postTripJson } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import type { TripMetadata, TripRevisionMetadata } from "@/features/trip-workspace/tripPersistence";
import {
  buildDayLoads,
  buildUserFacingRisks,
  formatDistance,
  formatMinutes,
  type RoutePreviewItinerary,
} from "./routePreviewModel";
import { RoadbookRepairPreview } from "./RoadbookRepairPreview";
import {
  isRepairStaleCode,
  repairFailureMessage,
  type LocalRepairImpact,
} from "./repairPreviewModel";
import { SavedLivingRoadbook } from "./SavedLivingRoadbook";

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

type Props = {
  itinerary: RoutePreviewItinerary;
  variant: "draft" | "saved";
  tripId?: string;
  baseRevisionId?: string;
  onApplied?: (response: MutationApplyResponse) => void;
  destination?: string | null;
};

type RepairState =
  | { status: "idle" }
  | { status: "previewing"; day: number }
  | { status: "review"; day: number; before: RoutePreviewItinerary; preview: MutationPreviewResponse }
  | { status: "applying"; day: number; before: RoutePreviewItinerary; preview: MutationPreviewResponse }
  | { status: "applied"; day: number; revisionId: string; undoing: boolean; errorMessage?: string }
  | { status: "restored" }
  | { status: "error"; message: string };

export function ExecutableRoutePreview({
  itinerary,
  variant,
  tripId,
  baseRevisionId,
  onApplied,
  destination,
}: Props) {
  const loads = useMemo(() => buildDayLoads(itinerary), [itinerary]);
  const risks = useMemo(() => buildUserFacingRisks(itinerary, loads), [itinerary, loads]);
  const [repair, setRepair] = useState<RepairState>({ status: "idle" });
  const previewRequestIdRef = useRef(0);
  const canRepair = variant === "saved" && Boolean(tripId && baseRevisionId && onApplied);

  async function previewRelaxation(day: number) {
    if (!tripId || !baseRevisionId) return;
    if (!loads.some((load) => load.day === day)) {
      setRepair({ status: "error", message: "暂时无法读取这一天的行程负载，当前行程没有被修改。" });
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
      setRepair({ status: "error", message: repairFailureMessage(response.code, "preview") });
      return;
    }
    const localRepair = repairImpact(response.data);
    if (!localRepair) {
      setRepair({ status: "error", message: "暂时找不到一个有充分证据的安全小调整。原路线不会被改变。" });
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
      setRepair({ status: "error", message: repairFailureMessage(response.code, "apply") });
      return;
    }
    onApplied(response.data);
    setRepair({ status: "applied", day, revisionId: response.data.current_revision.id, undoing: false });
  }

  async function undoRelaxation(day: number, revisionId: string) {
    if (!tripId || !onApplied) return;
    setRepair({ status: "applied", day, revisionId, undoing: true });
    const response = await postTripJson<MutationApplyResponse>(
      TRIP_API_ENDPOINTS.undoPersistedRevision(tripId, revisionId),
      { base_revision_id: revisionId },
      "暂时无法撤销这次调整。当前保存的路线没有改变。",
      "服务暂时不可用，当前保存的路线没有改变。",
      { headers: { "X-Idempotency-Key": `undo-day-relax:${revisionId}` } },
    );
    if (!response.ok) {
      const message = repairFailureMessage(response.code, "undo");
      setRepair(isRepairStaleCode(response.code)
        ? { status: "error", message }
        : { status: "applied", day, revisionId, undoing: false, errorMessage: message });
      return;
    }
    onApplied(response.data);
    setRepair({ status: "restored" });
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
          repairDay={"day" in repair ? repair.day : undefined}
          onRelaxDay={(day) => void previewRelaxation(day)}
        />
        {repair.status === "review" || repair.status === "applying" ? (
          <RoadbookRepairPreview
            before={repair.before}
            after={repair.preview.itinerary}
            targetDay={repair.day}
            impact={repair.preview.impact_summary.local_repair!}
            applying={repair.status === "applying"}
            onKeep={dismissRepair}
            onApply={() => void applyRelaxation(repair.day, repair.before, repair.preview)}
          />
        ) : null}
        {repair.status === "applied" ? (
          <RepairFeedback
            message="这段路线已经松了一点，调整也已经保存。"
            errorMessage={repair.errorMessage}
            actionLabel={repair.undoing ? "正在恢复…" : repair.errorMessage ? "重试撤销" : "撤销刚才的调整"}
            busy={repair.undoing}
            onAction={() => void undoRelaxation(repair.day, repair.revisionId)}
          />
        ) : null}
        {repair.status === "restored" ? <RepairFeedback message="已恢复调整前的路线。" /> : null}
        {repair.status === "error" ? <RepairError message={repair.message} onDismiss={dismissRepair} /> : null}
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
        <div className="erp-header-summary">
          <strong>{itinerary.trip_days} 天</strong>
          <span>{loads.reduce((total, day) => total + day.activityCount, 0)} 个活动</span>
          <span>{loads.reduce((total, day) => total + day.fixedCount, 0)} 项固定安排</span>
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

function RepairFeedback({
  message,
  errorMessage,
  actionLabel,
  busy = false,
  onAction,
}: {
  message: string;
  errorMessage?: string;
  actionLabel?: string;
  busy?: boolean;
  onAction?: () => void;
}) {
  return <aside className="erp-repair-feedback" role="status"><div><p>ROUTE SAVED</p><strong>{message}</strong>{errorMessage ? <span className="erp-repair-feedback__error" role="alert">{errorMessage}</span> : null}</div>{actionLabel && onAction ? <button type="button" onClick={onAction} disabled={busy}>{actionLabel}</button> : null}</aside>;
}

function RepairError({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return <aside className="erp-repair-error" role="alert"><div><p>这次没有改动路线</p><strong>{message}</strong></div><button type="button" onClick={onDismiss} aria-label="关闭调整提示">×</button></aside>;
}

function RoutePreviewStyles() {
  return <style>{`
    .erp-shell{display:grid;gap:18px;margin:0 0 24px}.erp-header,.erp-day{border:1px solid var(--ec-line);background:rgba(255,253,249,.94);box-shadow:var(--ec-shadow-2)}.erp-header{display:flex;justify-content:space-between;gap:18px;align-items:end;padding:24px 26px;border-radius:20px}.erp-header p,.erp-day-header p{margin:0 0 5px;color:var(--ec-route-blue);font-size:12px;font-weight:900;letter-spacing:.08em}.erp-header h2,.erp-day h3{margin:0;font-family:"Iowan Old Style",Georgia,serif;color:var(--ec-ink);letter-spacing:0}.erp-header h2{font-size:30px}.erp-header span,.erp-day-header span{color:var(--ec-slate);font-size:14px;line-height:1.55}.erp-header-summary{display:flex;gap:10px;flex-wrap:wrap;justify-content:end}.erp-header-summary>*{padding:7px 10px;border-radius:999px;background:rgba(21,21,21,.05);font-size:12px}.erp-risks{border:1px solid rgba(185,78,72,.35);background:rgba(255,244,242,.85);padding:16px 18px;border-radius:14px;color:#822b27}.erp-risks p{margin:6px 0 0;line-height:1.5}.erp-days{display:grid;gap:16px}.erp-day{border-radius:18px;padding:22px}.erp-day-header{display:flex;justify-content:space-between;gap:16px;align-items:start;padding-bottom:16px;border-bottom:1px solid var(--ec-line)}.erp-day-header h3{font-size:25px;margin-bottom:4px}.erp-pace{padding:7px 10px;border-radius:999px;font-size:12px;font-weight:900;white-space:nowrap}.erp-pace--relaxed{background:#e9f3e8;color:#3f6c43}.erp-pace--balanced{background:#edf2f7;color:#486273}.erp-pace--rushed{background:#fff1dd;color:#8b5e1f}.erp-pace--infeasible{background:#fde9e6;color:#9d302a}.erp-load-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:16px 0}.erp-load-grid div{padding:11px;border:1px solid var(--ec-line);border-radius:10px;background:rgba(247,244,238,.72)}.erp-load-grid span{display:block;font-size:11px;color:var(--ec-slate);font-weight:800}.erp-load-grid strong{font-size:14px;color:var(--ec-ink)}.erp-timeline{display:grid;gap:10px}.erp-timeline-row{display:grid;gap:8px}.erp-leg{margin-left:26px;padding:8px 10px;border-left:2px solid rgba(37,99,235,.35);display:grid;gap:2px;color:var(--ec-slate);font-size:12px}.erp-leg span{color:var(--ec-route-blue);font-weight:900}.erp-leg strong{color:var(--ec-ink);font-size:13px}.erp-stop{display:grid;grid-template-columns:98px minmax(0,1fr);gap:14px;padding:14px 12px;border-radius:10px;background:rgba(255,255,255,.76);border:1px solid rgba(21,21,21,.08)}.erp-stop time{font-weight:900;color:var(--ec-route-blue);font-size:13px}.erp-stop-title{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.erp-stop strong{color:var(--ec-ink);font-size:17px}.erp-stop p{margin:5px 0 0;color:var(--ec-slate);font-size:13px;line-height:1.55}.erp-fixed,.erp-kind{padding:4px 7px;border-radius:999px;font-size:11px;font-weight:900}.erp-fixed{background:rgba(117,91,40,.12);color:#76531f}.erp-kind{background:rgba(37,99,235,.08);color:#285eae}.erp-why{margin-top:14px;color:var(--ec-slate);font-size:13px}.erp-why summary{cursor:pointer;font-weight:900;color:var(--ec-ink)}.erp-why div{display:grid;gap:6px;margin-top:9px}.erp-why p{margin:0;line-height:1.55}.erp-why p strong{margin-right:5px;color:var(--ec-ink)}.erp-repair-button{border:0;border-radius:10px;padding:10px 13px;background:var(--ec-ink);color:#fff;font-weight:900;cursor:pointer;margin-top:16px}.erp-repair-button:disabled{opacity:.55;cursor:wait}.erp-repair-feedback,.erp-repair-error{display:flex;justify-content:space-between;align-items:center;gap:18px;border-top:3px solid #5f6859;border-bottom:1px solid rgba(23,22,19,.18);background:#f7f3eb;padding:18px 22px;color:#171613}.erp-repair-feedback p,.erp-repair-error p{margin:0 0 4px;color:#5f6859;font-size:9px;font-weight:900;letter-spacing:.14em}.erp-repair-feedback strong,.erp-repair-error strong{font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:18px}.erp-repair-feedback__error{display:block;margin-top:6px;color:#8d3028;font-size:12px;font-weight:800}.erp-repair-feedback button,.erp-repair-error button{border:0;border-bottom:1px solid currentColor;background:transparent;padding:7px 0;color:#171613;font-weight:900;cursor:pointer}.erp-repair-feedback button:disabled{opacity:.55;cursor:wait}.erp-repair-error{border-top-color:#a23d32}.erp-repair-error p{color:#a23d32}.erp-repair-error>button{border:0;font-size:24px}.erp-error{margin:0;color:#9d302a;font-weight:800}@media(max-width:720px){.erp-header{display:grid;align-items:start;padding:19px}.erp-header-summary{justify-content:start}.erp-day{padding:16px}.erp-load-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.erp-stop{grid-template-columns:1fr;gap:5px}.erp-day-header{display:grid}.erp-header h2{font-size:27px}.erp-repair-feedback,.erp-repair-error{align-items:start;margin:0 -18px;padding:16px 18px}.erp-repair-feedback strong,.erp-repair-error strong{font-size:16px}}
  `}</style>;
}
