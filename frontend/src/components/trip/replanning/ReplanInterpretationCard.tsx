"use client";

import type { ReplanMutationPlan } from "./replanTypes";

export function ReplanInterpretationCard({
  plan,
  backendLines = [],
}: {
  plan: ReplanMutationPlan;
  backendLines?: string[];
}) {
  return (
    <section className="replan-interpretation-card">
      <div>
        <span>Interpretation</span>
        <h3>{plan.title}</h3>
        <p>{plan.summary}</p>
      </div>
      <div className="replan-interpretation-card__meta">
        <strong>{formatExecutionMode(plan.executionMode)}</strong>
        <strong>{formatConfidence(plan.confidence)}</strong>
      </div>
      <div className="replan-interpretation-card__evidence">
        {plan.evidence.map((line) => (
          <p key={line}>{line}</p>
        ))}
        {backendLines.map((line) => (
          <p key={`backend-${line}`}>{line}</p>
        ))}
      </div>
      <style>{`
        .replan-interpretation-card {
          display: grid;
          gap: 10px;
          padding: 12px;
          border-radius: 16px;
          border: 1px solid var(--ec-line-soft);
          background: rgba(255,253,249,0.72);
        }
        .replan-interpretation-card span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }
        .replan-interpretation-card h3 {
          margin: 4px 0 0;
          color: var(--ec-ink);
          font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
          font-size: 22px;
          line-height: 1.05;
          letter-spacing: 0;
        }
        .replan-interpretation-card p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.55;
        }
        .replan-interpretation-card__meta {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .replan-interpretation-card__meta strong {
          padding: 5px 8px;
          border-radius: 999px;
          background: rgba(47,111,168,0.1);
          color: var(--ec-route-blue);
          font-size: 11px;
        }
        .replan-interpretation-card__evidence {
          display: grid;
          gap: 6px;
          border-top: 1px solid var(--ec-line-soft);
          padding-top: 10px;
        }
      `}</style>
    </section>
  );
}

function formatExecutionMode(mode: ReplanMutationPlan["executionMode"]): string {
  if (mode === "local_mutation") {
    return "本地确定性 mutation";
  }
  if (mode === "backend_replan") {
    return "后端 follow-up replan";
  }
  return "当前不可执行";
}

function formatConfidence(confidence: ReplanMutationPlan["confidence"]): string {
  if (confidence === "high") {
    return "高置信";
  }
  if (confidence === "medium") {
    return "中置信";
  }
  return "低置信";
}
