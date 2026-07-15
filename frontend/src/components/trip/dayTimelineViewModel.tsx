"use client";

import {
  type DayTimelineDayViewModel,
} from "@/components/trip/DayTimeline";
import {
  ItineraryStopCard,
  type OwnershipBadgeViewModel,
} from "@/components/trip/ItineraryStopCard";

type TimelineBlockType = "morning" | "afternoon" | "evening";
export type TimelineItemType = "scenic" | "restaurant" | "hotel";

type AvailabilitySummaryLike = {
  was_trimmed: boolean;
};

type ScheduledItemLike = {
  stable_id?: string | null;
  name: string;
  type: TimelineItemType;
  start_time: string;
  end_time: string;
  is_fixed: boolean;
  placement_reason: string | null;
  travel_from_name: string | null;
  travel_distance_m: number | null;
  travel_duration_s: number | null;
  local_edit?: {
    previous_name: string;
    reasoning_summary: string;
    itinerary_relation_summary: string;
  } | null;
};

type DayBlockLike = {
  block_type: TimelineBlockType;
  start_time: string;
  end_time: string;
  items: ScheduledItemLike[];
};

type DayItineraryLike = {
  day: number;
  availability_summary: AvailabilitySummaryLike;
  blocks: DayBlockLike[];
};

export type ItineraryResponseLike = {
  days: DayItineraryLike[];
};

type DayOf<TResult extends ItineraryResponseLike> = TResult["days"][number];
type BlockOf<TResult extends ItineraryResponseLike> = DayOf<TResult>["blocks"][number];
type ItemOf<TResult extends ItineraryResponseLike> = BlockOf<TResult>["items"][number];

type TravelEdgeLike = {
  name: string;
  travelDurationSeconds: number;
  travelDistanceMeters: number | null;
  local_edit?: ScheduledItemLike["local_edit"];
};

export type DayTimelineSwapTarget = {
  stable_id?: string | null;
  day: number;
  block_type: TimelineBlockType;
  start_time: string;
  end_time: string;
  name: string;
  type: TimelineItemType;
};

export type CompletionOptionLike = {
  name: string;
  type: "scenic" | "restaurant";
  suggested_day: number;
  suggested_block: TimelineBlockType;
  reasoning_summary: string;
  itinerary_relation_summary: string;
};

type BlockPanelStyle = {
  backgroundColor: string;
  borderColor: string;
};

export type DayTimelineDependencies<
  TResult extends ItineraryResponseLike,
  TContext,
  TUserIntentState,
  TPreferenceSignals,
  TPacingProfile,
  TOption extends CompletionOptionLike,
> = {
  getOrderedDayItems: (day: DayOf<TResult>) => ItemOf<TResult>[];
  getNextScheduledItem: (
    orderedItems: ItemOf<TResult>[],
    item: ItemOf<TResult>,
  ) => TravelEdgeLike | null;
  getPreviousScheduledItem: (
    orderedItems: ItemOf<TResult>[],
    item: ItemOf<TResult>,
  ) => ItemOf<TResult> | null;
  getScheduledItemSourceBadge: (
    item: ItemOf<TResult>,
    context: TContext,
    userIntentState: TUserIntentState,
  ) => OwnershipBadgeViewModel | null;
  getScheduledItemFlexibilityBadge: (
    item: ItemOf<TResult>,
  ) => OwnershipBadgeViewModel | null;
  canSwapScheduledItem: (item: ItemOf<TResult>, context: TContext) => boolean;
  getSwapCandidates: (
    result: TResult,
    day: number,
    blockType: TimelineBlockType,
    item: ItemOf<TResult>,
    context: TContext,
    userIntentState: TUserIntentState,
    preferenceSignals: TPreferenceSignals,
    pacingProfile: TPacingProfile,
  ) => TOption[];
  buildSwapTargetKey: (target: DayTimelineSwapTarget) => string;
  blockPanelStyle: (blockType: TimelineBlockType) => BlockPanelStyle;
  blockEmoji: (blockType: TimelineBlockType) => string;
  blockExplanation: (blockType: TimelineBlockType) => string;
  formatBlockTitle: (blockType: TimelineBlockType) => string;
  formatCompletionOptionType: (type: TOption["type"]) => string;
  buildCompletionOptionKey: (option: TOption) => string;
  formatEffectiveAvailabilityRange: (
    availabilitySummary: DayOf<TResult>["availability_summary"],
  ) => string;
  formatRemainingBlocks: (remainingBlocks: unknown) => string;
  getRemainingBlocks: (availabilitySummary: DayOf<TResult>["availability_summary"]) => unknown;
  formatTravelDuration: (durationSeconds: number) => string;
  formatTravelDistance: (distanceMeters: number) => string;
  formatItemLabel: (type: TimelineItemType) => string;
  formatTime: (value: string) => string;
};

export type BuildDayTimelineViewModelParams<
  TResult extends ItineraryResponseLike,
  TContext,
  TUserIntentState,
  TPreferenceSignals,
  TPacingProfile,
  TOption extends CompletionOptionLike,
> = {
  result: TResult;
  generationContext: TContext;
  userIntentState: TUserIntentState;
  preferenceSignals: TPreferenceSignals;
  pacingProfile: TPacingProfile;
  activeSwapTarget: DayTimelineSwapTarget | null;
  recentCompletionTaskItemKey?: string | null;
  dependencies: DayTimelineDependencies<
    TResult,
    TContext,
    TUserIntentState,
    TPreferenceSignals,
    TPacingProfile,
    TOption
  >;
  onApplySwap: (target: DayTimelineSwapTarget, option: TOption) => void;
  onUndoSwap: (target: DayTimelineSwapTarget) => void;
  onToggleSwap: (target: DayTimelineSwapTarget) => void;
};

export function buildDayTimelineViewModel<
  TResult extends ItineraryResponseLike,
  TContext,
  TUserIntentState,
  TPreferenceSignals,
  TPacingProfile,
  TOption extends CompletionOptionLike,
>({
  result,
  generationContext,
  userIntentState,
  preferenceSignals,
  pacingProfile,
  activeSwapTarget,
  recentCompletionTaskItemKey,
  dependencies,
  onApplySwap,
  onUndoSwap,
  onToggleSwap,
}: BuildDayTimelineViewModelParams<
  TResult,
  TContext,
  TUserIntentState,
  TPreferenceSignals,
  TPacingProfile,
  TOption
>): DayTimelineDayViewModel[] {
  const {
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
    formatRemainingBlocks,
    getRemainingBlocks,
    formatTravelDuration,
    formatTravelDistance,
    formatItemLabel,
    formatTime,
  } = dependencies;

  return result.days.map((day) => {
    const orderedDayItems = getOrderedDayItems(day);

    return {
      key: `day-${day.day}`,
      dayLabel: `DAY ${day.day}`,
      availabilityLabel: day.availability_summary.was_trimmed
        ? `可用时间 ${formatEffectiveAvailabilityRange(day.availability_summary)}`
        : "完整日程窗口",
      remainingBlocksLabel: day.availability_summary.was_trimmed
        ? `剩余时段：${formatRemainingBlocks(getRemainingBlocks(day.availability_summary))}`
        : undefined,
      blocks: day.blocks.map((block) => {
        const blockStyle = blockPanelStyle(block.block_type);

        return {
          key: `${day.day}-${block.block_type}`,
          title: `${blockEmoji(block.block_type)} ${formatBlockTitle(block.block_type)}`,
          timeRangeLabel: `${block.start_time} - ${block.end_time}`,
          explanation: blockExplanation(block.block_type),
          backgroundColor: blockStyle.backgroundColor,
          borderColor: blockStyle.borderColor,
          stops: block.items.map((item) => {
            const nextStop = getNextScheduledItem(orderedDayItems, item);
            const previousStop = getPreviousScheduledItem(orderedDayItems, item);
            const sourceBadge = getScheduledItemSourceBadge(
              item,
              generationContext,
              userIntentState,
            );
            const flexibilityBadge = getScheduledItemFlexibilityBadge(item);
            const canSwap = canSwapScheduledItem(item, generationContext);
            const swapTarget: DayTimelineSwapTarget = {
              stable_id: item.stable_id ?? null,
              day: day.day,
              block_type: block.block_type,
              start_time: item.start_time,
              end_time: item.end_time,
              name: item.name,
              type: item.type,
            };
            const swapOptions = getSwapCandidates(
              result,
              day.day,
              block.block_type,
              item,
              generationContext,
              userIntentState,
              preferenceSignals,
              pacingProfile,
            );
            const swapIsOpen =
              activeSwapTarget !== null &&
              buildSwapTargetKey(activeSwapTarget) === buildSwapTargetKey(swapTarget);
            const stopKey = `${day.day}-${block.block_type}-${item.name}-${item.start_time}`;
            const isRecentlyInsertedByCompletionTask =
              recentCompletionTaskItemKey === buildRecentCompletionTaskItemKey(item);
            const recentlyInsertedBadge: OwnershipBadgeViewModel | null =
              isRecentlyInsertedByCompletionTask
                ? {
                    label: "刚刚补入",
                    tone: "fresh",
                  }
                : null;
            const badges = [recentlyInsertedBadge, sourceBadge, flexibilityBadge].filter(
              (badge): badge is OwnershipBadgeViewModel => badge !== null,
            );
            const travelFromLine =
              !item.is_fixed &&
              !item.local_edit &&
              !previousStop?.local_edit &&
              item.travel_from_name &&
              item.travel_duration_s !== null
                ? `从 ${item.travel_from_name} 出发 · ${formatTravelDuration(item.travel_duration_s)}${
                    item.travel_distance_m !== null
                      ? ` · ${formatTravelDistance(item.travel_distance_m)}`
                      : ""
                  }`
                : undefined;
            const travelToLine =
              nextStop && !item.local_edit && !nextStop.local_edit
                ? `去 ${nextStop.name} · ${formatTravelDuration(nextStop.travelDurationSeconds)}${
                    nextStop.travelDistanceMeters !== null
                      ? ` · ${formatTravelDistance(nextStop.travelDistanceMeters)}`
                      : ""
                  }`
                : undefined;

            return (
              <ItineraryStopCard
                key={stopKey}
                stop={{
                  key: stopKey,
                  name: item.name,
                  itemTypeLabel: formatItemLabel(item.type),
                  timeLabel: formatTime(item.start_time),
                  timeRangeLabel: `${item.start_time} - ${item.end_time}`,
                  badges,
                  highlightTone: isRecentlyInsertedByCompletionTask
                    ? "completion-task"
                    : undefined,
                  completionTaskNotice: isRecentlyInsertedByCompletionTask
                    ? "这是刚刚通过补全任务加入的新地点，已经进入当前旅行骨架。"
                    : undefined,
                  localEditNotice: item.local_edit
                    ? `已确认替换：你把 ${item.local_edit.previous_name} 改成了 ${item.name}，已加入你的行程偏好，并且不再优先推荐原来的点。 ${item.local_edit.reasoning_summary} ${item.local_edit.itinerary_relation_summary}`
                    : undefined,
                  placementReason: item.placement_reason ?? undefined,
                  travelFromLine,
                  travelToLine,
                  undoHint: item.local_edit
                    ? "这个替换已经被视为你的确认选择，撤销会回到原始地点。"
                    : undefined,
                  swapHint: "保留当前时间段，只替换这个地点。",
                  canSwap,
                  swapIsOpen,
                  swapCandidates: swapOptions.map((option) => ({
                    key: `${buildCompletionOptionKey(option)}-swap`,
                    name: option.name,
                    meta: `${formatCompletionOptionType(option.type)} · 第 ${option.suggested_day} 天 · ${formatBlockTitle(option.suggested_block)}`,
                    reasoningSummary: option.reasoning_summary,
                    relationSummary: option.itinerary_relation_summary,
                    onSelect: () => onApplySwap(swapTarget, option),
                  })),
                  onToggleSwap: () => onToggleSwap(swapTarget),
                  onUndo: item.local_edit ? () => onUndoSwap(swapTarget) : undefined,
                }}
              />
            );
          }),
        };
      }),
    };
  });
}

export function buildRecentCompletionTaskItemKey(item: {
  name: string;
  type: TimelineItemType;
  start_time: string;
  end_time: string;
}): string {
  return `${item.type}-${item.name}-${item.start_time}-${item.end_time}`;
}
