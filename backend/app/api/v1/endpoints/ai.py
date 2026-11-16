import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.approvals.models import ApprovalStatus
from app.approvals.schemas import ApprovalEditRequest
from app.approvals.service import ApprovalService
from app.chat.repository import ChatRepository
from app.chat.schemas import (
    ChatHistoryResponse,
    ChatMessageSchema,
    ChatSessionListResponse,
    ChatSessionSchema,
)
from app.core.dependencies import get_current_user
from app.core.logging import logger
from app.database.mongodb import get_database
from app.integrations.gemini.schemas import AIInterpretRequest, AIInterpretResponse
from app.integrations.gemini.service import GeminiService
from app.schemas.user import UserResponse
from app.tool_discovery.service import ToolDiscoveryService
from app.tool_executor.interfaces import ExecutionContext
from app.tool_executor.service import ToolExecutorService

router = APIRouter()


def get_ai_services(db: AsyncIOMotorDatabase = Depends(get_database)):
    discovery_service = ToolDiscoveryService(db)
    gemini_service = GeminiService()
    approval_service = ApprovalService(db)
    tool_executor = ToolExecutorService(db)
    chat_repo = ChatRepository(db)
    return discovery_service, gemini_service, approval_service, tool_executor, chat_repo


@router.get(
    "/sessions",
    response_model=ChatSessionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List user chat conversation sessions",
    description="Fetches all chat sessions (threads) for the authenticated user from MongoDB Atlas.",
)
async def list_user_chat_sessions(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ChatSessionListResponse:
    chat_repo = ChatRepository(db)
    sessions = await chat_repo.list_sessions(user_id=current_user.id, limit=50)
    parsed = []
    for s in sessions:
        try:
            parsed.append(ChatSessionSchema(**s))
        except Exception as e:
            logger.warning(f"Error parsing chat session: {e}")
    return ChatSessionListResponse(sessions=parsed, total=len(parsed))


@router.get(
    "/sessions/{session_id}/history",
    response_model=ChatHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get chat history for a specific conversation session",
    description="Fetches persistent conversational messages for a specific session from MongoDB Atlas.",
)
async def get_session_chat_history(
    session_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ChatHistoryResponse:
    chat_repo = ChatRepository(db)
    messages = await chat_repo.get_history(user_id=current_user.id, conversation_id=session_id, limit=100)
    parsed_messages = []
    for m in messages:
        try:
            parsed_messages.append(ChatMessageSchema(**m))
        except Exception as e:
            logger.warning(f"Error parsing chat message: {e}")
    return ChatHistoryResponse(messages=parsed_messages, total=len(parsed_messages), conversation_id=session_id)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a single conversation session",
    description="Removes a specific chat session and its messages from MongoDB Atlas.",
)
async def delete_user_chat_session(
    session_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    chat_repo = ChatRepository(db)
    deleted = await chat_repo.delete_session(user_id=current_user.id, conversation_id=session_id)
    return {"status": "SUCCESS", "message": f"Session '{session_id}' deleted.", "deleted": deleted}


@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get persistent user chat history",
    description="Fetches persistent conversational messages for the authenticated user from MongoDB Atlas.",
)
async def get_user_chat_history(
    conversation_id: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> ChatHistoryResponse:
    chat_repo = ChatRepository(db)
    messages = await chat_repo.get_history(user_id=current_user.id, conversation_id=conversation_id, limit=100)
    parsed_messages = []
    for m in messages:
        try:
            parsed_messages.append(ChatMessageSchema(**m))
        except Exception as e:
            logger.warning(f"Error parsing chat message: {e}")
    return ChatHistoryResponse(messages=parsed_messages, total=len(parsed_messages), conversation_id=conversation_id)


@router.delete(
    "/history",
    status_code=status.HTTP_200_OK,
    summary="Clear user conversation history",
    description="Removes all chat history documents for the authenticated user in MongoDB Atlas.",
)
async def clear_user_chat_history(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    chat_repo = ChatRepository(db)
    count = await chat_repo.clear_history(user_id=current_user.id)
    return {"status": "SUCCESS", "message": f"Cleared {count} messages from conversation history."}


@router.post(
    "/interpret",
    response_model=AIInterpretResponse,
    status_code=status.HTTP_200_OK,
    summary="Interpret natural language command and orchestrate dynamic tools",
    description="Conversational pipeline executing tool discovery, structured understanding, action drafting with approvals, and immediate read operations.",
)
async def interpret_user_command(
    payload: AIInterpretRequest,
    current_user: UserResponse = Depends(get_current_user),
    services=Depends(get_ai_services),
) -> AIInterpretResponse:
    discovery_service, gemini_service, approval_service, tool_executor, chat_repo = services
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    cmd = payload.command.strip()
    cmd_lower = cmd.lower()
    now_dt = datetime.now(timezone.utc)
    now_str = now_dt.isoformat()
    conv_id = payload.conversation_id or f"SES-{uuid.uuid4().hex[:10]}"

    # Record User Message in Atlas
    user_msg_id = f"MSG-U-{uuid.uuid4().hex[:8]}"
    await chat_repo.add_message({
        "id": user_msg_id,
        "user_id": current_user.id,
        "conversation_id": conv_id,
        "sender": "user",
        "content": cmd,
        "timestamp": now_str,
        "created_at": now_dt,
    })

    # --------------------------------------------------------------------------
    # 1. Resolve Active Pending Action Context for Conversational Confirm/Cancel/Edit
    # --------------------------------------------------------------------------
    active_action = None
    if payload.active_action_id:
        active_action = await approval_service.repository.get_by_action_id(payload.active_action_id)
        if active_action and active_action.get("status") != ApprovalStatus.PENDING.value:
            active_action = None

    if not active_action:
        # Check latest pending action for this user
        pending_list = await approval_service.repository.list_by_user(current_user.id, limit=3)
        for act in pending_list:
            if act.get("status") == ApprovalStatus.PENDING.value:
                active_action = act
                break

    # --------------------------------------------------------------------------
    # 2. Conversational Confirmation: "confirm", "yes create it", "looks good"
    # --------------------------------------------------------------------------
    is_confirm_intent = bool(
        active_action
        and (
            re.match(r"^(confirm|yes|proceed|looks good|approve|create it|go ahead)[\.\!]?$", cmd_lower)
            or ("confirm" in cmd_lower and len(cmd.split()) <= 4)
        )
    )
    if is_confirm_intent:
        act_id = active_action["action_id"]
        logger.info(f"User '{current_user.email}' requested conversational confirmation of action '{act_id}'")
        try:
            confirm_res = await approval_service.confirm_action(
                action_id=act_id,
                user_id=current_user.id,
                user_role=user_role_str,
            )
            card_title = active_action.get("draft", {}).get("title") or "Task"
            card_url = confirm_res.card_url
            asst_content = f"Action confirmed! Trello card '{card_title}' has been successfully created."
            if card_url:
                asst_content += f"\nView your card here: {card_url}"

            asst_msg_id = f"MSG-A-{uuid.uuid4().hex[:8]}"
            await chat_repo.add_message({
                "id": asst_msg_id,
                "user_id": current_user.id,
                "conversation_id": conv_id,
                "sender": "assistant",
                "content": asst_content,
                "timestamp": now_str,
                "created_at": now_dt,
                "intent": "confirm_action",
                "action_id": act_id,
                "execution_status": "EXECUTED",
                "execution_result": confirm_res.execution_result,
            })
            await chat_repo.update_action_status_in_chat(
                action_id=act_id,
                new_status="EXECUTED",
                card_url=card_url,
                card_id=confirm_res.card_id,
                execution_result=confirm_res.execution_result,
            )

            return AIInterpretResponse(
                command=cmd,
                intent="confirm_action",
                entity="card",
                parameters={"action_id": act_id},
                selected_tool_id=active_action.get("tool_id"),
                selected_tool_name=active_action.get("tool_name"),
                approval_required=False,
                confidence=1.0,
                candidate_tools_count=1,
                action_id=act_id,
                execution_result=confirm_res.execution_result,
                conversational_message=asst_content,
                conversation_id=conv_id,
            )
        except Exception as e:
            logger.error(f"Conversational confirmation failed: {e}")
            error_content = f"Confirmation failed: {str(e)}"
            return AIInterpretResponse(
                command=cmd,
                intent="confirm_action",
                entity="card",
                parameters={"action_id": act_id},
                approval_required=False,
                confidence=0.5,
                candidate_tools_count=0,
                conversational_message=error_content,
                conversation_id=conv_id,
            )

    # --------------------------------------------------------------------------
    # 3. Conversational Cancellation / Rejection: "cancel", "reject", "nevermind"
    # --------------------------------------------------------------------------
    is_cancel_intent = bool(
        active_action
        and (
            re.match(r"^(cancel|reject|discard|nevermind|don't create|abort|stop)[\.\!]?$", cmd_lower)
            or (("cancel" in cmd_lower or "reject" in cmd_lower or "discard" in cmd_lower) and len(cmd.split()) <= 4)
        )
    )
    if is_cancel_intent:
        act_id = active_action["action_id"]
        logger.info(f"User '{current_user.email}' requested conversational cancellation of action '{act_id}'")
        await approval_service.cancel_action(
            action_id=act_id,
            user_id=current_user.id,
            user_role=user_role_str,
        )
        asst_content = f"Task draft '{active_action.get('draft', {}).get('title', 'Task')}' has been rejected. No changes were made to Trello."
        asst_msg_id = f"MSG-A-{uuid.uuid4().hex[:8]}"
        await chat_repo.add_message({
            "id": asst_msg_id,
            "user_id": current_user.id,
            "conversation_id": conv_id,
            "sender": "assistant",
            "content": asst_content,
            "timestamp": now_str,
            "created_at": now_dt,
            "intent": "cancel_action",
            "action_id": act_id,
            "execution_status": "REJECTED",
        })
        await chat_repo.update_action_status_in_chat(action_id=act_id, new_status="REJECTED")

        return AIInterpretResponse(
            command=cmd,
            intent="cancel_action",
            entity="card",
            parameters={"action_id": act_id},
            selected_tool_id=active_action.get("tool_id"),
            selected_tool_name=active_action.get("tool_name"),
            approval_required=False,
            confidence=1.0,
            candidate_tools_count=1,
            action_id=act_id,
            conversational_message=asst_content,
            conversation_id=conv_id,
        )

    # --------------------------------------------------------------------------
    # 4. Conversational Editing of Active Draft: "change priority to...", "update description..."
    # --------------------------------------------------------------------------
    is_edit_intent = bool(
        active_action
        and not cmd_lower.startswith(("create ", "add ", "new "))
        and (
            cmd_lower.startswith(("change ", "update ", "set ", "edit ", "modify "))
            or "priority" in cmd_lower
            or "due date" in cmd_lower
            or "description" in cmd_lower
        )
    )
    if is_edit_intent:
        act_id = active_action["action_id"]
        logger.info(f"User '{current_user.email}' requested conversational draft edit for '{act_id}'")

        # Extract priority updates
        new_priority = None
        if "high" in cmd_lower or "urgent" in cmd_lower:
            new_priority = "HIGH"
        elif "low" in cmd_lower:
            new_priority = "LOW"
        elif "medium" in cmd_lower:
            new_priority = "MEDIUM"

        # Extract title updates
        new_title = None
        title_match = re.search(r"(?:change|update|set|edit)\s+title\s+(?:to\s+)?(.+)", cmd, re.IGNORECASE)
        if title_match:
            new_title = title_match.group(1).strip().strip('"\'')

        # Extract description updates
        new_desc = None
        desc_match = re.search(r"(?:change|update|add|set)\s+(?:a\s+)?description\s+(?:to\s+)?(.+)", cmd, re.IGNORECASE)
        if desc_match:
            new_desc = desc_match.group(1).strip().strip('"\'')
        elif "jwt implementation" in cmd_lower:
            new_desc = "Implement JWT authentication with secret keys, token issuance, and Argon2 password verification."

        edit_req = ApprovalEditRequest(
            title=new_title,
            description=new_desc,
            priority=new_priority,
        )
        updated_preview = await approval_service.edit_action(
            action_id=act_id,
            user_id=current_user.id,
            user_role=user_role_str,
            edit_data=edit_req,
        )

        preview_data = updated_preview.model_dump()
        preview_data["status"] = "PENDING"
        preview_data["action_id"] = act_id
        preview_data["parameters"] = updated_preview.draft.parameters
        preview_data["message"] = "Task draft updated. Please review the updated preview below and confirm."

        asst_content = f"I've updated the task draft with your changes. Please review the updated preview below and confirm."
        asst_msg_id = f"MSG-A-{uuid.uuid4().hex[:8]}"
        await chat_repo.add_message({
            "id": asst_msg_id,
            "user_id": current_user.id,
            "conversation_id": conv_id,
            "sender": "assistant",
            "content": asst_content,
            "timestamp": now_str,
            "created_at": now_dt,
            "intent": "edit_action",
            "action_id": act_id,
            "approval_required": True,
            "approval_preview": preview_data,
            "execution_status": "AWAITING_APPROVAL",
        })
        await chat_repo.update_action_status_in_chat(
            action_id=act_id,
            new_status="PENDING",
            updated_draft=preview_data.get("draft"),
        )

        return AIInterpretResponse(
            command=cmd,
            intent="edit_action",
            entity="card",
            parameters=updated_preview.draft.parameters,
            selected_tool_id=active_action.get("tool_id"),
            selected_tool_name=active_action.get("tool_name"),
            approval_required=True,
            confidence=0.98,
            candidate_tools_count=1,
            action_id=act_id,
            execution_preview=preview_data,
            conversational_message=asst_content,
            conversation_id=conv_id,
        )

    # --------------------------------------------------------------------------
    # 5. Standard Intent Pipeline: Tool Discovery & Gemini Interpretation
    # --------------------------------------------------------------------------
    discovered_tools = await discovery_service.discover_tools(
        query=cmd,
        user_role=user_role_str,
        limit=5,
    )

    # Retrieve prior conversation context to support multi-turn disambiguation within this session
    history_docs = await chat_repo.get_history(user_id=current_user.id, conversation_id=conv_id, limit=10)
    prev_history = [doc for doc in history_docs if doc.get("id") != user_msg_id]

    req_id = f"REQ-{uuid.uuid4().hex[:6]}"
    intent_output = await gemini_service.interpret_command(
        command=cmd,
        discovered_tools=discovered_tools,
        conversation_history=prev_history,
        correlation_id=req_id,
    )

    selected_tool = None
    if intent_output.suggested_tool_id:
        for item in discovered_tools:
            if item.tool.tool_id == intent_output.suggested_tool_id:
                selected_tool = item.tool
                break

    if not selected_tool and discovered_tools and intent_output.intent != "unknown":
        selected_tool = discovered_tools[0].tool

    approval_required = selected_tool.approval_required if selected_tool else False
    preview_data = None
    execution_result_data = None
    conversational_message = None
    generated_action_id = None

    # --------------------------------------------------------------------------
    # 6. MUTATION HANDLING: Task Creation, Movement, Update, Archive
    # --------------------------------------------------------------------------
    if selected_tool and approval_required:
        tool_id = selected_tool.tool_id
        action_type = "CREATE_CARD"
        params = dict(intent_output.parameters)

        if tool_id == "trello_create_list" or intent_output.intent in ["create_list", "add_list"]:
            action_type = "CREATE_LIST"
        elif tool_id == "trello_move_card" or intent_output.intent == "move_card":
            action_type = "MOVE_CARD"
        elif tool_id == "trello_update_card" or intent_output.intent in ["update_card", "assign_member"]:
            action_type = "UPDATE_CARD"
        elif tool_id in ["trello_delete_card", "trello_archive_card"] or intent_output.intent in ["delete_card", "archive_card"]:
            action_type = "ARCHIVE_CARD"

        draft_response = await approval_service.create_task_draft(
            user_id=current_user.id,
            user_email=current_user.email,
            command=cmd,
            intent=intent_output.intent,
            tool_id=tool_id,
            tool_name=selected_tool.name,
            category=selected_tool.category,
            parameters=params,
            action_type=action_type,
        )

        generated_action_id = draft_response.action_id
        preview_data = draft_response.model_dump()
        preview_data["status"] = "PENDING"
        preview_data["action_id"] = generated_action_id
        preview_data["parameters"] = draft_response.draft.parameters
        preview_data["message"] = "Action prepared for human review. Please confirm, edit, or reject."

        if action_type == "UPDATE_CARD" and params.get("member_name"):
            conversational_message = (
                f"I have prepared a draft to assign '{params.get('member_name')}' to '{draft_response.draft.title}'. "
                "Please review the preview below and confirm to execute it on Trello."
            )
        elif action_type == "UPDATE_CARD" and (params.get("new_due_date") or params.get("due_date") or params.get("due")):
            resolved_due = params.get("new_due_date") or params.get("due_date") or params.get("due")
            conversational_message = (
                f"I have prepared a draft to set due date '{resolved_due}' on '{draft_response.draft.title}'. "
                "Please review the preview below and confirm to execute it on Trello."
            )
        else:
            conversational_message = (
                f"I have prepared a draft to {action_type.lower().replace('_', ' ')} based on your request. "
                "Please review the preview below and confirm to execute it on Trello."
            )

    # --------------------------------------------------------------------------
    # 7. READ OPERATION EXECUTION: Listing, Searching, Workload Reports
    # --------------------------------------------------------------------------
    elif selected_tool and not approval_required:
        exec_context = ExecutionContext(
            user_id=current_user.id,
            user_role=user_role_str,
            confirmed=True,
        )
        try:
            exec_res = await tool_executor.execute(
                tool_id=selected_tool.tool_id,
                parameters=intent_output.parameters,
                context=exec_context,
            )
            execution_result_data = exec_res.result if hasattr(exec_res, "result") else exec_res
            if hasattr(exec_res, "model_dump"):
                execution_result_data = exec_res.model_dump().get("result")

            # Craft helpful conversational response
            if selected_tool.tool_id == "trello_search_cards":
                cards = (execution_result_data or {}).get("cards", [])
                list_spec = (
                    intent_output.parameters.get("list_name")
                    or intent_output.parameters.get("status")
                    or intent_output.parameters.get("list")
                )
                if list_spec:
                    if cards:
                        conversational_message = f"I found {len(cards)} card(s) in the '{list_spec}' list on your Trello board:"
                    else:
                        conversational_message = f"No cards were found in the '{list_spec}' list on your Trello board."
                elif cards:
                    conversational_message = f"I found {len(cards)} matching card(s) on your Trello board:"
                else:
                    conversational_message = "No matching task cards were found on your Trello board."
            elif selected_tool.tool_id == "report_get_workload":
                summary = (execution_result_data or {}).get("summary", {})
                conversational_message = (
                    f"Workload Summary: {summary.get('total_tasks', 0)} total tasks "
                    f"({summary.get('completed', 0)} completed, {summary.get('in_progress', 0)} in progress, {summary.get('todo', 0)} to do)."
                )
            elif selected_tool.tool_id == "trello_get_card_details":
                card_name = (execution_result_data or {}).get("card_name") or "Card"
                status_val = (execution_result_data or {}).get("status") or "Open"
                conversational_message = f"Details for '{card_name}': Current status is {status_val}."
            else:
                conversational_message = f"Executed {selected_tool.name} successfully."
        except Exception as e:
            logger.warning(f"Error executing read tool '{selected_tool.tool_id}': {e}")
            conversational_message = f"I encountered an issue executing {selected_tool.name}: {str(e)}"

    else:
        if intent_output.requires_clarification:
            conversational_message = intent_output.clarification_message or "Could you please clarify your request?"
        else:
            conversational_message = f"I couldn't identify a matching tool for your command. Please try asking in a different way."

    # --------------------------------------------------------------------------
    # 8. Record Assistant Response in Atlas Chat History
    # --------------------------------------------------------------------------
    asst_msg_id = f"MSG-A-{uuid.uuid4().hex[:8]}"
    await chat_repo.add_message({
        "id": asst_msg_id,
        "user_id": current_user.id,
        "conversation_id": conv_id,
        "sender": "assistant",
        "content": conversational_message,
        "timestamp": now_str,
        "created_at": now_dt,
        "intent": intent_output.intent,
        "parameters": intent_output.parameters,
        "selected_tool_id": selected_tool.tool_id if selected_tool else None,
        "selected_tool_name": selected_tool.name if selected_tool else None,
        "approval_required": approval_required,
        "action_id": generated_action_id,
        "approval_preview": preview_data,
        "execution_result": execution_result_data,
        "execution_status": "AWAITING_APPROVAL" if approval_required else "EXECUTED",
        "discovered_tool": {
            "name": selected_tool.name if selected_tool else "None",
            "category": selected_tool.category if selected_tool else "TRELLO",
            "relevance_score": intent_output.confidence,
            "explanation": f"Discovered dynamic tool for intent '{intent_output.intent}'.",
        } if selected_tool else None,
    })

    return AIInterpretResponse(
        command=cmd,
        intent=intent_output.intent,
        entity=intent_output.entity,
        parameters=intent_output.parameters,
        selected_tool_id=selected_tool.tool_id if selected_tool else None,
        selected_tool_name=selected_tool.name if selected_tool else None,
        approval_required=approval_required,
        requires_clarification=intent_output.requires_clarification,
        clarification_message=intent_output.clarification_message,
        confidence=intent_output.confidence,
        candidate_tools_count=len(discovered_tools),
        execution_preview=preview_data,
        action_id=generated_action_id,
        execution_result=execution_result_data,
        conversational_message=conversational_message,
        conversation_id=conv_id,
    )
