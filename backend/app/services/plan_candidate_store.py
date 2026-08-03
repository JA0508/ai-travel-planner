from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.schemas.plan_candidates import PlanCandidate


class CandidateProposalError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class StoredCandidate:
    candidate: PlanCandidate
    intent_digest: str
    intent: object
    itinerary_request: object
    expires_at: datetime
    selected_result: object | None = None
    idempotency_key: str | None = None


class PlanCandidateStore:
    def __init__(self, *, ttl_seconds: int = 600, clock=None) -> None:
        self.ttl_seconds = ttl_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._records: dict[str, StoredCandidate] = {}

    def put(self, *, candidate: PlanCandidate, intent_digest: str, intent: object, itinerary_request: object) -> None:
        self._records[candidate.id] = StoredCandidate(candidate, intent_digest, intent, itinerary_request, self.clock() + timedelta(seconds=self.ttl_seconds))

    def select(self, *, candidate_id: str, candidate_hash: str, intent_digest: str, idempotency_key: str):
        record = self._records.get(candidate_id)
        if record is None or self.clock() >= record.expires_at:
            raise CandidateProposalError("candidate_stale", "这份路线候选已过期，请重新生成后再保存。")
        if record.intent_digest != intent_digest or record.candidate.candidate_hash != candidate_hash:
            raise CandidateProposalError("candidate_mismatch", "这份路线候选与当前确认信息不一致，请重新生成。")
        if record.idempotency_key is not None:
            if record.idempotency_key != idempotency_key:
                raise CandidateProposalError("candidate_already_selected", "这份路线已经保存过。")
            return record, True
        record.idempotency_key = idempotency_key
        return record, False


_store = PlanCandidateStore()


def get_plan_candidate_store() -> PlanCandidateStore:
    return _store


def reset_plan_candidate_store_for_tests() -> None:
    global _store
    _store = PlanCandidateStore()
