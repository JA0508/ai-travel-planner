from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluationInvariantResult(BaseModel):
    code: str
    status: str
    evidence: dict = Field(default_factory=dict)


class EvaluationCaseResult(BaseModel):
    case_id: str
    status: str
    trace_digest: str | None = None
    repeat_trace_digest: str | None = None
    deterministic_match: bool
    invariant_results: list[EvaluationInvariantResult] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    error: str | None = None


class EvaluationReport(BaseModel):
    fixture_count: int
    passed_count: int
    failed_count: int
    deterministic_mismatch_count: int
    results: list[EvaluationCaseResult]


class HandoffEvaluationCaseResult(BaseModel):
    case_id: str
    coverage: str
    status: str
    can_apply: bool
    passed: bool
    deterministic_match: bool
    invariant_results: list[EvaluationInvariantResult] = Field(default_factory=list)


class HandoffEvaluationReport(BaseModel):
    fixture_count: int
    strict_fixture_count: int
    drift_fixture_count: int
    passed_count: int
    failed_count: int
    results: list[HandoffEvaluationCaseResult]
