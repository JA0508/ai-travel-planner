"use client";

import type { PlaceCaveat } from "./placeDetailViewModel";

export function PlaceCaveats({ caveats }: { caveats: PlaceCaveat[] }) {
  if (!caveats.length) {
    return null;
  }
  return (
    <section className="place-caveats">
      <span>Caveats</span>
      {caveats.slice(0, 4).map((caveat) => (
        <p key={caveat.key}>
          <strong>{caveat.label}</strong>
          {caveat.detail}
        </p>
      ))}
      <style>{`
        .place-caveats {
          display: grid;
          gap: 8px;
          padding: 12px 13px;
          border-radius: 16px;
          border: 1px solid rgba(177,138,88,0.18);
          background: rgba(239,229,214,0.46);
        }
        .place-caveats > span {
          color: var(--ec-clay);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }
        .place-caveats p {
          display: grid;
          gap: 3px;
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.45;
        }
        .place-caveats strong {
          color: var(--ec-ink-soft);
          font-size: 12.5px;
        }
      `}</style>
    </section>
  );
}
