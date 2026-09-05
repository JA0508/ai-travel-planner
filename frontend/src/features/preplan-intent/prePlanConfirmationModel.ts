import type { FixedEventIntent, IntentAssumption, IntentClarification, SourceLinkedTripIntentEnvelope } from "@/features/intent-confirmation/intentTypes";

type SummaryItem = {
  label: string;
  value: string;
};

type ConfirmationBlocker = {
  title: string;
  detail: string;
  source: "clarification" | "readiness" | "fixed_place";
};

export type PrePlanConfirmationViewModel = {
  heading: string;
  summary: SummaryItem[];
  mustPlaces: Array<{ id: string; name: string; source: "candidate" | "direct" }>;
  blockers: ConfirmationBlocker[];
  assumptions: Array<{ title: string; detail: string }>;
  fixedArrangements: Array<{ title: string; detail: string }>;
  sourceLines: Array<{ label: string; source: string }>;
  unresolvedFixedEventIds: string[];
  canGeneratePreview: boolean;
  actionHint: string;
};

export function buildPrePlanConfirmationViewModel(
  envelope: SourceLinkedTripIntentEnvelope,
): PrePlanConfirmationViewModel {
  const formal = envelope.formal_contract;
  const mustPlaces = displayedMustPlaces(envelope);
  const clarificationBlockers = envelope.clarification_queue
    .filter((question) => question.blocking)
    .map((question) => ({ ...clarificationCopy(question), source: "clarification" as const }));
  const fallbackBlockers = formal.readiness.blocking_issue_codes.map((code) => ({ ...issueCopy(code), source: "readiness" as const }));
  const assumptions = envelope.typed_assumptions
    .filter((assumption) => assumption.has_assumed_value && !assumption.blocks_planner_ready)
    .map((assumption) => assumptionCopy(assumption));
  const unresolvedFixedEventIds = formal.fixed_events
    .filter((event) => !hasVerifiedFixedPlace(event.event_id, formal.place_identities ?? []))
    .map((event) => event.event_id);
  const fixedPlaceBlockers = unresolvedFixedEventIds.map((eventId) => {
    const event = formal.fixed_events.find((item) => item.event_id === eventId);
    return {
      title: "请确认固定安排的地点",
      detail: `“${event?.title ?? "这个固定安排"}”需要明确地点，才能安全排进路线。`,
      source: "fixed_place" as const,
    };
  });
  const requiredBlockers = clarificationBlockers.length ? clarificationBlockers : fallbackBlockers;
  const combinedBlockers = uniqueBlockers([...requiredBlockers, ...fixedPlaceBlockers]);
  // Old Draft revisions may predate fixed-place readiness enforcement. Keep the
  // browser from issuing a request that the server must reject, while the server
  // remains the authority for every new immutable revision.
  const canGeneratePreview = isPlannerReady(envelope.planner_ready_status) && unresolvedFixedEventIds.length === 0;

  return {
    heading: canGeneratePreview ? "可以开始规划" : "还需要补充信息",
    summary: [
      { label: "目的地", value: formal.destinations.map((item) => item.city_name).join("、") || "还未确认" },
      { label: "旅行时间", value: describeTripTime(envelope) },
      { label: "旅行节奏", value: paceLabel(formal.pace?.value) },
      { label: "固定安排", value: formal.fixed_events.length ? `${formal.fixed_events.length} 个已安排` : "暂无" },
      { label: "想去的地方", value: mustPlaces.length ? `${mustPlaces.length} 个一定想去` : "暂未指定" },
    ],
    mustPlaces,
    blockers: combinedBlockers,
    assumptions,
    fixedArrangements: formal.fixed_events.map(fixedArrangementCopy),
    sourceLines: envelope.fields
      .filter((field) => field.status === "selected")
      .map((field) => ({ label: userFieldLabel(field.field_path), source: sourceLabel(field.source_refs[0]?.source_type) }))
      .filter((item, index, values) => values.findIndex((value) => value.label === item.label) === index),
    unresolvedFixedEventIds,
    canGeneratePreview,
    actionHint: canGeneratePreview
      ? assumptions.length
        ? `将按 ${assumptions.length} 项暂定设置生成，之后仍可修改。`
        : "关键信息已确认，可以先查看第一版路线。"
      : combinedBlockers.length
        ? `还需要补充 ${combinedBlockers.length} 个关键信息。`
        : "请先补充会影响路线安排的关键信息。",
  };
}

function displayedMustPlaces(envelope: SourceLinkedTripIntentEnvelope): Array<{ id: string; name: string; source: "candidate" | "direct" }> {
  const candidates = envelope.formal_contract.must_visit_places.map((place) => ({
    id: `candidate:${place.trip_candidate_id}`,
    name: place.display_name ?? "已确认地点",
    source: "candidate" as const,
  }));
  const direct = (envelope.formal_contract.place_identities ?? [])
    .filter((identity) => identity.ownership === "must")
    .map((identity) => ({
      id: identity.stable_id,
      name: identity.canonical_name ?? identity.original_name,
      source: "direct" as const,
    }));
  const seen = new Set<string>();
  return [...candidates, ...direct].filter((place) => {
    const key = place.name.replace(/\s/g, "").toLocaleLowerCase();
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function hasVerifiedFixedPlace(
  eventId: string,
  identities: NonNullable<SourceLinkedTripIntentEnvelope["formal_contract"]["place_identities"]>,
): boolean {
  const fixed = identities.filter((identity) => identity.ownership === "fixed");
  const matches = fixed.filter((identity) => identity.fixed_event_id === eventId || identity.stable_id === eventId);
  const candidates = matches.length ? matches : fixed.length === 1 ? fixed : [];
  return candidates.some((identity) => identity.resolution_status === "verified");
}

function uniqueBlockers(items: ConfirmationBlocker[]): ConfirmationBlocker[] {
  return items.filter((item, index) => items.findIndex((value) => value.title === item.title && value.detail === item.detail) === index);
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
    case "fixed_place_identity_not_verified":
    case "fixed_event_identity_not_verified":
      return { title: "请确认固定安排的地点", detail: "固定安排需要明确地点，才能安全排进路线。" };
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
