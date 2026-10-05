export type PrePlanPrimaryActionState = {
  sourcesChanged: boolean;
  canGeneratePreview: boolean;
  requiresTravelInformationEdit: boolean;
  remainingActionableConfirmationCount: number;
};

export type PrePlanPrimaryAction = {
  kind: "preview" | "modify_request" | "refresh_intent" | "blocked";
  label: string;
};

export function prePlanPrimaryAction(state: PrePlanPrimaryActionState): PrePlanPrimaryAction {
  if (state.sourcesChanged) return { kind: "refresh_intent", label: "重新整理旅行信息" };
  if (state.requiresTravelInformationEdit) return { kind: "modify_request", label: "请先修改旅行信息" };
  if (!state.canGeneratePreview) return { kind: "blocked", label: `还差 ${state.remainingActionableConfirmationCount} 项待确认` };
  return { kind: "preview", label: "生成路线预览" };
}

export function prePlanPrimaryActionLabel(state: PrePlanPrimaryActionState): string {
  return prePlanPrimaryAction(state).label;
}
