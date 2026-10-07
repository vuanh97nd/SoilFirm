"""Shared visual palette and Tk style defaults."""
import sys
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

# Font stack: Segoe UI trên Windows, SF Pro / Helvetica Neue trên macOS, DejaVu Sans trên Linux
def _ui_font():
    if sys.platform == 'win32':
        return 'Segoe UI'
    if sys.platform == 'darwin':
        return 'SF Pro Text'
    return 'DejaVu Sans'

UI_FONT = _ui_font()
UI_FONT_MONO = 'Consolas' if sys.platform == 'win32' else 'DejaVu Sans Mono'

_COLORS_LIGHT = {
    'background': '#F4F7FA', 'surface': '#FFFFFF', 'surface_soft': '#EDF3F6',
    'border': '#CFDAE2', 'text': '#172D46', 'muted': '#64748B',
    'nav': '#172D46', 'nav_active': '#0C6175', 'nav_hover': '#254B61',
    'header': '#17384D', 'accent': '#0284C7',
    'tab_selected': '#DCECF6', 'tab_idle': '#F1F5F9',
    'tab_hover': '#E5EEF5', 'control_text': '#163047',
}

_COLORS_DARK = {
    'background': '#0F172A', 'surface': '#1E293B', 'surface_soft': '#1A2E40',
    'border': '#334155', 'text': '#E2E8F0', 'muted': '#94A3B8',
    'nav': '#0F172A', 'nav_active': '#0E7490', 'nav_hover': '#164E63',
    'header': '#0C1A2E', 'accent': '#38BDF8',
    'tab_selected': '#1E3A5F', 'tab_idle': '#1E293B',
    'tab_hover': '#243447', 'control_text': '#CBD5E1',
}

COLORS = dict(_COLORS_LIGHT)  # khởi động ở chế độ sáng
_DARK_MODE_ACTIVE = False


def is_dark_mode() -> bool:
    return _DARK_MODE_ACTIVE


def configure_theme(root):
    _f = UI_FONT
    _fm = UI_FONT_MONO
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont',
                 'TkCaptionFont', 'TkSmallCaptionFont', 'TkIconFont', 'TkTooltipFont'):
        tkfont.nametofont(name, root=root).configure(family=_f)
    tkfont.nametofont('TkFixedFont', root=root).configure(family=_fm)
    root.option_add('*Font', (_f, 10))
    style = ttk.Style(root)
    if 'clam' in style.theme_names():
        style.theme_use('clam')
    style.configure('.', font=(_f, 10))
    style.configure('Workspace.TFrame', background=COLORS['background'])
    configure_tab_style(style)
    style.configure('TButton', font=(_f, 10),
                    foreground=COLORS['control_text'], background=COLORS['tab_idle'],
                    padding=(8, 5), bordercolor=COLORS['border'])
    style.map('TButton',
              background=[('disabled', '#E2E8F0'), ('pressed', COLORS['tab_selected']),
                          ('active', COLORS['tab_hover'])],
              foreground=[('disabled', '#94A3B8'), ('!disabled', COLORS['control_text'])])
    style.configure('Accent.TButton', font=(_f, 10, 'bold'),
                    foreground='white', background=COLORS['nav_active'], padding=(8, 5))
    style.map('Accent.TButton', background=[('disabled', '#94A3B8'), ('active', COLORS['accent']),
                                            ('pressed', COLORS['nav_hover'])],
              foreground=[('disabled', '#E2E8F0'), ('!disabled', 'white')])
    style.configure('Danger.TButton', font=(_f, 10),
                    foreground='#B91C1C', background='#FEE2E2', padding=(8, 5),
                    bordercolor='#FCA5A5')
    style.map('Danger.TButton',
              background=[('disabled', '#E2E8F0'), ('pressed', '#FECACA'), ('active', '#FECACA')],
              foreground=[('disabled', '#94A3B8'), ('!disabled', '#B91C1C')])

    style.configure('WorkflowMode.TCombobox',
                    font=(_f, 12, 'bold'), padding=(8, 9),
                    foreground='white', fieldbackground=COLORS['nav_active'],
                    background=COLORS['nav_active'], arrowcolor='white',
                    bordercolor=COLORS['nav_hover'], lightcolor=COLORS['nav_active'],
                    darkcolor=COLORS['nav_active'], selectbackground=COLORS['nav_active'],
                    selectforeground='white', arrowsize=18)
    style.map('WorkflowMode.TCombobox',
              foreground=[('readonly', 'white')],
              fieldbackground=[('readonly', COLORS['nav_active'])],
              background=[('active', COLORS['nav_hover']), ('readonly', COLORS['nav_active'])],
              arrowcolor=[('readonly', 'white')],
              selectbackground=[('readonly', COLORS['nav_active'])],
              selectforeground=[('readonly', 'white')])


def configure_treeview_style(style, name='Treeview', *, heading_bg=None, row_height=None, font_size=9):
    """Áp dụng style nhất quán cho tất cả Treeview: heading, màu hàng xen kẽ, highlight chọn.

    Gọi hàm này thay vì configure trực tiếp từng style riêng lẻ.
    Trả về dict {'even': str, 'odd': str, 'select_bg': str, 'select_fg': str}
    để caller dùng với tag_configure.
    """
    _f = UI_FONT
    _hbg = heading_bg or '#E4EDF3'
    _rh = row_height or max(22, font_size + 13)
    style.configure(f'{name}.Heading',
                    font=(_f, font_size, 'bold'),
                    padding=(4, 5),
                    background=_hbg,
                    foreground=COLORS['text'],
                    relief='flat')
    style.map(f'{name}.Heading',
              background=[('active', '#CCD9E3')],
              relief=[('active', 'flat')])
    style.configure(name,
                    font=(_f, font_size),
                    rowheight=_rh,
                    background='#FFFFFF',
                    foreground=COLORS['text'],
                    fieldbackground='#FFFFFF',
                    bordercolor=COLORS['border'],
                    relief='flat')
    style.map(name,
              background=[('selected', COLORS['tab_selected'])],
              foreground=[('selected', COLORS['text'])])
    return {
        'even': '#FFFFFF',
        'odd':  '#F3F8FB',
        'select_bg': COLORS['tab_selected'],
        'select_fg': COLORS['text'],
    }


def apply_theme_mode(root, dark: bool):
    """Chuyển toàn bộ UI giữa sáng và tối.

    Cập nhật COLORS in-place, tái cấu hình ttk style, rồi duyệt
    tất cả widget để đổi màu background/foreground theo bảng màu mới.
    """
    global _DARK_MODE_ACTIVE
    _DARK_MODE_ACTIVE = dark
    palette = _COLORS_DARK if dark else _COLORS_LIGHT
    COLORS.update(palette)
    configure_theme(root)
    # Map màu cũ → màu mới để cập nhật tk widgets tĩnh
    old = _COLORS_LIGHT if dark else _COLORS_DARK
    color_map = {old[k]: palette[k] for k in old if old[k] != palette[k]}
    # Màu cứng phổ biến ngoài palette
    if dark:
        color_map.update({
            '#FFFFFF': '#1E293B', '#F4F7FA': '#0F172A', '#EDF3F6': '#1A2E40',
            '#E7EDF2': '#1A2533', '#F8FAFC': '#1A2738', '#E4EDF3': '#1E3047',
            '#FEF3C7': '#2D2410', '#E0F2FE': '#0C2A3A',
        })
    else:
        color_map.update({
            '#1E293B': '#FFFFFF', '#0F172A': '#F4F7FA', '#1A2E40': '#EDF3F6',
            '#1A2533': '#E7EDF2', '#1A2738': '#F8FAFC', '#1E3047': '#E4EDF3',
            '#2D2410': '#FEF3C7', '#0C2A3A': '#E0F2FE',
        })

    def _recolor(widget):
        try:
            opts = widget.configure()
            if 'background' in opts:
                cur = widget.cget('background')
                if cur in color_map:
                    widget.configure(background=color_map[cur])
            if 'foreground' in opts:
                cur = widget.cget('foreground')
                if cur in color_map:
                    widget.configure(foreground=color_map[cur])
        except Exception:
            pass
        for child in widget.winfo_children():
            _recolor(child)

    _recolor(root)


def apply_row_stripes(tree, colors=None):
    """Cấu hình tag 'even'/'odd' và 'selected_row' cho một Treeview cụ thể."""
    c = colors or {'even': '#FFFFFF', 'odd': '#F3F8FB',
                   'select_bg': COLORS['tab_selected'], 'select_fg': COLORS['text']}
    tree.tag_configure('even', background=c['even'])
    tree.tag_configure('odd',  background=c['odd'])


def configure_tab_style(style):
    """One tab appearance for every native notebook in either data workflow."""
    _f = UI_FONT
    style.configure('TNotebook', background=COLORS['background'], borderwidth=0)
    style.configure('TNotebook.Tab', font=(_f, 10),
                    padding=(12, 7), foreground=COLORS['control_text'],
                    background=COLORS['tab_idle'], bordercolor=COLORS['border'])
    style.map('TNotebook.Tab',
              background=[('disabled', '#E2E8F0'), ('selected', COLORS['tab_selected']),
                          ('active', COLORS['tab_hover']), ('!selected', COLORS['tab_idle'])],
              foreground=[('disabled', '#94A3B8'), ('!disabled', COLORS['control_text'])],
              font=[('selected', (_f, 10, 'bold')),
                    ('!selected', (_f, 10))])


def style_action_button(widget, primary=False, danger=False):
    """Change presentation only; commands, bindings and disabled states stay intact."""
    if isinstance(widget, ttk.Button):
        if danger:
            widget.configure(style='Danger.TButton')
        else:
            widget.configure(style='Accent.TButton' if primary else 'TButton')
    elif isinstance(widget, tk.Button):
        if danger:
            widget.configure(font=(UI_FONT, 10),
                             bg='#FEE2E2', fg='#B91C1C',
                             activebackground='#FECACA', activeforeground='#B91C1C',
                             disabledforeground='#94A3B8', relief='flat', bd=1, padx=8, pady=5)
        else:
            widget.configure(font=(UI_FONT, 10, 'bold' if primary else 'normal'),
                             bg=COLORS['nav_active'] if primary else COLORS['tab_idle'],
                             fg='white' if primary else COLORS['control_text'],
                             activebackground=COLORS['accent'] if primary else COLORS['tab_hover'],
                             activeforeground='white' if primary else COLORS['control_text'],
                             disabledforeground='#94A3B8', relief='flat', bd=1, padx=8, pady=5)


class ProcessingBar(tk.Canvas):
    """One responsive, indeterminate animation for all processing tasks."""
    def __init__(self, parent, width=360):
        super().__init__(parent, width=width, height=8, bg='#E2E8F0',
                         highlightthickness=0)
        self._segment = self.create_rectangle(-64, 0, 0, 8,
                                              fill=COLORS['accent'], outline='')
        self._position = -64
        self._animation_job = None
        self.bind('<Destroy>', self._destroyed, add='+')

    def _destroyed(self, event):
        if event.widget is self: self.stop()

    def start(self, interval=25):
        if self._animation_job is None:
            self._animation_job = self.after(25, self._animate)

    def _animate(self):
        self._animation_job = None
        if not self.winfo_exists(): return
        width = max(1, self.winfo_width())
        self._position += 5
        if self._position > width: self._position = -64
        self.coords(self._segment, self._position, 0, self._position + 64, 8)
        self._animation_job = self.after(25, self._animate)

    def stop(self):
        if self._animation_job is not None:
            try: self.after_cancel(self._animation_job)
            except tk.TclError: pass
            self._animation_job = None
        self._position = -64
        try: self.coords(self._segment, -64, 0, 0, 8)
        except tk.TclError: pass


class ProcessingNotice(tk.Toplevel):
    """Task name above the common bar, real progress underneath, centered on app."""
    def __init__(self, app, task, detail=None, cancel=None, elapsed=None):
        super().__init__(app)
        self._popup_fit_scheduled = True
        self.title('Tiến trình xử lý')
        self.transient(app)
        self.resizable(False, False)
        self.configure(background=COLORS['surface'])
        self._app = app
        self._previous_grab = app.grab_current()
        stack = getattr(app, '_processing_windows', [])
        for previous in stack:
            if previous.winfo_exists(): previous.withdraw()
        stack.append(self)
        app._processing_windows = stack
        self._cancel_action = cancel
        self._elapsed = elapsed
        self._detail = detail if detail is not None else tk.StringVar(self, value='Đang xử lý…')
        self._processing_label = tk.Label(self, text=task.strip().rstrip('….'),
            bg=COLORS['surface'], fg=COLORS['text'], wraplength=440,
            font=(UI_FONT, 11, 'bold'))
        self._processing_label.pack(fill='x', padx=24, pady=(20,12))
        if elapsed is not None:
            self._elapsed_label = tk.Label(self, textvariable=elapsed,
                bg=COLORS['surface'], fg=COLORS['text'], wraplength=440,
                font=(UI_FONT, 12, 'bold'))
            self._elapsed_label.pack(fill='x', padx=24, pady=(0,10))
        self._processing_bar = ProcessingBar(self)
        self._processing_bar.pack(fill='x', padx=32, pady=(0,12))
        tk.Label(self, textvariable=self._detail, bg=COLORS['surface'],
            fg=COLORS['muted'], wraplength=440, height=3, anchor='n',
            font=(UI_FONT, 10)).pack(fill='x', padx=24, pady=(0,12))
        if cancel is not None:
            self._stop_button = ttk.Button(self, text='Dừng xử lý', command=self._request_stop)
            self._stop_button.pack(pady=(0,16))
        self.protocol('WM_DELETE_WINDOW', self._request_stop)
        self._center(app)
        self._processing_bar.start()

    def _center(self, app):
        width, height = 500, 240 if self._cancel_action is not None else 200
        if self._elapsed is not None: height += 36
        x = app.winfo_rootx() + (app.winfo_width() - width) // 2
        y = app.winfo_rooty() + (app.winfo_height() - height) // 2
        self.geometry(f'{width}x{height}+{max(0,x)}+{max(0,y)}')

    def _request_stop(self):
        if self._cancel_action is not None:
            self._stop_button.configure(state='disabled')
            self._detail.set('Đang dừng xử lý…')
            self._cancel_action()

    def close(self):
        self._processing_bar.stop()
        try:
            if self.grab_current() is self: self.grab_release()
            self.destroy()
            stack = [notice for notice in getattr(self._app, '_processing_windows', [])
                     if notice is not self and notice.winfo_exists()]
            self._app._processing_windows = stack
            if stack:
                stack[-1].deiconify()
                stack[-1].lift()
                if self._previous_grab is stack[-1]: stack[-1].grab_set()
        except tk.TclError: pass


def soil_parameter_keys(method, category=None):
    """Editable soil inputs; hidden laboratory/source values remain stored."""
    common = {'name', 'description', 'category', 'gamma', 'cohesion_c', 'friction_phi'}
    clay = {'state', 'drainage', 'co', 'cv_constant', 'cvp', 'cv'}
    groups = {'Cc/Cs/Pc': {'e0', 'cc', 'cs', 'pc'},
              'e–logP': {'ep', 'e'}, 'Mv–logP': {'e0', 'mvp', 'mv'}}
    clay.update(groups.get(method, groups['Cc/Cs/Pc']))
    sand = {'spt_n', 'sand_method'}
    if category in ('Đất dính', 'Cohesive soil'): return common | clay
    if category in ('Đất rời', 'Granular soil', 'Non-cohesive soil'): return common | sand
    return common | clay | sand
