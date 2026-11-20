from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class TaskAssignmentStatus(str, Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class PerformanceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    NOT_ENOUGH_DATA = "NOT_ENOUGH_DATA"


class TaskAssignmentModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
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
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: TaskAssignmentStatus = TaskAssignmentStatus.ASSIGNED
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
    trello_sync_status: str = "synced"  # synced, pending_retry, failed
    last_sync_error: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


class TaskAssignmentHistoryModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    assignment_id: str
    action: str  # assigned, due_date_updated, started, completed, cancelled, trello_sync_retry
    actor_id: str
    actor_role: str
    old_due_date: Optional[datetime] = None
    new_due_date: Optional[datetime] = None
    old_estimated_duration_minutes: Optional[int] = None
    new_estimated_duration_minutes: Optional[int] = None
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    reason: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


class EmployeePerformanceModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    employee_id: str
    employee_name: Optional[str] = None
    level: PerformanceLevel = PerformanceLevel.NOT_ENOUGH_DATA
    overall_score: float = 0.0
    on_time_rate: float = 0.0
    consistency_score: float = 0.0
    completion_rate: float = 0.0
    reliability_score: float = 0.0
    completed_tasks_count: int = 0
    total_assigned_tasks_count: int = 0
    in_progress_tasks_count: int = 0
    overdue_tasks_count: int = 0
    avg_estimated_minutes: float = 0.0
    avg_actual_minutes: float = 0.0
    rolling_days: int = 90
    reason: Optional[str] = None
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


class EmployeeLevelHistoryModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    employee_id: str
    old_level: Optional[str] = None
    new_level: str
    score: float
    reason: Optional[str] = None
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }


class ReminderLogModel(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    assignment_id: str
    trello_card_id: str
    employee_id: str
    due_date: datetime
    due_date_version: int = 1
    email_sent: bool = False
    email_sent_at: Optional[datetime] = None
    email_error: Optional[str] = None
    trello_comment_sent: bool = False
    trello_comment_sent_at: Optional[datetime] = None
    trello_comment_error: Optional[str] = None
    generated_comment: Optional[str] = None
    attempt_count: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
    }

