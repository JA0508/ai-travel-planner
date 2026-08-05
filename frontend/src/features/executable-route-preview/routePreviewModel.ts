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
  source_label?: string | null;
  placement_reason?: string | null;
  travel_from_name?: string | null;
  travel_distance_m?: number | null;
  travel_duration_s?: number | null;
  travel_data_status?: "confirmed" | "unavailable" | "estimated" | null;
  travel_provider?: string | null;
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
