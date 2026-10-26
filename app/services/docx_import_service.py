from pathlib import Path
import re
import unicodedata

from docx import Document
from docx.document import Document as WordDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.oxml.ns import qn

from sqlalchemy.orm import Session

from app.models import (
    LegalReference,
    Procedure,
    ProcedureStep,
    RequiredDocument,
)


class DocxImportError(Exception):
    pass


def normalize_text(value: str) -> str:
    if not value:
        return ""

    value = str(value).strip().lower()
    value = value.replace("đ", "d")

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


def get_paragraph_text(
    paragraph: Paragraph,
) -> str:
    """
    Đọc nội dung chữ, xuống dòng và hyperlink
    trong file Word.
    """

    parts = []

    for element in paragraph._p.iter():
        if element.tag == qn("w:t"):
            parts.append(
                element.text or ""
            )

        elif element.tag == qn("w:tab"):
            parts.append(" ")

        elif element.tag in {
            qn("w:br"),
            qn("w:cr"),
        }:
            parts.append("\n")

    text = "".join(parts)

    # Đọc URL thực tế của hyperlink
    for hyperlink in paragraph._p.iter(
        qn("w:hyperlink")
    ):
        relationship_id = hyperlink.get(
            qn("r:id")
        )

        if not relationship_id:
            continue

        relationship = paragraph.part.rels.get(
            relationship_id
        )

        if relationship is None:
            continue

        target = str(
            getattr(
                relationship,
                "target_ref",
                "",
            )
            or ""
        ).strip()

        if target.startswith(
            (
                "http://",
                "https://",
            )
        ):
            if target not in text:
                text += "\n" + target

    return text.strip()


def iter_block_items(parent):
    """
    Đọc đoạn văn và bảng theo đúng thứ tự
    xuất hiện trong file Word.
    """

    if isinstance(parent, WordDocument):
        parent_element = parent.element.body
    else:
        parent_element = parent._tc

    for child in parent_element.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(
                child,
                parent,
            )

        elif isinstance(child, CT_Tbl):
            yield Table(
                child,
                parent,
            )


INFO_LABELS = {
    "ma thu tuc": "procedure_code",
    "ten thu tuc": "name",
    "nhom linh vuc": "category",
    "nhom thu tuc": "category",
    "doi tuong thuc hien": "target",
    "mo ta": "description",
    "mo ta ngan": "description",
    "dieu kien": "conditions",
    "co quan thuc hien": "authority",
    "cach thuc hien": "method",
    "phuong thuc thuc hien": "method",
    "url nguon": "source_url",
    "link thu tuc": "source_url",
    "ten nguon": "source_title",
    "trang thai": "status",
    "thoi han": "processing_time",
    "phi le phi": "fee",
    "ket qua": "result",
    "ngay kiem tra": "last_verified_at",
}


def read_table_headers(
    table: Table,
) -> list[str]:
    if not table.rows:
        return []

    return [
        normalize_text(cell.text)
        for cell in table.rows[0].cells
    ]


def read_table_row(row) -> list[str]:
    return [
        clean_text(cell.text)
        for cell in row.cells
    ]


def read_documents_from_table(
    table: Table,
) -> list[dict]:
    """
    Đọc bảng:

    Tên giấy tờ | Mẫu đơn, tờ khai | Số lượng
    """

    headers = read_table_headers(
        table
    )

    if "ten giay to" not in headers:
        return []

    name_index = headers.index(
        "ten giay to"
    )

    form_index = None

    if "mau don to khai" in headers:
        form_index = headers.index(
            "mau don to khai"
        )

    quantity_index = None

    if "so luong" in headers:
        quantity_index = headers.index(
            "so luong"
        )

    documents = []

    for row in table.rows[1:]:
        values = read_table_row(row)

        if (
            name_index >= len(values)
            or not values[name_index]
        ):
            continue

        document_name = values[
            name_index
        ]

        form_name = ""

        if (
            form_index is not None
            and form_index < len(values)
        ):
            form_name = values[
                form_index
            ]

        quantity_text = ""

        if (
            quantity_index is not None
            and quantity_index < len(values)
        ):
            quantity_text = values[
                quantity_index
            ]

        normalized_name = normalize_text(
            document_name
        )

        is_required = 1

        if (
            "khong yeu cau"
            in normalized_name
            or "khong bat buoc"
            in normalized_name
        ):
            is_required = 0

        normalized_quantity = normalize_text(
            quantity_text
        )

        quantity = 1

        if (
            "ban chinh 0"
            in normalized_quantity
            and "ban sao 0"
            in normalized_quantity
        ):
            quantity = 0

        elif (
            "ban chinh 1"
            in normalized_quantity
            and "ban sao 1"
            in normalized_quantity
        ):
            quantity = 2

        documents.append(
            {
                "document_name": document_name,
                "is_required": is_required,
                "quantity": quantity,
                "document_type": quantity_text,
                "applicable_condition": "",
                "form_name": form_name,
                "form_url": "",
                "note": "",
            }
        )

    return documents


def parse_step_paragraph(
    text: str,
) -> tuple[int | None, str | None]:
    text = clean_text(text)

    match = re.match(
        r"^[\-\+\*]?\s*"
        r"Bước\s+(\d+)\s*:\s*(.*)$",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None, None

    return (
        int(match.group(1)),
        clean_text(match.group(2)),
    )


def find_form_code(text: str) -> str:
    """
    Nhận diện các mã biểu mẫu:

    CT01, CT02
    CC01, CC02
    DC01, DC02
    """

    normalized = normalize_text(
        text
    )

    match = re.search(
        r"\b(?:ct|cc|dc)\d{2}\b",
        normalized,
    )

    if not match:
        return ""

    return match.group(0).upper()


def is_minor_form(form: dict) -> bool:
    text = normalize_text(
        " ".join(
            [
                form.get("name", ""),
                form.get("condition", ""),
                form.get("note", ""),
            ]
        )
    )

    return (
        "chua thanh nien" in text
        or "nguoi chua thanh nien" in text
        or "cha me" in text
        or "nguoi giam ho" in text
    )


def is_minor_document(
    document: dict,
) -> bool:
    text = normalize_text(
        " ".join(
            [
                document.get(
                    "document_name",
                    "",
                ),
                document.get(
                    "form_name",
                    "",
                ),
                document.get(
                    "applicable_condition",
                    "",
                ),
            ]
        )
    )

    return (
        "chua thanh nien" in text
        or "nguoi chua thanh nien" in text
        or "cha me" in text
        or "nguoi giam ho" in text
    )


def attach_forms_to_documents(
    documents: list[dict],
    forms: list[dict],
) -> list[dict]:
    """
    Gắn biểu mẫu vào giấy tờ theo đúng mã.

    Hỗ trợ:
    - CT01, CT02
    - CC01, CC02
    - DC01, DC02

    Hai biểu mẫu có thể cùng mã nhưng khác
    điều kiện áp dụng.
    """

    used_document_indexes = set()

    for form in forms:
        form_url = clean_text(
            form.get("form_url", "")
        )

        if not form_url:
            continue

        form_code = normalize_text(
            form.get(
                "code",
                "",
            )
        )

        form_is_minor = is_minor_form(
            form
        )

        candidate_index = None

        for index, document in enumerate(
            documents
        ):
            if index in used_document_indexes:
                continue

            document_text = normalize_text(
                " ".join(
                    [
                        document.get(
                            "document_name",
                            "",
                        ),
                        document.get(
                            "form_name",
                            "",
                        ),
                    ]
                )
            )

            document_codes = re.findall(
                r"\b(?:ct|cc|dc)\d{2}\b",
                document_text,
            )

            # Chỉ ghép đúng mã biểu mẫu.
            #
            # Ví dụ:
            # CC01 chỉ ghép với dòng có CC01.
            # DC02 chỉ ghép với dòng có DC02.
            if (
                form_code
                and form_code.lower()
                not in document_codes
            ):
                continue

            document_is_minor = (
                is_minor_document(document)
            )

            if (
                form_is_minor
                == document_is_minor
            ):
                candidate_index = index
                break

        if candidate_index is not None:
            document = documents[
                candidate_index
            ]

            document["form_url"] = (
                form_url
            )

            document[
                "applicable_condition"
            ] = form.get(
                "condition",
                "",
            )

            document["note"] = form.get(
                "note",
                "",
            )

            used_document_indexes.add(
                candidate_index
            )

        else:
            documents.append(
                {
                    "document_name": form.get(
                        "name",
                        "Biểu mẫu",
                    ),
                    "is_required": 1,
                    "quantity": 1,
                    "document_type": (
                        "Mã biểu mẫu: "
                        + form.get(
                            "code",
                            "",
                        )
                    ),
                    "applicable_condition": (
                        form.get(
                            "condition",
                            "",
                        )
                    ),
                    "form_name": form.get(
                        "name",
                        "",
                    ),
                    "form_url": form_url,
                    "note": form.get(
                        "note",
                        "",
                    ),
                }
            )

    return documents


def remove_duplicate_documents(
    documents: list[dict],
) -> list[dict]:
    """
    Loại bỏ giấy tờ trùng hoàn toàn.
    """

    result = []
    seen = set()

    for document in documents:
        key = (
            normalize_text(
                document.get(
                    "document_name",
                    "",
                )
            ),
            normalize_text(
                document.get(
                    "form_name",
                    "",
                )
            ),
            normalize_text(
                document.get(
                    "applicable_condition",
                    "",
                )
            ),
            clean_text(
                document.get(
                    "form_url",
                    "",
                )
            ),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(document)

    return result


def looks_like_legal_reference(
    text: str,
) -> bool:
    normalized = normalize_text(
        text
    )

    legal_starts = (
        "luat ",
        "thong tu ",
        "nghi dinh ",
        "quyet dinh ",
        "phap lenh ",
    )

    return (
        normalized.startswith(
            legal_starts
        )
        and " so " in (
            f" {normalized} "
        )
    )


def parse_inline_legal_reference(
    text: str,
) -> dict | None:
    """
    Đọc dạng:

    Luật 68/2020/QH14 Số: 68/2020/QH14
    Thông tư 56/2021/TT-BCA Số: 56/2021/TT-BCA
    """

    text = clean_text(text)

    if not text:
        return None

    match = re.search(
        r"\bSố\s*:\s*(.+)$",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        document_number = clean_text(
            match.group(1)
        )

        document_name = clean_text(
            text[:match.start()]
        ).strip(" -:;")

    else:
        document_name = text
        document_number = ""

    if not document_name:
        return None

    normalized_name = normalize_text(
        document_name
    )

    document_type = ""

    if normalized_name.startswith(
        "luat "
    ):
        document_type = "Luật"

    elif normalized_name.startswith(
        "thong tu "
    ):
        document_type = "Thông tư"

    elif normalized_name.startswith(
        "nghi dinh "
    ):
        document_type = "Nghị định"

    elif normalized_name.startswith(
        "quyet dinh "
    ):
        document_type = "Quyết định"

    return {
        "document_name": document_name,
        "document_number": document_number,
        "document_type": document_type,
        "article_reference": "",
        "source_url": "",
        "effective_date": "",
        "note": "",
    }


def add_legal_reference(
    legal_references: list[dict],
    reference: dict,
):
    document_name = clean_text(
        reference.get(
            "document_name",
            "",
        )
    )

    if not document_name:
        return

    key = (
        normalize_text(
            reference.get(
                "document_name",
                "",
            )
        ),
        normalize_text(
            reference.get(
                "document_number",
                "",
            )
        ),
        clean_text(
            reference.get(
                "source_url",
                "",
            )
        ),
    )

    for existing in legal_references:
        existing_key = (
            normalize_text(
                existing.get(
                    "document_name",
                    "",
                )
            ),
            normalize_text(
                existing.get(
                    "document_number",
                    "",
                )
            ),
            clean_text(
                existing.get(
                    "source_url",
                    "",
                )
            ),
        )

        if existing_key == key:
            return

    reference["document_name"] = (
        document_name
    )

    legal_references.append(
        reference
    )


def parse_docx(
    file_path: str | Path,
) -> dict:
    file_path = Path(file_path)

    if not file_path.exists():
        raise DocxImportError(
            f"Không tìm thấy file: {file_path}"
        )

    if file_path.suffix.lower() != ".docx":
        raise DocxImportError(
            "Chỉ hỗ trợ file .docx."
        )

    try:
        document = Document(
            str(file_path)
        )

    except Exception as error:
        raise DocxImportError(
            f"Không thể đọc file Word: {error}"
        ) from error

    procedure = {
        "procedure_code": "",
        "name": "",
        "category": "",
        "target": "",
        "description": "",
        "conditions": "",
        "authority": "",
        "method": "",
        "processing_time": "",
        "fee": "",
        "result": "",
        "source_url": "",
        "source_title": "",
        "last_verified_at": "",
        "status": "",
    }

    steps = []
    documents = []
    forms = []
    legal_references = []

    current_section = ""
    current_step = None
    current_form = None

    pending_form_name = ""
    pending_form_condition = ""
    pending_url_field = None

    pending_legal = {
        "document_name": "",
        "document_number": "",
        "document_type": "",
        "article_reference": "",
        "source_url": "",
        "effective_date": "",
        "note": "",
    }

    method_lines = []
    time_lines = []
    fee_lines = []
    result_lines = []

    def flush_pending_legal():
        nonlocal pending_legal

        if pending_legal.get(
            "document_name",
            "",
        ):
            add_legal_reference(
                legal_references,
                dict(pending_legal),
            )

        pending_legal = {
            "document_name": "",
            "document_number": "",
            "document_type": "",
            "article_reference": "",
            "source_url": "",
            "effective_date": "",
            "note": "",
        }

    for block in iter_block_items(
        document
    ):
        if isinstance(block, Paragraph):
            raw_text = get_paragraph_text(
                block
            )

            if not raw_text:
                continue

            for raw_line in raw_text.splitlines():
                text = clean_text(
                    raw_line
                )

                if not text:
                    continue

                normalized = normalize_text(
                    text
                )

                # Các tiêu đề chính
                if normalized == "cach thuc hien":
                    current_section = "method"
                    continue

                if normalized == "cac buoc":
                    current_section = "steps"
                    continue

                if normalized == "ho so":
                    current_section = "documents"
                    continue

                if normalized == "thoi han":
                    current_section = "time"
                    continue

                if normalized == "phi le phi":
                    current_section = "fee"
                    continue

                if normalized == "ket qua":
                    current_section = "result"
                    continue

                if normalized == "can cu phap ly":
                    if current_section == "legal":
                        flush_pending_legal()

                    current_section = "legal"
                    continue

                if normalized == "bieu mau":
                    current_section = "forms"
                    continue

                # Đọc cách thức thực hiện
                if current_section == "method":
                    method_lines.append(text)
                    continue

                # Đọc căn cứ pháp lý
                if current_section == "legal":
                    if text.startswith(
                        (
                            "http://",
                            "https://",
                        )
                    ):
                        pending_legal[
                            "source_url"
                        ] = text
                        continue

                    if ":" in text:
                        label, value = (
                            text.split(
                                ":",
                                1,
                            )
                        )

                        normalized_label = (
                            normalize_text(
                                label
                            )
                        )

                        value = clean_text(
                            value
                        )

                        if normalized_label in {
                            "ten van ban",
                            "van ban",
                            "ten can cu phap ly",
                        }:
                            if pending_legal.get(
                                "document_name",
                                "",
                            ):
                                flush_pending_legal()

                            pending_legal[
                                "document_name"
                            ] = value
                            continue

                        if normalized_label in {
                            "so",
                            "so van ban",
                            "so ky hieu",
                        }:
                            pending_legal[
                                "document_number"
                            ] = value
                            continue

                        if normalized_label in {
                            "loai van ban",
                            "loai",
                        }:
                            pending_legal[
                                "document_type"
                            ] = value
                            continue

                        if normalized_label in {
                            "dieu",
                            "dieu khoan",
                            "can cu",
                        }:
                            pending_legal[
                                "article_reference"
                            ] = value
                            continue

                        if normalized_label in {
                            "link",
                            "link van ban",
                            "url van ban",
                        }:
                            pending_legal[
                                "source_url"
                            ] = value
                            continue

                    inline_reference = (
                        parse_inline_legal_reference(
                            text
                        )
                    )

                    if inline_reference:
                        if pending_legal.get(
                            "document_name",
                            "",
                        ):
                            flush_pending_legal()

                        add_legal_reference(
                            legal_references,
                            inline_reference,
                        )

                    continue

                # Các dòng có nhãn và giá trị
                if ":" in text:
                    label, value = (
                        text.split(
                            ":",
                            1,
                        )
                    )

                    normalized_label = (
                        normalize_text(
                            label
                        )
                    )

                    value = clean_text(
                        value
                    )

                    # Tên biểu mẫu
                    if normalized_label == "ten bieu mau":
                        pending_form_name = value
                        pending_form_condition = ""

                        if (
                            "chua thanh nien"
                            in normalize_text(value)
                        ):
                            pending_form_condition = (
                                "Dùng cho người đăng ký "
                                "tạm trú chưa thành niên."
                            )

                        continue

                    # Điều kiện biểu mẫu
                    if normalized_label in {
                        "dieu kien ap dung",
                        "ap dung cho",
                    }:
                        if current_form is not None:
                            current_form[
                                "condition"
                            ] = value
                        else:
                            pending_form_condition = value

                        continue

                    # Mã biểu mẫu
                    if normalized_label == "ma bieu mau":
                        code = find_form_code(
                            value
                        )

                        if code:
                            current_form = {
                                "code": code,
                                "name": (
                                    pending_form_name
                                    or f"Biểu mẫu {code}"
                                ),
                                "condition": (
                                    pending_form_condition
                                ),
                                "note": "",
                                "form_url": "",
                            }

                            forms.append(
                                current_form
                            )

                            pending_form_name = ""
                            pending_form_condition = ""

                        continue

                    # Link biểu mẫu
                    if normalized_label == "link tai":
                        if value.startswith(
                            (
                                "http://",
                                "https://",
                            )
                        ):
                            if current_form is not None:
                                current_form[
                                    "form_url"
                                ] = value
                        else:
                            pending_url_field = (
                                "form_url"
                            )

                        continue

                    # Các trường thông tin thủ tục
                    field_name = None

                    label_map = {
                        "ma thu tuc": "procedure_code",
                        "ten thu tuc": "name",
                        "nhom linh vuc": "category",
                        "nhom thu tuc": "category",
                        "doi tuong thuc hien": "target",
                        "mo ta": "description",
                        "mo ta ngan": "description",
                        "dieu kien": "conditions",
                        "co quan thuc hien": "authority",
                        "cach thuc hien": "method",
                        "phuong thuc thuc hien": "method",
                        "url nguon": "source_url",
                        "link thu tuc": "source_url",
                        "ten nguon": "source_title",
                        "trang thai": "status",
                        "thoi han": "processing_time",
                        "phi le phi": "fee",
                        "ket qua": "result",
                        "ngay kiem tra": "last_verified_at",
                    }

                    field_name = label_map.get(
                        normalized_label
                    )

                    if field_name:
                        if value:
                            procedure[
                                field_name
                            ] = value
                        else:
                            pending_url_field = (
                                field_name
                            )

                        continue

                # URL nguồn ở dòng tiếp theo
                if pending_url_field == "source_url":
                    if text.startswith(
                        (
                            "http://",
                            "https://",
                        )
                    ):
                        procedure[
                            "source_url"
                        ] = text

                        pending_url_field = None
                        continue

                # URL biểu mẫu ở dòng tiếp theo
                if (
                    pending_url_field == "form_url"
                    and text.startswith(
                        (
                            "http://",
                            "https://",
                        )
                    )
                ):
                    if current_form is not None:
                        current_form[
                            "form_url"
                        ] = text

                    pending_url_field = None
                    continue

                # Các bước
                if current_section == "steps":
                    step_no, action = (
                        parse_step_paragraph(
                            text
                        )
                    )

                    if step_no is not None:
                        current_step = {
                            "step_no": step_no,
                            "action": action,
                            "responsible_unit": "",
                            "note": "",
                        }

                        steps.append(
                            current_step
                        )

                    elif current_step is not None:
                        current_step[
                            "action"
                        ] += " " + text

                    continue

                # Thời hạn
                if current_section == "time":
                    time_lines.append(text)
                    continue

                # Lệ phí
                if current_section == "fee":
                    fee_lines.append(text)
                    continue

                # Kết quả
                if current_section == "result":
                    if looks_like_legal_reference(
                        text
                    ):
                        continue

                    result_lines.append(text)
                    continue

        elif isinstance(block, Table):
            table_documents = (
                read_documents_from_table(
                    block
                )
            )

            if table_documents:
                documents.extend(
                    table_documents
                )

    if current_section == "legal":
        flush_pending_legal()

    if method_lines:
        procedure["method"] = "\n".join(
            method_lines
        )

    if time_lines:
        procedure["processing_time"] = (
            "\n".join(time_lines)
        )

    if fee_lines:
        procedure["fee"] = (
            "\n".join(fee_lines)
        )

    # Sửa lỗi DOCX bị dính dòng, ví dụ:
    # "...theo quy định của pháp luật).Phí/lệ phí: không có"
    # Khi đó phần lệ phí bị đọc nhầm vào trường thời hạn.
    fee_pattern = re.compile(
        r"Phí\s*/\s*lệ phí\s*:\s*(.*)$",
        re.IGNORECASE | re.DOTALL,
    )
    processing_text = (
        procedure.get("processing_time") or ""
    )
    fee_match = fee_pattern.search(
        processing_text
    )
    if fee_match:
        procedure["processing_time"] = (
            processing_text[: fee_match.start()]
            .strip()
        )
        if not clean_text(
            procedure.get("fee", "")
        ):
            procedure["fee"] = (
                fee_match.group(1).strip()
            )

    if result_lines:
        procedure["result"] = (
            "\n".join(result_lines)
        )

    procedure_name = clean_text(
        procedure.get(
            "name",
            "",
        )
    )

    if not procedure.get("description"):
        procedure["description"] = (
            f"Thủ tục {procedure_name}."
        )

    if not procedure.get("target"):
        procedure["target"] = "Công dân"

    if not procedure.get("source_title"):
        procedure["source_title"] = (
            f"{procedure_name} - "
            "Cổng Dịch vụ công Bộ Công an"
        )

    if not procedure.get("status"):
        procedure["status"] = "VERIFIED"

    forms = [
        form
        for form in forms
        if clean_text(
            form.get("form_url", "")
        )
    ]

    documents = attach_forms_to_documents(
        documents,
        forms,
    )

    documents = remove_duplicate_documents(
        documents
    )

    required_fields = {
        "procedure_code": "Mã thủ tục",
        "name": "Tên thủ tục",
        "category": "Nhóm thủ tục",
        "source_url": "URL nguồn",
    }

    missing_fields = []

    for field_name, display_name in (
        required_fields.items()
    ):
        if not clean_text(
            procedure.get(field_name, "")
        ):
            missing_fields.append(
                display_name
            )

    if missing_fields:
        raise DocxImportError(
            "Thiếu thông tin bắt buộc: "
            + ", ".join(missing_fields)
        )

    return {
        "procedure": procedure,
        "steps": steps,
        "documents": documents,
        "forms": forms,
        "legal_references": legal_references,
    }


def upsert_procedure(
    db: Session,
    data: dict,
) -> dict:
    procedure_data = data["procedure"]

    procedure_code = clean_text(
        procedure_data.get(
            "procedure_code",
            "",
        )
    )

    procedure = (
        db.query(Procedure)
        .filter(
            Procedure.procedure_code
            == procedure_code
        )
        .first()
    )

    is_new = procedure is None

    if is_new:
        procedure = Procedure(
            procedure_code=procedure_code,
            name=procedure_data.get(
                "name",
                "",
            ),
            category=procedure_data.get(
                "category",
                "",
            ),
            source_url=procedure_data.get(
                "source_url",
                "",
            ),
        )

        db.add(procedure)

    fields_to_update = [
        "name",
        "category",
        "target",
        "description",
        "conditions",
        "authority",
        "method",
        "processing_time",
        "fee",
        "result",
        "source_url",
        "source_title",
        "last_verified_at",
        "status",
    ]

    for field_name in fields_to_update:
        if hasattr(
            procedure,
            field_name,
        ):
            setattr(
                procedure,
                field_name,
                clean_text(
                    procedure_data.get(
                        field_name,
                        "",
                    )
                ),
            )

    db.flush()

    # Xóa dữ liệu chi tiết cũ để tránh trùng
    db.query(ProcedureStep).filter(
        ProcedureStep.procedure_id
        == procedure.id
    ).delete(
        synchronize_session=False
    )

    db.query(RequiredDocument).filter(
        RequiredDocument.procedure_id
        == procedure.id
    ).delete(
        synchronize_session=False
    )

    db.query(LegalReference).filter(
        LegalReference.procedure_id
        == procedure.id
    ).delete(
        synchronize_session=False
    )

    # Thêm bước mới
    for step_data in data.get(
        "steps",
        [],
    ):
        db.add(
            ProcedureStep(
                procedure_id=procedure.id,
                step_no=step_data[
                    "step_no"
                ],
                action=step_data[
                    "action"
                ],
                responsible_unit=(
                    step_data.get(
                        "responsible_unit",
                        "",
                    )
                    or None
                ),
                note=(
                    step_data.get(
                        "note",
                        "",
                    )
                    or None
                ),
            )
        )

    # Thêm giấy tờ và biểu mẫu
    for document_data in data.get(
        "documents",
        [],
    ):
        db.add(
            RequiredDocument(
                procedure_id=procedure.id,
                document_name=document_data[
                    "document_name"
                ],
                is_required=document_data[
                    "is_required"
                ],
                quantity=document_data[
                    "quantity"
                ],
                document_type=(
                    document_data.get(
                        "document_type",
                        "",
                    )
                    or None
                ),
                applicable_condition=(
                    document_data.get(
                        "applicable_condition",
                        "",
                    )
                    or None
                ),
                form_url=(
                    document_data.get(
                        "form_url",
                        "",
                    )
                    or None
                ),
                note=(
                    document_data.get(
                        "note",
                        "",
                    )
                    or None
                ),
            )
        )

    # Thêm căn cứ pháp lý
    for reference in data.get(
        "legal_references",
        [],
    ):
        document_name = clean_text(
            reference.get(
                "document_name",
                "",
            )
        )

        if not document_name:
            continue

        db.add(
            LegalReference(
                procedure_id=procedure.id,
                document_number=(
                    reference.get(
                        "document_number",
                        "",
                    )
                    or None
                ),
                document_name=document_name,
                document_type=(
                    reference.get(
                        "document_type",
                        "",
                    )
                    or None
                ),
                article_reference=(
                    reference.get(
                        "article_reference",
                        "",
                    )
                    or None
                ),
                source_url=(
                    reference.get(
                        "source_url",
                        "",
                    )
                    or None
                ),
                effective_date=(
                    reference.get(
                        "effective_date",
                        "",
                    )
                    or None
                ),
                note=(
                    reference.get(
                        "note",
                        "",
                    )
                    or None
                ),
            )
        )

    return {
        "procedure_id": procedure.id,
        "procedure_code": procedure_code,
        "action": (
            "created"
            if is_new
            else "updated"
        ),
        "steps_count": len(
            data.get("steps", [])
        ),
        "documents_count": len(
            data.get("documents", [])
        ),
        "forms_count": len(
            data.get("forms", [])
        ),
        "legal_references_count": len(
            data.get(
                "legal_references",
                [],
            )
        ),
    }