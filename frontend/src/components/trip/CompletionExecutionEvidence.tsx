"use client";

import type { CSSProperties } from "react";

export type CompletionScoreFactor =
  | string
  | {
      code: string;
      label: string;
      value?: string | number | null;
      impact?: number | null;
    };

export type CompletionScoreBreakdownRow = {
  key: "density" | "meals" | "evening" | "transport_boundary";
  label: string;
  value: number;
  description: string;
  signals: CompletionScoreFactor[];
  penalties: CompletionScoreFactor[];
  color: string;
};

export type CompletionScoreBreakdownLike = {
  density: number;
  density_reason?: string | null;
  density_signals?: CompletionScoreFactor[] | null;
  density_penalties?: CompletionScoreFactor[] | null;
  meals: number;
  meals_reason?: string | null;
  meals_signals?: CompletionScoreFactor[] | null;
  meals_penalties?: CompletionScoreFactor[] | null;
  evening: number;
  evening_reason?: string | null;
  evening_signals?: CompletionScoreFactor[] | null;
  evening_penalties?: CompletionScoreFactor[] | null;
  transport_boundary: number;
  transport_boundary_reason?: string | null;
  transport_boundary_signals?: CompletionScoreFactor[] | null;
  transport_boundary_penalties?: CompletionScoreFactor[] | null;
};

export function buildCompletionScoreBreakdownRows(
  scoreBreakdown: CompletionScoreBreakdownLike,
): CompletionScoreBreakdownRow[] {
  return [
    {
      key: "density",
      label: "行程密度",
      value: scoreBreakdown.density,
      description:
        scoreBreakdown.density_reason ??
        "看每天是否有足够可执行的游玩 block，同时扣除仍然明显空着的时间段。",
      signals: scoreBreakdown.density_signals ?? [],
      penalties: scoreBreakdown.density_penalties ?? [],
      color: "linear-gradient(90deg, #91b66f 0%, #5f8f57 100%)",
    },
    {
      key: "meals",
      label: "餐食结构",
      value: scoreBreakdown.meals,
      description:
        scoreBreakdown.meals_reason ??
        "看午餐和晚餐是否作为结构锚点进入路线，而不是被当作普通 POI 塞进去。",
      signals: scoreBreakdown.meals_signals ?? [],
      penalties: scoreBreakdown.meals_penalties ?? [],
      color: "linear-gradient(90deg, #e5b96f 0%, #c8833a 100%)",
    },
    {
      key: "evening",
      label: "夜间安排",
      value: scoreBreakdown.evening,
      description:
        scoreBreakdown.evening_reason ??
        "看晚上是否有夜景、散步、美食或留白，避免白天排完就断掉。",
      signals: scoreBreakdown.evening_signals ?? [],
      penalties: scoreBreakdown.evening_penalties ?? [],
      color: "linear-gradient(90deg, #8da2d6 0%, #526fb3 100%)",
    },
    {
      key: "transport_boundary",
      label: "交通边界",
      value: scoreBreakdown.transport_boundary,
      description:
        scoreBreakdown.transport_boundary_reason ??
        "看到达、离开、固定事件、住宿区域和离开枢纽是否支撑这条路线走得稳。",
      signals: scoreBreakdown.transport_boundary_signals ?? [],
      penalties: scoreBreakdown.transport_boundary_penalties ?? [],
      color: "linear-gradient(90deg, #83c5be 0%, #3f8f89 100%)",
    },
  ];
}

export function CompletionExecutionEvidence({
  isApplyingImprovement = false,
  onApplyAndReplan,
  onApplyImprovement,
  rows,
}: {
  isApplyingImprovement?: boolean;
  onApplyAndReplan?: (prompt: string) => void;
  onApplyImprovement?: (prompt: string) => void;
  rows: CompletionScoreBreakdownRow[];
}) {
  const strengths = rows.flatMap((row) =>
    row.signals.slice(0, 2).map((signal) => ({
      key: `${row.key}-signal-${getScoreFactorKey(signal)}`,
      dimension: row.label,
      text: formatScoreFactorLabel(signal),
    })),
  );
  const risks = rows.flatMap((row) =>
    row.penalties.slice(0, 2).map((penalty) => ({
      key: `${row.key}-penalty-${getScoreFactorKey(penalty)}`,
      dimension: row.label,
      prompt: buildImprovementPrompt(row, penalty),
      text: formatScoreFactorLabel(penalty),
    })),
  );

  return (
    <section
      style={{
        display: "grid",
        gap: 12,
        padding: 14,
        borderRadius: 20,
        backgroundColor: "rgba(255,255,255,0.72)",
        border: "1px solid rgba(128, 150, 137, 0.16)",
      }}
    >
      <div style={{ display: "grid", gap: 4 }}>
        <p style={{ margin: 0, color: "#31483b", fontSize: 15, fontWeight: 900 }}>
          为什么这条路线可执行
        </p>
        <p style={{ margin: 0, color: "#6b7d73", fontSize: 13, lineHeight: 1.55 }}>
          系统不是只数景点，而是同时检查行程密度、餐食节奏、夜间安排和到离开边界。
        </p>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 10,
        }}
      >
        <div style={completionEvidenceColumnStyle("good")}>
          <p style={completionEvidenceHeadingStyle}>已支撑路线的证据</p>
          {strengths.length > 0 ? (
            strengths.slice(0, 6).map((item) => (
              <div key={item.key} style={completionEvidenceItemStyle}>
                <span style={completionEvidenceDimensionStyle}>{item.dimension}</span>
                <span>{item.text}</span>
              </div>
            ))
          ) : (
            <p style={completionEvidenceEmptyStyle}>暂无明确加分信号。</p>
          )}
        </div>
        <div style={completionEvidenceColumnStyle("risk")}>
          <p style={completionEvidenceHeadingStyle}>还可以继续加强</p>
          {risks.length > 0 ? (
            risks.slice(0, 6).map((item) => (
              <div key={item.key} style={completionEvidenceItemStyle}>
                <span style={completionEvidenceDimensionStyle}>{item.dimension}</span>
                <span>{item.text}</span>
                {onApplyImprovement && item.prompt ? (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {onApplyAndReplan ? (
                      <button
                        type="button"
                        disabled={isApplyingImprovement}
                        onClick={() => {
                          if (item.prompt) {
                            onApplyAndReplan(item.prompt);
                          }
                        }}
                        style={{
                          ...completionEvidenceActionStyle,
                          backgroundColor: "rgba(154, 106, 47, 0.12)",
                        }}
                      >
                        {isApplyingImprovement ? "优化中…" : "直接优化"}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      disabled={isApplyingImprovement}
                      onClick={() => {
                        if (item.prompt) {
                          onApplyImprovement(item.prompt);
                        }
                      }}
                      style={completionEvidenceActionStyle}
                    >
                      先编辑
                    </button>
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <p style={completionEvidenceEmptyStyle}>没有明显待补风险。</p>
          )}
        </div>
      </div>
    </section>
  );
}

function completionEvidenceColumnStyle(tone: "good" | "risk"): CSSProperties {
  return {
    display: "grid",
    gap: 8,
    alignContent: "start",
    padding: 12,
    borderRadius: 16,
    backgroundColor:
      tone === "good" ? "rgba(233, 243, 223, 0.8)" : "rgba(255, 247, 237, 0.86)",
    border:
      tone === "good"
        ? "1px solid rgba(123, 160, 127, 0.16)"
        : "1px solid rgba(206, 171, 111, 0.16)",
  };
}

const completionEvidenceHeadingStyle: CSSProperties = {
  margin: 0,
  color: "#33463d",
  fontSize: 12,
  fontWeight: 900,
  letterSpacing: "0.04em",
};

const completionEvidenceItemStyle: CSSProperties = {
  display: "grid",
  gap: 3,
  margin: 0,
  color: "#4f6258",
  fontSize: 12,
  lineHeight: 1.45,
};

const completionEvidenceActionStyle: CSSProperties = {
  justifySelf: "start",
  border: "1px solid rgba(154, 106, 47, 0.2)",
  borderRadius: 999,
  padding: "5px 9px",
  backgroundColor: "rgba(255,255,255,0.7)",
  color: "#8a6331",
  cursor: "pointer",
  fontSize: 11,
  fontWeight: 800,
};

const completionEvidenceDimensionStyle: CSSProperties = {
  color: "#7a8b82",
  fontSize: 11,
  fontWeight: 900,
};

const completionEvidenceEmptyStyle: CSSProperties = {
  margin: 0,
  color: "#7a8b82",
  fontSize: 12,
  lineHeight: 1.45,
};

function getScoreFactorKey(factor: CompletionScoreFactor): string {
  if (typeof factor === "string") {
    return factor;
  }
  return `${factor.code}-${factor.value ?? "none"}-${factor.impact ?? "none"}`;
}

function formatScoreFactorLabel(factor: CompletionScoreFactor): string {
  if (typeof factor === "string") {
    return factor;
  }
  const valueText =
    factor.value !== null && factor.value !== undefined ? ` ${factor.value}` : "";
  const impactText =
    factor.impact !== null && factor.impact !== undefined
      ? ` (${factor.impact > 0 ? "+" : ""}${factor.impact})`
      : "";
  return `${factor.label}${valueText}${impactText}`;
}

function buildImprovementPrompt(
  row: CompletionScoreBreakdownRow,
  factor: CompletionScoreFactor,
): string | null {
  const code = typeof factor === "string" ? factor : factor.code;

  if (code.includes("sparse_blocks") || code.includes("empty_core_blocks")) {
    return "请优先补齐行程里还偏空的时间段，补充顺路、低绕行、适合当前节奏的景点或轻量活动。";
  }
  if (code.includes("missing_meal")) {
    return "请把午餐和晚餐作为行程结构锚点补齐，优先选择顺路、符合我偏好的餐厅，不要把餐厅当普通景点硬塞。";
  }
  if (code.includes("missing_evening")) {
    return "请补强晚上安排，优先加入适合夜景、散步、美食或轻松收尾的活动，也可以保留合理留白。";
  }
  if (code.includes("stay_area")) {
    return "请根据当前行程分布推荐更合适的住宿区域，并说明为什么住在那里更顺。";
  }
  if (code.includes("departure_hub")) {
    return "请根据最后一天路线和我的出行偏好，推荐更合适的离开交通枢纽，并让最后一天安排更稳。";
  }
  if (code.includes("arrival_boundary")) {
    return "请把到达时间和到达地点考虑得更明确，让第一天安排更轻、更顺，不要一开始就太赶。";
  }
  if (code.includes("departure_boundary")) {
    return "请把离开时间和离开地点考虑得更明确，让最后一天安排更稳，避免离开前跨城折返。";
  }
  if (code.includes("availability") || code.includes("fixed_event")) {
    return "请重新检查我的固定事件和可用时间窗口，确保行程不会和硬约束冲突。";
  }

  return `请针对“${row.label}”这个薄弱点优化行程，让路线更可执行。`;
}
