"use client";

import type { PlaceDetailViewModel } from "./placeDetailViewModel";

export function PlaceDetailHeader({
  viewModel,
  onClose,
}: {
  viewModel: PlaceDetailViewModel;
  onClose: () => void;
}) {
  return (
    <header className="place-detail-header">
      <div>
        <p>{viewModel.identity.category ?? "地点"} · Day {viewModel.schedule.dayIndex} · {viewModel.schedule.blockLabel}</p>
        <h3>{viewModel.identity.name}</h3>
        <span>
          {[viewModel.schedule.startTime && viewModel.schedule.endTime
            ? `${viewModel.schedule.startTime}-${viewModel.schedule.endTime}`
            : null, viewModel.schedule.durationLabel].filter(Boolean).join(" · ")}
        </span>
      </div>
      <button type="button" onClick={onClose}>返回</button>
      <style>{`
        .place-detail-header {
          display: flex;
          justify-content: space-between;
          gap: 12px;
          align-items: start;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--ec-line-soft);
        }
        .place-detail-header div {
          display: grid;
          gap: 6px;
          min-width: 0;
        }
        .place-detail-header p {
          margin: 0;
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 900;
          letter-spacing: 0.1em;
          text-transform: uppercase;
        }
        .place-detail-header h3 {
          margin: 0;
          color: var(--ec-ink);
          font-family: "Iowan Old Style", Georgia, "Times New Roman", serif;
          font-size: 27px;
          line-height: 1;
          letter-spacing: 0;
          text-wrap: pretty;
        }
        .place-detail-header span {
          color: var(--ec-slate);
          font-size: 13px;
          font-weight: 800;
        }
        .place-detail-header button {
          flex: 0 0 auto;
          border: 1px solid var(--ec-line);
          border-radius: 12px;
          padding: 9px 11px;
          background: rgba(255,253,249,0.92);
          color: var(--ec-ink-soft);
          font-weight: 900;
          cursor: pointer;
        }
        .place-detail-header button:focus-visible {
          outline: none;
          box-shadow: var(--ec-focus-ring);
        }
      `}</style>
    </header>
  );
}
