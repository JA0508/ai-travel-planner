export type RouteWorkspaceMutationKind =
  | "route_edit_commit"
  | "local_replan_mutation"
  | "backend_replan_apply"
  | "backend_replan_undo"
  | "completion_task_apply"
  | "completion_task_undo";

export type RouteWorkspaceRefreshPolicy = {
  mutationKind: RouteWorkspaceMutationKind;
  itineraryUpdate: "local_patch" | "backend_authoritative";
  refreshEndpoint:
    | "refreshItinerarySurfaces"
    | "applyCompletionTask"
    | "applyPersistedReplan"
    | "undoPersistedRevision"
    | null;
  refreshTiming: "none" | "after_local_patch" | "during_backend_mutation";
  failureBehavior: "preserve_local_itinerary" | "preserve_previous_itinerary" | "use_backend_error";
  refreshedSurfaces: Array<"itinerary" | "trip_intent" | "completion_intelligence" | "completion_candidate_history">;
};

export const routeWorkspaceRefreshPolicies: Record<
  RouteWorkspaceMutationKind,
  RouteWorkspaceRefreshPolicy
> = {
  route_edit_commit: {
    mutationKind: "route_edit_commit",
    itineraryUpdate: "local_patch",
    refreshEndpoint: null,
    refreshTiming: "none",
    failureBehavior: "preserve_local_itinerary",
    refreshedSurfaces: ["itinerary", "trip_intent"],
  },
  local_replan_mutation: {
    mutationKind: "local_replan_mutation",
    itineraryUpdate: "local_patch",
    refreshEndpoint: "refreshItinerarySurfaces",
    refreshTiming: "after_local_patch",
    failureBehavior: "preserve_local_itinerary",
    refreshedSurfaces: [
      "itinerary",
      "trip_intent",
      "completion_intelligence",
      "completion_candidate_history",
    ],
  },
  backend_replan_apply: {
    mutationKind: "backend_replan_apply",
    itineraryUpdate: "backend_authoritative",
    refreshEndpoint: "applyPersistedReplan",
    refreshTiming: "during_backend_mutation",
    failureBehavior: "use_backend_error",
    refreshedSurfaces: [
      "itinerary",
      "trip_intent",
      "completion_intelligence",
      "completion_candidate_history",
    ],
  },
  backend_replan_undo: {
    mutationKind: "backend_replan_undo",
    itineraryUpdate: "backend_authoritative",
    refreshEndpoint: "undoPersistedRevision",
    refreshTiming: "during_backend_mutation",
    failureBehavior: "use_backend_error",
    refreshedSurfaces: ["itinerary", "trip_intent", "completion_candidate_history"],
  },
  completion_task_apply: {
    mutationKind: "completion_task_apply",
    itineraryUpdate: "backend_authoritative",
    refreshEndpoint: "applyCompletionTask",
    refreshTiming: "during_backend_mutation",
    failureBehavior: "use_backend_error",
    refreshedSurfaces: ["itinerary", "trip_intent", "completion_candidate_history"],
  },
  completion_task_undo: {
    mutationKind: "completion_task_undo",
    itineraryUpdate: "local_patch",
    refreshEndpoint: "refreshItinerarySurfaces",
    refreshTiming: "after_local_patch",
    failureBehavior: "preserve_local_itinerary",
    refreshedSurfaces: ["itinerary", "completion_intelligence", "completion_candidate_history"],
  },
};

export function getRouteWorkspaceRefreshPolicy(
  mutationKind: RouteWorkspaceMutationKind,
): RouteWorkspaceRefreshPolicy {
  return routeWorkspaceRefreshPolicies[mutationKind];
}
