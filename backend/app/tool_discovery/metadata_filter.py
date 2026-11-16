from typing import Any, Dict, List, Optional
from app.tool_discovery.interfaces import BaseMetadataFilter


class MetadataFilter(BaseMetadataFilter):
    """Filters tools by enabled status, category, capability, and user role permissions."""

    def filter(
        self,
        tools: List[Dict[str, Any]],
        user_role: Optional[str] = None,
        category: Optional[str] = None,
        required_capabilities: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []

        norm_role = user_role.upper() if user_role else None
        norm_category = category.lower() if category else None
        norm_caps = set(c.lower() for c in (required_capabilities or []))

        for tool in tools:
            # 1. Enabled status: Disabled tools must NEVER be discoverable
            if not tool.get("enabled", True):
                continue

            # 2. Category filtering
            if norm_category:
                tool_cat = str(tool.get("category", "")).lower()
                if tool_cat != norm_category:
                    continue

            # 3. User Permission / Role filtering
            if norm_role and norm_role != "ADMIN":
                tool_perms = [str(p).upper() for p in tool.get("permissions", [])]
                if tool_perms and "*" not in tool_perms and norm_role not in tool_perms:
                    continue

            # 4. Capability filtering
            if norm_caps:
                tool_caps = set(str(c).lower() for c in tool.get("capabilities", []))
                if not norm_caps.intersection(tool_caps):
                    continue

            filtered.append(tool)

        return filtered

