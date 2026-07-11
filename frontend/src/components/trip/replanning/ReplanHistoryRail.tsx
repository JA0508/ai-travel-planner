"use client";

import type { ReplanHistoryEntry, ReplanItineraryLike } from "./replanTypes";

export function ReplanHistoryRail<TItinerary extends ReplanItineraryLike>({
  history,
  onUndoLast,
}: {
  history: ReplanHistoryEntry<TItinerary>[];
  onUndoLast?: (entry: ReplanHistoryEntry<TItinerary>) => void;
}) {
  return (
    <section className="replan-history-rail">
      <div className="replan-history-rail__header">
        <span>Replan History</span>
        {history.length > 0 && onUndoLast ? (
          <button type="button" onClick={() => onUndoLast(history[0])}>
            撤销最近一次
          </button>
        ) : null}
      </div>
      {history.length > 0 ? (
        history.map((entry) => (
          <article key={entry.id}>
            <strong>{entry.plan.title}</strong>
            <p>{entry.changeSet.summary}</p>
            <small>{entry.usedBackend ? "后端重跑" : "本地 mutation"}</small>
          </article>
        ))
      ) : (
        <p className="replan-history-rail__empty">本轮还没有执行过调整。</p>
      )}
      <style>{`
        .replan-history-rail {
          display: grid;
          gap: 8px;
        }
        .replan-history-rail__header {
          display: flex;
          gap: 8px;
          align-items: center;
          justify-content: space-between;
        }
        .replan-history-rail__header span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }
        .replan-history-rail__header button {
          border: 1px solid var(--ec-line);
          border-radius: 999px;
          background: rgba(255,253,249,0.72);
          color: var(--ec-ink);
          font-size: 11px;
          font-weight: 850;
          min-height: 30px;
          padding: 0 10px;
          cursor: pointer;
        }
        .replan-history-rail article {
          display: grid;
          gap: 3px;
          padding: 9px 10px;
          border-radius: 12px;
          border: 1px solid var(--ec-line-soft);
          background: rgba(255,253,249,0.62);
        }
        .replan-history-rail strong {
          color: var(--ec-ink);
          font-size: 12px;
        }
        .replan-history-rail p,
        .replan-history-rail__empty {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.45;
        }
        .replan-history-rail small {
          color: var(--ec-route-blue);
          font-weight: 900;
        }
      `}</style>
    </section>
  );
}
