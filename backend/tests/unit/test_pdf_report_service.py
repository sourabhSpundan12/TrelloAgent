import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.pdf_report_service import PDFReportService, SimplePDFBuilder


def test_simple_pdf_builder_creates_valid_bytes():
    builder = SimplePDFBuilder(title="Test PDF")
    builder.draw_header_banner(title="Test Report", subtitle="Subtitle", badge_text="UNIT TEST")
    builder.draw_section_heading("Section 1")
    builder.draw_metric_cards([
        {"label": "Metric 1", "value": "42", "sub": "Units"},
        {"label": "Metric 2", "value": "99.5%", "sub": "Percent"},
    ])
    builder.draw_feedback_box(
        strengths=["Great accuracy", "Good velocity"],
        focus_areas=["Improve documentation"],
        explicit_hours_statement="This is your estimated time: 10 hrs and actual time: 12 hrs.",
    )
    pdf = builder.draw_footer_and_finish()
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf
    assert len(pdf) > 1000


@pytest.mark.asyncio
async def test_generate_board_weekly_report_mock():
    mock_db = MagicMock()
    mock_cursor = MagicMock()

    async def empty_aiter():
        if False:
            yield {}

    mock_cursor.__aiter__ = lambda self: empty_aiter()
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_db.__getitem__.return_value.find.return_value = mock_cursor
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=None)

    pdf_bytes, summary = await PDFReportService.generate_board_weekly_report(mock_db, board_id="test_b1")
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert "cards_done" in summary
    assert "total_estimated_hours" in summary
    assert "total_actual_hours" in summary
    assert "explicit_hours_statement" in summary
    assert "Board Weekly Summary" in summary["explicit_hours_statement"]


@pytest.mark.asyncio
async def test_generate_employee_weekly_report_mock():
    mock_db = MagicMock()
    mock_cursor = MagicMock()

    mock_tasks = [
        {
            "task_id": "tsk-1",
            "task_title": "Implement Login API",
            "status": "COMPLETED",
            "estimated_duration_minutes": 180,
            "actual_duration_minutes": 150,
        },
        {
            "task_id": "tsk-2",
            "task_title": "Database Optimization",
            "status": "IN_PROGRESS",
            "estimated_duration_minutes": 120,
            "actual_duration_minutes": 60,
        },
    ]

    mock_cursor.to_list = AsyncMock(return_value=mock_tasks)
    mock_db.__getitem__.return_value.find.return_value = mock_cursor
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value={
        "full_name": "Sourabh Mishra",
        "email": "sourabh@example.com",
        "role": "Senior Engineer",
        "department": "Backend",
    })

    pdf_bytes, summary = await PDFReportService.generate_employee_weekly_report(
        mock_db,
        employee_id="usr-123",
        employee_name="Sourabh Mishra",
        board_id="board_1",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert summary["cards_done"] == 1
    assert summary["total_estimated_hours"] == 5.0  # (180 + 120) / 60
    assert summary["total_actual_hours"] == 2.5     # 150 / 60
    assert "This is your estimated time to complete the task in entire week: 5.0 hours and actual time you have taken to complete the task on entire week: 2.5 hours." in summary["explicit_hours_statement"]
    # Check 4 sections metrics in summary
    assert "total_assigned" in summary
    assert "on_time_rate" in summary
    assert "occupancy_percentage" in summary
    assert "available_hours" in summary


@pytest.mark.asyncio
async def test_generate_employee_weekly_report_with_date_range():
    mock_db = MagicMock()
    mock_cursor = MagicMock()

    mock_tasks = [
        {
            "task_id": "tsk-101",
            "task_title": "Implement Microservice Hook",
            "status": "COMPLETED",
            "created_at": "2026-11-15T09:00:00Z",
            "completed_at": "2026-11-18T17:00:00Z",
            "due_date": "2026-11-19T18:00:00Z",
            "estimated_duration_minutes": 240,
            "actual_duration_minutes": 210,
        },
    ]

    mock_cursor.to_list = AsyncMock(return_value=mock_tasks)
    mock_db.__getitem__.return_value.find.return_value = mock_cursor
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value={
        "full_name": "Sourabh Mishra",
        "email": "sourabh@example.com",
        "role": "Lead Architect",
        "department": "Platform",
    })

    pdf_bytes, summary = await PDFReportService.generate_employee_weekly_report(
        mock_db,
        employee_id="emp_001",
        employee_name="Sourabh Mishra",
        from_date="2026-11-15",
        to_date="2026-11-21",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert summary["cards_done"] == 1
    assert summary["total_estimated_hours"] == 4.0
    assert summary["total_actual_hours"] == 3.5
    assert summary["on_time_rate"] == 100.0
    assert summary["late_completed_tasks"] == 0
    assert summary["task_completion_rate"] == 100.0
    assert "2026" in summary["week_range"]


@pytest.mark.asyncio
async def test_completed_tasks_show_done_list_and_proper_columns():
    mock_db = MagicMock()
    mock_cursor = MagicMock()

    mock_tasks = [
        {
            "task_id": "card-1",
            "task_title": "TrelloAgent",
            "status": "COMPLETED",
            "list_name": "To Do",  # Stale "To Do" in DB for a completed card
            "created_at": "2026-11-19T09:00:00Z",
            "completed_at": "2026-11-20T10:00:00Z",
            "due_date": "2026-11-20T09:00:00Z",
            "estimated_duration_minutes": 120,
            "actual_duration_minutes": 180,
        },
        {
            "task_id": "card-2",
            "task_title": "database",
            "status": "PENDING",
            "list_name": "To Do",
            "created_at": "2026-11-17T09:00:00Z",
            "due_date": None,  # Missing due date should format as '-' not '?'
            "estimated_duration_minutes": 60,
        },
    ]

    mock_cursor.to_list = AsyncMock(return_value=mock_tasks)
    mock_db.__getitem__.return_value.find.return_value = mock_cursor
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value={
        "full_name": "Shilpi",
        "email": "shilpi@example.com",
        "role": "Software Engineer",
        "department": "Engineering",
    })

    pdf_bytes, summary = await PDFReportService.generate_employee_weekly_report(
        mock_db,
        employee_id="emp_shilpi",
        employee_name="Shilpi",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    # Check that 'Done' appears in PDF stream for the completed task
    assert b"(Done)" in pdf_bytes
    # Check that headers are properly separated
    assert b"(ASSIGNED)" in pdf_bytes
    assert b"(DUE DATE)" in pdf_bytes
    assert b"(OVERDUE DURATION)" in pdf_bytes
    # Check that unencoded '?' is not generated for empty dates
    assert b"(?)" not in pdf_bytes


@pytest.mark.asyncio
async def test_consolidated_report_refinements_5d_9h_and_pm_feedback():
    mock_db = MagicMock()
    mock_cursor = MagicMock()

    mock_tasks = [
        {
            "task_id": "c-100",
            "task_title": "Implement Webhook Engine",
            "status": "COMPLETED",
            "created_at": "2026-11-16T09:00:00Z",
            "completed_at": "2026-11-20T17:00:00Z",
            "due_date": "2026-11-20T18:00:00Z",
            "estimated_duration_minutes": 180,
            "actual_duration_minutes": 150,
        },
        {
            "task_id": "c-101",
            "task_title": "Fix Auth Token Expiration",
            "status": "IN_PROGRESS",
            "created_at": "2026-11-17T09:00:00Z",
            "due_date": "2026-11-22T18:00:00Z",
            "estimated_duration_minutes": 240,
            "actual_duration_minutes": 120,
        },
    ]

    mock_cursor.to_list = AsyncMock(return_value=mock_tasks)
    mock_db.__getitem__.return_value.find.return_value = mock_cursor
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value={
        "full_name": "Shilpi",
        "email": "shilpi@example.com",
        "role": "Full Stack Engineer",
        "department": "Core Platform",
    })

    # Test standard weekly window (5 working days)
    pdf_bytes, summary = await PDFReportService.generate_employee_weekly_report(
        mock_db,
        employee_id="emp_shilpi",
        employee_name="Shilpi",
        from_date="2026-11-16",
        to_date="2026-11-22",
    )

    # 1. Occupancy: 5 working days * 9 hours/day = 45.0 hrs
    assert summary["total_available_hours"] == 45.0
    assert summary["total_estimated_hours"] == 7.0  # (180 + 240) / 60
    assert summary["total_actual_hours"] == 2.5     # 150 / 60

    # 2. Section 2 cards: Separate Estimated Time and Actual Time, No Avg Time / Task
    assert b"(ESTIMATED TIME)" in pdf_bytes
    assert b"(ACTUAL TIME)" in pdf_bytes
    assert b"(AVG TIME / TASK)" not in pdf_bytes

    # 3. Section 3 cards: Total Capacity 45 hrs
    assert b"(TOTAL CAPACITY)" in pdf_bytes
    assert b"(45.0 hrs)" in pdf_bytes

    # 4. Section 4: PM Feedback, no robotic brackets
    assert b"(PROJECT MANAGER WEEKLY ASSESSMENT & FEEDBACK)" in pdf_bytes
    assert b"(Project Manager)" in pdf_bytes
    assert b"[+]" not in pdf_bytes
    assert b"[!]" not in pdf_bytes
    assert b"[>]" not in pdf_bytes




