"use client";

import React, { useEffect, useMemo } from "react";
import {
  PlaceDetailPanelContainer,
  type ItineraryLike,
  type ScheduledItemLike,
  useEditableRouteWorkspaceState,
} from "@/components/trip/MobileEditRouteWorkspace";
import { RouteMapPane } from "@/components/trip/RouteMapPane";
import {
  buildNeighborStopIds,
  buildRelatedRouteSegmentKeys,
} from "@/components/trip/place-intelligence/placeDetailViewModel";
import { TRIP_API_ENDPOINTS } from "@/components/trip/tripRuntimeConfig";
import {
  formatDistance,
  formatMinutes,
  type DayLoad,
  type RoutePreviewItinerary,
  type RoutePreviewItem,
} from "./routePreviewModel";
import { isSafeReplaceEligible } from "./safeReplaceModel";

type Props = {
  itinerary: RoutePreviewItinerary;
  destination?: string | null;
  loads: DayLoad[];
  canRepair: boolean;
  repairStatus: "idle" | "previewing" | "review" | "applying" | "undoing" | "applied" | "restored" | "error";
  repairDay?: number;
  onRelaxDay: (day: number) => void;
  replaceControlStatus: "available" | "choosing" | "processing" | "applied" | "attention";
  focusedStopId?: string;
  onReplaceStop: (item: RoutePreviewItem) => void;
};

export function SavedLivingRoadbook({
  itinerary,
  destination,
  loads,
  canRepair,
  repairStatus,
  repairDay,
  onRelaxDay,
  replaceControlStatus,
  focusedStopId,
  onReplaceStop,
}: Props) {
  const workspaceItinerary = useMemo(() => toWorkspaceItinerary(itinerary), [itinerary]);
  const workspace = useEditableRouteWorkspaceState({
    itinerary: workspaceItinerary,
    routePreviewEndpoint: TRIP_API_ENDPOINTS.previewRouteSegments,
  });
  const {
    activeStop,
    activeStopId,
    editableDays,
    handleRouteModeChange,
    handleShowAllMapDays,
    handleToggleMapDayVisibility,
    mapOrigin,
    routeMode,
    routePreviewMap,
    routePreviewState,
    selectedDay,
    selectedDaySegments,
    selectedDayView,
    setActiveStopId,
    setSelectedDay,
    visibleMapDays,
  } = workspace;

  useEffect(() => {
    const day = editableDays.find((entry) => entry.day === selectedDay) ?? editableDays[0];
    if (!day?.stops.length) return;
    if (!activeStop || activeStop.day !== day.day) {
      setActiveStopId(day.stops[0].id);
    }
  }, [activeStop, editableDays, selectedDay, setActiveStopId]);

  useEffect(() => {
    if (!focusedStopId || activeStopId === focusedStopId) return;
    const focused = editableDays.flatMap((day) => day.stops).find((stop) => stop.id === focusedStopId);
    if (!focused) return;
    setSelectedDay(focused.day);
    setActiveStopId(focused.id);
  }, [activeStopId, editableDays, focusedStopId]);

  const selectedNeighborStopIds = activeStop
    ? buildNeighborStopIds(activeStop, editableDays)
    : [];
  const selectedRouteSegmentKeys = activeStop
    ? buildRelatedRouteSegmentKeys(activeStop, editableDays)
    : [];
  const selectedLoad = loads.find((load) => load.day === selectedDay) ?? null;
  const selectedMealDay = itinerary.meal_rhythm?.days.find((day) => day.day === selectedDay) ?? null;
  const hasSafeReplacement = editableDays.some((day) => day.stops.some((stop) => isSafeReplaceEligible(stop.item)));
  const hasRelaxableDay = canRepair && loads.some((load) => load.pace === "rushed" || load.pace === "infeasible");
  const adjustmentGuide = buildRoadbookAdjustmentGuide({ hasSafeReplacement, hasRelaxableDay });
  const city = destination
    ?? editableDays.flatMap((day) => day.stops).find((stop) => stop.item.city)?.item.city
    ?? "这次旅行";
  const totalStops = editableDays.reduce((total, day) => total + day.stops.length, 0);
  const selectedRouteContext = activeStop ? routeContext(activeStop.item) : null;
  const activeStopIndex = activeStop && selectedDayView
    ? selectedDayView.stops.findIndex((stop) => stop.id === activeStop.id)
    : -1;
  const nextStop = activeStopIndex >= 0 ? selectedDayView?.stops[activeStopIndex + 1] ?? null : null;

  function selectDay(dayNumber: number) {
    const day = editableDays.find((entry) => entry.day === dayNumber);
    setSelectedDay(dayNumber);
    setActiveStopId(day?.stops[0]?.id ?? null);
  }

  return (
    <div className="roadbook" data-roadbook-layout="living">
      <header className="roadbook__masthead">
        <div>
          <p>LIVING ROADBOOK / SAVED ROUTE</p>
          <h1>{city}</h1>
          <span>这份行程已保存为正式路线 · {itinerary.trip_days} DAYS · {totalStops} STOPS · 可继续查看路线</span>
          <p className="roadbook__sr-only" role="status" aria-live="polite">
            行程已保存为正式路线。可继续查看路线。
          </p>
        </div>
        <nav aria-label="选择行程日期">
          {editableDays.map((day) => (
            <button
              key={day.day}
              type="button"
              aria-pressed={selectedDay === day.day}
              onClick={() => selectDay(day.day)}
            >
              <span>DAY</span>
              <strong>{String(day.day).padStart(2, "0")}</strong>
            </button>
          ))}
        </nav>
      </header>

      <div className="roadbook__day-intro">
        <div>
          <p>DAY {String(selectedDay).padStart(2, "0")} / ON THE ROAD</p>
          <h2>{dayTitle(selectedDayView?.stops[0]?.item.name, selectedDayView?.stops.at(-1)?.item.name)}</h2>
        </div>
        <p>{selectedLoad?.explanation ?? "按时间线查看停留点、移动路段和已经留好的安排。"}</p>
      </div>

      <aside className="roadbook__entry-guide" aria-label="阅读路线提示">
        <p>ROUTE GUIDE</p>
        <strong>正在查看第 {selectedDay} 天</strong>
        <div>
          <span>点击时间线中的地点，即可切换当前地点；地图区域会同步显示可用的路线信息。</span>
          <small>{adjustmentGuide}</small>
        </div>
      </aside>

      <div className="roadbook__mobile-current" aria-label="当前和下一站">
        <div><span>当前</span><strong>{activeStop?.item.name ?? selectedDayView?.stops[0]?.item.name ?? "待规划"}</strong></div>
        <i aria-hidden="true">→</i>
        <div><span>下一站</span><strong>{nextStop?.item.name ?? "当天收口"}</strong></div>
      </div>
      <p className="roadbook__sr-only" aria-live="polite">
        {activeStop ? `已选择 ${activeStop.item.name}` : "当前日期还没有可查看的地点"}
      </p>

      <div className="roadbook__layout">
        <section className="roadbook__timeline" aria-label={`第 ${selectedDay} 天路线`}>
          <div className="roadbook__route-line" aria-hidden="true" />
          {selectedDayView?.stops.map((stop, index) => (
            <div className="roadbook__route-unit" key={stop.id}>
              {stop.item.travel_from_name ? <RoadbookLeg item={stop.item} /> : null}
              <button
                type="button"
                className={`roadbook-stop ${activeStopId === stop.id ? "is-selected" : ""} ${stop.item.is_fixed ? "is-fixed" : ""}`}
                data-roadbook-stop={stop.id}
                data-route-stop-id={stop.id}
                aria-pressed={activeStopId === stop.id}
                onClick={() => setActiveStopId(stop.id)}
              >
                <time>{shortTime(stop.item.start_time)}</time>
                <span className="roadbook-stop__node">{String(index + 1).padStart(2, "0")}</span>
                <span className="roadbook-stop__copy">
                  <span className="roadbook-stop__meta">
                    {stop.item.is_fixed ? "LOCKED" : stopLabel(stop.item)}
                  </span>
                  <strong>{stop.item.name}</strong>
                  <small>{userFacingPlacementReason(stop.item)}</small>
                  {stop.item.is_fixed ? (
                    <span className="roadbook-stop__locked">
                      <b>已经留好的时间</b>
                      <i>不会被随意移动</i>
                    </span>
                  ) : null}
                </span>
              </button>
            </div>
          ))}

          {selectedMealDay?.field_notes.map((note) => (
            <RoadbookMealNote key={note} note={note} />
          ))}

          <RoadbookDayNote
            load={selectedLoad}
            canRepair={canRepair}
            busy={repairStatus === "previewing" || repairStatus === "applying" || repairStatus === "undoing"}
            previewing={repairStatus === "previewing" && repairDay === selectedDay}
            onRelax={() => onRelaxDay(selectedDay)}
          />
        </section>

        <aside className="roadbook__context" aria-label="路线地图与地点详情">
          <div className="roadbook__map-heading">
            <p>LIVE ROUTE / DAY {String(selectedDay).padStart(2, "0")}</p>
            <span>{activeStop ? `正在看 ${activeStop.item.name}` : "选择一个地点查看路线位置"}</span>
          </div>
          <div className="roadbook__map-frame">
            <RouteMapPane
              appearance="roadbook"
              origin={mapOrigin}
              stops={selectedDayView?.stops ?? []}
              ghostStops={editableDays
                .filter((day) => day.day !== selectedDay && visibleMapDays.includes(day.day))
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
              onSelectStop={setActiveStopId}
            />
          </div>
          {activeStop ? (
            <>
              <PlaceDetailPanelContainer
                variant="roadbook"
                stop={activeStop}
                allDays={editableDays}
                originLabel={mapOrigin.name}
                routePreviewMap={routePreviewMap}
                routeMode={routeMode}
                poiDetailEndpoint={TRIP_API_ENDPOINTS.previewPoiDetail}
                editing={false}
                onClose={() => setActiveStopId(selectedDayView?.stops[0]?.id ?? null)}
                onSelectStop={setActiveStopId}
                onMoveStop={() => undefined}
                onDeleteStop={() => undefined}
                onToggleLockStop={() => undefined}
                onMoveToUnplanned={() => undefined}
              />
              <RoadbookReplaceEntry
                item={activeStop.item}
                controlStatus={replaceControlStatus}
                onReplace={() => onReplaceStop(activeStop.item)}
              />
            </>
          ) : (
            <div className="roadbook__selection-note">
              <p>FIELD NOTE</p>
              <strong>选择时间线中的地点</strong>
              <span>地图会聚焦到它，并一起显示相邻路线与可验证的地点信息。</span>
            </div>
          )}
        </aside>
      </div>

      <RoadbookStyles />
    </div>
  );
}

function RoadbookLeg({ item }: { item: ScheduledItemLike }) {
  const confirmed = item.travel_data_status === "confirmed" && item.travel_duration_s != null;
  return (
    <div className={`roadbook-leg ${confirmed ? "is-confirmed" : "is-unconfirmed"}`}>
      <span aria-hidden="true">│</span>
      <p>
        {confirmed
          ? `${formatMinutes(Math.round(item.travel_duration_s! / 60))}${item.travel_distance_m != null ? ` · ${formatDistance(item.travel_distance_m)}` : ""}`
          : "这段路线还没有确认"}
      </p>
      <small>{confirmed ? `${item.travel_from_name} → ${item.name} · 路线已确认` : "不会把缺失的路程当作 0 分钟"}</small>
    </div>
  );
}

function RoadbookDayNote({
  load,
  canRepair,
  busy,
  previewing,
  onRelax,
}: {
  load: DayLoad | null;
  canRepair: boolean;
  busy: boolean;
  previewing: boolean;
  onRelax: () => void;
}) {
  const tight = load?.pace === "rushed" || load?.pace === "infeasible";
  return (
    <aside className={`roadbook-day-note ${tight ? "is-tight" : ""}`}>
      <p>DAY {String(load?.day ?? 1).padStart(2, "0")} / {tight ? "A LITTLE TIGHT" : "FIELD NOTE"}</p>
      <h3>{tight ? "今天稍微赶了一点。" : "想走得更松一点？"}</h3>
      <span>
        {load
          ? `${load.activityCount} 个停留点 · 路上约 ${formatMinutes(load.travelMinutes)}`
          : "可以先查看路线，再决定是否做局部调整。"}
      </span>
      {tight && canRepair ? (
        <button type="button" data-roadbook-relax-day={load?.day} onClick={onRelax} disabled={busy}>
          {previewing ? "正在看看怎么把这一天松一点…" : busy ? "正在保存路线…" : "帮我松一点"} {!busy ? <i aria-hidden="true">→</i> : null}
        </button>
      ) : null}
    </aside>
  );
}

function RoadbookMealNote({ note }: { note: string }) {
  const meal = note.startsWith("午饭") ? "午饭" : "晚饭";
  return (
    <aside className="roadbook-meal-note" data-meal-gap="true">
      <p>DAY ROUTE / MEAL NOTE</p>
      <h3>{meal}还没找到合适的位置。</h3>
      <span>{note}</span>
    </aside>
  );
}

function toWorkspaceItinerary(itinerary: RoutePreviewItinerary): ItineraryLike {
  return {
    planning_anchor_source: itinerary.planning_anchor_source ?? {
      source_type: "saved_itinerary",
      source_name: "当天起点",
    },
    days: itinerary.days.map((day) => ({
      day: day.day,
      blocks: day.blocks.map((block) => ({
        block_type: block.block_type,
        start_time: block.start_time,
        end_time: block.end_time,
        items: block.items.map(toScheduledItem),
      })),
    })),
  };
}

function toScheduledItem(item: RoutePreviewItem): ScheduledItemLike {
  return {
    stable_id: item.stable_id,
    name: item.name,
    type: item.type,
    city: item.city,
    latitude: item.latitude,
    longitude: item.longitude,
    start_time: item.start_time,
    end_time: item.end_time,
    is_fixed: item.is_fixed,
    placement_reason: item.placement_reason ?? null,
    source_type: item.source_type,
    source_label: item.source_label,
    source_reason: item.source_reason,
    candidate_id: item.candidate_id,
    canonical_place_id: item.canonical_place_id,
    verified_place: item.verified_place,
    travel_from_name: item.travel_from_name ?? null,
    travel_distance_m: item.travel_distance_m ?? null,
    travel_duration_s: item.travel_duration_s ?? null,
    travel_data_status: item.travel_data_status,
    travel_provider: item.travel_provider,
    poi_research: item.poi_research,
    meal_role: item.meal_role,
  } as ScheduledItemLike;
}

function RoadbookReplaceEntry({
  item,
  controlStatus,
  onReplace,
}: {
  item: ScheduledItemLike;
  controlStatus: "available" | "choosing" | "processing" | "applied" | "attention";
  onReplace: () => void;
}) {
  const eligible = isSafeReplaceEligible(item);
  const controlLabel = {
    available: "换一个",
    choosing: "选择中",
    processing: "正在处理…",
    applied: "刚刚换好",
    attention: "查看提示",
  }[controlStatus];
  return (
    <section className={`roadbook-replace-entry ${eligible ? "is-eligible" : "is-protected"}`}>
      <div>
        <p>LOCAL CONTROL / ONE STOP ONLY</p>
        <strong>{eligible ? "这一站还有几个更合适的选择。" : protectedReplaceMessage(item)}</strong>
        {eligible ? <span>只换这一站，前后路线会先重新检查。</span> : null}
      </div>
      {eligible ? (
        <button type="button" onClick={onReplace} disabled={controlStatus !== "available"}>
          {controlLabel} {controlStatus === "available" ? <i aria-hidden="true">→</i> : null}
        </button>
      ) : null}
    </section>
  );
}

export function buildRoadbookAdjustmentGuide({
  hasSafeReplacement,
  hasRelaxableDay,
}: {
  hasSafeReplacement: boolean;
  hasRelaxableDay: boolean;
}): string {
  if (hasSafeReplacement && hasRelaxableDay) {
    return "如需调整：可检查一站的安全替换，或放松偏紧的一天。";
  }
  if (hasSafeReplacement) {
    return "如需调整：可先检查一站是否有安全替换。";
  }
  if (hasRelaxableDay) {
    return "如需调整：可请求放松偏紧的一天；已经留好的时间不会移动。";
  }
  return "当前没有需要调整的项目；已明确的安排会按原计划保留。";
}

function protectedReplaceMessage(item: ScheduledItemLike): string {
  if (item.is_fixed || item.source_type === "user_fixed" || item.source_label === "必去" || item.source_type === "user_seed") {
    return "这个地点是你明确保留的安排，目前不会被自动替换。";
  }
  return "这个地点还没有完成身份确认，暂时不会被替换。";
}

function dayTitle(firstName?: string, lastName?: string): string {
  if (!firstName) return "今天还没有停留点";
  if (!lastName || firstName === lastName) return `从 ${firstName} 开始`;
  return `${firstName} → ${lastName}`;
}

function stopLabel(item: ScheduledItemLike): string {
  if (item.meal_role === "lunch") return "LUNCH / 午饭";
  if (item.meal_role === "dinner") return "DINNER / 晚饭";
  if (item.source_type === "auto_seeded_poi" || item.source_type === "auto_seeded_meal" || item.source_type === "auto_filled") return "ROUTE NOTE / 系统补充";
  if (item.source_label === "必去") return "MUST GO / 必去";
  if (item.type === "restaurant") return "MEAL / 餐食";
  if (item.type === "hotel") return "STAY / 住宿";
  return "STOP / 行程地点";
}

function userFacingPlacementReason(item: ScheduledItemLike): string {
  if (item.meal_role && item.source_reason) return item.source_reason;
  const reason = item.placement_reason?.trim();
  if (reason && /[\u3400-\u9fff]/.test(reason)) return reason;
  if (item.is_fixed) return "这段时间已经为你留好，会按原计划保留。";
  if (item.source_label === "必去" || item.source_type === "user_seed") {
    return "这是你明确想去的地点，已放入当天路线。";
  }
  if (item.source_type === "auto_seeded_poi" || item.source_type === "auto_seeded_meal" || item.source_type === "auto_filled") {
    return "系统结合当天节奏和相邻地点，将它安排在这里。";
  }
  return "已按当天时间顺序放入路线。";
}

function shortTime(value: string): string {
  return value.slice(0, 5);
}

function routeContext(item: ScheduledItemLike): string {
  if (item.travel_data_status === "confirmed" && item.travel_duration_s != null) {
    return `${formatMinutes(Math.round(item.travel_duration_s / 60))} · 路线已确认`;
  }
  return "相邻路线待确认";
}

function RoadbookStyles() {
  return <style>{`
    .roadbook{--roadbook-paper:#faf6f0;--roadbook-paper-deep:#eee8df;--roadbook-ink:#171613;--roadbook-muted:#716a62;--roadbook-line:rgba(23,22,19,.18);--roadbook-orange:#e65a28;--roadbook-moss:#5f6859;display:grid;gap:0;margin:0 0 44px;border-top:1px solid var(--roadbook-ink);background:var(--roadbook-paper);color:var(--roadbook-ink)}
    .roadbook__masthead{display:flex;justify-content:space-between;align-items:end;gap:28px;padding:28px 0;border-bottom:1px solid var(--roadbook-line)}.roadbook__masthead p,.roadbook__day-intro>div>p,.roadbook__map-heading p,.roadbook-day-note>p,.roadbook__selection-note p{margin:0;color:var(--roadbook-orange);font-size:10px;font-weight:900;letter-spacing:.15em}.roadbook__masthead h1{margin:6px 0 4px;font-family:"Arial Narrow","Avenir Next Condensed","Noto Sans SC",sans-serif;font-size:58px;line-height:.88;letter-spacing:0}.roadbook__masthead>div>span{color:var(--roadbook-muted);font-size:11px;font-weight:800;letter-spacing:.08em}.roadbook__masthead nav{display:flex;align-items:stretch}.roadbook__masthead nav button{display:grid;min-width:68px;border:0;border-left:1px solid var(--roadbook-line);background:transparent;padding:7px 15px;text-align:left;color:var(--roadbook-muted);cursor:pointer}.roadbook__masthead nav button span{font-size:9px;font-weight:900;letter-spacing:.12em}.roadbook__masthead nav button strong{font-size:24px;line-height:1}.roadbook__masthead nav button[aria-pressed=true]{background:var(--roadbook-orange);color:#fff}.roadbook__masthead nav button:focus-visible,.roadbook-stop:focus-visible,.roadbook-day-note button:focus-visible{outline:3px solid rgba(230,90,40,.38);outline-offset:3px}
    .roadbook__day-intro{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,.45fr);gap:34px;align-items:end;padding:35px 0 26px}.roadbook__day-intro h2{max-width:760px;margin:9px 0 0;font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:42px;line-height:1.02}.roadbook__day-intro>p{margin:0;color:var(--roadbook-muted);font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:16px;line-height:1.65}.roadbook__entry-guide{display:grid;grid-template-columns:110px minmax(0,1fr) minmax(260px,.65fr);gap:16px;align-items:baseline;border-top:1px solid var(--roadbook-line);padding:13px 0 15px}.roadbook__entry-guide p{margin:0;color:var(--roadbook-orange);font-size:10px;font-weight:900;letter-spacing:.15em}.roadbook__entry-guide strong{font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:17px}.roadbook__entry-guide div{display:grid;gap:5px}.roadbook__entry-guide span{color:var(--roadbook-muted);font-size:12px;line-height:1.5}.roadbook__entry-guide small{color:var(--roadbook-moss);font-size:11px;line-height:1.45}
    .roadbook__sr-only{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);clip-path:inset(50%);white-space:nowrap}
    .roadbook__mobile-current{display:none}.roadbook__layout{display:grid;grid-template-columns:minmax(0,.9fr) minmax(520px,1.1fr);border-top:1px solid var(--roadbook-line);border-bottom:1px solid var(--roadbook-line)}.roadbook__timeline{position:relative;min-width:0;padding:10px 46px 42px 8px;border-right:1px solid var(--roadbook-line)}.roadbook__route-line{position:absolute;top:32px;bottom:210px;left:116px;width:2px;background:var(--roadbook-orange);transform-origin:top;animation:roadbook-route-reveal 480ms ease-out both}.roadbook__route-unit{position:relative}.roadbook-leg{display:grid;grid-template-columns:22px minmax(0,1fr);gap:0;margin-left:100px;padding:16px 0 12px;color:var(--roadbook-muted)}.roadbook-leg>span{grid-row:1/3;color:var(--roadbook-orange);font-size:28px;line-height:.75}.roadbook-leg p{margin:0;font-size:12px;font-weight:900}.roadbook-leg small{font-size:10px;line-height:1.45}.roadbook-leg.is-unconfirmed p{color:#965b3e}.roadbook-stop{position:relative;display:grid;grid-template-columns:84px 42px minmax(0,1fr);gap:12px;width:100%;border:0;border-top:1px solid var(--roadbook-line);background:transparent;padding:23px 0;text-align:left;color:inherit;cursor:pointer;transition:background 170ms ease,transform 170ms ease}.roadbook-stop time{padding-top:7px;color:var(--roadbook-muted);font-size:13px;font-weight:900}.roadbook-stop__node{position:relative;z-index:1;display:grid;width:38px;height:38px;place-items:center;border:2px solid var(--roadbook-paper);border-radius:50%;background:var(--roadbook-orange);color:#fff;font-size:11px;font-weight:900;box-shadow:0 0 0 1px var(--roadbook-orange)}.roadbook-stop__copy{display:grid;gap:6px;padding-right:10px}.roadbook-stop__meta{color:var(--roadbook-orange);font-size:9px;font-weight:900;letter-spacing:.13em}.roadbook-stop__copy>strong{font-family:"Arial Narrow","Avenir Next Condensed","Noto Sans SC",sans-serif;font-size:28px;line-height:1}.roadbook-stop__copy>small{max-width:440px;color:var(--roadbook-muted);font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:14px;line-height:1.55}.roadbook-stop.is-selected{background:rgba(230,90,40,.07);transform:translateX(6px)}.roadbook-stop.is-selected .roadbook-stop__node{background:var(--roadbook-ink);box-shadow:0 0 0 1px var(--roadbook-ink)}.roadbook-stop.is-fixed{border-top:2px solid var(--roadbook-ink);border-bottom:2px solid var(--roadbook-ink);margin:5px 0}.roadbook-stop.is-fixed .roadbook-stop__node{background:var(--roadbook-ink);box-shadow:0 0 0 1px var(--roadbook-ink)}.roadbook-stop__locked{display:flex;flex-wrap:wrap;gap:7px 12px;align-items:center;margin-top:5px;color:var(--roadbook-ink)}.roadbook-stop__locked b{background:var(--roadbook-ink);color:#fff;padding:4px 7px;font-size:9px;letter-spacing:.1em}.roadbook-stop__locked i{font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:12px;font-style:normal}
    .roadbook-day-note,.roadbook-meal-note{display:grid;gap:8px;margin:34px 0 0 100px;border-top:3px solid var(--roadbook-orange);padding:18px 0 0}.roadbook-day-note h3,.roadbook-meal-note h3{margin:0;font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:25px}.roadbook-day-note>span,.roadbook-meal-note>span{color:var(--roadbook-muted);font-size:12px;line-height:1.6}.roadbook-meal-note{border-top-color:#171613}.roadbook-meal-note>p{margin:0;color:var(--roadbook-orange);font-size:10px;font-weight:900;letter-spacing:.15em}.roadbook-day-note button{justify-self:start;border:0;border-bottom:1px solid currentColor;background:transparent;padding:7px 0;color:var(--roadbook-ink);font:inherit;font-size:13px;font-weight:900;cursor:pointer}.roadbook-day-note button i{margin-left:9px;color:var(--roadbook-orange);font-style:normal}.roadbook-day-note button:disabled{opacity:.55;cursor:wait}
    .roadbook__context{display:grid;align-content:start;min-width:0;background:var(--roadbook-paper-deep)}.roadbook__map-heading{display:flex;justify-content:space-between;gap:22px;padding:15px 18px;border-bottom:1px solid var(--roadbook-line)}.roadbook__map-heading span{overflow:hidden;color:var(--roadbook-muted);font-size:11px;font-weight:800;text-overflow:ellipsis;white-space:nowrap}.roadbook__map-frame{position:relative;min-height:470px;border-bottom:1px solid var(--roadbook-line)}.roadbook__selection-note{display:grid;gap:8px;min-height:240px;align-content:center;padding:28px}.roadbook__selection-note strong{font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:26px}.roadbook__selection-note span{max-width:430px;color:var(--roadbook-muted);line-height:1.6}.roadbook-replace-entry{display:flex;justify-content:space-between;align-items:center;gap:24px;border-bottom:1px solid var(--roadbook-line);padding:20px 24px;background:#f8f3eb}.roadbook-replace-entry>div{display:grid;gap:5px}.roadbook-replace-entry p{margin:0;color:var(--roadbook-orange);font-size:9px;font-weight:900;letter-spacing:.12em}.roadbook-replace-entry strong{font-family:"Iowan Old Style","Songti SC",Georgia,serif;font-size:16px}.roadbook-replace-entry span{color:var(--roadbook-muted);font-size:11px}.roadbook-replace-entry>button{flex:0 0 auto;border:0;border-bottom:1px solid currentColor;background:transparent;padding:8px 0;color:var(--roadbook-ink);font:inherit;font-size:13px;font-weight:900;cursor:pointer}.roadbook-replace-entry>button i{margin-left:8px;color:var(--roadbook-orange);font-style:normal}.roadbook-replace-entry>button:disabled{opacity:.5;cursor:wait}.roadbook-replace-entry.is-protected{border-left:3px solid var(--roadbook-ink)}
    @keyframes roadbook-route-reveal{from{transform:scaleY(0)}to{transform:scaleY(1)}}
    @media(max-width:980px){.roadbook__layout{grid-template-columns:minmax(0,1fr)}.roadbook__timeline{border-right:0;border-bottom:1px solid var(--roadbook-line)}.roadbook__context{position:static}.roadbook__map-frame{min-height:420px}}
    @media(max-width:620px){.roadbook{margin:0 -18px 30px;border-top:0}.roadbook__masthead{display:grid;gap:20px;padding:20px 18px}.roadbook__masthead h1{font-size:46px}.roadbook__masthead nav{overflow-x:auto;margin:0 -18px;padding:0 18px}.roadbook__masthead nav button{min-width:64px}.roadbook__day-intro{grid-template-columns:1fr;gap:12px;padding:25px 18px 20px}.roadbook__day-intro h2{font-size:32px}.roadbook__day-intro>p{font-size:14px}.roadbook__entry-guide{grid-template-columns:1fr;gap:5px;margin:0 18px;padding:13px 0}.roadbook__mobile-current{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:12px;align-items:center;margin:0 18px 18px;border-top:1px solid var(--roadbook-line);border-bottom:1px solid var(--roadbook-line);padding:13px 0}.roadbook__mobile-current div{display:grid;gap:3px;min-width:0}.roadbook__mobile-current div:last-child{text-align:right}.roadbook__mobile-current span{color:var(--roadbook-orange);font-size:9px;font-weight:900;letter-spacing:.12em}.roadbook__mobile-current strong{overflow:hidden;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.roadbook__mobile-current i{color:var(--roadbook-orange);font-style:normal}.roadbook__timeline{padding:4px 18px 32px}.roadbook__route-line{left:91px;bottom:190px}.roadbook-leg{margin-left:76px;padding:14px 0 10px}.roadbook-stop{grid-template-columns:55px 32px minmax(0,1fr);gap:8px;padding:20px 0}.roadbook-stop time{font-size:11px}.roadbook-stop__node{width:30px;height:30px;font-size:9px}.roadbook-stop__copy>strong{font-size:24px}.roadbook-stop__copy>small{font-size:13px}.roadbook-stop.is-selected{transform:none}.roadbook-day-note,.roadbook-meal-note{margin:28px 0 0 76px}.roadbook__map-heading{display:grid;gap:5px;padding:13px 18px}.roadbook__map-frame{min-height:410px}.roadbook__selection-note{min-height:210px;padding:22px 18px}.roadbook-replace-entry{display:grid;gap:14px;padding:18px}.roadbook-replace-entry>button{justify-self:start}}
    @media(prefers-reduced-motion:reduce){.roadbook__route-line{animation:none}.roadbook-stop{transition:none}}
  `}</style>;
}
