"use client";

import type { PlaceDetailViewModel } from "./placeDetailViewModel";

export function PlaceTrustCard({ trust }: { trust: PlaceDetailViewModel["trust"] }) {
  return (
    <section className={`place-trust-card place-trust-card--${trust.verdict}`}>
      <span>{trust.label}</span>
      <strong>{trust.headline}</strong>
      <p>{trust.explanation}</p>
      <style>{`
        .place-trust-card {
          display: grid;
          gap: 8px;
          padding: 13px;
          border-radius: 16px;
          background: rgba(255,253,249,0.76);
          border: 1px solid var(--ec-line);
        }
        .place-trust-card--strong-fit {
          border-color: rgba(102,113,95,0.28);
          background: rgba(231,236,232,0.68);
        }
        .place-trust-card--needs-review,
        .place-trust-card--uncertain-fit {
          border-color: rgba(177,138,88,0.24);
          background: rgba(239,229,214,0.62);
        }
        .place-trust-card span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.13em;
          text-transform: uppercase;
        }
        .place-trust-card strong {
          color: var(--ec-ink-soft);
          font-size: 16px;
          line-height: 1.25;
        }
        .place-trust-card p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12.5px;
          line-height: 1.55;
          text-wrap: pretty;
        }
      `}</style>
    </section>
  );
}
