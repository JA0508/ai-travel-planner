export type PrePlanPrimaryActionState = {
  sourcesChanged: boolean;
  canGeneratePreview: boolean;
  requiresTravelInformationEdit: boolean;
  remainingActionableConfirmationCount: number;
};

export function prePlanPrimaryActionLabel(state: PrePlanPrimaryActionState): string {
  if (state.sourcesChanged) return "请先重新整理旅行信息";
  if (state.requiresTravelInformationEdit) return "请先修改旅行信息";
  if (!state.canGeneratePreview) return `还差 ${state.remainingActionableConfirmationCount} 项待确认`;
  return "生成路线预览";
}
