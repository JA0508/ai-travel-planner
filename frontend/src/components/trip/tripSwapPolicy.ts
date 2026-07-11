"use client";

export type PreferenceSignalKey =
  | "food"
  | "night"
  | "shopping"
  | "landmark"
  | "relaxed"
  | "indoor"
  | "outdoor"
  | "culture";

export type PreferenceSignals = Record<PreferenceSignalKey, number>;
export type SwapPolicyBlockType = "morning" | "afternoon" | "evening";
export type SwapPolicyItemType = "scenic" | "restaurant" | "hotel";
export type SwapPolicyPacingProfile = "relaxed" | "balanced" | "packed";

type FixedEventLike = {
  name: string;
};

type SwapContextLike = {
  scenic_spots: string[];
  restaurants: string[];
  fixed_events: FixedEventLike[];
  preferences: string[];
};

type SwapItemLike = {
  name: string;
  type: SwapPolicyItemType;
  is_fixed: boolean;
  local_edit?: unknown;
};

type SwapCompletionOptionLike = {
  name: string;
  type: "scenic" | "restaurant";
  suggested_day: number;
  suggested_block: SwapPolicyBlockType;
  reasoning_summary: string;
  itinerary_relation_summary: string;
};

type SwapItineraryLike<TOption extends SwapCompletionOptionLike> = {
  days: Array<{
    blocks: Array<{
      items: Array<{
        name: string;
      }>;
    }>;
  }>;
  completion_recommendation: {
    options: TOption[];
  } | null;
};

type UserIntentStateLike = {
  rejected_scenic: string[];
  rejected_restaurants: string[];
};

type CommittedSwapLike = {
  original_name: string;
  original_type: "scenic" | "restaurant";
  replacement_name: string;
  replacement_type: "scenic" | "restaurant";
  reasoning_summary: string;
  itinerary_relation_summary: string;
};

export type SwapTargetLike = {
  day: number;
  block_type: SwapPolicyBlockType;
  start_time: string;
  end_time: string;
};

export function normalizeComparisonName(value: string): string {
  return value.trim().toLocaleLowerCase();
}

export function uniquePreserveOrder(values: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const value of values) {
    if (seen.has(value)) {
      continue;
    }
    seen.add(value);
    result.push(value);
  }

  return result;
}

export function createEmptyPreferenceSignals(): PreferenceSignals {
  return {
    food: 0,
    night: 0,
    shopping: 0,
    landmark: 0,
    relaxed: 0,
    indoor: 0,
    outdoor: 0,
    culture: 0,
  };
}

export function derivePreferenceSignalsFromCommittedSwaps(
  swaps: CommittedSwapLike[],
): PreferenceSignals {
  const scores = createEmptyPreferenceSignals();

  for (const swap of swaps) {
    const replacementSignals = inferSignalsFromPoi(
      swap.replacement_name,
      swap.replacement_type,
      `${swap.reasoning_summary} ${swap.itinerary_relation_summary}`,
    );
    const originalSignals = inferSignalsFromPoi(swap.original_name, swap.original_type);

    for (const key of Object.keys(scores) as PreferenceSignalKey[]) {
      scores[key] += replacementSignals[key];
      scores[key] -= originalSignals[key];
    }
  }

  return scores;
}

export function inferSignalsFromPoi(
  name: string,
  poiType: "scenic" | "restaurant",
  extraText: string = "",
): PreferenceSignals {
  const normalized = `${name} ${extraText}`.toLocaleLowerCase();
  const signals = createEmptyPreferenceSignals();

  if (/(餐|吃|小吃|美食|咖啡|food|dining|market|夜市)/i.test(normalized)) {
    signals.food += 1;
  }
  if (/(夜景|夜游|夜市|酒吧|晚餐|night|evening)/i.test(normalized)) {
    signals.night += 1;
  }
  if (/(街|步行街|街区|商场|shopping|district|market)/i.test(normalized)) {
    signals.shopping += 1;
  }
  if (/(轻松|漫步|咖啡|relaxed|easy|stroll)/i.test(normalized)) {
    signals.relaxed += 1;
  }
  if (/(博物馆|美术馆|展览|室内|museum|gallery|indoor)/i.test(normalized)) {
    signals.indoor += 1;
    signals.culture += 1;
  }
  if (/(公园|滨江|步道|户外|park|garden|waterfront|outdoor)/i.test(normalized)) {
    signals.outdoor += 1;
  }
  if (/(地标|塔|外滩|寺|广场|landmark|temple|tower)/i.test(normalized)) {
    signals.landmark += 1;
  }
  if (/(历史|文化|museum|gallery|temple|古迹|展馆)/i.test(normalized)) {
    signals.culture += 1;
  }

  if (poiType === "restaurant") {
    signals.food += 1;
    if (signals.relaxed === 0 && /(咖啡|brunch|tea)/i.test(normalized)) {
      signals.relaxed += 1;
    }
  }
  if (poiType === "scenic") {
    if (signals.landmark === 0 && /(塔|外滩|寺|古镇|地标)/i.test(normalized)) {
      signals.landmark += 1;
    }
    if (signals.culture === 0 && /(博物馆|美术馆|历史|古迹|展馆)/i.test(normalized)) {
      signals.culture += 1;
    }
  }

  return signals;
}

export function buildEffectivePreferences(
  explicitPreferences: string[],
  preferenceSignals: PreferenceSignals,
  pacingProfile: SwapPolicyPacingProfile,
): string[] {
  return uniquePreserveOrder([
    ...explicitPreferences,
    ...buildPacingPreferencePhrases(pacingProfile),
    ...buildPreferenceSignalPreferencePhrases(preferenceSignals),
  ]);
}

export function buildPacingPreferencePhrases(
  pacingProfile: SwapPolicyPacingProfile,
): string[] {
  if (pacingProfile === "relaxed") {
    return ["轻松", "别太赶", "留一点机动时间"];
  }
  if (pacingProfile === "packed") {
    return ["尽量排满", "多逛", "高效覆盖主要地点"];
  }
  return [];
}

export function buildPreferenceSignalPreferencePhrases(
  preferenceSignals: PreferenceSignals,
): string[] {
  const phrases: string[] = [];

  if (preferenceSignals.food >= 2) {
    phrases.push("偏向美食和餐饮体验");
  }
  if (preferenceSignals.night >= 1) {
    phrases.push("晚上更适合夜景和夜间活动");
  }
  if (preferenceSignals.shopping >= 1) {
    phrases.push("喜欢可逛的街区和热闹步行街");
  }
  if (preferenceSignals.relaxed >= 1) {
    phrases.push("偏向轻松漫步的节奏");
  }
  if (preferenceSignals.indoor >= 1) {
    phrases.push("对室内型地点接受度更高");
  }
  if (preferenceSignals.outdoor >= 1) {
    phrases.push("偏向户外散步和开放空间");
  }
  if (preferenceSignals.landmark >= 1) {
    phrases.push("愿意保留城市地标型地点");
  }
  if (preferenceSignals.culture >= 1) {
    phrases.push("对文化和展览型地点接受度更高");
  }

  return phrases;
}

export function getStrongPreferenceSignalLabels(
  preferenceSignals: PreferenceSignals,
): string[] {
  const labels: string[] = [];
  if (preferenceSignals.food >= 2) {
    labels.push("Food");
  }
  if (preferenceSignals.night >= 1) {
    labels.push("Night");
  }
  if (preferenceSignals.shopping >= 1) {
    labels.push("Shopping");
  }
  if (preferenceSignals.landmark >= 1) {
    labels.push("Landmark");
  }
  if (preferenceSignals.relaxed >= 1) {
    labels.push("Relaxed");
  }
  if (preferenceSignals.indoor >= 1) {
    labels.push("Indoor");
  }
  if (preferenceSignals.outdoor >= 1) {
    labels.push("Outdoor");
  }
  if (preferenceSignals.culture >= 1) {
    labels.push("Culture");
  }
  return labels;
}

export function canSwapScheduledItem(
  item: SwapItemLike,
  context: SwapContextLike | null,
): boolean {
  if (item.is_fixed || item.type === "hotel" || item.local_edit) {
    return false;
  }
  if (!context) {
    return true;
  }

  const userSelectedNames = new Set([
    ...context.scenic_spots.map(normalizeComparisonName),
    ...context.restaurants.map(normalizeComparisonName),
    ...context.fixed_events.map((event) => normalizeComparisonName(event.name)),
  ]);

  return !userSelectedNames.has(normalizeComparisonName(item.name));
}

export function buildCompletionOptionKey(option: SwapCompletionOptionLike): string {
  return `${option.name}-${option.suggested_day}-${option.suggested_block}-${option.type}`;
}

export function buildSwapTargetKey(target: SwapTargetLike): string {
  return `${target.day}-${target.block_type}-${target.start_time}-${target.end_time}`;
}

export function getSwapCandidates<TOption extends SwapCompletionOptionLike>(
  itinerary: SwapItineraryLike<TOption>,
  day: number,
  blockType: SwapPolicyBlockType,
  item: SwapItemLike,
  context: SwapContextLike | null,
  userIntentState: UserIntentStateLike,
  preferenceSignals: PreferenceSignals,
  pacingProfile: SwapPolicyPacingProfile,
): TOption[] {
  const options = itinerary.completion_recommendation?.options ?? [];
  if (options.length === 0) {
    return [];
  }

  const scheduledNames = new Set(
    itinerary.days
      .flatMap((itineraryDay) => itineraryDay.blocks.flatMap((block) => block.items))
      .map((scheduledItem) => normalizeComparisonName(scheduledItem.name)),
  );
  const rejectedNames = new Set([
    ...userIntentState.rejected_scenic.map(normalizeComparisonName),
    ...userIntentState.rejected_restaurants.map(normalizeComparisonName),
  ]);
  const currentName = normalizeComparisonName(item.name);

  return [...options]
    .filter((option) => {
      const normalizedOptionName = normalizeComparisonName(option.name);
      return (
        normalizedOptionName !== currentName &&
        !scheduledNames.has(normalizedOptionName) &&
        !rejectedNames.has(normalizedOptionName)
      );
    })
    .sort((left, right) => {
      const leftScore = scoreSwapOption(
        left,
        day,
        blockType,
        item.type,
        context,
        preferenceSignals,
        pacingProfile,
      );
      const rightScore = scoreSwapOption(
        right,
        day,
        blockType,
        item.type,
        context,
        preferenceSignals,
        pacingProfile,
      );
      if (leftScore !== rightScore) {
        return leftScore - rightScore;
      }
      return left.name.localeCompare(right.name);
    })
    .slice(0, 4);
}

function scoreSwapOption(
  option: SwapCompletionOptionLike,
  day: number,
  blockType: SwapPolicyBlockType,
  currentType: SwapPolicyItemType,
  context: SwapContextLike | null,
  preferenceSignals: PreferenceSignals,
  pacingProfile: SwapPolicyPacingProfile,
): number {
  let score = 100;
  if (option.suggested_day === day) {
    score -= 40;
  }
  if (option.suggested_block === blockType) {
    score -= 30;
  }
  if (option.type === currentType) {
    score -= 20;
  }
  score -= swapPreferenceAlignmentScore(option, blockType, context);
  score -= scoreOptionAgainstPreferenceSignals(option, preferenceSignals);
  score -= scoreOptionAgainstPacingProfile(option, pacingProfile);
  return score;
}

function swapPreferenceAlignmentScore(
  option: SwapCompletionOptionLike,
  blockType: SwapPolicyBlockType,
  context: SwapContextLike | null,
): number {
  let score = 0;
  const optionText = `${option.name} ${option.reasoning_summary} ${option.itinerary_relation_summary}`;

  if (
    blockType === "evening" &&
    /(夜景|夜游|晚餐|吃饭|food|night)/i.test(optionText)
  ) {
    score += 18;
  }
  if (
    blockType === "morning" &&
    /(博物馆|公园|museum|garden|daytime)/i.test(optionText)
  ) {
    score += 8;
  }
  if (!context) {
    return score;
  }

  for (const preference of context.preferences) {
    if (/(夜景|晚上|夜游)/.test(preference) && /(夜景|夜游|night)/i.test(optionText)) {
      score += 12;
    }
    if (/(美食|吃|餐|小吃|本帮菜)/.test(preference) && /(吃|餐|小吃|food|dining)/i.test(optionText)) {
      score += 12;
    }
    if (/(老街|街区|逛)/.test(preference) && /(街|街区|walk|district|old street)/i.test(optionText)) {
      score += 10;
    }
    if (/(轻松|休息|不要太赶)/.test(preference) && /(轻松|漫步|relaxed|easy)/i.test(optionText)) {
      score += 8;
    }
  }

  return score;
}

function scoreOptionAgainstPacingProfile(
  option: SwapCompletionOptionLike,
  pacingProfile: SwapPolicyPacingProfile,
): number {
  if (pacingProfile === "balanced") {
    return 0;
  }

  const optionSignals = inferSignalsFromPoi(
    option.name,
    option.type,
    `${option.reasoning_summary} ${option.itinerary_relation_summary}`,
  );

  if (pacingProfile === "relaxed") {
    let score = 0;
    if (optionSignals.relaxed > 0) {
      score += 12;
    }
    if (optionSignals.outdoor > 0) {
      score += 6;
    }
    if (optionSignals.food > 0 && option.type === "restaurant") {
      score += 4;
    }
    if (optionSignals.landmark > 0 || optionSignals.shopping > 0) {
      score -= 4;
    }
    return score;
  }

  let score = 0;
  if (optionSignals.landmark > 0) {
    score += 12;
  }
  if (optionSignals.culture > 0) {
    score += 6;
  }
  if (optionSignals.shopping > 0) {
    score += 4;
  }
  if (optionSignals.relaxed > 0) {
    score -= 3;
  }
  return score;
}

function scoreOptionAgainstPreferenceSignals(
  option: SwapCompletionOptionLike,
  preferenceSignals: PreferenceSignals,
): number {
  let score = 0;
  const optionSignals = inferSignalsFromPoi(
    option.name,
    option.type,
    `${option.reasoning_summary} ${option.itinerary_relation_summary}`,
  );

  for (const key of Object.keys(preferenceSignals) as PreferenceSignalKey[]) {
    if (preferenceSignals[key] > 0 && optionSignals[key] > 0) {
      score += Math.min(preferenceSignals[key], 3) * optionSignals[key] * 6;
    }
  }

  return score;
}
