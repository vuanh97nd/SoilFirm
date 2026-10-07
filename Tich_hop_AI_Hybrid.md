# Tích hợp GeotechAIExtractor vào SoilFirm Pro 2026.11

Các nút đọc chỉ tiêu đất, sức kháng, N-SPT, cố kết và địa tầng sử dụng bộ xử lý tích hợp, tài khoản/proxy và AI được chọn trong phần mềm. Không dùng khóa API riêng cho luồng SoilFirm.

- Nhãn/callback nút giữ nguyên. Mọi kết quả qua GeotechAIExtractor.review_soilfirm_reader và xác nhận AI mới trước khi được trả cho bảng xem trước.
- Cột chưa xác định: GeotechAIExtractor.propose_soilfirm_mapping gửi nhãn/ký hiệu/đơn vị, không gửi các giá trị đo; Pydantic chặn số liệu/khóa lạ. mapping_gate tiếp tục kiểm tra registry đầy đủ, đơn vị, nhóm và dữ liệu thật.
- Bảng Excel chưa xác định: pandas đọc ô thật theo tọa độ do bộ dò xác định; dữ liệu vào cổng chuyển đổi của registry SoilFirm. Null không biến thành 0. Các bộ đọc chuyên biệt Su/Co, N-SPT, e-P/Cv-P/mv-P, địa tầng vẫn giữ cách xử lý hiện có.
- Đọc nhiều file trong nền: tối đa 3 file đồng thời, tổng hợp theo thứ tự chọn. Hỏng một file không mất kết quả hợp lệ của file khác. Khi hủy, yêu cầu mạng đã chạy có thể phải chờ timeout.
- Kết quả chỉ là xem trước. Bấm Áp dụng để Python cập nhật; Tệp → Hoàn tác nhập dữ liệu khôi phục lần nhập phù hợp. AI lỗi vẫn giữ dữ liệu cũ.
- Đổi phiên bản cache để tránh dùng kết quả đọc của bộ xử lý cũ; cache không bỏ qua xác nhận AI mới.

## Chạy mã nguồn

Nếu môi trường chưa có thư viện mới, chạy từ đúng Python dùng để mở SoilFirm:

```bash
python -m pip install -r requirements_ai_hybrid.txt
python main.py
```

Không cần cài openai khi dùng proxy/tài khoản SoilFirm. SDK chỉ dùng cho chế độ gọi API trực tiếp của class độc lập. Build_app tự kiểm tra pandas/Pydantic và đóng gói module mới; spec đã thêm thư viện. Bản EXE cũ phải được build lại để nhận mã mới.

## Kiểm thử

- 151 test tự động đạt: 146 test cũ và 5 test tích hợp mới. Hai test đa file được sửa mock để lỗi gắn vào tên file, không phụ thuộc thứ tự luồng chạy.
- 83 kiểm tra giao diện Tk thật trên Linux: 62 bốn luồng A/B/C/D; 8 kiểm tra AI mất kết nối bằng bản sao BTH; 13 kiểm tra thiết lập và năm nút đọc/xem trước/Áp dụng/Hoàn tác.
- Năm nút được thử bằng dữ liệu tự dựng và AI mô phỏng. Trước Áp dụng dữ liệu giữ nguyên; sau Áp dụng dữ liệu đổi; sau Hoàn tác dữ liệu gốc được khôi phục.
- Chưa gọi DeepSeek/NVIDIA/OpenAI thật; chưa chạy EXE trên Windows; chưa đo token/latency thực hoặc chứng minh mọi mẫu Excel đều chính xác. Không cam kết đúng 100%.
- Chưa bổ sung bộ đọc CSV vào các nút Excel hiện có; class độc lập vẫn hỗ trợ CSV. Không tự biến bảng nhiều vùng/đường cong thành bảng vô hướng.
