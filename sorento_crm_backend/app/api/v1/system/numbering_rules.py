"""Document numbering rules API."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.services.numbering_service import NumberingService
from app.schemas.numbering import DocumentNumberingRuleResponse, DocumentNumberingRuleUpdate

router = APIRouter()


@router.get("/numbering-rules", response_model=list[DocumentNumberingRuleResponse])
async def list_numbering_rules(
    current_user: dict = Depends(require_permission("system.numbering_rules.view")),
    db: Session = Depends(get_db),
):
    """List all document numbering rules."""
    service = NumberingService(db)
    rules = service.list_rules()
    return [DocumentNumberingRuleResponse.model_validate(r) for r in rules]


@router.get("/numbering-rules/{doc_type}", response_model=DocumentNumberingRuleResponse)
async def get_numbering_rule(
    doc_type: str,
    current_user: dict = Depends(require_permission("system.numbering_rules.view")),
    db: Session = Depends(get_db),
):
    """Get a single numbering rule by doc_type."""
    service = NumberingService(db)
    rule = service.get_rule(doc_type)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Numbering rule not found")
    return DocumentNumberingRuleResponse.model_validate(rule)


@router.patch("/numbering-rules/{doc_type}", response_model=DocumentNumberingRuleResponse)
async def update_numbering_rule(
    doc_type: str,
    payload: DocumentNumberingRuleUpdate,
    current_user: dict = Depends(require_permission("system.numbering_rules.edit")),
    db: Session = Depends(get_db),
):
    """Update a numbering rule. Only provided fields are updated."""
    service = NumberingService(db)
    data = payload.model_dump(exclude_unset=True)
    rule = service.update_rule(
        doc_type,
        enabled=data.get("enabled"),
        prefix_template=data.get("prefix_template"),
        number_digits=data.get("number_digits"),
        next_value=data.get("next_value"),
        start_value=data.get("start_value"),
        reset_policy=data.get("reset_policy"),
    )
    return DocumentNumberingRuleResponse.model_validate(rule)
