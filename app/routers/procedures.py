from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Procedure,
    ProcedureStep,
    RequiredDocument,
    LegalReference
)


def summarize_procedure(procedure: Procedure) -> dict:
    return {
        "procedure_code": procedure.procedure_code,
        "name": procedure.name,
        "category": procedure.category,
        "authority": procedure.authority,
        "source_url": procedure.source_url,
    }


router = APIRouter(
    prefix="/api/procedures",
    tags=["Procedures"]
)


@router.get("")
def get_procedures(
    db: Session = Depends(get_db)
):
    procedures = (
        db.query(Procedure)
        .order_by(Procedure.procedure_code)
        .all()
    )

    return [summarize_procedure(item) for item in procedures]


@router.get("/search")
def search_procedures(
    q: str,
    db: Session = Depends(get_db)
):
    keyword = f"%{q}%"

    results = db.query(Procedure).filter(
        (Procedure.name.like(keyword)) |
        (Procedure.category.like(keyword)) |
        (Procedure.description.like(keyword))
    ).all()

    return [summarize_procedure(item) for item in results]


@router.get("/{procedure_code}")
def get_procedure_detail(
    procedure_code: str,
    db: Session = Depends(get_db)
):
    procedure = (
        db.query(Procedure)
        .filter(
            Procedure.procedure_code == procedure_code
        )
        .first()
    )

    if procedure is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy thủ tục"
        )

    steps = (
        db.query(ProcedureStep)
        .filter(
            ProcedureStep.procedure_id == procedure.id
        )
        .order_by(ProcedureStep.step_no)
        .all()
    )

    documents = (
        db.query(RequiredDocument)
        .filter(
            RequiredDocument.procedure_id == procedure.id
        )
        .order_by(RequiredDocument.id)
        .all()
    )

    legal_references = (
        db.query(LegalReference)
        .filter(
            LegalReference.procedure_id == procedure.id
        )
        .order_by(LegalReference.id)
        .all()
    )

    return {
        "procedure": {
            "id": procedure.id,
            "procedure_code": procedure.procedure_code,
            "name": procedure.name,
            "category": procedure.category,
            "target": procedure.target,
            "description": procedure.description,
            "conditions": procedure.conditions,
            "authority": procedure.authority,
            "processing_time": procedure.processing_time,
            "fee": procedure.fee,
            "result": procedure.result,
            "source_url": procedure.source_url,
            "source_title": procedure.source_title,
            "last_verified_at": procedure.last_verified_at,
            "status": procedure.status
        },

        "steps": [
            {
                "step_no": step.step_no,
                "action": step.action,
                "responsible_unit": step.responsible_unit,
                "note": step.note
            }
            for step in steps
        ],

        "required_documents": [
            {
                "document_name": document.document_name,
                "is_required": document.is_required,
                "quantity": document.quantity,
                "document_type": document.document_type,
                "applicable_condition": document.applicable_condition,
                "form_url": document.form_url,
                "note": document.note
            }
            for document in documents
        ],

        "legal_references": [
            {
                "document_number": legal.document_number,
                "document_name": legal.document_name,
                "document_type": legal.document_type,
                "article_reference": legal.article_reference,
                "source_url": legal.source_url,
                "effective_date": legal.effective_date,
                "note": legal.note
            }
            for legal in legal_references
        ]
    }