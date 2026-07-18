"use client";

import { type CSSProperties } from "react";
import type { BinaryImportState } from "./binaryImportState";
import type { BinaryInspectionView, SafeFinding } from "./importTypes";

export function BinaryInspectionResult({ state }: { state: BinaryImportState }) {
  if (state.status === "uploading") {
    return <p style={noticeStyle}>Receiving artifact and preparing quarantine...</p>;
  }
  if (state.status === "quarantined" || state.status === "inspecting") {
    return <p style={noticeStyle}>Inspection is running in an isolated worker...</p>;
  }
  if (state.status === "artifact_ready") {
    return (
      <div style={resultStyle} data-binary-inspection-result>
        <ResultHeader result={state.result} />
        {state.result.detected_kind === "image" ? (
          <ImageInspectionResult result={state.result} previewUrl={state.previewUrl} />
        ) : (
          <PdfInspectionResult result={state.result} />
        )}
        <InspectionFindingList findings={state.result.findings} />
      </div>
    );
  }
  if (state.status === "needs_password") {
    return (
      <div style={resultStyle} data-binary-inspection-result>
        <ResultHeader result={state.result} />
        <p style={noticeStyle}>Encrypted PDF. Password handling is not supported.</p>
        <InspectionFindingList findings={state.result.findings} />
      </div>
    );
  }
  if (state.status === "rejected") {
    return (
      <div style={resultStyle} data-binary-inspection-result>
        <p style={errorStyle}>{state.code}</p>
        <InspectionFindingList findings={state.findings} />
      </div>
    );
  }
  if (state.status === "error") {
    return <p style={errorStyle}>{state.code}: {state.message}</p>;
  }
  return null;
}

function ResultHeader({ result }: { result: BinaryInspectionView }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
      <strong style={{ color: "var(--ec-ink)", fontSize: 13 }}>{result.classification}</strong>
      <span style={hintStyle}>{result.detected_mime_type} · inspector {result.inspector_version}</span>
    </div>
  );
}

function ImageInspectionResult({ result, previewUrl }: { result: BinaryInspectionView; previewUrl?: string | null }) {
  return (
    <div style={detailGridStyle}>
      {previewUrl ? (
        <img src={previewUrl} alt="Metadata-stripped preview" style={previewStyle} />
      ) : (
        <div style={previewPlaceholderStyle}>Metadata-stripped preview</div>
      )}
      <div style={factsStyle}>
        <Fact label="Format" value={String(result.metadata.detected_format ?? result.detected_mime_type)} />
        <Fact label="Dimensions" value={`${result.metadata.width ?? "unknown"} x ${result.metadata.height ?? "unknown"}`} />
        <Fact label="Pixels" value={String(result.metadata.pixel_count ?? "unknown")} />
        <Fact label="Frames" value={String(result.metadata.frame_count ?? "unknown")} />
        <Fact label="Metadata" value={result.metadata.metadata_present ? "present, stripped" : "not detected"} />
        <Fact label="GPS metadata" value={result.metadata.gps_metadata_present ? "present, removed" : "not detected"} />
        <Fact label="State" value="Ready for future visual text extraction" />
      </div>
    </div>
  );
}

function PdfInspectionResult({ result }: { result: BinaryInspectionView }) {
  return (
    <div style={factsStyle} data-pdf-inspection-result>
      <Fact label="Format" value="PDF" />
      <Fact label="Pages" value={String(result.metadata.page_count ?? "unknown")} />
      <Fact label="Encrypted" value={result.metadata.encrypted ? "yes" : "no"} />
      <Fact label="Forms" value={result.metadata.acroform_present ? "present" : "not detected"} />
      <Fact label="Active content" value={result.metadata.active_content_present ? "detected" : "not detected"} />
      <Fact label="Embedded files" value={result.metadata.embedded_files_present ? "detected" : "not detected"} />
      <Fact label="State" value="Ready for future controlled text extraction" />
    </div>
  );
}

function InspectionFindingList({ findings }: { findings: SafeFinding[] }) {
  if (findings.length === 0) {
    return <p style={noticeStyle}>No blocking findings were detected by structural inspection.</p>;
  }
  return (
    <div style={{ display: "grid", gap: 6 }}>
      {findings.map((finding) => (
        <div key={finding.id} style={findingStyle}>
          <strong>{finding.code}</strong>
          <span>{finding.severity} · {finding.category}</span>
        </div>
      ))}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div style={factRowStyle}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

const resultStyle = { display: "grid", gap: 10, padding: 12, borderRadius: 12, border: "1px solid rgba(21,21,21,0.08)", background: "rgba(255,255,255,0.82)" } satisfies CSSProperties;
const detailGridStyle = { display: "grid", gridTemplateColumns: "minmax(120px, 180px) minmax(0, 1fr)", gap: 12, alignItems: "start" } satisfies CSSProperties;
const previewStyle = { width: "100%", aspectRatio: "4 / 3", objectFit: "contain", borderRadius: 10, border: "1px solid rgba(21,21,21,0.08)", background: "white" } satisfies CSSProperties;
const previewPlaceholderStyle = { ...previewStyle, display: "grid", placeItems: "center", color: "var(--ec-slate)", fontSize: 12 } satisfies CSSProperties;
const factsStyle = { display: "grid", gap: 6 } satisfies CSSProperties;
const factRowStyle = { display: "flex", justifyContent: "space-between", gap: 10, fontSize: 12, color: "var(--ec-slate)" } satisfies CSSProperties;
const hintStyle = { fontSize: 12, color: "var(--ec-slate)" } satisfies CSSProperties;
const noticeStyle = { margin: 0, fontSize: 12, color: "#5f6f54", lineHeight: 1.5 } satisfies CSSProperties;
const errorStyle = { margin: 0, fontSize: 12, color: "#9d302a", lineHeight: 1.5 } satisfies CSSProperties;
const findingStyle = { display: "flex", justifyContent: "space-between", gap: 10, padding: "7px 9px", borderRadius: 8, background: "rgba(21,21,21,0.04)", color: "var(--ec-slate)", fontSize: 12 } satisfies CSSProperties;
