"use client";

export type SwapCandidateViewModel = {
  key: string;
  name: string;
  meta: string;
  reasoningSummary: string;
  relationSummary: string;
  onSelect: () => void;
};

export function SwapCandidatePanel({
  candidates,
}: {
  candidates: SwapCandidateViewModel[];
}) {
  return (
    <div
      style={{
        display: "grid",
        gap: 10,
        padding: 12,
        borderRadius: 16,
        backgroundColor: "rgba(247,250,247,0.92)",
        border: "1px solid rgba(102,113,95,0.18)",
      }}
    >
      <p style={{ margin: 0, color: "var(--ec-moss)", fontSize: 13, fontWeight: 800 }}>
        这个时间段可替换的候选
      </p>
      <div style={{ display: "grid", gap: 10 }}>
        {candidates.map((candidate) => (
          <div
            key={candidate.key}
            style={{
              display: "grid",
              gap: 6,
              padding: 12,
              borderRadius: 14,
              backgroundColor: "rgba(255,253,249,0.92)",
              border: "1px solid var(--ec-line)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 12,
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <div style={{ display: "grid", gap: 4 }}>
                <p style={{ margin: 0, color: "var(--ec-ink)", fontWeight: 800 }}>
                  {candidate.name}
                </p>
                <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 12 }}>
                  {candidate.meta}
                </p>
              </div>
              <button type="button" onClick={candidate.onSelect} style={primaryButtonStyle}>
                换成这个
              </button>
            </div>
            <p style={{ margin: 0, color: "#56695f", fontSize: 13, lineHeight: 1.55 }}>
              {candidate.reasoningSummary}
            </p>
            <p style={{ margin: 0, color: "#73817a", fontSize: 13, lineHeight: 1.55 }}>
              {candidate.relationSummary}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

const primaryButtonStyle = {
  border: "none",
  borderRadius: 999,
  padding: "13px 20px",
  background: "var(--ec-night)",
  color: "#ffffff",
  fontWeight: 700,
  cursor: "pointer",
  boxShadow: "0 16px 30px rgba(21,21,21,0.18)",
};
