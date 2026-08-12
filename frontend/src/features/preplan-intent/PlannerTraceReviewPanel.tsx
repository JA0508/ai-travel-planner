import { buildPlannerTraceReviewView, type PlannerHandoffReviewSummary } from "./plannerTraceReviewModel";

export function PlannerTraceReviewPanel({ summary }: { summary: PlannerHandoffReviewSummary }) {
  const view = buildPlannerTraceReviewView(summary);
  return <details className={`uc-intent-card uc-intent-details uc-intent-trace-review uc-intent-trace-review--${view.tone}`} open={view.tone === "attention"}>
    <summary><span><strong>{view.title}</strong><small>{summary.readiness_status === "ready_with_assumptions" ? "包含暂定设置" : "查看规划依据"}</small></span><span aria-hidden="true">展开</span></summary>
    <div className="uc-intent-trace-review-body"><p>{view.detail}</p><p>{view.traceSummary}</p>{view.notice ? <p>{view.notice}</p> : null}</div>
  </details>;
}
