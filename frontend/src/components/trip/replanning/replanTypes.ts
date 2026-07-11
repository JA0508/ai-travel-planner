"use client";

export type ReplanBlockType = "morning" | "afternoon" | "evening";
export type ReplanItemType = "scenic" | "restaurant" | "hotel";

export type ReplanScheduledItemLike = {
  name: string;
  type: ReplanItemType;
  day?: number;
  start_time: string;
  end_time: string;
  is_fixed: boolean;
  placement_reason: string | null;
  source_type?:
    | "user_seed"
    | "user_fixed"
    | "auto_seeded_poi"
    | "auto_seeded_meal"
    | "auto_filled"
    | string;
  source_label?: string | null;
  source_reason?: string | null;
  travel_from_name: string | null;
  travel_distance_m: number | null;
  travel_duration_s: number | null;
  local_edit?: unknown;
};

export type ReplanDayBlockLike = {
  block_type: ReplanBlockType;
  start_time: string;
  end_time: string;
  items: ReplanScheduledItemLike[];
};

export type ReplanDayLike = {
  day: number;
  blocks: ReplanDayBlockLike[];
};

export type ReplanIntentLike = {
  flexible_scenic_spots?: string[];
  flexible_restaurants?: string[];
  carry_forward_scenic_spots?: string[];
  carry_forward_restaurants?: string[];
  auto_seeded_scenic_spots?: string[];
  auto_seeded_restaurants?: string[];
  rejected_scenic_spots?: string[];
  rejected_restaurants?: string[];
  notes?: string[];
};

export type ReplanItineraryLike = {
  trip_days: number;
  hotel?: { name: string } | null;
  planning_anchor_source?: {
    source_type: string;
    source_name: string;
  } | null;
  trip_intent?: {
    current_intent?: ReplanIntentLike | null;
    summary_lines?: string[];
    compile_summary?: unknown;
  } | null;
  planning_assumptions?: {
    regeneration_intent?: ReplanIntentLike | null;
    execution_trace?: unknown[] | null;
    follow_up_interpretation?: unknown;
  } | null;
  boundary_explanation?: {
    arrival_anchor_influenced?: boolean;
    arrival_anchor_name?: string | null;
    arrival_poi_name?: string | null;
    departure_anchor_influenced?: boolean;
    departure_anchor_name?: string | null;
    departure_poi_name?: string | null;
  } | null;
  days: ReplanDayLike[];
};

export type ReplanStopRef = {
  id: string;
  day: number;
  blockType: ReplanBlockType;
  blockLabel: string;
  index: number;
  name: string;
  type: ReplanItemType;
  startTime: string;
  endTime: string;
  isProtected: boolean;
  protectionReasons: string[];
  sourceType: string | null;
  travelDurationSeconds: number | null;
  travelDistanceMeters: number | null;
};

export type ReplanIntentKind =
  | "remove_stop"
  | "move_stop"
  | "relax_day"
  | "area_consolidation"
  | "weather_adaptation"
  | "add_preference"
  | "general_replan"
  | "unknown";

export type ReplanExecutionMode = "local_mutation" | "backend_replan" | "unsupported";

export type ReplanOperation =
  | {
      kind: "remove_stop";
      stopId: string;
      stopName: string;
      day: number;
      blockType: ReplanBlockType;
    }
  | {
      kind: "move_stop";
      stopId: string;
      stopName: string;
      fromDay: number;
      fromBlockType: ReplanBlockType;
      toDay: number;
      toBlockType: ReplanBlockType;
    }
  | {
      kind: "backend_replan";
      prompt: string;
      capabilityGap: string;
    };

export type ReplanConstraintSeverity = "ok" | "watch" | "blocked";

export type ReplanConstraintFinding = {
  key: string;
  severity: ReplanConstraintSeverity;
  title: string;
  detail: string;
  relatedStopIds?: string[];
};

export type ReplanImpactItem = {
  key: string;
  tone: "change" | "protect" | "estimate" | "gap";
  title: string;
  detail: string;
};

export type ReplanMutationPlan = {
  id: string;
  rawText: string;
  intentKind: ReplanIntentKind;
  title: string;
  summary: string;
  executionMode: ReplanExecutionMode;
  confidence: "high" | "medium" | "low";
  operations: ReplanOperation[];
  targetStops: ReplanStopRef[];
  candidateStops: ReplanStopRef[];
  constraints: ReplanConstraintFinding[];
  impactPreview: ReplanImpactItem[];
  evidence: string[];
  contractGaps: string[];
  requiresConfirmation: boolean;
  executable: boolean;
};

export type ReplanChange =
  | {
      key: string;
      kind: "removed";
      title: string;
      detail: string;
      stopName: string;
      before: ReplanStopRef;
    }
  | {
      key: string;
      kind: "added";
      title: string;
      detail: string;
      stopName: string;
      after: ReplanStopRef;
    }
  | {
      key: string;
      kind: "moved" | "retimed" | "route_changed";
      title: string;
      detail: string;
      stopName: string;
      before: ReplanStopRef;
      after: ReplanStopRef;
    };

export type ReplanChangeSet = {
  added: ReplanChange[];
  removed: ReplanChange[];
  moved: ReplanChange[];
  retimed: ReplanChange[];
  routeChanged: ReplanChange[];
  summary: string;
};

export type ReplanExecutionResult<TItinerary extends ReplanItineraryLike> =
  | {
      ok: true;
      beforeItinerary: TItinerary;
      afterItinerary: TItinerary;
      message: string;
      usedBackend: boolean;
    }
  | {
      ok: false;
      message: string;
    };

export type ReplanHistoryEntry<TItinerary extends ReplanItineraryLike = ReplanItineraryLike> = {
  id: string;
  createdAt: string;
  plan: ReplanMutationPlan;
  beforeItinerary: TItinerary;
  afterItinerary: TItinerary;
  changeSet: ReplanChangeSet;
  usedBackend: boolean;
};
