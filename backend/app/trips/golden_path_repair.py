"""Deterministic, local route repair used by the live golden path.

The browser supplies only the problem (a rushed day).  This module owns the
selection and emits a normal typed mutation envelope for the existing atomic
proposal/apply machinery.  It never parses, plans, or calls a route provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import InvalidRevisionOperationError
from .mutation_commands import MoveStopCommand, RouteRepairScope, StopPlacement, TripMutationCommandEnvelope


SYSTEM_SUGGESTED = {"auto_seeded_poi", "auto_seeded_meal", "auto_filled"}


@dataclass(frozen=True, slots=True)
class LocalRepairSelection:
    stop_id: str
    stop_name: str
    from_day: int
    to_day: int
    target_block: str


def select_relax_day_repair(snapshot: dict[str, Any], *, target_day: int) -> LocalRepairSelection:
    loads = {
        int(load["day"]): load
        for load in (snapshot.get("planner_realism") or {}).get("daily_loads", [])
        if isinstance(load, dict) and load.get("day") is not None
    }
    if loads.get(target_day, {}).get("classification") != "rushed":
        raise InvalidRevisionOperationError("Only a rushed day can receive this local repair.")
    days = {int(day["day"]): day for day in snapshot.get("days", []) if day.get("day") is not None}
    source = days.get(target_day)
    if source is None:
        raise InvalidRevisionOperationError("The requested day does not exist in this route.")

    receiving_days = [
        day_number
        for day_number in (target_day + 1, target_day - 1)
        if day_number in days and loads.get(day_number, {}).get("classification") in {"relaxed", "balanced"}
    ]
    if not receiving_days:
        raise InvalidRevisionOperationError("There is no adjacent day with enough room for a safe local move.")
    # Prefer the next day, then the lightest one.  This is stable and visible in tests.
    receiving_days.sort(key=lambda day: (0 if day == target_day + 1 else 1, loads[day].get("activity_count", 0), day))
    candidates: list[tuple[str, str, str, bool, int]] = []
    for receiving_rank, receiving_day_number in enumerate(receiving_days):
        receiving_day = days[receiving_day_number]
        for block in source.get("blocks", []):
            target_block = next(
                (
                    candidate
                    for candidate in receiving_day.get("blocks", [])
                    if candidate.get("block_type") == block.get("block_type")
                ),
                None,
            )
            if target_block is None:
                continue
            for item in block.get("items", []):
                if (
                    item.get("is_fixed")
                    or item.get("source_type") not in SYSTEM_SUGGESTED
                    or not repair_item_fits_at_end(item=item, target_block=target_block)
                    or duplicates_receiving_day(item=item, receiving_day=receiving_day)
                ):
                    continue
                stable_id = item.get("stable_id")
                if stable_id:
                    candidates.append(
                        (
                            str(stable_id),
                            str(item.get("name") or ""),
                            str(block.get("block_type") or "afternoon"),
                            item.get("source_type") == "auto_seeded_meal",
                            receiving_rank,
                        )
                    )
    if not candidates:
        raise InvalidRevisionOperationError("This day has no system-suggested activity that can be moved safely.")
    # Preserve meal rhythm when another system suggestion can absorb the repair.
    movable = [candidate for candidate in candidates if not candidate[3]] or candidates
    preferred_rank = min(candidate[4] for candidate in movable)
    movable = [candidate for candidate in movable if candidate[4] == preferred_rank]
    # Later activities are generally least disruptive.  The stable id removes any parser-order dependency.
    stop_id, name, block, _, receiving_rank = sorted(movable, key=lambda item: item[0])[-1]
    return LocalRepairSelection(
        stop_id=stop_id,
        stop_name=name,
        from_day=target_day,
        to_day=receiving_days[receiving_rank],
        target_block=block,
    )


def repair_item_fits_at_end(*, item: dict[str, Any], target_block: dict[str, Any]) -> bool:
    duration = int(item.get("duration_minutes") or 0)
    if duration <= 0:
        return False
    block_start = hhmm_minutes(target_block.get("start_time"))
    block_end = hhmm_minutes(target_block.get("end_time"))
    occupied_end = max(
        (hhmm_minutes(candidate.get("end_time")) for candidate in target_block.get("items", [])),
        default=block_start,
    )
    return max(block_start, occupied_end) + duration <= block_end


def duplicates_receiving_day(*, item: dict[str, Any], receiving_day: dict[str, Any]) -> bool:
    identity = item.get("canonical_place_id") or item.get("name")
    return any(
        (candidate.get("canonical_place_id") or candidate.get("name")) == identity
        for block in receiving_day.get("blocks", [])
        for candidate in block.get("items", [])
    )


def hhmm_minutes(value: Any) -> int:
    hour, minute, *_ = str(value or "00:00").split(":")
    return int(hour) * 60 + int(minute)


def build_relax_day_envelope(*, snapshot: dict[str, Any], base_revision_id: str, target_day: int) -> tuple[TripMutationCommandEnvelope, LocalRepairSelection]:
    selection = select_relax_day_repair(snapshot, target_day=target_day)
    return (
        TripMutationCommandEnvelope(
            base_revision_id=base_revision_id,
            mutation_kind="route_edit",
            repair=RouteRepairScope(target_day=target_day, goal="relax_day"),
            commands=[
                MoveStopCommand(
                    type="move_stop",
                    stop_id=selection.stop_id,
                    target_day=selection.to_day,
                    target_block=selection.target_block,
                    placement=StopPlacement(at_end=True),
                )
            ],
        ),
        selection,
    )
