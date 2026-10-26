"""
Các tiện ích bảo mật dùng chung cho CivicBot.

- Kiểm tra khóa quản trị (X-Admin-Key) cho API nhạy cảm.
- Giới hạn số yêu cầu theo địa chỉ IP (rate limit).
- Kiểm tra tệp tải lên: định dạng và dung lượng.
"""

import os
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

ALLOWED_UPLOAD_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".pdf",
    ".docx",
}


def get_max_upload_bytes() -> int:
    try:
        max_mb = float(os.getenv("MAX_UPLOAD_MB", "10"))
    except ValueError:
        max_mb = 10

    return int(max_mb * 1024 * 1024)


def is_admin_key_valid(provided_key: str | None) -> bool:
    """
    Nếu chưa cấu hình ADMIN_API_KEY (môi trường phát triển),
    API quản trị được mở để nhóm tiện thử nghiệm.
    Khi triển khai thật bắt buộc phải đặt ADMIN_API_KEY.
    """

    expected_key = os.getenv("ADMIN_API_KEY", "").strip()

    if not expected_key:
        return True

    return secrets.compare_digest(
        (provided_key or "").strip(),
        expected_key,
    )


def validate_upload_name(file_name: str) -> str | None:
    """
    Trả về thông báo lỗi nếu định dạng không hợp lệ,
    trả về None nếu hợp lệ.
    """

    suffix = Path(file_name or "").suffix.lower()

    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        return (
            "Định dạng tệp chưa được hỗ trợ. "
            "Bạn hãy gửi ảnh (PNG, JPG, WEBP), PDF hoặc DOCX."
        )

    return None


def build_safe_upload_name(file_name: str) -> str:
    """
    Sinh tên tệp ngẫu nhiên để tránh ghi đè
    và tránh tên tệp chứa ký tự nguy hiểm.
    """

    suffix = Path(file_name or "").suffix.lower()

    return f"{uuid.uuid4().hex}{suffix}"


class RateLimiter:
    """
    Giới hạn số yêu cầu trong một cửa sổ thời gian
    (sliding window) cho mỗi khóa (thường là IP).
    Lưu trong bộ nhớ, đủ dùng cho một tiến trình backend.
    """

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()

        with self._lock:
            hits = self._hits[key]

            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()

            if len(hits) >= self.max_requests:
                return False

            hits.append(now)
            return True


def build_chat_rate_limiter() -> RateLimiter:
    try:
        max_requests = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    except ValueError:
        max_requests = 60

    return RateLimiter(
        max_requests=max_requests,
        window_seconds=60,
    )
