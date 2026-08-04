export type PrePlanHandoffStatus = {
  kind: "current" | "stale";
  canApply: boolean;
  canGenerateReplacement: boolean;
  message: string;
};

export function buildPrePlanHandoffStatus({
  previewIntentRevisionId,
  latestIntentRevisionId,
}: {
  previewIntentRevisionId: string;
  latestIntentRevisionId: string | null;
}): PrePlanHandoffStatus {
  if (latestIntentRevisionId && previewIntentRevisionId !== latestIntentRevisionId) {
    return {
      kind: "stale",
      canApply: false,
      canGenerateReplacement: true,
      message: "路线预览已过期：行程信息已经更新，请重新生成预览后再保存。",
    };
  }
  return {
    kind: "current",
    canApply: true,
    canGenerateReplacement: false,
    message: "路线预览基于当前行程信息，可以确认并生成正式行程。",
  };
}

export function userFacingPrePlanHandoffError(code?: string): string | null {
  if (code === "stale_intent_revision") {
    return "路线预览已过期：行程信息已经更新，请重新生成预览后再保存。";
  }
  if (code === "stale_base_revision") {
    return "行程已在其他页面生成或更新，旧预览不能再保存。请返回查看最新行程。";
  }
  return null;
}
