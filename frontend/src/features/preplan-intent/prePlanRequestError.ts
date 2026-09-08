export function userFacingPrePlanRequestError(
  code?: string,
  fallback = "暂时无法整理旅行信息，你的输入已经保留。",
  context?: Record<string, unknown>,
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
    return "有一个必去地点还没有可用于规划的已确认位置。请打开该地点并重新选择，再生成路线预览。";
  }
  return fallback;
}

export function isStalePrePlanIntentError(code?: string): boolean {
  return code === "stale_intent_revision" || code === "stale_base_revision";
}
