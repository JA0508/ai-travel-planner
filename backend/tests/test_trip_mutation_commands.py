from __future__ import annotations

import unittest
from datetime import time

from app.schemas import (
    DayItinerary,
    DayTimeBlock,
    HotelStay,
    ItineraryResponse,
    PlanningAnchorSource,
    POIType,
    ScheduledPOI,
    ScheduledPOISourceType,
    TimeBlockType,
    VerifiedPlaceRef,
)
from app.trips.errors import MutationCommandFailedError, MutationCommandNoEffectError
from app.trips.mutation_commands import (
    TripMutationCommandEnvelope,
    TripMutationEngine,
    collect_item_ids,
    ensure_stable_item_ids,
)


class TripMutationCommandTests(unittest.TestCase):
    def test_stable_ids_are_added_deterministically_to_legacy_snapshots(self) -> None:
        first = ensure_stable_item_ids(command_itinerary().model_dump(mode="json"))
        second = ensure_stable_item_ids(command_itinerary().model_dump(mode="json"))

        self.assertEqual(collect_item_ids(first), collect_item_ids(second))
        self.assertEqual(len(collect_item_ids(first)), 3)

    def test_move_stop_preview_preserves_identity_and_invalidates_derived_surfaces(self) -> None:
        snapshot = ensure_stable_item_ids(command_itinerary().model_dump(mode="json"))
        stop_id = stop_id_by_name(snapshot, "豫园")
        anchor_id = stop_id_by_name(snapshot, "上海博物馆")

        preview = TripMutationEngine().preview(
            base_snapshot=snapshot,
            envelope=TripMutationCommandEnvelope.model_validate(
                {
                    "base_revision_id": "rev_1",
                    "mutation_kind": "route_edit",
                    "commands": [
                        {
                            "type": "move_stop",
                            "stop_id": stop_id,
                            "target_day": 1,
                            "target_block": "morning",
                            "placement": {"before_stop_id": anchor_id},
                        }
                    ],
                }
            ),
        )

        names = flattened_names(preview.resulting_snapshot)
        self.assertEqual(names, ["豫园", "上海博物馆", "外滩"])
        self.assertIn(stop_id, collect_item_ids(preview.resulting_snapshot))
        self.assertEqual(preview.validation_report["status"], "valid")
        self.assertIn("route_segments", preview.invalidated_surfaces)
        moved = find_item(preview.resulting_snapshot, "豫园")
        self.assertEqual(moved["travel_calculation_status"], "deterministic_local_estimate")
        self.assertIsNotNone(moved["travel_duration_s"])

    def test_reorder_day_preview_keeps_same_stop_set(self) -> None:
        snapshot = ensure_stable_item_ids(command_itinerary().model_dump(mode="json"))
        ordered = [
            stop_id_by_name(snapshot, "豫园"),
            stop_id_by_name(snapshot, "上海博物馆"),
            stop_id_by_name(snapshot, "外滩"),
        ]

        preview = TripMutationEngine().preview(
            base_snapshot=snapshot,
            envelope=TripMutationCommandEnvelope.model_validate(
                {
                    "base_revision_id": "rev_1",
                    "mutation_kind": "route_edit",
                    "commands": [{"type": "reorder_day", "day": 1, "ordered_stop_ids": ordered}],
                }
            ),
        )

        self.assertEqual(flattened_names(preview.resulting_snapshot), ["豫园", "上海博物馆", "外滩"])
        self.assertEqual(collect_item_ids(preview.resulting_snapshot), set(ordered))

    def test_remove_fixed_stop_is_rejected(self) -> None:
        snapshot = ensure_stable_item_ids(command_itinerary(fixed_museum=True).model_dump(mode="json"))

        with self.assertRaises(MutationCommandFailedError) as caught:
            TripMutationEngine().preview(
                base_snapshot=snapshot,
                envelope=TripMutationCommandEnvelope.model_validate(
                    {
                        "base_revision_id": "rev_1",
                        "mutation_kind": "route_edit",
                        "commands": [
                            {"type": "remove_stop", "stop_id": stop_id_by_name(snapshot, "上海博物馆")}
                        ],
                    }
                ),
            )

        self.assertEqual(caught.exception.context["reason_code"], "fixed_event_mutation_forbidden")

    def test_local_repair_scope_rejects_fixed_and_user_owned_stops(self) -> None:
        snapshot = ensure_stable_item_ids(command_itinerary(fixed_museum=True).model_dump(mode="json"))
        for name in ("上海博物馆", "豫园"):
            with self.subTest(name=name), self.assertRaises(MutationCommandFailedError) as caught:
                TripMutationEngine().preview(
                    base_snapshot=snapshot,
                    envelope=TripMutationCommandEnvelope.model_validate(
                        {
                            "base_revision_id": "rev_1",
                            "mutation_kind": "route_edit",
                            "repair": {"target_day": 1, "goal": "relax_day"},
                            "commands": [{"type": "remove_stop", "stop_id": stop_id_by_name(snapshot, name)}],
                        }
                    ),
                )
            self.assertEqual(caught.exception.context["reason_code"], "local_repair_protected_item")

    def test_local_repair_moves_only_system_suggested_item_without_planner_work(self) -> None:
        snapshot = ensure_stable_item_ids(command_itinerary(system_yu=True).model_dump(mode="json"))
        yu_id = stop_id_by_name(snapshot, "豫园")

        preview = TripMutationEngine().preview(
            base_snapshot=snapshot,
            envelope=TripMutationCommandEnvelope.model_validate(
                {
                    "base_revision_id": "rev_1",
                    "mutation_kind": "route_edit",
                    "repair": {"target_day": 1, "goal": "relax_day"},
                    "commands": [{"type": "remove_stop", "stop_id": yu_id}],
                }
            ),
        )

        self.assertNotIn("豫园", flattened_names(preview.resulting_snapshot))
        self.assertIn("上海博物馆", flattened_names(preview.resulting_snapshot))
        self.assertEqual(preview.impact_summary["repair"], {"target_day": 1, "goal": "relax_day"})
        self.assertEqual(
            preview.impact_summary["execution_evidence"],
            {"planner_calls": 0, "parser_calls": 0, "llm_calls": 0, "route_provider_calls": 0},
        )
        self.assertIsNotNone(preview.resulting_snapshot["planner_realism"])

    def test_swap_preview_exchanges_slots_without_reassigning_stable_ids(self) -> None:
        snapshot = ensure_stable_item_ids(command_itinerary().model_dump(mode="json"))
        museum_id = stop_id_by_name(snapshot, "上海博物馆")
        bund_id = stop_id_by_name(snapshot, "外滩")

        preview = TripMutationEngine().preview(
            base_snapshot=snapshot,
            envelope=TripMutationCommandEnvelope.model_validate(
                {
                    "base_revision_id": "rev_1",
                    "mutation_kind": "swap",
                    "commands": [
                        {"type": "swap_stops", "first_stop_id": museum_id, "second_stop_id": bund_id}
                    ],
                }
            ),
        )

        museum = find_item(preview.resulting_snapshot, "上海博物馆")
        bund = find_item(preview.resulting_snapshot, "外滩")
        self.assertEqual(museum["stable_id"], museum_id)
        self.assertEqual(bund["stable_id"], bund_id)
        self.assertEqual(museum["start_time"], "14:30:00")
        self.assertEqual(bund["start_time"], "09:00:00")
        self.assertEqual(preview.impact_summary["swapped_stop_ids"], [museum_id, bund_id])

    def test_replace_stop_preview_preserves_slot_identity_for_completion_swap(self) -> None:
        snapshot = ensure_stable_item_ids(command_itinerary(system_yu=True).model_dump(mode="json"))
        replaceable_id = stop_id_by_name(snapshot, "豫园")

        preview = TripMutationEngine().preview(
            base_snapshot=snapshot,
            envelope=replace_envelope(snapshot, "豫园"),
        )

        replacement = find_item(preview.resulting_snapshot, "田子坊")
        self.assertEqual(replacement["stable_id"], replaceable_id)
        self.assertEqual(replacement["start_time"], "11:15:00")
        self.assertEqual(preview.impact_summary["replaced_stop_ids"], [replaceable_id])
        self.assertEqual(replacement["canonical_place_id"], "shanghai:tianzifang")
        self.assertEqual(
            replacement["verified_place"]["provider_place_id"],
            "shanghai:tianzifang",
        )
        self.assertIn("selection", preview.invalidated_surfaces)

    def test_replace_stop_rejects_user_fixed_and_must_visit_targets(self) -> None:
        cases = (
            (command_itinerary(), "上海博物馆", "replace_target_not_eligible"),
            (command_itinerary(fixed_museum=True), "上海博物馆", "fixed_event_mutation_forbidden"),
            (command_itinerary(system_yu=True, must_yu=True), "豫园", "replace_target_not_eligible"),
        )
        for itinerary, target_name, reason_code in cases:
            snapshot = ensure_stable_item_ids(itinerary.model_dump(mode="json"))
            with self.subTest(target_name=target_name), self.assertRaises(
                MutationCommandFailedError
            ) as caught:
                TripMutationEngine().preview(
                    base_snapshot=snapshot,
                    envelope=replace_envelope(snapshot, target_name),
                )
            self.assertEqual(caught.exception.context["reason_code"], reason_code)

    def test_no_effect_command_is_rejected_before_persistence(self) -> None:
        snapshot = ensure_stable_item_ids(command_itinerary().model_dump(mode="json"))
        museum_id = stop_id_by_name(snapshot, "上海博物馆")
        yu_id = stop_id_by_name(snapshot, "豫园")

        with self.assertRaises(MutationCommandNoEffectError):
            TripMutationEngine().preview(
                base_snapshot=snapshot,
                envelope=TripMutationCommandEnvelope.model_validate(
                    {
                        "base_revision_id": "rev_1",
                        "mutation_kind": "route_edit",
                        "commands": [
                            {
                                "type": "move_stop",
                                "stop_id": yu_id,
                                "target_day": 1,
                                "target_block": "morning",
                                "placement": {"after_stop_id": museum_id},
                            }
                        ],
                    }
                ),
            )

    def test_invalid_target_id_is_rejected_without_mutating_base_snapshot(self) -> None:
        snapshot = ensure_stable_item_ids(command_itinerary().model_dump(mode="json"))

        with self.assertRaises(MutationCommandFailedError) as caught:
            TripMutationEngine().preview(
                base_snapshot=snapshot,
                envelope=TripMutationCommandEnvelope.model_validate(
                    {
                        "base_revision_id": "rev_1",
                        "mutation_kind": "route_edit",
                        "commands": [{"type": "remove_stop", "stop_id": "stop_missing"}],
                    }
                ),
            )

        self.assertEqual(caught.exception.context["reason_code"], "mutation_command_target_not_found")
        self.assertEqual(flattened_names(snapshot), ["上海博物馆", "豫园", "外滩"])

    def test_command_batch_is_atomic_when_later_command_fails(self) -> None:
        snapshot = ensure_stable_item_ids(command_itinerary(fixed_museum=True).model_dump(mode="json"))
        yu_id = stop_id_by_name(snapshot, "豫园")
        museum_id = stop_id_by_name(snapshot, "上海博物馆")

        with self.assertRaises(MutationCommandFailedError) as caught:
            TripMutationEngine().preview(
                base_snapshot=snapshot,
                envelope=TripMutationCommandEnvelope.model_validate(
                    {
                        "base_revision_id": "rev_1",
                        "mutation_kind": "route_edit",
                        "commands": [
                            {"type": "remove_stop", "stop_id": yu_id},
                            {"type": "remove_stop", "stop_id": museum_id},
                        ],
                    }
                ),
            )

        self.assertEqual(caught.exception.context["reason_code"], "fixed_event_mutation_forbidden")
        self.assertEqual(flattened_names(snapshot), ["上海博物馆", "豫园", "外滩"])


def command_itinerary(
    *,
    fixed_museum: bool = False,
    system_yu: bool = False,
    must_yu: bool = False,
) -> ItineraryResponse:
    hotel = HotelStay(name="人民广场酒店", city="上海", latitude=31.2304, longitude=121.4737)
    return ItineraryResponse(
        trip_days=1,
        planning_anchor_source=PlanningAnchorSource(
            source_type="provided_hotel",
            source_name=hotel.name,
            latitude=hotel.latitude,
            longitude=hotel.longitude,
        ),
        days=[
            DayItinerary(
                day=1,
                hotel=hotel,
                blocks=[
                    DayTimeBlock(
                        block_type=TimeBlockType.MORNING,
                        start_time=time(9, 0),
                        end_time=time(12, 0),
                        items=[
                            scheduled_item(
                                "上海博物馆",
                                TimeBlockType.MORNING,
                                time(9, 0),
                                time(11, 0),
                                fixed=fixed_museum,
                            ),
                            scheduled_item(
                                "豫园",
                                TimeBlockType.MORNING,
                                time(11, 15),
                                time(12, 0),
                                source_type=(
                                    ScheduledPOISourceType.AUTO_SEEDED_POI
                                    if system_yu
                                    else ScheduledPOISourceType.USER_SEED
                                ),
                                source_label="必去" if must_yu else None,
                                verified=system_yu,
                            ),
                        ],
                    ),
                    DayTimeBlock(
                        block_type=TimeBlockType.AFTERNOON,
                        start_time=time(14, 0),
                        end_time=time(18, 0),
                        items=[
                            scheduled_item(
                                "外滩",
                                TimeBlockType.AFTERNOON,
                                time(14, 30),
                                time(16, 0),
                            )
                        ],
                    ),
                ],
            )
        ],
    )


def scheduled_item(
    name: str,
    block_type: TimeBlockType,
    start: time,
    end: time,
    *,
    fixed: bool = False,
    source_type: ScheduledPOISourceType = ScheduledPOISourceType.USER_SEED,
    source_label: str | None = None,
    verified: bool = False,
) -> ScheduledPOI:
    return ScheduledPOI(
        name=name,
        type=POIType.SCENIC,
        city="上海",
        latitude=31.23,
        longitude=121.47,
        duration_minutes=60,
        day=1,
        start_time=start,
        end_time=end,
        is_fixed=fixed,
        source_type=ScheduledPOISourceType.USER_FIXED if fixed else source_type,
        source_label=source_label,
        canonical_place_id=(f"amap:shanghai:{name}" if verified else None),
        verified_place=(
            VerifiedPlaceRef(
                stable_id=f"place-shanghai:{name}",
                original_name=name,
                provider="amap",
                provider_place_id=f"shanghai:{name}",
                canonical_name=name,
                latitude=31.23,
                longitude=121.47,
                category="风景名胜",
            )
            if verified
            else None
        ),
        travel_from_name="人民广场酒店" if block_type == TimeBlockType.MORNING else "豫园",
        travel_distance_m=1200,
        travel_duration_s=900,
    )


def replace_envelope(snapshot: dict, target_name: str) -> TripMutationCommandEnvelope:
    return TripMutationCommandEnvelope.model_validate(
        {
            "base_revision_id": "rev_1",
            "mutation_kind": "swap",
            "commands": [
                {
                    "type": "replace_stop",
                    "stop_id": stop_id_by_name(snapshot, target_name),
                    "replacement": {
                        "name": "田子坊",
                        "type": "scenic",
                        "reasoning_summary": "使用已验证的系统候选。",
                        "itinerary_relation_summary": "只替换当前时间槽。",
                        "verified_place": {
                            "stable_id": "place-shanghai:tianzifang",
                            "original_name": "田子坊",
                            "provider": "amap",
                            "provider_place_id": "shanghai:tianzifang",
                            "canonical_name": "田子坊",
                            "latitude": 31.2107,
                            "longitude": 121.4688,
                            "category": "风景名胜",
                            "source_fragment_ids": [],
                        },
                        "route_impact": {
                            "safe_to_apply": True,
                            "before_duration_s": 1800,
                            "after_duration_s": 1500,
                            "delta_duration_s": -300,
                            "inbound": {
                                "from_name": "上海博物馆",
                                "to_name": "田子坊",
                                "distance_m": 900,
                                "duration_s": 600,
                                "provider": "amap",
                                "data_status": "confirmed",
                            },
                            "outbound": {
                                "from_name": "田子坊",
                                "to_name": "外滩",
                                "distance_m": 900,
                                "duration_s": 900,
                                "provider": "amap",
                                "data_status": "confirmed",
                            },
                        },
                    },
                }
            ],
        }
    )


def flattened_names(snapshot: dict) -> list[str]:
    return [
        item["name"]
        for day in snapshot["days"]
        for block in day["blocks"]
        for item in block["items"]
    ]


def find_item(snapshot: dict, name: str) -> dict:
    return next(
        item
        for day in snapshot["days"]
        for block in day["blocks"]
        for item in block["items"]
        if item["name"] == name
    )


def stop_id_by_name(snapshot: dict, name: str) -> str:
    return find_item(snapshot, name)["stable_id"]


if __name__ == "__main__":
    unittest.main()
