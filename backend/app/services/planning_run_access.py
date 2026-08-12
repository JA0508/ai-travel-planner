from __future__ import annotations

from os import getenv

from fastapi import Request, Response

from app.trips.access import hash_capability


PLANNING_RUN_COOKIE = "planning_run_capability"


def set_planning_run_capability_cookie(response: Response, capability: str) -> None:
    secure = getenv("TRIP_CAPABILITY_COOKIE_SECURE", "false").strip().lower() == "true"
    response.set_cookie(
        key=PLANNING_RUN_COOKIE,
        value=capability,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )


def planning_run_capability_hash(request: Request) -> str:
    capability = request.cookies.get(PLANNING_RUN_COOKIE)
    return hash_capability(capability) if capability else ""
