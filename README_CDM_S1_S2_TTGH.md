# Cập nhật CDM S1/S2 và PDF

Thay các module cùng tên bằng 4 file Python trong gói; dùng cùng các file còn lại của bản trước.

- PDF tách hai bảng kiểm toán đầu cọc TTGH1 và TTGH2, mỗi bảng có kết quả đánh giá riêng.
- PDF tách bảng lún khối gia cố S1 và bảng phân tố đất dưới mũi cọc S2/Sc2. Bảng S2 không còn trộn hàng khối CDM.
- S1 = q*Lc/[ap*Ec+(1-ap)*Es]*100 (cm), theo dạng công thức Phụ lục C của TCVN 9403:2012. q = gamma*H tính đắp + qH; chiều sâu khối gia cố trong công thức là Lc, không phải chiều cao đắp.
- Cọc treo: S2 = tổng Sc2 của các phân tố dưới mũi cọc; Si = S1+0.2*S2; Sc = Sc2; S = Si+Sc, theo quy tắc tổng hợp người dùng yêu cầu. Hệ số 0.2 này không được ghi là quy định của TCVN 9403.
- Cọc chống: không tính phân tố lún dưới mũi; S2=Sc2=0, Si=S1, Sc=0, S=S1+S2=S1.
- Bộ tính CDM, tổng hàng trên giao diện, kết quả nhanh và dữ liệu hàng loạt dùng cùng các giá trị cập nhật. Bản này không thay quy tắc tính ALiCC riêng.
- Hình CDM trong PDF có thước chiều dài cọc và nhãn Lc.
- Bỏ mục 5 Kết luận kiểm toán trong PDF CDM/ALiCC. Đánh giá riêng tại từng mục vẫn được giữ.
- Không chạy kiểm thử hoặc xuất PDF kiểm tra sau khi sửa.

Nguồn công thức S1: TCVN 9403:2012, Phụ lục C (bản tiêu chuẩn): https://www.mtu.edu.vn/Resources/Docs/Khoa%20-%20Bo%20mon/Khoa%20Xay%20dung/Tai%20lieu%20tham%20khao/TCVN/ThiCong-NghiemThu/TCVN9403_2012.pdf
