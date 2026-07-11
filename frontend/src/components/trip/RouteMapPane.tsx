"use client";

import { CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import { type EditableRouteStop } from "./MobileEditRouteWorkspace";
import { RouteControlBar } from "./map/RouteControlBar";
import { AMAP_BROWSER_CONFIG } from "./tripRuntimeConfig";

type RoutePathPoint = {
  latitude: number;
  longitude: number;
};

type RouteMapPointLayer = "active" | "ghost";

type RouteMapStopPoint = {
  id: string;
  name: string;
  longitude: number;
  latitude: number;
  day: number;
  order: number;
  layer: RouteMapPointLayer;
};

type VisualRouteMapStopPoint = RouteMapStopPoint & {
  visualLongitude: number;
  visualLatitude: number;
  overlapIndex: number;
  overlapTotal: number;
};

type GhostDayPathGroup = {
  day: number;
  path: Array<[number, number]>;
};

export type RoutePreviewMode = "walk" | "transit" | "drive";

type RouteMapSegmentLike = {
  segment_key?: string;
  from_name?: string;
  to_name?: string;
  duration_s?: number;
  distance_m?: number;
  mode?: RoutePreviewMode;
  path_points?: RoutePathPoint[];
};

type RouteMapPaneProps = {
  origin: {
    name: string;
    latitude?: number | null;
    longitude?: number | null;
  };
  stops: EditableRouteStop[];
  ghostStops?: EditableRouteStop[];
  selectedStopId: string | null;
  neighborStopIds?: string[];
  highlightedRouteSegmentKeys?: string[];
  selectedRouteContext?: string | null;
  routeSegments: RouteMapSegmentLike[];
  allDays: number[];
  selectedDay: number;
  visibleDays: number[];
  routeMode: RoutePreviewMode;
  routePreviewState?: "idle" | "loading" | "partial" | "failed";
  onToggleDayVisibility: (day: number) => void;
  onShowAllDays: () => void;
  onRouteModeChange: (mode: RoutePreviewMode) => void;
  onSelectStop: (stopId: string) => void;
};

type AmapNamespace = {
  Map: new (container: HTMLElement, options: Record<string, unknown>) => AmapMap;
  Marker: new (options: Record<string, unknown>) => AmapMarker;
  Pixel: new (x: number, y: number) => unknown;
  Polyline: new (options: Record<string, unknown>) => unknown;
};

type AmapMap = {
  add: (overlays: unknown[] | unknown) => void;
  remove: (overlays: unknown[] | unknown) => void;
  setFitView: (overlays?: unknown[], immediately?: boolean, avoid?: number[]) => void;
  panTo?: (position: [number, number]) => void;
  destroy: () => void;
};

type AmapMarker = {
  on: (eventName: string, handler: () => void) => void;
};

declare global {
  interface Window {
    AMap?: AmapNamespace;
    _AMapSecurityConfig?: {
      securityJsCode: string;
    };
    __amapRouteEditorPromise?: Promise<AmapNamespace>;
  }
}

export function RouteMapPane({
  origin,
  stops,
  ghostStops = [],
  selectedStopId,
  neighborStopIds = [],
  highlightedRouteSegmentKeys = [],
  selectedRouteContext,
  routeSegments,
  allDays,
  selectedDay,
  visibleDays,
  routeMode,
  routePreviewState = "idle",
  onToggleDayVisibility,
  onShowAllDays,
  onRouteModeChange,
  onSelectStop,
}: RouteMapPaneProps) {
  const key = AMAP_BROWSER_CONFIG.webKey;
  const securityJsCode = AMAP_BROWSER_CONFIG.securityJsCode;
  const shellRef = useRef<HTMLElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<AmapMap | null>(null);
  const fitOverlaysRef = useRef<unknown[]>([]);
  const lastFitSignatureRef = useRef<string | null>(null);
  const [amap, setAmap] = useState<AmapNamespace | null>(null);
  const [compactLayout, setCompactLayout] = useState(false);
  const [state, setState] = useState<"loading" | "ready" | "missing-key" | "failed">(
    key ? "loading" : "missing-key",
  );
  const neighborStopIdSet = useMemo(() => new Set(neighborStopIds), [neighborStopIds]);
  const highlightedRouteSegmentKeySet = useMemo(
    () => new Set(highlightedRouteSegmentKeys),
    [highlightedRouteSegmentKeys],
  );

  const stopPoints = useMemo(
    () =>
      stops
        .filter(hasStopCoordinates)
        .map((stop, index) => ({
          id: stop.id,
          name: stop.item.name,
          longitude: stop.item.longitude,
          latitude: stop.item.latitude,
          day: stop.day,
          order: index + 1,
          layer: "active" as const,
        })),
    [stops],
  );
  const ghostStopPoints = useMemo(
    () =>
      ghostStops
        .filter(hasStopCoordinates)
        .filter((stop) => !stops.some((currentStop) => currentStop.id === stop.id))
        .map((stop) => ({
          id: stop.id,
          name: stop.item.name,
          longitude: stop.item.longitude,
          latitude: stop.item.latitude,
          day: stop.day,
          order: stop.originalIndex + 1,
          layer: "ghost" as const,
        })),
    [ghostStops, stops],
  );

  const visualStopPoints = useMemo(() => {
    const visualPoints = spreadOverlappingMapPoints([...ghostStopPoints, ...stopPoints]);
    return visualPoints.filter((point) => point.layer === "active");
  }, [ghostStopPoints, stopPoints]);

  const visualGhostStopPoints = useMemo(() => {
    const visualPoints = spreadOverlappingMapPoints([...ghostStopPoints, ...stopPoints]);
    return visualPoints.filter((point) => point.layer === "ghost");
  }, [ghostStopPoints, stopPoints]);

  const realPathPoints = useMemo(
    () =>
      routeSegments.flatMap((segment) =>
        (segment.path_points ?? []).map((point) => [point.longitude, point.latitude]),
      ),
    [routeSegments],
  );
  const highlightedPathGroups = useMemo(
    () =>
      routeSegments
        .filter(
          (segment) =>
            segment.segment_key &&
            highlightedRouteSegmentKeySet.has(segment.segment_key) &&
            (segment.path_points?.length ?? 0) >= 2,
        )
        .map((segment) => ({
          key: segment.segment_key ?? "",
          path: (segment.path_points ?? []).map((point) => [point.longitude, point.latitude] as [number, number]),
        })),
    [highlightedRouteSegmentKeySet, routeSegments],
  );

  const selectedFallbackPathPoints = useMemo(() => {
    const points: Array<[number, number]> = [];
    if (typeof origin.longitude === "number" && typeof origin.latitude === "number") {
      points.push([origin.longitude, origin.latitude]);
    }
    for (const stop of stopPoints) {
      points.push([stop.longitude, stop.latitude]);
    }
    return points;
  }, [origin.latitude, origin.longitude, stopPoints]);

  const activePathPoints = realPathPoints.length >= 2 ? realPathPoints : selectedFallbackPathPoints;
  const activePathIsEstimated = realPathPoints.length < 2;

  useEffect(() => {
    const node = shellRef.current;
    if (!node || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      setCompactLayout(entry.contentRect.width < 560);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const ghostDayPathGroups = useMemo<GhostDayPathGroup[]>(() => {
    const groups = new Map<number, RouteMapStopPoint[]>();
    for (const stop of ghostStopPoints) {
      const current = groups.get(stop.day) ?? [];
      current.push(stop);
      groups.set(stop.day, current);
    }

    return Array.from(groups.entries())
      .map(([day, dayStops]) => {
        const sortedStops = [...dayStops].sort((a, b) => a.order - b.order);
        const path: Array<[number, number]> = [];
        if (typeof origin.longitude === "number" && typeof origin.latitude === "number") {
          path.push([origin.longitude, origin.latitude]);
        }
        for (const stop of sortedStops) {
          path.push([stop.longitude, stop.latitude]);
        }
        return { day, path };
      })
      .filter((group) => group.path.length >= 2);
  }, [ghostStopPoints, origin.latitude, origin.longitude]);

  const selectedStopPoint = useMemo(
    () => visualStopPoints.find((point) => point.id === selectedStopId) ?? null,
    [selectedStopId, visualStopPoints],
  );
  const fitSignature = useMemo(
    () =>
      JSON.stringify({
        origin: [origin.longitude, origin.latitude],
        activePathPoints,
        activeStops: visualStopPoints.map((point) => [point.id, point.visualLongitude, point.visualLatitude]),
        ghostDays: ghostDayPathGroups.map((group) => [group.day, group.path.length]),
      }),
    [
      activePathPoints,
      ghostDayPathGroups,
      origin.latitude,
      origin.longitude,
      visualStopPoints,
    ],
  );

  useEffect(() => {
    if (!key) {
      setState("missing-key");
      return;
    }

    let cancelled = false;
    loadAmap(key, securityJsCode)
      .then((namespace) => {
        if (!cancelled) {
          setAmap(namespace);
          setState("ready");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState("failed");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [key, securityJsCode]);

  useEffect(() => {
    if (!amap || !containerRef.current) {
      return;
    }
    const map = new amap.Map(containerRef.current, {
      zoom: 12,
      resizeEnable: true,
      viewMode: "2D",
      mapStyle: "amap://styles/whitesmoke",
    });
    mapRef.current = map;
    return () => {
      map.destroy();
      mapRef.current = null;
    };
  }, [amap]);

  useEffect(() => {
    if (!amap || !mapRef.current) {
      return;
    }

    const overlays: unknown[] = [];
    const fitOverlays: unknown[] = [];
    if (typeof origin.longitude === "number" && typeof origin.latitude === "number") {
      const originMarker = new amap.Marker({
        position: [origin.longitude, origin.latitude],
        title: origin.name,
        content: buildOriginMarkerContent(),
        offset: new amap.Pixel(-14, -14),
      });
      overlays.push(originMarker);
      fitOverlays.push(originMarker);
    }

    for (const group of ghostDayPathGroups) {
      const ghostPolyline = new amap.Polyline({
        path: group.path,
        strokeColor: getGhostDayColor(group.day),
        strokeOpacity: 0.34,
        strokeWeight: 4,
        strokeStyle: "dashed",
        lineJoin: "round",
      });
      overlays.push(ghostPolyline);
      fitOverlays.push(ghostPolyline);
    }

    for (const stop of visualGhostStopPoints) {
      overlays.push(
        new amap.Marker({
          position: [stop.visualLongitude, stop.visualLatitude],
          title: stop.name,
          content: buildGhostStopMarkerContent(`D${stop.day}`, stop.overlapTotal),
          offset: new amap.Pixel(-18, -18),
        }),
      );
    }

    for (const stop of visualStopPoints) {
      const marker = new amap.Marker({
        position: [stop.visualLongitude, stop.visualLatitude],
        title: stop.name,
          content: buildStopMarkerContent({
            active: stop.id === selectedStopId,
            neighbor: neighborStopIdSet.has(stop.id),
            label: `D${stop.day}.${stop.order}`,
            overlapped: stop.overlapTotal > 1,
          }),
        offset: new amap.Pixel(-28, -18),
      });
      marker.on("click", () => onSelectStop(stop.id));
      overlays.push(marker);
      fitOverlays.push(marker);
    }

    if (activePathPoints.length >= 2) {
      const realPolyline = new amap.Polyline({
        path: activePathPoints,
        strokeColor: ROUTE_SPINE_BLUE,
        strokeOpacity: selectedStopId ? 0.36 : activePathIsEstimated ? 0.78 : 0.96,
        strokeWeight: selectedStopId ? 4 : 6,
        strokeStyle: activePathIsEstimated ? "dashed" : "solid",
        lineJoin: "round",
      });
      overlays.push(realPolyline);
      fitOverlays.push(realPolyline);
    }

    for (const group of highlightedPathGroups) {
      const highlightPolyline = new amap.Polyline({
        path: group.path,
        strokeColor: ROUTE_SPINE_BLUE,
        strokeOpacity: 0.98,
        strokeWeight: 7,
        lineJoin: "round",
      });
      overlays.push(highlightPolyline);
    }

    try {
      if (overlays.length) {
        mapRef.current.add(overlays);
      }
      fitOverlaysRef.current = fitOverlays;
      if (fitOverlays.length && lastFitSignatureRef.current !== fitSignature) {
        mapRef.current.setFitView(fitOverlays, false, [72, 48, 72, 48]);
        lastFitSignatureRef.current = fitSignature;
      }
    } catch (error) {
      console.warn("Failed to render route map overlays.", error);
    }

    return () => {
      try {
        mapRef.current?.remove(overlays);
      } catch (error) {
        console.warn("Failed to clear route map overlays.", error);
      }
    };
  }, [
    activePathIsEstimated,
    activePathPoints,
    amap,
    fitSignature,
    ghostDayPathGroups,
    highlightedPathGroups,
    neighborStopIdSet,
    onSelectStop,
    origin.latitude,
    origin.longitude,
    origin.name,
    selectedStopId,
    visualGhostStopPoints,
    visualStopPoints,
  ]);

  useEffect(() => {
    if (!selectedStopPoint || !mapRef.current?.panTo) {
      return;
    }
    try {
      mapRef.current.panTo([selectedStopPoint.visualLongitude, selectedStopPoint.visualLatitude]);
    } catch (error) {
      console.warn("Failed to focus selected route stop.", error);
    }
  }, [selectedStopPoint]);

  const handleFitRoute = () => {
    try {
      if (fitOverlaysRef.current.length) {
        mapRef.current?.setFitView(fitOverlaysRef.current, false, [72, 48, 72, 48]);
      }
    } catch (error) {
      console.warn("Failed to fit route map overlays.", error);
    }
  };

  return (
    <section ref={shellRef} data-route-map-pane="true" style={mapShellStyle(compactLayout)}>
      <div ref={containerRef} style={mapCanvasStyle} />
      {state !== "ready" ? (
        <div style={fallbackStyle}>
          <strong>{state === "loading" ? "正在加载地图" : "地图暂未启用"}</strong>
          <span>
            {state === "missing-key"
              ? "未配置 NEXT_PUBLIC_AMAP_WEB_KEY，当前仍可继续编辑路线。"
              : state === "failed"
                ? "地图加载失败，已保留路线列表与编辑能力。"
                : "正在准备当前 day 的实时路线。"}
          </span>
        </div>
      ) : null}
      {state === "ready" ? (
        <>
          <div style={mapControlDockStyle(compactLayout)}>
          <RouteControlBar
            compact={compactLayout}
            allDays={allDays}
            selectedDay={selectedDay}
            visibleDays={visibleDays}
            routeMode={routeMode}
            routePreviewState={routePreviewState}
            selectedStopName={selectedStopPoint?.name ?? null}
            selectedRouteContext={selectedRouteContext}
            onToggleDayVisibility={onToggleDayVisibility}
            onShowAllDays={onShowAllDays}
            onRouteModeChange={onRouteModeChange}
            onFitRoute={handleFitRoute}
          />
          </div>
        </>
      ) : null}
    </section>
  );
}

function loadAmap(key: string, securityJsCode?: string): Promise<AmapNamespace> {
  if (window.AMap) {
    return Promise.resolve(window.AMap);
  }
  if (window.__amapRouteEditorPromise) {
    return window.__amapRouteEditorPromise;
  }
  if (securityJsCode) {
    window._AMapSecurityConfig = {
      securityJsCode,
    };
  }
  const promise = new Promise<AmapNamespace>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
    script.async = true;
    script.onload = () => {
      if (window.AMap) {
        resolve(window.AMap);
      } else {
        window.__amapRouteEditorPromise = undefined;
        reject(new Error("AMap global missing after script load."));
      }
    };
    script.onerror = () => {
      window.__amapRouteEditorPromise = undefined;
      reject(new Error("Failed to load AMap script."));
    };
    document.head.appendChild(script);
  });
  window.__amapRouteEditorPromise = promise.catch((error) => {
    window.__amapRouteEditorPromise = undefined;
    throw error;
  });
  return window.__amapRouteEditorPromise;
}

function hasStopCoordinates(
  stop: EditableRouteStop,
): stop is EditableRouteStop & { item: { latitude: number; longitude: number } } {
  return typeof stop.item.latitude === "number" && typeof stop.item.longitude === "number";
}

function spreadOverlappingMapPoints(points: RouteMapStopPoint[]): VisualRouteMapStopPoint[] {
  const groups: RouteMapStopPoint[][] = [];
  for (const point of points) {
    // Group close city-center stops so marker labels fan out without changing route math.
    const nearbyGroup = groups.find((group) => {
      const center = getPointGroupCenter(group);
      return distanceMeters(center, point) < 680;
    });
    if (nearbyGroup) {
      nearbyGroup.push(point);
    } else {
      groups.push([point]);
    }
  }

  return groups.flatMap((group) => {
    if (group.length === 1) {
      const [point] = group;
      return [
        {
          ...point,
          visualLatitude: point.latitude,
          visualLongitude: point.longitude,
          overlapIndex: 0,
          overlapTotal: 1,
        },
      ];
    }

    const sortedGroup = [...group].sort((a, b) => a.day - b.day || a.order - b.order);
    const radius = Math.min(0.0032, 0.0011 + sortedGroup.length * 0.00022);
    return group.map((point, index) => {
      const visualIndex = sortedGroup.findIndex((candidate) => candidate.id === point.id);
      const angle = -Math.PI / 2 + (Math.PI * 2 * visualIndex) / sortedGroup.length;
      const latitudeRadians = (point.latitude * Math.PI) / 180;
      const longitudeFactor = Math.max(Math.cos(latitudeRadians), 0.35);
      return {
        ...point,
        visualLatitude: point.latitude + Math.sin(angle) * radius,
        visualLongitude: point.longitude + (Math.cos(angle) * radius) / longitudeFactor,
        overlapIndex: index,
        overlapTotal: group.length,
      };
    });
  });
}

function getPointGroupCenter(group: RouteMapStopPoint[]): Pick<RouteMapStopPoint, "latitude" | "longitude"> {
  const total = group.reduce(
    (current, point) => ({
      latitude: current.latitude + point.latitude,
      longitude: current.longitude + point.longitude,
    }),
    { latitude: 0, longitude: 0 },
  );
  return {
    latitude: total.latitude / group.length,
    longitude: total.longitude / group.length,
  };
}

function distanceMeters(
  from: Pick<RouteMapStopPoint, "latitude" | "longitude">,
  to: Pick<RouteMapStopPoint, "latitude" | "longitude">,
): number {
  const latitudeMeters = (to.latitude - from.latitude) * 111_320;
  const longitudeMeters =
    (to.longitude - from.longitude) *
    111_320 *
    Math.max(Math.cos(((from.latitude + to.latitude) / 2) * (Math.PI / 180)), 0.35);
  return Math.hypot(latitudeMeters, longitudeMeters);
}

function buildStopMarkerContent({
  active,
  neighbor,
  label,
  overlapped,
}: {
  active: boolean;
  neighbor: boolean;
  label: string;
  overlapped: boolean;
}): string {
  const background = active ? ROUTE_SPINE_BLUE : neighbor ? "#b18a58" : "#5f7895";
  const width = active ? 62 : neighbor ? 54 : 50;
  return `<div style="
    min-width:${width}px;
    height:36px;
    padding:0 10px;
    border-radius:999px;
    display:flex;
    align-items:center;
    justify-content:center;
    border:3px solid white;
    background:${background};
    color:white;
    font:800 12px/1 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    letter-spacing:.03em;
    box-shadow:0 ${active ? 12 : 8}px ${active ? 24 : 18}px rgba(37,99,235,.24);
    outline:${active ? "3px solid rgba(37,99,235,.22)" : neighbor ? "2px solid rgba(177,138,88,.34)" : overlapped ? "2px solid rgba(177,138,88,.48)" : "none"};
  ">${label}</div>`;
}

function buildGhostStopMarkerContent(label: string, overlapTotal: number): string {
  return `<div style="
    width:36px;
    height:36px;
    border-radius:999px;
    display:flex;
    align-items:center;
    justify-content:center;
    background:rgba(255,253,249,0.78);
    color:#5f7895;
    border:2px solid rgba(95,120,149,0.52);
    font:800 11px/1 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    box-shadow:0 4px 12px rgba(21,21,21,0.12);
    outline:${overlapTotal > 1 ? "2px solid rgba(177,138,88,.28)" : "none"};
  ">${label}</div>`;
}

function buildOriginMarkerContent(): string {
  return `<div style="
    width:32px;
    height:32px;
    border-radius:999px;
    display:flex;
    align-items:center;
    justify-content:center;
    border:3px solid white;
    background:#b18a58;
    color:white;
    font:900 12px/1 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    box-shadow:0 8px 18px rgba(21,21,21,.22);
  ">起</div>`;
}

function getGhostDayColor(day: number): string {
  const colors = [GHOST_ROUTE_BLUE, "#7f9bb9", "#9aacc0", "#8ca4b8"];
  return colors[Math.abs(day - 1) % colors.length] ?? GHOST_ROUTE_BLUE;
}

const ROUTE_SPINE_BLUE = "#2563eb";
const GHOST_ROUTE_BLUE = "#7b93ad";

function mapShellStyle(compact: boolean): CSSProperties {
  return {
    position: "absolute",
    inset: 0,
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr)",
    gridTemplateRows: compact ? "minmax(196px, 1fr) auto auto" : "minmax(220px, 1fr) auto auto",
    gap: compact ? 10 : 10,
    padding: compact ? 12 : 12,
    overflow: "hidden",
    background:
      "radial-gradient(circle at 16% 12%, rgba(37,99,235,0.12), transparent 26%), radial-gradient(circle at 86% 8%, rgba(177,138,88,0.12), transparent 22%), linear-gradient(180deg, rgba(239,244,241,0.98), rgba(231,236,232,0.96))",
  };
}

const mapCanvasStyle: CSSProperties = {
  position: "relative",
  minWidth: 0,
  minHeight: 0,
  width: "100%",
  height: "100%",
  overflow: "hidden",
  borderRadius: 26,
  border: "1px solid rgba(37,99,235,0.10)",
  boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.56)",
};

function mapControlDockStyle(compact: boolean): CSSProperties {
  return {
    position: "relative",
    zIndex: 2,
    alignSelf: "stretch",
    minWidth: 0,
    overflow: "visible",
  };
}

const fallbackStyle: CSSProperties = {
  position: "absolute",
  top: 16,
  right: 16,
  left: 16,
  display: "grid",
  gap: 4,
  padding: "12px 14px",
  borderRadius: 18,
  background: "rgba(255,255,255,0.84)",
  boxShadow: "0 16px 34px rgba(15,23,42,0.08)",
  color: "#475569",
  backdropFilter: "blur(14px)",
};
