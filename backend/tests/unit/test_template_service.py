import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.template_service import TemplateService, BUILTIN_TEMPLATES


@pytest.mark.asyncio
async def test_list_builtin_templates():
    templates = await TemplateService.list_templates(db=None)
    assert len(templates) == len(BUILTIN_TEMPLATES)
    assert any(t["id"] == "tmpl_auth" for t in templates)
    assert any(t["category"] == "BACKEND" for t in templates)


@pytest.mark.asyncio
async def test_match_template_for_title_builtin():
    # Login card should match auth template
    desc = await TemplateService.match_template_for_title("LoginAPI", db=None)
    assert "Implement secure authentication workflows" in desc
    assert "LoginAPI" in desc

    # Database card
    desc_db = await TemplateService.match_template_for_title("MongoDB Atlas Setup", db=None)
    assert "Design and optimize data models" in desc_db
    assert "MongoDB Atlas Setup" in desc_db

    # Fallback to general template
    desc_fallback = await TemplateService.match_template_for_title("Something Unrelated XYZ", db=None)
    assert "Plan, implement, and verify deliverables for 'Something Unrelated XYZ'" in desc_fallback


@pytest.mark.asyncio
async def test_custom_template_priority():
    mock_db = MagicMock()
    mock_cursor = MagicMock()

    custom_doc = {
        "id": "tmpl_custom_payment",
        "name": "Payment Gateway Integration",
        "category": "PAYMENT",
        "keywords": ["stripe", "payment", "razorpay"],
        "description_template": "Integrate secure payment processing and webhook reconciliation for '{title}'.",
        "is_builtin": False,
    }

    async def async_iter():
        yield custom_doc

    mock_cursor.__aiter__ = lambda self: async_iter()
    mock_cursor.sort.return_value = mock_cursor
    mock_db.__getitem__.return_value.find.return_value = mock_cursor

    # Match custom keyword
    desc = await TemplateService.match_template_for_title("Stripe Checkout Flow", db=mock_db)
    assert "Integrate secure payment processing" in desc
    assert "Stripe Checkout Flow" in desc


@pytest.mark.asyncio
async def test_crud_template():
    mock_db = MagicMock()
    mock_col = MagicMock()
    mock_db.__getitem__.return_value = mock_col
    mock_col.insert_one = AsyncMock()

    # Create
    created = await TemplateService.create_template(
        db=mock_db,
        name="Custom Webhook",
        category="INTEGRATION",
        keywords=["webhook", "events"],
        description_template="Configure webhook receiver for '{title}'.",
        user_id="usr-123",
        user_email="admin@test.com",
    )
    assert created["name"] == "Custom Webhook"
    assert created["category"] == "INTEGRATION"
    assert "webhook" in created["keywords"]
    assert created["is_builtin"] is False
    assert mock_col.insert_one.called

    # Delete
    mock_col.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    deleted = await TemplateService.delete_template(db=mock_db, template_id="tmpl_custom_123")
    assert deleted is True

