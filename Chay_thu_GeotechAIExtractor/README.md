# GeotechAIExtractor cho SoilFirm Pro 2026.11

Đây là module độc lập và bản chạy thử; chưa ghi đè hoặc gắn vào phần mềm đang dùng. AI chỉ trả ánh xạ cột. Python lấy số từ ô nguồn. Không thể bảo đảm 100% ngữ nghĩa cho mọi mẫu bằng LLM; JSON hợp lệ cũng có thể ánh xạ sai. Phải kiểm tra đơn vị, nhóm thí nghiệm và bảng xem trước trước khi ghi vào SoilFirm.

## Cài đặt và chạy

Python 3.10 trở lên:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -v
python demo_tkinter.py
```

Trong PowerShell, đặt khóa thật từ tài khoản của bạn vào biến môi trường `DEEPSEEK_API_KEY` hoặc `OPENAI_API_KEY`. Có thể nhập kín, tránh lưu vào mã:

```powershell
$secret = Read-Host 'Khóa DeepSeek' -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
python demo_tkinter.py
```

Chọn nhà cung cấp, bấm **Đọc và xem trước**, chọn Excel/CSV. Tối đa 5 worker chạy đồng thời; có thể nạp nhiều hơn 5 file, các file còn lại chờ lượt.

## Gọi trong Python

```python
from tkinter import filedialog
from geotech_ai_extractor import GeotechAIExtractor

path = filedialog.askopenfilename()
if path:
    with GeotechAIExtractor(provider='deepseek') as extractor:
        result = extractor.extract_file(path)
        print(result.to_json())
```

Trong Tkinter thật, dùng `extract_files_background()` và `poll_tk()` như `demo_tkinter.py`, không gọi `extract_file()` đồng bộ trong sự kiện nút. Worker tuyệt đối không gọi widget; `root.after()` chỉ được đặt từ main thread.

API khác: `extract_files_async(paths)` dùng trong asyncio. Mỗi file trả `FileOutcome`; file lỗi có `error`, không có `result`. Không mất kết quả của file hợp lệ khác.

## Cấu hình nguồn và giới hạn

- Excel đọc sheet đầu mặc định; dùng `sheet='BTH'` hoặc tên sheet thật để đổi. Một lần xử lý là một bảng đồng nhất; không tự ghép nhiều bảng/lỗ khoan/lớp.
- Dùng `header_rows=[12,13]` khi tiêu đề không nằm trong 10 hàng đầu; dùng `data_start_row=15` khi biết vị trí mẫu đầu tiên. Chỉ số hàng là 1-based, giữ hàng trống để không lệch tọa độ.
- Nếu có hàng thống kê, tiêu đề lặp, nhiều nhóm thí nghiệm hoặc công thức lỗi xen trong dữ liệu: mặc định chặn. Cần bổ sung bộ tách vùng/mẫu theo registry của SoilFirm; không bật bỏ qua lỗi để đưa số liệu vào tính toán.
- `required=('gamma','e0')` yêu cầu hai chỉ tiêu có ánh xạ và giá trị ở mọi hàng; chọn theo phương pháp tính thật. Không mặc định mọi chỉ tiêu đều bắt buộc.
- `expected_groups={'cohesion_c':'cắt trực tiếp','phi':'cắt trực tiếp'}` chặn AI chọn UU/CU khác nhóm yêu cầu. Su/Co không ánh xạ vào c. γ khô hoặc γ đẩy nổi không dùng thay γ tự nhiên.
- `decimal='auto'`: một dấu phẩy là thập phân; `1,234` được hiểu là 1.234 theo quy ước này. Nếu nguồn dùng phân nhóm nghìn, phải khai báo rõ `decimal='.', thousands=','` hoặc `decimal=',', thousands='.'`. Không đoán `1.234,56` khi chưa cấu hình.
- Ô trống/NaN/null là `None`; số 0 thật vẫn bằng 0. Không làm tròn, nội suy, thêm chỉ tiêu hoặc điền mặc định.
- Giữ **đơn vị nguồn**; chưa tự đổi sang đơn vị nội bộ SoilFirm. Chưa rõ đơn vị có cảnh báo và không được dùng trong công thức. Muốn tự chuyển đơn vị cần registry đã kiểm toán; không có registry thì không đoán.
- φ dạng độ-phút bị chặn khi metadata ghi độ-phút. Chuỗi `7°58'` không bị biến thành float. Số mã 758 không thể tự phân biệt với độ thập phân khi nguồn không ghi quy ước: phải xác nhận/tiền xử lý trước.
- e-P/Cv-P và các dải áp lực là cấu trúc đường cong, không tự ánh xạ thành e0/Cv trung bình. Module này chỉ xử lý 9 chỉ tiêu vô hướng được yêu cầu; chưa thay thế bộ đọc cố kết, SPT theo độ sâu hay ghép lỗ khoan của SoilFirm.
- `strict_numbers=True` mặc định chặn toàn bộ kết quả file khi một ô số lỗi. `False` chỉ dùng để xem xét dữ liệu, giữ ô lỗi là None và cảnh báo; không dùng để tính tự động.
- AI lỗi/JSON sai/khóa lạ/cột bịa/trùng cột/độ tin cậy thấp => không trả số liệu. Không có fallback đoán, không gọi tools/function-calling ghi. Hủy tác vụ không trả kết quả muộn; yêu cầu API đã chạy có thể phải chờ timeout.

## Schema đầu ra AI

Tất cả khóa sau bắt buộc tồn tại; chỉ tiêu không xác định trả null. Các đối tượng cột chỉ gồm column/confidence/unit/group. Không chấp nhận trường value hay dữ liệu đo.

```json
{
  "data_start_row": 2,
  "gamma": {"column":"D", "confidence":0.99, "unit":"T/m³", "group":null},
  "e0": {"column":"F", "confidence":0.98, "unit":"1", "group":null},
  "cc": null, "cs": null, "pc": null, "cv": null,
  "cohesion_c": null, "phi": null, "spt": null
}
```

`result.records` chứa số do Python đọc, `source_row` truy về hàng nguồn, các chỉ tiêu chưa ánh xạ là None. `result.mapping` ghi cột, nhóm và đơn vị nguồn. `to_json()` trả null đúng chuẩn, cấm NaN/Infinity.

## Kết quả kiểm thử

16 kiểm thử tự động đã chạy đạt: số thập phân dấu phẩy, null/0, số mơ hồ, phân nhóm nghìn khai báo rõ, Excel/CSV thật tự dựng, file hỏng, JSON sai/bịa/kèm số liệu, AI lỗi không trả kết quả, cột trùng/không tồn tại, chỉ tiêu thiếu, nhóm sai, giới hạn 10 hàng, hủy, xử lý song song và asyncio.

API được mô phỏng trong test; chưa gọi OpenAI/DeepSeek thật, chưa đo token/latency thực, chưa kiểm thử trên BTH thực và chưa chạy EXE Windows. Các số usage trong test là số giả lập, không phải phép đo API. Module chưa tự ghi vào dự án SoilFirm.

## Tài liệu API đã đối chiếu

- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- DeepSeek JSON Output: https://api-docs.deepseek.com/guides/json_mode/

OpenAI dùng json_schema strict; DeepSeek dùng json_object và Python/Pydantic kiểm tra schema lần nữa. JSON mode không bảo đảm đúng ngữ nghĩa ánh xạ.

## Chạy thử trên Windows

Mở Chay_thu.bat. Lần đầu tạo môi trường .venv riêng và cài thư viện, cần Internet. Chọn DeepSeek/OpenAI, nhập khóa API khi được hỏi. Khóa chỉ dùng trong phiên chạy, không lưu file. Bấm Đọc và xem trước rồi chọn file. Module thử độc lập, không ghi vào dự án SoilFirm. Chưa kiểm thử launcher trên Windows.
