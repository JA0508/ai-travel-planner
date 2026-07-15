from __future__ import annotations

import unittest
from datetime import time
from unittest.mock import patch

from pydantic import ValidationError

from app.core.scheduler import Scheduler
from app.planner.trace import (
    PlannerDecision,
    PlannerDecisionEvent,
    PlannerDecisionStage,
    PlannerInputSnapshot,
    PlannerReasonCode,
    PlannerResultSummary,
    PlannerSubjectType,
    PlannerTraceCollector,
    planner_trace_digest,
    stable_subject_id,
)
from app.schemas import (
    HotelStay,
    NormalizedPOI,
    POIProfile,
    POIType,
    POIVisitStyle,
    PlanningAnchorSource,
    TimeBlockType,
)
from app.services.amap_direction import RoutePlanningError


class PlannerTraceTests(unittest.TestCase):
    def make_collector(self) -> PlannerTraceCollector:
        return PlannerTraceCollector(
            planner_run_id="run-test",
            input_summary=PlannerInputSnapshot(city="上海", scenic_seed_count=1),
            strict=True,
            volatile_metadata={"request_id": "request-a", "duration_ms": 12},
        )

    def test_schema_requires_known_reason_code(self) -> None:
        with self.assertRaises(ValidationError):
            PlannerDecisionEvent(
                sequence=1,
                stage=PlannerDecisionStage.CANDIDATE_RANKING,
                subject_type=PlannerSubjectType.CANDIDATE,
                subject_id="candidate:x",
                decision=PlannerDecision.REJECTED,
                reason_codes=["free text is not a reason code"],
            )

    def test_digest_is_stable_and_excludes_volatile_metadata(self) -> None:
        collector = self.make_collector()
        collector.record_decision(
            stage=PlannerDecisionStage.CANDIDATE_RANKING,
            subject_type=PlannerSubjectType.CANDIDATE,
            subject_id=stable_subject_id("candidate", "外滩"),
            decision=PlannerDecision.ACCEPTED,
            reason_codes=[PlannerReasonCode.ACCEPTED_RANKED_CANDIDATE],
            metrics={"rank": 1},
        )
        result_summary = PlannerResultSummary(
            status="completed",
            trip_days=1,
            scheduled_item_count=1,
        )
        trace_a = collector.build_trace(result_summary)
        trace_b = collector.build_trace(result_summary)
        trace_b.volatile_metadata = {"request_id": "request-b", "duration_ms": 999}

        self.assertEqual(planner_trace_digest(trace_a), planner_trace_digest(trace_b))

        trace_b.decisions[0].reason_codes = [PlannerReasonCode.REJECTED_NO_AVAILABLE_SLOT]
        self.assertNotEqual(planner_trace_digest(trace_a), planner_trace_digest(trace_b))

    def test_collector_preserves_event_order(self) -> None:
        collector = self.make_collector()
        for name in ("a", "b", "c"):
            collector.record_decision(
                stage=PlannerDecisionStage.CANDIDATE_DISCOVERY,
                subject_type=PlannerSubjectType.CANDIDATE,
                subject_id=stable_subject_id("candidate", name),
                decision=PlannerDecision.ACCEPTED,
                reason_codes=[PlannerReasonCode.ACCEPTED_INPUT_CANDIDATE],
            )

        self.assertEqual([event.sequence for event in collector.decisions], [1, 2, 3])

    def test_disabled_collector_does_not_alter_scheduler_result(self) -> None:
        scheduler = Scheduler()
        hotel = HotelStay(name="人民广场酒店", city="上海", latitude=31.2304, longitude=121.4737)
        anchor = PlanningAnchorSource(source_type="provided_hotel", source_name=hotel.name)
        poi = NormalizedPOI(
            name="静安寺",
            type=POIType.SCENIC,
            city="上海",
            latitude=31.22346,
            longitude=121.44531,
            duration_minutes=90,
            profile=POIProfile(
                visit_style=POIVisitStyle.TEMPLE_PARK,
                best_time_blocks=[TimeBlockType.MORNING],
                typical_duration_minutes=90,
                intensity="medium",
            ),
        )
        collector = self.make_collector()
        with patch("app.core.scheduler.get_route", side_effect=RoutePlanningError("offline")):
            without_trace = scheduler.build_schedule(
                scenic_spots=[poi],
                restaurants=[],
                hotel=hotel,
                planning_anchor_source=anchor,
                trip_days=1,
            )
            with_trace = scheduler.build_schedule(
                scenic_spots=[poi],
                restaurants=[],
                hotel=hotel,
                planning_anchor_source=anchor,
                trip_days=1,
                trace_collector=collector,
            )

        self.assertEqual(
            without_trace.model_dump(mode="json"),
            with_trace.model_dump(mode="json"),
        )
        self.assertTrue(collector.decisions)


if __name__ == "__main__":
    unittest.main()
