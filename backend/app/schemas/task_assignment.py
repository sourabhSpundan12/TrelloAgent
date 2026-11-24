from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from app.models.task_assignment import TaskAssignmentStatus, PerformanceLevel


class TaskAssignmentCreateRequest(BaseModel):
    employee_id: str
    board_id: str
    trello_card_id: str
    task_title: str
    task_description: Optional[str] = None
    due_date: Optional[datetime] = None
    board_name: Optional[str] = None
    trello_card_url: Optional[str] = None


class TaskAssignmentDueDateUpdateRequest(BaseModel):
    due_date: datetime
    reason: Optional[str] = None


class TaskAssignmentResponse(BaseModel):
    id: str
    employee_id: str
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None
    project_manager_id: str
    project_manager_name: Optional[str] = None
    board_id: str
    board_name: Optional[str] = None
    trello_card_id: str
    trello_card_url: Optional[str] = None
    task_title: str
    task_description: Optional[str] = None
    assigned_at: datetime
    status: str
    due_date: Optional[datetime] = None
    due_date_set_at: Optional[datetime] = None
    due_date_set_by: Optional[str] = None
    due_date_set_by_role: Optional[str] = None
    due_date_version: int = 1
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_duration_minutes: Optional[int] = None
    actual_duration_minutes: Optional[int] = None
    time_variance_minutes: Optional[int] = None
    time_remaining_minutes: Optional[int] = None
    is_overdue: bool = False
    trello_sync_status: str = "synced"
    last_sync_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class TaskAssignmentHistoryResponse(BaseModel):
    id: str
    assignment_id: str
    action: str
    actor_id: str
    actor_role: str
    old_due_date: Optional[datetime] = None
    new_due_date: Optional[datetime] = None
    old_estimated_duration_minutes: Optional[int] = None
    new_estimated_duration_minutes: Optional[int] = None
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    reason: Optional[str] = None
    timestamp: datetime


class EmployeePerformanceResponse(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    level: str
    overall_score: float
    on_time_rate: float
    consistency_score: float
    completion_rate: float
    reliability_score: float
    completed_tasks_count: int
    total_assigned_tasks_count: int
    in_progress_tasks_count: int
    overdue_tasks_count: int
    avg_estimated_minutes: float
    avg_actual_minutes: float
    rolling_days: int = 90
    reason: Optional[str] = None
    calculated_at: datetime


class EmployeeLevelHistoryResponse(BaseModel):
    id: str
    employee_id: str
    old_level: Optional[str] = None
    new_level: str
    score: float
    reason: Optional[str] = None
    calculated_at: datetime


class EmployeeTaskReportSummary(BaseModel):
    employee_id: str
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None
    role: Optional[str] = "MEMBER"
    assigned_count: int = 0
    in_progress_count: int = 0
    completed_count: int = 0
    overdue_count: int = 0
    on_time_completion_rate: float = 0.0
    avg_estimated_duration_minutes: float = 0.0
    avg_actual_duration_minutes: float = 0.0
    performance_level: str = "NOT_ENOUGH_DATA"
    overall_score: float = 0.0
    tasks: List[TaskAssignmentResponse] = []

