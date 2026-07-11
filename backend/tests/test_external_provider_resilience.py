from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.services.amap_client import GEOCODE_CACHE, GeocodingError, geocode_place
from app.services.llm_intent_parser import (
    IntentParsingError,
    parse_trip_text_with_llm,
    select_place_candidate_with_llm,
)


class ExternalProviderResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._geocode_cache_snapshot = dict(GEOCODE_CACHE)
        GEOCODE_CACHE.clear()

    def tearDown(self) -> None:
        GEOCODE_CACHE.clear()
        GEOCODE_CACHE.update(self._geocode_cache_snapshot)

    def test_geocode_place_wraps_invalid_json_response(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError("invalid json")

        with patch.dict("os.environ", {"AMAP_API_KEY": "fake-key"}, clear=True):
            with patch("app.services.amap_client.requests.get", return_value=response):
                with self.assertRaises(GeocodingError) as context:
                    geocode_place("不会命中缓存的地点", city="上海")

        self.assertIn("Failed to call Amap geocoding", str(context.exception))

    def test_llm_intent_parser_wraps_invalid_json_response(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError("invalid json")

        with patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}, clear=True):
            with patch("app.services.llm_intent_parser.requests.post", return_value=response):
                with self.assertRaises(IntentParsingError) as context:
                    parse_trip_text_with_llm("上海两天，想轻松一点")

        self.assertIn("Failed to call LLM intent parser", str(context.exception))

    def test_llm_disambiguation_wraps_invalid_json_response(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError("invalid json")

        with patch.dict("os.environ", {"OPENAI_API_KEY": "fake-key"}, clear=True):
            with patch("app.services.llm_intent_parser.requests.post", return_value=response):
                with self.assertRaises(IntentParsingError) as context:
                    select_place_candidate_with_llm(
                        raw_text="想去上海博物馆",
                        city="上海",
                        poi_name="上海博物馆",
                        poi_type="scenic",
                        candidates=[{"name": "上海博物馆", "address": "人民广场"}],
                    )

        self.assertIn("LLM place disambiguation failed", str(context.exception))


if __name__ == "__main__":
    unittest.main()
