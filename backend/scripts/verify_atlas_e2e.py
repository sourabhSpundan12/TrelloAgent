"""
End-to-End Verification Script for MongoDB Atlas Migration.
Tests:
1. Health & Readiness checks with Atlas.
2. Authentication against Atlas user collection (JWT + Refresh Tokens).
3. AI Interpretation & Task Draft Generation.
4. Pending Actions Persistence & Retrieval on Atlas.
5. Action ID Consistency Check.
6. Approval Draft Editing on Atlas.
7. Approval Draft Cancellation on Atlas.
8. Second Action Creation & Confirmation with MCP Trello Execution.
"""

import asyncio
import os
import sys
from pathlib import Path

backend_path = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(backend_path))

import httpx
from app.core.config import settings
from app.database.mongodb import MongoDBManager, mask_mongo_uri
from app.main import app


async def run_e2e_verification():
    print("=" * 70)
    print("AGENTIC TASK MANAGER - MONGODB ATLAS END-TO-END VERIFICATION")
    print("=" * 70)
    print(f"Target Database URI: {mask_mongo_uri(settings.EFFECTIVE_MONGODB_URI)}")
    print(f"Target Database    : {settings.MONGODB_DATABASE}")

    # Step 1: Initialize Database Connection
    print("\n[Step 1] Initializing MongoDB connection...")
    connected = await MongoDBManager.connect()
    if not connected:
        print("[FAIL] Could not connect to MongoDB Atlas.")
        return False
    print("  [PASS] MongoDB Atlas connected successfully.")

    db = MongoDBManager.get_db()
    health_status = await MongoDBManager.get_health_status()
    print(f"  Health status: {health_status}")

    # Use AsyncClient with ASGI transport for in-process end-to-end testing
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Step 2: Health & Readiness Endpoints
        print("\n[Step 2] Testing /health and /health/ready endpoints...")
        resp = await client.get("/health")
        assert resp.status_code == 200, f"/health returned {resp.status_code}"
        health_data = resp.json()
        print(f"  /health: status={health_data['status']}, database={health_data['database']}")
        assert health_data["status"] == "healthy"
        assert health_data["database"] == "connected"

        resp = await client.get("/health/ready")
        assert resp.status_code == 200, f"/health/ready returned {resp.status_code}"
        ready_data = resp.json()
        print(f"  /health/ready: status={ready_data['status']}, database={ready_data['database']}")
        assert ready_data["status"] == "ready"
        print("  [PASS] Health endpoints verified with Atlas.")

        # Step 3: Authentication against Atlas
        print("\n[Step 3] Testing Authentication against Atlas...")
        login_payload = {
            "email": "admin@example.com",
            "password": "AdminSecurePassword123!",
        }
        resp = await client.post("/api/v1/auth/login", json=login_payload)
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        auth_data = resp.json()
        access_token = auth_data["access_token"]
        refresh_token = auth_data["refresh_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        me_resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert me_resp.status_code == 200, f"/me failed: {me_resp.text}"
        user_info = me_resp.json()
        print(f"  [PASS] Login successful! User: {user_info['email']}, Role: {user_info['role']}")
        print(f"  Access token generated (first 25 chars): {access_token[:25]}...")

        # Verify refresh token in Atlas
        token_count = await db["refresh_tokens"].count_documents({"user_id": user_info["id"]})
        print(f"  Tokens in Atlas for user: {token_count}")
        assert token_count > 0, "No refresh tokens found in Atlas"

        # Step 4: AI Interpretation & Approval Creation
        print("\n[Step 4] Testing AI Task Interpretation & Approval Creation on Atlas...")
        interpret_payload = {
            "command": "Create a task to monitor MongoDB Atlas cluster performance and alerts.",
        }
        resp = await client.post("/api/v1/ai/interpret", json=interpret_payload, headers=auth_headers)
        assert resp.status_code == 200, f"AI interpret failed: {resp.text}"
        interpret_data = resp.json()
        preview = interpret_data.get("execution_preview")
        assert preview is not None, "Execution preview must be present for task creation mutation"
        action_id_1 = preview.get("action_id")
        print(f"  AI Intent: {interpret_data.get('intent')}")
        print(f"  Selected Tool: {interpret_data.get('selected_tool_name')}")
        print(f"  Approval Required: {interpret_data.get('approval_required')}")
        print(f"  Generated Action ID: {action_id_1}")
        assert action_id_1 is not None, "Action ID was not generated in execution_preview"

        # Step 5: Verify Pending Action Persistence in Atlas
        print("\n[Step 5] Verifying Pending Action in MongoDB Atlas pending_actions collection...")
        doc_1 = await db["pending_actions"].find_one({"action_id": action_id_1})
        assert doc_1 is not None, f"Document for {action_id_1} not found in Atlas!"
        print(f"  Persisted Action ID : {doc_1['action_id']}")
        print(f"  Action Status       : {doc_1['status']}")
        print(f"  Target Tool         : {doc_1['tool_name']}")
        print(f"  Expires At          : {doc_1['expires_at']}")
        print(f"  Payload Hash        : {doc_1['payload_hash']}")
        assert doc_1["action_id"] == action_id_1
        assert doc_1["status"] == "PENDING"
        print("  [PASS] Pending action persistence and action_id consistency verified on Atlas.")

        # Step 6: Test Editing the Approval Draft
        print("\n[Step 6] Testing Approval Draft Editing on Atlas...")
        edit_payload = {
            "title": "Monitor MongoDB Atlas Cluster & Enable Health Alerts",
            "description": "Configured Atlas monitoring with proactive notification webhooks.",
            "priority": "HIGH",
            "due_date": "2026-11-20T18:00:00Z",
        }
        resp = await client.patch(f"/api/v1/approvals/{action_id_1}", json=edit_payload, headers=auth_headers)
        assert resp.status_code == 200, f"Approval update failed: {resp.text}"
        updated_data = resp.json()
        print(f"  Updated Title: {updated_data['draft']['title']}")
        print(f"  New Payload Hash: {updated_data['payload_hash']}")
        assert updated_data["draft"]["title"] == edit_payload["title"]

        # Verify update in Atlas directly
        doc_1_updated = await db["pending_actions"].find_one({"action_id": action_id_1})
        assert doc_1_updated["draft"]["title"] == edit_payload["title"]
        print("  [PASS] Approval draft editing successfully persisted to Atlas.")

        # Step 7: Test Cancelling the Approval Draft
        print("\n[Step 7] Testing Approval Cancellation on Atlas...")
        resp = await client.post(
            f"/api/v1/approvals/{action_id_1}/cancel",
            json={"reason": "Testing cancellation flow on Atlas"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Cancel failed: {resp.text}"
        cancelled_data = resp.json()
        print(f"  Cancelled Action Status: {cancelled_data['status']}")
        assert cancelled_data["status"] == "REJECTED"

        # Verify cancellation in Atlas directly
        doc_1_cancelled = await db["pending_actions"].find_one({"action_id": action_id_1})
        assert doc_1_cancelled["status"] == "REJECTED"
        print("  [PASS] Approval cancellation successfully persisted to Atlas as REJECTED.")

        # Step 8: Test Confirmation with Live MCP Execution
        print("\n[Step 8] Testing Task Creation and Confirmation Flow on Atlas...")
        confirm_interpret_payload = {
            "command": "Create a task for automated Atlas backup snapshot validation.",
        }
        resp = await client.post("/api/v1/ai/interpret", json=confirm_interpret_payload, headers=auth_headers)
        assert resp.status_code == 200, f"Second AI interpret failed: {resp.text}"
        interpret_data_2 = resp.json()
        preview_2 = interpret_data_2.get("execution_preview")
        assert preview_2 is not None, "Execution preview missing on second interpret"
        action_id_2 = preview_2["action_id"]
        print(f"  Generated Action ID for Confirmation: {action_id_2}")

        # Confirm the action
        print(f"  Confirming action {action_id_2}...")
        resp = await client.post(f"/api/v1/approvals/{action_id_2}/confirm", headers=auth_headers)
        assert resp.status_code == 200, f"Confirm failed: {resp.text}"
        confirm_data = resp.json()
        print(f"  Confirmation Status : {confirm_data['status']}")
        print(f"  Execution Result    : {confirm_data.get('execution_result')}")
        assert confirm_data["status"] == "EXECUTED"

        # Verify execution in Atlas directly
        doc_2_executed = await db["pending_actions"].find_one({"action_id": action_id_2})
        assert doc_2_executed is not None
        assert doc_2_executed["status"] == "EXECUTED"
        assert doc_2_executed["action_id"] == action_id_2
        print(f"  Atlas Document Status: {doc_2_executed['status']}")
        print(f"  Action ID Match      : {doc_2_executed['action_id'] == action_id_2}")
        print("  [PASS] Action ID remained 100% consistent from interpretation to execution.")
        print("  [PASS] Live confirmation & MCP execution completed successfully!")

    await MongoDBManager.disconnect()
    print("\n" + "=" * 70)
    print("ALL ATLAS END-TO-END VERIFICATION STEPS PASSED SUCCESSFULLY!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = asyncio.run(run_e2e_verification())
    sys.exit(0 if success else 1)
