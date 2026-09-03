import sys
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from backend.config import settings
from backend.routers.auth import router as auth_router
from backend.routers.resume_management import router as resume_management_router
from backend.routers.user_profile import router as user_profile_router
from backend.routers.jobs import router as jobs_router
from backend.routers.applications import router as applications_router
from backend.routers.resume_parsing import router as resume_parsing_router
from backend.routers.workflows import router as orchestrator_router

from contextlib import asynccontextmanager
from backend.services.scheduler import start_scheduler, stop_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()

app = FastAPI(
    title="CareerOS API Gateway",
    description="Main entry point for all CareerOS backend services.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(resume_management_router)
app.include_router(user_profile_router)
app.include_router(jobs_router)
app.include_router(applications_router)
app.include_router(resume_parsing_router)
app.include_router(orchestrator_router)

@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "api-gateway"}
