# Đưa mã nguồn lên GitHub và bật CI

> Làm SAU khi đã thu hồi khóa Gemini cũ. Kiểm tra `git status` không có tệp `.env` trước mỗi lần commit.

## 1. Tạo kho và đẩy nhánh main
```bash
cd civicbot
git init
git branch -M main
git add .
git status                      # bảo đảm KHÔNG có .env
git commit -m "Khởi tạo CivicBot: FastAPI + React + MySQL + Docker"
git remote add origin https://github.com/<tai-khoan>/civicbot.git
git push -u origin main
git checkout -b develop && git push -u origin develop
```

## 2. Làm việc theo nhánh tính năng + Pull Request (minh chứng Scrum/CI)
Mỗi thay đổi tiếp theo (ví dụ sửa báo cáo, thêm câu hỏi đánh giá, chỉnh giao diện):
```bash
git checkout develop
git checkout -b feature/them-cau-hoi-danh-gia
# ... sửa code ...
git add . && git commit -m "Thêm 10 câu hỏi đánh giá về căn cước"
git push -u origin feature/them-cau-hoi-danh-gia
```
Trên GitHub: tạo Pull Request `feature/...` → `develop`, chờ CI chạy xanh, bạn còn lại review rồi Merge. Cuối Sprint: PR `develop` → `main`.

Mỗi thành viên nên commit bằng tài khoản của mình để lịch sử thể hiện đúng phân công.

## 3. Minh chứng chèn vào báo cáo
- Ảnh tab **Actions** có các lần chạy **Passed** (✓ xanh).
- Ảnh danh sách **Pull requests** (đã merge) và **Insights → Network** (các nhánh).
- Tải artifact `backend-test-reports` (pytest-report.xml, eval-report.csv).

## 4. (Tùy chọn) Triển khai online
- Backend + MySQL: Render / Railway (tạo MySQL, đặt các biến trong `.env.example` ở mục Environment/Secrets, không commit khóa).
- Frontend: build với `VITE_API_BASE_URL=<địa chỉ backend>`; thêm địa chỉ frontend vào `CORS_ORIGINS`.
