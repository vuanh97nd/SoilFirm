# SoilFirm Pro 2026.11 — Giao diện tính một đoạn và nhiều đoạn

Giải nén toàn bộ thư mục rồi chạy `run.bat` trên Windows. Đây là gói mã nguồn Python, chưa phải bộ cài EXE.

Chọn **TÍNH MỘT ĐOẠN** hoặc **TÍNH TOÀN TUYẾN** ở đầu thanh **QUY TRÌNH THIẾT KẾ**.

## TÍNH MỘT ĐOẠN
1. Thông tin và dữ liệu.
2. Thông số đầu vào.
3. Kiểm toán trước xử lý.
4. Thiết kế xử lý nền.
5. Lựa chọn và hồ sơ.

Nhập và tính thủ công tại các mục 1–4. Mục 5 chỉ so sánh các kết quả đã tính, gồm ba thẻ: So sánh phương án, Phương án lựa chọn, Xuất hồ sơ. Phân biệt kiểm toán lún với kiểm toán phương án; phương án chưa đạt không được chọn làm phương án cuối. Người dùng tự chọn và ghi lý do; không đưa chi phí vào so sánh và không tự gọi phương án đạt là tối ưu. Không có khối lượng trong luồng một đoạn.

Lưu dự án giữ các kết quả đã tính và phương án lựa chọn. Có thể xuất Excel, JSON và PDF của bản tính được chọn. Đầu vào thay đổi sẽ yêu cầu tính và lựa chọn lại trước khi xuất hồ sơ.

## TÍNH TOÀN TUYẾN
1. Dự án và phân đoạn: thông tin dự án đặt trên bảng Data, cùng các biến với trang thông tin dự án. Bấm Áp dụng thông tin dự án sau khi sửa. Giữ thông tin dự án trong Data khi nhập nguồn mới.
2. Địa chất và chỉ tiêu: Địa tầng lỗ khoan (AI), Thống kê số liệu (AI), Bảng tổng hợp chỉ tiêu.
3. Kiểm toán trước xử lý: bảng từng đoạn gồm lý trình, chiều dài, mặt cắt, lỗ khoan, địa tầng/bề dày và kết quả kiểm toán. Chọn hàng để xem chi tiết. Tính riêng trước xử lý, không bắt buộc chạy thiết kế xử lý trước. Có thao tác AI rà dữ liệu và tổ chức tính bằng bộ máy SoilFirm.
4. Thiết kế xử lý nền: bảng phương án theo phân đoạn, mỗi phương án một hàng. Giữ trang nhập và tính chi tiết cơ học, cố kết/thoát nước, CDM/ALiCC. Chạy AI hỗ trợ tính hàng loạt hoặc mở tính hàng loạt thủ công hiện có. Chọn hàng để xem chi tiết; nhấp đúp để so sánh đoạn đó.
5. So sánh, chọn phương án: đối chiếu kết quả, thông số và thời gian; phân biệt kiểm toán lún với kiểm toán phương án. Chốt theo từng đoạn trước khi tiếp tục. Đoạn đạt trước xử lý cũng cần người dùng duyệt Không cần xử lý trong luồng tính tuần tự.
6. Tổng hợp và hồ sơ: tổng hợp kết quả đã chốt, khối lượng xử lý nền, xuất hồ sơ chung.

AI sử dụng nhà cung cấp đang chọn, đọc/rà dữ liệu và hỗ trợ đề xuất. Bộ máy SoilFirm Pro tính theo công thức hiện có. Dữ liệu thiếu được báo để bổ sung; không tự điền bằng 0. Đề xuất hàng loạt cần được người dùng duyệt trước khi chốt. Tính hàng loạt thủ công hiện có vẫn giữ.

Chuyển chế độ giữ đầu vào, kết quả, phương án và dữ liệu AI; không bắt đầu phiên mới. Chế độ và kết quả mới được lưu cùng dự án. Dự án cũ vẫn được nạp bằng cơ chế khôi phục kết quả hiện có.

## Phạm vi kiểm tra
Đã mở toàn bộ trang và chuyển chế độ bằng Tk trên màn hình ảo Linux; kiểm tra bảng trước/sau xử lý, mở so sánh từ hàng phương án, lưu/khôi phục chế độ và kết quả; chọn phương án một đoạn và xuất JSON/Excel/PDF thành công trên dữ liệu kiểm tra. Đã sửa lỗi đóng/mở vùng thông số khi chuyển cơ học sang PVD/SD.

Chưa kiểm tra trực tiếp GUI Windows, nhà cung cấp AI thật và đóng gói EXE/Setup. Không sửa công thức của các mô đun tính toán.

Bộ kiểm tra cũ có 68 ca: 64 ca đạt; 4 ca đọc nhiều file/cache dùng giả lập chưa tương thích bản dữ liệu mới (3 ca dùng đường dẫn Excel không tồn tại, 1 ca kỳ vọng số lượt gọi cache khác hành vi hiện tại). Đây là các kiểm tra có sẵn, chưa sửa trong thay đổi giao diện này.
