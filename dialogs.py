"""
Module: dialogs.py
Chứa các hộp thoại chi tiết: 
- Thuộc tính lớp đất (Đã loại bỏ trường nhập chiều dày - nhập trực tiếp tại bảng địa tầng).
- Cửa sổ bảng phân tố đới đất chưa xử lý dưới đáy bấc/cọc (cắm lơ lửng).
- Bảng cường độ kháng cắt từng giai đoạn.
- Cửa sổ Help/About.
"""
from __future__ import annotations

import csv
from dataclasses import replace
import tkinter as tk
from tkinter import font as tkfont
from math_format import format_number
from tkinter import filedialog, messagebox, ttk

from model import (
    Soil, Project, OLD_TREATMENTS, is_radial, stage_schedule, treatment_history,
    effective_overburden, pressure
)
from utils import number, number_or_zero, ScrollableFrame
from ui_theme import COLORS, soil_parameter_keys, UI_FONT, UI_FONT_MONO
from ui_i18n import english as _english_ui


class _Tooltip:
    """Tooltip nhỏ xuất hiện khi hover vào widget."""
    def __init__(self, widget, text):
        self._widget = widget
        self._text = text
        self._tip = None
        widget.bind('<Enter>', self._show, add='+')
        widget.bind('<Leave>', self._hide, add='+')

    def _show(self, event=None):
        if self._tip or not self._text:
            return
        x = self._widget.winfo_rootx() + 20
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f'+{x}+{y}')
        lbl = tk.Label(tw, text=self._text, justify='left', wraplength=320,
                       background='#FFFBEA', foreground='#1A2C3D',
                       font=(UI_FONT, 9), relief='solid', borderwidth=1,
                       padx=8, pady=5)
        lbl.pack()

    def _hide(self, event=None):
        if self._tip:
            self._tip.destroy()
            self._tip = None


# Tooltip giải thích ký hiệu địa kỹ thuật
_PARAM_TOOLTIPS = {
    'gamma':          'Dung trọng tự nhiên γ: khối lượng đất trên đơn vị thể tích (T/m³)',
    'e0':             'Hệ số rỗng ban đầu e₀: tỷ lệ thể tích lỗ rỗng / thể tích hạt đất',
    'cc':             'Chỉ số nén Cc: độ dốc đường nén theo log áp lực (đường nguyên sinh)',
    'cs':             'Chỉ số nén lại Cs: độ dốc đường nén lại / giãn nở (thường Cs ≈ Cc/5–Cc/10)',
    'pc':             'Áp lực tiền cố kết Pc (T/m²): áp lực lớn nhất đất từng chịu trong lịch sử',
    'co':             'Lực dính ban đầu Co (T/m²): cường độ kháng cắt không thoát nước ban đầu',
    'cv_constant':    'Cv trung bình (×10⁻³ cm²/s): hệ số cố kết đứng, dùng thay thế bảng Cv–P nếu nhập',
    'cohesion_c':     'Lực dính c (T/m²): dùng để tính sức chịu tải tiêu chuẩn Rtc',
    'friction_phi':   'Góc ma sát trong φ (độ): dùng để tính Rtc; 0 ≤ φ < 90°',
    'spt_n':          'Chỉ số SPT N: số búa trong thí nghiệm xuyên tiêu chuẩn, dùng tính lún cát',
    'phi_cu_effective': 'φ′ hữu hiệu CU (độ): góc ma sát từ thí nghiệm cắt không thoát nước CU;\n'
                        'để trống nếu không có, phần mềm dùng hệ số m thay thế',
    'drainage':       'Số mặt thoát nước: 1 = thoát nước 1 chiều (mặt trên); 2 = hai chiều (trên + dưới)',
}

# Trường bắt buộc — luôn phải có giá trị hợp lệ
_REQUIRED_FIELDS = {'name', 'gamma', 'category'}
_REQUIRED_CLAY   = {'state', 'drainage', 'co'}
_REQUIRED_SAND   = {'spt_n'}


def _get_language(widget):
    """Lấy ngôn ngữ UI hiện tại từ widget cha (an toàn nếu không tìm thấy)."""
    try:
        top = widget.winfo_toplevel()
        if hasattr(top, 'ui_language'):
            return 'en' if top.ui_language.get() == 'English' else 'vi'
    except (tk.TclError, AttributeError):
        pass
    return 'vi'


def _L(text, language='vi'):
    """Dịch text nếu đang ở chế độ English."""
    return _english_ui(text) if language == 'en' else text


def _compact_heading(label, font, limit=105):
    words = str(label).split()
    if len(words) < 2 or font.measure(label) <= limit:
        return str(label)
    options = (' '.join(words[:i]) + '\n' + ' '.join(words[i:])
               for i in range(1, len(words)))
    return min(options, key=lambda s: max(font.measure(line) for line in s.split('\n')))


def _fit_tree_columns(tree, headers, parent, *, caps=None, minimum=45):
    """Cột theo nội dung, tiêu đề tối đa hai dòng, không tự giãn quá khung."""
    head_font = tkfont.Font(parent, family=UI_FONT, size=9, weight='bold')
    body_font = tkfont.Font(parent, family=UI_FONT, size=8)
    for i, (cid, label) in enumerate(zip(tree['columns'], headers)):
        display = _compact_heading(label, head_font)
        tree.heading(cid, text=display)
        width = max(head_font.measure(line) for line in display.split('\n')) + 14
        for item in tree.get_children():
            values = tree.item(item, 'values')
            if i < len(values):
                width = max(width, body_font.measure(str(values[i])) + 14)
        if caps:
            width = min(width, caps[i])
        width = max(minimum, width)
        tree.column(cid, width=width, minwidth=width, stretch=False)


class BoreholeDialog(tk.Toplevel):
    """Nhập hồ sơ lỗ khoan và bề dày địa tầng trong một lần cập nhật."""

    def __init__(self, parent, project, elevation, on_save):
        super().__init__(parent)
        self.language = _get_language(parent)
        self.L = lambda s: _L(s, self.language)
        self.title(self.L('Nhập lỗ khoan tính toán'))
        self.transient(parent)
        self.geometry('780x620')
        self.minsize(640, 420)
        self.project, self.on_save = project, on_save
        self.name_var = tk.StringVar(value=project.borehole_name)
        self.elevation_var = tk.StringVar(value=elevation)
        self.depth_var = tk.StringVar(value=str(project.borehole_depth))
        self.total_var = tk.StringVar()
        self.rows = []
        info = ttk.Frame(self, padding=12)
        info.pack(fill='x')
        for row, (label, variable) in enumerate([
            ('Tên lỗ khoan', self.name_var), ('Cao độ lỗ khoan (m)', self.elevation_var),
            ('Chiều sâu lỗ khoan tính toán (m)', self.depth_var),
        ]):
            ttk.Label(info, text=self.L(label)).grid(row=row, column=0, sticky='w', pady=4)
            ttk.Entry(info, textvariable=variable, width=25).grid(row=row, column=1, sticky='w', padx=10)
        ttk.Label(info, text=self.L('Cao độ lỗ khoan dùng làm Ztn của mặt cắt tính toán.'),
                  wraplength=720).grid(row=3, column=0, columnspan=3, sticky='w', pady=(8, 0))
        scroll = ScrollableFrame(self)
        scroll.pack(fill='both', expand=True, padx=12)
        self.layer_body = scroll.scrollable_frame
        self.layer_body.configure(padding=6)
        self.layer_body.columnconfigure(1, weight=1)
        self.layer_body.columnconfigure(2, weight=1)
        for column, text in enumerate(('STT', 'Tên lớp đất', 'Bề dày lớp (m)', 'CĐ đáy (m)')):
            ttk.Label(self.layer_body, text=self.L(text)).grid(row=0, column=column, sticky='w', padx=4, pady=4)
        for soil in project.soils:
            self.add_layer(soil)
        if not self.rows:
            self.add_layer()
        tools = ttk.Frame(self, padding=12)
        tools.pack(fill='x')
        ttk.Button(tools, text=self.L('+ Thêm lớp đất'), command=self.add_layer).pack(side='left')
        ttk.Button(tools, text=self.L('Tính tổng chiều dày'), command=self.use_total).pack(side='left', padx=8)
        ttk.Label(self, textvariable=self.total_var, padding=(12, 0)).pack(fill='x')
        buttons = ttk.Frame(self, padding=12)
        buttons.pack(fill='x')
        ttk.Button(buttons, text=self.L('Áp dụng lỗ khoan'), command=self.commit,
                   style='Accent.TButton').pack(side='right')
        ttk.Button(buttons, text=self.L('Hủy'), command=self.destroy).pack(side='right', padx=8)
        self.elevation_var.trace_add('write', lambda *_: self.update_totals())
        self.depth_var.trace_add('write', lambda *_: self.update_totals())
        self.update_totals()
        self.grab_set()

    def add_layer(self, soil=None):
        if soil is None:
            soil = Soil(name=f'{self.L("Lớp")} {len(self.rows)+1}', thickness=2.0)
        name = tk.StringVar(value=soil.name)
        thickness = tk.StringVar(value=str(soil.thickness))
        bottom = tk.StringVar()
        widgets = [ttk.Label(self.layer_body), ttk.Entry(self.layer_body, textvariable=name, width=25),
                   ttk.Entry(self.layer_body, textvariable=thickness, width=18),
                   ttk.Label(self.layer_body, textvariable=bottom)]
        record = {'soil': soil, 'name': name, 'thickness': thickness, 'bottom': bottom, 'widgets': widgets}
        remove = ttk.Button(self.layer_body, text=self.L('Xóa lớp'), style='Danger.TButton', command=lambda: self.remove_layer(record))
        widgets.append(remove)
        self.rows.append(record)
        thickness.trace_add('write', lambda *_: self.update_totals())
        self.reflow()

    def remove_layer(self, record):
        for widget in record['widgets']:
            widget.destroy()
        self.rows.remove(record)
        self.reflow()

    def reflow(self):
        for index, record in enumerate(self.rows, 1):
            record['widgets'][0].configure(text=str(index))
            for column, widget in enumerate(record['widgets']):
                widget.grid(row=index, column=column, sticky='ew', padx=4, pady=4)
        self.update_totals()

    def parsed_layers(self):
        return [replace(row['soil'], name=row['name'].get().strip(),
                        thickness=number(row['thickness'].get(), self.L('Bề dày lớp (m)')))
                for row in self.rows]

    def update_totals(self):
        try:
            elevation = number(self.elevation_var.get(), self.L('Cao độ lỗ khoan (m)'))
            total = 0.0
            for row in self.rows:
                thickness = number(row['thickness'].get(), self.L('Bề dày lớp (m)'))
                if thickness <= 0:
                    raise ValueError(self.L('Bề dày lớp phải lớn hơn 0.'))
                total += thickness
                row['bottom'].set(f'{elevation-total:.3f}')
            self.total_var.set(self.L('Tổng bề dày các lớp') + f': {total:.3f} m')
        except ValueError as exc:
            for row in self.rows:
                row['bottom'].set('—')
            self.total_var.set(str(exc))

    def use_total(self):
        try:
            self.depth_var.set(str(sum(s.thickness for s in self.parsed_layers())))
        except ValueError as exc:
            messagebox.showerror(self.L('Nhập lỗ khoan tính toán'), str(exc), parent=self)

    def commit(self):
        try:
            candidate = replace(self.project)
            candidate.set_borehole(self.name_var.get(),
                                   number(self.elevation_var.get(), self.L('Cao độ lỗ khoan (m)')),
                                   number(self.depth_var.get(), self.L('Chiều sâu lỗ khoan tính toán (m)')),
                                   self.parsed_layers())
            self.on_save(candidate)
            self.destroy()
        except ValueError as exc:
            messagebox.showerror(self.L('Nhập lỗ khoan tính toán'), str(exc), parent=self)


class SoilDialog(tk.Toplevel):
    """Hộp thoại khai báo và chỉnh sửa thông số lớp đất chi tiết (không có chiều dày)."""

    def __init__(self, parent, soil: Soil, on_save, method: str, treatment: str):
        super().__init__(parent)
        self.configure(background=COLORS['background'])
        self.language = _get_language(parent)
        L = lambda s: _L(s, self.language)

        self.title(L('Thông số lớp đất chi tiết'))
        self.transient(parent)
        self.grab_set()
        self.soil, self.on_save = soil, on_save
        self.method, self.treatment = method, treatment
        self.vars: dict[str, tk.StringVar] = {}
        self.grid_vars: dict[str, list[tk.StringVar]] = {}
        self.widgets = {}

        # Ngăn chặn cuộn chuột trên Combobox làm đổi giá trị ngoài ý muốn
        self.unbind_class("TCombobox", "<MouseWheel>")
        self.unbind_class("TCombobox", "<Button-4>")
        self.unbind_class("TCombobox", "<Button-5>")

        screen_w = parent.winfo_screenwidth()
        screen_h = parent.winfo_screenheight()

        dlg_w = min(720, screen_w - 40)
        dlg_h = min(620, screen_h - 60)
        pos_x = max(0, int((screen_w - dlg_w) / 2))
        pos_y = max(0, int((screen_h - dlg_h) / 2) - 20)

        self.geometry(f'{dlg_w}x{dlg_h}+{pos_x}+{pos_y}')
        self.minsize(680, 560)

        buttons = tk.Frame(self, bg=COLORS['surface'], padx=12, pady=10,
                           highlightthickness=1, highlightbackground=COLORS['border'])
        buttons.pack(side='bottom', fill='x')

        tk.Label(buttons, text=L('* Trường bắt buộc'), font=(UI_FONT, 9, 'italic'),
                 fg='#B91C1C', bg=COLORS['surface']).pack(side='left', padx=4)

        ttk.Button(buttons, text=L('Hủy bỏ (Esc)'),
                   command=self.destroy).pack(side='right', padx=6)

        btn_update = tk.Button(
            buttons, text=L('✔ Cập nhật (Enter)'),
            font=(UI_FONT, 9, 'bold'),
            bg=COLORS['accent'], fg='white',
            activebackground='#0C6175', activeforeground='white',
            relief='flat', cursor='hand2', padx=18, pady=5,
            command=self.commit
        )
        btn_update.pack(side='right', padx=6)

        tabs = self.tabs = ttk.Notebook(self)
        tabs.pack(side='top', fill='both', expand=True, padx=10, pady=(10, 4))

        basic = ScrollableFrame(tabs)
        compression = ScrollableFrame(tabs)
        cvtab = ScrollableFrame(tabs)
        basic_body = basic.scrollable_frame
        compression_body = compression.scrollable_frame
        cv_body = cvtab.scrollable_frame
        for body in (basic_body, compression_body, cv_body):
            body.configure(padding=12)
        tabs.add(basic, text=L('1. Chung'))
        tabs.add(compression, text=L('2. Nén lún · Cc/Cs/Pc'))
        tabs.add(cvtab, text=L('3. Cố kết · Cv'))
        self.compression_tab, self.cv_tab = compression, cvtab

        style = ttk.Style(self)
        style.configure('Required.TEntry', fieldbackground='#FFF8F8',
                        bordercolor='#FCA5A5')
        style.configure('Invalid.TEntry', fieldbackground='#FEE2E2',
                        bordercolor='#EF4444')
        style.configure('Valid.TEntry', fieldbackground='#FFFFFF',
                        bordercolor=COLORS['border'])

        def _required_for_category():
            cat_var = self.vars.get('category')
            cat = self._canonical(cat_var.get()) if cat_var else 'Đất dính'
            if cat == 'Đất dính':
                return _REQUIRED_FIELDS | _REQUIRED_CLAY
            if cat == 'Đất rời':
                return _REQUIRED_FIELDS | _REQUIRED_SAND
            return _REQUIRED_FIELDS

        def _validate_entry(key, entry, v):
            """Đổi style entry: đỏ nhạt nếu bắt buộc mà trống."""
            required = _required_for_category()
            if key in required and not v.get().strip():
                entry.configure(style='Invalid.TEntry')
            else:
                entry.configure(style='Valid.TEntry')

        def field(frame, key, label, value, row, choices=None):
            required = key in _REQUIRED_FIELDS or key in (_REQUIRED_CLAY | _REQUIRED_SAND)
            lbl_text = (label + ' *') if key in _REQUIRED_FIELDS else label
            lbl = ttk.Label(frame, text=lbl_text,
                            foreground='#B91C1C' if key in _REQUIRED_FIELDS else COLORS['text'])
            lbl.grid(row=row, column=0, sticky='w', pady=5)
            # Thêm tooltip nếu có
            if key in _PARAM_TOOLTIPS:
                _Tooltip(lbl, _PARAM_TOOLTIPS[key])
            v = self.vars[key] = tk.StringVar(value=format_number(value, key))
            if choices:
                entry = ttk.Combobox(frame, textvariable=v, values=choices,
                                     state='readonly', width=32)
                entry.bind("<MouseWheel>",
                           lambda e: (ScrollableFrame._route_wheel(e), "break")[1])
                entry.bind("<Button-4>",
                           lambda e: (ScrollableFrame._route_wheel(e), "break")[1])
                entry.bind("<Button-5>",
                           lambda e: (ScrollableFrame._route_wheel(e), "break")[1])
            else:
                entry = ttk.Entry(frame, textvariable=v, width=34,
                                  style='Required.TEntry' if key in _REQUIRED_FIELDS else 'TEntry')
                entry.bind('<FocusOut>',
                           lambda _e, k=key, ent=entry, var=v: _validate_entry(k, ent, var),
                           add='+')
                if key in _PARAM_TOOLTIPS:
                    _Tooltip(entry, _PARAM_TOOLTIPS[key])
            entry.grid(row=row, column=1, sticky='ew', padx=12, pady=5)
            frame.columnconfigure(1, weight=1)
            self.widgets[key] = (lbl, entry)
            return v

        # Tab 1: Chung
        field(basic_body, 'name', L('Tên lớp đất'), soil.name, 0)
        field(basic_body, 'gamma', L('Dung trọng tự nhiên γ (T/m³)'), soil.gamma, 1)
        category = field(basic_body, 'category', L('Phân loại đất'), soil.category, 2,
                         (L('Đất dính'), L('Đất rời')))

        field(basic_body, 'cohesion_c', L('Lực dính c dùng tính Rtc (T/m²)'), soil.cohesion_c, 5)
        field(basic_body, 'friction_phi', L('Góc ma sát φ dùng tính Rtc (độ)'), soil.friction_phi, 6)
        self.clay_frame = ttk.LabelFrame(basic_body,
                                         text=L('Đặc trưng đất dính'), padding=10)
        self.clay_frame.grid(row=3, column=0, columnspan=2, sticky='ew', pady=8)
        field(self.clay_frame, 'state', L('Trạng thái cố kết'), soil.state, 0,
              (L('Quá cố kết'), L('Cố kết thường')))
        field(self.clay_frame, 'drainage', L('Số mặt thoát nước (1 hoặc 2)'),
              soil.drainage, 1, ('1', '2'))

        field(self.clay_frame, 'e0', L('Hệ số rỗng ban đầu e₀'), str(soil.e0), 2)
        self.radial_treatment = treatment.startswith(('PVD', 'SD'))
        field(self.clay_frame, 'co', L('Lực dính ban đầu Co (T/m²)'), soil.co, 3)
        field(self.clay_frame, 'phi_cu_effective', L('φ′ hữu hiệu CU (độ; trống nếu không có CU)'),
              '' if soil.phi_cu_effective is None else soil.phi_cu_effective, 4)
        ttk.Label(self.clay_frame, text=L('Ch/Cv và m nhập tại bảng thông số PVD / SD.')).grid(row=5,column=0,columnspan=2,sticky='w')

        self.sand_frame = ttk.LabelFrame(basic_body,
                                         text=L('Đặc trưng đất rời'), padding=10)
        self.sand_frame.grid(row=4, column=0, columnspan=2, sticky='ew', pady=8)
        field(self.sand_frame, 'spt_n', L('Chỉ số SPT N'), soil.spt_n, 0)
        field(self.sand_frame, 'sand_method', L('Phương pháp tính lún'),
              soil.sand_method, 1, ('e–SPT (Hough)', 'De Beer'))

        lbl_info = self.method_info = ttk.Label(
            compression_body,
            text=L('Phương pháp tính lún:') + f" [{self.method}] · "
                 + L('Nhập Cc, Cs, Pc bên dưới.'),
            foreground='#1E3A8A',
            font=(UI_FONT, 9, 'italic')
        )
        lbl_info.pack(anchor='w', pady=(0, 6))

        self.cc_frame = ttk.LabelFrame(compression_body,
                                       text=L('Chỉ số nén lún (Cc, Cs, Pc)'),
                                       padding=10)
        self.cc_frame.pack(fill='x', pady=6)
        for idx, (key, label, val) in enumerate([
            ('cc', L('Chỉ số nén Cc'), soil.cc),
            ('cs', L('Chỉ số nén lại Cs'), soil.cs),
            ('pc', L('Áp lực tiền cố kết Pc (T/m²)'), soil.pc),
        ]):
            field(self.cc_frame, key, label, val, idx)

        self.ep_frame = ttk.Frame(compression_body)
        self.ep_frame.pack(fill='both', expand=True, pady=6)
        self._lab_grid(self.ep_frame, 'ep', 'e', soil.ep, soil.e,
                       L('Áp lực P (kg/cm²)'), L('Hệ số rỗng e'))

        self.mv_frame = ttk.Frame(compression_body)
        self._lab_grid(self.mv_frame, 'mvp', 'mv', soil.mvp, soil.mv,
                       L('Áp lực P (kg/cm²)'), L('Mv (m²/T)'))

        scalar_cv = ttk.Frame(cv_body); scalar_cv.pack(fill='x', pady=(0, 9))
        field(scalar_cv, 'cv_constant', L('Cv trung bình (10⁻³ cm²/s)'),
              '' if soil.cv_constant is None else str(soil.cv_constant), 0)
        self._lab_grid(cv_body, 'cvp', 'cv', soil.cvp, soil.cv,
                       L('Áp lực P (kg/cm²)'), L('Cv (10^-3 cm²/s)'))

        category.trace_add('write', lambda *_: self.update_visibility())
        self.update_visibility()

        self.bind('<Escape>', lambda _e: self.destroy())
        self.bind('<Return>', lambda _e: self.commit())

    def _lab_grid(self, parent, xkey, ykey, xvals, yvals, xlabel, ylabel):
        box = ttk.LabelFrame(parent,
                             text=f'{ylabel} ' + _L('theo áp lực thí nghiệm P',
                                                    self.language),
                             padding=10)
        box.pack(anchor='w', fill='x')
        ttk.Label(box, text=_L('STT', self.language),
                  font=(UI_FONT, 9, 'bold')).grid(row=0, column=0,
                                                            padx=10, pady=(0, 4))
        ttk.Label(box, text=xlabel,
                  font=(UI_FONT, 9, 'bold')).grid(row=0, column=1,
                                                            padx=10, pady=(0, 4))
        ttk.Label(box, text=ylabel,
                  font=(UI_FONT, 9, 'bold')).grid(row=0, column=2,
                                                            padx=10, pady=(0, 4))
        self.grid_vars[xkey], self.grid_vars[ykey] = [], []
        for i, (x, y) in enumerate(zip(xvals, yvals), 1):
            ttk.Label(box, text=str(i)).grid(row=i, column=0)
            for col, key, value in ((1, xkey, x), (2, ykey, y)):
                var = tk.StringVar(value=format_number(value, 'cv' if key == 'cv' else 'e0' if key == 'e' else key) if value is not None else '')
                self.grid_vars[key].append(var)
                entry = ttk.Entry(box, width=20, textvariable=var)
                entry.grid(row=i, column=col, padx=10, pady=3)

    def update_visibility(self):
        L = lambda s: _L(s, self.language)
        category = self._canonical(self.vars['category'].get())
        clay = category == 'Đất dính'
        allowed = soil_parameter_keys(self.method, category)
        for key, pair in self.widgets.items():
            if key in allowed:
                for widget in pair: widget.grid()
            else:
                for widget in pair: widget.grid_remove()
        if clay:
            self.sand_frame.grid_remove(); self.clay_frame.grid()
        else:
            self.clay_frame.grid_remove(); self.sand_frame.grid()
        for frame in (self.cc_frame, self.ep_frame, self.mv_frame): frame.pack_forget()
        active = self.cc_frame if 'cc' in allowed else self.ep_frame if 'ep' in allowed else self.mv_frame
        if clay: active.pack(fill='both', expand=True, pady=6)
        self.method_info.configure(text=L('Phương pháp tính lún:') + ' ' + self.method)
        self.tabs.tab(self.compression_tab, text=L('2. Nén lún') + ' · ' + self.method,
                      state='normal' if clay else 'hidden')
        self.tabs.tab(self.cv_tab, state='normal' if clay else 'hidden')

    def _series(self, key, label):
        out = []
        for i, var in enumerate(self.grid_vars[key], 1):
            raw = var.get().strip()
            out.append(number(raw, f'{label} hàng {i}') if raw else 0.0)
        return out

    def _highlight_required(self):
        """Đánh dấu đỏ các Entry bắt buộc đang bị trống."""
        required = _REQUIRED_FIELDS.copy()
        cat_var = self.vars.get('category')
        if cat_var:
            cat = self._canonical(cat_var.get())
            if cat == 'Đất dính':
                required |= _REQUIRED_CLAY
            elif cat == 'Đất rời':
                required |= _REQUIRED_SAND
        for key in required:
            if key not in self.vars:
                continue
            val = self.vars[key].get().strip()
            pair = self.widgets.get(key, ())
            if len(pair) >= 2 and isinstance(pair[1], ttk.Entry):
                pair[1].configure(style='Invalid.TEntry' if not val else 'Valid.TEntry')

    def commit(self):
        L = lambda s: _L(s, self.language)
        self._highlight_required()
        v = self.vars
        try:
            s = replace(self.soil, name=v['name'].get().strip(),
                        thickness=self.soil.thickness,
                        gamma=number(v['gamma'].get(), L('Dung trọng')),
                        category=self._canonical(v['category'].get()))
            s.cohesion_c = number_or_zero(v['cohesion_c'].get())
            s.friction_phi = number_or_zero(v['friction_phi'].get())
            if s.cohesion_c < 0 or not 0 <= s.friction_phi < 90:
                raise ValueError(L('c phải không âm và 0 ≤ φ < 90 độ.'))
            if s.category == 'Đất dính':
                s.state = self._canonical(v['state'].get())
                s.drainage = int(number(v['drainage'].get(),
                                        L('Số mặt thoát nước')))
                s.co = number_or_zero(v['co'].get())
                if self.method == 'Cc/Cs/Pc':
                    s.e0 = number_or_zero(v['e0'].get())
                    s.cc = number_or_zero(v['cc'].get())
                    s.cs = number_or_zero(v['cs'].get())
                    s.pc = number_or_zero(v['pc'].get())
                elif self.method == 'Mv–logP':
                    s.e0 = number_or_zero(v['e0'].get())
                    s.mvp = self._series('mvp', 'P Mv')
                    s.mv = self._series('mv', 'Mv')
                elif self.method == 'e–logP':
                    s.ep = self._series('ep', 'P e–logP')
                    s.e = self._series('e', 'e')
                    if s.ep and s.ep[0] == 0 and s.e[0] > 0:
                        s.e0 = s.e[0]
                s.cvp = self._series('cvp', 'P Cv')
                s.cv = self._series('cv', 'Cv')
                raw_cv = v['cv_constant'].get().strip()
                s.cv_constant = number(raw_cv, 'Cv trung bình') if raw_cv else None
                if s.cv_constant is not None and s.cv_constant <= 0:
                    raise ValueError('Cv trung bình phải lớn hơn 0.')
            else:
                s.spt_n = number(v['spt_n'].get() or '0', 'SPT N trung bình')
                s.sand_method = v['sand_method'].get()
            if s.gamma <= 0:
                raise ValueError(L('Dung trọng phải lớn hơn 0.'))
        except ValueError as exc:
            messagebox.showerror(L('Lỗi số liệu'), str(exc), parent=self)
            return
        self.on_save(s)
        self.destroy()

    def _canonical(self, value):
        """Chuyển giá trị hiển thị (đã dịch) về giá trị gốc tiếng Việt."""
        mapping = {
            'Cohesive soil': 'Đất dính', 'Đất dính': 'Đất dính',
            'Granular soil': 'Đất rời', 'Đất rời': 'Đất rời',
            'Overconsolidated': 'Quá cố kết', 'Quá cố kết': 'Quá cố kết',
            'Normally consolidated': 'Cố kết thường', 'Cố kết thường': 'Cố kết thường',
        }
        return mapping.get(value, value)


def show_unpenetrated_window(parent, project: Project, unp_res: dict):
    """Cửa sổ hiển thị bảng phân tố lún đới đất chưa xử lý bên dưới đáy bấc/cọc."""
    language = _get_language(parent)
    L = lambda s: _L(s, language)

    dlg = tk.Toplevel(parent)
    is_sd = ("SD" in project.treatment or project.drain_type == 'Cọc cát')
    drain_title = L("Cọc cát SD") if is_sd else L("Bấc thấm PVD")
    dlg.title(L(f'Bảng tính lún đới đất chưa xử lý dưới đáy') + f' {drain_title}')

    sw, sh = parent.winfo_screenwidth(), parent.winfo_screenheight()
    dlg_w = min(1200, max(1000, int(sw * 0.85)))
    dlg_h = min(650, max(460, int(sh * 0.65)))
    dlg.geometry(f"{dlg_w}x{dlg_h}+{max(0, (sw - dlg_w) // 2)}+{max(0, (sh - dlg_h) // 2)}")
    dlg.minsize(900, 400)
    dlg.transient(parent)

    top_frame = tk.Frame(dlg, bg='#FEF3C7', padx=14, pady=10, relief='solid', bd=1)
    top_frame.pack(fill='x', padx=10, pady=(10, 6))

    h_remain = unp_res.get('residual_thickness', 0.0)
    sc_tim = unp_res.get('sum_sc_tim', 0.0)
    res_tim = unp_res.get('sum_res_tim', 0.0)

    warn_title = L("⚠️ CẢNH BÁO:") + f" {drain_title.upper()} " + L("CẮM LƠ LỬNG (CHƯA XUYÊN HẾT TẦNG ĐẤT YẾU)")
    tk.Label(top_frame, text=warn_title,
             font=(UI_FONT, 10, 'bold'),
             fg='#92400E', bg='#FEF3C7').pack(anchor='w')

    desc_txt = (L("Chiều dài cắm:") + f" L = {project.drain_length:.2f} m  •  "
                + L("Chiều dày đới đất nén lún chưa xử lý còn lại:") + f" ΔH = {h_remain:.2f} m\n"
                + L("Độ lún cố kết đới dưới (Tim):") + f" Sc = {sc_tim:.2f} cm  •  "
                + L("Sc dư đới dưới =") + f" {res_tim:.2f} cm")
    tk.Label(top_frame, text=desc_txt, font=(UI_FONT, 9),
             fg='#B45309', bg='#FEF3C7', justify='left').pack(anchor='w', pady=(3, 0))

    tbl_frame = ttk.Frame(dlg, padding=8)
    tbl_frame.pack(fill='both', expand=True, padx=10)

    cols = ('stt', 'layer', 'z', 'h', 'gamma', 'e0', 'cc', 'cs', 'pc',
            'p0', 'dp_tim', 'dp_vai', 'sc_tim', 'res_tim')
    headers = [
        L('STT'), L('Tên lớp'), 'Z (m)', 'h (m)', "γ' (T/m³)", 'e₀', 'Cc', 'Cs',
        'Pc (T/m²)', 'P₀ (T/m²)', 'Δp Tim', 'Δp Vai',
        L('Sc Tim (cm)'), L('Sc dư (cm)'),
    ]
    widths = [45, 120, 65, 65, 75, 65, 65, 65, 75, 75, 75, 75, 85, 85]

    style = ttk.Style(dlg)
    style.configure("Unp.Treeview.Heading",
                    font=(UI_FONT, 9, 'bold'), padding=(3, 5))
    style.configure("Unp.Treeview",
                    font=(UI_FONT, 9), rowheight=21)

    tree = ttk.Treeview(tbl_frame, columns=cols, show='headings', style="Unp.Treeview")
    sb_y = ttk.Scrollbar(tbl_frame, orient='vertical', command=tree.yview)
    sb_x = ttk.Scrollbar(tbl_frame, orient='horizontal', command=tree.xview)
    tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

    for c, h, w in zip(cols, headers, widths):
        tree.heading(c, text=h)
        tree.column(c, width=w, anchor='w' if c == 'layer' else 'center',
                    stretch=False)

    tree.tag_configure('even', background='#FFFFFF')
    tree.tag_configure('odd', background='#F8FAFC')
    tree.tag_configure('total', background='#FEF3C7',
                       font=(UI_FONT, 9, 'bold'))

    tree.pack(side='left', fill='both', expand=True)
    sb_y.pack(side='right', fill='y')
    sb_x.pack(side='bottom', fill='x')

    csv_rows = [headers]
    for idx, el in enumerate(unp_res.get('elements', [])):
        row = (
            el['stt'], el['tên'], f"{el['z_m']:.2f}", f"{el['h_m']:.2f}",
            f"{el['gamma_eff']:.2f}", f"{el['e0']:.3f}", f"{el['cc']:.3f}",
            f"{el['cs']:.3f}", f"{el['pc']:.2f}", f"{el['p0']:.2f}",
            f"{el['dp_tim']:.2f}", f"{el['dp_vai']:.2f}",
            f"{el['sc_tim']:.2f}", f"{el['res_tim']:.2f}"
        )
        tree.insert('', 'end', values=row, tags=('odd' if idx % 2 else 'even',))
        csv_rows.append(list(row))
    _fit_tree_columns(tree, headers, dlg,
                      caps=[48, 160, 70, 70, 80, 65, 60, 60, 85, 85, 80, 80, 95, 95])

    tot_row = (L('TỔNG'), '', '', f"{unp_res.get('sum_h', 0.0):.2f}",
               '', '', '', '', '', '', '', '', f"{sc_tim:.2f}", f"{res_tim:.2f}")
    tree.insert('', 'end', values=tot_row, tags=('total',))
    csv_rows.append(list(tot_row))

    bot_bar = ttk.Frame(dlg, padding=(10, 9))
    bot_bar.pack(fill='x')

    def export_csv():
        dest = filedialog.asksaveasfilename(
            parent=dlg, defaultextension='.csv',
            filetypes=[('CSV Document', '*.csv')],
            initialfile='Bang_Lun_Doi_Duoi_Mui_Bac.csv')
        if dest:
            try:
                with open(dest, 'w', newline='', encoding='utf-8-sig') as f:
                    csv.writer(f).writerows(csv_rows)
                messagebox.showinfo(L('Thành công'),
                                    L('Đã xuất dữ liệu ra tệp:') + f'\n{dest}',
                                    parent=dlg)
            except Exception as e:
                messagebox.showerror(L('Lỗi xuất tệp'), str(e), parent=dlg)

    dlg._soilfirm_export_table = export_csv
    dlg._soilfirm_export_mode = parent.design_mode.get()
    dlg.bind('<FocusIn>', lambda _event: setattr(parent, '_active_export_dialog', dlg), add='+')
    table_menu = tk.Menu(dlg)
    file_menu = tk.Menu(table_menu, tearoff=False)
    file_menu.add_command(label=L('Xuất bảng dữ liệu'), command=export_csv)
    table_menu.add_cascade(label='File', menu=file_menu)
    dlg.configure(menu=table_menu)
    ttk.Button(bot_bar, text=L("Đóng"), command=dlg.destroy).pack(side='right')


def show_stage_strength_dialog(parent, project: Project, tdc: float, horiz_type: str,
                               compute=None):
    language = _get_language(parent)
    L = lambda s: _L(s, language)

    schedule = stage_schedule(project)
    if not schedule:
        messagebox.showwarning(L('Cảnh báo'),
                               L('Vui lòng khai báo lịch trình đắp phân kỳ ở mục 3.'),
                               parent=parent)
        return

    mode = project.treatment.lower()
    has_surcharge = getattr(project, 'surcharge_height', 0.0) > 0 and 'gia tải' in mode
    has_vacuum = getattr(project, 'vacuum_pressure', 0.0) > 0 and 'chân không' in mode

    extra_duration = 0.0
    if has_surcharge:
        extra_duration = max(extra_duration, getattr(project, 'surcharge_days', 0.0))
    if has_vacuum:
        extra_duration = max(extra_duration, getattr(project, 'vacuum_days', 0.0))

    end_wait = schedule[-1]['chờ_đến'] if schedule else 0.0
    horizon = max(end_wait, end_wait + extra_duration) + 30.0

    run_model = compute or (lambda fn, *args, **kwargs: fn(*args, **kwargs))
    history_tim, info_tim = run_model(treatment_history, project, horizon,
                                      step_days=1.0, axis_index=0)
    history_vai, info_vai = run_model(treatment_history, project, horizon,
                                      step_days=1.0, axis_index=1)

    tim_dict = {round(r['ngày'], 3): r for r in history_tim}
    vai_dict = {round(r['ngày'], 3): r for r in history_vai}

    def get_rec(d_map, t):
        if not d_map:
            return None
        k = min(d_map.keys(), key=lambda x: abs(x - t))
        return d_map[k]

    dlg = tk.Toplevel(parent)
    dlg.title(L('Kết quả cố kết, lún dư và cường độ theo giai đoạn'))
    dlg._popup_fit_scheduled = True

    screen_w, screen_h = parent.winfo_screenwidth(), parent.winfo_screenheight()
    dlg_w = min(1200, screen_w - 40)
    dlg_h = min(560, screen_h - 80)
    dlg.geometry(f'{dlg_w}x{dlg_h}+{max(0, (screen_w - dlg_w) // 2)}'
                 f'+{max(0, (screen_h - dlg_h) // 2)}')
    dlg.minsize(min(650, dlg_w), min(180, dlg_h))
    dlg.transient(parent)

    top_bar = tk.Frame(dlg, bg='#F1F5F9', padx=14, pady=10)
    top_bar.pack(fill='x', side='top')

    if horiz_type in ('Lớp đệm cát', 'Sand drainage blanket'):
        horiz_str = L("Thoát nước ngang: Lớp đệm cát") + f" (Tdc = {tdc:.2f} " + L("ngày") + ")"
    else:
        horiz_str = L("Thoát nước ngang:") + f" {horiz_type}"
    info_txt = L("Phương án:") + f" {project.treatment}   |   {horiz_str}"
    tk.Label(top_bar, text=info_txt, font=(UI_FONT, 9, 'bold'),
             fg='#1E3A8A', bg='#F1F5F9').pack(side='left')

    table_frame = tk.Frame(dlg, padx=8, pady=6)
    table_frame.pack(fill='both', expand=True)

    columns = [
        ('gd', L('Giai đoạn'), 90, 'center'),
        ('h_stage', L('H đắp (m)'), 75, 'center'),
        ('phase', L('Mốc tính toán'), 185, 'w'),
        ('day', L('Thời gian (ngày)'), 100, 'center'),
        ('u_tot', L('U chung (%)'), 85, 'center'),
        ('sc_tot', L('St (cm)'), 90, 'center'),
        ('res_tot', L('Sc dư (cm)'), 110, 'center'),
        ('layer_no', L('Lớp'), 40, 'center'),
        ('layer_name', L('Tên lớp đất'), 110, 'w'),
        ('thick', L('Dày h (m)'), 70, 'center'),
        ('dp_tim', "Δσ' Tim (T/m²)", 105, 'center'),
        ('dp_vai', "Δσ' Vai (T/m²)", 105, 'center'),
        ('u_layer', L('U lớp (%)'), 80, 'center'),
        ('cu_tim', 'Cu Tim (T/m²)', 95, 'center'),
        ('cu_vai', 'Cu Vai (T/m²)', 95, 'center'),
    ]

    col_ids = [c[0] for c in columns]
    headers = [c[1] for c in columns]

    style = ttk.Style(dlg)
    style.configure("Excel.Treeview",
                    font=(UI_FONT, 9), rowheight=20)
    style.configure("Excel.Treeview.Heading",
                    font=(UI_FONT, 9, 'bold'), padding=(3, 4))

    tree = ttk.Treeview(table_frame, columns=col_ids, show='headings',
                        style="Excel.Treeview", selectmode='browse')
    for cid, label, width, align in columns:
        tree.heading(cid, text=label)
        tree.column(cid, width=width, anchor=align, stretch=False)

    tree.tag_configure('even', background='#FFFFFF')
    tree.tag_configure('odd', background='#F8FAFC')
    tree.tag_configure('phase_b', background='#F1F5F9')
    tree.tag_configure('phase_c', background='#FEF3C7')

    sb_y = ttk.Scrollbar(table_frame, orient='vertical', command=tree.yview)
    sb_x = ttk.Scrollbar(table_frame, orient='horizontal', command=tree.xview)
    tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

    tree.pack(side='left', fill='both', expand=True)
    sb_y.pack(side='right', fill='y')
    sb_x.pack(side='bottom', fill='x')

    export_rows = [headers]
    row_count = 0

    for i, stg in enumerate(schedule):
        g = stg['giai_đoạn']
        t_end_fill = stg['kết_thúc']
        t_end_wait = stg['chờ_đến']
        h_stage = stg['h_cuối']

        phases = [
            (L(f"GĐ {g}"), h_stage, L(f"A. Sau đắp GĐ{g}"), t_end_fill, 'even'),
        ]

        if t_end_wait > t_end_fill:
            phases.append((L(f"GĐ {g}"), h_stage,
                           L(f"B. Hết chờ GĐ{g}"), t_end_wait, 'phase_b'))

        if i == len(schedule) - 1 and extra_duration > 0:
            t_end_extra = t_end_wait + extra_duration
            h_eq = h_stage
            if has_surcharge:
                h_eq += (getattr(project, 'surcharge_height', 0.0)
                         * (getattr(project, 'surcharge_gamma', 1.8) / project.gamma_fill))

            if has_surcharge and has_vacuum:
                gd_name = L("GT + Pvac")
                p_name = L("C. Hết Gia tải & Chân không")
            elif has_vacuum:
                gd_name = L("Chân không")
                p_name = L("C. Hết hút chân không")
            else:
                gd_name = L("Gia tải")
                p_name = L("C. Hết gia tải")

            phases.append((gd_name, h_eq, p_name, t_end_extra, 'phase_c'))

        for gd_label, h_val, phase_label, t_day, tag_name in phases:
            rec_tim = get_rec(tim_dict, t_day)
            rec_vai = get_rec(vai_dict, t_day)

            if not rec_tim or not rec_vai:
                continue

            is_phase_c = (tag_name == 'phase_c')
            hs_active = (getattr(project, 'surcharge_height', 0.0)
                         if (has_surcharge and is_phase_c) else 0.0)
            vac_active = (getattr(project, 'vacuum_pressure', 0.0)
                          if (has_vacuum and is_phase_c) else 0.0)

            trial_p = replace(
                project,
                h_design=h_stage + hs_active * (getattr(project, 'surcharge_gamma', 1.8) / project.gamma_fill),
                h_kcad=0.0, h_bl=0.0)
            trial_p.update_geometry()

            for lyr_idx, s in enumerate(project.soils):
                top = sum(lyr.thickness for lyr in project.soils[:lyr_idx])
                z = top + s.thickness / 2.0

                dp_tim_geom = pressure(trial_p, z, 0.0)
                dp_vai_geom = pressure(trial_p, z, project.crest_half_width)

                inc_tim = dp_tim_geom + vac_active
                inc_vai = dp_vai_geom + vac_active

                cu_tim_val = (rec_tim['C_t_m2'][lyr_idx]
                              if lyr_idx < len(rec_tim['C_t_m2']) else 0.0)
                cu_vai_val = (rec_vai['C_t_m2'][lyr_idx]
                              if lyr_idx < len(rec_vai['C_t_m2']) else 0.0)

                final_sc_lyr = info_tim[lyr_idx]['Sc_cuối_cm']
                cur_sc_lyr = (rec_tim['Sc_lớp_cm'][lyr_idx]
                              if lyr_idx < len(rec_tim['Sc_lớp_cm']) else 0.0)

                if final_sc_lyr > 0:
                    u_layer = cur_sc_lyr / final_sc_lyr * 100.0
                else:
                    u_layer = 100.0 if s.category == 'Đất dính' else 100.0

                vals = (
                    gd_label,
                    f"{h_val:.2f}",
                    phase_label,
                    f"{t_day:.2f}",
                    f"{rec_tim['U_%']:.2f}",
                    f"{rec_tim['Sc_cm']:.2f}",
                    f"{rec_tim['Sc_dư_cm']:.2f}",
                    f"{lyr_idx + 1}",
                    s.name or L(f"Lớp {lyr_idx+1}"),
                    f"{s.thickness:.2f}",
                    f"{inc_tim:.2f}",
                    f"{inc_vai:.2f}",
                    f"{u_layer:.2f}",
                    f"{cu_tim_val:.2f}",
                    f"{cu_vai_val:.2f}",
                )

                row_tag = (tag_name if tag_name in ('phase_b', 'phase_c')
                           else ('even' if row_count % 2 == 0 else 'odd'))
                tree.insert('', 'end', values=vals, tags=(row_tag,))
                export_rows.append(list(vals))
                row_count += 1

    _fit_tree_columns(tree, headers, dlg,
                      caps=[105, 90, 205, 110, 95, 85, 95, 50, 160, 85,
                            110, 110, 90, 110, 110])

    bottom_bar = tk.Frame(dlg, padx=14, pady=8)
    bottom_bar.pack(fill='x', side='bottom')

    def export_excel():
        dest = filedialog.asksaveasfilename(
            parent=dlg, defaultextension='.csv',
            filetypes=[('CSV Document', '*.csv')],
            initialfile='Bang_Cuong_Do_Va_Co_Ket.csv')
        if dest:
            try:
                with open(dest, 'w', newline='', encoding='utf-8-sig') as f:
                    csv.writer(f).writerows(export_rows)
                messagebox.showinfo(L('Thành công'),
                                    L('Đã xuất dữ liệu ra tệp:') + f'\n{dest}',
                                    parent=dlg)
            except Exception as e:
                messagebox.showerror(L('Lỗi xuất tệp'), str(e), parent=dlg)

    dlg._soilfirm_export_table = export_excel
    dlg._soilfirm_export_mode = parent.design_mode.get()
    dlg.bind('<FocusIn>', lambda _event: setattr(parent, '_active_export_dialog', dlg), add='+')
    table_menu = tk.Menu(dlg)
    file_menu = tk.Menu(table_menu, tearoff=False)
    file_menu.add_command(label=L('Xuất bảng dữ liệu'), command=export_excel)
    table_menu.add_cascade(label='File', menu=file_menu)
    dlg.configure(menu=table_menu)
    ttk.Button(bottom_bar, text=L('Đóng'),
               command=dlg.destroy).pack(side='right', padx=4)

    def fit_to_table():
        if not dlg.winfo_exists():
            return
        width = min(screen_w - 40,
                    sum(tree.column(cid, 'width') for cid in col_ids) + 44)
        visible_rows = min(18, max(3, row_count))
        tree.configure(height=visible_rows)
        height = min(screen_h - 80, max(560, 122 + 20 * visible_rows))
        dlg.geometry(f'{width}x{height}+{max(0, (screen_w - width) // 2)}'
                     f'+{max(0, (screen_h - height) // 2)}')

    dlg.after_idle(fit_to_table)


def show_help_dialog(parent):
    language = _get_language(parent)
    L = lambda s: _L(s, language)

    dlg = tk.Toplevel(parent)
    dlg.title(L('SoilFirm Pro - Hướng Dẫn Sử Dụng & Thuyết Minh Tính Toán'))

    screen_w, screen_h = parent.winfo_screenwidth(), parent.winfo_screenheight()
    dlg_w = min(1060, max(880, int(screen_w * 0.72)))
    dlg_h = min(740, max(540, int(screen_h * 0.75)))

    dlg.geometry(f'{dlg_w}x{dlg_h}+{max(0, (screen_w - dlg_w) // 2)}'
                 f'+{max(0, (screen_h - dlg_h) // 2)}')
    dlg.minsize(860, 500)
    dlg.transient(parent)

    nb = ttk.Notebook(dlg)
    nb.pack(fill='both', expand=True, padx=8, pady=8)

    tab_guide = ttk.Frame(nb)
    tab_theory = ttk.Frame(nb)
    nb.add(tab_guide, text=L('📖 1. Hướng Dẫn Sử Dụng (Quy Trình 5 Bước)'))
    nb.add(tab_theory, text=L('📐 2. Cơ Sở Lý Thuyết & Công Thức Tính Toán (TCVN & TCCS)'))

    def setup_text(p_tab, content):
        txt = tk.Text(p_tab, wrap='word', font=(UI_FONT, 9),
                      padx=16, pady=16, bg='#F8FAFC', fg='#0F172A')
        sb = ttk.Scrollbar(p_tab, orient='vertical', command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        txt.insert('1.0', content)
        txt.configure(state='disabled')

    if language == 'en':
        guide_content = """5-STEP DESIGN WORKFLOW FOR SOFT SOIL TREATMENT IN SOILFIRM PRO

SOILFIRM PRO is organized into 5 logical sequential steps per Vietnamese road design standards:

STEP 1: PROJECT INFORMATION & SETTLEMENT CRITERIA
- Enter project info: project name, package, chainage (From KM ... To KM ...), design cross section.
- Select "Road class" and "Fill location" (standard, bridge abutment, culvert).
- Software automatically looks up allowable settlement [ΔS] per 22 TCN 262-2000 & TCVN 9355:
  + Expressway / Class I-II (Vtk ≥ 80 km/h): Standard section [ΔS] = 20 cm; Bridge abutment [ΔS] = 10 cm.
  + Class III (Vtk ≤ 60 km/h): Standard section [ΔS] = 30 cm; Culvert [ΔS] = 20 cm; Bridge abutment [ΔS] = 10 cm.

STEP 2: EMBANKMENT GEOMETRY & HYDROGEOLOGY
- Design fill height Htk (m), crest width B (m), side slope m (1:m), pavement thickness Hkcad (m).
- Counterweight berm: optional, with height H, width L and slope m.
- Ground elevation Ztn and groundwater level GWL: directly affect effective unit weight γ' and overburden stress P0.
- Settlement method: most common is Cc/Cs/Pc (e-logP compression curve).
- Maximum sublayer dz (usually 1.0 m) and limit ratio Δp / Po (typically 0.15).

STEP 3: SOIL PROFILE & CONSOLIDATION PARAMETERS
- Declare soil layers from top to bottom.
- Enter layer thickness H (m) directly in the strata table by double-clicking the "Thickness H (m)" cell.
- For cohesive layers (soft clay, mud):
  + Natural unit weight γ, state (Normally Consolidated NC or Overconsolidated OC).
  + Number of natural drainage faces (1 if bottom rests on hard clay/impermeable rock, 2 if interbedded sand/gravel).
  + Compression index Cc, recompression index Cs (typically Cs ≈ Cc / 5), preconsolidation pressure Pc.
  + Ch/Cv ratio (horizontal to vertical permeability, typical alluvial soil Ch/Cv = 1.5 - 3.0).
  + Initial cohesion Co and strength increase factor m (CU) for stability and shear strength checks over time.

STEP 4: NATURAL SETTLEMENT VERIFICATION (BEFORE TREATMENT)
- Click "🔄 Iterate Hbl": software automatically iterates Euler method to find settlement compensation height Hbl so that after settlement, design elevation Htk is achieved.
- Click "Calculate consolidation": view stress distribution and settlement of each sublayer at Center, Shoulder, Toe.
- Click "Settlement over time": software automatically computes natural settlement over time.
- Compare residual settlement at service time with allowable [ΔS]. If NOT PASS, proceed to Step 5.

STEP 5: SELECT & DESIGN GROUND IMPROVEMENT SOLUTION
- Choose option: Natural waiting, Prefabricated Vertical Drains (PVD), or Sand Drains (SD).
- Optional combination: Preloading (Surcharge) and/or Vacuum.
- Horizontal drainage layout: Horizontal PVD or Sand drainage blanket (h = 0.5m, construction time Tdc).
- PVD/SD arrangement: triangular or square pattern, spacing d (m), depth L (m).
- Staged filling: declare stages H1, H2, H3, fill rate (cm/day) and waiting time between stages.
- Click "Calculate PVD, SD consolidation" and "Settlement chart": check residual settlement after treatment.
- Click "Untreated residual settlement": view Chờ lún result or consolidation settlement of soil below drain tip when drains are floating.
"""
        theory_content = """GEOTECHNICAL THEORY & FORMULAS

1. ADDITIONAL STRESS UNDER TRAPEZOIDAL EMBANKMENT (OSTERBERG / POULOS)
Additional stress Δσz at depth z and distance x from centerline is computed by integrating strip load:
   q = γ_fill * H_design
   Δσz = ∫ [ (2 * q(ξ) * z³) / (π * ((ξ - x)² + z²)²) ] dξ
The software uses Simpson's rule with 400 strips for accurate integration even at shoulder and toe.

2. INFLUENCE COMPRESSION DEPTH (Ha)
Per 22 TCN 262-2000, compression depth ha is limited where additional stress from embankment is ≤ 15% of effective overburden stress:
   Δσz(ha) ≤ 0.15 * σ'_v0(ha)

3. PRIMARY CONSOLIDATION SETTLEMENT (Sc) BY Cc, Cs, Pc
Settlement of a sublayer of thickness h with initial void ratio e0:
- Normally consolidated (NC: Pc ≤ P0):
   S_c = h * [ Cc / (1 + e0) ] * log10( (P0 + Δp) / P0 )
- Overconsolidated (OC: Pc > P0):
   + If P0 + Δp ≤ Pc:
     S_c = h * [ Cs / (1 + e0) ] * log10( (P0 + Δp) / P0 )
   + If P0 + Δp > Pc:
     S_c = h * [ Cs * log10(Pc / P0) + Cc * log10((P0 + Δp) / Pc) ] / (1 + e0)

4. SETTLEMENT COMPENSATION BY TRIAL-AND-ERROR (Hbl)
Since embankment subsides with the ground, the actual fill height must be increased:
   H_design = Htk + Hkcad + Hbl
   Hbl = S_t(H_design) = S_c + S_i
This nonlinear equation is solved by fixed-point Euler iteration with convergence tolerance < 0.001 m.

5. VERTICAL CONSOLIDATION THEORY (TERZAGHI)
Vertical time factor:
   Tv = (Cv * t) / (Hdr²)
Average vertical degree of consolidation:
   - When Tv ≤ 0.2827:  Uv = √(4 * Tv / π)
   - When Tv > 0.2827:  Uv = 1 - 10^( - (Tv + 0.085) / 0.933 )

6. RADIAL CONSOLIDATION THEORY BY HANSBO (PVD / SD)
Equivalent diameter of influence zone de:
   - Triangular pattern:   de = 1.05 * d
   - Square pattern:       de = 1.13 * d
Radial time factor:
   Th = (Ch * t) / (de²)
Total resistance factor F per TCVN 9355:2013:
   F = Fn + Fs + Fr
   Fn = [ n² / (n² - 1) ] * ln(n) - (3n² - 1) / (4n²)   with n = de / dw
   Fs = (kh / ks - 1) * ln(ds / dw)                    (smear zone)
   Fr = (2/3) * π * L² * (kh / qw)                      (drain resistance)
Radial degree of consolidation per Hansbo:
   Uh = 1 - exp( - 8 * Th / F )

7. THREE-DIMENSIONAL CONSOLIDATION BY CARRILLO
When both vertical and radial drainage occur:
   U = 1 - (1 - Uv) * (1 - Uh)

8. PRELOADING (SURCHARGE) & VACUUM
- Surcharge fill hs creates pressure Δp_s = γ_s * h_s, temporarily increasing consolidation stress to eliminate residual settlement quickly.
- Vacuum Pvac creates negative pore pressure equivalent to Pvac ≈ 70 - 80 kPa without slope instability risk.

9. UNDRAINED SHEAR STRENGTH INCREASE (Cu)
Shear strength of soft soil increases with degree of consolidation U:
   Cu(t) = C0 + m * (σ'v0 + Δσ'z - Pc) * U
where m is the strength increase factor from CU triaxial tests.
"""
    else:
        guide_content = """QUY TRÌNH 5 BƯỚC THIẾT KẾ XỬ LÝ NỀN ĐẤT YẾU TRÊN SOILFIRM PRO

SOILFIRM PRO được chuẩn hóa thành 5 bước logic liên hoàn theo tiêu chuẩn thiết kế cầu đường Việt Nam:

BƯỚC 1: THÔNG TIN DỰ ÁN & CHỈ TIÊU ĐÁNH GIÁ LÚN
- Nhập thông tin công trình: Tên dự án, gói thầu, lý trình (Từ KM ... Đến KM ...), mặt cắt tính toán.
- Chọn "Cấp đường" và "Vị trí đắp" (thông thường, đầu cầu, đầu cống).
- Phần mềm tự động tra và áp mức giới hạn độ lún cho phép [ΔS] theo 22 TCN 262-2000 & TCVN 9355:
  + Đường cao tốc / Cấp I-II (Vtk ≥ 80 km/h): Đoạn thông thường [ΔS] = 20 cm; Đoạn mố cầu [ΔS] = 10 cm.
  + Đường cấp III (Vtk ≤ 60 km/h): Đoạn thông thường [ΔS] = 30 cm; Cống [ΔS] = 20 cm; Mố cầu [ΔS] = 10 cm.

BƯỚC 2: THÔNG SỐ HÌNH HỌC NỀN ĐẮP & ĐỊA CHẤT THỦY VĂN
- Chiều cao đắp thiết kế Htk (m), bề rộng đỉnh B (m), hệ số mái dốc m (1:m), dày kết cấu áo đường Hkcad (m).
- Bệ phản áp (Counterweight): Tùy chọn có/không áp dụng, kích thước chiều cao H, chiều rộng L và mái dốc m.
- Cao độ tự nhiên Ztn và mực nước ngầm MNN: Ảnh hưởng trực tiếp đến dung trọng hiệu quả γ' và ứng suất bản thân P0.
- Chọn phương pháp tính lún: Phổ biến nhất là Cc/Cs/Pc (theo đường nén lún e-logP).
- Phân tố tính lún tối đa dz (thường lấy 1.0 m) và tỷ số giới hạn nén lún Δp / Po (quy định 0.15).

BƯỚC 3: MẶT CẮT ĐỊA TẦNG ĐỊA CHẤT & THÔNG SỐ CỐ KẾT
- Khai báo danh sách các lớp đất từ trên xuống dưới.
- Nhập trực tiếp bề dày lớp đất H (m) ngay trên bảng danh sách địa tầng bằng cách nhấp đúp vào cột "Dày H (m)".
- Với lớp đất dính (bùn sét, sét yếu):
  + Dung trọng tự nhiên γ, trạng thái (Cố kết thường NC hoặc Quá cố kết OC).
  + Số mặt thoát nước tự nhiên (1 mặt nếu đáy tựa sét cứng/đá kín nước, 2 mặt nếu kẹp cát cuội sỏi thoát nước).
  + Chỉ số nén lún Cc, nén lại Cs (thường lấy Cs ≈ Cc / 5), áp lực tiền cố kết Pc.
  + Tỷ số Ch/Cv (hệ số thấm ngang so với thấm đứng, thông thường đất bồi tích Ch/Cv = 1.5 - 3.0).
  + Lực dính ban đầu Co và hệ số tăng cường độ m (CU) để kiểm toán ổn định và sức kháng cắt theo thời gian.

BƯỚC 4: KIỂM TOÁN ĐỘ LÚN TỰ NHIÊN (TRƯỚC XỬ LÝ)
- Bấm "🔄 Tính lặp Hbl": Phần mềm lặp Euler tự động tìm chiều cao bù lún đắp thêm Hbl để khi lún xong đạt đúng cao độ thiết kế Htk.
- Bấm "Tính lún cố kết": Xem bảng phân bố ứng suất và lún từng phân tố tại Tim, Vai, Chân dốc.
- Bấm "Tính lún theo thời gian": Phần mềm tự động tính toán diễn biến lún tự nhiên theo thời gian.
- Đối chiếu độ lún còn dư tại thời điểm khai thác với giới hạn [ΔS]. Nếu KHÔNG ĐẠT, chuyển sang Bước 5.

BƯỚC 5: LỰA CHỌN & THIẾT KẾ GIẢI PHÁP GIA CỐ NỀN
- Chọn phương án: Chờ lún tự nhiên, Bấc thấm đứng (PVD), hoặc Cọc cát (SD).
- Tùy chọn kết hợp: Gia tải trước (Surcharge) và/hoặc Hút chân không (Vacuum).
- Bố trí thoát nước ngang: Bấc thấm ngang hoặc Đệm cát lọc (h = 0.5m, thời gian thi công Tdc).
- Bố trí bấc thấm/cọc cát: Sơ đồ tam giác hoặc hình vuông, cự ly cắm d (m), chiều dài cắm L (m).
- Thiết lập phân kỳ đắp: Khai báo các đợt đắp H1, H2, H3, tốc độ đắp (cm/ngày) và thời gian chờ giữa các đợt.
- Bấm "Tính lún PVD, SD" và "Biểu đồ lún": Kiểm tra độ lún còn dư sau xử lý bằng PVD hoặc SD.
- Bấm "Lún dư chưa xử lý": Xem kết quả Chờ lún hoặc độ lún cố kết của đất dưới mũi bấc/cọc khi cắm lửng.
"""
        theory_content = """CƠ SỞ LÝ THUYẾT & HỆ THỐNG CÔNG THỨC ĐỊA KỸ THUẬT

1. ỨNG SUẤT GIA TĂNG DƯỚI NỀN ĐẮP HÌNH THANG (OSTERBERG / POULOS)
Ứng suất gia tăng Δσz tại độ sâu z và khoảng cách x so với tim đường được tính tích phân phân tố tải trọng dải hình thang cân:
   q = γ_đắp * H_tt
   Δσz = ∫ [ (2 * q(ξ) * z³) / (π * ((ξ - x)² + z²)²) ] dξ
Phần mềm giải tích phân bằng quy tắc Simpson chia 400 dải vi phân, đảm bảo độ chính xác tuyệt đối ngay cả tại mép vai và chân cơ phản áp.

2. CHIỀU SÂU VÙNG NÉN LÚN ẢNH HƯỞNG (Ha)
Theo 22 TCN 262-2000, chiều sâu chịu nén ha được giới hạn tại vị trí mà ứng suất gia tăng do nền đắp gây ra nhỏ hơn hoặc bằng 15% ứng suất bản thân hiệu quả:
   Δσz(ha) ≤ 0.15 * σ'_v0(ha)

3. TÍNH LÚN CỐ KẾT SƠ CẤP (Sc) THEO Cc, Cs, Pc
Độ lún của phân tố đất dày h có hệ số rỗng ban đầu e0:
- Với đất cố kết thường (NC: Pc ≤ P0):
   S_c = h * [ Cc / (1 + e0) ] * log10( (P0 + Δp) / P0 )
- Với đất quá cố kết (OC: Pc > P0):
   + Nếu P0 + Δp ≤ Pc:
     S_c = h * [ Cs / (1 + e0) ] * log10( (P0 + Δp) / P0 )
   + Nếu P0 + Δp > Pc:
     S_c = h * [ Cs * log10(Pc / P0) + Cc * log10((P0 + Δp) / Pc) ] / (1 + e0)

4. BÙ LÚN THEO NGUYÊN LÝ THỬ DẦN TẮT LÚN (Hbl)
Do nền lún xuống kéo theo thân nền đắp chìm dưới mực nước ngầm, chiều cao đất đắp thực tế phải tăng thêm lượng bù lún:
   H_tt = H_tk + H_kcad + H_bl
   H_bl = S_t(H_tt) = S_c + S_i
Hệ thống giải phương trình phi tuyến này bằng phương pháp lặp điểm bất động Euler với sai số hội tụ < 0.001 m.

5. LÝ THUYẾT CỐ KẾT THẤM THEO PHƯƠNG ĐỨNG (TERZAGHI)
Nhân tố thời gian cố kết đứng:
   Tv = (Cv * t) / (Hdr²)
Độ cố kết trung bình theo phương đứng:
   - Khi Tv ≤ 0.2827:  Uv = √(4 * Tv / π)
   - Khi Tv > 0.2827:  Uv = 1 - 10^( - (Tv + 0.085) / 0.933 )

6. LÝ THUYẾT CỐ KẾT THẤM HƯỚNG TÂM THEO HANSBO (PVD / SD)
Đường kính vùng ảnh hưởng de:
   - Bố trí tam giác:   de = 1.05 * d
   - Bố trí hình vuông: de = 1.13 * d
Nhân tố thời gian thoát nước hướng tâm:
   Th = (Ch * t) / (de²)
Hệ số cản tổng hợp F theo TCVN 9355:2013:
   F = Fn + Fs + Fr
   Fn = [ n² / (n² - 1) ] * ln(n) - (3n² - 1) / (4n²)   với n = de / dw
   Fs = (kh / ks - 1) * ln(ds / dw)                    (vùng xáo động)
   Fr = (2/3) * π * L² * (kh / qw)                      (sức cản thấm dọc bấc)
Độ cố kết hướng tâm theo Hansbo:
   Uh = 1 - exp( - 8 * Th / F )

7. CỐ KẾT KHÔNG GIAN 3 CHIỀU CARRILLO
Khi đồng thời thoát nước theo cả phương đứng và hướng tâm:
   U = 1 - (1 - Uv) * (1 - Uh)

8. GIA TẢI TRƯỚC (SURCHARGE) & HÚT CHÂN KHÔNG (VACUUM)
- Gia tải trước bằng đất đắp hs: Tạo ra áp lực tương đương Δp_s = γ_s * h_s, làm tăng ứng suất cố kết tạm thời giúp triệt tiêu nhanh lún dư trong thời gian gia tải ngắn.
- Hút chân không Pvac: Tạo chênh lệch áp lực nước lỗ rỗng âm đẳng hướng tương đương tải trọng gia tải Pvac ≈ 70 - 80 kPa mà không gây nguy cơ mất ổn định trượt trồi cung trượt mái dốc.

9. TĂNG TRƯỞNG SỨC KHÁNG CẮT KHÔNG THOÁT NƯỚC (Cu)
Sức kháng cắt của đất yếu gia tăng đồng biến với mức độ cố kết U:
   Cu(t) = C0 + m * (σ'v0 + Δσ'z - Pc) * U
Trong đó m là hệ số tăng cường độ xác định từ thí nghiệm nén 3 trục CU.
"""

    from user_guide import GUIDE_VI, GUIDE_EN
    guide_content = GUIDE_EN if language == 'en' else GUIDE_VI
    setup_text(tab_guide, guide_content)
    setup_text(tab_theory, theory_content)
