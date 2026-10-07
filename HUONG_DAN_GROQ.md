# Kích hoạt Groq — SoilFirm Pro 2026.11

1. Mở Cloudflare Worker đang phục vụ SoilFirm Pro, cập nhật toàn bộ `worker.js` mới.
2. Trong Settings → Variables and Secrets, thêm **Secret** tên `GROQ_API_KEY` và nhập khóa tạo tại https://console.groq.com/keys .
3. Save và Deploy Worker.
4. Mở lại ứng dụng chạy mã nguồn hoặc dựng lại EXE. Chọn **Groq** ở Hỗ trợ AI, mục 1 hoặc mục 8.

Biến tùy chọn: `GROQ_MODEL` cho văn bản (mặc định `openai/gpt-oss-120b`), `GROQ_VISION_MODEL` cho ảnh/PDF scan (mặc định `qwen/qwen3.8-27b`). Chọn mô hình hỗ trợ ảnh nếu thay biến Vision. Kiểm tra các mô hình còn hoạt động tại https://console.groq.com/docs/models .

Groq dùng chung hướng dẫn trích địa chất, ghép nhiều Excel, quy đổi đơn vị, cập nhật e–P/Cv–P và quy trình duyệt đầu vào của SoilFirm. AI trả yêu cầu tính toán; bộ tính SoilFirm Pro thực hiện theo công thức hiện có. API key được Worker gửi tới Groq, không đóng gói trong ứng dụng máy khách.

Lỗi 401: kiểm tra Secret; lỗi 429: đợi hết giới hạn tài khoản; lỗi 400/model: kiểm tra tên và khả năng mô hình. Kiểm thử tích hợp HTTP được mô phỏng; chưa gọi Groq thật với tài khoản của người dùng.

Tài liệu API: https://console.groq.com/docs/api-reference ; ảnh và JSON mode: https://console.groq.com/docs/vision .
