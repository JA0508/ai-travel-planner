"use client";

import type { ComponentProps, ReactNode } from "react";
import { DesktopRouteLeftRail } from "@/components/trip/DesktopRouteLeftRail";
import {
  MobileEditRouteWorkspace,
  type ParsedTripIntentLike,
} from "@/components/trip/MobileEditRouteWorkspace";
import {
  RouteWorkspaceShell,
  type RouteWorkspaceSheetKey,
} from "@/components/trip/RouteWorkspaceShell";
import {
  buildRouteWorkspaceContainerViewModel,
  type RouteWorkspaceItinerary,
  type RouteWorkspaceContainerViewModelInput,
} from "./routeWorkspaceViewModel";

type MobileWorkspaceProps = ComponentProps<typeof MobileEditRouteWorkspace>;

export type RouteWorkspaceContainerProps = {
  city: string;
  itinerary: RouteWorkspaceItinerary;
  parsedIntent?: ParsedTripIntentLike | null;
  editing: boolean;
  activeSheet: RouteWorkspaceSheetKey | null;
  autoFilledCount: number;
  intentLine?: string | null;
  executionLine?: string | null;
  weakestDay?: RouteWorkspaceContainerViewModelInput["weakestDay"];
  routePreviewEndpoint?: string;
  poiDetailEndpoint?: string;
  initialRoutePreviewMap?: MobileWorkspaceProps["initialRoutePreviewMap"];
  poiDetailFixtures?: MobileWorkspaceProps["poiDetailFixtures"];
  headerUtility?: ReactNode;
  sheetContent?: ReactNode;
  commandCenter: ReactNode;
  completionRail: ReactNode;
  briefRail: ReactNode;
  onToggleEditing: () => void;
  onSheetChange: (sheet: RouteWorkspaceSheetKey | null) => void;
  onApplyEdits?: MobileWorkspaceProps["onApplyEdits"];
  onClose: () => void;
};

export function RouteWorkspaceContainer({
  city,
  itinerary,
  parsedIntent,
  editing,
  activeSheet,
  autoFilledCount,
  intentLine,
  executionLine,
  weakestDay,
  routePreviewEndpoint,
  poiDetailEndpoint,
  initialRoutePreviewMap,
  poiDetailFixtures,
  headerUtility,
  sheetContent,
  commandCenter,
  completionRail,
  briefRail,
  onToggleEditing,
  onSheetChange,
  onApplyEdits,
  onClose,
}: RouteWorkspaceContainerProps) {
  const viewModel = buildRouteWorkspaceContainerViewModel({
    city,
    itinerary,
    editing,
    activeSheet,
    autoFilledCount,
    intentLine,
    executionLine,
    weakestDay,
  });

  return (
    <RouteWorkspaceShell
      city={viewModel.shell.city}
      tripDays={viewModel.shell.tripDays}
      statusLabel={viewModel.shell.statusLabel}
      statusTone={viewModel.shell.statusTone}
      subtitle={viewModel.shell.subtitle}
      editing={editing}
      onToggleEditing={onToggleEditing}
      activeSheet={activeSheet}
      onSheetChange={onSheetChange}
      headerUtility={headerUtility}
      sheetTitle={viewModel.shell.sheetTitle}
      sheetDescription={viewModel.shell.sheetDescription}
      sheetContent={sheetContent}
    >
      <MobileEditRouteWorkspace
        mode={editing ? "edit" : "browse"}
        itinerary={itinerary}
        parsedIntent={parsedIntent}
        overview={viewModel.overview}
        routePreviewEndpoint={routePreviewEndpoint}
        poiDetailEndpoint={poiDetailEndpoint}
        initialRoutePreviewMap={initialRoutePreviewMap}
        poiDetailFixtures={poiDetailFixtures}
        desktopLeftRail={
          <DesktopRouteLeftRail
            commandCenter={commandCenter}
            completion={completionRail}
            brief={briefRail}
          />
        }
        onApplyEdits={onApplyEdits}
        onClose={onClose}
      />
    </RouteWorkspaceShell>
  );
}
