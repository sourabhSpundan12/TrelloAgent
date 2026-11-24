from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EmployeeCandidateEvaluation(BaseModel):
    employee_id: str
    employee_name: str
    employee_email: Optional[str] = None
    role: str = "MEMBER"
    
    # Workload & Capacity
    current_workload_score: str = "OPTIMAL"  # "OPTIMAL", "MODERATE", "HEAVY", "OVERLOADED"
    assigned_tasks_count: int = 0
    in_progress_count: int = 0
    pending_count: int = 0
    overdue_count: int = 0
    available_capacity_hours: float = 0.0
    has_sufficient_capacity: bool = True
    
    # Historical Performance
    completed_tasks_count: int = 0
    on_time_completion_rate: float = 0.0
    avg_actual_duration_minutes: float = 0.0
    avg_estimated_duration_minutes: float = 0.0
    time_variance_minutes: float = 0.0
    has_sufficient_history: bool = True
    performance_level: str = "NOT_ENOUGH_DATA"
    
    # Task Suitability
    similar_tasks_count: int = 0
    similar_task_experience: str = "None"
    estimated_task_completion_feasible: bool = True
    suitability_score: float = 0.0
    recommendation_reason: str = ""


class EmployeeRecommendationResult(BaseModel):
    task_name: Optional[str] = None
    task_requirements: Optional[str] = None
    due_date: Optional[str] = None
    target_employee_query: Optional[str] = None
    
    recommended_employee: Optional[EmployeeCandidateEvaluation] = None
    alternative_employees: List[EmployeeCandidateEvaluation] = Field(default_factory=list)
    has_sufficient_capacity_overall: bool = True
    no_capacity_reason: Optional[str] = None
    explanation: str = ""

