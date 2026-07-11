from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.runtime_config import (
    DEFAULT_AMAP_REQUEST_TIMEOUT_SECONDS,
    get_amap_request_timeout_seconds,
    get_runtime_configuration_summary,
    parse_cors_allow_origins,
)
from app.api.routes.itinerary import build_apply_completion_idempotency_key
from app.api.routes.itinerary import (
    get_apply_completion_idempotency_response,
    remember_apply_completion_idempotency_response,
)
from app.schemas import (
    CompletionTaskActionRequest,
    CompletionTaskActionResponse,
    ItineraryResponse,
    PlanningAnchorSource,
)


class RuntimeConfigurationTests(unittest.TestCase):
    def test_parse_cors_allow_origins_defaults_to_wildcard(self) -> None:
        self.assertEqual(parse_cors_allow_origins(None), ["*"])
        self.assertEqual(parse_cors_allow_origins(""), ["*"])
        self.assertEqual(parse_cors_allow_origins("   "), ["*"])

    def test_parse_cors_allow_origins_splits_and_trims_values(self) -> None:
        self.assertEqual(
            parse_cors_allow_origins("http://localhost:3000, https://travel.example.com "),
            ["http://localhost:3000", "https://travel.example.com"],
        )

    def test_amap_timeout_uses_positive_env_value(self) -> None:
        with patch.dict("os.environ", {"AMAP_REQUEST_TIMEOUT_SECONDS": "3.5"}, clear=True):
            self.assertEqual(get_amap_request_timeout_seconds(), 3.5)

    def test_amap_timeout_falls_back_for_invalid_values(self) -> None:
        for raw_value in ("", "0", "-1", "not-a-number"):
            with self.subTest(raw_value=raw_value):
                with patch.dict("os.environ", {"AMAP_REQUEST_TIMEOUT_SECONDS": raw_value}, clear=True):
                    self.assertEqual(
                        get_amap_request_timeout_seconds(),
                        DEFAULT_AMAP_REQUEST_TIMEOUT_SECONDS,
                    )

    def test_runtime_summary_exposes_presence_not_secret_values(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "APP_ENV": "production",
                "AMAP_API_KEY": "real-amap-secret",
                "OPENAI_API_KEY": "real-openai-secret",
                "OPENAI_INTENT_MODEL": "intent-model",
            },
            clear=True,
        ):
            summary = get_runtime_configuration_summary()

        self.assertEqual(summary["app_env"], "production")
        self.assertTrue(summary["amap"]["api_key_configured"])
        self.assertTrue(summary["openai"]["api_key_configured"])
        self.assertEqual(summary["openai"]["intent_model"], "intent-model")
        self.assertNotIn("real-amap-secret", str(summary))
        self.assertNotIn("real-openai-secret", str(summary))

    def test_completion_task_idempotency_key_is_payload_scoped(self) -> None:
        itinerary = ItineraryResponse(
            trip_days=1,
            planning_anchor_source=PlanningAnchorSource(source_type="city", source_name="上海"),
            days=[],
        )
        payload = CompletionTaskActionRequest(
            itinerary=itinerary,
            task_id="repair_sparse_block",
        )
        same_payload = CompletionTaskActionRequest(
            itinerary=itinerary,
            task_id="repair_sparse_block",
        )
        changed_payload = CompletionTaskActionRequest(
            itinerary=itinerary,
            task_id="repair_evening_close",
        )

        first_key = build_apply_completion_idempotency_key("same-click", payload)

        self.assertIsNotNone(first_key)
        self.assertEqual(
            first_key,
            build_apply_completion_idempotency_key("same-click", same_payload),
        )
        self.assertNotEqual(
            first_key,
            build_apply_completion_idempotency_key("same-click", changed_payload),
        )
        self.assertIsNone(build_apply_completion_idempotency_key("   ", payload))

    def test_completion_task_idempotency_cache_returns_deep_copies(self) -> None:
        itinerary = ItineraryResponse(
            trip_days=1,
            planning_anchor_source=PlanningAnchorSource(source_type="city", source_name="上海"),
            days=[],
        )
        response = CompletionTaskActionResponse(
            task_id="repair_sparse_block",
            applied=True,
            summary="inserted",
            itinerary=itinerary,
        )

        remember_apply_completion_idempotency_response("cache-key", response)
        cached_response = get_apply_completion_idempotency_response("cache-key")

        self.assertIsNotNone(cached_response)
        self.assertIsNot(cached_response, response)
        self.assertIsNot(cached_response.itinerary, response.itinerary)


if __name__ == "__main__":
    unittest.main()
