# Gói cập nhật SoilFirm Pro

Giữ bản sao chương trình, giải nén và chép các module Python ở gốc đè lên file cùng tên. Giữ các module khác của chương trình. Chạy `pip install -r requirements_update.txt`.

Gói này gồm tất cả sửa đổi trước đó và thêm Worker hoàn chỉnh ghép vào D1 hiện tại, thông báo tin nhắn mới và khay hệ thống. Worker nằm tại `server/worker.js`; chạy migration và cấu hình theo `server/SERVER_SETUP.md`.

Đóng cửa sổ bằng X sẽ hỏi chạy nền/thoát/hủy. Khi chạy nền, phần mềm giữ đăng nhập và nhận tin. Bấm khay để mở lại hoặc thoát hẳn. Thông báo mới có nút mở cuộc trò chuyện.

Email admin là vuanh97nd@gmail.com. Email hai chiều cần tiến trình email_bridge.py trên máy chủ luôn bật và hộp thư dịch vụ đã cấu hình. Chưa triển khai lên máy chủ thật, chưa gửi email.

Không chạy kiểm tra sau khi sửa theo yêu cầu.
