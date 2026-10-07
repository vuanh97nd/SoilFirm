"""Shared visual palette and Tk style defaults."""
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

COLORS = {
    'background': '#F4F7FA', 'surface': '#FFFFFF', 'surface_soft': '#EDF3F6',
    'border': '#CFDAE2', 'text': '#172D46', 'muted': '#64748B',
    'nav': '#172D46', 'nav_active': '#0C6175', 'nav_hover': '#254B61',
    'header': '#17384D', 'accent': '#0284C7',
    'tab_selected': '#DCECF6', 'tab_idle': '#F1F5F9',
    'tab_hover': '#E5EEF5', 'control_text': '#163047',
}


def configure_theme(root):
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont', 'TkCaptionFont', 'TkSmallCaptionFont', 'TkIconFont', 'TkTooltipFont', 'TkFixedFont'):
        tkfont.nametofont(name, root=root).configure(family='Times New Roman')
    root.option_add('*Font', ('Times New Roman', 9))
    style = ttk.Style(root)
    if 'clam' in style.theme_names():
        style.theme_use('clam')
    style.configure('.', font=('Times New Roman', 9))
    style.configure('Workspace.TFrame', background=COLORS['background'])
    configure_tab_style(style)
    style.configure('TButton', font=('Times New Roman', 10),
                    foreground=COLORS['control_text'], background=COLORS['tab_idle'],
                    padding=(12, 7), bordercolor=COLORS['border'])
    style.map('TButton',
              background=[('disabled', '#E2E8F0'), ('pressed', COLORS['tab_selected']),
                          ('active', COLORS['tab_hover'])],
              foreground=[('disabled', '#94A3B8'), ('!disabled', COLORS['control_text'])])
    style.configure('Accent.TButton', font=('Times New Roman', 10, 'bold'),
                    foreground='white', background=COLORS['nav_active'], padding=(12, 7))
    style.map('Accent.TButton', background=[('disabled', '#94A3B8'), ('active', '#0284C7')],
              foreground=[('disabled', '#E2E8F0'), ('!disabled', 'white')])

    style.configure('WorkflowMode.TCombobox',
                    font=('Times New Roman', 12, 'bold'), padding=(8, 9),
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


def configure_tab_style(style):
    """One tab appearance for every native notebook in either data workflow."""
    style.configure('TNotebook', background=COLORS['background'], borderwidth=0)
    style.configure('TNotebook.Tab', font=('Times New Roman', 10),
                    padding=(12, 7), foreground=COLORS['control_text'],
                    background=COLORS['tab_idle'], bordercolor=COLORS['border'])
    style.map('TNotebook.Tab',
              background=[('disabled', '#E2E8F0'), ('selected', COLORS['tab_selected']),
                          ('active', COLORS['tab_hover']), ('!selected', COLORS['tab_idle'])],
              foreground=[('disabled', '#94A3B8'), ('!disabled', COLORS['control_text'])],
              font=[('selected', ('Times New Roman', 10, 'bold')),
                    ('!selected', ('Times New Roman', 10))])


def style_action_button(widget, primary=False):
    """Change presentation only; commands, bindings and disabled states stay intact."""
    if isinstance(widget, ttk.Button):
        widget.configure(style='Accent.TButton' if primary else 'TButton')
    elif isinstance(widget, tk.Button):
        widget.configure(font=('Times New Roman', 10, 'bold' if primary else 'normal'),
                         bg=COLORS['nav_active'] if primary else COLORS['tab_idle'],
                         fg='white' if primary else COLORS['control_text'],
                         activebackground=COLORS['accent'] if primary else COLORS['tab_hover'],
                         activeforeground='white' if primary else COLORS['control_text'],
                         disabledforeground='#94A3B8', relief='flat', bd=1, padx=12, pady=7)


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
            font=('Times New Roman', 11, 'bold'))
        self._processing_label.pack(fill='x', padx=24, pady=(20,12))
        if elapsed is not None:
            self._elapsed_label = tk.Label(self, textvariable=elapsed,
                bg=COLORS['surface'], fg=COLORS['text'], wraplength=440,
                font=('Times New Roman', 12, 'bold'))
            self._elapsed_label.pack(fill='x', padx=24, pady=(0,10))
        self._processing_bar = ProcessingBar(self)
        self._processing_bar.pack(fill='x', padx=32, pady=(0,12))
        tk.Label(self, textvariable=self._detail, bg=COLORS['surface'],
            fg=COLORS['muted'], wraplength=440, height=3, anchor='n',
            font=('Times New Roman', 10)).pack(fill='x', padx=24, pady=(0,12))
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
