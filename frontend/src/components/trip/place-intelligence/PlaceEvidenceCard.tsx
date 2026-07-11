"use client";

import type { EvidenceKind, PlaceEvidenceItem } from "./placeDetailViewModel";

export function PlaceEvidenceCard({ evidence }: { evidence: PlaceEvidenceItem[] }) {
  const primary = evidence.slice(0, 5);
  const secondary = evidence.slice(5);
  return (
    <section className="place-evidence-card">
      <div className="place-evidence-card__heading">
        <span>Evidence provenance</span>
        <strong>证据分层</strong>
      </div>
      <div className="place-evidence-card__list">
        {primary.map((item) => <EvidenceRow key={item.key} item={item} />)}
      </div>
      {secondary.length > 0 ? (
        <details>
          <summary>查看完整证据</summary>
          <div>
            {secondary.map((item) => <EvidenceRow key={item.key} item={item} />)}
          </div>
        </details>
      ) : null}
      <style>{`
        .place-evidence-card {
          display: grid;
          gap: 10px;
          padding: 13px;
          border-radius: 16px;
          border: 1px solid var(--ec-line);
          background: rgba(255,253,249,0.68);
        }
        .place-evidence-card__heading {
          display: flex;
          justify-content: space-between;
          gap: 10px;
          align-items: baseline;
        }
        .place-evidence-card__heading span,
        .place-evidence-card__kind {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }
        .place-evidence-card__heading strong {
          color: var(--ec-ink-soft);
          font-size: 14px;
        }
        .place-evidence-card__list,
        .place-evidence-card details div {
          display: grid;
          gap: 8px;
        }
        .place-evidence-card__row {
          display: grid;
          gap: 4px;
          padding-top: 8px;
          border-top: 1px solid var(--ec-line-soft);
        }
        .place-evidence-card__row strong {
          color: var(--ec-ink-soft);
          font-size: 12.5px;
        }
        .place-evidence-card__row p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.45;
        }
        .place-evidence-card summary {
          cursor: pointer;
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 900;
          list-style: none;
        }
        .place-evidence-card summary::-webkit-details-marker {
          display: none;
        }
      `}</style>
    </section>
  );
}

function EvidenceRow({ item }: { item: PlaceEvidenceItem }) {
  return (
    <div className="place-evidence-card__row">
      <span className="place-evidence-card__kind">{evidenceLabel(item.kind)}</span>
      <strong>{item.label}</strong>
      <p>{item.detail}</p>
    </div>
  );
}

function evidenceLabel(kind: EvidenceKind): string {
  if (kind === "provider-fact") {
    return "Confirmed";
  }
  if (kind === "user-constraint") {
    return "Based on your request";
  }
  if (kind === "deterministic-inference") {
    return "System reasoning";
  }
  if (kind === "heuristic") {
    return "Needs verification";
  }
  return "Missing data";
}
