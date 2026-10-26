from datetime import datetime, timezone


def utc_now() -> datetime:
    """Giờ UTC hiện tại (dạng naive, giống giá trị cũ của datetime.utcnow)."""

    return datetime.now(timezone.utc).replace(tzinfo=None)

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from app.database import Base


class Procedure(Base):
    __tablename__ = "procedures"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    procedure_code = Column(
        Text,
        nullable=True,
    )

    name = Column(
        Text,
        nullable=False,
    )

    category = Column(
        Text,
        nullable=False,
    )

    target = Column(
        Text,
        nullable=True,
    )

    description = Column(
        Text,
        nullable=True,
    )

    conditions = Column(
        Text,
        nullable=True,
    )

    authority = Column(
        Text,
        nullable=True,
    )

    method = Column(
        Text,
        nullable=True,
    )

    processing_time = Column(
        Text,
        nullable=True,
    )

    fee = Column(
        Text,
        nullable=True,
    )

    result = Column(
        Text,
        nullable=True,
    )

    source_url = Column(
        Text,
        nullable=False,
    )

    source_title = Column(
        Text,
        nullable=True,
    )

    last_verified_at = Column(
        Text,
        nullable=True,
    )

    status = Column(
        Text,
        nullable=True,
    )


class ProcedureStep(Base):
    __tablename__ = "procedure_steps"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    procedure_id = Column(
        Integer,
        ForeignKey("procedures.id"),
        nullable=False,
    )

    step_no = Column(
        Integer,
        nullable=False,
    )

    action = Column(
        Text,
        nullable=False,
    )

    responsible_unit = Column(
        Text,
        nullable=True,
    )

    note = Column(
        Text,
        nullable=True,
    )


class RequiredDocument(Base):
    __tablename__ = "required_documents"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    procedure_id = Column(
        Integer,
        ForeignKey("procedures.id"),
        nullable=False,
    )

    document_name = Column(
        Text,
        nullable=False,
    )

    is_required = Column(
        Integer,
        default=1,
    )

    quantity = Column(
        Integer,
        nullable=True,
    )

    document_type = Column(
        Text,
        nullable=True,
    )

    applicable_condition = Column(
        Text,
        nullable=True,
    )

    form_url = Column(
        Text,
        nullable=True,
    )

    note = Column(
        Text,
        nullable=True,
    )


class LegalReference(Base):
    __tablename__ = "legal_references"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    procedure_id = Column(
        Integer,
        ForeignKey("procedures.id"),
        nullable=False,
    )

    document_number = Column(
        Text,
        nullable=True,
    )

    document_name = Column(
        Text,
        nullable=False,
    )

    document_type = Column(
        Text,
        nullable=True,
    )

    article_reference = Column(
        Text,
        nullable=True,
    )

    source_url = Column(
        Text,
        nullable=True,
    )

    effective_date = Column(
        Text,
        nullable=True,
    )

    note = Column(
        Text,
        nullable=True,
    )


class ChatHistory(Base):
    """
    Lưu lịch sử câu hỏi và câu trả lời.
    """

    __tablename__ = "chat_history"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    question = Column(
        Text,
        nullable=False,
    )

    answer = Column(
        Text,
        nullable=False,
    )

    source_type = Column(
        Text,
        nullable=True,
    )

    source_label = Column(
        Text,
        nullable=True,
    )

    sources_json = Column(
        Text,
        nullable=True,
    )

    file_name = Column(
        Text,
        nullable=True,
    )

    # Mã phiên hội thoại (sinh ở trình duyệt).
    # Dùng để tách lịch sử theo người dùng
    # và giữ ngữ cảnh khi hỏi tiếp.
    session_id = Column(
        String(64),
        nullable=True,
        index=True,
    )

    # Mã thủ tục đã dùng để trả lời
    # (phục vụ câu hỏi nối tiếp).
    procedure_code = Column(
        String(32),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=utc_now,
        nullable=False,
    )