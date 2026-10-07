# Kiểm tra mục 8 — SoilFirm Pro 2026.11

Đã chạy 61 kiểm thử tự động, tất cả đạt. Kiểm tra cú pháp toàn bộ mã Python và worker.js đạt.

Phạm vi: đọc Excel/PDF và CAD DXF; kiểm tra hợp đồng yêu cầu/trả lời AI bằng phản hồi mô phỏng; lấy trung bình mẫu theo mã lớp và cấp áp lực; bỏ qua ô thiếu nhưng giữ số 0; chọn lỗ khoan/cao độ/bề dày; ΔS trực tiếp từ THSH!BG; kiểm toán lún bằng bộ tính thật; hiển thị dữ liệu kết quả qua callback; chặn chốt phương án chưa đạt; lưu bản chụp mỗi đoạn; tính khối lượng theo bản chụp; lưu/mở phiên qua JSON; chặn kết quả tác vụ cũ khi đổi dự án.

Chạy lại từ thư mục mã nguồn: `python -m unittest test_ai_analysis -v` (cài requirements.txt trước).

Chưa kiểm tra trực quan giao diện Tkinter trên Windows, bản EXE hoặc kết nối dịch vụ AI thật vì môi trường hiện tại không có màn hình Windows/tài khoản dịch vụ. DWG cần ODA File Converter; DXF đọc trực tiếp. Cập nhật nguồn worker.js mới vào Cloudflare và Deploy để dùng giới hạn đầu ra trích số liệu mới (8192 token). Không thay đổi công thức tính toán.

Bổ sung kiểm tra phản hồi JSON có lời dẫn/Markdown/thẻ suy nghĩ; không nhập JSON bị cắt; yêu cầu AI trả lại một lần; giữ phản hồi lỗi gốc theo tên nguồn/trợ lý; trạng thái và cửa sổ thanh chạy được mở/đóng cả khi thành công và lỗi. Kiểm thử chu kỳ thông báo dùng widget giả lập; chưa kiểm tra trực quan cửa sổ Windows.

Bổ sung kiểm tra tiêu đề và đơn vị được lặp lại khi chia Excel, góc định dạng độ/phút, Cv hằng, hướng dẫn phân biệt mẫu với dòng trung bình và ký hiệu toán học chat. Kiểm tra đọc file Bang THL nen duong LNH.xlsx thực tế: 98 mẫu xuất hiện đúng một lần trong 8 phần; mọi phần có tiêu đề/đơn vị. Đây là kiểm tra chuẩn bị nguồn, chưa gọi dịch vụ AI thật.

Bổ sung ngày 02/10/2026: bảo vệ description/source khỏi kiểm tra số và loại metadata khỏi chỉ tiêu truyền vào Soil; lỗi kiểu dữ liệu từng dòng được yêu cầu AI trả lại một lần và lưu phản hồi gốc kèm nguồn. Worker tách chỉ dẫn trích dữ liệu khỏi hội thoại, bật JSON Schema cho Cloudflare Qwen mặc định/các mô hình text có hỗ trợ, JSON Object cho DeepSeek và MIME JSON cho Gemini. Mô hình Cloudflare Vision/custom chưa xác định hỗ trợ vẫn dùng chỉ dẫn riêng và kiểm tra phản hồi. 11 khẳng định Node về cấu trúc yêu cầu đạt (`node test_worker_extraction.mjs`). Chưa gọi AI thật; cần Deploy worker.js mới và khởi động lại ứng dụng chạy từ mã nguồn hoặc dựng lại EXE để dùng bản sửa.

Bổ sung: nhập một phần số liệu. Một ô/bảng sai không loại các chỉ tiêu hợp lệ của cùng lớp; ghi giá trị gốc và nguồn vào missing/cảnh báo. Giữ kết quả các phần đã đọc được khi phần sau không trả JSON hoặc lỗi dịch vụ. Không có bảng e–logP: bỏ bảng thiếu, dùng e0 cùng Cc/Cs/Pc trong nguồn bằng nhánh tính hiện có; e dạng scalar được hiểu là e0, không tạo đường cong giả. Kiểm thử thực tế bộ tính xác nhận kết quả nhánh thiếu e–logP bằng phương pháp Cc/Cs/Pc và dương; e0 đơn độc vẫn phải bổ sung chỉ tiêu nén trước khi tính. Lỗ khoan thiếu bề dày vẫn hiển thị phần cao độ/các lớp đọc được để sửa, không tính tổng chiều sâu giả.

Bổ sung: Cv không có cấp áp lực dùng giá trị trung bình của các mẫu, lưu dưới dạng Cv hằng; bảng Cv–logP có cấp áp lực giữ nguyên. Đọc c₀/Su/cu từ Excel riêng bằng nút mới, ghép theo mã lớp và giữ riêng nguồn sức kháng; không pha trung bình c₀ mới với chỉ tiêu c₀ cũ. φ′ hữu hiệu CU có nguồn rõ được đổi từ độ sang m=tan(φ′); không dùng góc cắt trực tiếp thay thế. AI đặt Ch/Cv=1, PVD/SD tự dùng 2 ở lớp chưa có số liệu riêng; giá trị nguồn và người nhập được giữ, có trường Ch/Cv trong phạm vi tính AI. Thoát nước thiếu số liệu tạm 1 mặt, cho sửa. Thêm kiểm thử Cv trung bình, ánh xạ Su/c₀, ghép file riêng, trung bình góc CU, nhánh PVD/SD và tự nhập tỷ số. 60 kiểm thử Python và 11 khẳng định Node đạt; chưa thử UI Windows hoặc API thật.

Bổ sung: chọn nhiều file Excel/PDF trong một lượt; trích từng file rồi ghép mẫu cùng mã lớp, bổ sung chỉ tiêu và lấy trung bình số có thật. Giữ kết quả khi một file lỗi. Gửi bảng hướng dẫn quy đổi đơn vị cụ thể cho mọi phần địa chất/sức kháng, gồm γ, pc/co/c, áp lực thí nghiệm, Cv có hệ số 10^n, Mv, độ dài và góc. Yêu cầu đơn vị gốc và phép đổi trong source; chưa rõ đơn vị để null/missing, quy đổi trước khi lấy trung bình. 60 kiểm thử đạt: kiểm tra ghép nhiều nguồn và xác nhận hướng dẫn được gửi ở cả hai chế độ. Chưa kiểm chứng phép đổi do dịch vụ AI thật thực hiện; các phản hồi AI trong kiểm thử được mô phỏng.

Bổ sung cập nhật thí nghiệm: nút AI cập nhật e–P/Cv–P đọc bảng mới theo mã lớp và thay riêng bảng được cung cấp, giữ các chỉ tiêu và lớp khác; Cv–P mới thay Cv hằng. Lưu riêng bản cập nhật để không bị trộn lại với dữ liệu cũ khi lấy trung bình các nguồn sau này. Hủy duyệt đầu vào và kết quả đang tính; cần duyệt lại. Đoạn có lớp được cập nhật e–P dùng phương pháp e–logP hiện có, lớp không có bảng vẫn dùng nhánh e0/Cc hiện có; không thay công thức. Nhận diện e–P/e-P/e=f(P) và Cv–P/Cv-P/C_v–p theo tiêu đề, ký hiệu, đơn vị của phòng thí nghiệm. Giữ giá trị P thực trên trục log; không lấy log hoặc lũy thừa lại khi nhãn đã là áp lực thực. Kiểm thử cập nhật cả hai bảng, cập nhật riêng e, giữ bảng cũ nếu bảng mới sai và ưu tiên dữ liệu mới qua lần lấy trung bình sau đều đạt.

Bổ sung Groq: lựa chọn nhà cung cấp ở mục 1, mục 8 và chat; Worker gọi Groq Chat Completions, chọn mô hình văn bản/ảnh theo dữ liệu, JSON mode khi trích số liệu, thời gian chờ 30 giây, báo lỗi khóa/giới hạn/mô hình và xóa khóa khỏi lỗi. 21 khẳng định Node dùng HTTP mô phỏng đạt (`node test_groq.mjs`), cùng 60 kiểm thử Python và 11 khẳng định Worker trích dữ liệu. Chưa gọi API Groq thật vì chưa có Secret/tài khoản được cấu hình trong môi trường. Kích hoạt theo HUONG_DAN_GROQ.md.

Bổ sung ChatGPT qua OpenAI API: lựa chọn ở chat, mục 1 và mục 8; OPENAI_API_KEY lưu tại Worker; mô hình văn bản/ảnh mặc định gpt-4.1-mini và cho cấu hình; JSON mode khi trích dữ liệu; store=false; báo lỗi khóa/giới hạn/mô hình, che khóa trong thông báo lỗi. 22 khẳng định Node HTTP mô phỏng OpenAI đạt (`node test_openai.mjs`); kiểm tra lại Groq 21, hợp đồng Worker 11 và Python 54 đều đạt. Chưa gọi OpenAI API thật. Kích hoạt theo HUONG_DAN_CHATGPT.md.

Bổ sung Cloudflare/Gemini đọc Excel: hướng dẫn ghép địa chỉ cột với tiêu đề nhiều tầng và các thuật ngữ tiếng Anh, có ví dụ minh họa được đánh dấu không phải dữ liệu nguồn. Cloudflare chia phần hàng 2600 ký tự, giữ tiêu đề/đơn vị mỗi phần và không bỏ hàng rộng; giới hạn sinh khi trích 4096 token, temperature=0, chờ tối đa 60 giây. JSON Schema yêu cầu hiện rõ trường chỉ tiêu core/missing. Chặn Giá trị trung bình/Average/Min/Max bị làm mã lớp. Cả Gemini và Cloudflare yêu cầu đọc lại một lần nếu chỉ trả mã lớp hoặc danh sách rỗng ở phần có ô số; lỗi giữ phản hồi gốc để đối chiếu, các phần đọc được vẫn giữ. Kiểm thử 60 Python đạt, gồm chặn dòng tổng hợp, không mất hàng khi chia nhỏ, kiểm tra hướng dẫn truyền đi và mô phỏng Gemini trả rỗng rồi đọc lại. API thật vẫn chưa kiểm tra được. Bắt đầu Phiên mới để đọc lại các file sau khi cập nhật ứng dụng và Deploy Worker mới.

Bổ sung sắp xếp lớp sau khi AI đọc: bảng địa chất có nút ↑ Lên/↓ Xuống; cửa sổ Sửa lỗ khoan có nút chuyển dòng lớp lên/xuống và lưu thứ tự mới. Di chuyển giữ nguyên toàn bộ chỉ tiêu, bề dày và nguồn của lớp; thay đổi làm hủy duyệt đầu vào để duyệt lại trước khi tính. Kiểm thử bộ tính thật xác nhận thứ tự lớp và bề dày theo lỗ khoan được áp dụng, tổng chiều sâu giữ nguyên; kiểm tra biên danh sách và nguồn dữ liệu đạt. 61 kiểm thử Python và kiểm tra cú pháp Python đạt; chưa kiểm tra trực quan Tkinter trên Windows.

Cập nhật tiếp: hướng dẫn đọc hình trụ CAD/PDF, giải mã TCVN3 và nhóm chữ theo vị trí khung; nút lên/xuống ở cả 5 bước mục 8. Theo yêu cầu mới của người dùng, không chạy kiểm thử cho lần cập nhật này. Các kết quả kiểm thử phía trên chỉ áp dụng cho bản trước lần sửa này.

Bổ sung ghép từng mẫu sức kháng theo tên lỗ và độ sâu CAD, c₀ riêng từng lỗ/tầng, xem/sửa mẫu và cập nhật JSON Schema Worker. Không chạy kiểm thử theo yêu cầu người dùng; chưa gọi API thật.

Bổ sung giảm lag mục 8: nạp bảng theo đợt, gộp tiến độ, giới hạn chữ trạng thái/ô hiển thị, ghi nhớ kết quả ghép mẫu và tra trạng thái bằng chỉ mục. Không chạy kiểm thử hoặc đo hiệu năng Windows theo yêu cầu.

Sửa phân biệt số hiệu UD/DS/SPT với mã lớp, nhắc lại nhóm lớp và yêu cầu đọc lại; chuyển chỉ dẫn dài sang context để tránh lỗi câu hỏi tối đa 2000 ký tự. Không chạy kiểm thử theo yêu cầu đang áp dụng.

Bổ sung đọc dữ liệu chính CAD, cô lập layout, ràng buộc tên theo khung, giữ độ sâu ranh giới, đánh dấu Cần đối chiếu và chặn duyệt dữ liệu thiếu/mâu thuẫn. Không chạy kiểm thử theo yêu cầu.

Bổ sung phạm vi chỉ trích số liệu liên quan đầu vào SoilFirm Pro và lọc trường địa chất ngoài danh sách; giữ nhận dạng mẫu để ghép. Không chạy kiểm thử.

Bổ sung hướng dẫn nhận diện chỉ tiêu BTH theo tên đầy đủ/nhóm thí nghiệm/đơn vị thay vì phụ thuộc ký hiệu; lưu tên và ký hiệu nguồn. Không chạy kiểm thử.

Giới hạn dạng mã lớp số/số kèm một chữ; chuẩn hóa tiền tố Lớp; đối chiếu mã với bằng chứng cột/ô gộp/nhóm Excel theo hàng nguồn. D/TK yêu cầu nguồn xác nhận. Không chạy kiểm thử.

Sửa ΔS: giới hạn Data của từng đoạn đồng bộ vào giới hạn lún tổng/chênh lún ALiCC trước khi kiểm tra đầu vào và tính, không yêu cầu nhập lại khi đã có nguồn Data. Nút AI tính hàng loạt dùng các phương án đã chọn theo ưu tiên và bộ tối ưu CDM/PVD/SD cùng phạm vi AI đã lưu. Không chạy kiểm thử theo yêu cầu.

Bổ sung hai nút thủ công/AI hàng loạt riêng. AI hỏi giải pháp ưu tiên sau khi nhận Excel, tối ưu theo thứ tự và chọn PA đầu tiên đạt; đoạn đã đạt trước xử lý không cần PA. Hồ sơ tổng hợp theo STT, thêm Ho_so_tung_doan/STT_XXXX.pdf và .json chứa trước xử lý rồi phương án đã chọn. JSON theo định dạng soilfirm_batch mở lại được trong ứng dụng. Không chạy kiểm thử theo yêu cầu.

Sửa nút AI hàng loạt mở trợ lý AI thực: nhận Data, hỏi chọn/sắp tối đa 5 ưu tiên, gửi yêu cầu tới nhà cung cấp AI đang chọn và chỉ chạy khi kế hoạch batch khớp STT/ưu tiên người dùng. Công thức/bộ tính và nút Tính thủ công hàng loạt được giữ nguyên. Kết quả/PDF/JSON vẫn từ bộ tính thật. Không chạy kiểm thử theo yêu cầu.


## 2026-10-02 — AI mục 1: tiến trình và bảng kết quả
- Thêm thanh chạy và trạng thái ở mục 1, đồng bộ cửa sổ AI khi đọc Excel, lập kế hoạch, tính từng STT và xuất PDF/JSON. Đọc Excel chạy nền, tránh khóa giao diện.
- Dùng STT/thứ tự ưu tiên đã được người dùng duyệt làm yêu cầu công cụ có cấu trúc; câu trả lời diễn giải của nhà cung cấp không làm mất lệnh tính hoặc thay đổi lựa chọn. AI không tự tính bằng lời, bộ tính SoilFirm Pro thực hiện phép tính.
- Truyền tiến trình thực của run_batch tới AI. Bảng hiển thị trước xử lý và các lần tính ưu tiên, điều kiện lún, thông số, chi tiết và lỗi dữ liệu thay vì chỉ có giá trị lún.
- Giữ luồng thủ công, các công thức tính hiện có.
- Kiểm tra: compileall các nguồn đã sửa; unittest 64/64 đạt. Kiểm tra tích hợp chạy bộ tính, giữ giới hạn riêng từng đoạn, thứ tự STT, PDF/JSON thật (PDF trước/sau đúng thứ tự), và bảng kết quả. Dữ liệu tích hợp dùng mẫu địa chất và mô phỏng bước nạp phân đoạn.
- Chưa kiểm tra GUI trên Windows và kết nối nhà cung cấp AI thật do môi trường không có màn hình/khóa API.


## 2026-10-02 — Tăng tốc đọc Excel AI
- Trước khi gửi AI, bỏ các cột có tên chỉ tiêu xác định chắc chắn không dùng (thành phần hạt, W/WL/WP, tỷ trọng hạt, dung trọng khô, v.v.). Giữ cột chưa rõ tên, mã lớp, lỗ khoan, số mẫu, độ sâu, mô tả và địa chỉ ô; không bỏ hàng dữ liệu. Giữ tiêu đề và đơn vị của cột còn lại.
- Excel đọc tối đa 2 phần song song với Cloudflare, 3 phần với các trợ lý khác; ghép kết quả theo thứ tự nguồn ban đầu. Giữ nguyên chuẩn hóa, quy đổi và trung bình theo lớp. PDF/CAD giữ 1 phần/lần.
- Lưu tối đa 8 kết quả đọc hoàn tất trong bộ nhớ phiên làm việc. Khóa dựa trên nội dung file, chế độ đọc, trợ lý, địa chỉ dịch vụ và tài khoản; file đổi thì đọc lại, dữ liệu trả về là bản sao. Không lưu khóa truy cập trong kết quả đọc. Không cache phản hồi lỗi dịch vụ.
- Dừng xử lý không phải đợi yêu cầu mạng kết thúc; các tác vụ đã gửi có thể hoàn tất ở nền, không áp dụng kết quả sau khi dừng.
- Đo file Bang THL nen duong LNH.xlsx: 27 -> 15 phần (Cloudflare), văn bản tài liệu 188185 -> 69912 ký tự (giảm 62,85%). Đối chiếu giữ đủ địa chỉ hàng có bằng chứng mã lớp. Đây là đo chuẩn bị tài liệu; chưa đo thời gian nhà cung cấp AI thật.
- compileall đạt; unittest 68/68 đạt, gồm giữ số liệu/cột chưa rõ, xử lý song song có thứ tự, cache bản sao, tự đọc lại khi sửa file, dừng xử lý và các kiểm tra bộ tính/PDF trước đó.


## 2026-10-02 — NVIDIA AI
Thêm NVIDIA AI vào các danh sách trợ lý, chat/công cụ tính và đọc dữ liệu mục 8. Worker gọi NVIDIA hosted chat completions với mô hình Nemotron Omni trong ảnh, hỗ trợ nội dung ảnh, timeout và giới hạn reasoning. API key chỉ nằm trong Secret máy chủ.
Kiểm tra compileall đạt; Python 68/68 đạt; kiểm tra Node OpenAI/NVIDIA, Groq và hợp đồng trích số liệu đạt (HTTP giả lập). Kiểm tra yêu cầu text/ảnh, override model, không chuyển khóa đăng nhập người dùng vào NVIDIA, che key trong thông báo lỗi, 401/429/timeout, loại trace suy nghĩ và nhận diện phản hồi cắt. Chưa gọi NVIDIA thật do chưa có API key; Worker cần Deploy mã mới và cấu hình NVIDIA_API_KEY.


### 2026-10-02 — NVIDIA quá tải 503/429
Thêm thử lại tối đa 3 lần cho HTTP 429 và 503 (bao gồm ResourceExhausted). Chờ 15 rồi 30 giây, tôn trọng Retry-After nếu có; thời gian tổng tối đa 120 giây. Không thử lại lỗi key/401 hoặc đầu vào sai. NVIDIA đọc Excel từng phần (1 yêu cầu cùng lúc), các AI khác giữ cấu hình song song. Client chờ tối đa 135 giây để không ngắt trước Worker. Nếu vẫn quá tải, báo rõ sau các lần thử; không tự chuyển AI hoặc tạo kết quả. Không chạy kiểm thử theo yêu cầu người dùng. Deploy worker.js mới để áp dụng xử lý máy chủ.


### 2026-10-02 — CAD lỗ khoan thiếu/lặp địa tầng
Nhận diện bộ cột Tên lớp/Cao độ/Độ sâu/Bề dày và lấy giá trị text đúng cột; hiệu chỉnh vị trí chèn chữ theo cột mã lớp, không dùng khoảng cách bản vẽ làm số khảo sát. Chỉ áp dụng đọc trực tiếp khi khung có tên rõ, đầy đủ các cột, cao độ/chiều sâu từ nhãn đầu khung và địa tầng đã qua đối chiếu ranh giới/tổng bề dày. Khung không chắc chắn vẫn chuyển AI, kèm số gốc đọc được. Nếu AI trả địa tầng thiếu/mâu thuẫn, yêu cầu đọc lại một lần, sau đó giữ kết quả thiếu để người dùng đối chiếu; không bịa số hoặc điền 0. Ghép tờ tiếp nối cùng tên khi có khoảng độ sâu rõ, loại bản sao cùng khoảng, giữ cùng mã ở khoảng khác; mâu thuẫn giữ riêng để đối chiếu. Bổ sung giải mã TCVN3 các từ mô tả đất, kiểm tra tổng bề dày cả vượt và thiếu chiều sâu. Đổi khóa bộ nhớ đọc để tránh dùng lại kết quả cũ. Không chạy kiểm thử theo yêu cầu; chưa gọi AI thật.


### 2026-10-03 — LK.dxf: nhãn tên bên phải khung
Nguồn LK.dxf có tên đầu khung KM31-1P, KM31-1T, KM31-2, KM31-3; còn KM29-T21/T23/T24 thuộc dòng khác, không thay tên lỗ ở nhãn Hình trụ lỗ khoan. Lỗi chia khung cũ giả định nhãn ở bên trái nên cắt mất địa tầng phía trái. Bổ sung đọc đoạn biên ngang LINE/POLYLINE (kể cả INSERT), lấy biên khung chứa nhãn tên gần mép trên để xác định vùng chữ; không suy độ sâu từ khoảng cách CAD. Khi có biên rõ, lấy cả các cột bên trái và bên phải nhãn; giữ tên ghi cùng hàng nhãn, không lấy tên dự án/ghi chú ở hàng dưới. Đổi khóa bộ nhớ để không dùng lại kết quả đọc lỗi. Không chạy kiểm thử theo yêu cầu.


### 2026-10-03 — AI thực sự đọc/tìm dữ liệu CAD
Bỏ trả kết quả đọc cột CAD trực tiếp và bỏ dùng cache khi người dùng yêu cầu đọc lỗ khoan. Luồng gửi text vị trí đầy đủ trong khung, tên xác định từ nhãn và số gốc đối chiếu tới nhà cung cấp AI đã chọn. Bổ sung hướng dẫn tìm nhãn/cột, ghép theo vị trí, phân biệt mã lỗ/dự án, UD/địa tầng, rà đủ tầng và kiểm tra tổng bề dày. AI phải trả JSON số liệu qua API; phần mềm không thay phản hồi AI bằng kết quả đọc cục bộ. So sánh cao độ, chiều sâu, số tầng, mã và bề dày với cột CAD đã xác định đủ; thiếu/sai thì yêu cầu AI đọc lại một lần, sau đó đánh dấu để người dùng sửa và không duyệt dữ liệu mâu thuẫn. Hướng dẫn đưa vào context mỗi lần gọi, không phải huấn luyện lại trọng số mô hình. Không chạy kiểm thử theo yêu cầu người dùng.


Cập nhật BTH đa mẫu: tiêu đề nhiều tầng/bilingual/Unicode tổ hợp; giữ dòng trung bình cho chỉ tiêu thiếu; e₀tb và Cvtb khi thiếu đường cong; lọc cột không liên quan và tránh gửi bảng trùng hoàn toàn. Chưa chạy kiểm tra theo yêu cầu người dùng. DWG mới chỉ nhận diện định dạng, chưa xác minh nội dung do cần chuyển đổi ODA.
