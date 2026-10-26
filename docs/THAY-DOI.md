# Nhật ký thay đổi – Sprint 4 (sau nhận xét của giảng viên)

## AI
- Thêm `retrieval_service.py`: chọn top-3 thủ tục liên quan làm ngữ cảnh (RAG) trước khi gọi Gemini.
- `ai_service.py`: prompt có ngữ cảnh + quy tắc chống bịa; prompt ngoài phạm vi chỉ định hướng chung; `AI_MODE=off` để chạy không cần Gemini.
- Hỏi tiếp theo ngữ cảnh hội thoại (`session_id`), không gán nhầm khi người dùng đổi chủ đề.
- Câu hỏi kiến thức chung (ngoài lề) được Gemini trả lời kèm câu lưu ý "Nội dung trên do trí tuệ nhân tạo tổng hợp, chỉ có giá trị tham khảo…" (`route=gemini_general`); bật/tắt bằng `GENERAL_QA`. Câu thủ tục hành chính ngoài CSDL (hộ chiếu, kết hôn…) được hướng dẫn cơ quan, các bước, giấy tờ thường cần, nhưng không nêu số văn bản, lệ phí, thời hạn cụ thể.
- Phân loại câu hỏi ngoài CSDL (thủ tục hành chính / kiến thức chung) bằng mã nguồn `is_administrative_question` thay vì để Gemini tự quyết (sửa lỗi Q32, Q36).
- Giới hạn thời gian chờ Gemini `GEMINI_TIMEOUT` (mặc định 25 s); `scripts/evaluate_chatbot.py` mặc định tắt AI, thêm `--with-ai` để đánh giá cả Gemini, in tiến độ từng câu.
- Tự thử lại khi Gemini quá tải (lỗi 503), tối đa `GEMINI_RETRIES` lần, có thể chuyển sang `GEMINI_FALLBACK_MODEL`; nếu vẫn lỗi thì trả thông báo dự phòng (`no_data`), hệ thống không dừng.
- Ghi chú nguồn dưới mỗi câu trả lời được viết lại theo văn phong trang trọng.
- Giao diện: thay hộp thoại mặc định của trình duyệt (`window.confirm`, `window.prompt`) bằng hộp thoại riêng của CivicBot cho xóa lịch sử (toàn bộ / từng lượt) và xác thực khóa quản trị khi chạy kiểm thử (ô nhập dạng mật khẩu, phím Esc để hủy).
- Phản hồi có `route` và `procedure_code` để giải thích khi nào gọi Gemini.

## Chất lượng & kiểm thử
- Tách `chat.py` (≈1.870 dòng) thành `nlp_service`, `procedure_service`, `retrieval_service`, `ai_service`, `security_service`; xóa `intent_service.py` không dùng; nối router `procedures`.
- Bộ kiểm thử nội bộ: 11 → 21 ca (thêm Acceptance AT01–04, AI01–03, Regression RT01–06).
- Thêm `tests/` (pytest, ~92 ca), `data/eval/questions.csv` (40 câu) + `scripts/evaluate_chatbot.py`, `scripts/load_test.py`.
- CI GitHub Actions: pytest → đánh giá 40 câu → build frontend → build Docker.
- Sửa lỗi: nhận diện "những bước", "xác nhận cư trú", "chuyển nhà", nhóm tuổi/cấp đổi/cấp lại căn cước, câu "… thế nào", câu hỏi nối tiếp gán nhầm, câu hỏi chung bị đưa vào RAG ("Việt Nam có bao nhiêu dân tộc"), câu hỏi kép chỉ trả lời một phần (nay tách và trả lời từng phần; một thủ tục hỏi nhiều ý cũng trả lời đủ), lệ phí 1.010028 dính vào thời hạn.

## Bảo mật & triển khai
- Bỏ `.env` khỏi mã nguồn, thêm `.env.example`; docker-compose đọc biến môi trường; đóng cổng MySQL 3306.
- Khóa quản trị `X-Admin-Key` cho chạy kiểm thử/xóa toàn bộ lịch sử; lịch sử tách theo phiên.
- Giới hạn tần suất câu hỏi; kiểm tra định dạng, dung lượng tệp; đổi tên ngẫu nhiên và xóa tệp sau xử lý; CORS cấu hình được.
- Backend tự nạp 14 thủ tục khi CSDL trống; `import_docx.py --all`.
- `requirements.txt` chuyển UTF-8, ghim phiên bản; `backup/civicbot_backup.sql` chuyển UTF-8, bỏ lịch sử chat.
- README, `docs/DEMO.md`, `start_civicbot.bat`, `demo_check.bat`.
