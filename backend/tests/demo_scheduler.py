from __future__ import annotations

from pprint import pprint

from app.core.scheduler import Scheduler
from app.schemas import HotelStay, NormalizedPOI, POIType


def main() -> None:
    scheduler = Scheduler()

    scenic_spots = [
        NormalizedPOI(
            name="The Bund",
            type=POIType.SCENIC,
            latitude=31.2400,
            longitude=121.4900,
            duration_minutes=120,
            fixed_day=1,
            fixed_time_start="14:00:00",
            fixed_time_end="16:00:00",
        ),
        NormalizedPOI(
            name="Yu Garden",
            type=POIType.SCENIC,
            latitude=31.2272,
            longitude=121.4925,
            duration_minutes=90,
        ),
    ]
    restaurants = [
        NormalizedPOI(
            name="Jia Jia Tang Bao",
            type=POIType.RESTAURANT,
            latitude=31.2309,
            longitude=121.4707,
            duration_minutes=60,
        ),
        NormalizedPOI(
            name="Lost Heaven",
            type=POIType.RESTAURANT,
            latitude=31.2206,
            longitude=121.4750,
            duration_minutes=90,
        ),
    ]
    hotel = HotelStay(
        name="Central Hotel Shanghai",
        latitude=31.2332,
        longitude=121.4753,
    )

    itinerary = scheduler.build_schedule(
        scenic_spots=scenic_spots,
        restaurants=restaurants,
        hotel=hotel,
        trip_days=1,
    )
    pprint(itinerary.model_dump(mode="json"))


if __name__ == "__main__":
    main()
