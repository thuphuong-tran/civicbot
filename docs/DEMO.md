# Kịch bản demo CivicBot (theo yêu cầu của thầy)

Thời lượng gợi ý: 10–12 phút. Một bạn thao tác máy, một bạn thuyết minh.

## 0. Chuẩn bị trước buổi demo (làm ở nhà, trước 1 ngày)

1. Cài Docker Desktop, mở Docker Desktop.
2. Trong thư mục `civicbot`: `copy .env.example .env`, mở `.env` và điền:
   - `GEMINI_API_KEY=` **khóa mới** (khóa cũ đã bị lộ trong bản nộp trước → thu hồi ở Google AI Studio).
   - `ADMIN_API_KEY=` một chuỗi bất kỳ, ví dụ `nhom1-demo-2025`.
   - Đổi `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`.
3. Chạy `start_civicbot.bat` (hoặc `docker compose up -d --build`) – lần đầu mất 5–10 phút để tải image.
4. Thử đủ 3 phần demo bên dưới một lần. Kiểm tra Gemini: mở http://localhost:8000/api/check-gemini.
5. **Phương án dự phòng**: nếu ở lớp không có mạng/Gemini lỗi → sửa `.env` thành `AI_MODE=off`, chạy `docker compose up -d` lại. Phần câu hỏi trong dữ liệu và kiểm thử vẫn chạy bình thường; nói rõ với thầy là đang chạy chế độ không AI. Nên quay sẵn một video ngắn phần Gemini để chiếu nếu cần.
6. Mở sẵn các tab: Docker Desktop, http://localhost:5173, http://localhost:8000/docs, một cửa sổ CMD ở thư mục `civicbot`.

---

## Demo 1 – Docker: React + FastAPI + MySQL kết nối với nhau (3 phút)

| Bước | Thao tác | Nói gì |
|---|---|---|
| 1 | `docker compose ps` | "Hệ thống gồm 3 container: `civicbot-frontend` (React build, chạy trên nginx), `civicbot-backend` (FastAPI), `civicbot-mysql` (MySQL 8). Cả 3 đang ở trạng thái Up/healthy." |
| 2 | Mở http://localhost:8000/health | "`database: ok` – backend đã kết nối được MySQL qua mạng nội bộ Docker (host `mysql`). Cổng 3306 không mở ra ngoài, chỉ backend truy cập được." |
| 3 | `docker exec civicbot-mysql mysql --default-character-set=utf8mb4 -ucivicbot -p<mật khẩu> civicbot -e "SELECT procedure_code, name FROM procedures;"` | "CSDL có 14 thủ tục, được nạp tự động từ 14 file DOCX lấy từ Cổng Dịch vụ công khi CSDL còn trống." |
| 4 | Mở http://localhost:5173, hỏi 1 câu bất kỳ | "React gọi API `POST /api/chat` của FastAPI (xem tab Network)." |
| 5 | Chạy lại câu lệnh ở bước 3 với `SELECT id, question, procedure_code FROM chat_history ORDER BY id DESC LIMIT 3;` | "Câu hỏi vừa gửi từ giao diện đã được backend ghi vào MySQL → chứng minh đủ 3 tầng kết nối." |

Có thể chạy nhanh toàn bộ bằng `demo_check.bat`.

## Demo 2 – Ba loại câu hỏi và khi nào gọi Gemini (4 phút)

Nguyên tắc cần nói: **CSDL là nguồn chính, Gemini chỉ là phương án bổ sung.** Mỗi câu trả lời có nhãn nguồn (CSDL NỘI BỘ / GEMINI / HỆ THỐNG) và dòng ghi chú cho biết có gọi Gemini hay không.

| # | Câu hỏi | Kết quả mong đợi | Giải thích |
|---|---|---|---|
| 2a | **Trong dữ liệu:** `Đăng ký tạm trú cần giấy tờ gì?` rồi hỏi tiếp `Mất bao lâu?` | Nhãn **CSDL NỘI BỘ**, liệt kê hồ sơ (tờ khai CT01...), có link nguồn. Câu 2 vẫn hiểu là thủ tục đăng ký tạm trú. | Hệ thống chuẩn hóa tiếng Việt → nhận ra chủ đề "tạm trú" và loại câu hỏi "hồ sơ" → lấy thẳng từ MySQL. **Không gọi Gemini**, nên nhanh (vài ms) và không bịa. Câu hỏi nối tiếp dùng `session_id` để nhớ thủ tục trước. |
| 2b | **Thuộc chủ đề nhưng hỏi tự do:** `Tôi thuê trọ ở Hà Nội để đi học thì cần làm thủ tục gì?` | Nhãn **GEMINI + CSDL**, ghi chú "Gemini trả lời dựa trên dữ liệu các thủ tục: 1.004194, ..." | Không xác định được chính xác 1 thủ tục → lấy 3 thủ tục tạm trú liên quan nhất làm ngữ cảnh (RAG) → Gemini chỉ được trả lời dựa trên ngữ cảnh đó. |
| 2c | **Ngoài dữ liệu:** `Làm hộ chiếu cần giấy tờ gì?` (hoặc `Thủ tục đăng ký kết hôn cần gì?`) | Nhãn **GEMINI**, ghi chú "Thủ tục chưa có trong cơ sở dữ liệu…"; nêu cơ quan, các bước, giấy tờ thường cần, khuyên kiểm tra Cổng DVC; **không có số văn bản, không có lệ phí, thời hạn cụ thể**. Nếu `AI_MODE=off`: thông báo chưa có dữ liệu. | Câu hỏi ngoài 14 thủ tục → prompt cho phép hướng dẫn chung nhưng cấm Gemini nêu con số cụ thể (văn bản, lệ phí, thời hạn) để tránh "ảo giác". |
| 2d | **Có tệp:** bấm 📎, chọn `docs/demo-files/tai-lieu-dang-ky-tam-tru.pdf`, hỏi `Tài liệu này hướng dẫn thủ tục gì và cần chuẩn bị những gì?` | Nhãn **GEMINI**, tóm tắt nội dung tệp | Có tệp thì **luôn gọi Gemini** (đọc PDF/DOCX/ảnh). Chỉ nhận PNG/JPG/WEBP/PDF/DOCX ≤ 5 MB, đổi tên ngẫu nhiên và **xóa tệp ngay sau khi xử lý** để bảo vệ dữ liệu cá nhân. Thử gửi file `.exe` → bị từ chối. |

| 2e | **(Thêm nếu còn thời gian) Câu hỏi kép:** `Tôi bị mất hộ chiếu và căn cước công dân thì cần phải làm gì` | 2 khối trả lời: **GEMINI** (hộ chiếu – định hướng chung) + **CSDL NỘI BỘ** (các bước cấp lại thẻ căn cước) | Hệ thống tách câu hỏi kép thành từng phần, mỗi phần đi đúng nhánh của nó. |

Câu hỏi ngoài lề hoàn toàn (ví dụ `Tác dụng của mướp đắng là gì?`) → CivicBot vẫn trả lời bằng Gemini, nhãn **GEMINI**, cuối câu luôn có dòng *"Lưu ý: Nội dung trên do trí tuệ nhân tạo tổng hợp, chỉ có giá trị tham khảo và không thuộc dữ liệu chính thức của CivicBot."* (`route=gemini_general`). Dòng ghi chú dưới mỗi câu trả lời cũng nêu rõ nguồn theo văn phong chính thức, ví dụ: "Nội dung không thuộc lĩnh vực thủ tục hành chính. Câu trả lời do AI tổng hợp từ kiến thức chung, chỉ có giá trị tham khảo và chưa được cơ quan có thẩm quyền kiểm chứng." Giải thích với thầy: hệ thống phân biệt 2 loại câu ngoài dữ liệu — (1) **thủ tục hành chính** chưa có (hộ chiếu, kết hôn) → Gemini nêu cơ quan tiếp nhận, các bước chính, giấy tờ thường cần, nhưng **cấm nêu số văn bản, số tiền lệ phí, số ngày giải quyết** vì các con số này dễ sai và gây hại cho người dân; (2) **kiến thức chung** → trả lời tham khảo, gắn nhãn rõ để người dùng không nhầm với dữ liệu chính thức. Có thể tắt bằng `GENERAL_QA=false` (khi đó chatbot từ chối lịch sự).

Tóm tắt khi nào gọi Gemini (nên đưa lên 1 slide):

```
Câu hỏi ─► rỗng/chào? ─► trả lời ngay
        ─► có tệp? ─────────────────────────────► Gemini đọc tệp
        ─► tìm được thủ tục + loại thông tin? ──► CSDL (không gọi Gemini)
        ─► câu hỏi nối tiếp? ───────────────────► CSDL (thủ tục của câu trước)
        ─► thuộc chủ đề cư trú/căn cước? ───────► Gemini + ngữ cảnh top-3 thủ tục
        ─► ngoài phạm vi ───────────────────────► Gemini định hướng chung (cấm bịa số liệu)
```

## Demo 3 – Chạy kiểm thử, PASS/FAIL và lỗi đã phát hiện (4 phút)

### Cách 1 – trên giao diện
Bấm **🧪 Kiểm thử hệ thống** → chọn `quick` → nhập `ADMIN_API_KEY` → **21 ca** hiện PASS/FAIL theo tầng: Unit (UT01–04), Integration (IT01–02), System (ST01–02), Acceptance (AT01–04, ứng với User Story), AI (AI01–03: grounding, chống bịa, giữ ngữ cảnh), Regression (RT01–06: các lỗi đã sửa). Bộ `regression` chạy thêm 3 ca giao diện bằng Selenium (UI01–03).

### Cách 2 – dòng lệnh (giống CI)
```bash
pip install -r requirements.txt
pytest
python scripts/evaluate_chatbot.py
```
Kết quả đánh giá 40 câu (30 trong phạm vi, 8 ngoài phạm vi, 2 lời chào): chọn đúng thủ tục 100%, đúng loại thông tin 100%, an toàn với câu ngoài phạm vi 100%, thời gian xử lý trung bình ~4 ms (chế độ không AI).

### Lỗi đã phát hiện nhờ kiểm thử (chọn 1–2 lỗi để trình bày)

| Mã | Lỗi | Phát hiện bằng | Nguyên nhân | Cách sửa |
|---|---|---|---|---|
| RT04 | Hỏi về căn cước, sau đó hỏi "Thủ tục đăng ký kết hôn cần gì?" → bot trả lời **hồ sơ căn cước** | Kiểm thử hội thoại nhiều lượt | Logic câu hỏi nối tiếp chỉ kiểm tra "không có chủ đề + có loại câu hỏi", nên câu ngoài phạm vi cũng bị coi là câu nối tiếp | Thêm `is_follow_up_question`: câu nối tiếp phải ngắn và không nêu tên thủ tục mới; thêm ca hồi quy RT04 |
| RT05 | "Việt Nam có bao nhiêu dân tộc" hiện nhãn **GEMINI + CSDL** kèm nguồn thủ tục căn cước (dù câu trả lời là "chưa có dữ liệu") | Chạy thử khi demo | Câu hỏi không thuộc chủ đề nhưng trùng từ "Việt Nam", "dân tộc" có trong thủ tục căn cước nên bị lấy làm ngữ cảnh | Chỉ lấy ngữ cảnh khi câu hỏi thuộc chủ đề cư trú/căn cước; nếu Gemini kết luận không đủ dữ liệu thì bỏ nhãn và nguồn thủ tục; thêm ca RT05 |
| RT06 | "Tôi bị mất hộ chiếu và căn cước công dân thì cần phải làm gì" chỉ trả lời thông tin chung về căn cước, bỏ qua hộ chiếu | Chạy thử câu hỏi kép | Hệ thống chỉ tìm 1 thủ tục khớp nhất cho cả câu | Tách câu hỏi kép thành các câu con: phần có trong CSDL trả lời từ CSDL, phần ngoài dữ liệu do Gemini định hướng chung; câu "nộp ở đâu, mất bao lâu" trả lời đủ 2 ý; thêm ca RT06 |
| IMP | Thủ tục 1.010028 (xóa đăng ký tạm trú) hiển thị thời hạn giải quyết lẫn dòng "Phí/lệ phí: không có" | Kiểm thử bộ đọc DOCX (`tests/test_importer.py`) | File DOCX gộp 2 thông tin trên cùng đoạn | Tách phần "Phí/lệ phí" khỏi thời hạn khi nhập dữ liệu |
| RT01 | "Tách hộ gồm **những bước** nào?" trả về thông tin chung thay vì các bước | Chạy thử bộ câu hỏi ban đầu | Từ khóa nhận diện loại "bước" thiếu "những bước", "bước nào" | Bổ sung từ khóa, thêm ca RT01 |
| RT02 | "Cho tôi hỏi về xác nhận cư trú" bị chuyển sang Gemini dù CSDL có thủ tục 1.010041 | Chạy thử bộ câu hỏi ban đầu | Thiếu cụm "xác nhận thông tin về cư trú" | Bổ sung từ khóa chủ đề, thêm ca RT02 |
| RT03 | "Tôi chuyển nhà sang quận khác thì phải làm gì?" không tìm được thủ tục | Chạy thử bộ câu hỏi ban đầu | Câu hỏi đời thường không chứa tên thủ tục | Nhận diện ý "chuyển nhà" → gợi ý cả thường trú và tạm trú, thêm ca RT03 |
| Q24, Q28 | "Cấp thẻ căn cước cho người **trên 14 tuổi**…", "**Cấp đổi** căn cước căn cứ pháp lý" chọn nhầm thủ tục căn cước khác | Bộ đánh giá 40 câu (lần chạy đầu: đúng thủ tục 93,3%) | Các thủ tục căn cước có tên gần giống nhau; chưa xét nhóm tuổi và hành động (cấp đổi/cấp lại) | Cộng điểm theo nhóm tuổi và hành động (`action_and_age_bonus`) → 100% |
| Q25 | "Mất thẻ căn cước thì xin cấp lại **thế nào**?" không trả về các bước | Bộ đánh giá 40 câu (lần đầu: đúng loại thông tin 90%) | Thiếu mẫu câu "… thế nào" cho loại "các bước" | Bổ sung mẫu câu → 100% |

Kịch bản nói mẫu cho RT04: *"Khi kiểm thử hội thoại nhiều lượt, nhóm phát hiện nếu người dùng vừa hỏi về căn cước rồi hỏi sang đăng ký kết hôn, bot vẫn trả lời hồ sơ căn cước – đây là lỗi nguy hiểm vì sai mà trông như đúng. Nguyên nhân là... Sau khi sửa, nhóm thêm ca RT04 vào bộ hồi quy để lỗi không quay lại; CI chạy lại toàn bộ mỗi lần push."*

## Câu hỏi thầy có thể hỏi thêm

- **Quản lý khóa API thế nào?** – Khóa chỉ nằm trong `.env` (không commit, có `.env.example`), Docker truyền vào qua biến môi trường; khóa cũ bị lộ đã thu hồi. Trên cloud dùng secret của nền tảng.
- **Hiệu năng?** – Chạy `python scripts/load_test.py` (đặt `RATE_LIMIT_PER_MINUTE=100000` khi đo), kết quả trong `docs/ket-qua-do-tai.csv`. Câu trong CSDL không gọi Gemini nên nhanh; câu gọi Gemini phụ thuộc mạng (đo riêng).
- **Nếu Gemini trả lời sai?** – Gemini chỉ dùng khi CSDL không đủ; câu trả lời gắn nhãn GEMINI + lời khuyên đối chiếu Cổng DVC; ca AI02 kiểm tra không bịa số văn bản/lệ phí.
- **Dữ liệu cập nhật thế nào?** – Thêm/sửa file DOCX theo mẫu `Form-thu-thap-thong-tin-thu-tuc.docx` rồi chạy `python import_docx.py --file <đường dẫn>` hoặc `--all`.
