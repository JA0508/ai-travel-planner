import type {
  ItineraryLike,
  POIDetailPreview,
  RoutePreviewMap,
  ScheduledItemLike,
} from "../MobileEditRouteWorkspace";
import type { BuildTripReadinessViewModelInput } from "../readiness/tripReadinessModel";

type FixturePlannerRealism = NonNullable<BuildTripReadinessViewModelInput["plannerRealism"]>;
type FixtureCompletion = NonNullable<BuildTripReadinessViewModelInput["completion"]>;
type FixtureBoundary = NonNullable<BuildTripReadinessViewModelInput["boundaryExplanation"]>;
type FixtureAssumptions = NonNullable<BuildTripReadinessViewModelInput["planningAssumptions"]>;

export type ResultWorkspaceFixture = {
  key: "complete" | "minor-gaps" | "route-risk" | "missing-data";
  label: string;
  city: string;
  tripDays: number;
  itinerary: ItineraryLike;
  completion: FixtureCompletion | null;
  plannerRealism: FixturePlannerRealism | null;
  boundaryExplanation: FixtureBoundary;
  planningAssumptions: FixtureAssumptions;
  routePreviewMap: RoutePreviewMap;
  poiDetailFixtures: Record<string, POIDetailPreview>;
};

type FixtureStop = ScheduledItemLike & { block: "morning" | "afternoon" | "evening" };

const day1Stops: FixtureStop[] = [
  stop("西湖断桥", "scenic", "morning", "09:00:00", "10:30:00", 30.2588, 120.1475, {
    source_type: "user_seed",
    source_label: "想去地点",
    source_reason: "用户明确提到想看西湖。",
    travel_from_name: "杭州东站",
    travel_duration_s: 1380,
    travel_distance_m: 8200,
  }),
  stop("浙江省博物馆", "scenic", "afternoon", "11:00:00", "13:00:00", 30.2521, 120.1434, {
    travel_from_name: "西湖断桥",
    travel_duration_s: 900,
    travel_distance_m: 1800,
    source_type: "auto_filled",
    source_label: "补全地点",
    source_reason: "位于西湖路线附近，可承接上午文化路线。",
  }),
  stop("湖滨银泰晚餐", "restaurant", "evening", "18:00:00", "19:30:00", 30.256, 120.1666, {
    travel_from_name: "浙江省博物馆",
    travel_duration_s: 1020,
    travel_distance_m: 3100,
    source_type: "auto_seeded_meal",
    source_label: "餐食锚点",
    source_reason: "晚餐作为第一天夜间收口。",
  }),
];

const day2Stops: FixtureStop[] = [
  stop("灵隐寺", "scenic", "morning", "09:00:00", "11:00:00", 30.2401, 120.1023, {
    source_type: "user_fixed",
    source_label: "已锁定",
    source_reason: "用户要求第二天上午优先安排灵隐寺。",
    is_fixed: true,
    travel_from_name: "湖滨银泰晚餐",
    travel_duration_s: 2200,
    travel_distance_m: 9600,
  }),
  stop("法喜寺", "scenic", "afternoon", "13:20:00", "15:00:00", 30.2326, 120.0944, {
    source_type: "user_seed",
    source_label: "想去地点",
    source_reason: "用户已种草寺庙路线。",
    travel_from_name: "灵隐寺",
    travel_duration_s: 720,
    travel_distance_m: 1400,
  }),
  stop("龙井村茶歇", "scenic", "afternoon", "15:30:00", "17:00:00", 30.2269, 120.1119, {
    source_type: "auto_filled",
    source_label: "顺路补全",
    source_reason: "连接寺庙路线和晚间回城。",
    travel_from_name: "法喜寺",
    travel_duration_s: 960,
    travel_distance_m: 3200,
  }),
];

const day3Stops: FixtureStop[] = [
  stop("良渚博物院", "scenic", "morning", "09:30:00", "11:30:00", 30.3864, 120.0478, {
    source_type: "auto_filled",
    source_label: "文化补全",
    source_reason: "补强第三天文化主线。",
    travel_from_name: "龙井村茶歇",
    travel_duration_s: 3600,
    travel_distance_m: 28000,
  }),
  stop("杭州东站", "hotel", "evening", "17:00:00", "18:00:00", 30.2909, 120.2123, {
    source_type: "user_fixed",
    source_label: "离开边界",
    source_reason: "第三天晚上从杭州东站离开。",
    is_fixed: true,
    travel_from_name: "良渚博物院",
    travel_duration_s: 3000,
    travel_distance_m: 24500,
  }),
];

export const resultWorkspaceFixtures: ResultWorkspaceFixture[] = [
  buildFixture("complete", "Complete trip", {
    completeness: 94,
    plannerStatus: "executable",
    sparseBlocks: [],
    routeRisk: false,
    missingPoi: false,
  }),
  buildFixture("minor-gaps", "Minor gaps", {
    completeness: 82,
    plannerStatus: "executable",
    sparseBlocks: ["Day 2 evening"],
    routeRisk: false,
    missingPoi: true,
  }),
  buildFixture("route-risk", "Route risk", {
    completeness: 71,
    plannerStatus: "needs_repair",
    sparseBlocks: ["Day 3 afternoon"],
    routeRisk: true,
    missingPoi: false,
  }),
  buildFixture("missing-data", "Missing provider data", {
    completeness: 76,
    plannerStatus: "needs_repair",
    sparseBlocks: ["Day 1 afternoon"],
    routeRisk: false,
    missingPoi: true,
    missingRoutes: true,
  }),
];

export function getResultWorkspaceFixture(key: string | null): ResultWorkspaceFixture {
  return resultWorkspaceFixtures.find((fixture) => fixture.key === key) ?? resultWorkspaceFixtures[0];
}

function buildFixture(
  key: ResultWorkspaceFixture["key"],
  label: string,
  options: {
    completeness: number;
    plannerStatus: string;
    sparseBlocks: string[];
    routeRisk: boolean;
    missingPoi: boolean;
    missingRoutes?: boolean;
  },
): ResultWorkspaceFixture {
  const itinerary: ItineraryLike = {
    planning_anchor_source: {
      source_type: "arrival_anchor",
      source_name: "杭州东站",
      latitude: 30.2909,
      longitude: 120.2123,
    },
    days: [
      day(1, day1Stops),
      day(2, day2Stops),
      day(3, day3Stops),
    ],
  };
  return {
    key,
    label,
    city: "杭州",
    tripDays: 3,
    itinerary,
    completion: {
      trip_completeness: options.completeness,
      action_tasks: options.sparseBlocks.length
        ? [{
            task_id: `${key}-gap`,
            task_instance_key: `${key}-gap-day-2`,
            title: "Day 2 evening has a sparse block",
            reason: "补一个低绕行晚间活动，可降低第二天晚上的临场决策。",
            action_prompt: "补齐第二天晚上，但不要移动灵隐寺固定安排。",
            priority: options.routeRisk ? "high" : "medium",
          }]
        : [],
      sparse_blocks_detected: options.sparseBlocks,
      auto_filled_scenic_count: 3,
      auto_filled_meal_count: 1,
      auto_filled_evening_count: 0,
      stay_area_recommendation: "湖滨 / 武林一带",
      departure_hub_recommendation: "杭州东站",
      why_this_plan_works: [
        "已优先保护固定离开边界和第二天寺庙路线。",
        "大部分停留点围绕西湖西侧与市中心展开，减少无意义折返。",
      ],
      score_breakdown: {
        density: options.completeness,
        meals: 86,
        evening: options.sparseBlocks.length ? 58 : 88,
        transport_boundary: options.routeRisk ? 56 : 84,
      },
    },
    plannerRealism: {
      status: options.plannerStatus,
      headline: options.routeRisk
        ? "第三天存在较重跨区移动，需要复核"
        : "路线骨架基本可执行",
      issues: options.routeRisk
        ? [{
            code: "long_segment_before_departure",
            severity: "high",
            title: "离开前移动偏长",
            detail: "良渚博物院到杭州东站的路线段较长，可能压缩离站缓冲。",
            day: 3,
          }]
        : [],
    },
    boundaryExplanation: {
      arrival_anchor_influenced: true,
      arrival_anchor_name: "杭州东站",
      departure_anchor_influenced: true,
      departure_anchor_name: "杭州东站",
    },
    planningAssumptions: {
      fixed_event_count: 2,
      availability_window_count: 1,
      summary_lines: ["第二天上午灵隐寺与第三天离开边界被作为硬约束保护。"],
    },
    routePreviewMap: options.missingRoutes ? {} : buildRoutePreviewMap(options.routeRisk),
    poiDetailFixtures: options.missingPoi ? buildPartialPoiDetails() : buildCompletePoiDetails(),
  };
}

function day(dayNumber: number, stops: FixtureStop[]): ItineraryLike["days"][number] {
  return {
    day: dayNumber,
    blocks: (["morning", "afternoon", "evening"] as const).map((blockType) => ({
      block_type: blockType,
      start_time: blockType === "morning" ? "09:00:00" : blockType === "afternoon" ? "13:00:00" : "18:00:00",
      end_time: blockType === "morning" ? "12:00:00" : blockType === "afternoon" ? "17:30:00" : "21:00:00",
      items: stops.filter((item) => item.block === blockType).map(({ block, ...item }) => item),
    })),
  };
}

function stop(
  name: string,
  type: ScheduledItemLike["type"],
  block: FixtureStop["block"],
  start_time: string,
  end_time: string,
  latitude: number,
  longitude: number,
  overrides: Partial<ScheduledItemLike> = {},
): FixtureStop {
  return {
    block,
    name,
    type,
    latitude,
    longitude,
    start_time,
    end_time,
    is_fixed: false,
    placement_reason: "根据当天空间顺序和用户偏好放入当前路线。",
    travel_from_name: null,
    travel_distance_m: null,
    travel_duration_s: null,
    ...overrides,
  };
}

function buildRoutePreviewMap(routeRisk: boolean): RoutePreviewMap {
  const entries = [
    routeSegmentEntry(
      segmentKey(1, "morning", "西湖断桥", "09:00:00", "10:30:00", 0, 1, "afternoon", "浙江省博物馆", "11:00:00", "13:00:00", 0),
      "西湖断桥",
      "浙江省博物馆",
      900,
      1800,
      [[30.2588, 120.1475], [30.2521, 120.1434]],
    ),
    routeSegmentEntry(
      segmentKey(1, "afternoon", "浙江省博物馆", "11:00:00", "13:00:00", 0, 1, "evening", "湖滨银泰晚餐", "18:00:00", "19:30:00", 0),
      "浙江省博物馆",
      "湖滨银泰晚餐",
      1020,
      3100,
      [[30.2521, 120.1434], [30.256, 120.1666]],
    ),
    routeSegmentEntry(
      segmentKey(2, "morning", "灵隐寺", "09:00:00", "11:00:00", 0, 2, "afternoon", "法喜寺", "13:20:00", "15:00:00", 0),
      "灵隐寺",
      "法喜寺",
      720,
      1400,
      [[30.2401, 120.1023], [30.2326, 120.0944]],
    ),
    routeSegmentEntry(
      segmentKey(2, "afternoon", "法喜寺", "13:20:00", "15:00:00", 0, 2, "afternoon", "龙井村茶歇", "15:30:00", "17:00:00", 1),
      "法喜寺",
      "龙井村茶歇",
      960,
      3200,
      [[30.2326, 120.0944], [30.2269, 120.1119]],
    ),
    routeSegmentEntry(
      segmentKey(3, "morning", "良渚博物院", "09:30:00", "11:30:00", 0, 3, "evening", "杭州东站", "17:00:00", "18:00:00", 0),
      "良渚博物院",
      "杭州东站",
      routeRisk ? 5400 : 3000,
      24500,
      [[30.3864, 120.0478], [30.2909, 120.2123]],
    ),
  ];
  return Object.fromEntries(entries);
}

function routeSegmentEntry(
  key: string,
  fromName: string,
  toName: string,
  durationSeconds: number,
  distanceMeters: number,
  points: Array<[number, number]>,
): [string, ReturnType<typeof segment>] {
  return [key, segment(key, fromName, toName, durationSeconds, distanceMeters, points)];
}

function segmentKey(
  fromDay: number,
  fromBlock: FixtureStop["block"],
  fromName: string,
  fromStart: string,
  fromEnd: string,
  fromIndex: number,
  toDay: number,
  toBlock: FixtureStop["block"],
  toName: string,
  toStart: string,
  toEnd: string,
  toIndex: number,
): string {
  return `${fromDay}-${fromBlock}-${fromName}-${fromStart}-${fromEnd}-${fromIndex}->${toDay}-${toBlock}-${toName}-${toStart}-${toEnd}-${toIndex}`;
}

function segment(
  key: string,
  fromName: string,
  toName: string,
  durationSeconds: number,
  distanceMeters: number,
  points: Array<[number, number]>,
) {
  return {
    segment_key: key,
    from_name: fromName,
    to_name: toName,
    distance_m: distanceMeters,
    duration_s: durationSeconds,
    source: "fixture_provider",
    mode: "walk" as const,
    path_points: points.map(([latitude, longitude]) => ({ latitude, longitude })),
  };
}

function buildCompletePoiDetails(): Record<string, POIDetailPreview> {
  return Object.fromEntries(
    [...day1Stops, ...day2Stops, ...day3Stops].map((item) => [
      item.name,
      poi(item.name, item.type === "restaurant" ? "餐饮服务" : "风景名胜", item.latitude, item.longitude),
    ]),
  );
}

function buildPartialPoiDetails(): Record<string, POIDetailPreview> {
  const details = buildCompletePoiDetails();
  delete details["龙井村茶歇"];
  delete details["良渚博物院"];
  return details;
}

function poi(name: string, category: string, latitude?: number | null, longitude?: number | null): POIDetailPreview {
  return {
    found: true,
    name,
    address: `${name} 周边示例地址`,
    category,
    business_area: "杭州核心游线",
    rating: null,
    cost: null,
    tel: null,
    website: null,
    open_time: category === "餐饮服务" ? "11:00-22:00" : "09:00-17:00",
    photo_url: null,
    latitude: latitude ?? null,
    longitude: longitude ?? null,
    source: "fixture",
    observed_at: "2026-09-26T12:00:00Z",
    failure_reason: null,
  };
}
