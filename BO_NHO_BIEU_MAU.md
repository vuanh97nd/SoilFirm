# Bộ nhớ biểu mẫu — SoilFirm Pro 2026.11

Nguồn: My Drive/Dev/Dao tao AI. Giữ nguyên toàn bộ file mẫu. Kiểm thử trên bản sao ngày 05/10/2026.

## Đã tích hợp

- `geotech_template_catalog.json`: 15 cấu trúc tiêu đề từ 6 file Excel tải được, kèm file/sheet và SHA-256. Chỉ metadata; không lưu bảng số thí nghiệm để điền file khác.
- Khi đọc Excel, phần mềm nạp các biểu mẫu tham khảo vào SQLite của dự án, ghi cấu trúc vừa gặp. Bộ nhớ còn sau khởi động lại; dự án và tài khoản tách riêng.
- Khi cần AI giải nghĩa cột, chỉ lấy tối đa 6 gợi ý phù hợp, tối đa 1.600 ký tự. Đơn vị hoặc nhóm thí nghiệm khác thì không dùng gợi ý đó.
- Gợi ý biểu mẫu chưa phải quy tắc đã xác nhận. Không tự tạo ánh xạ tin cậy; quy tắc người dùng xác nhận được ưu tiên và vẫn qua cổng kiểm tra số liệu hiện tại.
- Nút **Bộ nhớ AI → Biểu mẫu** hiển thị nguồn và cấu trúc đã lưu. Lịch sử sửa/kiến thức hiện có được giữ nguyên.
- Bổ sung asset vào build_app.py và SoilFirm_Professional.spec; không ghi đè cơ sở dữ liệu cá nhân khi cập nhật.

## Lỗi đã sửa

1. Bộ dò tiêu đề chưa nhận đầy đủ `Lớp đất`/`Mã lớp` và tiêu đề song ngữ: dòng mẫu đầu có thể bị đưa vào tiêu đề AI. Đã dừng trước dòng mẫu.
2. Bỏ trị số công thức lạc trong vùng tiêu đề; vẫn giữ cấp áp lực trong nhóm đường cong.
3. Sau nhập Su/SPT/đường cong, nếu chỉ tiêu đang xem không có số liệu, chọn chỉ tiêu thực có dữ liệu. Không thay lựa chọn đang có số liệu, không thay số gốc.

## Kết quả kiểm thử

| Ca | Nguồn | Thực tế | Đánh giá |
|---|---|---|---|
| R01 | BTH.xlsm / 24.07, BTH | 17 bản ghi lớp theo phạm vi dự án, 11 có chỉ tiêu, 6 chỉ có nhận dạng. Toàn bộ đầu ra trước/sau sửa giống nhau. | Hồi quy đạt; không coi lớp chỉ có tên là đủ đầu vào tính. |
| R02 | BTH.xlsm / 24.07!S13,V13,AD13,AE13 | Giữ γ, e0, φ độ-phút và c; không thay số khi thêm bộ nhớ. | Đối chiếu hồi quy đạt. |
| R03 | 6. Kết quả cắt cánh VD4 HCM.xlsx / H1-VST1!B19,E19 | Z nguồn; Su=27 kPa → Co=2.7532337750404063 T/m². Tổng 16 điểm đo đọc được. | Bộ đọc xác định chạy được; không gọi AI. |
| R04 | 05. Bieu do cat canh.xlsx / Tong!F1:F2 | Tiêu đề chỉ còn `Su`, không chứa số mẫu 33.924. Nguồn có Su và Su hiệu chỉnh nhưng thiếu đơn vị rõ tại tiêu đề. | Lỗi trộn dòng mẫu đã sửa. Đơn vị/nhóm còn phải xác định; không đoán. |
| R05 | Data.xlsx / CTDY | 7 lớp có chỉ tiêu. Kiểm thử thông qua các module phụ của phần mềm. | Bộ đọc chạy được; các phần lạ gọi AI được mô phỏng lỗi và vẫn giữ phần hợp lệ. |
| R06 | PL01. Bang Tong Hop Lop Cau Phu Kieng .xlsx / TH_Ngang | Lưu cấu trúc tiêu đề nhiều tầng và ký hiệu nguồn; chưa kiểm chứng ánh xạ bằng AI thật. | Còn cần kiểm chứng. |
| R07 | 1 Tổng hợp nền, công, hầm.xls / Tổng hợp, Phan lop | Lưu cấu trúc chỉ tiêu và đơn vị; Cv125–0.25 mơ hồ, không tự sửa thành Cv0.125–0.25. | Còn cần kiểm chứng ánh xạ/đơn vị. |
| R08 | SU.xlsm | Google Drive trả 403 `cannotDownloadAbusiveFile`. | Chưa tải, chưa kiểm thử. |
| M01 | SQLite tạm | Lưu/mở lại, phân tách dự án, nạp lặp không trùng, không sinh mapping đã xác nhận. | Đạt. |
| M02 | Bộ nhớ tiêu đề | Đơn vị/nhóm không tương thích bị loại khỏi gợi ý; dự án khác không truy xuất; hạn mức ký tự giữ đúng. | Đạt. |
| U01 | Mô phỏng lớp hiển thị | Su chọn Co; đường cong chọn e-logP; giữ Cc nếu đang có dữ liệu. | Đạt mô phỏng; chưa chạy Tkinter trên Windows. |

Đã chạy **19 kiểm thử tự động đạt** và đối chiếu đầu ra BTH trước/sau giống hệt. Kiểm thử không dùng mô hình Ollama thật. Không có số đo token/thời gian phản hồi AI thật. Thời gian bộ đọc đo tại môi trường kiểm thử: BTH khoảng 3,4 giây; cắt cánh khoảng 0,94 giây; Data khoảng 3,85 giây. Không dùng các thời gian này làm cam kết trên máy người dùng.

MAU.json và TT.json là tệp dự án, LK.dxf là CAD; đã đọc kiểm tra cấu trúc, không chuyển trị số của các công trình này thành kiến thức dùng chung. Bộ tham khảo mới tập trung vào các biểu mẫu Excel.

## Cách tự kiểm tra trên máy

1. Chạy bản mã nguồn mới (EXE cũ cần đóng gói lại).
2. Mở dự án, chọn Qwen/DeepSeek như đang dùng và đọc file Excel.
3. Vào **Bộ nhớ AI → Biểu mẫu** để kiểm tra cấu trúc được nạp/ghi nhận.
4. Sửa ánh xạ hoặc chỉ tiêu tại giao diện hiện có; bản sửa xác nhận được ghi vào lịch sử.
5. Lưu dự án, đóng/mở phần mềm; kiểm tra lịch sử còn và đổi dự án không lẫn dữ liệu.

Chạy kiểm thử: `python -m unittest test_geotech_memory test_template_catalog -v` tại thư mục mã nguồn. Test dùng bản sao mẫu nếu có, không ghi vào file nguồn.
