from __future__ import annotations

import unittest

from app.services.transport_hub_service import candidate_to_hub, static_transport_hubs_for_city


class TransportHubServiceTests(unittest.TestCase):
    def test_static_transport_hubs_cover_core_city_when_provider_is_unavailable(self) -> None:
        hubs = static_transport_hubs_for_city("西安市")

        self.assertTrue(any(hub.name == "西安站" and hub.category == "rail" for hub in hubs))
        self.assertTrue(any(hub.name == "西安咸阳国际机场" for hub in hubs))

    def test_candidate_to_hub_rejects_lodging_near_rail_station(self) -> None:
        hub = candidate_to_hub(
            {
                "name": "城市北站高铁公寓",
                "type": "住宿服务;宾馆酒店;公寓式酒店",
                "latitude": 34.374,
                "longitude": 108.940,
            },
            "rail",
        )

        self.assertIsNone(hub)

    def test_candidate_to_hub_accepts_real_rail_station(self) -> None:
        hub = candidate_to_hub(
            {
                "name": "城市北站",
                "type": "交通设施服务;火车站;火车站",
                "latitude": 34.376,
                "longitude": 108.940,
            },
            "rail",
        )

        self.assertIsNotNone(hub)
        self.assertEqual(hub.name, "城市北站")
        self.assertEqual(hub.category, "rail")

    def test_candidate_to_hub_collapses_rail_sublocation_to_parent_station(self) -> None:
        hub = candidate_to_hub(
            {
                "name": "城市北站(候车室2检票口)",
                "type": "交通设施服务;火车站;火车站",
                "latitude": 34.376,
                "longitude": 108.940,
            },
            "rail",
        )

        self.assertIsNotNone(hub)
        self.assertEqual(hub.name, "城市北站")

    def test_candidate_to_hub_rejects_airport_when_searching_rail(self) -> None:
        hub = candidate_to_hub(
            {
                "name": "城市航天基地通用机场",
                "type": "交通设施服务;机场相关;航站楼",
                "latitude": 34.446,
                "longitude": 108.751,
            },
            "rail",
        )

        self.assertIsNone(hub)

    def test_candidate_to_hub_rejects_airport_hotel(self) -> None:
        hub = candidate_to_hub(
            {
                "name": "城市机场酒店",
                "type": "住宿服务;宾馆酒店;宾馆酒店",
                "latitude": 34.446,
                "longitude": 108.751,
            },
            "airport",
        )

        self.assertIsNone(hub)

    def test_candidate_to_hub_collapses_airport_terminal_to_parent_airport(self) -> None:
        hub = candidate_to_hub(
            {
                "name": "城市国际机场T3航站楼",
                "type": "交通设施服务;机场相关;航站楼",
                "latitude": 34.446,
                "longitude": 108.751,
            },
            "airport",
        )

        self.assertIsNotNone(hub)
        self.assertEqual(hub.name, "城市国际机场")


if __name__ == "__main__":
    unittest.main()
