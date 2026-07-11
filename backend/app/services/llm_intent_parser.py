from __future__ import annotations

import json
import os

import requests

from app.core.runtime_config import (
    get_openai_disambiguation_timeout_seconds,
    get_openai_intent_model,
    get_openai_intent_timeout_seconds,
)
from app.schemas.intent import ParsedTripIntentResponse


OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"


class IntentParsingError(Exception):
    """Raised when the LLM intent parser cannot return a valid structured intent."""


def parse_trip_text_with_llm(text: str) -> ParsedTripIntentResponse:
    """
    Main NL parsing path for itinerary intent extraction.

    This is intentionally parse-only:
    - the LLM extracts structured planning intent
    - the deterministic scheduler remains responsible for final itinerary generation
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise IntentParsingError("OPENAI_API_KEY is not configured.")

    model = get_openai_intent_model()
    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "parsed_trip_intent",
            "strict": True,
            "schema": intent_json_schema(),
        },
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You extract travel planning intent from user text. "
                    "Return JSON only. Do not generate an itinerary. "
                    "Do not make final scheduling decisions. "
                    "Extract city, trip_days, hotel, arrival_anchor, departure_anchor, availability_windows, "
                    "scenic_spots, restaurants, fixed_events, preferences, style_preferences, and style_preference_sources as explicitly as possible. "
                    "Use preferences for explicit user desires such as pace, food style, "
                    "walking tolerance, atmosphere, must-do priorities, or trip style. "
                    "Use style_preferences only when the user clearly expresses or strongly implies a trip style such as museum-oriented, "
                    "old-street / wandering, cafe-break / food-stop, night-view / waterfront / evening stroll, "
                    "or landmark-oriented. Otherwise return an empty array. "
                    "Use style_preference_sources to mark each style bucket as explicit when the user directly asks for that style, "
                    "or inferred when the style is reasonably implied by the request or POI mix but not directly stated. "
                    "Keep inferred signals conservative. style_preferences should match the keys present in style_preference_sources. "
                    "Use arrival_anchor for where the trip begins if the user mentions an airport, station, "
                    "or other clear arrival point. Use departure_anchor for where the trip ends if the user "
                    "mentions a departure airport, station, or other clear final anchor. "
                    "Use availability_windows for partial trip availability such as late first day, early last day, "
                    "evening-only availability, or phrasing like Saturday afternoon to Sunday evening. "
                    "For each availability window, fill day if explicitly inferable, otherwise leave it null and "
                    "use label to preserve the user's framing like first day, last day, Saturday afternoon, or Sunday evening. "
                    "Use fixed_events only for items that clearly have a fixed day, fixed time, "
                    "ticketed slot, reservation, or non-flexible commitment. "
                    "If a place is clearly represented as a fixed_event, avoid also listing it "
                    "as a normal scenic_spot or restaurant unless the text strongly implies both. "
                    "Set fixed_events[].category to a simple label like scenic, restaurant, "
                    "transport, activity, or other when reasonably inferable."
                ),
            },
            {
                "role": "user",
                "content": text,
            },
        ],
        "response_format": response_format,
    }

    try:
        response = requests.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=get_openai_intent_timeout_seconds(),
        )
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise IntentParsingError("Failed to call LLM intent parser.") from exc

    try:
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        return ParsedTripIntentResponse.model_validate(parsed)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
        raise IntentParsingError("LLM intent parser returned invalid structured output.") from exc


def select_place_candidate_with_llm(
    *,
    raw_text: str | None,
    city: str | None,
    poi_name: str,
    poi_type: str,
    candidates: list[dict],
) -> str | None:
    """
    Pick one POI candidate from deterministic Amap candidates.

    The LLM is only allowed to choose among provided candidates. It cannot invent a
    place or make scheduling decisions.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise IntentParsingError("OPENAI_API_KEY is not configured.")

    model = get_openai_intent_model()
    candidate_payload = [
        {
            "name": candidate.get("name"),
            "address": candidate.get("address"),
            "type": candidate.get("type"),
            "business_area": candidate.get("business_area"),
        }
        for candidate in candidates[:6]
    ]
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You disambiguate a travel POI by selecting exactly one provided candidate. "
                    "Do not invent new places. Return JSON only. "
                    "If none clearly matches the user's intended place, return null."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "raw_text": raw_text,
                        "city": city,
                        "poi_name": poi_name,
                        "poi_type": poi_type,
                        "candidates": candidate_payload,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "place_disambiguation_choice",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "selected_name": {"type": ["string", "null"]},
                        "reason": {"type": "string"},
                    },
                    "required": ["selected_name", "reason"],
                },
            },
        },
    }

    try:
        response = requests.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=get_openai_disambiguation_timeout_seconds(),
        )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (
        requests.RequestException,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise IntentParsingError("LLM place disambiguation failed.") from exc

    selected_name = parsed.get("selected_name")
    if selected_name is None:
        return None
    if not isinstance(selected_name, str):
        return None
    candidate_names = {str(candidate.get("name") or "") for candidate in candidate_payload}
    return selected_name if selected_name in candidate_names else None


def intent_json_schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "city": {"type": ["string", "null"]},
            "trip_days": {"type": ["integer", "null"]},
            "hotel": {"type": ["string", "null"]},
            "arrival_anchor": {"type": ["string", "null"]},
            "departure_anchor": {"type": ["string", "null"]},
            "availability_windows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "day": {"type": ["integer", "null"]},
                        "label": {"type": ["string", "null"]},
                        "available_start": {"type": ["string", "null"]},
                        "available_end": {"type": ["string", "null"]},
                    },
                    "required": [
                        "day",
                        "label",
                        "available_start",
                        "available_end",
                    ],
                },
            },
            "scenic_spots": {
                "type": "array",
                "items": {"type": "string"},
            },
            "restaurants": {
                "type": "array",
                "items": {"type": "string"},
            },
            "fixed_events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "fixed_day": {"type": ["integer", "null"]},
                        "fixed_time_start": {"type": ["string", "null"]},
                        "fixed_time_end": {"type": ["string", "null"]},
                        "category": {
                            "type": ["string", "null"],
                            "enum": ["scenic", "restaurant", "transport", "activity", "other", None],
                        },
                    },
                    "required": [
                        "name",
                        "fixed_day",
                        "fixed_time_start",
                        "fixed_time_end",
                        "category",
                    ],
                },
            },
            "preferences": {
                "type": "array",
                "items": {"type": "string"},
            },
            "style_preferences": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["museum", "old_street", "landmark", "food_stop", "night_view"],
                },
            },
            "style_preference_sources": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "museum": {"type": ["string", "null"], "enum": ["explicit", "inferred", None]},
                    "old_street": {"type": ["string", "null"], "enum": ["explicit", "inferred", None]},
                    "landmark": {"type": ["string", "null"], "enum": ["explicit", "inferred", None]},
                    "food_stop": {"type": ["string", "null"], "enum": ["explicit", "inferred", None]},
                    "night_view": {"type": ["string", "null"], "enum": ["explicit", "inferred", None]},
                },
            },
        },
        "required": [
            "city",
            "trip_days",
            "hotel",
            "arrival_anchor",
            "departure_anchor",
            "availability_windows",
            "scenic_spots",
            "restaurants",
            "fixed_events",
            "preferences",
            "style_preferences",
            "style_preference_sources",
        ],
    }
