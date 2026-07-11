from __future__ import annotations

import unittest
from datetime import time

from app.schemas import (
    DayItinerary,
    DayTimeBlock,
    DayAvailabilitySummary,
    HotelStay,
    POIType,
    ScheduledPOI,
    ScheduledPOISourceType,
    TimeBlockType,
)
from app.services.poi_research_summary import build_poi_research_summary


class POIResearchSummaryTests(unittest.TestCase):
    def test_restaurant_research_uses_route_and_meal_context(self) -> None:
        item = ScheduledPOI(
            name="聚福缘菜馆",
            type=POIType.RESTAURANT,
            city="天津",
            latitude=39.13,
            longitude=117.2,
            duration_minutes=75,
            day=1,
            start_time=time(12, 30),
            end_time=time(13, 45),
            is_fixed=False,
            placement_reason="Amap categorizes this as a fuller meal stop.",
            source_type=ScheduledPOISourceType.USER_SEED,
            source_label="User seed",
            source_reason="This stop came from the user-provided trip seeds.",
            travel_from_name="天津之眼",
            travel_distance_m=2400,
            travel_duration_s=1800,
        )
        block = DayTimeBlock(
            block_type=TimeBlockType.AFTERNOON,
            start_time=time(13, 0),
            end_time=time(17, 0),
            items=[item],
        )
        day = DayItinerary(
            day=1,
            hotel=HotelStay(
                name="天津站 / 意风区一带",
                city="天津",
                latitude=39.13,
                longitude=117.2,
            ),
            availability_summary=DayAvailabilitySummary(
                was_trimmed=False,
                effective_start=None,
                effective_end=None,
                remaining_blocks=[],
            ),
            blocks=[block],
        )

        summary = build_poi_research_summary(day, block, item)

        self.assertIn("天津之眼", summary.access_tip)
        self.assertIn("30 分钟", summary.access_tip)
        self.assertIn("餐食", summary.practical_tip)
        self.assertIn("第 1 天", summary.best_for)
        self.assertEqual(summary.source, "route_context")


if __name__ == "__main__":
    unittest.main()
