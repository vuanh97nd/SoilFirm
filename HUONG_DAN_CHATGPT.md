# Kích hoạt ChatGPT qua OpenAI API — SoilFirm Pro 2026.11

1. Tạo khóa API tại https://platform.openai.com/api-keys .
2. Cập nhật toàn bộ `worker.js` mới trong Cloudflare Worker của SoilFirm.
3. Vào Settings → Variables and Secrets, thêm **Secret** tên `OPENAI_API_KEY` và nhập khóa OpenAI. Save và Deploy.
4. Mở lại ứng dụng từ mã nguồn hoặc dựng lại EXE, chọn **ChatGPT** tại chat, mục 1 hoặc mục 8.

Biến tùy chọn: `OPENAI_MODEL` cho văn bản, `OPENAI_VISION_MODEL` cho ảnh. Mặc định dùng `gpt-4.1-mini`; nếu không đặt Vision thì dùng mô hình văn bản. Khi thay mô hình, chọn mô hình hỗ trợ ảnh và Chat Completions/JSON mode để dùng đủ quy trình.

Đây là tích hợp OpenAI API. ChatGPT Plus/Pro và API có thanh toán riêng; tài khoản API cần được cấp quyền mô hình và hạn mức phù hợp. Tham khảo https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform .

Dùng chung quy trình đọc nhiều Excel/PDF, ghép theo mã lớp, quy đổi đơn vị, cập nhật e–P/Cv–P, duyệt/sửa đầu vào và chọn phương án. AI chỉ trích dữ liệu và đề nghị thao tác tính; công thức do bộ tính SoilFirm Pro thực hiện. API key lưu trong Secret của Worker, không đóng gói vào EXE. Worker gửi yêu cầu với `store=false`.

Lỗi 401: kiểm tra khóa API; 429: kiểm tra hạn mức API/số dư hoặc giới hạn tốc độ; lỗi mô hình/400: kiểm tra tên và tính năng mô hình. Đã kiểm thử HTTP mô phỏng; chưa gọi OpenAI thật bằng tài khoản người dùng.

Tài liệu: https://developers.openai.com/api/docs/models/gpt-4.1-mini ; https://developers.openai.com/api/docs/guides/images-vision ; https://developers.openai.com/api/docs/guides/structured-outputs .
