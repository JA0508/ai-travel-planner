"use client";

type CompletionCandidateTraceLike = {
  name: string;
  rank?: number | null;
  score?: number | null;
  status?: string | null;
  reason: string;
};

type CompletionDecisionEvidenceLike = {
  why_gap_exists: string;
  why_this_poi_fits: string;
  alternatives_rejected: string;
  top_candidates?: CompletionCandidateTraceLike[] | null;
  rejected_candidates?: CompletionCandidateTraceLike[] | null;
};

export type CompletionTaskCandidateOptionLike = {
  name: string;
  type: string;
  suggested_day: number;
  suggested_block: string;
  reasoning_summary: string;
  itinerary_relation_summary: string;
  decision_evidence?: CompletionDecisionEvidenceLike | null;
};

export type CompletionTaskCandidatePreviewLike = {
  summary: string;
  candidate_source_summary?: string | null;
  candidate_discovery_status?: string | null;
  options: CompletionTaskCandidateOptionLike[];
};

type CompletionTaskCandidatePreviewWithOptions<TOption extends CompletionTaskCandidateOptionLike> =
  Omit<CompletionTaskCandidatePreviewLike, "options"> & { options: TOption[] };

type CompletionTaskCandidatePanelProps<TOption extends CompletionTaskCandidateOptionLike> = {
  preview: CompletionTaskCandidatePreviewWithOptions<TOption>;
  disabled: boolean;
  applying: boolean;
  onApplyOption: (option: TOption) => void;
  onRefreshOptions: () => void;
  onRejectOption: (option: TOption) => void;
};

export function CompletionTaskCandidatePanel<TOption extends CompletionTaskCandidateOptionLike>({
  preview,
  disabled,
  applying,
  onApplyOption,
  onRefreshOptions,
  onRejectOption,
}: CompletionTaskCandidatePanelProps<TOption>) {
  const optionCount = preview.options.length;
  const emptyStateText =
    preview.candidate_discovery_status === "local_only"
      ? "当前未启用实时地点发现，只使用已解析地点和历史候选；不会展示占位地点。可以先编辑这句，让系统缩小偏好。"
      : preview.candidate_discovery_status === "empty"
        ? "暂时没有找到稳妥候选，可能是当前时间段太紧，或缺少实时地点发现能力；可以先编辑这句优化要求。"
        : "暂时没有顺路候选，可以先编辑这句优化要求。";

  return (
    <section
      style={{
        display: "grid",
        gap: 14,
        padding: 14,
        borderRadius: 20,
        background:
          "linear-gradient(180deg, rgba(255,253,249,0.98), rgba(247,244,238,0.94))",
        border: "1px solid var(--ec-line-soft)",
      }}
    >
      <div style={{ display: "grid", gap: 7 }}>
        <p style={{ margin: 0, color: "var(--ec-ink-soft)", fontSize: 13, lineHeight: 1.6 }}>
          {preview.summary}
        </p>
        {preview.candidate_source_summary ? (
          <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 12, lineHeight: 1.5 }}>
            {preview.candidate_source_summary}
          </p>
        ) : null}
        {optionCount === 1 ? (
          <p style={{ margin: 0, color: "var(--ec-clay)", fontSize: 12, lineHeight: 1.5 }}>
            当前只有 1 个稳妥候选，系统会优先保证顺路和可执行。
          </p>
        ) : null}
      </div>
      {optionCount > 0 ? (
        <div style={{ display: "grid", gap: 10 }}>
          {preview.options.map((option, index) => (
            <div
              key={completionOptionKey(option)}
              style={{
                position: "relative",
                display: "grid",
                gap: 10,
                padding: index === 0 ? "14px 14px 14px 18px" : 14,
                borderRadius: 18,
                backgroundColor: "rgba(255,255,255,0.84)",
                border:
                  index === 0
                    ? "1px solid rgba(177,138,88,0.24)"
                    : "1px solid rgba(102,113,95,0.14)",
              }}
            >
              {index === 0 ? (
                <span
                  aria-hidden="true"
                  style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: 0,
                    width: 4,
                    borderRadius: "18px 0 0 18px",
                    backgroundColor: "var(--ec-ochre)",
                  }}
                />
              ) : null}
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <p style={{ margin: 0, color: "var(--ec-ink)", fontSize: 14, fontWeight: 900 }}>
                  {option.name}
                </p>
                <span
                  style={{
                    padding: "4px 8px",
                    borderRadius: 999,
                    backgroundColor:
                      index === 0 ? "rgba(154, 106, 47, 0.12)" : "rgba(123, 160, 127, 0.12)",
                    color: index === 0 ? "#7d5426" : "#587663",
                    fontSize: 11,
                    fontWeight: 900,
                    whiteSpace: "nowrap",
                  }}
                >
                  {index === 0 ? "推荐补入" : "备选"}
                </span>
              </div>
              <p style={{ margin: 0, color: "var(--ec-ink-soft)", fontSize: 13, lineHeight: 1.6 }}>
                {option.reasoning_summary}
              </p>
              <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 12, lineHeight: 1.6 }}>
                {option.itinerary_relation_summary}
              </p>
              <CompletionDecisionEvidenceList evidence={option.decision_evidence ?? null} />
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onApplyOption(option)}
                  className="ec-interactive-pill"
                  style={{
                    border: "1px solid rgba(154, 106, 47, 0.18)",
                    borderRadius: 999,
                    padding: "8px 12px",
                    backgroundColor: "rgba(154, 106, 47, 0.12)",
                    color: "#7d5426",
                    cursor: disabled ? "not-allowed" : "pointer",
                    fontSize: 12,
                    fontWeight: 900,
                  }}
                >
                  {applying ? "补入中..." : "补进去"}
                </button>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={onRefreshOptions}
                  className="ec-interactive-pill"
                  style={secondaryCandidateActionStyle}
                >
                  换一批
                </button>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => onRejectOption(option)}
                  className="ec-interactive-pill"
                  style={secondaryCandidateActionStyle}
                >
                  不适合我
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p style={{ margin: 0, color: "var(--ec-clay)", fontSize: 12, lineHeight: 1.6 }}>
          {emptyStateText}
        </p>
      )}
    </section>
  );
}

const secondaryCandidateActionStyle = {
  border: "1px solid rgba(123, 160, 127, 0.18)",
  borderRadius: 999,
  padding: "8px 12px",
  backgroundColor: "rgba(255,255,255,0.72)",
  color: "#587663",
  cursor: "pointer",
  fontSize: 12,
  fontWeight: 800,
} as const;

function CompletionDecisionEvidenceList({
  evidence,
}: {
  evidence: CompletionDecisionEvidenceLike | null;
}) {
  if (!evidence) {
    return null;
  }

  const rows = [
    ["为什么要补", evidence.why_gap_exists],
    ["为什么适合", evidence.why_this_poi_fits],
    ["取舍", evidence.alternatives_rejected],
  ];

  return (
    <div
      style={{
        display: "grid",
        gap: 8,
        padding: "12px 14px",
        borderRadius: 18,
        background: "rgba(255,255,255,0.72)",
        border: "1px solid rgba(126, 151, 134, 0.16)",
      }}
    >
      {rows.map(([label, value]) => (
        <p
          key={`${label}-${value}`}
          style={{
            margin: 0,
            color: "var(--ec-slate)",
            fontSize: 12,
            lineHeight: 1.55,
          }}
        >
          <strong style={{ color: "var(--ec-moss)" }}>{label}:</strong> {value}
        </p>
      ))}
    </div>
  );
}

function completionOptionKey(option: CompletionTaskCandidateOptionLike): string {
  return [
    option.name,
    option.type,
    option.suggested_day,
    option.suggested_block,
  ].join("::");
}
