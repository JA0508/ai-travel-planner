import type { FixedEventIntent, IntentAssumption, IntentClarification, SourceLinkedTripIntentEnvelope } from "@/features/intent-confirmation/intentTypes";

type SummaryItem = {
  label: string;
  value: string;
};

export type PrePlanConfirmationViewModel = {
  heading: string;
  summary: SummaryItem[];
  blockers: Array<{ title: string; detail: string }>;
  assumptions: Array<{ title: string; detail: string }>;
  fixedArrangements: Array<{ title: string; detail: string }>;
  sourceLines: Array<{ label: string; source: string }>;
  canGeneratePreview: boolean;
  actionHint: string;
};

export type PrePlanClarificationControl = "destination" | "trip_days" | "pace" | "date_range" | "date_choice";

export function getPrePlanClarificationControl(question: IntentClarification): PrePlanClarificationControl | null {
  if (["destination_missing", "missing_destination", "destination_conflict"].includes(question.reason_code)) return "destination";
  if (["trip_length_missing", "missing_trip_length", "trip_dates_missing"].includes(question.reason_code)) return "trip_days";
  if (question.reason_code === "relative_date_requires_anchor") return "date_range";
  if (["date_conflict", "date_range_conflict", "date_invalid", "fixed_event_outside_trip_dates"].includes(question.reason_code)) return "date_choice";
  if (question.reason_code !== "same_priority_conflict") return null;
  const controls: Record<string, PrePlanClarificationControl> = {
    "trip.city": "destination",
    "trip.trip_days": "trip_days",
    "trip.pace": "pace",
    "trip.date_policy": "date_choice",
  };
  return controls[question.editor_field_path ?? ""] ?? null;
}

export function buildPrePlanConfirmationViewModel(
  envelope: SourceLinkedTripIntentEnvelope,
): PrePlanConfirmationViewModel {
  const formal = envelope.formal_contract;
  const blockers = envelope.clarification_queue
    .filter((question) => question.blocking)
    .map((question) => clarificationCopy(question));
  const fallbackBlockers = formal.readiness.blocking_issue_codes.map((code) => issueCopy(code));
  const requiredBlockers = blockers.length ? blockers : fallbackBlockers;
  const assumptions = envelope.typed_assumptions
    .filter((assumption) => assumption.has_assumed_value && !assumption.blocks_planner_ready)
    .map((assumption) => assumptionCopy(assumption));
  const canGeneratePreview = isPlannerReady(envelope.planner_ready_status);

  return {
    heading: canGeneratePreview ? "可以开始规划" : "还需要补充信息",
    summary: [
      { label: "目的地", value: formal.destinations.map((item) => item.city_name).join("、") || "还未确认" },
      { label: "旅行时间", value: describeTripTime(envelope) },
      { label: "旅行节奏", value: paceLabel(formal.pace?.value) },
      { label: "固定安排", value: formal.fixed_events.length ? `${formal.fixed_events.length} 个已安排` : "暂无" },
      { label: "想去的地方", value: formal.must_visit_places.length ? `${formal.must_visit_places.length} 个一定想去` : "暂未指定" },
    ],
    blockers: requiredBlockers,
    assumptions,
    fixedArrangements: formal.fixed_events.map(fixedArrangementCopy),
    sourceLines: envelope.fields
      .filter((field) => field.status === "selected")
      .map((field) => ({ label: userFieldLabel(field.field_path), source: sourceLabel(field.source_refs[0]?.source_type) }))
      .filter((item, index, values) => values.findIndex((value) => value.label === item.label) === index),
    canGeneratePreview,
    actionHint: canGeneratePreview
      ? assumptions.length
        ? `将按 ${assumptions.length} 项暂定设置生成，之后仍可修改。`
        : "关键信息已确认，可以先查看第一版路线。"
      : requiredBlockers.length
        ? `还需要补充 ${requiredBlockers.length} 个关键信息。`
        : "请先补充会影响路线安排的关键信息。",
  };
}

function fixedArrangementCopy(event: FixedEventIntent): { title: string; detail: string } {
  const day = event.fixed_day ? `第 ${event.fixed_day} 天` : null;
  const time = event.start_at ? new Date(event.start_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : null;
  return {
    title: event.title,
    detail: [day, time, event.location_text].filter(Boolean).join(" · ") || "已锁定安排",
  };
}

function isPlannerReady(status: SourceLinkedTripIntentEnvelope["planner_ready_status"]): boolean {
  return status === "ready" || status === "ready_for_planning" || status === "ready_with_assumptions";
}

function describeTripTime(envelope: SourceLinkedTripIntentEnvelope): string {
  const datePolicy = envelope.formal_contract.date_policy;
  if (!datePolicy) return "还未确认";
  if (datePolicy.start_date && datePolicy.end_date) return `${datePolicy.start_date} 至 ${datePolicy.end_date}`;
  if (datePolicy.trip_days) return `${datePolicy.trip_days} 天`;
  return "还未确认";
}

function paceLabel(value: "relaxed" | "balanced" | "intensive" | undefined): string {
  if (value === "relaxed") return "轻松";
  if (value === "intensive") return "紧凑";
  if (value === "balanced") return "适中";
  return "暂未指定";
}

function clarificationCopy(question: IntentClarification): { title: string; detail: string } {
  const copy = issueCopy(question.reason_code);
  return copy.title === "还需要确认一项信息"
    ? { title: copy.title, detail: question.question }
    : copy;
}

function issueCopy(code: string): { title: string; detail: string } {
  switch (code) {
    case "missing_destination":
      return { title: "请填写这次旅行的目的地", detail: "目的地决定路线范围和可安排的地点。" };
    case "missing_trip_length":
      return { title: "请填写旅行日期或天数", detail: "我们需要知道可用于安排行程的时间。" };
    case "relative_date_requires_anchor":
      return { title: "请确认具体出发日期", detail: "相对日期需要一个明确的日历参考。" };
    case "arrival_after_departure":
      return { title: "到达时间不能晚于离开时间", detail: "请调整到达或离开的时间后再继续。" };
    case "fixed_event_overlap":
      return { title: "固定安排时间有重叠", detail: "请调整重叠的安排后再生成路线。" };
    case "fixed_event_outside_trip_dates":
      return { title: "固定安排不在旅行日期范围内", detail: "请调整旅行日期或固定安排。" };
    default:
      return { title: "还需要确认一项信息", detail: "补充后才能保证路线可执行。" };
  }
}

function assumptionCopy(assumption: IntentAssumption): { title: string; detail: string } {
  switch (assumption.reason_code) {
    case "no_reviewed_must_candidates":
      return { title: "暂不设定必须到达的地点", detail: "路线会优先依据你的目的地、时间和旅行节奏安排。" };
    case "missing_value":
      return { title: "部分信息暂按默认设置", detail: "生成路线后仍然可以继续修改。" };
    default:
      return { title: "系统暂时这样理解", detail: "这项暂定设置不会阻止生成路线。" };
  }
}

function sourceLabel(sourceType: string | undefined): string {
  if (sourceType === "direct_user_language") return "你的输入";
  if (sourceType?.includes("import")) return "导入的资料";
  if (sourceType?.includes("review")) return "已审核资料";
  return "已确认信息";
}

function userFieldLabel(fieldPath: string): string {
  switch (fieldPath) {
    case "trip.city": return "目的地";
    case "trip.trip_days": return "旅行天数";
    case "trip.pace": return "旅行节奏";
    case "poi.must_candidates": return "想去的地方";
    case "trip.fixed_events": return "固定安排";
    default: return "旅行偏好";
  }
}
