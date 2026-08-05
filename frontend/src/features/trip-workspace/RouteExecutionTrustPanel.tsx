"use client";

import type {
  RouteWorkspaceExecutionTrustFactViewModel,
  RouteWorkspaceExecutionTrustViewModel,
} from "./routeWorkspaceViewModel";

export function RouteExecutionTrustPanel({
  viewModel,
}: {
  viewModel: RouteWorkspaceExecutionTrustViewModel;
}) {
  const facts = [
    ...viewModel.blockingFacts,
    ...viewModel.warningFacts,
    ...viewModel.contextFacts,
  ];

  return (
    <section className={`route-execution-trust route-execution-trust--${viewModel.status}`}>
      <header>
        <span>Execution Trust</span>
        <strong>{viewModel.statusLabel}</strong>
        <p>{viewModel.headline}</p>
      </header>

      {viewModel.blockingReasons.length > 0 ? (
        <ReasonList label="阻断项" reasons={viewModel.blockingReasons} tone="blocked" />
      ) : null}
      {viewModel.warningReasons.length > 0 ? (
        <ReasonList label="需要复核" reasons={viewModel.warningReasons} tone="attention" />
      ) : null}

      <div className="route-execution-trust__facts">
        <span>事实边界</span>
        {facts.length ? facts.map((fact) => <FactRow key={fact.key} fact={fact} />) : (
          <p>本次路线没有保存细粒度事实摘要；不要将界面中的估算当作实时确认。</p>
        )}
      </div>

      <style>{`
        .route-execution-trust {
          display: grid;
          gap: 10px;
          padding: 16px 15px;
          border: 1px solid var(--ec-line);
          border-radius: 22px;
          background: rgba(255,253,249,0.94);
          box-shadow: var(--ec-shadow-1);
        }
        .route-execution-trust--blocked { border-color: rgba(185,78,72,0.32); background: rgba(252,241,238,0.92); }
        .route-execution-trust--needs_attention { border-color: rgba(177,138,88,0.28); background: rgba(247,244,238,0.96); }
        .route-execution-trust header { display: grid; gap: 5px; }
        .route-execution-trust header > span,
        .route-execution-trust__facts > span,
        .route-execution-trust__reason-label {
          color: var(--ec-slate); font-size: 10px; font-weight: 900; letter-spacing: .12em; text-transform: uppercase;
        }
        .route-execution-trust header strong { color: var(--ec-ink); font-family: "Iowan Old Style", Georgia, serif; font-size: 22px; line-height: 1; }
        .route-execution-trust header p, .route-execution-trust__facts > p, .route-execution-trust__reason-list p, .route-execution-trust__fact p { margin: 0; color: var(--ec-slate); font-size: 12px; line-height: 1.5; text-wrap: pretty; }
        .route-execution-trust__reason-list, .route-execution-trust__facts { display: grid; gap: 7px; padding: 10px; border: 1px solid var(--ec-line-soft); border-radius: 14px; background: rgba(255,253,249,0.65); }
        .route-execution-trust__reason-list--blocked { border-color: rgba(185,78,72,0.24); }
        .route-execution-trust__fact { display: grid; gap: 4px; padding-top: 8px; border-top: 1px solid var(--ec-line-soft); }
        .route-execution-trust__fact:first-of-type { padding-top: 0; border-top: 0; }
        .route-execution-trust__fact-title { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; color: var(--ec-ink-soft); font-size: 12px; }
        .route-execution-trust__fact-title strong { font-size: 12px; }
        .route-execution-trust__fact-title span { color: var(--ec-slate); font-size: 11px; font-weight: 800; }
        .route-execution-trust__fact-meta { display: flex; flex-wrap: wrap; gap: 5px 8px; color: var(--ec-slate); font-size: 10px; line-height: 1.35; }
        .route-execution-trust__fact--attention .route-execution-trust__fact-title span { color: #8b673e; }
        .route-execution-trust__fact--blocked .route-execution-trust__fact-title span { color: #9d302a; }
      `}</style>
    </section>
  );
}

function ReasonList({ label, reasons, tone }: { label: string; reasons: string[]; tone: "attention" | "blocked" }) {
  return <div className={`route-execution-trust__reason-list route-execution-trust__reason-list--${tone}`}><span className="route-execution-trust__reason-label">{label}</span>{reasons.slice(0, 2).map((reason) => <p key={reason}>{reason}</p>)}</div>;
}

function FactRow({ fact }: { fact: RouteWorkspaceExecutionTrustFactViewModel }) {
  return <article className={`route-execution-trust__fact route-execution-trust__fact--${fact.tone}`}>
    <div className="route-execution-trust__fact-title"><strong>{fact.label}{fact.count ? ` · ${fact.count}` : ""}</strong><span>{fact.stateLabel}</span></div>
    <p>{fact.detail}</p>
    <div className="route-execution-trust__fact-meta"><span>{fact.sourceLabel}</span><span>{fact.verificationLabel}</span><span>{fact.freshnessLabel}</span></div>
  </article>;
}
