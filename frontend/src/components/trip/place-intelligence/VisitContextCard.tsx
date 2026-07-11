"use client";

import type { PlaceDetailViewModel } from "./placeDetailViewModel";

export function VisitContextCard({ visitContext }: { visitContext: PlaceDetailViewModel["visitContext"] }) {
  return (
    <section className="visit-context-card">
      <span>Visit context</span>
      <strong>{visitContext.label}</strong>
      {visitContext.reason ? <p>{visitContext.reason}</p> : null}
      <style>{`
        .visit-context-card {
          display: grid;
          gap: 6px;
          padding: 12px 13px;
          border-radius: 16px;
          background: rgba(247,244,238,0.72);
          border: 1px solid var(--ec-line-soft);
        }
        .visit-context-card span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }
        .visit-context-card strong {
          color: var(--ec-ink-soft);
          font-size: 14px;
        }
        .visit-context-card p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.5;
        }
      `}</style>
    </section>
  );
}
