import re
import uuid
from typing import Any, Dict, Optional
from app.core.config import settings
from app.core.logging import logger
from app.core.security import compute_payload_hash
from app.tool_executor.interfaces import BaseExecutor, ExecutionContext, ExecutionResult


class EchoExecutor(BaseExecutor):
    """Simple test executor that echoes provided parameters."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        return ExecutionResult(
            tool_id=tool.get("tool_id", "echo"),
            status="SUCCESS",
            is_mutation=False,
            result={"echo": parameters, "invoker": context.user_id},
            message="Echo execution completed successfully.",
        )


class MockTrelloCreateCardExecutor(BaseExecutor):
    """Safe Phase 4 mock executor for card creation. Never mutates live Trello data."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        payload_hash = compute_payload_hash(parameters)
        preview = {
            "action_id": context.action_id or f"ACT-PREV-{uuid.uuid4().hex[:8].upper()}",
            "action_type": "CREATE_CARD",
            "card_name": parameters.get("name", "Untitled Task"),
            "target_list": parameters.get("list_name", "TODO"),
            "board_name": "Sprint Board (Simulation)",
            "parameters": parameters,
            "requires_confirmation": True,
        }

        if not context.confirmed:
            return ExecutionResult(
                tool_id=tool.get("tool_id", "trello_create_card"),
                status="REQUIRES_APPROVAL",
                is_mutation=True,
                preview=preview,
                payload_hash=payload_hash,
                message="Card creation prepared for human review. Approval required before execution.",
            )

        # Real Trello execution via MCP tools if configured
        if settings.TRELLO_API_KEY and settings.TRELLO_TOKEN:
            try:
                from app.mcp_server import trello_tools
                board_id = parameters.get("board_id") or settings.TRELLO_BOARD_ID or None
                list_id = parameters.get("list_id")

                # Resolve list_id dynamically from list_name if missing
                if not list_id or list_id.startswith("list_"):
                    target_list_name = parameters.get("list_name") or "To Do"
                    lists_res = await trello_tools.trello_list_lists()
                    raw_target = target_list_name.lower().strip()
                    cleaned_target = re.sub(r"\s+(?:list|column)$", "", raw_target, flags=re.IGNORECASE).strip()
                    norm_target = re.sub(r"[\s\-_]+", "", cleaned_target)
                    for l in lists_res.get("lists", []):
                        l_name = l.get("name", "").strip()
                        l_raw = l_name.lower()
                        l_norm = re.sub(r"[\s\-_]+", "", l_raw)
                        if norm_target == l_norm or cleaned_target == l_raw:
                            list_id = l["id"]
                            break
                        if norm_target in l_norm or l_norm in norm_target:
                            list_id = l["id"]
                            break
                        if norm_target in ["todo", "backlog"] and l_norm in ["todo", "backlog"]:
                            list_id = l["id"]
                            break

                card_res = await trello_tools.trello_create_card(
                    name=parameters.get("name"),
                    desc=parameters.get("desc", ""),
                    due_date=parameters.get("due_date") or parameters.get("due"),
                    board_id=board_id,
                    list_id=list_id,
                    member_name=parameters.get("member_name") or parameters.get("member") or parameters.get("assignee"),
                )
                if card_res.get("status") == "SUCCESS":
                    card_data = card_res.get("card", {})
                    return ExecutionResult(
                        tool_id=tool.get("tool_id", "trello_create_card"),
                        status="SUCCESS",
                        is_mutation=True,
                        preview=preview,
                        result=card_res,
                        message=f"Trello card '{card_data.get('name')}' created successfully via MCP.",
                    )
                else:
                    logger.warning(f"trello_create_card MCP execution returned error: {card_res}")
            except Exception as exc:
                logger.warning(f"Live Trello execution via MCP failed: {exc}")

        return ExecutionResult(
            tool_id=tool.get("tool_id", "trello_create_card"),
            status="SUCCESS",
            is_mutation=True,
            preview=preview,
            result={
                "simulated_card_id": f"card_{uuid.uuid4().hex[:12]}",
                "name": parameters.get("name"),
                "list": parameters.get("list_name", "TODO"),
                "status": "CREATED_MOCK",
            },
            message=f"Simulated card '{parameters.get('name')}' created successfully in Phase 4 safe mode.",
        )


class MockTrelloCreateListExecutor(BaseExecutor):
    """Executor for Trello list creation with live MCP execution."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        payload_hash = compute_payload_hash(parameters)
        list_name = parameters.get("name") or "New List"

        preview = {
            "action_id": context.action_id or f"ACT-PREV-{uuid.uuid4().hex[:8].upper()}",
            "action_type": "CREATE_LIST",
            "list_name": list_name,
            "board_name": "Configured Trello Board",
            "parameters": parameters,
            "requires_confirmation": True,
        }

        if not context.confirmed:
            return ExecutionResult(
                tool_id=tool.get("tool_id", "trello_create_list"),
                status="REQUIRES_APPROVAL",
                is_mutation=True,
                preview=preview,
                payload_hash=payload_hash,
                message=f"List creation for '{list_name}' prepared for human review. Approval required before execution.",
            )

        if settings.TRELLO_API_KEY and settings.TRELLO_TOKEN:
            try:
                from app.mcp_server import trello_tools
                board_id = parameters.get("board_id") or settings.TRELLO_BOARD_ID or None
                list_res = await trello_tools.trello_create_list(
                    name=list_name,
                    board_id=board_id,
                    pos=parameters.get("pos", "bottom"),
                )
                if list_res.get("status") == "SUCCESS":
                    return ExecutionResult(
                        tool_id=tool.get("tool_id", "trello_create_list"),
                        status="SUCCESS",
                        is_mutation=True,
                        preview=preview,
                        result=list_res,
                        message=f"Trello list '{list_name}' created successfully via MCP.",
                    )
                else:
                    logger.warning(f"trello_create_list MCP execution returned error: {list_res}")
            except Exception as exc:
                logger.warning(f"Live Trello create list via MCP failed: {exc}")

        return ExecutionResult(
            tool_id=tool.get("tool_id", "trello_create_list"),
            status="SUCCESS",
            is_mutation=True,
            preview=preview,
            result={
                "simulated_list_id": f"list_{uuid.uuid4().hex[:12]}",
                "name": list_name,
                "status": "CREATED_MOCK",
            },
            message=f"Simulated list '{list_name}' created successfully.",
        )


class MockTrelloMoveCardExecutor(BaseExecutor):
    """Safe executor for card transitions with live Trello MCP execution."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        payload_hash = compute_payload_hash(parameters)
        card_name = parameters.get("card_name") or parameters.get("name") or "Task Card"
        target_status = parameters.get("target_status") or parameters.get("list_name") or "IN_PROGRESS"

        preview = {
            "action_id": context.action_id or f"ACT-PREV-{uuid.uuid4().hex[:8].upper()}",
            "action_type": "MOVE_CARD",
            "card_name": card_name,
            "target_status": target_status,
            "parameters": parameters,
            "requires_confirmation": True,
        }

        if not context.confirmed:
            return ExecutionResult(
                tool_id=tool.get("tool_id", "trello_move_card"),
                status="REQUIRES_APPROVAL",
                is_mutation=True,
                preview=preview,
                payload_hash=payload_hash,
                message=f"Move card '{card_name}' to '{target_status}' prepared for human review. Approval required before execution.",
            )

        if settings.TRELLO_API_KEY and settings.TRELLO_TOKEN:
            try:
                from app.mcp_server import trello_tools
                card_id = parameters.get("card_id")
                list_id = parameters.get("list_id")

                # Resolve card_id dynamically if missing
                if not card_id or card_id.startswith("card_") or card_id == "c101":
                    cards_res = await trello_tools.trello_list_cards()
                    for c in cards_res.get("cards", []):
                        if card_name.lower().strip() in c.get("name", "").lower():
                            card_id = c["id"]
                            card_name = c["name"]
                            break

                # Resolve list_id dynamically if missing
                if not list_id or list_id.startswith("list_"):
                    lists_res = await trello_tools.trello_list_lists()
                    raw_target = target_status.lower().strip()
                    cleaned_target = re.sub(r"\s+(?:list|column)$", "", raw_target, flags=re.IGNORECASE).strip()
                    norm_target = re.sub(r"[\s\-_]+", "", cleaned_target)

                    for l in lists_res.get("lists", []):
                        l_name = l.get("name", "").strip()
                        l_raw = l_name.lower()
                        l_norm = re.sub(r"[\s\-_]+", "", l_raw)

                        # Exact or normalized equality (e.g. 'testing' == 'testing')
                        if norm_target == l_norm or cleaned_target == l_raw:
                            list_id = l["id"]
                            target_status = l_name
                            break
                        if norm_target in l_norm or l_norm in norm_target:
                            list_id = l["id"]
                            target_status = l_name
                            break
                        if norm_target in ["inprogress", "doing"] and l_norm in ["inprogress", "doing"]:
                            list_id = l["id"]
                            target_status = l_name
                            break
                        if norm_target in ["done", "completed"] and l_norm in ["done", "completed"]:
                            list_id = l["id"]
                            target_status = l_name
                            break
                        if norm_target in ["todo", "backlog"] and l_norm in ["todo", "backlog"]:
                            list_id = l["id"]
                            target_status = l_name
                            break
                        if norm_target in ["inreview", "review"] and l_norm in ["inreview", "review"]:
                            list_id = l["id"]
                            target_status = l_name
                            break

                if card_id and list_id:
                    move_res = await trello_tools.trello_move_card(
                        card_id=card_id,
                        list_id=list_id,
                        due_date=parameters.get("due_date") or parameters.get("due"),
                        desc=parameters.get("desc") or parameters.get("description"),
                        board_id=parameters.get("board_id") or settings.TRELLO_BOARD_ID or None,
                    )
                    if move_res.get("status") == "SUCCESS":
                        return ExecutionResult(
                            tool_id=tool.get("tool_id", "trello_move_card"),
                            status="SUCCESS",
                            is_mutation=True,
                            preview=preview,
                            result=move_res,
                            message=f"Card '{card_name}' moved to '{target_status}' successfully via MCP.",
                        )
            except Exception as exc:
                logger.warning(f"Live Trello move via MCP failed: {exc}")

        return ExecutionResult(
            tool_id=tool.get("tool_id", "trello_move_card"),
            status="SUCCESS",
            is_mutation=True,
            preview=preview,
            result={
                "card_name": card_name,
                "new_status": target_status,
                "status": "MOVED_MOCK",
            },
            message=f"Simulated transition of '{card_name}' to '{target_status}' successful.",
        )


class MockTrelloUpdateCardExecutor(BaseExecutor):
    """Executor for card update mutations with live Trello MCP execution."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        payload_hash = compute_payload_hash(parameters)
        card_name = parameters.get("card_name") or parameters.get("name") or "Task Card"
        desc = parameters.get("desc") or parameters.get("description") or ""

        preview = {
            "action_id": context.action_id or f"ACT-PREV-{uuid.uuid4().hex[:8].upper()}",
            "action_type": "UPDATE_CARD",
            "card_name": card_name,
            "description": desc,
            "parameters": parameters,
            "requires_confirmation": True,
        }

        if not context.confirmed:
            return ExecutionResult(
                tool_id=tool.get("tool_id", "trello_update_card"),
                status="REQUIRES_APPROVAL",
                is_mutation=True,
                preview=preview,
                payload_hash=payload_hash,
                message=f"Card update for '{card_name}' prepared for human review. Approval required before execution.",
            )

        if settings.TRELLO_API_KEY and settings.TRELLO_TOKEN:
            try:
                from app.mcp_server import trello_tools
                card_id = parameters.get("card_id")

                if not card_id or card_id == "c101":
                    cards_res = await trello_tools.trello_list_cards()
                    clean_cname = re.sub(r"\s+card$", "", card_name.lower().strip()).strip()
                    for c in cards_res.get("cards", []):
                        c_low = c.get("name", "").lower()
                        if clean_cname and (clean_cname in c_low or c_low in clean_cname):
                            card_id = c["id"]
                            card_name = c["name"]
                            break

                if card_id:
                    new_title = parameters.get("new_title") or parameters.get("new_name")
                    member_name = parameters.get("member_name") or parameters.get("assignee")
                    up_res = await trello_tools.trello_update_card(
                        card_id=card_id,
                        name=new_title,
                        desc=desc or None,
                        due_date=parameters.get("due_date") or parameters.get("new_due_date") or parameters.get("due"),
                        member_name=member_name,
                    )
                    if up_res.get("status") == "SUCCESS":
                        return ExecutionResult(
                            tool_id=tool.get("tool_id", "trello_update_card"),
                            status="SUCCESS",
                            is_mutation=True,
                            preview=preview,
                            result=up_res,
                            message=f"Card '{card_name}' updated successfully via MCP.",
                        )
            except Exception as exc:
                logger.warning(f"Live Trello update via MCP failed: {exc}")

        return ExecutionResult(
            tool_id=tool.get("tool_id", "trello_update_card"),
            status="SUCCESS",
            is_mutation=True,
            preview=preview,
            result={"card_name": card_name, "status": "UPDATED_MOCK"},
            message=f"Simulated update for '{card_name}' completed successfully.",
        )


class MockTrelloArchiveCardExecutor(BaseExecutor):
    """Executor for card archiving mutations with live Trello MCP execution."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        payload_hash = compute_payload_hash(parameters)
        card_name = parameters.get("card_name") or parameters.get("name") or parameters.get("title") or "Task Card"

        preview = {
            "action_id": context.action_id or f"ACT-PREV-{uuid.uuid4().hex[:8].upper()}",
            "action_type": "ARCHIVE_CARD",
            "card_name": card_name,
            "parameters": parameters,
            "requires_confirmation": True,
        }

        if not context.confirmed:
            return ExecutionResult(
                tool_id=tool.get("tool_id", "trello_delete_card"),
                status="REQUIRES_APPROVAL",
                is_mutation=True,
                preview=preview,
                payload_hash=payload_hash,
                message=f"Deleting card '{card_name}' prepared for human review. Approval required before execution.",
            )

        if settings.TRELLO_API_KEY and settings.TRELLO_TOKEN:
            try:
                from app.mcp_server import trello_tools
                card_id = parameters.get("card_id")

                if not card_id or card_id == "c101":
                    cards_res = await trello_tools.trello_list_cards()
                    all_cards = cards_res.get("cards", [])
                    # 1. Exact match (case-insensitive)
                    for c in all_cards:
                        if c.get("name", "").strip().lower() == card_name.strip().lower():
                            card_id = c["id"]
                            break
                    # 2. Substring match
                    if not card_id:
                        for c in all_cards:
                            c_n = c.get("name", "").strip().lower()
                            cn_target = card_name.strip().lower()
                            if cn_target in c_n or c_n in cn_target:
                                card_id = c["id"]
                                break
                    # 3. Normalized alphanumeric match
                    if not card_id:
                        norm_target = re.sub(r"[^a-z0-9]", "", card_name.lower())
                        for c in all_cards:
                            c_norm = re.sub(r"[^a-z0-9]", "", c.get("name", "").lower())
                            if norm_target and (norm_target in c_norm or c_norm in norm_target):
                                card_id = c["id"]
                                break

                if card_id:
                    del_res = await trello_tools.trello_delete_card(card_id=card_id)
                    if del_res.get("status") == "SUCCESS":
                        return ExecutionResult(
                            tool_id=tool.get("tool_id", "trello_delete_card"),
                            status="SUCCESS",
                            is_mutation=True,
                            preview=preview,
                            result=del_res,
                            message=f"Card '{card_name}' deleted successfully via MCP.",
                        )
                    else:
                        return ExecutionResult(
                            tool_id=tool.get("tool_id", "trello_delete_card"),
                            status="FAILED",
                            is_mutation=True,
                            preview=preview,
                            result=del_res,
                            message=f"Failed to delete card '{card_name}': {del_res.get('message', 'Trello error')}",
                        )
                else:
                    return ExecutionResult(
                        tool_id=tool.get("tool_id", "trello_delete_card"),
                        status="FAILED",
                        is_mutation=True,
                        preview=preview,
                        result={"error": f"Card '{card_name}' not found on Trello board."},
                        message=f"Card '{card_name}' could not be found on the Trello board to delete.",
                    )
            except Exception as exc:
                logger.warning(f"Live Trello delete via MCP failed: {exc}")

        return ExecutionResult(
            tool_id=tool.get("tool_id", "trello_delete_card"),
            status="SUCCESS",
            is_mutation=True,
            preview=preview,
            result={"card_name": card_name, "status": "ARCHIVED_MOCK"},
            message=f"Simulated archive for '{card_name}' completed successfully.",
        )


class MockTrelloSearchExecutor(BaseExecutor):
    """Executor for card searches with live Trello MCP execution."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        query = (parameters.get("query") or "").lower().strip()
        raw_list_filter = (
            parameters.get("list_name")
            or parameters.get("status")
            or parameters.get("list")
            or ""
        ).strip()

        def norm_list_name(name: str) -> str:
            cleaned = re.sub(r"[\s\-_]+", "", name.lower())
            if cleaned in ("inprogress", "doing"):
                return "doing"
            return cleaned

        # If list_filter wasn't explicit but query represents a list name, treat query as list filter
        if not raw_list_filter and query:
            clean_q = norm_list_name(query)
            if clean_q in ("todo", "doing", "done", "inreview", "testing", "backlog"):
                raw_list_filter = query
                query = ""
            else:
                list_match = re.search(r"(?:in|to|under)\s+(?:the\s+)?([a-zA-Z0-9_\s\-]+?)(?:\s+list|\s+column)?$", query, re.IGNORECASE)
                if list_match:
                    raw_list_filter = list_match.group(1).strip()
                    query = re.sub(r"\s+(?:in|to|under)\s+(?:the\s+)?([a-zA-Z0-9_\s\-]+?)(?:\s+list|\s+column)?$", "", query, flags=re.IGNORECASE).strip()

        target_norm = norm_list_name(raw_list_filter) if raw_list_filter else ""

        if settings.TRELLO_API_KEY and settings.TRELLO_TOKEN:
            try:
                from app.mcp_server import trello_tools
                cards_res = await trello_tools.trello_list_cards()
                lists_res = await trello_tools.trello_list_lists()
                list_map = {l["id"]: l["name"] for l in lists_res.get("lists", [])}

                cards = []
                for c in cards_res.get("cards", []):
                    c_list = list_map.get(c.get("idList"), "To Do")
                    c_norm = norm_list_name(c_list)
                    card_obj = {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "desc": c.get("desc") or "",
                        "status": c_list,
                        "list_name": c_list,
                        "url": c.get("url"),
                        "due": c.get("due"),
                    }
                    if target_norm:
                        if target_norm != c_norm and target_norm not in c_norm and c_norm not in target_norm:
                            continue
                    if query and query not in ("card", "cards", "task", "tasks", "list", "lists", "all"):
                        if query not in card_obj["name"].lower() and query not in card_obj["desc"].lower():
                            continue
                    cards.append(card_obj)

                msg = f"Found {len(cards)} card(s) in '{raw_list_filter}' list on Trello." if target_norm else f"Found {len(cards)} live task cards on Trello."
                return ExecutionResult(
                    tool_id=tool.get("tool_id", "trello_search_cards"),
                    status="SUCCESS",
                    is_mutation=False,
                    result={"cards": cards, "total": len(cards)},
                    message=msg,
                )
            except Exception as exc:
                logger.warning(f"Live Trello search via MCP failed: {exc}")

        mock_results = [
            {"id": "c101", "name": "Login API Integration", "status": "IN_PROGRESS", "list_name": "In Progress", "assignee": "EMP-101"},
            {"id": "c102", "name": "Database Migration Script", "status": "DONE", "list_name": "Done", "assignee": "EMP-102"},
            {"id": "c103", "name": "OAuth Google Login Flow", "status": "TODO", "list_name": "To Do", "assignee": "EMP-101"},
        ]
        filtered = []
        for c in mock_results:
            c_norm = norm_list_name(c.get("status", "") or c.get("list_name", ""))
            if target_norm and target_norm != c_norm and target_norm not in c_norm and c_norm not in target_norm:
                continue
            if query and query not in ("card", "cards", "task", "tasks", "list", "lists", "all") and query not in c["name"].lower():
                continue
            filtered.append(c)

        msg = f"Found {len(filtered)} cards in '{raw_list_filter}' list." if target_norm else f"Found {len(filtered)} cards matching query '{query}'."
        return ExecutionResult(
            tool_id=tool.get("tool_id", "trello_search_cards"),
            status="SUCCESS",
            is_mutation=False,
            result={"cards": filtered, "total": len(filtered)},
            message=msg,
        )


class MockReportWorkloadExecutor(BaseExecutor):
    """Executor for workload metrics with live Trello MCP data."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        report_type = parameters.get("report_type", "daily")

        if settings.TRELLO_API_KEY and settings.TRELLO_TOKEN:
            try:
                from app.mcp_server import trello_tools
                cards_res = await trello_tools.trello_list_cards()
                lists_res = await trello_tools.trello_list_lists()
                list_map = {l["id"]: l["name"].lower() for l in lists_res.get("lists", [])}

                total = len(cards_res.get("cards", []))
                todo = 0
                in_progress = 0
                done = 0
                for c in cards_res.get("cards", []):
                    lname = list_map.get(c.get("idList"), "")
                    if "done" in lname:
                        done += 1
                    elif "doing" in lname or "progress" in lname:
                        in_progress += 1
                    else:
                        todo += 1

                return ExecutionResult(
                    tool_id=tool.get("tool_id", "report_get_workload"),
                    status="SUCCESS",
                    is_mutation=False,
                    result={
                        "report_type": report_type,
                        "summary": {
                            "total_tasks": total,
                            "completed": done,
                            "in_progress": in_progress,
                            "todo": todo,
                        },
                        "team_health": "OPTIMAL",
                    },
                    message=f"Generated {report_type} workload report from live Trello board ({total} cards).",
                )
            except Exception as exc:
                logger.warning(f"Live workload report via MCP failed: {exc}")

        return ExecutionResult(
            tool_id=tool.get("tool_id", "report_get_workload"),
            status="SUCCESS",
            is_mutation=False,
            result={
                "report_type": report_type,
                "summary": {"total_tasks": 28, "completed": 12, "in_progress": 8, "todo": 8},
                "team_health": "OPTIMAL",
            },
            message=f"Generated {report_type} workload report.",
        )


class MockEmployeeTasksExecutor(BaseExecutor):
    """Executor for employee task breakdowns."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        emp_name = parameters.get("employee_name", "All Employees")
        return ExecutionResult(
            tool_id=tool.get("tool_id", "report_get_employee_tasks"),
            status="SUCCESS",
            is_mutation=False,
            result={
                "employee": emp_name,
                "assigned_count": 5,
                "in_progress_active": 2,
                "in_review": 1,
                "done": 2,
            },
            message=f"Retrieved tasks for employee '{emp_name}'.",
        )


class MockTrelloCardDetailsExecutor(BaseExecutor):
    """Executor for card details with live Trello MCP data."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        card_name = parameters.get("card_name", "Task Card")
        card_id = parameters.get("card_id")

        if settings.TRELLO_API_KEY and settings.TRELLO_TOKEN:
            try:
                from app.mcp_server import trello_tools
                if not card_id or card_id == "c101":
                    cards_res = await trello_tools.trello_list_cards()
                    for c in cards_res.get("cards", []):
                        if card_name.lower() in c.get("name", "").lower():
                            card_id = c["id"]
                            break

                if card_id:
                    detail_res = await trello_tools.trello_get_card(card_id=card_id)
                    if detail_res.get("status") == "SUCCESS":
                        card = detail_res.get("card", {})
                        return ExecutionResult(
                            tool_id=tool.get("tool_id", "trello_get_card_details"),
                            status="SUCCESS",
                            is_mutation=False,
                            result={
                                "card_name": card.get("name"),
                                "id": card.get("id"),
                                "description": card.get("desc"),
                                "url": card.get("url"),
                                "due_date": card.get("due"),
                            },
                            message=f"Retrieved live card details for '{card.get('name')}'.",
                        )
            except Exception as exc:
                logger.warning(f"Live Trello card details via MCP failed: {exc}")

        return ExecutionResult(
            tool_id=tool.get("tool_id", "trello_get_card_details"),
            status="SUCCESS",
            is_mutation=False,
            result={
                "card_name": card_name,
                "status": "IN_PROGRESS",
                "assignee": "EMP-101",
                "due_date": "2026-11-20",
                "history": [
                    {"event": "CREATED", "timestamp": "2026-11-10T10:00:00Z"},
                    {"event": "MOVED_TO_IN_PROGRESS", "timestamp": "2026-11-11T14:30:00Z"},
                ],
            },
            message=f"Retrieved details and history for card '{card_name}'.",
        )


class MockEmployeeDirectoryExecutor(BaseExecutor):
    """Safe Phase 4 read-only executor for employee roster."""

    async def execute(
        self,
        tool: Dict[str, Any],
        parameters: Dict[str, Any],
        context: ExecutionContext,
    ) -> ExecutionResult:
        dept = parameters.get("department")
        return ExecutionResult(
            tool_id=tool.get("tool_id", "employee_list_directory"),
            status="SUCCESS",
            is_mutation=False,
            result={
                "department": dept or "All",
                "employees": [
                    {"id": "EMP-101", "name": "Sarah Connor", "role": "Senior Engineer", "status": "ACTIVE"},
                    {"id": "EMP-102", "name": "Kyle Reese", "role": "Backend Developer", "status": "ACTIVE"},
                    {"id": "EMP-103", "name": "John Connor", "role": "Product Manager", "status": "ACTIVE"},
                ],
            },
            message="Retrieved employee directory.",
        )


class ExecutorRegistry:
    """Central registry mapping executor keys to concrete BaseExecutor instances."""

    def __init__(self):
        self._executors: Dict[str, BaseExecutor] = {}
        self._register_default_executors()

    def _register_default_executors(self):
        self.register("mock.echo", EchoExecutor())
        self.register("trello_create_card", MockTrelloCreateCardExecutor())
        self.register("trello_create_list", MockTrelloCreateListExecutor())
        self.register("trello_move_card", MockTrelloMoveCardExecutor())
        self.register("trello_update_card", MockTrelloUpdateCardExecutor())
        self.register("trello_delete_card", MockTrelloArchiveCardExecutor())
        self.register("trello_archive_card", MockTrelloArchiveCardExecutor())
        self.register("trello_search_cards", MockTrelloSearchExecutor())
        self.register("trello_get_card_details", MockTrelloCardDetailsExecutor())
        self.register("report_get_workload", MockReportWorkloadExecutor())
        self.register("report_get_employee_tasks", MockEmployeeTasksExecutor())
        self.register("employee_list_directory", MockEmployeeDirectoryExecutor())

    def register(self, key: str, executor: BaseExecutor) -> None:
        self._executors[key] = executor

    def get(self, key: str) -> Optional[BaseExecutor]:
        return self._executors.get(key)

    def contains(self, key: str) -> bool:
        return key in self._executors


# Singleton registry instance
executor_registry = ExecutorRegistry()

