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
            extra_identities=[PlaceIdentity(
                stable_id="fixed_museum", original_name="中国茶叶博物馆", canonical_name="中国茶叶博物馆（双峰馆区）", city="杭州",
                ownership="fixed", fixed_event_id="fixed_museum", resolution_status="verified", provider="amap", provider_place_id="amap-tea-museum",
                latitude=30.218, longitude=120.104, source_fragment_ids=["direct"], resolution_confidence=1.0,
            )],
        )
        projected = project_confirmed_draft_intent(envelope)
        self.assertEqual([(item.name, item.day, item.start_time, item.end_time) for item in projected.fixed_events], [
            ("中国茶叶博物馆（双峰馆区）", 2, "14:00", "16:00"),
        ])
        self.assertEqual(projected.fixed_events[0].verified_place.provider_place_id, "amap-tea-museum")

    def test_fixed_event_without_verified_identity_never_projects(self) -> None:
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
        with self.assertRaises(DraftIntentProjectionError) as raised:
            project_confirmed_draft_intent(envelope)
        self.assertEqual(raised.exception.code, "draft_intent_fixed_event_identity_unconfirmed")

    def test_direct_language_fixed_event_links_to_its_single_discovered_identity(self) -> None:
        fixed_identity = PlaceIdentity(
            stable_id="fixed_tea_museum",
            fixed_event_id="fixed_tea_museum",
            original_name="中国茶叶博物馆",
            canonical_name="中国茶叶博物馆（双峰馆区）",
            city="杭州",
            ownership="fixed",
            resolution_status="verified",
            provider="amap",
            provider_place_id="amap-tea-museum",
            latitude=30.218,
            longitude=120.104,
            source_fragment_ids=["direct"],
            resolution_confidence=1.0,
        )
        envelope = compile_source_linked_intent(
            trip_id="trip_projection",
            base_revision_id=None,
            parent_intent_revision_id=None,
            next_revision_number=1,
            created_at="2026-08-04T00:00:00Z",
            request=CompileTripIntentRequest(
                base_intent_revision_id=None,
                direct_user_text="去杭州玩两天，第二天下午两点到四点预约了中国茶叶博物馆。",
            ),
            parser_result=IntentProposalParseResult(
                status="success", proposal=None, parser_name="test", parser_version="test",
            ),
            existing_trip_snapshot={},
            candidates=[],
            candidate_workflow_states={},
            candidate_preferences={},
            place_identities=[fixed_identity],
        )

        event = envelope.formal_contract.fixed_events[0]
        self.assertEqual(event.event_id, "fixed_tea_museum")
        self.assertEqual(
            (event.fixed_day, event.fixed_time_start, event.fixed_time_end),
            (2, "14:00", "16:00"),
        )
        projected = project_confirmed_draft_intent(envelope)
        self.assertEqual(projected.fixed_events[0].verified_place.provider_place_id, "amap-tea-museum")
        self.assertEqual(
            (projected.fixed_events[0].start_time, projected.fixed_events[0].end_time),
            ("14:00", "16:00"),
        )

    def _envelope(self, identity: PlaceIdentity, *, trip_days: int = 2, fixed_events: list[IntentFixedEventValue] | None = None, extra_identities: list[PlaceIdentity] | None = None):
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
            place_identities=[identity, *(extra_identities or [])],
        )
