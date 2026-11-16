import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.tool_registry.models import ToolModel


def compute_schema_fingerprint(schema: Dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 hash of a JSON Schema dictionary for drift detection."""
    try:
        canonical = json.dumps(schema or {}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except Exception:
        return hashlib.sha256(str(schema).encode("utf-8")).hexdigest()


class MCPToolAdapter:
    """
    Translates raw MCP tools discovered over the protocol into internal ToolModel instances
    with namespacing, fingerprinting, and execution routing metadata.
    """

    @staticmethod
    def extract_terms(text: str) -> List[str]:
        """Extracts unique clean lowercase tokens for keywords and synonyms."""
        words = re.findall(r"[a-zA-Z0-9]+", text.lower())
        stop_words = {"the", "a", "an", "and", "or", "to", "for", "in", "of", "on", "at", "by", "is", "with"}
        return [w for w in set(words) if len(w) > 2 and w not in stop_words]

    @classmethod
    def adapt_to_tool_model(
        cls,
        mcp_tool: Any,
        server_doc: Dict[str, Any],
        approval_required: bool = False,
    ) -> ToolModel:
        server_id = server_doc.get("server_id", "mcp")
        transport_type = server_doc.get("transport_type", "streamable_http")

        # Extract attributes from either object or dict
        if hasattr(mcp_tool, "name"):
            remote_name = mcp_tool.name
            description = getattr(mcp_tool, "description", None) or f"MCP remote tool {remote_name}"
            input_schema = getattr(mcp_tool, "input_schema", None) or getattr(mcp_tool, "inputSchema", None) or {}
        elif isinstance(mcp_tool, dict):
            remote_name = mcp_tool.get("name", "")
            description = mcp_tool.get("description") or f"MCP remote tool {remote_name}"
            input_schema = mcp_tool.get("input_schema") or mcp_tool.get("inputSchema") or {}
        else:
            remote_name = str(getattr(mcp_tool, "name", "unknown_tool"))
            description = str(getattr(mcp_tool, "description", ""))
            input_schema = {}

        if hasattr(input_schema, "model_dump"):
            input_schema = input_schema.model_dump()
        elif not isinstance(input_schema, dict):
            input_schema = {"type": "object", "properties": {}}

        # Ensure valid JSON Schema
        if "type" not in input_schema:
            input_schema["type"] = "object"
        if "properties" not in input_schema:
            input_schema["properties"] = {}

        namespaced_tool_id = f"mcp.{server_id}.{remote_name}"
        human_name = f"[{server_id.upper()}] {remote_name.replace('_', ' ').title()}"

        # Extract keywords and capabilities
        keywords = list(set([server_id, remote_name] + cls.extract_terms(remote_name) + cls.extract_terms(description)))
        capabilities = [remote_name] + [k for k in keywords if len(k) > 3][:5]
        synonyms = [f"{remote_name} tool", f"{server_id} {remote_name}"]

        # Infer category
        category = "mcp"
        if "trello" in server_id or any(k in remote_name.lower() for k in ["trello", "card", "board", "list"]):
            category = "trello"
        elif "report" in server_id or "metric" in remote_name:
            category = "reporting"
        elif "employee" in server_id or "user" in remote_name:
            category = "employee"

        fingerprint = compute_schema_fingerprint(input_schema)
        now = datetime.now(timezone.utc)

        return ToolModel(
            tool_id=namespaced_tool_id,
            name=human_name,
            description=description,
            category=category,
            keywords=keywords,
            synonyms=synonyms,
            capabilities=capabilities,
            input_schema=input_schema,
            permissions=["EMPLOYEE", "MANAGER", "ADMIN"],
            executor_type="mcp",
            executor_key=namespaced_tool_id,
            version="1.0.0",
            enabled=True,
            approval_required=approval_required,
            source_type="MCP",
            source_id=server_id,
            remote_tool_name=remote_name,
            server_identifier=server_id,
            transport_type=transport_type,
            schema_fingerprint=fingerprint,
            last_discovered_at=now,
            created_at=now,
            updated_at=now,
        )

