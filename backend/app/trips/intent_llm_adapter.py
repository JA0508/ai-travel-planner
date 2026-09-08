from __future__ import annotations

from app.services.llm_intent_parser import IntentParsingError, parse_trip_text_with_llm
from app.services.nl_parser import parse_trip_text_fallback
from app.schemas.intent import ParsedFixedEvent
from .intent_contracts import UntrustedIntentProposal


_GENERIC_FIXED_EVENT_NAMES = frozenset({"预约", "有安排", "安排", "固定安排", "固定行程"})


def build_untrusted_llm_intent_proposal(text: str) -> UntrustedIntentProposal | None:
    """Adapt production LLM parsing into an untrusted proposal for deterministic compilation."""
    if not text.strip():
        return None
    try:
        parsed = parse_trip_text_with_llm(text)
    except IntentParsingError:
        return None
    return UntrustedIntentProposal(
        city=parsed.city,
        trip_days=parsed.trip_days,
        pace="relaxed" if "不要太赶" in text or "轻松" in text else None,
        transport_preferences=[],
        fixed_events=_contract_safe_fixed_events(text, parsed.fixed_events),
        explanation="Production LLM intent adapter proposal; deterministic compiler remains authoritative.",
    )


def _contract_safe_fixed_events(text: str, events: list[ParsedFixedEvent]) -> list[dict[str, object]]:
    """Keep generic LLM events only when deterministic parsing finds the same commitment.

    Labels such as ``预约`` and ``有安排`` are meaningful only when the user actually
    supplied a fixed commitment.  Without source support, they are commonly caused
    by output instructions (for example, "if a place needs a reservation") or a
    requested rest period.  The adapter also maps the parser schema to the typed
    intent contract rather than passing parser-only fields such as ``category``.
    """

    source_supported_generic_names = {
        event.name.strip()
        for event in parse_trip_text_fallback(text).fixed_events
        if event.name.strip() in _GENERIC_FIXED_EVENT_NAMES
    }
    contract_events: list[dict[str, object]] = []
    for event in events:
        name = event.name.strip()
        if not name:
            continue
        if name in _GENERIC_FIXED_EVENT_NAMES and name not in source_supported_generic_names:
            continue
        contract_events.append(
            {
                "type": "fixed_event",
                "name": name,
                "fixed_day": event.fixed_day,
                "fixed_time_start": event.fixed_time_start,
                "fixed_time_end": event.fixed_time_end,
            }
        )
    return contract_events
