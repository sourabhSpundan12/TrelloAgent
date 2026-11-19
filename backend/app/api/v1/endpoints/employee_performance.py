from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.schemas.user import UserResponse
from app.schemas.task_assignment import (
    EmployeePerformanceResponse,
    EmployeeLevelHistoryResponse,
    EmployeeTaskReportSummary,
    TaskAssignmentResponse,
)
from app.services.performance_service import PerformanceCalculationService
from app.services.task_assignment_service import TaskAssignmentService

router = APIRouter()


@router.get(
    "/reports/summary",
    response_model=List[EmployeeTaskReportSummary],
    summary="Get employee overview reports for all registered employees",
    description="Returns aggregate counts, on-time completion rate, duration averages, and performance level badge per employee.",
)
async def get_all_employees_summary(
    board_id: Optional[str] = Query(None, description="Optional board filter"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    # 1. Reconcile live board cards to ensure existing Trello assignments & states are tracked
    await TaskAssignmentService.reconcile_board_cards(db, board_id=board_id)

    # 2. Collect employees from MongoDB users & Trello board members
    users_cursor = db["users"].find({"is_active": True})
    users = await users_cursor.to_list(length=200)

    # Also fetch board members to include any Trello collaborator
    from app.mcp_server import trello_tools
    trello_members_res = await trello_tools.trello_list_board_members(board_id=board_id)
    trello_members = trello_members_res.get("members", [])

    seen_names = set()
    employees_to_process = []

    for u in users:
        u_name = u.get("full_name") or u.get("email")
        seen_names.add(u_name.lower().strip())
        employees_to_process.append({
            "id": str(u["_id"]),
            "name": u_name,
            "email": u.get("email"),
        })

    for tm in trello_members:
        tm_name = tm.get("fullName") or tm.get("username")
        if tm_name and tm_name.lower().strip() not in seen_names:
            seen_names.add(tm_name.lower().strip())
            employees_to_process.append({
                "id": str(tm.get("id")),
                "name": tm_name,
                "email": f"{tm.get('username', 'member')}@trello.board",
            })

    summaries = []
    for emp in employees_to_process:
        emp_id = emp["id"]
        emp_name = emp["name"]
        tasks = await TaskAssignmentService.get_employee_tasks(
            db=db,
            employee_id=emp_id,
            board_id=board_id,
        )

        assigned_c = len([t for t in tasks if t.get("status") == "assigned"])
        in_prog_c = len([t for t in tasks if t.get("status") == "in_progress"])
        comp_c = len([t for t in tasks if t.get("status") == "completed"])
        overdue_c = len([t for t in tasks if t.get("is_overdue")])

        # Fetch performance snapshot
        perf = await db["employee_performance"].find_one({
            "$or": [{"employee_id": emp_id}, {"employee_name": emp_name}]
        })
        if not perf or (comp_c > 0 and perf.get("level") == "NOT_ENOUGH_DATA" and comp_c >= 3):
            perf = await PerformanceCalculationService.calculate_employee_performance(
                db=db,
                employee_id=emp_id,
                employee_name=emp_name,
            )

        summaries.append(EmployeeTaskReportSummary(
            employee_id=emp_id,
            employee_name=emp_name,
            employee_email=emp.get("email"),
            assigned_count=assigned_c,
            in_progress_count=in_prog_c,
            completed_count=comp_c,
            overdue_count=overdue_c,
            on_time_completion_rate=perf.get("on_time_rate", 0.0) if perf else 0.0,
            avg_estimated_duration_minutes=perf.get("avg_estimated_minutes", 0.0) if perf else 0.0,
            avg_actual_duration_minutes=perf.get("avg_actual_minutes", 0.0) if perf else 0.0,
            performance_level=perf.get("level", "NOT_ENOUGH_DATA") if perf else "NOT_ENOUGH_DATA",
            overall_score=perf.get("overall_score", 0.0) if perf else 0.0,
            tasks=[TaskAssignmentResponse(**t) for t in tasks],
        ))

    return summaries


@router.get(
    "/{employee_id}/performance",
    response_model=EmployeePerformanceResponse,
    summary="Get employee performance metrics and level",
)
async def get_employee_performance(
    employee_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    perf = await db["employee_performance"].find_one({"employee_id": str(employee_id)})
    if not perf:
        perf = await PerformanceCalculationService.calculate_employee_performance(
            db=db,
            employee_id=str(employee_id),
        )
    return perf


@router.get(
    "/{employee_id}/performance/history",
    response_model=List[EmployeeLevelHistoryResponse],
    summary="Get employee performance level transition history",
)
async def get_employee_level_history(
    employee_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    cursor = db["employee_level_history"].find({"employee_id": str(employee_id)}).sort("calculated_at", -1)
    history = await cursor.to_list(length=100)
    for h in history:
        h["id"] = str(h["_id"])
    return history


@router.post(
    "/{employee_id}/performance/recalculate",
    response_model=EmployeePerformanceResponse,
    summary="Force recalculation of employee performance metrics",
)
async def recalculate_employee_performance(
    employee_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    perf = await PerformanceCalculationService.calculate_employee_performance(
        db=db,
        employee_id=str(employee_id),
    )
    return perf


@router.get(
    "/{employee_id}/report",
    response_model=EmployeeTaskReportSummary,
    summary="Get detailed reporting summary for an individual employee",
)
async def get_employee_report(
    employee_id: str,
    board_id: Optional[str] = Query(None, description="Optional board filter"),
    status: Optional[str] = Query(None, description="Optional status filter"),
    from_date: Optional[datetime] = Query(None, description="From date"),
    to_date: Optional[datetime] = Query(None, description="To date"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    try:
        user = await db["users"].find_one({"_id": ObjectId(employee_id)})
    except Exception:
        user = await db["users"].find_one({"email": employee_id})

    tasks = await TaskAssignmentService.get_employee_tasks(
        db=db,
        employee_id=employee_id,
        board_id=board_id,
        status_filter=status,
        from_date=from_date,
        to_date=to_date,
    )

    assigned_c = len([t for t in tasks if t.get("status") == "assigned"])
    in_prog_c = len([t for t in tasks if t.get("status") == "in_progress"])
    comp_c = len([t for t in tasks if t.get("status") == "completed"])
    overdue_c = len([t for t in tasks if t.get("is_overdue")])

    perf = await db["employee_performance"].find_one({"employee_id": str(employee_id)})
    if not perf:
        perf = await PerformanceCalculationService.calculate_employee_performance(
            db=db,
            employee_id=str(employee_id),
            employee_name=user.get("full_name") if user else None,
        )

    return EmployeeTaskReportSummary(
        employee_id=employee_id,
        employee_name=user.get("full_name") if user else None,
        employee_email=user.get("email") if user else None,
        assigned_count=assigned_c,
        in_progress_count=in_prog_c,
        completed_count=comp_c,
        overdue_count=overdue_c,
        on_time_completion_rate=perf.get("on_time_rate", 0.0) if perf else 0.0,
        avg_estimated_duration_minutes=perf.get("avg_estimated_minutes", 0.0) if perf else 0.0,
        avg_actual_duration_minutes=perf.get("avg_actual_minutes", 0.0) if perf else 0.0,
        performance_level=perf.get("level", "NOT_ENOUGH_DATA") if perf else "NOT_ENOUGH_DATA",
        overall_score=perf.get("overall_score", 0.0) if perf else 0.0,
        tasks=[TaskAssignmentResponse(**t) for t in tasks],
    )

