HƯỚNG DẪN SỬ DỤNG SOILFIRM PRO

1. ĐĂNG NHẬP VÀ QUYỀN SỬ DỤNG
Bấm Tạo tài khoản Trial, nhập họ tên, email, tài khoản và mật khẩu. Máy chủ phải hỗ trợ API đăng ký. Sau khi đăng ký thành công, bấm Đăng nhập.
Trial được nhập số liệu ở mục 1–3 và tính thông thường ở mục 4–5. Trial không được sử dụng mục 6–10, tính tối ưu, import tính hàng loạt hoặc xuất PDF. Tài khoản đầy đủ/admin mở các chức năng tương ứng.

2. MỤC 1 — THÔNG TIN DỰ ÁN
Nhập tên dự án, bước thiết kế, hạng mục, lý trình và mặt cắt. Chọn cấp đường, vị trí nền đắp và giới hạn lún theo hồ sơ thiết kế của công trình.

3. MỤC 2 — HÌNH HỌC NỀN ĐẮP
Nhập Htk, Hkcad, bề rộng nền, mái dốc, trọng lượng thể tích, cao độ tự nhiên và điều kiện nước. Nếu có nền mở rộng, khai báo đúng phía, bề rộng và địa chất nền chính. Htt gồm Htk, Hkcad và phần bù lún Hbl.

4. MỤC 3 — ĐỊA CHẤT
Bấm “Nhập lỗ khoan…” để nhập tên, cao độ và chiều sâu lỗ khoan tính toán cùng bề dày từng lớp theo thứ tự từ trên xuống. Cao độ này dùng làm Ztn của mặt cắt. Tổng bề dày phải khớp chiều sâu; có thể bấm “Lấy chiều sâu bằng tổng lớp”. Các lớp mới cần bổ sung chỉ tiêu trong “Sửa thông số chi tiết” trước khi tính. Thay bề dày sẽ tự cập nhật chiều sâu, cao độ đáy và hủy kết quả cũ.
Nhập từng lớp theo thứ tự từ trên xuống: mã lớp, chiều dày, loại đất, trọng lượng thể tích và điều kiện thoát nước. Đất dính dùng bộ Cc/Cs/Pc hoặc đường e–logP, cùng Cv theo cấp áp lực. Đất rời dùng dữ liệu SPT theo mô hình đã chọn. Áp lực trong bảng thí nghiệm phải đúng đơn vị ghi trên giao diện.
Cc, Cs, e0, Cv hiển thị 3 chữ số thập phân; các đại lượng số còn lại hiển thị 2 chữ số. Định dạng hiển thị không phải là độ chính xác bảo đảm của kết quả tính.

5. MỤC 4 — LÚN TỰ NHIÊN
Chọn vị trí kiểm toán và thời gian đánh giá; mặc định thời gian là 0 ngày. Bấm nút ∑ Tính lún cố kết để xem bảng lún, kết quả nhanh và biểu đồ. Nút ∑ Tính lún theo thời gian lập diễn biến cố kết. Đổi vị trí xem cần bấm tính lại.

6. MỤC 5 — THAY THẾ VÀ GIA CƯỜNG CƠ HỌC
Khai báo đào thay, cọc tre hoặc cừ tràm. Chọn đắp phân kỳ, chờ lún/gia tải nếu sử dụng. Bấm ∑ Tính lún cố kết để xem kết quả của riêng mục 5.
Bản đầy đủ có tối ưu đào thay theo bước chiều sâu chọn được; mặc định 0,50 m, cọc tre 3,00 m, cừ tràm 4,00 m. Phạm vi quét đào thay hiện tại là 0–4 m. Tối ưu dừng ở phương án đầu tiên đạt điều kiện lún, không phải tối ưu chi phí và không thay thế kiểm toán ổn định mái dốc.

7. MỤC 6 — CỐ KẾT VÀ THOÁT NƯỚC
Chọn chờ lún, PVD, SD hoặc kết hợp gia tải/hút chân không. Khai báo khoảng cách, sơ đồ, đường kính tương đương, chiều dài xử lý, đệm thoát nước và lịch đắp. Chiều cao từng giai đoạn phải tăng và kết thúc ở Htt. Bấm tính để xem Sc, St, lún dư và độ cố kết; nếu có vùng chưa cắm hết chiều sâu thì xem riêng lún dư trong vùng xử lý và vùng chưa xử lý.
Tối ưu thời gian tìm thời điểm thỏa đồng thời điều kiện lún dư và độ cố kết theo mô hình. Lún dư của gia tải phải dùng đúng thời gian lưu tải, không cộng trùng với thời gian chờ giai đoạn cuối.

8. MỤC 7 — TRỘN SÂU CDM
Chọn phạm vi nền đường/nền mở rộng và phương pháp TCVN/BS hoặc ALiCC. Khai báo D, s, Lc, mô đun, cường độ cọc, tải, nền dưới mũi và gia cường đầu cọc nếu có. Bấm tính trong thẻ đang dùng. Xem đồng thời lún, ứng suất cọc, sức chịu tải nền và gia cường.
Bước tìm kiếm chiều dài cọc CDM mặc định 0,50 m và thay đổi được. Tính hàng loạt giữ các thông số đã khai báo, thử tăng chiều dài đến chiều sâu địa chất và chọn chiều dài đầu tiên đạt. Nút tối ưu riêng của TCVN/BS cho phép khai báo cả phạm vi Lc và khoảng cách cọc; ALiCC có bước Lc riêng.

9. MỤC 8–10 — PHƯƠNG ÁN, TỔNG HỢP VÀ KHỐI LƯỢNG
Mục 8 có bàn làm việc “AI · Phân tích theo phân đoạn”, tách khỏi thẻ “Phương án · Mặt cắt hiện tại”. Quy trình mới:
• Bước 1: AI đọc chỉ tiêu địa chất từ Excel/PDF, hiện bảng và nguồn số liệu; nhấp đúp để sửa chỉ tiêu hoặc bảng e–P/Cv–P, sau đó duyệt địa chất.
• Bước 2: AI đọc tên, cao độ và địa tầng các lỗ khoan từ CAD/PDF. Sửa bề dày từng lớp, ghép mã lớp đúng với bảng chỉ tiêu và duyệt danh sách. Cao độ lỗ khoan dùng làm Ztn của mặt cắt tính. CAD dùng DXF; DWG cần ODA File Converter đã cài trên máy hoặc Save As DXF từ AutoCAD. PDF scan dùng ảnh trang để đọc; nếu trợ lý hiện tại không đọc được ảnh, chọn Gemini/trợ lý có hỗ trợ ảnh và đọc lại.
• Bước 3: Đọc Data THSH, kiểm tra phân đoạn, chiều dài và nền đắp. ΔS giữ đúng cột BG của từng STT. Chọn lỗ khoan cho từng đoạn bằng sửa dòng; chỉ tự điền khi tên cột G khớp tên lỗ khoan. Địa tầng tính lấy từ lỗ khoan được chọn, không lấy bề dày của đoạn trước.
• Bước 4: Lấy thiết kế chung từ mục 1–7 nếu đã khai báo CDM/ALiCC và thông số xử lý. Duyệt đầu vào rồi tính bằng bộ tính SoilFirm. Nếu đoạn đạt trước xử lý, tự chốt “Không cần xử lý”; nếu chưa đạt, AI tính các phương án đã chọn, hiện thông số, điều kiện kiểm toán và kết quả. Thiếu thông số thiết kế thì bổ sung tại hộp thoại. Chọn phương án ĐẠT và bấm “Chốt PA → mục 9”. Bật “Tiếp tục đoạn kế” để chuyển/tính đoạn tiếp theo; không bỏ qua đoạn chưa đạt hoặc lỗi.
• Bước 5: Các đoạn đã chốt được hiển thị tạm ở mục 9 và thẻ Đã chốt. Mục 10 có “Tính khối lượng bằng AI”, tính từ bản chụp mặt cắt/phương án của từng đoạn đã chốt. Đoạn Không cần xử lý có khối lượng xử lý bằng 0. Bấm Lưu dự án để giữ phiên AI và bảng tổng hợp; mở lại dự án để tiếp tục.
Các chỉ tiêu/cao độ/bề dày AI đọc chưa được duyệt không tự đưa vào bộ tính. Không sửa công thức tính toán. Chỉ số tối ưu và kết luận dựa trên các mô đun kiểm toán hiện có.

Mục 8 so sánh các phương án đã tính. Mục 9 tổng hợp kết quả hiện tại hoặc các phân đoạn đã lưu. Mục 10 bóc khối lượng theo phương án, chiều dài đoạn và thông số hình học. Chọn đúng phạm vi và nguồn số cọc CDM: công thức diện tích ô cọc hoặc CIRCLE theo layer CAD.

10. IMPORT/EXPORT EXCEL VÀ TÍNH HÀNG LOẠT
Tệp Data phải có THSH và CTDY. Độ lún cho phép [ΔS] lấy trực tiếp từ cột BG của từng đoạn, đơn vị cm; tên lỗ khoan lấy từ cột G, cao độ tính toán từ H. Giới hạn import được giữ nguyên khi đổi cấp đường, nạp dự án và dùng AI tính từng đoạn. Ô BG trống/sai sẽ báo địa chỉ ô để sửa file Excel, không dùng giá trị mặc định hoặc yêu cầu nhập lại trên giao diện. Giới hạn này là độ lún cho phép của đoạn; giới hạn chênh lún đất–cọc ALiCC là điều kiện riêng. Thông tin dự án lấy từ THSH!A3, bước ở A4 và hạng mục ở A5. Mã lớp ở hàng 10; cột N:AD là chiều dày lớp, AE là điều kiện thoát nước. CTDY chứa chỉ tiêu theo mã lớp. Nếu có eCV-P, ghi rõ đơn vị áp lực và Cv; chương trình đọc cả bảng e–P và Cv–P. Công thức Excel phải được Excel/LibreOffice tính và lưu trước khi import; openpyxl không tự tính công thức.
Chọn STT hoặc để trống để tính toàn bộ, chọn thư mục và thứ tự tối đa 5 phương án ưu tiên. Bỏ trống một ưu tiên để bỏ qua. Khai báo bước đào/CDM và chiều dài tre/tràm. Tính dừng tại phương án đạt đầu tiên của từng đoạn.
Xuất Data ghi kết quả vào bản sao, gồm các giai đoạn đắp SD/PVD và các thông số xử lý, không xuất hệ số ổn định chưa có mô hình tương ứng. BTH lưu dữ liệu phương án/mặt cắt phục vụ bóc khối lượng. Tệp nguồn không bị ghi đè.

11. KẾT QUẢ NHANH VÀ BIỂU ĐỒ
Mục 4–7 có bộ kết quả riêng. Chưa bấm tính thì ẩn kết quả nhanh và biểu đồ. Quay lại một mục đã tính thì phục hồi kết quả/biểu đồ của mục đó. Khi thay đổi dữ liệu đầu vào, kết quả cũ bị hủy và cần tính lại. CDM hiển thị kết quả nhanh sau khi bấm tính trong thẻ phương pháp tương ứng.

12. PDF VÀ NGÔN NGỮ
Chọn tiếng Việt hoặc English trước khi xuất. Bấm tính đúng mục/phương pháp rồi xuất PDF của mục đó. Chọn Có ở câu hỏi logo để đặt logo SoilFirm Pro ở đầu trang bên phải; chọn Không để xuất không logo. Công thức dùng MathText để hiển thị phân số, căn, chỉ số và số mũ. Cài các thư viện trong requirements_update.txt. Trial không được xuất PDF.

13. HỖ TRỢ
Bấm “Hỗ trợ online 24/24 bấm vào đây”, nhập tin nhắn và có thể đính kèm ảnh PNG/JPEG/WebP. Ảnh được chuyển JPEG và giới hạn 2 MB sau khi xử lý. Bấm Xem ảnh để mở ảnh lớn. Tin nhắn tự cập nhật mỗi 10 giây.
Khi admin offline và máy chủ đã cấu hình cầu nối email, thông báo được gửi về vuanh97nd@gmail.com. Admin bấm Reply, viết nội dung phía trên phần trích dẫn và giữ mã luồng trong tiêu đề. Phản hồi được gửi lại đúng người dùng; có thể gửi kèm ảnh.

14. LƯU VÀ XỬ LÝ LỖI
Lưu dự án JSON trước khi thay đổi số liệu lớn. Khi thiếu dữ liệu, đọc thông báo tại mục đang làm và bổ sung trường tương ứng. Nếu đăng ký/chat ảnh/email báo máy chủ chưa hỗ trợ, cần cập nhật Worker theo tài liệu SERVER_SETUP.md. Đối chiếu giả thiết, đơn vị và phạm vi tiêu chuẩn với hồ sơ thiết kế trước khi sử dụng kết quả.

15. THÔNG BÁO VÀ CHẠY NỀN
Sau khi đăng nhập, ứng dụng kiểm tra tin chưa đọc mỗi 10 giây. Thông báo có nút Xem tin nhắn để mở cuộc trò chuyện. Bấm X và chọn Có để ẩn xuống khay; chọn Không để thoát, Hủy để giữ mở. Menu khay có Mở SoilFirm Pro và Thoát hoàn toàn. Cần pystray/Pillow. Máy phải đang bật và đã mở/đăng nhập SoilFirm Pro; chức năng này không tự khởi động cùng Windows.

Chỉ tiêu địa chất ở mục 8 được lấy trung bình số học các mẫu cùng mã lớp. Ô thiếu không tính vào mẫu số; số 0 có thật vẫn được tính. Bảng e/Cv/Mv được trung bình tại từng cấp áp lực tương ứng. Các lớp khác mã được giữ riêng; loại đất/thoát nước khác nhau phải chọn lại khi duyệt. Bảng hiển thị số mẫu và nguồn; người dùng được sửa giá trị trung bình trước kiểm toán. Bề dày và cao độ lấy riêng theo lỗ khoan đã chọn.
