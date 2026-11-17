import json
from typing import Any, Dict, List, Optional
from app.tool_discovery.schemas import DiscoveredToolItem

SYSTEM_INSTRUCTION = """You are the intent interpretation engine for an enterprise Agentic Task Manager.
Your role is strictly to interpret the user's natural language command, identify their intent, extract required non-sensitive parameters, and select the best matching tool from the provided dynamic tool definitions.

CRITICAL SECURITY AND PRIVACY RULES:
1. You MUST NEVER execute Python code, MongoDB queries, shell commands, or network calls.
2. You MUST NEVER output passwords, API keys, bearer tokens, or sensitive credentials.
3. You MUST NEVER invent sensitive employee records or private data.
4. If the user command is ambiguous, contradictory, or lacks vital required parameters, set "requires_clarification": true and explain what is needed in "clarification_message".
5. Output MUST be valid, parseable JSON conforming strictly to the requested schema. No markdown wrapping or conversational preambles outside the JSON.
"""


def format_tool_metadata_for_prompt(discovered_tools: List[DiscoveredToolItem]) -> str:
    """
    Formats discovered tool definitions into minimal, non-sensitive JSON context.
    NEVER includes database connection strings, credentials, or private internal structures.
    """
    formatted = []
    for item in discovered_tools:
        t = item.tool
        formatted.append({
            "tool_id": t.tool_id,
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "capabilities": t.capabilities,
            "approval_required": t.approval_required,
            "input_schema": t.input_schema,
        })
    return json.dumps(formatted, indent=2)


def build_interpretation_prompt(
    command: str,
    discovered_tools: List[DiscoveredToolItem],
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Builds the prompt provided to Gemini for intent extraction."""
    tools_context = format_tool_metadata_for_prompt(discovered_tools)

    history_context = ""
    if conversation_history:
        history_lines = []
        for msg in conversation_history:
            sender = msg.get("sender") or msg.get("role") or "user"
            content = msg.get("content", "")
            history_lines.append(f"[{sender.upper()}]: {content}")
        history_context = "\nPREVIOUS CONVERSATION CONTEXT:\n" + "\n".join(history_lines) + "\n"

    return f"""Analyze the following user command and extract the structured intent.
{history_context}
USER COMMAND:
\"{command}\"

AVAILABLE DYNAMIC TOOLS (Discovered from Registry):
{tools_context}

CRITICAL CONVERSATION CONTEXT & PRECEDENCE RULES:
- The CURRENT USER COMMAND ALWAYS takes absolute precedence over PREVIOUS CONVERSATION CONTEXT.
- NEVER copy, carry over, or blend task titles ('name') or descriptions ('desc') from previous conversation history into a new task command!
- If the current USER COMMAND defines a task (e.g. "Ask him to Checkin by 20 November"), the task title MUST be extracted from the current command ("Checkin"), NEVER from prior messages (like "client onboarding").

INSTRUCTIONS:
1. Identify the user intent (e.g., create_card, move_card, update_card, delete_card, search_cards, get_workload, get_employee_tasks).
2. Identify the target entity (e.g., card, task, report, employee).
3. Select the most relevant tool_id from AVAILABLE DYNAMIC TOOLS. If none match, set suggested_tool_id to null.
4. Extract parameters conforming to the selected tool's input_schema properties:
   - For listing or searching cards (e.g., 'trello_search_cards'):
     * 'list_name': If the user asks to view/show cards from a specific list or column (e.g. "show cards in the To Do list", "show Trello Starter Guide tasks", "show Today cards"), set 'list_name' to the requested list name (e.g. "To Do", "In-Review", "Doing", "Done", "Trello Starter Guide", "Today"). DO NOT put the list name in 'query'.
     * 'query': Specific keyword search query (e.g. "OAuth", "database"). Leave empty or omit if the user is asking to show cards from a list or column.
   - For task creation (e.g., 'trello_create_card'):
     * 'name': A clean, concise title/heading for the task:
       - If the user says "Create a task for <Person>. ... Ask him/her to <Action> by <Date>" (e.g. "Ask him to Checkin by 20 November"), the task title 'name' is the action requested: "Checkin" (or "Check In"), NOT the person's name, and NEVER prior topics from history!
       - If the user says "create a task card <Title>...", the title is <Title> (e.g. "Full Stack", "Backend", "JWT Authentication").
     * 'member_name': Name of team member or employee to assign or add to the card if mentioned in the command (e.g. "Yogesh", "Alex Rivera", "Jordan Lee").
     * 'desc': YOU MUST generate an informative, domain-relevant, and context-rich description directly related to the task heading/action (e.g. for "Backend", describe designing backend architecture, API endpoints, database interactions, schema validation, and unit test coverage; for "Frontend", describe building responsive UI components, state management, and accessibility; for "Auth", describe authentication workflows, token lifecycle, and route protection). CRITICAL: NEVER repeat or echo the user command prompt (DO NOT write things like "Create backend card with due date Thursday and assigned to..."). Formulate professional engineering and operational deliverables implied by the task title. If the user explicitly provided custom notes or specifications, incorporate them. NEVER leave 'desc' empty and NEVER pull descriptions from previous messages.
     * 'list_name': Target column name (defaults to "To Do" if unspecified).
     * 'priority': Task priority ("LOW", "MEDIUM", "HIGH", "URGENT").
     * 'due_date': Due date if mentioned.
   - For moving tasks (e.g., 'trello_move_card'):
     * 'card_name': The title of the card to move (e.g. "Login API", "Backend").
     * 'target_status': Destination list/column name (e.g. "In-Review", "Done").
   - For updating or assigning members to tasks (e.g., 'trello_update_card'):
     * 'card_name': The title or name of the existing card to find and update (e.g. "Login API", "Register Page").
     * 'member_name': Name or username of the team member to assign (e.g. "Alex Rivera").
     * 'new_title': Updated title if requested (e.g. updated title).
     * 'new_description': Updated description if requested.
     * 'new_due_date': Updated due date if requested.
     * 'board_name': The target board name if explicitly mentioned in the request (e.g. "My Trello Board", "mytrello board").
   - For deleting or archiving tasks (e.g., 'trello_delete_card', 'trello_archive_card'):
     * 'card_name': The title or name of the card to delete or archive (e.g. "Person 1", "Login API", "Backend"), OR the list name if the user asks to delete all tasks in a column/list (e.g. "Trello Starter Guide", "Today").
     * 'list_name': The column or list name if deleting tasks from a specific list (e.g. "Trello Starter Guide").
5. If the command is unclear or missing mandatory inputs, set requires_clarification to true.

Respond strictly with a JSON object in this exact schema:
{{
  "intent": "<intent_string>",
  "entity": "<entity_string>",
  "parameters": {{ <key>: <value> }},
  "suggested_tool_id": "<tool_id_or_null>",
  "requires_clarification": <true_or_false>,
  "clarification_message": "<clarification_or_null>",
  "confidence": <float_between_0.0_and_1.0>
}}
"""

