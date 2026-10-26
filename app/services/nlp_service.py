"""
Xử lý ngôn ngữ tự nhiên cho CivicBot (luật + từ khóa).

- Chuẩn hóa tiếng Việt (bỏ dấu, chữ thường, bỏ ký tự đặc biệt).
- Nhận diện câu chào.
- Nhận diện chủ đề thủ tục (thường trú, tạm trú, căn cước...).
- Phân loại loại câu hỏi (hồ sơ, biểu mẫu, các bước, nơi nộp,
  lệ phí, thời hạn, căn cứ pháp lý).

Tách ra từ app/routers/chat.py để mỗi module
chỉ đảm nhận một nhiệm vụ (Single Responsibility).
"""

import re
import unicodedata
from typing import Optional

from app.models import Procedure


# =========================================================
# HÀM TIỆN ÍCH
# =========================================================

def normalize_text(value: str) -> str:
    if not value:
        return ""

    value = str(value).strip().lower()

    value = value.replace(
        "đ",
        "d",
    )

    value = unicodedata.normalize(
        "NFD",
        value,
    )

    value = "".join(
        character
        for character in value
        if unicodedata.category(character) != "Mn"
    )

    value = re.sub(
        r"[^\w\s]",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def clean_text(value) -> str:
    if value is None:
        return ""

    value = str(value).strip()

    return re.sub(
        r"\s+",
        " ",
        value,
    )


def format_multiline_text(
    value,
    split_labels: Optional[list[str]] = None,
) -> str:
    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    text = text.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    )

    if split_labels:
        labels_pattern = "|".join(
            re.escape(label)
            for label in split_labels
        )

        text = re.sub(
            rf"\s+(?=(?:{labels_pattern})"
            rf"(?:\s*:|\s+\d|\s*$))",
            "\n",
            text,
            flags=re.IGNORECASE,
        )

    lines = []

    for line in text.splitlines():
        line = re.sub(
            r"[ \t]+",
            " ",
            line,
        ).strip()

        if line.startswith("-"):
            line = line[1:].strip()

        if line.startswith("•"):
            line = line[1:].strip()

        if line:
            lines.append(line)

    return "\n".join(lines)


def is_greeting(question: str) -> bool:
    normalized = normalize_text(
        question
    )

    normalized = re.sub(
        r"[!?.,;:]+$",
        "",
        normalized,
    ).strip()

    return normalized in {
        "xin chao",
        "chao",
        "chao ban",
        "hello",
        "hi",
        "alo",
        "cam on",
        "cam on ban",
        "thanks",
    }


# =========================================================
# NHẬN DIỆN CHỦ ĐỀ
# =========================================================

TOPIC_KEYWORDS = {
    "permanent_residence": [
        "thuong tru",
        "dang ky thuong tru",
        "nhap ho khau",
    ],
    "temporary_residence": [
        "tam tru",
        "dang ky tam tru",
        "gia han tam tru",
        "thue tro",
        "o tro",
        "nha tro",
        "phong tro",
        "thue nha",
    ],
    "temporary_absence": [
        "tam vang",
        "khai bao tam vang",
        "thong bao tam vang",
        "dang ky tam vang",
    ],
    "residence_confirmation": [
        "xac nhan thong tin cu tru",
        "xac nhan thong tin ve cu tru",
        "xac nhan cu tru",
        "giay xac nhan cu tru",
    ],
    "residence_adjustment": [
        "dieu chinh thong tin cu tru",
        "dieu chinh thong tin ve cu tru",
        "thay doi thong tin cu tru",
        "thay doi thong tin ve cu tru",
    ],
    "residence_notification": [
        "thong bao luu tru",
        "luu tru",
    ],
    "permanent_residence_deletion": [
        "xoa dang ky thuong tru",
        "xoa thuong tru",
    ],
    "temporary_residence_deletion": [
        "xoa dang ky tam tru",
        "xoa tam tru",
    ],
    "household_separation": [
        "tach ho",
        "tach khau",
    ],
    "identity_card": [
        "can cuoc",
        "the can cuoc",
        "can cuoc cong dan",
        "cap lai can cuoc",
        "cap doi can cuoc",
        "cap the can cuoc",
    ],
    "passport": [
        "ho chieu",
        "cap ho chieu",
        "mat ho chieu",
        "doi ho chieu",
    ],
}

ALL_TOPIC_KEYWORDS = sorted(
    {keyword for keywords in TOPIC_KEYWORDS.values() for keyword in keywords},
    key=len,
    reverse=True,
)


def detect_topics(
    question: str,
) -> list[str]:
    """
    Nhận diện chủ đề thủ tục trong câu hỏi.

    Nếu câu hỏi không chứa bất kỳ chủ đề nào,
    hàm trả về danh sách rỗng.

    Ví dụ:
        "giá xăng hôm nay là bao nhiêu"
        -> []

        "đăng ký tạm trú cần giấy tờ gì"
        -> ["temporary_residence"]
    """

    normalized = normalize_text(
        question
    )

    topics = []

    topic_keywords = TOPIC_KEYWORDS

    for topic_name, keywords in topic_keywords.items():
        if any(
            keyword in normalized
            for keyword in keywords
        ):
            topics.append(topic_name)

    return topics


def get_procedure_topics(
    procedure: Procedure,
) -> set[str]:
    """
    Xác định chủ đề của một thủ tục
    dựa trên các trường dữ liệu của thủ tục.
    """

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

    procedure_text = " ".join(
        clean_text(field)
        for field in fields
        if field
    )

    return set(
        detect_topics(
            procedure_text
        )
    )


# =========================================================
# NHẬN DIỆN LOẠI CÂU HỎI
# =========================================================

def is_legal_reference_question(
    question: str,
) -> bool:
    normalized = normalize_text(
        question
    )

    keywords = [
        "can cu phap ly",
        "co so phap ly",
        "van ban phap ly",
        "duoc quy dinh o dau",
        "quy dinh o van ban nao",
        "theo luat nao",
        "theo thong tu nao",
        "theo nghi dinh nao",
        "luat nao quy dinh",
        "thong tu nao quy dinh",
        "nghi dinh nao quy dinh",
        "can cu vao dau",
        "co van ban nao",
        "van ban nao quy dinh",
    ]

    return any(
        keyword in normalized
        for keyword in keywords
    )


def is_method_question(
    question: str,
) -> bool:
    normalized = normalize_text(
        question
    )

    keywords = [
        "truc tiep",
        "truc tuyen",
        "online",
        "qua mang",
        "nop online",
        "nop qua mang",
        "nop ho so truc tuyen",
        "co dang ky online duoc khong",
        "dang ky truc tuyen duoc khong",
        "co the dang ky truc tuyen khong",
        "truc tiep hay truc tuyen",
        "cach thuc hien",
        "hinh thuc nop",
        "nop ho so bang cach nao",
    ]

    return any(
        keyword in normalized
        for keyword in keywords
    )


def is_document_question(
    question: str,
) -> bool:
    normalized = normalize_text(
        question
    )

    keywords = [
        "giay to",
        "ho so",
        "tai lieu",
        "can chuan bi",
        "can mang gi",
        "chuan bi gi",
        "can nhung gi",
        "can gi",
        "thanh phan ho so",
        "ho so gom",
        "can nhung gi",
        "nop gi",
    ]

    return any(
        keyword in normalized
        for keyword in keywords
    )


def is_form_question(
    question: str,
) -> bool:
    normalized = normalize_text(
        question
    )

    keywords = [
        "mau don",
        "bieu mau",
        "mau to khai",
        "xin mau",
        "tai mau",
        "link mau",
        "mau dang ky",
        "mau ct01",
    ]

    return any(
        keyword in normalized
        for keyword in keywords
    )


def is_step_question(
    question: str,
) -> bool:
    normalized = normalize_text(
        question
    )

    keywords = [
        "cach dang ky",
        "cach thuc hien",
        "huong dan",
        "quy trinh",
        "cac buoc",
        "nhung buoc",
        "buoc nao",
        "may buoc",
        "buoc thuc hien",
        "trinh tu",
        "lam the nao",
        "lam sao",
        "cap lai the nao",
        "cap doi the nao",
        "xin cap lai the nao",
        "lam lai the nao",
        "xin the nao",
        "can lam gi",
        "phai lam gi",
        "phai lam sao",
        "thuc hien nhu the nao",
        "dang ky nhu the nao",
        "nop ho so",
    ]

    return any(
        keyword in normalized
        for keyword in keywords
    )


def is_location_question(
    question: str,
) -> bool:
    normalized = normalize_text(
        question
    )

    keywords = [
        "o dau",
        "noi nao",
        "co quan nao",
        "nop o dau",
        "thuc hien o dau",
        "co quan thuc hien",
        "dia diem nao",
        "lam tai dau",
    ]

    return any(
        keyword in normalized
        for keyword in keywords
    )


def is_fee_question(
    question: str,
) -> bool:
    # Thêm khoảng trắng hai đầu để "phi" chỉ khớp
    # nguyên từ, tránh khớp nhầm "phieu" (phiếu).
    normalized = " " + normalize_text(
        question
    ) + " "

    keywords = [
        "le phi",
        " phi ",
        "bao nhieu tien",
        "mat bao nhieu tien",
        "chi phi",
    ]

    return any(
        keyword in normalized
        for keyword in keywords
    )


def is_time_question(
    question: str,
) -> bool:
    normalized = normalize_text(
        question
    )

    keywords = [
        "bao lau",
        "thoi han",
        "thoi gian",
        "may ngay",
        "bao nhieu ngay",
        "han giai quyet",
    ]

    return any(
        keyword in normalized
        for keyword in keywords
    )




# =========================================================
# CÂU HỎI VỀ VIỆC CHUYỂN NƠI Ở
# =========================================================

MOVING_KEYWORDS = [
    "chuyen nha",
    "chuyen cho o",
    "chuyen noi o",
    "chuyen den noi moi",
    "chuyen ve o",
    "doi noi o",
    "doi cho o",
    "chuyen ho khau",
    "chuyen khau",
    "don nha",
    "chuyen di noi khac",
]


def is_moving_question(
    question: str,
) -> bool:
    """
    Người dân thường hỏi "chuyển nhà thì làm gì"
    mà không biết tên thủ tục (thường trú hay tạm trú).
    """

    normalized = normalize_text(
        question
    )

    return any(
        keyword in normalized
        for keyword in MOVING_KEYWORDS
    )


def has_specific_question_type(
    question: str,
) -> bool:
    """
    Câu hỏi có hỏi một loại thông tin cụ thể không
    (dùng cho câu hỏi nối tiếp, ví dụ "Thế lệ phí bao nhiêu?").
    """

    return any(
        checker(question)
        for checker in (
            is_document_question,
            is_form_question,
            is_step_question,
            is_location_question,
            is_fee_question,
            is_time_question,
            is_legal_reference_question,
            is_method_question,
        )
    )


def is_follow_up_question(question: str) -> bool:
    """
    Câu hỏi nối tiếp là câu ngắn, không nêu tên thủ tục mới.
    Ví dụ: "Mất bao lâu?", "Thế lệ phí bao nhiêu?".
    Câu "Thủ tục đăng ký kết hôn cần gì?" KHÔNG phải câu nối tiếp
    (lỗi phát hiện khi kiểm thử: trước đây bị gán nhầm thủ tục của câu trước).
    """

    normalized = normalize_text(question)

    if len(normalized.split()) > 8:
        return False

    return not any(
        marker in normalized
        for marker in ["thu tuc", "dang ky", "giay phep"]
    )


COMPOUND_SEPARATORS = r"\s*(?:,|;|\bva\b|\bvoi\b|\bcung nhu\b|\bca\b)\s*"


def _first_topic_span(text: str) -> tuple[int, int] | None:
    """
    Vị trí cụm từ chủ đề "lõi" đầu tiên trong đoạn (đã chuẩn hóa).
    Ví dụ "toi bi mat ho chieu": cụm khớp sớm nhất là "mat ho chieu",
    lõi là "ho chieu" để phần "toi bi mat" được dùng làm ngữ cảnh chung.
    """

    matches = []

    for keyword in ALL_TOPIC_KEYWORDS:
        index = text.find(keyword)

        if index >= 0:
            matches.append((index, index + len(keyword)))

    if not matches:
        return None

    first = min(matches, key=lambda m: (m[0], -(m[1] - m[0])))
    inside = [m for m in matches if m[0] >= first[0] and m[1] <= first[1]]

    return min(inside, key=lambda m: m[1] - m[0])


def split_compound_question(question: str) -> list[str]:
    """
    Tách câu hỏi kép thành các câu hỏi con (dạng đã chuẩn hóa).

    Ví dụ: "Tôi bị mất hộ chiếu và căn cước công dân thì cần phải làm gì"
      -> ["toi bi mat ho chieu thi can phai lam gi",
          "toi bi mat can cuoc cong dan thi can phai lam gi"]

    Trả về [] nếu câu hỏi chỉ nói về một chủ đề.
    """

    import re

    # tách dấu phẩy trước khi chuẩn hóa (chuẩn hóa sẽ bỏ dấu câu)
    parts = []

    for piece in re.split(r"[,;]", question or ""):
        parts.extend(
            part.strip()
            for part in re.split(COMPOUND_SEPARATORS, normalize_text(piece))
            if part and part.strip()
        )

    topic_parts = []

    for part in parts:
        topics = detect_topics(part)
        if topics:
            topic_parts.append((part, frozenset(topics)))
        elif topic_parts:
            # đoạn không có chủ đề (ví dụ "le phi bao nhieu") gộp vào đoạn trước
            prev_part, prev_topics = topic_parts[-1]
            topic_parts[-1] = (f"{prev_part} va {part}", prev_topics)

    if len(topic_parts) < 2:
        return []

    if len({topics for _, topics in topic_parts}) < 2:
        return []

    first_text = topic_parts[0][0]
    last_text = topic_parts[-1][0]

    first_span = _first_topic_span(first_text)
    last_span = _first_topic_span(last_text)

    # phần mở đầu chung (vd. "toi bi mat") và phần ý hỏi chung (vd. "thi can phai lam gi")
    lead = first_text[: first_span[0]].strip() if first_span else ""
    tail = last_text[last_span[1]:].strip() if last_span else ""
    tail = re.sub(r"^(cong dan|nguoi dung)\b", "", tail).strip()

    sub_questions = []

    for part, _ in topic_parts:
        span = _first_topic_span(part)
        sub = part

        if span and span[0] == 0 and lead:
            sub = f"{lead} {sub}"

        if tail and tail not in sub and not has_specific_question_type(sub):
            sub = f"{sub} {tail}"

        sub_questions.append(sub)

    return sub_questions
