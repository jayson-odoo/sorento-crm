from datetime import datetime

from app.schemas.forms import FormCreate, FormResponse, FormUpdate


def test_form_create_and_update_accept_access_levels():
    created = FormCreate(
        code="TEST_FORM",
        name="Test Form",
        form_type="marketing",
        language="en",
        access_levels=["dealer", "end_user"],
    )
    updated = FormUpdate(access_levels=["dealer"])

    assert created.access_levels == ["dealer", "end_user"]
    assert updated.access_levels == ["dealer"]


def test_form_response_returns_access_levels_and_form_type():
    response = FormResponse.model_validate(
        {
            "id": "form-id",
            "code": "TEST_FORM",
            "name": "Test Form",
            "form_type": "service",
            "purpose": None,
            "language": "en",
            "version": 1,
            "is_active": True,
            "attachment_id": None,
            "access_levels": ["sorento_office"],
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 2),
            "attachment": None,
        }
    )

    assert response.form_type == "service"
    assert response.access_levels == ["sorento_office"]
