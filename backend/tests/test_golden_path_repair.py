from __future__ import annotations

import unittest

from app.trips.golden_path_repair import select_relax_day_repair


class GoldenPathRepairSelectionTests(unittest.TestCase):
    def test_relax_day_prefers_a_non_meal_system_stop(self) -> None:
        snapshot = {
            "planner_realism": {
                "daily_loads": [
                    {"day": 1, "classification": "rushed", "activity_count": 5},
                    {"day": 2, "classification": "balanced", "activity_count": 2},
                ]
            },
            "days": [
                {
                    "day": 1,
                    "blocks": [
                        {
                            "block_type": "afternoon",
                            "items": [
                                {
                                    "stable_id": "aa-scenic-filler",
                                    "name": "山间散步",
                                    "source_type": "auto_seeded_poi",
                                    "is_fixed": False,
                                    "duration_minutes": 60,
                                },
                                {
                                    "stable_id": "zz-dinner",
                                    "name": "晚饭",
                                    "source_type": "auto_seeded_meal",
                                    "is_fixed": False,
                                    "duration_minutes": 60,
                                },
                            ],
                        }
                    ],
                },
                {
                    "day": 2,
                    "blocks": [
                        {
                            "block_type": "afternoon",
                            "start_time": "13:00:00",
                            "end_time": "17:00:00",
                            "items": [],
                        }
                    ],
                },
            ],
        }

        selection = select_relax_day_repair(snapshot, target_day=1)

        self.assertEqual(selection.stop_id, "aa-scenic-filler")
        self.assertEqual(selection.stop_name, "山间散步")


if __name__ == "__main__":
    unittest.main()
