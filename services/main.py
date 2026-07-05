from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.config import settings
from services.auth.router import router as auth_router
from services.resume_management.router import router as resume_management_router
from services.user_profile.router import router as user_profile_router
from services.jobs.router import router as jobs_router
from services.applications.router import router as applications_router
from services.resume_parsing.router import router as resume_parsing_router

app = FastAPI(
    title="CareerOS API Gateway",
    description="Main entry point for all CareerOS backend services.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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

@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "service": "api-gateway"}
