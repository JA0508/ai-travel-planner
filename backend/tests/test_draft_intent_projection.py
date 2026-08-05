from __future__ import annotations

import unittest
from datetime import datetime

from app.services.draft_intent_projection import DraftIntentProjectionError, project_confirmed_draft_intent
from app.trips.intent_contracts import (
    CompileTripIntentRequest,
    IntentProposalParseResult,
    IntentFixedEventValue,
    IntentStructuredOverrides,
    PlaceIdentity,
    PlaceResolutionOption,
    compile_source_linked_intent,
)


class DraftIntentProjectionTests(unittest.TestCase):
    def test_unconfirmed_required_place_never_projects_to_planning_run_input(self) -> None:
        envelope = self._envelope(
            PlaceIdentity(
                stable_id="place_west_lake", original_name="西湖", city="杭州", ownership="must",
                resolution_status="ambiguous", source_fragment_ids=["direct"],
                confirmation_options=[PlaceResolutionOption(provider_place_id="amap-west-lake", canonical_name="西湖风景名胜区")],
            )
        )
        self.assertEqual(envelope.planner_ready_status.value, "needs_clarification")
        with self.assertRaises(DraftIntentProjectionError) as raised:
            project_confirmed_draft_intent(envelope)
        self.assertEqual(raised.exception.code, "draft_intent_not_planner_ready")

    def test_verified_provider_identity_is_the_only_place_projected(self) -> None:
        envelope = self._envelope(
            PlaceIdentity(
                stable_id="place_west_lake", original_name="西湖", canonical_name="西湖风景名胜区", city="杭州",
                ownership="must", resolution_status="verified", provider="amap", provider_place_id="amap-west-lake",
                latitude=30.235, longitude=120.148, source_fragment_ids=["direct"], resolution_confidence=1.0,
            )
        )
        projected = project_confirmed_draft_intent(envelope)
        self.assertEqual(projected.destination, "杭州")
        self.assertEqual(projected.trip_days, 2)
        self.assertEqual([item.name for item in projected.must_visit_places], ["西湖风景名胜区"])

    def test_four_day_draft_is_not_silently_sent_to_three_day_compiler(self) -> None:
        envelope = self._envelope(
            PlaceIdentity(
                stable_id="place_west_lake", original_name="西湖", canonical_name="西湖风景名胜区", city="杭州",
                ownership="must", resolution_status="verified", provider="amap", provider_place_id="amap-west-lake",
                latitude=30.235, longitude=120.148, source_fragment_ids=["direct"], resolution_confidence=1.0,
            ),
            trip_days=4,
        )
        with self.assertRaises(DraftIntentProjectionError) as raised:
            project_confirmed_draft_intent(envelope)
        self.assertEqual(raised.exception.code, "draft_intent_trip_days_unsupported")

    def test_confirmed_draft_fixed_event_is_projected_without_reinterpreting_its_window(self) -> None:
        envelope = self._envelope(
            PlaceIdentity(
                stable_id="place_west_lake", original_name="西湖", canonical_name="西湖风景名胜区", city="杭州",
                ownership="must", resolution_status="verified", provider="amap", provider_place_id="amap-west-lake",
                latitude=30.235, longitude=120.148, source_fragment_ids=["direct"], resolution_confidence=1.0,
            ),
            fixed_events=[IntentFixedEventValue(
                name="博物馆预约", event_id="fixed_museum", fixed_day=2,
                start_at=datetime(2026, 10, 2, 14, 0), end_at=datetime(2026, 10, 2, 16, 0),
                timezone="Asia/Shanghai",
            )],
        )
        projected = project_confirmed_draft_intent(envelope)
        self.assertEqual([(item.name, item.day, item.start_time, item.end_time) for item in projected.fixed_events], [
            ("博物馆预约", 2, "14:00", "16:00"),
        ])

    def _envelope(self, identity: PlaceIdentity, *, trip_days: int = 2, fixed_events: list[IntentFixedEventValue] | None = None):
        return compile_source_linked_intent(
            trip_id="trip_projection",
            base_revision_id=None,
            parent_intent_revision_id=None,
            next_revision_number=1,
            created_at="2026-08-04T00:00:00Z",
            request=CompileTripIntentRequest(
                base_intent_revision_id=None,
                structured_overrides=IntentStructuredOverrides(
                    city="杭州", trip_days=trip_days, pace="relaxed", fixed_events=fixed_events or [],
                ),
            ),
            parser_result=IntentProposalParseResult(
                status="success", proposal=None, parser_name="test", parser_version="test",
            ),
            existing_trip_snapshot={},
            candidates=[],
            candidate_workflow_states={},
            candidate_preferences={},
            place_identities=[identity],
        )
