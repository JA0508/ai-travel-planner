export type PlannerHandoffReviewSummary = {
  status: "apply_ready" | "blocked" | "stale" | "unstable" | "applied";
  can_apply: boolean;
  intent_revision_id: string;
  current_intent_revision_id: string;
  base_trip_revision_id: string | null;
  current_trip_revision_id: string | null;
  readiness_status: string;
  blocking_reason_codes: string[];
  warning_codes: string[];
  trace: {
    decision_count: number;
    accepted_decision_count: number;
    rejected_decision_count: number;
    warning_count: number;
    reason_codes: string[];
  };
};

export type PlannerTraceReviewView = {
  tone: "ready" | "attention" | "neutral";
  title: string;
  detail: string;
  traceSummary: string;
  notice: string | null;
};

export function buildPlannerTraceReviewView(summary: PlannerHandoffReviewSummary): PlannerTraceReviewView {
  const traceSummary = `规划记录：${summary.trace.decision_count} 项安排判断，其中 ${summary.trace.accepted_decision_count} 项纳入路线、${summary.trace.rejected_decision_count} 项未纳入。`;
  const notice = summary.trace.warning_count ? `还有 ${summary.trace.warning_count} 项安排需要留意。` : null;

  if (summary.status === "apply_ready") {
    return { tone: "ready", title: "这份预览可以确认", detail: "它仍对应当前确认的信息，可以作为第一版正式行程保存。", traceSummary, notice };
  }
  if (summary.status === "stale") {
    return { tone: "attention", title: "这份预览已经过期", detail: staleDetail(summary.blocking_reason_codes), traceSummary, notice };
  }
  if (summary.status === "unstable") {
    return { tone: "attention", title: "这份预览仍有执行冲突", detail: "请先调整旅行信息，再重新生成路线预览。", traceSummary, notice };
  }
  if (summary.status === "blocked") {
    return { tone: "attention", title: "还需要补充后才能生成路线", detail: blockerDetail(summary.blocking_reason_codes), traceSummary, notice };
  }
  return { tone: "neutral", title: "这一版路线已保存", detail: "它来自已经确认的冻结规划结果；之后的调整会生成新的行程版本。", traceSummary, notice };
}

export function markPlannerHandoffReviewStale(summary: PlannerHandoffReviewSummary): PlannerHandoffReviewSummary {
  if (summary.status === "stale") return summary;
  return {
    ...summary,
    status: "stale",
    can_apply: false,
    blocking_reason_codes: [...new Set([...summary.blocking_reason_codes, "intent_revision_advanced"])],
  };
}

function staleDetail(codes: string[]): string {
  return codes.includes("base_revision_advanced")
    ? "这份行程已经在其他页面更新，旧预览不能再保存。"
    : "行程信息已更新，请重新生成路线预览后再保存。";
}

function blockerDetail(codes: string[]): string {
  if (codes.includes("trip_dates_missing")) return "还需要确认旅行日期或天数，才能安全安排路线。";
  if (codes.includes("fixed_event_identity_not_verified")) return "固定安排的地点还需要确认，才能安全纳入路线。";
  return "还有关键信息尚未确认，暂时不会生成或保存路线。";
}
