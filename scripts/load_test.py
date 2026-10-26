"""
Đo tải đơn giản cho API /api/chat (chỉ dùng thư viện chuẩn Python).

Cách chạy (backend đang chạy ở cổng 8000):
    python scripts/load_test.py
    python scripts/load_test.py --url http://localhost:8000 --levels 10 20 50 --requests 100

Lưu ý:
- Nên đặt RATE_LIMIT_PER_MINUTE đủ lớn (vd. 100000) trong .env khi đo tải,
  nếu không các yêu cầu vượt ngưỡng sẽ bị trả mã 429.
- Câu hỏi dùng để đo đều nằm trong CSDL nên không gọi Gemini
  (đo hiệu năng phần backend + MySQL, không tốn hạn mức API).
"""

import argparse
import csv
import json
import statistics
import time
import urllib.parse
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

QUESTIONS = [
    "Đăng ký tạm trú cần giấy tờ gì?",
    "Đăng ký thường trú mất bao lâu?",
    "Cấp lại thẻ căn cước nộp ở đâu?",
    "Tách hộ gồm những bước nào?",
    "Khai báo tạm vắng có mất phí không?",
]


def send(url: str, index: int) -> tuple[float, int]:
    body = urllib.parse.urlencode(
        {
            "question": QUESTIONS[index % len(QUESTIONS)],
            "session_id": f"load-{uuid.uuid4().hex[:8]}",
        }
    ).encode()

    started = time.perf_counter()
    try:
        request = urllib.request.Request(f"{url}/api/chat", data=body, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:
            json.loads(response.read().decode("utf-8"))
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except Exception:
        status = 0

    return (time.perf_counter() - started) * 1000, status


def percentile(values: list[float], percent: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(percent / 100 * len(ordered)) - 1))
    return ordered[index]


def run_level(url: str, concurrency: int, total: int) -> dict:
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = list(pool.map(lambda i: send(url, i), range(total)))
    elapsed = time.perf_counter() - started

    latencies = [ms for ms, status in results if status == 200]
    errors = sum(status != 200 for _, status in results)

    return {
        "concurrency": concurrency,
        "requests": total,
        "success": len(latencies),
        "error_rate_%": round(100 * errors / total, 1),
        "avg_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        "p95_ms": round(percentile(latencies, 95), 1) if latencies else 0,
        "max_ms": round(max(latencies), 1) if latencies else 0,
        "throughput_rps": round(total / elapsed, 1),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--levels", nargs="+", type=int, default=[1, 10, 20, 50])
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--output", default="docs/ket-qua-do-tai.csv")
    args = parser.parse_args()

    rows = []
    print(f"{'Đồng thời':>9} {'Thành công':>10} {'Lỗi %':>6} {'TB ms':>8} {'P95 ms':>8} {'Max ms':>8} {'req/s':>7}")
    for level in args.levels:
        row = run_level(args.url.rstrip("/"), level, max(args.requests, level))
        rows.append(row)
        print(
            f"{row['concurrency']:>9} {row['success']:>10} {row['error_rate_%']:>6} "
            f"{row['avg_ms']:>8} {row['p95_ms']:>8} {row['max_ms']:>8} {row['throughput_rps']:>7}"
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nĐã lưu kết quả: {output}")


if __name__ == "__main__":
    main()
