import type {
  RoutePreviewBlock,
  RoutePreviewItinerary,
  RoutePreviewItem,
  VerifiedPlaceReference,
} from "./routePreviewModel";

export type ReplacementRouteLegEvidence = {
  from_name: string;
  to_name: string;
  distance_m: number;
  duration_s: number;
  provider: "amap";
  data_status: "confirmed";
};

export type ReplacementRouteImpact = {
  safe_to_apply: boolean;
  before_duration_s: number | null;
  after_duration_s: number | null;
  delta_duration_s: number | null;
  inbound: ReplacementRouteLegEvidence | null;
  outbound: ReplacementRouteLegEvidence | null;
  blocking_reason: "route_unavailable" | "time_slot_conflict" | "fixed_event_at_risk" | null;
};

export type SafeReplaceCandidate = {
  stable_id: string;
  name: string;
  type: "scenic" | "restaurant";
  suggested_day: number;
  suggested_block: RoutePreviewBlock;
  reasoning_summary: string;
  itinerary_relation_summary: string;
  verified_place: VerifiedPlaceReference;
  route_impact: ReplacementRouteImpact;
};

export type SafeReplaceCandidateResponse = {
  task_id: string;
  target_day: number | null;
  target_block: RoutePreviewBlock | null;
  options: SafeReplaceCandidate[];
  candidate_source_summary?: string | null;
  candidate_discovery_status?: string | null;
};

export type SafeReplaceMutationEnvelope = {
  base_revision_id: string;
  mutation_kind: "swap";
  commands: Array<{
    type: "replace_stop";
    stop_id: string;
    replacement: {
      name: string;
      type: "scenic" | "restaurant";
      reasoning_summary: string;
      itinerary_relation_summary: string;
      verified_place: VerifiedPlaceReference;
      route_impact: ReplacementRouteImpact;
    };
  }>;
};

export type SafeReplaceRouteLeg = {
  fromName: string;
  toName: string;
  distanceMeters: number | null;
  durationSeconds: number;
};

export type SafeReplacePreviewModel = {
  change: { stopId: string; beforeName: string; afterName: string };
  before: { item: RoutePreviewItem; inbound: SafeReplaceRouteLeg | null; outbound: SafeReplaceRouteLeg | null };
  after: { item: RoutePreviewItem; inbound: SafeReplaceRouteLeg | null; outbound: SafeReplaceRouteLeg | null };
  protectedItems: Array<{ id: string; name: string; reason: string }>;
};

const SYSTEM_SUGGESTED_SOURCES = new Set(["auto_seeded_poi", "auto_seeded_meal", "auto_filled"]);

export function isSafeReplaceEligible(item: RoutePreviewItem): boolean {
  return Boolean(
    item.stable_id
      && !item.is_fixed
      && item.source_label !== "必去"
      && item.source_type
      && SYSTEM_SUGGESTED_SOURCES.has(item.source_type)
      && item.canonical_place_id
      && item.verified_place?.provider_place_id,
  );
}

export function parseSafeReplaceCandidates(
  value: unknown,
  currentProviderPlaceId?: string | null,
): SafeReplaceCandidate[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const candidates: SafeReplaceCandidate[] = [];
  for (const entry of value) {
    if (!isSafeReplaceCandidate(entry)) continue;
    if (
      !entry.route_impact.safe_to_apply
      || entry.route_impact.blocking_reason !== null
      || entry.route_impact.before_duration_s === null
      || entry.route_impact.after_duration_s === null
      || entry.route_impact.delta_duration_s === null
      || entry.route_impact.inbound === null
    ) continue;
    const providerPlaceId = entry.verified_place.provider_place_id;
    if (providerPlaceId === currentProviderPlaceId || seen.has(providerPlaceId)) continue;
    seen.add(providerPlaceId);
    candidates.push(entry);
    if (candidates.length === 3) break;
  }
  return candidates;
}

export function buildSafeReplaceCommandEnvelope(
  baseRevisionId: string,
  target: RoutePreviewItem,
  candidate: SafeReplaceCandidate,
): SafeReplaceMutationEnvelope {
  if (!isSafeReplaceEligible(target) || !target.stable_id) {
    throw new Error("replace_target_not_eligible");
  }
  return {
    base_revision_id: baseRevisionId,
    mutation_kind: "swap",
    commands: [{
      type: "replace_stop",
      stop_id: target.stable_id,
      replacement: {
        name: candidate.name,
        type: candidate.type,
        reasoning_summary: candidate.reasoning_summary,
        itinerary_relation_summary: candidate.itinerary_relation_summary,
        verified_place: candidate.verified_place,
        route_impact: candidate.route_impact,
      },
    }],
  };
}

export function buildSafeReplacePreviewModel(
  before: RoutePreviewItinerary,
  after: RoutePreviewItinerary,
  stopId: string,
): SafeReplacePreviewModel {
  const beforeStops = flattenStops(before);
  const afterStops = flattenStops(after);
  const beforeIndex = beforeStops.findIndex((entry) => entry.item.stable_id === stopId);
  const afterIndex = afterStops.findIndex((entry) => entry.item.stable_id === stopId);
  if (beforeIndex < 0 || afterIndex < 0) throw new Error("replace_preview_target_missing");
  const beforeStop = beforeStops[beforeIndex];
  const afterStop = afterStops[afterIndex];

  return {
    change: {
      stopId,
      beforeName: beforeStop.item.name,
      afterName: afterStop.item.name,
    },
    before: {
      item: beforeStop.item,
      inbound: routeLeg(beforeStop.item),
      outbound: outboundLeg(beforeStops, beforeIndex),
    },
    after: {
      item: afterStop.item,
      inbound: routeLeg(afterStop.item),
      outbound: outboundLeg(afterStops, afterIndex),
    },
    protectedItems: beforeStops
      .filter(({ item }) => item.stable_id !== stopId && (item.is_fixed || item.source_label === "必去"))
      .filter((entry) => {
        const afterEntry = afterStops.find(({ item }) => item.stable_id === entry.item.stable_id);
        return Boolean(afterEntry && unchangedScheduledItem(entry, afterEntry));
      })
      .map(({ item }) => ({
        id: item.stable_id!,
        name: item.name,
        reason: item.is_fixed ? "已经留好的时间，不会移动" : "你明确说想去",
      })),
  };
}

export function formatSafeReplaceRouteDelta(deltaSeconds: number | null): string {
  if (deltaSeconds === null) return "路程变化待确认";
  if (deltaSeconds === 0) return "路上时间大致不变";
  const minutes = Math.max(1, Math.round(Math.abs(deltaSeconds) / 60));
  return deltaSeconds < 0 ? `路上约少 ${minutes} 分钟` : `路上约多 ${minutes} 分钟`;
}

export function safeReplaceFailureMessage(
  code: string | undefined,
  phase: "candidates" | "preview" | "apply" | "undo",
  context?: Record<string, unknown>,
): string {
  const reasonCode = typeof context?.reason_code === "string" ? context.reason_code : code;
  if (reasonCode && ["stale_mutation_proposal", "proposal_base_revision_mismatch", "undo_target_not_current"].includes(reasonCode)) {
    return "路线刚刚发生了变化。请基于最新路线重新选择一个地点。";
  }
  if (reasonCode === "replacement_breaks_fixed_event") {
    return "这个地点可能赶不上后面的固定安排。你的原路线没有被改变。";
  }
  if (phase === "candidates") return "附近暂时没有找到不会打乱路线的已验证地点。先保留现在这一站。";
  if (phase === "undo") return "这次撤销没有保存。当前路线仍然保留。";
  if (phase === "apply") return "这次替换没有保存。原来的地点仍然保留。";
  return "暂时无法确认这次替换会怎么走。原来的地点仍然保留。";
}

export class LatestReplaceRequest {
  private current = 0;

  begin(): number {
    this.current += 1;
    return this.current;
  }

  cancel(): void {
    this.current += 1;
  }

  isLatest(requestId: number): boolean {
    return requestId === this.current;
  }
}

type FlatStop = {
  day: number;
  block: RoutePreviewBlock;
  item: RoutePreviewItem;
};

function flattenStops(itinerary: RoutePreviewItinerary): FlatStop[] {
  return itinerary.days.flatMap((day) => day.blocks.flatMap((block) => block.items.map((item) => ({
    day: day.day,
    block: block.block_type,
    item,
  }))));
}

function routeLeg(item: RoutePreviewItem): SafeReplaceRouteLeg | null {
  if (
    item.travel_data_status !== "confirmed"
      || !item.travel_from_name
      || item.travel_duration_s == null
      || item.travel_duration_s <= 0
  ) return null;
  return {
    fromName: item.travel_from_name,
    toName: item.name,
    distanceMeters: item.travel_distance_m != null && item.travel_distance_m > 0 ? item.travel_distance_m : null,
    durationSeconds: item.travel_duration_s,
  };
}

function outboundLeg(stops: FlatStop[], index: number): SafeReplaceRouteLeg | null {
  const current = stops[index];
  const next = stops[index + 1];
  if (!next || next.day !== current.day || next.item.travel_from_name !== current.item.name) return null;
  return routeLeg(next.item);
}

function unchangedScheduledItem(before: FlatStop, after: FlatStop): boolean {
  return before.day === after.day
    && before.block === after.block
    && before.item.name === after.item.name
    && before.item.start_time === after.item.start_time
    && before.item.end_time === after.item.end_time
    && before.item.is_fixed === after.item.is_fixed
    && before.item.canonical_place_id === after.item.canonical_place_id;
}

function isSafeReplaceCandidate(value: unknown): value is SafeReplaceCandidate {
  if (!isRecord(value) || !isNonEmptyString(value.stable_id) || !isNonEmptyString(value.name)) return false;
  if (value.type !== "scenic" && value.type !== "restaurant") return false;
  if (!Number.isInteger(value.suggested_day) || !["morning", "afternoon", "evening"].includes(String(value.suggested_block))) return false;
  if (!isNonEmptyString(value.reasoning_summary) || !isNonEmptyString(value.itinerary_relation_summary)) return false;
  if (!isVerifiedPlace(value.verified_place) || !isReplacementImpact(value.route_impact)) return false;
  return true;
}

function isVerifiedPlace(value: unknown): value is VerifiedPlaceReference {
  return isRecord(value)
    && isNonEmptyString(value.stable_id)
    && isNonEmptyString(value.original_name)
    && isNonEmptyString(value.canonical_name)
    && value.provider === "amap"
    && isNonEmptyString(value.provider_place_id)
    && isFiniteNumber(value.latitude)
    && isFiniteNumber(value.longitude);
}

function isReplacementImpact(value: unknown): value is ReplacementRouteImpact {
  if (!isRecord(value) || typeof value.safe_to_apply !== "boolean") return false;
  if (!isNullableFiniteNumber(value.before_duration_s)
    || !isNullableFiniteNumber(value.after_duration_s)
    || !isNullableFiniteNumber(value.delta_duration_s)) return false;
  if (!isNullableRouteLeg(value.inbound) || !isNullableRouteLeg(value.outbound)) return false;
  if (value.safe_to_apply && value.inbound === null) return false;
  return value.blocking_reason === null
    || value.blocking_reason === "route_unavailable"
    || value.blocking_reason === "time_slot_conflict"
    || value.blocking_reason === "fixed_event_at_risk";
}

function isNullableRouteLeg(value: unknown): value is ReplacementRouteLegEvidence | null {
  if (value === null) return true;
  return isRecord(value)
    && isNonEmptyString(value.from_name)
    && isNonEmptyString(value.to_name)
    && isFiniteNumber(value.distance_m)
    && value.distance_m > 0
    && isFiniteNumber(value.duration_s)
    && value.duration_s > 0
    && value.provider === "amap"
    && value.data_status === "confirmed";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isNullableFiniteNumber(value: unknown): value is number | null {
  return value === null || isFiniteNumber(value);
}
