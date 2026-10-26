"""Chạy lại bộ kiểm thử nội bộ (quick) mà giao diện quản trị dùng."""

from app.services.system_test_service import run_internal_tests


def test_bo_kiem_thu_noi_bo_deu_pass(db):
    results = run_internal_tests(db)
    failed = [r for r in results if r["status"] == "FAIL"]

    assert len(results) >= 18
    assert not failed, [f"{r['test_id']}: {r['detail']}" for r in failed]
