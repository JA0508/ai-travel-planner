"use client";

import type { TripReadinessAction, TripReadinessViewModel } from "./tripReadinessModel";

export function TripReadinessPanel({
  viewModel,
  onPrimaryAction,
}: {
  viewModel: TripReadinessViewModel;
  onPrimaryAction?: (action: TripReadinessAction) => void;
}) {
  return (
    <section className={`trip-readiness-panel trip-readiness-panel--${viewModel.status}`}>
      <div className="trip-readiness-panel__header">
        <span className="trip-readiness-panel__kicker">Trip Readiness</span>
        <div className="trip-readiness-panel__title-row">
          <h3>{viewModel.statusLabel}</h3>
          <span>{viewModel.confidenceLabel}</span>
        </div>
        <p>{viewModel.headline}</p>
      </div>

      <div className="trip-readiness-panel__metrics">
        {viewModel.metrics.map((metric) => (
          <div key={metric.label} className={`trip-readiness-panel__metric is-${metric.tone}`}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>

      <div className="trip-readiness-panel__judgement">
        <span>关键判断</span>
        <p>{viewModel.summary}</p>
      </div>

      {viewModel.primaryIssue ? (
        <article className={`trip-readiness-panel__issue is-${viewModel.primaryIssue.severity}`}>
          <span>{viewModel.primaryIssue.scope ?? "当前路线"}</span>
          <strong>{viewModel.primaryIssue.title}</strong>
          <p>{viewModel.primaryIssue.impact}</p>
        </article>
      ) : (
        <article className="trip-readiness-panel__issue is-quiet">
          <span>当前路线</span>
          <strong>没有发现高优先级阻断点</strong>
          <p>可以从地图空间关系和右侧时间线继续做细节确认。</p>
        </article>
      )}

      <button
        type="button"
        className="trip-readiness-panel__action"
        onClick={() => onPrimaryAction?.(viewModel.priorityAction)}
      >
        {viewModel.priorityAction.label}
      </button>

      <div className="trip-readiness-panel__boundaries">
        <span>Protected boundaries</span>
        {viewModel.protectedBoundaries.map((boundary) => (
          <div key={boundary.key}>
            <strong>{boundary.label}</strong>
            <p>{boundary.detail}</p>
          </div>
        ))}
      </div>

      {viewModel.secondaryIssues.length > 0 ? (
        <details className="trip-readiness-panel__details">
          <summary>查看其他风险</summary>
          <div>
            {viewModel.secondaryIssues.map((issue) => (
              <p key={issue.key}>
                <strong>{issue.title}</strong>
                <span>{issue.reason}</span>
              </p>
            ))}
          </div>
        </details>
      ) : null}

      <style>{`
        .trip-readiness-panel {
          position: relative;
          overflow: hidden;
          display: grid;
          gap: 12px;
          padding: 16px;
          border-radius: 22px;
          background: linear-gradient(180deg, rgba(255,253,249,0.98), rgba(247,244,238,0.94));
          border: 1px solid var(--ec-line);
          box-shadow: var(--ec-shadow-1);
        }

        .trip-readiness-panel::before {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 4px;
          background: var(--ec-route-blue);
        }

        .trip-readiness-panel--ready::before {
          background: var(--ec-moss);
        }

        .trip-readiness-panel--minor-gaps::before,
        .trip-readiness-panel--needs-attention::before {
          background: var(--ec-ochre);
        }

        .trip-readiness-panel--not-ready::before {
          background: #8a6331;
        }

        .trip-readiness-panel__header {
          display: grid;
          gap: 7px;
        }

        .trip-readiness-panel__kicker,
        .trip-readiness-panel__judgement span,
        .trip-readiness-panel__boundaries > span,
        .trip-readiness-panel__issue span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.14em;
          text-transform: uppercase;
        }

        .trip-readiness-panel__title-row {
          display: grid;
          gap: 6px;
        }

        .trip-readiness-panel__title-row h3 {
          margin: 0;
          color: var(--ec-ink);
          font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
          font-size: 28px;
          line-height: 0.98;
          letter-spacing: 0;
          text-wrap: pretty;
        }

        .trip-readiness-panel__title-row span {
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 800;
          line-height: 1.35;
        }

        .trip-readiness-panel__header p,
        .trip-readiness-panel__judgement p,
        .trip-readiness-panel__issue p,
        .trip-readiness-panel__boundaries p,
        .trip-readiness-panel__details span {
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.55;
          text-wrap: pretty;
        }

        .trip-readiness-panel__metrics {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 8px;
        }

        .trip-readiness-panel__metric {
          display: grid;
          gap: 4px;
          min-width: 0;
          padding: 10px;
          border-radius: 14px;
          border: 1px solid var(--ec-line-soft);
          background: rgba(255,253,249,0.72);
        }

        .trip-readiness-panel__metric span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 900;
        }

        .trip-readiness-panel__metric strong {
          overflow: hidden;
          color: var(--ec-ink);
          font-size: 15px;
          line-height: 1.1;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .trip-readiness-panel__metric.is-good {
          background: rgba(231,236,232,0.76);
        }

        .trip-readiness-panel__metric.is-watch {
          background: rgba(239,229,214,0.76);
        }

        .trip-readiness-panel__metric.is-risk {
          background: rgba(177,138,88,0.2);
        }

        .trip-readiness-panel__judgement,
        .trip-readiness-panel__issue,
        .trip-readiness-panel__boundaries,
        .trip-readiness-panel__details {
          display: grid;
          gap: 8px;
          padding: 12px;
          border-radius: 16px;
          background: rgba(255,253,249,0.68);
          border: 1px solid var(--ec-line-soft);
        }

        .trip-readiness-panel__issue strong {
          color: var(--ec-ink-soft);
          font-size: 15px;
          line-height: 1.25;
        }

        .trip-readiness-panel__issue.is-high {
          background: rgba(239,229,214,0.86);
          border-color: rgba(177,138,88,0.24);
        }

        .trip-readiness-panel__issue.is-medium {
          background: rgba(247,244,238,0.92);
          border-color: rgba(177,138,88,0.18);
        }

        .trip-readiness-panel__issue.is-quiet {
          background: rgba(231,236,232,0.72);
          border-color: rgba(102,113,95,0.18);
        }

        .trip-readiness-panel__action {
          width: 100%;
          border: 1px solid transparent;
          border-radius: 14px;
          padding: 12px 13px;
          background: var(--ec-night);
          color: #fffdf9;
          font-weight: 900;
          cursor: pointer;
          text-align: left;
        }

        .trip-readiness-panel__action:focus-visible {
          outline: none;
          box-shadow: var(--ec-focus-ring);
        }

        .trip-readiness-panel__boundaries div {
          display: grid;
          gap: 3px;
          padding-top: 8px;
          border-top: 1px solid var(--ec-line-soft);
        }

        .trip-readiness-panel__boundaries strong,
        .trip-readiness-panel__details strong {
          color: var(--ec-ink-soft);
          font-size: 12px;
        }

        .trip-readiness-panel__details summary {
          cursor: pointer;
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 900;
          letter-spacing: 0.1em;
          list-style: none;
          text-transform: uppercase;
        }

        .trip-readiness-panel__details summary::-webkit-details-marker {
          display: none;
        }

        .trip-readiness-panel__details div {
          display: grid;
          gap: 8px;
        }

        .trip-readiness-panel__details p {
          display: grid;
          gap: 2px;
          margin: 0;
        }
      `}</style>
    </section>
  );
}
