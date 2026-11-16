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

INSTRUCTIONS:
1. Identify the user intent (e.g., create_card, move_card, update_card, delete_card, search_cards, get_workload, get_employee_tasks).
2. Identify the target entity (e.g., card, task, report, employee).
3. Select the most relevant tool_id from AVAILABLE DYNAMIC TOOLS. If none match, set suggested_tool_id to null.
4. Extract parameters conforming to the selected tool's input_schema properties:
   - For task creation (e.g., 'trello_create_card'):
     * 'name': A clean, concise title/heading for the task (e.g. "Full Stack", "Backend", "JWT Authentication"). Note: If the user says "create a task card <Title>...", the title is <Title>!
     * 'member_name': Name of team member or employee to assign or add to the card if mentioned in the command (e.g. "Alex Rivera", "Jordan Lee").
     * 'desc': YOU MUST ALWAYS generate an informative, professional description directly related to the task heading/topic. Detail key objectives, deliverables, and implementation scope for this specific task. NEVER leave 'desc' empty and NEVER use a generic placeholder like "Task created via assistant".
     * 'list_name': Target column name (defaults to "To Do" if unspecified).
     * 'priority': Task priority ("LOW", "MEDIUM", "HIGH", "URGENT").
     * 'due_date': Due date if mentioned.
   - For deleting or archiving tasks (e.g., 'trello_delete_card', 'trello_archive_card'):
     * 'card_name': The title or name of the card to delete or archive (e.g. "Person 1", "Login API", "Backend").
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

