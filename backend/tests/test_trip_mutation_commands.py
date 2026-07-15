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
        self.assertIsNone(moved["travel_duration_s"])

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
        snapshot = ensure_stable_item_ids(command_itinerary().model_dump(mode="json"))
        museum_id = stop_id_by_name(snapshot, "上海博物馆")

        preview = TripMutationEngine().preview(
            base_snapshot=snapshot,
            envelope=TripMutationCommandEnvelope.model_validate(
                {
                    "base_revision_id": "rev_1",
                    "mutation_kind": "swap",
                    "commands": [
                        {
                            "type": "replace_stop",
                            "stop_id": museum_id,
                            "replacement": {
                                "name": "田子坊",
                                "type": "scenic",
                                "reasoning_summary": "更适合轻松街区体验。",
                                "itinerary_relation_summary": "保留上午 slot，不改变固定时间边界。",
                            },
                        }
                    ],
                }
            ),
        )

        replacement = find_item(preview.resulting_snapshot, "田子坊")
        self.assertEqual(replacement["stable_id"], museum_id)
        self.assertEqual(replacement["start_time"], "09:00:00")
        self.assertEqual(preview.impact_summary["replaced_stop_ids"], [museum_id])
        self.assertIn("selection", preview.invalidated_surfaces)

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


def command_itinerary(*, fixed_museum: bool = False) -> ItineraryResponse:
    hotel = HotelStay(name="人民广场酒店", city="上海", latitude=31.2304, longitude=121.4737)
    return ItineraryResponse(
        trip_days=1,
        planning_anchor_source=PlanningAnchorSource(
            source_type="city",
            source_name="上海",
            latitude=31.2304,
            longitude=121.4737,
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
        source_type=ScheduledPOISourceType.USER_FIXED if fixed else ScheduledPOISourceType.USER_SEED,
        travel_from_name="人民广场酒店" if block_type == TimeBlockType.MORNING else "豫园",
        travel_distance_m=1200,
        travel_duration_s=900,
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
