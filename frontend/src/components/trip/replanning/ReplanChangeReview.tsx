"use client";

import type { ReplanChangeSet } from "./replanTypes";

export function ReplanChangeReview({ changeSet }: { changeSet: ReplanChangeSet | null }) {
  if (!changeSet) {
    return null;
  }

  const changes = [
    ...changeSet.removed,
    ...changeSet.added,
    ...changeSet.moved,
    ...changeSet.retimed,
    ...changeSet.routeChanged,
  ];

  return (
    <section className="replan-change-review">
      <div className="replan-change-review__header">
        <span>Change Review</span>
        <strong>{changeSet.summary}</strong>
      </div>
      <div>
        {changes.length > 0 ? (
          changes.map((change) => (
            <article key={change.key} className={`is-${change.kind}`}>
              <strong>{change.title}</strong>
              <p>{change.detail}</p>
            </article>
          ))
        ) : (
          <p className="replan-change-review__empty">执行后没有检测到可见行程变化。</p>
        )}
      </div>
      <style>{`
        .replan-change-review {
          display: grid;
          gap: 10px;
          padding: 12px;
          border-radius: 16px;
          border: 1px solid rgba(47,111,168,0.28);
          background: rgba(47,111,168,0.07);
        }
        .replan-change-review__header {
          display: grid;
          gap: 5px;
        }
        .replan-change-review__header span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }
        .replan-change-review__header strong {
          color: var(--ec-ink);
          font-size: 13px;
        }
        .replan-change-review > div:last-child {
          display: grid;
          gap: 8px;
        }
        .replan-change-review article {
          display: grid;
          gap: 4px;
          padding: 9px 10px;
          border-radius: 12px;
          background: rgba(255,253,249,0.76);
          border: 1px solid var(--ec-line-soft);
        }
        .replan-change-review article strong {
          color: var(--ec-ink);
          font-size: 12px;
        }
        .replan-change-review article p,
        .replan-change-review__empty {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.5;
        }
      `}</style>
    </section>
  );
}
