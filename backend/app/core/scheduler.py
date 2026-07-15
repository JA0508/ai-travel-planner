from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time

from app.schemas import (
    AvailabilityPreviewDay,
    AvailabilityWindow,
    AvailabilityPreviewResponse,
    BoundaryInfluenceExplanation,
    DayAvailabilitySummary,
    DayItinerary,
    DayTimeBlock,
    HotelStay,
    ItineraryResponse,
    NormalizedPOI,
    POIType,
    PlanningAnchorSource,
    PlanningCandidateTrace,
    POIVisitStyle,
    RemainingBlockWindow,
    ScheduledPOI,
    ScheduledPOISourceType,
    TimeBlockType,
    TravelMode,
)
from app.schemas.preference_policy import PlannerPreferencePolicy
from app.planner.trace import (
    PlannerDecision,
    PlannerDecisionStage,
    PlannerSubjectType,
    PlannerTraceCollector,
    PlannerReasonCode,
    stable_subject_id,
)
from app.services.amap_direction import RoutePlanningError, get_route, get_walking_route


@dataclass(slots=True)
class TimeWindow:
    day: int
    block_type: TimeBlockType
    start_time: time
    end_time: time


@dataclass(slots=True)
class FreeSlot:
    day: int
    block_type: TimeBlockType
    start_time: time
    end_time: time


class SchedulingError(Exception):
    """Raised when the input constraints cannot produce a valid itinerary."""


class Scheduler:
    """
    MVP scheduling engine.

    Scope:
    - Accept normalized POIs plus one hotel anchor.
    - Estimate trip days if absent.
    - Place fixed items first.
    - Fill remaining slots greedily using distance as the primary heuristic.
    - Distance guides POI selection only; travel time is not deducted from slot time in V1.

    Out of scope here:
    - Geolocation
    - External APIs
    - ORM/database concerns
    """

    MORNING_WINDOW = (time(hour=9, minute=0), time(hour=12, minute=0))
    AFTERNOON_WINDOW = (time(hour=13, minute=0), time(hour=17, minute=0))
    EVENING_WINDOW = (time(hour=17, minute=30), time(hour=21, minute=0))
    SOFT_BLOCK_OCCUPANCY_PRESSURE_THRESHOLD = 0.75
    SOFT_BLOCK_OCCUPANCY_RELIEF_MARGIN = 0.08

    def build_schedule(
        self,
        scenic_spots: list[NormalizedPOI],
        restaurants: list[NormalizedPOI],
        hotel: HotelStay,
        planning_anchor_source: PlanningAnchorSource,
        travel_mode: TravelMode | None = None,
        apply_hotel_end_of_day_bias: bool = False,
        arrival_anchor: HotelStay | None = None,
        departure_anchor: HotelStay | None = None,
        availability_windows: list[AvailabilityWindow] | None = None,
        trip_days: int | None = None,
        preference_policy: PlannerPreferencePolicy | None = None,
        trace_collector: PlannerTraceCollector | None = None,
    ) -> ItineraryResponse:
        """
        Main orchestration entrypoint.

        Expected flow:
        1. Merge and validate normalized POIs.
        2. Estimate trip days if needed.
        3. Create day/block windows.
        4. Split POIs into fixed and flexible groups.
        5. Place fixed items.
        6. Fill remaining free slots greedily.
        7. Convert internal assignments into response-ready structures.

        MVP note:
        - Distance is only a greedy ranking heuristic.
        - Travel time is not yet subtracted from free-slot capacity.
        """
        all_pois = filter_schedulable_pois(scenic_spots + restaurants)
        self.validate_inputs(all_pois, hotel, trip_days)

        user_provided_trip_days = trip_days is not None
        planning_days = trip_days if trip_days is not None else self.estimate_trip_days(all_pois)

        while True:
            day_windows = self.create_day_windows(planning_days, availability_windows)
            fixed_pois, flexible_pois = self.split_fixed_and_flexible(all_pois)
            scheduled_by_day, free_slots = self.place_fixed_items(
                fixed_pois,
                day_windows,
                trace_collector=trace_collector,
            )
            scheduled_by_day, boundary_explanation = self.fill_flexible_items(
                flexible_pois,
                hotel,
                apply_hotel_end_of_day_bias,
                travel_mode,
                arrival_anchor,
                departure_anchor,
                free_slots,
                scheduled_by_day,
                preference_policy=preference_policy,
                trace_collector=trace_collector,
            )

            scheduled_names = {
                item.name
                for items in scheduled_by_day.values()
                for item in items
            }
            expected_names = {poi.name for poi in all_pois}
            if scheduled_names == expected_names:
                return ItineraryResponse(
                    trip_days=planning_days,
                    hotel=hotel,
                    planning_anchor_source=planning_anchor_source,
                    boundary_explanation=boundary_explanation,
                    days=self.build_response_days(
                        trip_days=planning_days,
                        hotel=hotel,
                        scheduled_by_day=scheduled_by_day,
                        availability_windows=availability_windows,
                    ),
                )

            if user_provided_trip_days:
                raise SchedulingError(
                    f"trip_days={planning_days} is too small to fit all POIs."
                )

            planning_days += 1

    def preview_availability(
        self,
        trip_days: int,
        availability_windows: list[AvailabilityWindow] | None = None,
    ) -> AvailabilityPreviewResponse:
        effective_day_windows = self.create_day_windows(trip_days, availability_windows)
        default_day_windows = self.create_day_windows(trip_days, None)

        return AvailabilityPreviewResponse(
            trip_days=trip_days,
            days=[
                AvailabilityPreviewDay(
                    day=day,
                    availability_summary=build_day_availability_summary(
                        effective_windows=effective_day_windows[day],
                        default_windows=default_day_windows[day],
                    ),
                )
                for day in range(1, trip_days + 1)
            ],
        )

    def estimate_trip_days(self, pois: list[NormalizedPOI]) -> int:
        """
        Estimate trip length from total duration.

        MVP idea:
        - Sum scenic + restaurant durations.
        - Divide by a configurable daily capacity.
        - Clamp minimum to 1 day.
        """
        schedulable_pois = filter_schedulable_pois(pois)
        total_minutes = sum(poi.duration_minutes for poi in schedulable_pois)
        daily_capacity_minutes = total_window_capacity_minutes()

        if total_minutes == 0:
            return 1

        estimated_days = (total_minutes + daily_capacity_minutes - 1) // daily_capacity_minutes
        return max(1, estimated_days)

    def validate_inputs(
        self,
        pois: list[NormalizedPOI],
        hotel: HotelStay,
        trip_days: int | None,
    ) -> None:
        """
        Validate basic scheduler assumptions before planning.

        Example checks:
        - exactly one hotel anchor object exists
        - fixed-day values are within trip range when trip_days is given
        - fixed time ranges are internally valid
        """
        if not hotel.name.strip():
            raise SchedulingError("Hotel anchor must have a valid name.")

        for poi in pois:
            if poi.type not in {POIType.SCENIC, POIType.RESTAURANT}:
                raise SchedulingError(
                    f"POI '{poi.name}' has unsupported schedulable type '{poi.type.value}'."
                )

            if (
                poi.fixed_time_start is not None or poi.fixed_time_end is not None
            ) and poi.fixed_day is None:
                raise SchedulingError(
                    f"POI '{poi.name}' has fixed time constraints but no fixed_day."
                )

            if trip_days is not None and poi.fixed_day is not None and poi.fixed_day > trip_days:
                raise SchedulingError(
                    f"POI '{poi.name}' is fixed to day {poi.fixed_day}, outside trip_days={trip_days}."
                )

    def split_fixed_and_flexible(
        self,
        pois: list[NormalizedPOI],
    ) -> tuple[list[NormalizedPOI], list[NormalizedPOI]]:
        """
        Return (fixed_pois, flexible_pois).

        A POI is treated as fixed when it has any scheduling constraint that
        the engine must honor before greedy filling.
        """
        fixed_pois: list[NormalizedPOI] = []
        flexible_pois: list[NormalizedPOI] = []

        for poi in pois:
            if is_fixed_poi(poi):
                fixed_pois.append(poi)
            else:
                flexible_pois.append(poi)

        fixed_pois.sort(
            key=lambda poi: (
                poi.fixed_day or 0,
                poi.fixed_time_start or time.min,
                poi.name,
            )
        )
        flexible_pois.sort(key=lambda poi: (poi.type.value, poi.name))
        return fixed_pois, flexible_pois

    def create_day_windows(
        self,
        trip_days: int,
        availability_windows: list[AvailabilityWindow] | None = None,
    ) -> dict[int, list[TimeWindow]]:
        """
        Build default morning / afternoon / evening windows for each day.
        """
        if trip_days < 1:
            raise SchedulingError("trip_days must be at least 1.")

        day_windows: dict[int, list[TimeWindow]] = {}
        default_windows = [
            (TimeBlockType.MORNING, self.MORNING_WINDOW),
            (TimeBlockType.AFTERNOON, self.AFTERNOON_WINDOW),
            (TimeBlockType.EVENING, self.EVENING_WINDOW),
        ]

        for day in range(1, trip_days + 1):
            day_windows[day] = [
                TimeWindow(
                    day=day,
                    block_type=block_type,
                    start_time=start_time,
                    end_time=end_time,
                )
                for block_type, (start_time, end_time) in default_windows
            ]

        apply_boundary_availability(day_windows, trip_days, availability_windows or [])
        apply_explicit_day_availability(day_windows, trip_days, availability_windows or [])
        return day_windows

    def place_fixed_items(
        self,
        fixed_pois: list[NormalizedPOI],
        day_windows: dict[int, list[TimeWindow]],
        trace_collector: PlannerTraceCollector | None = None,
    ) -> tuple[dict[int, list[ScheduledPOI]], list[FreeSlot]]:
        """
        Place fixed POIs first and return:
        - current scheduled items by day
        - remaining free slots after fixed placements
        """
        scheduled_by_day: dict[int, list[ScheduledPOI]] = {
            day: [] for day in sorted(day_windows)
        }
        free_slots: list[FreeSlot] = [
            FreeSlot(
                day=window.day,
                block_type=window.block_type,
                start_time=window.start_time,
                end_time=window.end_time,
            )
            for day in sorted(day_windows)
            for window in day_windows[day]
        ]

        for poi in fixed_pois:
            if poi.fixed_day is None:
                raise SchedulingError(
                    f"POI '{poi.name}' is in fixed placement but has no fixed_day."
                )

            day_time_windows = day_windows.get(poi.fixed_day, [])
            day_availability_summary = describe_day_availability(day_time_windows)
            day_was_trimmed = was_trimmed_day_window(poi.fixed_day, day_time_windows)

            candidate_slots = sorted(
                [slot for slot in free_slots if slot.day == poi.fixed_day],
                key=lambda slot: (slot.start_time, slot.end_time, slot.block_type.value),
            )
            if not candidate_slots:
                if day_was_trimmed:
                    raise SchedulingError(
                        f"POI '{poi.name}' conflicts with applied availability on day {poi.fixed_day}: "
                        f"{day_availability_summary}."
                    )
                raise SchedulingError(
                    f"POI '{poi.name}' is fixed to unavailable day {poi.fixed_day}."
                )

            target_slot: FreeSlot | None = None
            scheduled_start: time | None = None
            scheduled_end: time | None = None

            if poi.fixed_time_start is not None and poi.fixed_time_end is not None:
                if minutes_between(poi.fixed_time_start, poi.fixed_time_end) < poi.duration_minutes:
                    raise SchedulingError(
                        f"POI '{poi.name}' duration exceeds its fixed time range."
                    )

                for slot in candidate_slots:
                    if (
                        slot.start_time <= poi.fixed_time_start
                        and poi.fixed_time_end <= slot.end_time
                    ):
                        target_slot = slot
                        scheduled_start = poi.fixed_time_start
                        scheduled_end = poi.fixed_time_end
                        break

                if target_slot is None:
                    if day_was_trimmed:
                        raise SchedulingError(
                            f"POI '{poi.name}' fixed time "
                            f"{format_time_value(poi.fixed_time_start)}-{format_time_value(poi.fixed_time_end)} "
                            f"conflicts with applied availability on day {poi.fixed_day}: "
                            f"{day_availability_summary}."
                        )
                    raise SchedulingError(
                        f"POI '{poi.name}' fixed time is outside available day windows."
                    )
            else:
                for slot in candidate_slots:
                    if self.fits_in_slot(poi, slot):
                        target_slot = slot
                        scheduled_start = slot.start_time
                        scheduled_end = add_minutes(slot.start_time, poi.duration_minutes)
                        break

                if target_slot is None or scheduled_start is None or scheduled_end is None:
                    if day_was_trimmed:
                        raise SchedulingError(
                            f"POI '{poi.name}' cannot fit into day {poi.fixed_day} within applied "
                            f"availability: {day_availability_summary}."
                        )
                    raise SchedulingError(
                        f"POI '{poi.name}' cannot fit into day {poi.fixed_day}."
                    )

            for scheduled_item in scheduled_by_day[poi.fixed_day]:
                if overlaps(
                    scheduled_start,
                    scheduled_end,
                    scheduled_item.start_time,
                    scheduled_item.end_time,
                ):
                    raise SchedulingError(
                        f"POI '{poi.name}' overlaps with '{scheduled_item.name}' on day {poi.fixed_day}."
                    )

            scheduled_by_day[poi.fixed_day].append(
                ScheduledPOI(
                    name=poi.name,
                    type=poi.type,
                    city=poi.city,
                    latitude=poi.latitude,
                    longitude=poi.longitude,
                    duration_minutes=poi.duration_minutes,
                    day=poi.fixed_day,
                    start_time=scheduled_start,
                    end_time=scheduled_end,
                    is_fixed=True,
                    placement_reason=build_fixed_item_reason(poi.name, scheduled_start, scheduled_end),
                    source_type=ScheduledPOISourceType.USER_FIXED,
                    source_label="固定安排",
                    source_reason="这是你明确给出的固定时间安排，系统会优先保护它的日期和时间。",
                    travel_from_name=None,
                    travel_distance_m=None,
                    travel_duration_s=None,
                )
            )
            if trace_collector is not None:
                trace_collector.record_decision(
                    stage=PlannerDecisionStage.SCHEDULE_COMMIT,
                    subject_type=PlannerSubjectType.FIXED_EVENT,
                    subject_id=stable_candidate_id(poi),
                    decision=PlannerDecision.ACCEPTED,
                    reason_codes=[PlannerReasonCode.ACCEPTED_FIXED_EVENT],
                    metrics={
                        "name": poi.name,
                        "day": poi.fixed_day,
                        "start_time": format_time_value(scheduled_start),
                        "end_time": format_time_value(scheduled_end),
                    },
                )
            free_slots = split_free_slot(
                free_slots,
                target_slot,
                scheduled_start,
                scheduled_end,
            )

        for day in scheduled_by_day:
            scheduled_by_day[day].sort(key=lambda item: (item.start_time, item.end_time, item.name))
        free_slots.sort(key=lambda slot: (slot.day, slot.start_time, slot.end_time, slot.block_type.value))
        return scheduled_by_day, free_slots

    def fill_flexible_items(
        self,
        flexible_pois: list[NormalizedPOI],
        hotel: HotelStay,
        apply_hotel_end_of_day_bias: bool,
        travel_mode: TravelMode | None,
        arrival_anchor: HotelStay | None,
        departure_anchor: HotelStay | None,
        free_slots: list[FreeSlot],
        scheduled_by_day: dict[int, list[ScheduledPOI]],
        preference_policy: PlannerPreferencePolicy | None = None,
        trace_collector: PlannerTraceCollector | None = None,
    ) -> tuple[dict[int, list[ScheduledPOI]], BoundaryInfluenceExplanation]:
        """
        Greedily fill remaining slots.

        MVP heuristic:
        - choose a candidate that fits the slot
        - prefer shortest travel distance from the slot context
        - use hotel as the starting anchor when a block is empty
        """
        remaining_pois = sorted(
            flexible_pois,
            key=lambda poi: (poi.type.value, poi.name),
        )
        ordered_slots = self.order_flexible_slots(
            free_slots=free_slots,
            preference_policy=preference_policy,
        )
        final_slot = ordered_slots[-1] if ordered_slots else None
        last_slot_by_day = {
            day: max(
                [slot for slot in ordered_slots if slot.day == day],
                key=lambda slot: (slot.start_time, slot.end_time, slot.block_type.value),
            )
            for day in {slot.day for slot in ordered_slots}
        }
        boundary_explanation = BoundaryInfluenceExplanation(
            arrival_anchor_name=arrival_anchor.name if arrival_anchor is not None else None,
            departure_anchor_name=departure_anchor.name if departure_anchor is not None else None,
        )

        for slot_index, slot in enumerate(ordered_slots):
            future_same_day_slots = [
                future_slot
                for future_slot in ordered_slots[slot_index + 1 :]
                if future_slot.day == slot.day
            ]
            current_start = slot.start_time

            while current_start < slot.end_time and remaining_pois:
                current_slot = FreeSlot(
                    day=slot.day,
                    block_type=slot.block_type,
                    start_time=current_start,
                    end_time=slot.end_time,
                )
                current_anchor = get_anchor_for_slot(
                    hotel=hotel,
                    scheduled_items=scheduled_by_day.get(slot.day, []),
                    slot=current_slot,
                )
                apply_arrival_bias = False
                if (
                    arrival_anchor is not None
                    and slot.day == 1
                    and not any(
                        not item.is_fixed
                        for item in scheduled_by_day.get(1, [])
                    )
                    and isinstance(current_anchor, HotelStay)
                ):
                    current_anchor = arrival_anchor
                    apply_arrival_bias = True
                current_block_item_count = count_scheduled_items_in_block(
                    scheduled_items=scheduled_by_day.get(slot.day, []),
                    block_type=slot.block_type,
                )
                current_block_occupied_minutes = occupied_minutes_in_block(
                    scheduled_items=scheduled_by_day.get(slot.day, []),
                    block_type=slot.block_type,
                )
                future_underused_same_day_slots = [
                    future_slot
                    for future_slot in future_same_day_slots
                    if occupied_minutes_in_block(
                        scheduled_items=scheduled_by_day.get(future_slot.day, []),
                        block_type=future_slot.block_type,
                    )
                    < current_block_occupied_minutes
                    or count_scheduled_items_in_block(
                        scheduled_items=scheduled_by_day.get(future_slot.day, []),
                        block_type=future_slot.block_type,
                    )
                    < current_block_item_count
                ]
                eligible_candidates = self.filter_deferred_candidates_for_slot(
                    candidates=remaining_pois,
                    slot=current_slot,
                    future_same_day_slots=future_same_day_slots,
                    current_block_item_count=current_block_item_count,
                    future_underused_same_day_slots=future_underused_same_day_slots,
                    current_block_occupied_minutes=current_block_occupied_minutes,
                )
                eligible_candidates = self.apply_meal_anchor_filter(
                    candidates=eligible_candidates,
                    slot=current_slot,
                    scheduled_items=scheduled_by_day.get(slot.day, []),
                )
                if not eligible_candidates:
                    break
                baseline_poi = None
                if apply_arrival_bias:
                    baseline_poi = self.choose_best_poi_for_slot(
                        candidates=eligible_candidates,
                        slot=current_slot,
                        current_anchor=hotel,
                        day_has_items=bool(scheduled_by_day.get(slot.day)),
                        preference_policy=preference_policy,
                    )
                candidate_details = self.rank_poi_candidates_with_travel_info(
                    candidates=eligible_candidates,
                    slot=current_slot,
                    day_has_items=bool(scheduled_by_day.get(slot.day)),
                    current_anchor=current_anchor,
                    return_anchor=hotel,
                    apply_arrival_bias=apply_arrival_bias,
                    departure_anchor=departure_anchor,
                    apply_departure_bias=(
                        departure_anchor is not None
                        and final_slot is not None
                        and slot.day == final_slot.day
                        and slot.block_type == final_slot.block_type
                        and slot.start_time == final_slot.start_time
                        and slot.end_time == final_slot.end_time
                    ),
                    travel_mode=travel_mode,
                    apply_return_to_base_bias=(
                        apply_hotel_end_of_day_bias
                        and slot.day in last_slot_by_day
                        and slot.start_time == last_slot_by_day[slot.day].start_time
                        and slot.end_time == last_slot_by_day[slot.day].end_time
                        and slot.block_type == last_slot_by_day[slot.day].block_type
                    ),
                    preference_policy=preference_policy,
                    trace_collector=trace_collector,
                )
                if not candidate_details:
                    break
                _selection_rank, next_poi, travel_info = candidate_details[0]
                selection_top_candidates = self.build_seed_selection_top_candidates(
                    candidate_details,
                    selected_name=next_poi.name,
                )
                selection_rejected_candidates = self.build_seed_selection_rejected_candidates(
                    all_candidates=remaining_pois,
                    eligible_candidates=eligible_candidates,
                    ranked_candidates=candidate_details,
                    slot=current_slot,
                )
                if trace_collector is not None:
                    for rejected_trace in selection_rejected_candidates:
                        trace_collector.record_decision(
                            stage=PlannerDecisionStage.CANDIDATE_RANKING,
                            subject_type=PlannerSubjectType.CANDIDATE,
                            subject_id=stable_subject_id(
                                "candidate",
                                rejected_trace.name.casefold(),
                                rejected_trace.type.value,
                            ),
                            decision=PlannerDecision.REJECTED,
                            reason_codes=[
                                reason_code_for_candidate_rejection(
                                    rejected_trace.reason
                                )
                            ],
                            metrics={
                                "name": rejected_trace.name,
                                "type": rejected_trace.type.value,
                                "slot_day": current_slot.day,
                                "slot_block": current_slot.block_type.value,
                            },
                        )
                if next_poi is None:
                    break

                if (
                    apply_arrival_bias
                    and baseline_poi is not None
                    and baseline_poi.name != next_poi.name
                ):
                    boundary_explanation.arrival_anchor_influenced = True
                    boundary_explanation.arrival_poi_name = next_poi.name

                if (
                    departure_anchor is not None
                    and final_slot is not None
                    and slot.day == final_slot.day
                    and slot.block_type == final_slot.block_type
                    and slot.start_time == final_slot.start_time
                    and slot.end_time == final_slot.end_time
                ):
                    baseline_final_poi = self.choose_best_poi_for_slot(
                        candidates=eligible_candidates,
                        slot=current_slot,
                        current_anchor=current_anchor,
                        day_has_items=bool(scheduled_by_day.get(slot.day)),
                        apply_arrival_bias=apply_arrival_bias,
                        preference_policy=preference_policy,
                    )
                    if (
                        baseline_final_poi is not None
                        and baseline_final_poi.name != next_poi.name
                    ):
                        boundary_explanation.departure_anchor_influenced = True
                        boundary_explanation.departure_poi_name = next_poi.name

                scheduled_end = add_minutes(current_start, next_poi.duration_minutes)
                scheduled_by_day.setdefault(slot.day, []).append(
                    ScheduledPOI(
                        name=next_poi.name,
                        type=next_poi.type,
                        city=next_poi.city,
                        latitude=next_poi.latitude,
                        longitude=next_poi.longitude,
                        duration_minutes=next_poi.duration_minutes,
                        day=slot.day,
                        start_time=current_start,
                        end_time=scheduled_end,
                        is_fixed=False,
                        placement_reason=build_placement_reason(
                            slot=current_slot,
                            poi=next_poi,
                            apply_arrival_bias=apply_arrival_bias,
                            apply_departure_bias=(
                                departure_anchor is not None
                                and final_slot is not None
                                and slot.day == final_slot.day
                                and slot.block_type == final_slot.block_type
                                and slot.start_time == final_slot.start_time
                                and slot.end_time == final_slot.end_time
                            ),
                        ),
                        source_type=ScheduledPOISourceType.USER_SEED,
                        source_label="用户种子",
                        source_reason="这个地点来自你明确给出的想去地点或已确认意图。",
                        travel_from_name=current_anchor.name,
                        travel_distance_m=travel_info["distance_m"] if travel_info else None,
                        travel_duration_s=travel_info["duration_s"] if travel_info else None,
                        selection_top_candidates=selection_top_candidates,
                        selection_rejected_candidates=selection_rejected_candidates,
                    )
                )
                if trace_collector is not None:
                    trace_collector.record_decision(
                        stage=PlannerDecisionStage.SCHEDULE_COMMIT,
                        subject_type=PlannerSubjectType.SCHEDULED_ITEM,
                        subject_id=stable_candidate_id(next_poi),
                        decision=PlannerDecision.ACCEPTED,
                        reason_codes=[PlannerReasonCode.ACCEPTED_RANKED_CANDIDATE],
                        metrics={
                            "name": next_poi.name,
                            "type": next_poi.type.value,
                            "day": slot.day,
                            "block_type": slot.block_type.value,
                            "start_time": format_time_value(current_start),
                            "end_time": format_time_value(scheduled_end),
                            "travel_duration_s": travel_info.get("duration_s") if travel_info else None,
                            "travel_distance_m": travel_info.get("distance_m") if travel_info else None,
                        },
                    )
                remaining_pois.remove(next_poi)
                current_start = scheduled_end

        for day in scheduled_by_day:
            scheduled_by_day[day].sort(key=lambda item: (item.start_time, item.end_time, item.name))
        return scheduled_by_day, boundary_explanation

    def filter_deferred_candidates_for_slot(
        self,
        *,
        candidates: list[NormalizedPOI],
        slot: FreeSlot,
        future_same_day_slots: list[FreeSlot],
        current_block_item_count: int,
        future_underused_same_day_slots: list[FreeSlot],
        current_block_occupied_minutes: int,
    ) -> list[NormalizedPOI]:
        fitting_candidates = [
            poi for poi in candidates if self.fits_in_slot(poi, slot)
        ]
        if not fitting_candidates:
            return []

        eligible_candidates = [
            poi
            for poi in fitting_candidates
            if not self.should_defer_poi_to_later_preferred_slot(
                poi=poi,
                slot=slot,
                future_same_day_slots=future_same_day_slots,
            )
            and not self.should_defer_poi_for_day_spread(
                poi=poi,
                slot=slot,
                current_block_item_count=current_block_item_count,
                future_underused_same_day_slots=future_underused_same_day_slots,
            )
            and not self.should_defer_poi_for_occupancy_pressure(
                poi=poi,
                slot=slot,
                current_block_item_count=current_block_item_count,
                current_block_occupied_minutes=current_block_occupied_minutes,
                future_same_day_slots=future_same_day_slots,
            )
        ]

        if eligible_candidates:
            return eligible_candidates

        if self.should_allow_morning_neutral_backfill(
            slot=slot,
            fitting_candidates=fitting_candidates,
            future_same_day_slots=future_same_day_slots,
        ):
            backfill_candidates = [
                poi
                for poi in fitting_candidates
                if self.is_neutral_morning_backfill_candidate(poi)
            ]
            if backfill_candidates:
                return backfill_candidates

        return []

    def apply_meal_anchor_filter(
        self,
        *,
        candidates: list[NormalizedPOI],
        slot: FreeSlot,
        scheduled_items: list[ScheduledPOI],
    ) -> list[NormalizedPOI]:
        if not candidates:
            return []

        if slot.block_type == TimeBlockType.MORNING:
            non_restaurants = [poi for poi in candidates if poi.type != POIType.RESTAURANT]
            return non_restaurants or candidates

        if slot.block_type not in {TimeBlockType.AFTERNOON, TimeBlockType.EVENING}:
            return candidates

        has_meal_in_block = any(
            item.type == POIType.RESTAURANT
            and block_type_for_time_range(item.start_time, item.end_time) == slot.block_type
            for item in scheduled_items
        )
        if has_meal_in_block:
            return candidates

        restaurant_candidates = [
            poi
            for poi in candidates
            if poi.type == POIType.RESTAURANT and self.fits_in_slot(poi, slot)
        ]
        if restaurant_candidates:
            return restaurant_candidates

        return candidates

    def should_defer_poi_to_later_preferred_slot(
        self,
        *,
        poi: NormalizedPOI,
        slot: FreeSlot,
        future_same_day_slots: list[FreeSlot],
    ) -> bool:
        if slot.block_type in poi.profile.best_time_blocks:
            return False

        for future_slot in future_same_day_slots:
            if future_slot.block_type not in poi.profile.best_time_blocks:
                continue
            if self.fits_in_slot(poi, future_slot):
                return True

        return False

    def should_defer_poi_for_occupancy_pressure(
        self,
        *,
        poi: NormalizedPOI,
        slot: FreeSlot,
        current_block_item_count: int,
        current_block_occupied_minutes: int,
        future_same_day_slots: list[FreeSlot],
    ) -> bool:
        if current_block_item_count < 1:
            return False
        if poi.type != POIType.SCENIC or poi.profile.intensity == "heavy":
            return False
        if slot.block_type not in poi.profile.best_time_blocks:
            return False

        current_capacity_minutes = block_capacity_minutes(slot.block_type)
        current_projected_ratio = (
            current_block_occupied_minutes + poi.duration_minutes
        ) / current_capacity_minutes
        if current_projected_ratio < self.SOFT_BLOCK_OCCUPANCY_PRESSURE_THRESHOLD:
            return False

        for future_slot in future_same_day_slots:
            if future_slot.block_type not in poi.profile.best_time_blocks:
                continue
            if not self.fits_in_slot(poi, future_slot):
                continue

            future_occupied_minutes = (
                block_capacity_minutes(future_slot.block_type)
                - remaining_free_minutes_in_block(
                    free_slots=future_same_day_slots,
                    block_type=future_slot.block_type,
                )
            )
            future_projected_ratio = (
                future_occupied_minutes + poi.duration_minutes
            ) / block_capacity_minutes(future_slot.block_type)
            if (
                future_projected_ratio
                <= current_projected_ratio - self.SOFT_BLOCK_OCCUPANCY_RELIEF_MARGIN
            ):
                return True

        return False

    def should_defer_poi_for_day_spread(
        self,
        *,
        poi: NormalizedPOI,
        slot: FreeSlot,
        current_block_item_count: int,
        future_underused_same_day_slots: list[FreeSlot],
    ) -> bool:
        if current_block_item_count < 1:
            return False
        if poi.type != POIType.SCENIC or poi.profile.intensity == "heavy":
            return False
        if slot.block_type not in poi.profile.best_time_blocks:
            return False

        for future_slot in future_underused_same_day_slots:
            if future_slot.block_type not in poi.profile.best_time_blocks:
                continue
            if self.fits_in_slot(poi, future_slot):
                return True

        return False

    def should_allow_morning_neutral_backfill(
        self,
        *,
        slot: FreeSlot,
        fitting_candidates: list[NormalizedPOI],
        future_same_day_slots: list[FreeSlot],
    ) -> bool:
        if slot.block_type != TimeBlockType.MORNING:
            return False

        has_strong_later_sensitive_candidate = any(
            self.is_strong_later_block_preservation_candidate(
                poi=poi,
                slot=slot,
                future_same_day_slots=future_same_day_slots,
            )
            for poi in fitting_candidates
        )
        if not has_strong_later_sensitive_candidate:
            return False

        return any(
            self.is_neutral_morning_backfill_candidate(poi)
            and self.should_defer_poi_to_later_preferred_slot(
                poi=poi,
                slot=slot,
                future_same_day_slots=future_same_day_slots,
            )
            for poi in fitting_candidates
        )

    def is_neutral_morning_backfill_candidate(self, poi: NormalizedPOI) -> bool:
        return (
            poi.type == POIType.SCENIC
            and poi.profile.intensity != "heavy"
            and poi.profile.visit_style in {POIVisitStyle.LANDMARK, POIVisitStyle.GENERAL}
        )

    def is_strong_later_block_preservation_candidate(
        self,
        *,
        poi: NormalizedPOI,
        slot: FreeSlot,
        future_same_day_slots: list[FreeSlot],
    ) -> bool:
        if not self.should_defer_poi_to_later_preferred_slot(
            poi=poi,
            slot=slot,
            future_same_day_slots=future_same_day_slots,
        ):
            return False

        return (
            poi.type == POIType.RESTAURANT
            or poi.profile.visit_style in {
                POIVisitStyle.NIGHT_VIEW,
                POIVisitStyle.FOOD_STOP,
                POIVisitStyle.FOOD_DISTRICT,
            }
            or poi.profile.intensity == "heavy"
        )

    def order_flexible_slots(
        self,
        free_slots: list[FreeSlot],
        preference_policy: PlannerPreferencePolicy | None,
    ) -> list[FreeSlot]:
        block_order = {
            TimeBlockType.MORNING: 0,
            TimeBlockType.AFTERNOON: 1,
            TimeBlockType.EVENING: 2,
        }

        if preference_policy is None or preference_policy.pace == "packed":
            return sorted(
                free_slots,
                key=lambda slot: (slot.day, slot.start_time, slot.end_time, block_order[slot.block_type]),
            )

        if preference_policy.pace == "relaxed":
            return sorted(
                free_slots,
                key=lambda slot: (
                    block_order[slot.block_type],
                    slot.day,
                    slot.start_time,
                    slot.end_time,
                ),
            )

        return sorted(
            free_slots,
            key=lambda slot: (
                block_order[slot.block_type],
                slot.day,
                slot.start_time,
                slot.end_time,
            ),
        )

    def choose_best_poi_for_slot(
        self,
        candidates: list[NormalizedPOI],
        slot: FreeSlot,
        current_anchor: HotelStay | ScheduledPOI,
        day_has_items: bool = False,
        return_anchor: HotelStay | None = None,
        travel_mode: TravelMode | None = None,
        apply_arrival_bias: bool = False,
        departure_anchor: HotelStay | None = None,
        apply_departure_bias: bool = False,
        apply_return_to_base_bias: bool = False,
        preference_policy: PlannerPreferencePolicy | None = None,
        trace_collector: PlannerTraceCollector | None = None,
    ) -> NormalizedPOI | None:
        """
        Pick the next POI for a slot using a greedy travel-time-based heuristic.

        MVP note:
        - Block preference remains the first ranking signal.
        - Walking duration is used as the primary travel cost when available.
        - If route planning fails for a candidate, fall back to straight-line
          distance for that candidate only.
        """
        best_poi, _travel_info = self.choose_best_poi_with_travel_info(
            candidates=candidates,
            slot=slot,
            day_has_items=day_has_items,
            current_anchor=current_anchor,
            return_anchor=return_anchor,
            travel_mode=travel_mode,
            apply_arrival_bias=apply_arrival_bias,
            departure_anchor=departure_anchor,
            apply_departure_bias=apply_departure_bias,
            apply_return_to_base_bias=apply_return_to_base_bias,
            preference_policy=preference_policy,
            trace_collector=trace_collector,
        )
        return best_poi

    def choose_best_poi_with_travel_info(
        self,
        candidates: list[NormalizedPOI],
        slot: FreeSlot,
        current_anchor: HotelStay | ScheduledPOI,
        day_has_items: bool = False,
        return_anchor: HotelStay | None = None,
        travel_mode: TravelMode | None = None,
        apply_arrival_bias: bool = False,
        departure_anchor: HotelStay | None = None,
        apply_departure_bias: bool = False,
        apply_return_to_base_bias: bool = False,
        preference_policy: PlannerPreferencePolicy | None = None,
        trace_collector: PlannerTraceCollector | None = None,
    ) -> tuple[NormalizedPOI | None, dict[str, int | None] | None]:
        """
        Pick the next POI and return the travel metadata used during selection.
        """
        candidate_details = self.rank_poi_candidates_with_travel_info(
            candidates=candidates,
            slot=slot,
            day_has_items=day_has_items,
            current_anchor=current_anchor,
            return_anchor=return_anchor,
            travel_mode=travel_mode,
            apply_arrival_bias=apply_arrival_bias,
            departure_anchor=departure_anchor,
            apply_departure_bias=apply_departure_bias,
            apply_return_to_base_bias=apply_return_to_base_bias,
            preference_policy=preference_policy,
            trace_collector=trace_collector,
        )
        if not candidate_details:
            return None, None

        _rank, best_poi, best_travel_info = candidate_details[0]
        return best_poi, best_travel_info

    def rank_poi_candidates_with_travel_info(
        self,
        candidates: list[NormalizedPOI],
        slot: FreeSlot,
        current_anchor: HotelStay | ScheduledPOI,
        day_has_items: bool = False,
        return_anchor: HotelStay | None = None,
        travel_mode: TravelMode | None = None,
        apply_arrival_bias: bool = False,
        departure_anchor: HotelStay | None = None,
        apply_departure_bias: bool = False,
        apply_return_to_base_bias: bool = False,
        preference_policy: PlannerPreferencePolicy | None = None,
        trace_collector: PlannerTraceCollector | None = None,
    ) -> list[
        tuple[
            tuple[float, int, int, int, int, int, float, float, int, str, str],
            NormalizedPOI,
            dict[str, int | None],
        ]
    ]:
        """
        Rank fitting POIs using the exact deterministic selection tuple.
        """
        fitting_candidates = [
            poi for poi in candidates if self.fits_in_slot(poi, slot)
        ]
        if not fitting_candidates:
            return []

        candidate_details: list[
            tuple[tuple[float, int, int, int, int, int, float, float, int, str, str], NormalizedPOI, dict[str, int | None]]
        ] = []

        for poi in fitting_candidates:
            travel_info = self.estimate_city_travel_info(
                origin_lat=current_anchor.latitude,
                origin_lng=current_anchor.longitude,
                dest_lat=poi.latitude,
                dest_lng=poi.longitude,
                city=poi.city or getattr(current_anchor, "city", None),
                travel_mode=travel_mode,
                trace_collector=trace_collector,
                origin_id=stable_anchor_id(current_anchor),
                destination_id=stable_candidate_id(poi),
            )
            if not self.fits_in_slot_with_travel(poi=poi, slot=slot, travel_info=travel_info):
                if trace_collector is not None:
                    trace_collector.record_decision(
                        stage=PlannerDecisionStage.ROUTE_EVALUATION,
                        subject_type=PlannerSubjectType.CANDIDATE,
                        subject_id=stable_candidate_id(poi),
                        decision=PlannerDecision.REJECTED,
                        reason_codes=[PlannerReasonCode.REJECTED_ROUTE_INFEASIBLE],
                        metrics={
                            "name": poi.name,
                            "duration_s": travel_info.get("duration_s"),
                            "slot_day": slot.day,
                            "slot_block": slot.block_type.value,
                        },
                    )
                continue
            travel_cost = float(travel_info["duration_s"])

            continuation_cost = self.estimate_continuation_cost(
                poi=poi,
                remaining_candidates=candidates,
            )
            cluster_density_cost = self.estimate_cluster_density_cost(
                poi=poi,
                remaining_candidates=candidates,
            )

            candidate_details.append(
                (
                    (
                        float(block_preference_rank(slot.block_type, poi.type))
                        + self.preference_type_bias(
                            slot.block_type,
                            poi.type,
                            preference_policy,
                        ),
                        self.preference_travel_band_rank(
                            travel_cost,
                            preference_policy,
                        ),
                        self.arrival_anchor_band_rank(
                            travel_cost=travel_cost,
                            apply_arrival_bias=apply_arrival_bias,
                        ),
                        self.departure_anchor_band_rank(
                            poi=poi,
                            departure_anchor=departure_anchor,
                            apply_departure_bias=apply_departure_bias,
                        ),
                        self.poi_time_affinity_rank(
                            block_type=slot.block_type,
                            poi=poi,
                        ),
                        self.travel_mode_day_one_rank(
                            slot_day=slot.day,
                            block_type=slot.block_type,
                            poi=poi,
                            travel_mode=travel_mode,
                        ),
                        self.day_seed_profile_rank(
                            block_type=slot.block_type,
                            poi=poi,
                            day_has_items=day_has_items,
                        ),
                        self.cluster_density_band_rank(cluster_density_cost),
                        self.return_to_base_band_rank(
                            poi=poi,
                            return_anchor=return_anchor if apply_return_to_base_bias else None,
                        ),
                        self.continuation_band_rank(continuation_cost),
                        cluster_density_cost,
                        continuation_cost,
                        travel_cost,
                        poi.duration_minutes,
                        poi.type.value,
                        poi.name,
                    ),
                    poi,
                    travel_info,
                )
            )

        return sorted(candidate_details, key=lambda item: item[0])

    def fits_in_slot_with_travel(
        self,
        *,
        poi: NormalizedPOI,
        slot: FreeSlot,
        travel_info: dict[str, int],
    ) -> bool:
        slot_minutes = minutes_between(slot.start_time, slot.end_time)
        travel_minutes = max(0, math.ceil(int(travel_info.get("duration_s") or 0) / 60))
        if travel_minutes > 150:
            return False
        # The current scheduler still renders travel as leg metadata rather
        # than shifting every stop's clock time. Keep the guard conservative:
        # block impossible cross-region jumps, but do not reject valid remote
        # anchor trips that need a longer city transfer.
        return poi.duration_minutes <= slot_minutes

    def build_seed_selection_top_candidates(
        self,
        candidate_details: list[
            tuple[
                tuple[float, int, int, int, int, int, float, float, int, str, str],
                NormalizedPOI,
                dict[str, int | None],
            ]
        ],
        *,
        selected_name: str,
    ) -> list[PlanningCandidateTrace]:
        traces: list[PlanningCandidateTrace] = []
        for rank, (rank_key, poi, travel_info) in enumerate(candidate_details[:4], start=1):
            traces.append(
                PlanningCandidateTrace(
                    name=poi.name,
                    type=poi.type,
                    rank=rank,
                    score=rank,
                    status="selected" if poi.name == selected_name else "ranked_alternative",
                    reason=build_seed_candidate_rank_reason(
                        rank_key=rank_key,
                        travel_info=travel_info,
                    ),
                )
            )
        return traces

    def build_seed_selection_rejected_candidates(
        self,
        *,
        all_candidates: list[NormalizedPOI],
        eligible_candidates: list[NormalizedPOI],
        ranked_candidates: list[
            tuple[
                tuple[float, int, int, int, int, int, float, float, int, str, str],
                NormalizedPOI,
                dict[str, int | None],
            ]
        ],
        slot: FreeSlot,
    ) -> list[PlanningCandidateTrace]:
        eligible_names = {poi.name for poi in eligible_candidates}
        ranked_names = {poi.name for _rank, poi, _travel in ranked_candidates}
        traces: list[PlanningCandidateTrace] = []
        for poi in all_candidates:
            if poi.name in ranked_names:
                continue
            reason = build_seed_candidate_rejection_reason(
                poi=poi,
                slot=slot,
                eligible_names=eligible_names,
            )
            if reason is None:
                continue
            traces.append(
                PlanningCandidateTrace(
                    name=poi.name,
                    type=poi.type,
                    rank=None,
                    score=None,
                    status="rejected",
                    reason=reason,
                )
            )
            if len(traces) >= 4:
                break
        return traces

    def estimate_continuation_cost(
        self,
        poi: NormalizedPOI,
        remaining_candidates: list[NormalizedPOI],
    ) -> float:
        """
        Estimate how naturally this POI can connect to the next step of the route.

        Lower is better. We intentionally use straight-line distance here to keep
        this ranking cheap and bounded.
        """
        onward_distances = [
            self.calculate_distance(
                poi.latitude,
                poi.longitude,
                other.latitude,
                other.longitude,
            )
            for other in remaining_candidates
            if other.name != poi.name
        ]
        if not onward_distances:
            return 0.0

        onward_distances.sort()
        nearest_two = onward_distances[:2]
        return sum(nearest_two) / len(nearest_two)

    def estimate_cluster_density_cost(
        self,
        poi: NormalizedPOI,
        remaining_candidates: list[NormalizedPOI],
    ) -> float:
        nearby_distances = [
            self.calculate_distance(
                poi.latitude,
                poi.longitude,
                other.latitude,
                other.longitude,
            )
            for other in remaining_candidates
            if other.name != poi.name
        ]
        if not nearby_distances:
            return 0.0

        nearby_distances.sort()
        nearest_three = nearby_distances[:3]
        return sum(nearest_three) / len(nearest_three)

    def preference_type_bias(
        self,
        block_type: TimeBlockType,
        poi_type: POIType,
        preference_policy: PlannerPreferencePolicy | None,
    ) -> float:
        if preference_policy is None:
            return 0.0
        if (
            preference_policy.dining_priority == "high"
            and block_type == TimeBlockType.EVENING
            and poi_type == POIType.RESTAURANT
        ):
            return -0.85
        if (
            preference_policy.scenic_priority == "high"
            and block_type in {TimeBlockType.MORNING, TimeBlockType.AFTERNOON}
            and poi_type == POIType.SCENIC
        ):
            return -0.35
        return 0.0

    def preference_travel_band_rank(
        self,
        travel_cost: float,
        preference_policy: PlannerPreferencePolicy | None,
    ) -> int:
        if preference_policy is None or preference_policy.walking_tolerance != "low":
            return 0
        if travel_cost <= 10 * 60:
            return 0
        if travel_cost <= 20 * 60:
            return 1
        if travel_cost <= 35 * 60:
            return 3
        return 5

    def arrival_anchor_band_rank(
        self,
        travel_cost: float,
        apply_arrival_bias: bool,
    ) -> int:
        if not apply_arrival_bias:
            return 0
        if travel_cost <= 12 * 60:
            return 0
        if travel_cost <= 25 * 60:
            return 2
        return 5

    def departure_anchor_band_rank(
        self,
        poi: NormalizedPOI,
        departure_anchor: HotelStay | None,
        apply_departure_bias: bool,
    ) -> int:
        if not apply_departure_bias or departure_anchor is None:
            return 0

        try:
            route = self.estimate_city_travel_info(
                origin_lat=poi.latitude,
                origin_lng=poi.longitude,
                dest_lat=departure_anchor.latitude,
                dest_lng=departure_anchor.longitude,
                city=departure_anchor.city or poi.city,
            )
            anchor_cost = float(route["duration_s"])
        except (KeyError, TypeError, ValueError):
            anchor_cost = 60 * 60

        if anchor_cost <= 12 * 60:
            return 0
        if anchor_cost <= 25 * 60:
            return 3
        return 7

    def continuation_band_rank(self, continuation_cost: float) -> int:
        """
        Prefer POIs that leave a coherent nearby next step instead of creating a
        zig-zag route through the city.
        """
        if continuation_cost <= 1.2:
            return 0
        if continuation_cost <= 2.5:
            return 1
        if continuation_cost <= 4.0:
            return 3
        return 5

    def cluster_density_band_rank(self, cluster_density_cost: float) -> int:
        """
        Favor POIs that belong to a denser nearby pocket of the trip so a day can
        unfold around a more coherent local cluster.
        """
        if cluster_density_cost <= 0.8:
            return 0
        if cluster_density_cost <= 1.8:
            return 1
        if cluster_density_cost <= 3.2:
            return 3
        return 5

    def day_seed_profile_rank(
        self,
        block_type: TimeBlockType,
        poi: NormalizedPOI,
        day_has_items: bool,
    ) -> int:
        if day_has_items:
            return 0

        if block_type == TimeBlockType.MORNING:
            if poi.profile.visit_style in {
                POIVisitStyle.MUSEUM,
                POIVisitStyle.TEMPLE_PARK,
                POIVisitStyle.LANDMARK,
                POIVisitStyle.OLD_STREET,
            } or poi.profile.intensity == "heavy":
                return 0
            if poi.profile.visit_style in {
                POIVisitStyle.NIGHT_VIEW,
                POIVisitStyle.FOOD_STOP,
                POIVisitStyle.FOOD_DISTRICT,
            }:
                return 4
            return 1

        if block_type == TimeBlockType.AFTERNOON:
            if poi.profile.visit_style in {
                POIVisitStyle.MUSEUM,
                POIVisitStyle.OLD_STREET,
                POIVisitStyle.LEISURE_DISTRICT,
                POIVisitStyle.LANDMARK,
                POIVisitStyle.TEMPLE_PARK,
            }:
                return 0
            if poi.profile.visit_style == POIVisitStyle.NIGHT_VIEW:
                return 3
            return 1

        if poi.profile.visit_style in {
            POIVisitStyle.NIGHT_VIEW,
            POIVisitStyle.FOOD_STOP,
            POIVisitStyle.FOOD_DISTRICT,
            POIVisitStyle.LEISURE_DISTRICT,
            POIVisitStyle.OLD_STREET,
        }:
            return 0
        if poi.profile.intensity == "heavy":
            return 4
        return 2

    def return_to_base_band_rank(
        self,
        poi: NormalizedPOI,
        return_anchor: HotelStay | None,
    ) -> int:
        if return_anchor is None:
            return 0

        try:
            route = self.estimate_city_travel_info(
                origin_lat=poi.latitude,
                origin_lng=poi.longitude,
                dest_lat=return_anchor.latitude,
                dest_lng=return_anchor.longitude,
                city=return_anchor.city or poi.city,
            )
            return_cost = float(route["duration_s"])
        except (KeyError, TypeError, ValueError):
            return_cost = 60 * 60

        if return_cost <= 12 * 60:
            return 0
        if return_cost <= 25 * 60:
            return 2
        if return_cost <= 40 * 60:
            return 4
        return 7

    def poi_time_affinity_rank(
        self,
        block_type: TimeBlockType,
        poi: NormalizedPOI,
    ) -> int:
        """
        Encode lightweight real-world timing intuition for certain POI patterns.

        Lower is better. This stays heuristic and bounded on purpose.
        """
        if poi.type == POIType.RESTAURANT:
            if block_type == TimeBlockType.EVENING:
                return 0
            if block_type == TimeBlockType.AFTERNOON:
                return 2
            return 4

        if block_type in poi.profile.best_time_blocks:
            return 0
        if (
            poi.profile.visit_style == POIVisitStyle.NIGHT_VIEW
            and block_type == TimeBlockType.AFTERNOON
        ):
            return 2
        if (
            poi.profile.visit_style == POIVisitStyle.MUSEUM
            and block_type == TimeBlockType.AFTERNOON
        ):
            return 1
        if (
            poi.profile.visit_style in {POIVisitStyle.OLD_STREET, POIVisitStyle.LEISURE_DISTRICT}
            and block_type == TimeBlockType.EVENING
        ):
            return 1
        return 4

    def travel_mode_day_one_rank(
        self,
        slot_day: int,
        block_type: TimeBlockType,
        poi: NormalizedPOI,
        travel_mode: TravelMode | None,
    ) -> int:
        if slot_day != 1 or travel_mode is None or travel_mode == TravelMode.UNDECIDED:
            return 0

        if travel_mode == TravelMode.AIRPLANE:
            if poi.profile.intensity == "heavy":
                return 4 if block_type in {TimeBlockType.AFTERNOON, TimeBlockType.EVENING} else 1
            if poi.profile.visit_style in {POIVisitStyle.NIGHT_VIEW, POIVisitStyle.FOOD_STOP, POIVisitStyle.FOOD_DISTRICT}:
                return 0
            return 1

        if travel_mode in {TravelMode.HIGH_SPEED_RAIL, TravelMode.RAIL}:
            if poi.profile.visit_style == POIVisitStyle.MUSEUM and block_type == TimeBlockType.EVENING:
                return 3
            return 0

        if travel_mode == TravelMode.CAR:
            if poi.profile.visit_style == POIVisitStyle.FOOD_STOP and block_type == TimeBlockType.MORNING:
                return 2
            return 0

        return 0

    def fits_in_slot(self, poi: NormalizedPOI, slot: FreeSlot) -> bool:
        """
        Check whether a POI duration can fit inside the free slot.
        """
        return poi.duration_minutes <= minutes_between(slot.start_time, slot.end_time)

    def estimate_city_travel_info(
        self,
        *,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        city: str | None = None,
        travel_mode: TravelMode | None = None,
        trace_collector: PlannerTraceCollector | None = None,
        origin_id: str | None = None,
        destination_id: str | None = None,
    ) -> dict[str, int]:
        """
        Return deterministic route metadata for city itinerary scheduling.

        Short hops stay walk-first. Longer city hops use transit or driving so
        a remote POI does not get presented as a many-hour walking segment.
        If Amap fails, use a bounded local estimate from straight-line distance.
        """
        straight_distance_km = self.calculate_distance(origin_lat, origin_lng, dest_lat, dest_lng)
        preferred_modes = self.city_route_mode_order(
            straight_distance_km=straight_distance_km,
            travel_mode=travel_mode,
            city=city,
        )

        for mode in preferred_modes:
            try:
                route = get_route(
                    mode=mode,
                    origin_lat=origin_lat,
                    origin_lng=origin_lng,
                    dest_lat=dest_lat,
                    dest_lng=dest_lng,
                    city=city,
                )
                if trace_collector is not None:
                    trace_collector.record_route_snapshot(
                        origin_id=origin_id or stable_subject_id("route_origin", origin_lat, origin_lng),
                        destination_id=destination_id or stable_subject_id("route_destination", dest_lat, dest_lng),
                        travel_mode=mode,
                        availability="known",
                        duration_seconds=int(route["duration_s"]),
                        distance_meters=int(route["distance_m"]),
                    )
                    trace_collector.record_decision(
                        stage=PlannerDecisionStage.ROUTE_EVALUATION,
                        subject_type=PlannerSubjectType.ROUTE_SEGMENT,
                        subject_id=stable_subject_id(
                            "route_segment",
                            origin_id,
                            destination_id,
                            mode,
                        ),
                        decision=PlannerDecision.ACCEPTED,
                        reason_codes=[PlannerReasonCode.ROUTE_DATA_KNOWN],
                        metrics={
                            "mode": mode,
                            "duration_s": int(route["duration_s"]),
                            "distance_m": int(route["distance_m"]),
                        },
                    )
                return {
                    "distance_m": int(route["distance_m"]),
                    "duration_s": int(route["duration_s"]),
                }
            except (RoutePlanningError, KeyError, TypeError, ValueError):
                continue

        fallback_mode = preferred_modes[0] if preferred_modes else "transit"
        fallback_route = self.estimate_local_city_route(
            straight_distance_km=straight_distance_km,
            mode=fallback_mode,
        )
        if trace_collector is not None:
            trace_collector.record_route_snapshot(
                origin_id=origin_id or stable_subject_id("route_origin", origin_lat, origin_lng),
                destination_id=destination_id or stable_subject_id("route_destination", dest_lat, dest_lng),
                travel_mode=fallback_mode,
                availability="missing",
                duration_seconds=fallback_route["duration_s"],
                distance_meters=fallback_route["distance_m"],
            )
            trace_collector.record_decision(
                stage=PlannerDecisionStage.ROUTE_EVALUATION,
                subject_type=PlannerSubjectType.ROUTE_SEGMENT,
                subject_id=stable_subject_id(
                    "route_segment",
                    origin_id,
                    destination_id,
                    fallback_mode,
                ),
                decision=PlannerDecision.FALLBACK_USED,
                reason_codes=[
                    PlannerReasonCode.ROUTE_DATA_MISSING,
                    PlannerReasonCode.FALLBACK_ROUTE_ESTIMATE_USED,
                ],
                metrics={
                    "mode": fallback_mode,
                    "duration_s": fallback_route["duration_s"],
                    "distance_m": fallback_route["distance_m"],
                },
            )
        return fallback_route

    def city_route_mode_order(
        self,
        *,
        straight_distance_km: float,
        travel_mode: TravelMode | None,
        city: str | None,
    ) -> list[str]:
        if travel_mode == TravelMode.CAR:
            return ["drive", "transit", "walk"] if city else ["drive", "walk"]
        if straight_distance_km <= 1.6:
            return ["walk", "transit", "drive"] if city else ["walk", "drive"]
        if city:
            return ["transit", "drive", "walk"]
        return ["drive", "walk"]

    def estimate_local_city_route(
        self,
        *,
        straight_distance_km: float,
        mode: str,
    ) -> dict[str, int]:
        route_distance_km = max(straight_distance_km * 1.32, straight_distance_km)
        if mode == "walk":
            speed_kmh = 4.5
            overhead_seconds = 0
        elif mode == "drive":
            speed_kmh = 30.0
            overhead_seconds = 6 * 60
        else:
            speed_kmh = 24.0
            overhead_seconds = 10 * 60

        duration_s = int(overhead_seconds + (route_distance_km / speed_kmh) * 3600)
        return {
            "distance_m": int(route_distance_km * 1000),
            "duration_s": max(60, duration_s),
        }

    def calculate_distance(
        self,
        from_lat: float,
        from_lng: float,
        to_lat: float,
        to_lng: float,
    ) -> float:
        """
        Return a simple distance metric between two coordinates.

        MVP can use a lightweight approximation or precomputed distance matrix.
        """
        from_lat_rad = math.radians(from_lat)
        from_lng_rad = math.radians(from_lng)
        to_lat_rad = math.radians(to_lat)
        to_lng_rad = math.radians(to_lng)

        delta_lat = to_lat_rad - from_lat_rad
        delta_lng = to_lng_rad - from_lng_rad
        a = (
            math.sin(delta_lat / 2) ** 2
            + math.cos(from_lat_rad)
            * math.cos(to_lat_rad)
            * math.sin(delta_lng / 2) ** 2
        )
        return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


    def infer_block_type(
        self,
        start_time: time,
        end_time: time,
    ) -> TimeBlockType:
        """
        Map a time range to morning / afternoon / evening for output grouping.
        """
        for block_type, (block_start, block_end) in (
            (TimeBlockType.MORNING, self.MORNING_WINDOW),
            (TimeBlockType.AFTERNOON, self.AFTERNOON_WINDOW),
            (TimeBlockType.EVENING, self.EVENING_WINDOW),
        ):
            if block_start <= start_time and end_time <= block_end:
                return block_type
        raise SchedulingError("Scheduled item falls outside default day blocks.")

    def build_response_days(
        self,
        trip_days: int,
        hotel: HotelStay,
        scheduled_by_day: dict[int, list[ScheduledPOI]],
        availability_windows: list[AvailabilityWindow] | None = None,
    ) -> list[DayItinerary]:
        """
        Convert internal schedule assignments into per-day response data.
        """
        day_windows = self.create_day_windows(trip_days, availability_windows)
        default_day_windows = self.create_day_windows(trip_days, None)
        response_days: list[DayItinerary] = []

        for day in range(1, trip_days + 1):
            day_items = sorted(
                scheduled_by_day.get(day, []),
                key=lambda item: (item.start_time, item.end_time, item.name),
            )
            blocks: list[DayTimeBlock] = []

            for window in day_windows[day]:
                block_items = [
                    item
                    for item in day_items
                    if self.infer_block_type(item.start_time, item.end_time) == window.block_type
                ]
                blocks.append(
                    DayTimeBlock(
                        block_type=window.block_type,
                        start_time=window.start_time,
                        end_time=window.end_time,
                        items=block_items,
                    )
                )

            response_days.append(
                DayItinerary(
                    day=day,
                    hotel=hotel,
                    availability_summary=build_day_availability_summary(
                        effective_windows=day_windows[day],
                        default_windows=default_day_windows[day],
                    ),
                    blocks=blocks,
                )
            )

        return response_days


def is_fixed_poi(poi: NormalizedPOI) -> bool:
    """
    Helper predicate for identifying constrained POIs.
    """
    return any(
        [
            poi.fixed_day is not None,
            poi.fixed_time_start is not None,
            poi.fixed_time_end is not None,
        ]
    )


def stable_candidate_id(poi: NormalizedPOI) -> str:
    return stable_subject_id(
        "candidate",
        poi.name.strip().casefold(),
        poi.type.value,
        poi.city or "",
        round(poi.latitude, 6),
        round(poi.longitude, 6),
    )


def stable_anchor_id(anchor: HotelStay | ScheduledPOI) -> str:
    return stable_subject_id(
        "anchor",
        anchor.name.strip().casefold(),
        getattr(anchor, "city", None) or "",
        round(anchor.latitude, 6),
        round(anchor.longitude, 6),
    )


def reason_code_for_candidate_rejection(reason: str) -> PlannerReasonCode:
    if "排序低于" in reason:
        return PlannerReasonCode.REJECTED_LOWER_RANKED_CANDIDATE
    if "不是它最合适的时段" in reason:
        return PlannerReasonCode.DEFERRED_TO_BETTER_TIME_BLOCK
    if "放不进当前剩余时段" in reason:
        return PlannerReasonCode.REJECTED_SLOT_DURATION_OVERFLOW
    if "分散规则" in reason:
        return PlannerReasonCode.DEFERRED_FOR_DAY_SPREAD
    return PlannerReasonCode.REJECTED_NO_AVAILABLE_SLOT


def filter_schedulable_pois(pois: list[NormalizedPOI]) -> list[NormalizedPOI]:
    """
    Return only scenic spots and restaurants for scheduling blocks.

    Hotel is an anchor and should not be scheduled as a normal activity.
    """
    return [poi for poi in pois if poi.type in {POIType.SCENIC, POIType.RESTAURANT}]


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def total_window_capacity_minutes() -> int:
    """
    Return the total schedulable minutes in one default day.
    """
    return sum(
        minutes_between(start_time, end_time)
        for start_time, end_time in (
            Scheduler.MORNING_WINDOW,
            Scheduler.AFTERNOON_WINDOW,
            Scheduler.EVENING_WINDOW,
        )
    )


def apply_boundary_availability(
    day_windows: dict[int, list[TimeWindow]],
    trip_days: int,
    availability_windows: list[AvailabilityWindow],
) -> None:
    """
    Apply only the simplest supported availability constraints:
    - late first day via available_start
    - early last day via available_end

    Unrecognized or unusable windows are ignored to preserve current behavior.
    """
    first_day_bounded_window = select_boundary_bounded_window(
        availability_windows,
        matches_boundary=is_first_day_availability_window,
    )
    last_day_bounded_window = select_boundary_bounded_window(
        availability_windows,
        matches_boundary=lambda window: is_last_day_availability_window(window, trip_days),
    )
    late_first_start = resolve_late_first_day_start(availability_windows)
    early_last_end = resolve_early_last_day_end(availability_windows, trip_days)

    if first_day_bounded_window is not None and 1 in day_windows:
        day_windows[1] = trim_time_windows(
            day_windows[1],
            available_start=first_day_bounded_window[0],
            available_end=first_day_bounded_window[1],
        )
    elif late_first_start is not None and 1 in day_windows:
        day_windows[1] = trim_time_windows(
            day_windows[1],
            available_start=late_first_start,
            available_end=None,
        )

    if last_day_bounded_window is not None and trip_days in day_windows:
        day_windows[trip_days] = trim_time_windows(
            day_windows[trip_days],
            available_start=last_day_bounded_window[0],
            available_end=last_day_bounded_window[1],
        )
    elif early_last_end is not None and trip_days in day_windows:
        day_windows[trip_days] = trim_time_windows(
            day_windows[trip_days],
            available_start=None,
            available_end=early_last_end,
        )


def select_boundary_bounded_window(
    availability_windows: list[AvailabilityWindow],
    matches_boundary,
) -> tuple[time, time] | None:
    """
    Deterministically choose one valid bounded window for a boundary day.
    """
    sorted_windows = sorted(
        availability_windows,
        key=lambda window: (
            window.day or 0,
            window.available_start or "",
            window.available_end or "",
            window.label or "",
        ),
    )

    for window in sorted_windows:
        if not matches_boundary(window):
            continue

        available_start = parse_time_text(window.available_start)
        available_end = parse_time_text(window.available_end)
        if available_start is None or available_end is None:
            continue
        if available_start >= available_end:
            continue

        return available_start, available_end

    return None


def apply_explicit_day_availability(
    day_windows: dict[int, list[TimeWindow]],
    trip_days: int,
    availability_windows: list[AvailabilityWindow],
) -> None:
    """
    Apply one explicit, day-indexed availability window to non-boundary days.

    Boundary-day handling remains in apply_boundary_availability() so the
    already-accepted first-day / last-day behavior stays unchanged.
    """
    selected_windows_by_day = select_explicit_day_windows(
        availability_windows,
        trip_days,
    )

    for day, (available_start, available_end) in selected_windows_by_day.items():
        if day not in day_windows:
            continue

        day_windows[day] = trim_time_windows(
            day_windows[day],
            available_start=available_start,
            available_end=available_end,
        )


def select_explicit_day_windows(
    availability_windows: list[AvailabilityWindow],
    trip_days: int,
) -> dict[int, tuple[time | None, time | None]]:
    """
    Deterministically choose at most one valid explicit availability window per
    non-boundary day. We use the first valid window after stable sorting rather
    than merging competing windows.
    """
    selected_by_day: dict[int, tuple[time | None, time | None]] = {}

    sorted_windows = sorted(
        availability_windows,
        key=lambda window: (
            window.day or 0,
            window.available_start or "",
            window.available_end or "",
            window.label or "",
        ),
    )

    for window in sorted_windows:
        if window.day is None:
            continue
        if window.day <= 1 or window.day >= trip_days:
            continue
        if window.day in selected_by_day:
            continue

        available_start = parse_time_text(window.available_start)
        available_end = parse_time_text(window.available_end)
        if available_start is None and available_end is None:
            continue
        if (
            available_start is not None
            and available_end is not None
            and available_start >= available_end
        ):
            continue

        selected_by_day[window.day] = (available_start, available_end)

    return selected_by_day


def resolve_late_first_day_start(
    availability_windows: list[AvailabilityWindow],
) -> time | None:
    recognized_starts: list[time] = []
    for window in availability_windows:
        if window.available_start is None or window.available_end is not None:
            continue
        if not is_first_day_availability_window(window):
            continue

        parsed_time = parse_time_text(window.available_start)
        if parsed_time is not None:
            recognized_starts.append(parsed_time)

    if not recognized_starts:
        return None
    return max(recognized_starts)


def resolve_early_last_day_end(
    availability_windows: list[AvailabilityWindow],
    trip_days: int,
) -> time | None:
    recognized_ends: list[time] = []
    for window in availability_windows:
        if window.available_end is None or window.available_start is not None:
            continue
        if not is_last_day_availability_window(window, trip_days):
            continue

        parsed_time = parse_time_text(window.available_end)
        if parsed_time is not None:
            recognized_ends.append(parsed_time)

    if not recognized_ends:
        return None
    return min(recognized_ends)


def trim_time_windows(
    windows: list[TimeWindow],
    available_start: time | None,
    available_end: time | None,
) -> list[TimeWindow]:
    trimmed: list[TimeWindow] = []

    for window in windows:
        start_time = max_time(window.start_time, available_start)
        end_time = min_time(window.end_time, available_end)
        if start_time >= end_time:
            continue

        trimmed.append(
            TimeWindow(
                day=window.day,
                block_type=window.block_type,
                start_time=start_time,
                end_time=end_time,
            )
        )

    return trimmed


def build_day_availability_summary(
    effective_windows: list[TimeWindow],
    default_windows: list[TimeWindow],
) -> DayAvailabilitySummary:
    was_trimmed = windows_signature(effective_windows) != windows_signature(default_windows)
    if not effective_windows:
        return DayAvailabilitySummary(was_trimmed=was_trimmed)

    return DayAvailabilitySummary(
        was_trimmed=was_trimmed,
        effective_start=min(window.start_time for window in effective_windows),
        effective_end=max(window.end_time for window in effective_windows),
        remaining_blocks=[
            RemainingBlockWindow(
                block_type=window.block_type,
                start_time=window.start_time,
                end_time=window.end_time,
            )
            for window in effective_windows
        ],
    )


def windows_signature(windows: list[TimeWindow]) -> list[tuple[str, time, time]]:
    return [
        (window.block_type.value, window.start_time, window.end_time)
        for window in windows
    ]


def was_trimmed_day_window(day: int, effective_windows: list[TimeWindow]) -> bool:
    return windows_signature(effective_windows) != windows_signature(
        default_time_windows_for_day(day)
    )


def default_time_windows_for_day(day: int) -> list[TimeWindow]:
    return [
        TimeWindow(
            day=day,
            block_type=block_type,
            start_time=start_time,
            end_time=end_time,
        )
        for block_type, (start_time, end_time) in (
            (TimeBlockType.MORNING, Scheduler.MORNING_WINDOW),
            (TimeBlockType.AFTERNOON, Scheduler.AFTERNOON_WINDOW),
            (TimeBlockType.EVENING, Scheduler.EVENING_WINDOW),
        )
    ]


def describe_day_availability(windows: list[TimeWindow]) -> str:
    if not windows:
        return "no usable planner windows remain"

    effective_start = min(window.start_time for window in windows)
    effective_end = max(window.end_time for window in windows)
    remaining_blocks = ", ".join(
        f"{window.block_type.value} {format_time_value(window.start_time)}-{format_time_value(window.end_time)}"
        for window in windows
    )
    return (
        f"usable time is {format_time_value(effective_start)}-{format_time_value(effective_end)}; "
        f"remaining blocks: {remaining_blocks}"
    )


def is_first_day_availability_window(window: AvailabilityWindow) -> bool:
    if window.day == 1:
        return True
    label = (window.label or "").casefold()
    return any(token in label for token in ("first day", "day 1", "第一天", "首日"))


def is_last_day_availability_window(
    window: AvailabilityWindow,
    trip_days: int,
) -> bool:
    if window.day == trip_days:
        return True
    label = (window.label or "").casefold()
    return any(token in label for token in ("last day", f"day {trip_days}", "最后一天", "末日"))


def parse_time_text(value: str | None) -> time | None:
    if not value:
        return None

    try:
        hour_text, minute_text = value.strip().split(":", 1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except (TypeError, ValueError):
        return None


def format_time_value(value: time) -> str:
    return value.strftime("%H:%M")


def build_placement_reason(
    slot: FreeSlot,
    poi: NormalizedPOI,
    apply_arrival_bias: bool,
    apply_departure_bias: bool,
) -> str:
    if apply_arrival_bias:
        return "放在靠前时段，是为了让到达后的第一段路线更顺。"
    if apply_departure_bias:
        return "放在靠后时段，是为了让最后一天更贴近离开方向。"
    if poi.profile.signal_summary:
        if slot.block_type in poi.profile.best_time_blocks:
            return localize_planner_reason(poi.profile.signal_summary)
        return f"{localize_planner_reason(poi.profile.signal_summary)} 这个时段虽然不是最优，但作为路线折中仍然可走。"
    if poi.profile.visit_style == POIVisitStyle.NIGHT_VIEW:
        return "放在较晚时段，是因为它更像夜景或夜游点。"
    if poi.profile.visit_style == POIVisitStyle.MUSEUM:
        return "放在白天，是因为博物馆类地点通常更适合傍晚前完成。"
    if poi.profile.visit_style in {POIVisitStyle.OLD_STREET, POIVisitStyle.LEISURE_DISTRICT}:
        return "放在这里，是因为街区型地点适合接在当天路线中段慢慢逛。"
    return "放在这里，是因为它能放进当前时段，并让当天路线更自然地继续。"


def localize_planner_reason(reason: str) -> str:
    normalized = reason.strip()
    lowered = normalized.casefold()
    if "food-street" in lowered or "night-market" in lowered:
        return "地点特征更接近美食街或夜市，放在晚上更自然。"
    if "park" in lowered or "temple" in lowered or "scenic venue" in lowered:
        return "地点特征更接近公园、寺庙或景区，放在白天更合适。"
    return normalized


def build_seed_candidate_rank_reason(
    *,
    rank_key: tuple[float, int, int, int, int, int, float, float, int, int, float, float, float, int, str, str],
    travel_info: dict[str, int | None],
) -> str:
    (
        block_preference,
        travel_band,
        arrival_band,
        departure_band,
        time_affinity,
        travel_mode_rank,
        day_profile_rank,
        cluster_density_band,
        return_to_base_rank,
        continuation_rank,
        cluster_density_cost,
        continuation_cost,
        travel_cost,
        duration_minutes,
        _poi_type,
        _poi_name,
    ) = rank_key
    travel_minutes = (
        round(travel_info["duration_s"] / 60)
        if travel_info.get("duration_s") is not None
        else None
    )
    travel_phrase = (
        f"从当前锚点过来约 {travel_minutes} 分钟"
        if travel_minutes is not None
        else "当前使用直线距离作为兜底估算"
    )
    return (
        f"综合时段匹配、到离开边界、交通方式、同日聚合度和停留时长排序；"
        f"当前交通成本 {round(travel_cost, 1)}，停留约 {duration_minutes} 分钟，{travel_phrase}。"
    )


def build_seed_candidate_rejection_reason(
    *,
    poi: NormalizedPOI,
    slot: FreeSlot,
    eligible_names: set[str],
) -> str | None:
    if poi.name in eligible_names:
        return "它适合这个时段，但排序低于最终选中的种草点。"
    if slot.block_type not in poi.profile.best_time_blocks:
        return (
            f"暂缓安排，因为{slot.block_type.value}不是它最合适的时段，"
            "放到后续偏好时段会让当天更顺。"
        )
    if poi.duration_minutes > minutes_between(slot.start_time, slot.end_time):
        return "它的游玩时长放不进当前剩余时段，因此被排除。"
    return "确定性分散规则暂缓了它，避免一个时段吸收过多灵活种草点。"


def build_fixed_item_reason(name: str, start_time: time, end_time: time) -> str:
    return (
        f"{name} 被固定在这里，因为用户给出了 "
        f"{format_time_value(start_time)}-{format_time_value(end_time)} 的必要时间窗。"
    )


def max_time(left: time, right: time | None) -> time:
    if right is None or left >= right:
        return left
    return right


def min_time(left: time, right: time | None) -> time:
    if right is None or left <= right:
        return left
    return right


def minutes_between(start_time: time, end_time: time) -> int:
    """
    Return the positive minute span between two times on the same day.
    """
    return (end_time.hour * 60 + end_time.minute) - (
        start_time.hour * 60 + start_time.minute
    )


def add_minutes(value: time, minutes: int) -> time:
    """
    Return a same-day time offset by the given number of minutes.
    """
    total_minutes = value.hour * 60 + value.minute + minutes
    return time(hour=total_minutes // 60, minute=total_minutes % 60)


def overlaps(
    start_a: time,
    end_a: time,
    start_b: time,
    end_b: time,
) -> bool:
    """
    Return whether two same-day time intervals overlap.
    """
    return start_a < end_b and start_b < end_a


def split_free_slot(
    free_slots: list[FreeSlot],
    target_slot: FreeSlot,
    used_start: time,
    used_end: time,
) -> list[FreeSlot]:
    """
    Replace one free slot with its remaining left/right segments after placement.
    """
    updated_slots: list[FreeSlot] = []

    for slot in free_slots:
        if slot != target_slot:
            updated_slots.append(slot)
            continue

        if slot.start_time < used_start:
            updated_slots.append(
                FreeSlot(
                    day=slot.day,
                    block_type=slot.block_type,
                    start_time=slot.start_time,
                    end_time=used_start,
                )
            )
        if used_end < slot.end_time:
            updated_slots.append(
                FreeSlot(
                    day=slot.day,
                    block_type=slot.block_type,
                    start_time=used_end,
                    end_time=slot.end_time,
                )
            )

    return updated_slots


def get_anchor_for_slot(
    hotel: HotelStay,
    scheduled_items: list[ScheduledPOI],
    slot: FreeSlot,
) -> HotelStay | ScheduledPOI:
    """
    Return the latest scheduled item in the same block before this slot, or the hotel.
    """
    block_items = [
        item
        for item in scheduled_items
        if item.end_time <= slot.start_time and block_type_for_time_range(item.start_time, item.end_time) == slot.block_type
    ]
    if not block_items:
        return hotel
    return max(block_items, key=lambda item: (item.end_time, item.start_time, item.name))


def count_scheduled_items_in_block(
    scheduled_items: list[ScheduledPOI],
    block_type: TimeBlockType,
) -> int:
    return sum(
        1
        for item in scheduled_items
        if block_type_for_time_range(item.start_time, item.end_time) == block_type
    )


def occupied_minutes_in_block(
    scheduled_items: list[ScheduledPOI],
    block_type: TimeBlockType,
) -> int:
    return sum(
        minutes_between(item.start_time, item.end_time)
        for item in scheduled_items
        if block_type_for_time_range(item.start_time, item.end_time) == block_type
    )


def remaining_free_minutes_in_block(
    free_slots: list[FreeSlot],
    block_type: TimeBlockType,
) -> int:
    return sum(
        minutes_between(slot.start_time, slot.end_time)
        for slot in free_slots
        if slot.block_type == block_type
    )


def block_capacity_minutes(block_type: TimeBlockType) -> int:
    if block_type == TimeBlockType.MORNING:
        return minutes_between(*Scheduler.MORNING_WINDOW)
    if block_type == TimeBlockType.AFTERNOON:
        return minutes_between(*Scheduler.AFTERNOON_WINDOW)
    return minutes_between(*Scheduler.EVENING_WINDOW)


def block_type_for_time_range(start_time: time, end_time: time) -> TimeBlockType:
    """
    Return the matching default day block for a time range.
    """
    for block_type, (block_start, block_end) in (
        (TimeBlockType.MORNING, Scheduler.MORNING_WINDOW),
        (TimeBlockType.AFTERNOON, Scheduler.AFTERNOON_WINDOW),
        (TimeBlockType.EVENING, Scheduler.EVENING_WINDOW),
    ):
        if block_start <= start_time and end_time <= block_end:
            return block_type
    raise SchedulingError("Scheduled item falls outside default day blocks.")


def block_preference_rank(block_type: TimeBlockType, poi_type: POIType) -> int:
    """
    Return a soft ranking score for how well a POI type fits a day block.

    Lower is better. This is a preference only, not a hard constraint.
    """
    if block_type in {TimeBlockType.MORNING, TimeBlockType.AFTERNOON}:
        if poi_type == POIType.SCENIC:
            return 0
        return 3 if block_type == TimeBlockType.MORNING else 2
    if block_type == TimeBlockType.EVENING:
        return 0 if poi_type == POIType.RESTAURANT else 3
    return 1
