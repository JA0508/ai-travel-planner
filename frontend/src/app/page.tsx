"use client";

import { CSSProperties, FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import {
  CompletionExecutionEvidence,
  type CompletionScoreFactor,
  buildCompletionScoreBreakdownRows,
} from "@/components/trip/CompletionExecutionEvidence";
import {
  CompletionTaskActionList,
} from "@/components/trip/CompletionTaskActionList";
import {
  DayTimeline,
} from "@/components/trip/DayTimeline";
import type { EditableRouteDay } from "@/components/trip/MobileEditRouteWorkspace";
import { RouteWorkspaceContainer } from "@/features/trip-workspace/RouteWorkspaceContainer";
import { useRouteWorkspaceUiState } from "@/features/trip-workspace/routeWorkspaceUiState";
import {
  LEGACY_FULL_SESSION_KEY,
  PERSISTED_TRIP_REF_KEY,
  buildMutationProposalIdempotencyKey,
  buildReplanProposalIdempotencyKey,
  buildPersistedDraftTripRef,
  buildPersistedTripRef,
  describeTripPersistence,
  describeRevisionRestoreImpact,
  describeTripRevisionSource,
  markDirty,
  markSavedFromRevision,
  parsePersistedTripRef,
  serializePersistedTripRef,
  type TripMetadata,
  type TripPersistenceState,
  type TripRevisionMetadata,
} from "@/features/trip-workspace/tripPersistence";
import {
  buildRouteEditCommandEnvelope,
  buildSwapReplaceCommandEnvelope,
  type TripMutationCommandEnvelope,
} from "@/features/trip-workspace/routeWorkspaceMutationCommands";
import {
  buildCandidateAdmissionEnvelope,
  buildCompletionCandidatePayload,
  buildManualCandidatePayload,
  candidateIdempotencyKey,
  groupCandidates,
  type CandidateAdmissionCommandEnvelope,
  type CandidateDecisionResponse,
  type CandidateListResponse,
  type CandidateRegistrationResponse,
  type CandidateWorkspaceState,
  type TripCandidate,
} from "@/features/trip-workspace/tripCandidates";
import { ImportReviewWorkspace } from "@/features/imports/ImportReviewWorkspace";
import { IntentConfirmationWorkspace } from "@/features/intent-confirmation/IntentConfirmationWorkspace";
import { PrePlanIntentWorkspace } from "@/features/preplan-intent/PrePlanIntentWorkspace";
import { ExecutableRoutePreview } from "@/features/executable-route-preview/ExecutableRoutePreview";
import { buildPrePlanDraftText } from "@/features/preplan-intent/prePlanDraftInput";
import { ConversationalReplanPanel } from "@/components/trip/replanning/ConversationalReplanPanel";
import type {
  ReplanExecutionResult,
  ReplanHistoryEntry,
  ReplanMutationPlan,
} from "@/components/trip/replanning/replanTypes";
import { applyReplanMutationPlanToItinerary } from "@/components/trip/replanning/replanViewModel";
import { TripReadinessPanel } from "@/components/trip/readiness/TripReadinessPanel";
import { buildTripReadinessViewModel } from "@/components/trip/readiness/tripReadinessModel";
import {
  buildDayTimelineViewModel,
  buildRecentCompletionTaskItemKey,
} from "@/components/trip/dayTimelineViewModel";
import {
  buildDayTimelineDependencies,
} from "@/components/trip/tripTimelineAdapters";
import {
  blockEmoji,
  blockExplanation,
  blockPanelStyle,
  describePacingOutcome,
  describePacingProfile,
  formatBlockTitle,
  formatBlockTitleForExport,
  formatCompletionOptionType,
  formatEffectiveAvailabilityRange,
  formatItemLabel,
  formatPacingProfileLabel,
  formatPlanningAnchorSourceType,
  formatRemainingBlocks,
  formatTime,
  formatTravelDistance,
  formatTravelDuration,
  formatTravelMode,
} from "@/components/trip/tripFormatting";
import {
  buildCompletionOptionKey,
  buildEffectivePreferences,
  buildSwapTargetKey,
  canSwapScheduledItem,
  createEmptyPreferenceSignals,
  derivePreferenceSignalsFromCommittedSwaps,
  getStrongPreferenceSignalLabels,
  getSwapCandidates,
  inferSignalsFromPoi,
  normalizeComparisonName,
  uniquePreserveOrder,
  type PreferenceSignalKey,
  type PreferenceSignals,
} from "@/components/trip/tripSwapPolicy";
import {
  applySwapToItinerary,
  buildCommittedSwapSelectionFromOption,
  buildUserConfirmedReplacementFromSwap,
  undoSwapInItinerary,
  upsertCommittedSwap,
} from "@/components/trip/tripSwapState";
import {
  applyCompletionTaskItemToGenerationContext,
  applyCompletionTaskItemToTripIntentEnvelope,
  applyRouteEditsToGenerationContext,
  applyRouteEditsToTripIntentEnvelope,
  applySwapToGenerationContext,
  applySwapToTripIntentEnvelope,
  undoCompletionTaskItemFromGenerationContext,
  undoCompletionTaskItemFromTripIntentEnvelope,
  undoSwapFromGenerationContext,
  undoSwapFromTripIntentEnvelope,
} from "@/components/trip/tripIntentMutation";
import {
  applyRouteEditsToItinerary,
  hasEditedRouteChanges,
} from "@/components/trip/tripRouteEditMutation";
import {
  buildGenerateItineraryPayload,
  buildRegenerateValuesFromCurrentState,
  buildTripIntentPatchFromCurrentState,
} from "@/components/trip/tripIntentPayload";
import {
  buildParsedIntentFromRegenerationIntent,
  buildStructuredFormSyncFromParsedIntent,
  buildStructuredFormSyncFromRegenerationIntent,
  type TripStructuredFormSync,
} from "@/components/trip/tripFormSync";
import {
  formatAvailabilityWindowsForTextarea,
  parseAvailabilityWindowLines,
  parseFixedEventLines,
  splitLines,
} from "@/components/trip/tripInputParsing";
import { getTripJson, postTripJson, type TripApiResult } from "@/components/trip/tripApiClient";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";

const API_URL = TRIP_API_ENDPOINTS.generateItinerary;
const REPLAN_API_URL = TRIP_API_ENDPOINTS.replanItinerary;
const GENERATE_FROM_TRIP_INTENT_API_URL = TRIP_API_ENDPOINTS.generateFromTripIntent;
const APPLY_COMPLETION_TASK_API_URL = TRIP_API_ENDPOINTS.applyCompletionTask;
const PREVIEW_COMPLETION_TASK_CANDIDATES_API_URL =
  TRIP_API_ENDPOINTS.previewCompletionTaskCandidates;
const REFRESH_ITINERARY_SURFACES_API_URL = TRIP_API_ENDPOINTS.refreshItinerarySurfaces;
const PREVIEW_ROUTE_SEGMENTS_API_URL = TRIP_API_ENDPOINTS.previewRouteSegments;
const PREVIEW_POI_DETAIL_API_URL = TRIP_API_ENDPOINTS.previewPoiDetail;
const PLAN_FROM_TEXT_API_URL = TRIP_API_ENDPOINTS.planFromText;
const PLAN_TRIP_API_URL = TRIP_API_ENDPOINTS.planTrip;
const PARSE_API_URL = TRIP_API_ENDPOINTS.parseTripIntent;
const PLANNING_STATE_API_URL = TRIP_API_ENDPOINTS.parsePlanningState;
const PREVIEW_AVAILABILITY_API_URL = TRIP_API_ENDPOINTS.previewAvailability;
const SAVED_TRIP_SESSION_KEY = LEGACY_FULL_SESSION_KEY;
const SHARE_CARD_FEEDBACK_KEY = "travel-planner-share-card-feedback-v1";
const RESULT_NAV_TARGETS = {
  completionSummary: "completion-intelligence-summary",
  autoFill: "completion-auto-fill-recommendations",
  stay: "completion-stay-area-recommendation",
  departure: "completion-departure-hub-recommendation",
} as const;
const TRAVEL_MODE_OPTIONS: Array<{
  value: TravelMode;
  label: string;
  emoji: string;
  description: string;
}> = [
  { value: "airplane", label: "飞机", emoji: "✈️", description: "第一天更偏轻量和顺手的开始" },
  { value: "high_speed_rail", label: "高铁 / 动车", emoji: "🚄", description: "更适合直接进入城市节奏" },
  { value: "rail", label: "火车", emoji: "🚆", description: "适合稳定进入当天安排" },
  { value: "car", label: "自驾 / 其他", emoji: "🚗", description: "保留更多灵活度" },
  { value: "undecided", label: "还没想好", emoji: "🧭", description: "先按通用逻辑帮你排" },
];

const QUICK_GENERATE_EXAMPLES: Array<{
  label: string;
  hint: string;
  text: string;
}> = [
  {
    label: "上海周末轻松版",
    hint: "晚到 + 预约 + 夜景",
    text: "周六下午到上海，想吃本地小吃、逛老街和夜景，周日下午三点有个预约，周日晚回去。不要太赶。",
  },
  {
    label: "杭州 3 天种草点",
    hint: "零散 POI + 想轻松",
    text: "想去杭州 3 天，已经种草了西湖、灵隐寺、法喜寺和龙井村，想吃杭帮菜，晚上可以轻松散步，不想每天太满。",
  },
  {
    label: "深圳周末高效版",
    hint: "模糊偏好 + 自动补齐",
    text: "周末去深圳，想看海、逛点有城市感的地方，喜欢咖啡和夜景，第一天中午后才到，第二天晚上高铁走，帮我排得顺一点。",
  },
];

type ScheduledItem = {
  stable_id?: string | null;
  name: string;
  type: "scenic" | "restaurant" | "hotel";
  latitude?: number | null;
  longitude?: number | null;
  day?: number;
  start_time: string;
  end_time: string;
  is_fixed: boolean;
  placement_reason: string | null;
  source_type?: "user_seed" | "user_fixed" | "auto_seeded_poi" | "auto_seeded_meal" | "auto_filled";
  source_label?: string | null;
  source_reason?: string | null;
  travel_from_name: string | null;
  travel_distance_m: number | null;
  travel_duration_s: number | null;
  poi_research?: POIResearchSummary | null;
  local_edit?: {
    previous_name: string;
    source: "completion_recommendation";
    status: "committed";
    reasoning_summary: string;
    itinerary_relation_summary: string;
    original_type: ScheduledItem["type"];
    original_placement_reason: string | null;
    original_source_type?: ScheduledItem["source_type"];
    original_source_label?: string | null;
    original_source_reason?: string | null;
  } | null;
};

type POIResearchSummary = {
  overview: string;
  access_tip: string;
  practical_tip: string;
  best_for: string;
  source: string;
};

type ScheduledItemSourceType = NonNullable<ScheduledItem["source_type"]>;

type DayBlock = {
  block_type: "morning" | "afternoon" | "evening";
  start_time: string;
  end_time: string;
  items: ScheduledItem[];
};

type RemainingBlockWindow = {
  block_type: "morning" | "afternoon" | "evening";
  start_time: string;
  end_time: string;
};

type DayAvailabilitySummary = {
  was_trimmed: boolean;
  effective_start: string | null;
  effective_end: string | null;
  remaining_blocks: RemainingBlockWindow[];
};

type AvailabilityPreviewDay = {
  day: number;
  availability_summary: DayAvailabilitySummary;
};

type AvailabilityPreviewResponse = {
  trip_days: number;
  days: AvailabilityPreviewDay[];
};

type DayItinerary = {
  day: number;
  availability_summary: DayAvailabilitySummary;
  blocks: DayBlock[];
};

type ItineraryResponse = {
  trip_days: number;
  hotel: {
    name: string;
    latitude: number;
    longitude: number;
  } | null;
  planning_anchor_source: PlanningAnchorSource;
  trip_intent?: TripIntentEnvelope | null;
  planning_assumptions: PlanningAssumptionSummary | null;
  completion_recommendation: ItineraryCompletionRecommendation | null;
  completion_intelligence?: CompletionIntelligenceSummary | null;
  journey_approach_recommendation: JourneyApproachRecommendation | null;
  stay_recommendation: StayRecommendation | null;
  departure_recommendation: DepartureRecommendation | null;
  planner_realism?: PlannerRealismSummary | null;
  boundary_explanation: BoundaryExplanation;
  days: DayItinerary[];
};

type PlannerRealismIssue = {
  code: string;
  severity: "low" | "medium" | "high" | string;
  title: string;
  detail: string;
  day?: number | null;
  item_names?: string[] | null;
};

type PlannerRealismAction = {
  action_id: string;
  label: string;
  prompt: string;
  priority: "low" | "medium" | "high" | string;
  related_issue_code?: string | null;
};

type PlannerRealismSummary = {
  status: "executable" | "needs_repair" | "unstable" | string;
  headline: string;
  issues: PlannerRealismIssue[];
  suggested_actions: PlannerRealismAction[];
};

type CompletionIntelligenceSummary = {
  trip_completeness: number;
  score_breakdown?: CompletionScoreBreakdown | null;
  action_tasks?: CompletionTaskCard[] | null;
  sparse_blocks_detected: string[];
  auto_filled_scenic_count: number;
  auto_filled_meal_count: number;
  auto_filled_evening_count: number;
  auto_fill_attempted?: boolean;
  auto_fill_blocked_reasons?: string[];
  stay_area_recommendation: string | null;
  departure_hub_recommendation: string | null;
  why_this_plan_works: string[];
};

type CompletionTaskCard = {
  task_id: string;
  task_instance_key?: string | null;
  title: string;
  reason: string;
  action_label: string;
  action_prompt: string;
  priority?: "high" | "medium" | "low" | string;
};

type CompletionTaskActionResponse = {
  task_id: string;
  applied: boolean;
  summary: string;
  inserted_item: ScheduledItem | null;
  itinerary: ItineraryResponse;
};

type CompletionTaskCandidatePreviewResponse = {
  task_id: string;
  task_instance_key: string | null;
  target_day: number | null;
  target_block: DayBlock["block_type"] | null;
  summary: string;
  candidate_source_summary?: string | null;
  candidate_discovery_status?: "route_context" | "city_text" | "local_only" | "empty" | string | null;
  options: ItineraryCompletionOption[];
};

type CompletionScoreBreakdown = {
  density: number;
  density_reason?: string | null;
  density_signals?: CompletionScoreFactor[] | null;
  density_penalties?: CompletionScoreFactor[] | null;
  meals: number;
  meals_reason?: string | null;
  meals_signals?: CompletionScoreFactor[] | null;
  meals_penalties?: CompletionScoreFactor[] | null;
  evening: number;
  evening_reason?: string | null;
  evening_signals?: CompletionScoreFactor[] | null;
  evening_penalties?: CompletionScoreFactor[] | null;
  transport_boundary: number;
  transport_boundary_reason?: string | null;
  transport_boundary_signals?: CompletionScoreFactor[] | null;
  transport_boundary_penalties?: CompletionScoreFactor[] | null;
};

type DirectOptimizationComparison = {
  title: string;
  lines: string[];
};

type PlanningAssumptionSummary = {
  destination: string | null;
  trip_days_basis: string;
  trip_scope_estimate: TripScopeEstimate | null;
  user_seed_scenic_count: number;
  user_seed_restaurant_count: number;
  fixed_event_count: number;
  availability_window_count: number;
  auto_seeded_poi_count: number;
  auto_seeded_meal_count: number;
  auto_filled_count: number;
  meal_structure_applied: boolean;
  summary_lines: string[];
  execution_trace?: PlanningExecutionTraceItem[];
  departure_hub_trace?: DepartureHubDecisionTrace | null;
  regeneration_intent: RegenerationIntentSummary | null;
  follow_up_interpretation: FollowUpInterpretationSummary | null;
};

type DepartureHubCandidateTrace = {
  name: string;
  category: string;
  rank: number | null;
  distance_km: number | null;
  status: string;
  reason: string;
};

type DepartureHubDecisionTrace = {
  selected_hub_name: string;
  preferred_mode: TravelMode | null;
  target_summary: string;
  selection_rule: string;
  top_candidates: DepartureHubCandidateTrace[];
  rejected_candidates: DepartureHubCandidateTrace[];
};

type PlanningExecutionTraceItem = {
  item_name: string;
  item_type: "scenic" | "restaurant" | "hotel";
  day: number;
  block_type: DayBlock["block_type"];
  source_type: ScheduledItemSourceType;
  decision_type: string;
  decision_stage: string;
  ownership_type: string;
  timing_role: string;
  is_user_owned: boolean;
  is_hard_constraint: boolean;
  is_editable: boolean;
  summary: string;
  evidence: PlanningDecisionTraceEvidence;
};

type PlanningDecisionTraceEvidence = {
  why_included: string;
  timing_decision: string;
  ownership_signal: string;
  flexibility: string;
  top_candidates?: CompletionCandidateTrace[];
  rejected_candidates?: CompletionCandidateTrace[];
};

type FollowUpInterpretationSummary = {
  raw_text: string;
  destination_changed_to: string | null;
  pinned_trip_days: number | null;
  added_scenic_spots: string[];
  added_restaurants: string[];
  removed_scenic_spots: string[];
  removed_restaurants: string[];
  added_fixed_events: ParsedFixedEvent[];
  added_availability_windows: AvailabilityWindow[];
  added_preferences: string[];
  summary_lines: string[];
};

type TripIntentEnvelope = {
  version: number;
  source: "direct_generate" | "initial_text" | "follow_up" | "regenerate";
  raw_text: string | null;
  latest_follow_up_text: string | null;
  base_intent: RegenerationIntentSummary | null;
  current_intent: RegenerationIntentSummary;
  parsed_intent: ParsedTripIntent | null;
  planning_state: PlanningInputState | null;
  follow_up_interpretation: FollowUpInterpretationSummary | null;
  compile_summary?: TripIntentCompileSummary | null;
  completion_candidate_history?: ItineraryCompletionOption[];
  summary_lines: string[];
};

type TripIntentCompileSummary = {
  city: string | null;
  trip_days_mode: string;
  scenic_seed_count: number;
  restaurant_seed_count: number;
  fixed_event_count: number;
  availability_window_count: number;
  rejected_poi_count: number;
  confirmed_replacement_count: number;
  needs_auto_completion: boolean;
  summary_lines: string[];
};

type RegenerationIntentSummary = {
  city: string | null;
  travel_mode: TravelMode | null;
  hotel: string | null;
  arrival_anchor: string | null;
  departure_anchor: string | null;
  availability_windows: AvailabilityWindow[];
  trip_days: number | null;
  suggested_trip_days: number;
  trip_days_basis: string;
  flexible_scenic_spots: string[];
  flexible_restaurants: string[];
  fixed_events: ParsedFixedEvent[];
  preferences: string[];
  style_preferences: string[];
  style_preference_sources: Record<string, string>;
  auto_seeded_scenic_spots: string[];
  auto_seeded_restaurants: string[];
  carry_forward_scenic_spots: string[];
  carry_forward_restaurants: string[];
  rejected_scenic_spots: string[];
  rejected_restaurants: string[];
  confirmed_replacements: UserConfirmedReplacement[];
  notes: string[];
};

type UserConfirmedReplacement = {
  original_name: string;
  original_type: "scenic" | "restaurant";
  replacement_name: string;
  replacement_type: "scenic" | "restaurant";
  source: string;
  reasoning_summary: string | null;
};

type TravelMode = "airplane" | "high_speed_rail" | "rail" | "car" | "undecided";

type PlanningAnchorSource = {
  source_type: "provided_hotel" | "arrival_anchor" | "departure_anchor" | "fallback_poi";
  source_name: string;
  latitude?: number | null;
  longitude?: number | null;
};

type StayRecommendation = {
  recommendation_type: string;
  recommendation_title: string;
  options: StayOption[];
};

type StayOption = {
  option_title: string;
  suggested_area_label: string;
  fit_label: string;
  anchor_pois: string[];
  reasoning_summary: string;
  itinerary_relation_summary: string;
  area_source?: string | null;
};

type DepartureRecommendation = {
  recommendation_title: string;
  options: DepartureOption[];
};

type DepartureOption = {
  option_title: string;
  fit_label: string;
  suggested_departure_label: string;
  anchor_pois: string[];
  reasoning_summary: string;
  itinerary_relation_summary: string;
  decision_trace?: DepartureHubDecisionTrace | null;
};

type JourneyApproachSuggestion = {
  recommendation_title: string;
  recommended_mode: TravelMode;
  recommended_hub_name: string | null;
  fit_label: string;
  suggested_area_label: string;
  anchor_pois: string[];
  reasoning_summary: string;
  itinerary_relation_summary: string;
};

type JourneyApproachRecommendation = {
  recommendation_title: string;
  arrival: JourneyApproachSuggestion | null;
  departure: JourneyApproachSuggestion | null;
};

type ItineraryCompletionRecommendation = {
  recommendation_title: string;
  summary: string;
  sparse_days: SparseDaySummary[];
  options: ItineraryCompletionOption[];
};

type SparseDaySummary = {
  day: number;
  item_count: number;
  missing_blocks: ("morning" | "afternoon" | "evening")[];
};

type ItineraryCompletionOption = {
  name: string;
  type: "scenic" | "restaurant";
  suggested_day: number;
  suggested_block: "morning" | "afternoon" | "evening";
  reasoning_summary: string;
  itinerary_relation_summary: string;
  decision_evidence?: CompletionDecisionEvidence | null;
};

type CompletionDecisionEvidence = {
  why_gap_exists: string;
  why_this_poi_fits: string;
  alternatives_rejected: string;
  top_candidates?: CompletionCandidateTrace[];
  rejected_candidates?: CompletionCandidateTrace[];
};

type CompletionCandidateTrace = {
  name: string;
  type: "scenic" | "restaurant";
  rank: number | null;
  score: number | null;
  status: string;
  reason: string;
};

type BoundaryExplanation = {
  arrival_anchor_influenced: boolean;
  arrival_anchor_name: string | null;
  arrival_poi_name: string | null;
  departure_anchor_influenced: boolean;
  departure_anchor_name: string | null;
  departure_poi_name: string | null;
};

type ParsedFixedEvent = {
  name: string;
  fixed_day: number | null;
  fixed_time_start: string | null;
  fixed_time_end: string | null;
  category: string | null;
};

type AvailabilityWindow = {
  day: number | null;
  label: string | null;
  available_start: string | null;
  available_end: string | null;
};

type PlaceDisambiguationResolution = {
  input_name: string;
  resolved_name: string;
  poi_type: string;
  city: string | null;
  confidence: string;
  source: string;
  reason: string;
  candidate_names: string[];
};

type IntentDisambiguationSummary = {
  city_hint: string | null;
  resolved_city: string | null;
  city_source: string;
  place_resolutions: PlaceDisambiguationResolution[];
  warnings: string[];
};

type ParsedTripIntent = {
  city: string | null;
  trip_days: number | null;
  hotel: string | null;
  arrival_anchor: string | null;
  departure_anchor: string | null;
  availability_windows: AvailabilityWindow[];
  scenic_spots: string[];
  restaurants: string[];
  fixed_events: ParsedFixedEvent[];
  preferences: string[];
  disambiguation_summary?: IntentDisambiguationSummary | null;
};

type PreferenceState = {
  mode: "explicit" | "implicit";
  strength: "weak" | "strong";
  extracted_preferences: string[];
};

type PacingProfile = "relaxed" | "balanced" | "packed";
type ExportMode = "practical" | "share";
type TripDaysSource = "explicit" | "estimated" | "scheduler_estimated" | "interaction_estimated";
type ShareCardFeedbackRating = "会用" | "还行" | "不太行";
type QuickPreviewMode = "current_brief" | "original_parse";

type ShareCardData = {
  title: string;
  meta: string;
  highlights: string[];
  keyStops: string[];
  edits: string[];
  closingLine: string;
};

type BriefPreviewCardViewModel = {
  title: string;
  stats: Array<{ label: string; value: string }>;
  strips: Array<{ title: string; content: string }>;
};

type PlanningInterpretationCardViewModel = {
  title: string;
  stats: Array<{ label: string; value: string }>;
  strips: Array<{ title: string; content: string }>;
};

type FollowUpInterpretationCardViewModel = {
  title: string;
  stats: Array<{ label: string; value: string }>;
  strips: Array<{ title: string; content: string }>;
};

type SectionHeaderViewModel = {
  eyebrow: string;
  title: string;
  description?: string;
};

type ShareCardFeedbackEntry = {
  id: string;
  created_at: string;
  rating: ShareCardFeedbackRating;
  note: string;
  trip_days: number;
  pacing: PacingProfile;
  share_title: string;
};

type TripScopeEstimate = {
  estimated_trip_days: number;
  estimation_mode: "explicit" | "estimated";
  confidence: "low" | "medium" | "high";
  poi_load_level: "light" | "medium" | "dense";
  reasoning_summary: string;
};

type IntentReadinessIssue = {
  code: string;
  severity: "info" | "warning" | "blocking";
  message: string;
  can_auto_assume: boolean;
};

type IntentReadinessAssessment = {
  level: "ready" | "needs_assumption" | "needs_clarification";
  can_generate: boolean;
  issue_count: number;
  issues: IntentReadinessIssue[];
  auto_assumptions: string[];
  clarification_questions: string[];
  summary: string;
};

type PlanningInputState = {
  city: string | null;
  trip_days: number | null;
  hotel: string | null;
  arrival_anchor: string | null;
  departure_anchor: string | null;
  availability_windows: AvailabilityWindow[];
  scenic_spots: string[];
  restaurants: string[];
  fixed_events: ParsedFixedEvent[];
  preferences: string[];
  time_state: "fixed_duration" | "semi_fixed_duration" | "flexible_duration";
  hotel_state: "known" | "roughly_known" | "unknown";
  arrival_anchor_state: "known" | "unknown";
  departure_anchor_state: "known" | "unknown";
  poi_state: "explicit_pois" | "partial_pois" | "mostly_preference_driven";
  fixed_event_state: "present" | "absent";
  preference_state: PreferenceState;
  trip_scope_estimate: TripScopeEstimate;
  readiness?: IntentReadinessAssessment;
  disambiguation_summary?: IntentDisambiguationSummary | null;
};

type PlanTripFromTextResponse = {
  trip_intent: TripIntentEnvelope;
  parsed_intent: ParsedTripIntent;
  planning_state: PlanningInputState;
  itinerary: ItineraryResponse;
};

type TripPlanResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  itinerary: ItineraryResponse;
  trip_intent: TripIntentEnvelope | null;
  parsed_intent: ParsedTripIntent | null;
  planning_state: PlanningInputState | null;
  persistence: {
    status: "saved";
    schema_version: string;
    idempotent_replay: boolean;
  };
};

type TripCurrentResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  itinerary: ItineraryResponse;
};

type TripRevisionListResponse = {
  trip: TripMetadata;
  revisions: TripRevisionMetadata[];
};

type PersistedCompletionTaskActionResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  task_result: CompletionTaskActionResponse;
  persistence: {
    status: "saved";
    schema_version: string;
    idempotent_replay: boolean;
  };
};

type PersistedReplanResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  replan_result: ReplanItineraryResponse;
  persistence: {
    status: "saved";
    schema_version: string;
    idempotent_replay: boolean;
  };
};

type PersistedReplanPreviewResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  proposal: {
    id: string;
    schema_version: string;
    operation_type: string;
    source_type: string;
    base_revision_id: string;
    request_digest: string;
    instruction_digest: string | null;
    preview_content_digest: string;
    proposal_digest: string;
    planner_run_id: string | null;
    planner_version: string | null;
    trace_schema_version: string | null;
    trace_digest: string | null;
    validation_report: Record<string, unknown>;
    status: string;
    expires_at: string;
    applied_revision_id: string | null;
  };
  replan_result: ReplanItineraryResponse;
};

type PersistedMutationProposal = {
  id: string;
  schema_version: string;
  operation_type: string;
  source_type: string;
  base_revision_id: string;
  request_digest: string;
  instruction_digest: string | null;
  preview_content_digest: string;
  proposal_digest: string;
  planner_run_id: string | null;
  planner_version: string | null;
  trace_schema_version: string | null;
  trace_digest: string | null;
  validation_report: Record<string, unknown>;
  execution_kind: string | null;
  command_schema_version: string | null;
  mutation_engine_version: string | null;
  mutation_kind: "route_edit" | "swap" | string | null;
  commands: Array<Record<string, unknown>> | null;
  command_digest: string | null;
  impact_summary: Record<string, unknown> | null;
  invalidated_surfaces: string[] | null;
  status: string;
  expires_at: string;
  applied_revision_id: string | null;
};

type PersistedMutationPreviewResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  proposal: PersistedMutationProposal;
  itinerary: ItineraryResponse;
  impact_summary: Record<string, unknown>;
  invalidated_surfaces: string[];
  refresh_targets: string[];
};

type PersistedMutationApplyResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  itinerary: ItineraryResponse;
  impact_summary: Record<string, unknown> | null;
  invalidated_surfaces: string[] | null;
  refresh_targets: string[] | null;
  persistence: {
    status: "saved";
    schema_version: string;
    idempotent_replay: boolean;
  };
};

type PersistedReplanProposalState =
  | { status: "idle" }
  | { status: "previewing"; baseRevisionId: string }
  | {
      status: "awaiting_apply" | "applying";
      proposalId: string;
      baseRevisionId: string;
      proposalDigest: string;
      expiresAt: string;
    }
  | { status: "expired" | "stale" | "error"; message: string };

type RestoreRevisionResponse = {
  trip: TripMetadata;
  current_revision: TripRevisionMetadata;
  itinerary: ItineraryResponse;
  persistence: {
    status: "saved";
    schema_version: string;
    idempotent_replay: boolean;
  };
};

type UndoPersistedMutationResponse = RestoreRevisionResponse;

type ReplanItineraryResponse = {
  trip_intent: TripIntentEnvelope;
  itinerary: ItineraryResponse;
};

type GenerateFromTripIntentResponse = {
  trip_intent: TripIntentEnvelope;
  itinerary: ItineraryResponse;
};

type TripIntentPatch = {
  city?: string | null;
  travel_mode?: TravelMode | null;
  hotel?: string | null;
  arrival_anchor?: string | null;
  departure_anchor?: string | null;
  availability_windows?: AvailabilityWindow[];
  trip_days?: number | null;
  flexible_scenic_spots?: string[];
  flexible_restaurants?: string[];
  fixed_events?: ParsedFixedEvent[];
  preferences?: string[];
  rejected_scenic_spots?: string[];
  rejected_restaurants?: string[];
  confirmed_replacements?: UserConfirmedReplacement[];
};

type GenerationContext = {
  city?: string | null;
  scenic_spots: string[];
  restaurants: string[];
  fixed_events: ParsedFixedEvent[];
  preferences: string[];
  pacing_profile: PacingProfile;
  trip_days_source?: TripDaysSource;
  trip_scope_estimate?: TripScopeEstimate | null;
  hotel: string | null;
  arrival_anchor: string | null;
  departure_anchor: string | null;
  availability_windows: AvailabilityWindow[];
};

type SwapTarget = {
  stable_id?: string | null;
  day: number;
  block_type: DayBlock["block_type"];
  start_time: string;
  end_time: string;
  name: string;
  type: ScheduledItem["type"];
};

type CommittedSwapSelection = {
  target_key: string;
  day: number;
  block_type: DayBlock["block_type"];
  start_time: string;
  end_time: string;
  original_name: string;
  original_type: "scenic" | "restaurant";
  replacement_name: string;
  replacement_type: "scenic" | "restaurant";
  source: "completion_recommendation";
  status: "user_confirmed";
  reasoning_summary: string;
  itinerary_relation_summary: string;
};

type UserIntentState = {
  original_scenic: string[];
  original_restaurants: string[];
  confirmed_scenic: string[];
  confirmed_restaurants: string[];
  rejected_scenic: string[];
  rejected_restaurants: string[];
};

type CompletionTaskEdit = {
  task_id: string;
  task_instance_key: string;
  task_title: string;
  inserted_item: ScheduledItem;
  inserted_item_key: string;
  summary: string;
  applied_at: string;
  status: "applied";
};

type PersistedOriginalFormState = {
  tripText: string;
  travelMode: TravelMode | null;
  parsedIntent: ParsedTripIntent | null;
  planningState: PlanningInputState | null;
  scenicSpots: string;
  restaurants: string;
  hotel: string;
  arrivalAnchor: string;
  departureAnchor: string;
  availabilityWindowsText: string;
  preferencesText: string;
  tripDays: string;
  fixedEventsText: string;
  availabilityPreview: AvailabilityPreviewResponse | null;
  availabilityPreviewSignature: string | null;
};

type PersistedTripSession = {
  version: 2;
  saved_at: string;
  itinerary: {
    result: ItineraryResponse | null;
    generationContext: GenerationContext | null;
    committedSwaps: CommittedSwapSelection[];
  };
  userIntentState: UserIntentState;
  preferenceSignals: PreferenceSignals;
  pacing: PacingProfile;
  quickPreviewMode?: QuickPreviewMode;
  dismissedFollowUpRawText?: string | null;
  latestFollowUpBaseIntent?: RegenerationIntentSummary | null;
  completionTaskEdits?: CompletionTaskEdit[];
  completionCandidateHistory?: ItineraryCompletionOption[];
  restoredCompletionCandidates?: ItineraryCompletionOption[];
  originalFormState: PersistedOriginalFormState;
};

type LegacyPersistedTestSession = PersistedOriginalFormState & {
  result: ItineraryResponse | null;
  generationContext: GenerationContext | null;
  committedSwaps: CommittedSwapSelection[];
  userIntentState: UserIntentState;
  preferenceSignals: PreferenceSignals;
  pacingProfile: PacingProfile;
  quickPreviewMode?: QuickPreviewMode;
  dismissedFollowUpRawText?: string | null;
  latestFollowUpBaseIntent?: RegenerationIntentSummary | null;
  completionTaskEdits?: CompletionTaskEdit[];
  completionCandidateHistory?: ItineraryCompletionOption[];
  restoredCompletionCandidates?: ItineraryCompletionOption[];
};

function normalizeStoredTripSession(value: unknown): PersistedTripSession | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const maybe = value as Partial<PersistedTripSession> & Partial<LegacyPersistedTestSession>;
  const originalFormState = maybe.originalFormState ?? {
    tripText: maybe.tripText ?? "",
    travelMode: maybe.travelMode ?? null,
    parsedIntent: maybe.parsedIntent ?? null,
    planningState: maybe.planningState ?? null,
    scenicSpots: maybe.scenicSpots ?? "",
    restaurants: maybe.restaurants ?? "",
    hotel: maybe.hotel ?? "",
    arrivalAnchor: maybe.arrivalAnchor ?? "",
    departureAnchor: maybe.departureAnchor ?? "",
    availabilityWindowsText: maybe.availabilityWindowsText ?? "",
    preferencesText: maybe.preferencesText ?? "",
    tripDays: maybe.tripDays ?? "",
    fixedEventsText: maybe.fixedEventsText ?? "",
    availabilityPreview: maybe.availabilityPreview ?? null,
    availabilityPreviewSignature: maybe.availabilityPreviewSignature ?? null,
  };

  return {
    version: 2,
    saved_at: maybe.saved_at ?? new Date().toISOString(),
    itinerary: {
      result: maybe.itinerary?.result ?? maybe.result ?? null,
      generationContext: maybe.itinerary?.generationContext ?? maybe.generationContext ?? null,
      committedSwaps: maybe.itinerary?.committedSwaps ?? maybe.committedSwaps ?? [],
    },
    userIntentState:
      maybe.userIntentState ??
      createUserIntentStateFromOriginalInputs(
        originalFormState.scenicSpots,
        originalFormState.restaurants,
      ),
    preferenceSignals: normalizePreferenceSignals(maybe.preferenceSignals),
    pacing: maybe.pacing ?? maybe.pacingProfile ?? "balanced",
    quickPreviewMode:
      maybe.quickPreviewMode ??
      ((maybe.itinerary?.result ?? maybe.result)?.planning_assumptions?.regeneration_intent
        ? "current_brief"
        : "original_parse"),
    dismissedFollowUpRawText: maybe.dismissedFollowUpRawText ?? null,
    latestFollowUpBaseIntent: maybe.latestFollowUpBaseIntent ?? null,
    completionTaskEdits: normalizeCompletionTaskEdits(maybe.completionTaskEdits),
    completionCandidateHistory: normalizeCompletionCandidateHistory(
      maybe.completionCandidateHistory ?? maybe.restoredCompletionCandidates,
    ),
    originalFormState,
  };
}

function createUserIntentStateFromOriginalInputs(
  scenicSpots: string,
  restaurants: string,
): UserIntentState {
  return {
    original_scenic: splitLines(scenicSpots),
    original_restaurants: splitLines(restaurants),
    confirmed_scenic: [],
    confirmed_restaurants: [],
    rejected_scenic: [],
    rejected_restaurants: [],
  };
}

function normalizePreferenceSignals(value: Partial<PreferenceSignals> | undefined): PreferenceSignals {
  return {
    ...createEmptyPreferenceSignals(),
    ...(value ?? {}),
  };
}

function normalizeCompletionTaskEdits(
  value: Partial<CompletionTaskEdit>[] | undefined,
): CompletionTaskEdit[] {
  if (!value) {
    return [];
  }
  return value
    .filter((edit): edit is Partial<CompletionTaskEdit> & { task_id: string; inserted_item: ScheduledItem } =>
      typeof edit.task_id === "string" && edit.inserted_item !== undefined,
    )
    .map((edit) => ({
      task_id: edit.task_id,
      task_instance_key:
        edit.task_instance_key ??
        `${edit.task_id}:${normalizeCompletionTaskKeyPart(
          `${edit.task_title ?? edit.task_id} ${edit.summary ?? ""}`,
        )}`,
      task_title: edit.task_title ?? edit.task_id,
      inserted_item: edit.inserted_item,
      inserted_item_key:
        edit.inserted_item_key ?? buildRecentCompletionTaskItemKey(edit.inserted_item),
      summary: edit.summary ?? `已补入：${edit.inserted_item.name}`,
      applied_at: edit.applied_at ?? new Date().toISOString(),
      status: "applied",
    }));
}

function normalizeCompletionCandidateHistory(
  value: Partial<ItineraryCompletionOption>[] | undefined,
): ItineraryCompletionOption[] {
  if (!value) {
    return [];
  }
  return value
    .filter(
      (option): option is ItineraryCompletionOption =>
        typeof option.name === "string" &&
        (option.type === "scenic" || option.type === "restaurant") &&
        typeof option.suggested_day === "number" &&
        (option.suggested_block === "morning" ||
          option.suggested_block === "afternoon" ||
          option.suggested_block === "evening") &&
        typeof option.reasoning_summary === "string" &&
        typeof option.itinerary_relation_summary === "string",
    )
    .reduce<ItineraryCompletionOption[]>(
      (current, option) => upsertCompletionCandidateHistory(current, option),
      [],
    );
}

export default function HomePage() {
  const [tripText, setTripText] = useState("");
  const [travelMode, setTravelMode] = useState<TravelMode | null>(null);
  const [parsedIntent, setParsedIntent] = useState<ParsedTripIntent | null>(null);
  const [planningState, setPlanningState] = useState<PlanningInputState | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [parsing, setParsing] = useState(false);
  const [scenicSpots, setScenicSpots] = useState("");
  const [restaurants, setRestaurants] = useState("");
  const [hotel, setHotel] = useState("");
  const [arrivalAnchor, setArrivalAnchor] = useState("");
  const [departureAnchor, setDepartureAnchor] = useState("");
  const [availabilityWindowsText, setAvailabilityWindowsText] = useState("");
  const [preferencesText, setPreferencesText] = useState("");
  const [tripDays, setTripDays] = useState("");
  const [fixedEventsText, setFixedEventsText] = useState("");
  const [availabilityPreview, setAvailabilityPreview] = useState<AvailabilityPreviewResponse | null>(null);
  const [availabilityPreviewSignature, setAvailabilityPreviewSignature] = useState<string | null>(null);
  const [availabilityPreviewError, setAvailabilityPreviewError] = useState<string | null>(null);
  const [previewingAvailability, setPreviewingAvailability] = useState(false);
  const [result, setResult] = useState<ItineraryResponse | null>(null);
  const [generationContext, setGenerationContext] = useState<GenerationContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [followUpText, setFollowUpText] = useState("");
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [shareCardImageUrl, setShareCardImageUrl] = useState<string | null>(null);
  const [shareCardStatus, setShareCardStatus] = useState<string | null>(null);
  const [shareFeedbackRating, setShareFeedbackRating] = useState<ShareCardFeedbackRating | null>(null);
  const [shareFeedbackNote, setShareFeedbackNote] = useState("");
  const [shareFeedbackSaved, setShareFeedbackSaved] = useState(false);
  const [loading, setLoading] = useState(false);
  const [replanning, setReplanning] = useState(false);
  const [persistedReplanProposal, setPersistedReplanProposal] =
    useState<PersistedReplanProposalState>({ status: "idle" });
  const [applyingCompletionTaskId, setApplyingCompletionTaskId] = useState<string | null>(null);
  const [completionTaskStatus, setCompletionTaskStatus] = useState<string | null>(null);
  const [recentCompletionTaskItemKey, setRecentCompletionTaskItemKey] = useState<string | null>(null);
  const [travelModeModalOpen, setTravelModeModalOpen] = useState(false);
  const [completionPickerOpen, setCompletionPickerOpen] = useState(false);
  const [selectedCompletionOptionKeys, setSelectedCompletionOptionKeys] = useState<string[]>([]);
  const [activeSwapTarget, setActiveSwapTarget] = useState<SwapTarget | null>(null);
  const [advancedModeOpen, setAdvancedModeOpen] = useState(false);
  const [committedSwaps, setCommittedSwaps] = useState<CommittedSwapSelection[]>([]);
  const [userIntentState, setUserIntentState] = useState<UserIntentState>({
    original_scenic: [],
    original_restaurants: [],
    confirmed_scenic: [],
    confirmed_restaurants: [],
    rejected_scenic: [],
    rejected_restaurants: [],
  });
  const [preferenceSignals, setPreferenceSignals] = useState<PreferenceSignals>(
    createEmptyPreferenceSignals(),
  );
  const [pacingProfile, setPacingProfile] = useState<PacingProfile>("balanced");
  const [hasSavedSession, setHasSavedSession] = useState(false);
  const [sessionHydrated, setSessionHydrated] = useState(false);
  const [savedTripPromptOpen, setSavedTripPromptOpen] = useState(false);
  const [tripPersistence, setTripPersistence] = useState<TripPersistenceState>({
    status: "none",
  });
  const [returnToTripTextNotice, setReturnToTripTextNotice] = useState<string | null>(null);
  const [restoreTripTextFocus, setRestoreTripTextFocus] = useState(false);
  const [revisionHistory, setRevisionHistory] = useState<TripRevisionMetadata[]>([]);
  const [versionHistoryOpen, setVersionHistoryOpen] = useState(false);
  const [quickPreviewMode, setQuickPreviewMode] = useState<QuickPreviewMode>("original_parse");
  const [dismissedFollowUpRawText, setDismissedFollowUpRawText] = useState<string | null>(null);
  const [highlightedResultTargetId, setHighlightedResultTargetId] = useState<string | null>(null);
  const [latestFollowUpBaseIntent, setLatestFollowUpBaseIntent] =
    useState<RegenerationIntentSummary | null>(null);
  const [latestDirectOptimizationComparison, setLatestDirectOptimizationComparison] =
    useState<DirectOptimizationComparison | null>(null);
  const [completionTaskEdits, setCompletionTaskEdits] = useState<CompletionTaskEdit[]>([]);
  const [completionCandidateHistory, setCompletionCandidateHistory] = useState<
    ItineraryCompletionOption[]
  >([]);
  const [completionTasksExpanded, setCompletionTasksExpanded] = useState(false);
  const {
    routeEditMode,
    activeRouteSheet,
    toggleRouteEditMode,
    setRouteEditMode,
    setActiveRouteSheet,
    focusRouteDay,
    routeFocusRequest,
  } = useRouteWorkspaceUiState();
  const [completionTaskCandidatePreviews, setCompletionTaskCandidatePreviews] =
    useState<Record<string, CompletionTaskCandidatePreviewResponse>>({});
  const [previewingCompletionTaskId, setPreviewingCompletionTaskId] = useState<string | null>(null);
  const [candidateWorkspace, setCandidateWorkspace] = useState<CandidateWorkspaceState>({
    status: "idle",
  });
  const resultSectionRef = useRef<HTMLElement | null>(null);
  const shouldRevealResultRef = useRef(false);
  const shouldFocusResultRef = useRef(false);
  const isAvailabilityPreviewStale =
    availabilityPreview !== null &&
    availabilityPreviewSignature !== buildAvailabilityPreviewSignature(tripDays, availabilityWindowsText);
  const readiness = getPlanningReadiness({
    hotel,
    scenicSpots,
    restaurants,
    fixedEventsText,
  });
  const itineraryValueSummary =
    result && generationContext
      ? buildItineraryValueSummary(result, generationContext, committedSwaps)
      : null;
  const resultCompletionStatus = result
    ? buildResultCompletionStatus(result, generationContext)
    : [];
  const activeTripIntent = result?.trip_intent ?? null;
  const activeRegenerationIntent =
    activeTripIntent?.current_intent ?? result?.planning_assumptions?.regeneration_intent ?? null;
  const activeTripCity =
    activeRegenerationIntent?.city ??
    generationContext?.city ??
    parsedIntent?.city ??
    "当前城市";
  const tripReadinessViewModel = result
    ? buildTripReadinessViewModel({
        city: activeTripCity,
        tripDays: result.trip_days,
        completion: result.completion_intelligence,
        plannerRealism: result.planner_realism,
        boundaryExplanation: result.boundary_explanation,
        planningAssumptions: result.planning_assumptions,
        days: result.days,
      })
    : null;
  const commandCenterAutoFilledCount = result?.completion_intelligence
    ? result.completion_intelligence.auto_filled_scenic_count +
      result.completion_intelligence.auto_filled_meal_count +
      result.completion_intelligence.auto_filled_evening_count
    : (result?.planning_assumptions?.auto_filled_count ?? 0);
  const commandCenterIntentLines =
    itineraryValueSummary?.fromInputLines.slice(0, 2) ??
    resultCompletionStatus
      .filter((item) => item.label === "理解旅行意图" || item.label === "生成旅行骨架")
      .map((item) => `${item.label}：${item.description}`);
  const commandCenterSystemLines = result
    ? [
        result.planner_realism?.headline,
        ...(result.completion_intelligence
          ? buildCompletionIntelligenceDisplayLines(result.completion_intelligence).slice(0, 2)
          : []),
        ...(itineraryValueSummary?.whyLines.slice(0, 1) ?? []),
      ].filter((line): line is string => Boolean(line))
    : [];
  const latestFollowUpInterpretation =
    activeTripIntent?.follow_up_interpretation ??
    result?.planning_assumptions?.follow_up_interpretation ??
    null;
  const latestFollowUpEffectCleared =
    latestFollowUpInterpretation?.raw_text !== undefined &&
    latestFollowUpInterpretation.raw_text === dismissedFollowUpRawText;
  const activeFollowUpInterpretation = latestFollowUpInterpretation;
  const canClearLatestFollowUpEffect =
    latestFollowUpInterpretation !== null && latestFollowUpBaseIntent !== null;
  const effectiveRegenerationIntentForNextGenerate =
    latestFollowUpEffectCleared && latestFollowUpBaseIntent
      ? latestFollowUpBaseIntent
      : activeRegenerationIntent;
  const canPinCurrentTripScope =
    effectiveRegenerationIntentForNextGenerate !== null &&
    effectiveRegenerationIntentForNextGenerate.trip_days === null &&
    tripDays.trim() !== String(effectiveRegenerationIntentForNextGenerate.suggested_trip_days);
  const showQuickPreviewCurrentBrief =
    quickPreviewMode === "current_brief" && activeRegenerationIntent !== null;
  const quickPreviewBrief =
    showQuickPreviewCurrentBrief
      ? buildParsedIntentFromRegenerationIntent(activeRegenerationIntent)
      : parsedIntent;
  const advancedModeBrief =
    activeRegenerationIntent !== null
      ? buildParsedIntentFromRegenerationIntent(activeRegenerationIntent)
      : parsedIntent;
  const quickPreviewBriefCard =
    quickPreviewBrief !== null
      ? buildBriefPreviewCardViewModel(quickPreviewBrief, {
          isCurrentRegenerateBrief: showQuickPreviewCurrentBrief,
          regenerationIntent: activeRegenerationIntent,
        })
      : null;
  const advancedModeBriefCard =
    advancedModeBrief !== null
      ? buildBriefPreviewCardViewModel(advancedModeBrief, {
          isCurrentRegenerateBrief: activeRegenerationIntent !== null,
          regenerationIntent: activeRegenerationIntent,
        })
      : null;
  const quickPreviewSectionHeader = buildQuickPreviewSectionHeaderViewModel({
    isCurrentRegenerateBrief: showQuickPreviewCurrentBrief,
    hasFollowUpInterpretation: activeFollowUpInterpretation !== null,
  });
  const advancedModeSectionHeader = buildAdvancedReviewSectionHeaderViewModel({
    hasRegenerationIntent: activeRegenerationIntent !== null,
    hasFollowUpInterpretation: activeFollowUpInterpretation !== null,
  });

  function buildCurrentTripSession(): PersistedTripSession {
    return {
      version: 2,
      saved_at: new Date().toISOString(),
      itinerary: {
        result,
        generationContext,
        committedSwaps,
      },
      userIntentState,
      preferenceSignals,
      pacing: pacingProfile,
      quickPreviewMode,
      dismissedFollowUpRawText,
      latestFollowUpBaseIntent,
      completionTaskEdits,
      completionCandidateHistory,
      originalFormState: {
        tripText,
        travelMode,
        parsedIntent,
        planningState,
        scenicSpots,
        restaurants,
        hotel,
        arrivalAnchor,
        departureAnchor,
        availabilityWindowsText,
        preferencesText,
        tripDays,
        fixedEventsText,
        availabilityPreview,
        availabilityPreviewSignature,
      },
    };
  }

  function restoreSavedSession(session: PersistedTripSession) {
    const { originalFormState } = session;
    setTripText(originalFormState.tripText);
    setTravelMode(originalFormState.travelMode);
    setTravelModeModalOpen(false);
    setParsedIntent(originalFormState.parsedIntent);
    setPlanningState(originalFormState.planningState);
    setScenicSpots(originalFormState.scenicSpots);
    setRestaurants(originalFormState.restaurants);
    setHotel(originalFormState.hotel);
    setArrivalAnchor(originalFormState.arrivalAnchor);
    setDepartureAnchor(originalFormState.departureAnchor);
    setAvailabilityWindowsText(originalFormState.availabilityWindowsText);
    setPreferencesText(originalFormState.preferencesText);
    setTripDays(originalFormState.tripDays);
    setFixedEventsText(originalFormState.fixedEventsText);
    setAvailabilityPreview(originalFormState.availabilityPreview);
    setAvailabilityPreviewSignature(originalFormState.availabilityPreviewSignature);
    setResult(session.itinerary.result);
    setGenerationContext(session.itinerary.generationContext);
    setCommittedSwaps(session.itinerary.committedSwaps);
    setUserIntentState(session.userIntentState);
    setPreferenceSignals(normalizePreferenceSignals(session.preferenceSignals));
    setPacingProfile(session.pacing);
    setDismissedFollowUpRawText(session.dismissedFollowUpRawText ?? null);
    setLatestFollowUpBaseIntent(session.latestFollowUpBaseIntent ?? null);
    setCompletionTaskEdits(session.completionTaskEdits ?? []);
    setCompletionCandidateHistory(session.completionCandidateHistory ?? []);
    setQuickPreviewMode(
      session.quickPreviewMode ??
        (session.itinerary.result?.planning_assumptions?.regeneration_intent
          ? "current_brief"
          : "original_parse"),
    );
    setSavedTripPromptOpen(false);
    setParseError(null);
    setAvailabilityPreviewError(null);
    setError(null);
  }

  function rememberPersistedTrip(trip: TripMetadata, revision: TripRevisionMetadata) {
    const ref = buildPersistedTripRef(trip, revision);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(PERSISTED_TRIP_REF_KEY, serializePersistedTripRef(ref));
      window.localStorage.removeItem(SAVED_TRIP_SESSION_KEY);
    }
    setTripPersistence(markSavedFromRevision(revision));
    setHasSavedSession(true);
    void refreshCandidates(ref.tripId);
  }

  async function hydrateFromPersistedMutation(
    trip: TripMetadata,
    revision: TripRevisionMetadata,
    itinerary: ItineraryResponse,
  ) {
    setResult(itinerary);
    rememberPersistedTrip(trip, revision);
    setGenerationContext(
      itinerary.trip_intent?.current_intent
        ? buildGenerationContextFromRegenerationIntent(itinerary.trip_intent.current_intent)
        : generationContext,
    );
    syncFormStateWithRegenerationIntent(
      itinerary.trip_intent?.current_intent ??
        itinerary.planning_assumptions?.regeneration_intent ??
        null,
    );
    await refreshRevisionHistory(trip.id);
  }

  function clearPersistedTripRef() {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(PERSISTED_TRIP_REF_KEY);
      window.localStorage.removeItem(SAVED_TRIP_SESSION_KEY);
    }
    setTripPersistence({ status: "none" });
    setRevisionHistory([]);
    setCandidateWorkspace({ status: "idle" });
    setHasSavedSession(false);
  }

  function markWorkspaceDirty(reason: string) {
    setTripPersistence((current) => markDirty(current, reason));
  }

  async function restorePersistedTripRef() {
    if (typeof window === "undefined") {
      return false;
    }
    const ref = parsePersistedTripRef(window.localStorage.getItem(PERSISTED_TRIP_REF_KEY));
    if (!ref) {
      window.localStorage.removeItem(PERSISTED_TRIP_REF_KEY);
      return false;
    }

    if (ref.schemaVersion === 2 && ref.kind === "draft") {
      const draft = await getTripJson<{ trip: TripMetadata; direct_user_text: string }>(
        TRIP_API_ENDPOINTS.getDraftTrip(ref.tripId),
        "恢复草稿行程失败",
      );
      if (!draft.ok) {
        clearPersistedTripRef();
        return false;
      }
      setTripText(draft.data.direct_user_text);
      setTripPersistence({ status: "draft", tripId: draft.data.trip.id });
      setSavedTripPromptOpen(false);
      return true;
    }

    setTripPersistence({ status: "restoring", tripId: ref.tripId });
    const response = await getTripJson<TripCurrentResponse>(
      TRIP_API_ENDPOINTS.getTrip(ref.tripId),
      "恢复保存行程失败",
      "后端暂时不可用，当前页面不会重新生成行程。",
    );

    if (!response.ok) {
      if (
        response.message.includes("trip_not_found") ||
        response.message.includes("trip_access_denied")
      ) {
        clearPersistedTripRef();
      } else {
        setTripPersistence({
          status: "error",
          message: response.message,
          tripId: ref.tripId,
          recoverable: true,
        });
      }
      return false;
    }

    const current = response.data;
    setResult(current.itinerary);
    rememberPersistedTrip(current.trip, current.current_revision);
    setGenerationContext(
      current.itinerary.trip_intent?.current_intent
        ? buildGenerationContextFromRegenerationIntent(
            current.itinerary.trip_intent.current_intent,
          )
        : generationContext,
    );
    syncFormStateWithRegenerationIntent(
      current.itinerary.trip_intent?.current_intent ??
        current.itinerary.planning_assumptions?.regeneration_intent ??
        null,
    );
    setSavedTripPromptOpen(false);
    setError(null);
    await refreshRevisionHistory(current.trip.id);
    return true;
  }

  async function refreshRevisionHistory(tripId: string) {
    const response = await getTripJson<TripRevisionListResponse>(
      TRIP_API_ENDPOINTS.listTripRevisions(tripId),
      "获取版本历史失败",
    );
    if (response.ok) {
      setRevisionHistory(response.data.revisions);
    }
  }

  async function loadLatestSavedRoute(): Promise<{ revisionNumber: number } | { errorMessage: string }> {
    if (tripPersistence.status !== "saved") {
      return { errorMessage: "暂时无法确定需要载入哪一份路线。当前页面没有改动任何路线。" };
    }
    const response = await getTripJson<TripCurrentResponse>(
      TRIP_API_ENDPOINTS.getTrip(tripPersistence.tripId),
      "载入最新路线失败",
      "后端暂时不可用，当前页面没有改动任何路线。",
    );
    if (!response.ok) {
      return { errorMessage: "暂时无法载入最新路线。当前页面没有改动任何路线。" };
    }
    const current = response.data;
    setResult(current.itinerary);
    rememberPersistedTrip(current.trip, current.current_revision);
    setGenerationContext(
      current.itinerary.trip_intent?.current_intent
        ? buildGenerationContextFromRegenerationIntent(current.itinerary.trip_intent.current_intent)
        : generationContext,
    );
    syncFormStateWithRegenerationIntent(
      current.itinerary.trip_intent?.current_intent
        ?? current.itinerary.planning_assumptions?.regeneration_intent
        ?? null,
    );
    await refreshRevisionHistory(current.trip.id);
    return { revisionNumber: current.current_revision.revision_number };
  }

  async function refreshCandidates(tripId: string) {
    setCandidateWorkspace({ status: "loading" });
    const response = await getTripJson<CandidateListResponse>(
      TRIP_API_ENDPOINTS.listTripCandidates(tripId),
      "获取候选地点失败",
    );
    if (!response.ok) {
      setCandidateWorkspace({
        status: "error",
        code: response.code ?? "candidate_fetch_failed",
        message: response.message,
      });
      return;
    }
    setCandidateWorkspace(groupCandidates(response.data.candidates));
  }

  async function registerManualCandidate(name: string, type: "scenic" | "restaurant") {
    if (tripPersistence.status !== "saved") {
      setError("候选地点需要先有已保存的 TripRevision 才能持久化。");
      return null;
    }
    const payload = buildManualCandidatePayload(name, type);
    const response = await postTripJson<CandidateRegistrationResponse>(
      TRIP_API_ENDPOINTS.registerTripCandidate(tripPersistence.tripId),
      payload,
      "保存候选地点失败",
      undefined,
      {
        headers: {
          "X-Idempotency-Key": candidateIdempotencyKey(
            "candidate-manual",
            tripPersistence.tripId,
            `${payload.display_name}:${payload.category ?? ""}`,
          ),
        },
      },
    );
    if (!response.ok) {
      setError(response.message);
      return null;
    }
    await refreshCandidates(tripPersistence.tripId);
    return response.data.candidate;
  }

  async function registerCompletionCandidate(option: ItineraryCompletionOption) {
    if (tripPersistence.status !== "saved") {
      return null;
    }
    const payload = buildCompletionCandidatePayload(option);
    const response = await postTripJson<CandidateRegistrationResponse>(
      TRIP_API_ENDPOINTS.registerTripCandidate(tripPersistence.tripId),
      payload,
      "保存补全候选失败",
      undefined,
      {
        headers: {
          "X-Idempotency-Key": candidateIdempotencyKey(
            "candidate-completion",
            tripPersistence.tripId,
            `${payload.display_name}:${payload.explicit_day_reference ?? ""}:${payload.preferred_time_block ?? ""}`,
          ),
        },
      },
    );
    if (!response.ok) {
      setError(response.message);
      return null;
    }
    await refreshCandidates(tripPersistence.tripId);
    return response.data.candidate;
  }

  async function recordCandidateDecision(
    candidate: TripCandidate,
    decision: "reject" | "defer" | "restore_pending",
    reasonCode = "USER_REJECTED",
  ) {
    if (tripPersistence.status !== "saved") {
      setError("候选决策需要已保存的 TripRevision 作为审计上下文。");
      return;
    }
    const response = await postTripJson<CandidateDecisionResponse>(
      TRIP_API_ENDPOINTS.recordTripCandidateDecision(tripPersistence.tripId, candidate.id),
      {
        decision,
        reason_code: decision === "restore_pending" ? "RESTORED_TO_PENDING" : reasonCode,
        base_revision_id: tripPersistence.currentRevisionId,
      },
      "保存候选决策失败",
      undefined,
      {
        headers: {
          "X-Idempotency-Key": candidateIdempotencyKey(
            `candidate-${decision}`,
            tripPersistence.tripId,
            `${candidate.id}:${tripPersistence.currentRevisionId}`,
          ),
        },
      },
    );
    if (!response.ok) {
      setError(response.message);
      return;
    }
    await refreshCandidates(tripPersistence.tripId);
    setError(null);
  }

  async function admitCandidate(candidate: TripCandidate) {
    if (tripPersistence.status !== "saved") {
      setError("当前行程有未保存变更，无法把候选加入正式行程。");
      return;
    }
    const day = Number(candidate.explicit_day_reference || 1) || 1;
    const block =
      candidate.preferred_time_block === "morning" ||
      candidate.preferred_time_block === "afternoon" ||
      candidate.preferred_time_block === "evening"
        ? candidate.preferred_time_block
        : "afternoon";
    const envelope = buildCandidateAdmissionEnvelope(
      tripPersistence.currentRevisionId,
      candidate,
      day,
      block,
    );
    const applied = await applyPersistedMutationWithPreview(tripPersistence, envelope);
    if (!applied.ok) {
      if (applied.code === "candidate_admission_repair_required") {
        setError(`候选还不能直接加入行程：${formatCandidateRepairMessage(applied.context)}`);
        return;
      }
      markPersistedMutationFailure(tripPersistence, applied);
      return;
    }
    await hydrateFromPersistedMutation(
      applied.data.trip,
      applied.data.current_revision,
      applied.data.itinerary,
    );
    await refreshCandidates(applied.data.trip.id);
    setError(null);
  }

  async function handleRestoreRevision(revision: TripRevisionMetadata) {
    if (tripPersistence.status !== "saved") {
      setError("当前行程有未保存变更，先重新生成或刷新后再恢复历史版本。");
      return;
    }
    setTripPersistence({ status: "restoring", tripId: tripPersistence.tripId });
    const response = await postTripJson<RestoreRevisionResponse>(
      TRIP_API_ENDPOINTS.restoreTripRevision(tripPersistence.tripId, revision.id),
      {
        base_revision_id: tripPersistence.currentRevisionId,
      },
      "恢复历史版本失败",
      undefined,
      {
        headers: {
          "X-Idempotency-Key": `restore:${revision.id}:${tripPersistence.currentRevisionId}`,
        },
      },
    );

    if (!response.ok) {
      setError(response.message);
      setTripPersistence({
        status: "error",
        message: response.message,
        tripId: tripPersistence.tripId,
        recoverable: true,
      });
      return;
    }

    setResult(response.data.itinerary);
    rememberPersistedTrip(response.data.trip, response.data.current_revision);
    setGenerationContext(
      response.data.itinerary.trip_intent?.current_intent
        ? buildGenerationContextFromRegenerationIntent(
            response.data.itinerary.trip_intent.current_intent,
          )
        : generationContext,
    );
    syncFormStateWithRegenerationIntent(
      response.data.itinerary.trip_intent?.current_intent ??
        response.data.itinerary.planning_assumptions?.regeneration_intent ??
        null,
    );
    await refreshRevisionHistory(response.data.trip.id);
    setVersionHistoryOpen(false);
    setError(null);
  }

  function hasMeaningfulTripSession(session: PersistedTripSession): boolean {
    const { originalFormState } = session;
    return (
      originalFormState.tripText.trim().length > 0 ||
      originalFormState.travelMode !== null ||
      originalFormState.scenicSpots.trim().length > 0 ||
      originalFormState.restaurants.trim().length > 0 ||
      originalFormState.hotel.trim().length > 0 ||
      originalFormState.arrivalAnchor.trim().length > 0 ||
      originalFormState.departureAnchor.trim().length > 0 ||
      originalFormState.availabilityWindowsText.trim().length > 0 ||
      originalFormState.preferencesText.trim().length > 0 ||
      originalFormState.tripDays.trim().length > 0 ||
      originalFormState.fixedEventsText.trim().length > 0 ||
      originalFormState.parsedIntent !== null ||
      originalFormState.planningState !== null ||
      originalFormState.availabilityPreview !== null ||
      session.itinerary.result !== null ||
      session.itinerary.generationContext !== null ||
      session.itinerary.committedSwaps.length > 0 ||
      session.userIntentState.confirmed_scenic.length > 0 ||
      session.userIntentState.confirmed_restaurants.length > 0 ||
      session.userIntentState.rejected_scenic.length > 0 ||
      session.userIntentState.rejected_restaurants.length > 0 ||
      (session.completionTaskEdits?.length ?? 0) > 0 ||
      (session.completionCandidateHistory?.length ?? 0) > 0 ||
      Object.values(session.preferenceSignals).some((value) => value !== 0) ||
      session.pacing !== "balanced"
    );
  }

  function resetCurrentTripState() {
    setTripText("");
    setTravelMode(null);
    setParsedIntent(null);
    setPlanningState(null);
    setScenicSpots("");
    setRestaurants("");
    setHotel("");
    setArrivalAnchor("");
    setDepartureAnchor("");
    setAvailabilityWindowsText("");
    setPreferencesText("");
    setTripDays("");
    setFixedEventsText("");
    setAvailabilityPreview(null);
    setAvailabilityPreviewSignature(null);
    setAvailabilityPreviewError(null);
    setResult(null);
    setGenerationContext(null);
    setFollowUpText("");
    setCompletionTaskStatus(null);
    setRecentCompletionTaskItemKey(null);
    setAdvancedModeOpen(false);
    setCompletionPickerOpen(false);
    setSelectedCompletionOptionKeys([]);
    setActiveSwapTarget(null);
    setCommittedSwaps([]);
    setUserIntentState({
      original_scenic: [],
      original_restaurants: [],
      confirmed_scenic: [],
      confirmed_restaurants: [],
      rejected_scenic: [],
      rejected_restaurants: [],
    });
    setPreferenceSignals(createEmptyPreferenceSignals());
    setPacingProfile("balanced");
    setDismissedFollowUpRawText(null);
    setLatestFollowUpBaseIntent(null);
    setCompletionTaskEdits([]);
    setCompletionCandidateHistory([]);
    setQuickPreviewMode("original_parse");
    setParseError(null);
    setError(null);
    setTripPersistence({ status: "none" });
    setRevisionHistory([]);
    setVersionHistoryOpen(false);
  }

  function handleRestoreSavedSession() {
    void restorePersistedTripRef();
  }

  function handleStartNewTrip() {
    clearPersistedTripRef();
    resetCurrentTripState();
    setHasSavedSession(false);
    setSavedTripPromptOpen(false);
    setTravelModeModalOpen(false);
  }

  function handleResultStatusNavigate(targetId?: string) {
    if (!targetId || typeof document === "undefined") {
      return;
    }
    setHighlightedResultTargetId(targetId);
    document.getElementById(targetId)?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
    window.setTimeout(() => {
      setHighlightedResultTargetId((current) => (current === targetId ? null : current));
    }, 1600);
  }

  function scrollToResultWorkspace() {
    if (typeof window === "undefined") {
      return false;
    }

    const target =
      resultSectionRef.current ?? document.querySelector<HTMLElement>(".ec-result-entry");
    if (!target) {
      return false;
    }

    if (shouldFocusResultRef.current) {
      target.focus({ preventScroll: true });
      shouldFocusResultRef.current = false;
    }

    const targetTop = Math.max(0, target.getBoundingClientRect().top + window.scrollY - 20);
    window.scrollTo({
      top: targetTop,
      behavior: "smooth",
    });
    return true;
  }

  function scheduleResultReveal({ focus = false }: { focus?: boolean } = {}) {
    shouldRevealResultRef.current = true;
    shouldFocusResultRef.current = focus;

    if (typeof window === "undefined") {
      return;
    }

    window.setTimeout(() => {
      if (!shouldRevealResultRef.current) {
        return;
      }
      if (scrollToResultWorkspace()) {
        shouldRevealResultRef.current = false;
      }
    }, 220);
  }

  async function handleCopyItinerary(mode: ExportMode) {
    if (!result) {
      return;
    }

    const exportText =
      mode === "share"
        ? buildShareableItineraryText(result, generationContext, committedSwaps)
        : buildCopyableItineraryText(result, generationContext, committedSwaps);

    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(exportText);
      } else if (!copyTextWithTextareaFallback(exportText)) {
        throw new Error("Clipboard unavailable.");
      }
      setCopyStatus(
        mode === "share"
          ? "分享版已复制，适合发给朋友或小红书草稿。"
          : "实用版已复制，可粘贴到微信、备忘录或聊天里。",
      );
    } catch {
      setCopyStatus("复制失败，请手动重试。");
    }
  }

  function handleGenerateShareCard() {
    if (!result) {
      return;
    }

    try {
      const cardData = buildShareCardData(result, generationContext, committedSwaps, preferenceSignals);
      const imageUrl = renderShareCardToImage(cardData);
      setShareCardImageUrl(imageUrl);
      setShareCardStatus("分享图片已生成，可以预览或下载。");
      setShareFeedbackRating(null);
      setShareFeedbackNote("");
      setShareFeedbackSaved(false);
    } catch {
      setShareCardStatus("生成图片失败，请重试。");
    }
  }

  async function handleCopyShareQuestion() {
    const shareQuestion = "我准备这么走，你帮我看看有没有问题👇";

    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareQuestion);
      } else if (!copyTextWithTextareaFallback(shareQuestion)) {
        throw new Error("Clipboard unavailable.");
      }
      setShareCardStatus("提问文案已复制，可以和图片一起发给朋友。");
    } catch {
      setShareCardStatus("复制提问文案失败，请手动重试。");
    }
  }

  function handleShareFeedbackSelect(rating: ShareCardFeedbackRating) {
    setShareFeedbackRating(rating);
    setShareFeedbackSaved(false);
    if (rating === "会用") {
      saveShareCardFeedback(rating, "");
      setShareFeedbackSaved(true);
    }
  }

  function handleShareFeedbackSubmit() {
    if (!shareFeedbackRating) {
      return;
    }
    saveShareCardFeedback(shareFeedbackRating, shareFeedbackNote);
    setShareFeedbackSaved(true);
  }

  function saveShareCardFeedback(rating: ShareCardFeedbackRating, note: string) {
    if (!result || typeof window === "undefined") {
      return;
    }

    const entry: ShareCardFeedbackEntry = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      created_at: new Date().toISOString(),
      rating,
      note: note.trim(),
      trip_days: result.trip_days,
      pacing: generationContext?.pacing_profile ?? "balanced",
      share_title: buildShareTitle(result, generationContext, committedSwaps),
    };
    const existingRaw = window.localStorage.getItem(SHARE_CARD_FEEDBACK_KEY);
    const existing = existingRaw ? (JSON.parse(existingRaw) as ShareCardFeedbackEntry[]) : [];
    window.localStorage.setItem(
      SHARE_CARD_FEEDBACK_KEY,
      JSON.stringify([...existing, entry].slice(-50)),
    );
  }

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    window.localStorage.removeItem(SAVED_TRIP_SESSION_KEY);
    const persistedRef = parsePersistedTripRef(window.localStorage.getItem(PERSISTED_TRIP_REF_KEY));
    if (!persistedRef) {
      window.localStorage.removeItem(PERSISTED_TRIP_REF_KEY);
      setSessionHydrated(true);
      return;
    }

    setHasSavedSession(true);
    setSavedTripPromptOpen(false);
    void restorePersistedTripRef().finally(() => {
      setSessionHydrated(true);
    });
  }, []);

  useEffect(() => {
    if (!sessionHydrated || typeof window === "undefined") {
      return;
    }

    window.localStorage.removeItem(SAVED_TRIP_SESSION_KEY);
  }, [sessionHydrated]);

  useEffect(() => {
    const envelopeHistory = result?.trip_intent?.completion_candidate_history ?? [];
    const options = result?.completion_recommendation?.options ?? [];
    if (!envelopeHistory.length && !options.length) {
      return;
    }
    setCompletionCandidateHistory((current) => {
      const base = envelopeHistory.length ? envelopeHistory : current;
      return mergeCompletionCandidateHistory(base, options);
    });
  }, [result?.trip_intent?.completion_candidate_history, result?.completion_recommendation]);

  useEffect(() => {
    setShareCardImageUrl(null);
    setShareCardStatus(null);
    setShareFeedbackRating(null);
    setShareFeedbackNote("");
    setShareFeedbackSaved(false);
  }, [result]);

  useEffect(() => {
    if (!result || !shouldRevealResultRef.current || typeof window === "undefined") {
      return;
    }

    const target = resultSectionRef.current;
    if (!target) {
      return;
    }

    shouldRevealResultRef.current = false;
    if (shouldFocusResultRef.current) {
      target.focus({ preventScroll: true });
      shouldFocusResultRef.current = false;
    }
    const revealTimer = window.setTimeout(() => {
      const targetTop = Math.max(0, target.getBoundingClientRect().top + window.scrollY - 20);
      window.scrollTo({
        top: targetTop,
        behavior: "smooth",
      });
    }, 80);

    return () => window.clearTimeout(revealTimer);
  }, [result]);

  useEffect(() => {
    if (!restoreTripTextFocus || tripPersistence.status !== "none") {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      const input = document.getElementById("trip-text") as HTMLTextAreaElement | null;
      input?.focus({ preventScroll: true });
      if (input) {
        const targetTop = Math.max(0, input.getBoundingClientRect().top + window.scrollY - 96);
        window.scrollTo({ top: targetTop, behavior: "smooth" });
      }
      setRestoreTripTextFocus(false);
    });

    return () => window.cancelAnimationFrame(frame);
  }, [restoreTripTextFocus, tripPersistence.status]);

  useEffect(() => {
    if (!copyStatus) {
      return;
    }

    const timer = window.setTimeout(() => {
      setCopyStatus(null);
    }, 2800);

    return () => window.clearTimeout(timer);
  }, [copyStatus]);

  useEffect(() => {
    setUserIntentState((current) => ({
      ...current,
      original_scenic: splitLines(scenicSpots),
      original_restaurants: splitLines(restaurants),
    }));
  }, [scenicSpots, restaurants]);

  function applyStructuredFormSync(sync: TripStructuredFormSync) {
    setScenicSpots(sync.scenicSpots);
    setRestaurants(sync.restaurants);
    setHotel(sync.hotel);
    setArrivalAnchor(sync.arrivalAnchor);
    setDepartureAnchor(sync.departureAnchor);
    setAvailabilityWindowsText(sync.availabilityWindowsText);
    setPreferencesText(sync.preferencesText);
    setTripDays(sync.tripDays);
    setFixedEventsText(sync.fixedEventsText);
  }

  function populateStructuredFormFromParsedIntent(
    intent: ParsedTripIntent,
    planningStateSnapshot?: PlanningInputState | null,
  ) {
    applyStructuredFormSync(
      buildStructuredFormSyncFromParsedIntent(intent, planningStateSnapshot ?? null),
    );
  }

  function syncFormStateWithRegenerationIntent(
    regenerationIntent: RegenerationIntentSummary | null,
  ) {
    if (!regenerationIntent) {
      return;
    }

    const sync = buildStructuredFormSyncFromRegenerationIntent(regenerationIntent);
    applyStructuredFormSync(sync);
    setTravelMode(sync.travelMode);
    setAvailabilityPreview(null);
    setAvailabilityPreviewSignature(null);
    setAvailabilityPreviewError(null);
    setUserIntentState((current) => ({
      ...current,
      original_scenic: sync.originalScenic,
      original_restaurants: sync.originalRestaurants,
    }));
  }

  function formatRegenerationTripDays(regenerationIntent: RegenerationIntentSummary): string {
    if (regenerationIntent.trip_days !== null) {
      return `${regenerationIntent.trip_days} 天（已固定）`;
    }
    return `${regenerationIntent.suggested_trip_days} 天（系统建议）`;
  }

  function formatRegenerationScopeSummary(regenerationIntent: RegenerationIntentSummary): string {
    if (regenerationIntent.trip_days !== null) {
      return `${regenerationIntent.trip_days} 天 · 用户明确给出`;
    }
    return `${regenerationIntent.suggested_trip_days} 天 · 系统按当前计划估算`;
  }

function formatStylePreferenceSourceSummary(sources: Record<string, string>): string {
  const values = Object.values(sources);
  if (values.length === 0) {
    return "暂无偏好信号";
    }
    const explicitCount = values.filter((value) => value === "explicit").length;
    const inferredCount = values.filter((value) => value === "inferred").length;
    return [
      explicitCount > 0 ? `${explicitCount} 个显式` : null,
      inferredCount > 0 ? `${inferredCount} 个行为推断` : null,
    ]
      .filter((value): value is string => value !== null)
      .join(" · ");
  }

function buildPlannerAssumptionDisplayLines(
  assumptions: PlanningAssumptionSummary,
): string[] {
  return [
    ...assumptions.summary_lines,
    ...(assumptions.regeneration_intent?.notes ?? []),
  ].slice(0, 4);
}

function buildPlannerExecutionTraceDisplayLines(
  assumptions: PlanningAssumptionSummary,
): string[] {
  const trace = assumptions.execution_trace ?? [];
  const visibleTrace = assumptions.departure_hub_trace
    ? [formatDepartureHubTrace(assumptions.departure_hub_trace)]
    : [];
  const visibleScheduledTrace = trace.slice(0, 7).map((item) => {
    const sourceLabel = formatExecutionTraceSourceLabel(item.source_type);
    const editability = item.is_hard_constraint
      ? "固定约束"
      : item.is_user_owned
        ? "用户确认，可微调"
        : "可替换";
    const topCandidateLine = formatPlanningTraceCandidates(
      "Top",
      item.evidence.top_candidates ?? [],
    );
    const rejectedCandidateLine = formatPlanningTraceCandidates(
      "Skipped",
      item.evidence.rejected_candidates ?? [],
    );
    return [
      `第 ${item.day} 天 · ${formatBlockTitle(item.block_type)} · ${item.item_name}：${sourceLabel} · ${formatTraceToken(item.timing_role)} · ${editability}。`,
      item.evidence.why_included,
      item.evidence.timing_decision,
      item.evidence.ownership_signal,
      item.evidence.flexibility,
      topCandidateLine,
      rejectedCandidateLine,
    ]
      .filter((line): line is string => Boolean(line))
      .join(" ");
  });
  visibleTrace.push(...visibleScheduledTrace);
  if (trace.length > visibleScheduledTrace.length) {
    visibleTrace.push(`另外还有 ${trace.length - visibleScheduledTrace.length} 条规划取舍已保留在依据里。`);
  }
  return visibleTrace;
}

function formatDepartureHubTrace(trace: DepartureHubDecisionTrace): string {
  const topCandidateLine = formatDepartureHubCandidates("候选枢纽", trace.top_candidates);
  const rejectedCandidateLine = formatDepartureHubCandidates("已排除枢纽", trace.rejected_candidates);
  return [
    `离开交通 · ${trace.selected_hub_name}：${trace.selection_rule}`,
    `最后一天收口区域：${trace.target_summary}。`,
    topCandidateLine,
    rejectedCandidateLine,
  ]
    .filter((line): line is string => Boolean(line))
    .join(" ");
}

function formatDepartureHubCandidates(
  label: string,
  candidates: DepartureHubCandidateTrace[],
): string | null {
  if (candidates.length === 0) {
    return null;
  }
  const preview = candidates
    .slice(0, 3)
    .map((candidate) =>
      `${candidate.rank ? `#${candidate.rank} ` : ""}${candidate.name}（${formatHubCategoryLabel(candidate.category)}${candidate.distance_km !== null ? `，${candidate.distance_km} km` : ""}）`,
    )
    .join(" / ");
  return `${label}：${preview}。`;
}

function formatHubCategoryLabel(category: string): string {
  if (category === "airport") {
    return "机场";
  }
  if (category === "rail") {
    return "车站";
  }
  return category;
}

function formatPlanningTraceCandidates(
  label: string,
  candidates: CompletionCandidateTrace[],
): string | null {
  if (candidates.length === 0) {
    return null;
  }
  const preview = candidates
    .slice(0, 3)
    .map((candidate) =>
      `${candidate.rank ? `#${candidate.rank} ` : ""}${candidate.name}（${formatCandidateStatus(candidate.status)}${candidate.score !== null ? `，匹配 ${candidate.score}` : ""}）`,
    )
    .join(" / ");
  return `${formatTraceCandidateLabel(label)}：${preview}。`;
}

function formatTraceCandidateLabel(label: string): string {
  if (label === "Top") {
    return "优先候选";
  }
  if (label === "Skipped") {
    return "已跳过候选";
  }
  return label;
}

function formatCandidateStatus(status: string): string {
  if (status === "included") {
    return "已采用";
  }
  if (status === "rejected") {
    return "已排除";
  }
  if (status === "candidate") {
    return "候选";
  }
  return status.replaceAll("_", " ");
}

function formatExecutionTraceSourceLabel(sourceType: ScheduledItemSourceType): string {
  if (sourceType === "user_fixed") {
    return "用户固定安排";
  }
  if (sourceType === "user_seed") {
    return "用户给出的地点";
  }
  if (sourceType === "auto_seeded_meal") {
    return "系统补的餐食锚点";
  }
  if (sourceType === "auto_seeded_poi") {
    return "系统补的起步地点";
  }
  if (sourceType === "auto_filled") {
    return "系统补齐的空档";
  }
  return "已排入地点";
}

function formatTraceToken(value: string): string {
  const normalized = value.replaceAll("_", " ");
  const dictionary: Record<string, string> = {
    "opening anchor": "开场锚点",
    "closing anchor": "收口锚点",
    "meal anchor": "餐食锚点",
    flexible: "可调整",
    fixed: "固定",
  };
  return dictionary[normalized] ?? normalized;
}

function buildFollowUpInterpretationDisplayLines(
  interpretation: FollowUpInterpretationSummary,
): string[] {
  return [
    ...interpretation.summary_lines,
    interpretation.added_fixed_events.length > 0
      ? `固定安排：${formatFixedEventSummary(interpretation.added_fixed_events)}`
      : null,
    interpretation.added_availability_windows.length > 0
      ? `可用时间：${formatAvailabilityWindows(interpretation.added_availability_windows)}`
      : null,
  ]
    .filter((line): line is string => Boolean(line))
    .slice(0, 4);
}

function buildFollowUpInterpretationCardViewModel(
  interpretation: FollowUpInterpretationSummary,
): FollowUpInterpretationCardViewModel {
  const removalCount =
    interpretation.removed_scenic_spots.length + interpretation.removed_restaurants.length;
  const additionCount =
    interpretation.added_scenic_spots.length + interpretation.added_restaurants.length;
  return {
    title: "最近这句补充要求改了什么",
    stats: [
      {
        label: "新增地点",
        value: String(additionCount),
      },
      {
        label: "移除地点",
        value: String(removalCount),
      },
      {
        label: "固定安排",
        value: String(interpretation.added_fixed_events.length),
      },
      {
        label: "可用时间",
        value: String(interpretation.added_availability_windows.length),
      },
      {
        label: "行程天数",
        value:
          interpretation.pinned_trip_days !== null
            ? `固定为 ${interpretation.pinned_trip_days} 天`
            : "未变化",
      },
      {
        label: "目的地",
        value: interpretation.destination_changed_to ?? "未变化",
      },
    ],
    strips: [
      {
        title: "用户补充原句",
        content: interpretation.raw_text,
      },
      {
        title: "新增到当前计划的地点",
        content: formatList([
          ...interpretation.added_scenic_spots,
          ...interpretation.added_restaurants,
        ]),
      },
      {
        title: "从当前计划移除",
        content: formatList([
          ...interpretation.removed_scenic_spots,
          ...interpretation.removed_restaurants,
        ]),
      },
      {
        title: "系统如何理解这句话",
        content: formatList(buildFollowUpInterpretationDisplayLines(interpretation)),
      },
    ],
  };
}

function buildBriefPreviewCardViewModel(
  brief: ParsedTripIntent,
  options: {
    isCurrentRegenerateBrief: boolean;
    regenerationIntent: RegenerationIntentSummary | null;
  },
): BriefPreviewCardViewModel {
  return {
    title: options.isCurrentRegenerateBrief ? "当前旅行计划" : "原始解析结果",
    stats: [
      { label: "目的地", value: brief.city ?? "未识别" },
      {
        label: "行程天数",
        value:
          options.isCurrentRegenerateBrief && options.regenerationIntent
            ? formatRegenerationTripDays(options.regenerationIntent)
            : brief.trip_days !== null
              ? String(brief.trip_days)
              : "未识别",
      },
      { label: "住宿", value: brief.hotel ?? "稍后反推" },
      { label: "到达", value: brief.arrival_anchor ?? "未设置" },
      { label: "离开", value: brief.departure_anchor ?? "未设置" },
      {
        label: "可用时间",
        value:
          brief.availability_windows.length > 0
            ? formatAvailabilityWindows(brief.availability_windows)
            : "未设置",
      },
    ],
    strips: [
      {
        title: options.isCurrentRegenerateBrief
          ? "下一次会带入的地点"
          : "解析出的想去地点",
        content: formatList(brief.scenic_spots),
      },
      {
        title: options.isCurrentRegenerateBrief
          ? "下一次会带入的餐食"
          : "解析出的餐食线索",
        content: formatList(brief.restaurants),
      },
      {
        title: "偏好和节奏",
        content: formatList(brief.preferences),
      },
      {
        title: "固定安排",
        content: formatFixedEventSummary(brief.fixed_events),
      },
    ],
  };
}

function buildRegenerationSemanticsViewModel(
  assumptions: PlanningAssumptionSummary,
  regenerationIntent: RegenerationIntentSummary,
): {
  stats: Array<{ label: string; value: string }>;
  strips: Array<{ title: string; content: string }>;
} {
  return {
    stats: [
      {
        label: "行程范围",
        value: formatRegenerationScopeSummary(regenerationIntent),
      },
      {
        label: "可排地点",
        value: String(
          regenerationIntent.carry_forward_scenic_spots.length +
            regenerationIntent.carry_forward_restaurants.length,
        ),
      },
      {
        label: "固定安排",
        value: String(regenerationIntent.fixed_events.length),
      },
      {
        label: "自动起步点",
        value: String(
          assumptions.auto_seeded_poi_count + assumptions.auto_seeded_meal_count,
        ),
      },
      {
        label: "自动补齐",
        value: String(assumptions.auto_filled_count),
      },
      {
        label: "偏好来源",
        value: formatStylePreferenceSourceSummary(
          regenerationIntent.style_preference_sources,
        ),
      },
    ],
    strips: [
      {
        title: "会继续带入的地点",
        content: formatList(regenerationIntent.carry_forward_scenic_spots),
      },
      {
        title: "会继续带入的餐食",
        content: formatList(regenerationIntent.carry_forward_restaurants),
      },
      {
        title: "为什么下一次补全会这样理解",
        content: formatList(assumptions.summary_lines),
      },
      {
        title: "继续补全备注",
        content: formatList(regenerationIntent.notes),
      },
    ],
  };
}

  async function fetchTripParsing(text: string): Promise<{
    intent: ParsedTripIntent;
    planningState: PlanningInputState;
  } | null> {
    const [intentResult, planningStateResult] = await Promise.all([
      postTripJson<ParsedTripIntent>(
        PARSE_API_URL,
        { text },
        "Parse request failed",
      ),
      postTripJson<PlanningInputState>(
        PLANNING_STATE_API_URL,
        { text },
        "Planning state request failed",
      ),
    ]);

    if (!intentResult.ok) {
      setParseError(intentResult.message);
      return null;
    }

    if (!planningStateResult.ok) {
      setParseError(planningStateResult.message);
      return null;
    }

    return {
      intent: intentResult.data,
      planningState: planningStateResult.data,
    };
  }

  async function planTripFromText(text: string): Promise<TripPlanResponse | null> {
    setTripPersistence({ status: "creating" });
    const result = await postTripJson<TripPlanResponse>(
      PLAN_TRIP_API_URL,
      {
        text,
        travel_mode: travelMode ?? undefined,
        auto_fill_sparse_days: true,
        extra_preferences: buildEffectivePreferences([], preferenceSignals, pacingProfile),
      },
      "Natural-language planning failed",
    );
    if (!result.ok) {
      setParseError(result.message);
      setTripPersistence({ status: "error", message: result.message, recoverable: true });
      return null;
    }

    rememberPersistedTrip(result.data.trip, result.data.current_revision);
    await refreshRevisionHistory(result.data.trip.id);
    return result.data;
  }

  async function createDraftTrip(directUserText: string = tripText): Promise<string | null> {
    setTripPersistence({ status: "creating" });
    const idempotencyKey = `draft-trip:${crypto.randomUUID()}`;
    const result = await postTripJson<{ trip: TripMetadata }>(
      TRIP_API_ENDPOINTS.createDraftTrip,
      { direct_user_text: directUserText },
      "创建行程草稿失败",
      undefined,
      { headers: { "X-Idempotency-Key": idempotencyKey } },
    );
    if (!result.ok) {
      setTripPersistence({ status: "error", message: result.message, recoverable: true });
      return null;
    }
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        PERSISTED_TRIP_REF_KEY,
        serializePersistedTripRef(buildPersistedDraftTripRef(result.data.trip.id)),
      );
    }
    setTripPersistence({ status: "draft", tripId: result.data.trip.id });
    return result.data.trip.id;
  }

  function toggleCompletionOption(option: ItineraryCompletionOption) {
    const key = buildCompletionOptionKey(option);
    setSelectedCompletionOptionKeys((current) =>
      current.includes(key) ? current.filter((item) => item !== key) : [...current, key],
    );
  }

  function applySelectedCompletionOptions() {
    if (!result?.completion_recommendation) {
      return;
    }

    const selectedOptions = result.completion_recommendation.options.filter((option) =>
      selectedCompletionOptionKeys.includes(buildCompletionOptionKey(option)),
    );
    if (selectedOptions.length === 0) {
      return;
    }

    const currentScenic = splitLines(scenicSpots);
    const currentRestaurants = splitLines(restaurants);
    const nextScenic = [...currentScenic];
    const nextRestaurants = [...currentRestaurants];

    for (const option of selectedOptions) {
      if (option.type === "restaurant") {
        if (!nextRestaurants.includes(option.name)) {
          nextRestaurants.push(option.name);
        }
        continue;
      }

      if (!nextScenic.includes(option.name)) {
        nextScenic.push(option.name);
      }
    }

    setScenicSpots(nextScenic.join("\n"));
    setRestaurants(nextRestaurants.join("\n"));
    setCompletionPickerOpen(false);
    setSelectedCompletionOptionKeys([]);
    setError(null);

    if (typeof window !== "undefined") {
      document.getElementById("scenic-spots")?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }

  async function handleApplySwap(target: SwapTarget, option: ItineraryCompletionOption) {
    setRecentCompletionTaskItemKey(null);
    const committedSelection = buildCommittedSwapSelectionFromOption(target, option);
    if (tripPersistence.status === "saved") {
      const envelope = buildSwapReplaceCommandEnvelope(
        tripPersistence.currentRevisionId,
        target,
        option,
      );
      if (envelope) {
        const applied = await applyPersistedMutationWithPreview(tripPersistence, envelope);
        if (!applied.ok) {
          markPersistedMutationFailure(tripPersistence, applied);
          return;
        }
        await hydrateFromPersistedMutation(
          applied.data.trip,
          applied.data.current_revision,
          applied.data.itinerary,
        );
        setGenerationContext((current) =>
          current ? applySwapToGenerationContext(current, committedSelection) : current,
        );
        setCommittedSwaps((current) => {
          const nextSwaps = upsertCommittedSwap(current, committedSelection);
          setPreferenceSignals(derivePreferenceSignalsFromCommittedSwaps(nextSwaps));
          return nextSwaps;
        });
        setUserIntentState((current) =>
          addRejectedPoiToUserIntentState(
            addConfirmedPoiToUserIntentState(current, option.name, option.type),
            target.name,
            target.type === "restaurant" ? "restaurant" : "scenic",
          ),
        );
        setActiveSwapTarget(null);
        setError(null);
        return;
      }
    }
    setResult((current) => {
      if (!current) {
        return current;
      }
      return applySwapToTripIntentEnvelope(
        applySwapToItinerary(current, target, option),
        committedSelection,
      );
    });
    setGenerationContext((current) =>
      current ? applySwapToGenerationContext(current, committedSelection) : current,
    );
    setCommittedSwaps((current) => {
      const nextSwaps = upsertCommittedSwap(current, committedSelection);
      setPreferenceSignals(derivePreferenceSignalsFromCommittedSwaps(nextSwaps));
      return nextSwaps;
    });
    setUserIntentState((current) =>
      addRejectedPoiToUserIntentState(
        addConfirmedPoiToUserIntentState(current, option.name, option.type),
        target.name,
        target.type === "restaurant" ? "restaurant" : "scenic",
      ),
    );
    setActiveSwapTarget(null);
    setError(null);
    markWorkspaceDirty("swap_apply");
  }

  function handleUndoSwap(target: SwapTarget) {
    setRecentCompletionTaskItemKey(null);
    const targetKey = buildSwapTargetKey(target);
    const undoneSwap = committedSwaps.find((swap) => swap.target_key === targetKey) ?? null;
    setCommittedSwaps((current) => {
      const nextSwaps = current.filter((swap) => swap.target_key !== targetKey);
      setUserIntentState((intentState) => syncConfirmedPoisWithCommittedSwaps(intentState, nextSwaps));
      setPreferenceSignals(derivePreferenceSignalsFromCommittedSwaps(nextSwaps));
      return nextSwaps;
    });
    setResult((current) => {
      if (!current) {
        return current;
      }
      const nextItinerary = undoSwapInItinerary(current, target);
      return undoneSwap
        ? undoSwapFromTripIntentEnvelope(nextItinerary, undoneSwap)
        : nextItinerary;
    });
    if (undoneSwap) {
      setGenerationContext((current) =>
        current ? undoSwapFromGenerationContext(current, undoneSwap) : current,
      );
    }
    setActiveSwapTarget(null);
    setError(null);
    markWorkspaceDirty("swap_undo");
  }

  async function handleCommitRouteEdits(
    editedDays: EditableRouteDay[],
    routePreviewMap?: Record<string, { distance_m: number; duration_s: number }>,
    unplannedStops: EditableRouteDay["stops"] = [],
  ) {
    if (!result || !hasEditedRouteChanges(editedDays, unplannedStops)) {
      setError(null);
      return;
    }
    const editedPois = buildRouteEditPoiLists(editedDays, unplannedStops);

    if (tripPersistence.status === "saved") {
      const envelope = buildRouteEditCommandEnvelope(
        result,
        tripPersistence.currentRevisionId,
        editedDays,
        unplannedStops,
      );
      if (envelope) {
        const applied = await applyPersistedMutationWithPreview(tripPersistence, envelope);
        if (!applied.ok) {
          markPersistedMutationFailure(tripPersistence, applied);
          return;
        }
        await hydrateFromPersistedMutation(
          applied.data.trip,
          applied.data.current_revision,
          applied.data.itinerary,
        );
        setScenicSpots(editedPois.scenic.join("\n"));
        setRestaurants(editedPois.restaurants.join("\n"));
        setError(null);
        return;
      }
      const manualStops = [
        ...editedDays.flatMap((day) =>
          day.stops.filter((stop) => !stop.item.stable_id || stop.originalDay < 1),
        ),
        ...unplannedStops,
      ];
      if (manualStops.length > 0) {
        for (const stop of manualStops) {
          await registerManualCandidate(
            stop.item.name,
            stop.item.type === "restaurant" ? "restaurant" : "scenic",
          );
        }
        setCompletionTaskStatus(
          `已保存 ${manualStops.length} 个待安排候选；它们还没有进入正式行程，加入前需要通过候选验证。`,
        );
        setError(null);
        return;
      }
    }

    setResult((current) => {
      if (!current) {
        return current;
      }
      return applyRouteEditsToTripIntentEnvelope(
        applyRouteEditsToItinerary(current, editedDays, routePreviewMap ?? {}),
        editedDays,
        unplannedStops,
      );
    });
    setGenerationContext((current) =>
      current ? applyRouteEditsToGenerationContext(current, editedDays, unplannedStops) : current,
    );
    setScenicSpots(editedPois.scenic.join("\n"));
    setRestaurants(editedPois.restaurants.join("\n"));
    setUserIntentState((current) => ({
      ...current,
      original_scenic: editedPois.scenic,
      original_restaurants: editedPois.restaurants,
      confirmed_scenic: current.confirmed_scenic.filter((name) =>
        editedPois.scenic.some((poi) => normalizeComparisonName(poi) === normalizeComparisonName(name)),
      ),
      confirmed_restaurants: current.confirmed_restaurants.filter((name) =>
        editedPois.restaurants.some((poi) => normalizeComparisonName(poi) === normalizeComparisonName(name)),
      ),
      rejected_scenic: current.rejected_scenic.filter(
        (name) => !editedPois.scenic.some((poi) => normalizeComparisonName(poi) === normalizeComparisonName(name)),
      ),
      rejected_restaurants: current.rejected_restaurants.filter(
        (name) =>
          !editedPois.restaurants.some((poi) => normalizeComparisonName(poi) === normalizeComparisonName(name)),
      ),
    }));
    setError(null);
    markWorkspaceDirty("route_edit_commit");
  }

  async function handleParseSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setParsing(true);
    setParseError(null);
    setParsedIntent(null);
    setPlanningState(null);

    try {
      const parsed = await fetchTripParsing(tripText);
      if (!parsed) {
        return;
      }

      setParsedIntent(parsed.intent);
      setPlanningState(parsed.planningState);
      setQuickPreviewMode("original_parse");
    } catch {
      setParseError("无法连接意图解析接口。");
    } finally {
      setParsing(false);
    }
  }

  async function generateItineraryFromValues(values: {
    cityName: string | null;
    scenicSpotNames: string[];
    restaurantNames: string[];
    fixedEvents: ParsedFixedEvent[];
    availabilityWindows: AvailabilityWindow[];
    preferences: string[];
    hotelName: string;
    arrivalAnchorName: string;
    departureAnchorName: string;
    tripDayCount: number | undefined;
    tripDaysSource: TripDaysSource;
    tripScopeEstimate: TripScopeEstimate | null;
    travelModeValue: TravelMode | null;
  }) {
    const { payload, generationContextSnapshot } = buildGenerateItineraryPayload({
      values,
      userIntentState,
      committedSwaps,
      preferenceSignals,
      pacingProfile,
    });

    setTripPersistence({ status: "creating" });
    const result = await postTripJson<TripPlanResponse>(
      PLAN_TRIP_API_URL,
      {
        itinerary_request: payload,
        auto_fill_sparse_days: true,
      },
      "Request failed",
    );
    if (!result.ok) {
      setError(result.message);
      setTripPersistence({ status: "error", message: result.message, recoverable: true });
      return;
    }

    const itinerary = result.data.itinerary;
    const regenerationIntent =
      itinerary.trip_intent?.current_intent ??
      itinerary.planning_assumptions?.regeneration_intent ??
      null;
    setResult(itinerary);
    setRecentCompletionTaskItemKey(null);
    setCompletionTaskEdits([]);
    setCompletionCandidateHistory([]);
    setGenerationContext(
      regenerationIntent
        ? buildGenerationContextFromRegenerationIntent(regenerationIntent)
        : generationContextSnapshot as GenerationContext,
    );
    setDismissedFollowUpRawText(null);
    setLatestFollowUpBaseIntent(null);
    syncFormStateWithRegenerationIntent(regenerationIntent);
    setQuickPreviewMode(regenerationIntent ? "current_brief" : "original_parse");
    setCompletionPickerOpen(false);
    setSelectedCompletionOptionKeys([]);
    rememberPersistedTrip(result.data.trip, result.data.current_revision);
    await refreshRevisionHistory(result.data.trip.id);
  }

  async function generateItineraryFromTripIntent(tripIntent: TripIntentEnvelope) {
    const tripDaysOverride = tripDays.trim() ? Number(tripDays.trim()) : undefined;
    const intentPatch = buildTripIntentPatchFromCurrentState({
      tripIntent,
      userIntentState,
      scenicSpots,
      restaurants,
      hotel,
      arrivalAnchor,
      departureAnchor,
      availabilityWindowsText,
      preferencesText,
      tripDays,
      fixedEventsText,
      travelMode,
      committedSwaps,
      preferenceSignals,
      pacingProfile,
      splitLines,
      parseFixedEventLines,
      parseAvailabilityWindowLines,
    });
    const result = await postTripJson<GenerateFromTripIntentResponse>(
      GENERATE_FROM_TRIP_INTENT_API_URL,
      {
        trip_intent: withCompletionCandidateHistory(
          tripIntent,
          completionCandidateHistory,
        ),
        intent_patch: intentPatch,
        auto_fill_sparse_days: true,
        trip_days_override: tripDaysOverride,
        extra_preferences: buildEffectivePreferences([], preferenceSignals, pacingProfile),
      },
      "按当前旅行意图重新补全失败",
    );
    if (!result.ok) {
      setError(result.message);
      return;
    }

    const regenerateResult = result.data;
    const itinerary = regenerateResult.itinerary;
    const regenerationIntent =
      regenerateResult.trip_intent.current_intent ??
      itinerary.trip_intent?.current_intent ??
      itinerary.planning_assumptions?.regeneration_intent ??
      null;

    setResult(itinerary);
    setRecentCompletionTaskItemKey(null);
    setCompletionTaskEdits([]);
    setCompletionCandidateHistory(regenerateResult.trip_intent.completion_candidate_history ?? []);
    if (regenerationIntent) {
      setGenerationContext(buildGenerationContextFromRegenerationIntent(regenerationIntent));
      syncFormStateWithRegenerationIntent(regenerationIntent);
      setUserIntentState((current) => ({
        ...current,
        original_scenic: regenerationIntent.flexible_scenic_spots,
        original_restaurants: regenerationIntent.flexible_restaurants,
        rejected_scenic: uniquePreserveOrder([
          ...current.rejected_scenic,
          ...regenerationIntent.rejected_scenic_spots,
        ]),
        rejected_restaurants: uniquePreserveOrder([
          ...current.rejected_restaurants,
          ...regenerationIntent.rejected_restaurants,
        ]),
      }));
    }
    setDismissedFollowUpRawText(null);
    setLatestFollowUpBaseIntent(null);
    setQuickPreviewMode(regenerationIntent ? "current_brief" : "original_parse");
    setCompletionPickerOpen(false);
    setSelectedCompletionOptionKeys([]);
    markWorkspaceDirty("generate_from_trip_intent");
  }

  function buildGenerationContextFromRegenerationIntent(
    regenerationIntent: RegenerationIntentSummary,
  ): GenerationContext {
    return {
      city: regenerationIntent.city,
      scenic_spots: regenerationIntent.flexible_scenic_spots,
      restaurants: regenerationIntent.flexible_restaurants,
      fixed_events: regenerationIntent.fixed_events,
      preferences: regenerationIntent.preferences,
      pacing_profile: pacingProfile,
      trip_days_source:
        regenerationIntent.trip_days !== null
          ? "explicit"
          : regenerationIntent.trip_days_basis === "scheduler_estimated"
            ? "scheduler_estimated"
            : regenerationIntent.trip_days_basis === "interaction_estimated"
              ? "interaction_estimated"
              : "estimated",
      trip_scope_estimate: generationContext?.trip_scope_estimate ?? null,
      hotel: regenerationIntent.hotel,
      arrival_anchor: regenerationIntent.arrival_anchor,
      departure_anchor: regenerationIntent.departure_anchor,
      availability_windows: regenerationIntent.availability_windows,
    };
  }

  function buildGenerationContextFromPlanTextResponse(
    response: PlanTripFromTextResponse | TripPlanResponse,
  ): GenerationContext {
    const regenerationIntent =
      response.trip_intent?.current_intent ??
      response.itinerary.trip_intent?.current_intent ??
      response.itinerary.planning_assumptions?.regeneration_intent ??
      null;
    if (!regenerationIntent || !response.parsed_intent || !response.planning_state) {
      return {
        city: null,
        scenic_spots: [],
        restaurants: [],
        fixed_events: [],
        preferences: [],
        pacing_profile: pacingProfile,
        trip_days_source: "estimated",
        trip_scope_estimate: null,
        hotel: null,
        arrival_anchor: null,
        departure_anchor: null,
        availability_windows: [],
      };
    }
    const tripDaysBasis = regenerationIntent?.trip_days_basis;

    return {
      city: regenerationIntent.city ?? response.parsed_intent.city,
      scenic_spots: regenerationIntent.flexible_scenic_spots,
      restaurants: regenerationIntent.flexible_restaurants,
      fixed_events: regenerationIntent.fixed_events,
      preferences: regenerationIntent.preferences,
      pacing_profile: pacingProfile,
      trip_days_source:
        response.parsed_intent.trip_days !== null
          ? "explicit"
          : tripDaysBasis === "interaction_estimated"
            ? "interaction_estimated"
            : tripDaysBasis === "scheduler_estimated"
              ? "scheduler_estimated"
              : "estimated",
      trip_scope_estimate:
        response.itinerary.planning_assumptions?.trip_scope_estimate ??
        response.planning_state.trip_scope_estimate,
      hotel: regenerationIntent.hotel ?? response.parsed_intent.hotel,
      arrival_anchor: regenerationIntent.arrival_anchor ?? response.parsed_intent.arrival_anchor,
      departure_anchor:
        regenerationIntent.departure_anchor ?? response.parsed_intent.departure_anchor,
      availability_windows:
        regenerationIntent.availability_windows ?? response.parsed_intent.availability_windows,
    };
  }

  async function runFollowUpReplan(rawFollowUpText: string): Promise<{
    itinerary: ItineraryResponse;
    persistedRevisionId?: string;
    persistedBaseRevisionId?: string;
  } | null | undefined> {
    if (!activeRegenerationIntent) {
      setError("当前旅行计划缺失，暂时不能按补充要求继续补全。");
      return;
    }

    const trimmedFollowUpText = rawFollowUpText.trim();
    if (!trimmedFollowUpText) {
      setError("用一句话告诉我你想怎么调整这趟行程。");
      return;
    }

    setReplanning(true);
    setError(null);
    setActiveSwapTarget(null);

    try {
      const currentBaseIntent = activeRegenerationIntent;
      const persistedBase = tripPersistence.status === "saved" ? tripPersistence : null;
      const result = persistedBase
        ? await applyPersistedReplanWithPreview(persistedBase, trimmedFollowUpText)
        : await postTripJson<ReplanItineraryResponse>(
            REPLAN_API_URL,
            {
              trip_intent: activeTripIntent
                ? withCompletionCandidateHistory(activeTripIntent, completionCandidateHistory)
                : undefined,
              base_intent: currentBaseIntent,
              follow_up_text: trimmedFollowUpText,
              auto_fill_sparse_days: true,
            },
            "按补充要求继续补全失败",
            "无法连接后端接口继续补全这趟旅行。",
      );
      if (!result.ok) {
        if (
          persistedBase &&
          (result.code === "stale_base_revision" || result.code === "stale_mutation_proposal")
        ) {
          setTripPersistence({
            status: "conflict",
            tripId: persistedBase.tripId,
            providedBaseRevisionId: persistedBase.currentRevisionId,
            currentRevisionId: persistedBase.currentRevisionId,
            message: result.message,
          });
        }
        setError(result.message);
        return;
      }

      const replanResult = "replan_result" in result.data ? result.data.replan_result : result.data;
      const itinerary = replanResult.itinerary;
      const regenerationIntent =
        replanResult.trip_intent.current_intent ??
        itinerary.trip_intent?.current_intent ??
        itinerary.planning_assumptions?.regeneration_intent ??
        null;
      if ("current_revision" in result.data) {
        rememberPersistedTrip(result.data.trip, result.data.current_revision);
        await refreshRevisionHistory(result.data.trip.id);
      }

      setDismissedFollowUpRawText(null);
      setLatestFollowUpBaseIntent(currentBaseIntent);
      setResult(itinerary);
      setRecentCompletionTaskItemKey(null);
      setCompletionTaskEdits([]);
      setCompletionCandidateHistory(replanResult.trip_intent.completion_candidate_history ?? []);
      if (regenerationIntent) {
        setGenerationContext(buildGenerationContextFromRegenerationIntent(regenerationIntent));
        syncFormStateWithRegenerationIntent(regenerationIntent);
        setUserIntentState((current) => ({
          ...current,
          original_scenic: regenerationIntent.flexible_scenic_spots,
          original_restaurants: regenerationIntent.flexible_restaurants,
          confirmed_scenic: current.confirmed_scenic.filter((name) =>
            regenerationIntent.carry_forward_scenic_spots.some(
              (candidate) => normalizeComparisonName(candidate) === normalizeComparisonName(name),
            ),
          ),
          confirmed_restaurants: current.confirmed_restaurants.filter((name) =>
            regenerationIntent.carry_forward_restaurants.some(
              (candidate) => normalizeComparisonName(candidate) === normalizeComparisonName(name),
            ),
          ),
        }));
      }
      setCommittedSwaps([]);
      setQuickPreviewMode(regenerationIntent ? "current_brief" : "original_parse");
      setFollowUpText("");
      if (!("current_revision" in result.data)) {
        markWorkspaceDirty("backend_replan");
      }
      return {
        itinerary,
        persistedRevisionId: "current_revision" in result.data ? result.data.current_revision.id : undefined,
        persistedBaseRevisionId: persistedBase?.currentRevisionId,
      };
    } catch {
      setError("无法连接后端接口继续补全这趟旅行。");
      return null;
    } finally {
      setReplanning(false);
    }
  }

  async function applyPersistedReplanWithPreview(
    persistedBase: Extract<TripPersistenceState, { status: "saved" }>,
    followUpText: string,
  ): Promise<TripApiResult<PersistedReplanResponse>> {
    setPersistedReplanProposal({
      status: "previewing",
      baseRevisionId: persistedBase.currentRevisionId,
    });
    const preview = await postTripJson<PersistedReplanPreviewResponse>(
      TRIP_API_ENDPOINTS.previewPersistedReplan(persistedBase.tripId),
      {
        base_revision_id: persistedBase.currentRevisionId,
        follow_up_text: followUpText,
        auto_fill_sparse_days: true,
      },
      "预览补充调整失败",
      "无法连接后端接口预览这次调整。",
    );
    if (!preview.ok) {
      setPersistedReplanProposal({
        status: preview.code === "stale_mutation_proposal" ? "stale" : "error",
        message: preview.message,
      });
      return preview;
    }
    setPersistedReplanProposal({
      status: "applying",
      proposalId: preview.data.proposal.id,
      baseRevisionId: persistedBase.currentRevisionId,
      proposalDigest: preview.data.proposal.proposal_digest,
      expiresAt: preview.data.proposal.expires_at,
    });
    return postTripJson<PersistedReplanResponse>(
      TRIP_API_ENDPOINTS.applyPersistedReplanProposal(
        persistedBase.tripId,
        preview.data.proposal.id,
      ),
      {
        base_revision_id: persistedBase.currentRevisionId,
        proposal_digest: preview.data.proposal.proposal_digest,
      },
      "按补充要求继续补全失败",
      "无法连接后端接口继续补全这趟旅行。",
      {
        headers: {
          "X-Idempotency-Key": buildReplanProposalIdempotencyKey(
            preview.data.proposal.id,
            preview.data.proposal.proposal_digest,
          ),
        },
      },
    ).then((apply) => {
      if (apply.ok) {
        setPersistedReplanProposal({ status: "idle" });
      } else {
        setPersistedReplanProposal({
          status:
            apply.code === "mutation_proposal_expired"
              ? "expired"
              : apply.code === "stale_mutation_proposal"
                ? "stale"
                : "error",
          message: apply.message,
        });
      }
      return apply;
    });
  }

  async function applyPersistedMutationWithPreview(
    persistedBase: Extract<TripPersistenceState, { status: "saved" }>,
    envelope: TripMutationCommandEnvelope | CandidateAdmissionCommandEnvelope,
  ): Promise<TripApiResult<PersistedMutationApplyResponse>> {
    const preview = await postTripJson<PersistedMutationPreviewResponse>(
      TRIP_API_ENDPOINTS.previewPersistedMutation(persistedBase.tripId),
      envelope,
      "预览这次行程调整失败",
      "无法连接后端接口预览这次行程调整。",
    );
    if (!preview.ok) {
      return preview;
    }
    return postTripJson<PersistedMutationApplyResponse>(
      TRIP_API_ENDPOINTS.applyPersistedMutationProposal(
        persistedBase.tripId,
        preview.data.proposal.id,
      ),
      {
        base_revision_id: persistedBase.currentRevisionId,
        proposal_digest: preview.data.proposal.proposal_digest,
      },
      "保存这次行程调整失败",
      "无法连接后端接口保存这次行程调整。",
      {
        headers: {
          "X-Idempotency-Key": buildMutationProposalIdempotencyKey(
            preview.data.proposal.id,
            preview.data.proposal.proposal_digest,
          ),
        },
      },
    );
  }

  function markPersistedMutationFailure(
    persistedBase: Extract<TripPersistenceState, { status: "saved" }>,
    failure: Extract<TripApiResult<unknown>, { ok: false }>,
  ) {
    setError(failure.message);
    if (failure.code === "stale_mutation_proposal" || failure.code === "stale_base_revision") {
      setTripPersistence({
        status: "conflict",
        tripId: persistedBase.tripId,
        providedBaseRevisionId:
          String(failure.context?.provided_base_revision_id ?? persistedBase.currentRevisionId),
        currentRevisionId:
          String(failure.context?.current_revision_id ?? persistedBase.currentRevisionId),
        message: failure.message,
      });
      return;
    }
    setTripPersistence({
      status: "error",
      message: failure.message,
      tripId: persistedBase.tripId,
      recoverable: failure.recoverable,
    });
  }

  async function handleFollowUpReplan() {
    setLatestDirectOptimizationComparison(null);
    scheduleResultReveal();
    await runFollowUpReplan(followUpText);
  }

  async function handleConversationalReplanExecute(
    plan: ReplanMutationPlan,
    rawText: string,
  ): Promise<ReplanExecutionResult<ItineraryResponse>> {
    if (!result) {
      return {
        ok: false,
        message: "当前没有可调整的行程结果。",
      };
    }

    if (plan.executionMode === "backend_replan") {
      const beforeItinerary = result;
      setLatestDirectOptimizationComparison(null);
      scheduleResultReveal();
      const replanOutcome = await runFollowUpReplan(rawText);
      if (!replanOutcome) {
        return {
          ok: false,
          message: "后端 follow-up replan 未返回新行程。",
        };
      }
      return {
        ok: true,
        beforeItinerary,
        afterItinerary: replanOutcome.itinerary,
        message: "已通过后端 follow-up replan 生成新版行程。",
        usedBackend: true,
        persistedRevisionId: replanOutcome.persistedRevisionId,
        persistedBaseRevisionId: replanOutcome.persistedBaseRevisionId,
      };
    }

    if (plan.executionMode !== "local_mutation") {
      return {
        ok: false,
        message: "这次调整还没有可安全执行的 mutation plan。",
      };
    }

    const beforeItinerary = result;
    const locallyMutatedItinerary = applyReplanMutationPlanToItinerary(beforeItinerary, plan);
    setResult(locallyMutatedItinerary);
    syncLocalReplanIntentState(locallyMutatedItinerary);
    setError(null);
    setActiveSwapTarget(null);
    setRecentCompletionTaskItemKey(null);
    setCompletionTaskEdits([]);
    setCommittedSwaps([]);
    markWorkspaceDirty("local_replan_mutation");

    const refreshedResult = await postTripJson<ItineraryResponse>(
      REFRESH_ITINERARY_SURFACES_API_URL,
      {
        itinerary: locallyMutatedItinerary,
        completion_candidate_history: completionCandidateHistory,
      },
      "刷新调整后的解释和补全评分失败",
      "已完成本地调整，但暂时无法刷新解释和补全评分。",
    );

    const afterItinerary = refreshedResult.ok ? refreshedResult.data : locallyMutatedItinerary;
    setResult(afterItinerary);
    setCompletionCandidateHistory(
      afterItinerary.trip_intent?.completion_candidate_history ?? completionCandidateHistory,
    );
    syncLocalReplanIntentState(afterItinerary);
    if (!refreshedResult.ok) {
      setError(refreshedResult.message);
    }

    return {
      ok: true,
      beforeItinerary,
      afterItinerary,
      message: refreshedResult.ok
        ? "已执行本地 mutation，并刷新解释/补全表面。"
        : "已执行本地 mutation；解释和补全表面将在下次生成后刷新。",
      usedBackend: false,
    };
  }

  function handleUndoConversationalReplan(entry: ReplanHistoryEntry<ItineraryResponse>) {
    if (
      entry.persistedRevisionId &&
      tripPersistence.status === "saved" &&
      tripPersistence.currentRevisionId === entry.persistedRevisionId
    ) {
      void undoPersistedReplanRevision(entry, tripPersistence);
      return;
    }
    setResult(entry.beforeItinerary);
    syncLocalReplanIntentState(entry.beforeItinerary);
    setError(null);
    markWorkspaceDirty("replan_undo");
  }

  async function undoPersistedReplanRevision(
    entry: ReplanHistoryEntry<ItineraryResponse>,
    persistedBase: Extract<TripPersistenceState, { status: "saved" }>,
  ) {
    setReplanning(true);
    setError(null);
    try {
      const response = await postTripJson<UndoPersistedMutationResponse>(
        TRIP_API_ENDPOINTS.undoPersistedRevision(persistedBase.tripId, entry.persistedRevisionId ?? ""),
        {
          base_revision_id: persistedBase.currentRevisionId,
        },
        "撤销调整失败",
        "无法连接后端接口撤销这次调整。",
        {
          headers: {
            "X-Idempotency-Key": `undo-replan:${entry.persistedRevisionId}:${persistedBase.currentRevisionId}`,
          },
        },
      );
      if (!response.ok) {
        if (
          response.code === "stale_base_revision" ||
          response.code === "undo_target_not_current"
        ) {
          setTripPersistence({
            status: "conflict",
            tripId: persistedBase.tripId,
            providedBaseRevisionId: persistedBase.currentRevisionId,
            currentRevisionId: persistedBase.currentRevisionId,
            message: response.message,
          });
        }
        setError(response.message);
        return;
      }
      rememberPersistedTrip(response.data.trip, response.data.current_revision);
      await refreshRevisionHistory(response.data.trip.id);
      setResult(response.data.itinerary);
      syncLocalReplanIntentState(response.data.itinerary);
      setError(null);
    } finally {
      setReplanning(false);
    }
  }

  function syncLocalReplanIntentState(itinerary: ItineraryResponse) {
    const regenerationIntent =
      itinerary.trip_intent?.current_intent ??
      itinerary.planning_assumptions?.regeneration_intent ??
      null;
    if (!regenerationIntent) {
      return;
    }
    setGenerationContext(buildGenerationContextFromRegenerationIntent(regenerationIntent));
    syncFormStateWithRegenerationIntent(regenerationIntent);
    setUserIntentState((current) => ({
      ...current,
      original_scenic: regenerationIntent.flexible_scenic_spots,
      original_restaurants: regenerationIntent.flexible_restaurants,
      confirmed_scenic: current.confirmed_scenic.filter((name) =>
        regenerationIntent.carry_forward_scenic_spots.some(
          (candidate) => normalizeComparisonName(candidate) === normalizeComparisonName(name),
        ),
      ),
      confirmed_restaurants: current.confirmed_restaurants.filter((name) =>
        regenerationIntent.carry_forward_restaurants.some(
          (candidate) => normalizeComparisonName(candidate) === normalizeComparisonName(name),
        ),
      ),
    }));
  }

  function handleEditLatestFollowUp() {
    if (!activeFollowUpInterpretation?.raw_text) {
      return;
    }

    setDismissedFollowUpRawText(null);
    setFollowUpText(activeFollowUpInterpretation.raw_text);

    if (typeof window !== "undefined") {
      window.requestAnimationFrame(() => {
        const input = document.getElementById("constraint-replan-textarea") as
          | HTMLTextAreaElement
          | null;
        input?.scrollIntoView({ behavior: "smooth", block: "center" });
        input?.focus();
        input?.setSelectionRange(input.value.length, input.value.length);
      });
    }
  }

  function handleUseCompletionImprovementPrompt(prompt: string) {
    setDismissedFollowUpRawText(null);
    setFollowUpText((current) => {
      const trimmed = current.trim();
      return trimmed ? `${trimmed}\n${prompt}` : prompt;
    });
    setError(null);

    if (typeof window !== "undefined") {
      window.requestAnimationFrame(() => {
        const input = document.getElementById("follow-up-replan-textarea") as
          | HTMLTextAreaElement
          | null;
        input?.scrollIntoView({ behavior: "smooth", block: "center" });
        input?.focus();
      });
    }
  }

  async function handleApplyCompletionImprovement(prompt: string) {
    const before = result?.completion_intelligence ?? null;
    setRecentCompletionTaskItemKey(null);
    setDismissedFollowUpRawText(null);
    setFollowUpText(prompt);
    scheduleResultReveal();
    const replanOutcome = await runFollowUpReplan(prompt);
    setLatestDirectOptimizationComparison(
      buildDirectOptimizationComparison(
        before,
        replanOutcome?.itinerary.completion_intelligence ?? null,
      ),
    );
  }

  async function handlePreviewCompletionTaskCandidates(task: CompletionTaskCard) {
    if (!result) {
      setError("当前还没有可补全的旅行骨架。");
      return;
    }

    const taskAction = buildCompletionTaskActionRequest(task);
    if (!taskAction) {
      handleUseCompletionImprovementPrompt(task.action_prompt);
      return;
    }

    setPreviewingCompletionTaskId(taskAction.task_instance_key);
    setCompletionTaskStatus(null);
    setError(null);
    try {
      const apiResult = await postTripJson<CompletionTaskCandidatePreviewResponse>(
        PREVIEW_COMPLETION_TASK_CANDIDATES_API_URL,
        {
          itinerary: result,
          task_id: taskAction.task_id,
          task_instance_key: taskAction.task_instance_key,
          day: taskAction.day,
          block_type: taskAction.block_type,
          completion_candidate_history: completionCandidateHistory,
        },
        "获取补全候选失败",
        "无法连接后端接口获取补全候选。",
      );

      if (!apiResult.ok) {
        setError(apiResult.message);
        return;
      }

      const preview = apiResult.data;
      setCompletionTaskCandidatePreviews((current) => ({
        ...current,
        [taskAction.task_instance_key]: preview,
      }));
      setCompletionCandidateHistory((current) =>
        mergeCompletionCandidateHistory(current, preview.options),
      );
    } catch {
      setError("无法连接后端接口获取补全候选。");
    } finally {
      setPreviewingCompletionTaskId(null);
    }
  }

  async function handleApplyCompletionTask(
    task: CompletionTaskCard,
    selectedCandidate?: ItineraryCompletionOption,
  ) {
    if (!result) {
      setError("当前还没有可补全的旅行骨架。");
      return;
    }

    const taskAction = buildCompletionTaskActionRequest(task);
    if (!taskAction) {
      await handleApplyCompletionImprovement(task.action_prompt);
      return;
    }

    const before = result.completion_intelligence ?? null;
    setApplyingCompletionTaskId(taskAction.task_instance_key);
    setCompletionTaskStatus(null);
    setError(null);
    setActiveSwapTarget(null);

    try {
      const idempotencyKey = `completion-task:${taskAction.task_instance_key}`;
      const persistedBase = tripPersistence.status === "saved" ? tripPersistence : null;
      const apiResult = persistedBase
        ? await postTripJson<PersistedCompletionTaskActionResponse>(
            TRIP_API_ENDPOINTS.applyPersistedCompletionTask(persistedBase.tripId),
            {
              base_revision_id: persistedBase.currentRevisionId,
              task_id: taskAction.task_id,
              task_instance_key: taskAction.task_instance_key,
              day: taskAction.day,
              block_type: taskAction.block_type,
              selected_candidate: selectedCandidate,
              completion_candidate_history: completionCandidateHistory,
            },
            "应用补全任务失败",
            undefined,
            {
              headers: {
                "X-Idempotency-Key": idempotencyKey,
              },
            },
          )
        : await postTripJson<CompletionTaskActionResponse>(
            APPLY_COMPLETION_TASK_API_URL,
            {
              itinerary: result,
              task_id: taskAction.task_id,
              task_instance_key: taskAction.task_instance_key,
              day: taskAction.day,
              block_type: taskAction.block_type,
              selected_candidate: selectedCandidate,
              completion_candidate_history: completionCandidateHistory,
            },
            "应用补全任务失败",
            undefined,
            {
              headers: {
                "X-Idempotency-Key": idempotencyKey,
              },
            },
          );

      if (!apiResult.ok) {
        if (apiResult.message.includes("stale_base_revision") && persistedBase) {
          setTripPersistence({
            status: "conflict",
            tripId: persistedBase.tripId,
            providedBaseRevisionId: persistedBase.currentRevisionId,
            currentRevisionId: persistedBase.currentRevisionId,
            message: apiResult.message,
          });
        }
        setError(apiResult.message);
        return;
      }

      const taskResult =
        "task_result" in apiResult.data ? apiResult.data.task_result : apiResult.data;
      if ("current_revision" in apiResult.data) {
        rememberPersistedTrip(apiResult.data.trip, apiResult.data.current_revision);
        await refreshRevisionHistory(apiResult.data.trip.id);
      }
      const promotedItinerary =
        taskResult.applied && taskResult.inserted_item
          ? applyCompletionTaskItemToTripIntentEnvelope(
              taskResult.itinerary,
              taskResult.inserted_item,
            )
          : taskResult.itinerary;
      setResult(promotedItinerary);
      setRecentCompletionTaskItemKey(
        taskResult.applied && taskResult.inserted_item
          ? buildRecentCompletionTaskItemKey(taskResult.inserted_item)
          : null,
      );
      if (taskResult.applied && taskResult.inserted_item) {
        const insertedItem = taskResult.inserted_item;
        const insertedPoiType = getIntentPoiTypeFromScheduledItem(insertedItem);
        setCompletionTaskEdits((current) =>
          upsertCompletionTaskEdit(
            current,
            buildCompletionTaskEditFromResult(
              task,
              insertedItem,
              taskResult.summary,
            ),
          ),
        );
        setCompletionCandidateHistory((current) =>
          removeCompletionCandidateHistoryForItem(current, insertedItem),
        );
        setCompletionTaskCandidatePreviews((current) => {
          const next = { ...current };
          delete next[taskAction.task_instance_key];
          return next;
        });
        if (insertedPoiType) {
          setUserIntentState((current) =>
            addConfirmedPoiToUserIntentState(
              current,
              insertedItem.name,
              insertedPoiType,
            ),
          );
        }
        setGenerationContext((current) =>
          current
            ? applyCompletionTaskItemToGenerationContext(current, insertedItem)
            : current,
        );
      }
      setLatestDirectOptimizationComparison(
        buildDirectOptimizationComparison(before, promotedItinerary.completion_intelligence ?? null),
      );
      setCompletionTaskStatus(
        taskResult.applied
          ? `已补入并加入当前旅行计划：${taskResult.inserted_item?.name ?? taskResult.summary}`
          : taskResult.summary,
      );
    } catch {
      setError("无法连接后端接口应用这个补全任务。");
    } finally {
      setApplyingCompletionTaskId(null);
    }
  }

  async function handleRejectCompletionTaskCandidate(
    task: CompletionTaskCard,
    option: ItineraryCompletionOption,
  ) {
    const taskInstanceKey = getCompletionTaskInstanceKey(task);
    const poiType = option.type === "restaurant" ? "restaurant" : "scenic";
    const optionKey = completionOptionKey(option);

    setUserIntentState((current) =>
      addRejectedPoiToUserIntentState(current, option.name, poiType),
    );
    setCompletionCandidateHistory((current) =>
      current.filter((candidate) => completionOptionKey(candidate) !== optionKey),
    );
    setCompletionTaskCandidatePreviews((current) => {
      const preview = current[taskInstanceKey];
      if (!preview) {
        return current;
      }
      return {
        ...current,
        [taskInstanceKey]: {
          ...preview,
          options: preview.options.filter(
            (candidate) => completionOptionKey(candidate) !== optionKey,
          ),
        },
      };
    });
    setResult((current) => {
      if (!current) {
        return current;
      }
      return {
        ...current,
        completion_recommendation: current.completion_recommendation
          ? {
              ...current.completion_recommendation,
              options: current.completion_recommendation.options.filter(
                (candidate) => completionOptionKey(candidate) !== optionKey,
              ),
            }
          : current.completion_recommendation,
        trip_intent: current.trip_intent
          ? {
              ...current.trip_intent,
              completion_candidate_history: (
                current.trip_intent.completion_candidate_history ?? []
              ).filter((candidate) => completionOptionKey(candidate) !== optionKey),
            }
          : current.trip_intent,
      };
    });
    setCompletionTaskStatus(`已记住不再优先推荐：${option.name}`);
    setError(null);
    if (tripPersistence.status === "saved") {
      const candidate = await registerCompletionCandidate(option);
      if (candidate) {
        await recordCandidateDecision(candidate, "reject", "USER_REJECTED");
      }
      return;
    }
    markWorkspaceDirty("completion_candidate_reject");
  }

  async function handleUndoCompletionTaskEdit(taskInstanceKey: string) {
    const edit = completionTaskEdits.find(
      (candidate) => candidate.task_instance_key === taskInstanceKey,
    );
    if (!edit) {
      return;
    }
    if (tripPersistence.status === "saved") {
      const currentRevision =
        revisionHistory.find((revision) => revision.id === tripPersistence.currentRevisionId) ?? null;
      if (currentRevision?.source_type === "completion_patch") {
        const response = await postTripJson<UndoPersistedMutationResponse>(
          TRIP_API_ENDPOINTS.undoPersistedRevision(tripPersistence.tripId, currentRevision.id),
          {
            base_revision_id: tripPersistence.currentRevisionId,
          },
          "撤销补全失败",
          undefined,
          {
            headers: {
              "X-Idempotency-Key": `undo-completion:${currentRevision.id}:${tripPersistence.currentRevisionId}`,
            },
          },
        );
        if (!response.ok) {
          if (response.code === "undo_target_not_current" || response.code === "stale_base_revision") {
            setTripPersistence({
              status: "conflict",
              tripId: tripPersistence.tripId,
              providedBaseRevisionId: tripPersistence.currentRevisionId,
              currentRevisionId: tripPersistence.currentRevisionId,
              message: response.message,
            });
          }
          setError(response.message);
          return;
        }
        await hydrateFromPersistedMutation(
          response.data.trip,
          response.data.current_revision,
          response.data.itinerary,
        );
        setCompletionTaskEdits((current) =>
          current.filter((candidate) => candidate.task_instance_key !== taskInstanceKey),
        );
        setRecentCompletionTaskItemKey((current) =>
          current === edit.inserted_item_key ? null : current,
        );
        setCompletionTaskStatus(`已撤销本次补全：${edit.inserted_item.name}`);
        setError(null);
        return;
      }
    }

    const localUndoResult = result
      ? undoCompletionTaskItemFromTripIntentEnvelope(
          removeCompletionTaskItemFromItinerary(result, edit.inserted_item),
          edit.inserted_item,
        )
      : null;
    setResult(localUndoResult);
    setGenerationContext((current) =>
      current
        ? undoCompletionTaskItemFromGenerationContext(current, edit.inserted_item)
        : current,
    );
    const insertedPoiType = getIntentPoiTypeFromScheduledItem(edit.inserted_item);
    if (insertedPoiType) {
      setUserIntentState((current) =>
        removeConfirmedPoiFromUserIntentState(
          current,
          edit.inserted_item.name,
          insertedPoiType,
        ),
      );
    }
    setCompletionTaskEdits((current) =>
      current.filter((candidate) => candidate.task_instance_key !== taskInstanceKey),
    );
    setRecentCompletionTaskItemKey((current) =>
      current === edit.inserted_item_key ? null : current,
    );
    setCompletionTaskStatus(`已撤销本次补全：${edit.inserted_item.name}`);
    setError(null);
    markWorkspaceDirty("completion_task_undo");

    if (!localUndoResult) {
      return;
    }

    const restoredCandidate = buildRestoredCompletionCandidate(edit.inserted_item);
    const nextRestoredCompletionCandidates = restoredCandidate
      ? upsertCompletionCandidateHistory(completionCandidateHistory, restoredCandidate)
      : completionCandidateHistory;
    setCompletionCandidateHistory(nextRestoredCompletionCandidates);

    setApplyingCompletionTaskId(taskInstanceKey);
    try {
      const apiResult = await postTripJson<ItineraryResponse>(
        REFRESH_ITINERARY_SURFACES_API_URL,
        {
          itinerary: localUndoResult,
          restored_completion_candidate: restoredCandidate ?? undefined,
          restored_completion_candidates: nextRestoredCompletionCandidates,
          completion_candidate_history: nextRestoredCompletionCandidates,
        },
        "刷新补全评分失败",
        `已撤销本次补全：${edit.inserted_item.name}。补全评分将在下次生成后更新。`,
      );
      if (!apiResult.ok) {
        setCompletionTaskStatus(
          `已撤销本次补全：${edit.inserted_item.name}。补全评分将在下次生成后更新。`,
        );
        return;
      }
      const refreshedItinerary = apiResult.data;
      setResult(refreshedItinerary);
      setCompletionCandidateHistory(
        refreshedItinerary.trip_intent?.completion_candidate_history ??
          nextRestoredCompletionCandidates,
      );
      setCompletionTaskStatus(
        `已撤销本次补全：${edit.inserted_item.name}。补全建议已刷新，可重新选择。`,
      );
    } catch {
      setCompletionTaskStatus(
        `已撤销本次补全：${edit.inserted_item.name}。补全评分将在下次生成后更新。`,
      );
    } finally {
      setApplyingCompletionTaskId(null);
    }
  }

  function handleClearLatestFollowUpEffect() {
    if (!latestFollowUpInterpretation?.raw_text || !latestFollowUpBaseIntent) {
      return;
    }
    setDismissedFollowUpRawText(latestFollowUpInterpretation.raw_text);
    setError(null);
  }

  function handleUseLatestFollowUpAgain() {
    if (!latestFollowUpEffectCleared) {
      return;
    }
    setDismissedFollowUpRawText(null);
    setError(null);
  }

  function handlePinCurrentTripScope() {
    if (!effectiveRegenerationIntentForNextGenerate) {
      return;
    }

    setTripDays(String(effectiveRegenerationIntentForNextGenerate.suggested_trip_days));
    setAvailabilityPreview(null);
    setAvailabilityPreviewSignature(null);
    setAvailabilityPreviewError(null);
    setQuickPreviewMode("current_brief");
    setError(null);
  }

  async function handleQuickGenerateSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!tripText.trim()) {
      setParseError("Tell us the rough trip idea first.");
      return;
    }

    setParsing(true);
    setLoading(true);
    setParseError(null);
    setError(null);
    scheduleResultReveal();
    setResult(null);
    setCompletionTaskEdits([]);
    setCompletionCandidateHistory([]);
    setActiveSwapTarget(null);

    try {
      const draftId = await createDraftTrip();
      if (!draftId) return;
      return;
    } catch {
      setError("Unable to generate from the quick trip idea.");
    } finally {
      setParsing(false);
      setLoading(false);
    }
  }

  function returnToOriginalRequest(notice?: string) {
    setTripPersistence({ status: "none" });
    setReturnToTripTextNotice(notice?.trim() || null);
    setRestoreTripTextFocus(true);
  }

  function updateTripText(value: string) {
    setTripText(value);
    setReturnToTripTextNotice(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!readiness.ready) {
      setError(readiness.message);
      setResult(null);
      setCompletionTaskEdits([]);
      setCompletionCandidateHistory([]);
      return;
    }

    if (isAvailabilityPreviewStale) {
      setError("Effective availability preview is out of date. Preview again before generating.");
      setResult(null);
      setCompletionTaskEdits([]);
      setCompletionCandidateHistory([]);
      return;
    }

    const structuredDraftText = buildPrePlanDraftText({
      directText: tripText,
      tripDays,
      scenicSpots: splitLines(scenicSpots),
      restaurants: splitLines(restaurants),
      fixedEventsText,
      availabilityWindowsText,
      arrivalAnchor,
      departureAnchor,
      hotel,
      preferences: splitLines(preferencesText),
      pacingLabel: formatPacingProfileLabel(pacingProfile),
      travelMode,
    });

    setLoading(true);
    setError(null);
    setResult(null);
    setCompletionTaskEdits([]);
    setCompletionCandidateHistory([]);
    setActiveSwapTarget(null);

    try {
      setTripText(structuredDraftText);
      await createDraftTrip(structuredDraftText);
    } catch {
      setError("无法创建行程草稿。");
    } finally {
      setLoading(false);
    }
  }

  async function handlePreviewAvailability() {
    const parsedAvailabilityWindows = parseAvailabilityWindowLines(availabilityWindowsText);
    const previewTripDays = tripDays.trim() ? Number(tripDays.trim()) : null;

    setAvailabilityPreview(null);
    setAvailabilityPreviewError(null);

    if (!previewTripDays) {
      setAvailabilityPreviewError("请先填写行程天数，再预览可排时间。");
      return;
    }

    setPreviewingAvailability(true);
    try {
      const apiResult = await postTripJson<AvailabilityPreviewResponse>(
        PREVIEW_AVAILABILITY_API_URL,
        {
          trip_days: previewTripDays,
          availability_windows: parsedAvailabilityWindows,
        },
        "可排时间预览失败",
        "无法连接可排时间预览接口。",
      );

      if (!apiResult.ok) {
        setAvailabilityPreviewError(apiResult.message);
        return;
      }

      setAvailabilityPreview(apiResult.data);
      setAvailabilityPreviewSignature(
        buildAvailabilityPreviewSignature(previewTripDays, availabilityWindowsText),
      );
    } catch {
      setAvailabilityPreviewError("无法连接可排时间预览接口。");
    } finally {
      setPreviewingAvailability(false);
    }
  }

  const editorialIntentPreview = buildEditorialIntentPreview({
    city:
      parsedIntent?.city ??
      activeRegenerationIntent?.city ??
      planningState?.city ??
      "上海",
    tripDays,
    pacingProfile,
    fixedEventCount: parseFixedEventLines(fixedEventsText).length,
    preferencesText,
    arrivalAnchor,
  });

  return (
    <main
      style={{
        position: "relative",
        overflow: "hidden",
        maxWidth: 1480,
        margin: "0 auto",
        padding: "28px 32px 112px",
        fontFamily: '"Avenir Next", "Helvetica Neue", sans-serif',
        color: "var(--ec-ink-soft)",
        background: "transparent",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          backgroundImage: "radial-gradient(rgba(21, 21, 21, 0.045) 1px, transparent 1px)",
          backgroundSize: "28px 28px",
          maskImage: "linear-gradient(180deg, rgba(0,0,0,0.48), rgba(0,0,0,0.02))",
          opacity: 0.18,
        }}
      />

      {tripPersistence.status === "draft" ? (
        <PrePlanIntentWorkspace
          tripId={tripPersistence.tripId}
          directUserText={tripText}
          onCancel={returnToOriginalRequest}
          onApplied={(applied) => {
            setResult(applied.itinerary);
            rememberPersistedTrip(applied.trip, applied.current_revision);
            void refreshRevisionHistory(applied.trip.id);
            scheduleResultReveal({ focus: true });
          }}
        />
      ) : null}

      {!result && tripPersistence.status !== "draft" ? (
        <section
          className="ec-home-shell"
          style={{
            position: "relative",
            overflow: "hidden",
            borderRadius: 56,
            padding: "clamp(28px, 3vw, 42px)",
            marginBottom: 32,
            background:
              "radial-gradient(circle at 12% 10%, rgba(177,138,88,0.16), transparent 28%), radial-gradient(circle at 86% 12%, rgba(102,113,95,0.12), transparent 24%), linear-gradient(180deg, rgba(255,253,249,0.985) 0%, rgba(247,244,238,0.985) 100%)",
            border: "1px solid var(--ec-line)",
            boxShadow: "var(--ec-shadow-3)",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              pointerEvents: "none",
              background:
                "linear-gradient(90deg, rgba(21,21,21,0.024) 1px, transparent 1px), linear-gradient(180deg, rgba(21,21,21,0.024) 1px, transparent 1px)",
              backgroundSize: "36px 36px",
              opacity: 0.42,
            }}
          />
          <div className="ec-home-grid" style={{ position: "relative" }}>
            <EditorialHeroField
              tripText={tripText}
              parsing={parsing}
              loading={loading}
              advancedModeOpen={advancedModeOpen}
              intentPreview={editorialIntentPreview}
              recoveryNotice={returnToTripTextNotice}
              onTripTextChange={updateTripText}
              onSubmit={handleQuickGenerateSubmit}
              onToggleAdvancedMode={() => setAdvancedModeOpen((current) => !current)}
            />
            <EditorialRouteSpine />
            <EditorialRouteField />
          </div>
          {parseError ? <InlineMessage tone="error" title="旅行骨架补全遇到问题" body={parseError!} /> : null}
        </section>
      ) : null}

      {savedTripPromptOpen && !result ? (
        <SavedTripResumeCard onRestore={handleRestoreSavedSession} onStartNew={handleStartNewTrip} />
      ) : null}

      {quickPreviewBrief && !result ? (
        <SectionShell>
          <section style={{ display: "grid", gap: 20, marginBottom: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "end", flexWrap: "wrap" }}>
              <div style={{ display: "grid", gap: 6 }}>
                <p style={sectionEyebrowStyle}>{quickPreviewSectionHeader.eyebrow}</p>
                <h2 style={sectionHeadingStyle}>{quickPreviewSectionHeader.title}</h2>
                {quickPreviewSectionHeader.description ? (
                  <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.65, maxWidth: 860 }}>
                    {quickPreviewSectionHeader.description}
                  </p>
                ) : null}
              </div>
              {activeRegenerationIntent && parsedIntent ? (
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {canPinCurrentTripScope && effectiveRegenerationIntentForNextGenerate ? (
                    <button
                      type="button"
                      onClick={handlePinCurrentTripScope}
                      style={miniGhostButtonStyle}
                    >
                      固定为 {effectiveRegenerationIntentForNextGenerate.suggested_trip_days} 天
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => setQuickPreviewMode("current_brief")}
                    style={{
                      ...miniGhostButtonStyle,
                      backgroundColor:
                        quickPreviewMode === "current_brief"
                          ? "rgba(233, 243, 223, 0.92)"
                          : miniGhostButtonStyle.backgroundColor,
                      color: quickPreviewMode === "current_brief" ? "#48673f" : miniGhostButtonStyle.color,
                    }}
                  >
                    设为当前计划
                  </button>
                  <button
                    type="button"
                    onClick={() => setQuickPreviewMode("original_parse")}
                    style={{
                      ...miniGhostButtonStyle,
                      backgroundColor:
                        quickPreviewMode === "original_parse"
                          ? "rgba(243, 237, 223, 0.92)"
                          : miniGhostButtonStyle.backgroundColor,
                      color: quickPreviewMode === "original_parse" ? "#7d5b32" : miniGhostButtonStyle.color,
                    }}
                  >
                    回到原始解析
                  </button>
                </div>
              ) : null}
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
                gap: 20,
              }}
            >
              {quickPreviewBriefCard ? (
                <BriefPreviewCard viewModel={quickPreviewBriefCard} />
              ) : null}

              {planningState ? (
                <PlanningInterpretationCard
                  viewModel={buildPlanningInterpretationCardViewModel(planningState)}
                />
              ) : null}
            </div>
          </section>
        </SectionShell>
      ) : null}

      {advancedModeOpen && advancedModeBrief && !result ? (
        <SectionShell>
        <section style={{ display: "grid", gap: 22, marginBottom: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "end", flexWrap: "wrap" }}>
            <div style={{ display: "grid", gap: 6 }}>
              <p style={sectionEyebrowStyle}>{advancedModeSectionHeader.eyebrow}</p>
              <h2 style={sectionHeadingStyle}>{advancedModeSectionHeader.title}</h2>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {canPinCurrentTripScope && effectiveRegenerationIntentForNextGenerate ? (
                <button
                  type="button"
                  onClick={handlePinCurrentTripScope}
                  style={secondaryButtonStyle}
                >
                  固定为 {effectiveRegenerationIntentForNextGenerate.suggested_trip_days} 天
                </button>
              ) : null}
              <button
                type="button"
                onClick={() =>
                  activeRegenerationIntent
                    ? syncFormStateWithRegenerationIntent(activeRegenerationIntent)
                    : populateStructuredFormFromParsedIntent(advancedModeBrief, planningState)
                }
                style={secondaryButtonStyle}
              >
                {activeRegenerationIntent ? "同步为当前计划" : "用这份解析补全骨架"}
              </button>
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
              gap: 20,
            }}
          >
            {advancedModeBriefCard ? (
              <BriefPreviewCard viewModel={advancedModeBriefCard} />
            ) : null}

            {planningState ? (
              <PlanningInterpretationCard
                viewModel={buildPlanningInterpretationCardViewModel(planningState)}
              />
            ) : null}
          </div>
        </section>
        </SectionShell>
      ) : null}

      {advancedModeOpen && !result ? (
      <SectionShell>
      <section style={{ display: "grid", gap: 22, marginBottom: 8 }}>
        <div style={{ display: "grid", gap: 6 }}>
          <p style={sectionEyebrowStyle}>补充旅行边界</p>
          <h2 style={sectionHeadingStyle}>只补那些会影响旅行骨架的细节</h2>
          <p style={{ margin: 0, color: "var(--ec-slate)", maxWidth: 760, lineHeight: 1.65 }}>
            这里不是另一张复杂表单，只用来补充会影响补全结果的信息：已有地点、餐食、固定时间、可用窗口和出发/离开边界。住宿和交通枢纽可以辅助规划，但不需要先定死。
          </p>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
            gap: 12,
          }}
        >
          <EditorialRibbon title="保留你的点" body="种草地点、餐食和固定安排" tone="sand" />
          <EditorialRibbon title="补清边界" body="可用时间、到达和离开约束" tone="sea" />
          <EditorialRibbon title="路线成型后再定住哪" body="用完成后的骨架反推住宿区域" tone="olive" />
        </div>

        <form onSubmit={handleSubmit} style={{ display: "grid", gap: 20, marginBottom: 12 }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0, 1.1fr) minmax(300px, 0.9fr)",
              gap: 20,
              alignItems: "start",
            }}
          >
            <ProductCard title="这趟旅行必须围绕什么展开" subtitle="这些是旅行骨架里的核心偏好：值得被优先安排，而不是被系统建议淹没。" accent="paper">
              <div style={{ display: "grid", gap: 16 }}>
                <FieldBlock
                  label="种草点 / 想去的地方"
                  helper="一行一个。可以是景点、街区、博物馆、路线、观景点或内容平台里看到的地点。"
                >
                  <textarea
                    id="scenic-spots"
                    rows={8}
                    value={scenicSpots}
                    onChange={(event) => setScenicSpots(event.target.value)}
                    placeholder="外滩&#10;豫园&#10;武康路"
                    style={textareaStyle}
                  />
                </FieldBlock>
                <FieldBlock
                  label="想吃的 / 餐食线索"
                  helper="一行一个。餐厅、夜市、小吃街、咖啡、面包店都可以；系统会优先放进午餐/晚餐节奏里。"
                >
                  <textarea
                    id="restaurants"
                    rows={6}
                    value={restaurants}
                    onChange={(event) => setRestaurants(event.target.value)}
                    placeholder="佳家汤包&#10;绿波廊"
                    style={textareaStyle}
                  />
                </FieldBlock>
                <FieldBlock
                  label="固定安排"
                  helper="格式：类型 | 名称 | 第几天 | 开始 | 结束。适合预约、演出、见朋友这类必须卡时间的安排。"
                >
                  <textarea
                    id="fixed-events"
                    rows={6}
                    value={fixedEventsText}
                    onChange={(event) => setFixedEventsText(event.target.value)}
                    placeholder="scenic | 上海博物馆 | 1 | 14:00 | 16:00"
                    style={textareaStyle}
                  />
                </FieldBlock>
                <FieldBlock
                  label="偏好和旅行节奏"
                  helper="一行一个。比如不要太赶、少走路、本地美食、夜景、亲子友好、想轻松一点。"
                >
                  <div style={{ display: "grid", gap: 12 }}>
                    <textarea
                      id="preferences"
                      rows={4}
                      value={preferencesText}
                      onChange={(event) => setPreferencesText(event.target.value)}
                      placeholder="少走路&#10;本地美食"
                      style={textareaStyle}
                    />
                    <div style={{ display: "grid", gap: 8 }}>
                      <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13 }}>
                        旅行节奏
                      </p>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                        {(["relaxed", "balanced", "packed"] as PacingProfile[]).map((profile) => (
                          <button
                            key={`pacing-${profile}`}
                            type="button"
                            onClick={() => setPacingProfile(profile)}
                            style={{
                              ...secondaryButtonStyle,
                              backgroundColor:
                                pacingProfile === profile
                                  ? "rgba(233, 243, 223, 0.92)"
                                  : "rgba(255,255,255,0.84)",
                              color: pacingProfile === profile ? "var(--ec-moss)" : "var(--ec-ink-soft)",
                              border:
                                pacingProfile === profile
                                  ? "1px solid rgba(124, 160, 127, 0.26)"
                                  : secondaryButtonStyle.border,
                            }}
                          >
                            {formatPacingProfileLabel(profile)}
                          </button>
                        ))}
                      </div>
                      <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13, lineHeight: 1.5 }}>
                        {describePacingProfile(pacingProfile)}
                      </p>
                    </div>
                  </div>
                </FieldBlock>
              </div>
            </ProductCard>

            <div style={{ display: "grid", gap: 20 }}>
              <ProductCard title="时间边界和辅助上下文" subtitle="这些信息会帮助系统判断哪些时间能排、哪些空缺需要补、最后一天怎么收口更稳。" accent="sage">
                <div style={{ display: "grid", gap: 16 }}>
                  <FieldBlock label="行程天数" helper="已确定就填；不确定也可以先让系统按种草点和时间弹性估算。">
                    <input
                      id="trip-days"
                      type="number"
                      min={1}
                      value={tripDays}
                      onChange={(event) => setTripDays(event.target.value)}
                      placeholder="可选，例如 2"
                      style={inputStyle}
                    />
                  </FieldBlock>
                  <FieldBlock
                    label="可用时间窗口"
                    helper="格式：第几天 | 说明 | 开始 | 结束。适合第一天晚到、最后一天中午走、下午有空这类约束。"
                  >
                    <textarea
                      id="availability-windows"
                      rows={5}
                      value={availabilityWindowsText}
                      onChange={(event) => setAvailabilityWindowsText(event.target.value)}
                      placeholder="1 | first day partial | 14:00 | 21:00"
                      style={textareaStyle}
                    />
                  </FieldBlock>
                  <FieldBlock label="住宿（可选）" helper="只有已经定好住处才填；否则系统会根据完成后的路线推荐住宿区域。">
                    <input
                      id="hotel"
                      type="text"
                      value={hotel}
                      onChange={(event) => setHotel(event.target.value)}
                        placeholder="可选酒店名"
                      style={inputStyle}
                    />
                  </FieldBlock>
                  <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr" }}>
                    <FieldBlock label="到达锚点" helper="可选机场或车站。">
                      <input
                        id="arrival-anchor"
                        type="text"
                        value={arrivalAnchor}
                        onChange={(event) => setArrivalAnchor(event.target.value)}
                        placeholder="虹桥火车站"
                        style={inputStyle}
                      />
                    </FieldBlock>
                    <FieldBlock label="离开锚点" helper="可选机场或车站。">
                      <input
                        id="departure-anchor"
                        type="text"
                        value={departureAnchor}
                        onChange={(event) => setDepartureAnchor(event.target.value)}
                        placeholder="浦东机场"
                        style={inputStyle}
                      />
                    </FieldBlock>
                  </div>
                  {(arrivalAnchor.trim() || departureAnchor.trim()) ? (
                    <SoftInfoCard
                      title="到达/离开边界已纳入骨架"
                      lines={[
                        arrivalAnchor.trim()
                          ? `系统会在需要时从 ${arrivalAnchor.trim()} 组织第一天开头。`
                          : null,
                        departureAnchor.trim()
                          ? `系统会在需要时让最后一天更靠近 ${departureAnchor.trim()} 收口。`
                          : null,
                      ].filter((line): line is string => line !== null)}
                    />
                  ) : null}
                </div>
              </ProductCard>

              <ProductCard title="补全前检查" subtitle="快速确认当前计划是否足够让系统补出一条可执行骨架。 " accent="sand">
                <div style={{ display: "grid", gap: 14 }}>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                      gap: 12,
                    }}
                  >
                    <SoftInfoCard
                      title="当前会影响骨架的约束"
                      lines={[
                        formatActiveConstraintsSummary({
                          tripDays,
                          fixedEventsText,
                          preferencesText,
                          arrivalAnchor,
                          departureAnchor,
                          availabilityWindowsText,
                        }),
                      ]}
                    />
                    <SoftInfoCard
                      title={readiness.ready ? "可以开始补全" : "还缺关键信息"}
                      tone={readiness.ready ? "success" : "warning"}
                      lines={[readiness.message]}
                    />
                  </div>
                  <div style={{ display: "grid", gap: 10 }}>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
                      <button
                        type="button"
                        onClick={handlePreviewAvailability}
                        disabled={previewingAvailability}
                        style={secondaryButtonStyle}
                      >
                        {previewingAvailability ? "预览中…" : "预览可排时间"}
                      </button>
                      <span style={{ color: "var(--ec-slate)", fontSize: 14 }}>
                        先看哪些时间段能被排进行程骨架。
                      </span>
                    </div>
                    {availabilityPreviewError ? (
                    <InlineMessage tone="error" title="可排时间预览遇到问题" body={availabilityPreviewError} />
                    ) : null}
                    {availabilityPreview ? (
                      <div
                        style={{
                          border: "1px solid rgba(143, 155, 179, 0.14)",
                          borderRadius: 22,
                          background:
                            "linear-gradient(180deg, rgba(255,255,255,0.88) 0%, rgba(249,251,250,0.94) 100%)",
                          padding: 18,
                          display: "grid",
                          gap: 12,
                        }}
                      >
                        <div style={{ display: "grid", gap: 4 }}>
                          <p style={{ margin: 0, fontWeight: 700, color: "var(--ec-ink)" }}>
                            可排时间预览
                          </p>
                          <p
                            style={{
                              margin: 0,
                              color: isAvailabilityPreviewStale ? "#8a5a00" : "#2f6f3e",
                              fontSize: 14,
                            }}
                          >
                            {isAvailabilityPreviewStale
                              ? "当前预览已经和表单不一致，生成前建议刷新。"
                              : "预览已匹配当前天数和可用时间窗口。"}
                          </p>
                        </div>
                        <div style={{ display: "grid", gap: 10 }}>
                          {availabilityPreview.days.map((day) => (
                            <div
                              key={`preview-day-${day.day}`}
                              style={{
                                display: "grid",
                                gap: 4,
                                paddingTop: 10,
                                borderTop: "1px solid rgba(225, 228, 233, 0.85)",
                              }}
                            >
                              <p style={{ margin: 0, fontWeight: 600 }}>Day {day.day}</p>
                              <p style={{ margin: 0, color: "#555", fontSize: 14 }}>
                                可排时间：{formatEffectiveAvailabilityRange(day.availability_summary)}
                              </p>
                              <p style={{ margin: 0, color: "#777", fontSize: 13 }}>
                                剩余时间块：{formatRemainingBlocks(day.availability_summary.remaining_blocks)}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              </ProductCard>

              {activeRegenerationIntent && activeFollowUpInterpretation ? (
                <div style={{ display: "grid", gap: 10 }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 12,
                      alignItems: "center",
                      flexWrap: "wrap",
                    }}
                  >
                    <p style={{ margin: 0, color: "#7d5b32", fontSize: 13, fontWeight: 700 }}>
                      下一次补全前，最近这句补充要求仍会影响当前计划
                    </p>
                    <button
                      type="button"
                      onClick={handleEditLatestFollowUp}
                      style={secondaryButtonStyle}
                    >
                      编辑这句补充要求
                    </button>
                    <button
                      type="button"
                      onClick={
                        latestFollowUpEffectCleared
                          ? handleUseLatestFollowUpAgain
                          : handleClearLatestFollowUpEffect
                      }
                      style={secondaryButtonStyle}
                      disabled={!canClearLatestFollowUpEffect && !latestFollowUpEffectCleared}
                    >
                      {latestFollowUpEffectCleared
                        ? "重新使用这句补充要求"
                        : "不再沿用这句影响"}
                    </button>
                  </div>
                  {latestFollowUpEffectCleared ? (
                    <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13, lineHeight: 1.6 }}>
                      下一次补全会忽略最近这句补充要求的持续影响，回到它之前那版计划继续滚动；当前这版行程不会被直接改掉。
                    </p>
                  ) : null}
                  <FollowUpInterpretationCard interpretation={activeFollowUpInterpretation} />
                </div>
              ) : null}
            </div>
          </div>

          <div
            style={{
              position: "sticky",
              bottom: 18,
              zIndex: 5,
              display: "flex",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                width: "min(780px, 100%)",
                display: "grid",
                gap: 10,
                padding: 18,
                borderRadius: 24,
                background:
                  "linear-gradient(135deg, rgba(29,38,35,0.95) 0%, rgba(32,45,40,0.96) 100%)",
                color: "#f6f1e8",
                boxShadow: "0 24px 60px rgba(17, 24, 39, 0.22)",
                border: "1px solid rgba(255,255,255,0.06)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
                <div style={{ display: "grid", gap: 4 }}>
                  <p style={{ margin: 0, fontSize: 13, letterSpacing: "0.04em", textTransform: "uppercase", color: "#d2c1a1" }}>
                    补全当前旅行骨架
                  </p>
                  <p style={{ margin: 0, color: "#ece8df" }}>
                    {readiness.ready
                      ? "核心种草点和约束已经准备好。"
                      : readiness.message}
                  </p>
                </div>
                <button type="submit" disabled={loading} style={floatingPrimaryButtonStyle}>
                  {loading ? "正在创建草稿…" : "进入意图确认"}
                </button>
              </div>
              {!readiness.ready ? (
                <p style={{ margin: 0, color: "#f7d08a", fontSize: 14 }}>{readiness.message}</p>
              ) : null}
              {activeRegenerationIntent && activeFollowUpInterpretation ? (
                <div style={{ display: "grid", gap: 8 }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 12,
                      alignItems: "center",
                      flexWrap: "wrap",
                    }}
                  >
                    <p style={{ margin: 0, color: "#d7e5d6", fontSize: 13, lineHeight: 1.6 }}>
                      {latestFollowUpEffectCleared
                        ? "最近这句补充要求已从下一次补全中移除："
                        : "最近这句补充要求仍会影响下一次补全："}
                      {" "}
                      {activeFollowUpInterpretation.summary_lines[0]}
                    </p>
                    <button
                      type="button"
                      onClick={handleEditLatestFollowUp}
                      style={miniGhostButtonStyle}
                    >
                      编辑这句补充要求
                    </button>
                    <button
                      type="button"
                      onClick={
                        latestFollowUpEffectCleared
                          ? handleUseLatestFollowUpAgain
                          : handleClearLatestFollowUpEffect
                      }
                      style={miniGhostButtonStyle}
                      disabled={!canClearLatestFollowUpEffect && !latestFollowUpEffectCleared}
                    >
                      {latestFollowUpEffectCleared
                        ? "重新使用这句补充要求"
                        : "不再沿用这句影响"}
                    </button>
                  </div>
                  {latestFollowUpEffectCleared ? (
                    <p style={{ margin: 0, color: "#f7d08a", fontSize: 13, lineHeight: 1.6 }}>
                      下一次补全会回到这句补充要求之前的当前计划。
                    </p>
                  ) : null}
                </div>
              ) : null}
              {isAvailabilityPreviewStale ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                  <p style={{ margin: 0, color: "#f7d08a", fontSize: 14 }}>
                    生成前建议刷新可排时间预览。
                  </p>
                  <button
                    type="button"
                    onClick={handlePreviewAvailability}
                    disabled={previewingAvailability}
                    style={miniGhostButtonStyle}
                  >
                    {previewingAvailability ? "预览中…" : "刷新预览"}
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </form>
      </section>
      </SectionShell>
      ) : null}

      {error ? (
        isFixedEventAvailabilityConflict(error) ? (
          <InlineMessage
            tone="error"
                title="固定安排和可排时间冲突"
            body={error}
            prominent
          />
        ) : (
          <InlineMessage tone="error" title="旅行骨架补全遇到问题" body={error} prominent />
        )
      ) : null}

      {result ? (
        <section
          ref={resultSectionRef}
          className="ec-result-entry"
          tabIndex={-1}
          aria-label={tripPersistence.status === "saved" ? "已保存的正式路线工作台" : "路线工作台"}
        >
          <SectionShell>
            {tripPersistence.status === "saved" ? (
              <ExecutableRoutePreview
                itinerary={result}
                variant="saved"
                tripId={tripPersistence.tripId}
                baseRevisionId={tripPersistence.currentRevisionId}
                onApplied={(applied) => {
                  setResult(applied.itinerary as ItineraryResponse);
                  rememberPersistedTrip(applied.trip, applied.current_revision);
                  void refreshRevisionHistory(applied.trip.id);
                }}
                onReloadLatest={loadLatestSavedRoute}
              />
            ) : null}
            <RouteWorkspaceContainer
            city={activeTripCity}
            itinerary={result}
            parsedIntent={result.trip_intent?.parsed_intent ?? parsedIntent}
            editing={routeEditMode}
            activeSheet={activeRouteSheet}
            focusRequest={routeFocusRequest}
            onFocusRouteDay={focusRouteDay}
            autoFilledCount={commandCenterAutoFilledCount}
            intentLine={commandCenterIntentLines[0] ?? null}
            executionLine={commandCenterSystemLines[0] ?? null}
            weakestDay={buildRouteWorkspaceWeakestDay(result)}
            routePreviewEndpoint={PREVIEW_ROUTE_SEGMENTS_API_URL}
            poiDetailEndpoint={PREVIEW_POI_DETAIL_API_URL}
            onToggleEditing={toggleRouteEditMode}
            onSheetChange={setActiveRouteSheet}
            onApplyEdits={handleCommitRouteEdits}
            onClose={() => setRouteEditMode(false)}
            headerUtility={
              <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span
                  style={{
                    padding: "7px 10px",
                    borderRadius: 999,
                    border: "1px solid rgba(21,21,21,0.1)",
                    background:
                      tripPersistence.status === "dirty"
                        ? "rgba(247, 208, 138, 0.16)"
                        : tripPersistence.status === "conflict" || tripPersistence.status === "error"
                          ? "rgba(185, 78, 72, 0.12)"
                          : "rgba(239,248,243,0.9)",
                    color:
                      tripPersistence.status === "dirty"
                        ? "#7d5b32"
                        : tripPersistence.status === "conflict" || tripPersistence.status === "error"
                          ? "#9d302a"
                          : "#48673f",
                    fontSize: 12,
                    fontWeight: 900,
                    whiteSpace: "nowrap",
                  }}
                >
                  {describeTripPersistence(tripPersistence)}
                </span>
                {tripPersistence.status === "saved" || tripPersistence.status === "dirty" ? (
                  <button
                    className="ec-interactive-pill"
                    type="button"
                    onClick={() => {
                      setVersionHistoryOpen((current) => !current);
                      void refreshRevisionHistory(tripPersistence.tripId);
                    }}
                    style={{
                      ...miniGhostButtonStyle,
                      whiteSpace: "nowrap",
                    }}
                  >
                    版本记录
                  </button>
                ) : null}
                <button
                  className="ec-interactive-pill"
                  type="button"
                  onClick={handleStartNewTrip}
                  style={{
                    ...miniGhostButtonStyle,
                    whiteSpace: "nowrap",
                  }}
                >
                  新行程
                </button>
                {versionHistoryOpen ? (
                  <div
                    style={{
                      position: "absolute",
                      top: "calc(100% + 8px)",
                      right: 0,
                      zIndex: 20,
                      width: 320,
                      maxWidth: "calc(100vw - 32px)",
                      display: "grid",
                      gap: 8,
                      padding: 12,
                      borderRadius: 18,
                      border: "1px solid rgba(21,21,21,0.1)",
                      background: "rgba(255,253,249,0.98)",
                      boxShadow: "0 18px 44px rgba(21,21,21,0.14)",
                    }}
                  >
                    <strong style={{ fontSize: 13, color: "var(--ec-ink)" }}>
                      版本记录
                    </strong>
                    {revisionHistory.length === 0 ? (
                      <p style={{ margin: 0, fontSize: 12, color: "var(--ec-slate)" }}>
                        暂无可查看的已保存版本。
                      </p>
                    ) : (
                      revisionHistory.map((revision) => (
                        <div
                          key={revision.id}
                          style={{
                            display: "grid",
                            gap: 6,
                            padding: 10,
                            borderRadius: 12,
                            background:
                              tripPersistence.status !== "none" &&
                              "currentRevisionId" in tripPersistence &&
                              tripPersistence.currentRevisionId === revision.id
                                ? "rgba(239,248,243,0.94)"
                                : "rgba(21,21,21,0.035)",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                            <span style={{ fontSize: 12, fontWeight: 900, color: "var(--ec-ink)" }}>
                              版本 {revision.revision_number}
                            </span>
                            <span style={{ fontSize: 11, color: "var(--ec-slate)" }}>
                              {describeTripRevisionSource(revision.source_type)}
                            </span>
                          </div>
                          <p style={{ margin: 0, fontSize: 11, color: "var(--ec-slate)", lineHeight: 1.4 }}>
                              {revision.planner_version ? "规划记录已附带" : "无规划记录"} · {new Date(revision.created_at).toLocaleString()}
                          </p>
                          {tripPersistence.status === "saved" &&
                          tripPersistence.currentRevisionId !== revision.id ? (
                            <div style={{ display: "grid", gap: 6, justifyItems: "start" }}>
                              <p style={{ margin: 0, fontSize: 11, lineHeight: 1.4, color: "var(--ec-slate)" }}>
                                {describeRevisionRestoreImpact(revision.revision_number)}
                              </p>
                              <button
                                type="button"
                                onClick={() => void handleRestoreRevision(revision)}
                                style={{ ...miniGhostButtonStyle, justifySelf: "start" }}
                              >
                                恢复为新版本
                              </button>
                            </div>
                          ) : null}
                        </div>
                      ))
                    )}
                  </div>
                ) : null}
              </div>
            }
            sheetContent={
              activeRouteSheet === "completion" ? (
                <div style={{ display: "grid", gap: 14 }}>
                  {result.completion_intelligence ? (
                    <>
                      <section
                        style={{
                          display: "grid",
                          gap: 12,
                          padding: 16,
                          borderRadius: 24,
                          background:
                            "linear-gradient(135deg, rgba(239,248,243,0.96), rgba(255,253,249,0.92))",
                          border: "1px solid rgba(123, 160, 127, 0.18)",
                          boxShadow: "0 14px 34px rgba(21,21,21,0.045)",
                        }}
                      >
                        <div
                          style={{
                            display: "grid",
                            gridTemplateColumns: "auto 1fr",
                            gap: 14,
                            alignItems: "center",
                          }}
                        >
                          <div
                            style={{
                              display: "grid",
                              placeItems: "center",
                              width: 72,
                              height: 72,
                              borderRadius: 24,
                              background: "var(--ec-night)",
                              color: "#fffdf9",
                              boxShadow: "0 18px 34px rgba(21,21,21,0.14)",
                            }}
                          >
                            <strong style={{ fontSize: 24, lineHeight: 1 }}>
                              {result.completion_intelligence.trip_completeness}%
                            </strong>
                            <span
                              style={{
                                marginTop: -6,
                                fontSize: 10,
                                fontWeight: 900,
                                letterSpacing: "0.1em",
                              }}
                            >
                              完成度
                            </span>
                          </div>
                          <div style={{ display: "grid", gap: 5, minWidth: 0 }}>
                            <p
                              style={{
                                margin: 0,
                                color: "#557060",
                                fontSize: 11,
                                fontWeight: 900,
                                letterSpacing: "0.12em",
                                textTransform: "uppercase",
                              }}
                            >
                              路线补全引擎
                            </p>
                            <h3
                              style={{
                                margin: 0,
                                color: "var(--ec-ink)",
                                fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
                                fontSize: 24,
                                lineHeight: 1.12,
                                letterSpacing: "-0.04em",
                              }}
                            >
                              下一步只修最影响成行的空缺
                            </h3>
                            <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13, lineHeight: 1.55 }}>
                              {result.completion_intelligence.action_tasks?.[0]
                                ? formatProductFacingReason(result.completion_intelligence.action_tasks[0].reason)
                                : "当前路线已经可以先浏览；如果要继续精修，可以从地点详情和路线顺序开始。"}
                            </p>
                          </div>
                        </div>
                        {completionTaskStatus ? (
                          <ExplainabilityCard title="刚刚完成" tone="olive" lines={[completionTaskStatus]} />
                        ) : null}
                        {result.planner_realism || latestDirectOptimizationComparison ? (
                          <details
                            style={{
                              border: "1px solid rgba(123,160,127,0.16)",
                              borderRadius: 18,
                              background: "rgba(255,253,249,0.66)",
                              overflow: "hidden",
                            }}
                          >
                            <summary
                              style={{
                                padding: "11px 12px",
                                color: "var(--ec-slate)",
                                cursor: "pointer",
                                fontSize: 12,
                                fontWeight: 900,
                                letterSpacing: "0.08em",
                                textTransform: "uppercase",
                                listStyle: "none",
                              }}
                            >
                              查看系统依据
                            </summary>
                            <div style={{ display: "grid", gap: 10, padding: "0 10px 10px" }}>
                              {result.planner_realism ? (
                                <PlannerRealismCard plannerRealism={result.planner_realism} />
                              ) : null}
                              {latestDirectOptimizationComparison ? (
                                <ExplainabilityCard
                                  title={latestDirectOptimizationComparison.title}
                                  tone="olive"
                                  lines={latestDirectOptimizationComparison.lines}
                                />
                              ) : null}
                            </div>
                          </details>
                        ) : null}
                      </section>
                      {result.completion_intelligence.action_tasks?.length ? (
                        <CompletionTaskActionList
                          tasks={result.completion_intelligence.action_tasks}
                          expanded={completionTasksExpanded}
                          onExpandedChange={setCompletionTasksExpanded}
                          getTaskInstanceKey={getCompletionTaskInstanceKey}
                          completionTaskEdits={completionTaskEdits}
                          candidatePreviews={completionTaskCandidatePreviews}
                          previewingTaskId={previewingCompletionTaskId}
                          applyingTaskId={applyingCompletionTaskId}
                          disabled={replanning || applyingCompletionTaskId !== null}
                          replanning={replanning}
                          canPreviewTask={(task) => buildCompletionTaskActionRequest(task) !== null}
                          onPreviewTask={handlePreviewCompletionTaskCandidates}
                          onUndoTask={handleUndoCompletionTaskEdit}
                          onUsePrompt={handleUseCompletionImprovementPrompt}
                          onApplyOption={handleApplyCompletionTask}
                          onRejectOption={handleRejectCompletionTaskCandidate}
                        />
                      ) : null}
                      <CandidateWorkspacePanel
                        state={candidateWorkspace}
                        onRefresh={() => {
                          if (tripPersistence.status === "saved") {
                            void refreshCandidates(tripPersistence.tripId);
                          }
                        }}
                        onAdmit={(candidate) => void admitCandidate(candidate)}
                        onReject={(candidate) => void recordCandidateDecision(candidate, "reject", "USER_REJECTED")}
                        onDefer={(candidate) => void recordCandidateDecision(candidate, "defer", "USER_DEFERRED")}
                        onRestore={(candidate) => void recordCandidateDecision(candidate, "restore_pending", "RESTORED_TO_PENDING")}
                      />
                      <ImportReviewWorkspace
                        tripPersistence={tripPersistence}
                        onCandidatesChanged={(tripId) => void refreshCandidates(tripId)}
                      />
                      <IntentConfirmationWorkspace
                        tripPersistence={tripPersistence}
                        directUserText={tripText}
                      />
                      {result.completion_intelligence.score_breakdown ? (
                        <details
                          style={{
                            border: "1px solid var(--ec-line-soft)",
                            borderRadius: 24,
                            background:
                              "linear-gradient(180deg, rgba(255,253,249,0.82), rgba(247,244,238,0.66))",
                            boxShadow: "0 12px 32px rgba(21,21,21,0.035)",
                            overflow: "hidden",
                          }}
                        >
                          <summary
                            style={{
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                              gap: 14,
                              padding: "14px 16px",
                              color: "var(--ec-ink)",
                              cursor: "pointer",
                              fontSize: 14,
                              fontWeight: 900,
                              listStyle: "none",
                            }}
                          >
                            <span>查看路线评分依据</span>
                            <span
                              style={{
                                color: "var(--ec-slate)",
                                fontSize: 11,
                                fontWeight: 800,
                                letterSpacing: "0.08em",
                                textTransform: "uppercase",
                              }}
                            >
                              可展开
                            </span>
                          </summary>
                          <div style={{ padding: "0 12px 12px" }}>
                            <CompletionExecutionEvidence
                              rows={buildCompletionScoreBreakdownRows(
                                result.completion_intelligence.score_breakdown,
                              )}
                              isApplyingImprovement={replanning}
                              onApplyAndReplan={handleApplyCompletionImprovement}
                              onApplyImprovement={handleUseCompletionImprovementPrompt}
                            />
                          </div>
                        </details>
                      ) : null}
                    </>
                  ) : null}
                  {result.completion_recommendation ? (
                    <section
                      style={{
                        display: "grid",
                        gap: 10,
                        padding: 14,
                        borderRadius: 22,
                        backgroundColor: "rgba(255,255,255,0.82)",
                        border: "1px solid rgba(148,163,184,0.16)",
                      }}
                    >
                      <p style={{ margin: 0, color: "#22352c", fontWeight: 900 }}>
                        {result.completion_recommendation.recommendation_title}
                      </p>
                      <p style={{ margin: 0, color: "#617268", lineHeight: 1.6 }}>
                        {result.completion_recommendation.summary}
                      </p>
                      <button
                        type="button"
                        onClick={() => setCompletionPickerOpen(true)}
                        style={secondaryButtonStyle}
                      >
                        查看可补候选
                      </button>
                    </section>
                  ) : null}
                </div>
              ) : activeRouteSheet === "adjust" ? (
                <ConversationalReplanPanel
                  itinerary={result}
                  initialText={followUpText}
                  backendInterpretationLines={activeFollowUpInterpretation?.summary_lines ?? []}
                  executing={replanning}
                  onDraftChange={setFollowUpText}
                  onExecutePlan={handleConversationalReplanExecute}
                  onUndoSnapshot={handleUndoConversationalReplan}
                />
              ) : activeRouteSheet === "share" ? (
                <div style={{ display: "grid", gap: 12 }}>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                    <button type="button" onClick={() => handleCopyItinerary("practical")} style={secondaryButtonStyle}>
                      复制实用版
                    </button>
                    <button type="button" onClick={() => handleCopyItinerary("share")} style={secondaryButtonStyle}>
                      复制分享版
                    </button>
                    <button type="button" onClick={handleGenerateShareCard} style={secondaryButtonStyle}>
                      生成分享图片
                    </button>
                  </div>
                  {copyStatus ? <p style={{ margin: 0, color: "#56705e", fontWeight: 800 }}>{copyStatus}</p> : null}
                  {shareCardStatus ? <p style={{ margin: 0, color: "#56705e", fontWeight: 800 }}>{shareCardStatus}</p> : null}
                  {shareCardImageUrl ? (
                    <div style={{ display: "grid", gap: 10, maxWidth: 380 }}>
                      <img
                        src={shareCardImageUrl}
                        alt="Generated itinerary share card preview"
                        style={{ width: "100%", borderRadius: 18, boxShadow: "0 14px 34px rgba(15,23,42,0.12)" }}
                      />
                      <a
                        href={shareCardImageUrl}
                        download="itinerary-share-card.png"
                        style={{ ...secondaryButtonStyle, textAlign: "center", textDecoration: "none" }}
                      >
                        下载图片
                      </a>
                      <button type="button" onClick={handleCopyShareQuestion} style={miniGhostButtonStyle}>
                        复制提问文案
                      </button>
                      <section
                        style={{
                          display: "grid",
                          gap: 10,
                          padding: 12,
                          borderRadius: 18,
                          backgroundColor: "rgba(255,247,237,0.88)",
                          border: "1px solid rgba(206,171,111,0.16)",
                        }}
                      >
                        <p style={{ margin: 0, color: "#8a6331", fontWeight: 900 }}>
                          这个路线你会真的用吗？
                        </p>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                          {(["会用", "还行", "不太行"] as ShareCardFeedbackRating[]).map((rating) => (
                            <button
                              key={rating}
                              type="button"
                              onClick={() => handleShareFeedbackSelect(rating)}
                              style={{
                                ...miniGhostButtonStyle,
                                backgroundColor:
                                  shareFeedbackRating === rating
                                    ? "rgba(232,242,224,0.95)"
                                    : miniGhostButtonStyle.backgroundColor,
                                color: shareFeedbackRating === rating ? "#48673f" : miniGhostButtonStyle.color,
                              }}
                            >
                              {rating}
                            </button>
                          ))}
                        </div>
                        {shareFeedbackRating && shareFeedbackRating !== "会用" ? (
                          <div style={{ display: "grid", gap: 8 }}>
                            <input
                              value={shareFeedbackNote}
                              onChange={(event) => {
                                setShareFeedbackNote(event.target.value);
                                setShareFeedbackSaved(false);
                              }}
                              placeholder="哪里不太对？"
                              style={{
                                width: "100%",
                                boxSizing: "border-box",
                                border: "1px solid var(--ec-line)",
                                borderRadius: 12,
                                padding: "10px 12px",
                                color: "var(--ec-ink-soft)",
                                backgroundColor: "rgba(255,253,249,0.82)",
                              }}
                            />
                            <button type="button" onClick={handleShareFeedbackSubmit} style={miniGhostButtonStyle}>
                              保存反馈
                            </button>
                          </div>
                        ) : null}
                        {shareFeedbackSaved ? (
                          <p style={{ margin: 0, color: "#66736b", fontSize: 13 }}>
                            已保存到本地反馈记录。
                          </p>
                        ) : null}
                      </section>
                    </div>
                  ) : null}
                </div>
              ) : activeRouteSheet === "more" ? (
                <div style={{ display: "grid", gap: 14 }}>
                  {result.planner_realism?.status === "needs_repair" || result.planner_realism?.status === "unstable" ? (
                    <PlannerRealismCard plannerRealism={result.planner_realism} />
                  ) : null}
                  {itineraryValueSummary ? (
                    <ExplainabilityCard
                      title="来自你的输入"
                      tone="olive"
                      lines={itineraryValueSummary.fromInputLines}
                    />
                  ) : null}
                  {result.planning_assumptions?.summary_lines.length ? (
                    <ExplainabilityCard
                      title="当前计划"
                      tone="sand"
                      lines={buildPlannerAssumptionDisplayLines(result.planning_assumptions)}
                    />
                  ) : null}
                  {result.journey_approach_recommendation ? (
                    <section
                      style={{
                        display: "grid",
                        gap: 10,
                        padding: 14,
                        borderRadius: 20,
                        backgroundColor: "rgba(255,255,255,0.82)",
                        border: "1px solid rgba(148,163,184,0.16)",
                      }}
                    >
                      <p style={{ margin: 0, color: "#587081", fontSize: 12, fontWeight: 900 }}>
                        到达与离开
                      </p>
                      {result.journey_approach_recommendation.arrival ? (
                        <ResultJourneyLine
                          verb="到达"
                          value={
                            result.journey_approach_recommendation.arrival.recommended_hub_name ??
                            formatTravelMode(result.journey_approach_recommendation.arrival.recommended_mode)
                          }
                          meta={result.journey_approach_recommendation.arrival.fit_label}
                        />
                      ) : null}
                      {result.journey_approach_recommendation.departure ? (
                        <ResultJourneyLine
                          verb="离开"
                          value={
                            result.journey_approach_recommendation.departure.recommended_hub_name ??
                            formatTravelMode(result.journey_approach_recommendation.departure.recommended_mode)
                          }
                          meta={result.journey_approach_recommendation.departure.fit_label}
                        />
                      ) : null}
                    </section>
                  ) : null}
                  {result.stay_recommendation?.options[0] ? (
                    <ExplainabilityCard
                      title="住宿建议"
                      tone="sand"
                      lines={[
                        `建议住在 ${result.stay_recommendation.options[0].suggested_area_label}`,
                        result.stay_recommendation.options[0].reasoning_summary,
                      ]}
                    />
                  ) : null}
                  {result.departure_recommendation?.options[0] ? (
                    <ExplainabilityCard
                      title="离开建议"
                      tone="sea"
                      lines={[
                        result.departure_recommendation.options[0].suggested_departure_label,
                        result.departure_recommendation.options[0].reasoning_summary,
                      ]}
                    />
                  ) : null}
                </div>
              ) : null
            }
            commandCenter={
              tripReadinessViewModel ? (
                <TripReadinessPanel
                  viewModel={tripReadinessViewModel}
                  onPrimaryAction={(action) => {
                    if (action.kind === "focus-day") {
                      setActiveRouteSheet(null);
                      focusRouteDay(action.day);
                      return;
                    }
                    if (action.kind === "review-route") {
                      setActiveRouteSheet(null);
                      return;
                    }
                    setActiveRouteSheet("completion");
                  }}
                />
              ) : null
            }
            completionRail={
              <div style={{ display: "grid", gap: 10 }}>
                {result.completion_intelligence?.action_tasks?.length ? (
                  <CompletionTaskActionList
                    variant="rail"
                    tasks={result.completion_intelligence.action_tasks}
                    expanded={completionTasksExpanded}
                    onExpandedChange={setCompletionTasksExpanded}
                    getTaskInstanceKey={getCompletionTaskInstanceKey}
                    completionTaskEdits={completionTaskEdits}
                    candidatePreviews={completionTaskCandidatePreviews}
                    previewingTaskId={previewingCompletionTaskId}
                    applyingTaskId={applyingCompletionTaskId}
                    disabled={replanning || applyingCompletionTaskId !== null}
                    replanning={replanning}
                    canPreviewTask={(task) => buildCompletionTaskActionRequest(task) !== null}
                    onPreviewTask={handlePreviewCompletionTaskCandidates}
                    onUndoTask={handleUndoCompletionTaskEdit}
                    onUsePrompt={handleUseCompletionImprovementPrompt}
                    onApplyOption={handleApplyCompletionTask}
                    onRejectOption={handleRejectCompletionTaskCandidate}
                  />
                ) : (
                  <p style={{ margin: 0, color: "#617268", lineHeight: 1.6 }}>
                    当前没有需要立即处理的补全任务。
                  </p>
                )}
                {completionTaskStatus ? (
                  <ExplainabilityCard title="刚刚完成" tone="olive" lines={[completionTaskStatus]} />
                ) : null}
              </div>
            }
            briefRail={
              <div style={{ display: "grid", gap: 10 }}>
                {itineraryValueSummary ? (
                  <ExplainabilityCard
                    title="来自你的输入"
                    tone="olive"
                    lines={itineraryValueSummary.fromInputLines}
                  />
                ) : null}
                {result.planning_assumptions?.summary_lines.length ? (
                  <ExplainabilityCard
                    title="当前计划"
                    tone="sand"
                    lines={buildPlannerAssumptionDisplayLines(result.planning_assumptions)}
                  />
                ) : null}
              </div>
            }
          />
          </SectionShell>
        </section>
      ) : null}

      {completionPickerOpen && result?.completion_recommendation ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 50,
            backgroundColor: "rgba(24, 28, 32, 0.42)",
            display: "grid",
            placeItems: "center",
            padding: 24,
          }}
        >
          <div
            style={{
              width: "min(980px, 100%)",
              maxHeight: "min(88vh, 920px)",
              overflow: "auto",
              borderRadius: 30,
              background: "linear-gradient(180deg, #fffdf9 0%, #f8fbf8 100%)",
              boxShadow: "0 32px 80px rgba(15, 23, 42, 0.22)",
              padding: 24,
              display: "grid",
              gap: 18,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "start", flexWrap: "wrap" }}>
              <div style={{ display: "grid", gap: 6, maxWidth: 620 }}>
                <p style={{ margin: 0, color: "#72816f", fontSize: 12, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                  补齐更多空缺
                </p>
                <h3
                  style={{
                    margin: 0,
                    fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
                    fontSize: 38,
                    lineHeight: 1,
                    color: "#203129",
                  }}
                >
                  选择哪些推荐点要补进这趟旅行。
                </h3>
                <p style={{ margin: 0, color: "#617268", lineHeight: 1.6 }}>
                  选中后会直接加入当前旅行计划，让下一次补全也记住这些选择。
                </p>
              </div>
              <button
                type="button"
                onClick={() => setCompletionPickerOpen(false)}
                style={miniGhostButtonStyle}
              >
                关闭
              </button>
            </div>

            <div style={{ display: "grid", gap: 18 }}>
              {groupCompletionOptionsByDay(result.completion_recommendation.options).map(
                ([day, options]) => (
                  <div key={`completion-picker-day-${day}`} style={{ display: "grid", gap: 12 }}>
                    <p
                      style={{
                        margin: 0,
                        color: "#5d7267",
                        fontSize: 12,
                        fontWeight: 800,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                      }}
                    >
                      建议补到第 {day} 天
                    </p>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                        gap: 14,
                      }}
                    >
                      {options.map((option) => {
                        const optionKey = buildCompletionOptionKey(option);
                        const selected = selectedCompletionOptionKeys.includes(optionKey);
                        const imageUrl = getCompletionOptionImage(option.name);

                        return (
                          <label
                            key={`${optionKey}-picker`}
                            style={{
                              cursor: "pointer",
                              overflow: "hidden",
                              borderRadius: 24,
                              border: selected
                                ? "2px solid rgba(96, 140, 93, 0.58)"
                                : "1px solid rgba(151, 171, 160, 0.18)",
                              background: selected
                                ? "linear-gradient(180deg, rgba(243,250,239,0.98) 0%, rgba(255,255,255,0.96) 100%)"
                                : "linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(249,250,248,0.96) 100%)",
                              boxShadow: selected
                                ? "0 18px 40px rgba(83, 118, 72, 0.12)"
                                : "0 10px 28px rgba(83, 95, 105, 0.06)",
                              display: "grid",
                              gap: 0,
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={selected}
                              onChange={() => toggleCompletionOption(option)}
                              style={{ display: "none" }}
                            />
                            <div
                              style={{
                                position: "relative",
                                height: 164,
                                background:
                                  imageUrl
                                    ? `linear-gradient(180deg, rgba(19,31,37,0.06) 0%, rgba(19,31,37,0.3) 100%), url(${imageUrl}) center/cover`
                                    : "linear-gradient(135deg, rgba(241,206,159,0.75) 0%, rgba(158,201,205,0.72) 100%)",
                              }}
                            >
                              <div
                                style={{
                                  position: "absolute",
                                  inset: "auto 14px 14px 14px",
                                  display: "flex",
                                  justifyContent: "space-between",
                                  gap: 10,
                                  alignItems: "end",
                                }}
                              >
                                <div style={{ display: "grid", gap: 6 }}>
                                  <span
                                    style={{
                                      width: "fit-content",
                                      padding: "5px 10px",
                                      borderRadius: 999,
                                      backgroundColor: "rgba(255,255,255,0.84)",
                                      color: "#476055",
                                      fontSize: 12,
                                      fontWeight: 700,
                                    }}
                                  >
                                    {formatCompletionOptionType(option.type)}
                                  </span>
                                  <p
                                    style={{
                                      margin: 0,
                                      color: "#fffdfa",
                                      fontSize: 24,
                                      lineHeight: 1.05,
                                      fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
                                      textShadow: "0 2px 12px rgba(28, 27, 21, 0.35)",
                                    }}
                                  >
                                    {option.name}
                                  </p>
                                </div>
                                <div
                                  style={{
                                    width: 26,
                                    height: 26,
                                    borderRadius: "50%",
                                    backgroundColor: selected ? "#5f8f57" : "rgba(255,255,255,0.84)",
                                    color: selected ? "#ffffff" : "#5f6f67",
                                    display: "grid",
                                    placeItems: "center",
                                    fontSize: 14,
                                    fontWeight: 800,
                                  }}
                                >
                                  {selected ? "✓" : "+"}
                                </div>
                              </div>
                            </div>
                            <div style={{ padding: 16, display: "grid", gap: 8 }}>
                              <p style={{ margin: 0, color: "#65756d", fontSize: 13 }}>
                                {formatBlockTitle(option.suggested_block)}
                              </p>
                              <p style={{ margin: 0, color: "#415249", lineHeight: 1.55 }}>
                                {formatProductFacingReason(option.reasoning_summary)}
                              </p>
                              <p style={{ margin: 0, color: "#73817a", fontSize: 14, lineHeight: 1.55 }}>
                                {formatProductFacingReason(option.itinerary_relation_summary)}
                              </p>
                              <CompletionDecisionEvidenceList evidence={option.decision_evidence ?? null} />
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                ),
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
              <p style={{ margin: 0, color: "#6c7a74", fontSize: 14 }}>
                已选 {selectedCompletionOptionKeys.length} 个推荐点
              </p>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={() => setSelectedCompletionOptionKeys([])}
                  style={miniGhostButtonStyle}
                >
                  清空选择
                </button>
                <button
                  type="button"
                  onClick={applySelectedCompletionOptions}
                  disabled={selectedCompletionOptionKeys.length === 0}
                  style={primaryButtonStyle}
                >
                  加入当前旅行计划
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {sessionHydrated && travelModeModalOpen ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 60,
            background:
              "linear-gradient(180deg, rgba(20, 24, 29, 0.38) 0%, rgba(20, 24, 29, 0.52) 100%)",
            display: "grid",
            placeItems: "center",
            padding: 24,
          }}
        >
          <div
            style={{
              width: "min(760px, 100%)",
              borderRadius: 32,
              background: "linear-gradient(180deg, #fffaf4 0%, #f6f7f3 100%)",
              boxShadow: "0 30px 80px rgba(17, 24, 39, 0.22)",
              padding: 28,
              display: "grid",
              gap: 20,
            }}
          >
            <div style={{ display: "grid", gap: 8 }}>
              <p style={{ margin: 0, color: "#8b6c46", fontSize: 12, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                开始补全前
              </p>
              <h2
                style={{
                  margin: 0,
                  fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
                  fontSize: "clamp(2rem, 5vw, 3rem)",
                  lineHeight: 0.98,
                  color: "#1f2a21",
                }}
              >
                你这趟旅行大概怎么到达？
              </h2>
              <p style={{ margin: 0, color: "#617068", lineHeight: 1.6 }}>
                这会帮助系统把第一天开头排得更自然，而不是盲目塞地点。
              </p>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
                gap: 12,
              }}
            >
              {TRAVEL_MODE_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => {
                    setTravelMode(option.value);
                    setTravelModeModalOpen(false);
                  }}
                  style={{
                    border: "1px solid rgba(145, 157, 147, 0.18)",
                    borderRadius: 22,
                    padding: "18px 16px",
                    background: "rgba(255,255,255,0.82)",
                    display: "grid",
                    gap: 6,
                    textAlign: "left",
                    cursor: "pointer",
                  }}
                >
                  <span style={{ fontSize: 28 }}>{option.emoji}</span>
                  <span style={{ fontWeight: 700, color: "#233129" }}>{option.label}</span>
                  <span style={{ color: "#708078", fontSize: 13 }}>{option.description}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}

function ProductCard({
  title,
  subtitle,
  accent = "paper",
  label,
  children,
}: {
  title: string;
  subtitle?: string;
  accent?: "paper" | "sage" | "sand" | "atlas";
  label?: string;
  children: ReactNode;
}) {
  const accentStyles = {
    paper: {
      background: "linear-gradient(180deg, rgba(255,253,249,0.96) 0%, rgba(247,244,238,0.92) 100%)",
      border: "1px solid var(--ec-line)",
    },
    sage: {
      background: "linear-gradient(180deg, rgba(241,248,244,0.94) 0%, rgba(255,255,255,0.94) 100%)",
      border: "1px solid rgba(134, 154, 137, 0.16)",
    },
    sand: {
      background: "linear-gradient(180deg, rgba(252,247,238,0.95) 0%, rgba(255,255,255,0.94) 100%)",
      border: "1px solid rgba(196, 168, 123, 0.16)",
    },
    atlas: {
      background:
        "linear-gradient(180deg, rgba(255,253,249,0.98) 0%, rgba(247,244,238,0.94) 100%)",
      border: "1px solid rgba(177,138,88,0.18)",
    },
  }[accent];

  return (
    <section
      style={{
        position: "relative",
        overflow: "hidden",
        padding: 26,
        borderRadius: 32,
        display: "grid",
        gap: 20,
        boxShadow: "var(--ec-shadow-1)",
        backdropFilter: "blur(10px)",
        ...accentStyles,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          background:
            "linear-gradient(180deg, rgba(255,255,255,0.28) 0%, rgba(255,255,255,0) 28%)",
        }}
      />
      {label ? (
        <span
          style={{
            width: "fit-content",
            padding: "6px 10px",
            borderRadius: 999,
            background: "rgba(255,253,249,0.78)",
            border: "1px solid var(--ec-line)",
            color: accent === "sage" ? "var(--ec-moss)" : "var(--ec-ochre)",
            fontSize: 11,
            fontWeight: 900,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
          }}
        >
          {label}
        </span>
      ) : null}
      <div style={{ display: "grid", gap: 6 }}>
        <h3
          style={{
            margin: 0,
            fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
            fontSize: 28,
            lineHeight: 1.08,
            color: "#18212a",
          }}
        >
          {title}
        </h3>
        {subtitle ? (
          <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.65 }}>{subtitle}</p>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function SectionShell({ children }: { children: ReactNode }) {
  return (
    <section
      style={{
        position: "relative",
        marginBottom: 36,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: 34,
          background: "transparent",
          pointerEvents: "none",
        }}
      />
      <div style={{ position: "relative", padding: "6px 4px 2px" }}>{children}</div>
    </section>
  );
}

function StagePill({ label }: { label: string }) {
  return (
    <span
      style={{
        padding: "6px 10px",
        borderRadius: 999,
        background: "rgba(255,253,249,0.82)",
        border: "1px solid var(--ec-line)",
        color: "var(--ec-slate)",
        fontSize: 12,
        fontWeight: 700,
        letterSpacing: "0.02em",
      }}
    >
      {label}
    </span>
  );
}

type EditorialIntentPreview = {
  city: string;
  scopeLine: string;
  preferenceLine: string;
  arrivalLine: string;
};

function buildEditorialIntentPreview({
  city,
  tripDays,
  pacingProfile,
  fixedEventCount,
  preferencesText,
  arrivalAnchor,
}: {
  city: string | null;
  tripDays: string;
  pacingProfile: PacingProfile;
  fixedEventCount: number;
  preferencesText: string;
  arrivalAnchor: string;
}): EditorialIntentPreview {
  const normalizedPreferences = splitLines(preferencesText).slice(0, 4);
  const scopeFragments = [
    tripDays.trim() ? `${tripDays.trim()} 天` : "天数待估算",
    `${formatPacingProfileLabel(pacingProfile)}节奏`,
    fixedEventCount > 0 ? `${fixedEventCount} 个固定安排` : null,
  ].filter((value): value is string => value !== null);

  return {
    city: city?.trim() || "目的地待解析",
    scopeLine: scopeFragments.join(" · "),
    preferenceLine:
      normalizedPreferences.length > 0
        ? `偏好：${normalizedPreferences.join(" / ")}`
        : "偏好：本地小吃 / 老街 / 夜景 / 不要太赶",
    arrivalLine: `到达：${arrivalAnchor.trim() || "待补"}`,
  };
}

function EditorialHeroField({
  tripText,
  parsing,
  loading,
  advancedModeOpen,
  intentPreview,
  recoveryNotice,
  onTripTextChange,
  onSubmit,
  onToggleAdvancedMode,
}: {
  tripText: string;
  parsing: boolean;
  loading: boolean;
  advancedModeOpen: boolean;
  intentPreview: EditorialIntentPreview;
  recoveryNotice: string | null;
  onTripTextChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onToggleAdvancedMode: () => void;
}) {
  const generating = parsing || loading;
  const [generationProgress, setGenerationProgress] = useState(0);

  useEffect(() => {
    if (!generating) {
      setGenerationProgress(0);
      return;
    }

    setGenerationProgress((current) => Math.max(current, parsing ? 24 : 58));
    const interval = window.setInterval(() => {
      setGenerationProgress((current) => {
        const cap = loading ? 96 : 54;
        const step = loading ? 7 : 5;
        return Math.min(cap, current + step);
      });
    }, 420);

    return () => window.clearInterval(interval);
  }, [generating, loading, parsing]);

  const generationStage = loading
    ? generationProgress >= 96
      ? "骨架缓冲完成，等待路线返回"
      : "正在编排路线骨架"
    : parsing
      ? "正在理解旅行意图"
      : "生成旅行骨架";
  const generationDetail = loading
    ? "后端返回后会直接展开具体行程；若失败会显示可读原因"
    : parsing
      ? "目的地、偏好、固定安排和节奏正在被解析"
      : "先生成一条能继续补、换、移的路线";

  return (
    <div className="ec-editorial-left" style={{ display: "grid", alignContent: "space-between", gap: 34 }}>
      <div className="ec-editorial-copy" style={{ display: "grid", gap: 28, maxWidth: 540 }}>
        <div style={{ display: "grid", gap: 16 }}>
          <span
            className="ec-home-kicker"
            style={{
              width: "fit-content",
              color: "var(--ec-ochre)",
              fontSize: 12,
              fontWeight: 900,
              letterSpacing: "0.22em",
              textTransform: "uppercase",
            }}
          >
            路线骨架补全
          </span>
          <h1
            className="ec-home-title"
            style={{
              margin: 0,
              maxWidth: 520,
              color: "var(--ec-ink)",
              fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
              fontSize: "clamp(2.9rem, 4vw, 4.7rem)",
              lineHeight: 0.92,
              letterSpacing: "-0.075em",
            }}
          >
            把一句旅行想法，
            <br />
            编成可继续修改的路线。
          </h1>
          <p
            className="ec-home-lead"
            style={{
              margin: 0,
              maxWidth: 500,
              color: "var(--ec-slate)",
              fontSize: 17,
              lineHeight: 1.82,
            }}
          >
            系统会先读懂目的地、天数、偏好和固定安排，再交付一条可以继续补、换、移的旅行骨架。
          </p>
        </div>

        <form onSubmit={onSubmit} style={{ display: "grid", gap: 14 }}>
          <label
            className="ec-home-input-card"
            style={{
              display: "grid",
              gap: 14,
              padding: "18px 20px 20px",
              borderRadius: 30,
              background: "rgba(255,253,249,0.94)",
              border: "1px solid var(--ec-line)",
              boxShadow: "0 18px 44px rgba(21, 21, 21, 0.06)",
            }}
          >
            <span style={{ color: "var(--ec-slate)", fontSize: 12, fontWeight: 900, letterSpacing: "0.08em" }}>
              一句话先开工
            </span>
            <textarea
              className="ec-home-textarea"
              id="trip-text"
              aria-label="旅行需求"
              rows={5}
              value={tripText}
              onChange={(event) => onTripTextChange(event.target.value)}
              placeholder="例：周六下午到上海，想吃本地小吃、逛老街和夜景，周日下午三点有个预约，周日晚回去。不要太赶。"
              style={{
                width: "100%",
                minHeight: 152,
                resize: "vertical",
                border: "none",
                outline: "none",
                padding: 0,
                background: "transparent",
                color: "var(--ec-ink)",
                fontSize: 17,
                lineHeight: 1.78,
              }}
            />
            {recoveryNotice ? (
              <p
                role="status"
                style={{
                  margin: 0,
                  padding: "10px 12px",
                  borderLeft: "3px solid var(--ec-ochre)",
                  background: "rgba(177, 138, 88, 0.1)",
                  color: "var(--ec-ink-soft)",
                  fontSize: 14,
                  lineHeight: 1.55,
                }}
              >
                <strong style={{ color: "var(--ec-ink)" }}>请先修改这项行程信息：</strong>{recoveryNotice}
              </p>
            ) : null}
          </label>
          <div className="ec-home-actions" style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
            <button
              type="submit"
              disabled={generating}
              className={`ec-generate-buffer ${generating ? "ec-generate-buffer--active" : ""}`}
              style={editorialGenerateBufferButtonStyle}
            >
              <span style={editorialGenerateBufferToplineStyle}>
                <strong>{generationStage}</strong>
                <span>{generating ? `${generationProgress}%` : "就绪"}</span>
              </span>
              <span style={editorialGenerateBufferTrackStyle} aria-hidden="true">
                <span
                  style={{
                    ...editorialGenerateBufferFillStyle,
                    width: `${generating ? generationProgress : 0}%`,
                  }}
                />
              </span>
              <small style={editorialGenerateBufferHintStyle}>{generationDetail}</small>
            </button>
            <button type="button" onClick={onToggleAdvancedMode} style={editorialTextButtonStyle}>
              {advancedModeOpen ? "收起补充信息" : "补充到达 / 时间 / 偏好"}
            </button>
          </div>
        </form>
      </div>

      <aside
        style={{
          display: "grid",
          gap: 16,
          maxWidth: 480,
          paddingTop: 18,
          borderTop: "1px solid var(--ec-line)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <span style={{ color: "var(--ec-slate)", fontSize: 12, fontWeight: 900, letterSpacing: "0.14em" }}>
            意图解析
          </span>
          <span
            style={{
              width: 42,
              height: 1,
              background: "linear-gradient(90deg, var(--ec-ochre), transparent)",
            }}
          />
        </div>
        <div style={{ display: "grid", gap: 8 }}>
          <strong
            style={{
              color: "var(--ec-ink)",
              fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
              fontSize: 31,
              lineHeight: 1,
              letterSpacing: "-0.04em",
            }}
          >
            {intentPreview.city}
          </strong>
          <span style={{ color: "var(--ec-ink-soft)", fontSize: 16, fontWeight: 700 }}>
            {intentPreview.scopeLine}
          </span>
          <span style={{ color: "var(--ec-slate)", lineHeight: 1.65 }}>{intentPreview.preferenceLine}</span>
          <span style={{ color: "var(--ec-slate)", lineHeight: 1.65 }}>{intentPreview.arrivalLine}</span>
        </div>
      </aside>
    </div>
  );
}

function EditorialRouteSpine() {
  return (
    <aside className="ec-editorial-spine" aria-hidden="true" style={{ position: "relative" }}>
      <div
        style={{
          position: "absolute",
          inset: "0 50%",
          width: 1,
          transform: "translateX(-50%)",
          background:
            "linear-gradient(180deg, rgba(23,27,34,0) 0%, var(--ec-night) 12%, var(--ec-ochre) 48%, var(--ec-moss) 82%, rgba(102,113,95,0) 100%)",
        }}
      />
      {[
        { top: "10%", size: 14, fill: "var(--ec-night)" },
        { top: "35%", size: 10, fill: "var(--ec-ochre)" },
        { top: "62%", size: 16, fill: "var(--ec-paper-strong)" },
        { top: "84%", size: 10, fill: "var(--ec-moss)" },
      ].map((node) => (
        <span
          key={node.top}
          style={{
            position: "absolute",
            top: node.top,
            left: "50%",
            width: node.size,
            height: node.size,
            transform: "translate(-50%, -50%)",
            borderRadius: 999,
            background: node.fill,
            border: "2px solid var(--ec-paper-strong)",
            boxShadow: "0 0 0 1px rgba(21,21,21,0.12)",
          }}
        />
      ))}
      <span
        style={{
          position: "absolute",
          top: "48%",
          left: "50%",
          transform: "translate(-50%, -50%) rotate(-90deg)",
          color: "var(--ec-slate)",
          fontSize: 11,
          fontWeight: 900,
          letterSpacing: "0.28em",
          whiteSpace: "nowrap",
        }}
      >
        路线主轴
      </span>
    </aside>
  );
}

function EditorialRouteField() {
  return (
    <section
      className="ec-editorial-route"
      style={{
        display: "grid",
        alignContent: "space-between",
        gap: 22,
        padding: "28px 28px 26px",
        borderRadius: 40,
        background:
          "radial-gradient(circle at 88% 12%, rgba(102,113,95,0.16), transparent 28%), linear-gradient(180deg, rgba(255,253,249,0.98) 0%, rgba(247,244,238,0.96) 100%)",
        border: "1px solid var(--ec-line)",
        boxShadow: "0 24px 52px rgba(21,21,21,0.08)",
      }}
    >
      <div style={{ display: "grid", gap: 22 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "start" }}>
          <div style={{ display: "grid", gap: 6 }}>
            <span style={{ color: "var(--ec-slate)", fontSize: 12, fontWeight: 900, letterSpacing: "0.14em" }}>
              路线骨架
            </span>
            <strong
              style={{
                color: "var(--ec-ink)",
                fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
                fontSize: 36,
                lineHeight: 1,
                letterSpacing: "-0.05em",
              }}
            >
              DAY 1
            </strong>
          </div>
          <button type="button" style={editorialMiniButtonStyle}>
            编辑路线
          </button>
        </div>

        <div
          style={{
            position: "relative",
            display: "grid",
            gap: 10,
            paddingLeft: 30,
          }}
        >
          <span
            aria-hidden="true"
            style={{
              position: "absolute",
              top: 18,
              bottom: 18,
              left: 10,
              width: 2,
              background:
                "linear-gradient(180deg, var(--ec-night) 0%, var(--ec-ochre) 48%, var(--ec-moss) 100%)",
            }}
          />
          {[
            { tone: "night", label: "起点", title: "虹桥站", meta: "城市入口" },
            { tone: "paper", label: "景点", title: "武康路", meta: "第一站 · 32 分钟" },
            { tone: "ochre", label: "补全", title: "午餐锚点", meta: "系统建议 · 顺路补入" },
            { tone: "moss", label: "收口", title: "外滩", meta: "傍晚 · 适合接夜景" },
          ].map((stop) => (
            <div
              key={stop.title}
              style={{
                position: "relative",
                display: "grid",
                gridTemplateColumns: "auto minmax(0, 1fr)",
                gap: 14,
                alignItems: "center",
                padding: "14px 16px",
                borderRadius: 24,
                background: "rgba(255,253,249,0.9)",
                border: "1px solid var(--ec-line-soft)",
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  position: "absolute",
                  left: -26,
                  top: "50%",
                  width: 14,
                  height: 14,
                  transform: "translateY(-50%)",
                  borderRadius: 999,
                  background:
                    stop.tone === "night"
                      ? "var(--ec-night)"
                      : stop.tone === "ochre"
                        ? "var(--ec-ochre)"
                        : stop.tone === "moss"
                          ? "var(--ec-moss)"
                          : "var(--ec-paper-strong)",
                  border: "2px solid var(--ec-paper-strong)",
                  boxShadow: "0 0 0 1px rgba(21,21,21,0.14)",
                }}
              />
              <span
                style={{
                  minWidth: 52,
                  padding: "7px 10px",
                  borderRadius: 999,
                  background:
                    stop.tone === "ochre"
                      ? "rgba(239,229,214,0.74)"
                      : stop.tone === "moss"
                        ? "rgba(231,236,232,0.92)"
                        : "rgba(23,27,34,0.06)",
                  color:
                    stop.tone === "ochre"
                      ? "var(--ec-clay)"
                      : stop.tone === "moss"
                        ? "var(--ec-moss)"
                        : "var(--ec-ink-soft)",
                  fontSize: 12,
                  fontWeight: 900,
                  textAlign: "center",
                }}
              >
                {stop.label}
              </span>
              <div style={{ display: "grid", gap: 3 }}>
                <strong style={{ color: "var(--ec-ink)", fontSize: 18 }}>{stop.title}</strong>
                <span style={{ color: "var(--ec-slate)", fontSize: 14 }}>{stop.meta}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="ec-route-support-grid">
        <aside
          style={{
            display: "grid",
            gap: 12,
            alignContent: "start",
            padding: 18,
            borderRadius: 28,
            background: "rgba(239,229,214,0.56)",
            border: "1px solid rgba(177,138,88,0.14)",
          }}
        >
          <span style={{ color: "var(--ec-clay)", fontSize: 12, fontWeight: 900, letterSpacing: "0.14em" }}>
            补全任务
          </span>
          <strong style={{ color: "var(--ec-ink)", fontSize: 18 }}>14:00–17:00 偏空</strong>
          <span style={{ color: "var(--ec-slate)", lineHeight: 1.62 }}>建议补一个轻量地点，让骨架继续完整。</span>
          <span
            style={{
              width: "fit-content",
              padding: "8px 12px",
              borderRadius: 999,
              background: "var(--ec-night)",
              color: "#ffffff",
              fontSize: 13,
              fontWeight: 900,
            }}
          >
            补午餐
          </span>
        </aside>

        <aside
          style={{
            display: "grid",
            gap: 12,
            padding: 18,
            borderRadius: 28,
            background: "rgba(231,236,232,0.68)",
            border: "1px solid rgba(102,113,95,0.14)",
          }}
        >
          <span style={{ color: "var(--ec-moss)", fontSize: 12, fontWeight: 900, letterSpacing: "0.14em" }}>
            地点详情
          </span>
          <strong
            style={{
              color: "var(--ec-ink)",
              fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
              fontSize: 24,
              letterSpacing: "-0.03em",
            }}
          >
            外滩
          </strong>
          <span style={{ color: "var(--ec-ink-soft)", fontWeight: 800 }}>为什么放这里</span>
          <span style={{ color: "var(--ec-slate)", lineHeight: 1.62 }}>
            离前一站更顺路，也让第一天有自然收口。
          </span>
        </aside>
      </div>
    </section>
  );
}

function SavedTripResumeCard({
  onRestore,
  onStartNew,
}: {
  onRestore: () => void;
  onStartNew: () => void;
}) {
  return (
    <section
      style={{
        position: "relative",
        zIndex: 2,
        marginBottom: 26,
        padding: 20,
        borderRadius: 28,
        background:
          "linear-gradient(145deg, rgba(231,236,232,0.98) 0%, rgba(255,253,249,0.96) 100%)",
        border: "1px solid rgba(102, 113, 95, 0.14)",
        boxShadow: "var(--ec-shadow-1)",
        display: "grid",
        gap: 10,
      }}
    >
      <div style={{ display: "grid", gap: 4 }}>
        <p
          style={{
            margin: 0,
            color: "var(--ec-moss)",
            fontSize: 12,
            fontWeight: 800,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          已保存的旅行骨架
        </p>
        <p style={{ margin: 0, color: "var(--ec-ink)", fontWeight: 700, fontSize: 18 }}>
          你上次的旅行骨架还在，可以继续补全和微调。
        </p>
        <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.6 }}>
          已在本地保留路线结果、用户意图、节奏偏好和你通过替换表达出的喜好，下次可以继续围绕同一趟旅行往下优化。
        </p>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
        <button type="button" onClick={onRestore} style={primaryButtonStyle}>
          继续上次行程
        </button>
        <button type="button" onClick={onStartNew} style={secondaryButtonStyle}>
          开始新行程
        </button>
      </div>
    </section>
  );
}

function CompletionStatusCard({
  description,
  label,
  onNavigate,
  tone,
  value,
}: ResultCompletionStatusItem & {
  onNavigate?: () => void;
}) {
  const palette = {
    done: {
      background: "linear-gradient(180deg, rgba(239,248,233,0.94) 0%, rgba(255,255,255,0.9) 100%)",
      border: "rgba(112, 157, 96, 0.2)",
      dot: "#5f8f57",
      text: "#31483b",
    },
    watch: {
      background: "linear-gradient(180deg, rgba(255,248,237,0.96) 0%, rgba(255,255,255,0.9) 100%)",
      border: "rgba(210, 160, 82, 0.22)",
      dot: "#c8833a",
      text: "#6f4f1f",
    },
    info: {
      background: "linear-gradient(180deg, rgba(239,247,248,0.96) 0%, rgba(255,255,255,0.9) 100%)",
      border: "rgba(84, 143, 151, 0.2)",
      dot: "#4f9aa2",
      text: "#315964",
    },
  }[tone];

  return (
    <button
      type="button"
      onClick={onNavigate}
      disabled={!onNavigate}
      aria-label={onNavigate ? `查看${label}详情` : undefined}
      style={{
        display: "grid",
        gap: 8,
        width: "100%",
        textAlign: "left",
        padding: 14,
        borderRadius: 20,
        background: palette.background,
        border: `1px solid ${palette.border}`,
        boxShadow: "0 12px 28px rgba(15, 23, 42, 0.045)",
        cursor: onNavigate ? "pointer" : "default",
        appearance: "none",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
        <span
          style={{
            width: 9,
            height: 9,
            borderRadius: "50%",
            backgroundColor: palette.dot,
            boxShadow: `0 0 0 4px ${palette.dot}1f`,
          }}
        />
        <span
          style={{
            marginLeft: "auto",
            color: palette.text,
            fontSize: 12,
            fontWeight: 900,
          }}
        >
          {value}
        </span>
      </div>
      <div style={{ display: "grid", gap: 4 }}>
        <p style={{ margin: 0, color: "#22303a", fontSize: 14, fontWeight: 900 }}>
          {label}
        </p>
        <p style={{ margin: 0, color: "#667085", fontSize: 12, lineHeight: 1.55 }}>
          {description}
          {onNavigate ? (
            <span style={{ color: palette.text, fontWeight: 900 }}> 点击查看详情。</span>
          ) : null}
        </p>
      </div>
    </button>
  );
}

function resultGuideTargetStyle(
  highlighted: boolean,
  baseStyle: CSSProperties,
): CSSProperties {
  return {
    ...baseStyle,
    transition: "box-shadow 220ms ease, outline-color 220ms ease, background-color 220ms ease",
    outline: highlighted ? "2px solid rgba(200, 131, 58, 0.72)" : "2px solid transparent",
    outlineOffset: highlighted ? 4 : 0,
    boxShadow: highlighted
      ? "0 0 0 8px rgba(241, 202, 116, 0.18), 0 18px 46px rgba(139, 92, 43, 0.14)"
      : baseStyle.boxShadow,
  };
}

function ResultStatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "paper" | "sage" | "sand";
}) {
  const toneStyles = {
    paper: {
      background: "rgba(255,255,255,0.72)",
      border: "1px solid rgba(183, 191, 203, 0.18)",
    },
    sage: {
      background: "rgba(241,248,244,0.82)",
      border: "1px solid rgba(134, 154, 137, 0.16)",
    },
    sand: {
      background: "rgba(252,247,238,0.88)",
      border: "1px solid rgba(196, 168, 123, 0.16)",
    },
  }[tone];

  return (
    <div
      style={{
        padding: "16px 18px",
        borderRadius: 22,
        display: "grid",
        gap: 6,
        backdropFilter: "blur(10px)",
        ...toneStyles,
      }}
    >
      <p
        style={{
          margin: 0,
          color: "#7a8290",
          fontSize: 11,
          fontWeight: 800,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
        }}
      >
        {label}
      </p>
      <p style={{ margin: 0, color: "#1e2935", fontWeight: 700, lineHeight: 1.45 }}>
        {value}
      </p>
    </div>
  );
}

function ResultJourneyLine({
  verb,
  value,
  meta,
}: {
  verb: string;
  value: string;
  meta: string;
}) {
  return (
    <div
      style={{
        display: "grid",
        gap: 3,
        paddingTop: 8,
        borderTop: "1px solid rgba(183, 194, 205, 0.35)",
      }}
    >
      <p style={{ margin: 0, color: "#6d8594", fontSize: 13 }}>
        {verb}
      </p>
      <p
        style={{
          margin: 0,
          color: "#203947",
          fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
          fontSize: 24,
          lineHeight: 1.08,
        }}
      >
        {value}
      </p>
      <p style={{ margin: 0, color: "#718896", fontSize: 13 }}>{meta}</p>
    </div>
  );
}

function ExplainabilityCard({
  title,
  lines,
  tone,
}: {
  title: string;
  lines: string[];
  tone: "olive" | "sand" | "sea" | "neutral";
}) {
  const palette = {
    olive: {
      background: "rgba(241,247,242,0.88)",
      border: "rgba(123, 160, 127, 0.18)",
      title: "#4e6a51",
      body: "#66736b",
    },
    sand: {
      background: "rgba(255,247,237,0.9)",
      border: "rgba(206, 171, 111, 0.18)",
      title: "#8a6331",
      body: "#75634c",
    },
    sea: {
      background: "rgba(238,247,250,0.9)",
      border: "rgba(122, 171, 192, 0.18)",
      title: "#4c7484",
      body: "#657983",
    },
    neutral: {
      background: "rgba(255,253,249,0.86)",
      border: "var(--ec-line)",
      title: "var(--ec-ink-soft)",
      body: "var(--ec-slate)",
    },
  }[tone];

  return (
    <section
      style={{
        borderRadius: 22,
        padding: 16,
        background: palette.background,
        border: `1px solid ${palette.border}`,
        display: "grid",
        gap: 8,
      }}
    >
      <p
        style={{
          margin: 0,
          color: palette.title,
          fontWeight: 800,
          fontSize: 13,
          letterSpacing: "0.04em",
          textTransform: "uppercase",
        }}
      >
        {title}
      </p>
      {lines.map((line) => (
        <p key={line} style={{ margin: 0, color: palette.body, fontSize: 14, lineHeight: 1.6 }}>
          {line}
        </p>
      ))}
    </section>
  );
}

function PlannerRealismCard({
  plannerRealism,
}: {
  plannerRealism: PlannerRealismSummary;
}) {
  const unstable = plannerRealism.status !== "executable";
  const borderColor = unstable ? "rgba(185, 94, 63, 0.22)" : "rgba(123, 160, 127, 0.18)";
  const background = unstable
    ? "linear-gradient(180deg, rgba(255,246,241,0.92) 0%, rgba(255,255,255,0.82) 100%)"
    : "linear-gradient(180deg, rgba(239,248,235,0.9) 0%, rgba(255,255,255,0.82) 100%)";
  return (
    <section
      style={{
        display: "grid",
        gap: 10,
        padding: 14,
        borderRadius: 20,
        background,
        border: `1px solid ${borderColor}`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "start" }}>
        <div style={{ display: "grid", gap: 4 }}>
          <p style={{ margin: 0, color: unstable ? "#8a3f28" : "#3f6f45", fontSize: 12, fontWeight: 900 }}>
            {unstable ? "这版还不够稳" : "这版基本可执行"}
          </p>
          <p style={{ margin: 0, color: "#26382f", fontSize: 15, fontWeight: 900, lineHeight: 1.45 }}>
            {plannerRealism.headline}
          </p>
        </div>
        <span
          style={{
            padding: "5px 9px",
            borderRadius: 999,
            backgroundColor: unstable ? "rgba(185, 94, 63, 0.12)" : "rgba(123, 160, 127, 0.14)",
            color: unstable ? "#8a3f28" : "#3f6f45",
            fontSize: 11,
            fontWeight: 900,
            whiteSpace: "nowrap",
          }}
        >
          {plannerRealism.status === "unstable" ? "未稳" : plannerRealism.status === "needs_repair" ? "待修" : "可执行"}
        </span>
      </div>
      {plannerRealism.issues.length ? (
        <div style={{ display: "grid", gap: 7 }}>
          {plannerRealism.issues.slice(0, 3).map((issue) => (
            <p key={`${issue.code}-${issue.day ?? "trip"}-${issue.title}`} style={{ margin: 0, color: "#5f6f67", fontSize: 13, lineHeight: 1.55 }}>
              <strong style={{ color: "#31483b" }}>{issue.title}：</strong>
              {issue.detail}
            </p>
          ))}
        </div>
      ) : null}
      {plannerRealism.suggested_actions.length ? (
        <div style={{ display: "grid", gap: 6 }}>
          {plannerRealism.suggested_actions.slice(0, 2).map((action) => (
            <p key={action.action_id} style={{ margin: 0, color: "#6c533d", fontSize: 13, lineHeight: 1.45 }}>
              下一步：{action.label}
            </p>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function formatProductFacingReason(value: string): string {
  const normalized = value.trim().toLocaleLowerCase();
  if (!normalized) {
    return value;
  }
  const translated = value
    .replace(/\bDay\s*(\d+)\b/gi, "第 $1 天")
    .replace(/\bafternoon\b/gi, "下午")
    .replace(/\bevening\b/gi, "晚上")
    .replace(/\bmorning\b/gi, "上午")
    .replace(/\bmeal anchor\b/gi, "餐食锚点")
    .replace(/\blunch anchor\b/gi, "午餐锚点")
    .replace(/\bdinner anchor\b/gi, "晚餐锚点")
    .replace(/\blunch\b/gi, "午餐")
    .replace(/\bdinner\b/gi, "晚餐")
    .replace(/\bstop\b/gi, "地点")
    .replace(/\broute\b/gi, "路线")
    .replace(/补齐\s+第/g, "补齐第")
    .replace(/第\s+(\d+)\s+天/g, "第 $1 天")
    .replace(/第\s+(\d+)\s+天\s+(上午|下午|晚上)/g, "第 $1 天$2")
    .replace(/\s+的/g, "的");
  if (normalized.includes("auto-seeded from sparse city input")) {
    return normalized.includes("meal")
      ? "系统发现这一天缺少真实用餐停顿，建议先补一个顺路餐食点。"
      : "系统发现这一天停留点偏少，建议先补一个能串起路线的地点。";
  }
  if (normalized.includes("meal anchor") || normalized.includes("lunch") || normalized.includes("dinner")) {
    return translated;
  }
  if (!/[\u3400-\u9fff]/.test(translated) && /[a-z]{4,}/i.test(translated)) {
    if (normalized.includes("evening") || normalized.includes("night")) {
      return "建议补一个晚间收口活动，让当天不要太早结束。";
    }
    if (normalized.includes("route") || normalized.includes("distance") || normalized.includes("travel")) {
      return "建议先修正会影响顺路性的空缺，再继续做地点替换。";
    }
    return "建议先补齐当前路线里最影响成行的空缺。";
  }
  return translated;
}

function CompletionDecisionEvidenceList({
  evidence,
}: {
  evidence: CompletionDecisionEvidence | null;
}) {
  if (!evidence) {
    return null;
  }

  const rows = [
    ["为什么要补", formatProductFacingReason(evidence.why_gap_exists)],
    ["为什么适合", formatProductFacingReason(evidence.why_this_poi_fits)],
    ["取舍", formatProductFacingReason(evidence.alternatives_rejected)],
  ];

  return (
    <div
      style={{
        display: "grid",
        gap: 6,
        padding: "10px 12px",
        borderRadius: 16,
        background: "rgba(255,255,255,0.62)",
        border: "1px solid rgba(126, 151, 134, 0.16)",
      }}
    >
      {rows.map(([label, value]) => (
        <p
          key={`${label}-${value}`}
          style={{
            margin: 0,
            color: "#5f7168",
            fontSize: 12,
            lineHeight: 1.45,
          }}
        >
          <strong style={{ color: "#40564b" }}>{label}:</strong> {value}
        </p>
      ))}
    </div>
  );
}

function AmbientDetail({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        borderRadius: 18,
        padding: 14,
        background: "rgba(255,253,249,0.72)",
        border: "1px solid var(--ec-line-soft)",
        display: "grid",
        gap: 4,
      }}
    >
      <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 800 }}>
        {label}
      </p>
      <p style={{ margin: 0, color: "#23313d", lineHeight: 1.55 }}>{value}</p>
    </div>
  );
}

function resultDecisionCardStyle(tone: "sage" | "sand" | "sky"): CSSProperties {
  const toneStyles = {
    sage: {
      background: "linear-gradient(180deg, rgba(248,252,246,0.9) 0%, rgba(255,255,255,0.78) 100%)",
      border: "1px solid rgba(146, 176, 130, 0.14)",
    },
    sand: {
      background: "linear-gradient(180deg, rgba(255,249,240,0.92) 0%, rgba(255,255,255,0.82) 100%)",
      border: "1px solid rgba(188, 155, 92, 0.14)",
    },
    sky: {
      background: "linear-gradient(180deg, rgba(242,249,252,0.92) 0%, rgba(255,255,255,0.82) 100%)",
      border: "1px solid rgba(122, 171, 192, 0.14)",
    },
  }[tone];

  return {
    padding: 18,
    borderRadius: 24,
    display: "grid",
    gap: 10,
    boxShadow: "0 10px 28px rgba(31, 41, 55, 0.04)",
    ...toneStyles,
  };
}

function EditorialStamp({
  title,
  subtitle,
  tone,
}: {
  title: string;
  subtitle: string;
  tone: "sun" | "sea" | "olive";
}) {
  const palette = {
    sun: {
      background: "rgba(255,244,224,0.82)",
      border: "rgba(223, 181, 102, 0.26)",
      title: "#7f5d1d",
      body: "#866c45",
    },
    sea: {
      background: "rgba(235,246,250,0.82)",
      border: "rgba(113, 165, 190, 0.24)",
      title: "#386b82",
      body: "#617788",
    },
    olive: {
      background: "rgba(239,246,240,0.82)",
      border: "rgba(118, 154, 120, 0.24)",
      title: "#4d7050",
      body: "#66746b",
    },
  }[tone];

  return (
    <div
      style={{
        padding: "10px 12px",
        borderRadius: 18,
        background: palette.background,
        border: `1px solid ${palette.border}`,
        display: "grid",
        gap: 2,
        boxShadow: "0 10px 24px rgba(83, 92, 104, 0.06)",
      }}
    >
      <p style={{ margin: 0, color: palette.title, fontSize: 13, fontWeight: 800 }}>{title}</p>
      <p style={{ margin: 0, color: palette.body, fontSize: 12 }}>{subtitle}</p>
    </div>
  );
}

function CollageTicket({
  eyebrow,
  title,
  subtitle,
  tone,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  tone: "coral" | "sea";
}) {
  const palette =
    tone === "coral"
      ? {
          background:
            "linear-gradient(145deg, rgba(255,239,230,0.92) 0%, rgba(255,247,240,0.88) 100%)",
          border: "rgba(222, 145, 95, 0.22)",
          eyebrow: "#af5f3e",
          title: "#4a2f20",
          body: "#7b6558",
        }
      : {
          background:
            "linear-gradient(145deg, rgba(235,246,250,0.92) 0%, rgba(245,250,252,0.88) 100%)",
          border: "rgba(113, 165, 190, 0.22)",
          eyebrow: "#3d7388",
          title: "#243842",
          body: "#667884",
        };

  return (
    <div
      style={{
        padding: 16,
        borderRadius: 22,
        background: palette.background,
        border: `1px solid ${palette.border}`,
        display: "grid",
        gap: 6,
        boxShadow: "0 14px 28px rgba(84, 87, 92, 0.05)",
      }}
    >
      <p style={{ margin: 0, color: palette.eyebrow, fontSize: 11, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {eyebrow}
      </p>
      <p style={{ margin: 0, color: palette.title, fontWeight: 800, lineHeight: 1.3 }}>{title}</p>
      <p style={{ margin: 0, color: palette.body, fontSize: 13, lineHeight: 1.55 }}>{subtitle}</p>
    </div>
  );
}

function EditorialRibbon({
  title,
  body,
  tone,
}: {
  title: string;
  body: string;
  tone: "sand" | "sea" | "olive";
}) {
  const palette = {
    sand: {
      background: "linear-gradient(145deg, rgba(255,247,237,0.92) 0%, rgba(255,255,255,0.78) 100%)",
      border: "rgba(216, 180, 112, 0.18)",
      title: "#8a6030",
      body: "#7c6c57",
    },
    sea: {
      background: "linear-gradient(145deg, rgba(238,247,250,0.92) 0%, rgba(255,255,255,0.78) 100%)",
      border: "rgba(122, 171, 192, 0.18)",
      title: "#4e7889",
      body: "#677884",
    },
    olive: {
      background: "linear-gradient(145deg, rgba(241,247,242,0.92) 0%, rgba(255,255,255,0.78) 100%)",
      border: "rgba(124, 160, 127, 0.18)",
      title: "#587059",
      body: "#67736b",
    },
  }[tone];

  return (
    <div
      style={{
        padding: 16,
        borderRadius: 22,
        background: palette.background,
        border: `1px solid ${palette.border}`,
        display: "grid",
        gap: 4,
      }}
    >
      <p style={{ margin: 0, color: palette.title, fontWeight: 800 }}>{title}</p>
      <p style={{ margin: 0, color: palette.body, fontSize: 14, lineHeight: 1.55 }}>{body}</p>
    </div>
  );
}

function ResultRibbon({
  title,
  body,
  tone,
}: {
  title: string;
  body: string;
  tone: "sand" | "sea" | "olive";
}) {
  return <EditorialRibbon title={title} body={body} tone={tone} />;
}

function PostcardNote({
  title,
  lines,
}: {
  title: string;
  lines: string[];
}) {
  return (
    <div
      style={{
        padding: "14px 16px",
        borderRadius: 22,
        background: "rgba(255,250,244,0.8)",
        boxShadow: "0 16px 30px rgba(70, 74, 81, 0.08)",
        display: "grid",
        gap: 6,
        maxWidth: 180,
        transform: "rotate(3deg)",
      }}
    >
      <p style={{ margin: 0, color: "#9a6544", fontSize: 11, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {title}
      </p>
      <div style={{ display: "grid", gap: 3 }}>
        {lines.map((line) => (
          <p key={line} style={{ margin: 0, color: "#535e67", fontSize: 13, lineHeight: 1.45 }}>
            {line}
          </p>
        ))}
      </div>
    </div>
  );
}

function LuggageTag({
  title,
  value,
}: {
  title: string;
  value: string;
}) {
  return (
    <div
      style={{
        position: "relative",
        padding: "14px 16px 14px 22px",
        borderRadius: 20,
        background: "rgba(255,248,239,0.78)",
        boxShadow: "0 16px 28px rgba(84, 76, 58, 0.08)",
        display: "grid",
        gap: 4,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 10,
          top: 18,
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: "#5d8793",
        }}
      />
      <p style={{ margin: 0, color: "#8a6237", fontSize: 11, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {title}
      </p>
      <p style={{ margin: 0, color: "#43515a", fontSize: 14, lineHeight: 1.5 }}>{value}</p>
    </div>
  );
}

function FieldBlock({
  label,
  helper,
  children,
}: {
  label: string;
  helper?: string;
  children: ReactNode;
}) {
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "grid", gap: 4 }}>
        <label style={labelStyle}>{label}</label>
        {helper ? (
          <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13, lineHeight: 1.5 }}>{helper}</p>
        ) : null}
      </div>
      {children}
    </div>
  );
}

function SoftInfoCard({
  title,
  lines,
  tone = "neutral",
}: {
  title: string;
  lines: string[];
  tone?: "neutral" | "success" | "warning";
}) {
  const palette = {
    neutral: {
      background: "rgba(255,253,249,0.9)",
      border: "var(--ec-line)",
      title: "var(--ec-ink-soft)",
      body: "var(--ec-slate)",
    },
    success: {
      background: "#f6fbf7",
      border: "rgba(47, 111, 62, 0.15)",
      title: "#2f6f3e",
      body: "#556b5c",
    },
    warning: {
      background: "#fffaf2",
      border: "rgba(138, 90, 0, 0.16)",
      title: "#8a5a00",
      body: "#73614a",
    },
  }[tone];

  return (
    <section
      style={{
        borderRadius: 18,
        padding: 16,
        backgroundColor: palette.background,
        border: `1px solid ${palette.border}`,
        display: "grid",
        gap: 6,
      }}
    >
      <p style={{ margin: 0, fontWeight: 700, color: palette.title }}>{title}</p>
      {lines.map((line) => (
        <p key={line} style={{ margin: 0, color: palette.body, fontSize: 14, lineHeight: 1.55 }}>
          {line}
        </p>
      ))}
    </section>
  );
}

function InlineMessage({
  tone,
  title,
  body,
  prominent = false,
}: {
  tone: "error";
  title: string;
  body: string;
  prominent?: boolean;
}) {
  return (
    <section
      style={{
        marginBottom: prominent ? 24 : 0,
        padding: 16,
        border: "1px solid #f1c0c0",
        borderRadius: 16,
        backgroundColor: "#fff7f7",
        display: "grid",
        gap: 8,
      }}
    >
      <p style={{ margin: 0, color: "#8a1c1c", fontWeight: 700 }}>{title}</p>
      <p style={{ margin: 0, color: "#7a3b3b", fontSize: 14, lineHeight: 1.55 }}>{body}</p>
    </section>
  );
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        borderRadius: 18,
        padding: "14px 16px",
        background: "rgba(255,253,249,0.78)",
        border: "1px solid var(--ec-line-soft)",
        display: "grid",
        gap: 5,
      }}
    >
      <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 12, textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 800 }}>
        {label}
      </p>
      <p style={{ margin: 0, color: "var(--ec-ink)", fontWeight: 800, lineHeight: 1.35 }}>{value}</p>
    </div>
  );
}

function InfoStrip({ title, content }: { title: string; content: string }) {
  return (
    <div
      style={{
        display: "grid",
        gap: 4,
        paddingBottom: 12,
        borderBottom: "1px solid var(--ec-line-soft)",
      }}
    >
      <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 13, fontWeight: 800 }}>{title}</p>
      <p style={{ margin: 0, color: "var(--ec-ink-soft)", lineHeight: 1.65 }}>{content}</p>
    </div>
  );
}

function BriefPreviewCard({ viewModel }: { viewModel: BriefPreviewCardViewModel }) {
  return (
    <ProductCard title={viewModel.title} accent="paper" label="Brief">
      <div style={summaryGridStyle}>
        {viewModel.stats.map((stat) => (
          <SummaryStat
            key={`brief-preview-stat-${stat.label}`}
            label={stat.label}
            value={stat.value}
          />
        ))}
      </div>
      <div style={{ display: "grid", gap: 12 }}>
        {viewModel.strips.map((strip) => (
          <InfoStrip
            key={`brief-preview-strip-${strip.title}`}
            title={strip.title}
            content={strip.content}
          />
        ))}
      </div>
    </ProductCard>
  );
}

function PlanningInterpretationCard({
  viewModel,
}: {
  viewModel: PlanningInterpretationCardViewModel;
}) {
  return (
    <ProductCard
      title={viewModel.title}
      subtitle="系统已把一句话拆成天数、时间状态、固定安排与偏好强度。"
      accent="sage"
      label="Parsed intent"
    >
      <div style={summaryGridStyle}>
        {viewModel.stats.map((stat) => (
          <SummaryStat
            key={`planning-interpretation-stat-${stat.label}`}
            label={stat.label}
            value={stat.value}
          />
        ))}
      </div>
      <div style={{ display: "grid", gap: 12 }}>
        {viewModel.strips.map((strip) => (
          <InfoStrip
            key={`planning-interpretation-strip-${strip.title}`}
            title={strip.title}
            content={strip.content}
          />
        ))}
      </div>
    </ProductCard>
  );
}

function buildPlanningInterpretationCardViewModel(
  planningState: PlanningInputState,
): PlanningInterpretationCardViewModel {
  const readiness = getPlanningStateReadinessAssessment(planningState);

  return {
    title: "生成前旅行骨架解析",
    stats: [
      {
        label: "准备度",
        value: formatStateLabel(readiness.level),
      },
      {
        label: "能否补全",
        value: readiness.can_generate ? "可以" : "还需要一个线索",
      },
      {
        label: "时间状态",
        value: formatStateLabel(planningState.time_state),
      },
      {
        label: "地点状态",
        value: formatStateLabel(planningState.poi_state),
      },
      {
        label: "固定安排",
        value: formatStateLabel(planningState.fixed_event_state),
      },
      {
        label: "偏好强度",
        value: `${formatStateLabel(planningState.preference_state.mode)} · ${formatStateLabel(planningState.preference_state.strength)}`,
      },
      {
        label: "行程范围",
        value: `${planningState.trip_scope_estimate.estimated_trip_days} 天 · ${formatStateLabel(planningState.trip_scope_estimate.estimation_mode)}`,
      },
      {
        label: "置信度",
        value: formatStateLabel(planningState.trip_scope_estimate.confidence),
      },
    ],
    strips: [
      {
        title: "能否开始补全",
        content: readiness.summary,
      },
      {
        title: "现在生成会采用的自动假设",
        content: formatList(readiness.auto_assumptions),
      },
      {
        title: "想让骨架更准可以补充",
        content: formatList(readiness.clarification_questions),
      },
      {
        title: "当前待补线索",
        content: formatReadinessIssues(readiness.issues),
      },
      {
        title: "真实地点消歧",
        content: formatDisambiguationSummary(planningState.disambiguation_summary ?? null),
      },
      {
        title: "解析出的偏好",
        content: formatList(planningState.preference_state.extracted_preferences),
      },
      {
        title: "为什么这个天数范围合理",
        content: planningState.trip_scope_estimate.reasoning_summary,
      },
      {
        title: "可用时间理解",
        content:
          planningState.availability_windows.length > 0
            ? formatAvailabilityWindows(planningState.availability_windows)
            : "没有明确时间窗口",
      },
    ],
  };
}

function getPlanningStateReadinessAssessment(
  planningState: PlanningInputState,
): IntentReadinessAssessment {
  if (planningState.readiness) {
    return planningState.readiness;
  }

  return {
    level: "needs_assumption",
    can_generate: true,
    issue_count: 1,
    issues: [
      {
        code: "legacy_session_without_readiness",
        severity: "info",
        message:
          "这份恢复的本地行程创建于新版准备度摘要之前。",
        can_auto_assume: true,
      },
    ],
    auto_assumptions: ["使用恢复出的解析状态作为当前旅行计划。"],
    clarification_questions: [],
    summary:
      "这份已保存行程仍可继续补全，但不包含新版准备度摘要。",
  };
}

function formatReadinessIssues(issues: IntentReadinessIssue[]): string {
  if (issues.length === 0) {
    return "没有阻塞问题";
  }

  return issues
    .map((issue) => `${formatStateLabel(issue.severity)} · ${issue.message}`)
    .join(" / ");
}

function formatDisambiguationSummary(summary: IntentDisambiguationSummary | null): string {
  if (!summary) {
    return "本次还没有运行真实地点消歧";
  }

  const placeLines = summary.place_resolutions.map((resolution) => {
    const candidateText =
      resolution.candidate_names.length > 0
        ? ` 候选：${resolution.candidate_names.slice(0, 3).join("、")}`
        : "";
    return `${resolution.input_name} → ${resolution.resolved_name} (${formatStateLabel(resolution.confidence)} · ${formatStateLabel(resolution.source)})${candidateText}`;
  });
  const cityLine = summary.resolved_city
    ? `城市范围：${summary.resolved_city}（${formatStateLabel(summary.city_source)}）`
    : "城市范围尚未解析";
  const warningLines = summary.warnings.map((warning) => `提示：${warning}`);
  return [cityLine, ...placeLines, ...warningLines].join(" / ");
}

function buildQuickPreviewSectionHeaderViewModel(options: {
  isCurrentRegenerateBrief: boolean;
  hasFollowUpInterpretation: boolean;
}): SectionHeaderViewModel {
  if (options.isCurrentRegenerateBrief) {
    return {
      eyebrow: "当前旅行计划",
      title: "下一次补全会沿用这份旅行意图",
      description:
        options.hasFollowUpInterpretation
          ? "这里展示当前旅行计划，以及最近一句补充要求改动了什么，保证预览、补充信息和下一次请求都围绕同一份旅行骨架滚动。"
          : "这里展示当前旅行计划，保证预览、补充信息和下一次请求都围绕同一份旅行骨架滚动。",
    };
  }

  return {
    eyebrow: "生成前预览",
    title: "你的自然语言想法已经被整理成旅行骨架",
    description:
      "这里展示系统对原始一句话的解析：目的地、种草点、时间约束和节奏偏好会先被整理，再进入确定性的行程补全。",
  };
}

function buildAdvancedReviewSectionHeaderViewModel(options: {
  hasRegenerationIntent: boolean;
  hasFollowUpInterpretation: boolean;
}): SectionHeaderViewModel {
  if (options.hasRegenerationIntent) {
    return {
      eyebrow: "当前旅行计划",
      title: options.hasFollowUpInterpretation
        ? "补充信息已同步当前计划和最近补充要求的改动"
        : "补充信息已同步下一次补全真正会使用的计划",
    };
  }

  return {
    eyebrow: "生成前确认",
    title: "这份旅行想法已经可以进入骨架补全",
  };
}

function buildFollowUpInterpretationDisplayLinesForCard(
  interpretation: FollowUpInterpretationSummary,
): string[] {
  return [
    ...interpretation.summary_lines,
    interpretation.added_fixed_events.length > 0
      ? `固定安排：${formatFixedEventSummary(interpretation.added_fixed_events)}`
      : null,
    interpretation.added_availability_windows.length > 0
      ? `可用时间：${formatAvailabilityWindows(interpretation.added_availability_windows)}`
      : null,
  ]
    .filter((line): line is string => Boolean(line))
    .slice(0, 4);
}

function buildFollowUpInterpretationCardViewModel(
  interpretation: FollowUpInterpretationSummary,
): FollowUpInterpretationCardViewModel {
  const removalCount =
    interpretation.removed_scenic_spots.length + interpretation.removed_restaurants.length;
  const additionCount =
    interpretation.added_scenic_spots.length + interpretation.added_restaurants.length;
  return {
    title: "最近这句补充要求改了什么",
    stats: [
      { label: "新增地点", value: String(additionCount) },
      { label: "移除地点", value: String(removalCount) },
      { label: "固定安排", value: String(interpretation.added_fixed_events.length) },
      { label: "可用时间", value: String(interpretation.added_availability_windows.length) },
      {
        label: "行程天数",
        value:
          interpretation.pinned_trip_days !== null
            ? `固定为 ${interpretation.pinned_trip_days} 天`
            : "未变化",
      },
      {
        label: "目的地",
        value: interpretation.destination_changed_to ?? "未变化",
      },
    ],
    strips: [
      { title: "用户补充的原句", content: interpretation.raw_text },
      {
        title: "新增到当前计划的地点",
        content: formatList([
          ...interpretation.added_scenic_spots,
          ...interpretation.added_restaurants,
        ]),
      },
      {
        title: "从当前计划移除",
        content: formatList([
          ...interpretation.removed_scenic_spots,
          ...interpretation.removed_restaurants,
        ]),
      },
      {
        title: "系统如何理解这句话",
        content: formatList(buildFollowUpInterpretationDisplayLinesForCard(interpretation)),
      },
    ],
  };
}

function RegenerationSemanticsCard({
  assumptions,
  regenerationIntent,
  compileSummary,
}: {
  assumptions: PlanningAssumptionSummary;
  regenerationIntent: RegenerationIntentSummary;
  compileSummary?: TripIntentCompileSummary | null;
}) {
  const viewModel = buildRegenerationSemanticsCardViewModel(
    assumptions,
    regenerationIntent,
    compileSummary ?? null,
  );

  return (
    <ProductCard title="当前旅行计划" accent="sage">
      <div style={summaryGridStyle}>
        {viewModel.stats.map((stat) => (
          <SummaryStat
            key={`regeneration-semantics-stat-${stat.label}`}
            label={stat.label}
            value={stat.value}
          />
        ))}
      </div>
      <div style={{ display: "grid", gap: 12 }}>
        {viewModel.strips.map((strip) => (
          <InfoStrip
            key={`regeneration-semantics-strip-${strip.title}`}
            title={strip.title}
            content={strip.content}
          />
        ))}
      </div>
    </ProductCard>
  );
}

function FollowUpInterpretationCard({
  interpretation,
}: {
  interpretation: FollowUpInterpretationSummary;
}) {
  const viewModel = buildFollowUpInterpretationCardViewModel(interpretation);

  return (
    <ProductCard title={viewModel.title} accent="sand">
      <div style={summaryGridStyle}>
        {viewModel.stats.map((stat) => (
          <SummaryStat
            key={`follow-up-interpretation-stat-${stat.label}`}
            label={stat.label}
            value={stat.value}
          />
        ))}
      </div>
      <div style={{ display: "grid", gap: 12 }}>
        {viewModel.strips.map((strip) => (
          <InfoStrip
            key={`follow-up-interpretation-strip-${strip.title}`}
            title={strip.title}
            content={strip.content}
          />
        ))}
      </div>
    </ProductCard>
  );
}

function buildRegenerationSemanticsCardViewModel(
  assumptions: PlanningAssumptionSummary,
  regenerationIntent: RegenerationIntentSummary,
  compileSummary: TripIntentCompileSummary | null,
): {
  stats: Array<{ label: string; value: string }>;
  strips: Array<{ title: string; content: string }>;
} {
  return {
    stats: [
      {
        label: "行程范围",
        value: formatRegenerationScopeSummaryForCard(regenerationIntent),
      },
      {
        label: "天数估算",
        value: assumptions.trip_scope_estimate
          ? `${assumptions.trip_scope_estimate.estimated_trip_days} 天 · ${formatStateLabel(assumptions.trip_scope_estimate.confidence)}`
          : "暂无",
      },
      {
        label: "可排地点",
        value: String(
          compileSummary
            ? compileSummary.scenic_seed_count + compileSummary.restaurant_seed_count
            : regenerationIntent.carry_forward_scenic_spots.length +
                regenerationIntent.carry_forward_restaurants.length,
        ),
      },
      {
        label: "固定安排",
        value: String(compileSummary?.fixed_event_count ?? regenerationIntent.fixed_events.length),
      },
      {
        label: "用户反馈",
        value: formatCompileFeedbackSummaryForCard(compileSummary, regenerationIntent),
      },
      {
        label: "自动起步点",
        value: String(
          assumptions.auto_seeded_poi_count + assumptions.auto_seeded_meal_count,
        ),
      },
      {
        label: "自动补齐",
        value: String(assumptions.auto_filled_count),
      },
      {
        label: "偏好来源",
        value: formatStylePreferenceSourceSummaryForCard(
          regenerationIntent.style_preference_sources,
        ),
      },
    ],
    strips: [
      {
        title: "会继续带入的地点",
        content: formatList(regenerationIntent.carry_forward_scenic_spots),
      },
      {
        title: "会继续带入的餐食",
        content: formatList(regenerationIntent.carry_forward_restaurants),
      },
      {
        title: "为什么下一次补全会这样理解",
        content: formatList(assumptions.summary_lines),
      },
      {
        title: "旅行意图编译摘要",
        content: formatList(compileSummary?.summary_lines ?? []),
      },
      {
        title: "为什么这个行程范围合理",
        content:
          assumptions.trip_scope_estimate?.reasoning_summary ??
          "当前没有单独的天数估算说明。",
      },
      {
        title: "继续补全备注",
        content: formatList(regenerationIntent.notes),
      },
    ],
  };
}

function formatRegenerationScopeSummaryForCard(
  regenerationIntent: RegenerationIntentSummary,
): string {
  if (regenerationIntent.trip_days !== null) {
    return `${regenerationIntent.trip_days} 天 · 用户明确给出`;
  }
  return `${regenerationIntent.suggested_trip_days} 天 · 系统按当前计划估算`;
}

function formatCompileFeedbackSummaryForCard(
  compileSummary: TripIntentCompileSummary | null,
  regenerationIntent: RegenerationIntentSummary,
): string {
  const rejectedCount =
    compileSummary?.rejected_poi_count ??
    regenerationIntent.rejected_scenic_spots.length +
      regenerationIntent.rejected_restaurants.length;
  const confirmedCount =
    compileSummary?.confirmed_replacement_count ??
    regenerationIntent.confirmed_replacements.length;
  if (rejectedCount === 0 && confirmedCount === 0) {
    return "暂无替换反馈";
  }
  return [
    rejectedCount > 0 ? `${rejectedCount} 个已拒绝` : null,
    confirmedCount > 0 ? `${confirmedCount} 个已确认` : null,
  ]
    .filter((value): value is string => value !== null)
    .join(" · ");
}

function formatStylePreferenceSourceSummaryForCard(
  sources: Record<string, string>,
): string {
  const values = Object.values(sources);
  if (values.length === 0) {
    return "暂无偏好信号";
  }
  const explicitCount = values.filter((value) => value === "explicit").length;
  const inferredCount = values.filter((value) => value === "inferred").length;
  return [
    explicitCount > 0 ? `${explicitCount} 个显式` : null,
    inferredCount > 0 ? `${inferredCount} 个行为推断` : null,
  ]
    .filter((value): value is string => value !== null)
    .join(" · ");
}

const labelStyle: CSSProperties = {
  fontSize: 14,
  fontWeight: 700,
  color: "var(--ec-ink-soft)",
};

const inputStyle: CSSProperties = {
  width: "100%",
  padding: "14px 15px",
  borderRadius: 16,
  border: "1px solid rgba(15, 23, 42, 0.1)",
  backgroundColor: "#ffffff",
  fontSize: 15,
  color: "var(--ec-ink)",
  boxShadow: "inset 0 1px 0 rgba(255,255,255,0.72)",
};

const textareaStyle: CSSProperties = {
  ...inputStyle,
  minHeight: 120,
  resize: "vertical",
};

const heroTextareaStyle: CSSProperties = {
  ...textareaStyle,
  minHeight: 168,
  backgroundColor: "#ffffff",
  border: "none",
  padding: 0,
  fontSize: 16,
  lineHeight: 1.7,
};

const editorialGenerateBufferButtonStyle: CSSProperties = {
  minWidth: 272,
  display: "grid",
  gap: 8,
  border: "none",
  borderRadius: 26,
  padding: "14px 18px 15px",
  background: "var(--ec-night)",
  color: "#ffffff",
  cursor: "pointer",
  boxShadow: "0 18px 38px rgba(23, 27, 34, 0.2)",
  textAlign: "left",
};

const editorialGenerateBufferToplineStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: 18,
  alignItems: "center",
  fontSize: 14,
  fontWeight: 900,
};

const editorialGenerateBufferTrackStyle: CSSProperties = {
  position: "relative",
  height: 5,
  overflow: "hidden",
  borderRadius: 999,
  background: "rgba(255,255,255,0.2)",
};

const editorialGenerateBufferFillStyle: CSSProperties = {
  position: "absolute",
  insetBlock: 0,
  left: 0,
  borderRadius: 999,
  background: "linear-gradient(90deg, #f4d9a5, #ffffff)",
  transition: "width 420ms cubic-bezier(0.2, 0.8, 0.2, 1)",
};

const editorialGenerateBufferHintStyle: CSSProperties = {
  color: "rgba(255,255,255,0.72)",
  fontSize: 12,
  lineHeight: 1.45,
  fontWeight: 700,
};

const editorialTextButtonStyle: CSSProperties = {
  border: "none",
  background: "transparent",
  color: "var(--ec-ink-soft)",
  fontSize: 15,
  fontWeight: 900,
  padding: 0,
  cursor: "pointer",
  borderBottom: "1px solid rgba(21,21,21,0.22)",
};

const editorialMiniButtonStyle: CSSProperties = {
  border: "1px solid var(--ec-line)",
  borderRadius: 999,
  padding: "10px 14px",
  background: "rgba(255,253,249,0.92)",
  color: "var(--ec-ink-soft)",
  fontSize: 13,
  fontWeight: 900,
  cursor: "pointer",
};

const homeInlineActionStyle: CSSProperties = {
  border: "none",
  background: "transparent",
  color: "var(--ec-ink)",
  fontSize: 12,
  fontWeight: 900,
  cursor: "pointer",
  padding: 0,
};

const primaryButtonStyle: CSSProperties = {
  border: "none",
  borderRadius: 999,
  padding: "13px 20px",
  background: "var(--ec-night)",
  color: "#ffffff",
  fontWeight: 700,
  cursor: "pointer",
  boxShadow: "0 16px 32px rgba(21, 21, 21, 0.18)",
};

const secondaryButtonStyle: CSSProperties = {
  border: "1px solid var(--ec-line)",
  borderRadius: 999,
  padding: "11px 16px",
  backgroundColor: "rgba(255,253,249,0.92)",
  color: "var(--ec-ink)",
  fontWeight: 700,
  cursor: "pointer",
};

const floatingPrimaryButtonStyle: CSSProperties = {
  border: "none",
  borderRadius: 999,
  padding: "13px 20px",
  background: "var(--ec-night)",
  color: "#ffffff",
  fontWeight: 800,
  cursor: "pointer",
  boxShadow: "0 16px 32px rgba(21, 21, 21, 0.18)",
};

const miniGhostButtonStyle: CSSProperties = {
  border: "1px solid var(--ec-line)",
  borderRadius: 999,
  padding: "8px 12px",
  backgroundColor: "rgba(255,253,249,0.92)",
  color: "var(--ec-ink-soft)",
  fontWeight: 700,
  cursor: "pointer",
};

const inlineTextButtonStyle: CSSProperties = {
  border: "none",
  padding: 0,
  background: "transparent",
  color: "var(--ec-ink-soft)",
  fontWeight: 800,
  cursor: "pointer",
};

const sectionEyebrowStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ochre)",
  fontSize: 12,
  fontWeight: 800,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
};

const sectionHeadingStyle: CSSProperties = {
  margin: 0,
  fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
  fontSize: 42,
  lineHeight: 1.08,
  color: "var(--ec-ink)",
};

const summaryGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
  gap: 12,
};

function isFixedEventAvailabilityConflict(message: string): boolean {
  return message.includes("conflicts with applied availability");
}

function buildItineraryValueSummary(
  itinerary: ItineraryResponse,
  context: GenerationContext,
  committedSwaps: CommittedSwapSelection[],
): {
  fromInputLines: string[];
  completedLines: string[];
  whyLines: string[];
} {
  const userProvidedNames = new Set([
    ...context.scenic_spots.map(normalizeComparisonName),
    ...context.restaurants.map(normalizeComparisonName),
    ...context.fixed_events.map((event) => normalizeComparisonName(event.name)),
  ]);
  const scheduledItems = itinerary.days.flatMap((day) => getOrderedDayItems(day));
  const committedCount = committedSwaps.length;
  const userSelectedCount = scheduledItems.filter((item) =>
    userProvidedNames.has(normalizeComparisonName(item.name)),
  ).length;
  const fixedCount = scheduledItems.filter((item) => item.is_fixed).length;
  const flexibleCount = scheduledItems.filter((item) => !item.is_fixed).length;
  const autoSeededItems = scheduledItems.filter(isAutoSeededScheduledItem);
  const autoSeededMealCount =
    itinerary.planning_assumptions?.auto_seeded_meal_count ??
    autoSeededItems.filter((item) => item.type === "restaurant").length;
  const autoSeededPoiCount =
    itinerary.planning_assumptions?.auto_seeded_poi_count ??
    autoSeededItems.filter((item) => item.type === "scenic").length;
  const autoFilledScheduledCount = scheduledItems.filter((item) => {
    const normalizedName = normalizeComparisonName(item.name);
    return (
      !item.is_fixed &&
      !item.local_edit &&
      !isAutoSeededScheduledItem(item) &&
      (isAutoFilledScheduledItem(item) || !userProvidedNames.has(normalizedName))
    );
  }).length;
  const effectiveAutoFilledCount =
    itinerary.planning_assumptions?.auto_filled_count ?? autoFilledScheduledCount;
  const optionalPlaceCount = itinerary.completion_recommendation?.options.length ?? 0;
  const sparseDayCount = itinerary.completion_recommendation?.sparse_days.length ?? 0;
  const completedCategoryLabels = getCompletionCategoryLabels(itinerary);
  const preferencePreview = context.preferences.slice(0, 3).join(", ");
  const tripScopeLine = buildTripScopeOwnershipLine(context, itinerary.trip_days);
  const inputConstraintLines = buildInputConstraintOwnershipLines(context, itinerary);
  const seedInputLine =
    context.scenic_spots.length + context.restaurants.length > 0
      ? `${context.city ? `系统已把 ${context.city} 理解为目的地，` : ""}${context.scenic_spots.length} 个想去地点和 ${context.restaurants.length} 个餐食线索会被优先带入路线。`
      : `${context.city ? `系统已把 ${context.city} 理解为目的地。` : ""}你没有强行指定必去点，系统会用城市、偏好和约束作为旅行骨架的起点。`;

  const fromInputLines = [
    seedInputLine,
    tripScopeLine,
    ...inputConstraintLines,
    context.arrival_anchor || context.departure_anchor
      ? `已理解到达/离开边界：${[
          context.arrival_anchor ? `从 ${context.arrival_anchor} 到达` : null,
          context.departure_anchor ? `从 ${context.departure_anchor} 离开` : null,
        ]
          .filter((line): line is string => line !== null)
          .join(" · ")}。`
      : `骨架起点：${formatPlanningAnchorSourceType(itinerary.planning_anchor_source.source_type)} · ${itinerary.planning_anchor_source.source_name}。`,
    `当前启用${formatPacingProfileLabel(context.pacing_profile)}节奏，所以行程密度会参与补全，而不是最后才修文案。`,
    preferencePreview
      ? `继续保留的偏好线索：${preferencePreview}${context.preferences.length > 3 ? "…" : ""}。`
      : "没有额外套用隐藏攻略模板，只按你给出的计划补全。",
  ];

  const completedLines = [
    autoSeededPoiCount + autoSeededMealCount > 0
      ? `为了把稀疏输入变成可走骨架，系统自动补了 ${autoSeededPoiCount} 个起步地点和 ${autoSeededMealCount} 个餐食锚点。`
      : "不需要城市起步补点，这条路线主要从你提供的地点展开。",
    effectiveAutoFilledCount > 0
      ? `${effectiveAutoFilledCount} 个已排入行程的停留点来自系统补齐，用来让空缺时间段真正可执行。`
      : "这版行程尽量贴近你明确给出的地点，没有默默塞进无关填充点。",
    itinerary.planning_assumptions?.meal_structure_applied
      ? "餐食被当作午餐/晚餐锚点处理，所以餐厅会支撑当天节奏，而不是和景点抢同一个时间槽。"
      : null,
    optionalPlaceCount > 0
      ? `${optionalPlaceCount} 个候选补点可用于替换或继续补齐${completedCategoryLabels.length > 0 ? `：${completedCategoryLabels.join("、")}` : ""}。`
      : "这版暂时不需要额外候选池。",
    sparseDayCount > 0
      ? `系统检测到 ${sparseDayCount} 个偏稀疏的天数/时间段，所以缺口会被展示出来，而不是藏在结果里。`
      : "当前旅行骨架里没有明显的大段空缺。",
    committedCount > 0
      ? `${committedCount} 个替换选择已保存为你的旅行意图，后续重新补全会继续带入。`
      : `${flexibleCount} 个灵活停留点仍可用“换一个”局部调整，不必整段重生成。`,
  ].filter((line): line is string => line !== null);

  const whyLines = buildWhyThisFlowLines(itinerary, context);
  whyLines.push(
    `${fixedCount} 个固定停留点和 ${flexibleCount} 个灵活停留点被分开处理：硬约束会被保护，软选择仍然可编辑。`,
  );

  return {
    fromInputLines,
    completedLines,
    whyLines: whyLines.slice(0, 4),
  };
}

type ResultCompletionStatusItem = {
  label: string;
  value: string;
  description: string;
  targetId?: string;
  tone: "done" | "watch" | "info";
};

function buildResultCompletionStatus(
  itinerary: ItineraryResponse,
  context: GenerationContext | null,
): ResultCompletionStatusItem[] {
  const scheduledItems = itinerary.days.flatMap((day) => getOrderedDayItems(day));
  const fixedCount = scheduledItems.filter((item) => item.is_fixed).length;
  const userSeedCount =
    (context?.scenic_spots.length ?? itinerary.planning_assumptions?.user_seed_scenic_count ?? 0) +
    (context?.restaurants.length ?? itinerary.planning_assumptions?.user_seed_restaurant_count ?? 0);
  const preferenceCount = context?.preferences.length ?? 0;
  const completion = itinerary.completion_intelligence ?? null;
  const sparseCount =
    completion?.sparse_blocks_detected.length ??
    itinerary.completion_recommendation?.sparse_days.length ??
    0;
  const autoScenicCount =
    completion?.auto_filled_scenic_count ??
    scheduledItems.filter((item) => item.type === "scenic" && isAutoFilledScheduledItem(item)).length;
  const autoMealCount =
    completion?.auto_filled_meal_count ??
    (itinerary.planning_assumptions?.auto_seeded_meal_count ??
      scheduledItems.filter(
        (item) => item.type === "restaurant" && (isAutoFilledScheduledItem(item) || isAutoSeededScheduledItem(item)),
      ).length);
  const autoEveningCount =
    completion?.auto_filled_evening_count ??
    itinerary.days
      .flatMap((day) => day.blocks.filter((block) => block.block_type === "evening"))
      .flatMap((block) => block.items)
      .filter((item) => isAutoFilledScheduledItem(item) || isAutoSeededScheduledItem(item)).length;
  const autoFilledTotal = autoScenicCount + autoMealCount + autoEveningCount;
  const stayReady = Boolean(
    completion?.stay_area_recommendation ?? itinerary.stay_recommendation?.options[0],
  );
  const departureReady = Boolean(
    completion?.departure_hub_recommendation ?? itinerary.departure_recommendation?.options[0],
  );
  const sparseTargetId = completion
    ? RESULT_NAV_TARGETS.completionSummary
    : itinerary.completion_recommendation
      ? RESULT_NAV_TARGETS.autoFill
      : undefined;
  const autoFillTargetId = itinerary.completion_recommendation
    ? RESULT_NAV_TARGETS.autoFill
    : completion
      ? RESULT_NAV_TARGETS.completionSummary
      : undefined;
  const stayDepartureTargetId = itinerary.stay_recommendation
    ? RESULT_NAV_TARGETS.stay
    : itinerary.departure_recommendation
      ? RESULT_NAV_TARGETS.departure
      : completion
        ? RESULT_NAV_TARGETS.completionSummary
        : undefined;

  return [
    {
      label: "理解旅行意图",
      value: context?.city ?? itinerary.planning_assumptions?.destination ?? "已解析",
      description:
        userSeedCount > 0
          ? `保留 ${userSeedCount} 个用户给出的地点、${fixedCount} 个固定安排${preferenceCount > 0 ? `和 ${preferenceCount} 条偏好` : ""}。`
          : `输入较稀疏，先用目的地、时间和偏好建立当前计划。`,
      tone: "done",
    },
    {
      label: "生成旅行骨架",
      value: `${itinerary.trip_days} 天 · ${scheduledItems.length} 站`,
      description: "先把用户输入和硬约束放进时间线，再补齐可执行的日程结构。",
      tone: "done",
    },
    {
      label: "识别空缺",
      value: sparseCount > 0 ? `${sparseCount} 处` : "暂无明显空缺",
      description:
        sparseCount > 0
          ? "仍有偏稀疏时间段会被明确展示，方便继续补全或调整。"
          : "当前骨架没有明显大段空白，可以直接进入微调。",
      targetId: sparseTargetId,
      tone: sparseCount > 0 ? "watch" : "done",
    },
    {
      label: "自动补齐",
      value: `${autoFilledTotal} 项`,
      description: buildAutoFillStatusCopy(itinerary, autoFilledTotal, autoScenicCount, autoMealCount, autoEveningCount),
      targetId: autoFillTargetId,
      tone: autoFilledTotal > 0 ? "done" : "info",
    },
    {
      label: "住宿与离开",
      value: `${stayReady ? "住宿✓" : "住宿待定"} · ${departureReady ? "离开✓" : "离开待定"}`,
      description:
        stayReady || departureReady
          ? "系统会根据已成型路线反推落脚区域和最后一天离开方向。"
          : "当前路线还可以继续补全，之后再反推住宿区域和离开枢纽。",
      targetId: stayDepartureTargetId,
      tone: stayReady && departureReady ? "done" : "info",
    },
  ];
}

function buildAutoFillStatusCopy(
  itinerary: ItineraryResponse,
  autoFilledTotal: number,
  autoScenicCount: number,
  autoMealCount: number,
  autoEveningCount: number,
): string {
  const intelligence = itinerary.completion_intelligence;
  if (autoFilledTotal > 0) {
    return `已自动补入景点/活动 ${autoScenicCount}、餐食 ${autoMealCount}、夜间 ${autoEveningCount}。`;
  }
  const blockedReasons = intelligence?.auto_fill_blocked_reasons ?? [];
  if (blockedReasons.length > 0) {
    return `已识别空缺，但暂不自动塞占位点：${blockedReasons[0]}`;
  }
  if (intelligence?.auto_fill_attempted) {
    return "已尝试自动补齐，但当前没有足够稳妥的真实候选，等待你选择候选。";
  }
  return "已识别空缺，等待你选择候选或继续补充偏好。";
}

function buildCompletionIntelligenceDisplayLines(
  summary: CompletionIntelligenceSummary,
): string[] {
  const lines = [
    `旅行骨架完整度：${summary.trip_completeness}%。`,
    summary.score_breakdown
      ? `分项：密度 ${summary.score_breakdown.density}%、餐食 ${summary.score_breakdown.meals}%、夜间 ${summary.score_breakdown.evening}%、交通边界 ${summary.score_breakdown.transport_boundary}%。`
      : "",
    summary.sparse_blocks_detected.length > 0
      ? `仍可见的空缺：${summary.sparse_blocks_detected.slice(0, 4).join("、")}${summary.sparse_blocks_detected.length > 4 ? "…" : ""}。`
      : "补全后没有明显的大段空缺。",
    `已补入骨架：${summary.auto_filled_scenic_count} 个景点/活动、${summary.auto_filled_meal_count} 个餐食锚点、${summary.auto_filled_evening_count} 个夜间安排。`,
    (summary.auto_fill_blocked_reasons ?? []).length > 0
      ? `暂未自动补齐的原因：${summary.auto_fill_blocked_reasons?.[0]}`
      : "",
    summary.stay_area_recommendation
      ? `住宿区域建议：${summary.stay_area_recommendation}。`
      : "当前骨架暂未形成住宿区域建议。",
    summary.departure_hub_recommendation
      ? `离开枢纽建议：${summary.departure_hub_recommendation}。`
      : "当前骨架暂未形成离开枢纽建议。",
    ...summary.why_this_plan_works.slice(0, 3),
  ];

  return lines.filter((line) => line.trim().length > 0);
}

function buildDirectOptimizationComparison(
  before: CompletionIntelligenceSummary | null,
  after: CompletionIntelligenceSummary | null,
): DirectOptimizationComparison | null {
  if (!after) {
    return null;
  }

  if (!before) {
    return {
      title: "已按这条风险重新优化",
      lines: ["系统已基于当前补全智能重新生成路线，你可以继续查看新的完整度和待加强点。"],
    };
  }

  const lines: string[] = [];
  const completenessDelta = after.trip_completeness - before.trip_completeness;
  if (completenessDelta > 0) {
    lines.push(`整体完整度提升了 ${completenessDelta} 分，现在是 ${after.trip_completeness}%。`);
  } else if (completenessDelta < 0) {
    lines.push(`整体完整度变为 ${after.trip_completeness}%，系统可能为了满足新约束牺牲了一些密度。`);
  }

  const scoreChanges = buildScoreBreakdownChangeLines(
    before.score_breakdown ?? null,
    after.score_breakdown ?? null,
  );
  lines.push(...scoreChanges);

  const sparseDelta =
    before.sparse_blocks_detected.length - after.sparse_blocks_detected.length;
  if (sparseDelta > 0) {
    lines.push(`减少了 ${sparseDelta} 个明显空缺时间段。`);
  }

  const mealDelta = after.auto_filled_meal_count - before.auto_filled_meal_count;
  if (mealDelta > 0) {
    lines.push(`新增 ${mealDelta} 个系统补齐的餐食锚点。`);
  }

  const eveningDelta = after.auto_filled_evening_count - before.auto_filled_evening_count;
  if (eveningDelta > 0) {
    lines.push(`新增 ${eveningDelta} 个晚间补齐安排。`);
  }

  const scenicDelta = after.auto_filled_scenic_count - before.auto_filled_scenic_count;
  if (scenicDelta > 0) {
    lines.push(`新增 ${scenicDelta} 个顺路活动/景点补齐。`);
  }

  return {
    title: "这次直接优化改了什么",
    lines: uniquePreserveOrder(lines).slice(0, 4).length
      ? uniquePreserveOrder(lines).slice(0, 4)
      : ["已重新规划，当前可执行性分项保持稳定；可以继续点待加强项微调。"],
  };
}

function buildCompletionTaskActionRequest(task: CompletionTaskCard): {
  task_id: "repair_meal_anchor" | "repair_evening_close" | "repair_sparse_block";
  task_instance_key: string;
  day?: number;
  block_type?: DayBlock["block_type"];
} | null {
  const targetText = `${task.title} ${task.reason} ${task.action_prompt}`;
  if (task.task_id === "add_meal_anchor") {
    const target = extractCompletionTaskTarget(targetText);
    return {
      task_id: "repair_meal_anchor",
      task_instance_key: getCompletionTaskInstanceKey(task),
      day: target.day,
      block_type: target.day ? target.block_type : undefined,
    };
  }
  if (task.task_id === "add_evening_close") {
    return {
      task_id: "repair_evening_close",
      task_instance_key: getCompletionTaskInstanceKey(task),
      ...extractCompletionTaskTarget(targetText),
      block_type: "evening",
    };
  }
  if (task.task_id === "fill_sparse_block") {
    return {
      task_id: "repair_sparse_block",
      task_instance_key: getCompletionTaskInstanceKey(task),
      ...extractCompletionTaskTarget(targetText),
    };
  }
  return null;
}

function getCompletionTaskInstanceKey(task: CompletionTaskCard): string {
  return (
    task.task_instance_key?.trim() ||
    `${task.task_id}:${normalizeCompletionTaskKeyPart(`${task.title} ${task.action_prompt}`)}`
  );
}

function normalizeCompletionTaskKeyPart(value: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[\\s/:：]+/g, "-")
    .replace(/[^\\p{L}\\p{N}_-]+/gu, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
  return normalized || "default";
}

function extractCompletionTaskTarget(text: string): {
  day?: number;
  block_type?: DayBlock["block_type"];
} {
  const dayMatch = text.match(/Day\s*(\d+)/i) ?? text.match(/第\s*(\d+)\s*天/);
  return {
    day: dayMatch ? Number(dayMatch[1]) : undefined,
    block_type: extractCompletionTaskBlockType(text),
  };
}

function extractCompletionTaskBlockType(text: string): DayBlock["block_type"] | undefined {
  const normalized = text.toLowerCase();
  if (normalized.includes("morning") || text.includes("上午")) {
    return "morning";
  }
  if (normalized.includes("afternoon") || text.includes("下午") || text.includes("午餐")) {
    return "afternoon";
  }
  if (
    normalized.includes("evening") ||
    text.includes("晚上") ||
    text.includes("晚间") ||
    text.includes("晚餐") ||
    text.includes("夜间")
  ) {
    return "evening";
  }
  return undefined;
}

function buildRouteWorkspaceWeakestDay(
  itinerary: ItineraryResponse,
): { day: number; reason: string } | null {
  const dayScores = new Map<number, { taskCount: number; issueCount: number; score: number }>();

  itinerary.days.forEach((day) => {
    dayScores.set(day.day, { taskCount: 0, issueCount: 0, score: 0 });
  });

  itinerary.completion_intelligence?.action_tasks?.forEach((task) => {
    const target = extractCompletionTaskTarget(`${task.title} ${task.reason} ${task.action_prompt}`);
    if (!target.day) {
      return;
    }
    const current = dayScores.get(target.day);
    if (!current) {
      return;
    }
    current.taskCount += 1;
    current.score += 2;
  });

  itinerary.planner_realism?.issues.forEach((issue) => {
    if (!issue.day) {
      return;
    }
    const current = dayScores.get(issue.day);
    if (!current) {
      return;
    }
    current.issueCount += 1;
    current.score += issue.severity === "high" ? 3 : issue.severity === "medium" ? 2 : 1;
  });

  const weakestEntry = [...dayScores.entries()]
    .filter(([, value]) => value.score > 0)
    .sort((left, right) => {
      if (right[1].score !== left[1].score) {
        return right[1].score - left[1].score;
      }
      if (right[1].issueCount !== left[1].issueCount) {
        return right[1].issueCount - left[1].issueCount;
      }
      if (right[1].taskCount !== left[1].taskCount) {
        return right[1].taskCount - left[1].taskCount;
      }
      return left[0] - right[0];
    })[0];

  if (!weakestEntry) {
    return null;
  }

  const [day, value] = weakestEntry;
  const fragments: string[] = [];
  if (value.issueCount > 0) {
    fragments.push(`${value.issueCount} 个路线风险`);
  }
  if (value.taskCount > 0) {
    fragments.push(`${value.taskCount} 个待补任务`);
  }

  return {
    day,
    reason: `${fragments.join("，")} 还没收口，先修这里最能提升整趟体验。`,
  };
}

function buildScoreBreakdownChangeLines(
  before: CompletionScoreBreakdown | null,
  after: CompletionScoreBreakdown | null,
): string[] {
  if (!before || !after) {
    return [];
  }

  return [
    scoreChangeLine("行程密度", before.density, after.density),
    scoreChangeLine("餐食结构", before.meals, after.meals),
    scoreChangeLine("夜间安排", before.evening, after.evening),
    scoreChangeLine("交通边界", before.transport_boundary, after.transport_boundary),
  ].filter((line): line is string => line !== null);
}

function scoreChangeLine(label: string, before: number, after: number): string | null {
  const delta = after - before;
  if (delta <= 0) {
    return null;
  }
  return `${label}提升了 ${delta} 分。`;
}

function buildInputConstraintOwnershipLines(
  context: GenerationContext,
  itinerary: ItineraryResponse,
): string[] {
  const lines: string[] = [];
  const fixedEventPreview = context.fixed_events
    .slice(0, 2)
    .map((event) => event.name)
    .join(", ");
  if (context.fixed_events.length > 0) {
    lines.push(
      `${context.fixed_events.length} 个固定安排${fixedEventPreview ? `（${fixedEventPreview}${context.fixed_events.length > 2 ? "…" : ""}）` : ""}会作为硬约束保护。`,
    );
  }

  if (context.availability_windows.length > 0) {
    lines.push(
      `${context.availability_windows.length} 段可用时间会影响每天边界，不会被当作随手备注忽略。`,
    );
  }

  if (
    context.fixed_events.length === 0 &&
    context.availability_windows.length === 0 &&
    !context.arrival_anchor &&
    !context.departure_anchor
  ) {
    lines.push(
      `没有强时间约束，所以确定性调度器有空间把这份计划整理成 ${itinerary.trip_days} 天可执行骨架。`,
    );
  }

  return lines;
}

function buildTripScopeOwnershipLine(
  context: GenerationContext,
  generatedTripDays: number,
): string {
  if (context.trip_days_source === "explicit") {
    return `行程天数来自你的输入：${generatedTripDays} 天。`;
  }
  if (
    (context.trip_days_source === "estimated" ||
      context.trip_days_source === "interaction_estimated") &&
    context.trip_scope_estimate
  ) {
    return `你没有把天数说死，系统按 ${formatStateLabel(context.trip_scope_estimate.estimation_mode)} 和 ${formatStateLabel(context.trip_scope_estimate.poi_load_level)} 先估成 ${context.trip_scope_estimate.estimated_trip_days} 天。`;
  }
  return `行程天数保持弹性，所以调度器把这份计划整理成 ${generatedTripDays} 天可执行骨架。`;
}

function isAutoSeededScheduledItem(item: ScheduledItem): boolean {
  if (item.source_type === "auto_seeded_poi" || item.source_type === "auto_seeded_meal") {
    return true;
  }
  return (item.placement_reason ?? "").toLocaleLowerCase().includes("auto-seeded from sparse city input");
}

function isAutoFilledScheduledItem(item: ScheduledItem): boolean {
  return item.source_type === "auto_filled";
}

function getAutoSeededShareStats(itinerary: ItineraryResponse): {
  poiCount: number;
  mealCount: number;
  names: string[];
} {
  const autoSeededItems = itinerary.days
    .flatMap((day) => getOrderedDayItems(day))
    .filter(isAutoSeededScheduledItem);
  return {
    poiCount: autoSeededItems.filter((item) => item.type === "scenic").length,
    mealCount: autoSeededItems.filter((item) => item.type === "restaurant").length,
    names: autoSeededItems.map((item) => item.name),
  };
}

function buildShareTripScopeLine(
  itinerary: ItineraryResponse,
  context: GenerationContext | null,
): string | null {
  if (!context) {
    return null;
  }
  if (context.trip_days_source === "explicit") {
    return `天数是我一开始就定好的：${itinerary.trip_days}天。`;
  }
  if (
    (context.trip_days_source === "estimated" ||
      context.trip_days_source === "interaction_estimated") &&
    context.trip_scope_estimate
  ) {
    return `我没把天数说得特别死，系统按我给的信息先估成了${context.trip_scope_estimate.estimated_trip_days}天，作为一个比较能走完的版本。`;
  }
  if (context.trip_days_source === "scheduler_estimated") {
    return `我没有先定死天数，所以这版是按当前内容整理出来的${itinerary.trip_days}天路线。`;
  }
  return null;
}

function buildShareAutoSeedLine(itinerary: ItineraryResponse): string | null {
  const stats = getAutoSeededShareStats(itinerary);
  if (stats.poiCount + stats.mealCount === 0) {
    return null;
  }

  const parts = [
    stats.poiCount > 0 ? `${stats.poiCount}个起步停留点` : null,
    stats.mealCount > 0 ? `${stats.mealCount}个吃饭点` : null,
  ].filter((part): part is string => part !== null);
  const preview = stats.names.slice(0, 3).join("、");
  return `因为我给的信息比较散，它还自动补了${parts.join("和")}，比如 ${preview}${stats.names.length > 3 ? "…" : ""}，这样路线不是空架子。`;
}

function buildShareTimeFlexLine(context: GenerationContext | null): string | null {
  if (!context) {
    return null;
  }

  const parts = [
    context.fixed_events.length > 0 ? `${context.fixed_events.length}个固定安排` : null,
    context.availability_windows.length > 0 ? `${context.availability_windows.length}段时间弹性/可用窗口` : null,
  ].filter((part): part is string => part !== null);

  if (parts.length === 0) {
    return null;
  }

  const fixedPreview = context.fixed_events
    .slice(0, 2)
    .map((event) => event.name)
    .join("、");
  const fixedSuffix = fixedPreview ? `（比如 ${fixedPreview}${context.fixed_events.length > 2 ? "…" : ""}）` : "";

  return `它也不是只按景点热度硬排，而是先把我提到的${parts.join("和")}${fixedSuffix}卡进去，再把中间空出来的时间补顺。`;
}

function buildPracticalExportConstraintLine(context: GenerationContext | null): string | null {
  if (!context) {
    return null;
  }

  const parts = [
    context.fixed_events.length > 0
      ? `固定安排 ${context.fixed_events
          .slice(0, 3)
          .map((event) => event.name)
          .join("、")}${context.fixed_events.length > 3 ? "…" : ""}`
      : null,
    context.availability_windows.length > 0
      ? `时间窗口 ${formatAvailabilityWindowsForExport(context.availability_windows)}`
      : null,
  ].filter((part): part is string => part !== null);

  return parts.length > 0 ? `结构化约束：${parts.join("；")}` : null;
}

function getCompletionCategoryLabels(itinerary: ItineraryResponse): string[] {
  const options = itinerary.completion_recommendation?.options ?? [];
  const signals = createEmptyPreferenceSignals();

  for (const option of options) {
    const optionSignals = inferSignalsFromPoi(
      option.name,
      option.type,
      `${option.reasoning_summary} ${option.itinerary_relation_summary}`,
    );
    for (const key of Object.keys(signals) as PreferenceSignalKey[]) {
      signals[key] += optionSignals[key];
    }
  }

  return getStrongPreferenceSignalLabels(signals).slice(0, 4);
}

function buildCopyableItineraryText(
  itinerary: ItineraryResponse,
  context: GenerationContext | null,
  committedSwaps: CommittedSwapSelection[],
): string {
  const lines: string[] = [
    `我的旅行计划（${itinerary.trip_days}天）`,
    context?.city ? `目的地：${context.city}` : null,
    `节奏：${formatPacingProfileLabel(context?.pacing_profile ?? "balanced")}`,
    `规划基准：${formatPlanningAnchorSourceType(itinerary.planning_anchor_source.source_type)} · ${itinerary.planning_anchor_source.source_name}`,
  ].filter((line): line is string => line !== null);

  if (context?.arrival_anchor || context?.departure_anchor) {
    lines.push(
      `边界约束：${[
        context.arrival_anchor ? `到达 ${context.arrival_anchor}` : null,
        context.departure_anchor ? `离开 ${context.departure_anchor}` : null,
      ]
        .filter((item): item is string => item !== null)
        .join("；")}`,
    );
  }

  const structuredConstraintLine = buildPracticalExportConstraintLine(context);
  if (structuredConstraintLine) {
    lines.push(structuredConstraintLine);
  }

  if (context?.preferences.length) {
    lines.push(`偏好：${context.preferences.slice(0, 5).join("；")}`);
  }

  if (committedSwaps.length > 0) {
    lines.push(
      `我的调整：${committedSwaps
        .map((swap) => `${swap.original_name} -> ${swap.replacement_name}`)
        .join("；")}`,
    );
  }

  for (const day of itinerary.days) {
    lines.push("", `第 ${day.day} 天`);
    lines.push(`可用时间：${formatEffectiveAvailabilityRange(day.availability_summary)}`);

    for (const block of day.blocks) {
      if (block.items.length === 0) {
        continue;
      }

      lines.push(`${formatBlockTitleForExport(block.block_type)}（${formatTime(block.start_time)}-${formatTime(block.end_time)}）`);

      for (const item of block.items) {
        const labels = [
          formatScheduledItemTypeForExport(item.type),
          formatScheduledItemSourceForExport(item),
          item.is_fixed ? "固定" : null,
          item.local_edit ? "已替换" : null,
        ].filter((label): label is string => label !== null);
        lines.push(
          `- ${formatTime(item.start_time)}-${formatTime(item.end_time)} ${item.name}（${labels.join(" / ")}）`,
        );

        const reason = getExportReasonForItem(item);
        if (reason) {
          lines.push(`  原因：${reason}`);
        }

        if (item.travel_from_name && item.travel_duration_s !== null) {
          lines.push(
            `  衔接：从 ${item.travel_from_name} 约 ${formatTravelDuration(item.travel_duration_s)}`,
          );
        }
      }
    }
  }

  const optionalOptions = itinerary.completion_recommendation?.options.slice(0, 4) ?? [];
  if (optionalOptions.length > 0) {
    lines.push("", "可选替换 / 补充");
    for (const option of optionalOptions) {
      lines.push(
        `- ${option.name}（${formatCompletionOptionType(option.type)} · 第 ${option.suggested_day} 天 ${formatBlockTitleForExport(option.suggested_block)}）：${shortenExportText(option.reasoning_summary, 48)}`,
      );
    }
  }

  lines.push("", "由当前行程版本复制，可继续在产品中调整。");

  return lines.join("\n");
}

function buildShareableItineraryText(
  itinerary: ItineraryResponse,
  context: GenerationContext | null,
  committedSwaps: CommittedSwapSelection[],
): string {
  const pacing = context?.pacing_profile ?? "balanced";
  const shareTitle = buildShareTitle(itinerary, context, committedSwaps);
  const seedNames = [
    ...(context?.scenic_spots ?? []),
    ...(context?.restaurants ?? []),
  ].slice(0, 5);
  const preferenceText = context?.preferences.length
    ? context.preferences.slice(0, 4).join("、")
    : describePacingForShare(pacing);
  const tripScopeLine = buildShareTripScopeLine(itinerary, context);
  const autoSeedLine = buildShareAutoSeedLine(itinerary);
  const timeFlexLine = buildShareTimeFlexLine(context);
  const lines: string[] = [
    shareTitle,
    "",
    `这次的${itinerary.trip_days}天行程，我没有直接照搬攻略。`,
  ];

  if (seedNames.length > 0) {
    lines.push(
      `一开始只是随手丢了几个想去的点：${seedNames.join("、")}${seedNames.length < (context?.scenic_spots.length ?? 0) + (context?.restaurants.length ?? 0) ? "…" : ""}`,
    );
  } else {
    lines.push("一开始只是给了一些大概的想法，然后把它整理成了可以真正走的路线。");
  }

  lines.push(`我的需求大概是：${preferenceText}，整体想走${describePacingForShare(pacing)}。`);
  if (tripScopeLine) {
    lines.push(tripScopeLine);
  }
  if (autoSeedLine) {
    lines.push(autoSeedLine);
  }
  if (timeFlexLine) {
    lines.push(timeFlexLine);
  }

  if (context?.arrival_anchor || context?.departure_anchor) {
    lines.push(
      `时间上也有一点现实限制：${[
        context.arrival_anchor ? `从 ${context.arrival_anchor} 开始` : null,
        context.departure_anchor ? `最后要接到 ${context.departure_anchor}` : null,
      ]
        .filter((item): item is string => item !== null)
        .join("，")}。`,
    );
  }

  if (committedSwaps.length > 0) {
    lines.push(
      `中间我还自己换掉了${committedSwaps.length}个不太想去的点，比如 ${committedSwaps
        .slice(0, 3)
        .map((swap) => `${swap.original_name} 换成 ${swap.replacement_name}`)
        .join("、")}，所以这个版本更像我自己的路线。`,
    );
  }

  for (const day of itinerary.days) {
    const dayItems = getOrderedDayItems(day);
    if (dayItems.length === 0) {
      continue;
    }

    lines.push("", `Day ${day.day}`);
    lines.push(buildShareDaySummary(dayItems));

    for (const item of dayItems) {
      const labels = [
        formatScheduledItemSourceForShare(item),
        item.is_fixed ? "固定安排" : null,
        item.local_edit ? "我后来换的" : null,
      ].filter((label): label is string => label !== null);
      lines.push(
        `- ${formatTime(item.start_time)} ${item.name}${labels.length > 0 ? `（${labels.join(" / ")}）` : ""}`,
      );
    }
  }

  lines.push("");
  lines.push("我喜欢这个版本的点是：它不是那种把热门景点全塞进去的攻略，而是先保留我真的想去的地方，再把空白时间补顺。");
  lines.push(`每天的节奏也比较清楚：${describeSharePlanWhyWorks(itinerary, context)}。`);
  lines.push("后面如果临时想换一个点，也不用推倒重来，直接替换掉就行。");

  return lines.join("\n");
}

function buildShareTitle(
  itinerary: ItineraryResponse,
  context: GenerationContext | null,
  committedSwaps: CommittedSwapSelection[],
): string {
  const cityLabel = inferShareCityLabel(itinerary, context);
  const durationLabel = itinerary.trip_days <= 2 ? "周末" : `${itinerary.trip_days}天`;
  const templateIndex = Math.abs(
    itinerary.trip_days +
      committedSwaps.length +
      itinerary.planning_anchor_source.source_name.length +
      (context?.preferences.length ?? 0),
  ) % 3;
  const pacing = context?.pacing_profile ?? "balanced";

  if (pacing === "relaxed") {
    return [
      `${cityLabel}${itinerary.trip_days}天轻松版，真的不赶也能玩得顺`,
      `${cityLabel}${durationLabel}这样排很舒服，不像赶场打卡`,
      `${cityLabel}${itinerary.trip_days}天不累玩法，我自己改完更好走`,
    ][templateIndex];
  }

  if (pacing === "packed") {
    return [
      `${cityLabel}${itinerary.trip_days}天高效版，该去的基本都去了`,
      `${cityLabel}${durationLabel}这样排，一次逛得更完整`,
      `${cityLabel}${itinerary.trip_days}天紧凑但顺路，比硬做攻略省心`,
    ][templateIndex];
  }

  return [
    `${cityLabel}${itinerary.trip_days}天这样玩刚刚好，不累也不空`,
    `${cityLabel}${durationLabel}这样排，比我自己做攻略顺多了`,
    `${cityLabel}${itinerary.trip_days}天顺路版，保留想去的也不乱`,
  ][templateIndex];
}

function inferShareCityLabel(
  itinerary: ItineraryResponse,
  context: GenerationContext | null,
): string {
  const sourceText = [
    context?.city,
    context?.arrival_anchor,
    context?.departure_anchor,
    itinerary.planning_anchor_source.source_name,
    ...(context?.scenic_spots ?? []),
    ...(context?.restaurants ?? []),
  ]
    .filter((value): value is string => Boolean(value))
    .join(" ");
  const knownCities = [
    "上海",
    "北京",
    "杭州",
    "深圳",
    "广州",
    "成都",
    "重庆",
    "南京",
    "苏州",
    "厦门",
    "武汉",
    "西安",
    "长沙",
    "青岛",
    "大理",
    "丽江",
    "香港",
    "澳门",
    "台北",
  ];
  const matchedCity = knownCities.find((city) => sourceText.includes(city));
  if (matchedCity) {
    return matchedCity;
  }

  const sourceName = itinerary.planning_anchor_source.source_name.trim();
  if (sourceName.length <= 4) {
    return sourceName;
  }

  return sourceName.slice(0, 4);
}

function buildShareCardData(
  itinerary: ItineraryResponse,
  context: GenerationContext | null,
  committedSwaps: CommittedSwapSelection[],
  preferenceSignals: PreferenceSignals,
): ShareCardData {
  const pacing = context?.pacing_profile ?? "balanced";
  const cityLabel = inferShareCityLabel(itinerary, context);
  const preferenceHighlights = getShareHighlightLabels(preferenceSignals);
  const autoSeedStats = getAutoSeededShareStats(itinerary);
  const highlights = uniquePreserveOrder([
    formatPacingForCard(pacing),
    autoSeedStats.poiCount + autoSeedStats.mealCount > 0 ? "自动补全" : "",
    ...preferenceHighlights,
    itinerary.completion_recommendation?.options.length ? "可替换" : "",
  ].filter(Boolean)).slice(0, 3);

  return {
    title: buildShareTitle(itinerary, context, committedSwaps),
    meta: `${cityLabel} · ${itinerary.trip_days}天 · ${formatPacingForCard(pacing)}`,
    highlights,
    keyStops: getShareCardKeyStops(itinerary),
    edits: committedSwaps
      .slice(0, 2)
      .map((swap) => `${swap.original_name} -> ${swap.replacement_name}`),
    closingLine: buildShareCardClosingLine(pacing, committedSwaps.length, autoSeedStats),
  };
}

function getShareCardKeyStops(itinerary: ItineraryResponse): string[] {
  const allItems = itinerary.days.flatMap((day) => getOrderedDayItems(day));
  const editedItems = allItems.filter((item) => item.local_edit);
  const fixedItems = allItems.filter((item) => item.is_fixed);
  const restaurantItems = allItems.filter((item) => item.type === "restaurant");
  const scenicItems = allItems.filter((item) => item.type === "scenic" && !item.is_fixed);

  return uniquePreserveOrder([
    ...editedItems.map((item) => item.name),
    ...fixedItems.map((item) => item.name),
    ...scenicItems.map((item) => item.name),
    ...restaurantItems.map((item) => item.name),
  ]).slice(0, 4);
}

function buildShareCardClosingLine(
  pacingProfile: PacingProfile,
  editedCount: number,
  autoSeedStats: { poiCount: number; mealCount: number },
): string {
  if (editedCount > 0) {
    return "这版是我改完最顺的一版";
  }
  if (autoSeedStats.poiCount + autoSeedStats.mealCount > 0) {
    return "从几个模糊想法整理成了能走的路线";
  }
  if (pacingProfile === "relaxed") {
    return "适合不想赶、但又想好好逛的人";
  }
  if (pacingProfile === "packed") {
    return "适合想高效多看一点的人";
  }
  return "适合不想做攻略、但想玩得顺的人";
}

function getShareHighlightLabels(preferenceSignals: PreferenceSignals): string[] {
  const labels: string[] = [];
  if (preferenceSignals.food >= 2) {
    labels.push("美食");
  }
  if (preferenceSignals.night >= 1) {
    labels.push("夜景");
  }
  if (preferenceSignals.shopping >= 1) {
    labels.push("可逛");
  }
  if (preferenceSignals.landmark >= 1) {
    labels.push("地标");
  }
  if (preferenceSignals.relaxed >= 1) {
    labels.push("慢逛");
  }
  if (preferenceSignals.culture >= 1) {
    labels.push("文化");
  }
  return labels;
}

function formatPacingForCard(pacingProfile: PacingProfile): string {
  if (pacingProfile === "relaxed") {
    return "轻松不赶";
  }
  if (pacingProfile === "packed") {
    return "高效覆盖";
  }
  return "顺路刚好";
}

function renderShareCardToImage(data: ShareCardData): string {
  if (typeof document === "undefined") {
    throw new Error("Canvas is unavailable.");
  }

  const width = 900;
  const height = 1400;
  const scale = 2;
  const canvas = document.createElement("canvas");
  canvas.width = width * scale;
  canvas.height = height * scale;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("Canvas context is unavailable.");
  }

  context.scale(scale, scale);
  context.fillStyle = "#f7efe2";
  context.fillRect(0, 0, width, height);
  drawShareCardBlob(context, 90, 30, 760, 620, "rgba(91, 132, 165, 0.15)");
  drawShareCardBlob(context, 500, 590, 520, 620, "rgba(226, 167, 91, 0.22)");
  drawShareCardBlob(context, -180, 840, 500, 500, "rgba(105, 158, 139, 0.18)");

  drawRoundedRect(context, 54, 48, 792, 1304, 42, "rgba(255, 252, 246, 0.94)");
  drawRoundedRect(context, 78, 72, 744, 1256, 34, "rgba(255, 255, 255, 0.58)");

  let y = 132;
  context.fillStyle = "#8a6331";
  context.font = '700 23px "Avenir Next", "PingFang SC", sans-serif';
  context.fillText("不是照搬攻略，是我的路线封面", 112, y);
  y += 74;

  context.fillStyle = "#17201b";
  context.font = '800 64px "Avenir Next", "PingFang SC", sans-serif';
  y = drawWrappedCanvasText(context, data.title, 112, y, 670, 74, 3);
  y += 20;

  context.fillStyle = "#65705f";
  context.font = '500 27px "Avenir Next", "PingFang SC", sans-serif';
  context.fillText(data.meta, 112, y);
  y += 64;

  let pillX = 112;
  for (const highlight of data.highlights) {
    const pillWidth = Math.min(210, context.measureText(highlight).width + 48);
    drawRoundedRect(context, pillX, y - 34, pillWidth, 50, 25, "rgba(232, 242, 224, 0.95)");
    context.fillStyle = "#48673f";
    context.font = '700 24px "Avenir Next", "PingFang SC", sans-serif';
    context.fillText(highlight, pillX + 24, y);
    pillX += pillWidth + 14;
  }
  y += 112;

  drawRoundedRect(context, 112, y, 676, 360, 34, "rgba(247, 241, 230, 0.88)");
  context.fillStyle = "#8a6331";
  context.font = '800 28px "Avenir Next", "PingFang SC", sans-serif';
  context.fillText("这次大概这样走", 154, y + 58);

  context.fillStyle = "#22303a";
  context.font = '700 34px "Avenir Next", "PingFang SC", sans-serif';
  let stopY = y + 122;
  for (const [index, stop] of data.keyStops.entries()) {
    const marker = `${index + 1}`.padStart(2, "0");
    context.fillStyle = "#b77a3d";
    context.font = '800 23px "Avenir Next", "PingFang SC", sans-serif';
    context.fillText(marker, 154, stopY);
    context.fillStyle = "#22303a";
    context.font = '700 34px "Avenir Next", "PingFang SC", sans-serif';
    context.fillText(shortenExportText(stop, 14), 214, stopY);
    stopY += 64;
  }
  y += 420;

  if (data.edits.length > 0) {
    context.fillStyle = "#5d6b62";
    context.font = '700 24px "Avenir Next", "PingFang SC", sans-serif';
    context.fillText("我自己改过", 112, y);
    y += 42;
    context.font = '500 24px "Avenir Next", "PingFang SC", sans-serif';
    for (const edit of data.edits) {
      context.fillText(shortenExportText(edit, 24), 112, y);
      y += 38;
    }
    y += 24;
  }

  drawRoundedRect(context, 112, 1190, 676, 82, 30, "rgba(48, 65, 55, 0.9)");
  context.fillStyle = "#fff7eb";
  context.font = '700 27px "Avenir Next", "PingFang SC", sans-serif';
  context.fillText(data.closingLine, 154, 1241);

  return canvas.toDataURL("image/png");
}

function drawShareCardBlob(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  color: string,
) {
  context.save();
  context.fillStyle = color;
  context.beginPath();
  context.ellipse(x + width / 2, y + height / 2, width / 2, height / 2, -0.35, 0, Math.PI * 2);
  context.fill();
  context.restore();
}

function drawRoundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
  fillStyle: string,
) {
  context.fillStyle = fillStyle;
  context.beginPath();
  context.moveTo(x + radius, y);
  context.lineTo(x + width - radius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + radius);
  context.lineTo(x + width, y + height - radius);
  context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  context.lineTo(x + radius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
  context.fill();
}

function drawWrappedCanvasText(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
  maxLines: number,
): number {
  const lines: string[] = [];
  let currentLine = "";

  for (const character of Array.from(text)) {
    const nextLine = `${currentLine}${character}`;
    if (context.measureText(nextLine).width > maxWidth && currentLine) {
      lines.push(currentLine);
      currentLine = character;
      if (lines.length === maxLines - 1) {
        break;
      }
      continue;
    }
    currentLine = nextLine;
  }

  if (currentLine) {
    lines.push(lines.length === maxLines - 1 && currentLine.length < text.length ? `${currentLine}…` : currentLine);
  }

  for (const line of lines.slice(0, maxLines)) {
    context.fillText(line, x, y);
    y += lineHeight;
  }

  return y;
}

function buildShareDaySummary(items: ScheduledItem[]): string {
  const scenicCount = items.filter((item) => item.type === "scenic").length;
  const restaurantCount = items.filter((item) => item.type === "restaurant").length;
  const fixedCount = items.filter((item) => item.is_fixed).length;
  const editedCount = items.filter((item) => item.local_edit).length;
  const parts = [
    scenicCount > 0 ? `${scenicCount}个主要停留点` : null,
    restaurantCount > 0 ? `${restaurantCount}个吃饭/休息点` : null,
    fixedCount > 0 ? `${fixedCount}个固定安排` : null,
    editedCount > 0 ? `${editedCount}个我自己换过的点` : null,
  ].filter((part): part is string => part !== null);

  return `这天大概是${parts.join(" + ")}，按时间顺着走：`;
}

function describePacingForShare(pacingProfile: PacingProfile): string {
  if (pacingProfile === "relaxed") {
    return "轻松一点，不想太赶";
  }
  if (pacingProfile === "packed") {
    return "尽量多看一点，路线紧凑一些";
  }
  return "不要太松也不要太赶";
}

function describeSharePlanWhyWorks(
  itinerary: ItineraryResponse,
  context: GenerationContext | null,
): string {
  const reasons = ["白天按区域顺着走"];
  if (context?.arrival_anchor) {
    reasons.push("开头照顾到达时间");
  }
  if (context?.departure_anchor) {
    reasons.push("最后一天不会离返程点太远");
  }
  if (context?.pacing_profile === "relaxed") {
    reasons.push("中间留了喘口气的空间");
  } else if (context?.pacing_profile === "packed") {
    reasons.push("想看的点覆盖得更多");
  }
  if ((itinerary.completion_recommendation?.options.length ?? 0) > 0) {
    reasons.push("还有备选点可以临时替换");
  }

  return reasons.join("，");
}

function getExportReasonForItem(item: ScheduledItem): string | null {
  if (item.local_edit) {
    return shortenExportText(
      `你已从 ${item.local_edit.previous_name} 换成这里。${item.local_edit.reasoning_summary}`,
      64,
    );
  }
  if (item.placement_reason) {
    return shortenExportText(item.placement_reason, 64);
  }
  return null;
}

function formatScheduledItemTypeForExport(type: ScheduledItem["type"]): string {
  if (type === "restaurant") {
    return "餐饮";
  }
  if (type === "hotel") {
    return "住宿";
  }
  return "景点";
}

function formatScheduledItemSourceForExport(item: ScheduledItem): string | null {
  if (item.local_edit) {
    return "我的选择";
  }
  if (item.source_type === "user_fixed") {
    return "固定安排";
  }
  if (item.source_type === "user_seed") {
    return "原始输入";
  }
  if (item.source_type === "auto_seeded_meal") {
    return "系统补餐食";
  }
  if (item.source_type === "auto_seeded_poi") {
    return "系统补起步点";
  }
  if (item.source_type === "auto_filled") {
    return "系统补空档";
  }
  if (isAutoSeededScheduledItem(item)) {
    return item.type === "restaurant" ? "系统补餐食" : "系统补起步点";
  }
  return null;
}

function formatScheduledItemSourceForShare(item: ScheduledItem): string | null {
  if (item.local_edit) {
    return "我改过";
  }
  if (item.source_type === "user_fixed") {
    return "固定";
  }
  if (item.source_type === "user_seed") {
    return "我给的点";
  }
  if (item.source_type === "auto_seeded_meal") {
    return "补的吃饭点";
  }
  if (item.source_type === "auto_seeded_poi") {
    return "补的顺路点";
  }
  if (item.source_type === "auto_filled") {
    return "补空档";
  }
  if (isAutoSeededScheduledItem(item)) {
    return item.type === "restaurant" ? "补的吃饭点" : "补的顺路点";
  }
  return null;
}

function shortenExportText(value: string, maxLength: number): string {
  const trimmed = value.trim();
  if (trimmed.length <= maxLength) {
    return trimmed;
  }
  return `${trimmed.slice(0, maxLength - 1)}…`;
}

function copyTextWithTextareaFallback(text: string): boolean {
  if (typeof document === "undefined") {
    return false;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.select();

  try {
    return document.execCommand("copy");
  } finally {
    document.body.removeChild(textarea);
  }
}

function buildWhyThisFlowLines(
  itinerary: ItineraryResponse,
  context: GenerationContext,
): string[] {
  const lines: string[] = [
    `这条旅行骨架以 ${itinerary.planning_anchor_source.source_name} 为组织中心，所以路线有稳定重心，而不是像复制来的清单。`,
  ];

  if (context.pacing_profile === "relaxed") {
    lines.push("系统刻意降低密度，给转场和休息留更多空间，不会把每个时间块都塞满。");
  } else if (context.pacing_profile === "packed") {
    lines.push("系统按偏紧凑节奏补全，让这版覆盖更多地点，而不是保留过长空白。");
  }

  if (itinerary.boundary_explanation.arrival_anchor_influenced) {
    lines.push(
      `开头会更轻一点，因为 ${itinerary.boundary_explanation.arrival_anchor_name} 的到达边界影响了第一站。`,
    );
  }
  if (itinerary.boundary_explanation.departure_anchor_influenced) {
    lines.push(
      `结尾会更干净，因为最后一天会围绕 ${itinerary.boundary_explanation.departure_anchor_name} 收口。`,
    );
  }

  if (
    context.preferences.some((preference) =>
      /(夜景|吃饭|美食|轻松|不要太赶|休息|逛)/.test(preference),
    )
  ) {
    lines.push(
      "软偏好正在影响路线节奏，尤其是晚间安排、餐食锚点和每天到底排多满。",
    );
  }

  if (lines.length < 3) {
    lines.push(
      "每个停留点都会同时考虑路线连续性和可用时间，所以它更像能执行的骨架，而不是泛泛愿望清单。",
    );
  }

  return lines.slice(0, 3);
}

function getScheduledItemSourceBadge(
  item: ScheduledItem,
  context: GenerationContext | null,
  userIntentState: UserIntentState,
): { label: string; tone: "olive" | "sand" | "sea" | "neutral" } | null {
  if (item.local_edit) {
    return {
      label: "我的选择",
      tone: "olive",
    };
  }
  if (!context) {
    return item.is_fixed ? { label: "你的固定安排", tone: "sand" } : null;
  }

  const userSelectedNames = new Set([
    ...userIntentState.original_scenic.map(normalizeComparisonName),
    ...userIntentState.original_restaurants.map(normalizeComparisonName),
  ]);
  const userConfirmedNames = new Set([
    ...userIntentState.confirmed_scenic.map(normalizeComparisonName),
    ...userIntentState.confirmed_restaurants.map(normalizeComparisonName),
  ]);
  const fixedNames = new Set(context.fixed_events.map((event) => normalizeComparisonName(event.name)));
  const normalizedName = normalizeComparisonName(item.name);

  if (item.source_type === "user_fixed" || fixedNames.has(normalizedName) || item.is_fixed) {
    return { label: "你的固定安排", tone: "sand" };
  }
  if (userConfirmedNames.has(normalizedName)) {
    if (isAutoFilledScheduledItem(item) || isAutoSeededScheduledItem(item)) {
      return { label: "已接受补全", tone: "olive" };
    }
    return { label: "我的选择", tone: "olive" };
  }
  if (item.source_type === "user_seed" || userSelectedNames.has(normalizedName)) {
    return { label: "原始输入", tone: "olive" };
  }
  if (item.source_type === "auto_seeded_meal") {
    return {
      label: "系统补餐食",
      tone: "sea",
    };
  }
  if (item.source_type === "auto_seeded_poi" || isAutoSeededScheduledItem(item)) {
    return {
      label: item.type === "restaurant" ? "系统补餐食" : "系统补种子点",
      tone: "sea",
    };
  }
  if (item.source_type === "auto_filled") {
    return {
      label: "系统补空档",
      tone: "sea",
    };
  }
  return { label: "系统顺路安排", tone: "sea" };
}

function getScheduledItemFlexibilityBadge(
  item: ScheduledItem,
): { label: string; tone: "olive" | "sand" | "sea" | "neutral" } | null {
  if (item.is_fixed) {
    return { label: "硬约束", tone: "sand" };
  }
  if (item.local_edit) {
    return {
      label: "已确认替换",
      tone: "olive",
    };
  }

  const reason = (item.placement_reason ?? "").toLocaleLowerCase();
  if (reason.includes("arrival-side start")) {
    return { label: "灵活，受到达影响", tone: "sea" };
  }
  if (reason.includes("trip ends")) {
    return { label: "灵活，受离开影响", tone: "sea" };
  }
  return { label: "可替换", tone: "neutral" };
}

function buildRouteEditPoiLists(
  editedDays: EditableRouteDay[],
  unplannedStops: EditableRouteDay["stops"] = [],
): { scenic: string[]; restaurants: string[] } {
  const scenic: string[] = [];
  const restaurants: string[] = [];

  for (const day of editedDays) {
    for (const stop of day.stops) {
      if (stop.item.type === "restaurant") {
        restaurants.push(stop.item.name);
      } else if (stop.item.type === "scenic") {
        scenic.push(stop.item.name);
      }
    }
  }
  for (const stop of unplannedStops) {
    if (stop.item.type === "restaurant") {
      restaurants.push(stop.item.name);
    } else if (stop.item.type === "scenic") {
      scenic.push(stop.item.name);
    }
  }

  return {
    scenic: uniquePreserveOrder(scenic),
    restaurants: uniquePreserveOrder(restaurants),
  };
}

function addConfirmedPoiToUserIntentState(
  state: UserIntentState,
  poiName: string,
  poiType: "scenic" | "restaurant",
): UserIntentState {
  if (poiType === "restaurant") {
    if (state.confirmed_restaurants.includes(poiName)) {
      return state;
    }
    return {
      ...state,
      confirmed_restaurants: [...state.confirmed_restaurants, poiName],
    };
  }

  if (state.confirmed_scenic.includes(poiName)) {
    return state;
  }

  return {
    ...state,
    confirmed_scenic: [...state.confirmed_scenic, poiName],
  };
}

function removeConfirmedPoiFromUserIntentState(
  state: UserIntentState,
  poiName: string,
  poiType: "scenic" | "restaurant",
): UserIntentState {
  const removeByName = (values: string[]) =>
    values.filter(
      (value) => normalizeComparisonName(value) !== normalizeComparisonName(poiName),
    );

  return poiType === "restaurant"
    ? {
        ...state,
        confirmed_restaurants: removeByName(state.confirmed_restaurants),
      }
    : {
        ...state,
        confirmed_scenic: removeByName(state.confirmed_scenic),
      };
}

function getIntentPoiTypeFromScheduledItem(
  item: ScheduledItem,
): "scenic" | "restaurant" | null {
  if (item.type === "restaurant") {
    return "restaurant";
  }
  if (item.type === "scenic") {
    return "scenic";
  }
  return null;
}

function buildCompletionTaskEditFromResult(
  task: CompletionTaskCard,
  insertedItem: ScheduledItem,
  summary: string,
): CompletionTaskEdit {
  return {
    task_id: task.task_id,
    task_instance_key: getCompletionTaskInstanceKey(task),
    task_title: task.title,
    inserted_item: insertedItem,
    inserted_item_key: buildRecentCompletionTaskItemKey(insertedItem),
    summary,
    applied_at: new Date().toISOString(),
    status: "applied",
  };
}

function buildRestoredCompletionCandidate(item: ScheduledItem): ItineraryCompletionOption | null {
  const poiType = getIntentPoiTypeFromScheduledItem(item);
  if (!poiType) {
    return null;
  }
  return {
    name: item.name,
    type: poiType,
    suggested_day: item.day ?? 1,
    suggested_block: inferScheduledItemBlock(item),
    reasoning_summary: "刚刚撤销的补全项，可以作为候选重新考虑。",
    itinerary_relation_summary: item.placement_reason ?? "这个点来自刚才的局部补全，可再次选择加入。",
    decision_evidence: null,
  };
}

function inferScheduledItemBlock(item: ScheduledItem): DayBlock["block_type"] {
  const startHour = Number(item.start_time.split(":")[0]);
  if (startHour >= 18) {
    return "evening";
  }
  if (startHour >= 12) {
    return "afternoon";
  }
  return "morning";
}

function upsertCompletionCandidateHistory(
  current: ItineraryCompletionOption[],
  next: ItineraryCompletionOption,
): ItineraryCompletionOption[] {
  return [
    next,
    ...current.filter((candidate) => completionOptionKey(candidate) !== completionOptionKey(next)),
  ].slice(0, 12);
}

function mergeCompletionCandidateHistory(
  current: ItineraryCompletionOption[],
  options: ItineraryCompletionOption[],
): ItineraryCompletionOption[] {
  return options.reduce(
    (history, option) => upsertCompletionCandidateHistory(history, option),
    current,
  );
}

function withCompletionCandidateHistory(
  tripIntent: TripIntentEnvelope,
  completionCandidateHistory: ItineraryCompletionOption[],
): TripIntentEnvelope {
  return {
    ...tripIntent,
    completion_candidate_history: mergeCompletionCandidateHistory(
      tripIntent.completion_candidate_history ?? [],
      completionCandidateHistory,
    ),
  };
}

function removeCompletionCandidateHistoryForItem(
  current: ItineraryCompletionOption[],
  item: ScheduledItem,
): ItineraryCompletionOption[] {
  const restoredCandidate = buildRestoredCompletionCandidate(item);
  if (!restoredCandidate) {
    return current;
  }
  const restoredKey = completionOptionKey(restoredCandidate);
  return current.filter((candidate) => completionOptionKey(candidate) !== restoredKey);
}

function completionOptionKey(option: ItineraryCompletionOption): string {
  return [
    option.name,
    option.type,
    option.suggested_day,
    option.suggested_block,
  ].join("::");
}

function upsertCompletionTaskEdit(
  current: CompletionTaskEdit[],
  next: CompletionTaskEdit,
): CompletionTaskEdit[] {
  return [
    ...current.filter((edit) => edit.task_instance_key !== next.task_instance_key),
    next,
  ];
}

function removeCompletionTaskItemFromItinerary(
  itinerary: ItineraryResponse,
  itemToRemove: ScheduledItem,
): ItineraryResponse {
  const targetKey = buildRecentCompletionTaskItemKey(itemToRemove);

  return {
    ...itinerary,
    days: itinerary.days.map((day) => ({
      ...day,
      blocks: day.blocks.map((block) => ({
        ...block,
        items: block.items.filter(
          (item) => buildRecentCompletionTaskItemKey(item) !== targetKey,
        ),
      })),
    })),
  };
}

function addRejectedPoiToUserIntentState(
  state: UserIntentState,
  poiName: string,
  poiType: "scenic" | "restaurant",
): UserIntentState {
  if (poiType === "restaurant") {
    if (state.rejected_restaurants.includes(poiName)) {
      return state;
    }
    return {
      ...state,
      rejected_restaurants: [...state.rejected_restaurants, poiName],
    };
  }

  if (state.rejected_scenic.includes(poiName)) {
    return state;
  }

  return {
    ...state,
    rejected_scenic: [...state.rejected_scenic, poiName],
  };
}

function syncConfirmedPoisWithCommittedSwaps(
  state: UserIntentState,
  swaps: CommittedSwapSelection[],
): UserIntentState {
  return {
    ...state,
    confirmed_scenic: uniquePreserveOrder(
      swaps
        .filter((swap) => swap.replacement_type === "scenic")
        .map((swap) => swap.replacement_name),
    ),
    confirmed_restaurants: uniquePreserveOrder(
      swaps
        .filter((swap) => swap.replacement_type === "restaurant")
        .map((swap) => swap.replacement_name),
    ),
    rejected_scenic: uniquePreserveOrder(
      swaps
        .filter((swap) => swap.original_type === "scenic")
        .map((swap) => swap.original_name),
    ),
    rejected_restaurants: uniquePreserveOrder(
      swaps
        .filter((swap) => swap.original_type === "restaurant")
        .map((swap) => swap.original_name),
    ),
  };
}

function getCompletionOptionImage(name: string): string | null {
  const imageMap: Record<string, string> = {
    "豫园":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Yuyuan_Garden_pond.jpg/1280px-Yuyuan_Garden_pond.jpg",
    "上海自然博物馆":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/3/39/Shanghai_Natural_History_Museum_2015.jpg/1280px-Shanghai_Natural_History_Museum_2015.jpg",
    "静安寺":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f9/Jing%27an_Temple_202001.jpg/1280px-Jing%27an_Temple_202001.jpg",
    "思南公馆":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/1/16/Sinan_Mansions_Shanghai.jpg/1280px-Sinan_Mansions_Shanghai.jpg",
    "新天地":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e8/Xintiandi%2C_Shanghai.jpg/1280px-Xintiandi%2C_Shanghai.jpg",
    "田子坊":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/5/54/Tianzifang_01.jpg/1280px-Tianzifang_01.jpg",
    "陆家嘴滨江步道":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/5/54/Lujiazui_skyline_from_the_Bund.jpg/1280px-Lujiazui_skyline_from_the_Bund.jpg",
    "南京路步行街":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/5/54/Nanjing_Road_East_Pedestrian_Mall%2C_Shanghai.jpg/1280px-Nanjing_Road_East_Pedestrian_Mall%2C_Shanghai.jpg",
    "城隍庙小吃街":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d7/City_God_Temple_of_Shanghai.jpg/1280px-City_God_Temple_of_Shanghai.jpg",
    "BFC 外滩枫径":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/4/49/The_Bund%2C_Shanghai%2C_evening.jpg/1280px-The_Bund%2C_Shanghai%2C_evening.jpg",
    "武康路咖啡街区":
      "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0d/Wukang_Road_in_Shanghai.jpg/1280px-Wukang_Road_in_Shanghai.jpg",
  };

  return imageMap[name] ?? null;
}

function formatSparseDaySummary(day: SparseDaySummary): string {
  if (day.missing_blocks.length === 0) {
    return `${day.item_count} 个已排地点`;
  }
  return `light in ${day.missing_blocks.map(formatBlockTitle).join(" / ")}`;
}

function groupCompletionOptionsByDay(
  options: ItineraryCompletionOption[],
): Array<[number, ItineraryCompletionOption[]]> {
  const blockOrder: Record<ItineraryCompletionOption["suggested_block"], number> = {
    morning: 0,
    afternoon: 1,
    evening: 2,
  };

  const grouped = new Map<number, ItineraryCompletionOption[]>();
  const sorted = [...options].sort(
    (left, right) =>
      left.suggested_day - right.suggested_day ||
      blockOrder[left.suggested_block] - blockOrder[right.suggested_block] ||
      left.name.localeCompare(right.name),
  );

  for (const option of sorted) {
    const current = grouped.get(option.suggested_day) ?? [];
    current.push(option);
    grouped.set(option.suggested_day, current);
  }

  return [...grouped.entries()];
}

function getOrderedDayItems(day: DayItinerary): ScheduledItem[] {
  return day.blocks
    .flatMap((block) => block.items)
    .sort(
      (left, right) =>
        left.start_time.localeCompare(right.start_time) ||
        left.end_time.localeCompare(right.end_time) ||
        left.name.localeCompare(right.name),
    );
}

function getNextScheduledItem(
  orderedDayItems: ScheduledItem[],
  currentItem: ScheduledItem,
): {
  name: string;
  travelDistanceMeters: number | null;
  travelDurationSeconds: number;
  local_edit?: ScheduledItem["local_edit"];
} | null {
  const currentIndex = orderedDayItems.findIndex(
    (item) =>
      item.name === currentItem.name &&
      item.start_time === currentItem.start_time &&
      item.end_time === currentItem.end_time,
  );
  if (currentIndex < 0 || currentIndex === orderedDayItems.length - 1) {
    return null;
  }

  const nextItem = orderedDayItems[currentIndex + 1];
  if (nextItem.travel_duration_s === null) {
    return null;
  }

  return {
    name: nextItem.name,
    travelDistanceMeters: nextItem.travel_distance_m,
    travelDurationSeconds: nextItem.travel_duration_s,
  };
}

function getPreviousScheduledItem(
  orderedDayItems: ScheduledItem[],
  currentItem: ScheduledItem,
): ScheduledItem | null {
  const currentIndex = orderedDayItems.findIndex(
    (item) =>
      item.name === currentItem.name &&
      item.start_time === currentItem.start_time &&
      item.end_time === currentItem.end_time,
  );
  if (currentIndex <= 0) {
    return null;
  }
  return orderedDayItems[currentIndex - 1];
}

const dayTimelineDependencies = buildDayTimelineDependencies<
  ItineraryResponse,
  GenerationContext | null,
  UserIntentState,
  PreferenceSignals,
  PacingProfile,
  ItineraryCompletionOption
>({
  getOrderedDayItems,
  getNextScheduledItem,
  getPreviousScheduledItem,
  getScheduledItemSourceBadge,
  getScheduledItemFlexibilityBadge,
  canSwapScheduledItem,
  getSwapCandidates,
  buildSwapTargetKey,
  blockPanelStyle,
  blockEmoji,
  blockExplanation,
  formatBlockTitle,
  formatCompletionOptionType,
  buildCompletionOptionKey,
  formatEffectiveAvailabilityRange,
  formatRemainingBlocks: (remainingBlocks) =>
    formatRemainingBlocks(remainingBlocks as RemainingBlockWindow[]),
  getRemainingBlocks: (availabilitySummary) => availabilitySummary.remaining_blocks,
  formatTravelDuration,
  formatTravelDistance,
  formatItemLabel,
  formatTime,
});

function formatList(values: string[]): string {
  if (values.length === 0) {
    return "None";
  }
  return values.join(", ");
}

function formatStateLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatFixedEventSummary(events: ParsedFixedEvent[]): string {
  if (events.length === 0) {
    return "没有固定安排";
  }

  return events
    .map((event) => {
      const parts = [event.name];
      if (event.fixed_day !== null) {
        parts.push(`第 ${event.fixed_day} 天`);
      }
      if (event.fixed_time_start || event.fixed_time_end) {
        parts.push(`${event.fixed_time_start ?? "?"}-${event.fixed_time_end ?? "?"}`);
      }
      return parts.join(" · ");
    })
    .join(", ");
}

function formatAvailabilityWindows(windows: AvailabilityWindow[]): string {
  if (windows.length === 0) {
    return "None";
  }

  return windows
    .map((window) => {
      const parts = [
        window.day !== null ? `Day ${window.day}` : null,
        window.label,
        window.available_start || window.available_end
          ? `${window.available_start ?? "?"}-${window.available_end ?? "?"}`
          : null,
      ].filter(Boolean);

      return parts.join(" · ");
    })
    .join(", ");
}

function formatAvailabilityWindowsForExport(windows: AvailabilityWindow[]): string {
  return windows
    .slice(0, 3)
    .map((window) => {
      const dayLabel = window.day !== null ? `第${window.day}天` : "某天";
      const timeLabel =
        window.available_start || window.available_end
          ? `${window.available_start ?? "?"}-${window.available_end ?? "?"}`
          : null;
      return [dayLabel, window.label, timeLabel].filter(Boolean).join(" ");
    })
    .join("；");
}

function buildAvailabilityPreviewSignature(
  tripDaysValue: string | number,
  availabilityWindowsValue: string,
): string {
  const normalizedTripDays =
    typeof tripDaysValue === "number" ? String(tripDaysValue) : tripDaysValue.trim();
  const normalizedWindows = formatAvailabilityWindowsForTextarea(
    parseAvailabilityWindowLines(availabilityWindowsValue),
  );
  return `${normalizedTripDays}::${normalizedWindows}`;
}

function formatActiveConstraintsSummary(values: {
  tripDays: string;
  fixedEventsText: string;
  preferencesText: string;
  arrivalAnchor: string;
  departureAnchor: string;
  availabilityWindowsText: string;
}): string {
  const parts: string[] = [];

  if (values.tripDays.trim()) {
    parts.push(`天数：${values.tripDays.trim()}`);
  }

  const fixedEventCount = parseFixedEventLines(values.fixedEventsText).length;
  if (fixedEventCount > 0) {
    parts.push(`固定安排：${fixedEventCount}`);
  }

  const preferenceCount = splitLines(values.preferencesText).length;
  if (preferenceCount > 0) {
    parts.push(`偏好：${preferenceCount}`);
  }

  if (values.arrivalAnchor.trim()) {
    parts.push("到达锚点已启用");
  }

  if (values.departureAnchor.trim()) {
    parts.push("离开锚点已启用");
  }

  const availabilityCount = parseAvailabilityWindowLines(values.availabilityWindowsText).length;
  if (availabilityCount > 0) {
    parts.push(`可用时间：${availabilityCount}`);
  }

  if (parts.length === 0) {
    return "当前没有额外结构化约束。";
  }

  return parts.join(" · ");
}

function CandidateWorkspacePanel({
  state,
  onRefresh,
  onAdmit,
  onReject,
  onDefer,
  onRestore,
}: {
  state: CandidateWorkspaceState;
  onRefresh: () => void;
  onAdmit: (candidate: TripCandidate) => void;
  onReject: (candidate: TripCandidate) => void;
  onDefer: (candidate: TripCandidate) => void;
  onRestore: (candidate: TripCandidate) => void;
}) {
  if (state.status === "idle") {
    return null;
  }
  const pending = state.status === "ready" ? state.pending : [];
  const rejected = state.status === "ready" ? state.rejected : [];
  const deferred = state.status === "ready" ? state.deferred : [];
  const scheduled = state.status === "ready" ? state.scheduled : [];
  return (
    <section style={candidatePanelStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <div>
          <p style={candidateEyebrowStyle}>Candidate boundary</p>
          <h3 style={candidateTitleStyle}>待安排候选</h3>
        </div>
        <button type="button" onClick={onRefresh} className="ec-interactive-pill" style={miniGhostButtonStyle}>
          Refresh
        </button>
      </div>
      {state.status === "loading" ? (
        <p style={candidateMutedStyle}>正在读取候选池...</p>
      ) : state.status === "error" ? (
        <p style={candidateErrorStyle}>{state.message}</p>
      ) : (
        <div style={{ display: "grid", gap: 12 }}>
          <CandidateBucket
            title={`Pending · ${pending.length}`}
            candidates={pending}
            empty="还没有待安排候选。"
            actions={(candidate) => (
              <>
                <button type="button" onClick={() => onAdmit(candidate)} style={candidatePrimaryButtonStyle}>
                  Add to itinerary
                </button>
                <button type="button" onClick={() => onReject(candidate)} style={candidateSecondaryButtonStyle}>
                  Reject
                </button>
                <button type="button" onClick={() => onDefer(candidate)} style={candidateSecondaryButtonStyle}>
                  Defer
                </button>
              </>
            )}
          />
          <CandidateBucket
            title={`Rejected / Deferred · ${rejected.length + deferred.length}`}
            candidates={[...rejected, ...deferred]}
            empty="没有被拒绝或暂缓的候选。"
            actions={(candidate) => (
              <button type="button" onClick={() => onRestore(candidate)} style={candidateSecondaryButtonStyle}>
                Restore pending
              </button>
            )}
          />
          {scheduled.length > 0 ? (
            <CandidateBucket
              title={`Scheduled · ${scheduled.length}`}
              candidates={scheduled}
              empty=""
              actions={() => null}
            />
          ) : null}
        </div>
      )}
    </section>
  );
}

function CandidateBucket({
  title,
  candidates,
  empty,
  actions,
}: {
  title: string;
  candidates: TripCandidate[];
  empty: string;
  actions: (candidate: TripCandidate) => ReactNode;
}) {
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <strong style={{ color: "var(--ec-ink)", fontSize: 13 }}>{title}</strong>
      {candidates.length === 0 ? (
        <p style={candidateMutedStyle}>{empty}</p>
      ) : (
        candidates.map((candidate) => (
          <article key={candidate.id} style={candidateCardStyle}>
            <div style={{ minWidth: 0 }}>
              <p style={{ margin: 0, color: "var(--ec-ink)", fontWeight: 900, fontSize: 14 }}>
                {candidate.display_name}
              </p>
              <p style={candidateMutedStyle}>
                {candidate.source_kind} · location {candidate.location_state} · duration {candidate.duration_state}
              </p>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{actions(candidate)}</div>
          </article>
        ))
      )}
    </div>
  );
}

function formatCandidateRepairMessage(context?: Record<string, unknown>): string {
  const repair = context?.repair;
  if (!repair || typeof repair !== "object") {
    return "需要补充候选事实或调整插入位置。";
  }
  const missing = Array.isArray((repair as { missing_fact_codes?: unknown }).missing_fact_codes)
    ? ((repair as { missing_fact_codes: unknown[] }).missing_fact_codes).join(", ")
    : "";
  const conflicts = Array.isArray((repair as { conflict_codes?: unknown }).conflict_codes)
    ? ((repair as { conflict_codes: unknown[] }).conflict_codes).join(", ")
    : "";
  return [missing, conflicts].filter(Boolean).join("；") || "需要补充候选事实或调整插入位置。";
}

const candidatePanelStyle: CSSProperties = {
  display: "grid",
  gap: 14,
  padding: 16,
  borderRadius: 24,
  background: "linear-gradient(180deg, rgba(255,253,249,0.92), rgba(239,248,243,0.72))",
  border: "1px solid rgba(123,160,127,0.18)",
};

const candidateEyebrowStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 11,
  fontWeight: 900,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
};

const candidateTitleStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ink)",
  fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
  fontSize: 21,
  lineHeight: 1.15,
};

const candidateMutedStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 12,
  lineHeight: 1.55,
};

const candidateErrorStyle: CSSProperties = {
  margin: 0,
  color: "#9d302a",
  fontSize: 12,
  lineHeight: 1.55,
  fontWeight: 800,
};

const candidateCardStyle: CSSProperties = {
  display: "grid",
  gap: 10,
  padding: 12,
  borderRadius: 16,
  background: "rgba(255,255,255,0.74)",
  border: "1px solid rgba(21,21,21,0.08)",
};

const candidatePrimaryButtonStyle: CSSProperties = {
  border: "1px solid rgba(154, 106, 47, 0.18)",
  borderRadius: 999,
  padding: "7px 10px",
  backgroundColor: "rgba(154, 106, 47, 0.12)",
  color: "#7d5426",
  cursor: "pointer",
  fontSize: 12,
  fontWeight: 900,
};

const candidateSecondaryButtonStyle: CSSProperties = {
  border: "1px solid rgba(123, 160, 127, 0.18)",
  borderRadius: 999,
  padding: "7px 10px",
  backgroundColor: "rgba(255,255,255,0.72)",
  color: "#587663",
  cursor: "pointer",
  fontSize: 12,
  fontWeight: 800,
};

function getPlanningReadiness(values: {
  hotel: string;
  scenicSpots: string;
  restaurants: string;
  fixedEventsText: string;
}): { ready: boolean; message: string } {
  const scenicCount = splitLines(values.scenicSpots).length;
  const restaurantCount = splitLines(values.restaurants).length;
  const fixedEventCount = parseFixedEventLines(values.fixedEventsText).length;
  if (scenicCount + restaurantCount + fixedEventCount === 0) {
    return {
      ready: false,
      message: "至少补一个地点、餐食线索或固定安排，系统才能开始补全骨架。",
    };
  }

  return {
    ready: true,
    message: values.hotel.trim()
      ? "核心线索已就绪，住宿会作为可选锚点参与补全。"
      : "核心线索已就绪，不填酒店也可以先生成旅行骨架。",
  };
}
