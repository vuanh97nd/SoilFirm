"""Đồng bộ bộ nhớ chung với Worker. Chỉ gọi trong luồng nền, không ghi ô đất."""
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from geotech_memory import GeotechMemory,packed,digest,structure_signature


def _mapping_payload(payload,registry):
    from mapping_gate import strict_json
    if set(payload)!={'signature','registry_hash','columns','answer','overrides'}:raise ValueError('Sai schema quy tắc chung.')
    if payload['registry_hash']!=digest(registry):return False
    columns=payload['columns'];ids=set()
    for col in columns:
        if set(col)!={'cot_id','label','symbol','unit','group'} or type(col['cot_id']) is not int or col['cot_id']<1 or col['cot_id'] in ids:raise ValueError('Cột bộ nhớ chung không hợp lệ.')
        ids.add(col['cot_id'])
        if any(not isinstance(col[k],str) or len(col[k])>600 for k in ('label','symbol','unit','group')):raise ValueError('Metadata cột sai.')
    if structure_signature(columns,registry)!=payload['signature']:raise ValueError('Chữ ký bộ nhớ chung không khớp cấu trúc/đơn vị.')
    proposal=strict_json(packed(payload['answer']));seen=set();targets=set()
    for item in proposal['items']:
        cid,target=item['cot_id'],item['thong_so']
        if cid not in ids or cid in seen or target not in registry and target!='unknown':raise ValueError('Ánh xạ chung ngoài sổ thông số.')
        seen.add(cid)
        if target!='unknown':
            column=next(c for c in columns if c['cot_id']==cid);spec=registry[target]
            if spec['type']!='text' and column['unit'] not in spec['units']:raise ValueError('Quy tắc chung suy đơn vị còn thiếu.')
            if spec.get('groups') and column['group'] not in spec['groups']:raise ValueError('Quy tắc chung nhầm nhóm thí nghiệm.')

            if target in targets:raise ValueError('Ánh xạ chung trùng đích.')
            targets.add(target)
    if any(cid not in ids for cid in proposal['khong_chac']):raise ValueError('Cột chưa xác định không tồn tại.')
    for cid,override in payload['overrides'].items():
        if int(cid) not in ids or set(override)-{'unit','group'} or any(not isinstance(v,str) for v in override.values()):raise ValueError('Hiệu chỉnh chung không hợp lệ.')
        col=next(c for c in columns if c['cot_id']==int(cid))
        if any(v!=col[k] for k,v in override.items()):raise ValueError('Quy tắc chung không được suy đơn vị hoặc nhóm riêng.')
    return True


def shared_request(base_url,credentials,route,body,post=None):
    parsed=urlsplit(base_url)
    if parsed.scheme!='https' or not parsed.netloc or parsed.username or parsed.password:raise ValueError('Máy chủ bộ nhớ phải dùng HTTPS.')
    if post is None:
        import requests
        post=requests.post
    try:
        from requests.exceptions import Timeout,ConnectionError as RequestConnectionError
    except ImportError:
        # Injected transports can use stdlib network exceptions in headless tests.
        Timeout=TimeoutError;RequestConnectionError=ConnectionError
    # Sync uses content hashes/client ids; pending is read-only. Review is not retried.
    attempts=2 if route in ('/api/memory/shared/sync','/api/memory/shared/pending') else 1
    for attempt in range(attempts):
        try:
            response=post(base_url.rstrip('/')+route,json={**credentials,**body},timeout=(5,30),allow_redirects=False)
            break
        except (Timeout,RequestConnectionError) as exc:
            if attempt+1==attempts:
                raise ValueError('Không kết nối hoặc chưa nhận được phản hồi bộ nhớ sau '+str(attempts)+' lần thử; thời hạn chờ phản hồi mỗi lần là 30 giây. Thử Đồng bộ lại khi kết nối ổn định.') from exc
    if len(response.content)>3500000:raise ValueError('Phản hồi bộ nhớ quá lớn.')
    try:result=response.json()
    except ValueError:result=None
    if not response.ok:
        message=str(result.get('message') or result.get('error') or '') if isinstance(result,dict) else ''
        key=str(credentials.get('key') or '')
        if key:message=message.replace(key,'[KEY]')
        reason='Máy chủ bộ nhớ HTTP '+str(response.status_code)+(': '+message[:600] if message else '.')
        if response.status_code in (401,403):raise PermissionError(reason)
        raise ValueError(reason)
    if not isinstance(result,dict) or result.get('success') is not True:raise ValueError('Phản hồi bộ nhớ không hợp lệ.')
    return result


def sync_shared_memory(base_url,credentials,scope,eligible,*,post=None,path=None,max_pages=1,outbox_ids=None):
    """Mất mạng giữ hàng đợi và cache; trial không gọi máy chủ, không dùng cache chung."""
    memory=GeotechMemory(path);account=str(credentials.get('username') or '')
    memory.set_shared_access(scope,bool(eligible and account),account)
    if not eligible or not account:return {'success':False,'message':'Tài khoản dùng thử không được dùng bộ nhớ chung.'}
    registry=json.loads(Path(__file__).with_name('parameter_registry.json').read_text(encoding='utf-8'))
    registry_hash=digest(registry);updated=0;sent=0
    try:
        if outbox_ids is None:queue_bth_reading_reference(memory,account)
        for _ in range(max(1,min(5,max_pages))):
            with memory.connection() as db:
                state=db.execute("SELECT value FROM shared_memory_state WHERE key='cursor'").fetchone()
                version=db.execute("SELECT value FROM shared_memory_state WHERE key='registry_hash'").fetchone()
                reset=not version or version[0]!=registry_hash;cursor=0 if reset else int(state[0]) if state else 0
                if outbox_ids is None:
                    pending=db.execute('SELECT id,kind,payload FROM shared_memory_outbox WHERE account=? ORDER BY created_at LIMIT 20',(account,)).fetchall()
                elif outbox_ids:
                    marks=','.join('?' for _ in outbox_ids)
                    pending=db.execute(f'SELECT id,kind,payload FROM shared_memory_outbox WHERE account=? AND id IN ({marks}) ORDER BY created_at LIMIT 20',(account,*outbox_ids)).fetchall()
                else:pending=[]
            batch=[];size=0
            for row in pending:
                item={'client_id':row['id'],'kind':row['kind'],'payload':json.loads(row['payload'])};encoded=packed(item)
                if size+len(encoded)>450000:break
                batch.append(item);size+=len(encoded)
            result=shared_request(base_url,credentials,'/api/memory/shared/sync',{'cursor':cursor,'items':batch},post)
            if set(result)!={'success','ack','changes','cursor','more'}:raise ValueError('Sai schema đồng bộ bộ nhớ.')
            ack=result['ack'];changes=result['changes'];new_cursor=result['cursor']
            if not isinstance(ack,list) or len(set(ack))!=len(ack) or any(x not in {b['client_id'] for b in batch} for x in ack):raise ValueError('Máy chủ xác nhận sai lô gửi.')
            if not isinstance(changes,list) or type(new_cursor) is not int or new_cursor<cursor or type(result['more']) is not bool:raise ValueError('Vị trí đồng bộ không hợp lệ.')
            accepted=[];previous=cursor
            for item in changes:
                if set(item)!={'seq','item_id','kind','state','payload','reviewer','created_at'}:raise ValueError('Sai schema bản ghi máy chủ.')
                if type(item['seq']) is not int or item['seq']<=previous or item['state'] not in ('approved','disabled','rejected') or not isinstance(item['reviewer'],str) or not item['reviewer']:raise ValueError('Nhật ký công bố không hợp lệ.')
                previous=item['seq']
                if not isinstance(item['item_id'],str) or len(item['item_id'])!=64 or any(c not in '0123456789abcdef' for c in item['item_id']):raise ValueError('Mã bản ghi không hợp lệ.')
                payload=item['payload'];kind=item['kind']
                if kind=='mapping':supported=_mapping_payload(payload,registry)
                elif kind=='knowledge':
                    supported=True
                    if set(payload)!={'topic','title','body','source'} or any(not isinstance(v,str) for v in payload.values()) or not payload['source'].strip() or len(payload['body'])>12000:raise ValueError('Kiến thức chung sai schema.')
                else:raise ValueError('Loại bộ nhớ lạ.')
                accepted.append((item,supported))
            if new_cursor!=previous:raise ValueError('Máy chủ trả con trỏ không khớp nhật ký.')
            # Nhận toàn lô hoặc giữ nguyên: không xóa hàng đợi nếu phản hồi lỗi.
            with memory.connection() as db:
                if reset:db.execute('DELETE FROM shared_memory_cache')
                for item,supported in accepted:
                    db.execute('DELETE FROM shared_memory_cache WHERE id=?',(item['item_id'],))
                    if item['state']=='approved' and supported:
                        db.execute('INSERT INTO shared_memory_cache(id,kind,payload,reviewer,seq) VALUES(?,?,?,?,?)',(item['item_id'],item['kind'],packed(item['payload']),item['reviewer'],item['seq']))
                for ident in ack:db.execute('DELETE FROM shared_memory_outbox WHERE id=? AND account=?',(ident,account))
                db.execute("INSERT OR REPLACE INTO shared_memory_state VALUES('cursor',?)",(str(new_cursor),))
                db.execute("INSERT OR REPLACE INTO shared_memory_state VALUES('registry_hash',?)",(registry_hash,))
            updated+=len(changes);sent+=len(ack)
            with memory.connection() as db:
                remaining=db.execute('SELECT count(*) FROM shared_memory_outbox WHERE account=?',(account,)).fetchone()[0] if outbox_ids is None else sum(db.execute('SELECT 1 FROM shared_memory_outbox WHERE account=? AND id=?',(account,ident)).fetchone() is not None for ident in outbox_ids)
            if batch and not ack:
                return {'success':False,'message':'Máy chủ chưa xác nhận lô gửi; còn '+str(remaining)+' mục chờ gửi, hàng đợi được giữ.','updated':updated,'submitted':sent,'remaining':remaining}
            # Server more describes published changes, not the local upload queue.
            if not result['more'] and not remaining:break
        with memory.connection() as db:
            remaining=db.execute('SELECT count(*) FROM shared_memory_outbox WHERE account=?',(account,)).fetchone()[0] if outbox_ids is None else sum(db.execute('SELECT 1 FROM shared_memory_outbox WHERE account=? AND id=?',(account,ident)).fetchone() is not None for ident in outbox_ids)
        message='Đã đồng bộ: gửi '+str(sent)+' mục, nhận '+str(updated)+' thay đổi.'
        message+=(' Còn '+str(remaining)+' mục chờ gửi; bấm Đồng bộ để tiếp tục.' if remaining else ' Không còn mục chờ gửi trên máy này.')
        message+=' Bộ nhớ Admin được server cập nhật tự động sau khi kiểm tra cấu trúc/đơn vị.'
        return {'success':True,'message':message,'updated':updated,'submitted':sent,'remaining':remaining}
    except PermissionError as exc:
        memory.set_shared_access(scope,False,account);return {'success':False,'message':str(exc)}
    except Exception as exc:
        # Lỗi mạng/schema không làm mất bộ nhớ và các đề xuất đang chờ gửi.
        return {'success':False,'message':'Chưa đồng bộ: '+str(exc)+' Bộ nhớ cục bộ và hàng đợi được giữ.'}

# Một lần đồng bộ mỗi cơ sở dữ liệu, tránh chat và đọc Excel ghi đè con trỏ nhau.
import threading
_SYNC_LOCKS={}
_SYNC_GUARD=threading.Lock()
_sync_impl=sync_shared_memory

def sync_shared_memory(base_url,credentials,scope,eligible,*,post=None,path=None,max_pages=1,outbox_ids=None):
    memory=GeotechMemory(path)
    memory.set_shared_access(scope,bool(eligible and credentials.get('username')),str(credentials.get('username') or ''))
    if not eligible:return {'success':False,'message':'Tài khoản dùng thử không được dùng bộ nhớ chung.'}
    with _SYNC_GUARD:lock=_SYNC_LOCKS.setdefault(str(memory.path.resolve()),threading.Lock())
    if not lock.acquire(blocking=False):return {'success':False,'message':'Đang đồng bộ trong tác vụ khác; dùng bộ nhớ đã lưu.'}
    try:return _sync_impl(base_url,credentials,scope,eligible,post=post,path=path,max_pages=max_pages,outbox_ids=outbox_ids)
    finally:lock.release()


def queue_template_references(memory,account):
    """Nạp metadata mẫu thành đề xuất kiến thức chung, không phải quy tắc đoán số."""
    seed=Path(__file__).with_name('shared_memory_seed.json')
    if seed.is_file():
        return queue_shared_seed(memory,account,seed)
    catalog=json.loads(Path(__file__).with_name('geotech_template_catalog.json').read_text(encoding='utf-8'))
    added=0
    with memory.connection() as db:
        for entry in catalog['templates']:
            labels=[{'label':c['label'],'unit':c.get('unit',''),'group':c.get('group',''),
                     'candidate_id':c.get('candidate_id','unknown')} for c in entry['columns']
                    if c.get('candidate_id') or 'cv' in c['label'].lower() or 'su' in c['label'].lower()]
            if not labels:continue
            body='Chỉ tham khảo cách đặt tiêu đề. Không suy đơn vị còn thiếu, không tạo số liệu, không coi nhãn gợi ý là ánh xạ đã xác nhận.\n'+packed(labels)
            if len(body)>12000:body=body[:body.index('\n')+1]+packed(labels[:12])
            payload={'topic':'Biểu mẫu Excel','title':entry['file']+' / '+entry['sheet'],
                     'body':body,'source':'Dao tao AI / '+entry['file']+' / '+entry['sheet']+'; SHA-256 '+entry['sha256']}
            before=db.total_changes
            db.execute('INSERT OR IGNORE INTO shared_memory_outbox VALUES(?,?,?,?,datetime(\'now\'))',
                (digest(['knowledge',payload]),account,'knowledge',packed(payload)))
            added+=db.total_changes-before
    return added


def read_shared_seed(path):
    """Kiểm tra cả bộ trước khi ghi hàng đợi. Không chấp nhận seed ánh xạ tự động."""
    import re
    bundle=json.loads(Path(path).read_text(encoding='utf-8'))
    if set(bundle)!={'version','origin','rule','items'} or bundle['version']!=1 or not isinstance(bundle['items'],list):
        raise ValueError('Bộ nhớ nguồn sai cấu trúc.')
    if not all(isinstance(bundle[k],str) for k in ('origin','rule')):raise ValueError('Nguồn bộ nhớ sai kiểu.')
    seen=set();items=[]
    for item in bundle['items']:
        if set(item)!={'id','kind','payload','state'} or item['kind']!='knowledge' or item['state']!='pending':
            raise ValueError('Chỉ nạp kiến thức tham khảo chờ xác nhận.')
        payload=item['payload']
        if not isinstance(payload,dict) or set(payload)!={'topic','title','body','source'}:
            raise ValueError('Nội dung kiến thức sai schema.')
        for key,maximum in [('topic',500),('title',500),('body',12000),('source',500)]:
            if not isinstance(payload[key],str) or not payload[key].strip() or len(payload[key])>maximum:
                raise ValueError('Nội dung kiến thức không hợp lệ: '+key)
        if not re.fullmatch(r'[a-f0-9]{64}',str(item['id'])) or item['id']!=digest(['knowledge',payload]) or item['id'] in seen:
            raise ValueError('Mã hoặc dấu kiểm tra bộ nhớ không khớp.')
        seen.add(item['id']);items.append(item)
    return items


def queue_shared_seed(memory,account,path):
    if not isinstance(account,str) or not account.strip():raise ValueError('Thiếu tài khoản gửi bộ nhớ.')
    items=read_shared_seed(path)
    marker='seed:templates:'+digest([account,[item['id'] for item in items]])
    with memory.connection() as db:
        if db.execute('SELECT value FROM shared_memory_state WHERE key=?',(marker,)).fetchone():return 0
        before=db.total_changes
        db.executemany("INSERT OR IGNORE INTO shared_memory_outbox VALUES(?,?,?,?,datetime('now'))",
            [(digest(['knowledge',item['payload'],account]),account,'knowledge',packed(item['payload'])) for item in items])
        added=db.total_changes-before
        db.execute('INSERT INTO shared_memory_state VALUES(?,?)',(marker,'queued'))
        return added


BTH_READING_REFERENCE = {'topic': 'Đọc BTH', 'title': 'Đọc BTH từng phần: giữ dữ liệu hợp lệ, thiếu để trống', 'body': 'Quy tắc kiểm chứng từ BTH An Thọ: tiêu đề Wet density g (g/cm3) là gamma tự nhiên; Void ratio e là e0. Chỉ đọc số thật trong ô theo đơn vị nguồn. Một nhóm mẫu có mã lớp, mẫu và độ sâu đã xác định nhưng ô chỉ tiêu trống phải giữ nhận dạng và cảnh báo thiếu, không điền 0, không lấy số mẫu/lớp khác. Khi cấu trúc cột đã xác định, không gọi AI ánh xạ lại nhóm không có số đo. Không hủy các mẫu hợp lệ ở phần khác vì nhóm trống này. Nhãn lạ mới yêu cầu AI ánh xạ, không dùng quy tắc này làm dự phòng sau lỗi AI. Phản hồi AI rỗng/sai hoặc không có số liệu mới phải thông báo rõ tên file/sheet và nguyên nhân. Không coi bảng nhận dạng không có chỉ tiêu là đủ đầu vào tính. Kiến thức chỉ giải nghĩa cấu trúc, không thay cổng kiểm tra đơn vị/điều kiện tính. Đọc từng phần độc lập: có ít nhất một chỉ tiêu đã xác định thì trả chỉ tiêu đó; phần chưa đọc được để trống và nêu nguồn/lý do. Một phần AI sai schema hoặc lỗi không được làm mất phần hợp lệ trước/sau nó. Không trích số từ phản hồi AI sai schema để cứu kết quả. Lỗi đọc bổ sung không xóa các mẫu đã đọc hợp lệ. Kết quả chưa đầy đủ không được ghi cache hay đánh dấu nguồn đã đọc đầy đủ.', 'source': 'My Drive/Dev/Dao tao AI/An tho/5. Bang tong hop - CN An Tho.xlsx; sheet BTH (pl); S62/V62/AI62/AJ62 trống; S97/V97/AI97/AJ97 có số; SHA-256 6e249d1520aa64eb946d6f42d1bfbb2af17d9057104b794745f4399638e4dd2f; kiểm thử 2026-10-05; đối chiếu thêm TH DY tuyen chinh- A2z khoan mới.xlsx / TH (2), X16 và AB16; ca giữ kết quả khi AI sai schema 2026-10-05'}

def queue_bth_reading_reference(memory,account):
    """Queue verified reading guidance once per account; server still reviews it."""
    if not account:return 0
    payload=BTH_READING_REFERENCE
    ident=digest(['knowledge',payload,account]);marker='seed:bth_reference:'+ident
    with memory.connection() as db:
        if db.execute('SELECT value FROM shared_memory_state WHERE key=?',(marker,)).fetchone():return 0
        db.execute("INSERT OR IGNORE INTO shared_memory_outbox VALUES(?,?,?,?,datetime('now'))",
                   (ident,account,'knowledge',packed(payload)))
        db.execute('INSERT INTO shared_memory_state VALUES(?,?)',(marker,'queued'))
        return 1


def upload_all_template_references(base_url,credentials,scope,eligible,*,post=None,path=None,progress=None,cancel=None,pause=None,max_batches=None):
    """Upload the whole reference queue on a worker; count only server ACKs."""
    import time
    if pause is None:pause=time.sleep
    if max_batches is not None and (type(max_batches) is not int or max_batches<1):raise ValueError('Số lô phải là số nguyên dương.')
    account=str(credentials.get('username') or '')
    if not eligible or not account:return {'success':False,'message':'Tài khoản chưa đủ quyền gửi biểu mẫu.'}
    memory=GeotechMemory(path)
    if cancel and cancel():return {'success':False,'message':'Đã dừng trước khi nạp biểu mẫu.'}
    added=queue_template_references(memory,account)
    def remaining():
        with memory.connection() as db:return db.execute('SELECT count(*) FROM shared_memory_outbox WHERE account=?',(account,)).fetchone()[0]
    sent=updated=batches=0;total=remaining();rate_retries=0
    if progress:progress('Đã nạp '+str(added)+' mục vào hàng đợi; chuẩn bị gửi toàn bộ '+str(total)+' mục.')
    while True:
        if cancel and cancel():
            return {'success':False,'submitted':sent,'remaining':remaining(),'message':'Đã dừng; server xác nhận '+str(sent)+' mục, phần chưa gửi giữ trong hàng đợi.'}
        result=sync_shared_memory(base_url,credentials,scope,eligible,post=post,path=path,max_pages=1)
        sent+=result.get('submitted',0);updated+=result.get('updated',0);left=remaining();total=max(total,sent+left)
        if progress:progress('Server đã xác nhận '+str(sent)+'/'+str(total)+' mục; còn '+str(left)+' chờ gửi.')
        if not result.get('success'):
            message=result.get('message','Không gửi được lô biểu mẫu.')
            if 'HTTP 429' in message and rate_retries<2:
                rate_retries+=1
                if progress:progress('Server giới hạn tốc độ; giữ hàng đợi và chờ 30 giây rồi gửi tiếp.')
                pause(30);continue
            return {**result,'submitted':sent,'remaining':left,'message':'Chưa gửi hết: server xác nhận '+str(sent)+' mục, còn '+str(left)+' chờ gửi. '+message}
        rate_retries=0;batches+=1
        if not left:
            return {'success':True,'submitted':sent,'updated':updated,'remaining':0,'message':'Đã gửi hết biểu mẫu: server xác nhận '+str(sent)+' mục; không còn mục chờ gửi. Bộ nhớ Admin được cập nhật tự động.'}
        if not result.get('submitted'):
            return {'success':False,'submitted':sent,'remaining':left,'message':'Server chưa xác nhận thêm; còn '+str(left)+' mục, giữ hàng đợi để gửi tiếp.'}
        if max_batches is not None and batches>=max_batches:
            return {'success':True,'submitted':sent,'updated':updated,'remaining':left,'message':'Đã gửi '+str(batches)+' lô: server xác nhận '+str(sent)+' mục; còn '+str(left)+' chờ gửi. Nạp một lô để gửi tiếp hoặc Nạp toàn bộ.'}
        # Worker permits 30 memory requests/minute; avoid bursting 60+ seed batches.
        pause(2.2)


def submit_admin_read_experience(base_url,credentials,scope,eligible,sources,*,role='',path=None,post=None):
    """Share header metadata after a successful admin read; never share sample values."""
    if role!='admin' or not eligible or not credentials.get('username'):
        return {'success':True,'submitted':0,'message':'Không tự chia sẻ kinh nghiệm của tài khoản thường.'}
    memory=GeotechMemory(path);account=str(credentials['username'])
    names={Path(source).name for source in sources}
    ids=[];added=0
    with memory.connection() as db:
        templates=db.execute("SELECT metadata,source FROM templates WHERE scope=? AND signature NOT LIKE 'reference:%'",(scope,)).fetchall()
        for record in templates:
            source=str(record['source'])
            if not any(source==name or source.startswith(name+' / ') for name in names):continue
            columns=json.loads(record['metadata'])
            clean=[{key:column[key] for key in ('cot_id','label','symbol','unit','group') if key in column} for column in columns]
            for offset in range(0,len(clean),12):
                payload={'topic':'Kinh nghiệm đọc tiêu đề Excel','title':'Cấu trúc '+source[:350]+' / '+str(offset//12+1),
                    'body':'Metadata quan sát khi admin đọc file thành công; chỉ tham khảo nhãn và đơn vị, chưa phải ánh xạ đã xác nhận. Không có trị số mẫu; không dùng để điền số liệu dự án khác.\n'+packed(clean[offset:offset+12]),'source':source[:500]}
                if len(payload['body'])>12000:continue
                ident=digest(['knowledge',payload,account]);marker='admin_read:'+ident
                ids.append(ident)
                if db.execute('SELECT 1 FROM shared_memory_state WHERE key=?',(marker,)).fetchone():continue
                db.execute("INSERT OR IGNORE INTO shared_memory_outbox VALUES(?,?,?,?,datetime('now'))",(ident,account,'knowledge',packed(payload)))
                db.execute('INSERT INTO shared_memory_state VALUES(?,?)',(marker,'queued'));added+=1
    if not ids:return {'success':True,'submitted':0,'message':'Chưa có metadata tiêu đề để gửi; không tự tạo kinh nghiệm.'}
    with memory.connection() as db:
        ids=[ident for ident in dict.fromkeys(ids) if db.execute('SELECT 1 FROM shared_memory_outbox WHERE account=? AND id=?',(account,ident)).fetchone()]
    if not ids:return {'success':True,'submitted':0,'message':'Kinh nghiệm biểu mẫu này đã được server xác nhận; không gửi trùng.'}
    result=sync_shared_memory(base_url,credentials,scope,eligible,path=path,post=post,max_pages=5,outbox_ids=tuple(dict.fromkeys(ids)))
    with memory.connection() as db:
        result['remaining']=sum(db.execute('SELECT 1 FROM shared_memory_outbox WHERE account=? AND id=?',(account,ident)).fetchone() is not None for ident in ids)

    result['message']='Kinh nghiệm admin: thêm '+str(added)+' mục. '+result.get('message','')
    return result
