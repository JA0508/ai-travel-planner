"use client";

import { useMemo } from "react";
import {
  getResultWorkspaceFixture,
  resultWorkspaceFixtures,
} from "@/components/trip/fixtures/resultWorkspaceFixtures";
import { TripReadinessPanel } from "@/components/trip/readiness/TripReadinessPanel";
import { buildTripReadinessViewModel } from "@/components/trip/readiness/tripReadinessModel";
import { RouteWorkspaceContainer } from "@/features/trip-workspace/RouteWorkspaceContainer";
import { useRouteWorkspaceUiState } from "@/features/trip-workspace/routeWorkspaceUiState";

export function FixtureResultWorkspace({ fixtureKey }: { fixtureKey: string }) {
  const {
    routeEditMode,
    activeRouteSheet,
    toggleRouteEditMode,
    setActiveRouteSheet,
    focusRouteDay,
    routeFocusRequest,
  } = useRouteWorkspaceUiState();
  const fixture = getResultWorkspaceFixture(fixtureKey);
  const readiness = useMemo(
    () =>
      buildTripReadinessViewModel({
        city: fixture.city,
        tripDays: fixture.tripDays,
        completion: fixture.completion,
        plannerRealism: fixture.plannerRealism,
        boundaryExplanation: fixture.boundaryExplanation,
        planningAssumptions: fixture.planningAssumptions,
        days: fixture.itinerary.days,
      }),
    [fixture],
  );

  return (
    <main className="fixture-result-page">
      <div className="fixture-result-page__switcher">
        {resultWorkspaceFixtures.map((candidate) => (
          <a
            key={candidate.key}
            href={`/fixture-result?case=${candidate.key}`}
            aria-current={candidate.key === fixture.key ? "page" : undefined}
          >
            {candidate.label}
          </a>
        ))}
      </div>
      <RouteWorkspaceContainer
        city={fixture.city}
        itinerary={{
          ...fixture.itinerary,
          trip_days: fixture.tripDays,
          planner_realism: fixture.plannerRealism,
          completion_intelligence: fixture.completion,
        }}
        editing={routeEditMode}
        onToggleEditing={toggleRouteEditMode}
        activeSheet={activeRouteSheet}
        focusRequest={routeFocusRequest}
        onSheetChange={setActiveRouteSheet}
        onFocusRouteDay={focusRouteDay}
        autoFilledCount={fixture.completion?.auto_filled_scenic_count ?? 0}
        weakestDay={
          readiness.priorityAction.kind === "focus-day"
            ? { day: readiness.priorityAction.day, reason: readiness.priorityAction.label }
            : null
        }
        intentLine={fixture.planningAssumptions.summary_lines?.[0] ?? null}
        executionLine={fixture.plannerRealism?.headline ?? null}
        initialRoutePreviewMap={fixture.routePreviewMap}
        poiDetailFixtures={fixture.poiDetailFixtures}
        sheetContent={
          <section style={{ display: "grid", gap: 10 }}>
            <strong>{fixture.label}</strong>
            <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.5 }}>
              Covers readiness, route segments, POI detail presence, caveats, and place intelligence fallback behavior.
            </p>
          </section>
        }
        commandCenter={(
          <TripReadinessPanel
            viewModel={readiness}
            onPrimaryAction={(action) => {
              if (action.kind === "focus-day") {
                setActiveRouteSheet(null);
                focusRouteDay(action.day);
                return;
              }
              if (action.kind === "review-route") {
                setActiveRouteSheet(null);
                return;
              }
              setActiveRouteSheet("completion");
            }}
          />
        )}
        completionRail={
          <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.55 }}>
            Fixture: {fixture.completion?.action_tasks?.[0]?.reason ?? "No urgent completion suggestion."}
          </p>
        }
        briefRail={
          <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.55 }}>
            {fixture.planningAssumptions.summary_lines?.[0] ?? "Fixture planning assumptions."}
          </p>
        }
        onClose={() => undefined}
      />
      <style>{`
        .fixture-result-page {
          min-height: 100dvh;
          padding: 18px;
          background: var(--ec-canvas);
        }
        .fixture-result-page__switcher {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin-bottom: 14px;
        }
        .fixture-result-page__switcher a {
          border: 1px solid var(--ec-line);
          border-radius: 12px;
          padding: 8px 10px;
          color: var(--ec-ink-soft);
          background: rgba(255,253,249,0.84);
          font-size: 12px;
          font-weight: 900;
          text-decoration: none;
        }
        .fixture-result-page__switcher a[aria-current="page"] {
          background: var(--ec-night);
          color: #fffdf9;
        }
      `}</style>
    </main>
  );
}
