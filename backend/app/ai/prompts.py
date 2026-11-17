import json
from typing import Any, Dict, List, Optional
from langchain_core.prompts import ChatPromptTemplate
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
    """Builds the prompt provided to the LLM for intent extraction."""
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
- Previous conversation context is ONLY for resolving references like 'it', 'that card', or 'confirm'.
- If the current USER COMMAND defines a task (e.g. "Ask him to Checkin by 20 November"), the task title MUST be extracted from the current command ("Checkin"), NEVER from prior messages (like "client onboarding").

INSTRUCTIONS:
1. Identify the user intent (e.g., create_card, create_list, move_card, update_card, delete_card, search_cards, get_workload, get_employee_tasks).
2. Identify the target entity (e.g., card, task, list, report, employee).
3. Select the most relevant tool_id from AVAILABLE DYNAMIC TOOLS. If none match, set suggested_tool_id to null.
4. Extract parameters conforming to the selected tool's input_schema properties:
   - For listing or searching cards (e.g., 'trello_search_cards'):
     * 'list_name': If the user asks to view/show cards in a specific list (e.g. "show cards in the To Do list", "list cards in In-Review"), set 'list_name' to the requested list name (e.g. "To Do", "In-Review", "Doing", "Done"). DO NOT put the list name in 'query'.
     * 'query': Specific keyword search query (e.g. "OAuth", "database"). Leave empty or omit if the user is asking to show all cards in a list.
   - For list creation (e.g., 'trello_create_list'):
     * 'name': The name of the new column or list to create (e.g. "In-Review", "Backlog", "Testing").
   - For task creation (e.g., 'trello_create_card'):
     * 'name': A clean, concise title/heading for the task:
       - If the user says "Create a task for <Person>. ... Ask him/her to <Action> by <Date>" (e.g. "Ask him to Checkin by 20 November"), the task title 'name' is the action requested: "Checkin" (or "Check In"), NOT the person's name, and NEVER prior topics from history!
       - If the user says "create a task card <Title>...", the title is <Title> (e.g. "Full Stack", "Backend", "JWT Authentication").
     * 'member_name': Name of team member or employee to assign or add to the card if mentioned in the command (e.g. "Yogesh", "Alex Rivera", "Jordan Lee").
     * 'desc': YOU MUST generate an informative, domain-relevant, and context-rich description directly related to the task heading/action (e.g. for "Backend", describe designing backend architecture, API endpoints, database interactions, schema validation, and unit test coverage; for "Frontend", describe building responsive UI components, state management, and accessibility; for "Auth", describe authentication workflows, token lifecycle, and route protection). CRITICAL: NEVER repeat or echo the user command prompt (DO NOT write things like "Create backend card with due date Thursday and assigned to..."). Formulate professional engineering and operational deliverables implied by the task title. If the user explicitly provided custom notes or specifications, incorporate them. NEVER leave 'desc' empty and NEVER pull descriptions from previous messages.
     * 'list_name': Target column name (e.g. "To Do", "Doing", "In-Review", "Testing", defaults to "To Do" if unspecified).
     * 'priority': Task priority ("LOW", "MEDIUM", "HIGH", "URGENT").
     * 'due_date': Due date if mentioned in the command (e.g. "21 November 2026", "tomorrow", "next Friday", "2026-11-20").
   - For moving tasks (e.g., 'trello_move_card'):
     * 'card_name': The exact name or title of the card to move (e.g. "Backend", "Login API").
     * 'target_status': The EXACT destination list name requested by the user (e.g. "Testing", "In-Review", "To Do", "Doing", "Done", or any custom list name). NEVER coerce custom list names into other predefined statuses.
     * 'due_date': Due date or deadline if mentioned in the command (e.g. "tomorrow", "next Friday", "2026-11-20").
     * 'description': Any additional notes, description, or instructions to update on the card.
   - For updating or assigning members to tasks (e.g., 'trello_update_card'):
     * 'card_name': The title or name of the existing card to find and update (e.g. "Register Page", "Register", "Login API", "Backend").
     * 'member_name': Name or username of the team member or employee to assign or add to the card (e.g. "Alex Rivera"). NOTE: When the user says "on <card> add member <person>" or "assign <person> to <card>" or "add <person> to <card>", this is ALWAYS an 'update_card' intent using 'trello_update_card', NOT 'create_card'!
     * 'new_title': Updated title if requested.
     * 'new_description': Updated description if requested.
     * 'new_due_date': Updated due date if requested.
   - For deleting or archiving tasks (e.g., 'trello_delete_card', 'trello_archive_card'):
     * 'card_name': The title or name of the card to delete or archive (e.g. "Person 1", "Login API", "Backend").
5. If the command is unclear or missing mandatory inputs, set requires_clarification to true.

Respond strictly with a JSON object conforming to the schema.
"""


def get_langchain_prompt_template() -> ChatPromptTemplate:
    """Constructs a LangChain ChatPromptTemplate for structured intent extraction."""
    return ChatPromptTemplate.from_messages([
        ("system", SYSTEM_INSTRUCTION),
        ("human", """Analyze the following user command and extract the structured intent.

USER COMMAND:
"{command}"

AVAILABLE DYNAMIC TOOLS (Discovered from Registry):
{tools_context}

INSTRUCTIONS:
1. Identify the user intent (e.g., create_card, create_list, move_card, update_card, delete_card, search_cards, get_workload, get_employee_tasks).
2. Identify the target entity (e.g., card, task, list, report, employee).
3. Select the most relevant tool_id from AVAILABLE DYNAMIC TOOLS. If none match, set suggested_tool_id to null.
4. Extract parameters conforming to the selected tool's input_schema properties:
   - For listing or searching cards (e.g., 'trello_search_cards'):
     * 'list_name': If the user asks to view/show cards in a specific list (e.g. "show cards in the To Do list", "list cards in In-Review"), set 'list_name' to the requested list name (e.g. "To Do", "In-Review", "Doing", "Done"). DO NOT put the list name in 'query'.
     * 'query': Specific keyword search query (e.g. "OAuth", "database"). Leave empty or omit if the user is asking to show all cards in a list.
   - For list creation (e.g., 'trello_create_list'):
     * 'name': The name of the new column or list to create (e.g. "In-Review", "Backlog", "Testing").
   - For task creation (e.g., 'trello_create_card'):
     * 'name': A clean, concise title/heading for the task (e.g. "Full Stack", "Backend", "JWT Authentication"). Note: If the user says "create a task card <Title>...", the title is <Title>!
     * 'member_name': Name of team member or employee to assign or add to the card if mentioned in the command (e.g. "Alex Rivera", "Jordan Lee").
     * 'desc': YOU MUST ALWAYS generate an informative, professional description directly related to the task heading/topic. Detail key objectives, deliverables, and implementation scope for this specific task. If the user provides additional information or description in their message, include it in 'desc'. NEVER leave 'desc' empty and NEVER use a generic placeholder like "Task created via assistant".
     * 'list_name': Target column name (e.g. "To Do", "Doing", "In-Review", "Testing", defaults to "To Do" if unspecified).
     * 'priority': Task priority ("LOW", "MEDIUM", "HIGH", "URGENT").
     * 'due_date': Due date if mentioned in the command (e.g. "21 November 2026", "tomorrow", "next Friday", "2026-11-20").
   - For moving tasks (e.g., 'trello_move_card'):
     * 'card_name': The exact name or title of the card to move (e.g. "Backend", "Login API").
     * 'target_status': The EXACT destination list name requested by the user (e.g. "Testing", "In-Review", "To Do", "Doing", "Done", or any custom list name). NEVER coerce custom list names into other predefined statuses.
     * 'due_date': Due date or deadline if mentioned in the command (e.g. "tomorrow", "next Friday", "2026-11-20").
     * 'description': Any additional notes, description, or instructions to update on the card.
   - For updating or assigning members to tasks (e.g., 'trello_update_card'):
     * 'card_name': The title or name of the existing card to find and update (e.g. "Register Page", "Register", "Login API", "Backend").
     * 'member_name': Name or username of the team member or employee to assign or add to the card (e.g. "Alex Rivera"). NOTE: When the user says "on <card> add member <person>" or "assign <person> to <card>" or "add <person> to <card>", this is ALWAYS an 'update_card' intent using 'trello_update_card', NOT 'create_card'!
     * 'new_title': Updated title if requested.
     * 'new_description': Updated description if requested.
     * 'new_due_date': Updated due date if requested.
   - For deleting or archiving tasks (e.g., 'trello_delete_card', 'trello_archive_card'):
     * 'card_name': The title or name of the card to delete or archive (e.g. "Person 1", "Login API", "Backend").
5. If the command is unclear or missing mandatory inputs, set requires_clarification to true.
"""),
    ])
