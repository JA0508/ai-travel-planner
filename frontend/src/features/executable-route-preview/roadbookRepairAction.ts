export type RoadbookRepairStatus =
  | "idle"
  | "previewing"
  | "review"
  | "applying"
  | "undoing"
  | "applied"
  | "restored"
  | "reloaded"
  | "error";

type RoadbookRelaxActionInput = {
  day: number;
  repairStatus: RoadbookRepairStatus;
  repairDay?: number;
  blocked: boolean;
};

export type RoadbookRelaxAction = {
  label: string;
  ariaLabel: string;
  disabled: boolean;
  showArrow: boolean;
};

export function buildRoadbookRelaxAction({
  day,
  repairStatus,
  repairDay,
  blocked,
}: RoadbookRelaxActionInput): RoadbookRelaxAction {
  if (repairStatus === "previewing") {
    const activeDay = repairDay ?? day;
    return {
      label: "正在评估调整…",
      ariaLabel: `正在评估第 ${activeDay} 天的放松调整`,
      disabled: true,
      showArrow: false,
    };
  }
  if (repairStatus === "applying") {
    const activeDay = repairDay ?? day;
    return {
      label: "正在保存调整…",
      ariaLabel: `正在保存第 ${activeDay} 天的调整`,
      disabled: true,
      showArrow: false,
    };
  }
  if (repairStatus === "undoing") {
    return {
      label: "正在恢复路线…",
      ariaLabel: "正在恢复调整前的路线",
      disabled: true,
      showArrow: false,
    };
  }
  if (repairStatus === "review") {
    const activeDay = repairDay ?? day;
    return {
      label: "请先决定当前调整",
      ariaLabel: `请先决定第 ${activeDay} 天的调整，再开始新的调整`,
      disabled: true,
      showArrow: false,
    };
  }
  if (blocked) {
    return {
      label: "请先完成当前调整",
      ariaLabel: `请先完成当前调整，暂时不能调整第 ${day} 天`,
      disabled: true,
      showArrow: false,
    };
  }
  return {
    label: "帮我松一点",
    ariaLabel: `让第 ${day} 天轻松一些`,
    disabled: false,
    showArrow: true,
  };
}
