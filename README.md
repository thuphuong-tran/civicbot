# CivicBot – Chatbot AI hỗ trợ tra cứu thủ tục cư trú và giấy tờ tùy thân

![CI](https://github.com/thuphuong-tran/civicbot/actions/workflows/ci.yml/badge.svg)

Đề tài môn **Các vấn đề hiện đại của Công nghệ phần mềm** – Nhóm 1, lớp K11 CNTTA, Học viện Phụ nữ Việt Nam.
GVHD: PGS.TS Ngô Tứ Thành. Sinh viên: Trần Thu Phương (2374820154), Lê Văn Đạt (2374820034).

CivicBot trả lời câu hỏi của công dân về **14 thủ tục** cư trú và thẻ căn cước (đăng ký/xóa thường trú, tạm trú, gia hạn tạm trú, tạm vắng, tách hộ, thông báo lưu trú, xác nhận/điều chỉnh thông tin cư trú, cấp – cấp đổi – cấp lại thẻ căn cước). Dữ liệu lấy từ Cổng Dịch vụ công Quốc gia, lưu trong MySQL; Google Gemini chỉ được gọi khi dữ liệu nội bộ không đủ để trả lời trực tiếp.

## Kiến trúc

```
Trình duyệt ──► React + Vite (nginx, cổng 5173)
                    │  REST /api/*
                    ▼
               FastAPI (cổng 8000) ──► MySQL 8 (mạng nội bộ Docker)
                    │
                    └── chỉ khi cần ──► Google Gemini API
```

| Thành phần | Công nghệ | Thư mục |
|---|---|---|
| Giao diện | React 19, Vite | `frontend/` |
| API | FastAPI, SQLAlchemy | `app/` |
| Xử lý câu hỏi | Chuẩn hóa tiếng Việt, nhận diện chủ đề/loại câu hỏi | `app/services/nlp_service.py` |
| Tra cứu thủ tục | Chấm điểm tên/từ khóa, nhóm tuổi, hành động | `app/services/procedure_service.py` |
| RAG nhẹ | Chọn top-3 thủ tục làm ngữ cảnh cho Gemini | `app/services/retrieval_service.py` |
| AI | Prompt có ngữ cảnh, chống bịa, fallback | `app/services/ai_service.py` |
| Bảo mật | Khóa quản trị, giới hạn tần suất, kiểm tra tệp | `app/services/security_service.py` |
| Nhập dữ liệu | Đọc DOCX thủ tục → MySQL | `app/services/docx_import_service.py`, `import_docx.py` |
| Kiểm thử | pytest + bộ kiểm thử nội bộ + đánh giá 40 câu | `tests/`, `app/services/system_test_service.py`, `scripts/` |

### Luồng xử lý một câu hỏi (`POST /api/chat`)

1. Câu rỗng / lời chào → trả lời ngay.
2. Có tệp đính kèm → kiểm tra định dạng & dung lượng → Gemini đọc tệp → xóa tệp sau khi xử lý.
3. Câu hỏi kép ("mất hộ chiếu **và** căn cước…") → tách thành các câu con, mỗi phần đi đúng nhánh (`compound`).
3b. Tìm được thủ tục trong CSDL **và** xác định được loại thông tin (hồ sơ, bước, nơi nộp, lệ phí, thời hạn, căn cứ, biểu mẫu) → **trả lời từ CSDL, không gọi Gemini** (`route=local`).
4. Câu hỏi nối tiếp ("mất bao lâu?") → dùng thủ tục của câu trước trong cùng `session_id` (`local_followup`).
5. Câu hỏi thuộc chủ đề nhưng diễn đạt tự do → lấy top-3 thủ tục liên quan làm ngữ cảnh → **Gemini trả lời dựa trên ngữ cảnh** (`gemini_grounded`). Nếu tắt AI → gợi ý các thủ tục gần nhất (`local_candidates`).
6. Thủ tục hành chính ngoài dữ liệu (hộ chiếu, kết hôn…) → Gemini hướng dẫn chung (cơ quan, các bước, giấy tờ thường cần), **cấm nêu số văn bản, lệ phí, thời hạn cụ thể** (`gemini_out_of_scope`); tắt AI → thông báo chưa có dữ liệu (`no_data`).
7. Câu hỏi kiến thức chung, không phải thủ tục (ví dụ "Tác dụng của mướp đắng là gì?") → Gemini trả lời ngắn gọn, nhãn **GEMINI**, luôn kèm dòng lưu ý "Nội dung trên do trí tuệ nhân tạo tổng hợp, chỉ có giá trị tham khảo và không thuộc dữ liệu chính thức của CivicBot" (`gemini_general`). Đặt `GENERAL_QA=false` để từ chối lịch sự các câu ngoài lề.

Mỗi phản hồi có trường `route` và `procedure_code` để kiểm thử và giải thích khi nào Gemini được gọi.

## Chạy bằng Docker (khuyến nghị)

Yêu cầu: Docker Desktop.

```bash
copy .env.example .env      # Windows (Linux/macOS: cp .env.example .env)
# mở .env, điền GEMINI_API_KEY, đổi mật khẩu MySQL và ADMIN_API_KEY
docker compose up -d --build
```

Hoặc nháy đúp `start_civicbot.bat`. Lần chạy đầu backend tự nạp 14 thủ tục từ `data/procedures/` vào MySQL.

- Giao diện: http://localhost:5173
- Tài liệu API (Swagger): http://localhost:8000/docs
- Kiểm tra kết nối CSDL: http://localhost:8000/health
- Kiểm tra nhanh để demo: `demo_check.bat`

Không có mạng hoặc không có key: đặt `AI_MODE=off` – hệ thống vẫn trả lời các câu trong CSDL.

## Chạy kiểm thử

```bash
pip install -r requirements.txt
pytest                                   # kiểm thử tự động (SQLite tạm, AI tắt)
python scripts/evaluate_chatbot.py       # đánh giá 40 câu hỏi → docs/ket-qua-danh-gia-chatbot.csv
python scripts/load_test.py              # đo tải khi backend đang chạy → docs/ket-qua-do-tai.csv
```

Trên giao diện: nút **🧪 Kiểm thử hệ thống** (cần nhập `ADMIN_API_KEY`). CI chạy tự động trên GitHub Actions (`.github/workflows/ci.yml`) mỗi lần push/PR: pytest → đánh giá 40 câu → build frontend → build Docker image.

## Cấu hình (`.env`)

| Biến | Ý nghĩa | Mặc định |
|---|---|---|
| `AI_MODE` | `gemini` hoặc `off` | `gemini` |
| `GEMINI_TIMEOUT` | Thời gian chờ tối đa mỗi lần gọi Gemini (giây) | `25` |
| `GEMINI_RETRIES` / `GEMINI_FALLBACK_MODEL` | Số lần thử lại khi Gemini quá tải (503) / model dự phòng | `2` / trống |
| `GENERAL_QA` | `true` (trả lời câu hỏi kiến thức chung, có nhãn cảnh báo) hoặc `false` (từ chối) | `true` |
| `GEMINI_API_KEY` | Khóa Gemini (không commit) | – |
| `GEMINI_MODEL` | Tên model | `gemini-3.1-flash-lite` |
| `MYSQL_*` | Kết nối MySQL | xem `.env.example` |
| `ADMIN_API_KEY` | Khóa cho chạy kiểm thử / xóa toàn bộ lịch sử | – |
| `RATE_LIMIT_PER_MINUTE` | Số câu hỏi / phút / IP | 30 |
| `MAX_UPLOAD_MB` | Dung lượng tệp tối đa | 5 |
| `KEEP_UPLOADS` | Giữ tệp sau xử lý | `false` |
| `CORS_ORIGINS` | Nguồn giao diện được phép | localhost:5173 |
| `AUTO_IMPORT_DOCX` | Tự nạp DOCX khi CSDL trống | `true` |

## API chính

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| POST | `/api/chat` | Gửi câu hỏi (form: `question`, `session_id`, `file` tùy chọn) |
| GET/DELETE | `/api/history?session_id=` | Lịch sử của phiên |
| GET | `/api/procedures`, `/api/procedures/search?q=`, `/api/procedures/{code}` | Tra cứu thủ tục |
| GET | `/health`, `/api/status`, `/api/check-gemini` | Trạng thái hệ thống |
| POST | `/api/system-tests/run` | Chạy kiểm thử (header `X-Admin-Key`) |

## Bảo mật & dữ liệu cá nhân

- Không lưu khóa API trong mã nguồn; `.env` nằm trong `.gitignore`.
- MySQL không mở cổng ra ngoài; chỉ backend truy cập.
- Lịch sử hỏi đáp tách theo `session_id`; xóa toàn bộ cần khóa quản trị.
- Tệp tải lên: chỉ PNG/JPG/WEBP/PDF/DOCX, giới hạn dung lượng, đổi tên ngẫu nhiên, xóa sau khi xử lý.
- Giới hạn tần suất câu hỏi để chống spam và bảo vệ hạn mức Gemini.
- CivicBot chỉ cung cấp thông tin tham khảo; người dân cần đối chiếu Cổng Dịch vụ công trước khi nộp hồ sơ.
