from __future__ import annotations

from app.services.llm_intent_parser import IntentParsingError, parse_trip_text_with_llm
from .intent_contracts import UntrustedIntentProposal


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
        fixed_events=[event.model_dump(mode="json") for event in parsed.fixed_events],
        explanation="Production LLM intent adapter proposal; deterministic compiler remains authoritative.",
    )
