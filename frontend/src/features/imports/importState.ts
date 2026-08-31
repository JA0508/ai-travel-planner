import type { ArtifactDerivation, ImportCapabilityPack, ImportCommitResult, ImportJob, ImportMention, SourceArtifact, URLFetchSnapshot } from "./importTypes";

export type ImportCapabilityState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; snapshot: ImportCapabilityPack }
  | { status: "error"; code: string; message: string };

type ImportWorkflowState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "processing"; jobId: string; stage: string }
  | {
      status: "reviewing";
      artifact: SourceArtifact;
      job: ImportJob;
      sourceText: string;
      mentions: ImportMention[];
      sourceFetch?: URLFetchSnapshot | null;
      derivation?: ArtifactDerivation | null;
      activeMentionId: string | null;
      reviewVersion: number;
    }
  | { status: "committing"; jobId: string; idempotencyKey: string }
  | { status: "committed"; result: ImportCommitResult }
  | { status: "conflict"; code: "stale_import_review"; jobId: string }
  | { status: "error"; code: string; message: string; recoverable: boolean };

export type ImportWorkspaceState = ImportWorkflowState & {
  capability: ImportCapabilityState;
};

export const initialImportWorkspaceState: ImportWorkspaceState = {
  status: "idle",
  capability: { status: "idle" },
};

export type ImportWorkspaceAction =
  | { type: "submit" }
  | {
      type: "review";
      artifact: SourceArtifact;
      job: ImportJob;
      mentions: ImportMention[];
      sourceText: string;
      sourceFetch?: URLFetchSnapshot | null;
      derivation?: ArtifactDerivation | null;
    }
  | { type: "select"; mentionId: string }
  | { type: "committing"; jobId: string; idempotencyKey: string }
  | { type: "committed"; result: ImportCommitResult }
  | { type: "conflict"; jobId: string }
  | { type: "error"; code: string; message: string; recoverable?: boolean }
  | { type: "capabilities_loading" }
  | { type: "capabilities_ready"; snapshot: ImportCapabilityPack }
  | { type: "capabilities_error"; code: string; message: string }
  | { type: "reset" };

export function importWorkspaceReducer(
  state: ImportWorkspaceState,
  action: ImportWorkspaceAction,
): ImportWorkspaceState {
  switch (action.type) {
    case "submit":
      return withCapabilities({ status: "submitting" }, state);
    case "review":
      return withCapabilities({
        status: "reviewing",
        artifact: action.artifact,
        job: action.job,
        sourceText: action.sourceText,
        mentions: action.mentions,
        sourceFetch: action.sourceFetch ?? null,
        derivation: action.derivation ?? null,
        activeMentionId: action.mentions[0]?.id ?? null,
        reviewVersion: action.job.review_version,
      }, state);
    case "select":
      if (state.status !== "reviewing") {
        return state;
      }
      return { ...state, activeMentionId: action.mentionId };
    case "committing":
      return withCapabilities({ status: "committing", jobId: action.jobId, idempotencyKey: action.idempotencyKey }, state);
    case "committed":
      return withCapabilities({ status: "committed", result: action.result }, state);
    case "conflict":
      return withCapabilities({ status: "conflict", code: "stale_import_review", jobId: action.jobId }, state);
    case "error":
      return withCapabilities({
        status: "error",
        code: action.code,
        message: action.message,
        recoverable: action.recoverable ?? false,
      }, state);
    case "capabilities_loading":
      return { ...state, capability: { status: "loading" } };
    case "capabilities_ready":
      return { ...state, capability: { status: "ready", snapshot: action.snapshot } };
    case "capabilities_error":
      return { ...state, capability: { status: "error", code: action.code, message: action.message } };
    case "reset":
      return withCapabilities({ status: "idle" }, state);
    default:
      return state;
  }
}

function withCapabilities(state: ImportWorkflowState, previous: ImportWorkspaceState): ImportWorkspaceState {
  return { ...state, capability: previous.capability };
}

export function importIdempotencyKey(prefix: string, tripId: string, stablePart: string): string {
  return `${asciiToken(prefix)}:${asciiToken(tripId)}:${stableDigest(stablePart)}`.slice(0, 180);
}

function asciiToken(value: string): string {
  return value.replace(/[^A-Za-z0-9._:-]/g, "_").slice(0, 80);
}

function stableDigest(value: string): string {
  let hash = 2166136261;
  for (const byte of new TextEncoder().encode(value)) {
    hash ^= byte;
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, "0");
}
