import type { ImportMention } from "./importTypes";

export function buildImportSummary(mentions: ImportMention[]) {
  return {
    placeCount: mentions.filter((mention) => mention.entity_type === "place").length,
    confirmedCount: mentions.filter((mention) => mention.review_state === "confirmed").length,
    ignoredCount: mentions.filter((mention) => mention.review_state === "ignored").length,
    unresolvedCount: mentions.filter((mention) => mention.review_state === "unresolved").length,
    preservedContextCount: mentions.filter((mention) =>
      mention.entity_type === "fixed_event" || mention.entity_type === "time_constraint" || mention.entity_type === "note",
    ).length,
  };
}

export function sourceSegments(sourceText: string, activeMention: ImportMention | null) {
  if (!activeMention) {
    return [{ text: sourceText, active: false }];
  }
  return [
    { text: sourceText.slice(0, activeMention.start_offset), active: false },
    { text: sourceText.slice(activeMention.start_offset, activeMention.end_offset), active: true },
    { text: sourceText.slice(activeMention.end_offset), active: false },
  ].filter((segment) => segment.text.length > 0);
}

export function selectedResolutionId(mention: ImportMention): string | null {
  if (mention.selected_resolution_candidate_id) {
    return mention.selected_resolution_candidate_id;
  }
  const usable = mention.resolution_candidates
    .filter((candidate) => candidate.data_state !== "missing" && candidate.data_state !== "provider_failed")
    .sort((left, right) => right.confidence - left.confidence || left.canonical_name.localeCompare(right.canonical_name));
  return usable[0]?.id ?? null;
}
