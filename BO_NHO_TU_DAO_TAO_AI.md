# Bộ nhớ dùng chung từ Dao tao AI

Đã tạo bộ nguồn cho các AI tích hợp trong SoilFirm Pro 2026.11. Chưa nạp lên Cloudflare thật: phiên này không có quyền triển khai/khóa quản trị. Không gửi bí mật đăng nhập trong chat.

## Phạm vi đã đọc

Đã duyệt 9 thư mục dự án và 53 file, không sửa nguồn. Đã đọc nội dung 40 file: 26 Excel (148 sheet), 10 DXF, 2 JSON, 2 PDF (9 trang có lớp text). Kiểm kê từng nguồn và lỗi nằm trong source_read_report.json. Phạm vi đọc là ô/văn bản và cấu trúc tài liệu; chưa bóc tách ảnh hay biểu đồ nhúng (bao gồm ảnh WMF trong Excel).

| Dự án | File | Đã đọc | Chưa đọc |
|---|---:|---:|---:|
| An tho | 4 | 3 | 1 |
| Bai dinh | 4 | 3 | 1 |
| Cam lo La Son | 7 | 6 | 1 |
| Cau dinh | 4 | 3 | 1 |
| Cau thoi an | 6 | 3 | 3 |
| DD-TL | 5 | 4 | 1 |
| Hung my | 3 | 1 | 2 |
| Kim thanh | 5 | 4 | 1 |
| VD4_HN | 5 | 4 | 1 |

Ngoài các thư mục dự án, thư mục gốc có 10 file, đọc được 9; SU.xlsm bị Google Drive chặn tải. Hai file vượt giới hạn tải 32 MiB: DXF đất yếu đầu cầu Thới An và báo cáo PDF cầu Hưng Mỹ. Có 10 DWG tải được nhưng chưa giải mã; không suy nội dung DWG từ DXF đi kèm.

## Bộ nhớ tạo được

- 91 mẫu tiêu đề Excel; 84 cấu trúc khác nhau sau khi loại bản giống nhau.
- 1228 mảnh tham khảo ngắn, có nguồn file/Drive ID/SHA-256, sheet/ô Excel hoặc trang PDF/đối tượng DXF.
- Nhãn γ, e0, Cc, Cs, Cv, Pc, Co/Su, c/φ, SPT; ký hiệu cấp áp lực e-P/Cv-P; tên đất, trạng thái đất, địa tầng, hình học và cấu trúc JSON dự án.
- Từ điển thông số theo parameter_registry.json hiện có của phần mềm. Không xác nhận đây là danh sách mọi thông số địa kỹ thuật ngoài phạm vi registry hiện tại.
- Các file font TCVN3 được giải mã trong bộ nhớ đọc; không sửa chữ hay số trong file nguồn. Lỗi Excel và đơn vị/nhãn chưa chắc giữ nguyên trong báo cáo.

Kiến thức là tham khảo có nguồn, không phải ánh xạ đã được xác nhận cho mọi file. Bộ nhớ không chứa mảng số đo để điền lại vào dự án khác. Trị số lẫn trong đoạn văn được che; số mũ đơn vị và cấp áp lực ở tiêu đề xác định được giữ. Python tiếp tục đọc/đổi đơn vị/kiểm tra file hiện tại, AI chỉ giải nghĩa nhãn. Không thay công thức tính hoặc huấn luyện lại trọng số mô hình.

## Tệp để dùng

Tại thư mục gốc SoilFirm_Pro_2026.11: shared_memory_seed.json, geotech_template_catalog.json, push_shared_memory_seed.py, geotech_memory_sync.py, geotech_memory.py và cấu hình đóng gói đã cập nhật.

Bộ nhớ chung độc lập nhà cung cấp: Qwen, DeepSeek, Gemini, ChatGPT và các AI khác trong SoilFirm lấy ngữ cảnh qua cùng lớp bộ nhớ. Không có nghĩa mọi ứng dụng AI bên ngoài SoilFirm tự truy cập được. Trial bị chặn tại API và không dùng cache chung; bộ nhớ dự án riêng được giữ.

Các mảnh nguồn ban đầu ở trạng thái chờ quản trị viên công bố. Chỉ công bố khi đã xem nguồn và hiểu nhãn. Nguồn mơ hồ không trở thành luật tự động.

## Nạp lên máy chủ

Cần triển khai worker.js mới từ lần sửa bộ nhớ chung trước, giữ binding D1 DB và ADMIN_KEY. Sau đó, trong thư mục nguồn, chạy:

```bash
python push_shared_memory_seed.py --dry-run
python push_shared_memory_seed.py
```

Lệnh thứ hai hỏi khóa quản trị bằng getpass (không hiển thị, không lưu), gửi lô 20 mảnh, chờ công bố. Sau khi kiểm tra nguồn, quản trị viên có thể công bố bằng giao diện Bộ nhớ AI → Bộ nhớ chung, hoặc chủ động chạy:

```bash
python push_shared_memory_seed.py --publish
```

Tốc độ gửi được giới hạn để tránh lỗi API 429. Chạy lại không nhân bản bản ghi. Nếu đang dừng giữa chừng, các mục đã gửi vẫn còn trên máy chủ, phần chưa gửi có thể chạy lại. Không tự chuyển API lỗi thành thành công.

Có thể dùng seed_shared_memory.sql để nạp cùng bộ nguồn vào D1 với trạng thái pending bằng công cụ quản trị Cloudflare. Đây là tệp SQL chuẩn bị triển khai, chưa thực thi trên D1 thật. shared_memory_reference.sqlite3 là snapshot riêng chứa hàng đợi pending để kiểm tra; không chép đè lên geotech_memory.sqlite3 cá nhân đang dùng.

Trong Desktop mới, quản trị viên chọn Nạp biểu mẫu để đưa bộ nguồn vào hàng đợi, rồi Đồng bộ. Mỗi lượt đồng bộ giới hạn số trang; nếu còn hàng đợi thì chạy tiếp. Sau khi công bố, tài khoản đầy đủ đồng bộ để nhận bộ nhớ. EXE cũ cần đóng gói lại để có dữ liệu mới.

## Kiểm chứng

36 kiểm thử Python đạt: lưu bền, không tự tin cậy seed, hàng đợi không nhân bản, seed hỏng bị chặn toàn bộ, chỉ admin nạp, gửi theo lô, công bố riêng, RAG tìm cả mục cũ ngoài 100 mục gần nhất, trial không dùng bộ nhớ chung và các kiểm thử trước.

Toàn bộ 1228 payload qua schema Worker. SQL nạp thử vào SQLite và chạy lại không nhân bản. Đo RAG trên toàn corpus công bố giả lập cục bộ: 2961 ký tự, khoảng 142 ms trong phiên này. Đây là số đo tra cứu cục bộ, không phải thời gian/tốc độ Ollama hay Cloudflare thật.

Chưa kiểm chứng: Cloudflare/D1 thật, GUI/EXE Windows, cuộc gọi Ollama/API AI thật; độ chính xác bóc tách số liệu của mọi nguồn. Đọc được nội dung và kiểm thử bộ nhớ không đồng nghĩa toàn bộ số liệu đã ánh xạ đúng.

## Chạy lại bộ tạo nguồn

Đặt build_shared_corpus.py, source_inventory_portable.json và parameter_registry.json cùng thư mục mã nguồn; chạy trên máy có nguồn:

```bash
python build_shared_corpus.py --inventory source_inventory_portable.json --source-dir "G:/My Drive/Dev/Dao tao AI" --output "AI_Memory_Dao_tao_AI_Rebuild"
```

Bộ tạo cần thư viện hiện có của phần mềm (openpyxl, xlrd, ezdxf), thêm PyMuPDF cho PDF; OCR chỉ dùng nếu trang không có text, với tesseract. Nó đọc nguồn, tạo tệp mới tại output, không ghi đè file mẫu. Nếu file thiếu hoặc định dạng không được hỗ trợ, ghi rõ lỗi và không tạo kiến thức từ phần chưa đọc.

## Giữ thay đổi mới nhất

Trong lúc chuẩn bị lưu, phát hiện mã máy chủ/desktop có thêm hướng dẫn đọc BTH An Thọ. Đã ghép nguyên phần queue_bth_reading_reference và lời gọi của nó; không ghi đè sửa đổi mới này. Các kiểm thử cũ được cập nhật số lượng cấu trúc tham khảo (84 cấu trúc khác nhau) và tính cả mục hướng dẫn BTH đang chờ gửi. Sau khi ghép, 36 kiểm thử vẫn đạt.
