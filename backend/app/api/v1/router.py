from fastapi import APIRouter
from app.api.v1.endpoints import (
    activities,
    ai,
    approvals,
    auth,
    health,
    mcp,
    overview,
    reports,
    tasks,
    users,
)
from app.tool_discovery.routes import router as tool_discovery_router
from app.tool_registry.routes import router as tool_registry_router

api_v1_router = APIRouter()

# Health endpoints
api_v1_router.include_router(health.router, tags=["Health"])

# Authentication endpoints
api_v1_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])

# User management endpoints
api_v1_router.include_router(users.router, prefix="/users", tags=["Users"])

# Phase 4: Dynamic Tool Registry & Tool Discovery endpoints
api_v1_router.include_router(tool_registry_router, prefix="/tools", tags=["Tool Registry"])
api_v1_router.include_router(tool_discovery_router, prefix="/tools", tags=["Tool Discovery"])

# Phase 4B: Model Context Protocol (MCP) Management endpoints
api_v1_router.include_router(mcp.router, prefix="/mcp", tags=["MCP Management"])

# Phase 4/7A: AI Assistant Intent & Orchestration endpoints
api_v1_router.include_router(ai.router, prefix="/ai", tags=["AI Assistant"])

# Phase 6: Human-in-the-Loop Approvals & Task Planning endpoints
api_v1_router.include_router(approvals.router, prefix="/approvals", tags=["Approvals"])

# Phase 7A: Live Trello Tasks, Overview, Activities, and Reports endpoints
api_v1_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_v1_router.include_router(overview.router, prefix="/overview", tags=["Overview"])
api_v1_router.include_router(activities.router, prefix="/activities", tags=["Activities"])
api_v1_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
