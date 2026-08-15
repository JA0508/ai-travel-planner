import type {
  EditableRouteDay,
  EditableRouteStop,
  POIDetailPreview,
  RoutePreviewMap,
  RouteSegmentPreviewResult,
  TimelineBlockType,
} from "../MobileEditRouteWorkspace";
import type { RoutePreviewMode } from "../RouteMapPane";

export type EvidenceKind =
  | "provider-fact"
  | "user-constraint"
  | "deterministic-inference"
  | "heuristic"
  | "missing-data";

export type PlaceTrustVerdict =
  | "strong-fit"
  | "reasonable-fit"
  | "uncertain-fit"
  | "needs-review";

export type SpatialTopology =
  | "linear"
  | "minor-detour"
  | "backtracking"
  | "isolated"
  | "unknown";

export type RouteSegmentSummary = {
  key: string;
  fromName: string;
  toName: string;
  durationSeconds?: number;
  durationLabel?: string;
  distanceLabel?: string;
  travelModeLabel: string;
  source: "provider" | "scheduled" | "estimated" | "missing";
  pressure: "normal" | "watch" | "high" | "unknown";
};

export type RouteNeighborSummary = {
  id: string;
  name: string;
  role: "previous" | "next";
  isFixed: boolean;
};

export type SpatialObservation = {
  key: string;
  kind: EvidenceKind;
  label: string;
  detail: string;
};

export type PlaceCaveat = {
  key: string;
  kind: EvidenceKind;
  label: string;
  detail: string;
};

export type PlaceEvidenceItem = {
  key: string;
  kind: EvidenceKind;
  label: string;
  detail: string;
};

export type PlaceActionAvailability = {
  canKeep: boolean;
  canReplace: boolean;
  canRemove: boolean;
  canMoveToUnplanned: boolean;
  protectedBoundaryWarning?: string;
};

export type PlaceDetailViewModel = {
  identity: {
    id: string;
    name: string;
    category?: string;
    address?: string;
    photoUrl?: string;
  };
  schedule: {
    dayIndex: number;
    blockLabel: string;
    startTime?: string;
    endTime?: string;
    durationLabel?: string;
  };
  trust: {
    verdict: PlaceTrustVerdict;
    label: string;
    headline: string;
    explanation: string;
  };
  routeFit: {
    topology: SpatialTopology;
    previousStop?: RouteNeighborSummary;
    nextStop?: RouteNeighborSummary;
    inboundSegment?: RouteSegmentSummary;
    outboundSegment?: RouteSegmentSummary;
    spatialSummary: string;
    observations: SpatialObservation[];
  };
  visitContext: {
    role:
      | "anchor"
      | "fixed-event"
      | "route-connector"
      | "meal"
      | "flexible-stop"
      | "completion-suggestion"
      | "unknown";
    label: string;
    reason?: string;
  };
  evidence: PlaceEvidenceItem[];
  caveats: PlaceCaveat[];
  actions: PlaceActionAvailability;
};

export type BuildPlaceDetailViewModelInput = {
  stop: EditableRouteStop;
  allDays: EditableRouteDay[];
  originLabel: string;
  routePreviewMap: RoutePreviewMap;
  routeMode: RoutePreviewMode;
  poiDetail: POIDetailPreview | null;
  poiDetailState: "idle" | "loading" | "failed";
};

export function buildPlaceDetailViewModel({
  stop,
  allDays,
  originLabel,
  routePreviewMap,
  routeMode,
  poiDetail,
  poiDetailState,
}: BuildPlaceDetailViewModelInput): PlaceDetailViewModel {
  const day = allDays.find((entry) => entry.day === stop.day) ?? null;
  const stopIndex = day?.stops.findIndex((candidate) => candidate.id === stop.id) ?? -1;
  const previousStop = day && stopIndex > 0 ? day.stops[stopIndex - 1] : null;
  const nextStop = day && stopIndex >= 0 && stopIndex < day.stops.length - 1
    ? day.stops[stopIndex + 1]
    : null;
  const spatial = buildSpatialReasoning({
    stop,
    previousStop,
    nextStop,
    originLabel,
    routePreviewMap,
    routeMode,
  });
  const evidence = buildEvidence({
    stop,
    previousStop,
    nextStop,
    spatial,
    poiDetail,
    poiDetailState,
  });
  const caveats = buildCaveats({
    stop,
    spatial,
    poiDetail,
    poiDetailState,
  });
  const trust = buildTrustVerdict({ stop, spatial, poiDetail, caveats });

  return {
    identity: {
      id: stop.id,
      name: stop.item.name,
      category: poiDetail?.category ?? stop.item.source_label ?? formatStopType(stop.item.type),
      address: poiDetail?.address ?? undefined,
      photoUrl: poiDetail?.photo_url ?? undefined,
    },
    schedule: {
      dayIndex: stop.day,
      blockLabel: formatBlockLabel(stop.blockType),
      startTime: stop.item.start_time,
      endTime: stop.item.end_time,
      durationLabel: formatTimeDuration(stop.item.start_time, stop.item.end_time),
    },
    trust,
    routeFit: {
      topology: spatial.topology,
      previousStop: previousStop
        ? { id: previousStop.id, name: previousStop.item.name, role: "previous", isFixed: previousStop.item.is_fixed }
        : undefined,
      nextStop: nextStop
        ? { id: nextStop.id, name: nextStop.item.name, role: "next", isFixed: nextStop.item.is_fixed }
        : undefined,
      inboundSegment: spatial.inbound,
      outboundSegment: spatial.outbound,
      spatialSummary: spatial.summary,
      observations: spatial.observations,
    },
    visitContext: buildVisitContext(stop, previousStop, nextStop),
    evidence,
    caveats,
    actions: {
      canKeep: true,
      canReplace: !stop.item.is_fixed,
      canRemove: !stop.item.is_fixed,
      canMoveToUnplanned: !stop.item.is_fixed,
      protectedBoundaryWarning: stop.item.is_fixed
        ? "这是固定或锁定地点，当前操作不会移动它。"
        : nextStop?.item.is_fixed || previousStop?.item.is_fixed
          ? "调整这个地点前后，会先保护相邻固定安排。"
          : undefined,
    },
  };
}

export function buildSpatialReasoning({
  stop,
  previousStop,
  nextStop,
  originLabel,
  routePreviewMap,
  routeMode,
}: {
  stop: EditableRouteStop;
  previousStop: EditableRouteStop | null;
  nextStop: EditableRouteStop | null;
  originLabel: string;
  routePreviewMap: RoutePreviewMap;
  routeMode: RoutePreviewMode;
}): {
  topology: SpatialTopology;
  inbound?: RouteSegmentSummary;
  outbound?: RouteSegmentSummary;
  summary: string;
  observations: SpatialObservation[];
  caveats: PlaceCaveat[];
} {
  const inbound = buildInboundSegmentSummary(stop, previousStop, originLabel, routePreviewMap, routeMode);
  const outbound = nextStop
    ? buildOutboundSegmentSummary(stop, nextStop, routePreviewMap, routeMode)
    : undefined;
  const observations: SpatialObservation[] = [];
  const caveats: PlaceCaveat[] = [];

  if (!hasCoordinates(stop)) {
    caveats.push({
      key: "missing-current-coordinates",
      kind: "missing-data",
      label: "缺少坐标",
      detail: "当前地点没有坐标，无法判断真实空间关系。",
    });
  }
  if (!inbound && previousStop) {
    caveats.push({
      key: "missing-inbound-route",
      kind: "missing-data",
      label: "缺少到达路线",
      detail: "尚未获得上一地点到当前地点的路线段数据。",
    });
  }
  if (!outbound && nextStop) {
    caveats.push({
      key: "missing-outbound-route",
      kind: "missing-data",
      label: "缺少离开路线",
      detail: "尚未获得当前地点到下一地点的路线段数据。",
    });
  }

  const knownDurations = [inbound?.durationSeconds, outbound?.durationSeconds].filter(
    (value): value is number => typeof value === "number",
  );
  const longSegment = knownDurations.some((duration) => duration >= 45 * 60);
  const pressureSegment = knownDurations.some((duration) => duration >= 70 * 60);
  let topology: SpatialTopology = "unknown";

  if (!previousStop && !nextStop) {
    topology = "isolated";
  } else if (caveats.some((caveat) => caveat.key.startsWith("missing-current"))) {
    topology = "unknown";
  } else if (pressureSegment) {
    topology = "minor-detour";
    observations.push({
      key: "route-pressure",
      kind: "heuristic",
      label: "路线压力",
      detail: "至少一段相邻通勤超过约 70 分钟，需要复核是否值得保留。",
    });
  } else if (longSegment) {
    topology = "minor-detour";
    observations.push({
      key: "minor-detour",
      kind: "heuristic",
      label: "轻微绕行可能",
      detail: "相邻路线段较长，可能会压缩游玩时间。",
    });
  } else if (inbound || outbound) {
    topology = "linear";
    observations.push({
      key: "route-connector",
      kind: "deterministic-inference",
      label: "路线连接",
      detail: "当前地点与相邻停留点存在可解释的前后连接。",
    });
  }

  return {
    topology,
    inbound,
    outbound,
    summary: buildSpatialSummary(topology, stop, previousStop, nextStop, inbound, outbound),
    observations,
    caveats,
  };
}

function buildInboundSegmentSummary(
  stop: EditableRouteStop,
  previousStop: EditableRouteStop | null,
  originLabel: string,
  routePreviewMap: RoutePreviewMap,
  routeMode: RoutePreviewMode,
): (RouteSegmentSummary & { durationSeconds?: number }) | undefined {
  if (!previousStop) {
    const preview = routePreviewMap[buildOriginRouteSegmentKey(stop.day, stop)];
    if (preview) {
      return summarizePreviewSegment(preview, routeMode);
    }
    if (stop.item.travel_from_name && stop.item.travel_duration_s !== null) {
      return summarizeScheduledSegment({
        key: buildOriginRouteSegmentKey(stop.day, stop),
        fromName: stop.item.travel_from_name,
        toName: stop.item.name,
        distanceMeters: stop.item.travel_distance_m,
        durationSeconds: stop.item.travel_duration_s,
        routeMode,
      });
    }
    return {
      key: buildOriginRouteSegmentKey(stop.day, stop),
      fromName: originLabel,
      toName: stop.item.name,
      travelModeLabel: formatRouteMode(routeMode),
      source: "missing",
      pressure: "unknown",
    };
  }

  const preview = routePreviewMap[buildRouteSegmentKey(previousStop, stop)];
  if (preview) {
    return summarizePreviewSegment(preview, routeMode);
  }
  if (stop.item.travel_from_name === previousStop.item.name && stop.item.travel_duration_s !== null) {
    return summarizeScheduledSegment({
      key: buildRouteSegmentKey(previousStop, stop),
      fromName: previousStop.item.name,
      toName: stop.item.name,
      distanceMeters: stop.item.travel_distance_m,
      durationSeconds: stop.item.travel_duration_s,
      routeMode,
    });
  }
  return undefined;
}

function buildOutboundSegmentSummary(
  stop: EditableRouteStop,
  nextStop: EditableRouteStop,
  routePreviewMap: RoutePreviewMap,
  routeMode: RoutePreviewMode,
): (RouteSegmentSummary & { durationSeconds?: number }) | undefined {
  const preview = routePreviewMap[buildRouteSegmentKey(stop, nextStop)];
  if (preview) {
    return summarizePreviewSegment(preview, routeMode);
  }
  if (nextStop.item.travel_from_name === stop.item.name && nextStop.item.travel_duration_s !== null) {
    return summarizeScheduledSegment({
      key: buildRouteSegmentKey(stop, nextStop),
      fromName: stop.item.name,
      toName: nextStop.item.name,
      distanceMeters: nextStop.item.travel_distance_m,
      durationSeconds: nextStop.item.travel_duration_s,
      routeMode,
    });
  }
  return undefined;
}

function summarizePreviewSegment(
  segment: RouteSegmentPreviewResult,
  fallbackMode: RoutePreviewMode,
): RouteSegmentSummary & { durationSeconds: number } {
  const estimated = segment.source.startsWith("local_estimate");
  return {
    key: segment.segment_key,
    fromName: segment.from_name,
    toName: segment.to_name,
    durationLabel: formatDuration(segment.duration_s),
    distanceLabel: formatDistance(segment.distance_m),
    travelModeLabel: formatRouteMode(segment.mode ?? fallbackMode),
    source: estimated ? "estimated" : "provider",
    pressure: routePressure(segment.duration_s),
    durationSeconds: segment.duration_s,
  };
}

function summarizeScheduledSegment({
  key,
  fromName,
  toName,
  distanceMeters,
  durationSeconds,
  routeMode,
}: {
  key: string;
  fromName: string;
  toName: string;
  distanceMeters: number | null;
  durationSeconds: number;
  routeMode: RoutePreviewMode;
}): RouteSegmentSummary & { durationSeconds: number } {
  return {
    key,
    fromName,
    toName,
    durationLabel: formatDuration(durationSeconds),
    distanceLabel: distanceMeters !== null ? formatDistance(distanceMeters) : undefined,
    travelModeLabel: formatRouteMode(routeMode),
    source: "scheduled",
    pressure: routePressure(durationSeconds),
    durationSeconds,
  };
}

function buildEvidence({
  stop,
  previousStop,
  nextStop,
  spatial,
  poiDetail,
  poiDetailState,
}: {
  stop: EditableRouteStop;
  previousStop: EditableRouteStop | null;
  nextStop: EditableRouteStop | null;
  spatial: ReturnType<typeof buildSpatialReasoning>;
  poiDetail: POIDetailPreview | null;
  poiDetailState: "idle" | "loading" | "failed";
}): PlaceEvidenceItem[] {
  const evidence: PlaceEvidenceItem[] = [
    {
      key: "schedule",
      kind: stop.item.is_fixed ? "user-constraint" : "deterministic-inference",
      label: "时间安排",
      detail: `第 ${stop.day} 天 ${formatBlockLabel(stop.blockType)} · ${stop.item.start_time}-${stop.item.end_time}`,
    },
  ];
  if (poiDetail?.address) {
    evidence.push({
      key: "provider-address",
      kind: "provider-fact",
      label: "地点地址",
      detail: poiDetail.address,
    });
  }
  if (poiDetail?.category) {
    evidence.push({
      key: "provider-category",
      kind: "provider-fact",
      label: "地点类型",
      detail: poiDetail.category,
    });
  }
  if (stop.item.source_type === "user_seed" || stop.item.source_type === "user_fixed") {
    evidence.push({
      key: "user-source",
      kind: "user-constraint",
      label: "来自用户输入",
      detail: stop.item.source_reason ?? stop.item.source_label ?? "用户明确给出的地点会被优先保护。",
    });
  }
  if (spatial.inbound) {
    evidence.push({
      key: "inbound-segment",
      kind: spatial.inbound.source === "provider" ? "provider-fact" : "deterministic-inference",
      label: "到达路线",
      detail: segmentEvidenceText(spatial.inbound),
    });
  }
  if (spatial.outbound) {
    evidence.push({
      key: "outbound-segment",
      kind: spatial.outbound.source === "provider" ? "provider-fact" : "deterministic-inference",
      label: "离开路线",
      detail: segmentEvidenceText(spatial.outbound),
    });
  }
  if (previousStop || nextStop) {
    evidence.push({
      key: "neighbor-order",
      kind: "deterministic-inference",
      label: "前后位置",
      detail: [
        previousStop ? `前一站 ${previousStop.item.name}` : null,
        nextStop ? `后一站 ${nextStop.item.name}` : null,
      ].filter(Boolean).join(" · "),
    });
  }
  if (!poiDetail && poiDetailState !== "loading") {
    evidence.push({
      key: "missing-poi-detail",
      kind: "missing-data",
      label: "地点详情",
      detail: "暂未获得 provider 地点详情，不能确认地址、营业时间或照片。",
    });
  }
  return evidence;
}

function buildCaveats({
  stop,
  spatial,
  poiDetail,
  poiDetailState,
}: {
  stop: EditableRouteStop;
  spatial: ReturnType<typeof buildSpatialReasoning>;
  poiDetail: POIDetailPreview | null;
  poiDetailState: "idle" | "loading" | "failed";
}): PlaceCaveat[] {
  const caveats = [...spatial.caveats];
  if (!poiDetail?.open_time) {
    caveats.push({
      key: "missing-open-time",
      kind: "missing-data",
      label: "营业时间待验证",
      detail: poiDetailState === "loading" ? "正在请求地点详情。" : "当前无法确认该地点是否覆盖安排时间。",
    });
  }
  if (spatial.topology === "minor-detour") {
    caveats.push({
      key: "route-pressure-caveat",
      kind: "heuristic",
      label: "可能压缩游玩时间",
      detail: "相邻路线段较长，建议结合当天固定事件和停留时长复核。",
    });
  }
  if (stop.item.is_fixed) {
    caveats.push({
      key: "fixed-event-boundary",
      kind: "user-constraint",
      label: "固定边界",
      detail: "这个地点不可被自动替换或移除。",
    });
  }
  return uniqueByKey(caveats);
}

function buildTrustVerdict({
  stop,
  spatial,
  poiDetail,
  caveats,
}: {
  stop: EditableRouteStop;
  spatial: ReturnType<typeof buildSpatialReasoning>;
  poiDetail: POIDetailPreview | null;
  caveats: PlaceCaveat[];
}): PlaceDetailViewModel["trust"] {
  if (spatial.topology === "minor-detour" || caveats.some((caveat) => caveat.kind === "heuristic")) {
    return {
      verdict: "needs-review",
      label: "Needs review",
      headline: "这个地点可能带来路线压力",
      explanation: "系统只能确认它在时间线上成立，但相邻移动成本需要复核。",
    };
  }
  if (!poiDetail || caveats.some((caveat) => caveat.kind === "missing-data")) {
    return {
      verdict: "uncertain-fit",
      label: "Uncertain fit",
      headline: "位置关系可读，但事实证据不足",
      explanation: "当前缺少 provider 地点详情或完整路线段，不应把启发式判断当作事实。",
    };
  }
  if (stop.item.is_fixed || spatial.topology === "linear") {
    return {
      verdict: stop.item.is_fixed ? "strong-fit" : "reasonable-fit",
      label: stop.item.is_fixed ? "Strong route fit" : "Reasonable fit",
      headline: stop.item.is_fixed ? "这是受保护的行程边界" : "这个地点与前后路线衔接合理",
      explanation: spatial.summary,
    };
  }
  return {
    verdict: "reasonable-fit",
    label: "Reasonable fit",
    headline: "这个地点可以保留，但仍适合细看证据",
    explanation: spatial.summary,
  };
}

function buildVisitContext(
  stop: EditableRouteStop,
  previousStop: EditableRouteStop | null,
  nextStop: EditableRouteStop | null,
): PlaceDetailViewModel["visitContext"] {
  if (stop.item.is_fixed || stop.item.source_type === "user_fixed") {
    return {
      role: "fixed-event",
      label: "Fixed event",
      reason: "用户或调度层已把它作为固定边界处理。",
    };
  }
  if (stop.item.type === "hotel") {
    return { role: "anchor", label: "Anchor", reason: "住宿/起止锚点用于稳定当天路线。" };
  }
  if (stop.item.type === "restaurant") {
    return { role: "meal", label: "Meal anchor", reason: "餐食点用于支撑午后或晚间节奏。" };
  }
  if (stop.item.source_type === "auto_filled") {
    return {
      role: "completion-suggestion",
      label: "Completion suggestion",
      reason: stop.item.source_reason ?? "它来自补全流程，用于降低当前时间段空缺。",
    };
  }
  if (previousStop && nextStop) {
    return {
      role: "route-connector",
      label: "Route connector",
      reason: "它位于两个已安排地点之间，需要同时看进出路线。",
    };
  }
  return {
    role: "flexible-stop",
    label: "Flexible stop",
    reason: stop.item.placement_reason ?? "这是当前路线中的可编辑停留点。",
  };
}

function buildSpatialSummary(
  topology: SpatialTopology,
  stop: EditableRouteStop,
  previousStop: EditableRouteStop | null,
  nextStop: EditableRouteStop | null,
  inbound?: RouteSegmentSummary,
  outbound?: RouteSegmentSummary,
): string {
  if (topology === "isolated") {
    return "当前地点是当天唯一停留点，无法从前后路线判断空间作用。";
  }
  if (topology === "unknown") {
    return "尚未获得完整路线段数据，当前只能确认地点顺序，无法判断实际通勤成本。";
  }
  if (topology === "minor-detour") {
    return "相邻路线段偏长，可能形成绕行或压缩当天停留时间。";
  }
  return [
    previousStop ? `它承接 ${previousStop.item.name}` : `它从当天起点进入路线`,
    nextStop ? `并连接到 ${nextStop.item.name}` : "并作为当天后段收口",
    inbound?.durationLabel || outbound?.durationLabel
      ? `相邻通勤约 ${[inbound?.durationLabel, outbound?.durationLabel].filter(Boolean).join(" / ")}`
      : null,
  ].filter(Boolean).join("，") + "。";
}

function segmentEvidenceText(segment: RouteSegmentSummary): string {
  return `${segment.fromName} → ${segment.toName}${
    segment.durationLabel ? ` · ${segment.durationLabel}` : ""
  }${segment.distanceLabel ? ` · ${segment.distanceLabel}` : ""} · ${segment.travelModeLabel}`;
}

function buildRouteSegmentKey(fromStop: EditableRouteStop, toStop: EditableRouteStop): string {
  return `${fromStop.id}->${toStop.id}`;
}

function buildOriginRouteSegmentKey(dayNumber: number, toStop: EditableRouteStop): string {
  return `origin-day-${dayNumber}->${toStop.id}`;
}

export function buildRelatedRouteSegmentKeys(
  stop: EditableRouteStop,
  allDays: EditableRouteDay[],
): string[] {
  const day = allDays.find((entry) => entry.day === stop.day) ?? null;
  const stopIndex = day?.stops.findIndex((candidate) => candidate.id === stop.id) ?? -1;
  if (!day || stopIndex < 0) {
    return [];
  }
  const previousStop = stopIndex > 0 ? day.stops[stopIndex - 1] : null;
  const nextStop = stopIndex < day.stops.length - 1 ? day.stops[stopIndex + 1] : null;
  return [
    previousStop ? buildRouteSegmentKey(previousStop, stop) : buildOriginRouteSegmentKey(day.day, stop),
    nextStop ? buildRouteSegmentKey(stop, nextStop) : null,
  ].filter((key): key is string => key !== null);
}

export function buildNeighborStopIds(stop: EditableRouteStop, allDays: EditableRouteDay[]): string[] {
  const day = allDays.find((entry) => entry.day === stop.day) ?? null;
  const stopIndex = day?.stops.findIndex((candidate) => candidate.id === stop.id) ?? -1;
  if (!day || stopIndex < 0) {
    return [];
  }
  return [day.stops[stopIndex - 1]?.id, day.stops[stopIndex + 1]?.id].filter(
    (id): id is string => Boolean(id),
  );
}

function routePressure(durationSeconds: number): RouteSegmentSummary["pressure"] {
  if (durationSeconds >= 70 * 60) {
    return "high";
  }
  if (durationSeconds >= 45 * 60) {
    return "watch";
  }
  return "normal";
}

function hasCoordinates(stop: EditableRouteStop): boolean {
  return typeof stop.item.latitude === "number" && typeof stop.item.longitude === "number";
}

function formatStopType(type: EditableRouteStop["item"]["type"]): string {
  if (type === "restaurant") {
    return "餐食";
  }
  if (type === "hotel") {
    return "住宿";
  }
  return "地点";
}

function formatBlockLabel(blockType: TimelineBlockType): string {
  if (blockType === "morning") {
    return "上午";
  }
  if (blockType === "afternoon") {
    return "下午";
  }
  return "晚上";
}

function formatRouteMode(mode: RoutePreviewMode): string {
  if (mode === "transit") {
    return "公交地铁";
  }
  if (mode === "drive") {
    return "驾车";
  }
  return "步行";
}

function formatDuration(seconds: number): string {
  return `${Math.round(seconds / 60)} min`;
}

function formatDistance(meters: number): string {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${meters} m`;
}

function formatTimeDuration(startTime?: string, endTime?: string): string | undefined {
  if (!startTime || !endTime) {
    return undefined;
  }
  const start = parseTimeMinutes(startTime);
  const end = parseTimeMinutes(endTime);
  if (start === null || end === null || end <= start) {
    return undefined;
  }
  return formatDuration((end - start) * 60);
}

function parseTimeMinutes(value: string): number | null {
  const match = value.match(/^(\d{1,2}):(\d{2})/);
  if (!match) {
    return null;
  }
  return Number(match[1]) * 60 + Number(match[2]);
}

function uniqueByKey<T extends { key: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (seen.has(item.key)) {
      return false;
    }
    seen.add(item.key);
    return true;
  });
}
