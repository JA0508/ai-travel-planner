import os
import logging
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.runtime_config import (
    configure_logging,
    get_runtime_configuration_summary,
    parse_cors_allow_origins,
)
from app.services.poi_discovery_provider import (
    enforce_poi_discovery_configuration,
    get_poi_discovery_capability,
)
from app.api.routes.trips import persistence_readiness

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
configure_logging()
logger = logging.getLogger(__name__)


app = FastAPI(title="Travel Itinerary Planner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=parse_cors_allow_origins(os.getenv("CORS_ALLOW_ORIGINS")),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.middleware("http")
async def attach_request_observability(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # Middleware is the last observability boundary; re-raise so FastAPI keeps its normal error handling.
        logger.exception(
            "Unhandled request failure request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        raise

    duration_ms = (time.perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
    return response


@app.on_event("startup")
def check_runtime_capabilities() -> None:
    enforce_poi_discovery_configuration()


@app.get("/readiness")
def readiness() -> dict:
    poi_capability = get_poi_discovery_capability(validate_provider=True)
    return {
        "status": "ok" if poi_capability.production_ready else "failed",
        "poi_discovery": poi_capability.to_dict(),
        "runtime": get_runtime_configuration_summary(),
        "persistence": persistence_readiness(),
    }
