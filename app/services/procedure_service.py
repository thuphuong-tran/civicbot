"""
Tìm thủ tục trong CSDL nội bộ và xây dựng câu trả lời
từ dữ liệu MySQL (không gọi AI).

Tách ra từ app/routers/chat.py.
"""

import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    LegalReference,
    Procedure,
    ProcedureStep,
    RequiredDocument,
)
from app.services.nlp_service import *  # noqa: F401,F403
from app.services.nlp_service import (
    clean_text,
    detect_topics,
    format_multiline_text,
    get_procedure_topics,
    is_document_question,
    is_fee_question,
    is_form_question,
    is_legal_reference_question,
    is_location_question,
    is_method_question,
    is_step_question,
    is_time_question,
    normalize_text,
)


# =========================================================
# TÌM THỦ TỤC
# =========================================================

ACTION_PHRASES = [
    "cap doi",
    "cap lai",
    "gia han",
    "xoa dang ky",
    "khai bao",
    "dieu chinh",
    "xac nhan",
]

UNDER_14_PHRASES = ["duoi 14", "chua du 14", "tre em", "cho con", "cho be"]
OVER_14_PHRASES = ["tren 14", "tu 14", "du 14", "tu du 14", "nguoi lon"]


def detect_age_group(normalized_question: str) -> str:
    """
    Phân biệt căn cước cho người dưới 14 tuổi và từ đủ 14 tuổi.
    Nhận cả số tuổi cụ thể, ví dụ "con 10 tuổi" -> under_14.
    """

    if any(phrase in normalized_question for phrase in OVER_14_PHRASES):
        return "over_14"

    if any(phrase in normalized_question for phrase in UNDER_14_PHRASES):
        return "under_14"

    match = re.search(r"(\d{1,3})\s*tuoi", normalized_question)

    if match:
        return "under_14" if int(match.group(1)) < 14 else "over_14"

    return ""


def action_and_age_bonus(
    normalized_question: str,
    normalized_name: str,
) -> int:
    """
    Cộng điểm khi câu hỏi và tên thủ tục cùng chứa
    hành động đặc trưng (cấp đổi, cấp lại, gia hạn...)
    hoặc cùng nhóm tuổi (căn cước dưới / từ đủ 14 tuổi).
    """

    bonus = 0

    for phrase in ACTION_PHRASES:
        if phrase in normalized_question and phrase in normalized_name:
            bonus += 10

    age_group = detect_age_group(normalized_question)

    if age_group == "under_14" and "duoi 14" in normalized_name:
        bonus += 10

    if age_group == "over_14" and "du 14" in normalized_name:
        bonus += 10

    return bonus


def find_procedure(
    db: Session,
    question: str,
) -> Optional[Procedure]:
    """
    Tìm thủ tục phù hợp.

    Quy tắc quan trọng:

    Nếu câu hỏi không có chủ đề thủ tục
    thì không được chọn ngẫu nhiên một thủ tục
    chỉ vì có một vài từ chung.

    Ví dụ:
        "giá xăng hôm nay là bao nhiêu"
        phải trả về None.

    Không được chọn:
        "Tách hộ"
        "Đăng ký tạm trú"
        hoặc thủ tục bất kỳ nào khác.
    """

    normalized_question = normalize_text(
        question
    )

    if not normalized_question:
        return None

    procedures = db.query(
        Procedure
    ).all()

    if not procedures:
        return None

    question_topics = set(
        detect_topics(
            question
        )
    )

    best_procedure = None
    best_score = 0

    question_words = set(
        normalized_question.split()
    )

    generic_words = {
        "la",
        "gi",
        "nhu",
        "nao",
        "bao",
        "nhieu",
        "hom",
        "nay",
        "toi",
        "muon",
        "cho",
        "hoi",
        "ve",
        "can",
        "co",
        "khong",
        "duoc",
        "thuc",
        "hien",
        "lam",
        "the",
        "nao",
        "mot",
        "thu",
        "tuc",
    }

    meaningful_question_words = {
        word
        for word in question_words
        if word not in generic_words
        and len(word) > 1
    }

    # Nếu câu hỏi không có bất kỳ chủ đề thủ tục
    # thì không được chọn thủ tục nội bộ.
    #
    # Ví dụ:
    # "giá xăng hôm nay là bao nhiêu"
    # -> question_topics = set()
    # -> trả về None
    if not question_topics:
        return None

    for procedure in procedures:
        procedure_topics = (
            get_procedure_topics(
                procedure
            )
        )

        # Nếu câu hỏi đã xác định chủ đề,
        # thủ tục bắt buộc phải cùng chủ đề.
        #
        # Ví dụ:
        # - Hỏi hộ chiếu không chọn tách hộ.
        # - Hỏi tạm trú không chọn thường trú.
        # - Hỏi căn cước không chọn tạm trú.
        if not question_topics.intersection(
            procedure_topics
        ):
            continue

        fields = [
            getattr(
                procedure,
                "procedure_code",
                "",
            ),
            getattr(
                procedure,
                "name",
                "",
            ),
            getattr(
                procedure,
                "category",
                "",
            ),
            getattr(
                procedure,
                "target",
                "",
            ),
            getattr(
                procedure,
                "description",
                "",
            ),
            getattr(
                procedure,
                "conditions",
                "",
            ),
        ]

        procedure_text = normalize_text(
            " ".join(
                clean_text(field)
                for field in fields
                if field
            )
        )

        if not procedure_text:
            continue

        procedure_words = set(
            procedure_text.split()
        )

        meaningful_procedure_words = {
            word
            for word in procedure_words
            if word not in generic_words
            and len(word) > 1
        }

        score = len(
            meaningful_question_words.intersection(
                meaningful_procedure_words
            )
        )

        exact_name = normalize_text(
            getattr(
                procedure,
                "name",
                "",
            )
        )

        procedure_code = normalize_text(
            getattr(
                procedure,
                "procedure_code",
                "",
            )
        )

        if (
            exact_name
            and exact_name in normalized_question
        ):
            score += 30

        if (
            procedure_code
            and procedure_code in normalized_question
        ):
            score += 30

        if (
            exact_name
            and exact_name == normalized_question
        ):
            score += 50

        score += action_and_age_bonus(
            normalized_question,
            exact_name,
        )

        if score > best_score:
            best_score = score
            best_procedure = procedure

    # Không chấp nhận kết quả quá yếu.
    if best_score < 2:
        return None

    return best_procedure


# =========================================================
# LẤY DỮ LIỆU TỪ CSDL
# =========================================================

def get_documents(
    db: Session,
    procedure: Procedure,
) -> list:
    try:
        return (
            db.query(RequiredDocument)
            .filter(
                RequiredDocument.procedure_id
                == procedure.id
            )
            .all()
        )
    except Exception as error:
        print(
            "Không thể lấy danh sách giấy tờ."
        )
        print(
            f"Chi tiết lỗi: {error}"
        )
        return []


def get_steps(
    db: Session,
    procedure: Procedure,
) -> list:
    try:
        return (
            db.query(ProcedureStep)
            .filter(
                ProcedureStep.procedure_id
                == procedure.id
            )
            .order_by(
                ProcedureStep.step_no
            )
            .all()
        )
    except Exception as error:
        print(
            "Không thể lấy các bước thực hiện."
        )
        print(
            f"Chi tiết lỗi: {error}"
        )
        return []


def get_legal_references(
    db: Session,
    procedure: Procedure,
) -> list:
    try:
        return (
            db.query(LegalReference)
            .filter(
                LegalReference.procedure_id
                == procedure.id
            )
            .order_by(
                LegalReference.id
            )
            .all()
        )
    except Exception as error:
        print(
            "Không thể lấy căn cứ pháp lý."
        )
        print(
            f"Chi tiết lỗi: {error}"
        )
        return []


# =========================================================
# NGUỒN THAM KHẢO
# =========================================================

def build_sources(
    procedure: Procedure,
) -> list[dict]:
    procedure_url = clean_text(
        getattr(
            procedure,
            "source_url",
            "",
        )
    )

    if not procedure_url:
        return []

    procedure_name = clean_text(
        getattr(
            procedure,
            "name",
            "Thủ tục",
        )
    )

    return [
        {
            "title": (
                "Trang thủ tục: "
                + procedure_name
            ),
            "url": procedure_url,
        }
    ]


# =========================================================
# CÂU TRẢ LỜI CĂN CỨ PHÁP LÝ
# =========================================================

def build_legal_answer(
    procedure: Procedure,
    legal_references: list,
) -> str:
    procedure_name = clean_text(
        getattr(
            procedure,
            "name",
            "thủ tục này",
        )
    )

    if not legal_references:
        return (
            f"CSDL nội bộ chưa có dữ liệu "
            f"về căn cứ pháp lý của thủ tục "
            f"{procedure_name}."
        )

    lines = [
        f"Căn cứ pháp lý của thủ tục "
        f"{procedure_name}:"
    ]

    for index, reference in enumerate(
        legal_references,
        start=1,
    ):
        document_name = clean_text(
            getattr(
                reference,
                "document_name",
                "",
            )
        )

        document_number = clean_text(
            getattr(
                reference,
                "document_number",
                "",
            )
        )

        document_type = clean_text(
            getattr(
                reference,
                "document_type",
                "",
            )
        )

        article_reference = clean_text(
            getattr(
                reference,
                "article_reference",
                "",
            )
        )

        title = document_name

        if (
            document_type
            and not title.lower().startswith(
                document_type.lower()
            )
        ):
            title = (
                f"{document_type} "
                f"{title}"
            )

        line = f"{index}. {title}"

        if document_number:
            line += (
                f" — Số: {document_number}"
            )

        if article_reference:
            line += (
                f" — {article_reference}"
            )

        lines.append(line)

    return "\n".join(lines)


# =========================================================
# CÂU TRẢ LỜI CÁCH THỨC THỰC HIỆN
# =========================================================

def build_method_answer(
    procedure: Procedure,
) -> str:
    procedure_name = clean_text(
        getattr(
            procedure,
            "name",
            "thủ tục này",
        )
    )

    raw_method = getattr(
        procedure,
        "method",
        "",
    )

    raw_method = str(
        raw_method or ""
    ).strip()

    if not raw_method:
        return (
            "CSDL nội bộ chưa có dữ liệu "
            "về cách thức thực hiện thủ tục "
            f"{procedure_name}."
        )

    raw_method = raw_method.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    raw_method = re.sub(
        r"(?:^|\s+)"
        r"(?:Hình thức|Hinh thuc)"
        r"\s*\d+\s*:\s*",
        "\n",
        raw_method,
        flags=re.IGNORECASE,
    )

    raw_method = re.sub(
        r"\s+-\s+",
        "\n",
        raw_method,
    )

    parts = re.split(
        r"\n+",
        raw_method,
    )

    method_lines = []

    for part in parts:
        part = re.sub(
            r"\s+",
            " ",
            part,
        ).strip()

        part = part.strip(
            "-•: "
        )

        if part:
            method_lines.append(
                part
            )

    if not method_lines:
        return (
            "CSDL nội bộ chưa có dữ liệu "
            "về cách thức thực hiện thủ tục "
            f"{procedure_name}."
        )

    lines = [
        f"Cách thực hiện thủ tục "
        f"{procedure_name}:"
    ]

    for index, method_line in enumerate(
        method_lines,
        start=1,
    ):
        lines.append(
            f"{index}. {method_line}"
        )

    return "\n".join(lines)


# =========================================================
# XÂY DỰNG CÂU TRẢ LỜI NỘI BỘ
# =========================================================

def build_local_answer(
    db: Session,
    procedure: Procedure,
    question: str,
) -> tuple[str, list[dict]]:
    documents = get_documents(
        db,
        procedure,
    )

    steps = get_steps(
        db,
        procedure,
    )

    legal_references = get_legal_references(
        db,
        procedure,
    )

    procedure_name = clean_text(
        getattr(
            procedure,
            "name",
            "",
        )
        or "thủ tục này"
    )

    authority = clean_text(
        getattr(
            procedure,
            "authority",
            "",
        )
        or "Cơ quan có thẩm quyền"
    )

    sources = build_sources(
        procedure
    )

    if is_method_question(question):
        return (
            build_method_answer(
                procedure
            ),
            sources,
        )

    if is_legal_reference_question(
        question
    ):
        return (
            build_legal_answer(
                procedure,
                legal_references,
            ),
            sources,
        )

    if is_form_question(question):
        form_documents = [
            document
            for document in documents
            if clean_text(
                getattr(
                    document,
                    "form_url",
                    "",
                )
            )
        ]

        if not form_documents:
            return (
                "CSDL nội bộ chưa có liên kết "
                f"biểu mẫu cho thủ tục "
                f"{procedure_name}.",
                sources,
            )

        lines = [
            f"Biểu mẫu của thủ tục "
            f"{procedure_name}:"
        ]

        for index, document in enumerate(
            form_documents,
            start=1,
        ):
            document_name = clean_text(
                getattr(
                    document,
                    "document_name",
                    "Biểu mẫu liên quan",
                )
            )

            condition = clean_text(
                getattr(
                    document,
                    "applicable_condition",
                    "",
                )
            )

            form_url = clean_text(
                getattr(
                    document,
                    "form_url",
                    "",
                )
            )

            lines.append(
                f"{index}. {document_name}"
            )

            if condition:
                lines.append(
                    f"   Điều kiện: {condition}"
                )

            if form_url:
                lines.append(
                    f"   Link biểu mẫu: {form_url}"
                )

        return (
            "\n".join(lines),
            sources,
        )

    if is_document_question(question):
        if not documents:
            return (
                "CSDL nội bộ chưa có danh sách "
                f"giấy tờ của thủ tục "
                f"{procedure_name}.",
                sources,
            )

        lines = [
            f"Hồ sơ cần chuẩn bị cho "
            f"{procedure_name}:"
        ]

        count = 0

        for document in documents:
            document_name = clean_text(
                getattr(
                    document,
                    "document_name",
                    "",
                )
            )

            if not document_name:
                continue

            count += 1

            required = getattr(
                document,
                "is_required",
                None,
            )

            note = clean_text(
                getattr(
                    document,
                    "note",
                    "",
                )
            )

            suffix = ""

            if required in (
                1,
                True,
                "1",
                "true",
                "True",
            ):
                suffix = " — bắt buộc"

            if note:
                suffix += f". {note}"

            lines.append(
                f"{count}. "
                f"{document_name}"
                f"{suffix}"
            )

        return (
            "\n".join(lines),
            sources,
        )

    if is_step_question(question):
        if not steps:
            return (
                "CSDL nội bộ chưa có các bước "
                f"thực hiện của thủ tục "
                f"{procedure_name}.",
                sources,
            )

        lines = [
            f"Các bước thực hiện "
            f"{procedure_name}:"
        ]

        count = 0

        for step in steps:
            action = clean_text(
                getattr(
                    step,
                    "action",
                    "",
                )
            )

            if not action:
                continue

            count += 1

            lines.append(
                f"{count}. {action}"
            )

        return (
            "\n".join(lines),
            sources,
        )

    if is_location_question(question):
        return (
            f"Thủ tục {procedure_name} "
            f"được thực hiện tại: "
            f"{authority}.",
            sources,
        )

    if is_fee_question(question):
        fee = clean_text(
            getattr(
                procedure,
                "fee",
                "",
            )
        )

        return (
            f"Lệ phí của thủ tục "
            f"{procedure_name}: "
            f"{fee or 'Chưa có dữ liệu trong CSDL nội bộ.'}",
            sources,
        )

    if is_time_question(question):
        processing_time = format_multiline_text(
            getattr(
                procedure,
                "processing_time",
                "",
            ),
            split_labels=[
                "Trực tiếp",
                "Trực tuyến",
                "Thời gian tiếp nhận hồ sơ",
            ],
        )

        if not processing_time:
            return (
                "CSDL nội bộ chưa có dữ liệu "
                f"về thời hạn giải quyết thủ tục "
                f"{procedure_name}.",
                sources,
            )

        lines = [
            f"Thời hạn giải quyết thủ tục "
            f"{procedure_name}:"
        ]

        for line in processing_time.splitlines():
            lines.append(
                f"- {line}"
            )

        return (
            "\n".join(lines),
            sources,
        )

    description = clean_text(
        getattr(
            procedure,
            "description",
            "",
        )
    )

    lines = [
        f"Thủ tục: {procedure_name}",
        f"Cơ quan thực hiện: {authority}",
    ]

    if description:
        lines.append(
            f"Mô tả: {description}"
        )

    lines.append(
        "Bạn có thể hỏi thêm về giấy tờ, "
        "biểu mẫu, nơi nộp, thời hạn, "
        "cách thực hiện hoặc căn cứ pháp lý."
    )

    return (
        "\n".join(lines),
        sources,
    )




# =========================================================
# CÂU HỎI NHIỀU Ý TRÊN CÙNG MỘT THỦ TỤC
# "Đăng ký tạm trú cần giấy tờ gì và lệ phí bao nhiêu?"
# =========================================================

QUESTION_TYPE_CHECKS = [
    ("legal", is_legal_reference_question, "can cu phap ly"),
    ("form", is_form_question, "bieu mau"),
    ("documents", is_document_question, "can giay to gi"),
    ("steps", is_step_question, "cac buoc"),
    ("location", is_location_question, "nop o dau"),
    ("fee", is_fee_question, "le phi bao nhieu"),
    ("time", is_time_question, "mat bao lau"),
]


def detect_question_types_by_clause(question: str) -> list[str]:
    """
    Nhận diện các loại thông tin được hỏi, mỗi vế (ngăn bởi "và", dấu phẩy)
    lấy một loại. Chỉ dùng khi câu có nhiều vế để tránh trả lời thừa.
    """

    clauses = []

    # tách dấu phẩy trước khi chuẩn hóa (chuẩn hóa sẽ bỏ dấu câu)
    for piece in re.split(r"[,;]", question or ""):
        normalized = normalize_text(piece)
        clauses.extend(
            clause
            for clause in re.split(r"\s*\b(?:va|voi)\b\s*", normalized)
            if clause.strip()
        )

    if len(clauses) < 2:
        return []

    types = []

    for clause in clauses:
        for type_name, checker, _ in QUESTION_TYPE_CHECKS:
            if checker(f" {clause} "):
                if type_name not in types:
                    types.append(type_name)
                break

    return types if len(types) >= 2 else []


def build_answer(
    db: Session,
    procedure: Procedure,
    question: str,
) -> tuple[str, list[dict]]:
    """
    Soạn câu trả lời từ CSDL. Nếu câu hỏi gồm nhiều ý (hồ sơ + lệ phí...)
    thì ghép câu trả lời của từng ý.
    """

    types = detect_question_types_by_clause(question)

    if not types:
        return build_local_answer(db=db, procedure=procedure, question=question)

    canonical = {name: phrase for name, _, phrase in QUESTION_TYPE_CHECKS}
    answers = []
    sources = []

    for type_name in types:
        answer, type_sources = build_local_answer(
            db=db,
            procedure=procedure,
            question=canonical[type_name],
        )
        answers.append(answer)
        sources = sources or type_sources

    return "\n\n".join(answers), sources
