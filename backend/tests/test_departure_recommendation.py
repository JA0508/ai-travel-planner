from __future__ import annotations

import unittest
from datetime import time
from unittest.mock import patch

from app.schemas import (
    DayItinerary,
    DayTimeBlock,
    HotelStay,
    ItineraryResponse,
    PlanningAnchorSource,
    POIType,
    ScheduledPOI,
    TimeBlockType,
    TravelMode,
)
from app.services.departure_recommendation import build_departure_recommendation
from app.services.transport_hub_service import TransportHub


class DepartureRecommendationTests(unittest.TestCase):
    @patch("app.services.departure_recommendation.find_transport_hubs")
    def test_airplane_preference_recommends_nearest_airport(self, mock_find_hubs) -> None:
        mock_find_hubs.return_value = [
            TransportHub("近机场", "airport", 31.21, 121.49),
            TransportHub("远机场", "airport", 31.80, 121.10),
            TransportHub("近火车站", "rail", 31.205, 121.485),
        ]

        recommendation = build_departure_recommendation(
            itinerary=self.itinerary(),
            departure_anchor_was_provided=False,
            preferred_mode=TravelMode.AIRPLANE,
        )

        self.assertIsNotNone(recommendation)
        self.assertEqual(len(recommendation.options), 1)
        option = recommendation.options[0]
        self.assertEqual(option.suggested_departure_label, "近机场")
        self.assertIn("飞机", option.fit_label)
        self.assertIn("估算直线距离", option.reasoning_summary)
        self.assertIsNotNone(option.decision_trace)
        self.assertEqual(option.decision_trace.selected_hub_name, "近机场")
        self.assertEqual(option.decision_trace.top_candidates[0].name, "近机场")
        self.assertEqual(option.decision_trace.top_candidates[0].status, "selected")
        self.assertGreaterEqual(len(option.decision_trace.rejected_candidates), 1)
        self.assertEqual(option.decision_trace.rejected_candidates[0].status, "rejected")
        self.assertIsNotNone(option.decision_trace.rejected_candidates[0].distance_km)

    @patch("app.services.departure_recommendation.find_transport_hubs")
    def test_rail_preference_recommends_nearest_station(self, mock_find_hubs) -> None:
        mock_find_hubs.return_value = [
            TransportHub("近机场", "airport", 31.205, 121.485),
            TransportHub("远火车站", "rail", 31.80, 121.10),
            TransportHub("近火车站", "rail", 31.21, 121.49),
        ]

        recommendation = build_departure_recommendation(
            itinerary=self.itinerary(),
            departure_anchor_was_provided=False,
            preferred_mode=TravelMode.HIGH_SPEED_RAIL,
        )

        self.assertIsNotNone(recommendation)
        self.assertEqual(len(recommendation.options), 1)
        option = recommendation.options[0]
        self.assertEqual(option.suggested_departure_label, "近火车站")
        self.assertIn("高铁", option.fit_label)
        self.assertIsNotNone(option.decision_trace)
        self.assertEqual(option.decision_trace.preferred_mode, TravelMode.HIGH_SPEED_RAIL)
        self.assertEqual(option.decision_trace.top_candidates[0].category, "rail")
        self.assertTrue(
            all(candidate.category == "rail" for candidate in option.decision_trace.top_candidates)
        )

    @patch("app.services.departure_recommendation.find_transport_hubs")
    def test_user_provided_departure_anchor_suppresses_recommendation(self, mock_find_hubs) -> None:
        recommendation = build_departure_recommendation(
            itinerary=self.itinerary(),
            departure_anchor_was_provided=True,
            preferred_mode=TravelMode.AIRPLANE,
        )

        self.assertIsNone(recommendation)
        mock_find_hubs.assert_not_called()

    def itinerary(self) -> ItineraryResponse:
        hotel = HotelStay(
            name="人民广场酒店",
            city="上海",
            latitude=31.2304,
            longitude=121.4737,
        )
        return ItineraryResponse(
            trip_days=2,
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            days=[
                DayItinerary(
                    day=1,
                    hotel=hotel,
                    blocks=[
                        self.block(
                            day=1,
                            item=self.poi("上海博物馆", 31.2304, 121.4737, day=1),
                        )
                    ],
                ),
                DayItinerary(
                    day=2,
                    hotel=hotel,
                    blocks=[
                        self.block(
                            day=2,
                            item=self.poi("武康路", 31.205, 121.485, day=2),
                        )
                    ],
                ),
            ],
        )

    def block(self, *, day: int, item: ScheduledPOI) -> DayTimeBlock:
        return DayTimeBlock(
            block_type=TimeBlockType.AFTERNOON,
            start_time=time(14, 0),
            end_time=time(17, 30),
            items=[item],
        )

    def poi(self, name: str, lat: float, lng: float, *, day: int) -> ScheduledPOI:
        return ScheduledPOI(
            name=name,
            type=POIType.SCENIC,
            city="上海",
            latitude=lat,
            longitude=lng,
            duration_minutes=90,
            day=day,
            start_time=time(14, 30),
            end_time=time(16, 0),
            is_fixed=False,
        )


if __name__ == "__main__":
    unittest.main()
