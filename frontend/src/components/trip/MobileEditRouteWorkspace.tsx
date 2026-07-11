"use client";

import { CSSProperties, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  RouteEditorSheet,
  type RouteEditorSheetSnap,
} from "./RouteEditorSheet";
import { RouteMapPane, type RoutePreviewMode } from "./RouteMapPane";
import { postTripJson } from "./tripApiClient";

type TimelineItemType = "scenic" | "restaurant" | "hotel";
type TimelineBlockType = "morning" | "afternoon" | "evening";

type CompletionCandidateTraceLike = {
  name: string;
  reason: string;
};

type ScheduledItemLike = {
  name: string;
  type: TimelineItemType;
  city?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  start_time: string;
  end_time: string;
  is_fixed: boolean;
  placement_reason: string | null;
  source_type?: "user_seed" | "user_fixed" | "auto_seeded_poi" | "auto_seeded_meal" | "auto_filled";
  source_label?: string | null;
  source_reason?: string | null;
  travel_from_name: string | null;
  travel_distance_m: number | null;
  travel_duration_s: number | null;
  poi_research?: POIResearchSummaryLike | null;
  selection_top_candidates?: CompletionCandidateTraceLike[];
  selection_rejected_candidates?: CompletionCandidateTraceLike[];
  local_edit?: {
    previous_name: string;
    source: "completion_recommendation";
    status: "committed";
    reasoning_summary: string;
    itinerary_relation_summary: string;
    original_type: TimelineItemType;
  } | null;
};

type POIResearchSummaryLike = {
  overview: string;
  access_tip: string;
  practical_tip: string;
  best_for: string;
  source: string;
};

type DayBlockLike = {
  block_type: TimelineBlockType;
  start_time: string;
  end_time: string;
  items: ScheduledItemLike[];
};

type DayItineraryLike = {
  day: number;
  blocks: DayBlockLike[];
};

export type ItineraryLike = {
  planning_anchor_source: {
    source_type: string;
    source_name: string;
    latitude?: number | null;
    longitude?: number | null;
  };
  days: DayItineraryLike[];
};

type PlaceDisambiguationResolutionLike = {
  input_name: string;
  resolved_name: string;
  poi_type: string;
  city: string | null;
  confidence: string;
  source: string;
  reason: string;
  candidate_names: string[];
};

export type ParsedTripIntentLike = {
  disambiguation_summary?: {
    place_resolutions: PlaceDisambiguationResolutionLike[];
  } | null;
};

export type EditableRouteStop = {
  id: string;
  day: number;
  originalDay: number;
  originalIndex: number;
  originalIsFixed: boolean;
  blockType: TimelineBlockType;
  originalBlockType: TimelineBlockType;
  item: ScheduledItemLike;
};

export type EditableRouteDay = {
  day: number;
  label: string;
  originalStopCount: number;
  stops: EditableRouteStop[];
};

type MobileEditRouteWorkspaceProps = {
  itinerary: ItineraryLike;
  parsedIntent?: ParsedTripIntentLike | null;
  overview?: RouteWorkspaceOverview | null;
  mode?: "browse" | "edit";
  routePreviewEndpoint?: string;
  poiDetailEndpoint?: string;
  desktopLeftRail?: ReactNode;
  onApplyEdits?: (
    days: EditableRouteDay[],
    routePreviewMap?: RoutePreviewMap,
    unplannedStops?: EditableRouteStop[],
  ) => void;
  onClose: () => void;
};

export type RouteWorkspaceOverview = {
  completeness?: number | null;
  pendingTaskCount?: number | null;
  autoFilledCount?: number | null;
  stayAreaLabel?: string | null;
  departureLabel?: string | null;
  realismHeadline?: string | null;
  realismStatus?: "executable" | "needs_repair" | "unstable" | string | null;
  intentLine?: string | null;
  executionLine?: string | null;
  weakestDay?: {
    day: number;
    reason: string;
  } | null;
};

type DraggingStopMeta = {
  stopId: string;
  day: number;
  blockType: TimelineBlockType;
};

type RouteWorkspaceSnapshot = {
  days: EditableRouteDay[];
  unplannedStops: EditableRouteStop[];
};

type RightPanelMode =
  | { type: "timeline"; dayIndex: number }
  | { type: "place-detail"; dayIndex: number; stopId: string };

type PoiDetailCardViewModel = {
  title: string;
  subtitle: string;
  typeLabel: string;
  heroInitial: string;
  heroImageUrl: string | null;
  trustChips: string[];
  routeLine: string;
  liveFacts: PoiLiveFactsViewModel | null;
  introduction: string;
  research: PoiResearchCardViewModel;
  fitBullets: string[];
  cautionBullets: string[];
};

type PoiResearchCardViewModel = {
  sourceLabel: string;
  overview: string;
  accessTip: string;
  practicalTip: string;
  bestFor: string;
};

type PoiLiveFactsViewModel = {
  sourceLabel: string;
  facts: Array<{
    label: string;
    value: string;
  }>;
};

type RouteSegmentViewModel = {
  label: string;
  status: "confirmed" | "previewed" | "estimated" | "pending";
};

type RouteSegmentPreviewInput = {
  segment_key: string;
  mode: RoutePreviewMode;
  from_name: string;
  from_latitude: number;
  from_longitude: number;
  from_city?: string | null;
  to_name: string;
  to_latitude: number;
  to_longitude: number;
  to_city?: string | null;
};

type RouteSegmentPreviewResult = {
  segment_key: string;
  from_name: string;
  to_name: string;
  distance_m: number;
  duration_s: number;
  source: string;
  mode?: RoutePreviewMode;
  path_points?: Array<{
    latitude: number;
    longitude: number;
  }>;
};

export type RoutePreviewMap = Record<string, RouteSegmentPreviewResult>;

type POIDetailPreview = {
  found: boolean;
  name: string;
  address: string | null;
  category: string | null;
  business_area: string | null;
  rating: string | null;
  cost: string | null;
  tel: string | null;
  website: string | null;
  open_time: string | null;
  photo_url: string | null;
  latitude: number | null;
  longitude: number | null;
  source: string;
  failure_reason: string | null;
};

const BLOCK_ORDER: TimelineBlockType[] = ["morning", "afternoon", "evening"];
const POI_DETAIL_CACHE_TTL_MS = 15 * 60 * 1000;
const poiDetailPreviewCache = new Map<
  string,
  {
    expiresAt: number;
    value: POIDetailPreview;
  }
>();

export function useEditableRouteWorkspaceState({
  itinerary,
  routePreviewEndpoint,
}: {
  itinerary: ItineraryLike;
  routePreviewEndpoint?: string;
}) {
  const [editableDays, setEditableDays] = useState<EditableRouteDay[]>(() =>
    buildEditableRouteDays(itinerary),
  );
  const [selectedDay, setSelectedDay] = useState<number>(itinerary.days[0]?.day ?? 1);
  const [draggingStop, setDraggingStop] = useState<DraggingStopMeta | null>(null);
  const [pendingStopName, setPendingStopName] = useState("");
  const [pendingStopType, setPendingStopType] = useState<TimelineItemType>("scenic");
  const [pendingStopBlock, setPendingStopBlock] = useState<TimelineBlockType>("afternoon");
  const [unplannedStops, setUnplannedStops] = useState<EditableRouteStop[]>([]);
  const [showUnplanned, setShowUnplanned] = useState(false);
  const [routeMode, setRouteMode] = useState<RoutePreviewMode>("walk");
  const [visibleMapDays, setVisibleMapDays] = useState<number[]>(() =>
    itinerary.days.map((day) => day.day),
  );
  const [undoStack, setUndoStack] = useState<RouteWorkspaceSnapshot[]>([]);
  const [redoStack, setRedoStack] = useState<RouteWorkspaceSnapshot[]>([]);
  const [routePreviewMap, setRoutePreviewMap] = useState<RoutePreviewMap>({});
  const [routePreviewState, setRoutePreviewState] = useState<
    "idle" | "loading" | "partial" | "failed"
  >("idle");
  const [rightPanelMode, setRightPanelMode] = useState<RightPanelMode>(() => ({
    type: "timeline",
    dayIndex: itinerary.days[0]?.day ?? 1,
  }));
  const activeStopId = rightPanelMode.type === "place-detail" ? rightPanelMode.stopId : null;
  const setActiveStopId = (
    nextStopIdOrUpdater: string | null | ((currentStopId: string | null) => string | null),
  ) => {
    setRightPanelMode((currentMode) => {
      const currentStopId = currentMode.type === "place-detail" ? currentMode.stopId : null;
      const nextStopId =
        typeof nextStopIdOrUpdater === "function"
          ? nextStopIdOrUpdater(currentStopId)
          : nextStopIdOrUpdater;
      if (!nextStopId) {
        return { type: "timeline", dayIndex: selectedDay };
      }
      const nextStop = findActiveStop(editableDays, nextStopId);
      return {
        type: "place-detail",
        dayIndex: nextStop?.day ?? selectedDay,
        stopId: nextStopId,
      };
    });
  };

  useEffect(() => {
    const nextDays = buildEditableRouteDays(itinerary);
    setEditableDays(nextDays);
    setSelectedDay((current) =>
      nextDays.some((day) => day.day === current) ? current : nextDays[0]?.day ?? 1,
    );
    setDraggingStop(null);
    setRightPanelMode({ type: "timeline", dayIndex: nextDays[0]?.day ?? 1 });
    setRoutePreviewMap({});
    setRoutePreviewState("idle");
    setVisibleMapDays(nextDays.map((day) => day.day));
    setUnplannedStops([]);
    setShowUnplanned(false);
    setUndoStack([]);
    setRedoStack([]);
  }, [itinerary]);

  useEffect(() => {
    if (!routePreviewEndpoint) {
      return;
    }

    const segments = buildRoutePreviewInputs(
      editableDays,
      itinerary.planning_anchor_source,
      routeMode,
    );
    if (segments.length === 0) {
      setRoutePreviewState("idle");
      return;
    }

    const controller = new AbortController();
    setRoutePreviewState("loading");
    setRoutePreviewMap({});

    postTripJson<{
      segments?: RouteSegmentPreviewResult[];
      failed_segments?: Array<{ segment_key: string }>;
    }>(
      routePreviewEndpoint,
      { segments },
      "Route preview failed.",
      "Route preview failed.",
      { signal: controller.signal },
    )
      .then((result) => {
        if (!result.ok) {
          if (!result.aborted) {
            setRoutePreviewState("failed");
          }
          return;
        }
        const payload = result.data;
        setRoutePreviewMap((current) => {
          const next = { ...current };
          for (const segment of payload.segments ?? []) {
            next[segment.segment_key] = segment;
          }
          return next;
        });
        setRoutePreviewState(payload.failed_segments?.length ? "partial" : "idle");
      });

    return () => controller.abort();
  }, [editableDays, itinerary.planning_anchor_source, routeMode, routePreviewEndpoint]);

  const selectedDayView =
    editableDays.find((day) => day.day === selectedDay) ?? editableDays[0] ?? null;
  const activeStop = findActiveStop(editableDays, activeStopId);
  const mapOrigin = buildOriginForDay(editableDays, selectedDay, itinerary.planning_anchor_source);
  const visibleDayNumbers = useMemo(() => {
    const visibleSet = new Set(visibleMapDays);
    visibleSet.add(selectedDay);
    return editableDays.map((day) => day.day).filter((day) => visibleSet.has(day));
  }, [editableDays, selectedDay, visibleMapDays]);
  const selectedDaySegments = selectedDayView
    ? collectDayRouteSegments(selectedDayView, routePreviewMap)
    : [];
  const canUndo = undoStack.length > 0;
  const canRedo = redoStack.length > 0;

  const commitRouteEdit = (
    nextDays: EditableRouteDay[],
    nextUnplannedStops: EditableRouteStop[] = unplannedStops,
  ) => {
    if (
      sameReferenceList(nextDays, editableDays) &&
      sameReferenceList(nextUnplannedStops, unplannedStops)
    ) {
      return;
    }
    setUndoStack((current) => [
      ...current.slice(-19),
      {
        days: editableDays,
        unplannedStops,
      },
    ]);
    setRedoStack([]);
    setEditableDays(nextDays);
    setUnplannedStops(nextUnplannedStops);
  };

  const handleUndoRouteEdit = () => {
    const previous = undoStack.at(-1);
    if (!previous) {
      return;
    }
    setUndoStack((current) => current.slice(0, -1));
    setRedoStack((current) => [
      ...current.slice(-19),
      {
        days: editableDays,
        unplannedStops,
      },
    ]);
    setEditableDays(previous.days);
    setUnplannedStops(previous.unplannedStops);
    setActiveStopId(null);
  };

  const handleRedoRouteEdit = () => {
    const next = redoStack.at(-1);
    if (!next) {
      return;
    }
    setRedoStack((current) => current.slice(0, -1));
    setUndoStack((current) => [
      ...current.slice(-19),
      {
        days: editableDays,
        unplannedStops,
      },
    ]);
    setEditableDays(next.days);
    setUnplannedStops(next.unplannedStops);
    setActiveStopId(null);
  };

  const handleMoveWithinDay = (dayNumber: number, fromId: string, toId: string) => {
    if (fromId === toId) {
      return;
    }
    const nextDays = editableDays.map((day) => {
        if (day.day !== dayNumber) {
          return day;
        }
        const nextStops = reorderStops(day.stops, fromId, toId);
        return nextStops === day.stops ? day : { ...day, stops: nextStops };
      });
    commitRouteEdit(nextDays);
  };

  const handleMoveByOffset = (dayNumber: number, stopId: string, offset: -1 | 1) => {
    const nextDays = editableDays.map((day) => {
        if (day.day !== dayNumber) {
          return day;
        }
        const index = day.stops.findIndex((stop) => stop.id === stopId);
        const nextIndex = index + offset;
        if (index < 0 || nextIndex < 0 || nextIndex >= day.stops.length) {
          return day;
        }
        const nextStops = [...day.stops];
        const [moved] = nextStops.splice(index, 1);
        nextStops.splice(nextIndex, 0, moved);
        return { ...day, stops: nextStops };
      });
    commitRouteEdit(nextDays);
  };

  const handleMoveAcrossTimeline = (
    stopId: string,
    targetDay: number,
    targetBlockType: TimelineBlockType,
  ) => {
    commitRouteEdit(moveStopAcrossTimeline(editableDays, stopId, targetDay, targetBlockType));
    setSelectedDay(targetDay);
  };

  const handleMoveAcrossTimelineBeforeStop = (
    stopId: string,
    targetDay: number,
    targetBlockType: TimelineBlockType,
    beforeStopId: string,
  ) => {
    const movedDays = moveStopAcrossTimeline(editableDays, stopId, targetDay, targetBlockType);
    const reorderedDays = movedDays.map((day) => {
      if (day.day !== targetDay) {
        return day;
      }
      return {
        ...day,
        stops: reorderStops(day.stops, stopId, beforeStopId),
      };
    });
    commitRouteEdit(reorderedDays);
    setSelectedDay(targetDay);
  };

  const handleInsertPendingStop = () => {
    const trimmedName = pendingStopName.trim();
    if (!trimmedName || !selectedDayView) {
      return;
    }
    commitRouteEdit(
      insertPendingStop(editableDays, selectedDayView.day, pendingStopBlock, trimmedName, pendingStopType),
    );
    setPendingStopName("");
  };

  const handleAddPendingStopToUnplanned = () => {
    const trimmedName = pendingStopName.trim();
    if (!trimmedName) {
      return;
    }
    commitRouteEdit(editableDays, [
      ...unplannedStops,
      buildManualPendingStop(0, pendingStopBlock, trimmedName, pendingStopType),
    ]);
    setPendingStopName("");
    setShowUnplanned(true);
  };

  const handleDeleteStop = (stopId: string) => {
    commitRouteEdit(
      editableDays.map((day) => ({
        ...day,
        stops: day.stops.filter((stop) => stop.id !== stopId),
      })),
    );
    setActiveStopId((current) => (current === stopId ? null : current));
  };

  const handleToggleLockStop = (stopId: string) => {
    commitRouteEdit(
      editableDays.map((day) => ({
        ...day,
        stops: day.stops.map((stop) => (stop.id === stopId ? toggleRouteStopLock(stop) : stop)),
      })),
    );
  };

  const handleMoveToUnplanned = (stopId: string) => {
    const movedStop = findActiveStop(editableDays, stopId);
    if (!movedStop || movedStop.item.is_fixed) {
      return;
    }
    commitRouteEdit(
      editableDays.map((day) => ({
        ...day,
        stops: day.stops.filter((candidate) => candidate.id !== stopId),
      })),
      [...unplannedStops, { ...movedStop, day: 0 }],
    );
    setActiveStopId(null);
    setShowUnplanned(true);
  };

  const handlePlaceUnplannedStop = (
    stopId: string,
    targetDay: number,
    targetBlockType: TimelineBlockType,
  ) => {
    const stop = unplannedStops.find((candidate) => candidate.id === stopId);
    if (!stop) {
      return;
    }
    commitRouteEdit(
      insertExistingStop(editableDays, {
        ...stop,
        day: targetDay,
        blockType: targetBlockType,
      }),
      unplannedStops.filter((candidate) => candidate.id !== stopId),
    );
    setSelectedDay(targetDay);
    setShowUnplanned(false);
  };

  const handleDeleteUnplannedStop = (stopId: string) => {
    commitRouteEdit(
      editableDays,
      unplannedStops.filter((candidate) => candidate.id !== stopId),
    );
  };

  return {
    editableDays,
    selectedDay,
    setSelectedDay,
    draggingStop,
    setDraggingStop,
    activeStopId,
    setActiveStopId,
    rightPanelMode,
    pendingStopName,
    setPendingStopName,
    pendingStopType,
    setPendingStopType,
    pendingStopBlock,
    setPendingStopBlock,
    unplannedStops,
    showUnplanned,
    setShowUnplanned,
    routePreviewMap,
    routePreviewState,
    routeMode,
    visibleMapDays: visibleDayNumbers,
    selectedDayView,
    activeStop,
    mapOrigin,
    selectedDaySegments,
    canUndo,
    canRedo,
    handleMoveWithinDay,
    handleMoveByOffset,
    handleMoveAcrossTimeline,
    handleMoveAcrossTimelineBeforeStop,
    handleInsertPendingStop,
    handleAddPendingStopToUnplanned,
    handleDeleteStop,
    handleToggleLockStop,
    handleMoveToUnplanned,
    handlePlaceUnplannedStop,
    handleDeleteUnplannedStop,
    handleUndoRouteEdit,
    handleRedoRouteEdit,
    handleRouteModeChange: setRouteMode,
    handleToggleMapDayVisibility: (dayNumber: number) => {
      if (dayNumber === selectedDay) {
        return;
      }
      setVisibleMapDays((current) => {
        const daySet = new Set(current);
        if (daySet.has(dayNumber)) {
          daySet.delete(dayNumber);
        } else {
          daySet.add(dayNumber);
        }
        daySet.add(selectedDay);
        return editableDays
          .map((day) => day.day)
          .filter((day) => daySet.has(day));
      });
    },
    handleShowAllMapDays: () => {
      setVisibleMapDays(editableDays.map((day) => day.day));
    },
  };
}

export type EditableRouteWorkspaceState = ReturnType<typeof useEditableRouteWorkspaceState>;

export function MobileEditRouteWorkspace({
  itinerary,
  parsedIntent,
  overview,
  mode = "edit",
  routePreviewEndpoint,
  poiDetailEndpoint,
  desktopLeftRail,
  onApplyEdits,
  onClose,
}: MobileEditRouteWorkspaceProps) {
  const editing = mode === "edit";
  const workspace = useEditableRouteWorkspaceState({ itinerary, routePreviewEndpoint });
  const [sheetSnap, setSheetSnap] = useState<RouteEditorSheetSnap>(68);
  const [showOverview, setShowOverview] = useState(false);
  useEffect(() => {
    setSheetSnap(68);
    setShowOverview(false);
  }, [itinerary]);

  const {
    editableDays,
    selectedDay,
    setSelectedDay,
    draggingStop,
    setDraggingStop,
    activeStopId,
    setActiveStopId,
    rightPanelMode,
    pendingStopName,
    setPendingStopName,
    pendingStopType,
    setPendingStopType,
    pendingStopBlock,
    setPendingStopBlock,
    unplannedStops,
    showUnplanned,
    setShowUnplanned,
    routePreviewMap,
    routePreviewState,
    routeMode,
    visibleMapDays,
    selectedDayView,
    activeStop,
    mapOrigin,
    selectedDaySegments,
    handleMoveWithinDay,
    handleMoveByOffset,
    handleMoveAcrossTimeline,
    handleMoveAcrossTimelineBeforeStop,
    handleInsertPendingStop,
    handleAddPendingStopToUnplanned,
    handleDeleteStop,
    handleToggleLockStop,
    handleMoveToUnplanned,
    handlePlaceUnplannedStop,
    handleDeleteUnplannedStop,
    canUndo,
    canRedo,
    handleUndoRouteEdit,
    handleRedoRouteEdit,
    handleRouteModeChange,
    handleToggleMapDayVisibility,
    handleShowAllMapDays,
  } = workspace;
  const [isPanelLayout, setIsPanelLayout] = useState(false);
  const workspaceRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(min-width: 1120px)");
    const sync = () => setIsPanelLayout(mediaQuery.matches);
    sync();
    mediaQuery.addEventListener("change", sync);
    return () => mediaQuery.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (!isPanelLayout || !activeStopId || typeof window === "undefined") {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      const target = workspaceRef.current;
      if (!target) {
        return;
      }
      const rect = target.getBoundingClientRect();
      if (rect.top < 18 || rect.top > 140) {
        window.scrollTo({
          top: Math.max(0, window.scrollY + rect.top - 28),
          behavior: "smooth",
        });
      }
    });

    return () => window.cancelAnimationFrame(frame);
  }, [activeStopId, isPanelLayout]);

  return (
    <section ref={workspaceRef} className="editable-route-workspace" style={workspaceShellStyle}>
      <aside className="editable-route-workspace__left">
        {desktopLeftRail}
        <UnplannedStopPool
          stops={unplannedStops}
          days={editableDays}
          selectedDay={selectedDay}
          editing={editing}
          onPlaceStop={handlePlaceUnplannedStop}
          onDeleteStop={handleDeleteUnplannedStop}
        />
      </aside>

      <aside className="editable-route-workspace__right">
        <div className="editable-route-workspace__map">
          <RouteMapPane
            origin={mapOrigin}
            stops={selectedDayView?.stops ?? []}
            ghostStops={editableDays
              .filter((day) => day.day !== selectedDay)
              .filter((day) => visibleMapDays.includes(day.day))
              .flatMap((day) => day.stops)}
            selectedStopId={activeStopId}
            routeSegments={selectedDaySegments}
            allDays={editableDays.map((day) => day.day)}
            selectedDay={selectedDay}
            visibleDays={visibleMapDays}
            routeMode={routeMode}
            routePreviewState={routePreviewState}
            onToggleDayVisibility={handleToggleMapDayVisibility}
            onShowAllDays={handleShowAllMapDays}
            onRouteModeChange={handleRouteModeChange}
            onSelectStop={(stopId) => {
              setActiveStopId(stopId);
              setSheetSnap(96);
            }}
          />
        </div>
      </aside>

      <RouteEditorSheet
        className="editable-route-workspace__center"
        snap={sheetSnap}
        onSnapChange={setSheetSnap}
      >
      {isPanelLayout && rightPanelMode.type === "place-detail" && activeStop ? (
        <StopDetailDrawer
          variant="panel"
          stop={activeStop}
          allDays={editableDays}
          parsedIntent={parsedIntent}
          originLabel={originLabelForDay(
            editableDays,
            activeStop.day,
            itinerary.planning_anchor_source.source_name,
          )}
          poiDetailEndpoint={poiDetailEndpoint}
          editing={editing}
          onClose={() => setActiveStopId(null)}
          onMoveStop={handleMoveAcrossTimeline}
          onDeleteStop={handleDeleteStop}
          onToggleLockStop={handleToggleLockStop}
          onMoveToUnplanned={handleMoveToUnplanned}
        />
      ) : (
      <>
      {editing ? (
        <div style={workspaceHeaderStyle}>
          <div style={{ display: "grid", gap: 5 }}>
            <p style={workspaceEyebrowStyle}>路线编辑</p>
            <h4 style={workspaceTitleStyle}>编辑路线</h4>
            <p style={workspaceSubtitleStyle}>
              可以拖动、跨天调整、锁定或先放进待规划。保存后，这版路线会成为后续继续生成的当前基线。
            </p>
            <div style={routeEditToolbarStyle}>
              <button
                type="button"
                onClick={handleUndoRouteEdit}
                disabled={!canUndo}
                className="ec-interactive-pill"
                style={{
                  ...routeToolbarButtonStyle,
                  opacity: canUndo ? 1 : 0.45,
                }}
              >
                撤销
              </button>
              <button
                type="button"
                onClick={handleRedoRouteEdit}
                disabled={!canRedo}
                className="ec-interactive-pill"
                style={{
                  ...routeToolbarButtonStyle,
                  opacity: canRedo ? 1 : 0.45,
                }}
              >
                重做
              </button>
              <span style={routeToolbarHintStyle}>
                {canUndo ? "本地编辑已记录，可随时回退。" : "还没有本地编辑。"}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              onApplyEdits?.(editableDays, routePreviewMap, unplannedStops);
              onClose();
            }}
            className="ec-interactive-pill"
            style={doneButtonStyle}
          >
            保存并返回
          </button>
        </div>
      ) : null}

      <div style={dayTabsWrapStyle}>
        <button
          type="button"
          onClick={() => {
            setShowOverview(true);
            setShowUnplanned(false);
          }}
          className="ec-interactive-pill"
          style={buildDayTabStyle(showOverview)}
        >
          总览
        </button>
        {editableDays.map((day) => {
          const active = !showOverview && !showUnplanned && day.day === selectedDay;
          return (
            <button
              key={`edit-day-tab-${day.day}`}
              type="button"
              onClick={() => {
                setSelectedDay(day.day);
                setShowUnplanned(false);
                setShowOverview(false);
              }}
              onDragOver={(event) => {
                if (!editing) {
                  return;
                }
                if (!draggingStop || draggingStop.stopId === activeStopId) {
                  event.preventDefault();
                  return;
                }
                event.preventDefault();
              }}
              onDrop={(event) => {
                if (!editing) {
                  return;
                }
                if (!draggingStop) {
                  return;
                }
                event.preventDefault();
                handleMoveAcrossTimeline(draggingStop.stopId, day.day, draggingStop.blockType);
                setDraggingStop(null);
              }}
              className="ec-interactive-pill"
              style={{
                ...buildDayTabStyle(active),
                border:
                  draggingStop && day.day !== draggingStop.day
                    ? "1px dashed rgba(177, 138, 88, 0.34)"
                    : "1px solid transparent",
              }}
            >
              {day.label}
            </button>
          );
        })}
        <button
          type="button"
          onClick={() => {
            setShowUnplanned(true);
            setShowOverview(false);
          }}
          className="ec-interactive-pill"
          style={buildDayTabStyle(showUnplanned)}
        >
          待规划 {unplannedStops.length > 0 ? `(${unplannedStops.length})` : ""}
        </button>
      </div>

      {!isPanelLayout ? (
        <MobileMapLayerPanel
          allDays={editableDays.map((day) => day.day)}
          selectedDay={selectedDay}
          visibleDays={visibleMapDays}
          routeMode={routeMode}
          routePreviewState={routePreviewState}
          onRouteModeChange={handleRouteModeChange}
          onToggleDayVisibility={handleToggleMapDayVisibility}
          onShowAllDays={handleShowAllMapDays}
        />
      ) : null}

      {showOverview ? (
        <RouteOverviewPanel
          days={editableDays}
          tripOrigin={itinerary.planning_anchor_source.source_name}
          overview={overview}
          onSelectDay={(dayNumber) => {
            setSelectedDay(dayNumber);
            setShowOverview(false);
          }}
        />
      ) : showUnplanned ? (
        <UnplannedStopPool
          stops={unplannedStops}
          days={editableDays}
          selectedDay={selectedDay}
          editing={editing}
          onPlaceStop={handlePlaceUnplannedStop}
          onDeleteStop={handleDeleteUnplannedStop}
        />
      ) : selectedDayView ? (
        <div style={{ display: "grid", gap: 16 }}>
          <RouteSummaryCard
            originLabel={originLabelForDay(
              editableDays,
              selectedDayView.day,
              itinerary.planning_anchor_source.source_name,
            )}
            summary={buildDayRouteSummary(editableDays, selectedDayView.day)}
            routePreviewState={routePreviewState}
          />

          {editing ? (
            <>
              <BlockTargetRail
                day={selectedDayView}
                draggingStop={draggingStop}
                activeStop={activeStop}
                onMoveStop={handleMoveAcrossTimeline}
              />

              <PendingStopComposer
                name={pendingStopName}
                type={pendingStopType}
                blockType={pendingStopBlock}
                onNameChange={setPendingStopName}
                onTypeChange={setPendingStopType}
                onBlockChange={setPendingStopBlock}
                onInsert={handleInsertPendingStop}
                onAddToUnplanned={handleAddPendingStopToUnplanned}
              />
            </>
          ) : null}

          <div style={routeStopListStyle}>
            {selectedDayView.stops.map((stop, index) => {
              const previousStop = index > 0 ? selectedDayView.stops[index - 1] : null;
              const nextStop =
                index < selectedDayView.stops.length - 1 ? selectedDayView.stops[index + 1] : null;
                  const segment = buildSegmentLabel(
                    stop,
                    previousStop,
                    originLabelForDay(
                      editableDays,
                      selectedDayView.day,
                      itinerary.planning_anchor_source.source_name,
                    ),
                    routePreviewMap,
                  );
              const detailOpen = activeStopId === stop.id;
              const canMoveUp = index > 0;
              const canMoveDown = index < selectedDayView.stops.length - 1;

              return (
                <div
                  key={stop.id}
                  style={{ display: "grid", gap: 8 }}
                >
                  {segment ? (
                    <div style={segmentPillStyle(segment.status)}>
                      <span style={segmentLabelKickerStyle(segment.status)}>
                        {segment.status === "confirmed"
                          ? "路线段"
                          : segment.status === "previewed"
                            ? "真实路线"
                          : segment.status === "estimated"
                            ? "本地估算"
                            : "待重算"}
                      </span>
                      <span style={segmentLabelTextStyle(segment.status)}>
                        {segment.label}
                      </span>
                    </div>
                  ) : null}

                  <article
                    role="button"
                    tabIndex={0}
                    onClick={() => setActiveStopId(stop.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setActiveStopId(stop.id);
                      }
                    }}
                    onDragOver={(event) => {
                      if (!editing) {
                        return;
                      }
                      if (!draggingStop || draggingStop.stopId === stop.id) {
                        return;
                      }
                      event.preventDefault();
                    }}
                    onDrop={(event) => {
                      if (!editing) {
                        return;
                      }
                      if (!draggingStop) {
                        return;
                      }
                      event.preventDefault();
                      if (draggingStop.day === selectedDayView.day) {
                        handleMoveWithinDay(selectedDayView.day, draggingStop.stopId, stop.id);
                      } else {
                        handleMoveAcrossTimelineBeforeStop(
                          draggingStop.stopId,
                          selectedDayView.day,
                          stop.blockType,
                          stop.id,
                        );
                      }
                      setDraggingStop(null);
                    }}
                    className={`ec-route-stop-card ${
                      detailOpen ? "is-selected" : ""
                    } ${draggingStop?.stopId === stop.id ? "is-dragging" : ""}`}
                    style={{
                      ...routeStopCardStyle,
                    }}
                  >
                    <div style={routeStopThumbStyle(stop.item.type)}>
                      <span style={routeStopIndexBadgeStyle}>{index + 1}</span>
                      {stop.item.name.slice(0, 1)}
                    </div>
                    <div style={routeStopBodyStyle}>
                      <div style={{ display: "grid", gap: 4 }}>
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            gap: 12,
                            alignItems: "start",
                          }}
                        >
                          <div style={{ display: "grid", gap: 4 }}>
                            <p
                              style={{
                                margin: 0,
                                color: itemTone(stop.item.type),
                                fontSize: 11,
                                fontWeight: 900,
                                letterSpacing: "0.1em",
                                textTransform: "uppercase",
                              }}
                            >
                              {formatStopType(stop.item.type)} · {formatBlockLabel(stop.blockType)}
                            </p>
                            <h5
                              style={{
                                margin: 0,
                                color: "var(--ec-ink)",
                                fontSize: 18,
                                lineHeight: 1.12,
                                letterSpacing: "-0.02em",
                              }}
                            >
                              {stop.item.name}
                            </h5>
                          </div>
                          <div style={{ display: "grid", gap: 8, justifyItems: "end" }}>
                            <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 12, fontWeight: 800 }}>
                              {formatTimeRange(stop.item.start_time, stop.item.end_time)}
                            </p>
                            {editing ? (
                            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleToggleLockStop(stop.id);
                                }}
                                className="ec-interactive-icon"
                                style={tinyMoveButtonStyle}
                                title={isRouteEditLockedStop(stop) ? "取消锁定" : "锁定"}
                              >
                                {stop.item.is_fixed ? "锁" : "定"}
                              </button>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleDeleteStop(stop.id);
                                }}
                                disabled={stop.item.is_fixed}
                                className="ec-interactive-icon"
                                style={tinyMoveButtonStyle}
                                title={stop.item.is_fixed ? "固定地点需要先取消锁定" : "删除"}
                              >
                                ×
                              </button>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleMoveByOffset(selectedDayView.day, stop.id, -1);
                                }}
                                disabled={!canMoveUp}
                                className="ec-interactive-icon"
                                style={tinyMoveButtonStyle}
                              >
                                ↑
                              </button>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleMoveByOffset(selectedDayView.day, stop.id, 1);
                                }}
                                disabled={!canMoveDown}
                                className="ec-interactive-icon"
                                style={tinyMoveButtonStyle}
                              >
                                ↓
                              </button>
                              <div
                                draggable
                                onDragStart={(event) => {
                                  event.stopPropagation();
                                  setDraggingStop({
                                    stopId: stop.id,
                                    day: stop.day,
                                    blockType: stop.blockType,
                                  });
                                  event.dataTransfer.effectAllowed = "move";
                                  event.dataTransfer.setData("text/plain", stop.id);
                                }}
                                onDragEnd={() => setDraggingStop(null)}
                                style={dragHandleStyle}
                                aria-label="拖动排序"
                                title="拖动排序"
                              >
                                ⋮⋮
                              </div>
                            </div>
                            ) : null}
                          </div>
                        </div>

                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          {buildStopBadges(stop).map((badge) => (
                            <span key={`${stop.id}-${badge}`} style={stopBadgeStyle}>
                              {badge}
                            </span>
                          ))}
                        </div>
                      </div>

                      <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.65, fontSize: 14 }}>
                        {shortenText(formatPlannerCopy(stop.item.placement_reason ?? "这个地点已经排入当天路线。"), 54)}
                      </p>
                    </div>
                  </article>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
      </>
      )}
      </RouteEditorSheet>

      {!isPanelLayout && activeStop ? (
        <StopDetailDrawer
          stop={activeStop}
          allDays={editableDays}
          parsedIntent={parsedIntent}
          originLabel={originLabelForDay(
            editableDays,
            activeStop.day,
            itinerary.planning_anchor_source.source_name,
          )}
          poiDetailEndpoint={poiDetailEndpoint}
          editing={editing}
          onClose={() => setActiveStopId(null)}
          onMoveStop={handleMoveAcrossTimeline}
          onDeleteStop={handleDeleteStop}
          onToggleLockStop={handleToggleLockStop}
          onMoveToUnplanned={handleMoveToUnplanned}
        />
      ) : null}
      <style>{`
        .editable-route-workspace__left {
          display: none;
        }

        .editable-route-workspace__right {
          position: absolute;
          inset: 0;
        }

        .editable-route-workspace__map {
          position: absolute;
          inset: 0;
        }

        @media (min-width: 820px) and (max-width: 1119px) {
          .editable-route-workspace {
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            grid-template-areas:
              "map"
              "timeline";
            gap: 16px;
            min-height: 0;
            padding: 16px;
            background:
              radial-gradient(circle at 10% 10%, rgba(177,138,88,0.1), transparent 24%),
              radial-gradient(circle at 90% 8%, rgba(102,113,95,0.1), transparent 22%),
              rgba(247,244,238,0.88);
          }

          .editable-route-workspace__left {
            display: none;
          }

          .editable-route-workspace__right {
            grid-area: map;
            position: relative;
            inset: auto;
            z-index: 2;
            display: grid;
            grid-template-rows: minmax(420px, auto);
            gap: 0;
            min-width: 0;
            min-height: 420px;
          }

          .editable-route-workspace__map {
            position: relative;
            inset: auto;
            min-height: 420px;
            overflow: hidden;
            border: 1px solid rgba(37, 99, 235, 0.12);
            border-radius: 30px;
            box-shadow: 0 18px 48px rgba(21,21,21,0.08);
          }

          .editable-route-workspace__center {
            position: relative !important;
            grid-area: timeline;
            right: auto !important;
            bottom: auto !important;
            left: auto !important;
            z-index: 2 !important;
            height: auto !important;
            min-height: 620px;
            max-height: none;
            grid-template-rows: minmax(0, 1fr) !important;
            border-radius: 30px !important;
            box-shadow: var(--ec-shadow-1) !important;
          }

          .editable-route-workspace__center > :first-child {
            display: none !important;
          }
        }

        @media (min-width: 1120px) and (max-width: 1379px) {
          .editable-route-workspace {
            display: grid;
            grid-template-columns: minmax(232px, 300px) minmax(0, 1fr) minmax(320px, 388px);
            gap: 18px;
            min-height: min(668px, calc(100dvh - 206px));
            height: min(668px, calc(100dvh - 206px));
            padding: 18px;
            background:
              radial-gradient(circle at 12% 8%, rgba(37,99,235,0.08), transparent 24%),
              radial-gradient(circle at 88% 10%, rgba(102,113,95,0.08), transparent 22%),
              rgba(247,244,238,0.88);
          }

          .editable-route-workspace__left {
            position: relative;
            z-index: 2;
            display: grid;
            gap: 14px;
            align-content: start;
            min-width: 0;
            min-height: 0;
            max-height: 100%;
            overflow-y: auto;
            scrollbar-gutter: stable;
          }

          .editable-route-workspace__right {
            position: relative;
            inset: auto;
            z-index: 2;
            display: grid;
            grid-template-rows: minmax(0, 1fr);
            gap: 16px;
            min-width: 0;
            min-height: 0;
          }

          .editable-route-workspace__map {
            position: relative;
            inset: auto;
            min-height: 0;
            overflow: hidden;
            border: 1px solid rgba(37, 99, 235, 0.12);
            border-radius: 32px;
            box-shadow: 0 18px 48px rgba(21,21,21,0.08);
          }

          .editable-route-workspace__center {
            position: relative !important;
            right: auto !important;
            bottom: auto !important;
            left: auto !important;
            z-index: 2 !important;
            height: auto !important;
            min-height: 0;
            max-height: none;
            grid-template-rows: minmax(0, 1fr) !important;
            border-radius: 30px !important;
            box-shadow: 0 18px 48px rgba(21,21,21,0.07) !important;
          }

          .editable-route-workspace__center > :first-child {
            display: none !important;
          }
        }

        @media (min-width: 1380px) {
          .editable-route-workspace {
            display: grid;
            grid-template-columns: minmax(300px, 340px) minmax(0, 1fr) minmax(360px, 420px);
            gap: 20px;
            min-height: min(720px, calc(100dvh - 220px));
            height: min(720px, calc(100dvh - 220px));
            padding: 22px;
            background:
              radial-gradient(circle at 12% 8%, rgba(37,99,235,0.08), transparent 24%),
              radial-gradient(circle at 90% 8%, rgba(102,113,95,0.08), transparent 22%),
              rgba(247,244,238,0.88);
          }

          .editable-route-workspace__left,
          .editable-route-workspace__right {
            display: grid;
            gap: 16px;
            align-content: start;
            min-width: 0;
          }

          .editable-route-workspace__left {
            position: relative;
            z-index: 2;
            overflow-y: auto;
            scrollbar-gutter: stable;
            max-height: 100%;
            padding-right: 2px;
          }

          .editable-route-workspace__right {
            position: relative;
            inset: auto;
            grid-template-rows: minmax(0, 1fr);
            align-content: stretch;
            z-index: 2;
            min-height: 0;
          }

          .editable-route-workspace__map {
            position: relative;
            inset: auto;
            min-height: 0;
            overflow: hidden;
            border-radius: 34px;
            border: 1px solid rgba(37, 99, 235, 0.12);
            box-shadow: 0 20px 54px rgba(21,21,21,0.08);
          }

          .editable-route-workspace__center {
            position: relative !important;
            right: auto !important;
            bottom: auto !important;
            left: auto !important;
            z-index: 2 !important;
            height: auto !important;
            min-height: 0;
            max-height: none;
            overflow: hidden !important;
            grid-template-rows: minmax(0, 1fr) !important;
            border-radius: 32px !important;
            box-shadow: 0 18px 48px rgba(21,21,21,0.07) !important;
          }

          .editable-route-workspace__center > :first-child {
            display: none !important;
          }
        }

        @media (min-width: 1720px) {
          .editable-route-workspace {
            grid-template-columns: minmax(312px, 340px) minmax(0, 1fr) minmax(388px, 432px);
            gap: 22px;
            min-height: min(740px, calc(100dvh - 220px));
            height: min(740px, calc(100dvh - 220px));
          }

          .editable-route-workspace__right .editable-route-workspace__map {
            min-height: 520px;
          }

          .editable-route-workspace__center {
            min-width: 0;
          }
        }
      `}</style>
    </section>
  );
}

function RouteOverviewPanel({
  days,
  tripOrigin,
  overview,
  onSelectDay,
}: {
  days: EditableRouteDay[];
  tripOrigin: string;
  overview?: RouteWorkspaceOverview | null;
  onSelectDay: (dayNumber: number) => void;
}) {
  const totalStops = days.reduce((sum, day) => sum + day.stops.length, 0);
  const totalMeals = days.reduce(
    (sum, day) => sum + day.stops.filter((stop) => stop.item.type === "restaurant").length,
    0,
  );
  const totalLocked = days.reduce(
    (sum, day) => sum + day.stops.filter((stop) => isRouteEditLockedStop(stop)).length,
    0,
  );
  const realismStatusLabel =
    overview?.realismStatus === "executable"
      ? "基本可走"
      : overview?.realismStatus === "unstable"
        ? "需要重修"
        : overview?.realismStatus === "needs_repair"
          ? "仍需补齐"
          : "待确认";
  const crossDayInsights = buildCrossDayOverviewInsights(days);

  return (
    <section style={overviewPanelStyle}>
      <div style={{ display: "grid", gap: 5 }}>
        <p style={workspaceEyebrowStyle}>总览</p>
        <h5 style={secondaryPanelTitleStyle}>整趟路线</h5>
        <p style={secondaryPanelBodyStyle}>
          从 {tripOrigin} 出发，先看每一天怎么铺开，再点进具体日期继续调整顺序。
        </p>
      </div>

      <div style={overviewStatsGridStyle}>
        <div style={overviewStatStyle}>
          <span style={miniLabelStyle}>天数</span>
          <strong>{days.length}</strong>
        </div>
        <div style={overviewStatStyle}>
          <span style={miniLabelStyle}>站点</span>
          <strong>{totalStops}</strong>
        </div>
        <div style={overviewStatStyle}>
          <span style={miniLabelStyle}>餐食</span>
          <strong>{totalMeals}</strong>
        </div>
        <div style={overviewStatStyle}>
          <span style={miniLabelStyle}>锁定</span>
          <strong>{totalLocked}</strong>
        </div>
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        <div style={overviewHealthCardStyle(overview?.realismStatus)}>
          <span style={miniLabelStyle}>当前状态</span>
          <strong>{realismStatusLabel}</strong>
          <span style={secondaryPanelBodyStyle}>
            {overview?.realismHeadline ?? "系统会继续检查路线是否需要补齐或修稳。"}
          </span>
        </div>

        <div style={overviewSignalsGridStyle}>
          <div style={overviewSignalCardStyle}>
            <span style={miniLabelStyle}>可执行度</span>
            <strong>{overview?.completeness != null ? `${overview.completeness}%` : "--"}</strong>
          </div>
          <div style={overviewSignalCardStyle}>
            <span style={miniLabelStyle}>待补任务</span>
            <strong>{overview?.pendingTaskCount ?? "--"}</strong>
          </div>
          <div style={overviewSignalCardStyle}>
            <span style={miniLabelStyle}>住哪里</span>
            <strong>{overview?.stayAreaLabel ?? "待反推"}</strong>
          </div>
          <div style={overviewSignalCardStyle}>
            <span style={miniLabelStyle}>怎么离开</span>
            <strong>{overview?.departureLabel ?? "待确认"}</strong>
          </div>
        </div>

        <div style={overviewLedgerStyle}>
          <div style={overviewLedgerItemStyle("intent")}>
            <span style={miniLabelStyle}>已理解</span>
            <strong style={overviewLedgerTitleStyle}>你给出的边界</strong>
            <span style={overviewInsightBodyStyle}>
              {overview?.intentLine ?? "已把一句话拆成目的地、天数、偏好和固定安排，先保护这些输入。"}
            </span>
          </div>
          <div style={overviewLedgerItemStyle("execution")}>
            <span style={miniLabelStyle}>已检查</span>
            <strong style={overviewLedgerTitleStyle}>这版路线风险</strong>
            <span style={overviewInsightBodyStyle}>
              {overview?.executionLine ??
                `已补入 ${overview?.autoFilledCount ?? 0} 项，并继续检查空档、绕路和缺餐食。`}
            </span>
          </div>
        </div>

        {overview?.weakestDay ? (
          <button
            type="button"
            onClick={() => onSelectDay(overview.weakestDay?.day ?? days[0]?.day ?? 1)}
            className="ec-interactive-card"
            style={overviewFocusCardStyle}
          >
            <div style={{ display: "grid", gap: 4 }}>
              <span style={miniLabelStyle}>优先修哪里</span>
              <strong style={overviewCardTitleStyle}>
                第 {overview.weakestDay.day} 天
              </strong>
            </div>
            <span style={secondaryPanelBodyStyle}>
              {overview.weakestDay.reason}
            </span>
            <span style={overviewDayArrowStyle}>›</span>
          </button>
        ) : null}
      </div>

      {crossDayInsights.length > 0 ? (
        <div style={{ display: "grid", gap: 10 }}>
          <span style={miniLabelStyle}>跨天判断</span>
          <div style={overviewInsightGridStyle}>
            {crossDayInsights.map((insight) => (
              <button
                key={insight.key}
                type="button"
                onClick={() => onSelectDay(insight.day)}
                className="ec-interactive-card"
                style={overviewInsightCardStyle}
              >
                <span style={miniLabelStyle}>{insight.label}</span>
                <strong style={overviewInsightTitleStyle}>{insight.title}</strong>
                <span style={overviewInsightBodyStyle}>{insight.detail}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      <div style={{ display: "grid", gap: 10 }}>
        {days.map((day) => {
          const firstStop = day.stops[0]?.item.name ?? "还没有地点";
          const lastStop = day.stops.at(-1)?.item.name ?? firstStop;
          return (
            <button
              key={`overview-day-${day.day}`}
              type="button"
              onClick={() => onSelectDay(day.day)}
              className="ec-interactive-card"
              style={overviewDayCardStyle}
            >
              <div style={{ display: "grid", gap: 4 }}>
                <span style={miniLabelStyle}>{day.label}</span>
                <strong style={overviewCardTitleStyle}>
                  {day.stops.length} 个地点
                </strong>
              </div>
              <div style={{ display: "grid", gap: 4, minWidth: 0 }}>
                <span style={{ color: "var(--ec-ink-soft)", fontWeight: 800 }}>
                  {firstStop === lastStop ? firstStop : `${firstStop} → ${lastStop}`}
                </span>
                <span style={overviewInsightBodyStyle}>
                  {shortenText(buildDayRouteSummary(days, day.day), 72)}
                </span>
              </div>
              <span style={overviewDayArrowStyle}>›</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function PendingStopComposer({
  name,
  type,
  blockType,
  onNameChange,
  onTypeChange,
  onBlockChange,
  onInsert,
  onAddToUnplanned,
}: {
  name: string;
  type: TimelineItemType;
  blockType: TimelineBlockType;
  onNameChange: (value: string) => void;
  onTypeChange: (value: TimelineItemType) => void;
  onBlockChange: (value: TimelineBlockType) => void;
  onInsert: () => void;
  onAddToUnplanned: () => void;
}) {
  return (
    <div style={pendingComposerStyle}>
      <div style={{ display: "grid", gap: 4, minWidth: 0 }}>
        <p style={miniLabelStyle}>插入待规划点</p>
        <input
          value={name}
          onChange={(event) => onNameChange(event.target.value)}
          placeholder="输入地点名，例如 五大道附近咖啡"
          className="ec-field"
          style={pendingInputStyle}
        />
      </div>
      <div style={pendingControlsStyle}>
        <select
          value={type}
          onChange={(event) => onTypeChange(event.target.value as TimelineItemType)}
          className="ec-field"
          style={pendingSelectStyle}
        >
          <option value="scenic">景点</option>
          <option value="restaurant">餐食</option>
        </select>
        <select
          value={blockType}
          onChange={(event) => onBlockChange(event.target.value as TimelineBlockType)}
          className="ec-field"
          style={pendingSelectStyle}
        >
          <option value="morning">上午</option>
          <option value="afternoon">下午</option>
          <option value="evening">晚上</option>
        </select>
        <button
          type="button"
          onClick={onInsert}
          disabled={!name.trim()}
          className="ec-interactive-pill"
          style={{
            ...insertButtonStyle,
            opacity: name.trim() ? 1 : 0.48,
          }}
        >
          插入
        </button>
        <button
          type="button"
          onClick={onAddToUnplanned}
          disabled={!name.trim()}
          className="ec-interactive-pill"
          style={{
            ...insertButtonStyle,
            background: "rgba(255,255,255,0.88)",
            color: "var(--ec-ink-soft)",
            opacity: name.trim() ? 1 : 0.48,
          }}
        >
          先放待规划
        </button>
      </div>
    </div>
  );
}

function MobileMapLayerPanel({
  allDays,
  selectedDay,
  visibleDays,
  routeMode,
  routePreviewState,
  onRouteModeChange,
  onToggleDayVisibility,
  onShowAllDays,
}: {
  allDays: number[];
  selectedDay: number;
  visibleDays: number[];
  routeMode: RoutePreviewMode;
  routePreviewState: "idle" | "loading" | "partial" | "failed";
  onRouteModeChange: (mode: RoutePreviewMode) => void;
  onToggleDayVisibility: (day: number) => void;
  onShowAllDays: () => void;
}) {
  return (
    <section style={mobileMapLayerPanelStyle} aria-label="地图路线图层">
      <div style={mobileMapLayerHeaderStyle}>
        <div>
          <p style={mobileMapLayerEyebrowStyle}>路线图层</p>
          <h5 style={mobileMapLayerTitleStyle}>路线方式与 Day 图层</h5>
        </div>
        <span style={mobileMapLayerStatusStyle(routePreviewState)}>
          {routePreviewStateText(routePreviewState)}
        </span>
      </div>
      <div style={mobileRouteModeGridStyle}>
        {ROUTE_MODE_CONTROL_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onRouteModeChange(option.value)}
            className="ec-interactive-pill"
            style={mobileRouteModeButtonStyle(routeMode === option.value)}
            aria-pressed={routeMode === option.value}
          >
            <span style={mobileRouteModeKickerStyle(routeMode === option.value)}>
              {option.kicker}
            </span>
            {option.label}
          </button>
        ))}
      </div>
      <div style={mobileDayLayerGridStyle}>
        <button
          type="button"
          onClick={onShowAllDays}
          className="ec-interactive-pill"
          style={mobileDayLayerButtonStyle(visibleDays.length >= allDays.length, false)}
        >
          <span style={mobileDayLayerKickerStyle}>显示</span>
          全部
        </button>
        {allDays.map((day) => {
          const active = visibleDays.includes(day);
          const locked = day === selectedDay;
          return (
            <button
              key={`mobile-map-layer-day-${day}`}
              type="button"
              onClick={() => onToggleDayVisibility(day)}
              disabled={locked}
              className="ec-interactive-pill"
              style={mobileDayLayerButtonStyle(active, locked)}
              aria-pressed={active}
              title={locked ? "当前 Day 始终显示" : active ? "隐藏这一天" : "显示这一天"}
            >
              <span style={mobileDayLayerKickerStyle}>
                {locked ? "当前" : active ? "显示" : "隐藏"}
              </span>
              D{day}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function UnplannedStopPool({
  stops,
  days,
  selectedDay,
  editing,
  onPlaceStop,
  onDeleteStop,
}: {
  stops: EditableRouteStop[];
  days: EditableRouteDay[];
  selectedDay: number;
  editing: boolean;
  onPlaceStop: (stopId: string, targetDay: number, targetBlockType: TimelineBlockType) => void;
  onDeleteStop: (stopId: string) => void;
}) {
  return (
    <section style={unplannedPoolStyle}>
      <div style={{ display: "grid", gap: 5 }}>
        <p style={workspaceEyebrowStyle}>待规划</p>
        <h5 style={secondaryPanelTitleStyle}>待规划</h5>
        <p style={secondaryPanelBodyStyle}>
          先把还没决定放哪天的地点收进来。它们会保留在当前计划里，但暂时不挤进某一天的路线。
        </p>
      </div>

      {stops.length === 0 ? (
        <p style={emptyUnplannedStyle}>
          {editing ? "还没有待规划点。你可以在上方输入地点后点“先放待规划”。" : "这趟旅行暂时没有待规划点。"}
        </p>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {stops.map((stop) => (
            <article key={stop.id} style={unplannedStopCardStyle}>
              <div style={{ display: "grid", gap: 4 }}>
                <p style={secondaryMetaLabelStyle(itemTone(stop.item.type))}>
                  {formatStopType(stop.item.type)}
                </p>
                <h6 style={unplannedCardTitleStyle}>{stop.item.name}</h6>
                <p style={{ margin: 0, color: "var(--ec-slate)", lineHeight: 1.55 }}>
                  尚未安排到具体日期，后续继续生成时仍会把它当作你的明确偏好。
                </p>
              </div>
              {editing ? (
              <div style={{ display: "grid", gap: 8 }}>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {days.map((day) => (
                    <button
                      key={`${stop.id}-day-${day.day}`}
                      type="button"
                      onClick={() => onPlaceStop(stop.id, day.day, stop.blockType)}
                      className="ec-interactive-pill"
                      style={tinyPlacementButtonStyle}
                    >
                      放到第 {day.day} 天
                    </button>
                  ))}
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {BLOCK_ORDER.map((blockType) => (
                    <button
                      key={`${stop.id}-block-${blockType}`}
                      type="button"
                      onClick={() => onPlaceStop(stop.id, selectedDay, blockType)}
                      className="ec-interactive-pill"
                      style={tinyPlacementButtonStyle}
                    >
                      第 {selectedDay} 天 · {formatBlockLabel(blockType)}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => onDeleteStop(stop.id)}
                    className="ec-interactive-pill"
                    style={tinyDangerButtonStyle}
                  >
                    删除
                  </button>
                </div>
              </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function BlockTargetRail({
  day,
  draggingStop,
  activeStop,
  onMoveStop,
}: {
  day: EditableRouteDay;
  draggingStop: DraggingStopMeta | null;
  activeStop: EditableRouteStop | null;
  onMoveStop: (stopId: string, targetDay: number, targetBlockType: TimelineBlockType) => void;
}) {
  return (
    <div style={blockRailStyle}>
      {BLOCK_ORDER.map((blockType) => {
        const count = day.stops.filter((stop) => stop.blockType === blockType).length;
        const targetableStopId =
          activeStop && activeStop.day === day.day ? activeStop.id : draggingStop?.stopId ?? null;
        return (
          <button
            key={`block-target-${day.day}-${blockType}`}
            type="button"
            disabled={!targetableStopId}
            className="ec-interactive-pill"
            onClick={() => {
              if (targetableStopId) {
                onMoveStop(targetableStopId, day.day, blockType);
              }
            }}
            onDragOver={(event) => {
              if (!draggingStop) {
                return;
              }
              event.preventDefault();
            }}
            onDrop={(event) => {
              if (!draggingStop) {
                return;
              }
              event.preventDefault();
              onMoveStop(draggingStop.stopId, day.day, blockType);
            }}
            style={{
              ...buildBlockTargetStyle(blockType),
              opacity: targetableStopId ? 1 : 0.68,
            }}
          >
            <span style={{ fontWeight: 900 }}>{formatBlockLabel(blockType)}</span>
            <span>{count} 个地点</span>
          </button>
        );
      })}
    </div>
  );
}

function RouteSummaryCard({
  originLabel,
  summary,
  routePreviewState,
}: {
  originLabel: string;
  summary: string;
  routePreviewState: "idle" | "loading" | "partial" | "failed";
}) {
  return (
    <div style={routeSummaryCardStyle}>
      <div style={{ display: "grid", gap: 3 }}>
        <p style={miniLabelStyle}>始发地</p>
        <p style={{ margin: 0, color: "#15212c", fontSize: 19, fontWeight: 900 }}>{originLabel}</p>
      </div>
      <p style={{ margin: 0, color: "#61707a", lineHeight: 1.5, fontSize: 14 }}>{summary}</p>
      {routePreviewState !== "idle" ? (
        <p style={{ margin: 0, color: routePreviewState === "failed" ? "#9a3412" : "#23745f", fontSize: 13, lineHeight: 1.55 }}>
          {routePreviewState === "loading"
            ? "正在用真实路线刷新被改动的相邻路段..."
            : routePreviewState === "partial"
              ? "部分路段已用真实路线刷新，其余仍使用本地估算。"
              : "真实路线刷新失败，当前保留本地估算。"}
        </p>
      ) : null}
    </div>
  );
}

function StopDetailDrawer({
  variant = "drawer",
  stop,
  allDays,
  parsedIntent,
  originLabel,
  poiDetailEndpoint,
  editing,
  onClose,
  onMoveStop,
  onDeleteStop,
  onToggleLockStop,
  onMoveToUnplanned,
}: {
  variant?: "drawer" | "panel";
  stop: EditableRouteStop;
  allDays: EditableRouteDay[];
  parsedIntent?: ParsedTripIntentLike | null;
  originLabel: string;
  poiDetailEndpoint?: string;
  editing: boolean;
  onClose: () => void;
  onMoveStop: (stopId: string, targetDay: number, targetBlockType: TimelineBlockType) => void;
  onDeleteStop: (stopId: string) => void;
  onToggleLockStop: (stopId: string) => void;
  onMoveToUnplanned: (stopId: string) => void;
}) {
  const [poiDetail, setPoiDetail] = useState<POIDetailPreview | null>(null);
  const [poiDetailState, setPoiDetailState] = useState<"idle" | "loading" | "failed">("idle");
  const [showPlannerDetails, setShowPlannerDetails] = useState(false);
  const resolution = findPlaceResolution(parsedIntent, stop.item.name);
  const day = allDays.find((entry) => entry.day === stop.day) ?? null;
  const stopIndex = day?.stops.findIndex((candidate) => candidate.id === stop.id) ?? -1;
  const previousStop = day && stopIndex > 0 ? day.stops[stopIndex - 1] : null;
  const nextStop =
    day && stopIndex >= 0 && stopIndex < day.stops.length - 1 ? day.stops[stopIndex + 1] : null;
  const routeState = describeStopRouteState(stop);
  const detailCard = buildPoiDetailCardViewModel({
    stop,
    previousStop,
    nextStop,
    resolution,
    originLabel,
    routeState,
    poiDetail,
  });

  useEffect(() => {
    if (!poiDetailEndpoint) {
      setPoiDetail(null);
      setPoiDetailState("idle");
      return;
    }
    if (isGenericPlanningAnchorName(stop.item.name)) {
      setPoiDetail(null);
      setPoiDetailState("idle");
      return;
    }

    const cacheKey = buildPoiDetailCacheKey({
      name: stop.item.name,
      city: stop.item.city ?? resolution?.city ?? null,
      latitude: stop.item.latitude ?? null,
      longitude: stop.item.longitude ?? null,
    });
    const cachedDetail = getCachedPoiDetailPreview(cacheKey);
    if (cachedDetail) {
      setPoiDetail(cachedDetail);
      setPoiDetailState("idle");
      return;
    }

    const controller = new AbortController();
    setPoiDetailState("loading");
    setPoiDetail(null);

    postTripJson<POIDetailPreview>(
      poiDetailEndpoint,
      {
        name: stop.item.name,
        city: stop.item.city ?? resolution?.city ?? null,
        latitude: stop.item.latitude ?? null,
        longitude: stop.item.longitude ?? null,
      },
      "POI detail failed.",
      "POI detail failed.",
      { signal: controller.signal },
    )
      .then((result) => {
        if (!result.ok) {
          if (!result.aborted) {
            setPoiDetail(null);
            setPoiDetailState("failed");
          }
          return;
        }
        const payload = result.data;
        if (payload.found) {
          cachePoiDetailPreview(cacheKey, payload);
        }
        setPoiDetail(payload.found ? payload : null);
        setPoiDetailState(payload.found ? "idle" : "failed");
      });

    return () => controller.abort();
  }, [
    poiDetailEndpoint,
    resolution?.city,
    stop.id,
    stop.item.city,
    stop.item.latitude,
    stop.item.longitude,
    stop.item.name,
  ]);

  const panel = variant === "panel";
  const content = (
      <div
        data-stop-detail-panel={panel ? "panel" : "drawer"}
        style={variant === "drawer" ? drawerSheetStyle : detailPanelStyle}
        onClick={(event) => event.stopPropagation()}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: 12,
            alignItems: "start",
          }}
        >
          <div style={{ display: "grid", gap: 8 }}>
            <p
              style={{
                margin: 0,
                color: itemTone(stop.item.type),
                fontSize: 11,
                fontWeight: 900,
                letterSpacing: "0.12em",
                textTransform: "uppercase",
              }}
            >
              {formatStopType(stop.item.type)} · {formatBlockLabel(stop.blockType)}
            </p>
            <h4
              style={{
                margin: 0,
                color: "var(--ec-ink)",
                fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
                fontSize: panel ? 22 : 30,
                lineHeight: 1.08,
              }}
            >
              {stop.item.name}
            </h4>
            <p style={{ margin: 0, color: "var(--ec-slate)", fontSize: 14 }}>
              {formatTimeRange(stop.item.start_time, stop.item.end_time)}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ec-interactive-pill"
            style={drawerCloseButtonStyle}
          >
            关闭
          </button>
        </div>

        {panel ? (
          <PlaceInspectorCard
            viewModel={detailCard}
            routeState={routeState}
            travelLine={buildDrawerTravelLine(stop, originLabel)}
            compact
          />
        ) : (
          <PoiDetailCard viewModel={detailCard} compact={false} />
        )}

        {poiDetailState === "loading" ? (
          <p style={poiDetailStatusStyle}>正在加载真实地点信息...</p>
        ) : poiDetailState === "failed" ? (
          <p style={poiDetailStatusStyle}>暂时没有拿到实时地点卡片，当前展示路线语境信息。</p>
        ) : null}

        {panel ? (
          <div style={detailPanelFooterStyle}>
            <button
              type="button"
              onClick={onClose}
              className="ec-interactive-pill"
              style={drawerSecondaryActionStyle}
            >
              返回时间线
            </button>
            {editing ? (
              <>
                <button
                  type="button"
                  onClick={() => onToggleLockStop(stop.id)}
                  className="ec-interactive-pill"
                  style={drawerSecondaryActionStyle}
                >
                  {isRouteEditLockedStop(stop) ? "取消锁定" : "锁定"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (stop.item.is_fixed) {
                      return;
                    }
                    onMoveToUnplanned(stop.id);
                    onClose();
                  }}
                  disabled={stop.item.is_fixed}
                  className="ec-interactive-pill"
                  style={{
                    ...drawerSecondaryActionStyle,
                    opacity: stop.item.is_fixed ? 0.45 : 1,
                  }}
                >
                  移到待规划
                </button>
              </>
            ) : null}
          </div>
        ) : null}

        {!panel ? (
          <>
            <section style={detailDecisionSummaryStyle}>
              <DetailRow label="当前路线状态" value={routeState} />
              <DetailRow label="这段怎么接" value={buildDrawerTravelLine(stop, originLabel)} />
              {stop.item.local_edit ? (
	                <DetailRow
	                  label="你的编辑"
	                  value={`你把 ${stop.item.local_edit.previous_name} 换成了 ${stop.item.name}。${formatPlannerCopy(stop.item.local_edit.reasoning_summary)}`}
	                />
              ) : null}
            </section>

            <button
              type="button"
              onClick={() => setShowPlannerDetails((current) => !current)}
              className="ec-interactive-pill"
              style={plannerDetailToggleStyle}
            >
              {showPlannerDetails ? "收起规划细节" : "查看规划细节"}
            </button>
          </>
        ) : null}

        {showPlannerDetails ? (
          <section style={plannerDetailPanelStyle}>
	            <DetailRow
	              label="放在这里的原因"
	              value={formatPlannerCopy(stop.item.placement_reason ?? "当前版本还没有补出更细的理由。")}
	            />
            {stop.item.source_reason ? (
              <DetailRow label="来源说明" value={formatPlannerCopy(stop.item.source_reason)} />
            ) : null}
            {resolution ? (
              <>
                <DetailRow
                  label="地点解析"
                  value={formatPlaceResolutionLine(resolution)}
                />
                {resolution.candidate_names.length > 0 ? (
                  <DetailRow
                    label="候选名"
                    value={resolution.candidate_names.slice(0, 4).join(" / ")}
                  />
                ) : null}
              </>
            ) : null}
            {stop.item.local_edit ? (
	              <DetailRow
	                label="完整编辑理由"
	                value={formatPlannerCopy(stop.item.local_edit.itinerary_relation_summary)}
	              />
            ) : null}
          </section>
        ) : null}

        {editing && !panel ? (
        <div style={{ display: "grid", gap: 12 }}>
          <p style={miniLabelStyle}>移动到别的时间段</p>
          <div style={blockRailStyle}>
            {BLOCK_ORDER.map((blockType) => (
              <button
                key={`drawer-block-${blockType}`}
                type="button"
                onClick={() => onMoveStop(stop.id, stop.day, blockType)}
                className="ec-interactive-pill"
                style={buildBlockTargetStyle(blockType)}
              >
                {formatBlockLabel(blockType)}
              </button>
            ))}
          </div>
        </div>
        ) : null}

        {editing && !panel ? (
          <>
            <div style={{ display: "grid", gap: 12 }}>
              <p style={miniLabelStyle}>移动到别的天</p>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {allDays.map((day) => (
                  <button
                    key={`drawer-day-${day.day}`}
                    type="button"
                    onClick={() => onMoveStop(stop.id, day.day, stop.blockType)}
                    className="ec-interactive-pill"
                    style={buildDayTabStyle(day.day === stop.day)}
                  >
                    {day.label}
                  </button>
                ))}
              </div>
            </div>

            <div style={drawerActionGridStyle}>
              <button
                type="button"
                onClick={() => onToggleLockStop(stop.id)}
                className="ec-interactive-pill"
                style={drawerSecondaryActionStyle}
              >
                {isRouteEditLockedStop(stop) ? "取消锁定" : "锁定这个地点"}
              </button>
              <button
                type="button"
                onClick={() => onMoveToUnplanned(stop.id)}
                disabled={stop.item.is_fixed}
                className="ec-interactive-pill"
                style={{
                  ...drawerSecondaryActionStyle,
                  opacity: stop.item.is_fixed ? 0.45 : 1,
                }}
              >
                移到待规划
              </button>
              <button
                type="button"
                onClick={() => {
                  if (stop.item.is_fixed) {
                    return;
                  }
                  onDeleteStop(stop.id);
                  onClose();
                }}
                disabled={stop.item.is_fixed}
                className="ec-interactive-pill"
                style={{
                  ...drawerDangerActionStyle,
                  opacity: stop.item.is_fixed ? 0.45 : 1,
                }}
              >
                删除这个地点
              </button>
            </div>
          </>
        ) : !panel ? (
          <section style={detailReadOnlyHintStyle}>
            <p style={miniLabelStyle}>编辑提示</p>
            <span>
              当前先作为地点信任卡查看。进入编辑路线后，可以把它跨天移动、锁定或移到待规划池。
            </span>
          </section>
        ) : null}
      </div>
  );

  if (variant === "panel") {
    return content;
  }

  return (
    <div style={drawerOverlayStyle} onClick={onClose}>
      {content}
    </div>
  );
}

function PoiDetailCard({
  viewModel,
  compact = false,
}: {
  viewModel: PoiDetailCardViewModel;
  compact?: boolean;
}) {
  return (
    <section style={poiCardStyle(compact)}>
      <div aria-hidden="true" style={poiFieldNoteRuleStyle} />
      <div style={poiHeroRowStyle(compact)}>
        <div
          style={{
            ...poiThumbStyle(compact),
            ...(viewModel.heroImageUrl
              ? {
                  backgroundImage: `url(${viewModel.heroImageUrl})`,
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                  color: "transparent",
                }
              : null),
          }}
        >
          {viewModel.heroInitial}
        </div>
        <div style={{ display: "grid", gap: 8, minWidth: 0 }}>
          <p style={poiTypeLabelStyle}>{viewModel.typeLabel}</p>
          <h5 style={poiCardTitleStyle(compact)}>{viewModel.title}</h5>
          <p style={poiSubtitleStyle}>{viewModel.subtitle}</p>
        </div>
      </div>

      <div style={poiChipRowStyle}>
        {viewModel.trustChips.map((chip) => (
          <span key={chip} style={poiChipStyle}>
            {chip}
          </span>
        ))}
      </div>

      {viewModel.liveFacts ? <PoiLiveFactsCard facts={viewModel.liveFacts} /> : null}

      <div style={poiRouteStripStyle}>
        <span style={{ color: "var(--ec-ochre)", fontWeight: 900 }}>为什么放这里</span>
        <span>{viewModel.routeLine}</span>
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        <p style={poiSectionTitleStyle}>值不值得去</p>
        <p style={poiBodyTextStyle}>{viewModel.introduction}</p>
      </div>

      <PoiResearchCard research={viewModel.research} compact={compact} />

      <div style={poiTwoColumnStyle(compact)}>
        <PoiBulletBox title="适合这趟路线" bullets={viewModel.fitBullets} tone="fit" />
        <PoiBulletBox title="出行避坑" bullets={viewModel.cautionBullets} tone="caution" />
      </div>
    </section>
  );
}

function PlaceInspectorCard({
  viewModel,
  routeState,
  travelLine,
  compact = false,
}: {
  viewModel: PoiDetailCardViewModel;
  routeState: string;
  travelLine: string;
  compact?: boolean;
}) {
  const primaryFacts = [
    ...viewModel.trustChips.slice(0, 3),
    viewModel.liveFacts?.facts.find((fact) => fact.label === "开放")?.value ?? null,
  ].filter((fact): fact is string => Boolean(fact));
  const visibleFacts = compact ? primaryFacts.slice(0, 3) : primaryFacts;

  return (
    <section style={placeInspectorCardStyle(compact)}>
      <div style={placeInspectorRouteStyle(compact)}>
        <span style={placeInspectorLabelStyle}>为什么放这里</span>
        <strong style={placeInspectorRouteTextStyle(compact)}>
          {shortenText(viewModel.routeLine, compact ? 62 : 84)}
        </strong>
      </div>
      {visibleFacts.length > 0 ? (
        <div style={placeInspectorFactsStyle}>
          {visibleFacts.map((fact) => (
            <span key={fact} style={placeInspectorFactStyle(compact)}>
              {fact}
            </span>
          ))}
        </div>
      ) : null}
      <div style={placeInspectorGridStyle(compact)}>
        <div style={placeInspectorNoteStyle("fit", compact)}>
          <span style={placeInspectorLabelStyle}>路线价值</span>
          <p style={placeInspectorNoteTextStyle(compact)}>
            {shortenText(viewModel.introduction, compact ? 56 : 92)}
          </p>
        </div>
        <div style={placeInspectorNoteStyle("caution", compact)}>
          <span style={placeInspectorLabelStyle}>注意事项</span>
          <p style={placeInspectorNoteTextStyle(compact)}>
            {shortenText(viewModel.cautionBullets[0] ?? routeState, compact ? 52 : 80)}
          </p>
        </div>
      </div>
      {!compact ? (
        <p style={placeInspectorTravelStyle}>{shortenText(travelLine, 86)}</p>
      ) : null}
    </section>
  );
}

function PoiLiveFactsCard({ facts }: { facts: PoiLiveFactsViewModel }) {
  return (
    <section style={poiLiveFactsCardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <p style={poiSectionTitleStyle}>真实信息</p>
        <span style={poiLiveFactsSourceStyle}>{facts.sourceLabel}</span>
      </div>
      <div style={poiLiveFactsGridStyle}>
        {facts.facts.map((fact) => (
          <div key={fact.label} style={poiLiveFactItemStyle}>
            <p style={researchLabelStyle}>{fact.label}</p>
            <p style={poiLiveFactValueStyle}>{fact.value}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function PoiResearchCard({
  research,
  compact = false,
}: {
  research: PoiResearchCardViewModel;
  compact?: boolean;
}) {
  return (
    <div style={researchCardStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <p style={poiSectionTitleStyle}>到达与判断</p>
        <span style={researchSourceStyle}>{research.sourceLabel}</span>
      </div>
      <div style={researchGridStyle(compact)}>
        <ResearchItem label="到达" value={research.accessTip} />
        <ResearchItem label="注意" value={research.practicalTip} />
        <ResearchItem label="适合" value={research.bestFor} />
      </div>
      <div style={researchOverviewStyle}>
        <p style={researchLabelStyle}>高频评价</p>
        <p style={researchValueStyle}>{research.overview}</p>
      </div>
    </div>
  );
}

function ResearchItem({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "grid", gap: 4 }}>
      <p style={researchLabelStyle}>{label}</p>
      <p style={researchValueStyle}>{value}</p>
    </div>
  );
}

function PoiBulletBox({
  title,
  bullets,
  tone,
}: {
  title: string;
  bullets: string[];
  tone: "fit" | "caution";
}) {
  return (
    <div style={poiBulletBoxStyle(tone)}>
      <p style={poiSectionTitleStyle}>{title}</p>
      <div style={{ display: "grid", gap: 6 }}>
        {bullets.map((bullet) => (
          <p key={bullet} style={poiBulletTextStyle}>
            {bullet}
          </p>
        ))}
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <p style={miniLabelStyle}>{label}</p>
      <p style={{ margin: 0, color: "var(--ec-ink-soft)", fontSize: 14, lineHeight: 1.7 }}>{value}</p>
    </div>
  );
}

function buildEditableRouteDays(itinerary: ItineraryLike): EditableRouteDay[] {
  return itinerary.days.map((day) => {
    let originalIndex = 0;
    const stops = day.blocks.flatMap((block) =>
      block.items.map((item, index) => {
        const stop: EditableRouteStop = {
          id: buildEditableStopId(day.day, block.block_type, item, index),
          day: day.day,
          originalDay: day.day,
          originalIndex,
          originalIsFixed: item.is_fixed,
          blockType: block.block_type,
          originalBlockType: block.block_type,
          item,
        };
        originalIndex += 1;
        return stop;
      }),
    );
    return {
      day: day.day,
      label: `DAY ${day.day}`,
      originalStopCount: stops.length,
      stops,
    };
  });
}

function buildEditableStopId(
  day: number,
  blockType: TimelineBlockType,
  item: ScheduledItemLike,
  index: number,
): string {
  return `${day}-${blockType}-${item.name}-${item.start_time}-${item.end_time}-${index}`;
}

function buildManualStopId(
  day: number,
  blockType: TimelineBlockType,
  name: string,
): string {
  return `manual-${day}-${blockType}-${name}-${Date.now()}`;
}

function insertPendingStop(
  days: EditableRouteDay[],
  targetDay: number,
  targetBlockType: TimelineBlockType,
  name: string,
  type: TimelineItemType,
): EditableRouteDay[] {
  return days.map((day) => {
    if (day.day !== targetDay) {
      return day;
    }

    const stop = buildManualPendingStop(targetDay, targetBlockType, name, type);
    const insertionIndex = buildBlockInsertionIndex(day.stops, targetBlockType);
    const nextStops = [...day.stops];
    nextStops.splice(insertionIndex, 0, stop);
    return { ...day, stops: nextStops };
  });
}

function buildManualPendingStop(
  day: number,
  blockType: TimelineBlockType,
  name: string,
  type: TimelineItemType,
): EditableRouteStop {
  const blockTime = getBlockDefaultTime(blockType);
  return {
    id: buildManualStopId(day, blockType, name),
    day,
    originalDay: -1,
    originalIndex: -1,
    originalIsFixed: false,
    blockType,
    originalBlockType: blockType,
    item: {
      name,
      type,
      start_time: blockTime.start,
      end_time: blockTime.end,
      is_fixed: false,
      placement_reason: "你在编辑路线时手动插入了这个待规划点，下一次补全会把它作为当前计划的一部分继续处理。",
      source_type: "user_seed",
      source_label: "手动插入",
      source_reason: "来自路线编辑器里的插入动作。",
      travel_from_name: null,
      travel_distance_m: null,
      travel_duration_s: null,
    },
  };
}

function insertExistingStop(
  days: EditableRouteDay[],
  stop: EditableRouteStop,
): EditableRouteDay[] {
  return days.map((day) => {
    if (day.day !== stop.day) {
      return day;
    }
    const insertionIndex = buildBlockInsertionIndex(day.stops, stop.blockType);
    const nextStops = [...day.stops];
    nextStops.splice(insertionIndex, 0, stop);
    return { ...day, stops: nextStops };
  });
}

function toggleRouteStopLock(stop: EditableRouteStop): EditableRouteStop {
  if (isRouteEditLockedStop(stop)) {
    return {
      ...stop,
      item: {
        ...stop.item,
        is_fixed: false,
        source_type: stop.item.source_type === "user_fixed" ? "user_seed" : stop.item.source_type,
        source_label: null,
        source_reason: "你在编辑路线里取消了这个地点的锁定。",
      },
    };
  }

  if (stop.item.is_fixed && !isRouteEditLockedStop(stop)) {
    return stop;
  }

  return {
    ...stop,
    item: {
      ...stop.item,
      is_fixed: true,
      source_type: "user_fixed",
      source_label: "已锁定",
      source_reason: "你在编辑路线里锁定了这个地点，下一次生成会把它作为固定路线意图带入。",
    },
  };
}

function isRouteEditLockedStop(stop: EditableRouteStop): boolean {
  return stop.item.source_label === "已锁定" || stop.item.source_reason?.includes("编辑路线里锁定") === true;
}

function getBlockDefaultTime(blockType: TimelineBlockType): { start: string; end: string } {
  if (blockType === "morning") {
    return { start: "09:00:00", end: "10:15:00" };
  }
  if (blockType === "afternoon") {
    return { start: "13:00:00", end: "14:15:00" };
  }
  return { start: "18:00:00", end: "19:15:00" };
}

function reorderStops(
  stops: EditableRouteStop[],
  fromId: string,
  toId: string,
): EditableRouteStop[] {
  const fromIndex = stops.findIndex((stop) => stop.id === fromId);
  const toIndex = stops.findIndex((stop) => stop.id === toId);
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) {
    return stops;
  }
  const next = [...stops];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

function moveStopAcrossTimeline(
  days: EditableRouteDay[],
  stopId: string,
  targetDay: number,
  targetBlockType: TimelineBlockType,
): EditableRouteDay[] {
  let movedStop: EditableRouteStop | null = null;
  const strippedDays = days.map((day) => {
    const index = day.stops.findIndex((stop) => stop.id === stopId);
    if (index < 0) {
      return day;
    }
    const nextStops = [...day.stops];
    const [removed] = nextStops.splice(index, 1);
    movedStop = {
      ...removed,
      day: targetDay,
      blockType: targetBlockType,
    };
    return { ...day, stops: nextStops };
  });

  if (!movedStop) {
    return days;
  }

  const finalMovedStop = movedStop;

  return strippedDays.map((day) => {
    if (day.day !== targetDay) {
      return day;
    }
    const insertionIndex = buildBlockInsertionIndex(day.stops, targetBlockType);
    const nextStops = [...day.stops];
    nextStops.splice(insertionIndex, 0, finalMovedStop);
    return { ...day, stops: nextStops };
  });
}

function buildBlockInsertionIndex(
  stops: EditableRouteStop[],
  targetBlockType: TimelineBlockType,
): number {
  const targetOrder = BLOCK_ORDER.indexOf(targetBlockType);
  let insertionIndex = stops.length;
  for (let index = 0; index < stops.length; index += 1) {
    const stopOrder = BLOCK_ORDER.indexOf(stops[index].blockType);
    if (stopOrder > targetOrder) {
      insertionIndex = index;
      break;
    }
    if (stopOrder === targetOrder) {
      insertionIndex = index + 1;
    }
  }
  return insertionIndex;
}

function originLabelForDay(
  days: EditableRouteDay[],
  dayNumber: number,
  tripOrigin: string,
): string {
  const dayIndex = days.findIndex((day) => day.day === dayNumber);
  if (dayIndex <= 0) {
    return displayableOriginName(tripOrigin);
  }
  const previousDay = days[dayIndex - 1];
  return previousDay?.stops.at(-1)?.item.name ?? displayableOriginName(tripOrigin);
}

function displayableOriginName(name: string): string {
  return isGenericPlanningAnchorName(name) ? "当前城市起点" : name;
}

function isGenericPlanningAnchorName(name: string | null | undefined): boolean {
  const normalized = (name ?? "").trim();
  return normalized === "预约" || normalized === "有安排" || normalized === "安排";
}

function sameReferenceList<T>(left: T[], right: T[]): boolean {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function buildDayRouteSummary(days: EditableRouteDay[], dayNumber: number): string {
  const day = days.find((entry) => entry.day === dayNumber);
  if (!day || day.stops.length === 0) {
    return "这一日还没有排入地点。";
  }
  const movedStops = day.stops.filter((stop) => stop.day !== stop.originalDay || stop.blockType !== stop.originalBlockType);
  const reorderedStops = day.stops.filter((stop, index) => stop.originalDay === day.day && stop.originalIndex !== index);
  if (movedStops.length > 0 || reorderedStops.length > 0) {
    const estimatedMetrics = buildEstimatedDayRouteMetrics(day);
    return `这一日已有 ${movedStops.length + reorderedStops.length} 处本地编辑，路线段已按新顺序更新${
      estimatedMetrics
        ? `，已用坐标粗估约 ${formatDurationZh(estimatedMetrics.durationSeconds)} · ${formatDistanceZh(estimatedMetrics.distanceMeters)}`
        : "，部分距离需要下一次规划时重新确认"
    }。`;
  }
  const totalDurationSeconds = day.stops.reduce((sum, stop) => sum + (stop.item.travel_duration_s ?? 0), 0);
  const totalDistanceMeters = day.stops.reduce((sum, stop) => sum + (stop.item.travel_distance_m ?? 0), 0);
  if (totalDurationSeconds <= 0 && totalDistanceMeters <= 0) {
    return "当前骨架还没有足够的路段距离数据，可以先调整顺序再继续补全。";
  }
  return `当前原始骨架里，这一天的已知衔接约 ${formatDurationZh(totalDurationSeconds)}${totalDistanceMeters > 0 ? ` · ${formatDistanceZh(totalDistanceMeters)}` : ""}。`;
}

function buildCrossDayOverviewInsights(days: EditableRouteDay[]): Array<{
  key: string;
  day: number;
  label: string;
  title: string;
  detail: string;
}> {
  if (days.length === 0) {
    return [];
  }

  const stopCounts = days.map((day) => ({
    day: day.day,
    count: day.stops.length,
  }));
  const lightestDay = [...stopCounts].sort((left, right) => left.count - right.count || left.day - right.day)[0];
  const fullestDay = [...stopCounts].sort((left, right) => right.count - left.count || left.day - right.day)[0];

  const longestTransfer = days
    .flatMap((day) =>
      day.stops.map((stop) => ({
        day: day.day,
        stopName: stop.item.name,
        fromName: stop.item.travel_from_name,
        durationSeconds: stop.item.travel_duration_s ?? 0,
        distanceMeters: stop.item.travel_distance_m ?? 0,
      })),
    )
    .filter((entry) => entry.durationSeconds > 0 || entry.distanceMeters > 0)
    .sort(
      (left, right) =>
        right.durationSeconds - left.durationSeconds ||
        right.distanceMeters - left.distanceMeters ||
        left.day - right.day,
    )[0];

  const insights: Array<{
    key: string;
    day: number;
    label: string;
    title: string;
    detail: string;
  }> = [];

  if (lightestDay) {
    insights.push({
      key: `lightest-${lightestDay.day}`,
      day: lightestDay.day,
      label: "最空",
      title: `DAY ${lightestDay.day}`,
      detail:
        lightestDay.count === 0
          ? "这一天还没有地点，最适合先补骨架。"
          : `目前只有 ${lightestDay.count} 个地点，仍有继续补点空间。`,
    });
  }

  if (fullestDay && fullestDay.day !== lightestDay?.day) {
    insights.push({
      key: `fullest-${fullestDay.day}`,
      day: fullestDay.day,
      label: "最满",
      title: `DAY ${fullestDay.day}`,
      detail: `已经排了 ${fullestDay.count} 个地点，继续加点前更值得先看节奏。`,
    });
  }

  if (longestTransfer && longestTransfer.fromName) {
    insights.push({
      key: `transfer-${longestTransfer.day}-${longestTransfer.stopName}`,
      day: longestTransfer.day,
      label: "最长衔接",
      title: `DAY ${longestTransfer.day}`,
      detail: `${longestTransfer.fromName} → ${longestTransfer.stopName} 约 ${formatDurationZh(
        longestTransfer.durationSeconds,
      )}${longestTransfer.distanceMeters > 0 ? ` · ${formatDistanceZh(longestTransfer.distanceMeters)}` : ""}。`,
    });
  }

  return insights;
}

function buildEstimatedDayRouteMetrics(
  day: EditableRouteDay,
): { distanceMeters: number; durationSeconds: number } | null {
  let distanceMeters = 0;
  let durationSeconds = 0;
  let estimatedCount = 0;

  for (let index = 1; index < day.stops.length; index += 1) {
    const segment = estimateRouteSegment(day.stops[index - 1].item, day.stops[index].item);
    if (!segment) {
      continue;
    }
    estimatedCount += 1;
    distanceMeters += segment.distanceMeters;
    durationSeconds += segment.durationSeconds;
  }

  if (estimatedCount === 0) {
    return null;
  }

  return { distanceMeters, durationSeconds };
}

function buildRoutePreviewInputs(
  days: EditableRouteDay[],
  planningAnchor: ItineraryLike["planning_anchor_source"],
  mode: RoutePreviewMode,
): RouteSegmentPreviewInput[] {
  const segments: RouteSegmentPreviewInput[] = [];
  const seen = new Set<string>();

  for (const day of days) {
    const origin = buildOriginForDay(days, day.day, planningAnchor);
    const firstStop = day.stops[0];
    if (
      firstStop &&
      typeof origin.latitude === "number" &&
      typeof origin.longitude === "number" &&
      hasCoordinates(firstStop.item)
    ) {
      const segmentKey = buildOriginRouteSegmentKey(day.day, firstStop);
      segments.push({
        segment_key: segmentKey,
        mode,
        from_name: origin.name,
        from_latitude: origin.latitude,
        from_longitude: origin.longitude,
        from_city: firstStop.item.city,
        to_name: firstStop.item.name,
        to_latitude: firstStop.item.latitude,
        to_longitude: firstStop.item.longitude,
        to_city: firstStop.item.city,
      });
      seen.add(segmentKey);
    }

    for (let index = 1; index < day.stops.length; index += 1) {
      const previousStop = day.stops[index - 1];
      const stop = day.stops[index];
      if (!hasCoordinates(previousStop.item) || !hasCoordinates(stop.item)) {
        continue;
      }
      const segmentKey = buildRouteSegmentKey(previousStop, stop);
      if (seen.has(segmentKey)) {
        continue;
      }
      seen.add(segmentKey);
      segments.push({
        segment_key: segmentKey,
        mode,
        from_name: previousStop.item.name,
        from_latitude: previousStop.item.latitude,
        from_longitude: previousStop.item.longitude,
        from_city: previousStop.item.city,
        to_name: stop.item.name,
        to_latitude: stop.item.latitude,
        to_longitude: stop.item.longitude,
        to_city: stop.item.city,
      });
    }
  }

  return segments;
}

function buildRouteSegmentKey(fromStop: EditableRouteStop, toStop: EditableRouteStop): string {
  return `${fromStop.id}->${toStop.id}`;
}

function buildOriginRouteSegmentKey(dayNumber: number, toStop: EditableRouteStop): string {
  return `origin-day-${dayNumber}->${toStop.id}`;
}

function buildOriginForDay(
  days: EditableRouteDay[],
  dayNumber: number,
  planningAnchor: ItineraryLike["planning_anchor_source"],
): { name: string; latitude?: number | null; longitude?: number | null } {
  const dayIndex = days.findIndex((day) => day.day === dayNumber);
  if (dayIndex <= 0) {
    if (isGenericPlanningAnchorName(planningAnchor.source_name)) {
      return {
        name: "当前城市起点",
        latitude: null,
        longitude: null,
      };
    }
    return {
      name: planningAnchor.source_name,
      latitude: planningAnchor.latitude,
      longitude: planningAnchor.longitude,
    };
  }
  const previousStop = days[dayIndex - 1]?.stops.at(-1);
  return {
    name: previousStop?.item.name ?? planningAnchor.source_name,
    latitude: previousStop?.item.latitude ?? planningAnchor.latitude,
    longitude: previousStop?.item.longitude ?? planningAnchor.longitude,
  };
}

function collectDayRouteSegments(
  day: EditableRouteDay,
  routePreviewMap: RoutePreviewMap,
): RouteSegmentPreviewResult[] {
  const segmentKeys: string[] = [];
  const firstStop = day.stops[0];
  if (firstStop) {
    segmentKeys.push(buildOriginRouteSegmentKey(day.day, firstStop));
  }
  for (let index = 1; index < day.stops.length; index += 1) {
    segmentKeys.push(buildRouteSegmentKey(day.stops[index - 1], day.stops[index]));
  }
  return segmentKeys
    .map((segmentKey) => routePreviewMap[segmentKey])
    .filter((segment): segment is RouteSegmentPreviewResult => Boolean(segment));
}

function hasCoordinates(
  item: ScheduledItemLike,
): item is ScheduledItemLike & { latitude: number; longitude: number } {
  return typeof item.latitude === "number" && typeof item.longitude === "number";
}

function buildSegmentLabel(
  stop: EditableRouteStop,
  previousStop: EditableRouteStop | null,
  originLabel: string,
  routePreviewMap: RoutePreviewMap,
): RouteSegmentViewModel | null {
  if (previousStop === null) {
    if (
      stop.day === stop.originalDay &&
      stop.blockType === stop.originalBlockType &&
      stop.item.travel_from_name &&
      stop.item.travel_from_name === originLabel &&
      stop.item.travel_duration_s !== null
    ) {
      return {
        label: `从 ${originLabel} 出发 · ${formatDurationZh(stop.item.travel_duration_s)}${stop.item.travel_distance_m !== null ? ` · ${formatDistanceZh(stop.item.travel_distance_m)}` : ""}`,
        status: "confirmed",
      };
    }
    return {
      label: `从 ${originLabel} 开始这一天`,
      status: "confirmed",
    };
  }

  const originalLinkStillValid =
    stop.day === stop.originalDay &&
    stop.blockType === stop.originalBlockType &&
    previousStop.day === previousStop.originalDay &&
    previousStop.blockType === previousStop.originalBlockType &&
    stop.item.travel_from_name === previousStop.item.name &&
    stop.originalIndex === previousStop.originalIndex + 1;

  if (originalLinkStillValid && stop.item.travel_duration_s !== null) {
    return {
      label: `${previousStop.item.name} -> ${stop.item.name} · ${formatDurationZh(stop.item.travel_duration_s)}${stop.item.travel_distance_m !== null ? ` · ${formatDistanceZh(stop.item.travel_distance_m)}` : ""}`,
      status: "confirmed",
    };
  }

  const previewSegment = routePreviewMap[buildRouteSegmentKey(previousStop, stop)];
  if (previewSegment) {
    const estimated = previewSegment.source.startsWith("local_estimate");
    return {
      label: `${previousStop.item.name} -> ${stop.item.name} · ${estimated ? "约 " : ""}${formatDurationZh(previewSegment.duration_s)} · ${formatDistanceZh(previewSegment.distance_m)}${estimated ? "，真实路线待恢复后校准" : ""}`,
      status: estimated ? "estimated" : "previewed",
    };
  }

  const estimatedSegment = estimateRouteSegment(previousStop.item, stop.item);
  if (estimatedSegment) {
    return {
      label: `${previousStop.item.name} -> ${stop.item.name} · 约 ${formatDurationZh(estimatedSegment.durationSeconds)} · ${formatDistanceZh(estimatedSegment.distanceMeters)}，下一次生成会用真实路线校准`,
      status: "estimated",
    };
  }

  return {
    label: `${previousStop.item.name} -> ${stop.item.name} 的衔接已改动，距离待重新计算`,
    status: "pending",
  };
}

function buildDrawerTravelLine(stop: EditableRouteStop, originLabel: string): string {
  if (
    stop.day === stop.originalDay &&
    stop.blockType === stop.originalBlockType &&
    stop.item.travel_from_name &&
    stop.item.travel_duration_s !== null
  ) {
    return `从 ${stop.item.travel_from_name} 过来约 ${formatDurationZh(stop.item.travel_duration_s)}${stop.item.travel_distance_m !== null ? `，约 ${formatDistanceZh(stop.item.travel_distance_m)}` : ""}。`;
  }
  return `这一站已经被本地调整过，当前只保留路线位置关系；起点参考 ${originLabel}。`;
}

function estimateRouteSegment(
  fromItem: ScheduledItemLike,
  toItem: ScheduledItemLike,
): { distanceMeters: number; durationSeconds: number } | null {
  if (
    typeof fromItem.latitude !== "number" ||
    typeof fromItem.longitude !== "number" ||
    typeof toItem.latitude !== "number" ||
    typeof toItem.longitude !== "number"
  ) {
    return null;
  }

  const directDistanceMeters = haversineDistanceMeters(
    fromItem.latitude,
    fromItem.longitude,
    toItem.latitude,
    toItem.longitude,
  );
  if (!Number.isFinite(directDistanceMeters) || directDistanceMeters <= 0) {
    return null;
  }

  const walkingDistanceMeters = Math.round(directDistanceMeters * 1.35);
  const walkingMetersPerSecond = 1.15;
  return {
    distanceMeters: walkingDistanceMeters,
    durationSeconds: Math.max(300, Math.round(walkingDistanceMeters / walkingMetersPerSecond)),
  };
}

function haversineDistanceMeters(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const earthRadiusMeters = 6371000;
  const toRadians = (value: number) => (value * Math.PI) / 180;
  const dLat = toRadians(lat2 - lat1);
  const dLon = toRadians(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRadians(lat1)) *
      Math.cos(toRadians(lat2)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  return earthRadiusMeters * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function buildStopBadges(stop: EditableRouteStop): string[] {
  const badges: string[] = [];
  if (stop.item.source_type === "user_seed") {
    badges.push("原始输入");
  }
  if (stop.item.source_type === "user_fixed") {
    badges.push("固定安排");
  }
  if (isRouteEditLockedStop(stop)) {
    badges.push("已锁定");
  }
  if (stop.originalDay < 0) {
    badges.push("手动插入");
  }
  if (stop.item.source_type === "auto_filled") {
    badges.push("系统补入");
  }
  if (stop.item.source_type === "auto_seeded_poi" || stop.item.source_type === "auto_seeded_meal") {
    badges.push("系统起步点");
  }
  if (stop.day !== stop.originalDay) {
    badges.push(`已移到第 ${stop.day} 天`);
  } else if (stop.blockType !== stop.originalBlockType) {
    badges.push(`改到${formatBlockLabel(stop.blockType)}`);
  }
  if (!stop.item.is_fixed && stop.item.type !== "hotel") {
    badges.push("可编辑");
  }
  return badges;
}

function describeStopRouteState(stop: EditableRouteStop): string {
  const movedDay = stop.day !== stop.originalDay;
  const movedBlock = stop.blockType !== stop.originalBlockType;
  if (movedDay && movedBlock) {
    return `这个地点已经从第 ${stop.originalDay} 天的${formatBlockLabel(stop.originalBlockType)}，挪到第 ${stop.day} 天的${formatBlockLabel(stop.blockType)}。`;
  }
  if (movedDay) {
    return `这个地点已经从第 ${stop.originalDay} 天挪到第 ${stop.day} 天，路线段需要按新日程重算。`;
  }
  if (movedBlock) {
    return `这个地点已经从${formatBlockLabel(stop.originalBlockType)}挪到${formatBlockLabel(stop.blockType)}。`;
  }
  return "这个地点还保持在原始规划位置上。";
}

function findPlaceResolution(
  parsedIntent: ParsedTripIntentLike | null | undefined,
  stopName: string,
): PlaceDisambiguationResolutionLike | null {
  const resolutions = parsedIntent?.disambiguation_summary?.place_resolutions ?? [];
  const normalizedTarget = normalizeName(stopName);
  return (
    resolutions.find(
      (resolution) =>
        normalizeName(resolution.resolved_name) === normalizedTarget ||
        normalizeName(resolution.input_name) === normalizedTarget,
    ) ?? null
  );
}

function normalizeName(value: string): string {
  return value.replace(/\s+/g, "").replace(/[（）()]/g, "").trim().toLowerCase();
}

function findActiveStop(days: EditableRouteDay[], stopId: string | null): EditableRouteStop | null {
  if (!stopId) {
    return null;
  }
  for (const day of days) {
    const found = day.stops.find((stop) => stop.id === stopId);
    if (found) {
      return found;
    }
  }
  return null;
}

function buildPoiDetailCardViewModel({
  stop,
  previousStop,
  nextStop,
  resolution,
  originLabel,
  routeState,
  poiDetail,
}: {
  stop: EditableRouteStop;
  previousStop: EditableRouteStop | null;
  nextStop: EditableRouteStop | null;
  resolution: PlaceDisambiguationResolutionLike | null;
  originLabel: string;
  routeState: string;
  poiDetail: POIDetailPreview | null;
}): PoiDetailCardViewModel {
  const resolvedName = poiDetail?.name || resolution?.resolved_name || stop.item.name;
  const trustChips = uniqueText([
    poiDetail?.rating ? `评分 ${poiDetail.rating}` : null,
    poiDetail?.business_area ?? null,
    poiDetail?.category ? formatAmapCategory(poiDetail.category) : null,
    resolution?.city ? resolution.city : stop.item.city ?? null,
    resolution?.confidence ? `解析 ${resolution.confidence}` : null,
    resolution?.source ? `来源 ${formatResolutionSource(resolution.source)}` : null,
    stop.item.source_label,
    isRouteEditLockedStop(stop) ? "已锁定" : null,
    stop.originalDay < 0 ? "手动插入" : null,
  ]).slice(0, 5);

  return {
    title: stop.item.name,
    subtitle: poiDetail?.address
      ? poiDetail.address
      : poiDetail?.business_area
        ? `${poiDetail.business_area}一带`
        : resolvedName !== stop.item.name
          ? `已匹配到 ${resolvedName}`
          : buildPoiSubtitle(stop, resolution),
    typeLabel: `${formatStopType(stop.item.type)} · 第 ${stop.day} 天 · ${formatBlockLabel(stop.blockType)}`,
    heroInitial: stop.item.name.slice(0, 1),
    heroImageUrl: poiDetail?.photo_url ?? null,
    trustChips: trustChips.length > 0 ? trustChips : ["当前路线点"],
    routeLine: buildPoiRouteLine(stop, previousStop, nextStop, originLabel),
    liveFacts: buildPoiLiveFactsViewModel(poiDetail),
    introduction: buildPoiIntroduction(stop, resolution, poiDetail),
    research: buildPoiResearchCardViewModel(stop, previousStop, nextStop, resolution, originLabel, poiDetail),
    fitBullets: buildPoiFitBullets(stop, previousStop, nextStop),
    cautionBullets: buildPoiCautionBullets(stop, previousStop, routeState),
  };
}

function buildPoiDetailCacheKey({
  name,
  city,
  latitude,
  longitude,
}: {
  name: string;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
}): string {
  return [
    name.trim().toLowerCase(),
    city?.trim().toLowerCase() ?? "",
    latitude != null ? latitude.toFixed(6) : "",
    longitude != null ? longitude.toFixed(6) : "",
  ].join("|");
}

function getCachedPoiDetailPreview(cacheKey: string): POIDetailPreview | null {
  const cached = poiDetailPreviewCache.get(cacheKey);
  if (!cached) {
    return null;
  }
  if (cached.expiresAt <= Date.now()) {
    poiDetailPreviewCache.delete(cacheKey);
    return null;
  }
  return cached.value;
}

function cachePoiDetailPreview(cacheKey: string, value: POIDetailPreview): void {
  poiDetailPreviewCache.set(cacheKey, {
    expiresAt: Date.now() + POI_DETAIL_CACHE_TTL_MS,
    value,
  });
}

function buildPoiResearchCardViewModel(
  stop: EditableRouteStop,
  previousStop: EditableRouteStop | null,
  nextStop: EditableRouteStop | null,
  resolution: PlaceDisambiguationResolutionLike | null,
  originLabel: string,
  poiDetail: POIDetailPreview | null,
): PoiResearchCardViewModel {
  if (poiDetail) {
    return {
      sourceLabel: "来自高德地点信息",
      overview: buildAmapDetailOverview(poiDetail, stop),
      accessTip: buildResearchAccessTip(stop, previousStop, originLabel),
      practicalTip: buildAmapDetailPracticalTip(poiDetail, stop),
      bestFor: buildResearchBestFor(stop, nextStop),
    };
  }

  if (stop.item.poi_research) {
    return {
      sourceLabel: formatResearchSource(stop.item.poi_research.source),
      overview: formatPlannerCopy(stop.item.poi_research.overview),
      accessTip: formatPlannerCopy(stop.item.poi_research.access_tip),
      practicalTip: formatPlannerCopy(stop.item.poi_research.practical_tip),
      bestFor: formatPlannerCopy(stop.item.poi_research.best_for),
    };
  }

  const sourceLabel = resolution?.source
    ? `来自${formatResolutionSource(resolution.source)}解析`
    : stop.item.source_reason
      ? "来自规划理由"
      : "来自当前路线";
  const overview = buildResearchOverview(stop, resolution);
  const accessTip = buildResearchAccessTip(stop, previousStop, originLabel);
  const practicalTip = buildResearchPracticalTip(stop);
  const bestFor = buildResearchBestFor(stop, nextStop);

  return {
    sourceLabel,
    overview,
    accessTip,
    practicalTip,
    bestFor,
  };
}

function formatResearchSource(source: string): string {
  if (source === "planner_completion") {
    return "来自补全逻辑";
  }
  if (source === "fixed_route_context") {
    return "来自固定安排";
  }
  if (source === "route_context") {
    return "来自路线上下文";
  }
  return source;
}

function buildAmapDetailOverview(
  detail: POIDetailPreview,
  stop: EditableRouteStop,
): string {
  const parts = uniqueText([
    detail.category ? `真实地点类型：${formatAmapCategory(detail.category)}` : null,
    detail.business_area ? `所在区域：${detail.business_area}` : null,
    detail.address ? `可定位地址：${detail.address}` : null,
  ]);
  if (parts.length > 0) {
    return parts.join("。");
  }
  return stop.item.type === "restaurant"
    ? "已匹配到真实餐饮地点，可作为当天餐食锚点继续调整。"
    : "已匹配到真实地点，可继续查看路线衔接或移动到更合适的时间段。";
}

function buildAmapDetailPracticalTip(
  detail: POIDetailPreview,
  stop: EditableRouteStop,
): string {
  const parts = uniqueText([
    detail.open_time ? `营业/开放参考：${detail.open_time}` : null,
    detail.tel ? `可提前电话确认：${detail.tel}` : null,
    detail.cost ? `人均/费用参考：${detail.cost}` : null,
  ]);
  if (parts.length > 0) {
    return parts.join("。");
  }
  if (stop.item.type === "restaurant") {
    return "餐食点建议留出排队和点餐缓冲，避免压缩后面的路线。";
  }
  return "真实地点信息已匹配，但开放时间/费用仍建议出行前再确认一次。";
}

function buildPoiLiveFactsViewModel(
  detail: POIDetailPreview | null,
): PoiLiveFactsViewModel | null {
  if (!detail) {
    return null;
  }

  const facts = [
    detail.rating ? { label: "评分", value: detail.rating } : null,
    detail.business_area ? { label: "区域", value: detail.business_area } : null,
    detail.address ? { label: "地址", value: detail.address } : null,
    detail.open_time ? { label: "开放", value: detail.open_time } : null,
    detail.cost ? { label: "费用", value: formatPoiCost(detail.cost) } : null,
    detail.tel ? { label: "电话", value: detail.tel } : null,
  ].filter((fact): fact is { label: string; value: string } => fact !== null);

  if (facts.length === 0) {
    return null;
  }

  return {
    sourceLabel: "高德实时",
    facts,
  };
}

function formatPoiCost(cost: string): string {
  const normalized = cost.trim();
  if (!normalized) {
    return normalized;
  }
  if (/^[0-9]+(?:\.[0-9]+)?$/.test(normalized)) {
    return `约 ¥${normalized}`;
  }
  return normalized;
}

function formatAmapCategory(category: string): string {
  return category
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 2)
    .join(" / ");
}

function buildResearchOverview(
  stop: EditableRouteStop,
  resolution: PlaceDisambiguationResolutionLike | null,
): string {
  if (resolution?.reason) {
    return shortenText(formatPlannerCopy(resolution.reason), 76);
  }
  if (stop.item.type === "restaurant") {
    return "这类地点更适合作为午餐或晚餐锚点，用来让当天路线有真实停顿。";
  }
  if (stop.item.type === "hotel") {
    return "住宿点会影响每天起收口和跨天移动，适合在路线骨架稳定后再确认。";
  }
  if (stop.originalDay < 0) {
    return "这是你手动插入的待规划点，下一次生成会优先尝试解析它的位置并放回路线。";
  }
  return "这是当前旅行骨架里的停留点，已经参与当天路线顺序和后续补全判断。";
}

function buildResearchAccessTip(
  stop: EditableRouteStop,
  previousStop: EditableRouteStop | null,
  originLabel: string,
): string {
  const fromName = previousStop?.item.name ?? stop.item.travel_from_name ?? originLabel;
  if (stop.item.travel_duration_s !== null && stop.item.travel_duration_s > 0) {
    const duration = formatDurationZh(stop.item.travel_duration_s);
    const distance =
      stop.item.travel_distance_m !== null && stop.item.travel_distance_m > 0
        ? `，约 ${formatDistanceZh(stop.item.travel_distance_m)}`
        : "";
    return `从 ${fromName} 过来约 ${duration}${distance}。`;
  }
  if (stop.day !== stop.originalDay || stop.blockType !== stop.originalBlockType || stop.originalDay < 0) {
    return `当前从 ${fromName} 到这里的路段需要下一次规划重算。`;
  }
  return `从 ${fromName} 进入这一站，当前没有更细的路段数据。`;
}

function buildResearchPracticalTip(stop: EditableRouteStop): string {
  if (stop.item.is_fixed) {
    return "已锁定，后续自动规划会尽量围绕它调整，不适合频繁移动。";
  }
  if (stop.item.type === "restaurant") {
    return "餐食点建议保留一定缓冲，不要把前后景点排得太紧。";
  }
  if (stop.blockType === "evening") {
    return "晚间点更适合作为收口，后面最好少接长距离转场。";
  }
  if (stop.day !== stop.originalDay || stop.blockType !== stop.originalBlockType) {
    return "已被手动调整，保存后下一次生成会重新校验距离和顺路性。";
  }
  return "如果这里感觉不顺，可以先移动到别的时间段，再让系统重新生成确认路段。";
}

function buildResearchBestFor(
  stop: EditableRouteStop,
  nextStop: EditableRouteStop | null,
): string {
  if (stop.item.type === "restaurant") {
    return nextStop
      ? `适合在去 ${nextStop.item.name} 前作为补给和休息。`
      : "适合作为当天后半段的餐食收口。";
  }
  if (stop.blockType === "morning") {
    return "适合放在上午作为当天的主要游玩起点。";
  }
  if (stop.blockType === "evening") {
    return "适合放在晚上作为轻量散步、夜景或收尾安排。";
  }
  if (nextStop) {
    return `适合和 ${nextStop.item.name} 串成同一段路线。`;
  }
  return "适合作为这一日的自由调整点。";
}

function buildPoiSubtitle(
  stop: EditableRouteStop,
  resolution: PlaceDisambiguationResolutionLike | null,
): string {
  if (resolution?.poi_type) {
    return `${resolution.poi_type}${resolution.city ? ` · ${resolution.city}` : ""}`;
  }
  if (stop.item.type === "restaurant") {
    return "餐食锚点";
  }
  if (stop.item.type === "hotel") {
    return "住宿锚点";
  }
  return "行程停留点";
}

function buildPoiIntroduction(
  stop: EditableRouteStop,
  resolution: PlaceDisambiguationResolutionLike | null,
  poiDetail: POIDetailPreview | null,
): string {
  if (poiDetail) {
    return buildAmapDetailOverview(poiDetail, stop);
  }
  if (resolution?.reason) {
    return formatPlannerCopy(resolution.reason);
  }
  if (stop.item.source_reason) {
    return formatPlannerCopy(stop.item.source_reason);
  }
  if (stop.item.placement_reason) {
    return formatPlannerCopy(stop.item.placement_reason);
  }
  if (stop.item.type === "restaurant") {
    return "这一站更适合作为餐食锚点，用来支撑当天的节奏，而不是和景点争抢普通游玩时段。";
  }
  return "这一站已经进入当前旅行骨架，后续可以继续查看路线衔接、锁定或移动到更合适的时间段。";
}

function buildPoiRouteLine(
  stop: EditableRouteStop,
  previousStop: EditableRouteStop | null,
  nextStop: EditableRouteStop | null,
  originLabel: string,
): string {
  const fromLabel = previousStop?.item.name ?? stop.item.travel_from_name ?? originLabel;
  const duration =
    stop.item.travel_duration_s !== null && stop.item.travel_duration_s > 0
      ? ` · ${formatDurationZh(stop.item.travel_duration_s)}`
      : "";
  const distance =
    stop.item.travel_distance_m !== null && stop.item.travel_distance_m > 0
      ? ` · ${formatDistanceZh(stop.item.travel_distance_m)}`
      : "";
  const nextLabel = nextStop ? `，下一站 ${nextStop.item.name}` : "，这是当天最后一站";
  return `从 ${fromLabel} 到这里${duration}${distance}${nextLabel}`;
}

function buildPoiFitBullets(
  stop: EditableRouteStop,
  previousStop: EditableRouteStop | null,
  nextStop: EditableRouteStop | null,
): string[] {
  const bullets: string[] = [];
  if (stop.item.placement_reason) {
    bullets.push(shortenText(formatPlannerCopy(stop.item.placement_reason), 54));
  }
  if (previousStop) {
    bullets.push(`接在 ${previousStop.item.name} 后面，当前路线顺序更清楚。`);
  } else {
    bullets.push(`作为第 ${stop.day} 天的开头，从当天始发地进入。`);
  }
  if (nextStop) {
    bullets.push(`后面接 ${nextStop.item.name}，方便继续调整这一段。`);
  }
  if (stop.item.type === "restaurant") {
    bullets.push("作为餐食点能让这一天更像真实出行节奏。");
  }
  return uniqueText(bullets).slice(0, 3);
}

function buildPoiCautionBullets(
  stop: EditableRouteStop,
  previousStop: EditableRouteStop | null,
  routeState: string,
): string[] {
  const bullets: string[] = [];
  if (stop.day !== stop.originalDay || stop.blockType !== stop.originalBlockType) {
    bullets.push("这站被手动移动过，距离和时长需要下一次规划重算。");
  }
  if (previousStop && stop.item.travel_duration_s === null) {
    bullets.push("当前没有可确认路段时间，保存后会作为待确认衔接。");
  }
  if (stop.item.is_fixed) {
    bullets.push("已锁定的地点会减少后续自动调整空间。");
  }
  if (stop.originalDay < 0) {
    bullets.push("这是手动插入点，下一次生成前需要后端重新解析位置。");
  }
  if (bullets.length === 0) {
    bullets.push(shortenText(routeState, 56));
  }
  return uniqueText(bullets).slice(0, 3);
}

function formatResolutionSource(source: string): string {
  if (/amap/i.test(source)) {
    return "高德";
  }
  if (/llm/i.test(source)) {
    return "智能解析";
  }
  if (/rule/i.test(source)) {
    return "规则";
  }
  return source;
}

function formatPlaceResolutionLine(resolution: PlaceDisambiguationResolutionLike): string {
  const source = formatResolutionSource(resolution.source);
  const city = resolution.city ? ` · ${resolution.city}` : "";
  const confidence =
    resolution.confidence === "high"
      ? "高置信"
      : resolution.confidence === "medium"
        ? "中置信"
        : resolution.confidence === "low"
          ? "低置信"
          : resolution.confidence;
  return `${resolution.input_name} 已解析为 ${resolution.resolved_name}${city} · ${source} · ${confidence}。`;
}

function shortenText(value: string, maxLength: number): string {
  const trimmed = value.trim();
  if (trimmed.length <= maxLength) {
    return trimmed;
  }
  return `${trimmed.slice(0, maxLength - 1)}…`;
}

function formatPlannerCopy(value: string): string {
  const trimmed = value.trim();
  const normalized = trimmed.toLocaleLowerCase();
  if (!trimmed) {
    return trimmed;
  }
  if (normalized.includes("amap identifies this as")) {
    if (normalized.includes("museum")) {
      return "已用高德地点信息确认这里偏博物馆/展馆场景，更适合放在白天的历史文化路线里。";
    }
    if (
      normalized.includes("food") ||
      normalized.includes("restaurant") ||
      normalized.includes("dining") ||
      normalized.includes("cafe")
    ) {
      return "已用高德地点信息确认这里偏餐饮/休闲场景，更适合承担午餐、晚餐或中途休息。";
    }
    if (
      normalized.includes("park") ||
      normalized.includes("scenic") ||
      normalized.includes("viewpoint")
    ) {
      return "已用高德地点信息确认这里偏景点/观景场景，适合放入当天游玩主线。";
    }
    return "已用高德地点信息校验类型与位置，后续可结合真实详情判断是否保留。";
  }
  if (
    normalized.includes("amap signals") ||
    normalized.includes("amap categorizes") ||
    normalized.includes("amap classifies") ||
    normalized.includes("amap tags") ||
    normalized.includes("amap indicates")
  ) {
    if (normalized.includes("food") || normalized.includes("dining") || normalized.includes("cafe")) {
      return "高德地点信息显示这里偏餐饮/休闲场景，因此更适合放在午后或晚间节奏里。";
    }
    if (normalized.includes("museum")) {
      return "高德地点信息显示这里偏博物馆/展馆场景，因此更适合白天安排。";
    }
    if (normalized.includes("viewpoint") || normalized.includes("waterfront")) {
      return "高德地点信息显示这里偏观景或滨水体验，因此更适合下午后段或夜间。";
    }
    if (normalized.includes("park") || normalized.includes("temple") || normalized.includes("scenic")) {
      return "高德地点信息显示这里偏景区/公园/寺庙场景，因此更适合白天游览。";
    }
    return "已用高德地点信息校验类型与位置，后续可结合真实详情判断是否保留。";
  }
  if (normalized.includes("placed here because")) {
    return "系统把它放在这里，是因为它更贴合当前时段、前后路线和你的偏好。";
  }
  if (normalized.includes("helps keep")) {
    return "这个地点用于维持当天路线节奏，之后仍可替换或移到待规划。";
  }
  if (normalized.includes("fixed in place because")) {
    return "这是你给出的固定安排，系统会优先保护它的日期和时间；如果地点本身不准确，可以在编辑模式里替换。";
  }
  if (normalized.includes("auto-filled sparse")) {
    if (normalized.includes("evening")) {
      return "系统根据当天夜间空档补入的地点，用来让晚间路线有自然收口。";
    }
    if (normalized.includes("morning")) {
      return "系统根据当天上午空档补入的地点，用来让路线从一开始就能跑起来。";
    }
    if (normalized.includes("afternoon")) {
      return "系统根据当天下午空档补入的地点，用来减少大片空白时段。";
    }
    return "系统根据当天空档补入的地点，用来让这一天的路线更完整。";
  }
  if (normalized.includes("meal-slot repair")) {
    return "系统补入的餐食锚点，用来填补用餐空档，并尽量不打断前后景点。";
  }
  if (normalized.includes("completion candidate")) {
    return "来自补全候选池，系统会根据顺路程度、时段和偏好继续校准。";
  }
  if (normalized.includes("auto-seeded from sparse city input")) {
    if (normalized.includes("meal")) {
      return "系统根据你的城市和偏好补入的餐食锚点，用来让当天节奏更完整。";
    }
    return "系统根据你的城市和偏好补入的起步地点，用来先形成可编辑路线。";
  }
  if (normalized.includes("system added this meal anchor")) {
    return "系统补入的餐食锚点，用来填补当天用餐空档。";
  }
  if (normalized.includes("system added this")) {
    return "系统补入的地点，用来让路线先跑起来，之后可以替换或移走。";
  }
  if (!/[\u3400-\u9fff]/.test(trimmed) && /[a-z]{4,}/i.test(trimmed)) {
    if (normalized.includes("museum") || normalized.includes("history") || normalized.includes("cultural")) {
      return "这是一处偏历史文化的地点，适合放在白天主线里，并与前后景点保持顺路。";
    }
    if (
      normalized.includes("food") ||
      normalized.includes("meal") ||
      normalized.includes("restaurant") ||
      normalized.includes("dining") ||
      normalized.includes("cafe")
    ) {
      return "这是一处餐食/休息锚点，用来让当天路线有真实停顿，不把景点排得过满。";
    }
    if (normalized.includes("evening") || normalized.includes("night")) {
      return "这处安排更适合晚间收口，能补足夜游或吃饭后的轻量活动。";
    }
    if (normalized.includes("route") || normalized.includes("distance") || normalized.includes("travel")) {
      return "系统根据前后路线、距离和当天节奏放入此处，后续仍可替换或移动。";
    }
    return "系统已把这个地点纳入当前路线判断，后续可以结合真实地点详情继续调整。";
  }
  return trimmed;
}

function uniqueText(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const trimmed = value?.trim();
    if (!trimmed || seen.has(trimmed)) {
      continue;
    }
    seen.add(trimmed);
    result.push(trimmed);
  }
  return result;
}

function formatStopType(type: TimelineItemType): string {
  if (type === "restaurant") {
    return "餐食";
  }
  if (type === "hotel") {
    return "住宿";
  }
  return "景点";
}

function formatBlockLabel(blockType: TimelineBlockType): string {
  if (blockType === "morning") {
    return "上午";
  }
  if (blockType === "afternoon") {
    return "下午";
  }
  return "晚上";
}

function formatTimeRange(startTime: string, endTime: string): string {
  return `${startTime.slice(0, 5)} - ${endTime.slice(0, 5)}`;
}

function formatDurationZh(durationSeconds: number): string {
  return `${Math.round(durationSeconds / 60)} 分钟`;
}

function formatDistanceZh(distanceMeters: number): string {
  if (distanceMeters >= 1000) {
    return `${(distanceMeters / 1000).toFixed(1)} km`;
  }
  return `${distanceMeters} m`;
}

function itemTone(type: TimelineItemType): string {
  if (type === "restaurant") {
    return "#8a5a00";
  }
  if (type === "hotel") {
    return "var(--ec-slate)";
  }
  return "#4f7b59";
}

const workspaceShellStyle: CSSProperties = {
  position: "relative",
  minHeight: "min(84dvh, 940px)",
  overflow: "hidden",
  borderRadius: 36,
  background:
    "radial-gradient(circle at top right, rgba(102,113,95,0.1), transparent 26%), radial-gradient(circle at bottom left, rgba(177,138,88,0.1), transparent 24%), linear-gradient(180deg, rgba(255,253,249,0.99), rgba(247,244,238,0.98))",
  border: "1px solid var(--ec-line)",
  boxShadow: "var(--ec-shadow-2)",
};

const workspaceHeaderStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  gap: 16,
  alignItems: "start",
  flexWrap: "wrap",
};

const workspaceEyebrowStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 11,
  fontWeight: 800,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const secondaryPanelTitleStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ink)",
  fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
  fontSize: 27,
  lineHeight: 1.06,
  letterSpacing: "-0.03em",
};

const secondaryPanelBodyStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 14,
  lineHeight: 1.7,
};

const overviewCardTitleStyle: CSSProperties = {
  color: "var(--ec-ink)",
  fontSize: 18,
  lineHeight: 1.2,
};

const overviewInsightTitleStyle: CSSProperties = {
  color: "var(--ec-ink)",
  fontSize: 17,
  lineHeight: 1.25,
};

const overviewInsightBodyStyle: CSSProperties = {
  color: "var(--ec-slate)",
  fontSize: 13,
  lineHeight: 1.6,
};

function secondaryMetaLabelStyle(color: string): CSSProperties {
  return {
    margin: 0,
    color,
    fontSize: 11,
    fontWeight: 900,
    letterSpacing: "0.1em",
    textTransform: "uppercase",
  };
}

const unplannedCardTitleStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ink)",
  fontSize: 20,
  lineHeight: 1.15,
};

const workspaceTitleStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ink)",
  fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
  fontSize: "clamp(1.9rem, 4vw, 2.6rem)",
  fontWeight: 700,
  letterSpacing: "-0.04em",
  lineHeight: 0.96,
};

const workspaceSubtitleStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  lineHeight: 1.6,
  maxWidth: 620,
};

const routeEditToolbarStyle: CSSProperties = {
  display: "flex",
  gap: 8,
  alignItems: "center",
  flexWrap: "wrap",
};

const routeToolbarButtonStyle: CSSProperties = {
  border: "1px solid var(--ec-line)",
  borderRadius: 999,
  padding: "8px 12px",
  background: "rgba(255,253,249,0.92)",
  color: "var(--ec-ink)",
  fontWeight: 800,
  cursor: "pointer",
};

const routeToolbarHintStyle: CSSProperties = {
  color: "var(--ec-slate)",
  fontSize: 13,
};

const overviewPanelStyle: CSSProperties = {
  display: "grid",
  gap: 18,
  padding: 18,
  borderRadius: 30,
  background:
    "radial-gradient(circle at top right, rgba(102,113,95,0.08), transparent 26%), linear-gradient(180deg, rgba(255,253,249,0.98), rgba(247,244,238,0.94))",
  border: "1px solid var(--ec-line)",
};

const overviewStatsGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(96px, 1fr))",
  gap: 8,
};

const overviewStatStyle: CSSProperties = {
  display: "grid",
  gap: 6,
  padding: 14,
  borderRadius: 20,
  background: "rgba(244,241,235,0.92)",
  color: "var(--ec-ink)",
};

function overviewHealthCardStyle(status?: string | null): CSSProperties {
  const executable = status === "executable";
  const unstable = status === "unstable";

  return {
    display: "grid",
    gap: 8,
    padding: 16,
    borderRadius: 22,
    background: executable
      ? "rgba(231,236,232,0.86)"
      : unstable
        ? "rgba(239,229,214,0.9)"
        : "rgba(247,244,238,0.96)",
    border: executable
      ? "1px solid rgba(102,113,95,0.18)"
      : unstable
        ? "1px solid rgba(177,138,88,0.22)"
        : "1px solid var(--ec-line)",
    color: "var(--ec-ink)",
  };
}

const overviewSignalsGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
  gap: 8,
};

const overviewSignalCardStyle: CSSProperties = {
  display: "grid",
  gap: 6,
  padding: 14,
  borderRadius: 20,
  background: "rgba(244,241,235,0.92)",
  color: "var(--ec-ink)",
};

const overviewLedgerStyle: CSSProperties = {
  display: "grid",
  gap: 8,
  padding: 10,
  borderRadius: 24,
  background:
    "linear-gradient(135deg, rgba(255,253,249,0.78), rgba(247,244,238,0.74))",
  border: "1px solid var(--ec-line-soft)",
};

function overviewLedgerItemStyle(tone: "intent" | "execution"): CSSProperties {
  return {
    display: "grid",
    gap: 5,
    padding: "12px 12px 12px 14px",
    borderRadius: 18,
    background: "rgba(255,253,249,0.72)",
    border: "1px solid var(--ec-line-soft)",
    borderLeft:
      tone === "intent" ? "3px solid var(--ec-ochre)" : "3px solid var(--ec-moss)",
  };
}

const overviewLedgerTitleStyle: CSSProperties = {
  color: "var(--ec-ink-soft)",
  fontSize: 14,
  lineHeight: 1.2,
};

const overviewFocusCardStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(96px, 0.28fr) minmax(0, 1fr) auto",
  gap: 12,
  alignItems: "center",
  width: "100%",
  padding: 16,
  borderRadius: 22,
  border: "1px solid var(--ec-line)",
  background: "rgba(255,253,249,0.92)",
  textAlign: "left",
  cursor: "pointer",
};

const overviewInsightGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: 8,
};

const overviewInsightCardStyle: CSSProperties = {
  display: "grid",
  gap: 7,
  padding: 14,
  borderRadius: 20,
  border: "1px solid var(--ec-line)",
  background: "rgba(255,253,249,0.94)",
  textAlign: "left",
  cursor: "pointer",
};

const overviewDayCardStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(72px, 0.25fr) minmax(0, 1fr) auto",
  gap: 12,
  alignItems: "center",
  width: "100%",
  padding: 16,
  borderRadius: 22,
  border: "1px solid var(--ec-line)",
  background: "rgba(255,253,249,0.94)",
  textAlign: "left",
  cursor: "pointer",
};

const overviewDayArrowStyle: CSSProperties = {
  color: "var(--ec-clay)",
  fontSize: 24,
  fontWeight: 700,
};

const detailDecisionSummaryStyle: CSSProperties = {
  display: "grid",
  gap: 14,
  padding: 16,
  borderRadius: 22,
  background:
    "linear-gradient(135deg, rgba(244,241,235,0.9), rgba(255,253,249,0.96))",
  border: "1px solid var(--ec-line)",
};

const plannerDetailToggleStyle: CSSProperties = {
  justifySelf: "start",
  border: "1px solid var(--ec-line)",
  borderRadius: 999,
  padding: "9px 12px",
  background: "rgba(255,253,249,0.9)",
  color: "var(--ec-slate)",
  fontWeight: 800,
  cursor: "pointer",
};

const plannerDetailPanelStyle: CSSProperties = {
  display: "grid",
  gap: 14,
  padding: 16,
  borderRadius: 22,
  background: "rgba(255,253,249,0.94)",
  border: "1px dashed rgba(21, 21, 21, 0.16)",
};

const detailReadOnlyHintStyle: CSSProperties = {
  display: "grid",
  gap: 6,
  padding: 14,
  borderRadius: 20,
  background:
    "linear-gradient(135deg, rgba(37,99,235,0.06), rgba(255,253,249,0.94))",
  border: "1px solid rgba(37,99,235,0.12)",
  color: "var(--ec-slate)",
  fontSize: 13,
  lineHeight: 1.55,
};

const doneButtonStyle: CSSProperties = {
  border: "none",
  borderRadius: 999,
  padding: "12px 18px",
  background: "var(--ec-night)",
  color: "#ffffff",
  fontWeight: 800,
  cursor: "pointer",
};

const dayTabsWrapStyle: CSSProperties = {
  display: "flex",
  gap: 10,
  overflowX: "auto",
  padding: "4px 0 14px",
  borderBottom: "1px solid rgba(37,99,235,0.08)",
};

function buildDayTabStyle(active: boolean): CSSProperties {
  return {
    borderRadius: 999,
    padding: "12px 18px",
    background: active ? "var(--ec-route-blue)" : "rgba(255,253,249,0.9)",
    color: active ? "#ffffff" : "var(--ec-ink-soft)",
    border: active ? "1px solid transparent" : "1px solid rgba(21,21,21,0.09)",
    boxShadow: active ? "0 12px 28px rgba(37,99,235,0.20)" : "none",
    fontSize: 13,
    fontWeight: 900,
    letterSpacing: active ? "0.02em" : "0",
    cursor: "pointer",
    whiteSpace: "nowrap",
  };
}

const ROUTE_MODE_CONTROL_OPTIONS: Array<{
  value: RoutePreviewMode;
  label: string;
  kicker: string;
}> = [
  { value: "walk", label: "步行", kicker: "步行优先" },
  { value: "transit", label: "公交地铁", kicker: "公共交通" },
  { value: "drive", label: "驾车", kicker: "自驾路线" },
];

function routePreviewStateText(state: "idle" | "loading" | "partial" | "failed"): string {
  if (state === "loading") {
    return "刷新中";
  }
  if (state === "partial") {
    return "含估算";
  }
  if (state === "failed") {
    return "待重试";
  }
  return "已同步";
}

const mobileMapLayerPanelStyle: CSSProperties = {
  display: "grid",
  gap: 10,
  padding: 12,
  borderRadius: 22,
  background:
    "linear-gradient(135deg, rgba(255,253,249,0.98), rgba(244,241,235,0.9))",
  border: "1px solid rgba(37,99,235,0.1)",
  boxShadow: "0 12px 28px rgba(21,21,21,0.065)",
};

const mobileMapLayerHeaderStyle: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "start",
  gap: 12,
};

const mobileMapLayerEyebrowStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-clay)",
  fontSize: 10,
  fontWeight: 900,
  letterSpacing: "0.16em",
  textTransform: "uppercase",
};

const mobileMapLayerTitleStyle: CSSProperties = {
  margin: "3px 0 0",
  color: "var(--ec-ink)",
  fontSize: 17,
  lineHeight: 1.2,
  letterSpacing: "-0.02em",
};

function mobileMapLayerStatusStyle(
  state: "idle" | "loading" | "partial" | "failed",
): CSSProperties {
  const warning = state === "partial" || state === "failed";
  return {
    flex: "0 0 auto",
    borderRadius: 999,
    padding: "7px 10px",
    background: warning ? "rgba(177,138,88,0.14)" : "rgba(102,113,95,0.12)",
    color: warning ? "var(--ec-clay)" : "var(--ec-moss)",
    fontSize: 12,
    fontWeight: 900,
  };
}

const mobileRouteModeGridStyle: CSSProperties = {
  display: "flex",
  gap: 6,
  padding: 5,
  borderRadius: 999,
  background: "rgba(18,23,34,0.055)",
  overflowX: "auto",
};

function mobileRouteModeButtonStyle(active: boolean): CSSProperties {
  return {
    flex: "1 0 120px",
    display: "grid",
    gap: 2,
    minHeight: 44,
    border: active ? "1px solid transparent" : "1px solid transparent",
    borderRadius: 999,
    padding: "8px 14px",
    background: active ? "var(--ec-route-blue)" : "transparent",
    color: active ? "#fffdfa" : "var(--ec-ink)",
    textAlign: "center",
    fontSize: 13,
    fontWeight: 900,
    cursor: "pointer",
    boxShadow: active ? "0 10px 22px rgba(37,99,235,0.22)" : "none",
  };
}

function mobileRouteModeKickerStyle(active: boolean): CSSProperties {
  return {
    color: active ? "rgba(255,253,249,0.66)" : "var(--ec-slate)",
    fontSize: 9,
    fontWeight: 900,
    letterSpacing: "0.14em",
    textTransform: "uppercase",
  };
}

const mobileDayLayerGridStyle: CSSProperties = {
  display: "flex",
  gap: 8,
  overflowX: "auto",
  paddingBottom: 2,
};

function mobileDayLayerButtonStyle(active: boolean, locked: boolean): CSSProperties {
  return {
    flex: "0 0 128px",
    display: "grid",
    gap: 2,
    minHeight: 42,
    border: active ? "1px solid rgba(37,99,235,0.3)" : "1px solid var(--ec-line-soft)",
    borderRadius: 999,
    padding: "7px 12px",
    background: active ? "rgba(37,99,235,0.08)" : "rgba(18,23,34,0.04)",
    color: active ? "var(--ec-ink)" : "var(--ec-slate)",
    textAlign: "center",
    fontSize: 13,
    fontWeight: 900,
    cursor: locked ? "default" : "pointer",
    opacity: locked ? 0.82 : 1,
  };
}

const mobileDayLayerKickerStyle: CSSProperties = {
  color: "var(--ec-slate)",
  fontSize: 10,
  fontWeight: 900,
};

const routeSummaryCardStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "minmax(108px, 0.28fr) minmax(0, 1fr)",
  alignItems: "center",
  gap: 16,
  padding: "14px 16px",
  borderRadius: 24,
  background:
    "linear-gradient(135deg, rgba(255,253,249,0.96), rgba(239,244,248,0.74))",
  border: "1px solid rgba(37,99,235,0.10)",
};

const blockRailStyle: CSSProperties = {
  display: "flex",
  gap: 10,
  overflowX: "auto",
  paddingBottom: 2,
};

const pendingComposerStyle: CSSProperties = {
  display: "grid",
  gap: 12,
  padding: 14,
  borderRadius: 22,
  background: "rgba(255,253,249,0.92)",
  border: "1px dashed rgba(21, 21, 21, 0.16)",
};

const pendingInputStyle: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  border: "1px solid var(--ec-line)",
  borderRadius: 14,
  padding: "11px 12px",
  color: "var(--ec-ink)",
  fontSize: 15,
  outline: "none",
  background: "rgba(244,241,235,0.88)",
};

const pendingControlsStyle: CSSProperties = {
  display: "flex",
  gap: 8,
  flexWrap: "wrap",
};

const pendingSelectStyle: CSSProperties = {
  border: "1px solid var(--ec-line)",
  borderRadius: 999,
  padding: "9px 10px",
  background: "rgba(255,253,249,0.92)",
  color: "var(--ec-ink-soft)",
  fontWeight: 800,
};

const unplannedPoolStyle: CSSProperties = {
  display: "grid",
  gap: 18,
  padding: 18,
  borderRadius: 30,
  background:
    "radial-gradient(circle at top right, rgba(177,138,88,0.08), transparent 28%), linear-gradient(180deg, rgba(255,253,249,0.98), rgba(247,244,238,0.94))",
  border: "1px solid var(--ec-line)",
};

const emptyUnplannedStyle: CSSProperties = {
  margin: 0,
  padding: 16,
  borderRadius: 20,
  background: "rgba(244,241,235,0.92)",
  color: "var(--ec-slate)",
  lineHeight: 1.6,
};

const unplannedStopCardStyle: CSSProperties = {
  display: "grid",
  gap: 14,
  padding: 16,
  borderRadius: 22,
  background: "rgba(255,253,249,0.96)",
  border: "1px solid var(--ec-line)",
};

const tinyPlacementButtonStyle: CSSProperties = {
  border: "1px solid var(--ec-line)",
  borderRadius: 999,
  padding: "7px 10px",
  background: "rgba(244,241,235,0.88)",
  color: "var(--ec-ink)",
  fontSize: 12,
  fontWeight: 800,
  cursor: "pointer",
};

const tinyDangerButtonStyle: CSSProperties = {
  ...tinyPlacementButtonStyle,
  color: "#9f1239",
  background: "rgba(255,241,242,0.92)",
};

const insertButtonStyle: CSSProperties = {
  border: "none",
  borderRadius: 999,
  padding: "9px 14px",
  background: "var(--ec-night)",
  color: "#ffffff",
  fontWeight: 900,
  cursor: "pointer",
};

function buildBlockTargetStyle(blockType: TimelineBlockType): CSSProperties {
  const tone = {
    morning: {
      background: "rgba(231,236,232,0.92)",
      color: "var(--ec-moss)",
    },
    afternoon: {
      background: "rgba(239,229,214,0.94)",
      color: "var(--ec-clay)",
    },
    evening: {
      background: "rgba(23,27,34,0.92)",
      color: "#ffffff",
    },
  }[blockType];
  return {
    border:
      blockType === "evening" ? "1px solid rgba(23,27,34,0.92)" : "1px solid var(--ec-line)",
    borderRadius: 999,
    padding: "10px 14px",
    background: tone.background,
    color: tone.color,
    fontWeight: 800,
    cursor: "pointer",
    whiteSpace: "nowrap",
  };
}

function segmentPillStyle(status: RouteSegmentViewModel["status"]): CSSProperties {
  return {
    display: "flex",
    flexWrap: "wrap",
    gap: 7,
    alignItems: "center",
    padding: "0 4px 0 14px",
    background: "transparent",
    border: "none",
    borderLeft: `2px solid ${segmentTone(status)}`,
    fontSize: 12,
    lineHeight: 1.45,
  };
}

function segmentLabelKickerStyle(status: RouteSegmentViewModel["status"]): CSSProperties {
  return {
    flex: "0 0 auto",
    color: segmentTone(status),
    fontSize: 11,
    fontWeight: 900,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
  };
}

function segmentLabelTextStyle(status: RouteSegmentViewModel["status"]): CSSProperties {
  return {
    minWidth: 0,
    color: segmentTone(status),
    fontSize: 12,
    fontWeight: 750,
    lineHeight: 1.45,
  };
}

function segmentTone(status: RouteSegmentViewModel["status"]): string {
  if (status === "pending") {
    return "#8a5a00";
  }
  if (status === "previewed") {
    return "var(--ec-route-blue)";
  }
  if (status === "estimated") {
    return "#3a6f9d";
  }
  return "#667985";
}

const routeStopCardStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "48px minmax(0, 1fr)",
  gap: 12,
  padding: "14px 15px",
  borderRadius: 24,
  background:
    "linear-gradient(180deg, rgba(255,253,249,0.99), rgba(248,250,252,0.88))",
  border: "1px solid rgba(21,21,21,0.085)",
  cursor: "pointer",
  boxShadow: "0 12px 26px rgba(21,21,21,0.045)",
};

const routeStopListStyle: CSSProperties = {
  display: "grid",
  gap: 16,
};

function routeStopThumbStyle(type: TimelineItemType): CSSProperties {
  const tone = {
    scenic: {
      background: "rgba(231,236,232,0.92)",
      color: "#53624e",
    },
    restaurant: {
      background: "rgba(239,229,214,0.96)",
      color: "#8b673e",
    },
    hotel: {
      background: "rgba(230,236,239,0.96)",
      color: "#576671",
    },
  }[type];
  return {
    position: "relative",
    width: 50,
    height: 50,
    borderRadius: 17,
    background: tone.background,
    color: tone.color,
    display: "grid",
    placeItems: "center",
    fontWeight: 900,
    fontSize: 16,
  };
}

const routeStopIndexBadgeStyle: CSSProperties = {
  position: "absolute",
  top: -5,
  left: -5,
  width: 21,
  height: 21,
  borderRadius: 999,
  background: "var(--ec-night)",
  color: "#ffffff",
  display: "grid",
  placeItems: "center",
  fontWeight: 900,
  fontSize: 11,
};

const routeStopBodyStyle: CSSProperties = {
  display: "grid",
  gap: 10,
  minWidth: 0,
};

const tinyMoveButtonStyle: CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: 999,
  border: "1px solid var(--ec-line)",
  background: "rgba(255,253,249,0.92)",
  color: "var(--ec-ink-soft)",
  fontWeight: 800,
  cursor: "pointer",
};

const drawerActionGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
  gap: 10,
};

const drawerSecondaryActionStyle: CSSProperties = {
  border: "1px solid var(--ec-line)",
  borderRadius: 18,
  padding: "13px 16px",
  background: "rgba(255,253,249,0.96)",
  color: "var(--ec-ink)",
  fontWeight: 900,
  cursor: "pointer",
};

const drawerDangerActionStyle: CSSProperties = {
  border: "1px solid rgba(185, 28, 28, 0.14)",
  borderRadius: 18,
  padding: "13px 16px",
  background: "rgba(254, 242, 242, 0.96)",
  color: "#991b1b",
  fontWeight: 900,
  cursor: "pointer",
};

function poiCardStyle(compact: boolean): CSSProperties {
  return {
    position: "relative",
    overflow: "hidden",
    display: "grid",
    gap: compact ? 14 : 20,
    padding: compact ? "20px 16px 16px" : "24px 20px 20px",
    borderRadius: compact ? 24 : 30,
    background:
      "linear-gradient(180deg, rgba(255,253,249,0.99) 0%, rgba(247,244,238,0.96) 100%)",
    border: "1px solid var(--ec-line)",
    boxShadow: compact ? "0 12px 30px rgba(21,21,21,0.055)" : "var(--ec-shadow-2)",
  };
}

const poiFieldNoteRuleStyle: CSSProperties = {
  position: "absolute",
  top: 0,
  right: 0,
  left: 0,
  height: 6,
  background:
    "linear-gradient(90deg, var(--ec-night) 0 24%, var(--ec-ochre) 24% 56%, var(--ec-moss) 56% 100%)",
};

function poiHeroRowStyle(compact: boolean): CSSProperties {
  return {
    display: "grid",
    gridTemplateColumns: compact ? "56px minmax(0, 1fr)" : "72px minmax(0, 1fr)",
    gap: compact ? 12 : 16,
    alignItems: "center",
  };
}

function poiThumbStyle(compact: boolean): CSSProperties {
  return {
    width: compact ? 56 : 72,
    height: compact ? 56 : 72,
    borderRadius: compact ? 16 : 20,
    display: "grid",
    placeItems: "center",
    background:
      "linear-gradient(135deg, rgba(239,229,214,0.96) 0%, rgba(231,236,232,0.94) 100%)",
    color: "var(--ec-clay)",
    fontSize: compact ? 24 : 30,
    fontWeight: 900,
  };
}

const poiTypeLabelStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 11,
  fontWeight: 900,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
};

function poiCardTitleStyle(compact: boolean): CSSProperties {
  return {
    margin: 0,
    color: "var(--ec-ink)",
    fontFamily: '"Iowan Old Style", Georgia, "Times New Roman", serif',
    fontSize: compact ? 23 : 29,
    lineHeight: 1.12,
  };
}

const poiSubtitleStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 14,
  lineHeight: 1.6,
};

const poiChipRowStyle: CSSProperties = {
  display: "flex",
  gap: 8,
  flexWrap: "wrap",
};

const poiChipStyle: CSSProperties = {
  padding: "6px 9px",
  borderRadius: 999,
  background: "rgba(231,236,232,0.96)",
  color: "var(--ec-moss)",
  fontSize: 12,
  fontWeight: 850,
};

function placeInspectorCardStyle(compact: boolean): CSSProperties {
  return {
    display: "grid",
    gap: compact ? 6 : 12,
    minHeight: 0,
  };
}

function placeInspectorRouteStyle(compact: boolean): CSSProperties {
  return {
    display: "grid",
    gap: compact ? 3 : 6,
    padding: compact ? "8px 10px" : "13px 14px",
    borderRadius: compact ? 16 : 18,
    background:
      "linear-gradient(135deg, rgba(37,99,235,0.08), rgba(255,253,249,0.92))",
    border: "1px solid rgba(37,99,235,0.13)",
    borderLeft: "4px solid var(--ec-route-blue)",
  };
}

const placeInspectorFactsStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 7,
};

function placeInspectorFactStyle(compact: boolean): CSSProperties {
  return {
    padding: compact ? "4px 7px" : "6px 9px",
    borderRadius: 999,
    background: "rgba(231,236,232,0.88)",
    color: "var(--ec-moss)",
    fontSize: compact ? 11 : 12,
    fontWeight: 850,
  };
}

function placeInspectorGridStyle(compact: boolean): CSSProperties {
  return {
    display: "grid",
    gridTemplateColumns: compact ? "repeat(2, minmax(0, 1fr))" : "repeat(auto-fit, minmax(180px, 1fr))",
    gap: compact ? 6 : 10,
  };
}

function placeInspectorNoteStyle(tone: "fit" | "caution", compact = false): CSSProperties {
  return {
    display: "grid",
    gap: compact ? 3 : 6,
    padding: compact ? "7px 9px" : "12px 13px",
    borderRadius: compact ? 15 : 18,
    background: tone === "fit" ? "rgba(231,236,232,0.66)" : "rgba(239,229,214,0.64)",
    border:
      tone === "fit"
        ? "1px solid rgba(102,113,95,0.12)"
        : "1px solid rgba(177,138,88,0.14)",
  };
}

const placeInspectorTravelStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 13,
  lineHeight: 1.55,
};

const placeInspectorLabelStyle: CSSProperties = {
  color: "var(--ec-slate)",
  fontSize: 10,
  fontWeight: 900,
  letterSpacing: "0.12em",
  textTransform: "uppercase",
};

function placeInspectorRouteTextStyle(compact: boolean): CSSProperties {
  return {
    color: "var(--ec-ink-soft)",
    fontSize: compact ? 12.5 : 14,
    lineHeight: compact ? 1.3 : 1.45,
  };
}

function placeInspectorNoteTextStyle(compact: boolean): CSSProperties {
  return {
    margin: 0,
    color: "var(--ec-ink-soft)",
    fontSize: compact ? 11.5 : 13,
    lineHeight: compact ? 1.34 : 1.52,
  };
}

const poiRouteStripStyle: CSSProperties = {
  display: "grid",
  gap: 8,
  padding: "16px 18px",
  borderRadius: 22,
  background:
    "linear-gradient(135deg, rgba(239,229,214,0.76) 0%, rgba(255,253,249,0.92) 100%)",
  border: "1px solid rgba(177,138,88,0.18)",
  borderLeft: "4px solid var(--ec-ochre)",
  color: "var(--ec-ink-soft)",
  lineHeight: 1.55,
};

const poiLiveFactsCardStyle: CSSProperties = {
  display: "grid",
  gap: 14,
  padding: 16,
  borderRadius: 22,
  background: "rgba(231,236,232,0.7)",
  border: "1px solid rgba(102, 113, 95, 0.14)",
};

const poiLiveFactsSourceStyle: CSSProperties = {
  padding: "4px 8px",
  borderRadius: 999,
  background: "rgba(231,236,232,0.96)",
  color: "var(--ec-moss)",
  fontSize: 12,
  fontWeight: 800,
};

const poiLiveFactsGridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(145px, 1fr))",
  gap: 10,
};

const poiLiveFactItemStyle: CSSProperties = {
  display: "grid",
  gap: 5,
  padding: 12,
  borderRadius: 16,
  background: "rgba(255,255,255,0.76)",
};

const poiLiveFactValueStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ink-soft)",
  fontSize: 13,
  lineHeight: 1.55,
  fontWeight: 750,
};

const poiSectionTitleStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ink)",
  fontSize: 15,
  fontWeight: 900,
};

const poiBodyTextStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ink-soft)",
  lineHeight: 1.7,
};

const researchCardStyle: CSSProperties = {
  display: "grid",
  gap: 14,
  padding: 16,
  borderRadius: 22,
  background: "rgba(255,253,249,0.92)",
  border: "1px solid var(--ec-line)",
};

const researchSourceStyle: CSSProperties = {
  padding: "4px 8px",
  borderRadius: 999,
  background: "rgba(255,253,249,0.92)",
  color: "var(--ec-slate)",
  fontSize: 12,
  fontWeight: 800,
};

function researchGridStyle(compact: boolean): CSSProperties {
  return {
    display: "grid",
    gridTemplateColumns: compact ? "minmax(0, 1fr)" : "repeat(auto-fit, minmax(150px, 1fr))",
    gap: compact ? 10 : 12,
  };
}

const researchOverviewStyle: CSSProperties = {
  display: "grid",
  gap: 6,
  paddingTop: 12,
  borderTop: "1px solid var(--ec-line)",
};

const researchLabelStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 12,
  fontWeight: 850,
};

const researchValueStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ink-soft)",
  fontSize: 13,
  lineHeight: 1.55,
};

function poiTwoColumnStyle(compact: boolean): CSSProperties {
  return {
    display: "grid",
    gridTemplateColumns: compact ? "minmax(0, 1fr)" : "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 12,
  };
}

function poiBulletBoxStyle(tone: "fit" | "caution"): CSSProperties {
  return {
    display: "grid",
    gap: 10,
    padding: 14,
    borderRadius: 20,
    background: tone === "fit" ? "rgba(231,236,232,0.72)" : "rgba(239,229,214,0.72)",
    border:
      tone === "fit"
        ? "1px solid rgba(102, 113, 95, 0.14)"
        : "1px solid rgba(177, 138, 88, 0.16)",
  };
}

const poiBulletTextStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-ink-soft)",
  lineHeight: 1.55,
  fontSize: 13,
};

const poiDetailStatusStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 13,
  lineHeight: 1.55,
  padding: "0 2px",
};

const dragHandleStyle: CSSProperties = {
  width: 30,
  height: 30,
  borderRadius: 10,
  background: "rgba(244,241,235,0.96)",
  color: "var(--ec-slate)",
  display: "grid",
  placeItems: "center",
  cursor: "grab",
  fontWeight: 900,
  letterSpacing: "-0.18em",
  userSelect: "none",
};

const stopBadgeStyle: CSSProperties = {
  padding: "5px 9px",
  borderRadius: 999,
  background: "rgba(244,241,235,0.96)",
  color: "var(--ec-slate)",
  fontSize: 11,
  fontWeight: 800,
  letterSpacing: "0.02em",
};

const drawerOverlayStyle: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(23, 27, 34, 0.28)",
  display: "grid",
  alignItems: "end",
  padding: 16,
  zIndex: 60,
};

const drawerSheetStyle: CSSProperties = {
  width: "min(760px, 100%)",
  maxHeight: "min(78dvh, 680px)",
  margin: "0 auto",
  borderRadius: "32px 32px 22px 22px",
  background:
    "radial-gradient(circle at top left, rgba(239,229,214,0.34), transparent 30%), linear-gradient(180deg, rgba(255,253,249,0.99), rgba(247,244,238,0.97))",
  padding: 22,
  display: "grid",
  gap: 20,
  overflowY: "auto",
  boxShadow: "0 28px 68px rgba(21, 21, 21, 0.2)",
};

const detailPanelStyle: CSSProperties = {
  minHeight: 0,
  height: "100%",
  maxHeight: "none",
  display: "grid",
  gridTemplateRows: "auto auto auto minmax(0, 1fr) auto",
  gap: 10,
  alignContent: "stretch",
  overflowY: "auto",
  padding: 12,
  borderRadius: 24,
  background: "linear-gradient(180deg, rgba(255,253,249,0.98), rgba(247,244,238,0.96))",
  border: "1px solid var(--ec-line)",
  boxShadow: "var(--ec-shadow-1)",
};

const detailPanelFooterStyle: CSSProperties = {
  position: "sticky",
  bottom: 0,
  display: "flex",
  flexWrap: "wrap",
  gap: 8,
  paddingTop: 10,
  background:
    "linear-gradient(180deg, rgba(247,244,238,0), rgba(247,244,238,0.96) 32%, rgba(247,244,238,0.98))",
};

const drawerCloseButtonStyle: CSSProperties = {
  border: "1px solid var(--ec-line)",
  borderRadius: 999,
  padding: "10px 14px",
  background: "rgba(255,253,249,0.9)",
  color: "var(--ec-ink-soft)",
  fontWeight: 800,
  cursor: "pointer",
};

const miniLabelStyle: CSSProperties = {
  margin: 0,
  color: "var(--ec-slate)",
  fontSize: 11,
  fontWeight: 800,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};
