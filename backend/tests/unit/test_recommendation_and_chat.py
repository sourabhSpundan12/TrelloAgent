import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from app.schemas.recommendation import EmployeeRecommendationResult, EmployeeCandidateEvaluation
from app.services.recommendation_service import EmployeeRecommendationService
from app.models.task_assignment import TaskAssignmentStatus


@pytest.mark.asyncio
async def test_recommend_employee_availability_and_suitability():
    """Test availability analysis, workload scoring, and recommending employee with capacity."""
    mock_db = MagicMock()

    # Two employees: Rahul and Sneha
    mock_users = [
        {"_id": "u1", "full_name": "Rahul Sharma", "email": "rahul@example.com", "role": "MEMBER", "is_active": True},
        {"_id": "u2", "full_name": "Sneha Patel", "email": "sneha@example.com", "role": "MEMBER", "is_active": True},
    ]

    mock_db["users"].find.return_value.to_list = AsyncMock(return_value=mock_users)
    mock_perf = {
        "on_time_rate": 95.0,
        "average_actual_duration_minutes": 110.0,
        "average_estimated_duration_minutes": 120.0,
        "level": "HIGH",
    }

    # Rahul has 1 completed backend task and 0 active tasks (Optimal workload)
    # Sneha has 4 active in-progress tasks (Heavy/Overloaded)
    now = datetime.now(timezone.utc)
    rahul_tasks = [
        {
            "id": "t1",
            "task_title": "Build Authentication API",
            "task_description": "Implement JWT backend login",
            "status": TaskAssignmentStatus.COMPLETED.value,
            "due_date": now - timedelta(days=2),
            "completed_at": now - timedelta(days=3),
            "estimated_duration_minutes": 120,
            "actual_duration_minutes": 110,
        }
    ]
    sneha_tasks = [
        {
            "id": f"s{i}",
            "task_title": f"Active Task {i}",
            "status": TaskAssignmentStatus.IN_PROGRESS.value,
            "due_date": now + timedelta(days=1),
        }
        for i in range(5)
    ]

    async def mock_get_employee_tasks(db, employee_id, board_id=None):
        if employee_id == "u1":
            return rahul_tasks
        return sneha_tasks

    with patch("app.services.task_assignment_service.TaskAssignmentService.reconcile_board_cards", AsyncMock()), \
         patch("app.services.task_assignment_service.TaskAssignmentService.get_employee_tasks", side_effect=mock_get_employee_tasks), \
         patch("app.services.performance_service.PerformanceCalculationService.calculate_employee_performance", AsyncMock(return_value=mock_perf)), \
         patch("app.mcp_server.trello_tools.trello_list_board_members", AsyncMock(return_value={"members": []})):

        res: EmployeeRecommendationResult = await EmployeeRecommendationService.recommend_employee_for_task(
            db=mock_db,
            task_name="Authentication API enhancement",
            task_requirements="Build secure token refresh and login endpoints",
        )

        assert res.has_sufficient_capacity_overall is True
        assert res.recommended_employee is not None
        assert res.recommended_employee.employee_name == "Rahul Sharma"
        assert res.recommended_employee.current_workload_score == "OPTIMAL"
        assert res.recommended_employee.has_sufficient_capacity is True
        assert "Authentication" in res.recommended_employee.similar_task_experience or "1 completed task" in res.recommended_employee.similar_task_experience
        assert len(res.alternative_employees) >= 1
        assert res.alternative_employees[0].employee_name == "Sneha Patel"
        assert res.alternative_employees[0].has_sufficient_capacity is False or res.alternative_employees[0].current_workload_score == "OVERLOADED"


@pytest.mark.asyncio
async def test_recommend_employee_specific_query_evaluation():
    """Test queries like 'Rahul has fewer tasks. Can he handle this task?'"""
    mock_db = MagicMock()
    mock_users = [
        {"_id": "u1", "full_name": "Rahul Sharma", "email": "rahul@example.com", "role": "MEMBER", "is_active": True},
    ]
    mock_db["users"].find.return_value.to_list = AsyncMock(return_value=mock_users)

    rahul_tasks = [
        {
            "id": "t1",
            "task_title": "Database Schema Setup",
            "status": TaskAssignmentStatus.COMPLETED.value,
            "due_date": datetime.now(timezone.utc) - timedelta(days=1),
            "completed_at": datetime.now(timezone.utc) - timedelta(days=2),
        }
    ]

    mock_perf = {
        "on_time_rate": 90.0,
        "average_actual_duration_minutes": 60.0,
        "average_estimated_duration_minutes": 60.0,
        "level": "HIGH",
    }

    with patch("app.services.task_assignment_service.TaskAssignmentService.reconcile_board_cards", AsyncMock()), \
         patch("app.services.task_assignment_service.TaskAssignmentService.get_employee_tasks", AsyncMock(return_value=rahul_tasks)), \
         patch("app.services.performance_service.PerformanceCalculationService.calculate_employee_performance", AsyncMock(return_value=mock_perf)), \
         patch("app.mcp_server.trello_tools.trello_list_board_members", AsyncMock(return_value={"members": []})):

        res = await EmployeeRecommendationService.recommend_employee_for_task(
            db=mock_db,
            task_name="Postgres Migration",
            target_employee_query="Rahul",
        )

        assert res.recommended_employee is not None
        assert res.recommended_employee.employee_name == "Rahul Sharma"
        assert "can handle this task" in res.explanation.lower() or "optimal" in res.explanation.lower()


@pytest.mark.asyncio
async def test_recommend_employee_no_capacity_scenario():
    """Test scenario where all employees are overloaded and system informs manager instead of forcing."""
    mock_db = MagicMock()
    mock_users = [
        {"_id": "u1", "full_name": "Employee Overloaded", "email": "emp@example.com", "role": "MEMBER", "is_active": True},
    ]
    mock_db["users"].find.return_value.to_list = AsyncMock(return_value=mock_users)

    # 6 in-progress tasks
    overloaded_tasks = [
        {"id": f"t{i}", "task_title": f"T{i}", "status": TaskAssignmentStatus.IN_PROGRESS.value}
        for i in range(6)
    ]

    mock_perf = {"on_time_rate": 50.0, "level": "LOW"}

    with patch("app.services.task_assignment_service.TaskAssignmentService.reconcile_board_cards", AsyncMock()), \
         patch("app.services.task_assignment_service.TaskAssignmentService.get_employee_tasks", AsyncMock(return_value=overloaded_tasks)), \
         patch("app.services.performance_service.PerformanceCalculationService.calculate_employee_performance", AsyncMock(return_value=mock_perf)), \
         patch("app.mcp_server.trello_tools.trello_list_board_members", AsyncMock(return_value={"members": []})):

        res = await EmployeeRecommendationService.recommend_employee_for_task(
            db=mock_db,
            task_name="Critical Hotfix",
        )

        assert res.has_sufficient_capacity_overall is False
        assert res.recommended_employee is None
        assert res.no_capacity_reason is not None
        assert "capacity" in res.no_capacity_reason.lower()


@pytest.mark.asyncio
async def test_multilingual_recommendation_intent_detection():
    """Test intent understanding for English, Hindi, and Hinglish recommendation requests."""
    from app.ai.service import AIService
    ai = AIService()

    # 1. English
    out_en = ai._fallback_deterministic_interpreter("Who should I assign this task to?", [])
    assert out_en.intent == "recommend_employee"
    assert out_en.suggested_tool_id == "employee_recommend_assignment"

    # 2. Free employee inquiry
    out_free = ai._fallback_deterministic_interpreter("Which employee is currently free?", [])
    assert out_free.intent == "recommend_employee"

    # 3. Hindi/Hinglish
    out_hi = ai._fallback_deterministic_interpreter("Mujhe ye task kis employee ko dena chahiye?", [])
    assert out_hi.intent == "recommend_employee"

    # 4. Target specific employee
    out_target = ai._fallback_deterministic_interpreter("Rahul has fewer tasks. Can he handle this task?", [])
    assert out_target.intent == "recommend_employee"
    assert out_target.parameters.get("target_employee") == "Rahul"


@pytest.mark.asyncio
async def test_chat_session_rename():
    """Test renaming a chat session."""
    from app.chat.repository import ChatRepository

    mock_db = MagicMock()
    mock_sessions = MagicMock()
    mock_sessions.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_db.__getitem__.side_effect = lambda key: mock_sessions if key == "chat_sessions" else MagicMock()

    repo = ChatRepository(mock_db)
    success = await repo.rename_session(user_id="u1", conversation_id="ses_1", title="Feature Discussion")

    assert success is True
    mock_sessions.update_one.assert_called_once()
    called_filter = mock_sessions.update_one.call_args[0][0]
    called_update = mock_sessions.update_one.call_args[0][1]
    assert called_filter == {"id": "ses_1", "user_id": "u1"}
    assert called_update["$set"]["title"] == "Feature Discussion"
