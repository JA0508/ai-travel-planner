"use client";

export type ParsedAvailabilityWindowInput = {
  day: number | null;
  label: string | null;
  available_start: string | null;
  available_end: string | null;
};

export type ParsedFixedEventInput = {
  name: string;
  fixed_day: number | null;
  fixed_time_start: string | null;
  fixed_time_end: string | null;
  category: string | null;
};

export function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function parseAvailabilityWindowLines(value: string): ParsedAvailabilityWindowInput[] {
  return splitLines(value)
    .map((line) => {
      const [rawDay, rawLabel, rawStart, rawEnd] = line
        .split("|")
        .map((part) => part.trim());

      if (!rawDay && !rawLabel && !rawStart && !rawEnd) {
        return null;
      }

      return {
        day: rawDay ? Number(rawDay) : null,
        label: rawLabel || null,
        available_start: rawStart || null,
        available_end: rawEnd || null,
      };
    })
    .filter((window): window is ParsedAvailabilityWindowInput => window !== null);
}

export function formatAvailabilityWindowsForTextarea(
  windows: ParsedAvailabilityWindowInput[],
): string {
  return windows
    .map((window) =>
      [
        window.day ?? "",
        window.label ?? "",
        window.available_start ?? "",
        window.available_end ?? "",
      ].join(" | "),
    )
    .join("\n");
}

export function parseFixedEventLines(value: string): ParsedFixedEventInput[] {
  return splitLines(value)
    .map((line): ParsedFixedEventInput | null => {
      const [rawCategory, rawName, rawDay, rawStart, rawEnd] = line
        .split("|")
        .map((part) => part.trim());

      if (!rawName) {
        return null;
      }

      const normalizedCategory =
        rawCategory === "restaurant" ? "restaurant" : "scenic";

      return {
        category: normalizedCategory,
        name: rawName,
        fixed_day: rawDay ? Number(rawDay) : null,
        fixed_time_start: rawStart || null,
        fixed_time_end: rawEnd || null,
      };
    })
    .filter((event): event is ParsedFixedEventInput => event !== null);
}

export function formatFixedEventsForTextarea(events: ParsedFixedEventInput[]): string {
  return events
    .map((event) =>
      [
        event.category ?? "scenic",
        event.name,
        event.fixed_day ?? "",
        event.fixed_time_start ?? "",
        event.fixed_time_end ?? "",
      ].join(" | "),
    )
    .join("\n");
}
