export type PrototypeDataSource = "prototype_fixture";

export type ActivitySource = "user_must" | "fixed_arrangement" | "system_suggested";

export type TravelMode = "walk" | "metro" | "taxi" | "bus";

export type FixedEvent = {
  id: string;
  title: string;
  startTime: string;
  endTime: string;
  location: string;
  protectedLabel: "已预约 · 不可随意移动";
};

export type Activity = {
  id: string;
  title: string;
  startTime: string;
  endTime: string;
  durationMinutes: number;
  source: ActivitySource;
  reason: string;
  fixedEventId?: string;
};

export type TravelLeg = {
  id: string;
  fromActivityId: string;
  toActivityId: string;
  mode: TravelMode;
  durationMinutes: number;
  distanceLabel: string;
};

export type DayLoad = {
  label: "轻松" | "刚好" | "偏赶";
  activityCount: number;
  travelMinutes: number;
  explanation: string;
};

export type RouteRisk = {
  id: string;
  day: number;
  message: string;
  severity: "attention";
};

export type TripDay = {
  day: number;
  title: string;
  startLabel: string;
  endLabel: string;
  activities: Activity[];
  travelLegs: TravelLeg[];
  load: DayLoad;
  capacityNote?: string;
};

export type TripDraft = {
  dataSource: PrototypeDataSource;
  title: string;
  naturalLanguageRequest: string;
};

export type TripIntentSummary = {
  destination: string;
  days: number;
  pace: "轻松" | "适中";
  mustVisit: string[];
  fixedEvents: FixedEvent[];
  understandingNotes: string[];
};

export type TripRoute = {
  dataSource: PrototypeDataSource;
  trip: TripIntentSummary;
  days: TripDay[];
  risks: RouteRisk[];
};

export type RepairProposal = {
  title: string;
  day: number;
  movedActivityId: string;
  movedActivityTitle: string;
  fromDay: number;
  toDay: number;
  keepsProtected: string[];
  before: DayLoad;
  after: DayLoad;
  localOnlyNotice: "Prototype only — no TripRevision is persisted in this round.";
};

export type PrototypeScenario = "hangzhou" | "shanghai" | "rushed";

export type PrototypeFixture = {
  id: PrototypeScenario;
  label: string;
  hint: string;
  draft: TripDraft;
  intent: TripIntentSummary;
  route: TripRoute;
  repair?: RepairProposal;
};

export function findTravelLeg(day: TripDay, fromActivityId: string): TravelLeg | undefined {
  return day.travelLegs.find((leg) => leg.fromActivityId === fromActivityId);
}

export function findFixedEvent(route: TripRoute, activity: Activity): FixedEvent | undefined {
  if (!activity.fixedEventId) return undefined;
  return route.trip.fixedEvents.find((event) => event.id === activity.fixedEventId);
}

export function applyFixtureRepair(route: TripRoute, proposal: RepairProposal): TripRoute {
  const movingDay = route.days.find((day) => day.day === proposal.fromDay);
  const receivingDay = route.days.find((day) => day.day === proposal.toDay);
  if (!movingDay || !receivingDay) return route;

  const activity = movingDay.activities.find((candidate) => candidate.id === proposal.movedActivityId);
  if (!activity || activity.source !== "system_suggested") return route;

  const remainingActivities = movingDay.activities.filter((candidate) => candidate.id !== activity.id);
  const movedActivity: Activity = { ...activity, startTime: "16:20", endTime: "17:20" };
  return {
    ...route,
    days: route.days.map((day) => {
      if (day.day === movingDay.day) {
        return {
          ...day,
          activities: remainingActivities,
          travelLegs: day.travelLegs.filter((leg) => leg.fromActivityId !== activity.id && leg.toActivityId !== activity.id),
          load: proposal.after,
        };
      }
      if (day.day === receivingDay.day) {
        return {
          ...day,
          activities: [...day.activities, movedActivity],
          load: { ...day.load, activityCount: day.load.activityCount + 1, explanation: "给下午留出一段从容的城市散步时间。" },
          capacityNote: "已接住 1 个建议地点，仍保留休息余量。",
        };
      }
      return day;
    }),
    risks: route.risks.filter((risk) => risk.day !== proposal.fromDay),
  };
}
