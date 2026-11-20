from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints.health import router as root_health_router
from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.logging import logger, setup_logging
from app.database.indexes import create_database_indexes
from app.database.mongodb import MongoDBManager
from app.middleware.error_handler import (
    app_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.middleware.logging_middleware import StructuredLoggingMiddleware
from app.mcp_server import create_mcp_streamable_app
from app.services.auth_service import AuthService
from app.services.one_hour_reminder_service import OneHourReminderService
from app.tool_registry.service import ToolRegistryService

mcp_subapp = create_mcp_streamable_app(streamable_http_path="/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]")
    await MongoDBManager.connect()

    # Ensure indexes and bootstrap admin if configured
    try:
        db = MongoDBManager.get_db()
        await create_database_indexes(db)
        auth_service = AuthService(db)
        await auth_service.bootstrap_admin()
        tool_service = ToolRegistryService(db)
        await tool_service.seed_default_tools()
    except Exception as exc:
        logger.warning(f"Startup post-connection hook encountered an issue: {exc}")

    # Module 5: Start background worker for automatic 1-hour deadline reminders
    import asyncio
    async def _one_hour_reminder_worker():
        while True:
            try:
                await asyncio.sleep(60)
                db = MongoDBManager.get_db()
                await OneHourReminderService.process_due_reminders(db)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"One-hour reminder worker encountered an error: {e}")

    reminder_task = asyncio.create_task(_one_hour_reminder_worker())

    try:
        async with mcp_subapp.router.lifespan_context(mcp_subapp):
            yield
    finally:
        reminder_task.cancel()

    # Shutdown
    logger.info(f"Shutting down {settings.PROJECT_NAME}...")
    await MongoDBManager.disconnect()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for Agentic Task Manager with Dynamic Tools, Human-in-the-Loop Approvals, and Trello Integration.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Structured request/response logging middleware
app.add_middleware(StructuredLoggingMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception Handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Root health check endpoint for container orchestrators
app.include_router(root_health_router, tags=["Health"])

# Versioned API routes (/api/v1)
app.include_router(api_v1_router, prefix=settings.API_V1_STR)

# Mount official Model Context Protocol (MCP) server over Streamable HTTP
app.mount("/mcp", mcp_subapp)


@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "health": "/health",
        "api_v1": settings.API_V1_STR,
    }
