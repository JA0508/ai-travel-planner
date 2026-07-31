"use client";

export const TRIP_API_ENDPOINTS = {
  generateItinerary: buildApiUrl("/generate-itinerary"),
  replanItinerary: buildApiUrl("/replan-itinerary"),
  generateFromTripIntent: buildApiUrl("/generate-from-trip-intent"),
  applyCompletionTask: buildApiUrl("/apply-completion-task"),
  previewCompletionTaskCandidates: buildApiUrl("/preview-completion-task-candidates"),
  refreshItinerarySurfaces: buildApiUrl("/refresh-itinerary-surfaces"),
  previewRouteSegments: buildApiUrl("/preview-route-segments"),
  previewPoiDetail: buildApiUrl("/preview-poi-detail"),
  planFromText: buildApiUrl("/plan-trip-from-text"),
  planTrip: buildApiUrl("/trips/plan"),
  createDraftTrip: buildApiUrl("/trips/drafts"),
  getDraftTrip: (tripId: string) => buildApiUrl(`/trips/${encodeURIComponent(tripId)}/draft`),
  compilePrePlanIntent: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/preplan-intent/compile`),
  editPrePlanIntent: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/preplan-intent/edits`),
  getLatestPrePlanIntent: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/preplan-intent`),
  resolvePrePlanIntentClarification: (tripId: string, clarificationId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/preplan-intent/clarifications/${encodeURIComponent(clarificationId)}/resolve`),
  previewPrePlanHandoff: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/preplan-handoff/preview`),
  applyPrePlanHandoff: (tripId: string, runId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/preplan-handoff/runs/${encodeURIComponent(runId)}/apply`),
  getTrip: (tripId: string) => buildApiUrl(`/trips/${encodeURIComponent(tripId)}`),
  listTripRevisions: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/revisions`),
  restoreTripRevision: (tripId: string, revisionId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/revisions/${encodeURIComponent(revisionId)}/restore`,
    ),
  applyPersistedCompletionTask: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/completion-task`),
  previewPersistedReplan: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/replan/preview`),
  applyPersistedReplanProposal: (tripId: string, proposalId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/replan/proposals/${encodeURIComponent(proposalId)}/apply`,
    ),
  previewPersistedMutation: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/mutations/preview`),
  previewLocalRelaxDayRepair: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/local-repairs/relax-day/preview`),
  applyPersistedMutationProposal: (tripId: string, proposalId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/mutation-proposals/${encodeURIComponent(proposalId)}/apply`,
    ),
  previewPlannerHandoff: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/planner-handoff/preview`),
  applyPlannerHandoffProposal: (tripId: string, proposalId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/planner-handoff/proposals/${encodeURIComponent(proposalId)}/apply`,
    ),
  listTripCandidates: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/candidates`),
  registerTripCandidate: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/candidates`),
  recordTripCandidateDecision: (tripId: string, candidateId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/candidates/${encodeURIComponent(candidateId)}/decisions`,
    ),
  compileTripIntentEnvelope: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/intent-envelope/compile`),
  listTripIntentEnvelopes: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/intent-envelope`),
  getTripIntentEnvelope: (tripId: string, intentRevisionId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/intent-envelope/${encodeURIComponent(intentRevisionId)}`,
    ),
  editTripIntentEnvelope: (tripId: string, intentRevisionId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/intent-envelope/${encodeURIComponent(intentRevisionId)}/edit`,
    ),
  restoreTripIntentEnvelope: (tripId: string, intentRevisionId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/intent-envelope/${encodeURIComponent(intentRevisionId)}/restore`,
    ),
  answerTripIntentClarification: (tripId: string, intentRevisionId: string, questionId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/intent-envelope/${encodeURIComponent(intentRevisionId)}/clarifications/${encodeURIComponent(questionId)}/answer`,
    ),
  createTextImport: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/imports/text`),
  createUrlImport: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/imports/url`),
  createBinaryImport: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/imports/artifacts`),
  getTextImport: (tripId: string, importJobId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}`,
    ),
  getBinaryInspection: (tripId: string, importJobId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}/inspection`,
    ),
  getSanitizedImage: (tripId: string, importJobId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}/sanitized-image`,
    ),
  extractDocumentImport: (tripId: string, importJobId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}/extract-document`,
    ),
  getDocumentExtractionEvidence: (tripId: string, importJobId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}/document-extraction`,
    ),
  getDocumentPagePreview: (tripId: string, importJobId: string, pageNumber: number) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}/document-extraction/pages/${encodeURIComponent(String(pageNumber))}/preview`,
    ),
  retryDocumentPageExtraction: (tripId: string, importJobId: string, pageNumber: number) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}/document-extraction/pages/${encodeURIComponent(String(pageNumber))}/retry`,
    ),
  getTextImportArtifact: (tripId: string, importJobId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}/artifact`,
    ),
  recordTextImportDecision: (tripId: string, importJobId: string, mentionId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}/mentions/${encodeURIComponent(mentionId)}/decisions`,
    ),
  commitTextImport: (tripId: string, importJobId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}/commit`,
    ),
  undoPersistedRevision: (tripId: string, revisionId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/revisions/${encodeURIComponent(revisionId)}/undo`,
    ),
  parseTripIntent: buildApiUrl("/parse-trip-intent"),
  compileTripCompilerIntent: buildApiUrl("/trip-compiler/intents/compile"),
  planTripCompilerIntent: buildApiUrl("/trip-compiler/trips"),
  parsePlanningState: buildApiUrl("/parse-planning-state"),
  previewAvailability: buildApiUrl("/preview-availability"),
} as const;

export const AMAP_BROWSER_CONFIG = {
  webKey: normalizeOptionalEnv(process.env.NEXT_PUBLIC_AMAP_WEB_KEY),
  securityJsCode: normalizeOptionalEnv(process.env.NEXT_PUBLIC_AMAP_SECURITY_JS_CODE),
} as const;

export function getTripApiBaseUrl(): string {
  return normalizeApiBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL);
}

function buildApiUrl(path: `/${string}`): string {
  return `${getTripApiBaseUrl()}${path}`;
}

function normalizeApiBaseUrl(value: string | undefined): string {
  // Keep browser requests same-origin by default. Next proxies /api to the
  // private backend target, avoiding browser-specific cross-port failures.
  return (value || "/api").replace(/\/+$/, "");
}

function normalizeOptionalEnv(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}
