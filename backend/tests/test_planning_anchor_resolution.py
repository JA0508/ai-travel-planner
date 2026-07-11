import unittest

from app.api.routes.itinerary import resolve_planning_anchor
from app.schemas import NormalizedPOI, POIType
from app.services.mock_normalizer import infer_poi_profile


def make_scenic(name: str, latitude: float, longitude: float) -> NormalizedPOI:
    profile = infer_poi_profile(name, POIType.SCENIC)
    return NormalizedPOI(
        name=name,
        type=POIType.SCENIC,
        city="西安",
        latitude=latitude,
        longitude=longitude,
        duration_minutes=profile.typical_duration_minutes,
        profile=profile,
    )


class PlanningAnchorResolutionTests(unittest.TestCase):
    def test_sparse_trip_uses_route_center_instead_of_first_remote_poi(self):
        remote_first = make_scenic("秦始皇兵马俑博物馆", 34.386214, 109.28196)
        museum = make_scenic("陕西历史博物馆", 34.224199, 108.955044)
        pagoda = make_scenic("大雁塔", 34.218229, 108.964176)
        wall = make_scenic("西安城墙", 34.2759, 108.948183)

        anchor, source = resolve_planning_anchor(
            provided_hotel=None,
            scenic_spots=[remote_first, museum, pagoda, wall],
            restaurants=[],
            arrival_anchor=None,
            departure_anchor=None,
            city="西安",
        )

        self.assertNotEqual(anchor.name, "秦始皇兵马俑博物馆")
        self.assertEqual(source.source_type, "route_soft_anchor")
        self.assertIn("路线中心", source.source_name)
        self.assertLess(abs(anchor.longitude - 108.96), 0.05)


if __name__ == "__main__":
    unittest.main()
