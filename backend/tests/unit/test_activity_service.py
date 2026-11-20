import pytest
from datetime import datetime, timezone
from mongomock_motor import AsyncMongoMockClient
from app.services.activity_service import ActivityService


@pytest.fixture
def mock_db():
    client = AsyncMongoMockClient()
    return client["test_database"]


@pytest.mark.asyncio
async def test_log_activity_saves_to_mongo(mock_db):
    doc = await ActivityService.log_activity(
        db=mock_db,
        event_type="CARD_CREATED",
        title="Created Card 'API Integration'",
        description="Created in list 'To Do'",
        status="EXECUTED",
        user_name="Test Manager",
        user_email="manager@example.com",
        board_id="board_123",
        board_name="Engineering Board",
        metadata={"card_id": "c_999", "list_id": "l_111"},
    )

    assert doc is not None
    assert doc["event_type"] == "CARD_CREATED"
    assert doc["status"] == "EXECUTED"
    assert doc["user_name"] == "Test Manager"

    # Verify MongoDB persistence in activity_logs collection
    saved = await mock_db["activity_logs"].find_one({"action_id": doc["action_id"]})
    assert saved is not None
    assert saved["title"] == "Created Card 'API Integration'"


@pytest.mark.asyncio
async def test_get_combined_activities_merges_sources(mock_db):
    # 1. Insert an explicit activity log
    await ActivityService.log_activity(
        db=mock_db,
        event_type="BOARD_ACTIVATED",
        title="Activated Board 'Main Sprint'",
        description="Board switched to active",
        status="EXECUTED",
        user_name="PM User",
        board_id="board_100",
    )

    # 2. Insert a task assignment history record
    await mock_db["task_assignment_history"].insert_one({
        "action": "ASSIGNED",
        "task_title": "Write Unit Tests",
        "board_id": "board_100",
        "employee_name": "Dev Alice",
        "changed_by": "PM User",
        "notes": "Assigned task to Dev Alice",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # 3. Insert a pending action record
    await mock_db["pending_actions"].insert_one({
        "action_id": "ACT-PREV-TEST1",
        "action_type": "MOVE_CARD",
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc),
        "draft": {
            "title": "Hr-atlas",
            "description": "Moved to Doing",
            "board_id": "board_100",
            "board_name": "Main Sprint",
            "list_name": "Doing",
        },
        "user_email": "pm@example.com",
    })

    activities = await ActivityService.get_combined_activities(
        db=mock_db,
        board_id="board_100",
    )

    assert len(activities) >= 3
    action_types = [a.get("action_type") for a in activities]
    assert "BOARD_ACTIVATED" in action_types
    assert "TASK_ASSIGNED" in action_types
    assert "MOVE_CARD" in action_types

    # Ensure all have standard required fields
    for a in activities:
        assert "id" in a
        assert "title" in a
        assert "status" in a
        assert "created_at" in a
