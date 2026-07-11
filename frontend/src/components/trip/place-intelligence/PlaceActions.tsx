"use client";

import type { PlaceDetailViewModel } from "./placeDetailViewModel";

export function PlaceActions({
  actions,
  onBack,
  onRemove,
  onMoveToUnplanned,
}: {
  actions: PlaceDetailViewModel["actions"];
  onBack: () => void;
  onRemove?: () => void;
  onMoveToUnplanned?: () => void;
}) {
  return (
    <footer className="place-actions">
      {actions.protectedBoundaryWarning ? <p>{actions.protectedBoundaryWarning}</p> : null}
      <div>
        <button type="button" onClick={onBack}>Back to timeline</button>
        {actions.canMoveToUnplanned && onMoveToUnplanned ? (
          <button type="button" onClick={onMoveToUnplanned}>Move out</button>
        ) : null}
        {actions.canRemove && onRemove ? (
          <button type="button" onClick={onRemove} className="is-danger">Remove</button>
        ) : null}
      </div>
      <style>{`
        .place-actions {
          position: sticky;
          bottom: 0;
          display: grid;
          gap: 8px;
          padding-top: 12px;
          background: linear-gradient(180deg, rgba(247,244,238,0), rgba(247,244,238,0.96) 30%, rgba(247,244,238,0.98));
        }
        .place-actions p {
          margin: 0;
          color: var(--ec-clay);
          font-size: 11.5px;
          line-height: 1.45;
        }
        .place-actions div {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        .place-actions button {
          border: 1px solid var(--ec-line);
          border-radius: 12px;
          padding: 9px 11px;
          background: rgba(255,253,249,0.94);
          color: var(--ec-ink-soft);
          font-size: 12px;
          font-weight: 900;
          cursor: pointer;
        }
        .place-actions button:first-child {
          border-color: transparent;
          background: var(--ec-night);
          color: #fffdf9;
        }
        .place-actions button.is-danger {
          color: var(--ec-clay);
        }
        .place-actions button:focus-visible {
          outline: none;
          box-shadow: var(--ec-focus-ring);
        }
      `}</style>
    </footer>
  );
}
