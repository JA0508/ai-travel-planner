from __future__ import annotations

import unittest
from datetime import time

from app.core.scheduler import Scheduler
from app.schemas import (
    HotelStay,
    NormalizedPOI,
    POIProfile,
    POIType,
    POIVisitStyle,
    PlanningAnchorSource,
    TimeBlockType,
)
from app.services.itinerary_completion_recommendation import (
    apply_completion_recommendation_autofill,
    build_itinerary_completion_recommendation,
)


class SchedulerFirstPassTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = Scheduler()
        self.hotel = HotelStay(
            name="人民广场酒店",
            city="上海",
            latitude=31.2304,
            longitude=121.4737,
        )
        self.anchor_source = PlanningAnchorSource(
            source_type="provided_hotel",
            source_name=self.hotel.name,
        )

    def make_poi(
        self,
        *,
        name: str,
        visit_style: POIVisitStyle,
        best_time_blocks: list[TimeBlockType],
        intensity: str,
        duration_minutes: int,
        latitude: float,
        longitude: float,
        poi_type: POIType = POIType.SCENIC,
    ) -> NormalizedPOI:
        return NormalizedPOI(
            name=name,
            type=poi_type,
            city="上海",
            latitude=latitude,
            longitude=longitude,
            duration_minutes=duration_minutes,
            profile=POIProfile(
                visit_style=visit_style,
                best_time_blocks=best_time_blocks,
                typical_duration_minutes=duration_minutes,
                intensity=intensity,
            ),
        )

    def test_scheduler_defers_afternoon_only_museum_out_of_morning_slot(self) -> None:
        itinerary = self.scheduler.build_schedule(
            scenic_spots=[
                self.make_poi(
                    name="上海博物馆",
                    visit_style=POIVisitStyle.MUSEUM,
                    best_time_blocks=[TimeBlockType.AFTERNOON],
                    intensity="heavy",
                    duration_minutes=120,
                    latitude=31.23041,
                    longitude=121.4737,
                )
            ],
            restaurants=[],
            hotel=self.hotel,
            planning_anchor_source=self.anchor_source,
            trip_days=1,
        )

        day_one = itinerary.days[0]
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.MORNING).items],
            [],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["上海博物馆"],
        )

    def test_scheduler_places_restaurants_as_lunch_and_dinner_anchors(self) -> None:
        itinerary = self.scheduler.build_schedule(
            scenic_spots=[
                self.make_poi(
                    name="静安寺",
                    visit_style=POIVisitStyle.TEMPLE_PARK,
                    best_time_blocks=[TimeBlockType.MORNING],
                    intensity="medium",
                    duration_minutes=90,
                    latitude=31.22346,
                    longitude=121.44531,
                ),
                self.make_poi(
                    name="思南公馆",
                    visit_style=POIVisitStyle.OLD_STREET,
                    best_time_blocks=[TimeBlockType.AFTERNOON],
                    intensity="medium",
                    duration_minutes=75,
                    latitude=31.21992,
                    longitude=121.46753,
                ),
                self.make_poi(
                    name="外滩",
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.238235,
                    longitude=121.497253,
                ),
            ],
            restaurants=[
                self.make_poi(
                    name="人民广场本帮菜午餐",
                    visit_style=POIVisitStyle.FOOD_STOP,
                    best_time_blocks=[TimeBlockType.AFTERNOON],
                    intensity="medium",
                    duration_minutes=60,
                    latitude=31.2304,
                    longitude=121.4737,
                    poi_type=POIType.RESTAURANT,
                ),
                self.make_poi(
                    name="城隍庙小吃街",
                    visit_style=POIVisitStyle.FOOD_DISTRICT,
                    best_time_blocks=[TimeBlockType.EVENING],
                    intensity="medium",
                    duration_minutes=60,
                    latitude=31.22738,
                    longitude=121.49058,
                    poi_type=POIType.RESTAURANT,
                ),
            ],
            hotel=self.hotel,
            planning_anchor_source=self.anchor_source,
            trip_days=1,
        )

        day_one = itinerary.days[0]
        afternoon_items = next(
            block for block in day_one.blocks if block.block_type == TimeBlockType.AFTERNOON
        ).items
        evening_items = next(
            block for block in day_one.blocks if block.block_type == TimeBlockType.EVENING
        ).items
        self.assertEqual(afternoon_items[0].type, POIType.RESTAURANT)
        self.assertEqual([item.name for item in afternoon_items], ["人民广场本帮菜午餐", "思南公馆"])
        self.assertEqual(evening_items[0].type, POIType.RESTAURANT)
        self.assertEqual([item.name for item in evening_items], ["城隍庙小吃街", "外滩"])
        self.assertTrue(afternoon_items[0].selection_top_candidates)
        self.assertEqual(afternoon_items[0].selection_top_candidates[0].status, "selected")
        self.assertIn(
            "综合时段匹配",
            afternoon_items[0].selection_top_candidates[0].reason,
        )
        self.assertTrue(
            afternoon_items[1].selection_top_candidates
            or afternoon_items[1].selection_rejected_candidates
        )

    def test_scheduler_keeps_night_view_for_evening_instead_of_filling_morning(self) -> None:
        itinerary = self.scheduler.build_schedule(
            scenic_spots=[
                self.make_poi(
                    name="外滩",
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.238235,
                    longitude=121.497253,
                ),
                self.make_poi(
                    name="静安寺",
                    visit_style=POIVisitStyle.TEMPLE_PARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    intensity="medium",
                    duration_minutes=90,
                    latitude=31.22346,
                    longitude=121.44531,
                ),
            ],
            restaurants=[],
            hotel=self.hotel,
            planning_anchor_source=self.anchor_source,
            trip_days=1,
        )

        day_one = itinerary.days[0]
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.MORNING).items],
            ["静安寺"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.EVENING).items],
            ["外滩"],
        )

    def test_scheduler_uses_neutral_landmark_to_backfill_morning_while_preserving_evening_poi(self) -> None:
        itinerary = self.scheduler.build_schedule(
            scenic_spots=[
                self.make_poi(
                    name="外滩",
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.238235,
                    longitude=121.497253,
                ),
                self.make_poi(
                    name="城市地标",
                    visit_style=POIVisitStyle.LANDMARK,
                    best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.2305,
                    longitude=121.4740,
                ),
            ],
            restaurants=[],
            hotel=self.hotel,
            planning_anchor_source=self.anchor_source,
            trip_days=1,
        )

        day_one = itinerary.days[0]
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.MORNING).items],
            ["城市地标"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.EVENING).items],
            ["外滩"],
        )

    def test_scheduler_spreads_daytime_pois_across_morning_and_afternoon_when_evening_is_reserved(self) -> None:
        itinerary = self.scheduler.build_schedule(
            scenic_spots=[
                self.make_poi(
                    name="人民广场",
                    visit_style=POIVisitStyle.LANDMARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.2304,
                    longitude=121.4737,
                ),
                self.make_poi(
                    name="静安寺",
                    visit_style=POIVisitStyle.TEMPLE_PARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    intensity="medium",
                    duration_minutes=90,
                    latitude=31.22346,
                    longitude=121.44531,
                ),
                self.make_poi(
                    name="外滩",
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.238235,
                    longitude=121.497253,
                ),
            ],
            restaurants=[],
            hotel=self.hotel,
            planning_anchor_source=self.anchor_source,
            trip_days=1,
        )

        day_one = itinerary.days[0]
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.MORNING).items],
            ["人民广场"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["静安寺"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.EVENING).items],
            ["外滩"],
        )

    def test_scheduler_uses_later_underused_evening_block_when_fixed_item_already_exists(self) -> None:
        itinerary = self.scheduler.build_schedule(
            scenic_spots=[
                self.make_poi(
                    name="人民广场",
                    visit_style=POIVisitStyle.LANDMARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.2304,
                    longitude=121.4737,
                ),
                self.make_poi(
                    name="城市广场",
                    visit_style=POIVisitStyle.GENERAL,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    intensity="medium",
                    duration_minutes=75,
                    latitude=31.2305,
                    longitude=121.4739,
                ),
                self.make_poi(
                    name="思南公馆",
                    visit_style=POIVisitStyle.LEISURE_DISTRICT,
                    best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=90,
                    latitude=31.21992,
                    longitude=121.46753,
                ),
                self.make_poi(
                    name="外滩",
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.238235,
                    longitude=121.497253,
                ).model_copy(
                    update={
                        "fixed_day": 1,
                        "fixed_time_start": time(19, 0),
                        "fixed_time_end": time(20, 0),
                    }
                ),
            ],
            restaurants=[],
            hotel=self.hotel,
            planning_anchor_source=self.anchor_source,
            trip_days=1,
        )

        day_one = itinerary.days[0]
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.MORNING).items],
            ["人民广场"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["城市广场"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.EVENING).items],
            ["思南公馆", "外滩"],
        )

    def test_scheduler_avoids_overcompressing_morning_when_afternoon_can_absorb_candidate(self) -> None:
        itinerary = self.scheduler.build_schedule(
            scenic_spots=[
                self.make_poi(
                    name="人民广场",
                    visit_style=POIVisitStyle.LANDMARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.2304,
                    longitude=121.4737,
                ).model_copy(
                    update={
                        "fixed_day": 1,
                        "fixed_time_start": time(9, 0),
                        "fixed_time_end": time(10, 0),
                    }
                ),
                self.make_poi(
                    name="城市广场",
                    visit_style=POIVisitStyle.GENERAL,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    intensity="medium",
                    duration_minutes=75,
                    latitude=31.2305,
                    longitude=121.4739,
                ).model_copy(
                    update={
                        "fixed_day": 1,
                        "fixed_time_start": time(13, 0),
                        "fixed_time_end": time(14, 15),
                    }
                ),
                self.make_poi(
                    name="静安寺",
                    visit_style=POIVisitStyle.TEMPLE_PARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    intensity="medium",
                    duration_minutes=90,
                    latitude=31.22346,
                    longitude=121.44531,
                ),
                self.make_poi(
                    name="外滩",
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.238235,
                    longitude=121.497253,
                ).model_copy(
                    update={
                        "fixed_day": 1,
                        "fixed_time_start": time(19, 0),
                        "fixed_time_end": time(20, 0),
                    }
                ),
            ],
            restaurants=[],
            hotel=self.hotel,
            planning_anchor_source=self.anchor_source,
            trip_days=1,
        )

        day_one = itinerary.days[0]
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.MORNING).items],
            ["人民广场"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["城市广场", "静安寺"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.EVENING).items],
            ["外滩"],
        )

    def test_scheduler_does_not_over_backfill_morning_with_non_neutral_old_street(self) -> None:
        itinerary = self.scheduler.build_schedule(
            scenic_spots=[
                self.make_poi(
                    name="外滩",
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.238235,
                    longitude=121.497253,
                ),
                self.make_poi(
                    name="新天地",
                    visit_style=POIVisitStyle.OLD_STREET,
                    best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
                    intensity="medium",
                    duration_minutes=75,
                    latitude=31.21943,
                    longitude=121.47529,
                ),
            ],
            restaurants=[],
            hotel=self.hotel,
            planning_anchor_source=self.anchor_source,
            trip_days=1,
        )

        day_one = itinerary.days[0]
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.MORNING).items],
            [],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["新天地"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.EVENING).items],
            ["外滩"],
        )

    def test_completion_autofill_still_builds_on_improved_first_pass_output(self) -> None:
        itinerary = self.scheduler.build_schedule(
            scenic_spots=[
                self.make_poi(
                    name="思南公馆",
                    visit_style=POIVisitStyle.LEISURE_DISTRICT,
                    best_time_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=90,
                    latitude=31.21992,
                    longitude=121.46753,
                )
            ],
            restaurants=[
                self.make_poi(
                    name="BFC 外滩枫径",
                    visit_style=POIVisitStyle.FOOD_DISTRICT,
                    best_time_blocks=[TimeBlockType.EVENING],
                    intensity="light",
                    duration_minutes=60,
                    latitude=31.23374,
                    longitude=121.49759,
                    poi_type=POIType.RESTAURANT,
                )
            ],
            hotel=self.hotel,
            planning_anchor_source=self.anchor_source,
            trip_days=1,
        )

        day_one = itinerary.days[0]
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["思南公馆"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.EVENING).items],
            ["BFC 外滩枫径"],
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)
        self.assertIsNotNone(recommendation)

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)
        filled_day = autofilled.days[0]
        self.assertEqual(
            [item.name for item in next(block for block in filled_day.blocks if block.block_type == TimeBlockType.MORNING).items],
            ["豫园"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in filled_day.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["思南公馆"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in filled_day.blocks if block.block_type == TimeBlockType.EVENING).items],
            ["BFC 外滩枫径", "南京路步行街"],
        )
        self.assertIsNone(build_itinerary_completion_recommendation(autofilled))


if __name__ == "__main__":
    unittest.main()
