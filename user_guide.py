"""Hướng dẫn cho quy trình 10 mục và các chức năng hiện tại."""
GUIDE_VI = '''HƯỚNG DẪN SỬ DỤNG SOILFIRM PRO

1. ĐĂNG NHẬP VÀ QUYỀN SỬ DỤNG
Bấm Tạo tài khoản Trial, nhập họ tên, email, tài khoản và mật khẩu. Máy chủ phải hỗ trợ API đăng ký. Sau khi đăng ký thành công, bấm Đăng nhập.
Trial được nhập số liệu ở mục 1–3 và tính thông thường ở mục 4–5. Trial không được sử dụng mục 6–10, tính tối ưu, import tính hàng loạt hoặc xuất PDF. Tài khoản đầy đủ/admin mở các chức năng tương ứng.

2. MỤC 1 — THÔNG TIN DỰ ÁN
Nhập tên dự án, bước thiết kế, hạng mục, lý trình và mặt cắt. Chọn cấp đường, vị trí nền đắp và giới hạn lún theo hồ sơ thiết kế của công trình.

3. MỤC 2 — HÌNH HỌC NỀN ĐẮP
Nhập Htk, Hkcad, bề rộng nền, mái dốc, trọng lượng thể tích, cao độ tự nhiên và điều kiện nước. Nếu có nền mở rộng, khai báo đúng phía, bề rộng và địa chất nền chính. Htt gồm Htk, Hkcad và phần bù lún Hbl.

4. MỤC 3 — ĐỊA CHẤT
Nhập từng lớp theo thứ tự từ trên xuống: mã lớp, chiều dày, loại đất, trọng lượng thể tích và điều kiện thoát nước. Đất dính dùng bộ Cc/Cs/Pc hoặc đường e–logP, cùng Cv theo cấp áp lực. Đất rời dùng dữ liệu SPT theo mô hình đã chọn. Áp lực trong bảng thí nghiệm phải đúng đơn vị ghi trên giao diện.
Cc, Cs, e0, Cv hiển thị 3 chữ số thập phân; các đại lượng số còn lại hiển thị 2 chữ số. Định dạng hiển thị không phải là độ chính xác bảo đảm của kết quả tính.

5. MỤC 4 — LÚN TỰ NHIÊN
Chọn vị trí tính toán và thời gian đánh giá; mặc định thời gian là 0 ngày. Bấm nút Tính lún cố kết để xem bảng lún, kết quả nhanh và biểu đồ. Nút Tính lún theo thời gian lập diễn biến cố kết. Đổi vị trí tính toán cần bấm tính lại.

6. MỤC 5 — THAY THẾ VÀ GIA CƯỜNG CƠ HỌC
Khai báo đào thay, cọc tre hoặc cừ tràm. Chọn đắp phân kỳ, chờ lún/gia tải nếu sử dụng. Bấm Tính lún cố kết để xem kết quả của riêng mục 5.
Bản đầy đủ có tối ưu đào thay theo bước chiều sâu chọn được; mặc định 0,50 m, cọc tre 3,00 m, cừ tràm 4,00 m. Phạm vi quét đào thay hiện tại là 0–4 m. Tối ưu dừng ở phương án đầu tiên đạt điều kiện lún, không phải tối ưu chi phí và không thay thế kiểm toán ổn định mái dốc.

7. MỤC 6 — CỐ KẾT VÀ THOÁT NƯỚC
Chọn chờ lún, PVD, SD hoặc kết hợp gia tải/hút chân không. Khai báo khoảng cách, sơ đồ, đường kính tương đương, chiều dài xử lý, đệm thoát nước và lịch đắp. Chiều cao từng giai đoạn phải tăng và kết thúc ở Htt. Bấm tính để xem Sc, St, lún dư và độ cố kết; nếu có vùng chưa cắm hết chiều sâu thì xem riêng lún dư trong vùng xử lý và vùng chưa xử lý.
Tối ưu thời gian tìm thời điểm thỏa đồng thời điều kiện lún dư và độ cố kết theo mô hình. Lún dư của gia tải phải dùng đúng thời gian lưu tải, không cộng trùng với thời gian chờ giai đoạn cuối.

8. MỤC 7 — TRỘN SÂU CDM
Chọn phạm vi nền đường/nền mở rộng và phương pháp TCVN/BS hoặc ALiCC. Khai báo D, s, Lc, mô đun, cường độ cọc, tải, nền dưới mũi và gia cường đầu cọc nếu có. Bấm tính trong thẻ đang dùng. Xem đồng thời lún, ứng suất cọc, sức chịu tải nền và gia cường.
Bước tìm kiếm chiều dài cọc CDM mặc định 0,50 m và thay đổi được. Tính hàng loạt giữ các thông số đã khai báo, thử tăng chiều dài đến chiều sâu địa chất và chọn chiều dài đầu tiên đạt. Nút tối ưu riêng của TCVN/BS cho phép khai báo cả phạm vi Lc và khoảng cách cọc; ALiCC có bước Lc riêng.

9. MỤC 8–10 — PHƯƠNG ÁN, TỔNG HỢP VÀ KHỐI LƯỢNG
Mục 8 so sánh các phương án đã tính. Mục 9 tổng hợp kết quả hiện tại hoặc các phân đoạn đã lưu. Mục 10 bóc khối lượng theo phương án, chiều dài đoạn và thông số hình học. Chọn đúng phạm vi và nguồn số cọc CDM: công thức diện tích ô cọc hoặc CIRCLE theo layer CAD.

10. IMPORT/EXPORT EXCEL VÀ TÍNH HÀNG LOẠT
Tệp Data phải có THSH và CTDY. Thông tin dự án lấy từ THSH!A3, bước ở A4 và hạng mục ở A5. Mã lớp ở hàng 10; cột N:AD là chiều dày lớp, AE là điều kiện thoát nước. CTDY chứa chỉ tiêu theo mã lớp. Nếu có eCV-P, ghi rõ đơn vị áp lực và Cv; chương trình đọc cả bảng e–P và Cv–P. Công thức Excel phải được Excel/LibreOffice tính và lưu trước khi import; openpyxl không tự tính công thức.
Chọn STT hoặc để trống để tính toàn bộ, chọn thư mục và thứ tự tối đa 5 phương án ưu tiên. Bỏ trống một ưu tiên để bỏ qua. Khai báo bước đào/CDM và chiều dài tre/tràm. Tính dừng tại phương án đạt đầu tiên của từng đoạn.
Xuất Data ghi kết quả vào bản sao, gồm các giai đoạn đắp SD/PVD và các thông số xử lý, không xuất hệ số ổn định chưa có mô hình tương ứng. BTH lưu dữ liệu phương án/mặt cắt phục vụ bóc khối lượng. Tệp nguồn không bị ghi đè.

11. KẾT QUẢ NHANH VÀ BIỂU ĐỒ
Mục 4–7 có bộ kết quả riêng. Chưa bấm tính thì ẩn kết quả nhanh và biểu đồ. Quay lại một mục đã tính thì phục hồi kết quả/biểu đồ của mục đó. Khi thay đổi dữ liệu đầu vào, kết quả cũ bị hủy và cần tính lại. CDM hiển thị kết quả nhanh sau khi bấm tính trong thẻ phương pháp tương ứng.

12. PDF VÀ NGÔN NGỮ
Chọn tiếng Việt hoặc English trước khi xuất. Bấm tính đúng mục/phương pháp rồi xuất PDF của mục đó. Chọn Có ở câu hỏi logo để đặt logo SOILFIRM PRO ở đầu trang bên phải; chọn Không để xuất không logo. Công thức dùng MathText để hiển thị phân số, căn, chỉ số và số mũ. Cài các thư viện trong requirements_update.txt. Trial không được xuất PDF.

13. HỖ TRỢ
Bấm “Hỗ trợ online 24/24 bấm vào đây”, nhập tin nhắn và có thể đính kèm ảnh PNG/JPEG/WebP. Ảnh được chuyển JPEG và giới hạn 2 MB sau khi xử lý. Bấm Xem ảnh để mở ảnh lớn. Tin nhắn tự cập nhật mỗi 10 giây.
Khi admin offline và máy chủ đã cấu hình cầu nối email, thông báo được gửi về vuanh97nd@gmail.com. Admin bấm Reply, viết nội dung phía trên phần trích dẫn và giữ mã luồng trong tiêu đề. Phản hồi được gửi lại đúng người dùng; có thể gửi kèm ảnh.

14. LƯU VÀ XỬ LÝ LỖI
Lưu dự án JSON trước khi thay đổi số liệu lớn. Khi thiếu dữ liệu, đọc thông báo tại mục đang làm và bổ sung trường tương ứng. Nếu đăng ký/chat ảnh/email báo máy chủ chưa hỗ trợ, cần cập nhật Worker theo tài liệu SERVER_SETUP.md. Đối chiếu giả thiết, đơn vị và phạm vi tiêu chuẩn với hồ sơ thiết kế trước khi sử dụng kết quả.
'''
GUIDE_EN = '''SOILFIRM PRO USER GUIDE

1. SIGN-IN AND ACCESS
Click Create a trial account and enter your name, email, username and password. Registration requires the server extension. After registration, click Sign in.
Trial allows input sections 1–3 and standard calculations in sections 4–5. Sections 6–10, optimization, batch import/calculation and PDF export require a full license. Admin accounts retain their management access.

2. SECTION 1 — PROJECT
Enter the project name, design stage, work item, station range and section. Set the road category, embankment location and settlement limit according to the project design.

3. SECTION 2 — GEOMETRY
Enter design fill height Htk, equivalent pavement height Hkcad, crest width, side slope, fill unit weight, ground elevation and groundwater conditions. For widening, define the correct side, width and existing embankment soil. Total calculation height Htt includes Htk, Hkcad and settlement compensation Hbl.

4. SECTION 3 — SOIL
Enter layers from top to bottom with layer codes, thicknesses, soil types, unit weights and drainage conditions. Cohesive soil uses Cc/Cs/Pc or an e–logP curve plus Cv versus pressure. Granular soil uses SPT parameters for the selected model. Match the pressure units displayed in the test tables.
Cc, Cs, e0 and Cv use three decimal places; other numeric quantities use two. Display precision does not guarantee equivalent analytical accuracy.

5. SECTION 4 — NATURAL SETTLEMENT
Select the assessment location and time; the default time is zero days. Click Calculate consolidation settlement to show the table, quick results and chart. The settlement-versus-time action calculates consolidation history. After changing the assessment location, click Calculate again.

6. SECTION 5 — MECHANICAL TREATMENT
Define excavation/replacement, bamboo or cajuput piles and the fill schedule. Enable waiting or surcharge where appropriate. Click Calculate to view results specific to section 5.
Full-license optimization uses a selectable excavation increment, default 0.50 m; default bamboo and cajuput lengths are 3.00 m and 4.00 m. The excavation search range is currently 0–4 m. The first settlement-compliant alternative is selected. This is not cost optimization and does not replace slope stability checks.

7. SECTION 6 — CONSOLIDATION AND DRAINAGE
Choose natural waiting, PVD, sand drains, surcharge or vacuum. Define spacing, pattern, equivalent diameter, treatment depth, drainage cushion and fill stages. Stage heights must increase and finish at Htt. Calculate to view Sc, St, residual settlement and consolidation degree. Review treated-zone and untreated-depth residual settlement separately where relevant.
Time optimization searches for simultaneous compliance with residual settlement and consolidation criteria. Surcharge duration must not duplicate the last stage waiting time.

8. SECTION 7 — CDM
Choose the road/widening scope and TCVN/BS or ALiCC. Define D, s, Lc, stiffness, pile strength, loads, soil beneath the tips and reinforcement. Calculate in the selected method tab. Review settlement, pile stress, foundation bearing capacity and reinforcement together.
The default selectable CDM length increment is 0.50 m. Batch calculation keeps the other saved inputs and increases pile length up to the soil investigation depth, selecting the first passing length. The TCVN/BS optimizer also accepts pile-spacing ranges. ALiCC has its own Lc increment setting.

9. SECTIONS 8–10 — OPTIONS, SUMMARY AND QUANTITIES
Section 8 compares calculated options. Section 9 summarizes current or saved section results. Section 10 calculates quantities using the selected treatment, segment length and geometry. Choose the correct CDM pile-count source: cell-area calculation or CIRCLE entities on the CAD layer.

10. EXCEL AND BATCH CALCULATION
Data must contain THSH and CTDY. Project, design stage and work item are read from THSH!A3, A4 and A5. Layer codes are on row 10; N:AD contains layer thicknesses and AE contains drainage conditions. CTDY parameters are matched by layer code. If present, eCV-P supplies e–P and Cv–P tables with explicitly stated units.
Recalculate and save Excel formulas in Excel or LibreOffice before importing. openpyxl does not evaluate formulas.
Choose section numbers or leave the selection empty for all sections. Set the output folder, up to five priority options, excavation/CDM increments and pile lengths. Empty priorities are skipped. Each section stops at the first passing option.
Export Data writes a copy containing SD/PVD fill-stage results and relevant treatment parameters. Stability factors without a corresponding model are omitted. BTH stores option and section data for quantity calculations. The source workbook is not overwritten.

11. QUICK RESULTS AND CHARTS
Sections 4–7 keep separate calculated results. Quick results and charts stay hidden until Calculate is clicked. Returning to a calculated section restores its results and chart. Input changes invalidate previous results. CDM quick results appear after calculation in the selected method tab.

12. PDF AND LANGUAGE
Choose Vietnamese or English before exporting. Calculate the selected section/method first. Choose Yes in the logo prompt to place the SOILFIRM PRO logo at the upper-right page edge, or No to export without the logo. Formulas use MathText for fractions, roots, subscripts and exponents. Install requirements_update.txt. PDF export is unavailable in Trial.

13. SUPPORT
Click “24/7 online support — click here”. Send text and optionally attach PNG/JPEG/WebP images. Images are converted to JPEG and limited to 2 MB after processing. Click View image for the larger image. Messages refresh every ten seconds.
With the server email bridge configured, messages received while admin is offline trigger an email to vuanh97nd@gmail.com. Admin replies above the quoted content, keeping the thread token in the subject. The response is delivered to the corresponding user. Image replies are supported.

14. SAVING AND ERRORS
Save your project as JSON before major input changes. Read calculation messages and complete missing fields. If registration, image chat or email reports an unavailable server feature, update the Worker using SERVER_SETUP.md. Review model assumptions, units and applicable design standards before using calculated results.
'''

GUIDE_VI += "\n15. THÔNG BÁO VÀ CHẠY NỀN\nSau khi đăng nhập, ứng dụng kiểm tra tin chưa đọc mỗi 10 giây. Thông báo có nút Xem tin nhắn để mở cuộc trò chuyện. Bấm X và chọn Có để ẩn xuống khay; chọn Không để thoát, Hủy để giữ mở. Menu khay có Mở SOILFIRM PRO và Thoát hoàn toàn. Cần pystray/Pillow. Máy phải đang bật và đã mở/đăng nhập SOILFIRM PRO; chức năng này không tự khởi động cùng Windows.\n"
GUIDE_EN += "\n15. NOTIFICATIONS AND BACKGROUND MODE\nAfter sign-in, the application checks unread messages every ten seconds. Click View messages in the notification to open the conversation. Close the main window and choose Yes to minimize to the tray, No to exit, or Cancel to keep the window open. The tray menu offers Open SOILFIRM PRO and Exit completely. Install pystray/Pillow. The computer must stay on and SOILFIRM PRO must already be running and signed in; this feature does not automatically start the application with Windows.\n"
