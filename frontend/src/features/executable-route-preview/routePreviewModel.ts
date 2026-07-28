export type RoutePreviewBlock = "morning" | "afternoon" | "evening";

export type RoutePreviewItem = {
  stable_id?: string | null;
  name: string;
  type: "scenic" | "restaurant" | "hotel";
  day?: number;
  start_time: string;
  end_time: string;
  duration_minutes?: number;
  is_fixed: boolean;
  source_type?: "user_seed" | "user_fixed" | "auto_seeded_poi" | "auto_seeded_meal" | "auto_filled";
  placement_reason?: string | null;
  travel_from_name?: string | null;
  travel_distance_m?: number | null;
  travel_duration_s?: number | null;
};

export type RoutePreviewDay = {
  day: number;
  blocks: Array<{
    block_type: RoutePreviewBlock;
    start_time: string;
    end_time: string;
    items: RoutePreviewItem[];
  }>;
};

export type RoutePreviewItinerary = {
  trip_days: number;
  days: RoutePreviewDay[];
  planner_realism?: {
    status?: string | null;
    headline?: string | null;
    issues?: Array<{ title?: string | null; detail?: string | null; description?: string | null }> | null;
    daily_loads?: Array<{
      day: number;
      classification: DayLoad["pace"];
      activity_count: number;
      fixed_count: number;
      activity_minutes: number;
      travel_minutes: number;
      route_distance_m: number | null;
      reason_codes: string[];
      explanation: string;
    }> | null;
  } | null;
};

export type DayLoad = {
  day: number;
  activityCount: number;
  fixedCount: number;
  activityMinutes: number;
  travelMinutes: number;
  routeDistanceMeters: number | null;
  pace: "relaxed" | "balanced" | "rushed" | "infeasible";
  paceLabel: "轻松" | "适中" | "偏赶" | "不可执行";
  explanation: string;
};

export type DayRepairPlan = {
  day: number;
  action: "move" | "remove";
  stopId: string;
  stopName: string;
  fromDay: number;
  toDay: number | null;
  targetBlock: RoutePreviewBlock | null;
  command: Record<string, unknown>;
  before: DayLoad;
};

const FLEXIBLE_SOURCE_TYPES = new Set<RoutePreviewItem["source_type"]>([
  "auto_seeded_poi",
  "auto_seeded_meal",
  "auto_filled",
]);

export function buildDayLoads(itinerary: RoutePreviewItinerary): DayLoad[] {
  return (itinerary.planner_realism?.daily_loads ?? []).map((load) => {
    const pace = load.classification;
    const paceLabels: Record<DayLoad["pace"], DayLoad["paceLabel"]> = {
      relaxed: "轻松",
      balanced: "适中",
      rushed: "偏赶",
      infeasible: "不可执行",
    };
    return {
      day: load.day,
      activityCount: load.activity_count,
      fixedCount: load.fixed_count,
      activityMinutes: load.activity_minutes,
      travelMinutes: load.travel_minutes,
      routeDistanceMeters: load.route_distance_m,
      pace,
      paceLabel: paceLabels[pace],
      explanation: load.explanation,
    };
  });
}

export function buildDayRelaxationPlan(
  itinerary: RoutePreviewItinerary,
  dayNumber: number,
  baseRevisionId: string,
): DayRepairPlan | null {
  const day = itinerary.days.find((candidate) => candidate.day === dayNumber);
  if (!day) return null;
  const before = buildDayLoads(itinerary).find((entry) => entry.day === dayNumber);
  if (!before) return null;
  if (before.pace !== "rushed") return null;
  const flexible = [...day.blocks]
    .reverse()
    .flatMap((block) => [...block.items].reverse().map((item) => ({ block, item })))
    .find(({ item }) => Boolean(item.stable_id) && !item.is_fixed && FLEXIBLE_SOURCE_TYPES.has(item.source_type));
  if (!flexible?.item.stable_id) return null;
  const nextDay = itinerary.days.find((candidate) => candidate.day === dayNumber + 1);
  if (nextDay) {
    return {
      day: dayNumber,
      action: "move",
      stopId: flexible.item.stable_id,
      stopName: flexible.item.name,
      fromDay: dayNumber,
      toDay: nextDay.day,
      targetBlock: flexible.block.block_type,
      command: {
        schema_version: "1.0",
        base_revision_id: baseRevisionId,
        mutation_kind: "route_edit",
        repair: { target_day: dayNumber, goal: "relax_day" },
        commands: [{
          type: "move_stop",
          stop_id: flexible.item.stable_id,
          target_day: nextDay.day,
          target_block: flexible.block.block_type,
          placement: { at_end: true },
        }],
      },
      before,
    };
  }
  return {
    day: dayNumber,
    action: "remove",
    stopId: flexible.item.stable_id,
    stopName: flexible.item.name,
    fromDay: dayNumber,
    toDay: null,
    targetBlock: null,
    command: {
      schema_version: "1.0",
      base_revision_id: baseRevisionId,
      mutation_kind: "route_edit",
      repair: { target_day: dayNumber, goal: "relax_day" },
      commands: [{ type: "remove_stop", stop_id: flexible.item.stable_id }],
    },
    before,
  };
}

export function buildUserFacingRisks(itinerary: RoutePreviewItinerary, loads: DayLoad[]): string[] {
  const risks = loads
    .filter((load) => load.pace === "rushed" || load.pace === "infeasible")
    .map((load) => `第 ${load.day} 天${load.paceLabel}：${load.explanation}`);
  for (const issue of itinerary.planner_realism?.issues ?? []) {
    const text = issue.detail ?? issue.description ?? issue.title;
    if (text && !risks.includes(text)) risks.push(text);
  }
  return risks;
}

export function formatMinutes(value: number): string {
  if (value < 60) return `${value} 分钟`;
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return minutes ? `${hours} 小时 ${minutes} 分钟` : `${hours} 小时`;
}

export function formatDistance(value: number | null): string {
  if (value === null) return "路线距离待确认";
  return value >= 1000 ? `${(value / 1000).toFixed(1)} 公里` : `${value} 米`;
}
