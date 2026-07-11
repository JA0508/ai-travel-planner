"use client";

import type { ReplanConstraintFinding } from "./replanTypes";

export function ReplanConstraintSummary({
  constraints,
  contractGaps,
}: {
  constraints: ReplanConstraintFinding[];
  contractGaps: string[];
}) {
  return (
    <section className="replan-constraint-summary">
      <span>Constraint Check</span>
      <div className="replan-constraint-summary__list">
        {constraints.map((constraint) => (
          <article key={constraint.key} className={`is-${constraint.severity}`}>
            <strong>{constraint.title}</strong>
            <p>{constraint.detail}</p>
          </article>
        ))}
      </div>
      {contractGaps.length > 0 ? (
        <div className="replan-constraint-summary__gaps">
          <strong>Contract gaps</strong>
          {contractGaps.map((gap) => (
            <p key={gap}>{gap}</p>
          ))}
        </div>
      ) : null}
      <style>{`
        .replan-constraint-summary {
          display: grid;
          gap: 8px;
        }
        .replan-constraint-summary > span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }
        .replan-constraint-summary__list {
          display: grid;
          gap: 8px;
        }
        .replan-constraint-summary article,
        .replan-constraint-summary__gaps {
          display: grid;
          gap: 5px;
          padding: 10px;
          border-radius: 14px;
          border: 1px solid var(--ec-line-soft);
          background: rgba(255,253,249,0.68);
        }
        .replan-constraint-summary article.is-ok {
          background: rgba(231,236,232,0.78);
        }
        .replan-constraint-summary article.is-watch {
          background: rgba(239,229,214,0.72);
        }
        .replan-constraint-summary article.is-blocked,
        .replan-constraint-summary__gaps {
          background: rgba(177,138,88,0.18);
        }
        .replan-constraint-summary strong {
          color: var(--ec-ink);
          font-size: 12px;
        }
        .replan-constraint-summary p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.5;
        }
      `}</style>
    </section>
  );
}
