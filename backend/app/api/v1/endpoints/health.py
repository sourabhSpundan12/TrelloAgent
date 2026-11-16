import time
from datetime import datetime, timezone
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from app.core.config import settings
from app.database.mongodb import MongoDBManager

router = APIRouter()
START_TIME = time.time()


class ServiceStatus(BaseModel):
    mongodb: str
    gemini_configured: bool
    trello_configured: bool
    n8n_configured: bool


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    uptime_seconds: float
    timestamp: str
    services: ServiceStatus


class LivenessResponse(BaseModel):
    status: str = "alive"
    timestamp: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    timestamp: str


class InfoResponse(BaseModel):
    app_name: str
    version: str
    environment: str
    api_prefix: str
    docs_url: str


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Health Check",
    description="Check the operational health and connectivity of the backend and backing services."
)
async def get_health():
    db_connected = await MongoDBManager.ping()
    uptime = round(time.time() - START_TIME, 2)
    overall_status = "healthy" if db_connected else "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.VERSION,
        environment=settings.APP_ENV,
        database="connected" if db_connected else "disconnected",
        uptime_seconds=uptime,
        timestamp=datetime.now(timezone.utc).isoformat(),
        services=ServiceStatus(
            mongodb="connected" if db_connected else "disconnected",
            gemini_configured=bool(settings.GEMINI_API_KEY),
            trello_configured=bool(settings.TRELLO_API_KEY and settings.TRELLO_TOKEN),
            n8n_configured=bool(settings.N8N_WEBHOOK_URL or settings.N8N_API_KEY),
        )
    )


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Returns HTTP 200 if the application process is running. Does not depend on external services."
)
async def liveness_probe():
    return LivenessResponse(
        status="alive",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness Probe",
    description="Returns HTTP 200 if MongoDB is connected. Fails with HTTP 503 if required database dependencies are unavailable."
)
async def readiness_probe(response: Response):
    db_connected = await MongoDBManager.ping()
    now_iso = datetime.now(timezone.utc).isoformat()

    if not db_connected:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="not_ready",
            database="disconnected",
            timestamp=now_iso,
        )

    return ReadinessResponse(
        status="ready",
        database="connected",
        timestamp=now_iso,
    )


@router.get(
    "/info",
    response_model=InfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Application Metadata",
    description="Public application information without exposing internal connection strings or credentials."
)
async def get_app_info():
    return InfoResponse(
        app_name=settings.APP_NAME,
        version=settings.VERSION,
        environment=settings.APP_ENV,
        api_prefix=settings.API_V1_PREFIX,
        docs_url="/docs",
    )
