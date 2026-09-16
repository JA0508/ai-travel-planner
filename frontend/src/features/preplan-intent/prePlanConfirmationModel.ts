import type { FixedEventIntent, IntentAssumption, IntentClarification, PlaceIdentity, SourceLinkedTripIntentEnvelope } from "@/features/intent-confirmation/intentTypes";

type SummaryItem = {
  label: string;
  value: string;
};

type ConfirmationBlocker = {
  title: string;
  detail: string;
  source: "clarification" | "readiness" | "fixed_place";
};

export type ConfirmationItem =
  | {
      id: string;
      kind: "must_place";
      title: string;
      detail: string;
      identityId: string;
      tone: "todo";
    }
  | {
      id: string;
      kind: "fixed_place";
      title: string;
      detail: string;
      eventId: string;
      identityId: string | null;
      tone: "todo";
    }
  | {
      id: string;
      kind: "clarification" | "conflict";
      title: string;
      detail: string;
      questionId: string | null;
      tone: "todo" | "conflict";
    };

export type ConfirmedItem = {
  id: string;
  title: string;
  detail: string;
};

export type PrePlanConfirmationViewModel = {
  heading: string;
  summary: SummaryItem[];
  mustPlaces: Array<{ id: string; name: string; source: "candidate" | "direct" }>;
  blockers: ConfirmationBlocker[];
  confirmationItems: ConfirmationItem[];
  confirmedItems: ConfirmedItem[];
  remainingConfirmationCount: number;
  remainingActionableConfirmationCount: number;
  requiresTravelInformationEdit: boolean;
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
  const identities = formal.place_identities ?? [];
  const mustPlaces = displayedMustPlaces(envelope);
  const clarificationBlockers = envelope.clarification_queue
    .filter((question) => question.blocking)
    .filter((question) => !isPlaceIdentityClarification(question.reason_code))
    .map((question) => ({ ...clarificationCopy(question), source: "clarification" as const }));
  const fallbackBlockers = formal.readiness.blocking_issue_codes
    .filter((code) => !isPlaceIdentityClarification(code))
    .map((code) => ({ ...issueCopy(code), source: "readiness" as const }));
  const assumptions = envelope.typed_assumptions
    .filter((assumption) => assumption.has_assumed_value && !assumption.blocks_planner_ready)
    .map((assumption) => assumptionCopy(assumption));
  const unresolvedFixedEventIds = formal.fixed_events
    .filter((event) => !hasVerifiedFixedPlace(event.event_id, identities))
    .map((event) => event.event_id);
  const requiredBlockers = clarificationBlockers.length ? clarificationBlockers : fallbackBlockers;
  const blockers = uniqueBlockers(requiredBlockers);
  const genericItems = requiredConfirmationItems(envelope, requiredBlockers);
  const fixedPlaceItems = unresolvedFixedEventIds.map((eventId): ConfirmationItem => {
    const event = formal.fixed_events.find((item) => item.event_id === eventId);
    return {
      id: `fixed-place:${eventId}`,
      kind: "fixed_place",
      title: event?.title ?? "固定安排",
      detail: "这段时间会被保留；请确认具体地点后再安排路线。",
      eventId,
      identityId: fixedIdentityForEvent(eventId, identities)?.stable_id ?? null,
      tone: "todo",
    };
  });
  const unresolvedMustItems = identities
    .filter((identity) => identity.ownership === "must" && identity.resolution_status !== "verified")
    .map((identity): ConfirmationItem => ({
      id: `must-place:${identity.stable_id}`,
      kind: "must_place",
      title: `确认「${identity.original_name}」具体是哪一处`,
      detail: "确认后才会使用真实的位置和路线数据。",
      identityId: identity.stable_id,
      tone: "todo",
    }));
  const confirmationItems = [...genericItems, ...fixedPlaceItems, ...unresolvedMustItems];
  // Old Draft revisions may predate fixed-place readiness enforcement. Keep the
  // browser from issuing a request that the server must reject, while the server
  // remains the authority for every new immutable revision.
  const canGeneratePreview = isPlannerReady(envelope.planner_ready_status) && unresolvedFixedEventIds.length === 0;
  const actionableConfirmationItems = getActionableConfirmationItems(
    confirmationItems,
    identities,
    formal.fixed_events,
    envelope.clarification_queue,
  );
  const remainingActionableConfirmationCount = actionableConfirmationItems.length;
  const requiresTravelInformationEdit = !canGeneratePreview && remainingActionableConfirmationCount === 0;

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
    blockers,
    confirmationItems,
    confirmedItems: confirmedItems(formal.fixed_events, identities),
    remainingConfirmationCount: confirmationItems.length,
    remainingActionableConfirmationCount,
    requiresTravelInformationEdit,
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
      : requiresTravelInformationEdit
        ? "请先修改旅行信息，再生成首版路线。"
        : `还差 ${remainingActionableConfirmationCount} 项即可生成首版路线。`,
  };
}

export function getActionableConfirmationItems(
  items: ConfirmationItem[],
  identities: PlaceIdentity[],
  events: FixedEventIntent[],
  questions: IntentClarification[],
): ConfirmationItem[] {
  const questionIds = new Set(questions.map((question) => question.question_id));
  return items.filter((item) => {
    if (item.kind === "conflict") return false;
    if (item.kind === "clarification") return Boolean(item.questionId && questionIds.has(item.questionId));
    if (item.kind === "must_place") return identities.some((identity) => identity.stable_id === item.identityId);
    return item.kind === "fixed_place" && events.some((event) => event.event_id === item.eventId);
  });
}

function requiredConfirmationItems(
  envelope: SourceLinkedTripIntentEnvelope,
  blockers: ConfirmationBlocker[],
): ConfirmationItem[] {
  const questions = envelope.clarification_queue
    .filter((question) => question.blocking && !isPlaceIdentityClarification(question.reason_code));
  if (questions.length) {
    return questions.map((question) => confirmationItemFromQuestion(question));
  }
  return blockers.map((blocker, index) => ({
    id: `readiness:${index}:${blocker.title}`,
    kind: isConflictTitle(blocker.title) ? "conflict" : "clarification",
    title: blocker.title,
    detail: blocker.detail,
    questionId: null,
    tone: isConflictTitle(blocker.title) ? "conflict" : "todo",
  }));
}

function confirmationItemFromQuestion(question: IntentClarification): ConfirmationItem {
  const copy = clarificationCopy(question);
  const conflict = isConflictCode(question.reason_code);
  return {
    id: `clarification:${question.question_id}`,
    kind: conflict ? "conflict" : "clarification",
    title: copy.title,
    detail: copy.detail,
    questionId: question.question_id,
    tone: conflict ? "conflict" : "todo",
  };
}

function confirmedItems(events: FixedEventIntent[], identities: PlaceIdentity[]): ConfirmedItem[] {
  const fixed = events.flatMap((event) => {
    const identity = fixedIdentityForEvent(event.event_id, identities);
    return identity?.resolution_status === "verified"
      ? [{ id: `confirmed-fixed:${event.event_id}`, title: event.title, detail: `${identity.canonical_name ?? identity.original_name} · 时间已保留` }]
      : [];
  });
  const must = identities
    .filter((identity) => identity.ownership === "must" && identity.resolution_status === "verified")
    .map((identity) => ({ id: `confirmed-must:${identity.stable_id}`, title: identity.canonical_name ?? identity.original_name, detail: "已确认地点" }));
  return [...fixed, ...must];
}

function isPlaceIdentityClarification(code: string): boolean {
  return code === "fixed_place_identity_not_verified" || code === "fixed_event_identity_not_verified" || code === "must_place_identity_not_verified";
}

function isConflictCode(code: string): boolean {
  return code === "arrival_after_departure" || code === "fixed_event_overlap" || code === "fixed_event_outside_trip_dates";
}

function isConflictTitle(title: string): boolean {
  return title.includes("不能") || title.includes("重叠") || title.includes("不在旅行日期");
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
  return fixedIdentityForEvent(eventId, identities)?.resolution_status === "verified";
}

function fixedIdentityForEvent(
  eventId: string,
  identities: NonNullable<SourceLinkedTripIntentEnvelope["formal_contract"]["place_identities"]>,
): PlaceIdentity | null {
  const fixed = identities.filter((identity) => identity.ownership === "fixed");
  const matches = fixed.filter((identity) => identity.fixed_event_id === eventId || identity.stable_id === eventId);
  return matches[0] ?? (fixed.length === 1 ? fixed[0] : null);
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
