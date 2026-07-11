"use client";

import { useEffect, useRef } from "react";
import { PlaceActions } from "./PlaceActions";
import { PlaceCaveats } from "./PlaceCaveats";
import { PlaceDetailHeader } from "./PlaceDetailHeader";
import { PlaceEvidenceCard } from "./PlaceEvidenceCard";
import { PlaceTrustCard } from "./PlaceTrustCard";
import { RouteFitCard } from "./RouteFitCard";
import { VisitContextCard } from "./VisitContextCard";
import type { PlaceDetailViewModel } from "./placeDetailViewModel";

export function PlaceDetailPanel({
  viewModel,
  onBack,
  onRemove,
  onMoveToUnplanned,
}: {
  viewModel: PlaceDetailViewModel;
  onBack: () => void;
  onRemove?: () => void;
  onMoveToUnplanned?: () => void;
}) {
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    panelRef.current?.focus();
  }, [viewModel.identity.id]);

  return (
    <div
      ref={panelRef}
      tabIndex={-1}
      className="place-detail-panel"
      data-place-detail-panel="true"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          onBack();
        }
      }}
    >
      <div className="place-detail-panel__scroll">
        <PlaceDetailHeader viewModel={viewModel} onClose={onBack} />
        <PlaceTrustCard trust={viewModel.trust} />
        <RouteFitCard routeFit={viewModel.routeFit} currentName={viewModel.identity.name} />
        <VisitContextCard visitContext={viewModel.visitContext} />
        <PlaceCaveats caveats={viewModel.caveats} />
        <PlaceEvidenceCard evidence={viewModel.evidence} />
      </div>
      <PlaceActions
        actions={viewModel.actions}
        onBack={onBack}
        onRemove={onRemove}
        onMoveToUnplanned={onMoveToUnplanned}
      />
      <style>{`
        .place-detail-panel {
          min-height: 0;
          height: 100%;
          display: grid;
          grid-template-rows: minmax(0, 1fr) auto;
          gap: 10px;
          padding: 12px;
          border-radius: 22px;
          border: 1px solid var(--ec-line);
          background: linear-gradient(180deg, rgba(255,253,249,0.98), rgba(247,244,238,0.96));
          box-shadow: var(--ec-shadow-1);
        }
        .place-detail-panel:focus {
          outline: none;
        }
        .place-detail-panel:focus-visible {
          box-shadow: var(--ec-focus-ring);
        }
        .place-detail-panel__scroll {
          min-height: 0;
          overflow-y: auto;
          display: grid;
          align-content: start;
          gap: 12px;
          padding-right: 2px;
        }
      `}</style>
    </div>
  );
}
