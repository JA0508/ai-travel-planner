import type { PlannerHandoffReviewSummary } from "@/features/preplan-intent/plannerTraceReviewModel";

export type FrozenHandoffEvidenceView = {
  title: string;
  intentLabel: string;
  handoffLabel: string;
  statusLabel: string;
  readinessLabel: string;
  traceLabel: string;
  sourceBoundary: string;
  heuristicBoundary: string;
  providerBoundary: string;
};

export function buildFrozenHandoffEvidenceView(
  summary: PlannerHandoffReviewSummary,
  handoffRunId = "已关联的冻结规划记录",
): FrozenHandoffEvidenceView {
  return {
    title: "已保存的规划依据",
    intentLabel: `关联 IntentRevision：${summary.intent_revision_id}`,
    handoffLabel: `冻结 handoff run：${handoffRunId}`,
    statusLabel: `Handoff 状态：${handoffStatusLabel(summary.status)}`,
    readinessLabel: `当时 readiness：${readinessLabel(summary.readiness_status)}`,
    traceLabel: `规划记录：${summary.trace.decision_count} 项判断，${summary.trace.accepted_decision_count} 项纳入、${summary.trace.rejected_decision_count} 项未纳入、${summary.trace.warning_count} 项需要留意。`,
    sourceBoundary: "来源：用户确认的地点与固定安排保留其来源边界。",
    heuristicBoundary: "系统判断：时间安排、路线取舍和自动补充属于系统建议，不等同于用户确认事实。",
    providerBoundary: "本次规划没有独立 provider evidence。",
  };
}

function handoffStatusLabel(status: PlannerHandoffReviewSummary["status"]): string {
  if (status === "applied") return "已生成正式行程";
  if (status === "apply_ready") return "可以确认";
  if (status === "stale") return "已过期";
  if (status === "unstable") return "存在执行风险";
  return "暂时不能应用";
}

function readinessLabel(status: string): string {
  if (status === "ready_for_planning") return "可以开始规划";
  if (status === "ready_with_assumptions") return "可以开始规划，包含暂定设置";
  if (status === "needs_clarification") return "还需要补充信息";
  return "当前不可开始规划";
}
