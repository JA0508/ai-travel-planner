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
};

export function PlanCandidateComparison({ response, selectedId, busy, error, onSelect, onConfirm, onBack }: {
  response: PlanCandidateResponse;
  selectedId: string;
  busy: boolean;
  error: string | null;
  onSelect: (candidateId: string) => void;
  onConfirm: () => void;
  onBack: () => void;
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
          <dl><div><dt>必去</dt><dd>{candidate.metrics.must_coverage}</dd></div><div><dt>可调整</dt><dd>{candidate.metrics.optional_coverage}</dd></div><div><dt>弹性时间</dt><dd>{Math.floor(candidate.metrics.free_buffer_minutes / 60)}h</dd></div></dl>
          <ul>{highlights.slice(0, 2).map((highlight) => <li key={highlight}>{highlight}</li>)}</ul>
        </button>;
      })}
    </section>
    <section className="tc-selected-route"><div><p className="tc-eyebrow">你选择的路线</p><h2>{selected.title}</h2><p>{selected.itinerary.days.map((day) => `第 ${day.day} 天 ${day.blocks.flatMap((block) => block.items).map((item) => item.name).slice(0, 3).join(" · ")}`).join(" / ")}</p></div><details className="tc-source"><summary>查看依据</summary><p>这条路线按你确认的目的地、天数、固定安排和必去地点生成。原始描述与后续确认会一起保留为这次规划的依据。</p></details></section>
    {error ? <p className="tc-candidate-error" role="alert">{error}</p> : null}
    <footer className="tc-confirm-footer"><span>确认后才会保存为第一版行程。</span><button type="button" className="tc-primary" onClick={onConfirm} disabled={busy}>{busy ? "正在保存这条路线" : "确认并保存这条路线"}</button></footer>
  </main>;
}
