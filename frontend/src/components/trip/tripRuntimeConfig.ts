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
  applyPersistedMutationProposal: (tripId: string, proposalId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/mutation-proposals/${encodeURIComponent(proposalId)}/apply`,
    ),
  listTripCandidates: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/candidates`),
  registerTripCandidate: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/candidates`),
  recordTripCandidateDecision: (tripId: string, candidateId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/candidates/${encodeURIComponent(candidateId)}/decisions`,
    ),
  createTextImport: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/imports/text`),
  createUrlImport: (tripId: string) =>
    buildApiUrl(`/trips/${encodeURIComponent(tripId)}/imports/url`),
  getTextImport: (tripId: string, importJobId: string) =>
    buildApiUrl(
      `/trips/${encodeURIComponent(tripId)}/imports/${encodeURIComponent(importJobId)}`,
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
  return (value || "http://localhost:8000").replace(/\/+$/, "");
}

function normalizeOptionalEnv(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}
