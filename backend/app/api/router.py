from fastapi import APIRouter

from app.api.routes.intent import router as intent_router
from app.api.routes.itinerary import router as itinerary_router
from app.api.routes.trip_compiler import router as trip_compiler_router
from app.api.routes.trips import router as trips_router

api_router = APIRouter()
api_router.include_router(intent_router)
api_router.include_router(itinerary_router)
api_router.include_router(trip_compiler_router)
api_router.include_router(trips_router)
