"""
Kiểm thử tích hợp qua HTTP bằng TestClient của FastAPI
(cần cài fastapi + httpx, đã có trong requirements.txt).
"""

import io

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_ket_noi_csdl():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"


def test_post_chat_tra_ve_thu_tuc():
    response = client.post(
        "/api/chat",
        data={"question": "Đăng ký tạm trú cần giấy tờ gì?", "session_id": "api-test"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["procedure_code"] == "1.004194"
    assert body["route"].startswith("local")


def test_lich_su_tach_theo_phien():
    client.post("/api/chat", data={"question": "Tách hộ ở đâu?", "session_id": "phien-A"})
    items_b = client.get("/api/history", params={"session_id": "phien-B"}).json()["items"]
    assert all(item["question"] != "Tách hộ ở đâu?" for item in items_b)


def test_xoa_toan_bo_lich_su_can_khoa_quan_tri():
    assert client.delete("/api/history").status_code == 403


def test_chay_kiem_thu_can_khoa_quan_tri():
    response = client.post("/api/system-tests/run", json={"suite": "quick"})
    assert response.status_code == 403


def test_tu_choi_tep_sai_dinh_dang():
    response = client.post(
        "/api/chat",
        data={"question": "", "session_id": "api-file"},
        files={"file": ("virus.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert response.status_code == 200
    assert response.json()["route"] == "file_rejected"


def test_danh_sach_thu_tuc():
    response = client.get("/api/procedures")
    assert response.status_code == 200


def test_tep_hop_le_khi_tat_ai_bao_ro_rang():
    response = client.post(
        "/api/chat",
        data={"question": "Tệp này nói gì?", "session_id": "api-file-2"},
        files={"file": ("anh.png", io.BytesIO(b"\x89PNG"), "image/png")},
    )
    assert response.json()["route"] == "file_ai_disabled"
