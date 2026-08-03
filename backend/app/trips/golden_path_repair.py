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
    target = receiving_days[0]
    candidates: list[tuple[str, str, str]] = []
    for block in source.get("blocks", []):
        for item in block.get("items", []):
            if item.get("is_fixed") or item.get("source_type") not in SYSTEM_SUGGESTED:
                continue
            stable_id = item.get("stable_id")
            if stable_id:
                candidates.append((str(stable_id), str(item.get("name") or ""), str(block.get("block_type") or "afternoon")))
    if not candidates:
        raise InvalidRevisionOperationError("This day has no system-suggested activity that can be moved safely.")
    # Later activities are generally least disruptive.  The stable id removes any parser-order dependency.
    stop_id, name, block = sorted(candidates, key=lambda item: item[0])[-1]
    return LocalRepairSelection(stop_id=stop_id, stop_name=name, from_day=target_day, to_day=target, target_block=block)


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
