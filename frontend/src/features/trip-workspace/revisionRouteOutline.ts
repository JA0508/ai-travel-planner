export type RevisionRouteOutlineSnapshot = {
  trip_days: number;
  days: Array<{
    day: number;
    blocks: Array<{
      items: Array<{
        name: string;
        is_fixed: boolean;
        source_type?: string | null;
      }>;
    }>;
  }>;
};

export type RevisionRouteOutline = {
  tripDays: number;
  stopCount: number;
  fixedStopNames: string[];
  days: Array<{ day: number; stopNames: string[] }>;
};

export function buildRevisionRouteOutline(
  snapshot: RevisionRouteOutlineSnapshot,
): RevisionRouteOutline {
  const days = snapshot.days.map((day) => ({
    day: day.day,
    stopNames: day.blocks.flatMap((block) => block.items.map((item) => item.name)),
  }));
  const fixedStopNames = snapshot.days.flatMap((day) =>
    day.blocks.flatMap((block) =>
      block.items
        .filter((item) => item.is_fixed || item.source_type === "user_fixed")
        .map((item) => item.name),
    ),
  );

  return {
    tripDays: snapshot.trip_days,
    stopCount: days.reduce((count, day) => count + day.stopNames.length, 0),
    fixedStopNames: Array.from(new Set(fixedStopNames)),
    days,
  };
}
