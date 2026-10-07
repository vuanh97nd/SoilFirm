"""Mục 8: bàn làm việc AI đọc nguồn, duyệt đầu vào và chốt phương án từng đoạn."""
from __future__ import annotations

from pathlib import Path


def _source_file_stamp(path):
    stat=Path(path).stat()
    return stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns

def _depth_column_letter(value):
    import re
    value=str(value).strip().upper()
    cell=re.fullmatch(r'([A-Z]{1,3})[1-9][0-9]*',value)
    if cell:value=cell[1]  # Accept D11 as column D; row still comes from each sample.
    if value.isdigit():
        number=int(value)
        if not 1<=number<=16384:raise ValueError('Số cột Excel phải từ 1 đến 16384.')
        letters=''
        while number:number,remainder=divmod(number-1,26);letters=chr(65+remainder)+letters
        return letters
    if not re.fullmatch(r'[A-Z]{1,3}',value):raise ValueError('Nhập cột như G/H hoặc số cột như 7/8, không nhập từng ô.')
    number=0
    for char in value:number=number*26+ord(char)-64
    if number>16384:raise ValueError('Cột vượt giới hạn XFD của Excel.')
    return value

def _sample_source_row(source,sheet):
    """Use explicit provenance; never infer row from sample order."""
    import re
    source=str(source);prefix=r"(?:'"+re.escape(sheet)+r"'|"+re.escape(sheet)+r')!'
    explicit={int(v) for v in re.findall(prefix+r'\s*row\s+(\d+)\b',source,re.I)}
    if len(explicit)==1:return next(iter(explicit))
    if explicit:return None
    rows={int(v) for v in re.findall(prefix+r'\$?[A-Z]{1,3}\$?([1-9][0-9]*)\b',source,re.I)}
    if len(rows)==1:return next(iter(rows))
    if not rows and (' / '+sheet+';' in source or ' / '+sheet+' / ' in source):
        rows={int(v) for v in re.findall(r'(?<![A-Za-z0-9])\$?[A-Z]{1,3}\$?([1-9][0-9]*)\s*=',source,re.I)}
        if len(rows)==1:return next(iter(rows))
    return None

from copy import deepcopy
from dataclasses import replace
import json
from queue import Empty, Queue
import threading
import time
from local_ai_engine import FREE_PROVIDER, make_local_post, run_deepseek_free_async,offer_ai_install
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ai_analysis_data import (SOIL_KEYS, ARRAY_KEYS, TEXT_KEYS, normalize_material, normalize_borehole,
    request_extraction, request_extraction_files, read_data_sections, project_for_section, validate_section,
    new_session, make_record, commit_record, validate_analysis_project, average_materials, move_layer)
from utils import number, ScrollableFrame
from model import Project
from ui_theme import ProcessingNotice, UI_FONT


class PageRouter:
    def __init__(self,workspace,notebook):self.workspace=workspace;self.notebook=notebook
    def select(self,page=None):
        if page is None:return self.notebook.select()
        w=self.workspace
        if w.app.design_mode.get() == 'TÍNH MỘT ĐOẠN':
            w.app.switch_step(14 if page is w.pages[0] else 2)
            return
        if page is w.pages[0] and w.app.calculation_settings()['data_processed']:
            w.app.switch_step(11)
            return
        if page is w.pages[0]:w.app.switch_step(14)
        elif page is w.pages[1]:w.app.switch_step(11)
        elif page is w.pages[2]:w.app.switch_step(12)
        else:w.app.switch_step(16)


class AnalysisWorkspace(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        state = getattr(app, '_ai_analysis_state', None)
        self.state = state or new_session(Project())
        from geology_statistics import layer_order
        self.state['materials'].sort(key=lambda material:layer_order(material['code']))
        app._ai_analysis_state = self.state
        self.busy = False
        self.cancel_event = threading.Event()
        self.events = Queue()
        self.buttons = []
        self.options = []
        self.last_ai_response = ''
        self.processing_notice = None
        self.geometry_inputs = {}
        self.status = tk.StringVar(value='Đọc dữ liệu → kiểm tra và xác nhận → tính toán → chọn phương án.')
        self.elapsed_var = tk.StringVar(value="Thời gian xử lý: 00:00:00 · Chưa chạy")
        self._job_started_at = None
        self.progress_var = tk.StringVar()
        self.current_label = tk.StringVar()
        self.auto_next = tk.BooleanVar(value=True)
        self.provider = app.ai_provider_var
        self._build()
        self.button(self,text='Hoàn tác nhập',command=lambda:getattr(self,'_undo_last_import',lambda:None)()).pack(anchor='e',padx=8,pady=3)
        self.refresh()
        self.after(100, self.drain)
        app.refresh_ai_analysis = self.reload_state
        if hasattr(app,'geology_statistics_view') and self.state.get('materials'):
            app.geology_statistics_view.import_ai_samples(self.state['materials'])

    def button(self, parent, text, command, **kwargs):
        widget = ttk.Button(parent, text=text, command=command, **kwargs)
        self.buttons.append(widget)
        return widget

    def table(self, parent, headings, widths=None):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True, padx=8, pady=6)
        frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)
        cols = tuple('c'+str(i) for i in range(len(headings)))
        tree = ttk.Treeview(frame, columns=cols, show='headings', selectmode='browse')
        for i, (col, title) in enumerate(zip(cols, headings)):
            width = widths[i] if widths else 120
            tree.heading(col, text=title); tree.column(col, width=width, minwidth=70, stretch=False)
        sy = ttk.Scrollbar(frame, command=tree.yview)
        sx = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        tree.grid(row=0, column=0, sticky='nsew'); sy.grid(row=0, column=1, sticky='ns')
        sx.grid(row=1, column=0, sticky='ew')
        return tree

    def _build(self):
        from ui_theme import configure_tab_style
        configure_tab_style(ttk.Style(self))
        header = ttk.Frame(self, padding=(12, 10))
        header.pack(fill='x')
        ttk.Label(header, text='Chọn phân đoạn và so sánh phương án',
                  font=(UI_FONT, 13, 'bold'), foreground='#123B56').pack(side='left')
        ttk.Combobox(header, textvariable=self.provider, values=('Cloudflare AI','Gemini','DeepSeek','DeepSeek (g4f)','deepseek-r1:8b', 'qwen3:8b', 'qwen3:4b-q4_K_M', 'qwen3:4b-q8_0','Groq','Grok (xAI)','ChatGPT','NVIDIA AI','Kimi AI'),
                     state='readonly', width=22).pack(side='right')
        controls = ttk.Frame(self, padding=(12, 0))
        controls.pack(fill='x')
        self.button(controls, 'Xóa kết quả mục này', lambda:self.reset_section_data('results')).pack(side='left', padx=3)
        self.button(controls, 'Xóa dữ liệu tuyến', self.reset_imported_data).pack(side='left', padx=3)
        self.button(controls, 'Đồng bộ số liệu tuyến', self.capture_template).pack(side='left', padx=3)
        self.button(controls, 'Xem bảng tổng hợp', lambda: self.app.switch_step(8)).pack(side='right', padx=3)
        self.cancel_button = ttk.Button(controls, text='Dừng và giữ phần đã đọc', command=self.cancel_event.set)
        ttk.Button(controls, text='Xem phản hồi AI', command=self.show_ai_response).pack(side='right', padx=3)
        self.native_tabs=ttk.Notebook(self);self.native_tabs.pack(fill='both',expand=True,padx=8,pady=6)
        selection_page=ttk.Frame(self.native_tabs);self.native_tabs.add(selection_page,text='1 · Chọn phân đoạn')
        pages=[ttk.Frame(self.app.ai_material_host),ttk.Frame(self.app.tab_ai_boreholes),ttk.Frame(self.app.tab_ai_sections),ttk.Frame(self.native_tabs),ttk.Frame(self.native_tabs)]
        for page in pages[:3]:page.pack(fill='both',expand=True)
        self.native_tabs.add(pages[3],text='2 · Tính & so sánh');self.native_tabs.add(pages[4],text='3 · Phương án đã chốt')
        self.pages=pages;self.tabs=PageRouter(self,self.native_tabs)
        ttk.Label(selection_page,text='Dùng phân đoạn ở mục 1, địa chất ở mục 2 và cấu hình thiết kế ở mục 4.',padding=8).pack(fill='x')
        self.section_choice=tk.StringVar()
        ttk.Combobox(selection_page,textvariable=self.section_choice,state='readonly',width=65).pack(anchor='w',padx=8,pady=8)
        self.section_combo=selection_page.winfo_children()[-1]
        def choose():
            if self.busy:return
            try:
                self.state['index']=self.section_combo.current()
                if self.state['index']<0:raise ValueError('Chọn một phân đoạn đã nhập.')
                self.state['pending']=None;self.state.pop('pending_project',None);self.refresh();self.tabs.select(self.pages[3])
            except Exception as exc:self.error(exc)
        self.button(selection_page,'Mở đoạn tính toán',choose).pack(anchor='w',padx=8,pady=5)
        self.button(selection_page,'Bổ sung phân đoạn',lambda:self.app.switch_step(12)).pack(anchor='w',padx=8,pady=5)
        self.button(selection_page,'Mở tính toán toàn tuyến',lambda:self.app.switch_step(8)).pack(anchor='w',padx=8,pady=5)
        ttk.Label(selection_page,textvariable=self.progress_var,padding=8).pack(fill='x')
        for index, text in enumerate((
            'AI đọc từng mẫu vào Thống kê số liệu. Bảng dưới là giá trị trung bình của các mẫu được dùng theo từng lớp.',
            'Đọc bảng phân đoạn trước; tên lỗ khoan được lấy tự động; AI đọc cao độ miệng lỗ, chiều sâu, mã/tên lớp và bề dày từ trụ CAD/PDF. Xác nhận rồi tính phân đoạn.',
            'Đọc THSH của Data Excel. ΔS cho phép lấy đúng cột BG của từng đoạn; nhấp đúp để sửa hình học và chọn lỗ khoan.',
            'Dùng đầu vào đã xác nhận để tính bằng bộ tính SOILFIRM PRO. Đoạn đã đạt trước xử lý được lưu Không cần xử lý.',
            'Phương án đã chốt được lưu tạm ở thẻ Tổng hợp kết quả. Bấm Lưu dự án để giữ dữ liệu và tiếp tục phiên sau.'
        )):
            if index != 2:
                description = ttk.Label(pages[index], text=text, padding=8, wraplength=960)
                description.pack(fill='x')
                if index == 1: self.borehole_description = description
        summary_bar=ttk.Frame(pages[0]);summary_bar.pack(fill='x',padx=8,pady=4)
        self.button(summary_bar, 'Áp dụng chỉ tiêu', self.approve_geology, style='Accent.TButton').pack(side='right', padx=3)
        for label,command in [('Nhập chỉ tiêu',lambda:self.edit_material(new=True)),('Sửa chỉ tiêu',self.edit_material),('Sắp xếp lớp',self.sort_materials),('↑',lambda:self.move_material(-1)),('↓',lambda:self.move_material(1))]:
            self.button(summary_bar,label,command).pack(side='left',padx=3)
        self.button(summary_bar,'Xóa dữ liệu bảng',lambda:self.reset_section_data('materials')).pack(side='left',padx=3)
        self.button(summary_bar,'Xóa dữ liệu đầu vào',self.reset_imported_data).pack(side='left',padx=3)
        self.material_tree = self.table(pages[0], ('Mã lớp','Loại đất','γ TB (T/m³)','e₀ TB','Cc TB','Cs TB','Pc TB (T/m²)','Cv TB (10⁻³ cm²/s)',
            'c₀ / Su (T/m²)','N-SPT (búa)','φ′ CU (độ)','c TB (T/m²)','φ cắt TB (độ)',
            'P nén (kgf/cm²)','e theo P','P cố kết (kgf/cm²)','P nén thể tích (kgf/cm²)','mv theo P (m²/T)',
            'e-logP (P:e)','Cv-logP (P:Cv)','Mặt thoát','Số mẫu','Nguồn'),
            (110,100,100,75,75,75,105,140,110,100,100,110,115,160,180,160,180,180,240,240,90,80,420))
        bar = ttk.Frame(pages[1]); bar.pack(fill='x', padx=8)
        self.direct_input_button = self.button(bar, 'Nhập chỉ tiêu đất', self.edit_borehole_parameters)
        self.button(bar, 'Đọc địa tầng lỗ khoan', lambda: self.read_source('boreholes')).pack(side='left', padx=3)
        self.button(bar, 'Thêm lỗ khoan', lambda: self.edit_borehole(new=True)).pack(side='left', padx=3)
        self.button(bar, 'Sửa lỗ khoan', self.edit_borehole).pack(side='left', padx=3)
        self.button(bar, 'Xác nhận địa tầng', self.approve_boreholes, style='Accent.TButton').pack(side='right', padx=3)
        bar = ttk.Frame(pages[1]); bar.pack(fill='x', padx=8, pady=3)
        self.button(bar, 'Xóa lỗ khoan', lambda: self.remove_row('boreholes', self.hole_tree)).pack(side='left', padx=3)
        self.order_buttons(bar,lambda d:self.move_input('boreholes',self.hole_tree,d), inline=True)
        self.button(bar,'Xóa dữ liệu bảng',lambda:self.reset_section_data('boreholes')).pack(side='left',padx=3)
        self.button(bar,'Xóa dữ liệu tuyến',self.reset_imported_data).pack(side='left',padx=3)
        self.hole_tree = self.table(pages[1], ('Lỗ khoan','Cao độ (m)','Chiều sâu (m)','Địa tầng: mã lớp / bề dày','Nguồn','Cần đối chiếu'), (160,120,120,460,420,450))
        self.hole_tree.bind('<Double-1>', lambda _e: self.edit_borehole())
        bar = ttk.Frame(pages[2]); bar.pack(fill='x', padx=8)
        self.button(bar, 'Nhập dữ liệu phân đoạn', self.read_data).pack(side='left', padx=3)
        self.button(bar, 'Sửa số liệu đoạn', self.edit_section).pack(side='left', padx=3)
        self.button(bar, 'Xác nhận phân đoạn', self.approve_sections, style='Accent.TButton').pack(side='right', padx=3)
        self.order_buttons(bar,lambda d:self.move_input('sections',self.section_tree,d), inline=True)
        self.button(bar,'Xóa dữ liệu bảng',lambda:self.reset_section_data('sections')).pack(side='left',padx=3)
        self.button(bar,'Xóa dữ liệu tuyến',self.reset_imported_data).pack(side='left',padx=3)
        self.section_tree = self.table(pages[2], ('STT','Lý trình','L (m)','Htk (m)','B (m)','ΔS (cm)','Lỗ khoan chọn','Nguồn ΔS','Trạng thái'),
                                       (65,210,85,85,85,85,180,200,160))
        self.section_tree.bind('<Double-1>', lambda _e: self.edit_section())
        ttk.Label(pages[3], textvariable=self.current_label, font=(UI_FONT,11,'bold'), padding=8).pack(fill='x')
        bar = ttk.Frame(pages[3]); bar.pack(fill='x', padx=8)
        self.button(bar, 'Thiết lập tính toán', self.edit_settings).pack(side='left', padx=3)
        self.button(bar, 'Xem số liệu đoạn', self.review_current_project).pack(side='left', padx=3)
        self.button(bar, 'Tính bằng AI', self.calculate, style='Accent.TButton').pack(side='left', padx=3)
        self.button(bar, 'Xác nhận phương án', self.accept_option, style='Accent.TButton').pack(side='left', padx=3)
        ttk.Checkbutton(bar, text='Tính đoạn tiếp theo', variable=self.auto_next).pack(side='right')
        self.result_tabs = ttk.Notebook(pages[3]); self.result_tabs.pack(fill='both',expand=True,padx=8,pady=6)
        self.option_page = ttk.Frame(self.result_tabs); self.before_page = ttk.Frame(self.result_tabs)
        self.detail_page = ttk.Frame(self.result_tabs)
        self.result_tabs.add(self.option_page,text='So sánh phương án')
        self.result_tabs.add(self.before_page,text='Trước xử lý')
        self.result_tabs.add(self.detail_page,text='Thông số & kiểm toán')
        self.order_buttons(self.option_page,lambda d:self.move_display(self.option_tree,d))
        self.option_tree = self.table(self.option_page, ('Phương án','Lún dư (cm)','Giới hạn (cm)','Kiểm toán lún','Kiểm toán phương án','Thời gian','Thông số / thông tin'),(210,100,110,140,160,140,620))
        self.before_tree = self.table(self.before_page, ('Vị trí','Sc cuối (cm)','Sc dư (cm)','U (%)','t (ngày)','ΔS (cm)','Đánh giá'),(220,120,120,100,100,110,150))
        self.detail_tree = self.table(self.detail_page, ('Phương án','Thông số / Điều kiện','Giá trị','Đơn vị / Kết quả'),(230,380,400,160))
        self.order_buttons(pages[4],lambda d:self.move_saved(d))
        self.saved_tree = self.table(pages[4], ('STT','Lý trình','Lỗ khoan','Phương án','Lún (cm)','ΔS (cm)','Kết quả'),(75,220,150,250,110,110,100))
        ttk.Label(self, textvariable=self.progress_var, foreground='#087780', padding=(12,0)).pack(fill='x')
        ttk.Label(self, textvariable=self.elapsed_var, foreground='#087780', padding=(12, 0)).pack(fill='x')
        ttk.Label(self, textvariable=self.status, wraplength=1100, padding=12).pack(fill='x')

    @staticmethod
    def fmt(value):
        return '—' if value is None else f'{value:.3f}' if isinstance(value, (int,float)) else str(value)

    def sort_materials(self):
        from geology_statistics import layer_order
        self.state['materials'].sort(key=lambda material:layer_order(material['code']))
        self.refresh()

    def refresh(self):
        from geology_statistics import parameter_text
        # Keep the borehole catalogue scoped to the imported segment table.
        if self.state.get('sections') and not self.app.calculation_settings()['data_processed']:
            from ai_analysis_data import borehole_key
            names=list(dict.fromkeys(str(section.get('borehole_name') or '').strip()
                       for section in self.state['sections'] if str(section.get('borehole_name') or '').strip()))
            allowed={borehole_key(name) for name in names}
            self.state['data_borehole_names']=names
            retained=[hole for hole in self.state['boreholes'] if borehole_key(hole['name']) in allowed or hole.get('test_samples')]
            if len(retained)!=len(self.state['boreholes']):
                self.state['boreholes']=retained
                self.state['boreholes_approved']=False
            for section in self.state['sections']:
                selected=section.get('borehole_selected','')
                if selected and borehole_key(selected)!=borehole_key(section.get('borehole_name','')):
                    section['borehole_selected']=''
                    self.state['sections_approved']=False
        self._render_generation=getattr(self,'_render_generation',0)+1
        tables=(self.material_tree,self.hole_tree,self.section_tree,self.saved_tree)
        buffers={tree:[] for tree in tables}
        def collect(tree,*args,**kwargs):buffers[tree].append((args,kwargs))
        for tree in tables:
            tree._requested_selection=None
            children=tree.get_children()
            if children:tree.delete(*children)
        for i, m in enumerate(self.state['materials']):
            v=m['values']; cv=v.get('cv')
            collect(self.material_tree,'', 'end', iid=str(i), values=(m['code'],v.get('category','—'),
                *[parameter_text(v.get(k),k) or '—' for k in ('gamma','e0','cc','cs','pc')],
                (self.fmt(m['cv_constant'])+' (hằng)' if m.get('cv_constant') is not None else
                 ', '.join(self.fmt(x) for x in cv) if cv else '—'),
                parameter_text(v.get('co'),'co') or '—',parameter_text(v.get('spt_n'),'spt_n') or '—',parameter_text(v.get('phi_cu_effective',m.get('phi_cu_effective')),'phi_cu_effective') or '—',
                parameter_text(v.get('cohesion_c'),'cohesion_c') or '—',parameter_text(v.get('friction_phi'),'friction_phi') or '—',
                ', '.join(self.fmt(x) for x in v.get('ep',[])) if v.get('e') else '—',
                ', '.join(self.fmt(x) for x in v.get('e',[])) or '—',
                ', '.join(self.fmt(x) for x in v.get('cvp',[])) if cv else '—',
                ', '.join(self.fmt(x) for x in v.get('mvp',[])) if v.get('mv') else '—',
                ', '.join(self.fmt(x) for x in v.get('mv',[])) or '—',
                '; '.join(f'{self.fmt(p)}:{self.fmt(e)}' for p,e in zip(v.get('ep',[]),v.get('e',[]))) or '—',
                '; '.join(f'{self.fmt(p)}:{self.fmt(c)}' for p,c in zip(v.get('cvp',[]),v.get('cv',[]))) or '—',
                v.get('drainage',1),m.get('sample_count',1),m['source']))
        for i,h in enumerate(self.state['boreholes']):
            collect(self.hole_tree,'', 'end', iid=str(i), values=(h['name'],self.fmt(h['elevation']),self.fmt(h['depth']),
                '; '.join(x['code']+(' · '+x['description'] if x.get('description') else '')+': '+self.fmt(x['thickness'])+' m' for x in h['layers']),h['source'],'; '.join(h.get('validation_issues',[]))))
        saved={r['section_no'] for r in self.state['records']}
        for i,s in enumerate(self.state['sections']):
            collect(self.section_tree,'', 'end', iid=str(i), values=(s['section_no'],s['station_from']+' – '+s['station_to'],
                *[self.fmt(s[k]) for k in ('length','h_design','crest_width','limit_cm')],s['borehole_selected'],s['limit_source'],
                'Đã chọn phương án' if s['section_no'] in saved else ('Chờ tính toán' if all(self.state.get(k) for k in ('geology_approved','boreholes_approved','sections_approved')) else 'Chờ xác nhận dữ liệu')))
        for i,r in enumerate(self.state['records']):
            collect(self.saved_tree,'', 'end', iid=str(i), values=(r['section_no'],r['station'],r['project_snapshot'].borehole_name,
                r['opt_name'],self.fmt(r['residual']),self.fmt(r['limit']),r['status']))
        self.section_combo.configure(values=[f'STT {r["section_no"]} · {r["station_from"]} – {r["station_to"]}' for r in self.state['sections']])
        index=self.state['index']; sections=self.state['sections']
        if index < len(sections):
            s=sections[index]
            self.current_label.set(f'Đoạn {index+1}/{len(sections)} · STT {s["section_no"]} · '
                f'{s["station_from"]} – {s["station_to"]} · Lỗ khoan {s["borehole_selected"] or "chưa chọn"} · ΔS={self.fmt(s["limit_cm"])} cm')
        else:
            self.current_label.set('Đã hoàn tất tất cả phân đoạn.' if sections else 'Chưa có dữ liệu phân đoạn đã xác nhận.')
        approvals=['✓' if self.state.get(key) else '○' for key in ('sections_approved','boreholes_approved','geology_approved')]
        self.progress_var.set(f'{approvals[0]} Phân đoạn Data    →    {approvals[1]} Địa tầng lỗ khoan    →    {approvals[2]} Chỉ tiêu đất    |    Đã chọn phương án {len(self.state["records"])} đoạn')

        for tree,items in buffers.items():self.insert_table_batches(tree,items,self._render_generation)

    def insert_table_batches(self,tree,items,generation):
        def batch(start=0):
            if not self.winfo_exists() or not tree.winfo_exists() or generation!=self._render_generation:return
            end=min(start+75,len(items))
            for args,kwargs in items[start:end]:
                if 'values' in kwargs:
                    kwargs=dict(kwargs,values=tuple(v[:1000]+' …' if isinstance(v,str) and len(v)>1000 else v for v in kwargs['values']))
                tree.insert(*args,**kwargs)
            wanted=getattr(tree,'_requested_selection',None)
            if wanted is not None and tree.exists(wanted):
                tree.selection_set(wanted);tree.focus(wanted);tree.see(wanted);tree._requested_selection=None
            if end<len(items):self.after(8,lambda:batch(end))
        batch()

    def select_table_row(self,tree,target):
        item=str(target)
        if tree.exists(item):tree.selection_set(item);tree.focus(item);tree.see(item)
        else:tree._requested_selection=item

    def warning_summary(self,notes):
        if not notes:return ''
        self.last_ai_response='Thông tin khi đọc/ghép dữ liệu:\n'+'\n'.join(notes)
        summary=' '.join(str(n)[:180] for n in notes[:3])
        if len(notes)>3:summary+=f' … Tổng {len(notes)} thông báo. Bấm Xem phản hồi AI để xem đầy đủ.'
        return summary

    def reload_state(self):
        if self.busy:
            self.cancel_event.set()
            return
        self.state=getattr(self.app,'_ai_analysis_state',None) or new_session(Project())
        self.app._ai_analysis_state=self.state
        self._strength_binding_cache=None
        self.refresh(); self.show_pending()

    def invalidate(self, key):
        if key in ('geology_approved','boreholes_approved') and (self.state.get('strength_samples') or self.state.get('spt_samples')):self.bind_strength_samples()
        self.state[key]=False
        self.state['pending']=None; self.state.pop('pending_project',None)
        self.clear_results(); self.refresh()

    def clear_results(self):
        for tree in (self.option_tree,self.before_tree,self.detail_tree):
            tree.delete(*tree.get_children())
        self.options=[]

    def data_project(self):
        if self.app.design_mode.get() == 'TÍNH MỘT ĐOẠN':
            self.state['template'] = self.app.project
            return self.app.project
        return self.state['template']

    def sync_input_controls(self):
        direct = (self.app.design_mode.get() == 'TÍNH TOÀN TUYẾN'
                  and self.app.calculation_settings()['data_processed'])
        self.borehole_description.configure(text=(
            'Khai báo lỗ khoan và nhập chỉ tiêu đã xử lý. Xác nhận địa tầng trước khi tính phân đoạn.' if direct else
            'Python đọc địa tầng; AI kiểm tra cấu trúc trước khi trả số liệu. Xác nhận địa tầng trước khi tính.'))
        if direct:
            if not self.direct_input_button.winfo_manager():
                self.direct_input_button.pack(side='left', padx=3)
        else:
            self.direct_input_button.pack_forget()

    def edit_borehole_parameters(self):
        if self.busy: return
        try:
            hole = self.state['boreholes'][self.selected_index(self.hole_tree)]
            if not hole['layers']: raise ValueError('Khai báo địa tầng lỗ khoan trước khi nhập chỉ tiêu.')
            popup = tk.Toplevel(self); popup.title('Chỉ tiêu đất · '+hole['name']); popup.transient(self.app)
            body = ttk.Frame(popup, padding=12); body.pack(fill='both', expand=True)
            ttk.Label(body, text='Lớp đất:').pack(anchor='w')
            choice = ttk.Combobox(body, state='readonly', width=45,
                values=[f'{i+1}. {layer["code"]}' for i, layer in enumerate(hole['layers'])])
            choice.pack(fill='x', pady=8); choice.current(0)
            def edit():
                layer = hole['layers'][choice.current()]
                material = next((m for m in self.state['materials']
                    if m['code'].casefold() == layer['code'].casefold()), {})
                values = deepcopy(material.get('values', {}))
                values.update(layer.get('direct_values', {}))
                labels = {'category':'Loại đất', 'state':'Trạng thái', 'gamma':'γ (T/m³)',
                    'drainage':'Mặt thoát nước (1/2)', 'e0':'e₀', 'cc':'Cc', 'cs':'Cs',
                    'pc':'Pc (T/m²)', 'co':'Co / Su (T/m²)', 'cohesion_c':'c (T/m²)',
                    'friction_phi':'φ (độ)', 'phi_cu_effective':'φ′ CU (độ)',
                    'cv_constant':'Cv trung bình (10⁻³ cm²/s)', 'ch_cv':'Ch/Cv',
                    'strength_m':'Hệ số sức kháng m', 'spt_n':'N-SPT (búa)', 'sand_method':'Mô hình đất rời'}
                specs = [(k, label, values.get(k),
                    {'category':('Đất dính','Đất rời'), 'state':('Quá cố kết','Cố kết thường'),
                     'sand_method':('De Beer','Schmertmann')}.get(k), False) for k,label in labels.items()]
                for key, label in (('ep','P nén (kg/cm²)'), ('e','e theo P'),
                        ('cvp','P cố kết (kg/cm²)'), ('cv','Cv theo P (10⁻³ cm²/s)'),
                        ('mvp','P nén thể tích (kg/cm²)'), ('mv','mv theo P (m²/T)')):
                    specs.append((key, label, '; '.join(str(v) for v in values.get(key, [])), None, False))
                def save(raw):
                    if self.busy or hole not in self.state['boreholes']:
                        raise ValueError('Danh sách lỗ khoan đã thay đổi; mở lại hộp nhập chỉ tiêu.')
                    data = deepcopy(values)
                    data.update(code=layer['code'], layer_code_verified=True, source='Người dùng nhập trực tiếp')
                    for key in (*labels, *ARRAY_KEYS):
                        if key not in raw: continue
                        if not str(raw[key] or '').strip():
                            data.pop(key, None); continue
                        data[key] = [number(v,key) for v in raw[key].split(';') if v.strip()] if key in ARRAY_KEYS else raw[key]
                    normalized = normalize_material(data)
                    layer['direct_values'] = normalized['values']
                    layer['direct_source'] = data['source']
                    self.state['geology_approved'] = False
                    self.invalidate('boreholes_approved')
                    self.status.set('Đã lưu chỉ tiêu '+hole['name']+' / '+layer['code'])
                self.form('Chỉ tiêu '+hole['name']+' / '+layer['code'], specs, save, soil_fields=True)
            ttk.Button(body, text='Nhập chỉ tiêu', command=edit, style='Accent.TButton').pack(side='left')
            ttk.Button(body, text='Đóng', command=popup.destroy).pack(side='right', padx=8)
        except Exception as exc: self.error(exc)

    def capture_template(self):
        if self.busy:return
        if self.app.design_mode.get() != 'TÍNH TOÀN TUYẾN':
            messagebox.showinfo('Đồng bộ dữ liệu', 'Thiết kế tuyến lấy dữ liệu từ luồng TÍNH TOÀN TUYẾN.', parent=self.app)
            return
        try:
            selector = self.app.route_section_selector
            if self.app.current_step in (4,5,6) and selector.active is not None:
                selector.require_section()
                self.app.sync_ai_calculation_inputs()
                selector.stash()
                self.status.set('Đã lưu thông số thiết kế của STT '+str(selector.active)+'. Đầu vào từng đoạn vẫn lấy từ dữ liệu toàn tuyến đã xác nhận.')
            else:
                # Common settings already belong to this session; a displayed section
                # or the single-section workspace must never replace this template.
                self.state['template']=deepcopy(self.data_project())
                self.status.set('Đã đồng bộ thiết kế tuyến; phân đoạn, lỗ khoan và chỉ tiêu lấy từ dữ liệu toàn tuyến đã xác nhận.')
            self.state.pop('pending_project',None);self.state['pending']=None
            self.clear_results()
        except Exception as exc:self.error(exc)

    def reset_section_data(self, scope):
        """Clear the selected data category and invalidate dependent results."""
        labels={'materials':'Bảng tổng hợp chỉ tiêu','statistics':'Thống kê số liệu',
                'boreholes':'Địa tầng lỗ khoan','sections':'Bảng phân đoạn','results':'Kết quả tính toán'}
        if scope not in labels:raise ValueError('Mục xóa không hợp lệ.')
        if self.busy:
            messagebox.showinfo('Đang xử lý','Dừng tác vụ hiện tại rồi xóa dữ liệu.',parent=self);return
        explanation={
            'materials':'Xóa các lớp/chỉ tiêu và các mẫu thống kê liên quan. Giữ bảng phân đoạn và địa tầng lỗ khoan.',
            'statistics':'Xóa các mẫu, lựa chọn thống kê, điểm Su/N-SPT và giá trị trung bình từ các mẫu. Giữ mã lớp và chỉ tiêu đã nhập/sửa trực tiếp.',
            'boreholes':'Xóa địa tầng lỗ khoan và bỏ liên kết chọn lỗ trong các phân đoạn. Giữ phân đoạn và các mẫu nguồn để đọc/ghép lại.',
            'sections':'Xóa bảng phân đoạn và lựa chọn đoạn tính. Giữ địa tầng lỗ khoan và số liệu địa chất.',
            'results':'Xóa kết quả tính và phương án đã chốt. Giữ toàn bộ dữ liệu đầu vào.'}
        if not messagebox.askyesno('Xóa '+labels[scope],explanation[scope]+
                '\nKết quả phụ thuộc trong phiên cũng được xóa để tính lại. File nguồn và file đã lưu giữ nguyên.',parent=self):return
        self._strength_binding_cache=None
        project=self.data_project()
        if scope in ('materials','statistics'):
            data=project.geology_statistics
            data.update(samples=[],choices={},revision=data.get('revision',0)+1,imported_sources={})
            self.state['strength_samples']=[];self.state['spt_samples']=[]
            self.state['strength_audit']=[];self.state['spt_audit']=[]
            self.state['geology_approved']=False
            if scope=='materials':
                self.state['materials']=[];data['layer_catalog']={}
                project.soils=[];project.main_soils=[]
                self.state['template'].soils=[];self.state['template'].main_soils=[]
                self.state.pop('material_source_order',None)
            else:
                for material in self.state['materials']:
                    material['samples']=[];material['sample_count']=0
                    for key in ('borehole_strength','strength_values','strength_source','depth_co_generated',
                                'depth_spt_n_generated','depth_strength_generated','statistics_source'):
                        material.pop(key,None)
                view=getattr(self.app,'geology_statistics_view',None)
                if view is not None:view.update_ai_summary()
        if scope=='boreholes':
            self.state['boreholes']=[];self.state['boreholes_approved']=False
            self.state['sections_approved']=False;project.borehole_name=''
            for section in self.state['sections']:section['borehole_selected']=''
            self.bind_strength_samples()
        if scope=='sections':
            self.state['sections']=[];self.state['sections_approved']=False
            self.state['data_borehole_names']=[];self.state['source']='';self.state['index']=0
            self.app._section_excel_path=''
            self.section_choice.set('')
            self.app.excel_section_combo.configure(values=())
            self.app.excel_section_no.set('');self.app.excel_section_notice.set('Chưa nhập Data.')
        self.state['records']=[];self.state['pending']=None;self.state.pop('pending_project',None)
        project.calculation_results={}
        if self.app.design_mode.get() == 'TÍNH MỘT ĐOẠN':
            self.app._single_batch_records=[];self.app._single_batch_failures=[]
            self.app._single_selected_option=None
            for attribute in ('_choice_group_results','_cdm_reports','_step_result_cache'):
                getattr(self.app,attribute,{}).clear()
            self.app.chart_data={};self.clear_results();self.refresh();self.app.populate()
            self.app.geology_statistics_view.refresh();self.app.draw_live_diagram()
            self.status.set('Đã xóa '+labels[scope]);return
        self.app._saved_sections_data=[];self.app._batch_candidates={};self.app._batch_runs={}
        self.app._route_manual_designs={}
        self.app.route_section_selector.active=None
        self.app.route_section_selector.base=None
        self.app._active_section_no=None;self.app._active_section_length=0
        for attribute in ('_choice_group_results','_cdm_reports','_step_result_cache'):
            getattr(self.app,attribute,{}).clear()
        self.app.chart_data={};self.app._ai_statistics_context=''
        self.last_ai_response='';self.progress_var.set('');self.current_label.set('')
        self.clear_results();self.refresh();self.app.populate();self.app.draw_live_diagram()
        if hasattr(self.app,'geology_statistics_view'):self.app.geology_statistics_view.refresh()
        if hasattr(self.app,'refresh_result_summary'):self.app.refresh_result_summary()
        self.status.set('Đã xóa '+labels[scope]+'. '+explanation[scope])

    def reset_imported_data(self):
        if self.app.design_mode.get() == 'TÍNH MỘT ĐOẠN':
            self.reset_section_data('materials')
            return
        if self.busy:
            messagebox.showinfo('Đang xử lý','Dừng tác vụ hiện tại rồi xóa dữ liệu.',parent=self)
            return
        if not messagebox.askyesno('Xóa dữ liệu để nhập lại',
                'Xóa toàn bộ phân đoạn, lỗ khoan, mẫu thống kê, lớp đất và kết quả trong phiên đang mở?\n'
                'File nguồn và file dự án đã lưu trên máy vẫn giữ nguyên.',parent=self):return
        project=deepcopy(self.data_project())
        project.soils=[];project.main_soils=[];project.calculation_results={}
        project.geology_statistics={'version':1,'samples':[],'choices':{},'revision':0}
        project.borehole_name=''
        self.app.project=project
        self.state=new_session(project);self.app._ai_analysis_state=self.state
        self.app._section_excel_path=''
        self.app._active_section_no=None;self.app._active_section_length=0
        self.app._saved_sections_data=[]
        self.app._batch_candidates={};self.app._batch_runs={}
        self.app._route_manual_designs={}
        self.app.route_section_selector.active=None
        self.app.route_section_selector.base=None
        self.app._choice_group_results.clear();self.app._cdm_reports.clear()
        self.app.chart_data={}
        self.app._ai_statistics_context=''
        self._strength_binding_cache=None
        getattr(self.app,'_step_result_cache',{}).clear()
        self.last_ai_response='';self.progress_var.set('');self.current_label.set('')
        self.section_choice.set('');self.cancel_event.clear()
        self.app.excel_section_combo.configure(values=())
        self.app.excel_section_no.set('');self.app.excel_section_notice.set('Chưa nhập Data.')
        import ai_analysis_data
        with ai_analysis_data._EXTRACTION_CACHE_LOCK:
            ai_analysis_data._EXTRACTION_CACHE.clear()
        self.clear_results();self.refresh();self.app.populate()
        self.app.draw_live_diagram()
        if hasattr(self.app,'geology_statistics_view'):self.app.geology_statistics_view.refresh()
        if hasattr(self.app,'refresh_result_summary'):self.app.refresh_result_summary()
        self.status.set('Đã xóa dữ liệu phiên. Đọc bảng phân đoạn rồi nhập lại trụ địa chất và số liệu thống kê.')
        self.tabs.select(self.pages[2])

    def start_new(self):
        if self.busy:return
        if self.state['sections'] and not messagebox.askyesno('Phiên AI mới','Bắt đầu phiên mới? Các phương án đã chốt vẫn giữ ở thẻ Tổng hợp kết quả.',parent=self):return
        self.state=new_session(self.data_project());self.app._ai_analysis_state=self.state
        self.capture_template();self.clear_results();self.refresh()

    def error(self, exc):
        if offer_ai_install(self,exc,self.provider.get(),getattr(self.app,'current_user_role','')=='admin',self.status.set):
            self.last_ai_response='Đang tải/cài thành phần AI trong nền theo lựa chọn của bạn. Dữ liệu trước đó được giữ nguyên.'
            return
        if hasattr(exc,'mapping_context'):
            self._pending_mapping_context=exc.mapping_context
            reason=str(exc.mapping_context.get('reason') or exc)
            self.last_ai_response='Chưa tự cập nhật ánh xạ chưa đủ căn cứ. Dữ liệu cũ được giữ nguyên.\n'+reason
            self.status.set('Chưa cập nhật: '+reason+' · Chọn Xem phản hồi AI để xem chi tiết.')
            self.show_ai_response()
            return
        answer=str(getattr(exc,'answer','') or '').strip()
        self.last_ai_response='Thông báo xử lý:\n'+str(exc)+'\n\n'+(answer or 'Chưa có bảng số liệu được trả về trong lượt xử lý này. Nguyên nhân cụ thể được ghi ở thông báo phía trên; dữ liệu đã có được giữ nguyên.')
        self.status.set(str(exc))
        self.show_ai_response()

    def show_ai_response(self):
        popup=tk.Toplevel(self);popup.title('Phản hồi AI gần nhất');popup.geometry('860x520');popup.transient(self.app)
        ttk.Label(popup,text='Phản hồi dưới đây chưa được nhập vào bộ tính nếu sai cấu trúc. Kiểm tra trước khi đọc lại.',padding=10).pack(fill='x')
        frame=ttk.Frame(popup);frame.pack(fill='both',expand=True,padx=10,pady=6)
        text=tk.Text(frame,wrap='word',font=(UI_FONT,11))
        scrollbar=ttk.Scrollbar(frame,command=text.yview);text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y');text.pack(fill='both',expand=True)
        text.insert('1.0',self.last_ai_response or 'Chưa có phản hồi lỗi từ AI.');text.configure(state='disabled')
        actions=ttk.Frame(popup);actions.pack(pady=8)
        def copy_response():
            popup.clipboard_clear();popup.clipboard_append(self.last_ai_response)
        ttk.Button(actions,text='Sao chép',command=copy_response).pack(side='left',padx=5)
        context=getattr(self,'_pending_mapping_context',None)
        if context:
            ttk.Button(actions,text='Chỉnh ánh xạ khi cần',command=lambda:self.mapping_review(context)).pack(side='left',padx=5)
        ttk.Button(actions,text='Đóng',command=popup.destroy).pack(side='left',padx=5)

    def start_processing_notice(self, label):
        def cancel():
            self.cancel_event.set()
            self.status.set('Đang dừng xử lý…')
        self.processing_notice = ProcessingNotice(self.app, label, detail=self.status, cancel=cancel, elapsed=self.elapsed_var)
        self.processing_notice.grab_set()
        if hasattr(self.app, 'status_text'): self.app.status_text.set(label)

    def stop_processing_notice(self):
        notice = getattr(self, 'processing_notice', None)
        self.processing_notice = None
        if notice is not None: notice.close()

    def update_job_elapsed(self, outcome=None):
        started = getattr(self, '_job_started_at', None)
        if started is None:
            return
        seconds = max(0, int(time.monotonic() - started))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        state = outcome or ('Đang dừng' if self.cancel_event.is_set() else 'Đang xử lý')
        text = f'Thời gian xử lý: {hours:02d}:{minutes:02d}:{seconds:02d} · {state}'
        if self.elapsed_var.get() != text:
            self.elapsed_var.set(text)
        if outcome is not None:
            self._job_started_at = None

    def run_job(self, label, action, done, keep_partial=False, use_ai=True, on_error=None):
        if self.busy:return
        self._job_use_ai=use_ai
        self.busy=True;self.cancel_event.clear();self._latest_progress=None;self.status.set(label)
        self._job_started_at = time.monotonic()
        self.update_job_elapsed()
        self.start_processing_notice(label)
        if getattr(self,'_job_use_ai',True) and hasattr(self.app,'set_ai_processing'):self.app.set_ai_processing(True,label)
        if hasattr(self.app,'_summary_progressbar') and self.app._summary_progressbar.winfo_ismapped():self.app._summary_progressbar.start(25)
        for b in self.buttons:b.configure(state='disabled')
        self._done=done
        self._job_use_ai=use_ai
        self._job_error=on_error or self.error
        self._keep_partial=keep_partial
        self._job_state=self.state
        self._job_account=(self.app.current_username,self.app.current_login_key)
        def progress(text):
            if self.cancel_event.is_set():
                if keep_partial:return
                raise InterruptedError('Đã dừng; giữ nguyên các đoạn đã chốt.')
            self._latest_progress=text
        def run():
            try:self.events.put(('done',action(progress)))
            except Exception as exc:self.events.put(('error',exc))
        if self.provider.get() in (FREE_PROVIDER, 'deepseek-r1:8b', 'qwen3:8b', 'qwen3:4b-q4_K_M', 'qwen3:4b-q8_0') and use_ai:
            run_deepseek_free_async(
                self.app, label,
                lambda result: self.events.put(('done', result)),
                lambda exc: self.events.put(('error', exc)),
                task=lambda: action(progress), manage_progress=False,
                cancel=self.cancel_event, keep_partial=keep_partial,
            )
        else:
            threading.Thread(target=run,daemon=True).start()

    def drain(self):
        if self.busy:
            self.update_job_elapsed()
        progress=getattr(self,'_latest_progress',None)
        self._latest_progress=None
        if progress is not None and self.busy and not self.cancel_event.is_set():
            self.status.set(progress[:400])
            if getattr(self,'_job_use_ai',True) and hasattr(self.app,'set_ai_processing'):self.app.set_ai_processing(True,progress[:400])
            if hasattr(self.app,'status_text'):self.app.status_text.set(progress[:400])
            if hasattr(self.app,'summary_progress_text'):self.app.summary_progress_text.set(progress[:400])
        batch_changed=False
        try:
            for _ in range(20):
                kind,value=self.events.get_nowait()
                if kind=='batch_record':
                    if self._job_state is not getattr(self.app,'_ai_analysis_state',None) or self._job_account!=(self.app.current_username,self.app.current_login_key):continue
                    number,record,pending=value
                    self.app._batch_candidates=getattr(self.app,'_batch_candidates',{})
                    self.app._batch_runs=getattr(self.app,'_batch_runs',{})
                    self.app._batch_candidates[number]=record;self.app._batch_runs[number]=pending
                    batch_changed=True
                    continue
                if kind=='progress':
                    if not self.cancel_event.is_set():
                        self.status.set(str(value)[:400])
                        if hasattr(self.app,'status_text'):self.app.status_text.set(str(value)[:400])
                    continue
                self.busy=False
                self.stop_processing_notice()
                if getattr(self,'_job_use_ai',True) and hasattr(self.app,'set_ai_processing'):self.app.set_ai_processing(False,'Đã dừng.' if self.cancel_event.is_set() else 'Không thể hoàn thành xử lý.' if kind=='error' else 'Đã hoàn thành xử lý.')
                if hasattr(self.app,'_summary_progressbar'):self.app._summary_progressbar.stop()
                for b in self.buttons:b.configure(state='normal')
                if ((self.cancel_event.is_set() and not (getattr(self,'_keep_partial',False) and kind=='done')) or self._job_state is not getattr(self.app,'_ai_analysis_state',None)
                    or self._job_account != (self.app.current_username,self.app.current_login_key)):
                    self.status.set('Đã dừng; chưa áp dụng kết quả của bước đang xử lý.')
                    if self._job_state is not getattr(self.app,'_ai_analysis_state',None):self.reload_state()
                elif kind=='error':self._job_error(value)
                else:
                    try:
                        partial=getattr(self,'_keep_partial',False) and (self.cancel_event.is_set() or bool(getattr(value,'partial_reason',None)))
                        save_partial=True
                        if partial:
                            rows=value[0] if isinstance(value,tuple) and value else []
                            # Tự động giữ phần đã đọc hợp lệ, cảnh báo chưa đầy đủ.
                            save_partial=bool(rows)
                        if save_partial:
                            self._done(value)
                            if partial:self.status.set('Đã lưu phần số liệu đọc được; chưa đọc hết nguồn, cần đối chiếu số liệu trước khi xác nhận. '+self.status.get())
                        else:self.status.set('Đã bỏ kết quả lần đọc bị dừng; giữ nguyên dữ liệu trước đó.')
                    except Exception as exc:
                        kind='error'
                        self._job_error(exc)
                self.update_job_elapsed('Đã dừng' if self.cancel_event.is_set() or self._job_state is not getattr(self.app,'_ai_analysis_state',None) or self._job_account != (self.app.current_username,self.app.current_login_key) else 'Lỗi' if kind=='error' else 'Hoàn tất')
                if hasattr(self.app,'status_text'):self.app.status_text.set(self.status.get())
        except Empty:pass
        except Exception as exc:self._job_error(exc)
        try:
            if batch_changed:
                if hasattr(self.app,'refresh_result_summary'):self.app.refresh_result_summary()
                if hasattr(self.app,'batch_design_view'):self.app.batch_design_view.refresh()
        except Exception as exc:self._job_error(exc)
        finally:
            if self.winfo_exists():self.after(100,self.drain)

    def mapping_review(self, context):
        self.status.set('Chưa ánh xạ; chưa liên kết số liệu. Dữ liệu cũ được giữ nguyên.')
        from mapping_gate import (strict_json,validate_mapping,save_mapping_memory,
                                  fingerprint,audit_event)
        from ai_analysis_data import _mapping_storage
        columns=deepcopy(context['columns']);original_columns=deepcopy(context.get('original_columns',columns))
        registry=context['registry'];data_rows=context['rows']
        proposal={'task':'column_mapping','items':[],'khong_chac':[]}
        try:proposal=strict_json(context.get('answer',''))
        except ValueError:pass  # Invalid AI content is NOT partially retained.
        initial={x['cot_id']:x for x in proposal['items']}
        variables={}
        target_labels={'Không ánh xạ':'unknown',**{spec['label']:key for key,spec in registry.items()}}
        target_display={value:label for label,value in target_labels.items()}
        group_labels={'':'','Dung trọng tự nhiên':'natural_density','Nén cố kết':'consolidation','Cắt trực tiếp':'direct_shear','Ba trục không cố kết':'triaxial_UU','Ba trục cố kết hữu hiệu':'triaxial_CU_effective','Không thoát nước':'undrained','Cắt cánh nguyên trạng':'vane_undisturbed'}
        group_display={value:label for label,value in group_labels.items()}
        popup=tk.Toplevel(self);popup.title('Xác nhận ánh xạ cột');popup.geometry('1050x640');popup.transient(self.app)
        ttk.Label(popup,text=context.get('reason','')+'\nChọn thông số, đơn vị và nhóm theo file nguồn. Chưa liên kết dữ liệu.',wraplength=990).pack(fill='x',padx=10,pady=8)
        frame=ttk.Frame(popup);frame.pack(fill='both',expand=True)
        canvas=tk.Canvas(frame);scroll=ttk.Scrollbar(frame,command=canvas.yview);canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        body=ttk.Frame(canvas);body_window=canvas.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(body_window,width=event.width))
        body.columnconfigure(0,weight=3);body.columnconfigure(1,weight=2)
        body.columnconfigure(2,weight=1);body.columnconfigure(3,weight=2)
        for index,title in enumerate(('Cột nguồn','Thông số đích','Đơn vị nguồn','Nhóm thí nghiệm')):
            ttk.Label(body,text=title).grid(row=0,column=index,sticky='w',padx=5,pady=5)
        units=sorted({u for spec in registry.values() for u in spec['units']})
        groups=sorted({g for spec in registry.values() for g in spec.get('groups',[])})
        for row_index,col in enumerate(columns,1):
            cid=col['cot_id'];entry=initial.get(cid,{})
            ttk.Label(body,text=str(cid)+' · '+col['label'],wraplength=340).grid(row=row_index,column=0,sticky='w',padx=5,pady=4)
            target=tk.StringVar(value=target_display.get(entry.get('thong_so'),'Không ánh xạ'))
            unit=tk.StringVar(value=col.get('unit',''));group=tk.StringVar(value=group_display.get(col.get('group',''),''))
            ttk.Combobox(body,textvariable=target,values=list(target_labels),state='readonly',width=20).grid(row=row_index,column=1,sticky='ew',padx=3)
            ttk.Combobox(body,textvariable=unit,values=['']+units,state='readonly',width=14).grid(row=row_index,column=2,sticky='ew',padx=3)
            ttk.Combobox(body,textvariable=group,values=list(group_labels),state='readonly',width=23).grid(row=row_index,column=3,sticky='ew',padx=3)
            variables[cid]=(target,unit,group)
        notice=tk.StringVar();ttk.Label(popup,textvariable=notice,wraplength=990).pack(fill='x',padx=10)
        def confirm():
            try:
                items=[];overrides={}
                for col in columns:
                    target,unit,group=variables[col['cot_id']]
                    col['unit']=unit.get();col['group']=group_labels[group.get()]
                    overrides[str(col['cot_id'])]={'unit':col['unit'],'group':col['group']}
                    items.append({'cot_id':col['cot_id'],'thong_so':target_labels[target.get()],'do_tin_cay':1.0,'ly_do':'Người dùng xác nhận ánh xạ'})
                import json
                answer=json.dumps({'task':'column_mapping','items':items,'khong_chac':[]},ensure_ascii=False)
                actor=self.app.current_username or 'Người dùng'
                signature=fingerprint([context['chunk']['source'],columns,data_rows])
                checked=validate_mapping(answer,columns,data_rows,registry,required=tuple(context.get('required',('code',))),confirmed_by=actor,source_signature=signature)
                if checked.status!='accepted':raise ValueError('\n'.join(checked.reasons))
                memory,log=_mapping_storage()
                audit_event(log,{'event':'manual_mapping','actor':actor,'source':context['chunk']['source'],'answer':answer,'overrides':overrides,'validation':checked.status})
                from geotech_memory import GeotechMemory,project_scope
                scope=context.get('memory_scope') or project_scope(self.data_project(),self.app.current_username or '')
                GeotechMemory().remember_mapping(scope,original_columns,registry,answer,
                    overrides=overrides,original_answer=context.get('answer',''),
                    source=context['chunk']['source'],actor=actor,confirmed=True)
                # Quy tắc mới chỉ lưu theo dự án trong SQLite, không ghi toàn cục JSON.
                popup.destroy()
                self._mapping_retry_paths=self._mapping_selected_paths
                self.read_source(self._mapping_retry_kind)
            except Exception as exc:notice.set(str(exc))
        def dictionary():
            from mapping_gate import alias_mapping,strict_json
            matched=strict_json(alias_mapping(columns,registry))
            for entry in matched['items']:variables[entry['cot_id']][0].set(target_display[entry['thong_so']])
            notice.set('Chỉ dùng alias khớp chính xác; cột chưa chắc giữ unknown.')
        actions=ttk.Frame(popup);actions.pack(pady=8)
        ttk.Button(actions,text='Tra ánh xạ',command=dictionary).pack(side='left',padx=5)
        ttk.Button(actions,text='Xác nhận ánh xạ',command=confirm).pack(side='left',padx=5)
        ttk.Button(actions,text='Hủy',command=popup.destroy).pack(side='left',padx=5)

    def _import_snapshot(self):
        return {'state':deepcopy(self.state),'project':deepcopy(self.app.project),
                'options':deepcopy(self.options),'mode':self.app.design_mode.get(),
                'vars':{key:var.get() for key,var in getattr(self.app,'vars',{}).items()},
                'attrs':{key:deepcopy(getattr(self.app,key)) for key in
                         ('_choice_group_results','_cdm_reports','_step_result_cache','chart_data') if hasattr(self.app,key)}}

    def _restore_import(self, snapshot):
        self.state.clear();self.state.update(deepcopy(snapshot['state']))
        self.app.project=deepcopy(snapshot['project'])
        if snapshot['mode']=='TÍNH MỘT ĐOẠN' and 'template' in snapshot['state']:self.state['template']=self.app.project
        self.options=deepcopy(snapshot['options'])
        for key,value in snapshot['attrs'].items():setattr(self.app,key,deepcopy(value))
        self.app.populate()
        for key,value in snapshot.get('vars',{}).items():
            if key in getattr(self.app,'vars',{}):self.app.vars[key].set(value)
        self.refresh()
        view=getattr(self.app,'geology_statistics_view',None)
        if view is not None:view.refresh()

    def _resolve_missing_sample_depths(self, rows, paths, warnings):
        """Pause the Tk import until cell locations are supplied or explicitly skipped."""
        missing=[]
        for material in rows:
            if not isinstance(material,dict) or 'values' not in material:continue
            for sample in material.get('samples') or [material]:
                meta=sample.get('strength_sample') or sample
                point=meta.get('test_depth')
                start=meta.get('depth_from') if meta.get('depth_from') is not None else point
                end=meta.get('depth_to') if meta.get('depth_to') is not None else point
                if start is None or end is None:missing.append((sample,meta))
        if not missing:return True
        excel=[str(Path(p).resolve()) for p in paths if Path(p).suffix.lower() in ('.xlsx','.xlsm','.xls')]
        popup=tk.Toplevel(self);popup.title('AI cần vị trí độ sâu mẫu');popup.transient(self.winfo_toplevel())
        popup.geometry('920x520');popup.protocol('WM_DELETE_WINDOW',popup.destroy)
        ttk.Label(popup,text=f'Tôi chưa tìm thấy độ sâu của {len(missing)} mẫu. Dùng luôn file vừa đọc; chỉ nhập cột Từ/Đến cho sheet.\nVí dụ: cột 7 và 8 (hoặc G và H). Nhập D11 cũng được hiểu là cột D; hàng lấy theo từng mẫu.\nBấm Cập nhật để lấy số liệu ngay. Mẫu điểm: cùng cột; đơn vị mét. Bỏ qua mới cho phép trống.',padding=10,wraplength=890).pack(fill='x')
        bulk=ttk.Frame(popup,padding=6);bulk.pack(fill='x')
        bulk_vars=[tk.StringVar(value=excel[0] if len(excel)==1 else ''),tk.StringVar(),tk.StringVar(),tk.StringVar()]
        suggested_sheets={str(sample.get('source','')).split('!',1)[0].split(' / ')[-1].strip("' ") for sample,_ in missing if '!' in str(sample.get('source',''))}
        if len(suggested_sheets)==1:bulk_vars[1].set(next(iter(suggested_sheets)))
        ttk.Label(bulk,text='Nguồn: file vừa đọc').pack(side='left',padx=4)
        for label,var,width in zip(('Sheet','Cột Từ','Cột Đến'),bulk_vars[1:],(16,8,8)):
            ttk.Label(bulk,text=label).pack(side='left',padx=3)
            ttk.Entry(bulk,textvariable=var,width=width).pack(side='left')
        canvas=tk.Canvas(popup,highlightthickness=0);scroll=ttk.Scrollbar(popup,orient='vertical',command=canvas.yview)
        scroll.pack(side='right',fill='y');canvas.pack(fill='both',expand=True);canvas.configure(yscrollcommand=scroll.set)
        body=ttk.Frame(canvas);canvas.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        for col,label in enumerate(('Mẫu / nguồn đã đọc','File','Sheet','Ô Từ (m)','Ô Đến (m)')):ttk.Label(body,text=label).grid(row=0,column=col,padx=4,pady=5)
        entries=[]
        saved_locations=self.state.setdefault('sample_depth_locations',{})
        import hashlib
        hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in excel}
        for i,(sample,meta) in enumerate(missing,1):
            label=str(meta.get('borehole_name') or sample.get('borehole_name') or '')+' / '+str(meta.get('sample_id') or sample.get('sample_id') or sample.get('code') or i)
            ttk.Label(body,text=label+'\n'+str(sample.get('source',''))[:75],wraplength=260).grid(row=i,column=0,sticky='w',padx=4,pady=4)
            origin=str(Path(sample['_source_file']).resolve()) if sample.get('_source_file') else ''
            named=[p for p in excel if Path(p).name in str(sample.get('source',''))]
            origin=origin if origin in excel else named[0] if len(named)==1 else excel[0] if len(excel)==1 else ''
            variables=[tk.StringVar(value=origin),tk.StringVar(),tk.StringVar(),tk.StringVar()]
            identity=str(meta.get('borehole_name') or sample.get('borehole_name') or '')+'|'+str(meta.get('sample_id') or sample.get('sample_id') or sample.get('code') or i)+'|'+str(sample.get('source',''))
            for filename in excel:
                key='sample_depth:'+hashes[filename]+':'+hashlib.sha256(identity.encode()).hexdigest()
                stored=saved_locations.get(key)
                if not stored:
                    try:
                        from geotech_memory import GeotechMemory,project_scope
                        hits=GeotechMemory().retrieve(project_scope(self.data_project(),self.app.current_username or ''),key,limit=5,max_chars=12000)
                        hit=next((h for h in hits if h.get('title')==key),None)
                        candidate=json.loads(hit['body']) if hit else None
                        if isinstance(candidate,dict) and candidate.get('file_sha256')==hashes[filename] and candidate.get('unit')=='m' and all(isinstance(candidate.get(k),str) for k in ('sheet','from_cell','to_cell')):stored=candidate
                    except Exception:pass  # A memory outage must still allow the user to supply cells.
                if stored:
                    for var,value in zip(variables,(filename,stored['sheet'],stored['from_cell'],stored['to_cell'])):var.set(value)
                    break
            ttk.Label(body,text=Path(origin).name if origin else 'Nguồn chưa được ghi nhận',width=27).grid(row=i,column=1,padx=3)
            for col,var in enumerate(variables[1:],2):ttk.Entry(body,textvariable=var,width=12).grid(row=i,column=col,padx=3)
            entries.append((sample,meta,variables,identity))
        outcome={'accepted':False}
        def apply_columns():
            try:
                _,sheet,left,right=[v.get().strip() for v in bulk_vars]
                if not sheet:raise ValueError('Nhập tên sheet của nguồn vừa đọc.')
                left,right=_depth_column_letter(left),_depth_column_letter(right)
                applied=0;unknown=[]
                for sample,meta,variables,identity in entries:
                    source=str(sample.get('source',''))
                    filename=variables[0].get().strip()
                    if filename not in excel:
                        unknown.append(str(meta.get('borehole_name',''))+'/'+str(meta.get('sample_id','')));continue
                    row=_sample_source_row(source,sheet)
                    if row is None:
                        unknown.append(str(meta.get('borehole_name',''))+'/'+str(meta.get('sample_id','')));continue
                    for var,value in zip(variables,(filename,sheet,left+str(row),right+str(row))):var.set(value)
                    applied+=1
                if not applied:raise ValueError('Chưa xác định được hàng mẫu của sheet này từ nguồn. Không tự gán theo thứ tự; kiểm tra sheet/file hoặc bổ sung vị trí cho mẫu chưa rõ.')
                self.status.set(f'Đang lấy độ sâu theo cột cho {applied} mẫu.'+(f' {len(unknown)} mẫu thuộc nguồn khác/chưa rõ hàng.' if unknown else ''))
                read_cells()
            except ValueError as exc:messagebox.showerror('Chưa áp dụng cột độ sâu',str(exc),parent=popup)
        ttk.Button(bulk,text='Cập nhật theo cột',command=apply_columns).pack(side='left',padx=6)
        def read_cells():
            import re,math
            from ai_analysis_data import open_source_excel
            updates=[];books={}
            try:
                for sample,meta,variables,identity in entries:
                    filename,sheet,left,right=[v.get().strip() for v in variables]
                    if filename not in excel:raise ValueError('Lượt đọc chưa ghi nhận nguồn của mẫu này; đọc lại nguồn để nhận file tự động.')
                    if filename not in books:books[filename]=open_source_excel(filename)
                    book=books[filename]
                    if sheet not in book.sheetnames:raise ValueError('Sheet không tồn tại: '+sheet+'; các sheet: '+', '.join(book.sheetnames))
                    values=[]
                    for address in (left,right):
                        if not re.fullmatch(r'[A-Za-z]{1,3}[1-9][0-9]{0,6}',address):raise ValueError('Nhập địa chỉ ô như G12, H12; không nhập số độ sâu.')
                        value=book[sheet][address.upper()].value
                        if isinstance(value,bool) or value is None:raise ValueError(sheet+'!'+address+': ô trống hoặc không có số được lưu. Kiểm tra công thức/ô gộp và chỉ ô chứa số thực tế.')
                        number=float(str(value).strip().replace(',','.'))
                        if not math.isfinite(number) or number<0:raise ValueError('Độ sâu phải là số hữu hạn không âm theo mét.')
                        values.append(number)
                    if values[1]<values[0]:raise ValueError('Độ sâu Đến nhỏ hơn Từ; kiểm tra hai ô nguồn.')
                    if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=hashes[filename]:raise ValueError('File nguồn đã thay đổi; hủy nhập và đọc lại.')
                    updates.append((sample,meta,values,filename,sheet,left.upper(),right.upper(),identity))
                memory_records=[]
                for sample,meta,values,filename,sheet,left,right,identity in updates:
                    meta['depth_from'],meta['depth_to']=values
                    sample['depth_from'],sample['depth_to']=values
                    sample['source']=str(sample.get('source',''))+'; độ sâu: '+Path(filename).name+' / '+sheet+'!'+left+'/'+right+' (m)'
                    key='sample_depth:'+hashes[filename]+':'+hashlib.sha256(identity.encode()).hexdigest()
                    location={'sheet':sheet,'from_cell':left,'to_cell':right,'unit':'m','status':'read_from_source','file_sha256':hashes[filename]}
                    saved_locations[key]=location
                    memory_records.append({'key':key,'value':location,'source':Path(filename).name+' / '+sheet+'!'+left+'/'+right})
                if getattr(self.app,'current_user_role','')=='admin':
                    from geotech_memory import project_scope
                    credentials={'username':self.app.current_username,'key':self.app.current_login_key}
                    memory_scope=project_scope(self.data_project(),self.app.current_username or '')
                    api_url=self.app.API_BASE_URL
                    def sync_locations():
                        try:
                            from geotech_memory import GeotechMemory,packed,digest
                            from geotech_memory_sync import sync_shared_memory
                            ids=[];memory=GeotechMemory()
                            for record in memory_records:
                                payload={'topic':'agent_mapping','title':record['key'],'body':packed(record['value']),'source':record['source']}
                                memory.add_knowledge(memory_scope,'agent_mapping',record['key'],payload['body'],source=record['source'],actor=credentials['username'],confirmed=True)
                                ident=digest(['knowledge',payload,credentials['username']]);ids.append(ident)
                                with memory.connection() as db:db.execute("INSERT OR IGNORE INTO shared_memory_outbox VALUES(?,?,?,?,datetime('now'))",(ident,credentials['username'],'knowledge',packed(payload)))
                            response=sync_shared_memory(api_url,credentials,memory_scope,True,outbox_ids=tuple(ids))
                            self.events.put(('progress','Đã lưu vị trí độ sâu lên server.' if response.get('success') and response.get('remaining',1)==0 else 'Chưa xác nhận lưu server; vị trí đang chờ đồng bộ lại.'))
                        except Exception:
                            self.events.put(('progress','Chưa xác nhận lưu vị trí lên server; kiểm tra kết nối và đọc lại khi cần.'))
                    threading.Thread(target=sync_locations,daemon=True).start()
                outcome['accepted']=True
                warnings.append('Người dùng đã chỉ ô độ sâu; Python đọc và kiểm tra trực tiếp trước khi nhập.')
                popup.destroy()
            except Exception as exc:messagebox.showerror('Chưa đọc được độ sâu',str(exc),parent=popup)
            finally:
                for book in books.values():book.close()
        def skip():
            warnings.append('Người dùng chọn Bỏ qua sau câu hỏi vị trí: độ sâu chưa xác định được từ nguồn, giữ trống; không thay bằng 0.')
            for sample,meta in missing:sample['missing_depth_reason']='Người dùng bỏ qua yêu cầu chỉ vị trí ô nguồn.'
            outcome['accepted']=True;popup.destroy()
        controls=ttk.Frame(popup,padding=8);controls.pack(fill='x')
        ttk.Button(controls,text='Cập nhật số liệu',command=lambda:apply_columns() if any(v.get().strip() for v in bulk_vars[2:]) else read_cells()).pack(side='left')
        ttk.Button(controls,text='Bỏ qua — cho phép độ sâu trống',command=skip).pack(side='left',padx=8)
        ttk.Button(controls,text='Hủy nhập',command=popup.destroy).pack(side='right')
        self.status.set('AI đang chờ bạn chỉ vị trí độ sâu mẫu; chưa cập nhật bảng.')
        if entries and all(all(v.get().strip() for v in variables) for _,_,variables,_ in entries):
            read_cells()
            if outcome['accepted']:return True
        popup.grab_set();self.wait_window(popup)
        return outcome['accepted']

    def _apply_import_automatically(self, result, commit, paths, source_hashes=None, source_stats=None):
        """Cập nhật dữ liệu hợp lệ trên luồng Tk; lỗi thì hoàn tác giao dịch."""
        import json,hashlib
        from mapping_gate import audit_event,apply_mapping,ValidatedMapping
        from ai_analysis_data import _mapping_storage
        rows,warnings=result
        if rows and not self._resolve_missing_sample_depths(rows,paths,warnings):
            self.status.set('Đã hủy nhập: chưa có vị trí độ sâu; dữ liệu trước đó được giữ nguyên.')
            return
        if not rows:
            details='\n'.join(str(w) for w in warnings if not str(w).startswith('__MAPPING_'))
            self.last_ai_response='Không có số liệu mới để cập nhật. Dữ liệu cũ được giữ nguyên.\n'+(details or 'Lượt đọc kết thúc nhưng không trả dòng số liệu hoặc nguyên nhân; cần kiểm tra phản hồi dịch vụ và cấu trúc file nguồn.')
            self.status.set('Không có số liệu mới để cập nhật. '+self.warning_summary(warnings))
            self.show_ai_response()
            return
        if self.busy:raise ValueError('Đang xử lý tác vụ khác; chưa cập nhật dữ liệu.')
        original_state=self.state
        baseline=self._import_snapshot()
        original_mode=self.app.design_mode.get()
        if source_stats and {str(path):_source_file_stamp(path) for path in paths}!=source_stats:
            raise ValueError('File nguồn đổi trước khi áp dụng; giữ dữ liệu cũ.')
        if source_hashes is None:
            source_hashes={str(path):hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}
        registry=json.loads(Path(__file__).with_name('parameter_registry.json').read_text(encoding='utf-8'))
        messages=[]
        for warning in warnings:
            if warning.startswith('__MAPPING_CONTEXT__'):
                context=json.loads(warning[len('__MAPPING_CONTEXT__'):])
                receipt=ValidatedMapping(**context['receipt'])
                if receipt.status!='accepted':raise ValueError('Ánh xạ chưa hợp lệ; không tự liên kết dữ liệu.')
                source_rows=[{int(k):v for k,v in row.items()} for row in context['rows']]
                apply_mapping(receipt,context['columns'],source_rows,registry,{},
                    required=tuple(context['required']),confirmed_by='Python tự động',
                    source_signature=receipt.source_signature)
            elif not warning.startswith('__MAPPING_PREVIEW__'):
                messages.append(warning)
        _,log=_mapping_storage()
        audit_event(log,{'event':'prepare_import','actor':'Python tự động',
            'account':self.app.current_username,'mode':original_mode,'files':source_hashes})
        try:
            commit((deepcopy(rows),messages))
            after=self._import_snapshot()
            audit_event(log,{'event':'committed_import','actor':'Python tự động',
                'account':self.app.current_username,'mode':original_mode,'files':source_hashes})
        except BaseException:
            self._restore_import(baseline)
            raise
        self._import_undo=(original_state,baseline)
        self._import_after=after
        def undo():
            try:
                token=getattr(self,'_import_undo',None)
                if self.busy or not token or token[0] is not self.state or token[1]['mode']!=self.app.design_mode.get():
                    raise ValueError('Không có lần nhập phù hợp để hoàn tác.')
                if repr(self._import_snapshot())!=repr(getattr(self,'_import_after',None)):
                    raise ValueError('Dữ liệu đã thay đổi sau nhập; không hoàn tác đè lên thay đổi mới.')
                self._restore_import(token[1]);self._import_undo=None
                self.status.set('Đã hoàn tác lần nhập; khôi phục dữ liệu trước đó.')
            except Exception as exc:self.status.set(str(exc))
        self._undo_last_import=undo

    def preview_import(self, result, commit, paths):
        import json,hashlib
        from mapping_gate import audit_event
        from ai_analysis_data import _mapping_storage
        rows,warnings=result
        if not rows:
            self.status.set('Chưa có số liệu hợp lệ; dữ liệu cũ được giữ nguyên. '+self.warning_summary(warnings));return
        def hashes():return {str(path):hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}
        read_summary=getattr(self,'_pending_read_summary','')
        original_hashes=hashes();original_state=self.state
        original_mode=self.app.design_mode.get();original_account=(self.app.current_username,self.app.current_login_key)
        baseline=self._import_snapshot()
        popup=tk.Toplevel(self);popup.title('Xem trước liên kết dữ liệu');popup.geometry('1050x640');popup.transient(self.app)
        ttk.Label(popup,text='Python đã đọc ô nguồn. Chỉ bấm Áp dụng mới cập nhật bảng dữ liệu. Kiểm tra đơn vị, lớp đất và các cảnh báo.',wraplength=990).pack(fill='x',padx=10,pady=8)
        if read_summary:
            summary_frame=ttk.Frame(popup);summary_frame.pack(fill='x',padx=10,pady=4)
            summary_box=tk.Text(summary_frame,height=7,wrap='word',font=(UI_FONT,11))
            summary_scroll=ttk.Scrollbar(summary_frame,command=summary_box.yview)
            summary_box.configure(yscrollcommand=summary_scroll.set)
            summary_box.pack(side='left',fill='both',expand=True)
            summary_scroll.pack(side='right',fill='y')
            summary_box.insert('1.0',read_summary);summary_box.configure(state='disabled')
        table=ttk.Treeview(popup,columns=('source','target','units','samples','confidence'),show='headings')
        for key,label,width in [('source','Cột nguồn / ô nguồn',350),('target','Thông số đích',140),('units','Đơn vị gốc → đích',160),('samples','Ba giá trị sau đổi',220),('confidence','Tin cậy',80)]:table.heading(key,text=label);table.column(key,width=width)
        table.pack(fill='both',expand=True,padx=10)
        messages=[];mapping_contexts=[]
        for warning in warnings:
            if warning.startswith('__MAPPING_PREVIEW__'):
                for entry in json.loads(warning[len('__MAPPING_PREVIEW__'):]):
                    table.insert('','end',values=(entry['source'],entry['target'],entry['unit_source']+' → '+entry['unit_target'],str(entry['samples']),entry['confidence']))
            elif warning.startswith('__MAPPING_CONTEXT__'):
                mapping_contexts.append(json.loads(warning[len('__MAPPING_CONTEXT__'):]))
            else:messages.append(warning)
        if not table.get_children():
            from pathlib import Path as P
            registry=json.loads(P(__file__).with_name('parameter_registry.json').read_text(encoding='utf-8'))
            for item in rows:
                for key,value in item.get('values',{}).items():
                    if key=='name':continue
                    table.insert('','end',values=(item.get('source',''),key,'Ô nguồn đã đối chiếu → '+registry.get(key,{}).get('unit','xem nguồn'),str(value), 'Python'))
        notice=tk.StringVar(value='\n'.join(messages)[:5000]);ttk.Label(popup,textvariable=notice,wraplength=990).pack(fill='x',padx=10,pady=6)
        def apply():
            try:
                if self.busy or self.state is not original_state or self.app.design_mode.get()!=original_mode or (self.app.current_username,self.app.current_login_key)!=original_account:
                    raise ValueError('Phiên/luồng/tài khoản đã đổi; đọc lại nguồn trước khi áp dụng.')
                if hashes()!=original_hashes:raise ValueError('File nguồn đã đổi; đọc lại trước khi áp dụng.')
                current=self._import_snapshot()
                if repr(current)!=repr(baseline):raise ValueError('Dữ liệu đã đổi khi xem trước; đọc lại trước khi áp dụng.')
                from mapping_gate import apply_mapping,ValidatedMapping
                registry=json.loads(Path(__file__).with_name('parameter_registry.json').read_text(encoding='utf-8'))
                for context in mapping_contexts:
                    receipt=ValidatedMapping(**context['receipt'])
                    source_rows=[{int(k):v for k,v in row.items()} for row in context['rows']]
                    stage={}
                    apply_mapping(receipt,context['columns'],source_rows,registry,stage,
                                  required=tuple(context['required']),confirmed_by=self.app.current_username or 'Người dùng',
                                  source_signature=receipt.source_signature)
                _,log=_mapping_storage()
                audit_event(log,{'event':'prepare_import','actor':self.app.current_username,'mode':original_mode,'files':original_hashes,'rows':rows})
                try:
                    commit((deepcopy(rows),list(messages)))
                    if read_summary:
                        applied_summary=read_summary.replace('Chưa liên kết số liệu. Kiểm tra bảng xem trước và bấm Áp dụng để cập nhật.','Đã áp dụng dữ liệu bằng Python.')
                        self.last_ai_response=applied_summary
                        self.status.set(applied_summary)
                        if hasattr(self.app,'status_text'):self.app.status_text.set(applied_summary)
                    audit_event(log,{'event':'committed_import','actor':self.app.current_username,'mode':original_mode,'files':original_hashes})
                except BaseException:
                    self._restore_import(baseline)
                    raise
                self._import_undo=(original_state,baseline)
                popup.destroy()
            except Exception as exc:notice.set(str(exc))
        def undo():
            try:
                token=getattr(self,'_import_undo',None)
                if self.busy or not token or token[0] is not self.state or token[1]['mode']!=self.app.design_mode.get():raise ValueError('Không có lần nhập phù hợp để hoàn tác.')
                # Do not overwrite subsequent user edits/calculations.
                if repr(self._import_snapshot())!=repr(getattr(self,'_import_after',None)):raise ValueError('Dữ liệu đã thay đổi sau nhập; không hoàn tác đè lên thay đổi mới.')
                self._restore_import(token[1]);self._import_undo=None
                self.status.set('Đã hoàn tác lần nhập; khôi phục dữ liệu trước đó.')
            except Exception as exc:self.status.set(str(exc))
        actions=ttk.Frame(popup);actions.pack(pady=8)
        def apply_and_keep_undo():
            old_token=getattr(self,'_import_undo',None)
            apply()
            if getattr(self,'_import_undo',None) is not old_token:
                self._import_after=self._import_snapshot()
        ttk.Button(actions,text='Áp dụng',command=apply_and_keep_undo).pack(side='left',padx=5)
        ttk.Button(actions,text='Hủy',command=popup.destroy).pack(side='left',padx=5)
        # Undo remains accessible after the preview closes.
        self._undo_last_import=undo

    def read_source(self, kind):
        if self.busy:return
        target_names=None
        reviewed_boreholes=deepcopy(self.state['boreholes']) if kind in ('strength','spt') else None
        # Su measurements may be imported before CAD; unbound points remain
        # visible in the review table and never alter calculation strata.
        if kind=='boreholes':
            target_names=list(dict.fromkeys(str(section.get('borehole_name') or '').strip() for section in self.state.get('sections',[]) if str(section.get('borehole_name') or '').strip()))
            if not target_names:
                messagebox.showinfo('Danh sách lỗ khoan','Đọc Data để lấy tên lỗ khoan ở THSH cột G trước. Sau đó chọn trụ CAD/PDF để AI đọc các lỗ trong danh sách.',parent=self)
                self.read_data(show_holes=True,path=getattr(self.app,'_section_excel_path',None));return
        types=([('N-SPT CAD/PDF/Excel','*.dxf *.dwg *.pdf *.xlsx *.xlsm *.xls')] if kind=='spt' else [('Sức kháng Excel','*.xlsx *.xlsm *.xls')] if kind=='strength' else
               [('Địa chất Excel/PDF','*.xlsx *.xlsm *.xls *.pdf')] if kind in ('geology','curves') else [('Lỗ khoan CAD/PDF','*.dxf *.dwg *.pdf')])
        if kind in ('geology','strength','spt','curves','boreholes'):
            paths=getattr(self,'_mapping_retry_paths',None)
            self._mapping_retry_paths=None
            paths=paths or filedialog.askopenfilenames(parent=self,filetypes=types,
                title='Chọn trụ CAD/PDF để đọc địa tầng và đối chiếu với Data' if kind=='boreholes' else 'Chọn các file để AI đọc và gộp theo mã lớp (Ctrl/Shift để chọn nhiều)')
        else:
            path=filedialog.askopenfilename(parent=self,filetypes=types)
            paths=(path,) if path else ()
        if not paths:return
        known_sources=deepcopy((self.app.project if self.app.design_mode.get()=='TÍNH MỘT ĐOẠN' else self.state['template']).geology_statistics.get('imported_sources',{}))
        if not self.app.current_username or not self.app.current_login_key:
            self.error(ValueError('Đăng nhập trước khi đọc dữ liệu bằng AI.'));return
        credentials={'username':self.app.current_username,'key':self.app.current_login_key}
        from geotech_memory import project_scope
        memory_scope=project_scope(self.data_project(),self.app.current_username or '')
        shared_eligible=not self.app.is_trial()
        shared_role=getattr(self.app,'current_user_role','')
        provider={'Cloudflare AI':'cloudflare','Gemini':'gemini','DeepSeek':'deepseek','DeepSeek (g4f)':'deepseek_free','deepseek-r1:8b':'ollama','qwen3:8b':'ollama_qwen','qwen3:4b-q4_K_M':'ollama_qwen_4b_q4','qwen3:4b-q8_0':'ollama_qwen_4b_q8','Groq':'groq','Grok (xAI)':'grok','ChatGPT':'openai','NVIDIA AI':'nvidia','Kimi AI':'kimi'}[self.provider.get()]
        url=self.app.API_BASE_URL+'/api/chat/ai'
        import hashlib
        import_source_hashes={};import_source_stats={}
        source_order=[];completed_sources={}
        self._mapping_retry_kind=kind
        self._mapping_selected_paths=tuple(paths)
        def mark_sources():self.data_project().geology_statistics.setdefault('imported_sources',{}).update(completed_sources)
        def read_sources(progress):
            progress('Đang kiểm tra nguồn Excel trên tác vụ nền…')
            start_stats={str(path):_source_file_stamp(path) for path in paths}
            import_source_hashes.update({str(path):hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths})
            if {str(path):_source_file_stamp(path) for path in paths}!=start_stats:
                raise ValueError('File nguồn đổi trong khi kiểm tra; chưa đọc dữ liệu.')
            selected_paths=paths;duplicate_notes=[]
            if kind in ('geology','strength','spt','curves'):
                from ai_analysis_data import unique_data_sources,data_import_scope
                selected_paths,duplicate_notes=unique_data_sources(paths,cancel=self.cancel_event.is_set,
                    known_sources=known_sources,scope=data_import_scope(kind))
            if not selected_paths:return [],duplicate_notes
            if kind=='geology':
                import openpyxl
                from ai_analysis_data import excel_layer_evidence, open_source_excel
                for path in selected_paths:
                    if Path(path).suffix.lower() not in ('.xlsx','.xlsm','.xls'):continue
                    book=open_source_excel(path)
                    try:
                        for sheet in book:
                            for code in excel_layer_evidence(sheet).values():
                                if code.casefold() not in source_order:source_order.append(code.casefold())
                    finally:book.close()
            from geotech_memory_sync import sync_shared_memory
            shared_sync=sync_shared_memory(self.app.API_BASE_URL,credentials,memory_scope,shared_eligible)
            if progress:progress(shared_sync['message'])
            local_post = make_local_post(self.cancel_event, engine=provider if provider in ('ollama','ollama_qwen','ollama_qwen_4b_q4','ollama_qwen_4b_q8') else 'g4f') if provider in ('deepseek_free', 'ollama', 'ollama_qwen','ollama_qwen_4b_q4','ollama_qwen_4b_q8') else None
            result=request_extraction_files(selected_paths,kind,credentials,url,provider,progress,
                self.cancel_event.is_set,post=local_post,target_names=target_names,
                reviewed_boreholes=reviewed_boreholes,completed_sources=completed_sources,memory_scope=memory_scope)
            if {str(path):hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in paths}!=import_source_hashes:
                raise ValueError('File nguồn đổi trong khi đọc; chưa áp dụng dữ liệu.')
            end_stats={str(path):_source_file_stamp(path) for path in paths}
            if end_stats!=start_stats:raise ValueError('File nguồn đổi trong khi đọc; chưa áp dụng dữ liệu.')
            if shared_role=='admin' and not self.cancel_event.is_set() and not getattr(result,'partial_reason',None):
                try:
                    if progress:progress('Đã đọc nguồn; đang gửi kinh nghiệm biểu mẫu của admin lên server…')
                    from geotech_memory_sync import submit_admin_read_experience
                    experience=submit_admin_read_experience(self.app.API_BASE_URL,credentials,memory_scope,shared_eligible,selected_paths,role=shared_role)
                    if progress:progress(experience['message'])
                    result[1].append(experience['message'])
                except Exception as exc:
                    result[1].append('Chưa gửi được kinh nghiệm admin; kết quả đọc vẫn được giữ: '+str(exc))
            import_source_stats.update(end_stats)
            result[1].extend(duplicate_notes)
            return result
        def done(result):
            if import_source_stats and {str(path):_source_file_stamp(path) for path in paths}!=import_source_stats:
                raise ValueError('File nguồn đổi sau khi đọc; chưa áp dụng dữ liệu.')
            self._pending_read_summary=''
            self._pending_mapping_context=None
            self._apply_import_automatically(result,done_confirmed,paths,
                source_hashes=import_source_hashes,source_stats=import_source_stats)
        def done_confirmed(result):
            rows,warnings=result
            if kind=='boreholes':self.state['data_borehole_names']=list(target_names or [])
            import_summary=''
            if kind in ('geology','strength','spt','curves') and rows:
                from ai_analysis_data import align_borehole_samples
                rows,alignment_notes=align_borehole_samples(self.state,rows,kind)
                warnings.extend(alignment_notes)
            if kind in ('geology','strength','spt','curves') and rows:
                from ai_analysis_data import register_test_boreholes
                import_summary=register_test_boreholes(self.state,rows,kind)+' '
                view=getattr(self.app,'geology_statistics_view',None)
                if view is not None and hasattr(view,'borehole_import_notice'):
                    view.borehole_import_notice.set(self.state['last_borehole_import_summary'])
            if kind=='geology':
                vane_points=[r for r in rows if r.get('strength_sample')]
                if vane_points:
                    self.state.setdefault('strength_samples',[]).extend(deepcopy(vane_points))
                    warnings+=self.bind_strength_samples()
                    rows=[r for r in rows if not r.get('strength_sample')]
                    self.invalidate('geology_approved')
                    if not rows:
                        mark_sources()
                        self.status.set(import_summary+'Đã đọc số liệu cắt cánh vào Co; giữ tên lỗ và độ sâu, ghép lớp theo địa tầng đã xác nhận. '+self.warning_summary(warnings))
                        self.app.switch_step(10)
                        view=getattr(self.app,'geology_statistics_view',None)
                        if view is not None:view.show_strength_results([(sample.get('strength_sample') or {}).get('borehole_name') for sample in vane_points])
                        self.after_idle(self.review_strength_samples)
                        return
            if kind=='curves':
                has_ep=any(len(item.get('values',{}).get('ep',[]))>=2 and
                           len(item.get('values',{}).get('ep',[]))==len(item.get('values',{}).get('e',[])) for item in rows)
                has_cv=any(len(item.get('values',{}).get('cvp',[]))>=2 and
                           len(item.get('values',{}).get('cvp',[]))==len(item.get('values',{}).get('cv',[])) for item in rows)
                has_scalar_cv=any(item.get('cv_constant') is not None or item.get('values',{}).get('cv_constant') is not None for item in rows)
                if not (has_ep or has_cv or has_scalar_cv):
                    self.refresh()
                    self.status.set(import_summary+'Không có đường cong e-P/Cv-P hợp lệ để cập nhật. Bảng chỉ tiêu và thẻ đang xem được giữ nguyên. '+self.warning_summary(warnings))
                    return
                from ai_analysis_data import merge_lab_curve_materials
                self.state['materials'],notes=merge_lab_curve_materials(self.state['materials'],rows)
                if hasattr(self.app,'geology_statistics_view'):
                    self.app.geology_statistics_view.import_ai_samples(self.state['materials'])
                mark_sources()
                self.invalidate('geology_approved')
                detail='Đã cập nhật '
                detail+=('e-P' if has_ep else '')+(' và ' if has_ep and has_cv else '')+('Cv-P' if has_cv else '')
                if has_scalar_cv:detail+=(' và ' if has_ep or has_cv else '')+'Cv chính từ BTH'
                if has_ep and not has_cv:detail+='; nguồn không có Cv theo cấp áp lực nên không tạo đường Cv-P từ Cv trung bình'
                detail+=' theo mã lớp; kiểm tra và xác nhận lại. '
                self.status.set(import_summary+detail+self.warning_summary(warnings+notes))
                # Keep the current screen after updating laboratory measurements.
                return
            if kind in ('strength','spt'):
                self.state.setdefault('spt_samples' if kind=='spt' else 'strength_samples',[]).extend(deepcopy(rows))
                notes=self.bind_strength_samples()
                mark_sources()
                warnings+=notes
                self.invalidate('geology_approved')
                assigned=sum(bool(r.get('code')) and r.get('status','').startswith('Đã ghép') for r in self.state.get('spt_audit' if kind=='spt' else 'strength_audit',[]))
                total=len(self.state.get('spt_samples' if kind=='spt' else 'strength_samples',[]))
                self.status.set(import_summary+f'Đã đọc {"N-SPT" if kind=="spt" else "Su"}: ghép {assigned}/{total} điểm đúng lỗ khoan/lớp; phần còn lại giữ trong bảng đối chiếu. '+self.warning_summary(warnings))
                self.app.switch_step(10)
                view=getattr(self.app,'geology_statistics_view',None)
                if view is not None:
                    show=view.show_spt_results if kind=='spt' else view.show_strength_results
                    show([(sample.get('strength_sample') or {}).get('borehole_name') for sample in rows])
                self.after_idle(self.review_strength_samples if kind=='strength' else self.review_spt_samples)
                return
            key='materials' if kind=='geology' else 'boreholes'
            if kind=='geology':
                edited={m['code'].casefold():m for m in self.state[key] if m.get('average_edited')}
                if any(m['code'].casefold() in edited for m in rows):
                    raise ValueError('Lớp đã sửa giá trị trung bình: bắt đầu phiên mới để đọc lại mẫu của lớp đó.')
                self.state[key], average_warnings = average_materials(self.state[key]+rows)
                self.state[key]=[edited.get(m['code'].casefold(),m) for m in self.state[key]]
                warnings += average_warnings
                if source_order:
                    rank={code:index for index,code in enumerate(source_order)}
                    self.state[key].sort(key=lambda material:rank.get(material['code'].casefold(),len(rank)))
                    self.state['material_source_order']=list(source_order)
                else:
                    import re
                    def natural_code(material):
                        parts=re.split(r'(\d+)',material['code'].casefold())
                        return tuple((0,int(part)) if part.isdigit() else (1,part) for part in parts)
                    self.state[key].sort(key=natural_code)
                from geology_statistics import layer_order
                self.state[key].sort(key=lambda material:layer_order(material['code']))
                if hasattr(self.app,'geology_statistics_view'):
                    self.app.geology_statistics_view.import_ai_samples(self.state[key])
                    report=getattr(self.app.geology_statistics_view,'_last_import_report',{})
                    if report:
                        from geology_statistics import import_report_text
                        warnings.append(import_report_text(report));warnings+=report.get('conflicts',[])
                mark_sources()
                self.invalidate('geology_approved')
                self.status.set(import_summary+'Đã tổng hợp chỉ tiêu theo lớp; kiểm tra, chỉnh sửa rồi xác nhận. '+ self.warning_summary(warnings))
                self.app.switch_step(10)
                return
            if kind=='boreholes':
                from ai_analysis_data import borehole_key,merge_borehole_parts
                targets={borehole_key(name):name for name in target_names}
                grouped={};conflicts=set()
                for row in rows:
                    key=borehole_key(row['name'])
                    if key not in targets:
                        warnings.append('Bỏ qua trụ không khớp bảng phân đoạn: '+row['name'])
                        continue
                    row['name']=targets[key]
                    if key in grouped:
                        merged=merge_borehole_parts(grouped[key],row)
                        if merged is not None:grouped[key]=merged
                        elif grouped[key]['layers']!=row['layers'] or grouped[key]['elevation']!=row['elevation']:conflicts.add(key)
                    else:grouped[key]=row
                for key in conflicts:
                    if key not in grouped:
                        current=next((h for h in self.state['boreholes'] if borehole_key(h['name'])==key),None)
                        if current is not None:current.setdefault('validation_issues',[]).append('Trụ có số liệu mâu thuẫn; đối chiếu file trước khi xác nhận.')
                for key,row in grouped.items():
                    if key in conflicts:row.setdefault('validation_issues',[]).append('Có số liệu trụ mâu thuẫn giữa các phần/file; đối chiếu số liệu trước khi xác nhận.')
                    index=next((i for i,h in enumerate(self.state['boreholes']) if borehole_key(h['name'])==key),None)
                    if index is not None:
                        row['data_references']=deepcopy(self.state['boreholes'][index].get('data_references',[]))
                        if self.state['boreholes'][index].get('test_samples'):
                            row['test_samples']=deepcopy(self.state['boreholes'][index]['test_samples'])
                        self.state['boreholes'][index]=row
                    else:self.state['boreholes'].append(row)
                for section in self.state['sections']:
                    matched=grouped.get(borehole_key(section['borehole_name']))
                    if matched and matched.get('layers'):section['borehole_selected']=matched['name']
                    elif not any(borehole_key(h['name'])==borehole_key(section.get('borehole_selected','')) and h.get('layers') for h in self.state['boreholes']):
                        section['borehole_selected']=''
                warnings+=self.bind_strength_samples();self.invalidate('boreholes_approved')
                missing=[name for name in target_names if not any(borehole_key(h['name'])==borehole_key(name) and h.get('layers') for h in self.state['boreholes'])]
                self.status.set('Đã đọc và đối chiếu địa tầng với danh sách lỗ khoan. '+('Chưa có trụ: '+', '.join(missing)+'. ' if missing else '')+self.warning_summary(warnings))
                self.tabs.select(self.pages[1]);return
            identity='code' if kind=='geology' else 'name'
            existing={r[identity].casefold() for r in self.state[key]}
            for row in rows:
                original=row[identity];suffix=2
                while row[identity].casefold() in existing:
                    row[identity]=original+' ['+str(suffix)+']';suffix+=1
                if key=='materials':row['values']['name']=row['code']
                existing.add(row[identity].casefold());self.state[key].append(row)
            if kind=='boreholes':warnings+=self.bind_strength_samples()
            self.invalidate('geology_approved' if kind=='geology' else 'boreholes_approved')
            self.status.set(f'AI đọc {len(rows)} dòng; kiểm tra, chỉnh sửa rồi xác nhận. '+ self.warning_summary(warnings))
            self.tabs.select(self.pages[0 if kind=='geology' else 1])
        self.run_job(self.provider.get()+' đang đọc và gộp nguồn…',read_sources,done,keep_partial=True)

    def selected_index(self, tree):
        selected=tree.selection()
        if not selected:raise ValueError('Chọn một dòng để sửa.')
        return int(selected[0])

    def remove_row(self,key,tree):
        if self.busy:return
        try:
            index=self.selected_index(tree)
            self.state[key].pop(index)
            self.invalidate('geology_approved' if key=='materials' else 'boreholes_approved')
        except Exception as exc:self.error(exc)

    def bind_strength_samples(self):
        samples=self.state.get('strength_samples',[])
        spt_samples=self.state.get('spt_samples',[])
        if not samples and not spt_samples:return []
        signature=(tuple((h['name'],h.get('elevation'),tuple((l['code'],l.get('thickness')) for l in h['layers'])) for h in self.state['boreholes']),
                   tuple((s['code'],s['source'],s['values'].get('co'),repr(s.get('strength_sample'))) for s in samples),
                   tuple((m['code'],m.get('average_edited'),repr(m.get('borehole_spt')),repr(m.get('borehole_strength')),
                          tuple((p.get('depth_point_field'),p.get('borehole_name'),p.get('sample_id'),p.get('depth_from'),p.get('depth_to'),p.get('values',{}).get('co'),p.get('values',{}).get('spt_n')) for p in m.get('samples',[]) if p.get('depth_point_field'))) for m in self.state['materials']),repr(spt_samples))
        cached=getattr(self,'_strength_binding_cache',None)
        if cached and cached[0] is self.state and cached[1]==signature:return cached[2]
        from ai_analysis_data import assign_strength_by_depth
        rows,notes,audit=assign_strength_by_depth(self.state['materials'],samples,self.state['boreholes'])
        if spt_samples:
            rows,spt_notes,spt_audit=assign_strength_by_depth(rows,spt_samples,self.state['boreholes'],parameter='spt_n')
            notes+=spt_notes;self.state['spt_audit']=spt_audit
        self.state['materials']=rows;self.state['strength_audit']=audit
        self._strength_binding_cache=(self.state,signature,notes)
        statistics_view=getattr(self.app,'geology_statistics_view',None)
        if statistics_view is not None:
            data=statistics_view.store()
            data['samples']=[sample for sample in data['samples'] if not sample.get('depth_point_field') or sample.get('history')]
            statistics_view.import_ai_samples(rows)
        return notes

    def review_strength_samples(self):
        if self.busy:return
        popup=tk.Toplevel(self);popup.title('Kết quả đọc Su và ghép địa tầng');popup.geometry('1100x620');popup.transient(self.app)
        ttk.Label(popup,text='Nhấp đúp để sửa tên lỗ, độ sâu, mã lớp ghi trong Excel hoặc c₀ đã đổi về T/m². CAD phải có bề dày đúng; mẫu chưa khớp không được tự gán lớp.',wraplength=1040,padding=10).pack(fill='x')
        tree=self.table(popup,('Lỗ khoan','Độ sâu (m)','Lớp đã ghép / Excel','c₀ (T/m²)','Trạng thái ghép','Nguồn'),(160,95,95,100,380,430))
        def fill():
            tree.delete(*tree.get_children())
            self.bind_strength_samples()
            reports={(r['source'],r['hole']):r for r in self.state.get('strength_audit',[])}
            items=[]
            for i,sample in enumerate(self.state.get('strength_samples',[])):
                meta=sample.get('strength_sample') or {}
                report=reports.get((sample['source'],meta.get('borehole_name') or ''))
                items.append((('', 'end'),dict(iid=str(i),values=(meta.get('borehole_name') or '',self.fmt(meta.get('test_depth')),
                    (report.get('code') if report and report.get('status','').startswith('Đã ghép') else None) or meta.get('layer_code') or '',self.fmt(sample['values'].get('co')),report['status'] if report else 'Đã đọc Su; chưa đối chiếu địa tầng',sample['source']))))
            self.insert_table_batches(tree,items,self._render_generation)
        def edit(_event=None):
            try:
                index=self.selected_index(tree);sample=self.state['strength_samples'][index];meta=sample.get('strength_sample') or {}
                specs=[('hole','Tên lỗ khoan',meta.get('borehole_name'),None,False),
                       ('depth','Độ sâu điểm cắt (m)',meta.get('test_depth'),None,False),
                       ('layer','Mã lớp Excel (trống nếu chưa phân lớp)',meta.get('layer_code'),None,False),
                       ('co','c₀ / Su nguyên trạng (T/m²)',sample['values'].get('co'),None,False)]
                def save(raw):
                    depth=number(raw['depth'],'Độ sâu');co=number(raw['co'],'c₀')
                    if depth<0 or co<0:raise ValueError('Độ sâu/c₀ phải không âm.')
                    sample['strength_sample']=dict(meta,borehole_name=raw['hole'].strip(),test_depth=depth,layer_code=raw['layer'].strip() or None,test_elevation=None)
                    sample['values']['co']=co;sample['source']+=' · người dùng sửa'
                    self.bind_strength_samples();self.invalidate('geology_approved');fill()
                self.form('Sửa mẫu sức kháng',specs,save)
            except Exception as exc:self.error(exc)
        tree.bind('<Double-1>',edit)
        ttk.Button(popup,text='Sửa mẫu được chọn',command=edit).pack(pady=8)
        fill()

    def review_spt_samples(self):
        if self.busy:return
        popup=tk.Toplevel(self);popup.title('Kết quả đọc N-SPT và ghép địa tầng');popup.geometry('1100x620');popup.transient(self.app)
        ttk.Label(popup,text='Các mẫu SPT đã đọc được giữ riêng kể cả khi chưa có địa tầng. Nhấp đúp để sửa tên lỗ, độ sâu, mã lớp và N-SPT theo nguồn.',wraplength=1040,padding=10).pack(fill='x')
        tree=self.table(popup,('Lỗ khoan','Độ sâu (m)','Mã lớp','N-SPT (búa)','Trạng thái ghép','Nguồn'),(160,95,95,100,380,430))
        def fill():
            tree.delete(*tree.get_children())
            self.bind_strength_samples()
            reports={(r['source'],r['hole']):r for r in self.state.get('spt_audit',[])}
            for i,sample in enumerate(self.state.get('spt_samples',[])):
                meta=sample.get('strength_sample') or {}
                report=reports.get((sample['source'],meta.get('borehole_name') or ''))
                tree.insert('','end',iid=str(i),values=(meta.get('borehole_name') or '',self.fmt(meta.get('test_depth',meta.get('depth_from'))),
                    (report.get('code') if report else None) or meta.get('layer_code') or '',self.fmt(sample['values'].get('spt_n')),
                    report['status'] if report else 'Đã đọc N-SPT; chưa đối chiếu địa tầng',sample['source']))
        def edit(_event=None):
            try:
                sample=self.state['spt_samples'][self.selected_index(tree)];meta=sample.get('strength_sample') or {}
                specs=[('hole','Tên lỗ khoan',meta.get('borehole_name'),None,False),
                    ('depth','Độ sâu thí nghiệm (m)',meta.get('test_depth',meta.get('depth_from')),None,False),
                    ('layer','Mã lớp nguồn (trống nếu chưa phân lớp)',meta.get('layer_code'),None,False),
                    ('n','N-SPT (số búa nguyên)',sample['values'].get('spt_n'),None,False)]
                def save(raw):
                    depth=number(raw['depth'],'Độ sâu');n=number(raw['n'],'N-SPT')
                    if depth<0 or n<0 or n!=int(n):raise ValueError('Độ sâu phải không âm; N-SPT phải là số nguyên không âm.')
                    if not raw['hole'].strip():raise ValueError('Nhập tên lỗ khoan theo nguồn.')
                    sample['strength_sample']=dict(meta,borehole_name=raw['hole'].strip(),test_depth=depth,
                        depth_from=depth,depth_to=depth,layer_code=raw['layer'].strip() or None,test_elevation=None)
                    sample['values']['spt_n']=int(n);sample['source']+=' · người dùng sửa'
                    self.bind_strength_samples();self.invalidate('geology_approved');fill()
                self.form('Sửa mẫu N-SPT',specs,save)
            except Exception as exc:self.error(exc)
        tree.bind('<Double-1>',edit)
        ttk.Button(popup,text='Sửa mẫu được chọn',command=edit).pack(pady=8)
        fill()

    def order_buttons(self,parent,command,inline=False):
        bar=parent if inline else ttk.Frame(parent)
        if not inline:bar.pack(fill='x',padx=8,pady=4)
        self.button(bar,'↑ Lên',lambda:command(-1)).pack(side='left',padx=3)
        self.button(bar,'↓ Xuống',lambda:command(1)).pack(side='left',padx=3)

    def move_display(self,tree,direction):
        if self.busy:return
        try:
            selected=tree.selection()
            if not selected:raise ValueError('Chọn dòng cần di chuyển.')
            item=selected[0];index=tree.index(item);target=index+direction
            if 0<=target<len(tree.get_children()):tree.move(item,'',target)
            tree.see(item);tree.focus(item)
        except Exception as exc:self.error(exc)

    def move_input(self,key,tree,direction):
        if self.busy:return
        try:
            index=self.selected_index(tree)
            current=(self.state['sections'][self.state['index']]
                     if self.state['index']<len(self.state['sections']) else None)
            target=move_layer(self.state[key],index,direction)
            if target!=index:
                if key=='sections' and current is not None:
                    self.state['index']=next(i for i,row in enumerate(self.state['sections']) if row is current)
                if key=='boreholes':self.bind_strength_samples()
                self.invalidate('boreholes_approved' if key=='boreholes' else 'sections_approved')
            self.select_table_row(tree,target)
        except Exception as exc:self.error(exc)

    def move_saved(self,direction):
        if self.busy:return
        try:
            index=self.selected_index(self.saved_tree)
            target=move_layer(self.state['records'],index,direction)
            if target!=index:
                saved=getattr(self.app,'_saved_sections_data',[])
                positions=[i for i,r in enumerate(saved) if r.get('ai_workflow_id')==self.state['id']]
                by_no={r['section_no']:r for r in saved if r.get('ai_workflow_id')==self.state['id']}
                ordered=[by_no[r['section_no']] for r in self.state['records'] if r['section_no'] in by_no]
                if len(positions)==len(ordered):
                    for i,row in zip(positions,ordered):saved[i]=row
                self.refresh()
                if hasattr(self.app,'refresh_result_summary'):self.app.refresh_result_summary()
            self.select_table_row(self.saved_tree,target)
        except Exception as exc:self.error(exc)

    def move_material(self,direction):
        if self.busy:return
        try:
            index=self.selected_index(self.material_tree)
            target=move_layer(self.state['materials'],index,direction)
            if target!=index:self.invalidate('geology_approved')
            self.select_table_row(self.material_tree,target)
        except Exception as exc:self.error(exc)

    def form(self,title,specs,save,help_text='',soil_fields=False):
        popup=tk.Toplevel(self);popup.title(title);popup.geometry('720x650');popup.transient(self.app)
        if help_text:ttk.Label(popup,text=help_text,wraplength=670,padding=10).pack(fill='x')
        scroll=ScrollableFrame(popup);scroll.pack(fill='both',expand=True,padx=10)
        body=scroll.scrollable_frame;body.configure(padding=8);body.columnconfigure(1,weight=1)
        variables={};original={};initial={};rows={};editable=set()
        from geology_statistics import parameter_text
        for row,(key,label,value,choices,readonly) in enumerate(specs):
            label_widget=ttk.Label(body,text=label);label_widget.grid(row=row,column=0,sticky='w',pady=4)
            original[key]=value
            var=tk.StringVar(value='' if value is None else parameter_text(value,key));variables[key]=var;initial[key]=var.get()
            widget=ttk.Combobox(body,textvariable=var,values=choices,state='readonly') if choices else ttk.Entry(body,textvariable=var)
            if readonly:widget.configure(state='readonly')
            widget.grid(row=row,column=1,sticky='ew',pady=4,padx=10)
            rows[key]=(label_widget,widget)
        def update_fields(*_):
            from ui_theme import soil_parameter_keys
            allowed=soil_parameter_keys(self.data_project().method,variables['category'].get() if 'category' in variables else None)
            editable.clear()
            for key,pair in rows.items():
                if not soil_fields or key not in SOIL_KEYS or key in allowed:
                    editable.add(key)
                    for widget in pair:widget.grid()
                else:
                    for widget in pair:widget.grid_remove()
        if soil_fields and 'category' in variables:variables['category'].trace_add('write',update_fields)
        update_fields()
        error=tk.StringVar();ttk.Label(popup,textvariable=error,foreground='#b91c1c',wraplength=670,padding=10).pack(fill='x')
        def commit():
            if self.busy:return
            update_fields()
            try:save({k:(str(original[k]) if isinstance(original[k],(int,float)) and v.get()==initial[k] else v.get().strip()) for k,v in variables.items() if k in editable});popup.destroy()
            except Exception as exc:error.set(str(exc))
        bar=ttk.Frame(popup,padding=10);bar.pack(fill='x')
        ttk.Button(bar,text='Lưu',command=commit,style='Accent.TButton').pack(side='right')
        ttk.Button(bar,text='Hủy',command=popup.destroy).pack(side='right',padx=8)
        popup.grab_set();return popup

    def view_material_samples(self):
        if self.busy:return
        try:
            material=self.state['materials'][self.selected_index(self.material_tree)]
            popup=tk.Toplevel(self);popup.title('Mẫu gốc · lớp '+material['code'])
            popup.geometry('1000x540');popup.transient(self.app)
            ttk.Label(popup,text='Giá trị trung bình được tính riêng cho từng chỉ tiêu có dữ liệu; ô thiếu được bỏ qua.',padding=10).pack(fill='x')
            tree=self.table(popup,('Mẫu','γ','e₀','Cc','Cs','Pc','N-SPT','Bảng e/Cv/Mv','Nguồn'),(60,80,80,80,80,80,90,400,400))
            for index,sample in enumerate(material.get('samples') or [material],1):
                v=sample['values']
                curves='; '.join(k+'='+str(v[k]) for k in ('ep','e','cvp','cv','mvp','mv') if k in v)
                tree.insert('', 'end',values=(index,*[self.fmt(v.get(k)) for k in ('gamma','e0','cc','cs','pc','spt_n')],curves,sample['source']))
            ttk.Button(popup,text='Đóng',command=popup.destroy).pack(pady=8)
        except Exception as exc:self.error(exc)

    def edit_material(self,new=False):
        if self.busy:return
        try:
            index=None if new else self.selected_index(self.material_tree)
            m={'code':'','values':{},'source':'Người dùng nhập','description':''} if new else self.state['materials'][index]
            labels={'category':'Loại đất','state':'Trạng thái','gamma':'γ (T/m³)','drainage':'Thoát nước (1/2 mặt)',
                'e0':'e₀','cc':'Cc','cs':'Cs','pc':'Pc (T/m²)','co':'Co / cᵤ (T/m²)','cohesion_c':'c (T/m²)',
                'friction_phi':'φ (độ)','cv_constant':'Cv trung bình (10⁻³ cm²/s)','phi_cu_effective':'φ′ hữu hiệu CU (độ; để trống nếu không có CU)','spt_n':'N-SPT','sand_method':'Mô hình đất rời'}
            specs=[('code','Mã lớp',m['code'],None,False),('description','Mô tả',m.get('description',''),None,False)]
            for k,label in labels.items():
                choices={'category':('Đất dính','Đất rời'),'state':('Quá cố kết','Cố kết thường'),
                         'sand_method':('De Beer','Schmertmann')} .get(k)
                specs.append((k,label,m['values'].get(k,m.get('phi_cu_effective') if k=='phi_cu_effective' else 1 if k=='drainage' else None),choices,False))
            for k in ('ep','e','cvp','cv','mvp','mv'):
                specs.append((k,k+' · các số cách nhau bởi dấu ;','; '.join(str(v) for v in m['values'].get(k,[])),None,False))
            specs.append(('source','Nguồn gốc',m['source'],None,True))
            def save(raw):
                candidate=deepcopy(m['values'])
                for k in SOIL_KEYS:
                    if k not in raw:continue
                    if not raw[k]:candidate.pop(k,None)
                    elif k in ARRAY_KEYS:candidate[k]=[number(v,k) for v in raw[k].split(';') if v.strip()]
                    else:candidate[k]=raw[k]
                candidate.update(code=raw['code'],description=raw['description'],source=m['source']+' · đã sửa')
                candidate['layer_code_verified']=True  # explicitly reviewed/typed by the user
                value=normalize_material(candidate)
                value['sample_count']=m.get('sample_count',1)
                value['samples']=deepcopy(m.get('samples') or [m])
                value['average_edited']=True
                if m.get('strength_values'):
                    value['strength_values']={k:value['values'][k] for k in ('co','strength_m') if k in value['values']}
                    value['strength_source']=m.get('strength_source','')+' · đã sửa'
                if m.get('curve_values'):
                    value['curve_values']={k:value['values'][k] for k in ('ep','e','cvp','cv') if k in value['values']}
                    value['curve_source']=m.get('curve_source','')+' · đã sửa'
                if any(x['code'].casefold()==value['code'].casefold() for i,x in enumerate(self.state['materials']) if i!=index):
                    raise ValueError('Mã lớp trùng; dùng mã duy nhất để ghép địa tầng.')
                from geotech_memory import GeotechMemory,project_scope
                scope=project_scope(self.data_project(),self.app.current_username or '')
                GeotechMemory().record_correction(scope,'material_edit',m,value,
                    source=m.get('source',''),context={'code':m['code'],'origin':'user_editor'},
                    actor=self.app.current_username or 'Người dùng',confirmed=True)
                if index is None:self.state['materials'].append(value)
                else:self.state['materials'][index]=value
                self.invalidate('geology_approved')
            self.form('Chỉ tiêu lớp đất',specs,save,'Giữ trống thông số chưa có. Pc/c/Co: T/m²; Cv: 10⁻³ cm²/s; ep/cvp/mvp: kg/cm². Bảng đường cong nhập bằng dấu ;.',soil_fields=True)
        except Exception as exc:self.error(exc)

    def edit_borehole(self,new=False):
        if self.busy:return
        try:
            index=None if new else self.selected_index(self.hole_tree)
            hole={'name':'','elevation':None,'depth':None,'layers':[],'source':'Người dùng nhập'} if new else self.state['boreholes'][index]
            popup=tk.Toplevel(self);popup.title('Cao độ & địa tầng lỗ khoan');popup.geometry('790x620');popup.transient(self.app)
            info=ttk.Frame(popup,padding=10);info.pack(fill='x');variables={}
            for row,(key,label) in enumerate((('name','Tên lỗ khoan'),('elevation','Cao độ (m)'),('depth','Chiều sâu tính (m)'))):
                ttk.Label(info,text=label).grid(row=row,column=0,sticky='w',pady=4)
                var=tk.StringVar(value='' if hole[key] is None else str(hole[key]));variables[key]=var
                ttk.Entry(info,textvariable=var,width=24).grid(row=row,column=1,padx=10)
            ttk.Label(popup,text='Mỗi dòng: mã lớp ; bề dày (m). Giữ thứ tự từ trên xuống. Cao độ dùng làm Ztn của mặt cắt.',padding=10,wraplength=740).pack(fill='x')
            text=tk.Text(popup,height=12,font=(UI_FONT,11));text.pack(fill='both',expand=True,padx=10)
            text.insert('1.0','\n'.join(x['code']+' ; '+('' if x['thickness'] is None else str(x['thickness'])) for x in hole['layers']))
            orderbar=ttk.Frame(popup,padding=(10,4));orderbar.pack(fill='x')
            def move_line(direction):
                if self.busy:return
                lines=text.get('1.0','end-1c').split('\n')
                row,column=map(int,text.index('insert').split('.'))
                if not 0<=row-1<len(lines):return
                target=move_layer(lines,row-1,direction)
                if target==row-1:return
                text.delete('1.0','end');text.insert('1.0','\n'.join(lines))
                text.mark_set('insert',f'{target+1}.{column}');text.see('insert');text.focus_set()
            ttk.Button(orderbar,text='↑ Lớp lên',command=lambda:move_line(-1)).pack(side='left',padx=3)
            ttk.Button(orderbar,text='↓ Lớp xuống',command=lambda:move_line(1)).pack(side='left',padx=3)
            ttk.Label(orderbar,text='Đặt con trỏ tại dòng lớp cần chuyển; bấm Lưu để áp dụng địa tầng.').pack(side='left',padx=8)
            notice=tk.StringVar();ttk.Label(popup,textvariable=notice,foreground='#b91c1c',wraplength=740,padding=10).pack(fill='x')
            def layers():
                result=[]
                for line in text.get('1.0','end-1c').splitlines():
                    if not line.strip():continue
                    code,sep,value=line.partition(';')
                    if not sep:raise ValueError('Dòng địa tầng phải có dạng mã lớp ; bề dày.')
                    result.append({'code':code.strip(),'thickness':number(value,'Bề dày lớp'),'source':hole['source']+' · đã sửa'})
                return result
            def total():
                try:variables['depth'].set(str(sum(x['thickness'] for x in layers())))
                except Exception as exc:notice.set(str(exc))
            def save():
                if self.busy:return
                try:
                    raw={k:v.get() for k,v in variables.items()};raw.update(layers=layers(),source=hole['source']+' · đã sửa')
                    value=normalize_borehole(raw)
                    # Keep reviewed indicators when only borehole geometry is edited.
                    occurrences={}
                    for layer in value['layers']:
                        code=layer['code'].casefold();occurrence=occurrences.get(code,0)
                        matched=[x for x in hole['layers'] if x['code'].casefold()==code]
                        old=matched[occurrence] if occurrence<len(matched) else None
                        occurrences[code]=occurrence+1
                        if old and 'direct_values' in old:
                            layer['direct_values']=deepcopy(old['direct_values'])
                            layer['direct_source']=old.get('direct_source','')
                    if hole.get('test_samples'):value['test_samples']=deepcopy(hole['test_samples'])
                    if any(h['name'].casefold()==value['name'].casefold() for i,h in enumerate(self.state['boreholes']) if i!=index):raise ValueError('Tên lỗ khoan bị trùng.')
                    from geotech_memory import GeotechMemory,project_scope
                    GeotechMemory().record_correction(
                        project_scope(self.data_project(),self.app.current_username or ''),
                        'borehole_edit',hole,value,source=hole.get('source',''),
                        context={'borehole_name':hole.get('name'),'origin':'user_editor'},
                        actor=self.app.current_username or 'Người dùng',confirmed=True)
                    if index is None:self.state['boreholes'].append(value)
                    else:self.state['boreholes'][index]=value
                    self.bind_strength_samples()
                    self.invalidate('boreholes_approved');popup.destroy()
                except Exception as exc:notice.set(str(exc))
            bar=ttk.Frame(popup,padding=10);bar.pack(fill='x')
            ttk.Button(bar,text='Tính tổng chiều dày',command=total).pack(side='left')
            ttk.Button(bar,text='Lưu lỗ khoan',command=save,style='Accent.TButton').pack(side='right')
            ttk.Button(bar,text='Hủy',command=popup.destroy).pack(side='right',padx=8);popup.grab_set()
        except Exception as exc:self.error(exc)

    def approve_geology(self):
        if self.busy:return
        try:
            if not self.state['materials']:raise ValueError('Chưa có chỉ tiêu địa chất.')
            scopes={}
            for material in self.state['materials']:
                scopes.setdefault(material['code'].casefold(),set()).add(material.get('project_scope',''))
            duplicates=[code for code,origins in scopes.items() if len(origins)>1]
            if duplicates:
                self.state['geology_approved']=False
                self.tabs.select(self.pages[0])
                details='\n'.join(m['code']+' · '+str(m.get('project_scope') or m.get('source') or 'Chưa rõ nguồn') for m in self.state['materials'] if m['code'].casefold() in duplicates)
                self.status.set('Chưa xác nhận: mã lớp trùng nguồn. Sửa mã lớp hoặc bỏ nguồn không thuộc dự án trong Bảng tổng hợp chỉ tiêu.')
                messagebox.showwarning('Cần sửa nguồn chỉ tiêu','Mã lớp trùng giữa các dự án/nguồn:\n'+details+'\nĐã chuyển đến Bảng tổng hợp chỉ tiêu để sửa. Dữ liệu được giữ nguyên; chưa cho phép tính khi nguồn còn mâu thuẫn.',parent=self)
                return
            # Confirm the imported observations so the user can finish the
            # soil inputs in Địa tầng. Calculation still validates those inputs.
            incomplete=[m['code'] for m in self.state['materials']
                if m['values'].get('category') not in ('Đất dính','Đất rời')
                or m['values'].get('gamma') is None or m['values']['gamma']<=0]
            if self.app.design_mode.get() == 'TÍNH MỘT ĐOẠN':
                from model import Soil
                candidate=deepcopy(self.app.project)
                existing={soil.name.casefold() for soil in candidate.soils}
                for material in self.state['materials']:
                    if material['code'].casefold() not in existing:
                        # No layer thickness is inferred from sample depths.
                        candidate.soils.append(Soil(no=len(candidate.soils)+1,
                            name=material['code'],thickness=0,gamma=0,category='Chưa xác định'))
                        existing.add(material['code'].casefold())
                for soil in candidate.soils:
                    material=next((m for m in self.state['materials'] if m['code'].casefold()==soil.name.casefold()),None)
                    if material:
                        for key,value in material['values'].items():
                            if key in SOIL_KEYS and key not in ('thickness','name'):setattr(soil,key,deepcopy(value))
                        if material['values'].get('category') not in ('Đất dính','Đất rời'):
                            soil.category='Chưa xác định'
                        if material['values'].get('gamma') is None:soil.gamma=0
                        catalog=candidate.geology_statistics.get('layer_catalog',{})
                        if not soil.statistics_id:
                            soil.statistics_id=catalog.get(material['code'].casefold(),{}).get('id','')
                backup=self.app.project
                try:
                    self.app.project=candidate;self.app.populate();self.app.invalidate_assessment()
                except BaseException:
                    self.app.project=backup;self.app.populate();raise
            self.state['geology_approved']=True;self.refresh();self.tabs.select(self.pages[1])
            self.status.set('Đã xác nhận chỉ tiêu; '+
                ('sửa loại đất / γ còn thiếu tại Địa tầng: '+', '.join(incomplete)+'. ' if incomplete else '')+
                ('Kiểm tra bề dày và chỉ tiêu tại Địa tầng trước khi tính.'
                 if self.app.design_mode.get()=='TÍNH MỘT ĐOẠN' else 'Tiếp theo đọc và xác nhận lỗ khoan.'))
        except Exception as exc:self.error(exc)

    def approve_boreholes(self):
        if self.busy:return
        try:
            if not self.state['boreholes']:raise ValueError('Chưa có danh sách lỗ khoan.')
            from model import Project, Soil
            codes={m['code'].casefold() for m in self.state['materials']}
            direct=(self.app.design_mode.get()=='TÍNH TOÀN TUYẾN' and self.app.calculation_settings()['data_processed'])
            readable=[h for h in self.state['boreholes'] if h.get('layers')]
            if not readable:raise ValueError('Chưa đọc được địa tầng trụ nào; chọn file trụ địa chất trước khi xác nhận.')
            for hole in readable:
                if hole.get('validation_issues'):raise ValueError(hole['name']+': '+'; '.join(hole['validation_issues'])+' Sửa lỗ khoan trước khi xác nhận.')
                for layer in hole['layers']:
                    if direct:
                        material=next((m for m in self.state['materials'] if m['code'].casefold()==layer['code'].casefold()),{})
                        values=dict(material.get('values',{}));values.update(layer.get('direct_values',{}))
                        if values.get('category') not in ('Đất dính','Đất rời') or number(values.get('gamma'),'γ '+layer['code'])<=0:
                            raise ValueError(hole['name']+' / '+layer['code']+': nhập loại đất và γ trước khi xác nhận.')
                    elif self.state['geology_approved'] and layer['code'].casefold() not in codes:raise ValueError(hole['name']+': mã lớp '+layer['code']+' chưa có chỉ tiêu.')
                Project().set_borehole(hole['name'],number(hole['elevation']),number(hole['depth']),
                    [Soil(thickness=number(x['thickness'])) for x in hole['layers']])
            self.state['boreholes_approved']=True
            if direct:self.state['geology_approved']=True
            self.refresh()
            self.tabs.select(self.pages[2])
            self.status.set('Đã xác nhận địa tầng. Đã chuyển sang tab Bảng phân đoạn ở ngay bên cạnh để tiếp tục.')
        except Exception as exc:self.error(exc)

    def read_data(self,show_holes=False,path=None):
        if self.busy:return
        path=path or filedialog.askopenfilename(parent=self,filetypes=[('Data Excel','*.xlsx *.xlsm')])
        if not path:return
        template=deepcopy(self.state['template'])
        def done(sections):
            from ai_analysis_data import boreholes_from_data,borehole_key
            listed=boreholes_from_data(sections)
            existing={borehole_key(h['name']):h for h in self.state['boreholes']}
            for hole in listed:
                key=borehole_key(hole['name'])
                if key in existing:existing[key]['data_references']=hole['data_references']
                else:self.state['boreholes'].append(hole)
            names={borehole_key(h['name']):h['name'] for h in self.state['boreholes']}
            for section in sections:section['borehole_selected']=names.get(borehole_key(section['borehole_name']),'')
            self.state.update(sections=sections,index=0,source=path,sections_approved=False,boreholes_approved=False,pending=None,
                              data_borehole_names=[h['name'] for h in listed])
            self.app._section_excel_path=path
            self.app._route_manual_designs={}
            self.app.route_section_selector.active=None
            self.app.route_section_selector.base=None
            self.app._step_result_cache.clear()
            # Import project identity and the first calculation cross-section together.
            if sections:
                first=sections[0]
                from section_excel import import_section
                try:
                    project,length=import_section(path,first['section_no'],template,load_geology=False)
                    import_note='Đã nạp hình học mặt cắt. Chỉ tiêu đất lấy từ Thống kê; địa tầng và bề dày lấy từ trụ địa chất đã xác nhận.'
                except ValueError as exc:
                    validate_section(first)
                    project=deepcopy(template);project.soils=[];project.main_soils=[]
                    for field in ('name','design_stage','work_item','station','station_from','station_to','h_design','h_kcad','slope_m','gamma_fill','borehole_name'):
                        setattr(project,field,first[field])
                    project.crest_half_width=first['crest_width']/2
                    if first.get('ground_elevation') is None:raise ValueError('Data thiếu cao độ mặt cắt: bổ sung THSH cột H trước khi nạp hình học.')
                    project.ground_elevation=first['ground_elevation'];project.h_bl=0
                    project.residual_limit_cm=first['limit_cm'];project.residual_limit_source=first['limit_source']
                    project.update_geometry();length=first['length']
                    import_note='Đã nạp hình học mặt cắt; cần xác nhận Thống kê và trụ địa chất trước khi tính. '+str(exc)
                project.calculation_results={}
                self.app.project=project;self.state['template']=deepcopy(project)
                self.app._active_section_no=first['section_no'];self.app._active_section_length=length
                self.app._choice_group_results.clear();self.app._cdm_reports.clear()
                self.app.excel_section_combo.configure(values=tuple(str(section['section_no']) for section in sections))
                self.app.excel_section_no.set(str(first['section_no']))
                self.app.populate();self.app.draw_live_diagram()
                self.app.excel_section_notice.set(f'{Path(path).name}: {len(sections)} phân đoạn · Mặt cắt STT {first["section_no"]}. '+import_note)
            self.state.pop('pending_project',None);self.clear_results();self.refresh()
            self.status.set('Đã đọc phân đoạn và danh sách lỗ khoan từ dữ liệu đầu vào. Đọc địa tầng còn thiếu rồi xác nhận.')
            if show_holes:self.tabs.select(self.pages[1])
        def data_error(exc):
            self.status.set(str(exc))
            messagebox.showerror('Đọc dữ liệu Excel',str(exc),parent=self)
        self.run_job('Đọc dữ liệu Excel…',lambda _progress:read_data_sections(path,template),done,
                     use_ai=False,on_error=data_error)

    def edit_section(self):
        if self.busy:return
        try:
            index=self.selected_index(self.section_tree);s=self.state['sections'][index]
            fields=[('station_from','Lý trình đầu'),('station_to','Lý trình cuối'),('station','Mặt cắt tính'),
                    ('length','Chiều dài đoạn (m)'),('h_design','Htk (m)'),('h_kcad','Hkcad (m)'),
                    ('crest_width','Bề rộng nền B (m)'),('slope_m','Mái dốc m'),('gamma_fill','γ đắp (T/m³)'),
                    ('ground_elevation','Ztn trong Data (m)'),('limit_cm','ΔS từ '+s['limit_source']+' (cm)')]
            specs=[(k,label,s.get(k),None,k=='limit_cm') for k,label in fields]
            specs.append(('borehole_selected','Lỗ khoan dùng để tính',s['borehole_selected'],tuple(h['name'] for h in self.state['boreholes']),False))
            def save(raw):
                candidate=deepcopy(s)
                for k,_label in fields:
                    if k=='limit_cm':continue
                    candidate[k]=(raw[k] if k.startswith('station') else
                                  None if k=='ground_elevation' and not raw[k].strip() else number(raw[k],k))
                candidate['borehole_selected']=raw['borehole_selected']
                from ai_analysis_data import borehole_key
                if (not self.app.calculation_settings()['data_processed'] and candidate['borehole_selected']
                        and borehole_key(candidate['borehole_selected'])!=borehole_key(candidate.get('borehole_name',''))):
                    raise ValueError('Lỗ khoan phải trùng tên trong bảng phân đoạn: '+str(candidate.get('borehole_name','')))
                validate_section(candidate)
                self.state['sections'][index]=candidate;self.invalidate('sections_approved')
            self.form('STT '+str(s['section_no'])+' · đầu vào phân đoạn',specs,save,
                'Cao độ và bề dày để tính lấy từ lỗ khoan đã chọn. ΔS giữ nguyên Data; nếu sai, sửa Excel và đọc lại.')
        except Exception as exc:self.error(exc)

    def approve_sections(self):
        if self.busy:return
        try:
            if not self.state['sections']:raise ValueError('Chưa có Data phân đoạn.')
            # Data approval validates segment input only, before borehole/lab input.
            for section in self.state['sections']:validate_section(section)
            self.state['sections_approved']=True;self.refresh()
            if not self.state['boreholes_approved']:
                self.tabs.select(self.pages[1])
                self.status.set('Đã xác nhận dữ liệu phân đoạn. Nhập/AI đọc trụ các lỗ khoan trong danh sách Data, sau đó xác nhận địa tầng.')
            elif not self.state['geology_approved']:
                self.tabs.select(self.pages[0])
                self.status.set('Đã xác nhận dữ liệu phân đoạn. Nhập chỉ tiêu đất và xác nhận địa tầng trước khi tính.'
                    if self.app.calculation_settings()['data_processed'] else
                    'Đã xác nhận dữ liệu phân đoạn. Nhập và xác nhận chỉ tiêu đất trước khi tính.')
            else:
                self.tabs.select(self.pages[3])
                self.status.set('Đã xác nhận đầy đủ dữ liệu phân đoạn, lỗ khoan và chỉ tiêu đất. Có thể tính và so sánh phương án.')
        except Exception as exc:self.error(exc)

    def build_project(self,section):
        hole=next((h for h in self.state['boreholes'] if h['name']==section['borehole_selected']),None)
        if hole is None:raise ValueError(f'STT {section["section_no"]}: chọn lỗ khoan để tính.')
        return project_for_section(self.state['template'],section,self.state['materials'],hole)

    def current_project(self):
        if not all(self.state.get(k) for k in ('geology_approved','boreholes_approved','sections_approved')):
            raise ValueError('Xác nhận đầy đủ địa tầng, lỗ khoan và dữ liệu phân đoạn trước khi tính.')
        if self.state['index']>=len(self.state['sections']):raise ValueError('Đã tính hết danh sách phân đoạn.')
        return self.state.get('pending_project') or self.build_project(self.state['sections'][self.state['index']])

    def review_current_project(self):
        if self.busy:return
        try:
            p=deepcopy(self.current_project())
            popup=tk.Toplevel(self);popup.title('Đầu vào kiểm toán của đoạn hiện tại');popup.geometry('900x600');popup.transient(self.app)
            ttk.Label(popup,text=f'{p.borehole_name}: cao độ {p.ground_elevation:g} m; chiều sâu {p.borehole_depth:g} m; '
                      f'Htk {p.h_design:g} m; B {2*p.crest_half_width:g} m; ΔS {p.residual_limit_cm:g} cm từ {p.residual_limit_source}; phương pháp {p.method}.',
                      padding=10,wraplength=860).pack(fill='x')
            tree=self.table(popup,('Lớp','h (m)','γ (T/m³)','e₀','Cc','Cs','Pc','Cv'),(150,90,100,90,90,90,90,150))
            def fill():
                tree.delete(*tree.get_children())
                for i,s in enumerate(p.soils):tree.insert('', 'end',iid=str(i),values=(s.name,s.thickness,s.gamma,s.e0,s.cc,s.cs,s.pc,str(s.cv)))
            def edit(_e=None):
                if not tree.selection():return
                from dialogs import SoilDialog
                index=int(tree.selection()[0])
                def save(soil):p.soils[index]=soil;fill()
                SoilDialog(popup,p.soils[index],save,p.method,'Chờ lún')
            tree.bind('<Double-1>',edit)
            def commit():
                if self.busy:return
                self.state['pending_project']=deepcopy(p);self.state['pending']=None;self.clear_results();popup.destroy()
            bar=ttk.Frame(popup,padding=10);bar.pack(fill='x')
            ttk.Button(bar,text='Sửa chỉ tiêu lớp chọn',command=edit).pack(side='left')
            ttk.Button(bar,text='Xác nhận đầu vào',command=commit,style='Accent.TButton').pack(side='right');fill();popup.grab_set()
        except Exception as exc:self.error(exc)

    def edit_settings(self, on_save=None):
        if self.busy:return
        from batch_calculation import OPTIONS
        allowed_options=self.app.calculation_options()
        if not allowed_options:
            if on_save is not None:self.after_idle(on_save)
            return
        popup=tk.Toplevel(self);popup.title('Phương án và phạm vi tính tuyến');popup.geometry('770x720');popup.transient(self.app)
        scroll=ScrollableFrame(popup);scroll.pack(fill='both',expand=True,padx=10);body=scroll.scrollable_frame
        chosen=self.state.get('options',list(OPTIONS));flags={}
        for i,name in enumerate(allowed_options):
            flag=tk.BooleanVar(value=name in chosen);flags[name]=flag
            ttk.Checkbutton(body,text=name,variable=flag).grid(row=i,column=0,columnspan=2,sticky='w',pady=2)
        specs=[('excavation_step','Bước đào thay (m)'),('cdm_length_step','Bước Lc (m)'),('cdm_lc_min','Lc tối thiểu (m)'),
               ('cdm_lc_max','Lc tối đa (m)'),('cdm_s_min','s CDM tối thiểu (m)'),('cdm_s_max','s CDM tối đa (m)'),
               ('cdm_s_step','Bước s CDM (m)'),('pvd_spacing','s PVD (m)'),('pvd_diameter','d PVD (cm)'),
               ('sd_spacing','s SD (m)'),('sd_diameter','d SD (cm)'),('ch_cv','Ch/Cv tự nhập (trống: PVD/SD dùng 2)'),('surcharge_height','Chiều cao gia tải (m)'),('max_wait_days','Ngày chờ tối đa')]
        variables={}
        for row,(key,label) in enumerate(specs,len(OPTIONS)+1):
            ttk.Label(body,text=label).grid(row=row,column=0,sticky='w',pady=4)
            var=tk.StringVar(value=str(self.state['settings'].get(key,'')));variables[key]=var
            ttk.Entry(body,textvariable=var).grid(row=row,column=1,padx=10)
        notice=tk.StringVar();ttk.Label(popup,textvariable=notice,foreground='#b91c1c',padding=10).pack(fill='x')
        def commit():
            try:
                settings={k:number(v.get(),k) for k,v in variables.items() if v.get().strip()}
                if any(v<=0 for v in settings.values()):raise ValueError('Thông số quét phải lớn hơn 0.')
                selected=[name for name in allowed_options if flags[name].get()]
                if not selected:raise ValueError('Chọn ít nhất một phương án.')
                self.state['settings']=settings;self.state['options']=selected;self.state['pending']=None;self.clear_results();popup.destroy()
                if on_save is not None:self.after_idle(on_save)
            except Exception as exc:notice.set(str(exc))
        ttk.Button(popup,text='Lưu và tính' if on_save is not None else 'Lưu phạm vi & phương án',command=commit,style='Accent.TButton').pack(pady=10);popup.grab_set()

    def calculate(self):
        if self.busy:return
        try:
            if not self.app.require_full_license():return
            from batch_calculation import OPTIONS
            project=deepcopy(self.current_project());section=deepcopy(self.state['sections'][self.state['index']])
            validate_analysis_project(project)
            settings=deepcopy(self.state['settings']);template=self.state['template']
            # Chỉ lấy thông số đã khai báo; bộ AI sẽ hỏi phần còn thiếu.
            for key,value in (('pvd_spacing',template.drain_spacing),('pvd_diameter',template.drain_diameter),
                              ('surcharge_height',template.surcharge_height)):
                if key not in settings and value>0:settings[key]=value
            options=self.state.get('options',list(OPTIONS))
            def action(progress):
                from soilfirm_ai_engine import _valid_project,before_treatment,execute_tool
                _valid_project(project);progress('Tính kiểm toán trước xử lý…')
                before=before_treatment(project)
                if before['pass_check']:return {'before':before,'natural':True,'project':project,'section':section}
                plan={'tool':'optimize','params':{'options':options,'criterion':'priority'}}
                result=execute_tool(plan,project,settings,length=section['length'],progress=progress)
                return {'before':before,'natural':False,'result':result,'project':project,'section':section}
            self.run_job('AI tính toán từng phương án…',action,self.calculation_done)
        except Exception as exc:self.error(exc)

    def calculation_done(self,pending):
        self.state['pending']=pending;self.show_pending()
        if self.app.design_mode.get() == 'TÍNH TOÀN TUYẾN':
            self.app._batch_runs = getattr(self.app, '_batch_runs', {})
            self.app._batch_runs[int(pending['section']['section_no'])] = deepcopy(pending)
            self.app.switch_step(16)
        if pending['natural']:
            self.status.set('Phân đoạn đạt trước xử lý. Bấm Chọn phương án để xác nhận không cần xử lý; chưa chuyển sang đoạn tiếp theo.')
        elif pending['result'].get('input_requirements'):
            self.request_missing(pending['result']['input_requirements'])
        else:
            self.status.set('Đã tính; chọn một phương án ĐẠT trong bảng rồi bấm Chọn phương án → thẻ Tổng hợp kết quả.')

    def request_missing(self,requirements):
        specs=[(str(i),r['label']+' ('+r.get('unit','')+')',r.get('value'),None,False) for i,r in enumerate(requirements)]
        def save(raw):
            from soilfirm_ai_engine import apply_calculation_inputs
            p=deepcopy(self.state['pending']['project']);values=[raw[str(i)] for i in range(len(requirements))]
            apply_calculation_inputs(p,requirements,values)
            for r,text in zip(requirements,values):
                value=number(text,r['label'])
                if r['target']=='treatment':self.state['settings'][r['key']]=value
                elif r['target']=='app_var':setattr(p,r['key'],value)
            self.state['pending_project']=p
            self.state['template'].cdm_inputs=deepcopy(p.cdm_inputs)
            self.state['template'].alicc_inputs=deepcopy(p.alicc_inputs)
            self.state['pending']=None;self.clear_results()
            self.after_idle(self.calculate)
        self.form('Bổ sung thông số phương án trước khi tính',specs,save,'Chỉ bổ sung các thông số còn thiếu. ΔS cho phép của đoạn vẫn lấy từ Data.')

    def show_pending(self):
        self.clear_results();pending=self.state.get('pending')
        if not pending:return
        before=pending['before']
        for i,row in enumerate(before['locations']):
            self.before_tree.insert('', 'end',iid=str(i),values=(row['vị_trí'],self.fmt(row['Sc_cuối_cm']),
                self.fmt(row['Sc_dư_cm']),self.fmt(row['U_%']),self.fmt(before['evaluation_day']),self.fmt(before['limit_cm']),
                'ĐẠT' if row['Sc_dư_cm']<=before['limit_cm'] else 'CHƯA ĐẠT'))
        if pending['natural']:
            self.option_tree.insert('', 'end',values=('Không cần xử lý',self.fmt(before['residual_cm']),self.fmt(before['limit_cm']),'ĐẠT','ĐẠT',self.fmt(before['evaluation_day'])+' ngày','Đạt trước xử lý'))
            return
        result=pending['result'];self.options=[]
        for i,attempt in enumerate(result['summary'].get('attempts',[])):
            name=attempt['option'];record=result.get('options',{}).get(name)
            self.options.append(record)
            info=attempt.get('error') or ('; '.join(v['label']+'='+str(v['value'])+' '+v.get('unit','') for v in attempt.get('design',{}).values()))
            residual=attempt.get('residual_cm');limit=attempt.get('limit_cm')
            settlement_check=('CHƯA TÍNH' if residual is None or limit is None else 'ĐẠT' if residual<=limit else 'CHƯA ĐẠT')
            from design_workflow import option_time
            self.option_tree.insert('', 'end',iid=str(i),values=(name,self.fmt(residual),self.fmt(limit),settlement_check,
                'ĐẠT' if attempt.get('pass_check') else 'CHƯA ĐẠT / CHƯA TÍNH',option_time(attempt,record),info))
        from soilfirm_ai_engine import present_result
        view=present_result(result)
        for row in view.get('parameter_rows',[]):self.detail_tree.insert('', 'end',values=row)
        for row in view.get('check_rows',[]):self.detail_tree.insert('', 'end',values=row)
        for row in view.get('detail_rows',[]):self.detail_tree.insert('', 'end',values=(row[0],row[1],row[2],row[3]))

    def accept_option(self):
        if self.busy:return
        try:
            pending=self.state.get('pending')
            if not pending:raise ValueError('Bấm tính trước khi chọn phương án.')
            if pending['natural']:
                record=make_record(self.state,pending['section'],pending['project'],pending['before'])
                self.save_record(record);self.continue_next();return
            index=self.selected_index(self.option_tree)
            if index>=len(self.options) or self.options[index] is None:raise ValueError('Phương án chưa tính được.')
            record=make_record(self.state,pending['section'],pending['project'],pending['before'],self.options[index])
            self.save_record(record);self.status.set('Đã chọn phương án STT '+str(record['section_no'])+' · '+record['opt_name']+' vào thẻ Tổng hợp kết quả.')
            self.continue_next()
        except Exception as exc:self.error(exc)

    def save_record(self,record):
        self.app._saved_sections_data=commit_record(self.state,getattr(self.app,'_saved_sections_data',[]),record)
        try:
            from geotech_memory import GeotechMemory,project_scope
            summary={key:record.get(key) for key in ('section_no','station','length','group','opt_name','status','residual','limit')}
            summary['before']={key:record.get('before',{}).get(key) for key in ('pass_check','residual_cm')}
            GeotechMemory().record_correction(
                project_scope(self.data_project(),self.app.current_username or ''),
                'accepted_calculation',{},summary,source=record.get('source',''),
                context={'borehole_name':record['project_snapshot'].borehole_name},
                actor=self.app.current_username or 'Người dùng',confirmed=True)
        except Exception as exc:
            # Kết quả đã được bộ tính chấp nhận vẫn giữ nguyên; báo lỗi lưu nhật ký.
            messagebox.showwarning('Bộ nhớ AI','Đã lưu kết quả tính, nhưng chưa ghi được bộ nhớ: '+str(exc),parent=self)
        self.state.pop('pending_project',None)
        # Không chuyển địa chất/hình học của đoạn trước thành đầu vào đoạn sau.
        p=record['project_snapshot']
        self.app._section_excel_path=self.state['source']
        if hasattr(self.app,'refresh_result_summary'):self.app.refresh_result_summary()
        self.refresh()

    def continue_next(self):
        self.clear_results()
        if self.state['index']>=len(self.state['sections']):
            self.tabs.select(self.pages[4]);self.status.set(f'Hoàn tất {len(self.state["records"])} đoạn. Kết quả đã hiển thị ở thẻ Tổng hợp kết quả; sang thẻ Khối lượng để tính khối lượng bằng AI.')
        elif self.auto_next.get():self.after(100,self.calculate)


def build_view(parent):
    app=parent.winfo_toplevel()
    workspace=AnalysisWorkspace(parent,app);workspace.pack(fill='both',expand=True)
    app._ai_analysis_workspace=workspace
    return workspace
