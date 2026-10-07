# Bộ nhớ AI dùng chung — SoilFirm Pro 2026.11

Ngày: 05/10/2026. Mã đã tích hợp; chưa triển khai lên Cloudflare thật trong phiên này.

## Quyền truy cập

| Tài khoản | Quyền |
|---|---|
| Dùng thử (trial) | Không tải, gửi hoặc sử dụng bộ nhớ chung; API trả 403 |
| Tài khoản đầy đủ | Tải quy tắc đã công bố; gửi ánh xạ đã xác nhận và kiến thức |
| Quản trị viên | Xem đề xuất, công bố, từ chối, ngừng sử dụng |

Quy tắc do người dùng gửi luôn ở trạng thái chờ xác nhận. Chỉ quản trị viên công bố mới được dùng chung. Các hiệu chỉnh giá trị mẫu và dữ liệu công trình không tự động được chia sẻ. Gửi kiến thức là thao tác rõ ràng của người dùng; nội dung được quản trị viên xem trước khi công bố.

## Cách hoạt động

Bộ nhớ máy chủ dùng D1, bộ nhớ máy khách dùng SQLite. Ánh xạ dùng chữ ký cấu trúc, đơn vị, nhóm thí nghiệm và phiên bản sổ thông số. Quy tắc riêng của dự án được ưu tiên. Python vẫn kiểm tra số liệu thật của mỗi file trước khi áp dụng; bộ nhớ không thay thế cổng kiểm tra và không sinh giá trị đầu vào.

Mất mạng giữ bộ nhớ đã đồng bộ và hàng đợi gửi. Tài khoản trial không dùng cache chung. Phản hồi hỏng không cập nhật một phần cache hoặc xóa hàng đợi. Thu hồi quy tắc có hiệu lực tại máy khách sau khi đồng bộ thành công. Đây là bộ nhớ tra cứu, không huấn luyện lại trọng số Qwen hoặc thay đổi công thức tính.

## Tệp thay đổi

- `worker.js`: API bộ nhớ, kiểm tra tài khoản ở máy chủ, D1 và kiểm tra dữ liệu công bố. Mã helper được nhúng sẵn, Worker không cần import tệp riêng.
- `geotech_memory.py`: cache, hàng đợi SQLite và tra cứu bộ nhớ chung.
- `geotech_memory_sync.py`: đồng bộ HTTPS trong luồng nền, kiểm tra phản hồi, chống đồng bộ chồng nhau.
- `geotech_memory_ui.py`: tab Bộ nhớ chung; đồng bộ, gửi kiến thức và thao tác quản trị.
- `ai_analysis_workflow.py`, `chat_dialog.py`: đồng bộ và lấy ngữ cảnh trước khi gọi AI.
- `build_app.py`, `SoilFirm_Professional.spec`: đóng gói module mới.
- `shared_memory_server.js`: bản helper độc lập phục vụ kiểm thử.
- `migration_shared_memory.sql`: tạo bảng tùy chọn, không sửa bảng tài khoản.

Giữ nguyên các lựa chọn mô hình, chức năng tính toán và bộ nhớ riêng hiện có. Không sửa file mẫu.

## Triển khai

1. Triển khai toàn bộ `worker.js` mới vào Worker hiện tại. Giữ binding D1 tên `DB` và secret quản trị `ADMIN_KEY` hiện có.
2. Bảng được tạo tự động khi tài khoản hợp lệ gọi API bộ nhớ lần đầu. Có thể chạy `migration_shared_memory.sql` trên cùng D1 trước đó nếu muốn.
3. Dùng mã Desktop đã cập nhật hoặc đóng gói lại EXE. EXE cũ chưa có giao diện và module mới.
4. Trong Bộ nhớ AI → Bộ nhớ chung, tài khoản quản trị chọn Nạp biểu mẫu → Đồng bộ → Xem đề xuất. Kiểm tra nội dung rồi Công bố từng mục phù hợp.
5. Tài khoản đầy đủ chọn Đồng bộ hoặc bắt đầu lượt đọc/chat; quy tắc đã công bố được tải về. Tài khoản trial bị chặn ở cả máy khách và API.

Nạp biểu mẫu chỉ tạo đề xuất tham chiếu từ catalog sẵn có, không công bố tự động và không đưa số đo mẫu thành quy tắc. Không cần tải lại file Excel để tạo đề xuất này.

## Kiểm thử và giới hạn

Đã chạy 29 kiểm thử Python về bộ nhớ, cấu trúc biểu mẫu và đồng bộ; tất cả đạt. Kiểm thử Worker qua hàm fetch với SQLite thực mô phỏng giao diện D1 cũng đạt: xác thực, trial, quyền admin, đề xuất chưa công bố, công bố/thu hồi, gửi lại và lô sai.

Chạy trong thư mục mã nguồn:

```bash
python -m unittest test_shared_memory -v
node test_shared_memory_server.mjs
```

Test Python cần các module hiện có và parameter_registry.json. Test Node cần Node.js hỗ trợ ES module, Python 3, worker.js và shared_memory_server.js cùng thư mục; không gọi API máy chủ thật.

Chưa kiểm chứng: triển khai Cloudflare/D1 thật, giao diện Tkinter chạy trên Windows, EXE đóng gói, lượt gọi Ollama thật. Phiên này không có quyền triển khai Cloudflare; lưu mã nguồn không có nghĩa tính năng đã hoạt động trên máy chủ.

D1 batch transaction: https://developers.cloudflare.com/d1/worker-api/d1-database/
