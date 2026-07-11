"use client";

export type TripBlockType = "morning" | "afternoon" | "evening";
export type TripItemType = "scenic" | "restaurant" | "hotel";
export type PacingProfileLike = "relaxed" | "balanced" | "packed";
export type TravelModeLike = "airplane" | "high_speed_rail" | "rail" | "car" | "undecided";

export type DayAvailabilitySummaryLike = {
  effective_start: string | null;
  effective_end: string | null;
};

export type RemainingBlockWindowLike = {
  block_type: TripBlockType;
  start_time: string;
  end_time: string;
};

export function blockPanelStyle(blockType: TripBlockType) {
  if (blockType === "morning") {
    return {
      backgroundColor: "#f8fbff",
      borderColor: "rgba(123, 168, 230, 0.22)",
    };
  }
  if (blockType === "afternoon") {
    return {
      backgroundColor: "#fff9f2",
      borderColor: "rgba(225, 173, 91, 0.22)",
    };
  }
  return {
    backgroundColor: "#fbf8ff",
    borderColor: "rgba(160, 124, 214, 0.18)",
  };
}

export function formatBlockTitle(blockType: TripBlockType): string {
  if (blockType === "morning") {
    return "上午";
  }
  if (blockType === "afternoon") {
    return "下午";
  }
  return "晚上";
}

export function formatBlockTitleForExport(blockType: TripBlockType): string {
  if (blockType === "morning") {
    return "上午";
  }
  if (blockType === "afternoon") {
    return "下午";
  }
  return "晚上";
}

export function blockEmoji(blockType: TripBlockType): string {
  if (blockType === "morning") {
    return "🌅";
  }
  if (blockType === "afternoon") {
    return "🌇";
  }
  return "🌙";
}

export function blockExplanation(blockType: TripBlockType): string {
  if (blockType === "morning") {
    return "先放近一点的景点，开场更顺。";
  }
  if (blockType === "afternoon") {
    return "继续安排当天的主要景点。";
  }
  return "用餐食或轻活动把晚上收住。";
}

export function formatPlanningAnchorSourceType(sourceType: string): string {
  if (sourceType === "provided_hotel") {
    return "已提供住宿";
  }
  if (sourceType === "arrival_anchor") {
    return "到达锚点";
  }
  if (sourceType === "departure_anchor") {
    return "离开锚点";
  }
  return "路线中心点";
}

export function formatTravelMode(mode: TravelModeLike): string {
  if (mode === "airplane") {
    return "飞机";
  }
  if (mode === "high_speed_rail") {
    return "高铁";
  }
  if (mode === "rail") {
    return "火车";
  }
  if (mode === "car") {
    return "自驾";
  }
  return "待确定";
}

export function formatEffectiveAvailabilityRange(summary: DayAvailabilitySummaryLike): string {
  if (!summary.effective_start || !summary.effective_end) {
    return "暂无可排时间";
  }
  return `${formatTime(summary.effective_start)}-${formatTime(summary.effective_end)}`;
}

export function formatRemainingBlocks(blocks: RemainingBlockWindowLike[]): string {
  if (blocks.length === 0) {
    return "无";
  }

  return blocks
    .map(
      (block) =>
        `${formatBlockTitle(block.block_type)} ${formatTime(block.start_time)}-${formatTime(block.end_time)}`,
    )
    .join(", ");
}

export function formatItemLabel(type: TripItemType): string {
  if (type === "scenic") {
    return "景点";
  }
  if (type === "restaurant") {
    return "餐食";
  }
  return "住宿";
}

export function formatTime(value: string): string {
  return value.slice(0, 5);
}

export function formatTravelDuration(durationSeconds: number): string {
  const minutes = Math.round(durationSeconds / 60);
  return `步行 ${minutes} 分钟`;
}

export function formatTravelDistance(distanceMeters: number): string {
  if (distanceMeters >= 1000) {
    return `${(distanceMeters / 1000).toFixed(1)} km`;
  }
  return `${distanceMeters} m`;
}

export function formatPacingProfileLabel(pacingProfile: PacingProfileLike): string {
  if (pacingProfile === "relaxed") {
    return "轻松";
  }
  if (pacingProfile === "packed") {
    return "紧凑";
  }
  return "平衡";
}

export function describePacingProfile(pacingProfile: PacingProfileLike): string {
  if (pacingProfile === "relaxed") {
    return "留更多余量，少赶路，允许一天里有呼吸感。";
  }
  if (pacingProfile === "packed") {
    return "在时间允许时尽量多覆盖，但仍保留基本可执行性。";
  }
  return "在效率和舒适之间取中间值，路线能走，也不会太满。";
}

export function describePacingOutcome(pacingProfile: PacingProfileLike): string {
  if (pacingProfile === "relaxed") {
    return "更轻松、更有余量";
  }
  if (pacingProfile === "packed") {
    return "更紧凑、覆盖更多";
  }
  return "平衡且可执行";
}

export function formatCompletionOptionType(type: "scenic" | "restaurant"): string {
  return type === "restaurant" ? "餐食候选" : "地点候选";
}
