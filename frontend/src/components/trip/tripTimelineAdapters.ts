"use client";

import {
  type DayTimelineDependencies,
  type CompletionOptionLike,
  type ItineraryResponseLike,
} from "@/components/trip/dayTimelineViewModel";

export function buildDayTimelineDependencies<
  TResult extends ItineraryResponseLike,
  TContext,
  TUserIntentState,
  TPreferenceSignals,
  TPacingProfile,
  TOption extends CompletionOptionLike,
>(
  dependencies: DayTimelineDependencies<
    TResult,
    TContext,
    TUserIntentState,
    TPreferenceSignals,
    TPacingProfile,
    TOption
  >,
) {
  return dependencies;
}
