"use client";

import { useMemo, useState } from "react";
import { DesktopRouteLeftRail } from "@/components/trip/DesktopRouteLeftRail";
import { MobileEditRouteWorkspace } from "@/components/trip/MobileEditRouteWorkspace";
import { RouteWorkspaceShell, type RouteWorkspaceSheetKey } from "@/components/trip/RouteWorkspaceShell";
import {
  getResultWorkspaceFixture,
  resultWorkspaceFixtures,
} from "@/components/trip/fixtures/resultWorkspaceFixtures";
import { TripReadinessPanel } from "@/components/trip/readiness/TripReadinessPanel";
import { buildTripReadinessViewModel } from "@/components/trip/readiness/tripReadinessModel";

export function FixtureResultWorkspace({ fixtureKey }: { fixtureKey: string }) {
  const [activeSheet, setActiveSheet] = useState<RouteWorkspaceSheetKey | null>(null);
  const [editing, setEditing] = useState(false);
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
      <RouteWorkspaceShell
        city={fixture.city}
        tripDays={fixture.tripDays}
        statusLabel={readiness.statusLabel}
        statusTone={readiness.status === "ready" || readiness.status === "minor-gaps" ? "stable" : "attention"}
        subtitle="Fixture QA workspace: no backend, no provider calls, stable place intelligence scenarios."
        editing={editing}
        onToggleEditing={() => setEditing((current) => !current)}
        activeSheet={activeSheet}
        onSheetChange={setActiveSheet}
        sheetTitle="Fixture notes"
        sheetDescription="This route uses frontend fixture data only."
        sheetContent={
          <section style={{ display: "grid", gap: 10 }}>
            <strong>{fixture.label}</strong>
            <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.5 }}>
              Covers readiness, route segments, POI detail presence, caveats, and place intelligence fallback behavior.
            </p>
          </section>
        }
      >
        <MobileEditRouteWorkspace
          mode={editing ? "edit" : "browse"}
          itinerary={fixture.itinerary}
          initialRoutePreviewMap={fixture.routePreviewMap}
          poiDetailFixtures={fixture.poiDetailFixtures}
          desktopLeftRail={
            <DesktopRouteLeftRail
              commandCenter={<TripReadinessPanel viewModel={readiness} onPrimaryAction={() => setActiveSheet("completion")} />}
              completion={
                <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.55 }}>
                  Fixture: {fixture.completion?.action_tasks?.[0]?.reason ?? "No urgent completion suggestion."}
                </p>
              }
              brief={
                <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.55 }}>
                  {fixture.planningAssumptions.summary_lines?.[0] ?? "Fixture planning assumptions."}
                </p>
              }
            />
          }
          onClose={() => undefined}
        />
      </RouteWorkspaceShell>
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
