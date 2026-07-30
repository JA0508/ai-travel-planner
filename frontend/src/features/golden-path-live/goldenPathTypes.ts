export type Ownership = "user_must" | "user_fixed" | "user_optional" | "system_suggested";

export type LiveItem = {
  stable_id: string | null;
  name: string;
  type: "scenic" | "restaurant" | "hotel";
  day: number;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  is_fixed: boolean;
  source_type: "user_seed" | "user_fixed" | "auto_seeded_poi" | "auto_seeded_meal" | "auto_filled";
  source_label?: string | null;
  source_reason?: string | null;
  placement_reason?: string | null;
  travel_from_name?: string | null;
  travel_distance_m?: number | null;
  travel_duration_s?: number | null;
  travel_calculation_status?: string | null;
  candidate_provenance?: { intent_field_path?: string } | null;
};

export type LiveItinerary = {
  trip_days: number;
  days: Array<{ day: number; blocks: Array<{ block_type: string; items: LiveItem[] }> }>;
  planner_realism?: {
    status: string;
    headline: string;
    issues: Array<{ code: string; title: string; detail: string; severity: string; day?: number | null }>;
    daily_loads: Array<{ day: number; classification: "relaxed" | "balanced" | "rushed" | "infeasible"; activity_count: number; fixed_count: number; activity_minutes: number; travel_minutes: number; route_distance_m: number | null; reason_codes: string[]; explanation: string }>;
  } | null;
};

export type HandoffPreview = {
  trip: { id: string };
  draft_intent_revision_id: string;
  handoff: { id: string; trace_digest: string };
  itinerary: LiveItinerary;
};

export type AppliedHandoff = {
  trip: { id: string; current_revision_id: string };
  current_revision: { id: string; revision_number: number };
  itinerary: LiveItinerary;
};

export type RepairPreview = {
  trip: { id: string };
  current_revision: { id: string; revision_number: number };
  proposal: {
    proposal_id: string;
    proposal_digest: string;
    base_revision: string;
    target_day: number;
    moved_activity_id: string;
    moved_activity_name: string;
    from_day: number;
    to_day: number;
    before: LiveItinerary;
    after: LiveItinerary;
    protection_summary: string;
    execution_evidence: Record<string, number>;
  };
};

export type RepairApplied = { current_revision: { id: string; revision_number: number }; itinerary: LiveItinerary };

export function ownershipFor(item: LiveItem): Ownership {
  if (item.is_fixed || item.source_type === "user_fixed") return "user_fixed";
  if (["auto_seeded_poi", "auto_seeded_meal", "auto_filled"].includes(item.source_type)) return "system_suggested";
  const fieldPath = item.candidate_provenance?.intent_field_path ?? "";
  return fieldPath.includes("optional_places") ? "user_optional" : "user_must";
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "移动时间待确认";
  const minutes = Math.round(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分钟` : `${minutes} 分钟`;
}
