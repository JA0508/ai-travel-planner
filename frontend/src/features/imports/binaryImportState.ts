import type { BinaryInspectionView, ImportJob, SafeFinding, SourceArtifact } from "./importTypes";

export type BinaryImportState =
  | { status: "idle" }
  | {
      status: "selected";
      displayName: string;
      byteSize: number;
      declaredKind: "image" | "pdf";
      file: File;
    }
  | { status: "uploading" }
  | { status: "quarantined"; jobId: string }
  | { status: "inspecting"; jobId: string }
  | {
      status: "artifact_ready";
      artifact: SourceArtifact;
      job: ImportJob;
      result: BinaryInspectionView;
      previewUrl?: string | null;
    }
  | {
      status: "needs_password";
      artifact: SourceArtifact;
      job: ImportJob;
      result: BinaryInspectionView;
    }
  | { status: "rejected"; code: string; findings: SafeFinding[]; result?: BinaryInspectionView }
  | { status: "error"; code: string; message: string; recoverable: boolean };

export type BinaryImportAction =
  | { type: "select"; file: File; declaredKind: "image" | "pdf" }
  | { type: "uploading" }
  | { type: "uploaded"; artifact: SourceArtifact; job: ImportJob; inspection: BinaryInspectionView }
  | { type: "preview"; previewUrl: string }
  | { type: "error"; code: string; message: string; recoverable?: boolean }
  | { type: "reset" };

export function binaryImportReducer(
  state: BinaryImportState,
  action: BinaryImportAction,
): BinaryImportState {
  switch (action.type) {
    case "select":
      return {
        status: "selected",
        displayName: action.declaredKind === "image" ? "Selected image artifact" : "Selected PDF artifact",
        byteSize: action.file.size,
        declaredKind: action.declaredKind,
        file: action.file,
      };
    case "uploading":
      return { status: "uploading" };
    case "uploaded":
      if (action.job.status === "artifact_ready") {
        return {
          status: "artifact_ready",
          artifact: action.artifact,
          job: action.job,
          result: action.inspection,
          previewUrl: null,
        };
      }
      if (action.job.status === "needs_password") {
        return {
          status: "needs_password",
          artifact: action.artifact,
          job: action.job,
          result: action.inspection,
        };
      }
      if (action.job.status === "rejected") {
        return {
          status: "rejected",
          code: action.inspection.error_code ?? "import_binary_rejected",
          findings: action.inspection.findings,
          result: action.inspection,
        };
      }
      if (action.job.status === "quarantined") {
        return { status: "quarantined", jobId: action.job.id };
      }
      if (action.job.status === "inspecting") {
        return { status: "inspecting", jobId: action.job.id };
      }
      return {
        status: "error",
        code: action.inspection.error_code ?? "import_inspection_worker_failed",
        message: "Artifact inspection did not produce a ready result.",
        recoverable: true,
      };
    case "preview":
      if (state.status !== "artifact_ready") {
        return state;
      }
      return { ...state, previewUrl: action.previewUrl };
    case "error":
      return {
        status: "error",
        code: action.code,
        message: action.message,
        recoverable: action.recoverable ?? true,
      };
    case "reset":
      return { status: "idle" };
    default:
      return state;
  }
}

export function binaryImportKindForFile(file: File): "image" | "pdf" | null {
  const type = file.type.toLowerCase();
  if (type === "application/pdf") {
    return "pdf";
  }
  if (["image/jpeg", "image/png", "image/webp"].includes(type)) {
    return "image";
  }
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension === "pdf") {
    return "pdf";
  }
  if (extension && ["jpg", "jpeg", "png", "webp"].includes(extension)) {
    return "image";
  }
  return null;
}

export function binaryImportIdempotencyKey(tripId: string, file: File, declaredKind: "image" | "pdf"): string {
  const nonce = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `binary-import:${asciiToken(tripId)}:${declaredKind}:${file.size}:${asciiToken(nonce)}`.slice(0, 180);
}

export function binaryImportStorageValue(tripId: string, jobId: string, declaredKind: "image" | "pdf"): string {
  return JSON.stringify({ tripId: asciiToken(tripId), jobId: asciiToken(jobId), declaredKind });
}

export function parseBinaryImportStorageValue(raw: string | null): { tripId: string; jobId: string; declaredKind: "image" | "pdf" } | null {
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as { tripId?: unknown; jobId?: unknown; declaredKind?: unknown };
    if (typeof parsed.tripId !== "string" || typeof parsed.jobId !== "string") {
      return null;
    }
    if (parsed.declaredKind !== "image" && parsed.declaredKind !== "pdf") {
      return null;
    }
    return { tripId: parsed.tripId, jobId: parsed.jobId, declaredKind: parsed.declaredKind };
  } catch {
    return null;
  }
}

function asciiToken(value: string): string {
  return value.replace(/[^A-Za-z0-9._:-]/g, "_").slice(0, 120);
}
