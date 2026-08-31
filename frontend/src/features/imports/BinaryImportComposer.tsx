"use client";

import { type CSSProperties, type DragEvent, type RefObject } from "react";
import type { BinaryImportState } from "./binaryImportState";
import { binaryImportKindForFile } from "./binaryImportState";

type BinaryImportComposerProps = {
  state: BinaryImportState;
  inputRef: RefObject<HTMLInputElement | null>;
  disabled: boolean;
  disabledKinds?: readonly ("image" | "pdf")[];
  disabledMessageForKind?: (kind: "image" | "pdf") => string;
  onFileSelected: (file: File, declaredKind: "image" | "pdf") => void;
  onUpload: () => void;
  onReset: () => void;
  onError: (code: string, message: string) => void;
};

export function BinaryImportComposer({
  state,
  inputRef,
  disabled,
  disabledKinds = [],
  disabledMessageForKind,
  onFileSelected,
  onUpload,
  onReset,
  onError,
}: BinaryImportComposerProps) {
  function handleFile(file: File | undefined) {
    if (!file) {
      return;
    }
    const declaredKind = binaryImportKindForFile(file);
    if (!declaredKind) {
      onError("import_binary_type_unsupported", "Only PDF, JPEG, PNG, and static WebP artifacts are supported.");
      return;
    }
    if (disabled || disabledKinds.includes(declaredKind)) {
      onError("import_form_unavailable", disabledMessageForKind?.(declaredKind) ?? "This import method is unavailable.");
      return;
    }
    onFileSelected(file, declaredKind);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    handleFile(event.dataTransfer.files[0]);
  }

  return (
    <div style={{ display: "grid", gap: 10 }}>
      <input
        ref={inputRef}
        type="file"
        accept={acceptedMimeTypes(disabledKinds)}
        disabled={disabled}
        onChange={(event) => handleFile(event.target.files?.[0])}
        style={{ display: "none" }}
      />
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        onDrop={handleDrop}
        onDragOver={(event) => event.preventDefault()}
        onClick={() => {
          if (!disabled) {
            inputRef.current?.click();
          }
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            if (!disabled) {
              inputRef.current?.click();
            }
          }
        }}
        style={{ ...dropZoneStyle, cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.58 : 1 }}
        aria-label="Select image or PDF artifact"
        aria-disabled={disabled}
      >
        <strong style={{ color: "var(--ec-ink)", fontSize: 13 }}>Drop or select an image / PDF artifact</strong>
        <span style={hintStyle}>PDF, JPEG, PNG, static WebP · private quarantine · no OCR in this step</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <span style={hintStyle}>
          {state.status === "selected"
            ? `${state.displayName} · ${state.byteSize} bytes · ${state.declaredKind}`
            : "Original binary is inspected server-side and never rendered inline."}
        </span>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" onClick={onReset} style={secondaryButtonStyle}>
            Clear
          </button>
          <button
            type="button"
            onClick={onUpload}
            disabled={disabled || state.status !== "selected"}
            style={primaryButtonStyle}
          >
            {state.status === "uploading" ? "Uploading..." : "Upload for inspection"}
          </button>
        </div>
      </div>
    </div>
  );
}

function acceptedMimeTypes(disabledKinds: readonly ("image" | "pdf")[]): string {
  const accepted: string[] = [];
  if (!disabledKinds.includes("pdf")) {
    accepted.push("application/pdf");
  }
  if (!disabledKinds.includes("image")) {
    accepted.push("image/jpeg", "image/png", "image/webp");
  }
  return accepted.join(",");
}

const hintStyle = { fontSize: 12, color: "var(--ec-slate)" } satisfies CSSProperties;
const dropZoneStyle = { display: "grid", gap: 4, padding: 14, borderRadius: 12, border: "1px dashed rgba(21,21,21,0.24)", background: "rgba(255,255,255,0.78)", cursor: "pointer" } satisfies CSSProperties;
const primaryButtonStyle = { border: 0, borderRadius: 999, padding: "9px 13px", background: "#151515", color: "white", fontWeight: 900, cursor: "pointer" } satisfies CSSProperties;
const secondaryButtonStyle = { border: "1px solid rgba(21,21,21,0.14)", borderRadius: 999, padding: "8px 12px", background: "rgba(255,255,255,0.8)", color: "var(--ec-ink)", fontWeight: 800, cursor: "pointer" } satisfies CSSProperties;
