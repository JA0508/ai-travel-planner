"use client";

import {
  buildCompletionOptionKey,
  buildSwapTargetKey,
} from "@/components/trip/tripSwapPolicy";

type SwapStateBlockType = "morning" | "afternoon" | "evening";
type SwapStateItemType = "scenic" | "restaurant" | "hotel";
type ReplaceableItemType = "scenic" | "restaurant";

export type SwapStateTarget = {
  day: number;
  block_type: SwapStateBlockType;
  start_time: string;
  end_time: string;
  name: string;
  type: SwapStateItemType;
};

type SwapStateOption = {
  name: string;
  type: ReplaceableItemType;
  suggested_day: number;
  suggested_block: SwapStateBlockType;
  reasoning_summary: string;
  itinerary_relation_summary: string;
};

type SwapStateScheduledItem = {
  name: string;
  type: SwapStateItemType;
  start_time: string;
  end_time: string;
  placement_reason: string | null;
  source_type?: string;
  source_label?: string | null;
  source_reason?: string | null;
  local_edit?: {
    previous_name: string;
    reasoning_summary: string;
    itinerary_relation_summary: string;
    original_type: SwapStateItemType;
    original_placement_reason: string | null;
    original_source_type?: string;
    original_source_label?: string | null;
    original_source_reason?: string | null;
  } | null;
};

type SwapStateItinerary<TOption extends SwapStateOption> = {
  days: Array<{
    day: number;
    blocks: Array<{
      block_type: SwapStateBlockType;
      items: SwapStateScheduledItem[];
    }>;
  }>;
  completion_recommendation: {
    options: TOption[];
  } | null;
};

export type CommittedSwapLike<TSource extends string = "completion_recommendation"> = {
  target_key: string;
  day: number;
  block_type: SwapStateBlockType;
  start_time: string;
  end_time: string;
  original_name: string;
  original_type: ReplaceableItemType;
  replacement_name: string;
  replacement_type: ReplaceableItemType;
  source: TSource;
  status: "user_confirmed";
  reasoning_summary: string;
  itinerary_relation_summary: string;
};

export type UserConfirmedReplacementLike<TSource extends string = "completion_recommendation"> = {
  original_name: string;
  original_type: ReplaceableItemType;
  replacement_name: string;
  replacement_type: ReplaceableItemType;
  source: TSource;
  reasoning_summary: string | null;
};

export function buildCommittedSwapSelectionFromOption<TOption extends SwapStateOption>(
  target: SwapStateTarget,
  option: TOption,
): CommittedSwapLike {
  return {
    target_key: buildSwapTargetKey(target),
    day: target.day,
    block_type: target.block_type,
    start_time: target.start_time,
    end_time: target.end_time,
    original_name: target.name,
    original_type: target.type === "restaurant" ? "restaurant" : "scenic",
    replacement_name: option.name,
    replacement_type: option.type,
    source: "completion_recommendation",
    status: "user_confirmed",
    reasoning_summary: option.reasoning_summary,
    itinerary_relation_summary: option.itinerary_relation_summary,
  };
}

export function buildUserConfirmedReplacementFromSwap<TSource extends string>(
  swap: CommittedSwapLike<TSource>,
): UserConfirmedReplacementLike<TSource> {
  return {
    original_name: swap.original_name,
    original_type: swap.original_type,
    replacement_name: swap.replacement_name,
    replacement_type: swap.replacement_type,
    source: swap.source,
    reasoning_summary: swap.reasoning_summary,
  };
}

export function upsertCommittedSwap<TSwap extends CommittedSwapLike>(
  current: TSwap[],
  next: TSwap,
): TSwap[] {
  const remaining = current.filter((item) => item.target_key !== next.target_key);
  return [...remaining, next];
}

export function applySwapToItinerary<
  TItinerary extends SwapStateItinerary<TOption>,
  TOption extends SwapStateOption,
>(
  itinerary: TItinerary,
  target: SwapStateTarget,
  option: TOption,
): TItinerary {
  return {
    ...itinerary,
    days: itinerary.days.map((day) => {
      if (day.day !== target.day) {
        return day;
      }

      return {
        ...day,
        blocks: day.blocks.map((block) => ({
          ...block,
          items: block.items.map((item) => {
            if (
              block.block_type !== target.block_type ||
              item.start_time !== target.start_time ||
              item.end_time !== target.end_time ||
              item.name !== target.name
            ) {
              return item;
            }

            return {
              ...item,
              name: option.name,
              type: option.type,
              placement_reason: `${option.reasoning_summary} This was swapped into the same time slot after generation.`,
              source_type: "user_seed",
              source_label: "User-confirmed replacement",
              source_reason:
                "The user selected this replacement, so it is treated as owned trip intent for future regeneration.",
              local_edit: {
                previous_name: item.name,
                source: "completion_recommendation",
                status: "committed",
                reasoning_summary: option.reasoning_summary,
                itinerary_relation_summary: option.itinerary_relation_summary,
                original_type: item.type,
                original_placement_reason: item.placement_reason,
                original_source_type: item.source_type,
                original_source_label: item.source_label,
                original_source_reason: item.source_reason,
              },
            };
          }),
        })),
      };
    }),
    completion_recommendation: itinerary.completion_recommendation
      ? {
          ...itinerary.completion_recommendation,
          options: itinerary.completion_recommendation.options.filter(
            (candidate) => buildCompletionOptionKey(candidate) !== buildCompletionOptionKey(option),
          ),
        }
      : itinerary.completion_recommendation,
  } as TItinerary;
}

export function undoSwapInItinerary<
  TItinerary extends SwapStateItinerary<TOption>,
  TOption extends SwapStateOption,
>(itinerary: TItinerary, target: SwapStateTarget): TItinerary {
  let restoredOption: TOption | null = null;

  return {
    ...itinerary,
    days: itinerary.days.map((day) => {
      if (day.day !== target.day) {
        return day;
      }

      return {
        ...day,
        blocks: day.blocks.map((block) => ({
          ...block,
          items: block.items.map((item) => {
            if (
              block.block_type !== target.block_type ||
              item.start_time !== target.start_time ||
              item.end_time !== target.end_time ||
              item.name !== target.name ||
              !item.local_edit
            ) {
              return item;
            }

            restoredOption = {
              name: item.name,
              type: item.type === "restaurant" ? "restaurant" : "scenic",
              suggested_day: target.day,
              suggested_block: target.block_type,
              reasoning_summary: item.local_edit.reasoning_summary,
              itinerary_relation_summary: item.local_edit.itinerary_relation_summary,
            } as TOption;

            return {
              ...item,
              name: item.local_edit.previous_name,
              type: item.local_edit.original_type,
              placement_reason: item.local_edit.original_placement_reason,
              source_type: item.local_edit.original_source_type,
              source_label: item.local_edit.original_source_label,
              source_reason: item.local_edit.original_source_reason,
              local_edit: null,
            };
          }),
        })),
      };
    }),
    completion_recommendation:
      itinerary.completion_recommendation && restoredOption !== null
        ? {
            ...itinerary.completion_recommendation,
            options: [...itinerary.completion_recommendation.options, restoredOption],
          }
        : itinerary.completion_recommendation,
  } as TItinerary;
}
