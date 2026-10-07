# Cập nhật lỗi St, biểu đồ và tối ưu cơ học

Thay các module cùng tên trong thư mục phần mềm bằng các file trong gói này. Gói giữ các cập nhật đã làm trước đó.

Các file sửa trong lần này:
- app.py, model.py: thống nhất kết quả tổng lún St; sửa hàm tính lún theo thời gian, bảng kết quả, biểu đồ và lưu kết quả theo mục.
- graphics.py: đường St dùng tổng lún thay vì Sc; đường Sc dư vẫn dùng lún cố kết còn lại.
- treatment_optimizer.py: thử đào tăng dần (bước mặc định 0.5 m, giới hạn đào 4 m theo mô hình hiện hành); chỉ sau khi đào không đạt mới thử đào + tre cố định 3 m, sau đó đào + cừ tràm cố định 4 m. Chiều dày xử lý = H đào + chiều dài cọc. Dừng ở cấu hình đạt đầu tiên, kiểm toán các vị trí thuộc vùng xử lý.
- batch_calculation.py, batch_view.py: cố định chiều dài tre/tràm, bổ sung chiều dày xử lý và mật độ trong kết quả; xử lý trường hợp đào 0 m không có cọc.
- treatment_boq.py, result_summary.py, boq_excel.py: mật độ tre và cừ tràm 25 cọc/m²; tính đủ số lượng và tổng chiều dài cọc, đồng nhất dữ liệu xuất Excel KL.

Không chạy kiểm thử hoặc chạy phần mềm sau khi sửa theo yêu cầu.
