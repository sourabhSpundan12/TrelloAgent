from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.schemas.user import UserResponse
from app.schemas.task_assignment import (
    TaskAssignmentCreateRequest,
    TaskAssignmentDueDateUpdateRequest,
    TaskAssignmentResponse,
    TaskAssignmentHistoryResponse,
)
from app.services.task_assignment_service import TaskAssignmentService

router = APIRouter()


@router.post(
    "",
    response_model=TaskAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new employee task assignment",
    description="Project Manager assigns a Trello task card to an employee with due date and tracking metadata.",
)
async def create_task_assignment(
    payload: TaskAssignmentCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    # Role check: only managers/admins/HR can create assignments
    user_role = str(current_user.role).upper()
    if user_role not in ("ADMIN", "MANAGER", "HR"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Project Managers or Administrators can create task assignments."
        )

    assignment = await TaskAssignmentService.create_assignment(
        db=db,
        employee_id=payload.employee_id,
        project_manager_id=current_user.id,
        board_id=payload.board_id,
        trello_card_id=payload.trello_card_id,
        task_title=payload.task_title,
        task_description=payload.task_description,
        due_date=payload.due_date,
        board_name=payload.board_name,
        trello_card_url=payload.trello_card_url,
        project_manager_name=current_user.full_name,
    )
    return assignment


@router.get(
    "/employee/{employee_id}",
    response_model=List[TaskAssignmentResponse],
    summary="Get all task assignments for a specific employee",
    description="Retrieve task assignments with optional filters for board, status, and date range.",
)
async def get_employee_assignments(
    employee_id: str,
    board_id: Optional[str] = Query(None, description="Filter by board ID"),
    status: Optional[str] = Query(None, description="Filter by status (assigned, in_progress, completed, overdue, cancelled)"),
    from_date: Optional[datetime] = Query(None, description="From date filter"),
    to_date: Optional[datetime] = Query(None, description="To date filter"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    # Reconcile board cards so fresh Trello assignments are synchronized
    await TaskAssignmentService.reconcile_board_cards(db, board_id=board_id)

    tasks = await TaskAssignmentService.get_employee_tasks(
        db=db,
        employee_id=employee_id,
        board_id=board_id,
        status_filter=status,
        from_date=from_date,
        to_date=to_date,
    )
    return tasks


@router.get(
    "/{assignment_id}",
    response_model=TaskAssignmentResponse,
    summary="Get single task assignment details",
)
async def get_assignment_detail(
    assignment_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    try:
        assignment = await db["task_assignments"].find_one({"_id": ObjectId(assignment_id)})
    except Exception:
        assignment = await db["task_assignments"].find_one({"id": assignment_id})

    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task assignment not found.")

    assignment["id"] = str(assignment["_id"])
    return assignment


@router.patch(
    "/{assignment_id}/due-date",
    response_model=TaskAssignmentResponse,
    summary="Update task assignment due date",
    description="Allows PM or assigned employee to set or update due date. Recalculates estimated duration and syncs with Trello.",
)
async def update_task_due_date(
    assignment_id: str,
    payload: TaskAssignmentDueDateUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    user_role = str(current_user.role).upper()
    assignment = await TaskAssignmentService.update_due_date(
        db=db,
        assignment_id=assignment_id,
        actor_id=current_user.id,
        actor_role=user_role,
        new_due_date=payload.due_date,
        reason=payload.reason,
    )
    return assignment


@router.post(
    "/{assignment_id}/start",
    response_model=TaskAssignmentResponse,
    summary="Start task timer and transition status to in_progress",
    description="Records startedAt server timestamp and calculates estimated duration.",
)
async def start_task(
    assignment_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    user_role = str(current_user.role).upper()
    assignment = await TaskAssignmentService.start_task(
        db=db,
        assignment_id=assignment_id,
        actor_id=current_user.id,
        actor_role=user_role,
    )
    return assignment


@router.post(
    "/{assignment_id}/complete",
    response_model=TaskAssignmentResponse,
    summary="Complete task, calculate actual elapsed time and time variance",
    description="Records completedAt, calculates elapsed actualDurationMinutes and timeVarianceMinutes, and recalculates performance.",
)
async def complete_task(
    assignment_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    user_role = str(current_user.role).upper()
    assignment = await TaskAssignmentService.complete_task(
        db=db,
        assignment_id=assignment_id,
        actor_id=current_user.id,
        actor_role=user_role,
    )
    return assignment


@router.get(
    "/{assignment_id}/history",
    response_model=List[TaskAssignmentHistoryResponse],
    summary="Get complete audit history for a task assignment",
)
async def get_assignment_history(
    assignment_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Any:
    cursor = db["task_assignment_history"].find({"assignment_id": str(assignment_id)}).sort("timestamp", -1)
    history = await cursor.to_list(length=100)
    for h in history:
        h["id"] = str(h["_id"])
    return history

