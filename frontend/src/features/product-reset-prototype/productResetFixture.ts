import type { PrototypeFixture, TripRoute } from "./productResetModel";

const dataSource = "prototype_fixture" as const;

const hangzhouRoute: TripRoute = {
  dataSource,
  trip: {
    destination: "杭州",
    days: 2,
    pace: "轻松",
    mustVisit: ["西湖", "灵隐寺"],
    fixedEvents: [],
    understandingNotes: ["周末出发", "想慢慢走，不把一天塞满"],
  },
  risks: [],
  days: [
    {
      day: 1,
      title: "湖边慢游",
      startLabel: "09:30 从西湖边开始",
      endLabel: "傍晚在湖滨散步收尾",
      activities: [
        { id: "hz-west-lake", title: "西湖 · 苏堤与花港", startTime: "09:30", endTime: "12:00", durationMinutes: 150, source: "user_must", reason: "把你最想去的西湖放在第一天最舒展的时段。" },
        { id: "hz-lunch", title: "湖滨午餐", startTime: "12:15", endTime: "13:15", durationMinutes: 60, source: "system_suggested", reason: "午餐留在步行范围内，下午不用赶路。" },
        { id: "hz-hefang", title: "河坊街慢逛", startTime: "14:00", endTime: "16:00", durationMinutes: 120, source: "system_suggested", reason: "用一段松弛的街区时间衔接傍晚。" },
        { id: "hz-hubin", title: "湖滨夜景", startTime: "18:30", endTime: "20:00", durationMinutes: 90, source: "system_suggested", reason: "把夜晚留给靠湖、可随时结束的散步。" },
      ],
      travelLegs: [
        { id: "hz-leg-1", fromActivityId: "hz-west-lake", toActivityId: "hz-lunch", mode: "walk", durationMinutes: 12, distanceLabel: "850 米" },
        { id: "hz-leg-2", fromActivityId: "hz-lunch", toActivityId: "hz-hefang", mode: "taxi", durationMinutes: 18, distanceLabel: "4.6 公里" },
        { id: "hz-leg-3", fromActivityId: "hz-hefang", toActivityId: "hz-hubin", mode: "metro", durationMinutes: 20, distanceLabel: "5.1 公里" },
      ],
      load: { label: "轻松", activityCount: 4, travelMinutes: 50, explanation: "景点之间留有午餐和休息余量，适合第一天慢慢进入节奏。" },
    },
    {
      day: 2,
      title: "山寺与返程前的留白",
      startLabel: "09:00 前往灵隐寺",
      endLabel: "16:30 前从杭州东站返程",
      activities: [
        { id: "hz-lingyin", title: "灵隐寺", startTime: "09:30", endTime: "12:00", durationMinutes: 150, source: "user_must", reason: "上午安静一些，也给返程保留充足余量。" },
        { id: "hz-lunch-2", title: "灵隐附近午餐", startTime: "12:15", endTime: "13:15", durationMinutes: 60, source: "system_suggested", reason: "不额外折返，吃完后直接向车站方向移动。" },
      ],
      travelLegs: [{ id: "hz-leg-4", fromActivityId: "hz-lingyin", toActivityId: "hz-lunch-2", mode: "walk", durationMinutes: 10, distanceLabel: "600 米" }],
      load: { label: "轻松", activityCount: 2, travelMinutes: 10, explanation: "返程日只保留一个核心景点，避免离开前手忙脚乱。" },
      capacityNote: "下午仍有休息或提前返程的余量。",
    },
  ],
};

const shanghaiRoute: TripRoute = {
  dataSource,
  trip: {
    destination: "上海",
    days: 3,
    pace: "适中",
    mustVisit: ["武康路", "外滩", "陆家嘴"],
    fixedEvents: [{ id: "sh-museum", title: "上海博物馆", startTime: "14:00", endTime: "16:00", location: "人民广场附近", protectedLabel: "已预约 · 不可随意移动" }],
    understandingNotes: ["第一天中午抵达", "第三天晚上从浦东离开"],
  },
  risks: [],
  days: [
    {
      day: 1,
      title: "梧桐街区与夜景",
      startLabel: "12:30 从武康路开始",
      endLabel: "20:30 外滩夜景收尾",
      activities: [
        { id: "sh-wukang", title: "武康路散步", startTime: "12:30", endTime: "14:30", durationMinutes: 120, source: "user_must", reason: "中午到站后先进入步行友好的街区。" },
        { id: "sh-bund", title: "外滩", startTime: "18:30", endTime: "20:30", durationMinutes: 120, source: "user_must", reason: "把夜景放在天色变暗后，体验更完整。" },
      ],
      travelLegs: [{ id: "sh-leg-1", fromActivityId: "sh-wukang", toActivityId: "sh-bund", mode: "metro", durationMinutes: 28, distanceLabel: "6.4 公里" }],
      load: { label: "刚好", activityCount: 2, travelMinutes: 28, explanation: "抵达日不塞满，晚间保留一个明确亮点。" },
    },
    {
      day: 2,
      title: "人民广场的固定下午",
      startLabel: "10:30 从人民广场附近开始",
      endLabel: "20:00 在陆家嘴看夜景",
      activities: [
        { id: "sh-lunch", title: "人民广场午餐", startTime: "12:20", endTime: "13:20", durationMinutes: 60, source: "system_suggested", reason: "把午餐放在固定安排附近，不需要赌路况。" },
        { id: "sh-museum-activity", title: "上海博物馆", startTime: "14:00", endTime: "16:00", durationMinutes: 120, source: "fixed_arrangement", fixedEventId: "sh-museum", reason: "你已预约，时间与地点会被保护。" },
        { id: "sh-lujiazui", title: "陆家嘴夜景", startTime: "18:30", endTime: "20:00", durationMinutes: 90, source: "user_must", reason: "博物馆结束后顺路过江，把夜晚留给城市天际线。" },
      ],
      travelLegs: [{ id: "sh-leg-2", fromActivityId: "sh-lunch", toActivityId: "sh-museum-activity", mode: "walk", durationMinutes: 8, distanceLabel: "450 米" }, { id: "sh-leg-3", fromActivityId: "sh-museum-activity", toActivityId: "sh-lujiazui", mode: "metro", durationMinutes: 22, distanceLabel: "4.9 公里" }],
      load: { label: "刚好", activityCount: 3, travelMinutes: 30, explanation: "固定预约是当天锚点，其他安排围绕它展开。" },
    },
    {
      day: 3,
      title: "田子坊与机场前收尾",
      startLabel: "10:00 从田子坊开始",
      endLabel: "17:30 前往浦东机场",
      activities: [{ id: "sh-tianzifang", title: "田子坊", startTime: "10:00", endTime: "12:00", durationMinutes: 120, source: "user_must", reason: "离开前保留一段容易控制时间的街区散步。" }],
      travelLegs: [],
      load: { label: "轻松", activityCount: 1, travelMinutes: 0, explanation: "把去机场的时间留足，比多加一个景点更安心。" },
    },
  ],
};

const rushedRoute: TripRoute = {
  dataSource,
  trip: {
    destination: "西安",
    days: 2,
    pace: "适中",
    mustVisit: ["兵马俑", "西安城墙"],
    fixedEvents: [{ id: "xa-wall-night", title: "城墙夜骑", startTime: "18:30", endTime: "20:00", location: "永宁门", protectedLabel: "已预约 · 不可随意移动" }],
    understandingNotes: ["第一天中午抵达", "晚上已有预约"],
  },
  risks: [{ id: "xa-rush", day: 1, message: "第 1 天有 5 个活动，移动约 95 分钟，下午会比较赶。", severity: "attention" }],
  days: [
    {
      day: 1,
      title: "到达日安排偏满",
      startLabel: "12:00 抵达后开始",
      endLabel: "20:00 城墙夜骑结束",
      activities: [
        { id: "xa-bell", title: "钟楼", startTime: "12:40", endTime: "13:30", durationMinutes: 50, source: "system_suggested", reason: "用一个靠近市中心的轻量地点承接抵达。" },
        { id: "xa-lunch", title: "回民街午餐", startTime: "13:45", endTime: "14:35", durationMinutes: 50, source: "system_suggested", reason: "午餐与钟楼相邻，减少抵达日的折返。" },
        { id: "xa-terracotta", title: "兵马俑", startTime: "15:50", endTime: "17:10", durationMinutes: 80, source: "user_must", reason: "这是你明确想去的地点，会保留在计划中。" },
        { id: "xa-wall", title: "西安城墙", startTime: "17:25", endTime: "18:15", durationMinutes: 50, source: "user_must", reason: "这是你明确想去的地点，会保留在计划中。" },
        { id: "xa-night", title: "城墙夜骑", startTime: "18:30", endTime: "20:00", durationMinutes: 90, source: "fixed_arrangement", fixedEventId: "xa-wall-night", reason: "你已预约，时间与地点会被保护。" },
      ],
      travelLegs: [{ id: "xa-leg-1", fromActivityId: "xa-bell", toActivityId: "xa-lunch", mode: "walk", durationMinutes: 12, distanceLabel: "700 米" }, { id: "xa-leg-2", fromActivityId: "xa-lunch", toActivityId: "xa-terracotta", mode: "taxi", durationMinutes: 45, distanceLabel: "42 公里" }, { id: "xa-leg-3", fromActivityId: "xa-terracotta", toActivityId: "xa-wall", mode: "taxi", durationMinutes: 28, distanceLabel: "38 公里" }, { id: "xa-leg-4", fromActivityId: "xa-wall", toActivityId: "xa-night", mode: "walk", durationMinutes: 10, distanceLabel: "600 米" }],
      load: { label: "偏赶", activityCount: 5, travelMinutes: 95, explanation: "抵达时间较晚，又要跨城移动，下午的转换余量不足。" },
    },
    {
      day: 2,
      title: "博物馆与可用余量",
      startLabel: "09:30 从陕西历史博物馆开始",
      endLabel: "傍晚前自由收尾",
      activities: [{ id: "xa-history", title: "陕西历史博物馆", startTime: "09:30", endTime: "12:00", durationMinutes: 150, source: "user_must", reason: "把另一处核心景点留在完整的一天。" }],
      travelLegs: [],
      load: { label: "轻松", activityCount: 1, travelMinutes: 0, explanation: "下午仍有可以承接一处轻量建议的空间。" },
      capacityNote: "下午有余量，可接住一个不影响核心安排的建议地点。",
    },
  ],
};

export const productResetFixtures: PrototypeFixture[] = [
  {
    id: "hangzhou",
    label: "杭州两天轻松游",
    hint: "西湖、灵隐寺、慢慢走",
    draft: { dataSource, title: "杭州周末", naturalLanguageRequest: "周末去杭州玩两天，轻松一点，想去西湖和灵隐寺。" },
    intent: hangzhouRoute.trip,
    route: hangzhouRoute,
  },
  {
    id: "shanghai",
    label: "上海固定预约",
    hint: "博物馆预约、夜景、三天",
    draft: { dataSource, title: "上海三日", naturalLanguageRequest: "去上海玩三天，第二天下午两点到四点预约了上海博物馆，想去武康路、外滩和陆家嘴。" },
    intent: shanghaiRoute.trip,
    route: shanghaiRoute,
  },
  {
    id: "rushed",
    label: "西安到达日太赶",
    hint: "看看一次局部调整",
    draft: { dataSource, title: "西安两日", naturalLanguageRequest: "去西安玩两天，第一天中午到，想去兵马俑和西安城墙，晚上有城墙夜骑预约。" },
    intent: rushedRoute.trip,
    route: rushedRoute,
    repair: {
      title: "让第 1 天轻松一些",
      day: 1,
      movedActivityId: "xa-bell",
      movedActivityTitle: "钟楼",
      fromDay: 1,
      toDay: 2,
      keepsProtected: ["兵马俑", "西安城墙", "城墙夜骑"],
      before: rushedRoute.days[0].load,
      after: { label: "刚好", activityCount: 4, travelMinutes: 83, explanation: "移走一处系统建议后，抵达日的转换更可控。" },
      localOnlyNotice: "Prototype only — no TripRevision is persisted in this round.",
    },
  },
];

export function fixtureForScenario(id: PrototypeFixture["id"]): PrototypeFixture {
  const fixture = productResetFixtures.find((candidate) => candidate.id === id);
  if (!fixture) throw new Error(`Unknown prototype fixture: ${id}`);
  return fixture;
}
