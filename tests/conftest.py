"""
Cấu hình chung cho pytest.

- Dùng SQLite tạm thay cho MySQL để test chạy được trên máy bất kỳ và trên CI.
- AI_MODE=off: không gọi Gemini (test ổn định, không tốn hạn mức, không cần key).
- Nạp 14 thủ tục từ thư mục data/procedures trước khi chạy test.
"""

import glob
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

_DB_FILE = Path(tempfile.gettempdir()) / "civicbot_pytest.db"
if _DB_FILE.exists():
    _DB_FILE.unlink()

# Phải đặt biến môi trường TRƯỚC khi import app.*
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE.as_posix()}"
os.environ["AI_MODE"] = "off"
os.environ["GEMINI_API_KEY"] = ""
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["MAX_UPLOAD_MB"] = "1"
os.environ["KEEP_UPLOADS"] = "false"

import pytest  # noqa: E402

from app import models  # noqa: E402
from app.database import Base, SessionLocal, engine, ensure_schema_upgrades  # noqa: E402
from app.services.docx_import_service import parse_docx, upsert_procedure  # noqa: E402

PROCEDURE_FILES = sorted(glob.glob(str(ROOT / "data" / "procedures" / "[12]*.docx")))


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    Base.metadata.create_all(bind=engine)
    ensure_schema_upgrades()

    db = SessionLocal()
    try:
        if db.query(models.Procedure).count() == 0:
            for path in PROCEDURE_FILES:
                upsert_procedure(db, parse_docx(path))
        db.commit()
    finally:
        # đóng phiên ngay để SQLite không bị khóa khi các test ghi lịch sử
        db.close()

    yield


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
