"use client";

import type { CSSProperties } from "react";
import {
  SwapCandidatePanel,
  type SwapCandidateViewModel,
} from "@/components/trip/SwapCandidatePanel";

export type OwnershipBadgeViewModel = {
  label: string;
  tone: "olive" | "sand" | "sea" | "neutral" | "fresh";
};

export type ItineraryStopCardViewModel = {
  key: string;
  name: string;
  itemTypeLabel: string;
  timeLabel: string;
  timeRangeLabel: string;
  badges: OwnershipBadgeViewModel[];
  highlightTone?: "completion-task";
  localEditNotice?: string;
  completionTaskNotice?: string;
  placementReason?: string;
  travelFromLine?: string;
  travelToLine?: string;
  undoHint?: string;
  swapHint?: string;
  canSwap: boolean;
  swapIsOpen: boolean;
  swapCandidates: SwapCandidateViewModel[];
  onToggleSwap?: () => void;
  onUndo?: () => void;
};

export function ItineraryStopCard({
  stop,
}: {
  stop: ItineraryStopCardViewModel;
}) {
  const isCompletionTaskHighlight = stop.highlightTone === "completion-task";

  return (
    <div
      style={{
        position: "relative",
        overflow: "hidden",
        borderRadius: 24,
        padding: 15,
        background: isCompletionTaskHighlight
          ? "linear-gradient(135deg, rgba(239, 244, 248, 0.96), rgba(255,253,249,0.98))"
          : "rgba(255,253,249,0.94)",
        border: isCompletionTaskHighlight
          ? "1px solid rgba(37,99,235,0.22)"
          : "1px solid var(--ec-line)",
        display: "grid",
        gap: 12,
        boxShadow: isCompletionTaskHighlight
          ? "0 18px 36px rgba(37,99,235,0.12)"
          : "0 10px 24px rgba(21, 21, 21, 0.05)",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 18,
          bottom: 18,
          width: 3,
          borderRadius: 999,
          background: isCompletionTaskHighlight
            ? "var(--ec-route-blue)"
            : "rgba(37,99,235,0.22)",
        }}
        aria-hidden="true"
      />
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "58px minmax(0, 1fr) auto",
          gap: 12,
          alignItems: "start",
        }}
      >
        <div style={timeAnchorStyle}>
          <span style={{ fontSize: 15, fontWeight: 950 }}>{stop.timeLabel}</span>
          <small style={{ fontSize: 10, fontWeight: 900, color: "#5f7895" }}>
            {stop.itemTypeLabel}
          </small>
        </div>
        <div style={{ display: "grid", gap: 7, minWidth: 0 }}>
          <p style={stopTitleStyle}>
            {stop.name}
          </p>
          {stop.badges.length > 0 ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {stop.badges.map((badge) => (
                <OwnershipBadge key={`${stop.key}-${badge.label}`} badge={badge} />
              ))}
            </div>
          ) : null}
        </div>
        <div style={timeRangeStyle}>
          {stop.timeRangeLabel}
        </div>
      </div>

      {stop.localEditNotice ? (
        <div
          style={{
            borderRadius: 14,
            padding: "10px 12px",
            backgroundColor: "rgba(232, 242, 255, 0.94)",
            color: "#37506f",
            fontSize: 13,
            lineHeight: 1.55,
          }}
        >
          {stop.localEditNotice}
        </div>
      ) : null}

      {stop.completionTaskNotice ? (
        <div
          style={{
            borderRadius: 14,
            padding: "10px 12px",
            backgroundColor: "rgba(255, 247, 214, 0.92)",
            color: "#7a4d00",
            fontSize: 13,
            fontWeight: 700,
            lineHeight: 1.55,
          }}
        >
          {stop.completionTaskNotice}
        </div>
      ) : null}

      {stop.placementReason ? (
        <div style={reasonBoxStyle}>
          <span
            style={{
              color: "var(--ec-route-blue)",
              fontSize: 11,
              fontWeight: 900,
              letterSpacing: "0.08em",
            }}
          >
            为什么放这里
          </span>
          <p style={{ margin: 0 }}>{stop.placementReason}</p>
        </div>
      ) : null}
      {stop.travelFromLine || stop.travelToLine ? (
        <div style={routeLegsStyle}>
          {stop.travelFromLine ? <span>{stop.travelFromLine}</span> : null}
          {stop.travelToLine ? <span>{stop.travelToLine}</span> : null}
        </div>
      ) : null}

      {stop.onUndo ? (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            alignItems: "center",
            paddingTop: 4,
          }}
        >
          <button type="button" onClick={stop.onUndo} style={secondaryButtonStyle}>
            撤销
          </button>
          {stop.undoHint ? (
            <span style={{ color: "#708090", fontSize: 12 }}>{stop.undoHint}</span>
          ) : null}
        </div>
      ) : null}

      {stop.canSwap && stop.swapCandidates.length > 0 ? (
        <div style={{ display: "grid", gap: 10, paddingTop: 4 }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <button type="button" onClick={stop.onToggleSwap} style={secondaryButtonStyle}>
              {stop.swapIsOpen ? "收起替换候选" : "换一个"}
            </button>
            {stop.swapHint ? (
              <span style={{ color: "#708090", fontSize: 12 }}>{stop.swapHint}</span>
            ) : null}
          </div>
          {stop.swapIsOpen ? (
            <SwapCandidatePanel candidates={stop.swapCandidates} />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function OwnershipBadge({ badge }: { badge: OwnershipBadgeViewModel }) {
  const palette = {
    olive: {
      background: "rgba(231,236,232,0.96)",
      color: "#53624e",
    },
    sand: {
      background: "rgba(239,229,214,0.96)",
      color: "#8b673e",
    },
    sea: {
      background: "rgba(230,236,239,0.96)",
      color: "#576671",
    },
    fresh: {
      background: "rgba(239,229,214,0.96)",
      color: "#8b673e",
    },
    neutral: {
      background: "rgba(244,241,235,0.96)",
      color: "#5d6670",
    },
  }[badge.tone];

  return (
    <span
      style={{
        width: "fit-content",
        padding: "4px 8px",
        borderRadius: 999,
        backgroundColor: palette.background,
        color: palette.color,
        fontSize: 11,
        fontWeight: 900,
      }}
    >
      {badge.label}
    </span>
  );
}

const secondaryButtonStyle = {
  border: "1px solid var(--ec-line)",
  borderRadius: 999,
  padding: "11px 16px",
  backgroundColor: "rgba(255,253,249,0.92)",
  color: "var(--ec-ink-soft)",
  fontWeight: 700,
  cursor: "pointer",
};

const timeAnchorStyle: CSSProperties = {
  display: "grid",
  gap: 5,
  justifyItems: "center",
  alignContent: "center",
  minHeight: 58,
  borderRadius: 18,
  background: "linear-gradient(180deg, rgba(37,99,235,0.11), rgba(239,244,248,0.76))",
  color: "var(--ec-route-blue)",
  border: "1px solid rgba(37,99,235,0.12)",
};

const stopTitleStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ink)",
  fontSize: 18,
  fontWeight: 900,
  lineHeight: 1.15,
  letterSpacing: "-0.02em",
};

const timeRangeStyle: CSSProperties = {
  color: "var(--ec-slate)",
  fontSize: 12,
  fontWeight: 900,
  whiteSpace: "nowrap",
};

const reasonBoxStyle: CSSProperties = {
  display: "grid",
  gap: 5,
  padding: "11px 12px",
  borderRadius: 18,
  background: "linear-gradient(135deg, rgba(239,246,255,0.55), rgba(255,253,249,0.9))",
  border: "1px solid rgba(37,99,235,0.12)",
  color: "var(--ec-slate)",
  fontSize: 13,
  lineHeight: 1.55,
};

const routeLegsStyle: CSSProperties = {
  display: "grid",
  gap: 5,
  paddingLeft: 12,
  borderLeft: "2px solid rgba(37,99,235,0.28)",
  color: "#5f7895",
  fontSize: 13,
  lineHeight: 1.45,
};
