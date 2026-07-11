"use client";

import type { PlaceDetailViewModel, RouteSegmentSummary } from "./placeDetailViewModel";

export function RouteFitCard({ routeFit, currentName }: {
  routeFit: PlaceDetailViewModel["routeFit"];
  currentName: string;
}) {
  return (
    <section className="route-fit-card">
      <div className="route-fit-card__heading">
        <span>Route fit</span>
        <strong>{routeFit.spatialSummary}</strong>
      </div>
      <div className="route-fit-card__spine">
        <RouteNode label="Previous" value={routeFit.previousStop?.name ?? "当天起点"} muted={!routeFit.previousStop} />
        <RouteSegmentLine segment={routeFit.inboundSegment} />
        <RouteNode label="Current" value={currentName} active />
        <RouteSegmentLine segment={routeFit.outboundSegment} />
        <RouteNode label="Next" value={routeFit.nextStop?.name ?? "当天收口"} muted={!routeFit.nextStop} />
      </div>
      {routeFit.observations.length > 0 ? (
        <div className="route-fit-card__observations">
          {routeFit.observations.map((observation) => (
            <p key={observation.key}>
              <span>{observation.label}</span>
              {observation.detail}
            </p>
          ))}
        </div>
      ) : null}
      <style>{`
        .route-fit-card {
          display: grid;
          gap: 12px;
          padding: 13px;
          border-radius: 16px;
          border: 1px solid var(--ec-line);
          background: rgba(255,253,249,0.72);
        }
        .route-fit-card__heading {
          display: grid;
          gap: 5px;
        }
        .route-fit-card__heading span,
        .route-fit-card__node span,
        .route-fit-card__segment span,
        .route-fit-card__observations span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }
        .route-fit-card__heading strong {
          color: var(--ec-ink-soft);
          font-size: 14px;
          line-height: 1.45;
        }
        .route-fit-card__spine {
          display: grid;
          grid-template-columns: 1fr;
          gap: 7px;
          padding-left: 10px;
          border-left: 2px solid rgba(37,99,235,0.2);
        }
        .route-fit-card__node {
          display: grid;
          gap: 3px;
          padding: 8px 10px;
          border-radius: 12px;
          background: rgba(247,244,238,0.72);
          border: 1px solid var(--ec-line-soft);
        }
        .route-fit-card__node.is-active {
          border-color: rgba(37,99,235,0.26);
          background: rgba(37,99,235,0.08);
        }
        .route-fit-card__node.is-muted {
          opacity: 0.72;
        }
        .route-fit-card__node strong {
          color: var(--ec-ink);
          font-size: 13px;
          line-height: 1.25;
        }
        .route-fit-card__segment {
          color: var(--ec-slate);
          font-size: 12px;
          font-weight: 800;
          padding-left: 10px;
        }
        .route-fit-card__observations {
          display: grid;
          gap: 7px;
          padding-top: 8px;
          border-top: 1px solid var(--ec-line-soft);
        }
        .route-fit-card__observations p {
          display: grid;
          gap: 3px;
          margin: 0;
          color: var(--ec-slate);
          font-size: 12px;
          line-height: 1.45;
        }
      `}</style>
    </section>
  );
}

function RouteNode({ label, value, active = false, muted = false }: {
  label: string;
  value: string;
  active?: boolean;
  muted?: boolean;
}) {
  return (
    <div className={`route-fit-card__node ${active ? "is-active" : ""} ${muted ? "is-muted" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RouteSegmentLine({ segment }: { segment?: RouteSegmentSummary }) {
  return (
    <div className="route-fit-card__segment">
      {segment ? (
        <>
          <span>{segment.source === "provider" ? "Provider route" : segment.source === "missing" ? "Missing route" : "Route context"}</span>
          <div>
            {[segment.durationLabel, segment.distanceLabel, segment.travelModeLabel].filter(Boolean).join(" · ")}
          </div>
        </>
      ) : (
        <>
          <span>Missing route</span>
          <div>尚未获得完整路线段数据</div>
        </>
      )}
    </div>
  );
}
