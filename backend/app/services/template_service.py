import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

BUILTIN_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "tmpl_auth",
        "name": "Authentication & Security",
        "category": "SECURITY",
        "keywords": ["auth", "login", "register", "signup", "password", "jwt", "oauth"],
        "description_template": (
            "Implement secure authentication workflows, credential hashing, token lifecycle, and session verification for '{title}'. "
            "Enforce role-based access control, route protection, and security audit compliance."
        ),
        "is_builtin": True,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "tmpl_backend",
        "name": "Backend & API Development",
        "category": "BACKEND",
        "keywords": ["backend", "server", "api", "endpoint", "microservice", "fullstack", "full stack", "full-stack"],
        "description_template": (
            "Design, develop, and test backend architecture, API endpoints, database interactions, "
            "and business logic for '{title}'. Ensure robust error handling, schema validation, "
            "performance optimization, and comprehensive unit test coverage."
        ),
        "is_builtin": True,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "tmpl_frontend",
        "name": "Frontend & UI Engineering",
        "category": "FRONTEND",
        "keywords": ["frontend", "ui", "ux", "web", "react", "view", "interface", "page"],
        "description_template": (
            "Build and refine responsive user interface components and client-side interactions for '{title}'. "
            "Ensure accessibility standards, seamless backend API integration, state management, and cross-browser reliability."
        ),
        "is_builtin": True,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "tmpl_database",
        "name": "Database & Data Modeling",
        "category": "DATABASE",
        "keywords": ["database", "db", "mongo", "postgres", "sql", "migration", "schema"],
        "description_template": (
            "Design and optimize data models, collections, indexes, and persistence layers for '{title}'. "
            "Ensure transactional integrity, migration reliability, query efficiency, and backup readiness."
        ),
        "is_builtin": True,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "tmpl_testing",
        "name": "Testing & Quality Assurance",
        "category": "QA",
        "keywords": ["test", "testing", "qa", "e2e", "integration test"],
        "description_template": (
            "Develop and execute automated test suites, end-to-end verification, and edge-case assertions for '{title}'. "
            "Identify potential defects, verify regression safety, and validate system stability under expected workloads."
        ),
        "is_builtin": True,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "tmpl_devops",
        "name": "DevOps & Cloud Infrastructure",
        "category": "DEVOPS",
        "keywords": ["deploy", "devops", "docker", "k8s", "kubernetes", "ci", "cd", "pipeline", "infrastructure"],
        "description_template": (
            "Configure deployment infrastructure, build pipelines, environment variables, and health monitoring for '{title}'. "
            "Ensure zero-downtime rollouts, security hardening, and operational observability."
        ),
        "is_builtin": True,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "tmpl_review",
        "name": "Sprint Review & Status Sync",
        "category": "PROJECT_MANAGEMENT",
        "keywords": ["checkin", "status", "standup", "sync", "review"],
        "description_template": (
            "Conduct milestone progress review and status synchronization for '{title}'. "
            "Track sprint deliverables against timeline, align dependencies, and document action items."
        ),
        "is_builtin": True,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "tmpl_bugfix",
        "name": "Bug Fix & Remediation",
        "category": "MAINTENANCE",
        "keywords": ["bug", "fix", "issue", "error", "hotfix"],
        "description_template": (
            "Investigate root cause of reported issue in '{title}', develop and test code fix, and verify regression safety before deploying to production."
        ),
        "is_builtin": True,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "tmpl_docs",
        "name": "Technical Documentation",
        "category": "DOCUMENTATION",
        "keywords": ["doc", "docs", "documentation", "guide", "readme"],
        "description_template": (
            "Author and update technical documentation, system specifications, architectural diagrams, and user guidelines for '{title}'."
        ),
        "is_builtin": True,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
    {
        "id": "tmpl_general",
        "name": "General Task Deliverables",
        "category": "GENERAL",
        "keywords": ["general", "task", "milestone"],
        "description_template": (
            "Plan, implement, and verify deliverables for '{title}'. "
            "Review project requirements, execute core development milestones, and validate against quality and acceptance standards."
        ),
        "is_builtin": True,
        "created_at": "2026-01-01T00:00:00.000Z",
    },
]


class TemplateService:
    """Service for managing built-in and custom task description templates."""

    @classmethod
    async def list_templates(cls, db: Optional[AsyncIOMotorDatabase] = None) -> List[Dict[str, Any]]:
        """Returns all templates: built-in templates + user-created custom templates from MongoDB."""
        templates = [dict(t) for t in BUILTIN_TEMPLATES]

        if db is not None:
            try:
                cursor = db["task_templates"].find().sort("created_at", -1)
                async for doc in cursor:
                    doc.pop("_id", None)
                    templates.insert(0, doc)
            except Exception as e:
                logger.warning(f"Could not load custom task templates: {e}")

        return templates

    @classmethod
    async def create_template(
        cls,
        db: AsyncIOMotorDatabase,
        name: str,
        category: str,
        keywords: List[str],
        description_template: str,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a new custom template in MongoDB."""
        now = datetime.now(timezone.utc).isoformat()
        template_id = f"tmpl_custom_{uuid.uuid4().hex[:8]}"

        clean_keywords = [k.strip().lower() for k in keywords if k and k.strip()]
        if not clean_keywords:
            clean_keywords = [name.strip().lower()]

        doc = {
            "id": template_id,
            "name": name.strip(),
            "category": (category or "CUSTOM").upper().strip(),
            "keywords": clean_keywords,
            "description_template": description_template.strip(),
            "is_builtin": False,
            "created_by_user_id": user_id,
            "created_by_email": user_email,
            "created_at": now,
            "updated_at": now,
        }

        await db["task_templates"].insert_one(doc)
        doc.pop("_id", None)
        return doc

    @classmethod
    async def update_template(
        cls,
        db: AsyncIOMotorDatabase,
        template_id: str,
        name: Optional[str] = None,
        category: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        description_template: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Updates an existing custom template."""
        update_fields: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if name:
            update_fields["name"] = name.strip()
        if category:
            update_fields["category"] = category.upper().strip()
        if keywords is not None:
            update_fields["keywords"] = [k.strip().lower() for k in keywords if k and k.strip()]
        if description_template:
            update_fields["description_template"] = description_template.strip()

        res = await db["task_templates"].find_one_and_update(
            {"id": template_id, "is_builtin": {"$ne": True}},
            {"$set": update_fields},
            return_document=True,
        )
        if res:
            res.pop("_id", None)
        return res

    @classmethod
    async def delete_template(cls, db: AsyncIOMotorDatabase, template_id: str) -> bool:
        """Deletes a custom template from MongoDB."""
        res = await db["task_templates"].delete_one({"id": template_id, "is_builtin": {"$ne": True}})
        return res.deleted_count > 0

    @classmethod
    async def find_matching_template(
        cls,
        text: str,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Finds the most relevant task description template for a given command or card title.
        Checks custom templates from MongoDB first, then built-in domain templates.
        Returns None if no relevant template matches (enforcing 'never select an unrelated template').
        """
        if not text or not text.strip():
            return None

        clean_text = text.strip()
        t_lower = clean_text.lower()

        # 1. Check custom templates from MongoDB
        if db is not None:
            try:
                cursor = db["task_templates"].find().sort("created_at", -1)
                async for doc in cursor:
                    kws = doc.get("keywords", [])
                    if any(re.search(r"\b" + re.escape(k.lower()) + r"\b", t_lower) or k.lower() in t_lower for k in kws):
                        doc_copy = dict(doc)
                        doc_copy.pop("_id", None)
                        return doc_copy
            except Exception as e:
                logger.debug(f"Error checking custom templates in DB: {e}")

        # 2. Check built-in domain templates (excluding tmpl_general)
        for b_tmpl in BUILTIN_TEMPLATES:
            if b_tmpl["id"] == "tmpl_general":
                continue
            kws = b_tmpl.get("keywords", [])
            for k in kws:
                # Word-boundary or substring match for technical keywords
                if re.search(r"\b" + re.escape(k.lower()) + r"\b", t_lower) or (len(k) > 3 and k.lower() in t_lower):
                    return dict(b_tmpl)

        return None

    @classmethod
    async def select_and_format_template(
        cls,
        title: str,
        db: Optional[AsyncIOMotorDatabase] = None,
        allow_fallback: bool = False,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Selects the best template and generates a professional description populated with the title.
        Returns: (template_id, populated_description).
        If no specific template matches:
          - If allow_fallback is True, uses General Task template ('tmpl_general').
          - Otherwise returns (None, None) so unrelated templates are never selected.
        """
        matched = await cls.find_matching_template(title, db=db)
        if matched:
            tmpl_str = matched.get("description_template", "")
            desc = tmpl_str.replace("{title}", title.strip())
            return matched.get("id"), desc

        if allow_fallback:
            general_tmpl = BUILTIN_TEMPLATES[-1]
            desc = general_tmpl["description_template"].replace("{title}", title.strip())
            return general_tmpl["id"], desc

        return None, None

    @classmethod
    async def match_template_for_title(
        cls,
        title: str,
        db: Optional[AsyncIOMotorDatabase] = None,
    ) -> Optional[str]:
        """
        Finds the best matching template description for a given card title.
        Prioritizes user-created custom templates from MongoDB before built-in defaults.
        """
        clean_title = title.strip()
        t_lower = clean_title.lower()

        # 1. Check custom templates from MongoDB
        if db is not None:
            try:
                cursor = db["task_templates"].find().sort("created_at", -1)
                async for doc in cursor:
                    kws = doc.get("keywords", [])
                    if any(k in t_lower for k in kws):
                        tmpl = doc.get("description_template", "")
                        if tmpl:
                            return tmpl.replace("{title}", clean_title)
            except Exception as e:
                logger.debug(f"Error checking custom templates in DB: {e}")

        # 2. Check built-in templates
        for b_tmpl in BUILTIN_TEMPLATES:
            if b_tmpl["id"] == "tmpl_general":
                continue
            kws = b_tmpl.get("keywords", [])
            if any(k in t_lower for k in kws):
                return b_tmpl["description_template"].replace("{title}", clean_title)

        # Fallback to general template
        return BUILTIN_TEMPLATES[-1]["description_template"].replace("{title}", clean_title)
