# Sửa PDF CDM/ALiCC

Thay 5 module cùng tên trong thư mục phần mềm bằng các file trong gói này. Gói chỉ gồm file liên quan, áp dụng trên bản cập nhật trước.

- Bỏ biểu đồ lún dư dưới mũi cọc CDM khỏi PDF; giữ biểu đồ giao diện.
- Tăng cỡ chữ nội dung và bảng CDM/ALiCC. Chia bảng địa chất và bảng phân tố rộng thành các bảng vừa trang để không phải ép chữ nhỏ.
- Mỗi thông số có tên riêng, mỗi giá trị một dòng. Không gộp D/s/Lc, Ac/qu/Suc, Ec/Es, Si/Sc/S, lún dư/giới hạn hay các hệ số.
- Trình tự PDF: tính lún; ứng suất đầu cọc TTGH1 và TTGH2 đối với CDM; ứng suất đất nền; kiểm toán vải/lưới hoặc đệm; kết luận. Thông số vải nằm ngay trong mục kiểm toán vải.
- ALiCC trình bày theo cùng thứ tự các mục và dùng kết quả đầu cọc Pcol đã có của mô hình ALiCC. Không thêm phép kiểm toán TTGH2 hoặc sức chịu tải đất chưa có trong mô hình.
- Bỏ kiểm toán chênh lún đầu cọc/đất nền ALiCC khỏi giao diện, PDF, điều kiện tối ưu, kết quả nhanh và tính hàng loạt. Không yêu cầu giới hạn chênh lún để tính ALiCC.
- Không chạy chương trình, kiểm thử hoặc xuất PDF kiểm tra sau khi sửa theo yêu cầu.
