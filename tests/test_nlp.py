"""Kiểm thử đơn vị: chuẩn hóa văn bản và nhận diện loại câu hỏi."""

import pytest

from app.services.nlp_service import (
    detect_topics,
    is_document_question,
    is_fee_question,
    is_greeting,
    is_location_question,
    is_step_question,
    is_time_question,
    normalize_text,
)


def test_normalize_text_bo_dau_va_chu_hoa():
    assert "dang ky tam tru" in normalize_text("ĐĂNG KÝ Tạm Trú")


@pytest.mark.parametrize("question", ["xin chào", "Chào bạn", "hello"])
def test_nhan_dien_loi_chao(question):
    assert is_greeting(question)


def test_cau_hoi_thu_tuc_khong_phai_loi_chao():
    assert not is_greeting("Đăng ký tạm trú cần giấy tờ gì?")


@pytest.mark.parametrize(
    "checker, question",
    [
        (is_document_question, "Đăng ký tạm trú cần giấy tờ gì?"),
        (is_fee_question, "Lệ phí cấp lại căn cước là bao nhiêu?"),
        (is_time_question, "Đăng ký thường trú mất bao lâu?"),
        (is_location_question, "Tách hộ nộp hồ sơ ở đâu?"),
        (is_step_question, "Khai báo tạm vắng gồm những bước nào?"),
    ],
)
def test_nhan_dien_loai_cau_hoi(checker, question):
    assert checker(question)


def test_tu_phi_khong_bi_nham_trong_tu_khac():
    # "phi" nằm trong từ khác (ví dụ "phiếu") không được coi là hỏi lệ phí
    assert not is_fee_question("Cần phiếu đề nghị nào?")


def test_nhan_dien_chu_de_cu_tru_va_can_cuoc():
    assert detect_topics("đăng ký tạm trú")
    assert detect_topics("cấp lại thẻ căn cước")
