import os
import re
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


def clean_ai_text(text: str) -> str:
    """
    Làm sạch nội dung trả về từ Gemini.
    """

    if not text:
        return ""

    text = str(text).strip()

    text = text.replace("```markdown", "")
    text = text.replace("```text", "")
    text = text.replace("```", "")

    text = re.sub(
        r"(?m)^\s*#{1,6}\s*",
        "",
        text,
    )

    text = re.sub(
        r"(?m)^\s*[-*_]{3,}\s*$",
        "",
        text,
    )

    text = re.sub(
        r"\*\*(.*?)\*\*",
        r"\1",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"(?<!\w)\*(.*?)\*",
        r"\1",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"__(.*?)__",
        r"\1",
        text,
        flags=re.DOTALL,
    )

    text = re.sub(
        r"(?m)^\s*[-+*]\s+",
        "• ",
        text,
    )

    text = re.sub(
        r"(?m)^\s*>\s?",
        "",
        text,
    )

    text = re.sub(
        r"\[([^]]+)\]\([^)]+\)",
        r"\1",
        text,
    )

    text = re.sub(
        r"\s+([,.!?;:])",
        r"\1",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


def get_model_name() -> str:
    """
    Lấy tên model Gemini từ file .env.
    """

    model_name = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.8-flash",
    ).strip()

    model_name = model_name.strip('"')
    model_name = model_name.strip("'")

    if model_name.startswith("models/"):
        model_name = model_name.replace(
            "models/",
            "",
            1,
        )

    return model_name


def get_gemini_client():
    """
    Tạo Gemini client.
    """

    api_key = os.getenv(
        "GEMINI_API_KEY",
        "",
    ).strip()

    if not api_key:
        return None

    from google import genai

    # Giới hạn thời gian chờ để một lần gọi Gemini chậm/treo không làm
    # người dùng chờ hàng phút (mặc định 25 giây, chỉnh bằng GEMINI_TIMEOUT).
    try:
        timeout_seconds = float(os.getenv("GEMINI_TIMEOUT", "25"))
    except ValueError:
        timeout_seconds = 25.0

    try:
        from google.genai import types

        return genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_seconds * 1000),
            ),
        )
    except Exception:
        return genai.Client(
            api_key=api_key,
        )


def is_temporary_gemini_error(error: Exception) -> bool:
    """Lỗi tạm thời phía máy chủ Gemini (quá tải) -> nên thử lại."""

    text = str(error)

    return any(
        marker in text
        for marker in ("503", "UNAVAILABLE", "500", "INTERNAL", "overloaded")
    )


def generate_with_retry(client, contents):
    """
    Gọi Gemini, tự thử lại khi máy chủ quá tải (503).
    - GEMINI_RETRIES: số lần thử lại (mặc định 2), chờ 1 s rồi 2 s.
    - GEMINI_FALLBACK_MODEL: model dự phòng cho lần thử cuối (tùy chọn).
    Không thử lại lỗi 504 (đã chờ hết GEMINI_TIMEOUT) hoặc 429 (hết hạn mức).
    """

    import time

    try:
        retries = max(0, int(os.getenv("GEMINI_RETRIES", "2")))
    except ValueError:
        retries = 2

    fallback_model = os.getenv("GEMINI_FALLBACK_MODEL", "").strip()
    model_name = get_model_name()

    for attempt in range(retries + 1):
        current_model = (
            fallback_model
            if fallback_model and attempt == retries and attempt > 0
            else model_name
        )

        try:
            return client.models.generate_content(
                model=current_model,
                contents=contents,
            )
        except Exception as error:
            if attempt >= retries or not is_temporary_gemini_error(error):
                raise

            print(
                f"Gemini quá tải, thử lại lần {attempt + 1}/{retries}..."
            )
            time.sleep(attempt + 1)


def call_gemini(
    prompt: str,
    extra_contents=None,
):
    """
    Gọi Gemini và trả về nội dung dạng text.
    """

    api_key = os.getenv(
        "GEMINI_API_KEY",
        "",
    ).strip()

    if not api_key:
        print(
            "Chưa cấu hình GEMINI_API_KEY."
        )
        return None

    try:
        client = get_gemini_client()

        if client is None:
            return None

        contents = [prompt]

        if extra_contents:
            contents.extend(extra_contents)

        response = generate_with_retry(client, contents)

        answer = getattr(
            response,
            "text",
            None,
        )

        if not answer:
            print(
                "Gemini không trả về nội dung."
            )
            return None

        return clean_ai_text(answer)

    except Exception as error:
        print("Gọi Gemini API thất bại.")
        print(f"Chi tiết lỗi: {error}")
        return None


def check_gemini_connection():
    """
    Kiểm tra API key và kết nối Gemini.
    """

    api_key = os.getenv(
        "GEMINI_API_KEY",
        "",
    ).strip()

    if not api_key:
        return {
            "ok": False,
            "message": (
                "Chưa cấu hình GEMINI_API_KEY "
                "trong file .env."
            ),
            "model": get_model_name(),
        }

    try:
        answer = call_gemini(
            "Hãy trả lời đúng một từ: OK"
        )

        if answer:
            return {
                "ok": True,
                "message": (
                    "Gemini API đang hoạt động."
                ),
                "model": get_model_name(),
            }

        return {
            "ok": False,
            "message": (
                "Gemini không trả về nội dung."
            ),
            "model": get_model_name(),
        }

    except Exception as error:
        return {
            "ok": False,
            "message": (
                "Không thể kết nối Gemini: "
                f"{error}"
            ),
            "model": get_model_name(),
        }


def is_ai_enabled() -> bool:
    ai_mode = os.getenv(
        "AI_MODE",
        "gemini",
    ).strip().lower()

    return ai_mode not in {
        "off",
        "none",
        "disabled",
    }


NO_DATA_MESSAGE = (
    "CivicBot chưa có dữ liệu chính thức cho câu hỏi này. "
    "Bạn vui lòng tra cứu tại Cổng Dịch vụ công Quốc gia "
    "(dichvucong.gov.vn) hoặc liên hệ Công an cấp xã nơi cư trú."
)


def build_grounded_prompt(
    question: str,
    context: str,
    conversation: str = "",
) -> str:
    """
    Prompt RAG: Gemini CHỈ được dùng dữ liệu trong ngữ cảnh.
    Hàm tách riêng để có thể kiểm thử nội dung prompt.
    """

    conversation_block = ""

    if conversation:
        conversation_block = f"""
LỊCH SỬ HỘI THOẠI GẦN NHẤT (chỉ để hiểu câu hỏi nối tiếp):
{conversation}
"""

    return f"""
Bạn là CivicBot, trợ lý tra cứu thủ tục cư trú và giấy tờ tùy thân.

QUY TẮC BẮT BUỘC:
1. Chỉ trả lời dựa trên phần DỮ LIỆU THỦ TỤC bên dưới.
2. Nếu DỮ LIỆU không đủ để trả lời, trả lời đúng câu:
   "{NO_DATA_MESSAGE}"
3. Không tự đặt số hiệu văn bản, lệ phí, thời hạn hoặc
   giấy tờ không có trong DỮ LIỆU.
4. Nếu câu hỏi chưa rõ thuộc thủ tục nào, nêu ngắn gọn
   các thủ tục phù hợp trong DỮ LIỆU và hỏi lại người dùng.
5. Trả lời bằng tiếng Việt, ngắn gọn, dễ hiểu, không dùng Markdown.
6. Dòng cuối cùng ghi: "Nguồn: <mã thủ tục đã dùng>".
{conversation_block}
DỮ LIỆU THỦ TỤC:
{context}

CÂU HỎI: {question}
"""


def generate_grounded_answer(
    question: str,
    context: str,
    conversation: str = "",
):
    """
    Gọi Gemini với ngữ cảnh lấy từ MySQL (RAG).
    Trả về None nếu AI bị tắt hoặc Gemini lỗi.
    """

    if not is_ai_enabled():
        return None

    if not context.strip():
        return None

    prompt = build_grounded_prompt(
        question=question,
        context=context,
        conversation=conversation,
    )

    return call_gemini(prompt)


GENERAL_QA_NOTE = (
    "Lưu ý: Nội dung trên do trí tuệ nhân tạo tổng hợp, chỉ có giá trị "
    "tham khảo và không thuộc dữ liệu chính thức của CivicBot."
)

GENERAL_QA_MARKER = "do trí tuệ nhân tạo tổng hợp"

OUT_OF_SCOPE_OPENING = "Câu hỏi này nằm ngoài dữ liệu chính thức của CivicBot."


def is_general_qa_enabled() -> bool:
    """
    GENERAL_QA=true (mặc định): cho phép Gemini trả lời câu hỏi
    kiến thức chung (không phải thủ tục hành chính), có nhãn cảnh báo.
    GENERAL_QA=false: từ chối lịch sự các câu hỏi ngoài lề.
    """

    value = os.getenv("GENERAL_QA", "true").strip().lower()

    return value not in {"false", "0", "off", "no"}


def is_general_answer(answer: str) -> bool:
    """Nhận biết câu trả lời thuộc nhánh kiến thức chung."""

    return bool(answer) and GENERAL_QA_MARKER in answer


# Từ khóa (không dấu) nhận biết câu hỏi về thủ tục hành chính / giấy tờ.
# Phân loại bằng mã nguồn thay vì để Gemini tự quyết, để kết quả ổn định
# và kiểm thử được (lỗi Q32/Q36: "khai sinh", "đăng ký xe máy" bị Gemini
# coi là kiến thức chung).
ADMIN_KEYWORDS = (
    "thu tuc", "giay to", "ho so", "dang ky", "cap lai", "cap doi", "cap moi",
    "lam lai", "gia han", "giay phep", "chung nhan", "xac nhan", "ho chieu",
    "visa", "thi thuc", "xuat nhap canh", "khai sinh", "khai tu", "ket hon",
    "ly hon", "con nuoi", "giam ho", "ho tich", "bang lai", "giay phep lai xe",
    "dang kiem", "bien so", "xe may", "o to", "le phi", "phi", "nop", "co quan",
    "uy ban", "ubnd", "cong an", "chung thuc", "cong chung", "sao y", "dat dai",
    "so do", "so hong", "quyen su dung dat", "xay dung", "kinh doanh",
    "doanh nghiep", "ma so thue", "thue", "bao hiem", "bhxh", "bhyt",
    "luong huu", "tro cap", "ly lich tu phap", "dich vu cong", "vneid",
    "dinh danh", "quoc tich", "phap luat", "luat", "nghi dinh", "thong tu",
)


def is_administrative_question(question: str) -> bool:
    """Câu hỏi có liên quan đến thủ tục hành chính / giấy tờ / pháp luật không."""

    from app.services.nlp_service import normalize_text

    text = f" {normalize_text(question)} "

    return any(f" {keyword} " in text for keyword in ADMIN_KEYWORDS)


def build_out_of_scope_prompt(question: str) -> str:
    """
    Câu hỏi KHÔNG có trong CSDL:
    - Thủ tục hành chính  -> hướng dẫn chung, cấm nêu con số cụ thể.
    - Kiến thức chung     -> trả lời tham khảo (GENERAL_QA=true) hoặc từ chối.
    """

    common = """Quy tắc chung: trả lời bằng tiếng Việt, không tự nhận là cơ quan
nhà nước, không dùng Markdown."""

    if is_administrative_question(question):
        return f"""
Bạn là trợ lý AI của CivicBot. Dữ liệu chính thức của CivicBot chỉ gồm thủ tục
cư trú và thẻ căn cước; câu hỏi sau về một thủ tục hành chính CHƯA có trong dữ liệu:

{question}

Quy tắc:
1. Trả lời trực tiếp, hữu ích theo cấu trúc: cơ quan tiếp nhận; các bước thực
   hiện chính (đánh số 1, 2, 3...); các giấy tờ thường phải chuẩn bị; hình thức
   nộp (trực tiếp / trực tuyến). Tối đa khoảng 10 dòng.
2. Chỉ nêu thông tin phổ biến, ổn định mà bạn chắc chắn; không chắc thì bỏ qua.
3. KHÔNG nêu số hiệu văn bản pháp luật, KHÔNG nêu số tiền lệ phí và
   KHÔNG nêu số ngày giải quyết cụ thể; nếu cần, ghi "theo quy định hiện hành".
4. Kết thúc bằng: "Thông tin có thể thay đổi theo quy định hiện hành, bạn nên
   kiểm tra lại tại dichvucong.gov.vn hoặc cơ quan tiếp nhận hồ sơ."
{common}
"""

    if not is_general_qa_enabled():
        return f"""
Bạn là trợ lý AI của CivicBot (tra cứu thủ tục cư trú và giấy tờ tùy thân).
Câu hỏi sau KHÔNG liên quan đến thủ tục hành chính:

{question}

Từ chối lịch sự trong 1–2 câu, cho biết CivicBot chỉ hỗ trợ tra cứu thủ tục
cư trú và giấy tờ tùy thân, và gợi ý người dùng đặt câu hỏi về các thủ tục này.
{common}
"""

    return f"""
Bạn là trợ lý AI của CivicBot. Câu hỏi sau là câu hỏi KIẾN THỨC CHUNG,
không phải thủ tục hành chính:

{question}

Quy tắc:
1. Trả lời trực tiếp, chính xác, ngắn gọn (tối đa 6 câu hoặc 5 ý).
2. Nếu không chắc chắn, nói rõ; không bịa số liệu.
3. Nếu câu hỏi cần dữ liệu thời gian thực (giá cả, thời tiết, tỷ giá, tin tức),
   nói rõ bạn không có dữ liệu cập nhật và gợi ý nguồn tra cứu phù hợp.
4. Với câu hỏi về sức khỏe, thuốc, pháp lý, tài chính: khuyên hỏi ý kiến
   chuyên gia (bác sĩ, luật sư...).
5. Dòng cuối cùng ghi đúng: "{GENERAL_QA_NOTE}"
{common}
"""


def generate_ai_fallback_answer(
    question: str,
):
    """
    Gọi Gemini khi CSDL nội bộ không có thủ tục liên quan.
    - Thủ tục hành chính ngoài CSDL: chỉ định hướng chung, không bịa chi tiết.
    - Kiến thức chung (GENERAL_QA=true): trả lời ngắn gọn, kèm nhãn cảnh báo.
    """

    if not is_ai_enabled():
        return None

    return call_gemini(
        build_out_of_scope_prompt(question)
    )


def generate_mock_answer(
    question,
    procedure,
    steps=None,
    documents=None,
    legal_references=None,
):
    """
    Hàm tương thích với các file cũ.
    """

    _ = question
    _ = steps
    _ = documents
    _ = legal_references

    procedure_name = getattr(
        procedure,
        "name",
        "thủ tục này",
    )

    description = getattr(
        procedure,
        "description",
        "",
    )

    authority = getattr(
        procedure,
        "authority",
        "",
    )

    lines = [
        f"Thủ tục: {procedure_name}",
    ]

    if authority:
        lines.append(
            f"Cơ quan thực hiện: {authority}"
        )

    if description:
        lines.append(
            f"Mô tả: {description}"
        )

    return "\n".join(lines)


def extract_text_from_file(
    file_bytes: bytes,
    file_name: str,
    mime_type: str,
) -> str:
    """
    Đọc nội dung PDF hoặc DOCX.
    """

    file_name = file_name or ""
    mime_type = mime_type or ""

    suffix = ""

    if "." in file_name:
        suffix = file_name.lower().rsplit(
            ".",
            1,
        )[-1]

    try:
        if (
            suffix == "pdf"
            or mime_type == "application/pdf"
        ):
            from pypdf import PdfReader

            reader = PdfReader(
                BytesIO(file_bytes)
            )

            pages = []

            for page in reader.pages:
                page_text = (
                    page.extract_text()
                    or ""
                ).strip()

                if page_text:
                    pages.append(page_text)

            return "\n\n".join(pages).strip()

        if suffix == "docx":
            from docx import Document

            document = Document(
                BytesIO(file_bytes)
            )

            paragraphs = []

            for paragraph in document.paragraphs:
                paragraph_text = paragraph.text.strip()

                if paragraph_text:
                    paragraphs.append(
                        paragraph_text
                    )

            for table in document.tables:
                for row in table.rows:
                    cells = []

                    for cell in row.cells:
                        cell_text = cell.text.strip()

                        if cell_text:
                            cells.append(cell_text)

                    if cells:
                        paragraphs.append(
                            " | ".join(cells)
                        )

            return "\n".join(paragraphs).strip()

        return ""

    except Exception as error:
        print("Đọc nội dung tệp thất bại.")
        print(f"Chi tiết lỗi: {error}")
        return ""


def generate_ai_image_answer(
    first_value,
    second_value=None,
    third_value=None,
):
    """
    Phân tích ảnh bằng Gemini.

    Hỗ trợ hai cách gọi:

    1. generate_ai_image_answer(
           file_path,
           question
       )

    2. generate_ai_image_answer(
           question,
           image_bytes,
           mime_type
       )
    """

    image_bytes = None
    question = ""
    mime_type = "image/jpeg"

    first_path = Path(str(first_value))

    if (
        third_value is None
        and first_path.exists()
    ):
        file_path = first_path
        question = str(
            second_value or ""
        ).strip()

        image_bytes = file_path.read_bytes()

        extension = file_path.suffix.lower()

        if extension == ".png":
            mime_type = "image/png"
        elif extension == ".webp":
            mime_type = "image/webp"
        elif extension == ".gif":
            mime_type = "image/gif"

    else:
        question = str(
            first_value or ""
        ).strip()

        image_bytes = second_value
        mime_type = (
            str(third_value)
            if third_value
            else "image/jpeg"
        )

    if not image_bytes:
        return None

    prompt = f"""
Bạn là trợ lý AI của CivicBot.

Câu hỏi của người dùng:

{question or "Hãy phân tích hình ảnh này."}

Hãy phân tích ảnh được gửi kèm
và trả lời bằng tiếng Việt,
ngắn gọn, đúng trọng tâm.

Nếu ảnh là giấy tờ hoặc biểu mẫu:

1. Xác định loại giấy tờ nếu nhìn thấy rõ.
2. Chỉ đọc thông tin nhìn thấy rõ.
3. Không đoán nội dung bị mờ hoặc bị che.
4. Không khẳng định giấy tờ chắc chắn hợp lệ.
5. Nếu liên quan đến thủ tục hành chính,
   hãy nói rõ chỉ mang tính tham khảo.
6. Không sử dụng Markdown.
"""

    try:
        from google.genai import types

        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type=mime_type,
        )

        return call_gemini(
            prompt,
            extra_contents=[
                image_part,
            ],
        )

    except Exception as error:
        print("Phân tích ảnh bằng Gemini thất bại.")
        print(f"Chi tiết lỗi: {error}")
        return None


def generate_ai_document_answer(
    first_value,
    second_value=None,
    third_value=None,
):
    """
    Phân tích PDF hoặc DOCX bằng Gemini.

    Hỗ trợ hai cách gọi:

    1. generate_ai_document_answer(
           file_path,
           question
       )

    2. generate_ai_document_answer(
           question,
           document_text,
           file_name
       )
    """

    first_path = Path(str(first_value))

    if (
        third_value is None
        and first_path.exists()
    ):
        file_path = first_path
        question = str(
            second_value or ""
        ).strip()

        file_bytes = file_path.read_bytes()

        document_text = extract_text_from_file(
            file_bytes=file_bytes,
            file_name=file_path.name,
            mime_type="",
        )

        file_name = file_path.name

    else:
        question = str(
            first_value or ""
        ).strip()

        document_text = str(
            second_value or ""
        ).strip()

        file_name = str(
            third_value or "tài liệu"
        )

    if not document_text:
        return None

    document_text = document_text[:30000]

    prompt = f"""
Bạn là trợ lý AI của CivicBot.

Tên tệp:

{file_name}

Câu hỏi của người dùng:

{question or "Hãy tóm tắt nội dung tài liệu."}

Nội dung tài liệu:

{document_text}

Hãy trả lời bằng tiếng Việt,
ngắn gọn và đúng trọng tâm.

Quy tắc:

1. Chỉ sử dụng nội dung có trong tài liệu.
2. Không tự bịa thông tin.
3. Nếu thông tin không có trong tài liệu,
   hãy nói rõ.
4. Nếu tài liệu liên quan đến thủ tục hành chính,
   hãy nói rõ câu trả lời chỉ mang tính tham khảo.
5. Không sử dụng Markdown.
"""

    return call_gemini(prompt)