"use client";

import type { RoutePreviewMode } from "../RouteMapPane";

type RouteControlBarProps = {
  appearance?: "default" | "roadbook";
  compact: boolean;
  allDays: number[];
  selectedDay: number;
  visibleDays: number[];
  routeMode: RoutePreviewMode;
  routePreviewState: "idle" | "loading" | "partial" | "failed";
  selectedStopName?: string | null;
  selectedRouteContext?: string | null;
  onToggleDayVisibility: (day: number) => void;
  onShowAllDays: () => void;
  onRouteModeChange: (mode: RoutePreviewMode) => void;
  onFitRoute: () => void;
};

const ROUTE_MODE_OPTIONS: Array<{ value: RoutePreviewMode; label: string; helper: string }> = [
  { value: "walk", label: "步行", helper: "步行预览" },
  { value: "transit", label: "公交地铁", helper: "公交预览" },
  { value: "drive", label: "驾车", helper: "驾车预览" },
];

export function RouteControlBar({
  appearance = "default",
  compact,
  allDays,
  selectedDay,
  visibleDays,
  routeMode,
  routePreviewState,
  selectedStopName,
  selectedRouteContext,
  onToggleDayVisibility,
  onShowAllDays,
  onRouteModeChange,
  onFitRoute,
}: RouteControlBarProps) {
  return (
    <div className={`route-control-bar ${compact ? "is-compact" : ""} ${appearance === "roadbook" ? "is-roadbook" : ""}`}>
      <div className="route-control-bar__status">
        <span>Map reasoning</span>
        <strong>Day {selectedDay}</strong>
        <p>
          {selectedStopName
            ? `${selectedStopName}${selectedRouteContext ? ` · ${selectedRouteContext}` : ""}`
            : routePreviewStateLabel(routePreviewState)}
        </p>
      </div>

      <div className="route-control-bar__group">
        <span>交通方式</span>
        <div className="route-control-bar__segments">
          {ROUTE_MODE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => onRouteModeChange(option.value)}
              aria-pressed={routeMode === option.value}
              title={option.helper}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="route-control-bar__group">
        <span>Day 图层</span>
        <div className="route-control-bar__days">
          <button
            type="button"
            onClick={onShowAllDays}
            aria-pressed={visibleDays.length >= allDays.length}
          >
            全部
          </button>
          {allDays.map((day) => {
            const active = visibleDays.includes(day);
            const locked = day === selectedDay;
            return (
              <button
                key={day}
                type="button"
                onClick={() => onToggleDayVisibility(day)}
                disabled={locked}
                aria-pressed={active}
                title={locked ? "当前 Day 始终显示" : active ? "隐藏这一天" : "显示这一天"}
              >
                D{day}
              </button>
            );
          })}
        </div>
      </div>

      <button type="button" className="route-control-bar__fit" onClick={onFitRoute}>
        适配路线视野
      </button>

      <div className="route-control-bar__legend" aria-label="路线图图例">
        <span><i className="is-active-route" />当前路线</span>
        <span><i className="is-ghost-route" />其他 Day</span>
        <span><i className="is-origin" />起点</span>
      </div>

      <style>{`
        .route-control-bar {
          display: grid;
          grid-template-columns: minmax(130px, 0.72fr) minmax(220px, 1fr) minmax(220px, 1fr) auto;
          gap: 10px;
          align-items: end;
          padding: 10px;
          border-radius: 18px;
          border: 1px solid rgba(21,21,21,0.1);
          background: rgba(255,253,249,0.94);
          box-shadow: 0 14px 34px rgba(21,21,21,0.1);
          backdrop-filter: blur(14px);
        }

        .route-control-bar.is-compact {
          grid-template-columns: minmax(0, 1fr);
          align-items: stretch;
        }

        .route-control-bar.is-roadbook {
          border-radius: 0;
          border-color: rgba(23,22,19,.18);
          border-right: 0;
          border-bottom: 0;
          border-left: 0;
          background: rgba(250,246,240,.96);
          box-shadow: none;
          backdrop-filter: none;
        }

        .route-control-bar.is-roadbook .route-control-bar__status span,
        .route-control-bar.is-roadbook .route-control-bar__group > span {
          color: #e65a28;
        }

        .route-control-bar.is-roadbook .route-control-bar__segments {
          border-radius: 0;
          background: rgba(23,22,19,.05);
        }

        .route-control-bar.is-roadbook button {
          border-radius: 0;
        }

        .route-control-bar.is-roadbook .route-control-bar__segments button[aria-pressed="true"] {
          background: #e65a28;
        }

        .route-control-bar.is-roadbook .route-control-bar__days button[aria-pressed="true"] {
          border-bottom-color: #e65a28;
          background: transparent;
          color: #171613;
        }

        .route-control-bar.is-roadbook .route-control-bar__legend {
          display: none;
        }

        .route-control-bar.is-roadbook .route-control-bar__legend .is-active-route {
          background: #e65a28;
        }

        .route-control-bar__status,
        .route-control-bar__group {
          display: grid;
          gap: 6px;
          min-width: 0;
        }

        .route-control-bar__status span,
        .route-control-bar__group > span {
          color: var(--ec-slate);
          font-size: 10px;
          font-weight: 950;
          letter-spacing: 0.12em;
          text-transform: uppercase;
        }

        .route-control-bar__status strong {
          color: var(--ec-ink);
          font-size: 18px;
          line-height: 1;
        }

        .route-control-bar__status p {
          overflow: hidden;
          margin: 0;
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 800;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .route-control-bar__segments,
        .route-control-bar__days {
          display: grid;
          gap: 5px;
        }

        .route-control-bar__segments {
          grid-template-columns: repeat(3, minmax(0, 1fr));
          padding: 4px;
          border-radius: 14px;
          background: rgba(37,99,235,0.08);
        }

        .route-control-bar__days {
          grid-template-columns: repeat(auto-fit, minmax(48px, 1fr));
        }

        .route-control-bar button {
          min-height: 36px;
          border: 1px solid transparent;
          border-radius: 12px;
          padding: 7px 9px;
          background: rgba(21,21,21,0.05);
          color: var(--ec-ink-soft);
          font-size: 12px;
          font-weight: 900;
          cursor: pointer;
        }

        .route-control-bar__segments button[aria-pressed="true"],
        .route-control-bar__days button[aria-pressed="true"] {
          background: var(--ec-route-blue);
          color: #fffdf9;
        }

        .route-control-bar__days button:disabled {
          cursor: default;
          opacity: 0.8;
        }

        .route-control-bar__fit {
          align-self: end;
          background: var(--ec-night) !important;
          color: #fffdf9 !important;
          white-space: nowrap;
        }

        .route-control-bar__legend {
          grid-column: 1 / -1;
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          color: var(--ec-slate);
          font-size: 11px;
          font-weight: 800;
        }

        .route-control-bar__legend span {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }

        .route-control-bar__legend i {
          width: 8px;
          height: 8px;
          border-radius: 999px;
          box-shadow: 0 0 0 3px rgba(255,255,255,0.72);
        }

        .route-control-bar__legend .is-active-route {
          background: var(--ec-route-blue);
        }

        .route-control-bar__legend .is-ghost-route {
          background: #7b93ad;
        }

        .route-control-bar__legend .is-origin {
          background: var(--ec-ochre);
        }
      `}</style>
    </div>
  );
}

function routePreviewStateLabel(state: "idle" | "loading" | "partial" | "failed"): string {
  if (state === "loading") {
    return "正在刷新真实路线";
  }
  if (state === "partial") {
    return "部分路段为估算";
  }
  if (state === "failed") {
    return "真实路线暂不可用";
  }
  return "按当前方式显示路线预览";
}
