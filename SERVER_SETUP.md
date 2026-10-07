# Triển khai Worker đã ghép và email hai chiều

worker.js đã ghép theo schema `users` và `messages` trong mã Worker bạn gửi. Dùng binding D1 tên `DB` hiện tại; không cần SUPPORT_DB hoặc KV mới. Hai file support_worker.js và support_schema.sql của gói cũ không còn dùng trong phiên bản này.

## Cập nhật Cloudflare

1. Sao lưu D1 trước khi sửa schema.
2. Chạy `migration.sql` đúng một lần trên D1 đang dùng. File chỉ thêm cột/bảng/chỉ mục; không xóa dữ liệu cũ. Nếu đã có một cột từ lần sửa khác, bỏ riêng câu ALTER TABLE tương ứng sau khi đối chiếu schema; không chạy lại cả file.
3. Đặt Worker secret `ADMIN_KEY` bằng mật khẩu admin hiện đang sử dụng. Mã mới không nhúng mật khẩu admin trong file. Giữ binding `DB` trỏ đúng D1.
4. Thay mã Worker bằng `worker.js` và Deploy. Đây là mã hoàn chỉnh; các route login, đổi mật khẩu, cập nhật, hoạt động, chat và quản trị cũ đã được giữ và mở rộng.
5. Có thể thêm Cron Trigger mỗi giờ để dọn bộ đếm giới hạn và các phiên cũ. `scheduled` chỉ dọn dữ liệu trạng thái tạm thời.

Tài khoản mới được lưu trực tiếp trong `users`, luôn role=user và tier=trial. Mật khẩu tự đăng ký/đổi mật khẩu được băm PBKDF2. Tài khoản/Key cũ vẫn đăng nhập được. Admin có thể nâng tier/hạn dùng; để trống Key khi sửa sẽ giữ mật khẩu hiện có. Admin không xem được mật khẩu gốc của người tự đăng ký.

Heartbeat lưu nhiều session, dùng sequence để tránh cộng trùng thời gian. Một tài khoản được coi online nếu có ít nhất một session gửi nhịp trong 180 giây. Logout xóa đúng session. Chạy nền vẫn gửi heartbeat nhưng không tính thời gian cửa sổ hoạt động khi không có focus.

Chat user chỉ đến admin; admin chọn người dùng. API ảnh kiểm tra người tham gia luồng. `client_id` chống gửi trùng khi retry. `/api/chat/unread` trả số tin chưa đọc; `/api/chat/read` xác nhận đã xem. Tin cũ vẫn nằm trong `messages` và được giữ.

Tin mới gửi đến admin lúc offline được đánh dấu vào hàng đợi email ngay khi lưu. Không gửi thông báo hồi tố cho toàn bộ lịch sử cũ. Relay lấy hàng đợi và xác nhận sau khi SMTP gửi thành công. Trường hợp SMTP đã nhận email nhưng kết nối ngắt trước phản hồi, retry có thể gây thông báo lặp; Message-ID được giữ cố định.

## Email Gmail

Chạy `email_bridge.py` trên máy chủ luôn bật bằng trình quản lý dịch vụ có tự khởi động lại. Đây là tiến trình Python riêng, không chạy bên trong Cloudflare Worker hoặc máy người dùng.

Biến môi trường bắt buộc:

- `SOILFIRM_API_BASE=https://soilfirm-api.vuanh97nd.workers.dev`
- `SOILFIRM_ADMIN_USER=admin`
- `SOILFIRM_ADMIN_KEY`: mật khẩu admin, lưu dưới dạng secret.
- `SUPPORT_MAIL_USER`: hộp thư dịch vụ gửi/nhận email, nên khác Gmail admin.
- `SUPPORT_MAIL_PASSWORD`: App Password của hộp thư dịch vụ nếu tài khoản Gmail hỗ trợ; không dùng mật khẩu Google thông thường và không ghi vào mã nguồn.
- `SUPPORT_STATE_DB`: đường dẫn SQLite bền vững để lưu các tin và phản hồi đã xử lý.

Gmail admin nhận thông báo: **vuanh97nd@gmail.com**. Hộp thư dịch vụ gửi email và nhận Reply. SMTP mặc định `smtp.gmail.com:465` với SSL; IMAP `imap.gmail.com:993` với SSL. Có thể đổi bằng `SUPPORT_SMTP_HOST`, `SUPPORT_IMAP_HOST` và `SUPPORT_IMAP_FOLDER` (mặc định INBOX).

Cài `requests` và `Pillow` trên máy chủ rồi chạy `python email_bridge.py`. Relay xử lý mỗi 30 giây. Admin bấm Reply, giữ mã luồng trong tiêu đề và viết nội dung phía trên phần trích dẫn. Relay chỉ nhận phản hồi từ Gmail admin có xác thực DKIM Gmail, rồi gửi vào đúng luồng chat; ảnh trả lời được chuyển JPEG.

Tài liệu nhà cung cấp:
- D1 batch: https://developers.cloudflare.com/d1/worker-api/d1-database/
- Gmail App Passwords: https://support.google.com/mail/answer/185833
- Gmail IMAP/SMTP: https://developers.google.com/workspace/gmail/imap/imap-smtp

## Ứng dụng

Giải nén gói cập nhật, chép các module ở gốc vào thư mục SoilFirm Pro và chạy `pip install -r requirements_update.txt`. Gói cần thêm `pystray` cho khay hệ thống.

Ứng dụng hỏi khi bấm X: Có để ẩn xuống khay và nhận tin; Không để thoát; Hủy để giữ mở. Mục “Chạy nền — Ẩn xuống khay” thực hiện cùng chức năng. Khay có “Mở SoilFirm Pro” và “Thoát hoàn toàn”. Đây không phải tự khởi động cùng Windows; cần mở SoilFirm Pro và đăng nhập trước.

Đã chuẩn bị mã và hướng dẫn triển khai; chưa truy cập, migrate hay Deploy máy chủ thật. Chưa cấu hình hộp thư và chưa gửi email thực tế.
