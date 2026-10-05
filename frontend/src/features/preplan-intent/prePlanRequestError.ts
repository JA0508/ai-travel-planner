const PLANNER_HANDOFF_MESSAGES: Record<string, string> = {
  formal_contract_not_verified: "行程信息正在更新，暂时不能安全进入路线规划。请重新整理旅行信息后再试。",
  intent_not_planner_ready: "还有会影响路线的信息未确认。请返回修改旅行信息后再生成路线预览。",
  intent_has_unresolved_required_fields: "还有关键行程信息未补全。请返回修改旅行信息后再生成路线预览。",
  destination_missing: "还没有确认目的地。请补充目的地后再生成路线预览。",
  multi_destination_handoff_not_supported: "第一版路线目前一次只能安排一个目的地。请拆分为单城市行程后再生成。",
  trip_days_missing: "还没有确认旅行天数。请补充旅行时间后再生成路线预览。",
  intent_candidate_missing: "有一个已选地点的资料已经更新。请重新整理旅行信息后再生成路线预览。",
  intent_candidate_identity_not_verified: "有一个已选地点的地点资料尚未完整核验。请重新整理旅行信息后再确认该地点。",
  fixed_event_requires_date_policy: "固定安排包含具体日期，需要补充旅行日期后才能安全排进路线。",
  fixed_event_outside_trip: "有一个固定安排不在当前旅行时间内。请调整旅行时间或固定安排后再生成路线预览。",
  fixed_event_time_range_incomplete: "有一个固定安排的时间不完整。请补充完整时间后再生成路线预览。",
  fixed_event_candidate_missing: "有一个固定安排的地点资料已经更新。请重新整理旅行信息后再确认。",
  availability_window_requires_date_policy: "你提供了具体可用时间，需要补充旅行日期后才能排进路线。",
  availability_window_outside_supported_range: "有一段可用时间不在当前旅行时间内。请调整旅行时间后再生成路线预览。",
  travel_boundary_outside_trip: "抵达或离开时间不在当前旅行时间内。请调整旅行时间后再生成路线预览。",
};

export type PlannerHandoffRecoveryAction = "edit_date_policy" | "edit_destination" | "refresh_intent" | "focus_place_confirmation" | "focus_fixed_place_confirmation";

const DATE_POLICY_RECOVERY_REASONS = new Set([
  "trip_days_missing",
  "fixed_event_requires_date_policy",
  "fixed_event_outside_trip",
  "availability_window_requires_date_policy",
  "availability_window_outside_supported_range",
  "travel_boundary_outside_trip",
]);

const INTENT_REFRESH_RECOVERY_REASONS = new Set([
  "formal_contract_not_verified",
  "intent_candidate_missing",
  "intent_candidate_identity_not_verified",
  "fixed_event_candidate_missing",
]);

export function plannerHandoffRecoveryAction(
  code?: string,
  context?: Record<string, unknown>,
): PlannerHandoffRecoveryAction | undefined {
  if (code !== "planner_handoff_blocked" || typeof context?.reason_code !== "string") return undefined;
  if (context.reason_code === "must_place_identity_not_verified") return "focus_place_confirmation";
  if (context.reason_code === "fixed_event_identity_not_verified") return "focus_fixed_place_confirmation";
  if (context.reason_code === "destination_missing") return "edit_destination";
  if (INTENT_REFRESH_RECOVERY_REASONS.has(context.reason_code)) return "refresh_intent";
  return DATE_POLICY_RECOVERY_REASONS.has(context.reason_code) ? "edit_date_policy" : undefined;
}

export function plannerHandoffRecoveryFieldId(
  action: PlannerHandoffRecoveryAction | undefined,
  context?: Record<string, unknown>,
): string | undefined {
  if (action !== "focus_fixed_place_confirmation" || typeof context?.field_id !== "string") return undefined;
  return context.field_id.trim() || undefined;
}

export function plannerHandoffRecoveryPlaceStableId(
  action: PlannerHandoffRecoveryAction | undefined,
  context?: Record<string, unknown>,
): string | undefined {
  if (action !== "focus_place_confirmation" || typeof context?.place_stable_id !== "string") return undefined;
  return context.place_stable_id.trim() || undefined;
}

export function userFacingPrePlanRequestError(
  code?: string,
  fallback = "暂时无法整理旅行信息，你的输入已经保留。",
  context?: Record<string, unknown>,
  placeName?: string,
): string {
  if (code === "stale_intent_revision" || code === "stale_base_revision") {
    return "行程信息已经在其他页面更新，请返回后重新进入确认页面。";
  }
  if (code === "intent_parser_unavailable" || code === "intent_parser_timeout" || code === "intent_parser_invalid_output") {
    return "部分内容未能自动识别，请检查关键信息。";
  }
  if (code === "planner_handoff_blocked" && context?.reason_code === "fixed_event_identity_not_verified") {
    return "固定安排的地点还没有确认，暂时不能把它排进可执行路线。请返回修改需求，补充预约地点或从导入资料中确认该地点。";
  }
  if (code === "planner_handoff_blocked" && context?.reason_code === "must_place_identity_not_verified") {
    const label = placeName?.trim();
    if (label) {
      return `「${label}」还没有可用于规划的已确认位置。请打开该地点卡，从系统推荐中选择，或搜索更具体的地点后再选择，再生成路线预览。`;
    }
    return "有一个必去地点还没有可用于规划的已确认位置。请打开该地点并重新选择，再生成路线预览。";
  }
  const reasonCode = typeof context?.reason_code === "string" ? context.reason_code : undefined;
  if (code === "planner_handoff_blocked" && reasonCode && PLANNER_HANDOFF_MESSAGES[reasonCode]) {
    return PLANNER_HANDOFF_MESSAGES[reasonCode];
  }
  return fallback;
}

export function isStalePrePlanIntentError(code?: string): boolean {
  return code === "stale_intent_revision" || code === "stale_base_revision";
}

export function previewTimedOutMessage(): string {
  return "路线预览暂未完成，已停止本次等待。你的确认信息没有变化，可以重新生成路线预览。";
}

export function previewUnavailableMessage(): string {
  return "路线预览服务暂时不可用，你的确认信息没有变化。请稍后重新生成路线预览。";
}

export function savePreviewUnavailableMessage(): string {
  return "正式行程的保存结果暂时未确认；你的路线预览和确认信息都还在。请稍后重新保存。";
}
