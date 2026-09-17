export type WorkspaceStateOwner =
  | "durable"
  | "server"
  | "draft"
  | "selection"
  | "ui"
  | "async";

export const routeWorkspacePageStateOwnership = {
  activeSwapTarget: "selection",
  advancedModeOpen: "ui",
  applyingCompletionTaskId: "async",
  arrivalAnchor: "draft",
  availabilityPreview: "server",
  availabilityPreviewError: "async",
  availabilityPreviewSignature: "server",
  availabilityWindowsText: "draft",
  candidateWorkspace: "server",
  committedSwaps: "durable",
  completionCandidateHistory: "durable",
  completionPickerOpen: "ui",
  completionTaskCandidatePreviews: "server",
  completionTaskEdits: "durable",
  completionTaskStatus: "async",
  completionTasksExpanded: "ui",
  copyStatus: "async",
  day: "selection",
  departureAnchor: "draft",
  dismissedFollowUpRawText: "ui",
  error: "async",
  fixedEventsText: "draft",
  followUpText: "draft",
  generationContext: "durable",
  generationProgress: "async",
  hasSavedSession: "durable",
  highlightedResultTargetId: "ui",
  hotel: "draft",
  index: "selection",
  intentResult: "server",
  latestDirectOptimizationComparison: "server",
  latestFollowUpBaseIntent: "durable",
  loading: "async",
  pacingProfile: "durable",
  parseError: "async",
  parsedIntent: "server",
  parsing: "async",
  persistedReplanProposal: "async",
  planningState: "server",
  preferencesText: "draft",
  preferenceSignals: "durable",
  previewingAvailability: "async",
  previewingCompletionTaskId: "async",
  quickPreviewMode: "ui",
  recentCompletionTaskItemKey: "selection",
  replanning: "async",
  restaurants: "draft",
  returnToTripTextNotice: "ui",
  restoreTripTextFocus: "ui",
  result: "server",
  revisionRestoreConfirmation: "selection",
  revisionRestoreBlockedNotice: "ui",
  revisionRestoreReceipt: "ui",
  revisionRoutePreview: "server",
  savedTripPromptOpen: "ui",
  scenicSpots: "draft",
  selectedCompletionOptionKeys: "selection",
  sessionHydrated: "async",
  shareCardImageUrl: "server",
  shareCardStatus: "async",
  shareFeedbackNote: "draft",
  shareFeedbackRating: "selection",
  shareFeedbackSaved: "async",
  travelMode: "draft",
  travelModeModalOpen: "ui",
  tripDays: "draft",
  tripPersistence: "durable",
  tripText: "draft",
  userIntentState: "durable",
  revisionHistory: "server",
  versionHistoryOpen: "ui",
} as const satisfies Record<string, WorkspaceStateOwner>;

export const routeWorkspaceFeatureStateOwnership = {
  activeRouteSheet: "ui",
  routeEditMode: "ui",
} as const satisfies Record<string, WorkspaceStateOwner>;

export const routeWorkspaceRuntimeStateOwnership = {
  draggingStop: "selection",
  editableDays: "draft",
  isPanelLayout: "ui",
  pendingStopBlock: "draft",
  pendingStopName: "draft",
  pendingStopType: "draft",
  poiDetail: "server",
  poiDetailState: "async",
  redoStack: "durable",
  rightPanelMode: "selection",
  routeMode: "ui",
  routePreviewMap: "server",
  routePreviewState: "async",
  selectedDay: "selection",
  sheetSnap: "ui",
  showOverview: "ui",
  showUnplanned: "ui",
  undoStack: "durable",
  unplannedStops: "draft",
  visibleMapDays: "selection",
} as const satisfies Record<string, WorkspaceStateOwner>;

export const routeWorkspaceDerivedStateOwnership = {
  activeStop: "selection",
  activeStopId: "selection",
  selectedDaySegments: "server",
  selectedDayView: "selection",
  visibleDayNumbers: "selection",
} as const satisfies Record<string, WorkspaceStateOwner>;

export type RouteWorkspacePageStateName = keyof typeof routeWorkspacePageStateOwnership;
export type RouteWorkspaceFeatureStateName = keyof typeof routeWorkspaceFeatureStateOwnership;
export type RouteWorkspaceRuntimeStateName = keyof typeof routeWorkspaceRuntimeStateOwnership;
export type RouteWorkspaceDerivedStateName = keyof typeof routeWorkspaceDerivedStateOwnership;

export function getWorkspaceStateOwner(stateName: string): WorkspaceStateOwner | null {
  return (
    routeWorkspacePageStateOwnership[stateName as RouteWorkspacePageStateName] ??
    routeWorkspaceFeatureStateOwnership[stateName as RouteWorkspaceFeatureStateName] ??
    routeWorkspaceRuntimeStateOwnership[stateName as RouteWorkspaceRuntimeStateName] ??
    routeWorkspaceDerivedStateOwnership[stateName as RouteWorkspaceDerivedStateName] ??
    null
  );
}

export function groupWorkspaceStateOwnership(
  ownership: Record<string, WorkspaceStateOwner> = routeWorkspacePageStateOwnership,
): Record<WorkspaceStateOwner, string[]> {
  const grouped: Record<WorkspaceStateOwner, string[]> = {
    async: [],
    draft: [],
    durable: [],
    selection: [],
    server: [],
    ui: [],
  };

  for (const [stateName, owner] of Object.entries(ownership)) {
    grouped[owner].push(stateName);
  }

  for (const names of Object.values(grouped)) {
    names.sort();
  }

  return grouped;
}
