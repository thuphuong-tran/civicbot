"""
Truy xuất dữ liệu thủ tục làm ngữ cảnh (context) cho Gemini.

Đây là cơ chế RAG mức đơn giản (retrieval-augmented generation):
1. Chấm điểm mức liên quan giữa câu hỏi và từng thủ tục trong MySQL.
2. Lấy tối đa k thủ tục liên quan nhất.
3. Ghép thông tin của các thủ tục đó thành văn bản ngữ cảnh.
4. Gemini chỉ được trả lời dựa trên ngữ cảnh này
   (xem generate_grounded_answer trong ai_service.py).
"""

from sqlalchemy.orm import Session

from app.models import (
    LegalReference,
    Procedure,
    ProcedureStep,
    RequiredDocument,
)
from app.services.nlp_service import (
    clean_text,
    detect_topics,
    get_procedure_topics,
    normalize_text,
)

STOP_WORDS = {
    "la", "gi", "nhu", "nao", "bao", "nhieu", "hom", "nay",
    "toi", "muon", "cho", "hoi", "ve", "can", "co", "khong",
    "duoc", "thuc", "hien", "lam", "the", "mot", "thu", "tuc",
    "va", "thi", "o", "de", "cua", "minh", "em", "anh", "chi",
    "ban", "xin", "giup", "voi", "nhe", "a", "di", "phai",
    # Từ chung của mọi thủ tục, không giúp phân biệt thủ tục
    "giay", "to", "ho", "so", "le", "phi", "dang", "ky", "cap",
    "nhung", "thong", "tin", "cong", "dan", "nguoi", "tren",
    "trong", "theo", "quy", "dinh", "bang",
}

MAX_CONTEXT_CHARS_PER_PROCEDURE = 2500


def _meaningful_words(text: str) -> set[str]:
    return {
        word
        for word in normalize_text(text).split()
        if word not in STOP_WORDS and len(word) > 1
    }


def _procedure_search_text(procedure: Procedure) -> str:
    fields = [
        procedure.procedure_code,
        procedure.name,
        procedure.category,
        procedure.target,
        procedure.description,
        procedure.conditions,
    ]

    return " ".join(
        clean_text(field)
        for field in fields
        if field
    )


def score_procedure(question: str, procedure: Procedure) -> int:
    question_words = _meaningful_words(question)
    procedure_words = _meaningful_words(
        _procedure_search_text(procedure)
    )

    score = len(question_words & procedure_words)

    question_topics = set(detect_topics(question))
    procedure_topics = get_procedure_topics(procedure)

    if question_topics & procedure_topics:
        score += 5

    return score


def find_candidate_procedures(
    db: Session,
    question: str,
    k: int = 3,
    min_score: int = 2,
) -> list[Procedure]:
    """
    Trả về tối đa k thủ tục liên quan nhất
    (có thể dùng khi find_procedure không đủ chắc chắn).
    """

    question_topics = set(detect_topics(question))

    # Câu hỏi không nêu chủ đề cư trú / căn cước thì không lấy ngữ cảnh.
    # Lỗi phát hiện khi demo: "Việt Nam có bao nhiêu dân tộc" trùng các từ
    # "Việt Nam", "dân tộc" trong thủ tục căn cước nên bị đưa vào RAG.
    if not question_topics:
        return []

    procedures = db.query(Procedure).all()

    scored = []

    for procedure in procedures:
        # Câu hỏi đã nêu chủ đề (ví dụ hộ chiếu) thì thủ tục
        # phải cùng chủ đề, tránh lấy nhầm ngữ cảnh.
        if question_topics and not (
            question_topics & get_procedure_topics(procedure)
        ):
            continue

        score = score_procedure(question, procedure)

        if score >= min_score:
            scored.append((score, procedure))

    scored.sort(key=lambda item: item[0], reverse=True)

    return [procedure for _, procedure in scored[:k]]


def build_procedure_context(
    db: Session,
    procedure: Procedure,
) -> str:
    """
    Chuyển một thủ tục trong MySQL thành đoạn văn bản ngữ cảnh.
    """

    documents = (
        db.query(RequiredDocument)
        .filter(RequiredDocument.procedure_id == procedure.id)
        .all()
    )
    steps = (
        db.query(ProcedureStep)
        .filter(ProcedureStep.procedure_id == procedure.id)
        .order_by(ProcedureStep.step_no)
        .all()
    )
    legal_references = (
        db.query(LegalReference)
        .filter(LegalReference.procedure_id == procedure.id)
        .all()
    )

    lines = [
        f"[MÃ THỦ TỤC: {clean_text(procedure.procedure_code)}]",
        f"Tên thủ tục: {clean_text(procedure.name)}",
        f"Cơ quan thực hiện: {clean_text(procedure.authority)}",
        f"Đối tượng: {clean_text(procedure.target)}",
        f"Điều kiện: {clean_text(procedure.conditions)}",
        f"Thời hạn giải quyết: {clean_text(procedure.processing_time)}",
        f"Lệ phí: {clean_text(procedure.fee) or 'không có dữ liệu'}",
        f"Kết quả: {clean_text(procedure.result)}",
    ]

    if documents:
        lines.append("Hồ sơ cần chuẩn bị:")
        for document in documents:
            lines.append(f"- {clean_text(document.document_name)}")

    if steps:
        lines.append("Các bước thực hiện:")
        for step in steps:
            lines.append(f"- Bước {step.step_no}: {clean_text(step.action)}")

    if legal_references:
        lines.append("Căn cứ pháp lý:")
        for reference in legal_references:
            lines.append(
                f"- {clean_text(reference.document_number)} "
                f"{clean_text(reference.document_name)}".strip()
            )

    if procedure.source_url:
        lines.append(f"Nguồn: {clean_text(procedure.source_url)}")

    context = "\n".join(line for line in lines if line.strip())

    return context[:MAX_CONTEXT_CHARS_PER_PROCEDURE]


def build_context(
    db: Session,
    procedures: list[Procedure],
) -> str:
    return "\n\n".join(
        build_procedure_context(db, procedure)
        for procedure in procedures
    )
