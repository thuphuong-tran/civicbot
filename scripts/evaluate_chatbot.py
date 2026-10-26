"""
Đánh giá chất lượng CivicBot trên bộ câu hỏi mẫu.

Cách chạy (trong thư mục civicbot, đã cấu hình CSDL):
    python scripts/evaluate_chatbot.py
    python scripts/evaluate_chatbot.py --output docs/ket-qua-danh-gia.csv

Chỉ số:
- Procedure accuracy : % câu trong phạm vi chọn đúng thủ tục.
- Type accuracy      : % câu trong phạm vi trả đúng loại thông tin.
- Out-of-scope safety: % câu ngoài phạm vi KHÔNG bị gán thủ tục
                       và KHÔNG có số văn bản / lệ phí tự bịa.
- Latency            : thời gian xử lý trung bình và P95 (ms).
"""

import argparse
import csv
import os
import re
import statistics
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Mặc định đánh giá ở chế độ tắt AI (đo phần CSDL + định tuyến, kết quả ổn định,
# không tốn hạn mức Gemini). Thêm --with-ai để đánh giá cả câu trả lời Gemini.
# Phải đặt trước khi import app vì load_dotenv không ghi đè biến đã có.
if "--with-ai" not in sys.argv:
    os.environ["AI_MODE"] = "off"

# Mặc định dùng CSDL SQLite riêng cho đánh giá (tự nạp 14 thủ tục từ DOCX),
# không cần mở cổng MySQL của Docker. Thêm --use-env-db để dùng CSDL trong .env.
if "--use-env-db" not in sys.argv:
    os.environ["DATABASE_URL"] = "sqlite:///civicbot_eval.db"

# Windows PowerShell: in tiếng Việt không lỗi mã hóa
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.database import Base, SessionLocal, engine, ensure_schema_upgrades  # noqa: E402
from app.models import ChatHistory  # noqa: E402
from app.routers.chat import chat  # noqa: E402
from app.services.ai_service import is_administrative_question  # noqa: E402

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


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(percent / 100 * len(ordered)) - 1))
    return ordered[index]


def seed_if_empty(db) -> None:
    """CSDL đánh giá còn trống -> nạp các thủ tục từ data/procedures/*.docx."""

    from app.models import Procedure
    from app.services.docx_import_service import parse_docx, upsert_procedure

    if db.query(Procedure).count() > 0:
        return

    files = sorted((ROOT / "data" / "procedures").glob("[12]*.docx"))
    print(f"CSDL đánh giá trống: đang nạp {len(files)} thủ tục từ DOCX...", flush=True)

    for path in files:
        upsert_procedure(db, parse_docx(str(path)))
        db.commit()


def evaluate(questions_path: Path, output_path: Path | None) -> dict:
    Base.metadata.create_all(bind=engine)
    ensure_schema_upgrades()

    db = SessionLocal()
    seed_if_empty(db)
    session_prefix = f"eval-{uuid.uuid4().hex[:8]}"
    rows = []

    with questions_path.open(encoding="utf-8") as file:
        cases = list(csv.DictReader(file))

    for index, case in enumerate(cases):
        started = time.perf_counter()
        response = chat(
            question=case["question"],
            file=None,
            # mỗi câu một phiên để các câu không ảnh hưởng nhau
            session_id=f"{session_prefix}-{index}",
            db=db,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        print(f"[{index + 1:2}/{len(cases)}] {case['question'][:60]}", flush=True)

        blocks = response.get("answer_blocks") or []
        answer = blocks[0].get("content", "") if blocks else ""
        actual_code = response.get("procedure_code") or ""
        route = response.get("route", "")

        expected_code = case["expected_code"]
        expected_type = case["expected_type"]

        if expected_code == "OUT":
            has_fake = any(
                re.search(pattern, answer, re.IGNORECASE)
                for pattern in FAKE_DETAIL_PATTERNS
            )
            # câu thủ tục hành chính không được đi nhánh "kiến thức chung"
            wrong_branch = (
                route == "gemini_general"
                and is_administrative_question(case["question"])
            )
            code_ok = not actual_code and not has_fake and not wrong_branch
            type_ok = code_ok
        elif expected_code in {"SUGGEST", "GREETING"}:
            code_ok = TYPE_MARKERS[expected_type] in answer
            type_ok = code_ok
        else:
            code_ok = actual_code == expected_code
            type_ok = code_ok and TYPE_MARKERS[expected_type] in answer

        rows.append(
            {
                "id": case["id"],
                "question": case["question"],
                "group": case["group"],
                "expected_code": expected_code,
                "actual_code": actual_code,
                "expected_type": expected_type,
                "route": route,
                "procedure_ok": "PASS" if code_ok else "FAIL",
                "type_ok": "PASS" if type_ok else "FAIL",
                "latency_ms": round(latency_ms, 1),
                "answer_preview": answer[:120].replace("\n", " / "),
            }
        )

    # dọn lịch sử do đánh giá tạo ra
    db.query(ChatHistory).filter(
        ChatHistory.session_id.like(f"{session_prefix}%")
    ).delete(synchronize_session=False)
    db.commit()
    db.close()

    in_scope = [row for row in rows if row["group"] == "in_scope"]
    out_scope = [row for row in rows if row["group"] == "out_of_scope"]
    latencies = [row["latency_ms"] for row in rows]

    def rate(items, key):
        if not items:
            return 0.0
        return round(100 * sum(row[key] == "PASS" for row in items) / len(items), 1)

    summary = {
        "total_questions": len(rows),
        "in_scope_procedure_accuracy_%": rate(in_scope, "procedure_ok"),
        "in_scope_type_accuracy_%": rate(in_scope, "type_ok"),
        "out_of_scope_safety_%": rate(out_scope, "procedure_ok"),
        "latency_avg_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        "latency_p95_ms": percentile(latencies, 95),
        "ai_mode": os.getenv("AI_MODE", "gemini"),
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    return {"summary": summary, "rows": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", default="data/eval/questions.csv")
    parser.add_argument("--output", default="docs/ket-qua-danh-gia-chatbot.csv")
    parser.add_argument(
        "--with-ai",
        action="store_true",
        help="Bật Gemini khi đánh giá (chậm hơn, tốn hạn mức API)",
    )
    parser.add_argument(
        "--use-env-db",
        action="store_true",
        help="Dùng CSDL cấu hình trong .env thay cho SQLite đánh giá",
    )
    args = parser.parse_args()

    result = evaluate(Path(args.questions), Path(args.output))

    for row in result["rows"]:
        print(
            f"{row['id']:4} {row['procedure_ok']:4} {row['type_ok']:4} "
            f"{row['route']:22} {row['question']}"
        )

    print("\nTỔNG HỢP")
    for key, value in result["summary"].items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()
