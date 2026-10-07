"""Paginated Excel/PDF extraction with cell/page provenance, never guessed units."""
from pathlib import Path
import math,re,unicodedata,zipfile
from datetime import date,datetime

KINDS=('summary','borehole','vane','consolidation')
FIELDS={
 'summary':['borehole','sample','depth','depth_top','depth_bottom','Cc','Cs','Cv','Cv1_2','e0','water_content','density','SPT_N'],
 'borehole':['borehole','sample','depth','depth_top','depth_bottom','layer','description','SPT_N'],
 'vane':['borehole','sample','depth','depth_top','depth_bottom','su','su_remoulded','sensitivity','torque','vane_diameter','vane_height'],
 'consolidation':['borehole','sample','depth','depth_top','depth_bottom','stress','time','displacement','void_ratio','Cc','Cs','Cv','Cv1_2','e0','preconsolidation_pressure']}
ALIASES={'borehole':['ho khoan','lo khoan','borehole','hk'], 'sample':['mau','sample'],
 'depth':['do sau','depth'], 'depth_top':['tu do sau','depth top'], 'depth_bottom':['den do sau','depth bottom'],
 'Cc':['cc'], 'Cs':['cs'], 'Cv':['cv'], 'Cv1_2':['cv1 2'], 'e0':['e0'], 'SPT_N':['spt','n30'],
 'su':['su','cu','suc khang cat','undrained'], 'su_remoulded':['remoulded','pha huy','xao tron'],
 'stress':['ung suat','ap luc','stress'], 'time':['thoi gian','time'], 'void_ratio':['he so rong','void ratio'],
 'displacement':['bien dang','chuyen vi','displacement'], 'description':['mo ta','description'], 'layer':['lop','layer']}
def norm(s):
    s=unicodedata.normalize('NFD',str(s or '').lower().replace('đ','d'))
    return re.sub(r'[^a-z0-9]+',' ',''.join(c for c in s if not unicodedata.combining(c))).strip()
def scalar(v):return v.isoformat() if isinstance(v,(date,datetime)) else v
def number(v):
    if v is None or isinstance(v,bool):return None
    if isinstance(v,(int,float)):return v if math.isfinite(v) else None
    s=str(v).strip().replace('−','-').replace('\u00a0','').replace(' ','')
    if not re.fullmatch(r'[+-]?(?:\d+[.,]?\d*|[.,]\d+)(?:[eE][+-]?\d+)?',s):return None
    # Both separators or repeated separators are ambiguous: leave missing.
    if ',' in s and '.' in s:return None
    try:n=float(s.replace(',','.'));return n if math.isfinite(n) else None
    except ValueError:return None
def check_file(path):
    p=Path(path)
    if p.stat().st_size>40*1024*1024:raise ValueError('Document exceeds 40 MB')
    if p.suffix.lower() not in ('.xlsx','.pdf'):raise ValueError('Use XLSX or PDF')
    if p.suffix.lower()=='.xlsx':
        with zipfile.ZipFile(p) as z:
            if sum(i.file_size for i in z.infolist())>100*1024*1024:raise ValueError('Expanded workbook exceeds 100 MB')
    return p
def inspect_document(path):
    p=check_file(path)
    if p.suffix.lower()=='.xlsx':
        from openpyxl import load_workbook
        b=load_workbook(p,read_only=False,data_only=False,keep_links=False)
        try:return {'format':'xlsx','sheets':[{'name':w.title,'rows':w.max_row,'columns':w.max_column,'merged_ranges':[str(r) for r in list(w.merged_cells.ranges)[:200]],'header_preview':[[scalar(c.value) for c in row] for row in w.iter_rows(min_row=1,max_row=min(15,w.max_row),max_col=min(40,w.max_column))]} for w in b]}
        finally:b.close()
    from pypdf import PdfReader
    b=PdfReader(p)
    if b.is_encrypted and not b.decrypt(''):raise ValueError('PDF requires password')
    return {'format':'pdf','pages':len(b.pages),'note':'Read requested page ranges; image scans require OCR. Table geometry must be checked.'}

def read_document(path,sheet='',start=1,end=100,table_mode='lines',ocr=False,cancel=None):
    p=check_file(path)
    if not isinstance(start,int) or not isinstance(end,int) or start<1 or end<start:raise ValueError('Invalid row/page interval')
    def stop():
        if cancel and cancel.is_set():raise InterruptedError('Cancelled')
    if p.suffix.lower()=='.xlsx':
        if end-start+1>200:raise ValueError('Read at most 200 Excel rows per call')
        from openpyxl import load_workbook
        from openpyxl.utils import get_column_letter
        b=load_workbook(p,read_only=False,data_only=False,keep_links=False);cached=load_workbook(p,read_only=False,data_only=True,keep_links=False)
        try:
            w=b[sheet] if sheet else b.worksheets[0];cw=cached[w.title]
            if start>w.max_row:raise ValueError('Start row exceeds sheet')
            end=min(end,w.max_row);cols=min(w.max_column,100);merged={}
            for rg in w.merged_cells.ranges:
                if rg.max_row<start or rg.min_row>end:continue
                if (rg.max_row-rg.min_row+1)*(rg.max_col-rg.min_col+1)>20000:raise ValueError('Merged range too large')
                for ri in range(max(start,rg.min_row),min(end,rg.max_row)+1):
                    for ci in range(rg.min_col,min(cols,rg.max_col)+1):merged[(ri,ci)]=w.cell(rg.min_row,rg.min_col).coordinate
            rows=[]
            for ri in range(start,end+1):
                stop();cells=[]
                for ci in range(1,cols+1):
                    c=w.cell(ri,ci);origin=merged.get((ri,ci),c.coordinate);o=w[origin];value=cw[origin].value if o.data_type=='f' else o.value
                    cells.append({'column':get_column_letter(ci),'cell':c.coordinate,'origin':origin,'raw':scalar(o.value),'value':scalar(value),'formula':o.value if o.data_type=='f' else None,'number_format':o.number_format,'merged':origin!=c.coordinate})
                rows.append({'_source':{'file':p.name,'sheet':w.title,'row':ri},'cells':cells})
            return {'format':'xlsx','rows':rows,'total_rows':w.max_row,'columns_truncated':w.max_column>cols,'next_start':end+1 if end<w.max_row else None,'warnings':['Formula cache may be missing/stale; no recalculation. Merged values carry origin cell.']}
        finally:b.close();cached.close()
    if end-start+1>5:raise ValueError('Read at most 5 PDF pages per call')
    if table_mode not in ('lines','text'):raise ValueError('PDF table_mode must be lines/text')
    import pdfplumber
    rows=[];pages=[];warnings=[]
    with pdfplumber.open(p) as b:
        if start>len(b.pages):raise ValueError('Start page exceeds PDF')
        end=min(end,len(b.pages))
        for pi in range(start-1,end):
            stop();page=b.pages[pi];text=page.extract_text(layout=True) or '';words=page.extract_words()[:3000];ocr_used=False
            tables=page.find_tables({'vertical_strategy':table_mode,'horizontal_strategy':table_mode})
            for ti,t in enumerate(tables,1):
                for ri,vals in enumerate(t.extract(),1):
                    cells=[{'column':str(ci),'cell':f'p{pi+1}:t{ti}:r{ri}:c{ci}','origin':f'p{pi+1}:t{ti}:r{ri}:c{ci}','raw':v,'value':v,'formula':None,'number_format':None,'merged':False} for ci,v in enumerate(vals,1)]
                    rows.append({'_source':{'file':p.name,'page':pi+1,'table':ti,'row':ri,'bbox':list(t.bbox)},'cells':cells})
            if not text.strip() and ocr:
                text,words=ocr_page(p,pi);ocr_used=True
                warnings.append(f'Page {pi+1}: OCR text requires visual verification; no invented table alignment.')
            if not text.strip():warnings.append(f'Page {pi+1}: no readable text; OCR is required or failed.')
            pages.append({'page':pi+1,'text':text[:30000],'text_truncated':len(text)>30000,'words':words,'ocr':ocr_used,'tables':len(tables)})
        if len(rows)>1000:raise ValueError('Too many PDF table rows; request fewer pages')
        return {'format':'pdf','rows':rows,'pages':pages,'total_pages':len(b.pages),'next_start':end+1 if end<len(b.pages) else None,'warnings':warnings+['PDF column alignment is an extraction hypothesis, not a validated mapping.']}

def ocr_page(path,index):
    try:import pypdfium2,pytesseract
    except ImportError:raise ValueError('OCR requires pypdfium2, pytesseract and Tesseract vie+eng installed') from None
    book=pypdfium2.PdfDocument(str(path))
    try:
        page=book[index];bitmap=page.render(scale=2);image=bitmap.to_pil()
        try:
            data=pytesseract.image_to_data(image,lang='vie+eng',timeout=30,output_type=pytesseract.Output.DICT)
            words=[{'text':data['text'][i],'confidence':data['conf'][i],'x0':data['left'][i]/2,'top':data['top'][i]/2,'x1':(data['left'][i]+data['width'][i])/2,'bottom':(data['top'][i]+data['height'][i])/2} for i in range(len(data['text'])) if data['text'][i].strip()]
            return ' '.join(w['text'] for w in words),words[:3000]
        finally:image.close();bitmap.close();page.close()
    finally:book.close()

def suggest_mapping(rows,kind):
    if kind not in KINDS:raise ValueError('Unknown dataset kind')
    labels={}
    for row in rows:
        for c in row['cells']:
            if c['value'] is not None:labels.setdefault(c['column'],[]).append(str(c['value']))
    suggestions={}
    for field in FIELDS[kind]:
        aliases=ALIASES.get(field,[norm(field)])
        candidates=[]
        for col,parts in labels.items():
            normalized=[norm(v) for v in parts]
            if any(alias==v for alias in aliases for v in normalized):candidates.append(col)
        if candidates:suggestions[field]={'candidates':candidates,'needs_validation':True}
    return {'kind':kind,'suggested':suggestions,'headers':labels,'note':'Only exact normalized aliases; mappings/units require validation against the source.'}

def mapped_records(rows,mapping,kind,cv_main=''):
    if kind not in KINDS or not isinstance(mapping,dict) or not mapping:raise ValueError('Explicit column mapping required')
    if any(k not in FIELDS[kind] for k in mapping):raise ValueError('Unsupported field for dataset kind')
    result=[]
    text_fields={'borehole','sample','layer','description'}
    for row in rows:
        fields={};sources={};units={};issues=[]
        bycol={c['column']:c for c in row['cells']}
        for field,spec in mapping.items():
            if not isinstance(spec,dict) or set(spec)-{'column','unit'} or not isinstance(spec.get('column'),str):raise ValueError('Each mapping requires column, optional unit and decimal')
            c=bycol.get(spec['column'])
            if c is None:raise ValueError('Mapped column is absent: '+spec['column'])
            value=c['value'];parsed=value if field in text_fields else number(value)
            if field not in text_fields and value not in (None,'') and parsed is None:issues.append(field+': unreadable/ambiguous numeric value')
            if c['formula'] and value is None:issues.append(field+': formula has no cached value')
            fields[field]=parsed;sources[field]={'cell':c['cell'],'origin':c['origin'],'raw':c['raw']};units[field]=spec.get('unit') or None
        if all(v is None or v=='' for v in fields.values()):continue
        if cv_main:
            if cv_main not in ('Cv','Cv1_2') or cv_main not in fields:raise ValueError('Cv main field must be explicitly mapped')
            fields['Cv_main']=fields[cv_main];units['Cv_main']=units[cv_main];sources['Cv_main']={**sources[cv_main],'selected_field':cv_main}
        result.append({'kind':kind,'values':fields,'units':units,'source':row['_source'],'field_sources':sources,'issues':issues})
    return result
