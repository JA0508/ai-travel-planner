"use client";

import React from "react";
import { formatDistance, formatMinutes, type RoutePreviewItinerary } from "@/features/executable-route-preview/routePreviewModel";

type CandidateMetrics = {
  fixed_coverage: number;
  must_coverage: number;
  optional_coverage: number;
  total_travel_minutes: number | null;
  activity_minutes: number;
  max_daily_activity_minutes: number;
  free_buffer_minutes: number;
  missing_travel_data: boolean;
  minimum_daily_slack_minutes: number;
  rushed_day_count: number;
  infeasible_day_count: number;
  risk_count: number;
  travel_data_completeness: "complete" | "partial" | "missing";
  daily_windows: unknown[];
};

export type PlanCandidate = {
  id: string;
  candidate_hash: string;
  strategy: "relaxed" | "balanced" | "low_travel";
  title: string;
  tradeoff_summary: string;
  itinerary: RoutePreviewItinerary;
  metrics: CandidateMetrics;
};

export type PlanCandidateResponse = {
  intent_digest: string;
  candidates: PlanCandidate[];
  comparison: { candidate_id: string; highlights: string[] }[];
  planning_run_id: string;
  status: "generated" | "selecting" | "selected" | "expired" | "invalidated";
  expires_at: string;
};

type Props = {
  response: PlanCandidateResponse;
  selectedId: string;
  busy: boolean;
  error: string | null;
  onSelect: (candidateId: string) => void;
  onConfirm: () => void;
  onBack: () => void;
};

const STRATEGY_LABELS = {
  relaxed: "留白更多",
  balanced: "节奏均衡",
  low_travel: "少走一点",
} as const;

export function PlanCandidateComparison({
  response,
  selectedId,
  busy,
  error,
  onSelect,
  onConfirm,
  onBack,
}: Props) {
  const selected = response.candidates.find((candidate) => candidate.id === selectedId) ?? response.candidates[0];
  const selectedHighlights = response.comparison.find((item) => item.candidate_id === selected.id)?.highlights ?? [];

  return <main className="tc-page tc-candidate-page" data-visual-shell="road-movie-v0">
    <header className="tc-candidate-hero">
      <img src="/editorial/shanghai-street-hero.png" alt="雨后城市街道与旅行中的自行车" />
      <div className="tc-candidate-hero-shade" />
      <div className="tc-candidate-hero-top">
        <span className="tc-wordmark"><i aria-hidden="true">✦</i> 旅程编辑部</span>
        <button type="button" className="tc-link" onClick={onBack} disabled={busy}>返回修改信息 ↗</button>
      </div>
      <div className="tc-candidate-hero-copy">
        <p className="tc-eyebrow">ROUTE DIRECTORY</p>
        <h1>路线怎么不同，<em>一眼就能看懂。</em></h1>
        <p>固定安排和必去地点都保留，区别只在路上的取舍。</p>
      </div>
    </header>

    <div className="tc-candidate-layout">
      <nav className="tc-route-directory" aria-label="路线方案目录">
        <p className="tc-eyebrow">{String(response.candidates.length).padStart(2, "0")} ROUTES</p>
        {response.candidates.map((candidate, index) => {
          const active = candidate.id === selected.id;
          return <button
            type="button"
            key={candidate.id}
            className={`tc-route-directory-item${active ? " is-selected" : ""}`}
            aria-pressed={active}
            onClick={() => onSelect(candidate.id)}
            disabled={busy}
          >
            <span>0{index + 1}</span>
            <div>
              <small>{STRATEGY_LABELS[candidate.strategy]}</small>
              <strong>{candidate.title}</strong>
              <p>{candidate.tradeoff_summary}</p>
            </div>
            <i aria-hidden="true">{active ? "●" : "○"}</i>
          </button>;
        })}
      </nav>

      <section className="tc-selected-route" aria-label="完整路线预览">
        <header className="tc-selected-route-header">
          <div>
            <p className="tc-eyebrow">SELECTED JOURNEY</p>
            <h2>{selected.title}</h2>
            <p>{selected.tradeoff_summary}</p>
          </div>
          <dl className="tc-route-facts">
            <div><dt>必去地点</dt><dd>{selected.metrics.must_coverage} 个</dd></div>
            <div><dt>路上时间</dt><dd>{formatOptionalMinutes(selected.metrics.total_travel_minutes)}</dd></div>
            <div><dt>每天至少留白</dt><dd>{formatMinutes(selected.metrics.minimum_daily_slack_minutes)}</dd></div>
          </dl>
        </header>

        <div className="tc-route-proof">
          <span>{selected.metrics.fixed_coverage ? "固定安排已保护" : "没有固定安排"}</span>
          <span>{selected.metrics.travel_data_completeness === "complete" ? "路程已确认" : "部分路程待确认"}</span>
          <span>{mealRhythmLabel(selected.itinerary)}</span>
        </div>

        <div className="tc-route-days">
          {selected.itinerary.days.map((day) => <section className="tc-day-route" key={day.day}>
            <header><span>DAY</span><b>{String(day.day).padStart(2, "0")}</b></header>
            <div className="tc-day-route-body">
              {day.blocks.flatMap((block) => block.items).map((item, index) => <div className="tc-route-item" key={item.stable_id ?? `${day.day}:${item.start_time}:${item.name}`}>
                {item.travel_from_name ? <TravelEvidence item={item} /> : null}
                <div className="tc-route-stop">
                  <time>{item.start_time ?? "待定"}</time>
                  <span className="tc-route-dot" aria-hidden="true" />
                  <div>
                    <strong>{item.name}</strong>
                    <small>{item.is_fixed ? "固定安排已保护" : item.source_label ?? "系统补充"}{item.duration_minutes ? ` · ${item.duration_minutes} 分钟` : ""}</small>
                  </div>
                  <span className="tc-route-order">0{index + 1}</span>
                </div>
              </div>)}
            </div>
          </section>)}
        </div>

        <details className="tc-route-rationale" open>
          <summary>为什么选这条路</summary>
          <p>{selected.tradeoff_summary}</p>
          {selectedHighlights.map((highlight) => <p key={highlight}>↳ {highlight}</p>)}
        </details>
      </section>
    </div>

    {error ? <p className="tc-candidate-error" role="alert">{error}</p> : null}
    <footer className="tc-confirm-footer">
      <span>确认后才会保存为第一版行程。</span>
      <button type="button" className="tc-primary" onClick={onConfirm} disabled={busy}>{busy ? "正在保存这条路线" : "就选这条路线"}</button>
    </footer>
  </main>;
}

function TravelEvidence({ item }: { item: RoutePreviewItinerary["days"][number]["blocks"][number]["items"][number] }) {
  if (item.travel_data_status === "confirmed" && item.travel_duration_s != null) {
    return <div className="tc-route-leg">
      <span>路程已确认</span>
      <strong>{item.travel_from_name} → {item.name}</strong>
      <small>{formatMinutes(Math.round(item.travel_duration_s / 60))}{item.travel_distance_m != null ? ` · ${formatDistance(item.travel_distance_m)}` : ""}</small>
    </div>;
  }
  return <div className="tc-route-leg is-unavailable">
    <span>路程待确认</span>
    <strong>{item.travel_from_name} → {item.name}</strong>
    <small>这段移动不会被当成已经核实的数据。</small>
  </div>;
}

function formatOptionalMinutes(minutes: number | null) {
  return minutes == null ? "待确认" : formatMinutes(minutes);
}

function mealRhythmLabel(itinerary: RoutePreviewItinerary) {
  const slots = itinerary.meal_rhythm?.days.flatMap((day) => day.slots) ?? [];
  const applicable = slots.filter((slot) => slot.status !== "not_applicable");
  if (!applicable.length) return "餐食按当天时段判断";
  const covered = applicable.filter((slot) => slot.status === "covered" || slot.status === "auto_completed");
  if (covered.length === applicable.length) {
    const coveredRoles = [...new Set(covered.map((slot) => slot.role === "lunch" ? "午饭" : "晚饭"))];
    return `${coveredRoles.join("和")}已安排`;
  }
  const missingRoles = [...new Set(applicable
    .filter((slot) => slot.status === "unresolved")
    .map((slot) => slot.role === "lunch" ? "午饭" : "晚饭"))];
  return `${missingRoles.join("、")}待补`;
}
