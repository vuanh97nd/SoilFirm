"""Deterministic validation/transaction. No model/UI/AI imports or callbacks."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import date,datetime,time,timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
import unicodedata

LOCK=RLock()
class MappingRejected(ValueError):pass

def json_temporal(value):
    """Preserve Excel temporal metadata without guessing a numerical value."""
    if isinstance(value,(datetime,date,time)):return value.isoformat()
    if isinstance(value,timedelta):return str(value)
    raise TypeError('Object of type '+type(value).__name__+' is not JSON serializable')

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'),default=json_temporal).encode()).hexdigest()

def normalized(text):
    s=unicodedata.normalize('NFKD',str(text)).replace('đ','d').replace('Đ','D')
    return re.sub(r'\s+',' ',''.join(c for c in s if not unicodedata.combining(c)).casefold()).strip()

def strict_json(answer):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise MappingRejected('Khóa JSON trùng: '+k)
            out[k]=v
        return out
    def invalid(value):raise MappingRejected('Số JSON không hữu hạn: '+value)
    try:
        if not isinstance(answer,str):raise MappingRejected('Phản hồi phải là JSON văn bản.')
        value=json.loads(answer,object_pairs_hook=pairs,parse_constant=invalid)
    except (ValueError,TypeError) as exc:raise MappingRejected('JSON không hợp lệ: '+str(exc)) from exc
    if type(value) is not dict or set(value)!={'task','items','khong_chac'} or value['task']!='column_mapping':
        raise MappingRejected('Sai schema ánh xạ; từ chối toàn bộ phản hồi.')
    if type(value['items']) is not list or type(value['khong_chac']) is not list:
        raise MappingRejected('Danh sách ánh xạ không hợp lệ.')
    for item in value['items']:
        if type(item) is not dict or set(item)!={'cot_id','thong_so','do_tin_cay','ly_do'}:
            raise MappingRejected('Mục ánh xạ có khóa lạ, thiếu trường hoặc số liệu.')
        if type(item['cot_id']) is not int or item['cot_id']<=0 or type(item['thong_so']) is not str:
            raise MappingRejected('Mã cột/thông số không hợp lệ.')
        confidence=item['do_tin_cay']
        if type(confidence) not in (int,float) or not math.isfinite(confidence) or not 0<=confidence<=1:
            raise MappingRejected('Độ tin cậy không hợp lệ.')
        reason=item['ly_do']
        if type(reason) is not str or not reason.strip() or len(reason.split())>=12 or len(reason)>200:
            raise MappingRejected('Lý do phải ngắn dưới 12 từ.')
        if any(ch.isalpha() and 'LATIN' not in unicodedata.name(ch,'') and ch not in 'γφσδεμαβθΓΦΣΔ' for ch in reason):raise MappingRejected('Lý do chưa đúng tiếng Việt.')
        # Ký hiệu/đơn vị là metadata, không phải giá trị đo. Chỉ bỏ mẫu cho phép;
        # số độc lập, công thức, URL/đường dẫn và khóa value vẫn bị chặn.
        semantic_reason=normalized(reason)
        semantic_reason=re.sub(r'\b(?:e0|a1[-–]2)\b','',semantic_reason)
        semantic_reason=re.sub(r'\bcot\s+'+str(item['cot_id'])+r'\b','',semantic_reason)
        semantic_reason=re.sub(r'10\s*(?:\^)?[-−][34]\s*cm2\s*/\s*(?:s|ngay)\b','',semantic_reason)
        semantic_reason=re.sub(r'\b(?:kgf?|g|kn|t)\s*/\s*(?:cm|m)[23]\b|\bcm2\s*/\s*(?:s|ngay)\b','',semantic_reason)
        if re.search(r'\d|[=<>/\\]',semantic_reason):raise MappingRejected('Lý do chứa số liệu, công thức hoặc đường dẫn; từ chối phản hồi.')
        # Output language is VI by contract; English explanations are not accepted.
        if re.search(r'\b(the|column|density|unknown|because|shear|value|unit|pressure|is|this|mapping|confidence|parameter|compression|ratio|soil)\b',reason,re.I):
            raise MappingRejected('Lý do chưa đúng tiếng Việt.')
    if any(type(c) is not int or c<=0 for c in value['khong_chac']) or len(set(value['khong_chac']))!=len(value['khong_chac']):
        raise MappingRejected('Danh sách chưa chắc không hợp lệ.')
    return value

@dataclass(frozen=True)
class ValidatedMapping:
    answer: str
    signature: str
    source_signature: str
    status: str
    reasons: tuple
    preview: tuple
    confirmed_by: str=''


def numeric(value):
    if isinstance(value,(datetime,date,time,timedelta)):
        raise MappingRejected('Ô số đang có kiểu ngày/giờ Excel; kiểm tra định dạng và giá trị ô nguồn, không tự đổi thành số.')
    if type(value) is bool:raise MappingRejected('Không nhận giá trị đúng/sai làm số.')
    if isinstance(value,str):
        value=value.strip().replace('−','-')
        if ',' in value and '.' in value:raise MappingRejected('Dấu phân cách số chưa rõ.')
        value=value.replace(',','.')
        if not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',value):raise MappingRejected('Ô không phải số.')
    try:v=float(value)
    except (ValueError,TypeError,OverflowError) as exc:raise MappingRejected('Ô không phải số.') from exc
    if not math.isfinite(v):raise MappingRejected('Ô không hữu hạn.')
    return v


def converted(value, column, spec):
    if value is None or (isinstance(value,str) and not value.strip()):return None
    if spec['type']=='text':
        if type(value) not in (str,int,float):raise MappingRejected('Ô nhận dạng không hợp lệ.')
        if type(value) in (int,float) and not math.isfinite(value):raise MappingRejected('Ô nhận dạng không hữu hạn.')
        text=str(value).strip()
        text=spec.get('value_aliases',{}).get(text,text)
        if spec.get('enum') and text not in spec['enum']:raise MappingRejected('Giá trị phân loại ngoài danh sách được phép.')
        return text
    unit=column.get('unit','')
    factor=spec['units'].get(unit)
    if factor is None:raise MappingRejected('Đơn vị chưa có phép đổi được phép.')
    v=numeric(value)
    if unit=='degree-minute':
        degree,minute=divmod(abs(v),100)
        if int(v)!=v or minute>=60 or v<0:raise MappingRejected('Góc độ-phút sai.')
        v=degree+minute/60
    else:v*=factor
    if spec.get('min') is not None and (v<spec['min'] or (spec.get('min_exclusive') and v==spec['min'])):
        raise MappingRejected('Giá trị dưới giới hạn hợp lệ.')
    if spec.get('max') is not None and (v>spec['max'] or (spec.get('max_exclusive') and v==spec['max'])):
        raise MappingRejected('Giá trị trên giới hạn hợp lệ.')
    if spec.get('integer') and int(v)!=v:raise MappingRejected('Thông số phải là số nguyên.')
    return v


def validate_mapping(answer, columns, data_rows, registry, required=(), *, threshold=.85,
                     max_blank=.5, confirmed_by='', source_signature=''):
    """Validates ALL fields/cells. Confirmation only resolves uncertainty, not errors."""
    try:
        proposal=strict_json(answer)
        cols={c['cot_id']:c for c in columns}
        if len(cols)!=len(columns):raise MappingRejected('Mã cột nguồn trùng.')
        seen_cols=set();seen_targets=set();reasons=[];preview=[]
        if any(c not in cols for c in proposal['khong_chac']):raise MappingRejected('Cột chưa chắc không tồn tại.')
        for item in proposal['items']:
            cid,target=item['cot_id'],item['thong_so']
            if cid not in cols or cid in seen_cols:raise MappingRejected('Cột không tồn tại hoặc ánh xạ nhiều lần.')
            seen_cols.add(cid)
            if target=='unknown':reasons.append(f'Cột {cid}: chưa ánh xạ.');continue
            if target not in registry:raise MappingRejected('Thông số ngoài sổ đăng ký: '+target)
            if target in seen_targets:raise MappingRejected('Hai cột cùng một thông số: '+target)
            seen_targets.add(target);column=cols[cid];spec=registry[target]
            exact={key for key,value in registry.items() if normalized(column['label']) in {normalized(a) for a in value.get('alias',[])}}
            if exact and target not in exact:raise MappingRejected(f'Cột {cid}: trái với alias nguồn đã xác định.')
            if spec['type']!='text' and column.get('unit','') not in spec['units']:
                raise MappingRejected(f'Cột {cid}: đơn vị không tương thích với {target}.')
            if spec.get('groups') and column.get('group') not in spec['groups']:
                raise MappingRejected(f'Cột {cid}: nhóm thí nghiệm không phù hợp với {target}.')
            vals=[converted(row.get(cid),column,spec) for row in data_rows]
            if not vals or sum(v is None for v in vals)/len(vals)>max_blank:
                raise MappingRejected(f'Cột {cid}: quá nhiều ô trống hoặc chưa có dòng mẫu.')
            if item['do_tin_cay']<threshold or cid in proposal['khong_chac']:
                reasons.append(f'Cột {cid}: cần người dùng xác nhận.')
            preview.append({'cot_id':cid,'source':column['label'],'target':target,
                            'unit_source':column.get('unit',''),'unit_target':spec['unit'],
                            'samples':[v for v in vals if v is not None][:3],
                            'confidence':item['do_tin_cay'],'group':column.get('group','')})
        for cid in set(cols)-seen_cols:reasons.append(f'Cột {cid}: phản hồi thiếu ánh xạ.')
        missing=set(required)-seen_targets
        if missing:raise MappingRejected('Thiếu thông số bắt buộc: '+', '.join(sorted(missing)))
        # Unknown/missing columns stay blank. Human confirmation cannot turn them into numbers.
        pending=[r for r in reasons if 'cần người dùng' in r]
        status='confirm' if pending and not confirmed_by else 'accepted'
        signature=fingerprint([proposal,columns,data_rows,registry,list(required),threshold,max_blank,source_signature])
        return ValidatedMapping(answer,signature,source_signature,status,tuple(reasons),tuple(preview),confirmed_by)
    except (ValueError,TypeError,KeyError,OverflowError) as exc:
        return ValidatedMapping(str(answer),'',source_signature,'rejected',(str(exc),),())


def preview_mapping(validated, columns, data_rows, registry, *, required=(),
                  confirmed_by='', source_signature='', threshold=.85,max_blank=.5):
    """Pure read/conversion for preview. Does not write application state."""
    if not isinstance(validated,ValidatedMapping) or validated.status!='accepted':
        raise MappingRejected('Chưa có ánh xạ được chấp nhận; không liên kết.')
    checked=validate_mapping(validated.answer,columns,data_rows,registry,required,
        threshold=threshold,max_blank=max_blank,confirmed_by=validated.confirmed_by,
        source_signature=source_signature)
    if checked.status!='accepted' or checked.signature!=validated.signature or source_signature!=validated.source_signature:
        raise MappingRejected('Nguồn/ánh xạ đã đổi hoặc chưa xác nhận; không liên kết.')
    proposal=strict_json(validated.answer);cols={c['cot_id']:c for c in columns}
    linked=[]
    for row in data_rows:
        candidate={}
        for item in proposal['items']:
            target=item['thong_so'];cid=item['cot_id']
            if target=='unknown':continue
            value=converted(row.get(cid),cols[cid],registry[target])
            if value is not None:candidate[target]=value
        linked.append(candidate)
    return linked


def apply_mapping(validated, columns, data_rows, registry, state, *, required=(),
                  confirmed_by='', source_signature='', threshold=.85,max_blank=.5):
    """Rechecks the receipt and commits only after explicit Apply."""
    if not confirmed_by:raise MappingRejected('Chưa bấm Áp dụng; không liên kết.')
    linked=preview_mapping(validated,columns,data_rows,registry,required=required,
                           source_signature=source_signature,threshold=threshold,max_blank=max_blank)
    with LOCK:
        backup=deepcopy(state);candidate=deepcopy(state);candidate['rows']=linked
        try:state.clear();state.update(candidate)
        except BaseException:
            state.clear();state.update(backup);raise
    return backup


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    content=json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2,default=json_temporal)
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix=path.name+'.',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def mapping_signature(columns,registry):
    return fingerprint([columns,registry,'strict-mapping-v1'])

def save_mapping_memory(path,columns,registry,answer,actor,overrides=None):
    if not actor:raise MappingRejected('Thiếu người xác nhận ánh xạ.')
    strict_json(answer)
    with LOCK:
        memory=json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else {}
        memory[mapping_signature(columns,registry)]={'answer':answer,'actor':actor,'origin':'user','overrides':overrides or {}}
        atomic_json(path,memory)

def lookup_mapping_memory(path,columns,registry):
    if not Path(path).exists():return None
    memory=json.loads(Path(path).read_text(encoding='utf-8'))
    return memory.get(mapping_signature(columns,registry))

def audit_event(path,event):
    from datetime import datetime,timezone
    event={**event,'time_utc':datetime.now(timezone.utc).isoformat()}
    with LOCK:
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with open(path,'a',encoding='utf-8') as stream:
            stream.write(json.dumps(event,ensure_ascii=False,allow_nan=False,default=json_temporal)+'\n');stream.flush();os.fsync(stream.fileno())


def alias_mapping(columns,registry):
    """Exact aliases only, with explicit compatible unit/group. No magnitude guesses."""
    items=[];used=set();ambiguous=[]
    for column in columns:
        label=normalized(column['label'])
        matches=[]
        for target,spec in registry.items():
            if label not in {normalized(a) for a in spec.get('alias',[])}:continue
            if spec['type']!='text' and column.get('unit','') not in spec['units']:continue
            if spec.get('groups') and column.get('group') not in spec['groups']:continue
            matches.append(target)
        target=matches[0] if len(matches)==1 and matches[0] not in used else 'unknown'
        if target!='unknown':used.add(target)
        else:ambiguous.append(column['cot_id'])
        items.append({'cot_id':column['cot_id'],'thong_so':target,'do_tin_cay':1.0 if target!='unknown' else 0.0,
                      'ly_do':'Tra từ điển chính xác' if target!='unknown' else 'Cần xác nhận nhãn nguồn'})
    return json.dumps({'task':'column_mapping','items':items,'khong_chac':ambiguous},ensure_ascii=False,default=json_temporal)


def required_parameters(method,category,include_time=True):
    """Explicit selection, not defaults inferred from measurements."""
    required={'code','gamma'}
    if category=='Đất rời':required.add('spt_n')
    elif category=='Đất dính':
        if method=='Cc/Cs/Pc':required.update(('e0','cc','cs','pc'))
        elif method=='e–logP':required.update(('ep','e'))
        elif method=='Mv–logP':required.update(('mvp','mv'))
        else:raise MappingRejected('Chưa xác định phương pháp tính.')
        if include_time:required.add('cv_constant')
    else:raise MappingRejected('Chưa xác nhận loại đất.')
    return tuple(sorted(required))
