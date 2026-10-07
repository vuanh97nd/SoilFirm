# Các file cập nhật liên quan

Chép các file Python trong gói vào thư mục phần mềm, thay file cùng tên. Bổ sung device_identity.py mới. Gói này chỉ gồm các file liên quan đến yêu cầu mới, sử dụng cùng các module còn lại của bản đã gửi trước đó.

- Thứ tự ưu tiên mặc định: đào thay đất → tre 3 m + đào → cừ tràm 4 m + đào → CDM → PVD. Bước đào mặc định 0.5 m; giữ bộ tối ưu đào tăng dần của bản trước.
- Popup kết quả kiểm tra xuất hiện sau khi người dùng bấm nút tính; chỉ một thông báo cho phép tính ngoài cùng.
- PVD mặc định khi mở mục cố kết/thoát nước lần đầu; có thể chọn lại phương án khác.
- Cọc treo còn lún cố kết dưới mũi vẫn có biểu đồ Sc dư theo thời gian trong giao diện và PDF, dùng chính phân tố lún đã tính. Nếu Cv không cho đạt U=99%, biểu đồ hiển thị thời gian 1 năm với mức cố kết thực tế, không giả lập đã đạt 99%.
- Nền mở rộng: tự chọn phạm vi CDM nền mở rộng; không vẽ xử lý cũ dưới nền chính. Vùng xử lý mới bắt đầu tại vai nền chính và kết thúc tại chân nền mở rộng đúng bên được chọn, cho đào thay/cọc tre/cừ tràm/PVD/SD/CDM, cả hình giao diện và PDF. Khối lượng và bảng Excel dùng chung ranh giới.
- Mục 4 CDM nằm một hàng riêng dưới mục 3. Không thay cách trình bày hệ số trên giao diện.
- PDF: các giá trị trong ảnh (Htk, Hkcad, Hbl, H tính cọc, qu, Ec, qT, qH, ffs, fq, n, Fs, gamma, q móng, c, phi, m) có tên riêng, mỗi giá trị một dòng. Các hệ số A, B, D, fm11, fm12, fm21, fm22, fn cũng có tên rõ ràng và dòng riêng.
- Popup chào mừng gồm lời chào, hướng dẫn xem Help/F1 và nút hỗ trợ online 24/24. Khi cập nhật máy chủ, mỗi tài khoản chỉ hiện một lần trên toàn hệ thống; nếu dùng máy chủ cũ, chỉ hiện một lần trên mỗi máy nhờ dấu lưu cục bộ.
- Popup tin nhắn và hoạt động dưới nền dùng module support_background.py đã gửi ở bản trước.

## Máy chủ: khóa một tài khoản trên một máy

1. Dùng cùng DB và ADMIN_KEY của Worker hiện tại. Nếu chưa áp dụng migration.sql của gói máy chủ trước đó, áp dụng migration đó trước.
2. Chạy server/migration_device_login.sql trên D1 trước khi triển khai server/worker.js của gói này.
3. Cập nhật phần mềm khách cùng lúc (app.py và device_identity.py).

Tài khoản người dùng chỉ được đăng nhập một máy. Máy cũ phải bấm Đăng xuất để máy chủ giải phóng khóa, sau đó mới đăng nhập máy khác. Máy mới sẽ nhận thông báo yêu cầu đăng xuất thiết bị kia. Chạy dưới nền, đóng chương trình hoặc mất mạng không tự giải phóng khóa. Khi mất mạng, thao tác đăng xuất báo lỗi và cần thử lại sau khi có mạng. Cùng máy có thể mở lại phần mềm. Admin được miễn khóa một máy.

Nếu máy cũ bị mất/hỏng, admin có thể giải phóng khóa có chủ đích trong D1 bằng lệnh có tham số: DELETE FROM device_logins WHERE username = ?; không có tự hết hạn khóa.

Chưa triển khai lên máy chủ. Không chạy chương trình, kiểm thử hoặc xuất PDF kiểm tra sau khi sửa theo yêu cầu.
