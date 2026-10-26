"""
Kiểm thử chức năng + chấp nhận: gọi trực tiếp hàm xử lý /api/chat
với bộ 40 câu hỏi đánh giá (data/eval/questions.csv).
"""

import csv
import re
import uuid
from pathlib import Path

import pytest

from app.routers.chat import chat

ROOT = Path(__file__).resolve().parents[1]

TYPE_MARKERS = {
    "documents": "Hồ sơ cần chuẩn bị",
    "steps": "Các bước thực hiện",
    "location": "được thực hiện tại",
    "fee": "Lệ phí của thủ tục",
    "time": "Thời hạn giải quyết",
    "legal": "Căn cứ pháp lý",
    "form": "Biểu mẫu",
    "general": "Thủ tục:",
    "suggestion": "Khi chuyển đến chỗ ở mới",
    "greeting": "Xin chào",
}

FAKE_DETAIL_PATTERNS = [
    r"\d+/\d{4}/(TT|NĐ|ND|QH)",
    r"\d[\d.]*\s*(đồng|vnđ|vnd)",
]

with (ROOT / "data" / "eval" / "questions.csv").open(encoding="utf-8") as f:
    CASES = list(csv.DictReader(f))


def ask(db, question, session_id=None):
    response = chat(
        question=question,
        file=None,
        session_id=session_id or f"pytest-{uuid.uuid4().hex[:8]}",
        db=db,
    )
    blocks = response.get("answer_blocks") or []
    answer = blocks[0].get("content", "") if blocks else ""
    return response, answer


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_bo_cau_hoi_danh_gia(db, case):
    response, answer = ask(db, case["question"])
    expected_code = case["expected_code"]

    if expected_code == "OUT":
        assert not response.get("procedure_code"), "Câu ngoài phạm vi không được gán thủ tục"
        for pattern in FAKE_DETAIL_PATTERNS:
            assert not re.search(pattern, answer, re.IGNORECASE), "Không được bịa số văn bản/lệ phí"
    elif expected_code in {"SUGGEST", "GREETING"}:
        assert TYPE_MARKERS[case["expected_type"]] in answer
    else:
        assert response.get("procedure_code") == expected_code
        assert TYPE_MARKERS[case["expected_type"]] in answer


def test_cau_hoi_rong(db):
    response, answer = ask(db, "")
    assert "nhập câu hỏi" in answer


def test_cau_hoi_noi_tiep_trong_cung_phien(db):
    session_id = f"pytest-followup-{uuid.uuid4().hex[:6]}"
    first, _ = ask(db, "Đăng ký tạm trú cần giấy tờ gì?", session_id)
    second, answer = ask(db, "Mất bao lâu?", session_id)

    assert first["procedure_code"] == "1.004194"
    assert second["procedure_code"] == "1.004194"
    assert "Thời hạn giải quyết" in answer


def test_ngoai_du_lieu_khi_tat_ai_khong_bia(db):
    response, answer = ask(db, "Thủ tục đăng ký kết hôn cần gì?")
    assert not response.get("procedure_code")
    assert response["route"] in {"no_data", "gemini_out_of_scope"}


def test_tu_dong_luu_lich_su_theo_phien(db):
    from app.models import ChatHistory

    session_id = f"pytest-history-{uuid.uuid4().hex[:6]}"
    ask(db, "Khai báo tạm vắng ở đâu?", session_id)

    saved = db.query(ChatHistory).filter(ChatHistory.session_id == session_id).all()
    assert len(saved) == 1
    assert saved[0].procedure_code == "1.003677"


def test_loi_da_sua_cau_ngoai_pham_vi_khong_bi_coi_la_cau_noi_tiep(db):
    """
    Lỗi phát hiện khi kiểm thử: sau câu hỏi về căn cước, câu
    'Thủ tục đăng ký kết hôn cần gì?' bị trả lời bằng hồ sơ căn cước.
    """
    session_id = f"pytest-rt04-{uuid.uuid4().hex[:6]}"
    ask(db, "Con tôi 10 tuổi có làm căn cước được không?", session_id)
    response, _ = ask(db, "Thủ tục đăng ký kết hôn cần gì?", session_id)

    assert not response.get("procedure_code")
    assert response["route"] != "local_followup"


def test_cau_hoi_tu_do_ve_thue_tro_duoc_dua_vao_chu_de_tam_tru(db):
    response, answer = ask(db, "Tôi thuê trọ ở Hà Nội để đi học thì cần làm thủ tục gì?")
    # AI tắt: gợi ý các thủ tục tạm trú; AI bật: Gemini trả lời dựa trên các thủ tục này
    assert response["route"] in {"local_candidates", "gemini_grounded", "local"}
    assert "tạm trú" in answer.lower()


def test_loi_da_sua_cau_hoi_chung_khong_dua_vao_rag(db):
    """
    Lỗi phát hiện khi demo: "Việt Nam có bao nhiêu dân tộc" bị lấy
    thủ tục căn cước làm ngữ cảnh vì trùng từ "Việt Nam", "dân tộc".
    """
    response, _ = ask(db, "Việt Nam có bao nhiêu dân tộc")
    assert not response.get("procedure_code")
    assert response["route"] in {"no_data", "gemini_out_of_scope", "gemini_general"}


def test_cau_hoi_kep_mot_phan_trong_mot_phan_ngoai_du_lieu(db):
    """
    Lỗi phát hiện khi chạy thử: "mất hộ chiếu và căn cước thì làm gì"
    chỉ trả lời căn cước (thông tin chung), bỏ qua phần hộ chiếu.
    """
    response, _ = ask(db, "Tôi bị mất hộ chiếu và căn cước công dân thì cần phải làm gì")
    labels = [block["source_label"] for block in response["answer_blocks"]]
    contents = " ".join(block["content"] for block in response["answer_blocks"])

    assert response["route"] == "compound"
    assert response["procedure_code"] == "2.001194"
    assert "Về hộ chiếu" in contents
    assert "Các bước thực hiện" in contents
    assert "CSDL NỘI BỘ" in labels


def test_cau_hoi_kep_hai_thu_tuc(db):
    response, _ = ask(db, "Đăng ký tạm trú và khai báo tạm vắng cần giấy tờ gì?")
    contents = [block["content"] for block in response["answer_blocks"]]

    assert response["route"] == "compound"
    assert len(contents) == 2
    assert "Đăng ký tạm trú" in contents[0] and "Khai báo tạm vắng" in contents[1]


def test_mot_thu_tuc_hoi_nhieu_y(db):
    response, answer = ask(db, "Đăng ký tạm trú nộp ở đâu, mất bao lâu?")
    assert response["procedure_code"] == "1.004194"
    assert "được thực hiện tại" in answer
    assert "Thời hạn giải quyết" in answer


def test_cau_hoi_kien_thuc_chung_co_nhan_canh_bao(db):
    """GENERAL_QA: giả lập Gemini trả lời kiến thức chung -> nhãn riêng, không nguồn CSDL."""
    import app.routers.chat as chat_module
    from app.services.ai_service import GENERAL_QA_NOTE

    original = chat_module.generate_ai_fallback_answer
    chat_module.generate_ai_fallback_answer = (
        lambda q: "Mướp đắng giúp thanh nhiệt, hỗ trợ tiêu hóa.\n" + GENERAL_QA_NOTE
    )
    try:
        response, answer = ask(db, "Tác dụng của mướp đắng là gì?")
    finally:
        chat_module.generate_ai_fallback_answer = original

    assert response["route"] == "gemini_general"
    assert not response.get("sources")
    assert not response.get("procedure_code")
    assert GENERAL_QA_NOTE in answer
