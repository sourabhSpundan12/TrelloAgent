import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from app.core.dependencies import get_current_user
from app.database.mongodb import get_database
from app.schemas.user import UserResponse
from app.services.template_service import TemplateService

logger = logging.getLogger(__name__)

router = APIRouter()


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Template display name")
    category: str = Field(default="CUSTOM", max_length=50, description="Template category")
    keywords: List[str] = Field(..., min_length=1, description="Trigger keywords matching card titles")
    description_template: str = Field(..., min_length=5, description="Template text supporting '{title}' placeholder")


class TemplateUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    category: Optional[str] = Field(None, max_length=50)
    keywords: Optional[List[str]] = None
    description_template: Optional[str] = Field(None, min_length=5)


@router.get(
    "",
    status_code=status.HTTP_200_OK,
    summary="List all task description templates",
    description="Returns built-in domain templates along with custom user-defined templates.",
)
async def list_templates(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    templates = await TemplateService.list_templates(db)
    return {
        "status": "SUCCESS",
        "templates": templates,
        "total": len(templates),
    }


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new custom task template",
    description="Registers a new template that matches specified keywords and generates customized card descriptions.",
)
async def create_template(
    payload: TemplateCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    doc = await TemplateService.create_template(
        db=db,
        name=payload.name,
        category=payload.category,
        keywords=payload.keywords,
        description_template=payload.description_template,
        user_id=current_user.id,
        user_email=current_user.email,
    )
    return {
        "status": "SUCCESS",
        "message": f"Template '{payload.name}' created successfully.",
        "template": doc,
    }


@router.put(
    "/{template_id}",
    status_code=status.HTTP_200_OK,
    summary="Update a custom task template",
)
async def update_template(
    template_id: str,
    payload: TemplateUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    updated = await TemplateService.update_template(
        db=db,
        template_id=template_id,
        name=payload.name,
        category=payload.category,
        keywords=payload.keywords,
        description_template=payload.description_template,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or built-in templates cannot be edited directly.",
        )
    return {
        "status": "SUCCESS",
        "message": "Template updated successfully.",
        "template": updated,
    }


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a custom task template",
)
async def delete_template(
    template_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> Dict[str, Any]:
    deleted = await TemplateService.delete_template(db=db, template_id=template_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found or built-in templates cannot be deleted.",
        )
    return {
        "status": "SUCCESS",
        "message": "Custom template deleted successfully.",
        "deleted_id": template_id,
    }
