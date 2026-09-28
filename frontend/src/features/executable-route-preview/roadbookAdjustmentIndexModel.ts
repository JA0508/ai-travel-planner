import { isSafeReplaceEligible } from "./safeReplaceModel";
import type { DayLoad, RoutePreviewItem } from "./routePreviewModel";

export type RoadbookAdjustmentAction =
  | { kind: "relax_day"; day: number; label: string }
  | { kind: "replace_stop"; day: number; stopId: string; label: string };

export type RoadbookAdjustmentIndex = {
  actions: RoadbookAdjustmentAction[];
  summary: string;
};

export function buildRoadbookAdjustmentIndex({
  canRepair,
  loads,
  stops,
}: {
  canRepair: boolean;
  loads: DayLoad[];
  stops: Array<RoutePreviewItem & { day?: number }>;
}): RoadbookAdjustmentIndex {
  const relaxActions: RoadbookAdjustmentAction[] = canRepair
    ? loads
      .filter((load) => load.pace === "rushed" || load.pace === "infeasible")
      .map((load) => ({ kind: "relax_day", day: load.day, label: `查看第 ${load.day} 天的放松方案` }))
    : [];
  const replaceActions: RoadbookAdjustmentAction[] = stops
    .filter((stop) => isSafeReplaceEligible(stop) && stop.stable_id && stop.day != null)
    .map((stop) => ({
      kind: "replace_stop",
      day: stop.day!,
      stopId: stop.stable_id!,
      label: `检查「${stop.name}」能否安全替换`,
    }));
  const actions = [...relaxActions, ...replaceActions];

  return {
    actions,
    summary: actions.length
      ? `有 ${actions.length} 个可以安全检查的小调整；固定安排、必去地点和时间边界不会被这些调整改动。`
      : "当前没有可安全自动微调的地方。",
  };
}
