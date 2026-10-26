"""Kiểm thử bộ đọc DOCX thủ tục hành chính."""

from pathlib import Path

import pytest

from app.services.docx_import_service import parse_docx
from tests.conftest import PROCEDURE_FILES


def test_co_du_14_tep_thu_tuc():
    assert len(PROCEDURE_FILES) == 14


@pytest.mark.parametrize("path", PROCEDURE_FILES, ids=lambda p: Path(p).stem[:8])
def test_moi_tep_doc_duoc_ma_ten_va_cac_buoc(path):
    data = parse_docx(path)
    code = Path(path).name.split("_")[0]

    assert data["procedure"]["procedure_code"] == code
    assert data["procedure"]["name"]
    assert data.get("steps"), "Thủ tục phải có ít nhất 1 bước thực hiện"


def test_loi_da_sua_le_phi_khong_dinh_vao_thoi_han():
    """
    Lỗi phát hiện khi kiểm thử: thủ tục 1.010028 có dòng
    'Phí/lệ phí: không có' bị dính vào trường thời hạn giải quyết.
    """
    path = next(p for p in PROCEDURE_FILES if "1.010028" in p)
    data = parse_docx(path)

    assert "lệ phí" not in (data["procedure"]["processing_time"] or "").lower()
