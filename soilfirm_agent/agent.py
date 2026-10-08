import json

DATA_TOOLS = {'read_file', 'read_document', 'extract_geotech', 'lookup_records', 'run_table_python'}
HELP_MARKER = 'Bạn chỉ giúp tên sheet và hàng, cột hoặc địa chỉ ô'

def meaningful(value):
    if value is None: return False
    if isinstance(value, str): return bool(value.strip())
    if isinstance(value, (list, tuple)): return any(meaningful(v) for v in value)
    if isinstance(value, dict): return any(meaningful(v) for v in value.values())
    return True  # Zero and False are valid values.

def empty_answer(text):
    if not isinstance(text, str) or not text.strip(): return True
    try: return not meaningful(json.loads(text))
    except (ValueError, TypeError): return False

def missing_result(name, result):
    if not isinstance(result, dict) or result.get('ok') is False: return True
    if name not in DATA_TOOLS: return False
    value = result.get('result')
    if not meaningful(value): return True
    if not isinstance(value, dict): return False
    if value.get('status') == 'not_found' or value.get('count') == 0: return True
    records = value.get('records', value.get('preview'))
    if isinstance(records, list):
        return not records or any(not meaningful(r.get('values')) or any(not meaningful(v) for v in r.get('values',{}).values()) for r in records if isinstance(r, dict))
    if 'rows' in value:
        if any(meaningful(p.get('text')) for p in value.get('pages',[]) if isinstance(p,dict)): return False
        return not value['rows'] or not any(meaningful(c.get('value')) for row in value['rows'] for c in (row.get('cells', []) if isinstance(row, dict) else row) if isinstance(c, dict))
    return False

class SoilFirmAgent:
    def __init__(self, provider, tools, max_steps=8, max_calls=16, max_result_chars=30000, allow_missing=False, document_reading=False):
        self.provider=provider; self.tools=tools; self.max_steps=max_steps; self.max_calls=max_calls
        self.max_result_chars=max(2000,max_result_chars); self.allow_missing=allow_missing
        self.document_reading=document_reading

    def run(self, question):
        if not isinstance(question,str) or not question.strip() or len(question)>20000: raise ValueError('Invalid question')
        self.provider.user(question)
        trace=[]; count=0; retries=0; unresolved=False; failed=set(); pending_tools=set()
        reading=self.document_reading
        def service_error(code):
            explanations={
                'connection':'Không kết nối được dịch vụ AI.',
                'context':'Mô hình AI chưa hoàn tất phản hồi hoặc đã đầy ngữ cảnh.',
                'http':'Dịch vụ AI báo lỗi HTTP; cần kiểm tra mô hình, khóa API hoặc hạn mức.',
                'format':'Mô hình chưa trả được phản hồi đúng định dạng sau các lần thử.',
                'incomplete':'Dịch vụ AI chưa hoàn tất phản hồi.'}
            return {'answer':explanations[code]+' Câu hỏi của bạn chưa được xử lý xong. Hãy thử lại; nếu còn lỗi, kiểm tra trạng thái dịch vụ AI. Đây là lỗi xử lý phản hồi, chưa có căn cứ để kết luận tài liệu thiếu số liệu.', 'tools':trace,'complete':False,'status':'provider_error','error_code':code}
        def fallback(reason):
            if not reading:
                return {'answer':'Tôi chưa hoàn tất câu trả lời cho yêu cầu của bạn. '+reason+' Nếu đang tra cứu tiêu chuẩn, hãy cho biết mã đầy đủ hoặc tên tiêu chuẩn để xác định đúng nguồn. Chưa có đủ căn cứ để đưa ra kết luận.', 'tools':trace,'complete':False,'status':'incomplete'}
            if self.allow_missing:
                answer='Đã bỏ qua yêu cầu bổ sung vị trí theo lựa chọn của bạn. Chỉ tiêu chưa xác định được từ tài liệu được để trống (null), không điền 0 hoặc đoán số.'
                return {'answer':answer,'tools':trace,'complete':False,'status':'missing_allowed','missing_value':None}
            subject='độ sâu mẫu' if any(s in question.lower() for s in ('độ sâu','depth')) else 'số liệu cần đọc'
            answer='Tôi chưa xác định được '+subject+' từ tài liệu. '+HELP_MARKER+' trong Excel để tôi đọc lại nhé. Với PDF, hãy chỉ trang và vị trí bảng. '+reason+' Bạn có thể trả lời “bỏ qua” nếu không có thông tin; khi đó chỉ tiêu thiếu mới được để trống.'
            return {'answer':answer,'tools':trace,'complete':False,'status':'awaiting_user','follow_up_question':HELP_MARKER+' trong Excel để tôi đọc lại nhé.'}
        for step in range(self.max_steps):
            self.tools.check_cancel()
            if self.tools.progress: self.tools.progress('Agent: bước '+str(step+1))
            try: text,calls=self.provider.step(self.tools.definitions)
            except (ValueError, json.JSONDecodeError):
                if retries>=2: return service_error('format')
                retries+=1; self.provider.user('Phản hồi vừa rồi không hợp lệ. Hãy trả lời hoặc gọi công cụ đúng định dạng, không trả nội dung rỗng.'); continue
            except RuntimeError as exc:
                message=str(exc).lower()
                code='connection' if 'connection' in message else 'context' if 'context full' in message else 'http' if 'http' in message else 'incomplete'
                return service_error(code)
            if not calls:
                if not empty_answer(text) and not unresolved:
                    return {'answer':text,'tools':trace,'complete':True}
                if retries>=2: return fallback('Các lần thử chưa cung cấp đủ thông tin có nguồn.')
                retries+=1
                if reading:
                    self.provider.user('Chưa được kết thúc bằng kết quả rỗng hoặc số tự đoán. Hãy thử cách đọc khác: đổi vùng/sheet, kiểm tra tiêu đề nhiều hàng, ô gộp hoặc cách đọc PDF; dùng công cụ được cấp quyền. Nếu vẫn thiếu, hỏi người dùng tên sheet, hàng, cột hoặc địa chỉ ô. Chỉ được để chỉ tiêu thiếu trống sau khi người dùng bỏ qua yêu cầu bổ sung vị trí.')
                else:
                    self.provider.user('Hãy trả lời đúng yêu cầu ban đầu bằng thông tin có căn cứ. Nếu cần thông tin cập nhật, gọi web_search rồi read_source và tổng hợp nội dung kèm nguồn. Nếu công cụ lỗi, nêu hạn chế đó; nếu mã tiêu chuẩn chưa rõ, hỏi mã đầy đủ hoặc tên tiêu chuẩn. Không hỏi vị trí ô Excel khi không đọc số liệu từ tệp.')
                continue
            if len(calls)>4 or count+len(calls)>self.max_calls: return fallback('Đã đạt giới hạn thao tác của lượt này.')
            results=[]
            for call in calls:
                if call.name in DATA_TOOLS: reading=True
                key=call.name+json.dumps(call.arguments,sort_keys=True,ensure_ascii=False,default=str)
                if key in failed:
                    result={'ok':False,'error':'RepeatedEmptyRequest','message':'Yêu cầu này đã thất bại hoặc thiếu số liệu. Đổi vùng, sheet, bộ lọc hoặc cách đọc.'}
                else: result=self.tools.call(call.name,call.arguments)
                count+=1
                problem=missing_result(call.name,result)
                if problem:
                    failed.add(key); pending_tools.add(call.name); unresolved=True
                    note='Thử cách đọc khác. Nếu vẫn thiếu, hỏi người dùng vị trí; chưa được xuất số liệu thiếu thành kết quả hoàn chỉnh.' if call.name in DATA_TOOLS else 'Công cụ chưa cung cấp kết quả. Thử cách khác phù hợp với yêu cầu và nêu hạn chế nếu vẫn lỗi; không hỏi ô Excel cho yêu cầu tra mạng.'
                    result={**result,'recovery_required':True,'note':note}
                else:
                    pending_tools.discard(call.name)
                    unresolved=bool(pending_tools)
                raw=json.dumps(result,ensure_ascii=False,default=str,allow_nan=False)
                if len(raw)>self.max_result_chars:
                    result={'ok':result.get('ok',False),'truncated':True,'excerpt':raw[:self.max_result_chars-1000],'recovery_required':problem,'note':'Đọc vùng nhỏ hơn để lấy dữ liệu đầy đủ.'}
                results.append((call,result)); trace.append({'name':call.name,'ok':result.get('ok',False),'missing':problem})
            self.provider.results(results)
        return fallback('Đã đạt giới hạn bước của lượt này.')
