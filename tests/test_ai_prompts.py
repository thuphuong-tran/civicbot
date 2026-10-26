"""Kiểm thử nội dung prompt Gemini (không gọi API thật)."""

import os
from contextlib import contextmanager

from app.services import ai_service
from app.services.ai_service import (
    is_administrative_question,
    GENERAL_QA_NOTE,
    build_out_of_scope_prompt,
    is_general_answer,
)


@contextmanager
def env(name, value):
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


def test_out_of_scope_prompt_keeps_procedure_safety():
    with env("GENERAL_QA", "true"):
        prompt = build_out_of_scope_prompt("Làm hộ chiếu cần gì?")
        assert "KHÔNG nêu số hiệu văn bản" in prompt
        assert "KHÔNG nêu số tiền lệ phí" in prompt
        assert "dichvucong.gov.vn" in prompt


def test_general_qa_enabled_answers_with_warning():
    with env("GENERAL_QA", "true"):
        prompt = build_out_of_scope_prompt("Tác dụng của mướp đắng là gì?")
        assert "KIẾN THỨC CHUNG" in prompt
        assert GENERAL_QA_NOTE in prompt
        assert "Từ chối lịch sự" not in prompt


def test_general_qa_disabled_refuses():
    with env("GENERAL_QA", "false"):
        prompt = build_out_of_scope_prompt("Tác dụng của mướp đắng là gì?")
        assert "Từ chối lịch sự" in prompt
        assert GENERAL_QA_NOTE not in prompt


def test_is_general_answer():
    assert is_general_answer("Mướp đắng giúp thanh nhiệt.\n" + GENERAL_QA_NOTE)
    assert not is_general_answer("Câu hỏi này nằm ngoài dữ liệu chính thức của CivicBot.")
    assert not is_general_answer("")


def test_ai_off_returns_none():
    with env("AI_MODE", "off"):
        assert ai_service.generate_ai_fallback_answer("Tác dụng của mướp đắng?") is None


def test_phan_loai_cau_hoi_thu_tuc_hanh_chinh():
    """Lỗi Q32/Q36: câu thủ tục bị coi là kiến thức chung."""
    for question in [
        "Đăng ký khai sinh cho con cần giấy tờ gì?",
        "Đăng ký xe máy cần giấy tờ gì?",
        "Làm hộ chiếu cần gì?",
        "Đổi bằng lái xe ở đâu?",
        "Thủ tục đăng ký kết hôn ở đâu?",
        "mất hộ chiếu cần làm thủ tục gì",
    ]:
        assert is_administrative_question(question), question

    for question in [
        "Tác dụng của mướp đắng là gì?",
        "Thời tiết Hà Nội hôm nay",
        "Giá xăng hôm nay bao nhiêu?",
        "Việt Nam có bao nhiêu dân tộc",
    ]:
        assert not is_administrative_question(question), question


def test_prompt_thu_tuc_khong_dung_nhanh_kien_thuc_chung():
    with env("GENERAL_QA", "true"):
        prompt = build_out_of_scope_prompt("Đăng ký xe máy cần giấy tờ gì?")
        assert GENERAL_QA_NOTE not in prompt
        assert "KHÔNG nêu số tiền lệ phí" in prompt


class _FakeModels:
    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = []

    def generate_content(self, model, contents):
        self.calls.append(model)
        if self.errors:
            raise self.errors.pop(0)
        return "OK"


class _FakeClient:
    def __init__(self, errors):
        self.models = _FakeModels(errors)


def test_gemini_qua_tai_duoc_thu_lai():
    """Lỗi 503 tạm thời được thử lại; lỗi 504 không thử lại."""
    import time as time_module

    from app.services.ai_service import generate_with_retry

    original_sleep = time_module.sleep
    time_module.sleep = lambda seconds: None
    try:
        with env("GEMINI_RETRIES", "2"):
            client = _FakeClient([Exception("503 UNAVAILABLE")])
            assert generate_with_retry(client, ["hi"]) == "OK"
            assert len(client.models.calls) == 2

            client = _FakeClient([Exception("504 DEADLINE_EXCEEDED")])
            try:
                generate_with_retry(client, ["hi"])
                assert False, "504 phải được báo lỗi ngay"
            except Exception as error:
                assert "504" in str(error)
            assert len(client.models.calls) == 1
    finally:
        time_module.sleep = original_sleep
