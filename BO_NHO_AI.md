# Bộ nhớ AI theo dự án – SoilFirm Pro 2026.11

Đây là bộ nhớ bên ngoài cho AI, không huấn luyện lại hoặc thay trọng số mô hình AI.
Áp dụng cho các nhà cung cấp AI hiện có trong danh sách lựa chọn của SoilFirm.

## Sử dụng

1. Mở dự án và đọc Excel bằng các nút hiện có. Cấu trúc biểu mẫu được ghi nhận;
   ghi nhận cấu trúc không có nghĩa ánh xạ đã được xác nhận.
2. Nếu ánh xạ cần sửa, chọn cột, thông số, đơn vị, nhóm thí nghiệm và xác nhận
   trên bảng ánh xạ hiện có. Chỉ ánh xạ qua cổng kiểm tra mới được lưu làm quy tắc.
3. Khi sửa mẫu, lớp đất hoặc lỗ khoan và bấm Lưu, lịch sử ghi giá trị trước/sau,
   người xác nhận, nguồn và các bằng chứng tọa độ có sẵn. Không tạo tọa độ giả
   khi nguồn chưa cung cấp. Trị số sửa không được dùng để điền file khác.
4. File tương tự trong cùng dự án phải khớp tiêu đề, vị trí cột, đơn vị, nhóm
   thí nghiệm và registry. Ánh xạ đã xác nhận được dùng lại không gọi AI;
   Python vẫn đọc trị số từ file mới và kiểm tra đầy đủ trước khi đưa vào bảng.
5. Trong cửa sổ chat, bấm **Bộ nhớ AI** để xem lịch sử và nhập kiến thức theo
   chủ đề địa tầng, chỉ tiêu, độ sâu, đường cong cố kết, xử lý nền hoặc kiểm toán.
   Kiến thức có nguồn, người xác nhận và được tích xác nhận mới vào RAG.
   Bản nháp không được AI sử dụng. Có thể ngừng dùng kiến thức hoặc quy tắc.
6. Lưu dự án trước khi thoát để giữ mã định danh dự án cùng file dự án.
   Mở lại chính file đã lưu sẽ truy xuất đúng bộ nhớ.

## Lưu trữ và cách ly

SQLite ở `%LOCALAPPDATA%\SoilFirm\memory\geotech_memory.sqlite3` trên Windows.
Nếu không có LOCALAPPDATA, dùng thư mục người dùng/SoilFirm/memory.
Bộ nhớ tồn tại sau khi tắt phần mềm, tách theo tài khoản + UUID của dự án,
không dùng tên công trình làm khóa. Hai dự án mới cùng tên vẫn tách biệt.
Bản sao của cùng dự án có cùng UUID và dùng cùng bộ nhớ; muốn một công trình
mới độc lập phải tạo dự án mới. Không tự nhập các quy tắc JSON toàn cục cũ
vào phạm vi dự án vì không biết chắc công trình gốc của chúng.

Chuyển sang máy khác: sao chép file dự án đã lưu và bộ nhớ SQLite khi phần mềm
đã đóng hoàn toàn. Giữ cả các file `-wal`, `-shm` nếu chúng còn tồn tại; không
sao chép riêng database đang có tiến trình ghi. Không tự đồng bộ bộ nhớ lên mạng.

## Phạm vi học

- Học ánh xạ ngữ nghĩa của cột, ký hiệu, đơn vị và nhóm thí nghiệm đã xác nhận.
- Lưu cấu trúc của biểu mẫu đã nhận diện, kể cả bộ đọc bằng quy tắc.
- Lưu lịch sử sửa mẫu/lớp/lỗ khoan và kết quả phương án được người dùng chấp nhận.
- RAG hiện dùng tìm kiếm từ vựng có giới hạn trên SQLite; tối đa 4 mục, 3.000 ký tự.
  Chỉ tìm trong tối đa 500 kiến thức gần nhất của dự án; không cần mô hình embedding.
- Không tự suy quy tắc đổi tên lớp hoặc trị số từ một lần sửa. Cột nhận dạng tên/mã
  lớp được học như ánh xạ; sửa nội dung tên/mã được lưu lịch sử để đối chiếu.
- Lịch sử số đo và kết quả tính không được tự nâng thành công thức hay tri thức.
  Khi muốn dùng một kết luận chuyên ngành, phải nhập kiến thức và xác nhận nguồn.
- Tọa độ nguồn được lưu theo bằng chứng reader cung cấp; mẫu nhập tay có thể không
  có tọa độ và được ghi rõ nguồn nhập tay. Không nói số Python đọc là số AI sinh.
- Giữ nguyên công thức tính, dữ liệu nguồn Excel, các nút đọc, sửa, xác nhận hiện có.

## Các tệp

Thêm: `geotech_memory.py`, `geotech_memory_ui.py`, `test_geotech_memory.py`.
Sửa: `ai_analysis_data.py`, `ai_analysis_workflow.py`, `geology_statistics.py`,
`chat_dialog.py`, `build_app.py`, `SoilFirm_Professional.spec`.

## Kiểm tra

```bat
python -m unittest test_geotech_memory -v
```

11 ca tự động đã chạy: tồn tại sau mở lại, cách ly dự án/tài khoản, đơn vị,
vị trí cột, thay registry, quy tắc chưa xác nhận, trị số sửa không trở thành
quy tắc, RAG bản nháp/dự án khác bị chặn, ngừng dùng quy tắc, ghi đồng thời,
đọc trị số mới khi dùng lại ánh xạ, dữ liệu sai vẫn bị chặn, id bịa bị chặn.
Đối chiếu bộ đọc BTH mẫu: giữ nguyên 17 bản ghi lớp tổng hợp trước/sau và ghi
2 cấu trúc biểu mẫu. Không có gọi Ollama thật trong các kiểm thử này.

Cần tự thử GUI/Windows: mở dự án, sửa mẫu, mở Bộ nhớ AI, xem lịch sử, xác nhận
ánh xạ rồi đọc file tương tự có số khác, lưu/thoát/mở lại, mở dự án mới cùng tên.
Chưa chạy EXE hoặc GPU trên máy người dùng; EXE phải đóng gói lại để nhận mã mới.
