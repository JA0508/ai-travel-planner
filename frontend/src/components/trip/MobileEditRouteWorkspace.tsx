"use client";

import { CSSProperties, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  RouteEditorSheet,
  type RouteEditorSheetSnap,
} from "./RouteEditorSheet";
import { RouteMapPane, type RoutePreviewMode } from "./RouteMapPane";
import { PlaceDetailPanel } from "./place-intelligence/PlaceDetailPanel";
import {
  buildNeighborStopIds,
  buildPlaceDetailViewModel,
  buildRelatedRouteSegmentKeys,
} from "./place-intelligence/placeDetailViewModel";
import { postTripJson } from "./tripApiClient";
import {
  ROUTE_WORKSPACE_BLOCK_ORDER,
  buildEditableRouteDays,
  buildManualPendingStop,
  buildRouteStopSelector,
  insertExistingStop,
  insertPendingStop,
  isRouteEditLockedStop,
  moveStopAcrossTimeline,
  reorderStops,
  sameReferenceList,
  toggleRouteStopLock,
} from "@/features/trip-workspace/routeWorkspaceEditModel";
import type { VerifiedPlaceReference } from "@/features/executable-route-preview/routePreviewModel";

export type TimelineItemType = "scenic" | "restaurant" | "hotel";
export type TimelineBlockType = "morning" | "afternoon" | "evening";

type CompletionCandidateTraceLike = {
  name: string;
  reason: string;
};

export type ScheduledItemLike = {
  stable_id?: string | null;
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
  candidate_id?: string | null;
  canonical_place_id?: string | null;
  verified_place?: VerifiedPlaceReference | null;
  travel_from_name: string | null;
  travel_distance_m: number | null;
  travel_duration_s: number | null;
  travel_data_status?: "confirmed" | "unavailable" | "estimated" | null;
  travel_provider?: string | null;
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
  meal_role?: "lunch" | "dinner" | null;
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
  focusRequest?: { day: number; requestId: number } | null;
  routePreviewEndpoint?: string;
  poiDetailEndpoint?: string;
  initialRoutePreviewMap?: RoutePreviewMap;
  poiDetailFixtures?: Record<string, POIDetailPreview>;
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

export type RouteSegmentPreviewResult = {
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

export type POIDetailPreview = {
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
  initialRoutePreviewMap,
}: {
  itinerary: ItineraryLike;
  routePreviewEndpoint?: string;
  initialRoutePreviewMap?: RoutePreviewMap;
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
  const [routePreviewMap, setRoutePreviewMap] = useState<RoutePreviewMap>(
    () => initialRoutePreviewMap ?? {},
  );
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
    setRoutePreviewMap(initialRoutePreviewMap ?? {});
    setRoutePreviewState("idle");
    setVisibleMapDays(nextDays.map((day) => day.day));
    setUnplannedStops([]);
    setShowUnplanned(false);
    setUndoStack([]);
    setRedoStack([]);
  }, [initialRoutePreviewMap, itinerary]);

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
        // A navigation can complete a proxied response after this workspace has
        // been replaced. Do not let an empty successful payload crash the route
        // surface; the itinerary remains server-authoritative without map legs.
        if (!payload) {
          setRoutePreviewState("failed");
          return;
        }
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
  focusRequest,
  routePreviewEndpoint,
  poiDetailEndpoint,
  initialRoutePreviewMap,
  poiDetailFixtures,
  desktopLeftRail,
  onApplyEdits,
  onClose,
}: MobileEditRouteWorkspaceProps) {
  const editing = mode === "edit";
  const workspace = useEditableRouteWorkspaceState({
    itinerary,
    routePreviewEndpoint,
    initialRoutePreviewMap,
  });
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

  useEffect(() => {
    const requestedDay = focusRequest?.day;
    if (!requestedDay || !editableDays.some((day) => day.day === requestedDay)) {
      return;
    }
    setSelectedDay(requestedDay);
    setShowOverview(false);
    setShowUnplanned(false);
    setActiveStopId(null);
    const frame = window.requestAnimationFrame(() => {
      document.querySelector<HTMLElement>(`[data-route-day="${requestedDay}"]`)?.focus();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [focusRequest?.day, focusRequest?.requestId]);
  const [isPanelLayout, setIsPanelLayout] = useState(false);
  const workspaceRef = useRef<HTMLElement | null>(null);
  const lastActiveStopIdRef = useRef<string | null>(null);
  const selectedNeighborStopIds = activeStop
    ? buildNeighborStopIds(activeStop, editableDays)
    : [];
  const selectedRouteSegmentKeys = activeStop
    ? buildRelatedRouteSegmentKeys(activeStop, editableDays)
    : [];
  const selectedRouteContext = activeStop
    ? buildSelectedRouteContext(activeStop, editableDays, routePreviewMap, routeMode)
    : null;

  useEffect(() => {
    if (activeStopId) {
      lastActiveStopIdRef.current = activeStopId;
      return;
    }
    const lastActiveStopId = lastActiveStopIdRef.current;
    if (!lastActiveStopId || typeof document === "undefined") {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      const target = document.querySelector<HTMLElement>(buildRouteStopSelector(lastActiveStopId));
      target?.focus();
      lastActiveStopIdRef.current = null;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activeStopId]);

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
            neighborStopIds={selectedNeighborStopIds}
            highlightedRouteSegmentKeys={selectedRouteSegmentKeys}
            selectedRouteContext={selectedRouteContext}
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
        <PlaceDetailPanelContainer
          variant="panel"
          stop={activeStop}
          allDays={editableDays}
          parsedIntent={parsedIntent}
          originLabel={originLabelForDay(
            editableDays,
            activeStop.day,
            itinerary.planning_anchor_source.source_name,
          )}
          routePreviewMap={routePreviewMap}
          routeMode={routeMode}
          poiDetailFixtures={poiDetailFixtures}
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
            setActiveStopId(null);
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
              data-route-day={day.day}
              onClick={() => {
                setSelectedDay(day.day);
                setShowUnplanned(false);
                setShowOverview(false);
                setActiveStopId(null);
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
            setActiveStopId(null);
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
            setActiveStopId(null);
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
                    data-route-stop-id={stop.id}
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
        <PlaceDetailPanelContainer
          stop={activeStop}
          allDays={editableDays}
          parsedIntent={parsedIntent}
          originLabel={originLabelForDay(
            editableDays,
            activeStop.day,
            itinerary.planning_anchor_source.source_name,
          )}
          routePreviewMap={routePreviewMap}
          routeMode={routeMode}
          poiDetailFixtures={poiDetailFixtures}
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
                  {ROUTE_WORKSPACE_BLOCK_ORDER.map((blockType) => (
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
      {ROUTE_WORKSPACE_BLOCK_ORDER.map((blockType) => {
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

export function PlaceDetailPanelContainer({
  variant = "drawer",
  stop,
  allDays,
  parsedIntent,
  originLabel,
  routePreviewMap,
  routeMode,
  poiDetailFixtures,
  poiDetailEndpoint,
  editing,
  onClose,
  onSelectStop,
  onMoveStop,
  onDeleteStop,
  onToggleLockStop,
  onMoveToUnplanned,
}: {
  variant?: "drawer" | "panel" | "roadbook";
  stop: EditableRouteStop;
  allDays: EditableRouteDay[];
  parsedIntent?: ParsedTripIntentLike | null;
  originLabel: string;
  routePreviewMap: RoutePreviewMap;
  routeMode: RoutePreviewMode;
  poiDetailFixtures?: Record<string, POIDetailPreview>;
  poiDetailEndpoint?: string;
  editing: boolean;
  onClose: () => void;
  onSelectStop?: (stopId: string) => void;
  onMoveStop: (stopId: string, targetDay: number, targetBlockType: TimelineBlockType) => void;
  onDeleteStop: (stopId: string) => void;
  onToggleLockStop: (stopId: string) => void;
  onMoveToUnplanned: (stopId: string) => void;
}) {
  const [poiDetail, setPoiDetail] = useState<POIDetailPreview | null>(null);
  const [poiDetailState, setPoiDetailState] = useState<"idle" | "loading" | "failed">("idle");
  const resolution = findPlaceResolution(parsedIntent, stop.item.name);
  const fixtureDetail = poiDetailFixtures?.[stop.id] ?? poiDetailFixtures?.[stop.item.name] ?? null;

  useEffect(() => {
    if (fixtureDetail) {
      setPoiDetail(fixtureDetail);
      setPoiDetailState("idle");
      return;
    }
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
    fixtureDetail,
    resolution?.city,
    stop.id,
    stop.item.city,
    stop.item.latitude,
    stop.item.longitude,
    stop.item.name,
  ]);

  const viewModel = buildPlaceDetailViewModel({
    stop,
    allDays,
    originLabel,
    routePreviewMap,
    routeMode,
    poiDetail,
    poiDetailState,
  });
  const panel = variant === "panel" || variant === "roadbook";
  const content = (
      <div
        data-stop-detail-panel={panel ? "panel" : "drawer"}
        style={variant === "drawer" ? drawerSheetStyle : variant === "roadbook" ? undefined : detailPanelStyle}
        onClick={(event) => event.stopPropagation()}
      >
        <PlaceDetailPanel
          viewModel={viewModel}
          onBack={onClose}
          appearance={variant === "roadbook" ? "roadbook" : "default"}
          onSelectNext={onSelectStop}
          onMoveToUnplanned={
            editing && !stop.item.is_fixed
              ? () => {
                  onMoveToUnplanned(stop.id);
                  onClose();
                }
              : undefined
          }
          onRemove={
            editing && !stop.item.is_fixed
              ? () => {
                  onDeleteStop(stop.id);
                  onClose();
                }
              : undefined
          }
        />

      </div>
  );

  if (panel) {
    return content;
  }

  return (
    <div style={drawerOverlayStyle} onClick={onClose}>
      {content}
    </div>
  );
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

function buildSelectedRouteContext(
  stop: EditableRouteStop,
  days: EditableRouteDay[],
  routePreviewMap: RoutePreviewMap,
  routeMode: RoutePreviewMode,
): string {
  const day = days.find((entry) => entry.day === stop.day) ?? null;
  const stopIndex = day?.stops.findIndex((candidate) => candidate.id === stop.id) ?? -1;
  if (!day || stopIndex < 0) {
    return routePreviewModeLabel(routeMode);
  }
  const previousStop = stopIndex > 0 ? day.stops[stopIndex - 1] : null;
  const nextStop = stopIndex < day.stops.length - 1 ? day.stops[stopIndex + 1] : null;
  const inboundSeconds =
    previousStop && routePreviewMap[buildRouteSegmentKey(previousStop, stop)]
      ? routePreviewMap[buildRouteSegmentKey(previousStop, stop)].duration_s
      : stop.item.travel_duration_s;
  const outboundSeconds =
    nextStop && routePreviewMap[buildRouteSegmentKey(stop, nextStop)]
      ? routePreviewMap[buildRouteSegmentKey(stop, nextStop)].duration_s
      : nextStop?.item.travel_from_name === stop.item.name
        ? nextStop.item.travel_duration_s
        : null;
  const routeParts = [
    inboundSeconds !== null && inboundSeconds !== undefined
      ? `${formatDurationZh(inboundSeconds)} from previous`
      : null,
    outboundSeconds !== null && outboundSeconds !== undefined
      ? `${formatDurationZh(outboundSeconds)} to next`
      : null,
  ].filter((part): part is string => part !== null);
  return routeParts.length ? routeParts.join(" · ") : routePreviewModeLabel(routeMode);
}

function routePreviewModeLabel(mode: RoutePreviewMode): string {
  if (mode === "transit") {
    return "公交地铁预览";
  }
  if (mode === "drive") {
    return "驾车预览";
  }
  return "步行预览";
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
