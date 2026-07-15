import type { ImportCommitResult, ImportJob, ImportMention, SourceArtifact } from "./importTypes";

export type ImportWorkspaceState =
  | { status: "idle" }
  | { status: "submitting" }
  | { status: "processing"; jobId: string; stage: string }
  | {
      status: "reviewing";
      artifact: SourceArtifact;
      job: ImportJob;
      sourceText: string;
      mentions: ImportMention[];
      activeMentionId: string | null;
      reviewVersion: number;
    }
  | { status: "committing"; jobId: string; idempotencyKey: string }
  | { status: "committed"; result: ImportCommitResult }
  | { status: "conflict"; code: "stale_import_review"; jobId: string }
  | { status: "error"; code: string; message: string; recoverable: boolean };

export type ImportWorkspaceAction =
  | { type: "submit" }
  | { type: "review"; artifact: SourceArtifact; job: ImportJob; mentions: ImportMention[]; sourceText: string }
  | { type: "select"; mentionId: string }
  | { type: "committing"; jobId: string; idempotencyKey: string }
  | { type: "committed"; result: ImportCommitResult }
  | { type: "conflict"; jobId: string }
  | { type: "error"; code: string; message: string; recoverable?: boolean }
  | { type: "reset" };

export function importWorkspaceReducer(
  state: ImportWorkspaceState,
  action: ImportWorkspaceAction,
): ImportWorkspaceState {
  switch (action.type) {
    case "submit":
      return { status: "submitting" };
    case "review":
      return {
        status: "reviewing",
        artifact: action.artifact,
        job: action.job,
        sourceText: action.sourceText,
        mentions: action.mentions,
        activeMentionId: action.mentions[0]?.id ?? null,
        reviewVersion: action.job.review_version,
      };
    case "select":
      if (state.status !== "reviewing") {
        return state;
      }
      return { ...state, activeMentionId: action.mentionId };
    case "committing":
      return { status: "committing", jobId: action.jobId, idempotencyKey: action.idempotencyKey };
    case "committed":
      return { status: "committed", result: action.result };
    case "conflict":
      return { status: "conflict", code: "stale_import_review", jobId: action.jobId };
    case "error":
      return {
        status: "error",
        code: action.code,
        message: action.message,
        recoverable: action.recoverable ?? false,
      };
    case "reset":
      return { status: "idle" };
    default:
      return state;
  }
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
