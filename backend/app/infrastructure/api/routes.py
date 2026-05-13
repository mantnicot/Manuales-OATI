from fastapi import APIRouter

from app.infrastructure.api.routes_library import router as library_router
from app.infrastructure.api.routes_manuals import router as manuals_router

api_router = APIRouter()
api_router.include_router(manuals_router)
api_router.include_router(library_router)
