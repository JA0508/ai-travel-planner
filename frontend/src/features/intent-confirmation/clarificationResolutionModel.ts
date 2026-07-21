import type { IntentClarification } from "./intentTypes";

export type ClarificationResolutionAction =
  | "answer_inline"
  | "edit_contract"
  | "reimport_evidence";

export function getClarificationResolutionAction(
  clarification: Pick<IntentClarification, "resolution_kind">,
): ClarificationResolutionAction {
  switch (clarification.resolution_kind) {
    case "inline_answer":
      return "answer_inline";
    case "edit_contract":
      return "edit_contract";
    case "reimport_evidence":
      return "reimport_evidence";
  }
}

export function canSubmitInlineClarification(
  clarification: Pick<IntentClarification, "resolution_kind">,
  answer: string,
): boolean {
  return getClarificationResolutionAction(clarification) === "answer_inline" && answer.trim().length > 0;
}
