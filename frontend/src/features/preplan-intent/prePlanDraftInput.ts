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
