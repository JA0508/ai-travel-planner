"use client";

import type { ReplanImpactItem } from "./replanTypes";

export function ReplanImpactPreview({ items }: { items: ReplanImpactItem[] }) {
  return (
    <section className="replan-impact-preview">
      <span>Impact Preview</span>
      <div>
        {items.map((item) => (
          <article key={item.key} className={`is-${item.tone}`}>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </article>
        ))}
      </div>
      <style>{`
        .replan-impact-preview {
          display: grid;
          gap: 8px;
        }
        .replan-impact-preview > span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }
        .replan-impact-preview > div {
          display: grid;
          gap: 8px;
        }
        .replan-impact-preview article {
          display: grid;
          gap: 5px;
          padding: 10px;
          border-radius: 14px;
          border-left: 3px solid var(--ec-route-blue);
          background: rgba(255,253,249,0.68);
        }
        .replan-impact-preview article.is-protect {
          border-left-color: var(--ec-moss);
        }
        .replan-impact-preview article.is-estimate {
          border-left-color: var(--ec-ochre);
        }
        .replan-impact-preview article.is-gap {
          border-left-color: #8a6331;
        }
        .replan-impact-preview strong {
          color: var(--ec-ink);
          font-size: 12px;
        }
        .replan-impact-preview p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.5;
        }
      `}</style>
    </section>
  );
}
