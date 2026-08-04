export type PrePlanDraftInput = {
  directText: string;
  tripDays: string;
  scenicSpots: string[];
  restaurants: string[];
  fixedEventsText: string;
  availabilityWindowsText: string;
  arrivalAnchor: string;
  departureAnchor: string;
  hotel: string;
  preferences: string[];
  pacingLabel: string;
  travelMode: string | null;
};

type CompilerIntentDraftInput = {
  destination: string | null;
  trip_days: number | null;
  pace: "relaxed" | "balanced" | "intensive";
  must_visit_places: Array<{ name: string }>;
  optional_places: Array<{ name: string }>;
  fixed_events: Array<{ name: string; day: number | null; start_time: string | null; end_time: string | null }>;
  preferences: Array<{ value: string }>;
  constraints: Array<{ kind: string; value: string }>;
  travel_mode: string | null;
};

/** Preserve structured form boundaries as source language for the draft intent compiler. */
export function buildPrePlanDraftText(input: PrePlanDraftInput): string {
  return [
    input.directText.trim(),
    input.tripDays.trim() ? `行程天数：${input.tripDays.trim()} 天。` : null,
    input.scenicSpots.length ? `必须优先考虑的地点：${input.scenicSpots.join("、")}。` : null,
    input.restaurants.length ? `餐食线索：${input.restaurants.join("、")}。` : null,
    input.fixedEventsText.trim() ? `固定安排：${input.fixedEventsText.trim()}。` : null,
    input.availabilityWindowsText.trim() ? `可用时间窗口：${input.availabilityWindowsText.trim()}。` : null,
    input.arrivalAnchor.trim() ? `到达锚点：${input.arrivalAnchor.trim()}。` : null,
    input.departureAnchor.trim() ? `离开锚点：${input.departureAnchor.trim()}。` : null,
    input.hotel.trim() ? `已确定住宿：${input.hotel.trim()}。` : null,
    input.preferences.length ? `偏好：${input.preferences.join("、")}。` : null,
    `旅行节奏：${input.pacingLabel}。`,
    input.travelMode ? `主要交通偏好：${input.travelMode}。` : null,
  ].filter((line): line is string => Boolean(line)).join("\n");
}

/** Keep the compiler confirmation path on the same labelled Draft Trip input boundary. */
export function buildPrePlanDraftTextFromCompilerIntent(intent: CompilerIntentDraftInput): string {
  const places = uniqueValues([
    ...intent.must_visit_places.map((place) => place.name),
    ...intent.optional_places.map((place) => place.name),
  ]);
  const fixedEvents = intent.fixed_events
    .filter((event) => event.day !== null && event.start_time && event.end_time)
    .map((event) => `${event.day} ${event.start_time}-${event.end_time} ${event.name}`);

  return buildPrePlanDraftText({
    directText: [
      intent.destination ? `城市：${intent.destination}` : "",
      places.length ? `景点：${places.join("、")}` : "",
    ].filter(Boolean).join("\n"),
    tripDays: intent.trip_days ? String(intent.trip_days) : "",
    scenicSpots: [],
    restaurants: [],
    fixedEventsText: fixedEvents.join("；"),
    availabilityWindowsText: intent.constraints
      .filter((constraint) => constraint.kind === "availability")
      .map((constraint) => constraint.value)
      .join("；"),
    arrivalAnchor: intent.constraints.find((constraint) => constraint.kind === "arrival")?.value ?? "",
    departureAnchor: intent.constraints.find((constraint) => constraint.kind === "departure")?.value ?? "",
    hotel: "",
    preferences: uniqueValues(intent.preferences.map((preference) => preference.value)),
    pacingLabel: { relaxed: "轻松节奏", balanced: "平衡节奏", intensive: "紧凑节奏" }[intent.pace],
    travelMode: intent.travel_mode,
  });
}

function uniqueValues(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}
