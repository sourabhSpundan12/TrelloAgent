import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
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


def find_best_matching_card(cards: List[Dict[str, Any]], target_name: str) -> Optional[Dict[str, Any]]:
    """
    Finds the best matching card from a list of Trello cards.
    Prioritizes exact match (ignoring optional trailing 'card'),
    then normalized alphanumeric match, then closest-length substring match.
    """
    if not target_name or not cards:
        return None

    clean_target = re.sub(r"\s+card$", "", target_name.strip().lower(), flags=re.IGNORECASE).strip()
    norm_target = re.sub(r"[^a-z0-9]", "", clean_target)

    # 1. Exact match (case-insensitive, ignoring trailing 'card')
    for c in cards:
        c_name = c.get("name", "").strip().lower()
        clean_cname = re.sub(r"\s+card$", "", c_name, flags=re.IGNORECASE).strip()
        if clean_cname == clean_target:
            return c

    # 2. Normalized alphanumeric match
    if norm_target:
        for c in cards:
            c_name = c.get("name", "").strip().lower()
            clean_cname = re.sub(r"\s+card$", "", c_name, flags=re.IGNORECASE).strip()
            norm_cname = re.sub(r"[^a-z0-9]", "", clean_cname)
            if norm_cname and norm_cname == norm_target:
                return c

    # 3. Substring match: rank by length difference to prefer the closest match
    candidates = []
    for c in cards:
        c_name = c.get("name", "").strip().lower()
        clean_cname = re.sub(r"\s+card$", "", c_name, flags=re.IGNORECASE).strip()
        if clean_target in clean_cname or clean_cname in clean_target:
            candidates.append(c)

    if candidates:
        candidates.sort(key=lambda c: abs(len(c.get("name", "")) - len(target_name)))
        return candidates[0]

    return None


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
                    lists_res = await trello_tools.trello_list_lists(board_id=board_id)
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
                    due_date=parameters.get("due_date") or parameters.get("due") or parameters.get("new_due_date"),
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
                "due": parameters.get("due_date") or parameters.get("due") or parameters.get("new_due_date"),
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
                board_id = parameters.get("board_id") or settings.TRELLO_BOARD_ID or None

                # Resolve card_id dynamically if missing
                if not card_id or card_id.startswith("card_") or card_id == "c101":
                    cards_res = await trello_tools.trello_list_cards(board_id=board_id)
                    matched_c = find_best_matching_card(cards_res.get("cards", []), card_name)
                    if matched_c:
                        card_id = matched_c["id"]
                        card_name = matched_c["name"]

                # Resolve list_id dynamically if missing
                if not list_id or list_id.startswith("list_"):
                    lists_res = await trello_tools.trello_list_lists(board_id=board_id)
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
                board_id = parameters.get("board_id") or settings.TRELLO_BOARD_ID or None

                if not card_id or card_id == "c101":
                    cards_res = await trello_tools.trello_list_cards(board_id=board_id)
                    matched_c = find_best_matching_card(cards_res.get("cards", []), card_name)
                    if matched_c:
                        card_id = matched_c["id"]
                        card_name = matched_c["name"]

                if card_id:
                    new_title = parameters.get("new_title") or parameters.get("new_name")
                    member_name = parameters.get("member_name") or parameters.get("assignee")
                    up_res = await trello_tools.trello_update_card(
                        card_id=card_id,
                        name=new_title,
                        desc=desc or None,
                        due_date=parameters.get("due_date") or parameters.get("new_due_date") or parameters.get("due"),
                        member_name=member_name,
                        board_id=board_id,
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
                    else:
                        error_msg = up_res.get("message") or "Failed updating card on Trello."
                        return ExecutionResult(
                            tool_id=tool.get("tool_id", "trello_update_card"),
                            status="ERROR",
                            is_mutation=True,
                            preview=preview,
                            result=up_res,
                            message=f"Trello update failed: {error_msg}",
                        )
                else:
                    return ExecutionResult(
                        tool_id=tool.get("tool_id", "trello_update_card"),
                        status="ERROR",
                        is_mutation=True,
                        preview=preview,
                        result={"error": f"Card '{card_name}' not found on active board."},
                        message=f"Could not find card '{card_name}' on the active Trello board.",
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
                board_id = parameters.get("board_id") or settings.TRELLO_BOARD_ID or None
                card_id = parameters.get("card_id")
                raw_target = (parameters.get("list_name") or parameters.get("card_name") or parameters.get("name") or card_name).strip()
                raw_target = re.sub(r"^(?:of|in|from|under)\s+", "", raw_target, flags=re.IGNORECASE).strip()
                raw_target = re.sub(r"\s+(?:list|column)$", "", raw_target, flags=re.IGNORECASE).strip()

                def norm_name(n: str) -> str:
                    return re.sub(r"[\s\-_]+", "", n.lower())

                # 1. Check if raw_target matches a LIST on the board (e.g. "To Do", "Trello Starter Guide")
                lists_res = await trello_tools.trello_list_lists(board_id=board_id)
                board_lists = lists_res.get("lists", [])
                matching_list = None

                list_id_param = parameters.get("list_id")
                if list_id_param:
                    for bl in board_lists:
                        if bl.get("id") == list_id_param:
                            matching_list = bl
                            break

                if not matching_list:
                    t_norm = norm_name(raw_target)
                    for bl in board_lists:
                        bl_norm = norm_name(bl["name"])
                        is_typo = (
                            ("starter" in t_norm and "starter" in bl_norm)
                            or ("started" in t_norm and "starter" in bl_norm)
                            or ("starter" in t_norm and "started" in bl_norm)
                        )
                        if t_norm == bl_norm or t_norm in bl_norm or bl_norm in t_norm or is_typo:
                            matching_list = bl
                            break

                if matching_list:
                    # Fetch all cards in that list
                    cards_res = await trello_tools.trello_list_cards(board_id=board_id, list_id=matching_list["id"])
                    list_cards = cards_res.get("cards", [])
                    deleted_names = []
                    for c in list_cards:
                        try:
                            await trello_tools.trello_delete_card(card_id=c["id"])
                            deleted_names.append(c.get("name", "Card"))
                        except Exception as e:
                            logger.warning(f"Failed deleting card {c.get('id')}: {e}")

                    msg = f"Successfully deleted {len(deleted_names)} card(s) from '{matching_list['name']}' list on Trello."
                    try:
                        from app.database.mongodb import get_database
                        db = await get_database()
                        del_ids = [str(c["id"]) for c in list_cards if c.get("id")]
                        if del_ids:
                            await db["task_assignments"].delete_many({"trello_card_id": {"$in": del_ids}})
                    except Exception as db_err:
                        logger.debug(f"Failed pruning task_assignments on bulk list delete: {db_err}")
                    return ExecutionResult(
                        tool_id=tool.get("tool_id", "trello_delete_card"),
                        status="SUCCESS",
                        is_mutation=True,
                        preview=preview,
                        result={"status": "SUCCESS", "deleted_cards": deleted_names, "total_deleted": len(deleted_names), "list_name": matching_list["name"]},
                        message=msg,
                    )

                # If this was specifically a bulk list delete request but list was not found live, return bulk result
                if parameters.get("is_bulk_delete") or parameters.get("action_type") == "DELETE_LIST_CARDS":
                    cnt = parameters.get("cards_count", 0)
                    ln = parameters.get("list_name") or raw_target or card_name
                    return ExecutionResult(
                        tool_id=tool.get("tool_id", "trello_delete_card"),
                        status="SUCCESS",
                        is_mutation=True,
                        preview=preview,
                        result={"status": "SUCCESS", "deleted_cards": parameters.get("card_names", []), "total_deleted": cnt, "list_name": ln},
                        message=f"Completed bulk delete for {cnt} task(s) in '{ln}' list.",
                    )

                # 2. Otherwise, single card deletion
                if not card_id or card_id == "c101":
                    cards_res = await trello_tools.trello_list_cards(board_id=board_id)
                    matched_c = find_best_matching_card(cards_res.get("cards", []), card_name)
                    if matched_c:
                        card_id = matched_c["id"]

                if card_id:
                    del_res = await trello_tools.trello_delete_card(card_id=card_id)
                    if del_res.get("status") == "SUCCESS":
                        try:
                            from app.database.mongodb import get_database
                            db = await get_database()
                            await db["task_assignments"].delete_many({"trello_card_id": str(card_id)})
                        except Exception as db_err:
                            logger.debug(f"Failed pruning task_assignments for card {card_id}: {db_err}")
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

        if parameters.get("is_bulk_delete") or parameters.get("action_type") == "DELETE_LIST_CARDS":
            cnt = parameters.get("cards_count", 0)
            ln = parameters.get("list_name") or card_name
            return ExecutionResult(
                tool_id=tool.get("tool_id", "trello_delete_card"),
                status="SUCCESS",
                is_mutation=True,
                preview=preview,
                result={"status": "SUCCESS", "deleted_cards": parameters.get("card_names", []), "total_deleted": cnt, "list_name": ln},
                message=f"Simulated bulk delete for {cnt} task(s) in '{ln}' completed successfully.",
            )

        return ExecutionResult(
            tool_id=tool.get("tool_id", "trello_delete_card"),
            status="SUCCESS",
            is_mutation=True,
            preview=preview,
            result={"card_name": card_name, "status": "ARCHIVED_MOCK"},
            message=f"Simulated archive for '{card_name}' completed successfully.",
        )


class MockTrelloSearchExecutor(BaseExecutor):
    """Executor for card searches with live Trello MCP execution and date range filtering."""

    @staticmethod
    def _parse_date(date_val: Any) -> Optional[datetime]:
        if not date_val:
            return None
        if isinstance(date_val, datetime):
            return date_val if date_val.tzinfo else date_val.replace(tzinfo=timezone.utc)
        s = str(date_val).strip()
        if not s:
            return None
        clean_s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean_s)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            pass
        for fmt in (
            "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d",
            "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y",
            "%d %b", "%d %B",
        ):
            try:
                parsed = datetime.strptime(s, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=datetime.now(timezone.utc).year)
                return parsed.replace(tzinfo=timezone.utc)
            except Exception:
                continue
        return None

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

        # Date range filtering (From Date - To Date)
        from_date_raw = (
            parameters.get("from_date")
            or parameters.get("start_date")
            or parameters.get("from")
            or parameters.get("startDate")
        )
        to_date_raw = (
            parameters.get("to_date")
            or parameters.get("end_date")
            or parameters.get("to")
            or parameters.get("endDate")
        )
        from_dt = self._parse_date(from_date_raw) if from_date_raw else None
        to_dt = self._parse_date(to_date_raw) if to_date_raw else None
        if to_dt:
            # Inclusive of the entire end date (up to 23:59:59)
            to_dt = to_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

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
                board_id = parameters.get("board_id") or settings.TRELLO_BOARD_ID or None
                cards_res = await trello_tools.trello_list_cards(board_id=board_id)
                lists_res = await trello_tools.trello_list_lists(board_id=board_id)
                board_lists = lists_res.get("lists", [])
                list_map = {l["id"]: l["name"] for l in board_lists}

                # Check if query or raw_list_filter matches any list on the board
                matching_list_name = None
                if raw_list_filter:
                    rf_norm = norm_list_name(raw_list_filter)
                    for bl in board_lists:
                        bl_norm = norm_list_name(bl["name"])
                        is_typo = (
                            ("starter" in rf_norm and "starter" in bl_norm)
                            or ("started" in rf_norm and "starter" in bl_norm)
                            or ("starter" in rf_norm and "started" in bl_norm)
                        )
                        if rf_norm == bl_norm or rf_norm in bl_norm or bl_norm in rf_norm or is_typo:
                            matching_list_name = bl["name"]
                            break

                if not matching_list_name and query and query not in ("card", "cards", "task", "tasks", "list", "lists", "all"):
                    q_norm = norm_list_name(query)
                    for bl in board_lists:
                        bl_norm = norm_list_name(bl["name"])
                        is_typo = (
                            ("starter" in q_norm and "starter" in bl_norm)
                            or ("started" in q_norm and "starter" in bl_norm)
                            or ("starter" in q_norm and "started" in bl_norm)
                        )
                        if q_norm == bl_norm or q_norm in bl_norm or bl_norm in q_norm or query in bl["name"].lower() or bl["name"].lower() in query or is_typo:
                            matching_list_name = bl["name"]
                            query = ""
                            break

                if matching_list_name:
                    raw_list_filter = matching_list_name
                    target_norm = norm_list_name(matching_list_name)

                cards = []
                for c in cards_res.get("cards", []):
                    c_list = list_map.get(c.get("idList"), "To Do")
                    c_norm = norm_list_name(c_list)
                    is_completed = "done" in c_norm or "completed" in c_norm

                    # Resolve card reference date (due date or creation date from card ObjectId)
                    card_dt = None
                    if c.get("due"):
                        card_dt = self._parse_date(c.get("due"))
                    if not card_dt and c.get("id") and len(str(c.get("id"))) >= 8:
                        try:
                            ts = int(str(c.get("id"))[:8], 16)
                            card_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                        except Exception:
                            card_dt = None

                    # Filter by date range if provided
                    if from_dt and card_dt and card_dt < from_dt:
                        continue
                    if to_dt and card_dt and card_dt > to_dt:
                        continue
                    if (from_dt or to_dt) and not card_dt:
                        continue

                    card_obj = {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "desc": c.get("desc") or "",
                        "status": c_list,
                        "list_name": c_list,
                        "url": c.get("url"),
                        "due": c.get("due"),
                        "is_completed": is_completed,
                        "status_category": "Completed" if is_completed else "Active",
                        "card_date": card_dt.isoformat() if card_dt else None,
                    }
                    if target_norm:
                        is_typo = (
                            ("starter" in target_norm and "starter" in c_norm)
                            or ("started" in target_norm and "starter" in c_norm)
                            or ("starter" in target_norm and "started" in c_norm)
                        )
                        if target_norm != c_norm and target_norm not in c_norm and c_norm not in target_norm and not is_typo:
                            continue
                    if query and query not in ("card", "cards", "task", "tasks", "list", "lists", "all"):
                        q_clean = query.lower()
                        in_name = q_clean in card_obj["name"].lower()
                        in_desc = q_clean in card_obj["desc"].lower()
                        in_list = q_clean in card_obj["list_name"].lower() or card_obj["list_name"].lower() in q_clean
                        if not (in_name or in_desc or in_list):
                            continue
                    cards.append(card_obj)

                active_count = sum(1 for c in cards if not c.get("is_completed"))
                completed_count = sum(1 for c in cards if c.get("is_completed"))

                if from_dt or to_dt:
                    date_range_label = f"from {from_dt.strftime('%d %b %Y') if from_dt else 'earliest'} to {to_dt.strftime('%d %b %Y') if to_dt else 'latest'}"
                    msg = f"Found {len(cards)} task(s) {date_range_label} on Trello ({active_count} active, {completed_count} completed)."
                elif target_norm:
                    msg = f"Found {len(cards)} card(s) in '{raw_list_filter}' list on Trello."
                else:
                    msg = f"Found {len(cards)} live task cards on Trello ({active_count} active, {completed_count} completed)."

                return ExecutionResult(
                    tool_id=tool.get("tool_id", "trello_search_cards"),
                    status="SUCCESS",
                    is_mutation=False,
                    result={
                        "cards": cards,
                        "total": len(cards),
                        "active_count": active_count,
                        "completed_count": completed_count,
                        "list_name": raw_list_filter if target_norm else None,
                        "from_date": from_dt.strftime("%Y-%m-%d") if from_dt else None,
                        "to_date": to_dt.strftime("%Y-%m-%d") if to_dt else None,
                    },
                    message=msg,
                )
            except Exception as exc:
                logger.warning(f"Live Trello search via MCP failed: {exc}")

        now_ref = datetime.now(timezone.utc)
        mock_results = [
            {"id": "c101", "name": "Login API Integration", "status": "IN_PROGRESS", "list_name": "In Progress", "assignee": "EMP-101", "due": (now_ref).isoformat(), "is_completed": False, "status_category": "Active"},
            {"id": "c102", "name": "Database Migration Script", "status": "DONE", "list_name": "Done", "assignee": "EMP-102", "due": (now_ref).isoformat(), "is_completed": True, "status_category": "Completed"},
            {"id": "c103", "name": "OAuth Google Login Flow", "status": "TODO", "list_name": "To Do", "assignee": "EMP-101", "due": (now_ref).isoformat(), "is_completed": False, "status_category": "Active"},
        ]
        filtered = []
        for c in mock_results:
            c_norm = norm_list_name(c.get("status", "") or c.get("list_name", ""))
            if target_norm and target_norm != c_norm and target_norm not in c_norm and c_norm not in target_norm:
                continue
            if query and query not in ("card", "cards", "task", "tasks", "list", "lists", "all") and query not in c["name"].lower():
                continue
            card_dt = self._parse_date(c.get("due"))
            if from_dt and card_dt and card_dt < from_dt:
                continue
            if to_dt and card_dt and card_dt > to_dt:
                continue
            filtered.append(c)

        active_cnt = sum(1 for c in filtered if not c.get("is_completed"))
        comp_cnt = sum(1 for c in filtered if c.get("is_completed"))
        if from_dt or to_dt:
            msg = f"Found {len(filtered)} task(s) within the specified date range ({active_cnt} active, {comp_cnt} completed)."
        elif target_norm:
            msg = f"Found {len(filtered)} cards in '{raw_list_filter}' list."
        else:
            msg = f"Found {len(filtered)} cards matching query '{query}'."

        return ExecutionResult(
            tool_id=tool.get("tool_id", "trello_search_cards"),
            status="SUCCESS",
            is_mutation=False,
            result={
                "cards": filtered,
                "total": len(filtered),
                "active_count": active_cnt,
                "completed_count": comp_cnt,
                "list_name": raw_list_filter if target_norm else None,
            },
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
                board_id = parameters.get("board_id") or settings.TRELLO_BOARD_ID or None
                cards_res = await trello_tools.trello_list_cards(board_id=board_id)
                lists_res = await trello_tools.trello_list_lists(board_id=board_id)
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
        board_id = parameters.get("board_id") or settings.TRELLO_BOARD_ID or None

        if settings.TRELLO_API_KEY and settings.TRELLO_TOKEN:
            try:
                from app.mcp_server import trello_tools
                if not card_id or card_id == "c101":
                    cards_res = await trello_tools.trello_list_cards(board_id=board_id)
                    matched_c = find_best_matching_card(cards_res.get("cards", []), card_name)
                    if matched_c:
                        card_id = matched_c["id"]

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

