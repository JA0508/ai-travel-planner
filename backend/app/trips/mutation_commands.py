from __future__ import annotations

import copy
import hashlib
from math import atan2, cos, radians, sin, sqrt
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evaluation.invariants import (
    no_duplicate_scheduled_place,
    no_schedule_overlap,
    within_arrival_departure_boundaries,
    within_day_availability,
)
from app.schemas import ItineraryResponse, TimeBlockType
from .digests import (
    TRIP_MUTATION_COMMAND_SCHEMA_VERSION,
    TRIP_MUTATION_ENGINE_VERSION,
    command_digest,
    itinerary_content_digest,
)
from .errors import (
    CandidateAdmissionRepairRequiredError,
    MutationCommandFailedError,
    MutationCommandNoEffectError,
    UnsupportedMutationCommandSchemaError,
)


MAX_MUTATION_COMMANDS = 25
MAX_ORDERED_STOP_IDS = 100
MAX_STOP_ID_LENGTH = 160


class StopPlacement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    before_stop_id: str | None = Field(default=None, max_length=MAX_STOP_ID_LENGTH)
    after_stop_id: str | None = Field(default=None, max_length=MAX_STOP_ID_LENGTH)
    at_end: bool = False

    @model_validator(mode="after")
    def validate_single_placement(self) -> "StopPlacement":
        selected = sum(
            [
                self.before_stop_id is not None,
                self.after_stop_id is not None,
                self.at_end,
            ]
        )
        if selected != 1:
            raise ValueError("Choose exactly one placement.")
        return self


class MoveStopCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["move_stop"]
    stop_id: str = Field(..., min_length=1, max_length=MAX_STOP_ID_LENGTH)
    target_day: int = Field(..., ge=1)
    target_block: TimeBlockType | None = None
    placement: StopPlacement = Field(default_factory=lambda: StopPlacement(at_end=True))


class ReorderDayCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["reorder_day"]
    day: int = Field(..., ge=1)
    ordered_stop_ids: list[str] = Field(..., min_length=1, max_length=MAX_ORDERED_STOP_IDS)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "ReorderDayCommand":
        if len(set(self.ordered_stop_ids)) != len(self.ordered_stop_ids):
            raise ValueError("ordered_stop_ids must be unique.")
        return self


class RemoveStopCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["remove_stop"]
    stop_id: str = Field(..., min_length=1, max_length=MAX_STOP_ID_LENGTH)


class SwapStopsCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["swap_stops"]
    first_stop_id: str = Field(..., min_length=1, max_length=MAX_STOP_ID_LENGTH)
    second_stop_id: str = Field(..., min_length=1, max_length=MAX_STOP_ID_LENGTH)

    @model_validator(mode="after")
    def validate_distinct_ids(self) -> "SwapStopsCommand":
        if self.first_stop_id == self.second_stop_id:
            raise ValueError("swap stop ids must be different.")
        return self


class ReplacementCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    type: Literal["scenic", "restaurant"]
    reasoning_summary: str = Field(..., min_length=1)
    itinerary_relation_summary: str = Field(..., min_length=1)


class ReplaceStopCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["replace_stop"]
    stop_id: str = Field(..., min_length=1, max_length=MAX_STOP_ID_LENGTH)
    replacement: ReplacementCandidate


class AddCandidateStopCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["add_candidate_stop"]
    candidate_id: str = Field(..., min_length=1, max_length=MAX_STOP_ID_LENGTH)
    target_day: int = Field(..., ge=1)
    target_block: TimeBlockType
    placement: StopPlacement = Field(default_factory=lambda: StopPlacement(at_end=True))
    requested_start_time: str | None = Field(default=None, max_length=16)


class RouteRepairScope(BaseModel):
    """Constrain a route edit to a small, deterministic local repair."""

    model_config = ConfigDict(extra="forbid")

    target_day: int = Field(..., ge=1)
    goal: Literal["relax_day"]


def build_relax_day_envelope(
    *,
    snapshot: dict[str, Any],
    base_revision_id: str,
    target_day: int,
) -> tuple["TripMutationCommandEnvelope", dict[str, Any]]:
    """Select one safe system-owned stop for a local day-relaxation proposal."""

    source_day = find_day(snapshot, target_day)
    next_day = find_day(snapshot, target_day + 1)
    if source_day is None:
        raise MutationCommandFailedError(command_index=0, reason_code="mutation_command_target_not_found")
    if next_day is None:
        raise MutationCommandFailedError(command_index=0, reason_code="local_repair_no_safe_option")
    candidate: tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None = None
    for block in reversed(source_day.get("blocks", [])):
        for item in reversed(block.get("items", [])):
            if item.get("is_fixed") is True or item.get("source_type") not in SYSTEM_REPAIR_SOURCE_TYPES or not item.get("stable_id"):
                continue
            target_block = next(
                (
                    destination_block
                    for destination_block in next_day.get("blocks", [])
                    if _item_fits_block(item, destination_block)
                    and not any(_items_overlap(item, existing) for existing in destination_block.get("items", []))
                ),
                None,
            )
            if target_block is not None:
                candidate = (block, item, target_block)
                break
        if candidate:
            break
    if candidate is None:
        raise MutationCommandFailedError(command_index=0, reason_code="local_repair_no_safe_option")
    _source_block, item, target_block = candidate
    block_type = TimeBlockType(str(target_block.get("block_type")))
    envelope = TripMutationCommandEnvelope(
        base_revision_id=base_revision_id,
        mutation_kind="route_edit",
        repair=RouteRepairScope(target_day=target_day, goal="relax_day"),
        commands=[MoveStopCommand(
            type="move_stop",
            stop_id=str(item["stable_id"]),
            target_day=target_day + 1,
            target_block=block_type,
            placement=StopPlacement(at_end=True),
        )],
    )
    return envelope, {
        "action": "move",
        "stop_name": str(item.get("name") or "系统补充"),
        "from_day": target_day,
        "to_day": target_day + 1,
        "ownership": "system_suggested",
        "protected": {"fixed_mutations": 0, "must_moves": 0, "must_deletions": 0, "full_planner_calls": 0},
    }


def _items_overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    """Keep a server-selected local repair from creating a time collision."""

    start = str(first.get("start_time") or "")
    end = str(first.get("end_time") or "")
    other_start = str(second.get("start_time") or "")
    other_end = str(second.get("end_time") or "")
    return bool(start and end and other_start and other_end and start < other_end and other_start < end)


def _item_fits_block(item: dict[str, Any], block: dict[str, Any]) -> bool:
    start = str(item.get("start_time") or "")
    end = str(item.get("end_time") or "")
    block_start = str(block.get("start_time") or "")
    block_end = str(block.get("end_time") or "")
    return bool(start and end and block_start and block_end and block_start <= start and end <= block_end)

TripMutationCommand = Annotated[
    MoveStopCommand
    | ReorderDayCommand
    | RemoveStopCommand
    | SwapStopsCommand
    | ReplaceStopCommand
    | AddCandidateStopCommand,
    Field(discriminator="type"),
]


class TripMutationCommandEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = TRIP_MUTATION_COMMAND_SCHEMA_VERSION
    base_revision_id: str = Field(..., min_length=1)
    mutation_kind: Literal["route_edit", "swap", "candidate_admission"]
    commands: list[TripMutationCommand] = Field(..., min_length=1, max_length=MAX_MUTATION_COMMANDS)
    repair: RouteRepairScope | None = None

    @model_validator(mode="after")
    def validate_schema_and_kind(self) -> "TripMutationCommandEnvelope":
        if self.schema_version != TRIP_MUTATION_COMMAND_SCHEMA_VERSION:
            raise UnsupportedMutationCommandSchemaError(self.schema_version)
        command_types = {command.type for command in self.commands}
        if self.mutation_kind == "swap" and not command_types.issubset({"swap_stops", "replace_stop"}):
            raise ValueError("swap mutation_kind accepts only swap_stops or replace_stop commands.")
        if self.mutation_kind == "route_edit" and command_types & {"swap_stops", "replace_stop"}:
            raise ValueError("route_edit mutation_kind does not accept swap commands.")
        if self.mutation_kind == "candidate_admission" and command_types != {"add_candidate_stop"}:
            raise ValueError("candidate_admission accepts only add_candidate_stop commands.")
        if self.mutation_kind != "candidate_admission" and "add_candidate_stop" in command_types:
            raise ValueError("add_candidate_stop requires candidate_admission mutation_kind.")
        if self.repair is not None:
            if self.mutation_kind != "route_edit":
                raise ValueError("repair scope requires route_edit mutation_kind.")
            if not command_types.issubset({"move_stop", "remove_stop"}) or len(self.commands) != 1:
                raise ValueError("local repair accepts exactly one move_stop or remove_stop command.")
        return self


class MutationPreview(BaseModel):
    resulting_snapshot: dict[str, Any]
    content_digest: str
    command_digest: str
    impact_summary: dict[str, Any]
    validation_report: dict[str, Any]
    invalidated_surfaces: list[str]
    refresh_targets: list[str]


class TripMutationEngine:
    def preview(
        self,
        *,
        base_snapshot: dict[str, Any],
        envelope: TripMutationCommandEnvelope,
        candidates_by_id: dict[str, dict[str, Any]] | None = None,
    ) -> MutationPreview:
        snapshot = ensure_stable_item_ids(base_snapshot)
        validate_local_repair_scope(snapshot, envelope)
        baseline_ids = collect_item_ids(snapshot)
        before_digest = itinerary_content_digest(snapshot)
        impact = empty_impact()
        if envelope.repair is not None:
            impact["repair"] = envelope.repair.model_dump(mode="json")
        for index, command in enumerate(envelope.commands):
            try:
                self._apply_command(snapshot, command, impact, candidates_by_id or {})
            except CandidateAdmissionRepairRequiredError:
                raise
            except MutationCommandNoEffectError:
                raise
            except MutationCommandFailedError:
                raise
            except Exception as exc:
                raise MutationCommandFailedError(
                    command_index=index,
                    reason_code="invalid_mutation_command",
                ) from exc
        if envelope.repair is not None and any(getattr(command, "type", None) == "move_stop" for command in envelope.commands):
            reslot_local_repair(snapshot, impact)
        normalize_snapshot_after_mutation(snapshot, impact)
        snapshot = ItineraryResponse.model_validate(snapshot).model_dump(mode="json")
        if itinerary_content_digest(snapshot) == before_digest:
            raise MutationCommandNoEffectError()
        validation_report = build_validation_report(snapshot, baseline_ids, envelope)
        if validation_report["status"] == "invalid":
            first_failure = next(
                (
                    item["code"]
                    for item in validation_report["invariant_results"]
                    if item["status"] == "fail"
                ),
                "mutation_validation_failed",
            )
            raise MutationCommandFailedError(command_index=0, reason_code=first_failure)
        invalidated = build_invalidated_surfaces(impact)
        digest = build_command_digest(envelope)
        impact["invalidated_surfaces"] = invalidated
        impact["route_recalculation_required"] = "route_segments" in invalidated
        return MutationPreview(
            resulting_snapshot=snapshot,
            content_digest=itinerary_content_digest(snapshot),
            command_digest=digest,
            impact_summary=impact,
            validation_report=validation_report,
            invalidated_surfaces=invalidated,
            refresh_targets=invalidated,
        )

    def _apply_command(
        self,
        snapshot: dict[str, Any],
        command: TripMutationCommand,
        impact: dict[str, Any],
        candidates_by_id: dict[str, dict[str, Any]],
    ) -> None:
        if isinstance(command, MoveStopCommand):
            apply_move_stop(snapshot, command, impact)
            return
        if isinstance(command, ReorderDayCommand):
            apply_reorder_day(snapshot, command, impact)
            return
        if isinstance(command, RemoveStopCommand):
            apply_remove_stop(snapshot, command, impact)
            return
        if isinstance(command, SwapStopsCommand):
            apply_swap_stops(snapshot, command, impact)
            return
        if isinstance(command, ReplaceStopCommand):
            apply_replace_stop(snapshot, command, impact)
            return
        if isinstance(command, AddCandidateStopCommand):
            apply_add_candidate_stop(snapshot, command, impact, candidates_by_id)
            return
        raise MutationCommandFailedError(command_index=0, reason_code="invalid_mutation_command")


def build_command_digest(envelope: TripMutationCommandEnvelope) -> str:
    return command_digest(
        {
            "schema_version": envelope.schema_version,
            "mutation_kind": envelope.mutation_kind,
            "base_revision_id": envelope.base_revision_id,
            "commands": [command.model_dump(mode="json") for command in envelope.commands],
            "repair": envelope.repair.model_dump(mode="json") if envelope.repair else None,
        }
    )


def ensure_stable_item_ids(snapshot: dict[str, Any]) -> dict[str, Any]:
    next_snapshot = copy.deepcopy(snapshot)
    seen: set[str] = set()
    for day in next_snapshot.get("days", []):
        day_number = int(day.get("day") or 0)
        flat_index = 0
        for block in day.get("blocks", []):
            block_type = str(block.get("block_type") or "")
            for item in block.get("items", []):
                stable_id = item.get("stable_id")
                if not stable_id:
                    stable_id = legacy_stable_item_id(day_number, block_type, item, flat_index)
                    item["stable_id"] = stable_id
                if stable_id in seen:
                    item["stable_id"] = f"{stable_id}-{flat_index}"
                seen.add(item["stable_id"])
                flat_index += 1
    return next_snapshot


def legacy_stable_item_id(day: int, block_type: str, item: dict[str, Any], index: int) -> str:
    payload = "|".join(
        [
            str(day),
            block_type,
            str(item.get("name") or ""),
            str(item.get("type") or ""),
            str(item.get("start_time") or ""),
            str(item.get("end_time") or ""),
            str(index),
        ]
    )
    return f"stop_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def collect_item_ids(snapshot: dict[str, Any]) -> set[str]:
    return {
        str(item["stable_id"])
        for day in snapshot.get("days", [])
        for block in day.get("blocks", [])
        for item in block.get("items", [])
        if item.get("stable_id")
    }


def find_stop(snapshot: dict[str, Any], stop_id: str) -> tuple[dict[str, Any], dict[str, Any], int] | None:
    for day in snapshot.get("days", []):
        for block in day.get("blocks", []):
            for index, item in enumerate(block.get("items", [])):
                if item.get("stable_id") == stop_id:
                    return day, block, index
    return None


def all_day_items(day: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for block in day.get("blocks", []) for item in block.get("items", [])]


def require_stop(snapshot: dict[str, Any], stop_id: str, *, command_index: int = 0):
    located = find_stop(snapshot, stop_id)
    if located is None:
        raise MutationCommandFailedError(
            command_index=command_index,
            reason_code="mutation_command_target_not_found",
        )
    return located


def assert_mutable_stop(item: dict[str, Any], *, command_index: int = 0) -> None:
    if item.get("is_fixed") is True or item.get("source_type") == "user_fixed":
        raise MutationCommandFailedError(
            command_index=command_index,
            reason_code="fixed_event_mutation_forbidden",
        )


SYSTEM_REPAIR_SOURCE_TYPES = {"auto_seeded_poi", "auto_seeded_meal", "auto_filled"}


def validate_local_repair_scope(
    snapshot: dict[str, Any],
    envelope: TripMutationCommandEnvelope,
) -> None:
    """Keep a UI-triggered relaxation repair away from user-owned route items."""
    if envelope.repair is None:
        return
    command = envelope.commands[0]
    stop_id = command.stop_id
    source_day, source_block, source_index = require_stop(snapshot, stop_id)
    item = source_block["items"][source_index]
    if source_day.get("day") != envelope.repair.target_day:
        raise MutationCommandFailedError(command_index=0, reason_code="local_repair_day_mismatch")
    if item.get("is_fixed") is True or item.get("source_type") not in SYSTEM_REPAIR_SOURCE_TYPES:
        raise MutationCommandFailedError(command_index=0, reason_code="local_repair_protected_item")


def find_day(snapshot: dict[str, Any], day_number: int) -> dict[str, Any] | None:
    return next((day for day in snapshot.get("days", []) if day.get("day") == day_number), None)


def find_block(day: dict[str, Any], block_type: str) -> dict[str, Any] | None:
    return next((block for block in day.get("blocks", []) if str(block.get("block_type")) == block_type), None)


def apply_move_stop(
    snapshot: dict[str, Any],
    command: MoveStopCommand,
    impact: dict[str, Any],
) -> None:
    source_day, source_block, source_index = require_stop(snapshot, command.stop_id)
    item = source_block["items"][source_index]
    assert_mutable_stop(item)
    target_day = find_day(snapshot, command.target_day)
    if target_day is None:
        raise MutationCommandFailedError(command_index=0, reason_code="mutation_command_target_not_found")
    target_block_type = enum_value(command.target_block) or str(source_block.get("block_type"))
    target_block = find_block(target_day, target_block_type)
    if target_block is None:
        raise MutationCommandFailedError(command_index=0, reason_code="invalid_stop_placement")
    if target_day is source_day and target_block is source_block and is_same_block_noop_move(
        source_block,
        source_index,
        command.placement,
    ):
        raise MutationCommandNoEffectError()
    source_block["items"].pop(source_index)
    item["day"] = command.target_day
    insertion_index = resolve_insertion_index(target_day, target_block, command.placement, command.stop_id)
    target_block["items"].insert(insertion_index, item)
    impact["moved_stop_ids"].append(command.stop_id)
    record_day_impact(impact, source_day.get("day"))
    record_day_impact(impact, target_day.get("day"))


def reslot_local_repair(snapshot: dict[str, Any], impact: dict[str, Any]) -> None:
    """Place the one moved activity in the receiving block without changing any other slot."""
    moved_ids = set(impact.get("moved_stop_ids") or [])
    if len(moved_ids) != 1:
        raise MutationCommandFailedError(command_index=0, reason_code="local_repair_requires_one_move")
    moved_id = next(iter(moved_ids))
    located = require_stop(snapshot, moved_id)
    _day, block, _index = located
    item = located[1]["items"][located[2]]
    block_start = minutes_from_hhmmss(str(block.get("start_time") or "00:00:00"))
    block_end = minutes_from_hhmmss(str(block.get("end_time") or "23:59:00"))
    occupied_end = max(
        (minutes_from_hhmmss(str(other.get("end_time") or "00:00:00")) for other in block.get("items", []) if other.get("stable_id") != moved_id),
        default=block_start,
    )
    start = max(block_start, occupied_end)
    end = start + int(item.get("duration_minutes") or 0)
    if end > block_end:
        raise MutationCommandFailedError(command_index=0, reason_code="local_repair_target_capacity_exceeded")
    item["start_time"] = hhmmss_from_minutes(start)
    item["end_time"] = hhmmss_from_minutes(end)


def minutes_from_hhmmss(value: str) -> int:
    hour, minute, *_rest = value.split(":")
    return int(hour) * 60 + int(minute)


def hhmmss_from_minutes(value: int) -> str:
    return f"{(value // 60) % 24:02d}:{value % 60:02d}:00"


def enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def is_same_block_noop_move(
    block: dict[str, Any],
    source_index: int,
    placement: StopPlacement,
) -> bool:
    items = block.get("items", [])
    if placement.at_end:
        return source_index == len(items) - 1
    if placement.before_stop_id:
        return source_index + 1 < len(items) and items[source_index + 1].get("stable_id") == placement.before_stop_id
    if placement.after_stop_id:
        return source_index > 0 and items[source_index - 1].get("stable_id") == placement.after_stop_id
    return False


def resolve_insertion_index(
    target_day: dict[str, Any],
    target_block: dict[str, Any],
    placement: StopPlacement,
    stop_id: str,
) -> int:
    if placement.at_end:
        return len(target_block.get("items", []))
    anchor_id = placement.before_stop_id or placement.after_stop_id
    if anchor_id == stop_id:
        raise MutationCommandFailedError(command_index=0, reason_code="invalid_stop_placement")
    if not anchor_id:
        return len(target_block.get("items", []))
    for block in target_day.get("blocks", []):
        for index, item in enumerate(block.get("items", [])):
            if item.get("stable_id") == anchor_id:
                if block is not target_block:
                    raise MutationCommandFailedError(command_index=0, reason_code="invalid_stop_placement")
                return index if placement.before_stop_id else index + 1
    raise MutationCommandFailedError(command_index=0, reason_code="mutation_command_target_not_found")


def apply_reorder_day(
    snapshot: dict[str, Any],
    command: ReorderDayCommand,
    impact: dict[str, Any],
) -> None:
    day = find_day(snapshot, command.day)
    if day is None:
        raise MutationCommandFailedError(command_index=0, reason_code="mutation_command_target_not_found")
    items = all_day_items(day)
    current_ids = [str(item.get("stable_id")) for item in items]
    if set(current_ids) != set(command.ordered_stop_ids):
        raise MutationCommandFailedError(command_index=0, reason_code="mutation_batch_failed")
    item_by_id = {str(item.get("stable_id")): item for item in items}
    ordered = [item_by_id[stop_id] for stop_id in command.ordered_stop_ids]
    cursor = 0
    for block in day.get("blocks", []):
        count = len(block.get("items", []))
        block["items"] = ordered[cursor : cursor + count]
        cursor += count
    impact["reordered_day_references"].append(str(command.day))
    record_day_impact(impact, command.day)


def apply_remove_stop(
    snapshot: dict[str, Any],
    command: RemoveStopCommand,
    impact: dict[str, Any],
) -> None:
    day, block, index = require_stop(snapshot, command.stop_id)
    item = block["items"][index]
    assert_mutable_stop(item)
    block["items"].pop(index)
    impact["removed_stop_ids"].append(command.stop_id)
    record_day_impact(impact, day.get("day"))


def apply_swap_stops(
    snapshot: dict[str, Any],
    command: SwapStopsCommand,
    impact: dict[str, Any],
) -> None:
    first_day, first_block, first_index = require_stop(snapshot, command.first_stop_id)
    second_day, second_block, second_index = require_stop(snapshot, command.second_stop_id)
    first = first_block["items"][first_index]
    second = second_block["items"][second_index]
    assert_mutable_stop(first)
    assert_mutable_stop(second)
    first_slot = slot_fields(first)
    second_slot = slot_fields(second)
    first_block["items"][first_index] = {**second, **first_slot}
    second_block["items"][second_index] = {**first, **second_slot}
    impact["swapped_stop_ids"].extend([command.first_stop_id, command.second_stop_id])
    record_day_impact(impact, first_day.get("day"))
    record_day_impact(impact, second_day.get("day"))


def apply_replace_stop(
    snapshot: dict[str, Any],
    command: ReplaceStopCommand,
    impact: dict[str, Any],
) -> None:
    day, block, index = require_stop(snapshot, command.stop_id)
    item = block["items"][index]
    assert_mutable_stop(item)
    replacement = command.replacement
    if item.get("name") == replacement.name and item.get("type") == replacement.type:
        raise MutationCommandNoEffectError()
    block["items"][index] = {
        **item,
        "name": replacement.name,
        "type": replacement.type,
        "is_fixed": False,
        "placement_reason": (
            f"{replacement.reasoning_summary} This was swapped into the same time slot after generation."
        ),
        "source_type": "auto_filled",
        "source_label": "已替换",
        "source_reason": replacement.itinerary_relation_summary,
        "local_edit": {
            "previous_name": item.get("name"),
            "source": "completion_recommendation",
            "status": "committed",
            "reasoning_summary": replacement.reasoning_summary,
            "itinerary_relation_summary": replacement.itinerary_relation_summary,
            "original_type": item.get("type"),
            "original_placement_reason": item.get("placement_reason"),
            "original_source_type": item.get("source_type"),
            "original_source_label": item.get("source_label"),
            "original_source_reason": item.get("source_reason"),
        },
    }
    impact["replaced_stop_ids"].append(command.stop_id)
    record_day_impact(impact, day.get("day"))


def apply_add_candidate_stop(
    snapshot: dict[str, Any],
    command: AddCandidateStopCommand,
    impact: dict[str, Any],
    candidates_by_id: dict[str, dict[str, Any]],
) -> None:
    candidate = candidates_by_id.get(command.candidate_id)
    if candidate is None:
        raise MutationCommandFailedError(command_index=0, reason_code="candidate_not_found")
    workflow_state = str(candidate.get("workflow_state") or "pending")
    if workflow_state == "rejected":
        raise MutationCommandFailedError(command_index=0, reason_code="candidate_rejected")
    if workflow_state == "scheduled":
        raise MutationCommandFailedError(command_index=0, reason_code="candidate_already_scheduled")
    missing_fact_codes: list[str] = []
    if candidate.get("coordinates") is None:
        missing_fact_codes.append("candidate_missing_location")
    if candidate.get("estimated_duration_minutes") is None:
        missing_fact_codes.append("candidate_missing_duration")
    if missing_fact_codes:
        suggested_actions = []
        if "candidate_missing_location" in missing_fact_codes:
            suggested_actions.append("resolve_location")
        if "candidate_missing_duration" in missing_fact_codes:
            suggested_actions.append("provide_duration")
        raise CandidateAdmissionRepairRequiredError(
            candidate_id=command.candidate_id,
            repair={
                "candidate_id": command.candidate_id,
                "conflict_codes": ["missing_candidate_facts"],
                "blocking_item_ids": [],
                "affected_day_references": [str(command.target_day)],
                "available_windows": [],
                "missing_fact_codes": missing_fact_codes,
                "suggested_actions": suggested_actions,
            },
        )
    if candidate_duplicates_existing_place(snapshot, candidate):
        raise CandidateAdmissionRepairRequiredError(
            candidate_id=command.candidate_id,
            repair={
                "candidate_id": command.candidate_id,
                "conflict_codes": ["duplicate_existing_place"],
                "blocking_item_ids": [],
                "affected_day_references": [str(command.target_day)],
                "available_windows": [],
                "missing_fact_codes": [],
                "suggested_actions": ["replace_existing_flexible_stop", "choose_another_position"],
            },
        )
    target_day = find_day(snapshot, command.target_day)
    if target_day is None:
        raise MutationCommandFailedError(command_index=0, reason_code="mutation_command_target_not_found")
    target_block = find_block(target_day, enum_value(command.target_block) or "")
    if target_block is None:
        raise MutationCommandFailedError(command_index=0, reason_code="invalid_stop_placement")
    coordinates = candidate["coordinates"]
    duration_minutes = int(candidate["estimated_duration_minutes"])
    start_time = command.requested_start_time or str(target_block.get("start_time") or "09:00:00")
    end_time = add_minutes_to_hhmmss(start_time, duration_minutes)
    item = {
        "stable_id": stable_scheduled_id_for_candidate(command.candidate_id, command.target_day),
        "name": candidate["display_name"],
        "type": scheduled_type_for_candidate(candidate),
        "city": None,
        "latitude": coordinates["latitude"],
        "longitude": coordinates["longitude"],
        "duration_minutes": duration_minutes,
        "day": command.target_day,
        "start_time": start_time,
        "end_time": end_time,
        "is_fixed": False,
        "placement_reason": "由候选地点通过 server-authoritative admission command 加入行程。",
        "source_type": "user_seed",
        "source_label": "候选加入",
        "source_reason": f"candidate:{command.candidate_id}; source:{candidate.get('source_kind')}",
        "travel_from_name": None,
        "travel_distance_m": None,
        "travel_duration_s": None,
        "selection_top_candidates": [],
        "selection_rejected_candidates": [],
        "candidate_id": command.candidate_id,
        "candidate_provenance": {
            "source_kind": candidate.get("source_kind"),
            "source_ref": candidate.get("source_ref"),
            "evidence_refs": candidate.get("evidence_refs") or [],
            "content_digest": candidate.get("content_digest"),
            "location_state": candidate.get("location_state"),
            "duration_state": candidate.get("duration_state"),
            "confidence": candidate.get("confidence"),
        },
    }
    insertion_index = resolve_insertion_index(target_day, target_block, command.placement, item["stable_id"])
    target_block.setdefault("items", []).insert(insertion_index, item)
    impact["admitted_candidate_ids"].append(command.candidate_id)
    impact["scheduled_item_ids"].append(item["stable_id"])
    record_day_impact(impact, target_day.get("day"))


def slot_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "day": item.get("day"),
        "start_time": item.get("start_time"),
        "end_time": item.get("end_time"),
    }


def normalize_snapshot_after_mutation(snapshot: dict[str, Any], impact: dict[str, Any]) -> None:
    affected = {int(day) for day in impact["affected_day_references"] if str(day).isdigit()}
    for day in snapshot.get("days", []):
        if int(day.get("day") or 0) not in affected:
            continue
        anchor = snapshot.get("planning_anchor_source", {})
        previous_name = anchor.get("source_name")
        previous_latitude = anchor.get("latitude")
        previous_longitude = anchor.get("longitude")
        for block in day.get("blocks", []):
            for item in block.get("items", []):
                item["travel_from_name"] = previous_name
                if previous_latitude is None or previous_longitude is None:
                    item["travel_distance_m"] = None
                    item["travel_duration_s"] = None
                    item["travel_calculation_status"] = "missing_anchor_coordinates"
                else:
                    distance_m = deterministic_route_distance_m(
                        previous_latitude, previous_longitude, item.get("latitude"), item.get("longitude"),
                    )
                    item["travel_distance_m"] = distance_m
                    item["travel_duration_s"] = deterministic_route_duration_s(distance_m)
                    item["travel_calculation_status"] = "deterministic_local_estimate"
                previous_name = item.get("name")
                previous_latitude = item.get("latitude")
                previous_longitude = item.get("longitude")
    snapshot["completion_recommendation"] = None
    snapshot["completion_intelligence"] = None
    # This is a pure deterministic recalculation over the mutated snapshot. It does
    # not invoke parsing, providers, or the full planner.
    from app.services.planner_realism_analyzer import analyze_planner_realism

    snapshot["planner_realism"] = analyze_planner_realism(
        ItineraryResponse.model_validate(snapshot)
    ).model_dump(mode="json")


def deterministic_route_distance_m(
    origin_latitude: Any, origin_longitude: Any, destination_latitude: Any, destination_longitude: Any,
) -> int | None:
    """Local great-circle estimate for a repaired leg; never an implied provider fact."""
    try:
        lat1, lon1, lat2, lon2 = map(float, (origin_latitude, origin_longitude, destination_latitude, destination_longitude))
    except (TypeError, ValueError):
        return None
    phi1, phi2 = radians(lat1), radians(lat2)
    delta_phi, delta_lambda = radians(lat2 - lat1), radians(lon2 - lon1)
    value = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    return round(6_371_000 * 2 * atan2(sqrt(value), sqrt(1 - value)))


def deterministic_route_duration_s(distance_m: int | None) -> int | None:
    if distance_m is None:
        return None
    # 18 km/h is an intentionally conservative local urban-transfer estimate.
    return max(60, round(distance_m / 18_000 * 3600))


def build_validation_report(
    snapshot: dict[str, Any],
    baseline_ids: set[str],
    envelope: TripMutationCommandEnvelope,
) -> dict[str, Any]:
    itinerary = ItineraryResponse.model_validate(snapshot)
    current_ids = collect_item_ids(snapshot)
    duplicated = len(current_ids) != sum(
        1
        for day in snapshot.get("days", [])
        for block in day.get("blocks", [])
        for item in block.get("items", [])
    )
    invariant_results = [
        {"code": "COMMAND_SCHEMA_VALID", "status": "pass", "evidence": {"schema_version": envelope.schema_version}},
        {"code": "COMMANDS_REFERENCE_BASE_REVISION", "status": "pass", "evidence": {"base_revision_id": envelope.base_revision_id}},
        {
            "code": "STABLE_ITEM_IDENTITY",
            "status": "fail" if duplicated else "pass",
            "evidence": {"before_count": len(baseline_ids), "after_count": len(current_ids)},
        },
        no_schedule_overlap(itinerary).model_dump(mode="json"),
        within_day_availability(itinerary).model_dump(mode="json"),
        within_arrival_departure_boundaries(itinerary).model_dump(mode="json"),
        no_duplicate_scheduled_place(itinerary).model_dump(mode="json"),
        {
            "code": "NO_DANGLING_ROUTE_REFERENCE",
            "status": "pass" if no_dangling_route_reference(snapshot) else "fail",
            "evidence": {},
        },
        {
            "code": "ROUTE_UNKNOWN_NOT_ZERO",
            "status": "pass" if route_unknown_not_zero(snapshot) else "fail",
            "evidence": {},
        },
    ]
    status = "invalid" if any(item["status"] == "fail" for item in invariant_results) else "valid"
    return {"schema_version": "1.0", "status": status, "invariant_results": invariant_results, "warnings": []}


def no_dangling_route_reference(snapshot: dict[str, Any]) -> bool:
    known = {
        str(item.get("name"))
        for day in snapshot.get("days", [])
        for block in day.get("blocks", [])
        for item in block.get("items", [])
    }
    anchor = snapshot.get("planning_anchor_source", {}).get("source_name")
    if anchor:
        known.add(str(anchor))
    for day in snapshot.get("days", []):
        for block in day.get("blocks", []):
            for item in block.get("items", []):
                ref = item.get("travel_from_name")
                if ref is not None and str(ref) not in known:
                    return False
    return True


def route_unknown_not_zero(snapshot: dict[str, Any]) -> bool:
    for day in snapshot.get("days", []):
        for block in day.get("blocks", []):
            for item in block.get("items", []):
                if item.get("travel_from_name") and item.get("travel_duration_s") == 0:
                    return False
    return True


def empty_impact() -> dict[str, Any]:
    return {
        "affected_day_references": [],
        "moved_stop_ids": [],
        "removed_stop_ids": [],
        "reordered_day_references": [],
        "swapped_stop_ids": [],
        "replaced_stop_ids": [],
        "admitted_candidate_ids": [],
        "scheduled_item_ids": [],
        "fixed_items_touched": [],
        "route_recalculation_required": False,
        "invalidated_surfaces": [],
        "warning_codes": [],
        "execution_evidence": {
            "planner_calls": 0,
            "parser_calls": 0,
            "llm_calls": 0,
            "route_provider_calls": 0,
        },
    }


def record_day_impact(impact: dict[str, Any], day: Any) -> None:
    value = str(day)
    if value not in impact["affected_day_references"]:
        impact["affected_day_references"].append(value)


def build_invalidated_surfaces(impact: dict[str, Any]) -> list[str]:
    surfaces = ["route_segments", "trip_readiness", "planner_realism", "completion_intelligence"]
    if impact["removed_stop_ids"] or impact["replaced_stop_ids"] or impact["admitted_candidate_ids"]:
        surfaces.append("selection")
    return surfaces


def candidate_duplicates_existing_place(snapshot: dict[str, Any], candidate: dict[str, Any]) -> bool:
    normalized = str(candidate.get("normalized_name") or "").strip()
    for day in snapshot.get("days", []):
        for block in day.get("blocks", []):
            for item in block.get("items", []):
                if normalized and compact_text(str(item.get("name") or "")) == normalized:
                    return True
    return False


def compact_text(value: str) -> str:
    return "".join(value.strip().casefold().split())


def stable_scheduled_id_for_candidate(candidate_id: str, day: int) -> str:
    digest = hashlib.sha256(f"{candidate_id}|{day}".encode("utf-8")).hexdigest()[:20]
    return f"stop_cand_{digest}"


def scheduled_type_for_candidate(candidate: dict[str, Any]) -> str:
    if candidate.get("candidate_type") == "meal":
        return "restaurant"
    return "scenic"


def add_minutes_to_hhmmss(value: str, minutes: int) -> str:
    parts = value.split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0
    total = hour * 60 + minute + minutes
    return f"{(total // 60) % 24:02d}:{total % 60:02d}:00"
