"""
API hỏi đáp của CivicBot.

Luồng xử lý một câu hỏi (xem sơ đồ trong README):

1. Câu hỏi rỗng / câu chào        -> trả lời mặc định.
2. Có tệp đính kèm               -> kiểm tra định dạng, dung lượng
                                    -> Gemini phân tích tệp.
3. Tìm thủ tục trong MySQL       -> trả lời từ CSDL nội bộ (không gọi AI).
4. Câu hỏi nối tiếp trong phiên  -> dùng lại thủ tục của câu trước.
5. Câu hỏi "chuyển nhà..."       -> gợi ý thường trú / tạm trú từ CSDL.
6. Có thủ tục gần đúng           -> Gemini trả lời DỰA TRÊN dữ liệu MySQL (RAG).
7. Không có dữ liệu liên quan    -> Gemini chỉ định hướng chung, không bịa chi tiết.
"""

from pathlib import Path
import os
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    ChatHistory,
    Procedure,
)
from app.services.ai_service import (
    NO_DATA_MESSAGE,
    generate_ai_document_answer,
    generate_ai_fallback_answer,
    is_administrative_question,
    is_general_answer,
    generate_ai_image_answer,
    generate_grounded_answer,
    is_ai_enabled,
)
from app.services.nlp_service import *  # noqa: F401,F403  (giữ tương thích import cũ)
from app.services.nlp_service import (
    clean_text,
    detect_topics,
    has_specific_question_type,
    is_follow_up_question,
    split_compound_question,
    is_greeting,
    is_moving_question,
)
from app.services.procedure_service import *  # noqa: F401,F403
from app.services.procedure_service import (
    build_answer,
    build_local_answer,
    build_sources,
    find_procedure,
)
from app.services.retrieval_service import (
    build_context,
    find_candidate_procedures,
)
from app.services.security_service import (
    build_safe_upload_name,
    get_max_upload_bytes,
    is_admin_key_valid,
    validate_upload_name,
)


router = APIRouter(
    prefix="/api",
    tags=["Chat"],
)


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(
    exist_ok=True
)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx"}


class UploadTooLargeError(Exception):
    pass


# =========================================================
# FILE ĐÍNH KÈM
# =========================================================

def save_uploaded_file(
    upload_file: UploadFile,
) -> Path:
    """
    Lưu tệp với tên ngẫu nhiên, đọc theo từng khối
    và dừng ngay nếu vượt quá MAX_UPLOAD_MB.
    """

    max_bytes = get_max_upload_bytes()

    file_path = UPLOAD_DIR / build_safe_upload_name(
        upload_file.filename or ""
    )

    written = 0

    try:
        with file_path.open("wb") as output:
            while True:
                chunk = upload_file.file.read(1024 * 1024)

                if not chunk:
                    break

                written += len(chunk)

                if written > max_bytes:
                    raise UploadTooLargeError()

                output.write(chunk)

    except UploadTooLargeError:
        file_path.unlink(missing_ok=True)
        raise

    return file_path


def remove_uploaded_file(file_path: Optional[Path]) -> None:
    """
    Xóa tệp sau khi phân tích (backend stateless).
    Đặt KEEP_UPLOADS=true nếu muốn giữ lại để kiểm tra.
    """

    if not file_path:
        return

    if os.getenv("KEEP_UPLOADS", "false").lower() == "true":
        return

    try:
        file_path.unlink(missing_ok=True)
    except Exception as error:
        print(f"Không thể xóa tệp tạm: {error}")


# =========================================================
# LƯU LỊCH SỬ
# =========================================================

def make_block(
    content: str,
    source_type: str,
    source_label: str,
    meta: str = "",
) -> dict:
    return {
        "content": content or "",
        "source_type": source_type,
        "source_label": source_label,
        "meta": meta,
    }


def save_chat_history(
    db: Session,
    question: str,
    answer_blocks: list[dict],
    sources: list[dict],
    file_name: str = "",
    session_id: str = "",
    procedure_code: str = "",
):
    import json

    if not answer_blocks:
        return

    answer = "\n\n".join(
        block.get("content", "")
        for block in answer_blocks
    )

    first_block = answer_blocks[0]

    history = ChatHistory(
        question=question or "(Không có câu hỏi)",
        answer=answer,
        source_type=first_block.get("source_type", "system"),
        source_label=first_block.get("source_label", "HỆ THỐNG"),
        sources_json=json.dumps(sources or [], ensure_ascii=False),
        file_name=file_name or None,
        session_id=(session_id or None),
        procedure_code=(procedure_code or None),
    )

    try:
        db.add(history)
        db.commit()
    except Exception as error:
        db.rollback()
        print("Không thể lưu lịch sử hỏi đáp.")
        print(f"Chi tiết lỗi: {error}")


def build_response(
    db: Session,
    question: str,
    answer_blocks: list[dict],
    sources: list[dict],
    file_name: str = "",
    session_id: str = "",
    procedure_code: str = "",
    route: str = "",
):
    save_chat_history(
        db=db,
        question=question,
        answer_blocks=answer_blocks,
        sources=sources,
        file_name=file_name,
        session_id=session_id,
        procedure_code=procedure_code,
    )

    return {
        "answer_blocks": answer_blocks,
        "sources": sources,
        "procedure_code": procedure_code or None,
        # route cho biết nhánh xử lý, dùng cho kiểm thử và đánh giá AI
        "route": route,
    }


# =========================================================
# NGỮ CẢNH HỘI THOẠI
# =========================================================

def normalize_session_id(session_id: str) -> str:
    session_id = (session_id or "").strip()

    # Chỉ nhận chuỗi ngắn gồm chữ, số, gạch ngang
    if len(session_id) > 64:
        session_id = session_id[:64]

    return "".join(
        character
        for character in session_id
        if character.isalnum() or character in "-_"
    )


def get_recent_history(
    db: Session,
    session_id: str,
    limit: int = 3,
) -> list[ChatHistory]:
    if not session_id:
        return []

    return (
        db.query(ChatHistory)
        .filter(ChatHistory.session_id == session_id)
        .order_by(ChatHistory.id.desc())
        .limit(limit)
        .all()
    )


def get_last_procedure_in_session(
    db: Session,
    session_id: str,
) -> Optional[Procedure]:
    if not session_id:
        return None

    last_item = (
        db.query(ChatHistory)
        .filter(
            ChatHistory.session_id == session_id,
            ChatHistory.procedure_code.isnot(None),
        )
        .order_by(ChatHistory.id.desc())
        .first()
    )

    if not last_item:
        return None

    return (
        db.query(Procedure)
        .filter(Procedure.procedure_code == last_item.procedure_code)
        .first()
    )


def build_conversation_text(
    history_items: list[ChatHistory],
) -> str:
    lines = []

    for item in reversed(history_items):
        lines.append(f"Người dùng: {clean_text(item.question)[:200]}")
        lines.append(f"CivicBot: {clean_text(item.answer)[:300]}")

    return "\n".join(lines)


# =========================================================
# TRẢ LỜI CÂU HỎI "CHUYỂN NHÀ"
# =========================================================

def find_procedure_by_name(
    db: Session,
    keyword: str,
) -> Optional[Procedure]:
    for procedure in db.query(Procedure).all():
        name = clean_text(procedure.name).lower()

        if name == keyword or name.startswith(keyword):
            return procedure

    return None


def build_moving_answer(
    db: Session,
) -> tuple[str, list[dict], list[Procedure]]:
    permanent = find_procedure_by_name(db, "đăng ký thường trú")
    temporary = find_procedure_by_name(db, "đăng ký tạm trú")

    lines = [
        "Khi chuyển đến chỗ ở mới, bạn cần làm một trong hai thủ tục sau:",
    ]

    procedures = []

    if permanent:
        procedures.append(permanent)
        lines.append(
            f"1. {clean_text(permanent.name)} (mã {permanent.procedure_code}): "
            "nếu bạn chuyển đến sinh sống ổn định, lâu dài tại chỗ ở mới. "
            f"Nơi thực hiện: {clean_text(permanent.authority)}."
        )

    if temporary:
        procedures.append(temporary)
        lines.append(
            f"2. {clean_text(temporary.name)} (mã {temporary.procedure_code}): "
            "nếu bạn chỉ đến ở có thời hạn (ví dụ thuê trọ, đi học, đi làm) "
            "từ 30 ngày trở lên. "
            f"Nơi thực hiện: {clean_text(temporary.authority)}."
        )

    lines.append(
        "Bạn có thể hỏi tiếp, ví dụ: "
        "\"Đăng ký thường trú cần giấy tờ gì?\" "
        "hoặc \"Đăng ký tạm trú mất bao lâu?\"."
    )

    sources = []

    for procedure in procedures:
        sources.extend(build_sources(procedure))

    return "\n".join(lines), sources, procedures


TOPIC_LABELS = {
    "passport": "hộ chiếu",
    "identity_card": "thẻ căn cước",
    "permanent_residence": "đăng ký thường trú",
    "temporary_residence": "đăng ký tạm trú",
    "temporary_absence": "khai báo tạm vắng",
    "household_separation": "tách hộ",
    "residence_notification": "thông báo lưu trú",
    "residence_confirmation": "xác nhận thông tin cư trú",
    "residence_adjustment": "điều chỉnh thông tin cư trú",
    "permanent_residence_deletion": "xóa đăng ký thường trú",
    "temporary_residence_deletion": "xóa đăng ký tạm trú",
}


def handle_compound_question(db: Session, question: str, session_id: str):
    """
    Câu hỏi kép: tách thành các câu hỏi con, phần nào có trong CSDL
    thì trả lời từ CSDL, phần nào ngoài dữ liệu thì Gemini định hướng chung.
    Trả về None nếu không phải câu hỏi kép hoặc không có phần nào trong CSDL.
    """

    sub_questions = split_compound_question(question)

    if not sub_questions:
        return None

    parts = []

    for sub in sub_questions:
        parts.append((sub, find_procedure(db, sub)))

    if not any(procedure for _, procedure in parts):
        return None

    blocks = []
    sources = []
    first_code = ""
    seen_codes = set()

    for sub, procedure in parts:
        if procedure:
            if procedure.procedure_code in seen_codes:
                continue

            seen_codes.add(procedure.procedure_code)
            answer, procedure_sources = build_answer(
                db=db,
                procedure=procedure,
                question=sub,
            )
            sources.extend(procedure_sources)
            first_code = first_code or procedure.procedure_code
            blocks.append(
                make_block(
                    answer,
                    "local",
                    "CSDL NỘI BỘ",
                    "Câu hỏi gồm nhiều nội dung – phần này được trả lời từ cơ sở dữ liệu thủ tục của CivicBot (không sử dụng Gemini).",
                )
            )
            continue

        topics = detect_topics(sub)
        label = TOPIC_LABELS.get(topics[0], "phần còn lại") if topics else "phần còn lại"

        ai_answer = None

        try:
            ai_answer = generate_ai_fallback_answer(sub)
        except Exception as error:
            print(f"Gemini (câu hỏi kép) lỗi: {error}")

        if ai_answer:
            general = is_general_answer(ai_answer) and not is_administrative_question(sub)
            blocks.append(
                make_block(
                    f"Về {label}: {ai_answer}",
                    "gemini",
                    "GEMINI",
                    "Câu hỏi gồm nhiều nội dung – phần này không thuộc lĩnh vực thủ tục hành chính; nội dung do AI tổng hợp, chỉ có giá trị tham khảo."
                    if general
                    else "Câu hỏi gồm nhiều nội dung – phần này chưa có trong cơ sở dữ liệu; nội dung do AI tổng hợp, chỉ có giá trị tham khảo, cần đối chiếu với cơ quan có thẩm quyền.",
                )
            )
        else:
            blocks.append(
                make_block(
                    f"Về {label}: {NO_DATA_MESSAGE}",
                    "system",
                    "HỆ THỐNG",
                )
            )

    return build_response(
        db=db,
        question=question,
        answer_blocks=blocks,
        sources=sources,
        session_id=session_id,
        procedure_code=first_code,
        route="compound",
    )


# =========================================================
# API CHAT
# =========================================================

@router.post("/chat")
def chat(
    question: str = Form(""),
    file: Optional[UploadFile] = File(None),
    session_id: str = Form(""),
    db: Session = Depends(get_db),
):
    question = (question or "").strip()
    session_id = normalize_session_id(session_id)

    if len(question) > 2000:
        question = question[:2000]

    # 1. Câu hỏi rỗng
    if not question and not file:
        blocks = [
            make_block(
                "Bạn hãy nhập câu hỏi hoặc "
                "đính kèm tài liệu cần tra cứu.",
                "system",
                "HỆ THỐNG",
            )
        ]

        return {
            "answer_blocks": blocks,
            "sources": [],
            "procedure_code": None,
            "route": "empty",
        }

    # 1b. Câu chào
    if question and is_greeting(question) and not file:
        blocks = [
            make_block(
                "Xin chào! Tôi là CivicBot. "
                "Tôi có thể giúp bạn tra cứu "
                "thủ tục cư trú và giấy tờ tùy thân.",
                "local",
                "CSDL NỘI BỘ",
                "Lời chào của hệ thống.",
            )
        ]

        return build_response(
            db=db,
            question=question,
            answer_blocks=blocks,
            sources=[],
            session_id=session_id,
            route="greeting",
        )

    # 2. Tệp đính kèm
    if file:
        return handle_file_question(
            db=db,
            question=question,
            file=file,
            session_id=session_id,
        )

    # 2b. Câu hỏi kép: "mất hộ chiếu và căn cước thì làm gì"
    compound_response = handle_compound_question(db, question, session_id)

    if compound_response:
        return compound_response

    # 3. Tìm thủ tục trong CSDL nội bộ
    procedure = find_procedure(db, question)
    route = "local"
    meta = "Nội dung được trích xuất từ cơ sở dữ liệu thủ tục hành chính của CivicBot (không sử dụng Gemini)."

    # 4. Câu hỏi nối tiếp: "Thế lệ phí bao nhiêu?"
    if (
        not procedure
        and session_id
        and not detect_topics(question)
        and has_specific_question_type(question)
        and is_follow_up_question(question)
    ):
        procedure = get_last_procedure_in_session(db, session_id)

        if procedure:
            route = "local_followup"
            meta = (
                "Câu hỏi nối tiếp: hệ thống áp dụng thủ tục của câu hỏi trước "
                f"(mã {procedure.procedure_code}); nội dung trích xuất từ cơ sở dữ liệu "
                "(không sử dụng Gemini)."
            )

    if procedure:
        answer, sources = build_answer(
            db=db,
            procedure=procedure,
            question=question,
        )

        blocks = [make_block(answer, "local", "CSDL NỘI BỘ", meta)]

        return build_response(
            db=db,
            question=question,
            answer_blocks=blocks,
            sources=sources,
            session_id=session_id,
            procedure_code=procedure.procedure_code,
            route=route,
        )

    # 5. Câu hỏi về chuyển nơi ở
    if is_moving_question(question) and not detect_topics(question):
        answer, sources, procedures = build_moving_answer(db)

        if procedures:
            blocks = [
                make_block(
                    answer,
                    "local",
                    "CSDL NỘI BỘ",
                    "Câu hỏi chưa xác định rõ thủ tục. Hệ thống đề xuất các thủ tục liên quan để người dùng lựa chọn.",
                )
            ]

            return build_response(
                db=db,
                question=question,
                answer_blocks=blocks,
                sources=sources,
                session_id=session_id,
                route="local_suggestion",
            )

    # 6. Có thủ tục gần đúng -> Gemini trả lời dựa trên dữ liệu MySQL (RAG)
    candidates = find_candidate_procedures(db, question, k=3)

    if candidates:
        sources = []

        for candidate in candidates:
            sources.extend(build_sources(candidate))

        context = build_context(db, candidates)
        conversation = build_conversation_text(
            get_recent_history(db, session_id)
        )

        try:
            ai_answer = generate_grounded_answer(
                question=question,
                context=context,
                conversation=conversation,
            )
        except Exception as error:
            print(f"Gemini (RAG) lỗi: {error}")
            ai_answer = None

        # Gemini kết luận ngữ cảnh không đủ -> không gắn nhãn/nguồn thủ tục
        if ai_answer and NO_DATA_MESSAGE[:40] in ai_answer:
            blocks = [make_block(NO_DATA_MESSAGE, "system", "HỆ THỐNG")]

            return build_response(
                db=db,
                question=question,
                answer_blocks=blocks,
                sources=[],
                session_id=session_id,
                route="no_data",
            )

        if ai_answer:
            codes = ", ".join(c.procedure_code for c in candidates)
            blocks = [
                make_block(
                    ai_answer,
                    "gemini",
                    "GEMINI + CSDL",
                    f"Nội dung do Gemini tổng hợp, chỉ dựa trên dữ liệu các thủ tục: {codes}.",
                )
            ]

            return build_response(
                db=db,
                question=question,
                answer_blocks=blocks,
                sources=sources,
                session_id=session_id,
                procedure_code=candidates[0].procedure_code,
                route="gemini_grounded",
            )

        # Gemini tắt hoặc lỗi: vẫn gợi ý thủ tục từ CSDL, không để người dùng trắng tay
        lines = ["Bạn có thể đang hỏi về một trong các thủ tục sau:"]

        for index, candidate in enumerate(candidates, start=1):
            lines.append(
                f"{index}. {clean_text(candidate.name)} (mã {candidate.procedure_code})"
            )

        lines.append("Bạn hãy hỏi lại kèm tên thủ tục để nhận câu trả lời chính xác.")

        blocks = [
            make_block(
                "\n".join(lines),
                "local",
                "CSDL NỘI BỘ",
                "Dịch vụ AI hiện không khả dụng. Hệ thống hiển thị các thủ tục liên quan nhất trong cơ sở dữ liệu.",
            )
        ]

        return build_response(
            db=db,
            question=question,
            answer_blocks=blocks,
            sources=sources,
            session_id=session_id,
            route="local_candidates",
        )

    # 7. Ngoài phạm vi dữ liệu -> Gemini chỉ định hướng chung
    try:
        ai_answer = generate_ai_fallback_answer(question)
    except Exception as error:
        print(f"Gemini lỗi: {error}")
        ai_answer = None

    if ai_answer and not is_administrative_question(question) and is_general_answer(ai_answer):
        blocks = [
            make_block(
                ai_answer,
                "gemini",
                "GEMINI",
                "Nội dung không thuộc lĩnh vực thủ tục hành chính. Câu trả lời do AI "
                "tổng hợp từ kiến thức chung, chỉ có giá trị tham khảo và chưa được "
                "cơ quan có thẩm quyền kiểm chứng.",
            )
        ]
        route = "gemini_general"
    elif ai_answer:
        blocks = [
            make_block(
                ai_answer,
                "gemini",
                "GEMINI",
                "Thủ tục chưa có trong cơ sở dữ liệu của CivicBot. Nội dung do AI tổng hợp, "
                "chỉ có giá trị tham khảo; đề nghị đối chiếu tại Cổng Dịch vụ công Quốc gia "
                "hoặc cơ quan có thẩm quyền.",
            )
        ]
        route = "gemini_out_of_scope"
    else:
        blocks = [make_block(NO_DATA_MESSAGE, "system", "HỆ THỐNG")]
        route = "no_data"

    return build_response(
        db=db,
        question=question,
        answer_blocks=blocks,
        sources=[],
        session_id=session_id,
        route=route,
    )


def handle_file_question(
    db: Session,
    question: str,
    file: UploadFile,
    session_id: str,
):
    file_name = file.filename or "Tệp đính kèm"
    history_question = question or f"Phân tích tệp: {file_name}"

    # Kiểm tra định dạng TRƯỚC khi lưu tệp
    error_message = validate_upload_name(file_name)

    if error_message:
        blocks = [make_block(error_message, "system", "HỆ THỐNG")]

        return build_response(
            db=db,
            question=history_question,
            answer_blocks=blocks,
            sources=[],
            file_name=file_name,
            session_id=session_id,
            route="file_rejected",
        )

    if not is_ai_enabled():
        blocks = [
            make_block(
                "Tính năng đọc tệp đính kèm cần Gemini nhưng AI đang tắt "
                "(AI_MODE=off). Bạn hãy nhập câu hỏi bằng chữ để tra cứu "
                "trong CSDL nội bộ.",
                "system",
                "HỆ THỐNG",
            )
        ]

        return build_response(
            db=db,
            question=history_question,
            answer_blocks=blocks,
            sources=[],
            file_name=file_name,
            session_id=session_id,
            route="file_ai_disabled",
        )

    file_path = None

    try:
        file_path = save_uploaded_file(file)
        suffix = Path(file_name).suffix.lower()

        if suffix in IMAGE_EXTENSIONS:
            answer = generate_ai_image_answer(str(file_path), question)
        elif suffix in DOCUMENT_EXTENSIONS:
            answer = generate_ai_document_answer(str(file_path), question)
        else:
            answer = None

        blocks = [
            make_block(
                answer or "Gemini chưa tạo được câu trả lời.",
                "gemini",
                "GEMINI",
                "Nội dung do Gemini phân tích từ tệp đính kèm, chỉ có giá trị tham khảo.",
            )
        ]
        route = "file_ai"

    except UploadTooLargeError:
        max_mb = get_max_upload_bytes() // (1024 * 1024)
        blocks = [
            make_block(
                f"Tệp vượt quá dung lượng cho phép ({max_mb} MB).",
                "system",
                "HỆ THỐNG",
            )
        ]
        route = "file_rejected"

    except Exception as error:
        blocks = [
            make_block(
                f"Không thể phân tích tệp: {error}",
                "system",
                "HỆ THỐNG",
            )
        ]
        route = "file_error"

    finally:
        remove_uploaded_file(file_path)

    return build_response(
        db=db,
        question=history_question,
        answer_blocks=blocks,
        sources=[],
        file_name=file_name,
        session_id=session_id,
        route=route,
    )


# =========================================================
# API LỊCH SỬ HỎI ĐÁP
# =========================================================

def serialize_history(item: ChatHistory) -> dict:
    return {
        "id": item.id,
        "question": item.question,
        "answer": item.answer,
        "source_type": item.source_type,
        "source_label": item.source_label,
        "file_name": item.file_name,
        "procedure_code": item.procedure_code,
        "created_at": (
            item.created_at.isoformat(sep=" ", timespec="seconds")
            if item.created_at
            else ""
        ),
    }


@router.get("/history")
def get_history(
    limit: int = 100,
    session_id: str = "",
    db: Session = Depends(get_db),
):
    """
    Có session_id: chỉ trả lịch sử của phiên đó
    (người dùng này không xem được lịch sử của người khác).
    """

    limit = max(1, min(limit, 500))
    session_id = normalize_session_id(session_id)

    query = db.query(ChatHistory)

    if session_id:
        query = query.filter(ChatHistory.session_id == session_id)

    total = query.count()

    history_items = (
        query.order_by(ChatHistory.created_at.desc(), ChatHistory.id.desc())
        .limit(limit)
        .all()
    )

    return {
        "items": [serialize_history(item) for item in history_items],
        "total": total,
    }


@router.delete("/history/{history_id}")
def delete_history(
    history_id: int,
    session_id: str = "",
    x_admin_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    session_id = normalize_session_id(session_id)

    history = (
        db.query(ChatHistory)
        .filter(ChatHistory.id == history_id)
        .first()
    )

    if not history:
        return {"ok": False, "message": "Không tìm thấy bản ghi lịch sử."}

    is_owner = bool(session_id) and history.session_id == session_id

    if not is_owner and not is_admin_key_valid(x_admin_key):
        raise HTTPException(
            status_code=403,
            detail="Bạn không có quyền xóa bản ghi này.",
        )

    db.delete(history)
    db.commit()

    return {"ok": True, "message": "Đã xóa bản ghi lịch sử."}


@router.delete("/history")
def clear_history(
    session_id: str = "",
    x_admin_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    """
    Có session_id: xóa lịch sử của phiên đó.
    Không có session_id: xóa toàn bộ, cần khóa quản trị.
    """

    session_id = normalize_session_id(session_id)

    query = db.query(ChatHistory)

    if session_id:
        query = query.filter(ChatHistory.session_id == session_id)
    elif not is_admin_key_valid(x_admin_key):
        raise HTTPException(
            status_code=403,
            detail="Cần khóa quản trị để xóa toàn bộ lịch sử.",
        )

    deleted_count = query.delete(synchronize_session=False)
    db.commit()

    return {
        "ok": True,
        "deleted": deleted_count,
        "message": "Đã xóa lịch sử hỏi đáp.",
    }
