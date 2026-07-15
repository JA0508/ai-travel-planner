export const PERSISTED_TRIP_REF_KEY = "travel-planner-trip-ref-v1";
export const LEGACY_FULL_SESSION_KEY = "travel-planner-saved-session-v1";

export type TripMetadata = {
  id: string;
  current_revision_id: string;
  revision_count: number;
  lifecycle_status: string;
  created_at: string;
  updated_at: string;
};

export type TripRevisionMetadata = {
  id: string;
  trip_id: string;
  revision_number: number;
  parent_revision_id: string | null;
  base_revision_id: string | null;
  source_type: string;
  snapshot_schema_version: string;
  content_digest: string;
  parent_lineage_digest: string | null;
  lineage_digest: string;
  planner_run_id: string | null;
  planner_version: string | null;
  trace_schema_version: string | null;
  trace_digest: string | null;
  restored_from_revision_id: string | null;
  created_at: string;
};

export type PersistedTripRef = {
  schemaVersion: 1;
  tripId: string;
  currentRevisionId: string;
};

export type TripPersistenceState =
  | { status: "none" }
  | { status: "creating" }
  | { status: "restoring"; tripId: string }
  | { status: "saved"; tripId: string; currentRevisionId: string; revisionNumber: number }
  | { status: "dirty"; tripId: string; currentRevisionId: string; revisionNumber: number; reason: string }
  | {
      status: "conflict";
      tripId: string;
      providedBaseRevisionId: string;
      currentRevisionId: string;
      message: string;
    }
  | { status: "error"; message: string; tripId?: string; recoverable?: boolean };

export function buildPersistedTripRef(
  trip: TripMetadata,
  revision: TripRevisionMetadata,
): PersistedTripRef {
  return {
    schemaVersion: 1,
    tripId: trip.id,
    currentRevisionId: revision.id,
  };
}

export function parsePersistedTripRef(raw: string | null): PersistedTripRef | null {
  if (!raw) {
    return null;
  }
  try {
    const value = JSON.parse(raw) as Partial<PersistedTripRef>;
    if (
      value.schemaVersion !== 1 ||
      typeof value.tripId !== "string" ||
      typeof value.currentRevisionId !== "string" ||
      !value.tripId ||
      !value.currentRevisionId
    ) {
      return null;
    }
    return {
      schemaVersion: 1,
      tripId: value.tripId,
      currentRevisionId: value.currentRevisionId,
    };
  } catch {
    return null;
  }
}

export function serializePersistedTripRef(ref: PersistedTripRef): string {
  return JSON.stringify(ref);
}

export function describeTripPersistence(state: TripPersistenceState): string {
  switch (state.status) {
    case "creating":
      return "Saving…";
    case "restoring":
      return "Restoring saved trip…";
    case "saved":
      return `Saved · Revision ${state.revisionNumber}`;
    case "dirty":
      return `Unsaved changes · Revision ${state.revisionNumber}`;
    case "conflict":
      return "Conflict detected";
    case "error":
      return "Persistence error";
    case "none":
    default:
      return "Not saved";
  }
}

export function markSavedFromRevision(
  revision: TripRevisionMetadata,
): TripPersistenceState {
  return {
    status: "saved",
    tripId: revision.trip_id,
    currentRevisionId: revision.id,
    revisionNumber: revision.revision_number,
  };
}

export function markDirty(
  state: TripPersistenceState,
  reason: string,
): TripPersistenceState {
  if (state.status !== "saved" && state.status !== "dirty") {
    return state;
  }
  return {
    status: "dirty",
    tripId: state.tripId,
    currentRevisionId: state.currentRevisionId,
    revisionNumber: state.revisionNumber,
    reason,
  };
}

export function buildReplanIdempotencyKey(baseRevisionId: string, followUpText: string): string {
  const normalized = followUpText.trim().replace(/\s+/g, " ");
  let hash = 2166136261;
  for (let index = 0; index < normalized.length; index += 1) {
    hash ^= normalized.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `replan:${baseRevisionId}:${(hash >>> 0).toString(16)}`;
}
