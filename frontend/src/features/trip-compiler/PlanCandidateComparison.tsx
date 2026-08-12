"use client";

import type { RoutePreviewItinerary } from "@/features/executable-route-preview/routePreviewModel";

export type CandidateMetrics = {
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
  daily_windows: { day: number; available_start: string; available_end: string; available_window_minutes: number; activity_minutes: number; travel_minutes: number; slack_minutes: number }[];
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

export type PlanningRecord = { summary: string[]; evidence: { label: string; kind: string }[]; status: string; selected_candidate_id: string | null; trip_id: string | null };

export function PlanCandidateComparison({ response, selectedId, busy, error, record, onSelect, onConfirm, onBack, onViewRecord }: {
  response: PlanCandidateResponse;
  selectedId: string;
  busy: boolean;
  error: string | null;
  record: PlanningRecord | null;
  onSelect: (candidateId: string) => void;
  onConfirm: () => void;
  onBack: () => void;
  onViewRecord: () => void;
}) {
  const selected = response.candidates.find((candidate) => candidate.id === selectedId) ?? response.candidates[0];
  return <main className="tc-page tc-candidate-page">
    <header className="tc-confirm-header"><div><p className="tc-eyebrow">选择路线</p><h1>选一条更符合这次旅行的安排。</h1><p>每条路线都保留了固定安排和必去地点，只是取舍不同。</p></div><button type="button" className="tc-link-button" onClick={onBack} disabled={busy}>返回修改信息</button></header>
    <section className="tc-candidate-grid" aria-label="路线方案比较">
      {response.candidates.map((candidate) => {
        const active = candidate.id === selected.id;
        const highlights = response.comparison.find((item) => item.candidate_id === candidate.id)?.highlights ?? [];
        return <button type="button" key={candidate.id} className={`tc-candidate-card${active ? " is-selected" : ""}`} aria-pressed={active} onClick={() => onSelect(candidate.id)} disabled={busy}>
          <span className="tc-candidate-tag">{active ? "已选择" : "路线方案"}</span><strong>{candidate.title}</strong><span>{candidate.tradeoff_summary}</span>
          <dl><div><dt>必去</dt><dd>{candidate.metrics.must_coverage}</dd></div><div><dt>可调整</dt><dd>{candidate.metrics.optional_coverage}</dd></div><div><dt>每天弹性</dt><dd>{candidate.metrics.minimum_daily_slack_minutes}m</dd></div></dl>
          <ul>{highlights.slice(0, 2).map((highlight) => <li key={highlight}>{highlight}</li>)}</ul>
        </button>;
      })}
    </section>
    <section className="tc-selected-route" aria-label="完整路线预览"><div><p className="tc-eyebrow">完整路线</p><h2>{selected.title}</h2>{selected.itinerary.days.map((day) => <section className="tc-day-route" key={day.day}><h3>第 {day.day} 天</h3>{day.blocks.flatMap((block) => block.items).map((item) => <div className="tc-route-item" key={item.stable_id ?? `${day.day}:${item.start_time}:${item.name}`}><time>{item.start_time ?? "待定"}</time><span><strong>{item.name}</strong><small>{item.is_fixed ? "固定安排" : item.source_label ?? "系统补充"} · {item.duration_minutes ?? 0} 分钟</small></span></div>)}</section>)}</div><aside><details className="tc-source"><summary>查看依据</summary><p>每项安排都来自你确认的地点、时间和固定安排；系统补充会明确标为系统建议。</p></details><button type="button" className="tc-link-button" onClick={onViewRecord}>查看规划记录</button>{record ? <section className="tc-planning-record"><h3>这次规划</h3>{record.summary.map((item) => <p key={item}>{item}</p>)}{record.evidence.slice(0, 5).map((item) => <p className="tc-record-evidence" key={`${item.kind}:${item.label}`}>“{item.label}” · {item.kind}</p>)}</section> : null}</aside></section>
    {error ? <p className="tc-candidate-error" role="alert">{error}</p> : null}
    <footer className="tc-confirm-footer"><span>确认后才会保存为第一版行程。</span><button type="button" className="tc-primary" onClick={onConfirm} disabled={busy}>{busy ? "正在保存这条路线" : "确认并保存这条路线"}</button></footer>
  </main>;
}
