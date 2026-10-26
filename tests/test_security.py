"""Kiểm thử bảo mật: khóa quản trị, định dạng tệp, giới hạn tần suất."""

import os

from app.services.security_service import (
    RateLimiter,
    build_safe_upload_name,
    get_max_upload_bytes,
    is_admin_key_valid,
    validate_upload_name,
)


def test_khoa_quan_tri_dung_sai():
    assert is_admin_key_valid(os.environ["ADMIN_API_KEY"])
    assert not is_admin_key_valid("sai-khoa")
    assert not is_admin_key_valid(None)


def test_chi_nhan_dinh_dang_tep_cho_phep():
    for name in ["anh.png", "anh.JPG", "giay.pdf", "to-khai.docx"]:
        assert validate_upload_name(name) is None
    for name in ["virus.exe", "script.js", "khong-duoi"]:
        assert validate_upload_name(name) is not None


def test_ten_tep_luu_tru_duoc_doi_ngau_nhien():
    safe_name = build_safe_upload_name("../../etc/passwd.pdf")
    assert "/" not in safe_name and ".." not in safe_name
    assert safe_name.endswith(".pdf")


def test_gioi_han_dung_luong_lay_tu_bien_moi_truong():
    assert get_max_upload_bytes() == 1 * 1024 * 1024


def test_rate_limiter_chan_khi_vuot_nguong():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    assert all(limiter.allow("1.2.3.4") for _ in range(3))
    assert not limiter.allow("1.2.3.4")
    # IP khác không bị ảnh hưởng
    assert limiter.allow("5.6.7.8")
