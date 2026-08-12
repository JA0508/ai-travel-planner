from __future__ import annotations

import unittest

from app.planner.trace import ProviderSnapshotSummary
from app.schemas import ItineraryResponse, PlannerRealismIssue, PlannerRealismSummary, PlanningAnchorSource
from app.services.execution_trust import build_execution_trust_summary


class ExecutionTrustTests(unittest.TestCase):
    def test_missing_provider_data_and_execution_conflicts_remain_explicit(self) -> None:
        itinerary = ItineraryResponse(
            trip_days=1,
            planning_anchor_source=PlanningAnchorSource(source_type="city", source_name="上海"),
            planner_realism=PlannerRealismSummary(
                status="unstable",
                headline="路线存在执行冲突。",
                issues=[
                    PlannerRealismIssue(
                        code="departure_conflict",
                        severity="high",
                        title="离开前移动偏长",
                        detail="离开前的移动和时间边界冲突。",
                    )
                ],
            ),
        )

        summary = build_execution_trust_summary(
            itinerary=itinerary,
            provider_summary=ProviderSnapshotSummary(
                place_known_count=1,
                route_missing_count=2,
            ),
        )

        self.assertEqual(summary.status, "blocked")
        self.assertIn("离开前的移动和时间边界冲突。", summary.blocking_reasons)
        facts = {fact.key: fact for fact in summary.facts}
        self.assertEqual(facts["execution-conflicts"].status, "conflicting")
        self.assertEqual(facts["route-facts-missing"].status, "missing")
        self.assertEqual(facts["route-facts-missing"].verification_status, "unavailable")
        self.assertEqual(facts["place-facts"].verification_status, "provider_returned")
        self.assertEqual(facts["place-facts"].freshness_status, "unknown")


if __name__ == "__main__":
    unittest.main()
