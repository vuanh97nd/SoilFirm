"""
Module: app.py
File thực thi chính của hệ thống SOILFIRM PRO.
- Tự động vẽ lớp gia tải (Surcharge) và ký hiệu màng hút chân không (Vacuum) trên mặt cắt CAD.
- Tự động fit CAD và nâng đường kích thước B, a khi có gia tải (ký hiệu rút gọn GT).
- Cho phép sửa trực tiếp chiều dày H ngay trên danh sách địa tầng (nhấp đúp vào ô).
- Khắc phục triệt để lỗi tính lún khi cắm bấc/cọc lơ lửng.
- Bảng địa chất Bước 3 hiển thị chỉ tiêu đến hệ số m (CU).
- Tự động tính toán cố kết đến U = 99% theo đơn vị Tháng.
- Bảng Quản trị Admin 5 cột tích hợp quản lý thời hạn sử dụng.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, replace
import json
import math
import os
import re
import sys
import tempfile
import time
import ctypes
import hashlib
import queue
import subprocess
import threading
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import wraps
from datetime import datetime, timedelta, timezone
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk
import webbrowser
import requests

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

from PIL import ImageGrab
from credential_store import (load_credentials, save_credentials, clear_credentials,
                              load_session, save_session, clear_session)
from activity_presence import PresenceClient
from support_background import SupportBackground
from device_identity import device_id
from weather_panel import build_weather_clock

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table, TableStyle, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

from model import (
    Project, Soil, FillStage, settlement, trial_compensation, cdm_design_project,
    consolidation, assess_locations, load, save, get_tv_from_u,
    stage_schedule, treatment_history, axes, crest_half_widths, expansion_geometry,
    expansion_parameters, side_reach, main_zone_boundary, main_treated_depth, soils_at,
    effective_overburden, pressure,
    void_ratio, cv_cm2_day, degree_vertical,
    settlement_unpenetrated_zone, mechanical_depth, validate_mechanical,
    mechanical_display_elements, expansion_settlement_forecast, time_to_consolidation,
    time_to_treatment_consolidation, treatment_ranges, cdm_time_history
)
# Bí danh để gọi hàm tính lún đới không xử lý
get_unpenetrated_data = settlement_unpenetrated_zone

from utils import number, number_or_zero, clean_km_str, correct_fill_height, ScrollableFrame
from dialogs import BoreholeDialog, SoilDialog, show_stage_strength_dialog, show_help_dialog, show_unpenetrated_window
from graphics import (
    draw_cad_grid, draw_soil_hatching, draw_dim_h, draw_dim_v,
    draw_rotated_text, SOIL_PALETTE, render_chart_view
)
from ui_theme import (COLORS, configure_theme, style_action_button, UI_FONT, UI_FONT_MONO,
                      configure_treeview_style, apply_row_stripes)
from ui_i18n import english as _english_ui
from cdm import build_view as build_cdm_view
from treatment_optimizer import optimize_mechanical, optimize_drainage_time
from math_format import display_math, apply_math_label, format_number


def _version_key(value):
    """So sánh v2026.11 đúng lớn hơn v2026.11."""
    parts = re.findall(r'\d+', str(value))
    if not parts:
        raise ValueError('Bản phát hành GitHub không có mã phiên bản hợp lệ.')
    numbers = [int(part) for part in parts]
    return tuple((numbers + [0, 0, 0])[:max(3, len(numbers))])


def _release_installer_url(release):
    for asset in release.get('assets', []):
        name = str(asset.get('name', '')).lower()
        if 'soilfirm_professional_setup' in name and name.endswith('.exe'):
            return asset.get('browser_download_url')
    return release.get('html_url', 'https://github.com/vuanh97nd/SoilFirm/releases/latest')


def _release_installer_asset(release):
    """Chỉ nhận bộ cài EXE trong Assets của release chính thức."""
    for asset in release.get('assets', []):
        name = str(asset.get('name', ''))
        url = str(asset.get('browser_download_url', ''))
        parsed = urlparse(url)
        if (name.lower().startswith('soilfirm_professional_setup')
                and name.lower().endswith('.exe')
                and parsed.scheme == 'https' and parsed.hostname == 'github.com'
                and parsed.path.startswith('/vuanh97nd/SoilFirm/releases/download/')):
            return asset
    return None


def _user_activity(user):
    """Chỉ hiện 'đang hoạt động' khi máy chủ trả trạng thái xác nhận."""
    raw = user.get('last_seen_at') or user.get('last_activity_at') or user.get('last_login_at')
    last_seen = '—'
    if raw:
        try:
            stamp = (datetime.fromtimestamp(float(raw) / (1000 if float(raw) > 1e11 else 1),
                                           tz=timezone.utc)
                     if isinstance(raw, (int, float)) else
                     datetime.fromisoformat(str(raw).replace('Z', '+00:00')))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            last_seen = stamp.astimezone().strftime('%d/%m/%Y %H:%M')
        except (ValueError, TypeError, OverflowError, OSError):
            last_seen = str(raw)
    online = user.get('is_online', user.get('online'))
    if online is True:
        status = 'Online'
    elif online is False:
        status = 'Offline'
    else:
        status = 'Chưa có dữ liệu'
    seconds = user.get('total_usage_seconds', user.get('usage_seconds'))
    try:
        if seconds is None and user.get('total_usage_minutes') is not None:
            seconds = float(user['total_usage_minutes']) * 60
        seconds = max(0, int(float(seconds)))
        usage = f'{seconds // 3600} giờ {(seconds % 3600) // 60} phút'
    except (TypeError, ValueError, OverflowError):
        usage = 'Chưa có dữ liệu'
    return status, last_seen, usage


def calculation_indicator(action):
    """Dùng chung trạng thái xử lý và khung kết quả cho các lệnh tính."""
    @wraps(action)
    def run(self, *args, **kwargs):
        titles = {
            'calculate_expansion_forecast': 'Dự báo lún nền mở rộng',
            'calculate_before': 'Lún theo thời gian',
            'calculate_settlement': 'Lún khi chưa xử lý',
            'calculate_hbl': 'Bù lún',
            'calculate_consolidation': 'Lún sau xử lý',
            'optimize_mechanical_solution': 'Tính tối ưu cơ học',
            '_run_mechanical_optimization': 'Tính tối ưu cơ học',
            'draw_natural_result_chart': 'Biểu đồ lún tự nhiên',
            'show_stage_strength': 'Sức kháng từng giai đoạn',
            'manual_show_unpenetrated': 'Lún dưới đáy bấc',
            'optimize_drainage_solution': 'Tối ưu thoát nước',
            'draw_treatment_chart': 'Biểu đồ lún sau xử lý',
        }
        return self.run_processing(titles.get(action.__name__, 'Xử lý tính toán'),
                                   lambda: action(self, *args, **kwargs))
    return run


from ui_theme import ProcessingBar, ProcessingNotice


def _new_processing_notice(self, label):
    return ProcessingNotice(self, label, detail=self.status_text)


def _processing_call(self, label, action):
    if getattr(self, '_calculation_notice', None) is not None:
        return action()
    previous_result = getattr(self, '_result_serial', 0)
    self.status_text.set(f'Đang xử lý: {label}…')
    try:
        notice = _new_processing_notice(self, label)
        self._calculation_notice = notice
        try:
            notice.update()
            notice.grab_set()
            with ThreadPoolExecutor(max_workers=1) as executor:
                self._calculation_executor = executor
                result = action()
            if getattr(self, '_result_serial', 0) == previous_result:
                current = self.status_text.get()
                if current.startswith('Đang xử lý:'):
                    current = 'Đã xử lý xong. Xem bảng kết quả trong mục đang mở.'
                self.report_result(label, current)
            return result
        except Exception as exc:
            self.report_result(label, str(exc), error=True)
            raise
        finally:
            self._calculation_executor = None
            notice.close()
            self._calculation_notice = None
            if getattr(self, '_result_serial', 0) != previous_result:
                title, detail, error = self._last_result_notice
                if not error and 'Biểu đồ' not in label:
                    if self.ui_language.get() == 'English':
                        title, detail = _english_ui(title), _english_ui(detail)
                    messagebox.showinfo(title, detail, parent=self)
    except Exception:
        raise


def _compact_heading(label, font, limit=105):
    """Chia tiêu đề dài thành tối đa hai dòng, giữ nguyên nhãn dữ liệu gốc."""
    words = str(label).split()
    if len(words) < 2 or font.measure(label) <= limit:
        return str(label)
    options = (' '.join(words[:i]) + '\n' + ' '.join(words[i:])
               for i in range(1, len(words)))
    return min(options, key=lambda s: (max(font.measure(line) for line in s.split('\n')),
                                       abs(len(s.split('\n')[0])-len(s.split('\n')[1]))))


def _heading_width(label, font):
    return max(font.measure(line) for line in label.split('\n'))


# ==============================================================================
# 0. HỘP THOẠI POPUP & CUỘN CHỐNG CHÈN NỘI DUNG
# ==============================================================================
def _popup_workarea(window):
    """Lấy kích thước màn hình làm việc an toàn, trừ thanh Taskbar."""
    if sys.platform == 'win32':
        try:
            from ctypes import wintypes

            class MonitorInfo(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.DWORD),
                            ('rcMonitor', wintypes.RECT),
                            ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]

            user32 = ctypes.windll.user32
            monitor_from_window = user32.MonitorFromWindow
            monitor_from_window.argtypes = [wintypes.HWND, wintypes.DWORD]
            monitor_from_window.restype = wintypes.HANDLE
            get_monitor_info = user32.GetMonitorInfoW
            get_monitor_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
            get_monitor_info.restype = wintypes.BOOL
            owner = window.master or window
            monitor = monitor_from_window(owner.winfo_id(), 2)
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(info)
            if get_monitor_info(monitor, ctypes.byref(info)):
                r = info.rcWork
                return r.left, r.top, r.right - r.left, r.bottom - r.top
        except (AttributeError, OSError, tk.TclError):
            pass
    return 0, 0, window.winfo_screenwidth(), window.winfo_screenheight()


def _fit_popup(window):
    """Căn chỉnh popup vừa vặn với kích thước màn hình."""
    if not window.winfo_exists():
        return
    window.update_idletasks()
    if not window.winfo_exists():
        return
    left, top, screen_w, screen_h = _popup_workarea(window)
    max_w, max_h = max(1, screen_w - 40), max(1, screen_h - 80)
    wanted_w, wanted_h = window.winfo_reqwidth(), window.winfo_reqheight()
    pending = list(window.winfo_children())
    while pending:
        child = pending.pop()
        if isinstance(child, tk.Toplevel):
            continue
        pending.extend(child.winfo_children())
        body = getattr(child, 'scrollable_frame', None)
        if body is not None:
            wanted_w = max(wanted_w, body.winfo_reqwidth() + 40)
            wanted_h = max(wanted_h, body.winfo_reqheight() + 40
                           + max(0, window.winfo_reqheight() - child.winfo_reqheight()))
    width = min(max_w, max(wanted_w, window.winfo_width()))
    height = min(max_h, max(wanted_h, window.winfo_height()))
    window.resizable(True, True)
    window.maxsize(max_w, max_h)
    window.minsize(min(360, width), min(240, height))
    x = left + (screen_w - width) // 2
    y = top + max(30, (screen_h - height) // 2)
    window.geometry(f'{width}x{height}+{x}+{y}')


def _popup_mapped(event):
    window = event.widget
    if isinstance(window, tk.Toplevel) and not getattr(window, '_popup_fit_scheduled', False):
        window._popup_fit_scheduled = True
        window.after_idle(lambda: _fit_popup(window))


def _scroll_under_pointer(event):
    """Scroll the local content region, including labels, inputs and blank space."""
    if not isinstance(event.widget, tk.Misc):
        return None
    try:
        origin = event.widget.winfo_containing(event.x_root, event.y_root) or event.widget
        horizontal = bool(event.state & 1)
        delta = getattr(event, 'delta', 0)
        units = (-max(1, abs(int(delta)) // 120) if delta > 0 else
                 max(1, abs(int(delta)) // 120)) if delta else (
                 -1 if getattr(event, 'num', None) == 4 else 1)

        def scroll_target(widget):
            canvas = getattr(widget, 'canvas', None)
            target = canvas if isinstance(canvas, tk.Canvas) else widget
            if not isinstance(target, (ttk.Treeview, tk.Text, tk.Listbox, tk.Canvas)):
                return None
            if isinstance(target, tk.Canvas) and not target.cget('scrollregion'):
                return None
            view = target.xview if horizontal else target.yview
            return target if tuple(view()) != (0.0, 1.0) else None

        # The enclosing scroll frame owns input fields and blank content space.
        ancestors = []
        widget = origin
        while widget is not None and not isinstance(widget, (tk.Tk, tk.Toplevel)):
            ancestors.append(widget)
            target = scroll_target(widget)
            if target is not None:
                (target.xview_scroll if horizontal else target.yview_scroll)(units, 'units')
                return 'break'
            widget = getattr(widget, 'master', None)

        # Empty margins outside a scroll canvas still belong to its visible panel.
        for container in ancestors:
            if not isinstance(container, (ttk.Frame, tk.Frame, ttk.LabelFrame, tk.LabelFrame)):
                continue
            pending = [(child, 0) for child in container.winfo_children()]
            while pending:
                child, depth = pending.pop(0)
                if isinstance(child, tk.Toplevel) or not child.winfo_viewable():
                    continue
                target = scroll_target(child)
                if target is not None:
                    (target.xview_scroll if horizontal else target.yview_scroll)(units, 'units')
                    return 'break'
                if depth < 3:
                    pending.extend((item, depth+1) for item in child.winfo_children())
    except tk.TclError:
        return None


def _install_scroll_route(event):
    widget = event.widget
    # Tcl-owned combobox popdowns may arrive as path strings rather than widgets.
    if not isinstance(widget, tk.Misc):
        return
    if getattr(widget, '_sf_wheel_installed', False):
        return
    widget._sf_wheel_installed = True
    tags = widget.bindtags()
    widget.bindtags((tags[0], 'SoilFirmWheel', *tags[1:]))


def _display_account_name(value):
    """Repair reversible UTF-8 mojibake for display, without changing account IDs."""
    text=str(value or '')
    def repair(match):
        word=match.group(0)
        def score(item):return sum(item.count(mark) for mark in ('Ã','Â','á»','áº','â€'))
        for _ in range(2):
            candidates=[]
            for encoding in ('cp1252','latin1'):
                try:candidate=word.encode(encoding).decode('utf-8')
                except UnicodeError:continue
                if score(candidate)<score(word):candidates.append(candidate)
            if not candidates:break
            word=min(candidates,key=score)
        return word
    import unicodedata
    # Repair the complete name first: Latin-1 mojibake may contain U+0085,
    # which Python treats as whitespace and would split a Vietnamese glyph.
    text=re.sub(r'[\s\S]+',repair,text,count=1)
    return unicodedata.normalize('NFC',re.sub(r'\S+',repair,text))



class _PopupScrollFrame(ttk.Frame):
    """Khung cuộn tự co giãn kích thước cho popup."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, width=1, height=1, highlightthickness=0, bg=COLORS['background'])
        self.scrollable_frame = ttk.Frame(self.canvas)
        self._item = self.canvas.create_window(0, 0, window=self.scrollable_frame, anchor='nw')
        self._vertical = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self._horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self._vertical.set, xscrollcommand=self._horizontal.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self._vertical.grid(row=0, column=1, sticky='ns')
        self._horizontal.grid(row=1, column=0, sticky='ew')
        self.canvas.bind('<Configure>', self._sync_content, add='+')
        self.scrollable_frame.bind('<Configure>', self._sync_content, add='+')
        top = self.winfo_toplevel()
        if not getattr(top, '_popup_scroll_bound', False):
            top._popup_scroll_bound = True
            for sequence in ('<MouseWheel>', '<Shift-MouseWheel>', '<Button-4>', '<Button-5>'):
                top.bind(sequence, self._route_wheel, add='+')

    def _sync_content(self, _event=None):
        width = max(self.canvas.winfo_width(), self.scrollable_frame.winfo_reqwidth())
        height = max(self.canvas.winfo_height(), self.scrollable_frame.winfo_reqheight())
        self.canvas.itemconfigure(self._item, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))

    @staticmethod
    def _route_wheel(event):
        widget = event.widget
        if isinstance(widget, (ttk.Treeview, tk.Text, tk.Listbox)):
            return
        while widget is not None:
            if isinstance(widget, _PopupScrollFrame):
                delta = getattr(event, 'delta', 0)
                units = (-1 if getattr(event, 'num', None) == 4 else 1)
                if delta:
                    units = -max(1, abs(int(delta)) // 120) if delta > 0 else max(1, abs(int(delta)) // 120)
                view = widget.canvas.xview_scroll if event.state & 1 else widget.canvas.yview_scroll
                view(units, 'units')
                return 'break'
            widget = getattr(widget, 'master', None)

import dialogs as _popup_dialogs
_popup_dialogs.ScrollableFrame = _PopupScrollFrame
import model as _soil_model


@dataclass
class Soil(_soil_model.Soil):
    description: str = ""


_soil_model.Soil = Soil
_BaseSoilDialog = SoilDialog


class SoilDialog(_BaseSoilDialog):
    def __init__(self, parent, soil, on_save, method, treatment):
        def save_with_description(updated_soil):
            updated_soil.description = self.vars['description'].get().strip()
            on_save(updated_soil)

        super().__init__(parent, soil, save_with_description, method, treatment)
        body = self.widgets['name'][1].master
        for widget in body.winfo_children():
            info = widget.grid_info()
            if info and int(info['row']) >= 1:
                widget.grid_configure(row=int(info['row']) + 1)
        self.vars['description'] = tk.StringVar(self, value=getattr(soil, 'description', ''))
        label = ttk.Label(body, text='Mô tả')
        label.grid(row=1, column=0, sticky='w', pady=5)
        entry = ttk.Entry(body, textvariable=self.vars['description'], width=42)
        entry.grid(row=1, column=1, sticky='ew', padx=(10, 0), pady=5)
        self.widgets['description'] = (label, entry)
        label.lift(self.widgets['name'][1])
        entry.lift(label)


# ==============================================================================
# 1. HÀM VẼ CAD NỀN ĐẮP TÍCH HỢP GIA TẢI (SURCHARGE) & HÚT CHÂN KHÔNG (VACUUM)
# ==============================================================================
def cad_pressure_value(project: Project, load_project: Project, plot_mode: str,
                       z: float, x: float, remaining: float = 1.0,
                       vacuum_active: float = 0.0, treated: bool = False) -> float:
    """Giá trị ứng suất/áp lực tại đúng phương án và thời điểm đang xem."""
    remaining = min(1.0, max(0.0, remaining))
    vacuum_here = (vacuum_active if abs(x) < project.crest_half_width+project.slope_width
                   and (project.drain_length <= 0 or z <= project.drain_length) else 0.0)
    if plot_mode == 'Ứng suất bản thân':
        return max(0.0, effective_overburden(project,z,treated=treated,x=x))
    applied = max(0.0, pressure(load_project,z,x))
    if plot_mode == 'Ứng suất tăng thêm':
        return applied+vacuum_here
    hydro = project.gamma_water*max(0.0,z-project.water_depth)
    if plot_mode == 'Áp lực nước tĩnh':
        return hydro
    excess = applied*remaining
    if plot_mode == 'Áp lực nước lỗ rỗng':
        return max(0.0,hydro+excess-vacuum_here)
    return excess


def draw_enhanced_cad_diagram(c: tk.Canvas, project: Project, vars_dict: dict, treatment_vars: dict,
                              treatment_flags: dict, has_cw_flag: bool,
                              surcharge_enabled: bool = False, vacuum_enabled: bool = False,
                              pan_x: float = 0.0, pan_y: float = 0.0, zoom: float = 1.0, current_step: int = 4,
                              plot_mode: str = 'Độ lún', settlement_elements=None, pore_remaining: float = 1.0,
                              settlement_totals=None, stage_label: str = '', analysis_project=None,
                              settlement_label: str = 'S', vacuum_active: float = 0.0,
                              cdm_overlay=None):
    """
    Vẽ mặt cắt kỹ thuật CAD nền đắp - địa chất.
    Cập nhật mới: Tự động Fit chiều cao gia tải, dời đường kính thước B, a lên trên.
    """
    c.delete('all')

    w = c.winfo_width()
    h = c.winfo_height()
    if w < 100 or h < 100:
        return

    draw_cad_grid(c, w, h)

    htk = number_or_zero(vars_dict.get('h_design', tk.StringVar()).get())
    m_slope = number_or_zero(vars_dict.get('slope_M', tk.StringVar(value='1.5')).get())
    b_total = number_or_zero(vars_dict.get('crest_B', tk.StringVar(value='12.0')).get())
    b = b_total / 2.0
    left_b = right_b = b

    hc = number_or_zero(vars_dict.get('counterweight_height', tk.StringVar()).get()) if has_cw_flag else 0.0
    wc = number_or_zero(vars_dict.get('counterweight_width', tk.StringVar()).get()) if has_cw_flag else 0.0
    mc_val = number_or_zero(vars_dict.get('counterweight_m', tk.StringVar(value='1.0')).get())
    mc = hc * mc_val if has_cw_flag else 0.0

    z_tn = number_or_zero(vars_dict.get('ground_elevation', tk.StringVar(value='0.0')).get())
    water_elevation = number_or_zero(vars_dict.get('water_elevation', tk.StringVar()).get())

    h_emb = htk if htk > 0 else 3.0
    a = m_slope * h_emb
    reach = max(b+a, side_reach(project, 'Trái'), side_reach(project, 'Phải'))

    total_depth = sum(max(0, s.thickness) for s in project.soils)
    if total_depth <= 0:
        total_depth = 8.0
    shallow_depths = {}
    if current_step in (4, 5) and getattr(project, 'treatment_group', 'drainage') == 'mechanical':
        for key in ('replacement_depth', 'bamboo_depth', 'cajuput_depth'):
            shallow_depths[key] = number_or_zero(treatment_vars.get(key, tk.StringVar(value='0')).get())
        shallow_depths = {key: depth for key, depth in shallow_depths.items() if depth > 0}
    shallow_bottom = min(total_depth, max(shallow_depths.values(), default=0.0))

    hs_val = number_or_zero(treatment_vars.get('surcharge_height', tk.StringVar()).get())
    has_sc = (current_step in (4, 5) and surcharge_enabled and hs_val > 0)
    extra_h_top = hs_val if has_sc else 0.0

    margin_left = min(105.0, max(28.0, w * 0.12))
    margin_right = margin_left
    margin_top = min(80.0 if has_sc else 65.0, max(28.0, h * 0.10))
    margin_bottom = min(45.0, max(22.0, h * 0.08))

    avail_w = max(100.0, w - (margin_left + margin_right))
    avail_h = max(100.0, h - (margin_top + margin_bottom))

    fit_scale_x = avail_w / (2.0 * max(reach, 1.0))
    depth_repr_ratio = 1.25
    headroom = 45.0 if current_step in (1, 2) else 32.0
    fit_scale_y = max(25.0, avail_h - headroom) / (
        h_emb + extra_h_top + total_depth * depth_repr_ratio)

    if current_step == 3:
        auto_base_scale = min(fit_scale_x * 0.70, fit_scale_y * 0.82)
    else:
        auto_base_scale = min(fit_scale_x, fit_scale_y)
        
    scale = max(1.0, auto_base_scale * zoom)

    cx = (w / 2) + pan_x + (5.0 if current_step != 3 else 0.0)
    
    if current_step in (1, 2):
        top_y = margin_top + 45.0 + pan_y
        ground_y = top_y + h_emb * scale
    else:
        top_peak_y = margin_top + 32.0 + pan_y
        ground_y = top_peak_y + (h_emb + extra_h_top) * scale
        top_y = ground_y - h_emb * scale
        
    bottom_y = ground_y + (total_depth * scale * depth_repr_ratio)

    def display_treatment_ranges():
        if project.expansion_width <= 0 or project.expansion_side == 'Không':
            return [(cx+lo*scale,cx+hi*scale) for lo,hi in treatment_ranges(project)]
        ext_h, ext_slope, _ = expansion_parameters(project)
        display_h = ext_h*h_emb/max(project.height,0.001)
        display_toe = b+m_slope*max(0.0,h_emb-display_h)+project.expansion_width+ext_slope*display_h
        result = []
        for side,sign in (('Trái',-1),('Phải',1)):
            geometry = expansion_geometry(project,side)
            if geometry is None:
                continue
            requested = project.expansion_treatment_width
            inner = b if requested is None else max(b,display_toe-requested)
            result.append(tuple(sorted((cx+sign*inner*scale,cx+sign*display_toe*scale))))
        return result


    # Geological layers extend beyond the viewport at every zoom/pan level.
    # Draw only the visible width to keep hatching responsive.
    x_soil_left = -12.0
    x_soil_right = w + 12.0
    y_curr = ground_y
    cum_depth = 0.0

    # 1. Vẽ các lớp địa tầng đất
    if current_step >= 2:
        for i, s in enumerate(project.soils):
            layer_h = (bottom_y - ground_y) * (s.thickness / total_depth)
            next_y = y_curr + layer_h
            cum_depth += s.thickness
            palette = SOIL_PALETTE[i % len(SOIL_PALETTE)]

            c.create_rectangle(x_soil_left, y_curr, x_soil_right, next_y,
                               fill=palette['fill'], outline=palette['border'], width=1.2)
            draw_soil_hatching(c, x_soil_left, y_curr, x_soil_right, next_y, s.category, palette['hatch'])

            if layer_h >= 14:
                s_name = s.name.strip() if s.name.strip() else f"Lớp {i+1}"
                c.create_text(x_soil_left + 14, (y_curr + next_y) / 2 - 2, anchor='w',
                              text=s_name, fill='#1E293B', font=(UI_FONT, 9, 'bold'))

            c.create_text(x_soil_left + 14, next_y - 6, text=f"▽ {z_tn - cum_depth:+.2f} m",
                          fill='#64748B', font=(UI_FONT, 7), anchor='w')
            y_curr = next_y

    # Ký hiệu nền chính đã xử lý đặt chìm dưới phương án nền mở rộng.
    extension_cdm = (current_step == 6 and cdm_overlay is not None and
                     cdm_overlay[0].get('scope') == 'Nền mở rộng')
    old_boundary = (main_zone_boundary(project)
                    if current_step >= 1 and project.expansion_width <= 0 and not extension_cdm else None)
    if old_boundary is not None and total_depth > 0:
        old_toe = b+a if project.main_treatment in ('CDM', 'Cơ học') else b
        old_left = cx-old_toe*scale
        old_right = cx+old_toe*scale
        soil_scale = (bottom_y-ground_y)/total_depth
        if project.main_treatment in ('PVD', 'SD'):
            old_depth = min(total_depth, max(0.0, project.drain_length or total_depth))
            tip_y = ground_y+old_depth*soil_scale
            for i in range(9):
                drain_x = old_left+(i+0.5)*(old_right-old_left)/9
                if project.main_treatment == 'SD':
                    c.create_rectangle(drain_x-2, ground_y+3, drain_x+2, tip_y,
                                       outline='#94A3B8', width=0.8, tags='old_main_treatment')
                else:
                    c.create_line(drain_x, ground_y+3, drain_x, tip_y,
                                  fill='#94A3B8', width=1, tags='old_main_treatment')
        else:
            excavation = min(total_depth, max(0.0, project.main_replacement_depth))
            pile_depth = max(0.0, project.main_bamboo_depth, project.main_cajuput_depth)
            pile_end = min(total_depth, excavation+pile_depth)
            cdm_end = min(total_depth, max(0.0, project.main_cdm_depth)) if project.main_treatment == 'CDM' else 0.0
            def old_edge(depth):
                return max(0.0, old_toe-0.5*depth)*scale
            if cdm_end > 0:
                c.create_rectangle(old_left, ground_y+2, old_right,
                                   ground_y+cdm_end*soil_scale,
                                   fill='#E2E8F0', stipple='gray75', outline='#94A3B8',
                                   dash=(3, 4), width=1, tags='old_main_treatment')
            if project.main_treatment == 'Cơ học' and excavation > 0:
                base_y = ground_y+excavation*soil_scale
                base_edge = old_edge(excavation)
                c.create_polygon(old_left, ground_y+2, old_right, ground_y+2,
                                 cx+base_edge, base_y, cx-base_edge, base_y,
                                 fill='#E2E8F0', stipple='gray50', outline='#94A3B8',
                                 width=1, tags='old_main_treatment')
                c.create_text(cx, (ground_y+base_y)/2, text='ĐÀO THAY ĐẤT',
                              fill='#64748B', font=(UI_FONT, 7),
                              tags='old_main_treatment')
            if project.main_treatment == 'Cơ học' and pile_end > excavation:
                start_edge = old_edge(excavation or pile_depth)
                end_edge = start_edge
                start_y = ground_y+excavation*soil_scale
                end_y = ground_y+pile_end*soil_scale
                c.create_polygon(cx-start_edge, start_y, cx+start_edge, start_y,
                                 cx+end_edge, end_y, cx-end_edge, end_y,
                                 fill='', outline='#94A3B8', dash=(3, 4),
                                 tags='old_main_treatment')
                for i in range(9):
                    fraction = -0.9+1.8*i/8
                    mark_x = cx+fraction*end_edge
                    c.create_line(mark_x, start_y+2, mark_x, end_y-2,
                                  fill='#94A3B8', width=1, tags='old_main_treatment')
                pile_label = 'CỌC TRE' if project.main_bamboo_depth else 'CỪ TRÀM'
                c.create_text(cx, end_y+9, text=pile_label, fill='#64748B',
                              font=(UI_FONT, 7), tags='old_main_treatment')
        c.create_text(cx, ground_y+12, text=f'PHƯƠNG ÁN ĐÃ XỬ LÝ CỦA NỀN CHÍNH: {project.main_treatment}',
                      fill='#64748B', font=(UI_FONT, 7),
                      tags='old_main_treatment')

    # Đường mặt đất tự nhiên Ztn
    c.create_line(x_soil_left - 15, ground_y, x_soil_right + 15, ground_y, fill='#0F172A', width=2.5)

    ztn_box_x = x_soil_left + 15
    c.create_polygon(ztn_box_x, ground_y, ztn_box_x - 5, ground_y - 7, ztn_box_x + 5, ground_y - 7,
                     fill='#1E293B', outline='#0F172A')
    c.create_text(ztn_box_x + 8, ground_y + 17, text=f"Ztn = {z_tn:+.2f} m",
                  fill='#0F172A', font=(UI_FONT, 9, 'bold'), anchor='w')

    # Trục tim đường (tự nâng khi có gia tải)
    y_tim_top = (top_y - extra_h_top * scale - 45) if has_sc else (top_y - 45)
    c.create_line(cx, y_tim_top, cx, bottom_y + 10, fill='#DC2626', dash=(12, 4, 3, 4), width=1.6)
    c.create_text(cx, y_tim_top - 5, text="TIM ĐƯỜNG", fill='#DC2626', font=(UI_FONT, 9, 'bold'), anchor='s')

    # 2. Vẽ hình học thân nền đắp chính
    toe_x = right_b * scale + a * scale
    if current_step >= 1:
        has_counterweight = (has_cw_flag and hc > 0 and wc > 0 and h_emb > hc)
        theta_deg = math.degrees(math.atan(1.0 / max(m_slope, 0.01)))

        if has_counterweight:
            by = ground_y - hc * scale
            shoulder_x = right_b * scale + m_slope * (h_emb - hc) * scale
            left_shoulder_x = left_b * scale + m_slope * (h_emb - hc) * scale
            outer_x = shoulder_x + wc * scale
            toe_x = outer_x + mc * scale

            right_pts = [(cx + right_b * scale, top_y), (cx + shoulder_x, by), (cx + outer_x, by), (cx + toe_x, ground_y)]
            left_pts = [(cx - left_shoulder_x - wc * scale - mc * scale, ground_y),
                        (cx - left_shoulder_x - wc * scale, by),
                        (cx - left_shoulder_x, by), (cx - left_b * scale, top_y)]
            c.create_polygon(left_pts + right_pts, fill='#FDF6E2', outline='#78350F', width=2)

            main_toe_px = (right_b + a) * scale
            c.create_line(cx + shoulder_x, by, cx + main_toe_px, ground_y, fill='#B45309', dash=(4, 3), width=1.5)
            c.create_line(cx - left_shoulder_x, by, cx - (left_b+a)*scale, ground_y,
                          fill='#B45309', dash=(4, 3), width=1.5)

            draw_dim_h(c, cx + shoulder_x, cx + outer_x, by, f"L={wc:.2f}m", offset=14)
            draw_dim_h(c, cx + outer_x, cx + toe_x, by, f"A={mc:.2f}m", offset=14)

            draw_rotated_text(c, cx + (b * scale + shoulder_x) / 2, (top_y + by) / 2 - 10,
                              f"1:{m_slope:.2f}", -theta_deg, '#78350F', 10)
            draw_rotated_text(c, cx - (b * scale + shoulder_x) / 2, (top_y + by) / 2 - 10,
                              f"1:{m_slope:.2f}", theta_deg, '#78350F', 10)
        else:
            toe_x = right_b * scale + a * scale
            right_pts = [(cx + right_b * scale, top_y), (cx + toe_x, ground_y)]
            left_pts = [(cx-(left_b+a)*scale, ground_y), (cx-left_b*scale, top_y)]
            c.create_polygon(left_pts + right_pts, fill='#FDF6E2', outline='#78350F', width=2)

            draw_rotated_text(c, cx + b * scale + (toe_x - b * scale) / 2 + 5,
                              (top_y + ground_y) / 2 - 11,
                              f"1:{m_slope:.2f}", -theta_deg, '#78350F', 11)

            draw_rotated_text(c, cx - b * scale - (toe_x - b * scale) / 2 - 5,
                              (top_y + ground_y) / 2 - 11,
                              f"1:{m_slope:.2f}", theta_deg, '#78350F', 11)

        if project.expansion_width > 0 and project.expansion_side != 'Không':
            vertical_ratio = h_emb/max(project.height, 0.001)
            ext_h, ext_slope, _ = expansion_parameters(project)
            ext_htk = project.expansion_h_design or project.h_design
            ext_display_h = ext_h*vertical_ratio
            y = ground_y-ext_display_h*scale
            for side, sign in (('Trái', -1), ('Phải', 1)):
                geometry = expansion_geometry(project, side)
                if geometry:
                    inner_display = project.crest_half_width + project.slope_m * max(0.0, h_emb-ext_display_h)
                    outer_display = inner_display + project.expansion_width
                    toe_display = outer_display + ext_slope*ext_display_h
                    x_inner = cx+sign*inner_display*scale
                    x_outer = cx+sign*outer_display*scale
                    x_toe = cx+sign*toe_display*scale
                    x_main_toe = cx+sign*(project.crest_half_width+project.slope_m*h_emb)*scale
                    main_join_y = ground_y-min(ext_display_h, h_emb)*scale
                    c.create_polygon(x_inner, y, x_outer, y, x_toe, ground_y,
                                     x_main_toe, ground_y, x_inner, main_join_y,
                                     fill='#BFE8ED', outline='')
                    c.create_line(x_inner, main_join_y, x_main_toe, ground_y,
                                  fill='#147D8A', dash=(4, 3), width=1.5)
                    if y < main_join_y:
                        c.create_line(x_inner, y, x_inner, main_join_y,
                                      fill='#147D8A', dash=(4, 3), width=1.5)
                    c.create_line(x_inner, y, x_outer, y, x_toe, ground_y,
                                  fill='#147D8A', dash=(6, 4), width=2)
                    c.create_text((x_inner+x_outer)/2, y-10,
                                  text=f"b={project.expansion_width:.2f}m",
                                  fill='#075A65', font=(UI_FONT, 9, 'bold'))
                    c.create_text((x_outer+x_toe)/2+sign*10, (y+ground_y)/2,
                                  text=f"1:{ext_slope:.2f}", fill='#075A65',
                                  font=(UI_FONT, 9, 'bold'))
                    x_dim = x_outer+sign*9
                    y_htk = ground_y-ext_htk*vertical_ratio*scale
                    c.create_line(x_dim, y_htk, x_dim, ground_y,
                                  fill='#147D8A', dash=(3, 3), width=1)
                    c.create_text(x_dim+sign*4, (y_htk+ground_y)/2,
                                  text=f"htk={ext_htk:.2f}m",
                                  anchor='w' if sign > 0 else 'e',
                                  fill='#075A65', font=(UI_FONT, 9, 'bold'))

        # NÂNG ĐƯỜNG KÍCH THƯỚC B, a LÊN ĐỈNH GIA TẢI
        dim_y = (top_y - extra_h_top * scale - 20) if has_sc else (top_y - 20)
        main_reach_px = right_b * scale + a * scale
        left_reach_px = (left_b + a) * scale

        c.create_line(cx - left_reach_px, dim_y, cx + main_reach_px, dim_y, fill='#1E293B', width=1.2)
        for xp in (cx - left_reach_px, cx - left_b * scale, cx + right_b * scale, cx + main_reach_px):
            c.create_line(xp, ground_y, xp, dim_y - 4, fill='#CBD5E1', width=1, dash=(2, 2))
            c.create_line(xp - 3, dim_y + 3, xp + 3, dim_y - 3, fill='#0F172A', width=1.6)

        if a > 0:
            c.create_text(cx - (left_b * scale + left_reach_px) / 2, dim_y - 8, text=f"a={a:.2f}m", fill='#0F172A', font=(UI_FONT, 9, 'bold'))
            c.create_text(cx + (right_b * scale + main_reach_px) / 2, dim_y - 8, text=f"a={a:.2f}m", fill='#0F172A', font=(UI_FONT, 9, 'bold'))
        if b_total > 0:
            c.create_text(cx+(right_b-left_b)*scale/2, dim_y - 8,
                          text=f"B={left_b+right_b:.2f}m", fill='#0F172A',
                          font=(UI_FONT, 9, 'bold'))

        if htk > 0:
            draw_dim_v(c, cx + toe_x, top_y, ground_y, f"Htk = {htk:.2f}m", offset=26)

# 3. Mực nước ngầm MNN
    if current_step >= 1:
        soil_scale = (bottom_y - ground_y) / total_depth
        wy = ground_y - water_elevation * soil_scale if water_elevation <= 0 else ground_y - water_elevation * scale
        wy = max(top_y, min(bottom_y, wy))

        x_mnn = x_soil_right - 25

        c.create_line(x_soil_left, wy, x_soil_right, wy, fill='#0284C7', dash=(6, 3), width=1.5)
        c.create_polygon(x_mnn, wy, x_mnn - 6, wy - 9, x_mnn + 6, wy - 9, fill='#0284C7', outline='#0369A1')
        c.create_line(x_mnn - 7, wy + 2, x_mnn + 7, wy + 2, fill='#0284C7', width=1.5)
        c.create_line(x_mnn - 4, wy + 4, x_mnn + 4, wy + 4, fill='#0284C7', width=1.5)
        c.create_line(x_mnn - 2, wy + 6, x_mnn + 2, wy + 6, fill='#0284C7', width=1.5)

        txt_mnn = "MNN = ±0.00 m" if abs(water_elevation) < 1e-4 else f"MNN = {water_elevation:+.2f} m"
        c.create_text(x_mnn - 12, wy - 8, text=txt_mnn, fill='#0369A1',
                      anchor='e', font=(UI_FONT, 9, 'bold'))

    zone_boundary = None if extension_cdm or project.expansion_width > 0 else main_zone_boundary(project)
    if current_step >= 1 and zone_boundary is not None:
        zone_x = (b+a if project.main_treatment == 'CDM' else
                  max(0.0, b+a-0.5*(project.main_replacement_depth or
                      max(project.main_bamboo_depth, project.main_cajuput_depth)))
                  if project.main_treatment == 'Cơ học' else b)
        for sign in (-1, 1):
            boundary_px = cx+sign*zone_x*scale
            c.create_line(boundary_px, ground_y+3, boundary_px, bottom_y,
                          fill='#94A3B8', dash=(4, 4), width=1,
                          tags='main_zone_boundary')
            c.create_text(boundary_px+sign*4, bottom_y-12,
                          text=f'Ranh giới {project.main_treatment}',
                          anchor='w' if sign > 0 else 'e',
                          fill='#64748B', font=(UI_FONT, 7),
                          tags='main_zone_boundary')

    if current_step == 6 and cdm_overlay:
        data, method = cdm_overlay
        params = data['params']
        depth = min(total_depth, max(0.0, params.get('Lc', 0.0)))
        spacing = max(0.1, params.get('s', 1.2))
        diameter = max(0.05, params.get('D', 0.6))
        tip_y = ground_y + depth*(bottom_y-ground_y)/total_depth
        if data['scope'] == 'Nền mở rộng' or project.expansion_width > 0:
            ranges = display_treatment_ranges()
        else:
            ranges = [(cx-(b+a)*scale, cx+(b+a)*scale)]
        for x0, x1 in ranges:
            if x1 <= x0:
                continue
            c.create_rectangle(x0, ground_y+3, x1, tip_y,
                               fill='#CFFAFE', stipple='gray50',
                               outline='#0891B2', width=1.5,
                               tags='cdm_overlay')
            c.create_line(x0, ground_y+3, x1, ground_y+3,
                          fill='#0E7490', width=3, tags='cdm_overlay')
            count = max(1, min(50, int((x1-x0)/max(spacing*scale, 1))))
            for i in range(count):
                x = x0+(i+0.5)*(x1-x0)/count
                radius = min(diameter*scale/2, (x1-x0)/(count*3))
                c.create_rectangle(x-radius, ground_y+4, x+radius, tip_y,
                                   fill='#BAE6FD', stipple='gray75', outline='#0E7490',
                                   width=1, tags='cdm_overlay')
            c.create_text((x0+x1)/2, tip_y+10,
                          text=f'{"NỀN MỞ RỘNG" if project.expansion_width > 0 or data["scope"] == "Nền mở rộng" else "NỀN ĐƯỜNG"} · '
                               f'{"ALiCC" if method == "alicc" else "CDM"} · Lc={depth:.2f}m',
                          fill='#075985', font=(UI_FONT, 9, 'bold'),
                          tags='cdm_overlay')

    # Ghi nhận các nét phân tích để đưa lên trên lớp bấc thấm/cọc cát.
    overlay_before = max(c.find_all(), default=0)
    if current_step in (3, 4, 5, 6) and plot_mode != 'Mặt cắt' and project.soils:
        load_project = analysis_project or project
        axis_values = axes(project)
        asymmetric = project.expansion_width > 0 and project.expansion_side != 'Không'
        ext_h, ext_slope, _ = expansion_parameters(project)
        ext_visible_h = ext_h*h_emb/max(project.height, .001)
        ext_inner = b + m_slope*max(0.0,h_emb-ext_visible_h)
        ext_outer = ext_inner + project.expansion_width
        ext_toe = ext_outer + ext_slope*ext_visible_h

        def display_axis_x(name, x_model):
            sign = -1 if x_model < 0 else 1
            if 'nền mở rộng' in name:
                return sign*(ext_toe if name.startswith('Chân') else ext_outer)
            if name.startswith('Chân đường'):
                return sign*(b+m_slope*h_emb)
            if 'bệ phản áp' in name and has_cw_flag:
                shoulder = b+m_slope*(h_emb-hc)+wc
                return sign*(shoulder+mc if name.startswith('Chân') else shoulder)
            return x_model

        positions = [(name, x, display_axis_x(name,x), i)
                     for i, (name,x) in enumerate(axis_values)]
        depth_px = bottom_y - ground_y
        if plot_mode == 'Độ lún':
            if current_step == 6 and cdm_overlay and settlement_totals is not None:
                data, method = cdm_overlay
                values = settlement_totals
                value = max(values, default=0.0)
                depth = min(total_depth, max(0.0, data['params']['Lc']))
                reference_y = ground_y+6
                drop = min(50.0,max(5.0,value)) if value > 0 else 0.0
                for x0,x1 in display_treatment_ranges():
                    c.create_line(x0,reference_y,x1,reference_y,fill='#94A3B8',dash=(4,3))
                    c.create_line(x0,reference_y+drop,x1,reference_y+drop,fill='#B91C1C',width=2.5)
                    for px in (x0,(x0+x1)/2,x1):
                        c.create_line(px,reference_y,px,reference_y+drop,fill='#475569',dash=(3,3))
                    c.create_text((x0+x1)/2,reference_y+drop+14,
                                  text=f'{settlement_label}={value:.2f} cm · {"ALiCC" if method == "alicc" else "CDM"}',
                                  fill='#B91C1C',font=(UI_FONT,8,'bold'))
            elif current_step == 6 or (not settlement_elements and settlement_totals is None):
                c.create_text(w - 12, h - 25, anchor='e', text='Bấm tính lún để xem đường nén lún',
                              fill='#475569', font=(UI_FONT, 9))
            else:
                totals = (list(settlement_totals) if settlement_totals is not None else
                          [sum(e['St_list'][i] for e in settlement_elements)
                           for i in range(len(axis_values))])
                max_value = max(totals + [0.01])
                vertical_scale = min(60.0, max(25.0, depth_px * 0.22)) / max_value
                # Dùng đúng tọa độ chân/vai của hình vẽ, kể cả bệ phản áp.
                right_nodes = sorted(((x_display, totals[i], label)
                                      for label, _, x_display, i in positions if x_display >= 0),
                                     key=lambda v: v[0])
                if asymmetric:
                    samples = sorted(((x_display, totals[i], label)
                                      for label, _, x_display, i in positions), key=lambda v: v[0])
                else:
                    samples = [(-x, value, label) for x, value, label in reversed(right_nodes[1:])]
                    samples += right_nodes
                curve = [(cx + x_m * scale, ground_y + 12 + s_cm * vertical_scale)
                         for x_m, s_cm, _ in samples]
                # Spline Hermite giữa các điểm đo; các điểm được giữ chính xác.
                for segment in range(len(curve)-1):
                    p0 = curve[max(0, segment-1)]
                    p1, p2 = curve[segment:segment+2]
                    p3 = curve[min(len(curve)-1, segment+2)]
                    prev = p1
                    for k in range(1, 17):
                        t = k/16
                        h00, h10 = 2*t**3-3*t*t+1, t**3-2*t*t+t
                        h01, h11 = -2*t**3+3*t*t, t**3-t*t
                        x1 = h00*p1[0]+h10*(p2[0]-p0[0])/2+h01*p2[0]+h11*(p3[0]-p1[0])/2
                        y1 = h00*p1[1]+h10*(p2[1]-p0[1])/2+h01*p2[1]+h11*(p3[1]-p1[1])/2
                        c.create_line(*prev, x1, y1, fill='#B91C1C', width=2.5)
                        prev = (x1, y1)
                for idx, ((x_m, s_cm, label), (px, py)) in enumerate(zip(samples, curve)):
                    c.create_line(px, ground_y, px, py, fill='#475569', width=1,
                                  dash=(4, 3))
                    c.create_oval(px-3, py-3, px+3, py+3, fill='#B91C1C', outline='white')
                    c.create_text(px, py+10+(idx%3)*12,
                                  text=f'{label}\n{settlement_label}={s_cm:.2f} cm', anchor='n',
                                  justify='center', fill='#B91C1C',
                                  font=(UI_FONT, 7, 'bold'))
                if stage_label:
                    c.create_text(w-12, h-25, anchor='e', text=stage_label,
                                  fill='#B91C1C', font=(UI_FONT, 9, 'bold'))
        else:
            hydro = plot_mode == 'Áp lực nước tĩnh'
            pore = plot_mode == 'Áp lực nước lỗ rỗng'
            stress_add = plot_mode == 'Ứng suất tăng thêm'
            stress_self = plot_mode == 'Ứng suất bản thân'
            symbol = 'Δp' if stress_add else 'P₀' if stress_self else 'u₀' if hydro else 'u' if pore else 'Δu'
            plot_color = '#D97706' if stress_add else '#0284C7' if stress_self else '#0369A1' if hydro else '#7C3AED' if pore else '#D97706'
            def water_pressure(z, x_m, axis_idx=0):
                fraction = (pore_remaining[axis_idx] if isinstance(pore_remaining, (tuple,list))
                            else pore_remaining)
                return cad_pressure_value(project,load_project,plot_mode,z,x_m,fraction,
                                          vacuum_active,treated=current_step >= 4)

            max_value = max(0.01, *(water_pressure(total_depth*k/20, x_model, axis_idx)
                                    for _, x_model, _, axis_idx in positions for k in range(21)))
            arrow_span = min(32.0, max(13.0, b * scale * 0.30))
            unit_scale = arrow_span / max_value
            c.create_text(x_soil_left + 8, ground_y + 12,
                          text=f'{plot_mode}: {symbol} (T/m²)', anchor='w',
                          fill=plot_color, font=(UI_FONT, 9, 'bold'))
            # Đường đứng tại Tim/Vai/Chân và đường bao áp lực đối xứng hai bên.
            for idx, (label, x_m, x_display, axis_idx) in enumerate(positions):
                for side in ((1,) if asymmetric else (-1, 1)):
                    baseline = cx + side * x_display * scale
                    sign = -1 if x_display < 0 else side
                    if idx or side == 1:
                        c.create_line(baseline, ground_y+3, baseline, bottom_y,
                                      fill='#64748B', width=1, dash=(4, 3))
                    points = []
                    first_z = 0.0
                    for step in range(61):
                        z = first_z + (total_depth-first_z) * step / 60
                        value = water_pressure(z, x_m, axis_idx)
                        points.append((baseline + sign * value * unit_scale,
                                       ground_y + depth_px * z / total_depth))
                    for p1, p2 in zip(points, points[1:]):
                        c.create_line(*p1, *p2, fill=plot_color, width=1.6)
                    for fraction in (0.2, 0.4, 0.6, 0.8):
                        z = total_depth * fraction
                        y = ground_y + depth_px * fraction
                        tail = baseline + sign * water_pressure(z, x_m, axis_idx) * unit_scale
                        if abs(tail-baseline) >= 3:
                            c.create_line(tail, y, baseline, y, fill=plot_color,
                                          width=1.2, arrow='last', arrowshape=(5, 6, 2))
                    if (idx or side == 1) and not (stress_add or stress_self):
                        c.create_text(baseline, bottom_y-8-idx*12,
                                      text=f'{symbol}={water_pressure(total_depth, x_m, axis_idx):.2f}',
                                      anchor='s', fill=plot_color,
                                      font=(UI_FONT, 7, 'bold'))
                    if (stress_add or stress_self) and (idx > 0 or side == 1):
                        depths = [first_z]
                        for soil in project.soils:
                            depths.append(min(total_depth, depths[-1]+max(0.0, soil.thickness)))
                        for boundary_index, z in enumerate(depths[1:], start=1):
                            y = ground_y + depth_px*z/total_depth
                            value = water_pressure(z, x_m, axis_idx)
                            x_curve = baseline + sign*value*unit_scale
                            c.create_oval(x_curve-2, y-2, x_curve+2, y+2,
                                          fill=plot_color, outline='white')
                            c.create_text(x_curve+sign*5, y+(-7 if boundary_index % 2 else 7),
                                          text=f'{symbol}={value:.2f}',
                                          anchor='w' if sign > 0 else 'e',
                                          fill=plot_color, font=(UI_FONT, 7, 'bold'))
                    if idx > 0 or side == 1:
                        # z=0 chính là đáy nền đắp, ghi riêng phía trên để không bị
                        # đường thoát nước ngang và nhãn ở ranh giới lớp che khuất.
                        top_value = water_pressure(first_z, x_m, axis_idx)
                        reference_y = ground_y + depth_px*first_z/total_depth
                        top_y_label = reference_y - 15 - 11*(idx % 2)
                        c.create_line(baseline, reference_y, baseline, top_y_label+3,
                                      fill=plot_color, width=1, dash=(3, 2))
                        c.create_text(baseline, top_y_label,
                                      text=f'{symbol}={top_value:.2f}', anchor='s',
                                      fill=plot_color, font=(UI_FONT, 7, 'bold'))
            if pore or plot_mode == 'Áp lực nước thặng dư':
                c.create_text(w-12, h-25, anchor='e',
                              text='Áp lực thặng dư ước tính theo U trung bình',
                              fill='#475569', font=(UI_FONT, 7))
            if stage_label:
                c.create_text(w-12, h-38, anchor='e', text=stage_label,
                              fill=plot_color, font=(UI_FONT, 9, 'bold'))

    overlay_after = max(c.find_all(), default=overlay_before)
    for overlay_id in range(overlay_before + 1, overlay_after + 1):
        c.addtag_withtag('cad_analysis_overlay', overlay_id)

    # Vùng xử lý chung cho đào thay, cọc, thoát nước và gia tải.
    if current_step in (4, 5):
        quiet_drains = plot_mode != 'Mặt cắt'
        mode = treatment_vars.get('treatment', tk.StringVar(value='PVD')).get()
        is_extension = project.expansion_width > 0 and project.expansion_side != 'Không'
        if is_extension:
            ranges = display_treatment_ranges()
        else:
            t_x = (b+a)*scale
            if has_cw_flag and treatment_flags.get('drain_cw_enabled', tk.BooleanVar()).get():
                t_x = reach*scale
            ranges = [(cx-t_x, cx+t_x)]
        sc_px = 0.0
        toe_l, toe_r = ranges[0] if ranges else (cx,cx)
        if mode in ('PVD', 'SD') and project.treatment_group != 'mechanical':
            is_pvd = mode == 'PVD'
            prefix = 'pvd_' if is_pvd else 'sd_'
            length = number_or_zero(treatment_vars.get(prefix+'length', tk.StringVar()).get())
            if length <= 0:
                length = sum(soil.thickness for soil in project.soils if soil.category == 'Đất dính')
            spacing = number_or_zero(treatment_vars.get(prefix+'spacing', tk.StringVar(value='1.2')).get()) or 1.2
            tip = ground_y+(bottom_y-ground_y)*min(total_depth,length)/total_depth
            color = '#A8A29E' if quiet_drains else '#7C3AED' if is_pvd else '#B45309'
            horizontal = treatment_vars.get('horizontal_drain_type', tk.StringVar()).get()
            for left,right in ranges:
                if horizontal == 'Lớp đệm cát':
                    cushion = number_or_zero(treatment_vars.get('h_sand_cushion', tk.StringVar(value='0.5')).get())
                    sc_px = max(4.0,cushion*scale)
                    c.create_rectangle(left,ground_y-sc_px,right,ground_y,
                                       fill='#FDE68A',outline=color)
                else:
                    c.create_line(left,ground_y-4,right,ground_y-4,fill=color,width=2,dash=(9,3))
                count = max(1,min(200,int((right-left)/max(spacing*scale,1))))
                if length > 0:
                    for j in range(count):
                        x = left+(j+.5)*(right-left)/count
                        c.create_line(x,ground_y,x,tip,fill=color,width=2 if is_pvd else 4)
                c.create_text((left+right)/2,tip+10,
                              text=f'{mode} · L={length:.2f} m · s={spacing:.2f} m',
                              font=(UI_FONT,8),fill=color)
        if shallow_depths:
            replacement = shallow_depths.get('replacement_depth',0.0)
            start_y = ground_y+(bottom_y-ground_y)*min(replacement,total_depth)/total_depth
            for left,right in ranges:
                # Giữ toàn bộ phạm vi mở rộng, không vẽ cọc dưới nền chính.
                inset = 0.0 if is_extension else min(replacement*scale,(right-left)/2)
                bottom_left,bottom_right = left+inset,right-inset
                if is_extension:
                    # Toe-side cut slopes inward at m=1; the Bxl-side cut is vertical.
                    inset = min(min(replacement,total_depth)*scale, right-left)
                    if (left+right)/2 < cx:
                        bottom_left = left+inset
                    else:
                        bottom_right = right-inset
                if replacement > 0:
                    c.create_polygon(left,ground_y,right,ground_y,bottom_right,start_y,bottom_left,start_y,
                                     fill='#F2EFE8',outline='#334155',width=1.3)
                    if is_extension:
                        toe_x = left if (left+right)/2 < cx else right
                        bottom_x = bottom_left if (left+right)/2 < cx else bottom_right
                        c.create_text((toe_x+bottom_x)/2,(ground_y+start_y)/2-10,
                                      text='m=1',fill='#334155',font=(UI_FONT,8,'bold'))
                    c.create_text((left+right)/2,(ground_y+start_y)/2,
                                  text=f'ĐÀO THAY {replacement:.2f} m',font=(UI_FONT,8),fill='#334155')
                for key,title in (('bamboo_depth','CỌC TRE'),('cajuput_depth','CỪ TRÀM')):
                    depth = shallow_depths.get(key,0.0)
                    if depth <= 0:
                        continue
                    tip = ground_y+(bottom_y-ground_y)*min(replacement+depth,total_depth)/total_depth
                    for j in range(11):
                        x = bottom_left+(j+.5)*(bottom_right-bottom_left)/11
                        c.create_line(x,start_y,x,tip,fill='#475569',width=2)
                        c.create_line(x-3,tip-5,x,tip,x+3,tip-5,fill='#475569')
                    c.create_text((left+right)/2,tip+10,text=f'{title} L={depth:.2f} m',
                                  font=(UI_FONT,8),fill='#334155')
        if is_extension:
            for left,right in ranges:
                if has_sc:
                    c.create_rectangle(left,top_y-extra_h_top*scale,right,top_y,
                                       fill='#FEF08A',outline='#D97706')
                    c.create_text((left+right)/2,top_y-extra_h_top*scale/2,text='GT',font=(UI_FONT,8))
                if vacuum_enabled:
                    c.create_line(left,ground_y-sc_px-4,right,ground_y-sc_px-4,fill='#DC2626',width=3)
                    c.create_line(left,ground_y-sc_px-4,left,ground_y+12,fill='#DC2626',width=2)
                    c.create_line(right,ground_y-sc_px-4,right,ground_y+12,fill='#DC2626',width=2)
                    c.create_text((left+right)/2,ground_y-sc_px-14,text='MÀNG KÍN KHÍ',font=(UI_FONT,8),fill='#DC2626')

        # =========================================================================
        # VẼ LỚP GIA TẢI TRƯỚC (SURCHARGE) KÝ HIỆU RÚT GỌN (GT)
        # =========================================================================
        if has_sc and not is_extension:
            m_surcharge = 1.2
            b_sc_top = max(0.4 * b, b - (m_surcharge * hs_val))

            surcharge_pts = [
                (cx - b * scale, top_y),
                (cx - b_sc_top * scale, top_y - extra_h_top * scale),
                (cx + b_sc_top * scale, top_y - extra_h_top * scale),
                (cx + b * scale, top_y)
            ]
            c.create_polygon(surcharge_pts, fill='#FEF08A', outline='#D97706', width=2)
            
            for lx in range(int(cx - b * scale) + 12, int(cx + b * scale), 20):
                c.create_line(lx, top_y - 2, lx + 8, top_y - extra_h_top * scale + 2, fill='#EAB308', width=1.2, dash=(2, 2))

            # Nhãn rút gọn GT
            c.create_text(cx, (top_y + top_y - extra_h_top * scale) / 2,
                          text="GT", fill='#92400E', font=(UI_FONT, 10, 'bold'))
            draw_dim_v(c, cx + b * scale + 10, top_y - extra_h_top * scale, top_y, f"hs = {hs_val:.2f}m", offset=16)

        # =========================================================================
        # VẼ HỆ THỐNG MÀNG KÍN KHÍ HÚT CHÂN KHÔNG (VACUUM)
        # =========================================================================
        p_vac = number_or_zero(treatment_vars.get('vacuum_pressure', tk.StringVar(value='8.0')).get())
        if vacuum_enabled and p_vac > 0 and not is_extension:
            membrane_y = ground_y - sc_px - 3 if sc_px > 0 else ground_y - 4
            trench_depth = 18.0
            
            membrane_pts = [
                (toe_l - 28, ground_y + trench_depth),
                (toe_l - 28, membrane_y),
                (toe_r + 28, membrane_y),
                (toe_r + 28, ground_y + trench_depth)
            ]
            for idx in range(len(membrane_pts) - 1):
                p1, p2 = membrane_pts[idx], membrane_pts[idx + 1]
                c.create_line(p1[0], p1[1], p2[0], p2[1], fill='#DC2626', width=2.8)

            c.create_rectangle(toe_l - 34, ground_y, toe_l - 22, ground_y + trench_depth, fill='#FECA57', outline='#DC2626')
            c.create_rectangle(toe_r + 22, ground_y, toe_r + 34, ground_y + trench_depth, fill='#FECA57', outline='#DC2626')
            c.create_text(toe_l - 38, ground_y + 8, text="Rãnh neo khí", fill='#DC2626', font=(UI_FONT, 7, 'italic'), anchor='e')
            c.create_text(toe_r + 38, ground_y + 8, text="Rãnh neo khí", fill='#DC2626', font=(UI_FONT, 7, 'italic'), anchor='w')

            pump_x = toe_l - 55
            pump_y = membrane_y - 20
            c.create_rectangle(pump_x - 16, pump_y - 12, pump_x + 16, pump_y + 12, fill='#1E293B', outline='#0284C7', width=1.5)
            c.create_text(pump_x, pump_y, text="BƠM CK", fill='#FFFFFF', font=(UI_FONT, 6, 'bold'))
            c.create_line(pump_x + 16, pump_y, toe_l - 28, membrane_y, fill='#0284C7', width=1.6, dash=(3, 2))

            c.create_rectangle(cx - 145, membrane_y - 19, cx + 145, membrane_y - 4, fill='#FEF2F2', outline='#DC2626', width=1)
            c.create_text(cx, membrane_y - 11,
                          text=f"MÀNG KÍN KHÍ & HÚT CHÂN KHÔNG (Pvac = -{p_vac:.2f} T/m²)",
                          fill='#DC2626', font=(UI_FONT, 7, 'bold'))

    if project.expansion_width > 0 and project.expansion_side != 'Không':
        for left,right in display_treatment_ranges():
            dim_y = ground_y-24
            c.create_line(left,ground_y,left,dim_y-4,fill='#075985',dash=(3,3),tags='bxl_dimension')
            c.create_line(right,ground_y,right,dim_y-4,fill='#075985',dash=(3,3),tags='bxl_dimension')
            c.create_line(left,dim_y,right,dim_y,fill='#075985',width=1.0,
                          arrow='both',arrowshape=(4,5,2),tags='bxl_dimension')
            label=c.create_text((left+right)/2,dim_y-10,
                                text=f'Bxl = {(right-left)/scale:.2f} m',
                                fill='#075985',font=(UI_FONT,7),tags='bxl_dimension')

    c.tag_raise('cad_analysis_overlay')
    c.tag_raise('main_zone_boundary')
    c.tag_raise('cdm_overlay')
    c.tag_raise('cad_analysis_overlay')
    # Thước tỷ lệ
    c.create_line(20, h - 14, 120, h - 14, fill='#0F172A', width=2)
    c.create_line(20, h - 19, 20, h - 9, fill='#0F172A', width=2)
    c.create_line(120, h - 19, 120, h - 9, fill='#0F172A', width=2)
    scale_meters = (100 / max(scale, 1e-3))
    c.create_text(70, h - 22, text=f"Thước tỷ lệ: ~{scale_meters:.2f} m", font=(UI_FONT, 7, 'bold'), fill='#475569')


# ==============================================================================
# 2. HỘP THOẠI ĐĂNG NHẬP (LOGIN GATEKEEPER)
# ==============================================================================
def authenticated_role(data):
    """Normalize administrator claims from a successful server login."""
    role = str(data.get('role') or 'user').strip().lower()
    account_type = str(data.get('account_type') or '').strip().lower()
    if data.get('success') and (
        role in ('admin', 'system')
        or data.get('is_system') is True
        or account_type == 'system'
    ):
        return 'admin'
    return 'user'


class StartupLoginDialog(tk.Toplevel):
    def __init__(self, parent, api_url: str, on_success_callback):
        super().__init__(parent)
        if getattr(parent, '_startup_splash', None) is not None:
            self.withdraw()
        self.parent = parent
        self.api_url = api_url
        self.on_success = on_success_callback
        self.authenticated = False

        self.title("SoilFirm Pro - Xác thực quyền sử dụng")
        self.configure(bg=COLORS['background'])
        
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        dlg_w = min(1000, sw - 40)
        dlg_h = min(720, sh - 60)
        x = int((sw - dlg_w) / 2)
        y = int((sh - dlg_h) / 2)
        
        self.geometry(f"{dlg_w}x{dlg_h}+{x}+{y}")
        self.attributes('-topmost', True)
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)

        self.auth_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.soilfirm_auth.json')
        self.scroll_frame = _PopupScrollFrame(self)
        self.scroll_frame.pack(fill='both', expand=True)
        inner = self.scroll_frame.scrollable_frame

        self._build_ui(inner, dlg_w)
        self._load_saved_credentials()
        self.parent._apply_ui_language()
        self.bind('<Map>', _popup_mapped, add='+')

    def _build_ui(self, parent_frame: tk.Frame, w: int):
        header = tk.Frame(parent_frame, bg=COLORS['nav'], padx=24, pady=18)
        header.pack(fill='x')
        language_row = tk.Frame(header, bg=COLORS['nav'])
        language_row.pack(fill='x')
        self.language_selector = ttk.Combobox(
            language_row, textvariable=self.parent.ui_language,
            values=('Tiếng Việt', 'English'), state='readonly', width=11,
            font=(UI_FONT, 9))
        self.language_selector._sf_language_selector = True
        self.language_selector.pack(side='right')
        tk.Label(language_row, text='Ngôn ngữ / Language:',
                 bg=COLORS['nav'], fg='#D8E6EF',
                 font=(UI_FONT, 9)).pack(side='right', padx=(0, 8))
        self.language_selector.bind('<<ComboboxSelected>>', self.parent._set_ui_language)
        brand = tk.Frame(header, bg=COLORS['nav'])
        brand.pack()
        c_head = tk.Canvas(brand, width=150, height=170, bg=COLORS['nav'], highlightthickness=0)
        c_head.pack(side='left', padx=(0, 18))
        lx, ly = 75, 85
        c_head.create_rectangle(lx - 65, ly + 22, lx + 65, ly + 42, fill='#162B44', outline='#244163', width=1.5)
        c_head.create_rectangle(lx - 65, ly + 42, lx + 65, ly + 62, fill='#112338', outline='#1F3A58', width=1.5)

        for dx in [lx - 42, lx - 21, lx, lx + 21, lx + 42]:
            c_head.create_line(dx, ly + 22, dx, ly + 55, fill=COLORS['accent'], width=2.5)
            c_head.create_polygon(dx - 3.5, ly + 55, dx + 3.5, ly + 55, dx, ly + 61, fill=COLORS['accent'], outline='')

        trap_pts = [lx - 30, ly - 34, lx + 30, ly - 34, lx + 60, ly + 22, lx - 60, ly + 22]
        c_head.create_polygon(trap_pts, fill='#17384D', outline=COLORS['accent'], width=2)
        c_head.create_text(lx, ly - 6, text="SF", fill='#FFFFFF', font=(UI_FONT, 20, 'bold'))

        for arr_x in [lx - 16, lx, lx + 16]:
            c_head.create_line(arr_x, ly - 54, arr_x, ly - 38, fill='#E5A642', width=2.5, arrow='last', arrowshape=(6, 9, 3))

        try:
            from PIL import Image, ImageTk
            with Image.open(os.path.join(os.path.dirname(__file__), 'logo.png')) as source:
                self._login_brand_image = ImageTk.PhotoImage(source.convert('RGBA').resize((145, 145), Image.Resampling.LANCZOS), master=self)
            c_head.delete('all')
            c_head.create_image(75, 85, image=self._login_brand_image)
        except (OSError, ValueError):
            pass

        titles = tk.Frame(brand, bg=COLORS['nav'])
        titles.pack(side='left', fill='y')
        login_wordmark = tk.Frame(titles, bg=COLORS['nav'])
        login_wordmark.pack(anchor='w', pady=(30, 8))
        tk.Label(login_wordmark, text='SOILFIRM', fg='white', bg=COLORS['nav'],
                 font=(UI_FONT, 20, 'bold')).grid(row=0, column=0)
        tk.Label(login_wordmark, text=' PRO', bg=COLORS['nav'], fg='#00D4E8',
                 font=(UI_FONT, 20, 'bold')).grid(row=0, column=1, sticky='w')
        tk.Label(login_wordmark, text='AI', fg='#00D4E8', bg=COLORS['nav'],
                 font=(UI_FONT, 9, 'bold')).grid(row=0, column=2, sticky='nw', padx=(2,0))
        tk.Label(titles, text="Hỗ trợ thiết kế xử lý nền đất yếu",
                 fg='#B8CEDD', bg=COLORS['nav'], font=(UI_FONT, 10)).pack(anchor='w')
        tk.Label(titles, text="Phiên bản 2026.11",
                 fg='#8DA8BB', bg=COLORS['nav'], font=(UI_FONT, 9)).pack(anchor='w', pady=(8, 0))

        center_frame = tk.Frame(parent_frame)
        center_frame.pack(fill='y', expand=True, pady=30)
        
        form_frame = tk.Frame(center_frame, padx=45, pady=25, relief='solid', bd=1, bg=COLORS['surface'])
        form_frame.pack()

        info_banner = tk.Frame(form_frame, bg='#FEF3C7', relief='solid', bd=1, padx=16, pady=10)
        info_banner.pack(fill='x', pady=(0, 18))
        tk.Label(info_banner, text="📞 LIÊN HỆ SĐT/ZALO: 0869233097 ĐỂ ĐĂNG NHẬP",
                 font=(UI_FONT, 10, 'bold'), fg='#92400E', bg='#FEF3C7').pack(anchor='center')
        tk.Label(info_banner, text="Tác giả: Vũ Ngọc Ánh • Vui lòng nhập Key bản quyền được cấp bên dưới.",
                 font=(UI_FONT, 9), fg='#B45309', bg='#FEF3C7').pack(anchor='center', pady=(3, 0))

        tk.Label(form_frame, text="Tên tài khoản (Username):", bg=COLORS['surface'], fg=COLORS['text'],
                 font=(UI_FONT, 10, 'bold')).pack(anchor='w', pady=(5, 3))
        self.ent_user = ttk.Entry(form_frame, font=(UI_FONT, 11), width=42)
        self.ent_user.pack(fill='x', ipady=4, pady=(0, 12))

        tk.Label(form_frame, text="Khóa kích hoạt (Key / Password):", bg=COLORS['surface'], fg=COLORS['text'],
                 font=(UI_FONT, 10, 'bold')).pack(anchor='w', pady=(5, 3))
        self.ent_key = ttk.Entry(form_frame, font=(UI_FONT, 11), show="*", width=42)
        self.ent_key.pack(fill='x', ipady=4, pady=(0, 10))

        self.var_remember = tk.BooleanVar(value=True)
        cb_style = ttk.Style()
        cb_style.configure("Login.TCheckbutton", font=(UI_FONT, 9))
        cb_rem = ttk.Checkbutton(form_frame, text=" Ghi nhớ tài khoản và mật khẩu trên máy này",
                                 variable=self.var_remember, style="Login.TCheckbutton")
        cb_rem.pack(anchor='w', pady=(0, 5))
        self.var_session_24h = tk.BooleanVar(value=True)
        ttk.Checkbutton(form_frame, text=' Duy trì đăng nhập trong 24 giờ',
                        variable=self.var_session_24h,
                        style='Login.TCheckbutton').pack(anchor='w', pady=(0, 18))

        btn_box = tk.Frame(form_frame, bg=COLORS['surface'])
        btn_box.pack(fill='x')

        self.btn_login = tk.Button(btn_box, text='Đăng nhập', bg=COLORS['accent'], fg='white',
                                   activebackground='#0C6175', activeforeground='white',
                                   font=(UI_FONT, 11, 'bold'), relief='flat', cursor='hand2',
                                   command=self.submit_login)
        self.btn_login.pack(side='left', fill='x', expand=True, ipady=8, padx=(0, 10))
        ttk.Button(form_frame, text='Tạo tài khoản dùng thử', command=self.open_registration).pack(fill='x', pady=(12, 0))

        btn_exit = tk.Button(btn_box, text="Thoát", bg='#E2E8F0', fg='#334155',
                             font=(UI_FONT, 10, 'bold'), relief='flat', cursor='hand2',
                             command=self.on_cancel)
        btn_exit.pack(side='right', ipady=8, ipadx=20)

        self.lbl_status = tk.Label(form_frame, text="", bg=COLORS['surface'], fg=COLORS['muted'], font=(UI_FONT, 9))
        self.lbl_status.pack(pady=(12, 0))
        tk.Label(parent_frame, text='Đăng ký bản quyền phần mềm',
                 bg=COLORS['background'], fg=COLORS['muted'],
                 font=(UI_FONT, 9)).pack(pady=(0, 10))

        self.bind('<Return>', lambda _e: self.submit_login())
        self.ent_user.focus_set()

    def _load_saved_credentials(self):
        try:
            saved = load_credentials(self.auth_file)
            if saved:
                username, key = saved
                self.ent_user.insert(0, username)
                self.ent_key.insert(0, key)
                self.var_remember.set(True)
                self.btn_login.focus_set()
        except Exception as exc:
            self.lbl_status.config(text=f'Không đọc được mật khẩu đã lưu: {exc}', fg='#DC2626')

    def _save_credentials(self, username, key):
        try:
            if self.var_remember.get():
                save_credentials(username, key)
            else:
                clear_credentials()
                if os.path.exists(self.auth_file):
                    os.remove(self.auth_file)
        except Exception as exc:
            messagebox.showwarning('Không lưu được đăng nhập',
                                   f'Đã đăng nhập nhưng không thể ghi nhớ mật khẩu trên máy này:\n{exc}',
                                   parent=self)

    def open_registration(self):
        from registration_dialog import show_registration_dialog
        show_registration_dialog(self)

    def submit_login(self):
        user = self.ent_user.get().strip()
        key = self.ent_key.get().strip()

        if not user or not key:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập đầy đủ Tên tài khoản và Khóa kích hoạt!", parent=self)
            return

        self.lbl_status.config(text="Đang kết nối đến API xác thực...", fg="#0284C7")
        self.update_idletasks()

        try:
            resp = requests.post(f"{self.api_url}/api/login", json={"username": user, "key": key, "device_id": device_id()}, timeout=6)
            data = resp.json()

            if data.get("success"):
                role = authenticated_role(data)
                tier = data.get("tier", "trial")
                fullname = data.get("fullname", user)
                expires_at = data.get("expires_at", "Vĩnh viễn")
                self.authenticated = True
                self.parent._server_first_login = data.get('first_login')
                self.parent._device_lock_supported = bool(data.get('device_lock', False))
                self._save_credentials(user, key)
                try:
                    if self.var_session_24h.get():
                        save_session(user, key)
                    else:
                        clear_session()
                except Exception as exc:
                    messagebox.showwarning('Phiên 24 giờ',
                                           f'Đã đăng nhập nhưng không thể duy trì phiên: {exc}', parent=self)
                self.on_success(role, key, user, fullname, tier, expires_at)
                self.destroy()
            else:
                self.lbl_status.config(text="Từ chối đăng nhập!", fg="#DC2626")
                if data.get('code') == 'ACCOUNT_IN_USE':
                    msg = ('This account is signed in on another device. Please sign out on that device before signing in here.'
                           if self.parent.ui_language.get() == 'English' else
                           'Tài khoản đang đăng nhập trên thiết bị khác. Vui lòng đăng xuất trên thiết bị kia để đăng nhập máy mới.')
                else:
                    msg = data.get('message', 'Key không hợp lệ!')
                messagebox.showerror("Đăng nhập thất bại", msg, parent=self)
        except Exception as err:
            self.lbl_status.config(text="Lỗi kết nối máy chủ!", fg="#DC2626")
            msg = (f"Không thể kết nối đến máy chủ Cloudflare:\n{str(err)}\n\n"
                   "Vui lòng kiểm tra lại đường truyền Internet.")
            messagebox.showerror("Lỗi mạng", msg, parent=self)

    def on_cancel(self):
        if not self.authenticated:
            self.parent.destroy()
            sys.exit(0)


# ==============================================================================
# 3. CLASS ỨNG DỤNG CHÍNH (APP)
# ==============================================================================
class App(tk.Tk):
    def __init__(self, show_startup=False, startup_splash=None):
        super().__init__()
        if startup_splash is not None:
            # Các biến/widget không ghi master phải thuộc ứng dụng chính.
            tk._default_root = self
        self.withdraw()
        self._startup_splash = startup_splash
        if show_startup and startup_splash is None:
            from splash import SplashScreen
            self._startup_splash = SplashScreen(self)
            self._startup_splash.set_progress(0.0, 'Đang khởi động SoilFirm Pro…')
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('SoilFirm.Professional')
            except (AttributeError, OSError):
                pass
            icon_roots = [getattr(sys, '_MEIPASS', ''), os.path.dirname(os.path.abspath(__file__))]
            if getattr(sys, 'frozen', False):
                icon_roots.append(os.path.dirname(sys.executable))
            for icon_root in icon_roots:
                icon_path = os.path.join(icon_root, 'logo.ico')
                if os.path.isfile(icon_path):
                    try:
                        self.iconbitmap(default=icon_path)
                        break
                    except tk.TclError:
                        continue
        try:
            from pathlib import Path
            self._window_brand_icon = tk.PhotoImage(file=str(Path(__file__).with_name('logo.png')), master=self)
            self.iconphoto(True, self._window_brand_icon)
        except (OSError, tk.TclError):
            pass
        self.withdraw()

        self.API_BASE_URL = "https://soilfirm-api.vuanh97nd.workers.dev"
        self.current_user_role = None
        self.current_user_tier = None
        self.admin_key_cached = None
        self.current_username = None
        self.current_fullname = None
        self.current_login_key = None
        self.current_expiry = "Vô hạn"
        self.presence = PresenceClient(self)
        self.support_background = SupportBackground(self)
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        self._calculation_preferences = self._load_calculation_preferences()
        self._calculation_settings = dict(self._calculation_preferences.get('stages', {}))
        self.ui_language = tk.StringVar(value='Tiếng Việt')
        self._install_language_messages()
        self._language_tick_active = True
        self.after(800, self._language_tick)
        self._update_check_queue = queue.Queue()
        self._startup_update_checked = False

        self.project = Project(
            h_design=3.0, h_kcad=0.15, crest_half_width=6.0, slope_m=1.5, water_depth=0.0,
            treatment='Chờ lún', horizontal_drain_type='Bấc thấm ngang', drain_spacing=1.2,
            ignore_uv=False, ignore_fs=False, ignore_fr=False
        )
        self.path: str | None = None
        self.last_rows: list[list[str]] = []
        self._choice_group_results = {}
        self._step_result_cache = {}
        self._switching_step = False
        self._section_excel_path = None
        self._active_section_no = None
        self._active_section_length = None
        
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        win_w = max(800, int(screen_w * 2 / 3))
        win_h = max(560, int(screen_h * 2 / 3))
        pos_x = max(0, int((screen_w - win_w) / 2))
        pos_y = max(0, int((screen_h - win_h) / 2))
        
        self.geometry(f'{win_w}x{win_h}+{pos_x}+{pos_y}')
        self.minsize(min(win_w, 750), min(win_h, 500))
        configure_theme(self)
        for font_name in tkfont.names(self):
            tkfont.nametofont(font_name, root=self).configure(family=UI_FONT)
        style = ttk.Style(self)
        for style_name in ('TLabel', 'TEntry', 'TCombobox', 'TCheckbutton',
                           'TRadiobutton', 'TLabelframe.Label', 'Treeview', 'Treeview.Heading'):
            style.configure(style_name, font=(UI_FONT, 9))
        self.bind_all('<Map>', _popup_mapped, add='+')
        self.bind_all('<Map>', _install_scroll_route, add='+')
        for sequence in ('<MouseWheel>', '<Shift-MouseWheel>', '<Button-4>', '<Button-5>'):
            self.bind_class('SoilFirmWheel', sequence, _scroll_under_pointer)
        compact_nav = screen_w < 1100
        self.compact_nav = compact_nav

        self.cad_zoom = 1.0
        self.cad_pan_x = 0.0
        self.cad_pan_y = 0.0
        self.cad_settlement_metric = tk.StringVar(value='Sc dư')
        self._cad_metric_values = {}
        self.cad_plot_mode = tk.StringVar(value='Độ lún')
        self.cad_stage_mode = tk.StringVar(value='')
        self.cad_plot_display = tk.StringVar(value='Độ lún')
        self.cad_stage_display = tk.StringVar(value='')
        self._cad_stage_days = {}
        self._cad_stage_totals = None
        self._cad_natural_totals = None
        self._cad_stage_project = None
        self._cad_default_totals = None
        self._cad_default_project = None
        self._cad_default_remaining = None
        self._cad_vacuum_active = 0.0
        self._cad_default_vacuum = 0.0
        self._cad_settlement_elements = None
        self._cad_metric_values = {}
        self._cad_pore_remaining = {3: 1.0, 4: 1.0}
        self._drag_start_x = 0
        self._drag_start_y = 0
        self.current_step = 0
        self._visited_groups: set[int] = set()  # theo dõi nhóm bước đã ghé thăm

        self.vars: dict[str, tk.StringVar] = {}
        self.treatment_vars: dict[str, tk.StringVar] = {}
        self.treatment_flags: dict[str, tk.BooleanVar] = {}

        self.bind('<Control-s>', lambda _event: self.save_file())
        self.bind('<Control-o>', lambda _event: self.open())
        self.bind('<F1>', lambda _event: show_help_dialog(self))

        # Thanh Header chính
# Thanh Header chính
        header = tk.Frame(self, bg=COLORS['header'], height=70)
        header.pack(fill='x')
        header.pack_propagate(False)
        
       # Logo biểu tượng kỹ thuật SoilFirm
        brand = tk.Frame(header, bg=COLORS['header'])
        brand.pack(side='left', fill='y', padx=(16, 12))

        # Ưu tiên load file ảnh logo nếu có trong thư mục, nếu không sẽ vẽ vector Canvas sắc nét
        logo_loaded = False
        app_dir = os.path.dirname(os.path.abspath(__file__))
        for img_name in ('logo.png', 'logo.ico'):
            img_path = os.path.join(app_dir, img_name)
            if os.path.isfile(img_path):
                try:
                    from PIL import Image, ImageTk
                    pil_img = Image.open(img_path).convert("RGBA")
                    pil_img = pil_img.resize((60, 60), Image.Resampling.LANCZOS)
                    self._header_logo_img = ImageTk.PhotoImage(pil_img)
                    lbl_logo = tk.Label(brand, image=self._header_logo_img, bg=COLORS['header'], bd=0)
                    lbl_logo.pack(pady=5)
                    logo_loaded = True
                    break
                except Exception:
                    pass

        if not logo_loaded:
            # Vẽ vector Canvas đồ họa kỹ thuật đồng bộ với Splash Screen
            c_logo = tk.Canvas(brand, width=48, height=48, bg=COLORS['header'], highlightthickness=0)
            c_logo.pack(pady=11)

            # 1. Khung huy hiệu công nghệ
            c_logo.create_rectangle(2, 2, 46, 46, fill='#112538', outline='#0284C7', width=1.5)

            # 2. Địa tầng đất ngầm bên dưới
            c_logo.create_rectangle(6, 28, 42, 35, fill='#162B44', outline='#244163', width=1)
            c_logo.create_rectangle(6, 35, 42, 42, fill='#0D1B2A', outline='#1F3A58', width=1)

            # 3. Hệ bấc thấm / cọc cát cắm thẳng đứng (màu vàng cam)
            for dx in [12, 18, 24, 30, 36]:
                c_logo.create_line(dx, 28, dx, 40, fill='#E5A642', width=1.5)
                c_logo.create_polygon(dx - 1.5, 40, dx + 1.5, 40, dx, 42.5, fill='#E5A642', outline='')

            # 4. Thân nền đường đắp hình thang cân
            trap_pts = [14, 15, 34, 15, 41, 28, 7, 28]
            c_logo.create_polygon(trap_pts, fill='#1A384F', outline='#38BDF8', width=1.5)

            # 5. Chữ lồng "SF" sắc nét ở lõi nền đắp
            c_logo.create_text(24, 22, text="SF", fill='#FFFFFF', font=(UI_FONT, 9, 'bold'))

            # 6. Nhãn AI trên biểu tượng SoilFirm
            c_logo.create_text(24, 9, text="AI", fill='#38BDF8', font=('Arial', 7, 'bold'))
                 
        # Tên phần mềm SOILFIRM PRO
        brand_text = tk.Frame(header, bg=COLORS['header'])
        brand_text.pack(side='left', fill='y')
        wordmark = tk.Frame(brand_text, bg=COLORS['header'])
        wordmark.pack(anchor='w', pady=(18, 0))
        tk.Label(wordmark, text='SOILFIRM', bg=COLORS['header'], fg='#FFFFFF',
                 font=(UI_FONT, 20, 'bold')).grid(row=0, column=0, sticky='w')
        tk.Label(wordmark, text=' PRO', bg=COLORS['header'], fg='#00D4E8',
                 font=(UI_FONT, 20, 'bold')).grid(row=0, column=1, sticky='w')
        tk.Label(wordmark, text='AI', bg=COLORS['header'], fg='#00D4E8',
                 font=(UI_FONT, 9, 'bold')).grid(row=0, column=2, sticky='nw', padx=(2, 0))
        
        self.project_caption = tk.StringVar(value='Dự án mới')

        # === CỤM NÚT HEADER MÀU SẮC BẮT MẮT & NHỎ GỌN ===
        actions = tk.Frame(header, bg=COLORS['header'])
        actions.pack(side='right', padx=10, fill='y')

        def make_header_btn(parent, text, command, bg, hover_bg, fg='white'):
            """Nút phẳng bo nhẹ, màu sắc nổi bật, font chữ sắc nét và hiệu ứng hover."""
            btn = tk.Button(
                parent, text=text, command=command,
                bg=bg, fg=fg, activebackground=hover_bg, activeforeground=fg,
                relief='flat', bd=0, cursor='hand2',
                font=(UI_FONT, 9, 'bold'),
                padx=8, pady=3
            )
            btn.bind('<Enter>', lambda _e: btn.configure(bg=hover_bg))
            btn.bind('<Leave>', lambda _e: btn.configure(bg=bg))
            return btn

        # Left-to-right: project actions | AI | account | language.
        f_project_grp = tk.Frame(actions, bg=COLORS['header'])
        self.btn_open_project = make_header_btn(
            f_project_grp, 'Mở dự án', self.open,
            bg='#0D9488', hover_bg='#14B8A6')
        self.btn_save_project = make_header_btn(
            f_project_grp, 'Lưu dự án', self.save_file,
            bg='#2563EB', hover_bg='#3B82F6')

        sep_header = tk.Frame(actions, bg='#53758B', width=1, height=18)
        f_ai_grp = tk.Frame(actions, bg=COLORS['header'])
        tk.Label(f_ai_grp, text='AI:', bg=COLORS['header'], fg='#EAF4FB',
                 font=(UI_FONT, 9, 'bold')).pack(side='left', padx=(0,4))
        self.ai_provider_var = tk.StringVar(value=self._calculation_preferences.get('provider', 'NVIDIA AI'))
        self.ai_web_search_var = tk.BooleanVar(value=self._calculation_preferences.get('web_search', True))
        self.header_ai_selector = ttk.Combobox(f_ai_grp,
            textvariable=self.ai_provider_var,
            values=('Cloudflare AI','Gemini','DeepSeek','DeepSeek (g4f)','deepseek-r1:8b', 'qwen3:8b', 'qwen3:4b-q4_K_M', 'qwen3:4b-q8_0','Groq','Grok (xAI)','ChatGPT','NVIDIA AI','Kimi AI'),
            state='readonly', width=16)

        f_user_grp = tk.Frame(actions, bg=COLORS['header'])
        f_user_grp.pack(side='left', pady=22)
        self.lbl_greeting = tk.Label(
            f_user_grp, text='', bg=COLORS['header'], fg='#FCD34D',
            font=('Segoe UI', 9, 'bold'))
        self.lbl_greeting.pack(side='left', padx=(0,8))
        self.btn_change_pw = make_header_btn(
            f_user_grp, 'Đổi mật khẩu', self.change_password,
            bg='#7C3AED', hover_bg='#8B5CF6')
        self.btn_change_pw.pack(side='left')
        self.btn_logout = make_header_btn(
            f_user_grp, 'Đăng xuất', self.logout,
            bg='#E11D48', hover_bg='#F43F5E')
        self.btn_logout.pack(side='left', padx=(4,0))

        tk.Frame(actions, bg='#53758B', width=1, height=18).pack(
            side='left', padx=8, pady=24)
        self.header_language_selector = ttk.Combobox(
            actions, textvariable=self.ui_language,
            values=('Tiếng Việt', 'English'), state='readonly', width=9,
            font=(UI_FONT, 9))
        self.header_language_selector._sf_language_selector = True
        self.header_language_selector.pack(side='left', pady=22)
        self.header_language_selector.bind('<<ComboboxSelected>>', self._set_ui_language)
        footer = tk.Frame(self, bg='#E7EDF2', height=26)
        footer.pack(side='bottom', fill='x')
        footer.pack_propagate(False)
        self.status_text = tk.StringVar(value='Sẵn sàng')
        tk.Label(footer, textvariable=self.status_text, bg='#E7EDF2', fg=COLORS['muted'],
                 font=(UI_FONT, 9)).pack(side='left', padx=16, pady=4)

        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill='both', expand=True, padx=10, pady=(10, 6))

        left_container = self.left_container = ttk.Frame(self.paned, width=760, height=1)
        left_container.pack_propagate(False)
        self.paned.add(left_container, weight=6)

        step_titles = ['01   Thông tin dự án', '02   Thông số nền đắp', '03   Thông số địa chất',
                       '04   Lún tự nhiên', '05   Thay thế & gia cường cơ học',
                       '06   Cố kết & Thoát nước', '07   Trộn sâu CDM',
                       '08   AI phân tích & lựa chọn phương án',
                       '09   Bảng tổng hợp kết quả xử lý',
                       '10   Tính toán khối lượng xử lý']
        nav_font = tkfont.Font(self, family=UI_FONT, size=9, weight='bold')
        sidebar_width = 212
        self.sidebar = tk.Frame(left_container, bg=COLORS['nav'], width=sidebar_width)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        chat_area = tk.Frame(self.sidebar, bg=COLORS['nav'])
        chat_area.pack(side='bottom', fill='x', padx=7, pady=(4, 8))
        build_weather_clock(chat_area)
        support_row = tk.Frame(chat_area, bg=COLORS['nav'])
        support_row.pack(fill='x', pady=(4, 0))
        support_row.columnconfigure(0, weight=1, uniform='support')
        support_row.rowconfigure(0,weight=1)
        support_row.rowconfigure(1,weight=1)
        self.chat_sidebar_button = tk.Button(
            support_row, text='Liên hệ quản trị viên', command=self.open_chat,
            font=(UI_FONT, 9, 'bold'), bg='#0284C7', fg='#FFFFFF',
            activebackground='#0369A1', activeforeground='#FFFFFF',
            relief='flat', bd=0, cursor='hand2', wraplength=sidebar_width-24)
        self.ai_sidebar_button = tk.Button(
            support_row, text='Hỗ trợ AI', command=self.open_ai_support,
            font=(UI_FONT, 9, 'bold'), bg='#0F766E', fg='#FFFFFF',
            activebackground='#115E59', activeforeground='#FFFFFF',
            relief='flat', bd=0, cursor='hand2', wraplength=sidebar_width-24)
        self.chat_sidebar_button.grid(row=1,column=0,sticky='nsew',ipady=8,pady=(4,0))
        self.ai_sidebar_button.grid(row=0,column=0,sticky='nsew',ipady=8)
        self.chat_sidebar_button.bind('<Enter>', lambda _e: self.chat_sidebar_button.configure(bg='#0369A1'))
        self.chat_sidebar_button.bind('<Leave>', lambda _e: self.chat_sidebar_button.configure(bg='#0284C7'))
        self.ai_sidebar_button.bind('<Enter>', lambda _e: self.ai_sidebar_button.configure(bg='#115E59'))
        self.ai_sidebar_button.bind('<Leave>', lambda _e: self.ai_sidebar_button.configure(bg='#0F766E'))
        nav_canvas = tk.Canvas(self.sidebar, bg=COLORS['nav'], highlightthickness=0,
                               width=sidebar_width-14)
        nav_canvas.pack(side='left', fill='both', expand=True)
        nav_items = tk.Frame(nav_canvas, bg=COLORS['nav'])
        nav_window = nav_canvas.create_window(0, 0, window=nav_items, anchor='nw')
        nav_canvas.bind('<Configure>', lambda event:
                        nav_canvas.itemconfigure(nav_window, width=event.width))
        # Quy trình cố định: không nhận bất kỳ thao tác cuộn nào.
        def lock_design_scroll(widget):
            tags=widget.bindtags()
            widget.bindtags(('SoilFirmDesignLocked',)+tuple(t for t in tags if t!='SoilFirmDesignLocked'))
            for child in widget.winfo_children():
                lock_design_scroll(child)
        for sequence in ('<MouseWheel>','<Shift-MouseWheel>','<Button-4>','<Button-5>'):
            self.bind_class('SoilFirmDesignLocked',sequence,lambda event:'break')
        self.after_idle(lambda: (lock_design_scroll(nav_canvas), lock_design_scroll(nav_items)))

        self.content_container = ttk.Frame(left_container, style='Workspace.TFrame')
        self.content_container.pack(side='right', fill='both', expand=True, padx=(10, 0))

        self.tab_proj = ttk.Frame(self.content_container)
        self.tab_params = ttk.Frame(self.content_container)
        self.tab_soils = ttk.Frame(self.content_container, padding=8)
        self.tab_before = ttk.Frame(self.content_container, padding=8)
        self.tab_after = ttk.Frame(self.content_container)
        self.tab_cdm = ttk.Frame(self.content_container)
        self.tab_choice = ttk.Frame(self.content_container)
        self.tab_result_summary = ttk.Frame(self.content_container)
        self.tab_treatment_boq = ttk.Frame(self.content_container)
        self.tab_geology_statistics = ttk.Frame(self.content_container)

        self.tab_ai_boreholes=ttk.Frame(self.content_container)
        self.tab_ai_sections=ttk.Frame(self.content_container)
        self.tab_export_records=ttk.Frame(self.content_container)
        self.ai_material_host=ttk.Frame(self.content_container)
        self.geology_statistics_host=self.tab_geology_statistics
        self.step_frames = [self.tab_proj, self.tab_params, self.tab_soils,
                            self.tab_before, self.tab_after, self.tab_after,
                            self.tab_cdm, self.tab_choice,
                            self.tab_result_summary, self.tab_treatment_boq, self.tab_geology_statistics, self.tab_ai_boreholes, self.tab_ai_sections, self.tab_export_records, self.ai_material_host]
        self.step_buttons: list[tk.Button] = []

        self._sidebar_heading_font = tkfont.Font(self, family=UI_FONT, size=10, weight='bold')
        # Giữ chiều rộng đã chọn; tên mục dài xuống dòng bằng wraplength.
        self.sidebar.configure(width=sidebar_width)
        nav_canvas.configure(width=sidebar_width-14)
        tk.Label(nav_items, text='QUY TRÌNH THIẾT KẾ', bg=COLORS['nav'], fg='#EAF4FB',
                 font=self._sidebar_heading_font, anchor='w', justify='left',
                 wraplength=sidebar_width-16).pack(fill='x', padx=8, pady=(18, 4))
        # Thanh tiến trình mỏng dưới tiêu đề sidebar
        self._progress_bar_canvas = tk.Canvas(
            nav_items, bg=COLORS['nav'], height=4, highlightthickness=0)
        self._progress_bar_canvas.pack(fill='x', padx=8, pady=(0, 6))
        self._progress_bar_fill = self._progress_bar_canvas.create_rectangle(
            0, 0, 0, 4, fill='#38BDF8', outline='', width=0)
        self._progress_bar_track = self._progress_bar_canvas.create_rectangle(
            0, 0, sidebar_width - 16, 4, fill='#254B61', outline='', width=0)
        self._progress_bar_canvas.tag_lower(self._progress_bar_fill)
        self._progress_bar_canvas.tag_raise(self._progress_bar_track)
        self._progress_bar_canvas.tag_lower(self._progress_bar_track)
        self._progress_bar_canvas.tag_raise(self._progress_bar_fill)

        step_headings = ['Dữ liệu dự án', 'Hình học nền đắp', 'Địa tầng và chỉ tiêu đất',
                         'Lún tự nhiên', 'Xử lý nền bằng biện pháp cơ học',
                         'Cố kết và thoát nước', 'Trộn sâu CDM', 'Lựa chọn phương án',
                         'Bảng tổng hợp kết quả xử lý', 'Tính toán khối lượng xử lý', 'Thống kê số liệu', 'Địa tầng lỗ khoan', 'Phân đoạn tính toán', 'Xuất hồ sơ', 'Bảng tổng hợp chỉ tiêu']
        self.step_descriptions = [
            'Thông tin công trình và chỉ tiêu đánh giá',
            'Hình học nền đắp, bệ phản áp và mực nước ngầm',
            'Mặt cắt địa chất và thông số cố kết',
            'Độ lún trước khi xử lý nền',
            'Đào thay đất, cọc tre, cọc cừ tràm và chờ lún',
            'PVD, SD, chờ lún, gia tải và hút chân không',
            'Cọc xi măng đất theo TCVN/BS và ALiCC',
            'Đọc dữ liệu, xác nhận địa tầng và chỉ tiêu đất, sau đó tính toán và chọn phương án cho từng phân đoạn',
            'Tổng hợp phương án xử lý theo từng phân đoạn',
            'Tính khối lượng xử lý nền cho các phân đoạn đã chọn',
            'AI đọc chỉ tiêu, mẫu thí nghiệm và lựa chọn giá trị thống kê',
            'AI đọc trụ địa chất CAD/PDF, liên kết lớp và lỗ khoan',
            'Nhập dữ liệu và xác nhận số liệu từng phân đoạn',
            'Excel dữ liệu xuất, JSON và PDF chung trước / sau xử lý',
            'Xem lại các chỉ tiêu tính toán tổng hợp từ thống kê mẫu',
        ]
        section_header = tk.Frame(self.content_container, bg=COLORS['background'])
        section_header.pack(fill='x', pady=(4, 8))
        self.workspace_heading = tk.StringVar(value=step_headings[0])
        self.workspace_subtitle = tk.StringVar(value=self.step_descriptions[0])
        tk.Label(section_header, textvariable=self.workspace_heading, bg=COLORS['background'],
                 fg=COLORS['nav'], font=(UI_FONT, 15, 'bold')).pack(anchor='w')
        tk.Label(section_header, textvariable=self.workspace_subtitle, bg=COLORS['background'],
                 fg=COLORS['muted'], font=(UI_FONT, 9)).pack(anchor='w', pady=(2, 0))
        self.workspace_pdf_button = ttk.Button(section_header, text='Xuất báo cáo', style='Accent.TButton')
        self.step_headings = step_headings

        self.result_output = None
        self._result_serial = 0
        self.report_result('Sẵn sàng', 'Kết quả xử lý sẽ hiển thị tại đây.')

        from design_workflow import navigation_groups
        self.design_mode = tk.StringVar(value=self._calculation_preferences.get('mode', 'TÍNH MỘT ĐOẠN'))
        self.navigation_groups = self._configured_navigation_groups()
        mode_box = tk.Frame(nav_items, bg=COLORS['nav'], height=60)
        # Data workflow selection is now available in calculation settings.
        # Keep the existing variables and selector bindings for compatibility.
        mode_box.pack_propagate(False)
        tk.Label(mode_box, text='PHẠM VI TÍNH', bg=COLORS['nav'], fg='#EAF4FB',
                 font=(UI_FONT, 9, 'bold'), anchor='w').place(
                     x=8, y=0, relwidth=1, width=-16, height=23)
        self.mode_display = tk.StringVar(value=(
            'Nhiều đoạn' if self.design_mode.get() == 'TÍNH TOÀN TUYẾN'
            else 'Một đoạn') + '  ▾')
        self.mode_selector = tk.Menubutton(
            mode_box, textvariable=self.mode_display, direction='below',
            font=(UI_FONT, 11, 'bold'), anchor='w',
            bg='#28556E', fg='#FFFFFF', activebackground='#346D88',
            activeforeground='#FFFFFF', relief='flat', bd=0,
            highlightthickness=2, highlightbackground='#60A5C4',
            highlightcolor='#B9E6F8', padx=12, pady=4, cursor='hand2', takefocus=True)
        self.mode_selector.place(x=0, y=27, relwidth=1, height=33)
        mode_menu = tk.Menu(self.mode_selector, tearoff=False,
            font=(UI_FONT, 9), bg='#254B61', fg='#FFFFFF',
            activebackground='#315E76', activeforeground='#FFFFFF',
            selectcolor='#FFFFFF', relief='flat', bd=1)
        for mode_name in ('TÍNH MỘT ĐOẠN', 'TÍNH TOÀN TUYẾN'):
            label = ('Nhiều đoạn'
                     if mode_name == 'TÍNH TOÀN TUYẾN'
                     else 'Một đoạn')
            mode_menu.add_radiobutton(label=label, variable=self.design_mode,
                value=mode_name, command=self.change_design_mode)
        self.mode_selector.configure(menu=mode_menu)
        self.design_mode.trace_add('write', lambda *_:
            self.mode_display.set(('Nhiều đoạn' if self.design_mode.get() == 'TÍNH TOÀN TUYẾN'
                                   else 'Một đoạn') + '  ▾'))
        self.nav_items = nav_items
        self.nav_groups_host = tk.Frame(nav_items, bg=COLORS['nav'])
        self.nav_groups_host.pack(fill='x')
        self._rebuild_workflow_navigation()
        tab_strip=tk.Frame(self.content_container, bg=COLORS['background'])
        self.workspace_tab_strip = tab_strip
        tabs_canvas=tk.Canvas(tab_strip,height=36,highlightthickness=0,bg=COLORS['background'])
        tabs_canvas.pack(fill='x')
        tabs_scroll=ttk.Scrollbar(tab_strip,orient='horizontal',command=tabs_canvas.xview)
        tabs_canvas.configure(xscrollcommand=tabs_scroll.set)
        self.workspace_tabs=tk.Frame(tabs_canvas, bg=COLORS['background'])
        tabs_window=tabs_canvas.create_window(0,0,window=self.workspace_tabs,anchor='nw')
        def fit_tabs(event=None):
            tabs_canvas.configure(scrollregion=tabs_canvas.bbox('all'))
            if self.workspace_tabs.winfo_reqwidth()>tabs_canvas.winfo_width():tabs_scroll.pack(fill='x')
            else:tabs_scroll.pack_forget();tabs_canvas.xview_moveto(0)
        self.workspace_tabs.bind('<Configure>',fit_tabs)
        tabs_canvas.bind('<Configure>',fit_tabs)
        self._visible_group=None

        self.right_container = ttk.Frame(self.paned, width=520, height=1)
        self.right_container.pack_propagate(False)
        self.paned.add(self.right_container, weight=4)

        self._update_startup_progress(0.25, 'Đang tải giao diện…')
        self._build_dashboard(self.right_container)
        self._build_tab_proj()
        self._build_tab_params()
        self._build_tab_soils()
        self._update_startup_progress(0.45, 'Đang tải giao diện…')
        self._build_tab_before()
        self.cdm_scope_var = tk.StringVar(value=self.project.cdm_scope)
        self._build_tab_after()
        self._cdm_reports = {}
        self._cdm_active_method = 'standard'
        self.cb_cdm_scope = self._build_treatment_scope_selector(self.tab_cdm)
        build_cdm_view(self.tab_cdm)
        from ai_analysis_workflow import build_view as build_choice_view
        build_choice_view(self.tab_choice)
        from result_summary import build_view as build_result_summary_view
        from treatment_boq import build_view as build_treatment_boq_view
        self.refresh_result_summary = build_result_summary_view(self.tab_result_summary)
        self.refresh_treatment_boq = build_treatment_boq_view(self.tab_treatment_boq)
        self._update_startup_progress(0.70, 'Đang chuẩn bị không gian làm việc…')

        from geology_statistics import GeologyStatistics
        self.geology_statistics_view=GeologyStatistics(self.geology_statistics_host,self)
        self.geology_statistics_view.pack(fill='both',expand=True)
        if getattr(self,'_ai_analysis_state',{}).get('materials'):
            self.geology_statistics_view.import_ai_samples()
        from batch_hub import build_export_view
        build_export_view(self.tab_export_records,self)
        from design_workflow import SegmentBoard, SingleSelection, RouteSectionSelector, SingleTreatmentBoard
        self.tab_batch_before = ttk.Frame(self.content_container)
        self.tab_batch_design = ttk.Frame(self.content_container)
        self.tab_single_selection = ttk.Frame(self.content_container)
        self.step_frames.extend([self.tab_batch_before, self.tab_batch_design, self.tab_single_selection])
        self.step_headings.extend(['Kiểm toán trước xử lý', 'Bảng tổng hợp xử lý', 'Chọn phương án và báo cáo'])
        self.step_descriptions.extend([
            'Đầu vào, địa tầng và kết quả kiểm toán trước xử lý của từng phân đoạn',
            'Cấu hình giải pháp, tính phương án và kiểm toán sau xử lý theo từng phân đoạn',
            'So sánh phương án đã tính, lựa chọn và xuất hồ sơ một đoạn'])
        self.batch_before_view = SegmentBoard(self.tab_batch_before, self)
        self.batch_before_view.pack(fill='both', expand=True)
        self.batch_design_view = SegmentBoard(self.tab_batch_design, self, after=True)
        self.batch_design_view.pack(fill='both', expand=True)
        self.single_selection_view = SingleSelection(self.tab_single_selection, self)
        self.single_selection_view.pack(fill='both', expand=True)
        self.tab_single_treatment_summary = ttk.Frame(self.content_container)
        self.step_frames.append(self.tab_single_treatment_summary)
        self.step_headings.append('Tổng hợp kết quả xử lý')
        self.step_descriptions.append('So sánh phương án và tổng hợp kết quả trước, sau xử lý của các phân đoạn')
        self.single_treatment_summary_view = SingleTreatmentBoard(self.tab_single_treatment_summary, self)
        self.single_treatment_summary_view.pack(fill='both', expand=True)
        metadata = ttk.LabelFrame(self.tab_ai_sections, text='Thông tin dự án', padding=8)
        first = self.tab_ai_sections.winfo_children()[0]
        metadata.pack(fill='x', padx=8, pady=6, before=first)
        for i, (key, title) in enumerate((('name','Dự án'), ('design_stage','Bước thiết kế'), ('work_item','Hạng mục'))):
            ttk.Label(metadata, text=title).grid(row=i, column=0, sticky='w', padx=4, pady=3)
            ttk.Entry(metadata, textvariable=self.vars[key]).grid(row=i, column=1, sticky='ew', padx=4, pady=3)
        metadata.columnconfigure(1, weight=1)
        for key in ('name', 'design_stage', 'work_item'):
            self.vars[key].trace_add('write', self._sync_project_metadata)
        self.route_section_selector = RouteSectionSelector(self.content_container, self)
        self._workflow_mode = self.design_mode.get()
        self._rebuild_workflow_navigation()
        self.switch_step(0)
        self.project.method = self._calculation_preferences.get('method', 'Cc/Cs/Pc')
        self.populate()
        self._sync_geology_session()
        self._ai_analysis_workspace.state['template'].method = self.project.method
        self._apply_calculation_visibility()
        for key, var in self.vars.items():
            var.trace_add('write', lambda *_: self.invalidate_assessment())
        for var in self.treatment_vars.values():
            var.trace_add('write', lambda *_: self._schedule_unpenetrated_state())
        for group in self.stage_vars:
            for var in group:
                var.trace_add('write', lambda *_: self._schedule_unpenetrated_state())
        for flag in self.stage_flags.values():
            flag.trace_add('write', lambda *_: self._schedule_unpenetrated_state())
        self.vars['name'].trace_add('write', lambda *_: self._update_file_identity())
            
        self._update_file_identity()
        self._schedule_unpenetrated_state()
        self.bind('<Configure>', self._on_window_resize, add='+')
        self.paned.bind('<Configure>', self._sync_workspace_split, add='+')

        self._menu()
        self._apply_ui_language()
        self._mark_project_saved()
        self._update_startup_progress(0.90, 'Đang chuẩn bị không gian làm việc…')
        self.after(50, self.require_login)

    def _update_startup_progress(self, progress, message):
        splash = getattr(self, '_startup_splash', None)
        if splash is not None and splash.winfo_exists():
            splash.set_progress(progress, message)

    def _finish_startup(self, window):
        splash = getattr(self, '_startup_splash', None)
        if splash is None:
            return
        window.update_idletasks()
        self._update_startup_progress(1.0, 'Sẵn sàng làm việc.')
        splash.destroy()
        process = getattr(splash, '_process', None)
        started = time.perf_counter()

        def reveal():
            if process is not None and process.poll() is None:
                # Chờ logo vẽ mức 100% rồi đóng; chỉ dùng giới hạn khi con bị lỗi.
                if time.perf_counter()-started < 2.0:
                    self.after(16, reveal)
                    return
                try:
                    process.terminate()
                except OSError:
                    pass
            self._startup_splash = None
            splash_root = getattr(splash, 'root', None)
            if splash_root is not None and splash_root is not self:
                splash_root.destroy()
            if window.winfo_exists():
                window.deiconify()
                window.lift()
                if hasattr(window, 'ent_user'):
                    window.ent_user.focus_set()
        reveal()

    def logout(self, force=False):
        if getattr(self, '_logout_in_progress', False):
            return
        if not force and not messagebox.askyesno('Đăng xuất', 'Bạn có chắc chắn muốn đăng xuất khỏi hệ thống?', parent=self):
            return
        self._logout_in_progress = True
        account = self.current_username
        key = self.current_login_key
        payload = {'username': account, 'key': key, 'device_id': device_id(),
                   'session_id': self.presence.session_id or '', 'release_device': True}
        base_url = self.API_BASE_URL
        lock_supported = getattr(self, '_device_lock_supported', False)
        is_admin = self.current_user_role == 'admin'
        completed = queue.Queue()
        self.status_text.set('Đang đăng xuất và giải phóng khóa thiết bị…')

        def request_logout():
            if not account or not key:
                completed.put(None)
                return
            try:
                with requests.Session() as session:
                    last_error = None
                    for attempt in range(2):
                        try:
                            response = session.post(base_url+'/api/logout', json=payload, timeout=(5,20))
                            missing_route = response.status_code in (404,405)
                            data = {} if missing_route else response.json()
                            message = str(data.get('message','')).strip().lower()
                            missing_route = missing_route or message in ('route not found.', 'route not found', 'route không tồn tại.', 'route không tồn tại', 'not found')
                            needs_receipt = data.get('success') and lock_supported and not is_admin and not data.get('device_released')
                            if missing_route or needs_receipt:
                                response = session.post(base_url+'/api/activity/logout', json=payload, timeout=(5,20))
                                data = response.json()
                            if response.status_code in (502,503,504):
                                raise requests.ConnectionError('Máy chủ đang bận. Hãy thử lại sau.')
                            if not response.ok or not data.get('success'):
                                raise ValueError(data.get('message','Máy chủ chưa xác nhận đăng xuất.'))
                            if lock_supported and not is_admin and not data.get('device_released'):
                                raise ValueError('Máy chủ chưa xác nhận giải phóng khóa thiết bị. Hãy cập nhật worker.js trong gói sửa.')
                            completed.put(None)
                            return
                        except requests.RequestException as exc:
                            last_error = exc
                            if attempt == 1:
                                raise
                    raise last_error
            except requests.RequestException as exc:
                completed.put('Không kết nối được máy chủ để xác nhận đăng xuất. Phiên đăng nhập được giữ lại; hãy thử lại.\n'+str(exc))
            except (ValueError, TypeError) as exc:
                completed.put(str(exc))
            except Exception as exc:
                completed.put('Không hoàn tất đăng xuất: '+str(exc))

        def finish_logout():
            try:
                error = completed.get_nowait()
            except queue.Empty:
                self.after(100, finish_logout)
                return
            self._logout_in_progress = False
            if error:
                self.status_text.set('Chưa hoàn tất đăng xuất. Vui lòng thử lại.')
                messagebox.showerror('Đăng xuất', error, parent=self)
                return
            active_chat = getattr(self, '_support_window', None)
            if active_chat is not None and active_chat.winfo_exists():
                active_chat.destroy()
            self._support_window = None
            ai_window = getattr(self, '_ai_support_window', None)
            if ai_window is not None and ai_window.winfo_exists():
                ai_window.destroy()
            self._ai_support_window = None
            self._server_first_login = None
            self.presence.stop()
            self.support_background.stop()
            try:
                clear_session()
            except OSError as exc:
                messagebox.showwarning('Đăng xuất', f'Không xóa được phiên đã lưu: {exc}', parent=self)
            self.withdraw()
            self.current_user_role = None
            self.current_user_tier = None
            self.admin_key_cached = None
            self.current_login_key = None
            self.current_username = None
            self.current_fullname = None
            self.lbl_greeting.config(text='')
            self.require_login()

        threading.Thread(target=request_logout, daemon=True).start()
        self.after(100, finish_logout)

    def _show_first_login_welcome(self):
        import hashlib
        from pathlib import Path
        account = (self.API_BASE_URL + '/' + str(self.current_username)).encode('utf-8')
        directory = Path(os.environ.get('APPDATA') or Path.home()) / 'SoilFirm' / 'welcome'
        marker = directory / (hashlib.sha256(account).hexdigest() + '.seen')
        first = getattr(self, '_server_first_login', None)
        if first is False or (first is None and marker.exists()):
            return
        if getattr(self, '_welcome_shown_accounts', None) is None:
            self._welcome_shown_accounts = set()
        if account in self._welcome_shown_accounts:
            return
        self._welcome_shown_accounts.add(account)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            marker.write_text('seen', encoding='utf-8')
        except OSError:
            pass
        window = tk.Toplevel(self)
        window.title('Welcome to SoilFirm Pro' if self.ui_language.get() == 'English' else 'Chào mừng đến với SoilFirm Pro')
        window.transient(self)
        english = self.ui_language.get() == 'English'
        message = ('Welcome to SOILFIRM PRO! Read the user guide in the Help menu (F1). '
                   'If you need assistance, contact the admin using the support button below.' if english else
                   'Chào mừng đến với SOILFIRM PRO!\nXem hướng dẫn sử dụng phần mềm tại mục Help (phím F1).\n'
                   'Nếu cần hỗ trợ, hãy liên hệ với admin tại đây.')
        ttk.Label(window, text=message, wraplength=460, padding=20).pack(fill='x')
        buttons = ttk.Frame(window, padding=12)
        buttons.pack(fill='x')
        def open_target(callback):
            window.destroy()
            callback()
        ttk.Button(buttons, text='User guide (Help)' if english else 'Xem hướng dẫn (Help)',
                   command=lambda: open_target(lambda: show_help_dialog(self))).pack(side='left', padx=4)
        ttk.Button(buttons, text='Admin support' if english else 'Hỗ trợ quản trị viên',
                   command=lambda: open_target(self.open_chat)).pack(side='left', padx=4)
        ttk.Button(buttons, text='Close' if english else 'Đóng', command=window.destroy).pack(side='left', padx=4)
        window.lift()
        window.focus_set()

    def _show_first_software_intro(self):
        import hashlib
        from pathlib import Path
        account = (self.API_BASE_URL + '/' + str(self.current_username)).encode('utf-8')
        folder = Path(os.environ.get('APPDATA') or Path.home()) / 'SoilFirm' / 'intro'
        intro_release = '2026.11-video-20261001'
        marker = folder / (hashlib.sha256(account).hexdigest() + '.' + intro_release + '.seen')
        shown = getattr(self, '_intro_shown_accounts', set())
        if marker.exists() or (account, intro_release) in shown:
            self._show_first_login_welcome()
            self.after(300, self._show_ai_feature_notice)
            return
        def finished():
            if process.poll() == 0:
                shown.add((account, intro_release))
                self._intro_shown_accounts = shown
                try:
                    folder.mkdir(parents=True, exist_ok=True)
                    marker.write_text('seen', encoding='utf-8')
                except OSError:
                    pass
            self._show_first_login_welcome()
            self.after(300, self._show_ai_feature_notice)
        try:
            process = self.show_software_intro(finished)
        except Exception as exc:
            self.report_result('Video giới thiệu', str(exc), error=True)
            self._show_first_login_welcome()
            self.after(300, self._show_ai_feature_notice)

    def _show_ai_feature_notice(self):
        from chat_dialog import show_ai_feature_notice
        show_ai_feature_notice(self)

    def show_software_intro(self, on_complete=None):
        from soilfirm_intro import show_intro
        return show_intro(self, duration_seconds=30, on_complete=on_complete)

    def require_login(self):
        def on_auth_ok(role, key, user, fullname, tier, expires_at="Vô hạn"):
            fullname = _display_account_name(fullname)
            role = 'admin' if str(role).strip().lower() in ('admin', 'system') else 'user'
            self.current_user_role = role
            self.chat_sidebar_button.configure(
                text='Hỗ trợ quản trị viên')
            self.current_user_tier = tier
            self.admin_key_cached = key if role == 'admin' else None
            self.current_login_key = key
            self.current_username = user
            self.current_fullname = fullname
            self.current_expiry = expires_at
            self.presence.start(user, key)
            self.support_background.start()
            self.after(400, self._show_first_software_intro)
            self._menu()
            self._apply_ui_language()
            if getattr(self, '_startup_splash', None) is None:
                self.deiconify()
            self._finish_startup(self)
            self.status_text.set(f'Sẵn sàng  •  Quyền: {role.upper()} ({tier.upper()})  •  Hạn dùng: {expires_at}')
            if not self._startup_update_checked:
                self._startup_update_checked = True
                self.after(1200, self._check_update_automatically)
            
            if role == 'admin':
                self.lbl_greeting.config(text=f"Chào, Admin {fullname}! (Hạn dùng: Vô hạn)")
            else:
                self.lbl_greeting.config(text=f"Chào, {fullname}! (Hạn dùng: {expires_at})")

        # Chỉ bỏ qua hộp đăng nhập khi phiên còn trong 24 giờ và máy chủ vẫn
        # chấp nhận tài khoản. Việc xác thực âm thầm không gia hạn mốc 24 giờ.
        try:
            cached = load_session()
        except Exception:
            cached = None
        if cached:
            user, key = cached
            try:
                response = requests.post(f'{self.API_BASE_URL}/api/login',
                                         json={'username': user, 'key': key, 'device_id': device_id()}, timeout=6)
                data = response.json()
                if data.get('success'):
                    self._server_first_login = data.get('first_login')
                    self._device_lock_supported = bool(data.get('device_lock', False))
                    on_auth_ok(authenticated_role(data), key, user,
                               data.get('fullname', user), data.get('tier', 'trial'),
                               data.get('expires_at', 'Vĩnh viễn'))
                    return
            except (requests.RequestException, ValueError):
                pass
            try:
                clear_session()
            except OSError:
                pass
        dlg = StartupLoginDialog(self, self.API_BASE_URL, on_auth_ok)
        self._finish_startup(dlg)
        self.wait_window(dlg)

    def change_password(self):
        pwd_win = tk.Toplevel(self)
        pwd_win.title("Đổi Mật Khẩu")
        
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(620, sw - 40)
        h = min(490, sh - 60)
        pwd_win.geometry(f"{w}x{h}+{int((sw-w)/2)}+{int((sh-h)/2)}")
        pwd_win.transient(self)
        pwd_win.grab_set()
        
        sf = _PopupScrollFrame(pwd_win)
        sf.pack(fill='both', expand=True)
        f = sf.scrollable_frame

        c_frame = tk.Frame(f, padx=40, pady=30)
        c_frame.pack(fill='both', expand=True)

        tk.Label(c_frame, text="Tài khoản:", font=(UI_FONT, 9, 'bold')).pack(anchor='w', pady=(0, 4))
        ent_user = ttk.Entry(c_frame, font=(UI_FONT, 10), width=40)
        ent_user.insert(0, self.current_username)
        ent_user.config(state='readonly')
        ent_user.pack(fill='x', pady=(0, 15))

        tk.Label(c_frame, text="Mật khẩu hiện tại:", font=(UI_FONT, 9, 'bold')).pack(anchor='w', pady=(0, 4))
        ent_old = ttk.Entry(c_frame, font=(UI_FONT, 10), show="*", width=40)
        ent_old.pack(fill='x', pady=(0, 15))

        tk.Label(c_frame, text="Mật khẩu mới:", font=(UI_FONT, 9, 'bold')).pack(anchor='w', pady=(0, 4))
        ent_new = ttk.Entry(c_frame, font=(UI_FONT, 10), show="*", width=40)
        ent_new.pack(fill='x', pady=(0, 15))

        tk.Label(c_frame, text="Nhập lại mật khẩu mới:", font=(UI_FONT, 9, 'bold')).pack(anchor='w', pady=(0, 4))
        ent_confirm = ttk.Entry(c_frame, font=(UI_FONT, 10), show="*", width=40)
        ent_confirm.pack(fill='x', pady=(0, 25))

        def submit():
            old = ent_old.get().strip()
            new = ent_new.get().strip()
            conf = ent_confirm.get().strip()
            if not old or not new or not conf:
                messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập đủ các trường!", parent=pwd_win)
                return
            if new != conf:
                messagebox.showerror("Lỗi", "Mật khẩu mới không khớp!", parent=pwd_win)
                return
            
            try:
                resp = requests.post(f"{self.API_BASE_URL}/api/change_password", json={
                    "username": self.current_username,
                    "old_key": old,
                    "new_key": new
                }, timeout=6)
                data = resp.json()
                if data.get("success"):
                    try:
                        clear_credentials()
                    except OSError as exc:
                        messagebox.showwarning('Mật khẩu đã đổi',
                                               f'Không thể xóa mật khẩu cũ đã lưu: {exc}', parent=pwd_win)
                    messagebox.showinfo("Thành công", "Đổi mật khẩu thành công! Vui lòng đăng nhập lại.", parent=pwd_win)
                    pwd_win.destroy()
                    self.logout(force=True)
                else:
                    messagebox.showerror("Thất bại", data.get("message", "Sai mật khẩu hiện tại!"), parent=pwd_win)
            except Exception as e:
                messagebox.showerror("Lỗi mạng", str(e), parent=pwd_win)

        btn_box = tk.Frame(c_frame)
        btn_box.pack(fill='x')
        ttk.Button(btn_box, text="Xác nhận", style='Accent.TButton', command=submit).pack(side='left', expand=True, fill='x', padx=(0, 5))
        ttk.Button(btn_box, text="Hủy", command=pwd_win.destroy).pack(side='right', expand=True, fill='x', padx=(5, 0))

    def _update_file_identity(self):
        name = self.vars['name'].get().strip() if 'name' in self.vars else ''
        if self.path:
            filename = os.path.basename(self.path)
            self.title(f'SoilFirm Pro 2026.11 · {filename}')
        else:
            caption = name or 'Dự án mới'
            self.title(f'SoilFirm Pro 2026.11 · {caption}')

    def show_import_guide(self):
        messagebox.showinfo('Hướng dẫn import Data',
            '1. Bấm Lưu file mẫu Data và lưu một bản sao để nhập số liệu.\n'
            '2. Giữ tên sheet THSH, CTDY và eCV-P; giữ các cột và tiêu đề mẫu.\n'
            '3. Ô xanh dương là dữ liệu đầu vào; ô vàng là kết quả xuất.\n'
            '4. THSH: mỗi phân đoạn có STT dạng số ở cột A; bỏ qua hàng chữ/ô gộp.\n'
            '5. CTDY: mã lớp phải khớp mã lớp trên THSH; nhập đúng đơn vị ghi trên mẫu.\n'
            '6. eCV-P: nhập cấp áp lực trên tiêu đề và giá trị e/Cv theo từng lớp; cấp áp lực trống bị bỏ qua.\n'
            '7. CP là vải, CQ là lưới; cường độ đọc từ tiêu đề. CR/CS là rộng/cao bệ phản áp.\n'
            '8. Bấm Import THSH/CTDY, chọn STT và Nạp đoạn hoặc Tính hàng loạt.\n'
            '9. Mục 9 có bảng Data xuất để đối chiếu. Hồ sơ hàng loạt gồm một Excel, một JSON TXL/SXL và một PDF ghép.',
            parent=self)

    def save_import_template(self):
        try:
            import shutil
            from pathlib import Path
            roots = [Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)),
                     Path(sys.executable).resolve().parent, Path(__file__).resolve().parent]
            source = next((root / 'Data_Import_Mau.xlsx' for root in roots
                           if (root / 'Data_Import_Mau.xlsx').is_file()), None)
            if source is None:
                raise ValueError('Không tìm thấy Data_Import_Mau.xlsx trong bộ cài.')
            target = filedialog.asksaveasfilename(parent=self, title='Lưu file mẫu import Data',
                initialfile='Data_Import_Mau.xlsx', defaultextension='.xlsx', filetypes=[('Excel', '*.xlsx')])
            if target:
                if Path(target).resolve() != source.resolve():
                    shutil.copy2(source, target)
                self.show_import_guide()
        except Exception as exc:
            messagebox.showerror('File mẫu import', str(exc), parent=self)

    def open_section_excel(self):
        if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
            self._ai_analysis_workspace.read_data()
            return
        path = filedialog.askopenfilename(parent=self, title='Chọn bảng THSH / CTDY',
                                          filetypes=[('Excel', '*.xlsx')])
        if not path:
            return
        try:
            from section_excel import list_sections
            sections = list_sections(path)
            if not sections:
                raise ValueError('THSH chưa có STT phân đoạn ở cột A.')
            self._section_excel_path = path
            self.excel_section_combo.configure(values=tuple(str(i) for i in sorted(sections)))
            self.excel_section_no.set(str(min(sections)))
            self.excel_section_notice.set(f'{os.path.basename(path)}: {len(sections)} phân đoạn.')
        except Exception as exc:
            messagebox.showerror('Import bảng tính', str(exc), parent=self)

    def is_trial(self):
        return getattr(self, 'current_user_role', 'user') != 'admin' and getattr(self, 'current_user_tier', 'trial') == 'trial'

    def require_full_license(self):
        if not self.is_trial():
            return True
        messagebox.showwarning('Khóa tính năng (Trial)',
                               'Trial chỉ cho phép tính thông thường ở mục 4 và 5. Tính năng này cần bản đầy đủ.', parent=self)
        return False

    def open_batch_calculation(self):
        if not self.require_full_license():
            return
        if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
            if not self.calculation_settings()['after']:
                self.batch_before_view.calculate(False, getattr(self, '_summary_selected_numbers', [])); return
            numbers = (sorted({int(i.split(':')[0]) for i in self.batch_design_view.tree.selection()})
                       if self.current_step == 16 else getattr(self, '_summary_selected_numbers', []))
            numbers = list(numbers)
            self._ai_analysis_workspace.edit_settings(on_save=lambda: self._summary_run_manual(numbers))
            return
        from batch_view import show_batch_dialog
        show_batch_dialog(self,ai_mode=False)

    def set_ai_processing(self, active, message=''):
        self._ai_processing_active=active
        self._ai_processing_message=message
        bar=getattr(self,'ai_processing_bar',None)
        label=getattr(self,'ai_processing_label',None)
        if bar is not None and bar.winfo_exists():
            if active:bar.start()
            else:bar.stop()
        if label is not None and label.winfo_exists():label.configure(text=message)

    def open_ai_batch_calculation(self):
        if not self.require_full_license():return
        if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
            self._summary_run_ai(getattr(self, '_summary_selected_numbers', []))
            return
        from chat_dialog import show_ai_dialog
        window = show_ai_dialog(self)
        window.after_idle(window._soilfirm_ai_batch)

    def open_ai_excel_sequence(self):
        if not self.require_full_license():return
        if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
            self._ai_analysis_workspace.read_data(show_holes=True)
            return
        from chat_dialog import show_ai_dialog
        window=show_ai_dialog(self)
        window.after_idle(window._soilfirm_ai_sections)

    def load_excel_section(self):
        if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
            if self.current_step in (4,5,6):
                self.route_section_selector.number.set(self.excel_section_no.get())
                self.route_section_selector.load()
            else:
                self._ai_analysis_workspace.read_data(path=self._ai_analysis_workspace.state.get('source'))
            return
        try:
            if not self._section_excel_path:
                raise ValueError('Hãy import bảng THSH / CTDY trước.')
            number = int(self.excel_section_no.get())
            from section_excel import import_section
            project, length = import_section(self._section_excel_path, number, self.project)
            self.project = project
            self._active_section_no = number
            self._active_section_length = length
            self._choice_group_results.clear()
            self._cdm_reports.clear()
            self.populate()
            self.excel_section_notice.set(
                f'STT {number}: {project.station_from} – {project.station_to}, '
                f'MCN {project.station}, {len(project.soils)} lớp đất, L={length:.2f} m.')
            self.draw_live_diagram()
        except Exception as exc:
            messagebox.showerror('Nạp phân đoạn', str(exc), parent=self)

    def _sync_workspace_split(self, event=None):
        """Keep the input pane visible without repeatedly moving the sash."""
        if getattr(self, '_syncing_workspace_split', False):
            return
        panes = tuple(str(pane) for pane in self.paned.panes())
        left, right = str(self.left_container), str(self.right_container)
        diagram_step = getattr(self, 'current_step', None) in (1,2,3,4,5,6)
        if diagram_step and not getattr(self, '_diagram_hidden', False) and right not in panes:
            self._syncing_workspace_split = True
            try:
                self.paned.add(self.right_container, weight=4)
            finally:
                self._syncing_workspace_split = False
            self.after_idle(self._refresh_visible_section)
            panes = tuple(str(pane) for pane in self.paned.panes())
        if panes != (left, right):
            return
        width = self.paned.winfo_width()
        if width < 20:
            return
        sidebar = max(self.sidebar.winfo_width(), self.sidebar.winfo_reqwidth()) + 10
        target = min(width - 1, max(1, sidebar + (width - sidebar - 4) // 2))
        if abs(self.paned.sashpos(0) - target) <= 2:
            return
        self._syncing_workspace_split = True
        try:
            self.paned.sashpos(0, target)
        finally:
            self._syncing_workspace_split = False

    def _refresh_visible_section(self):
        self._section_refresh_job = None
        if self.current_step not in (1,2,3,4,5,6):
            return
        if getattr(self, '_diagram_hidden', False):return
        panes = tuple(str(pane) for pane in self.paned.panes())
        if str(self.right_container) not in panes:
            self.right_container.configure(width=520)
            self.paned.add(self.right_container, weight=4)
        if not self.box_geom.winfo_manager():
            self.box_geom.pack(fill='both', expand=True, pady=4)
        # The previous full-width page leaves its allocated pane size behind.
        # Finish layout before resetting the sash and drawing into the canvas.
        self.paned.update_idletasks()
        self._sync_workspace_split()
        self.paned.update_idletasks()
        self.draw_live_diagram()

    def _on_window_resize(self, event):
        if event.widget is self:
            width = self.winfo_width()
            if width == getattr(self, '_last_root_width', None):
                return
            self._last_root_width = width
            self.after_idle(self._sync_workspace_split)

    def cdm_calculation_project(self):
        return cdm_design_project(self.project, self.cdm_scope_var.get())

    def collect_cdm_inputs(self):
        if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
            self.route_section_selector.require_section()
        """Đồng bộ hình học mở rộng mà không ghi đè phương án xử lý nền chính."""
        if self.cdm_scope_var.get() != 'Nền mở rộng':
            self.collect()
            return
        keys = ('main_treatment', 'main_replacement_depth', 'main_bamboo_depth',
                'main_cajuput_depth', 'main_cdm_depth', 'main_age_days',
                'main_observed_residual_cm')
        existing = {key: getattr(self.project, key) for key in keys}
        try:
            self.collect()
        finally:
            for key, value in existing.items():
                setattr(self.project, key, value)

    def sync_ai_calculation_inputs(self):
        """Capture visible CDM/ALiCC fields, including values restored without traces."""
        self.collect_cdm_inputs()
        if hasattr(self, 'refresh_cdm_inputs'):
            self.refresh_cdm_inputs()
        for name in ('_capture_cdm_state', '_capture_alicc_state'):
            callback = getattr(self, name, None)
            if callback is not None:
                callback()

    def _cdm_diagram_data(self):
        scope = self.cdm_scope_var.get()
        method = self._cdm_active_method
        calculated = self._cdm_reports.get(method)
        if calculated and calculated.get('scope') == scope:
            return calculated, method
        if method == 'standard':
            states = self.project.cdm_inputs or {}
            saved = states.get(scope, {}) if 'cdm' not in states else (
                states if scope == 'Nền đường' else {})
            values = saved.get('cdm', {})
            defaults = {'D': 0.8, 's': 1.4, 'Lc': 5.0}
        else:
            states = self.project.alicc_inputs or {}
            values = states.get(scope, {}) if 'D' not in states else (
                states if scope == 'Nền đường' else {})
            defaults = {'D': 0.8, 's': 1.3, 'Lc': 9.0}
        params = {key: number_or_zero(values.get(key, default)) or default
                  for key, default in defaults.items()}
        return {'params': params, 'scope': scope}, method

    def _build_treatment_scope_selector(self, parent):
        bar = ttk.Frame(parent, padding=(10, 8))
        bar.pack(fill='x')
        controls = ttk.Frame(bar)
        controls.pack(fill='x')
        ttk.Label(controls, text='Phạm vi xử lý:').pack(side='left', padx=(0, 8))
        scope_names = {'Nền đường': ('Nền đường chính', 'Main road embankment'),
                       'Nền mở rộng': ('Nền đường mở rộng', 'Widened road embankment')}
        shown_scope = tk.StringVar(master=self)
        selector = ttk.Combobox(controls, textvariable=shown_scope,
                               state='readonly', width=24)
        selector._sf_scope_display = shown_scope
        def scope_labels():
            language = 1 if self.ui_language.get() == 'English' else 0
            return {key: labels[language] for key, labels in scope_names.items()}
        def refresh_scope(*_):
            labels = scope_labels()
            selector.configure(values=tuple(labels.values()))
            shown_scope.set(labels.get(self.cdm_scope_var.get(), self.cdm_scope_var.get()))
        def select_scope(_event=None):
            labels = scope_labels()
            value = next((key for key, label in labels.items() if label == shown_scope.get()), None)
            if value is not None:
                self.cdm_scope_var.set(value)
                self._cdm_scope_changed(_event)
                refresh_scope()
        selector._sf_refresh_scope_display = refresh_scope
        self.cdm_scope_var.trace_add('write', refresh_scope)
        refresh_scope()
        selector.pack(side='left')
        selector.bind('<<ComboboxSelected>>', select_scope)
        note = ttk.Label(bar,
            text='Lưu ý: Đối với nền mở rộng, bấm vào đây để thay đổi phạm vi xử lý.',
            foreground='#075985', cursor='hand2', wraplength=760)
        note.pack(anchor='w', pady=(5, 0))
        def open_selector(_event=None):
            selector.focus_set()
            self.after_idle(lambda: selector.event_generate('<Button-1>'))
        note.bind('<Button-1>', open_selector)
        return selector

    def _cdm_scope_changed(self, _event=None):
        scope = self.cdm_scope_var.get()
        if scope == 'Nền mở rộng' and (not self.has_expansion.get() or
                                       number_or_zero(self.vars['expansion_width'].get()) <= 0):
            messagebox.showwarning('Phạm vi xử lý',
                                   'Bật và khai báo nền mở rộng trước khi chọn phạm vi này.',
                                   parent=self)
            self.cdm_scope_var.set('Nền đường')
            return
        if scope == 'Nền mở rộng':
            try:
                self.collect_cdm_inputs()
            except ValueError as exc:
                messagebox.showerror('Phạm vi xử lý', str(exc), parent=self)
                self.cdm_scope_var.set('Nền đường')
                return
        self.project.cdm_scope = scope
        if hasattr(self, 'cb_post_pos'):
            positions = [name for name, _ in axes(self.project)]
            selected = self.post_pos_var.get()
            preferred = [name for name in positions
                         if ('nền mở rộng' in name.lower()) == (scope == 'Nền mở rộng')]
            if preferred and selected not in preferred:
                self.post_pos_var.set(preferred[0])
                self.invalidate_assessment()
        self._cdm_reports.clear()
        self.clear_cdm_results()
        self.refresh_cdm_inputs()

    def open_module_ai(self):
        if self.current_step==11:
            self._ai_analysis_workspace.read_source('boreholes');return
        if self.current_step==12:
            self._ai_analysis_workspace.read_data();return
        if self.current_step==13:
            self.switch_step(13);return
        if self.current_step==10:
            self.geology_statistics_view.ai_support(True)
            return
        if self.current_step == 7:
            self.switch_step(7)
            return
        from chat_dialog import show_ai_dialog
        window=show_ai_dialog(self)
        questions={10:'Phân tích số liệu thống kê địa chất của lớp đang chọn, thông số thiếu và cách chọn giá trị dùng tính toán.',0:'Hướng dẫn dùng AI hỗ trợ dự án này; chỉ ra dữ liệu cần nhập.',1:'Phân tích hình học nền đường hiện tại và dữ liệu cần kiểm toán.',2:'Phân tích địa chất và chỉ tiêu đất yếu hiện tại theo căn cứ trong phần mềm.',3:'Tính toán kiểm toán trước xử lý với số liệu hiện tại.',4:'Tính tối ưu phương án cơ học với số liệu hiện tại.',5:'Tính tối ưu phương án cố kết và thoát nước với số liệu hiện tại.',6:'Tính tối ưu CDM hoặc ALiCC với các thông số đã khai báo.',7:'Hướng dẫn tính hàng loạt và hỏi tôi danh sách STT cùng thứ tự ưu tiên.',8:'Phân tích kết quả kiểm toán tổng hợp hiện tại.',9:'Tính khối lượng phương án với số liệu hiện tại.'}
        window._soilfirm_ai_draft.set(questions.get(self.current_step,'Phân tích mô đun hiện tại.'))
        window.lift()
        if self.current_step in (4,5,6):
            window._soilfirm_ai_scope.set('Mô đun đang mở')

    @staticmethod
    def _calculation_preferences_path():
        from pathlib import Path
        return Path(os.environ.get('APPDATA') or Path.home()) / 'SoilFirm' / 'calculation_settings.json'

    def _load_calculation_preferences(self):
        try:
            data = json.loads(self._calculation_preferences_path().read_text(encoding='utf-8'))
            if not isinstance(data, dict): return {}
            result = {}
            if type(data.get('web_search')) is bool:
                result['web_search'] = data['web_search']
            if data.get('method') in ('Cc/Cs/Pc', 'e–logP', 'Mv–logP'):
                result['method'] = data['method']
            if data.get('mode') in ('TÍNH MỘT ĐOẠN', 'TÍNH TOÀN TUYẾN'):
                result['mode'] = data['mode']
            # Chuyển nhãn cũ khi mở cấu hình, giữ đúng loại kết nối.
            data['provider'] = {'AI (miễn phí)':'deepseek-r1:8b',
                                'DeepSeek (miễn phí)':'deepseek-r1:8b',
                                'Qwen (miễn phí)':'qwen3:8b',
                                'DeepSeek (Miễn phí)':'DeepSeek (g4f)'}.get(data.get('provider'),data.get('provider'))
            if data.get('provider') in ('Cloudflare AI', 'Gemini', 'DeepSeek', 'DeepSeek (g4f)','deepseek-r1:8b', 'qwen3:8b', 'qwen3:4b-q4_K_M', 'qwen3:4b-q8_0', 'Groq',
                                        'Grok (xAI)', 'ChatGPT', 'NVIDIA AI', 'Kimi AI'):
                result['provider'] = data['provider']
            stages = data.get('stages')
            keys = ('before', 'after', 'mechanical', 'drainage', 'cdm')
            if (isinstance(stages, dict) and all(type(stages.get(k)) is bool for k in keys)
                and (stages['before'] or stages['after'])
                and (not stages['after'] or any(stages[k] for k in keys[2:]))):
                result['stages'] = {k: stages[k] for k in keys}
                for key in ('summary', 'quantities', 'data_processed'):
                    result['stages'][key] = stages.get(key, False) if type(stages.get(key, False)) is bool else False
            return result
        except (OSError, ValueError):
            return {}

    def _save_calculation_preferences(self):
        path = self._calculation_preferences_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {'version': 1, 'stages': self._stored_calculation_settings(),
                'method': self.vars['method'].get(), 'mode': self.design_mode.get(),
                'provider': self.ai_provider_var.get(),
                'web_search': self.ai_web_search_var.get()}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                    dir=path.parent, prefix='calculation_settings_', suffix='.tmp', delete=False) as stream:
                temporary = stream.name
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
            self._calculation_preferences = data
        finally:
            if temporary is not None and os.path.exists(temporary): os.unlink(temporary)

    def _stored_calculation_settings(self):
        defaults = {'before': True, 'after': True,
                    'mechanical': True, 'drainage': False, 'cdm': True,
                    'summary': False, 'quantities': False, 'data_processed': False}
        defaults.update(getattr(self, '_calculation_settings', {}))
        return defaults

    def calculation_settings(self):
        config = self._stored_calculation_settings()
        if self.design_mode.get() == 'TÍNH MỘT ĐOẠN':
            config.update(summary=False, quantities=False)
        return config

    def calculation_options(self):
        from batch_calculation import OPTIONS
        config = self.calculation_settings()
        if not config['after']:
            return ()
        return tuple(name for name in OPTIONS if config[
            'cdm' if name.startswith('CDM') else
            'mechanical' if name in OPTIONS[:3] or name == 'Chờ lún' else 'drainage'])

    def _configured_navigation_groups(self):
        from design_workflow import navigation_groups
        config = self.calculation_settings()
        hidden = set()
        if not config['before']: hidden.update((3, 15))
        if not config['after']: hidden.update((4, 5, 6, 16))
        else:
            for key, step in (('mechanical', 4), ('drainage', 5), ('cdm', 6)):
                if not config[key]: hidden.add(step)
        if not config['summary']: hidden.add(16)
        if not (config['quantities'] and config['after']): hidden.add(9)
        groups = list(navigation_groups(self.design_mode.get()))
        if self.design_mode.get() == 'TÍNH MỘT ĐOẠN':
            hidden.update((16, 18, 9))
            if config['data_processed']: hidden.add(14)
            groups = [(title, ((2,) if config['data_processed'] else (2, 10, 14)) if steps == (2,) else steps)
                      for title, steps in groups]
        elif config['data_processed']:
            hidden.update((10, 14))
        return tuple((title, tuple(step for step in steps if step not in hidden))
                     for title, steps in groups
                     if any(step not in hidden for step in steps))

    def _apply_calculation_visibility(self):
        workspace = getattr(self, '_ai_analysis_workspace', None)
        if workspace is None: return
        chosen = self.calculation_settings()
        for page, enabled in ((workspace.before_page, chosen['before']),
                              (workspace.option_page, chosen['after'])):
            if enabled: workspace.result_tabs.tab(page, state='normal')
            else: workspace.result_tabs.hide(page)
        workspace.sync_input_controls()

    def _sync_geology_session(self, target=None, refresh=True):
        from ai_analysis_data import new_session
        workspace = getattr(self, '_ai_analysis_workspace', None)
        if workspace is None: return
        target = target or self.design_mode.get()
        sessions = getattr(self, '_geology_sessions', {})
        previous = getattr(self, '_geology_session_mode', None)
        if previous is not None:
            sessions[previous] = workspace.state
        state = sessions.get(target)
        if state is None:
            state = new_session(self.project if target == 'TÍNH MỘT ĐOẠN' else Project())
            sessions[target] = state
        self._geology_sessions = sessions
        self._geology_session_mode = target
        self._ai_analysis_state = workspace.state = state
        if target == 'TÍNH MỘT ĐOẠN':
            state['template'] = self.project
            if not state['materials']:
                from dataclasses import asdict
                from ai_analysis_data import SOIL_KEYS
                for soil in self.project.soils:
                    if not soil.name or soil.gamma <= 0: continue
                    if any(m['code'].casefold()==soil.name.casefold() for m in state['materials']): continue
                    state['materials'].append({'code':soil.name, 'values':{k:v for k,v in asdict(soil).items() if k in SOIL_KEYS},
                        'source':'Địa tầng đang khai báo', 'description':'', 'sample_count':0,
                        'cv_constant':soil.cv_constant, 'phi_cu_effective':soil.phi_cu_effective})
        if refresh:
            workspace.reload_state()
            self.geology_statistics_view.refresh()
            workspace.sync_input_controls()

    def open_calculation_settings(self):
        existing = getattr(self, '_calculation_settings_window', None)
        if existing is not None and existing.winfo_exists():
            existing.lift(); return
        window = tk.Toplevel(self)
        self._calculation_settings_window = window
        window.title('Thiết lập tính toán')
        window.transient(self); window.resizable(True, True)
        window._popup_fit_scheduled = True
        scroll = ScrollableFrame(window); scroll.pack(fill='both', expand=True)
        body = ttk.Frame(scroll.scrollable_frame, padding=16); body.pack(fill='both', expand=True)
        method_labels = {'Theo Cc, Cs, Pc': 'Cc/Cs/Pc',
                         'Theo đường cong e–logP': 'e–logP',
                         'Theo đường cong mv–logP': 'Mv–logP'}
        method = tk.StringVar(window, value=next((label for label, value in method_labels.items()
            if value == self.vars['method'].get()), 'Theo Cc, Cs, Pc'))
        box = ttk.LabelFrame(body, text='1. Phương pháp tính lún', padding=10)
        box.pack(fill='x', pady=5)
        ttk.Combobox(box, textvariable=method, values=tuple(method_labels),
                     state='readonly', width=38).pack(fill='x')
        config = self._stored_calculation_settings()
        flags = {key: tk.BooleanVar(window, value=value) for key, value in config.items()}
        box = ttk.LabelFrame(body, text='2. Xử lý số liệu', padding=10)
        box.pack(fill='x', pady=5)
        for label, value in (('Chưa xử lý', False), ('Đã xử lý', True)):
            ttk.Radiobutton(box, text=label, variable=flags['data_processed'], value=value).pack(anchor='w')
        box = ttk.LabelFrame(body, text='3. Giai đoạn tính toán', padding=10)
        box.pack(fill='x', pady=5)
        ttk.Checkbutton(box, text='Trước xử lý nền', variable=flags['before']).pack(anchor='w')
        groups = ttk.Frame(box)
        def show_groups():
            if flags['after'].get(): groups.pack(fill='x', padx=(22, 0), pady=(4, 0))
            else: groups.pack_forget()
        ttk.Checkbutton(box, text='Sau xử lý nền', variable=flags['after'],
                        command=show_groups).pack(anchor='w')
        for key, label in (('mechanical', 'Cơ học'), ('drainage', 'Cố kết và thoát nước'),
                           ('cdm', 'Trộn sâu (CDM)')):
            ttk.Checkbutton(groups, text=label, variable=flags[key]).pack(anchor='w')
        show_groups()
        box = ttk.LabelFrame(body, text='4. Phạm vi tính', padding=10)
        box.pack(fill='x', pady=5)
        mode = tk.StringVar(window, value=self.design_mode.get())
        for label, value in (('Một đoạn', 'TÍNH MỘT ĐOẠN'), ('Nhiều đoạn', 'TÍNH TOÀN TUYẾN')):
            ttk.Radiobutton(box, text=label, variable=mode, value=value).pack(anchor='w')
        result_box = ttk.LabelFrame(body, text='5. Tổng hợp kết quả', padding=10)
        box = result_box
        ttk.Checkbutton(box, text='Hiển thị bảng tổng hợp', variable=flags['summary']).pack(anchor='w')
        quantity_check = ttk.Checkbutton(box, text='Tính khối lượng xử lý', variable=flags['quantities'])
        quantity_check.pack(anchor='w')
        def sync_quantity_state(*_):
            quantity_check.configure(state='normal' if flags['after'].get() else 'disabled')
        flags['after'].trace_add('write', sync_quantity_state)
        sync_quantity_state()
        ai_box = ttk.LabelFrame(body, text='6. Chọn AI hỗ trợ', padding=10)
        box = ai_box
        box.pack(fill='x', pady=5)
        provider = tk.StringVar(window, value=self.ai_provider_var.get())
        ttk.Combobox(box, textvariable=provider, values=self.header_ai_selector['values'],
                     state='readonly', width=38).pack(fill='x')
        web_search = tk.BooleanVar(window, value=self.ai_web_search_var.get())
        ttk.Checkbutton(box, text='Mặc định tra cứu mạng khi hỏi AI (DuckDuckGo miễn phí)',
                        variable=web_search).pack(anchor='w', pady=(8, 0))
        def sync_result_controls(*_):
            route = mode.get() == 'TÍNH TOÀN TUYẾN'
            if route: result_box.pack(fill='x', pady=5, before=ai_box)
            else: result_box.pack_forget()
            ai_box.configure(text=('6.' if route else '5.') + ' Chọn AI hỗ trợ')
        mode.trace_add('write', sync_result_controls)
        sync_result_controls()
        notice = tk.StringVar(window)
        ttk.Label(body, textvariable=notice, foreground='#B91C1C', wraplength=390).pack(fill='x')
        def apply():
            workspace = getattr(self, '_ai_analysis_workspace', None)
            if getattr(self, '_single_batch_busy', False) or (workspace is not None and workspace.busy):
                notice.set('Chờ tác vụ hiện tại hoàn thành trước khi đổi thiết lập.'); return
            chosen = {key: var.get() for key, var in flags.items()}
            if not chosen['before'] and not chosen['after']:
                notice.set('Chọn ít nhất một giai đoạn tính toán.'); return
            if chosen['after'] and not any(chosen[key] for key in ('mechanical', 'drainage', 'cdm')):
                notice.set('Chọn ít nhất một nhóm giải pháp sau xử lý.'); return
            previous_step = self.current_step
            inputs_changed = (self.design_mode.get() != mode.get()
                              or self.calculation_settings()['data_processed'] != chosen['data_processed'])
            if self.design_mode.get() != mode.get():
                self.design_mode.set(mode.get()); self.change_design_mode()
                if self.design_mode.get() != mode.get(): return
                previous_step = self.current_step
            self._calculation_settings = chosen
            self._sync_geology_session(refresh=False)
            self.vars['method'].set(method_labels[method.get()])
            self.project.method = method_labels[method.get()]
            self.ai_provider_var.set(provider.get())
            self.ai_web_search_var.set(web_search.get())
            self._workspace_tab_signature = None
            self._rebuild_workflow_navigation()
            visible = [step for _, steps in self.navigation_groups for step in steps]
            self._visible_group = None
            if inputs_changed:
                target_step = 2 if self.design_mode.get() == 'TÍNH MỘT ĐOẠN' else 11
            else:
                target_step = previous_step if previous_step in visible else visible[0]
            self.switch_step(target_step)
            self._sync_geology_session()
            summary = getattr(self, 'single_treatment_summary_view', None)
            if summary is not None and hasattr(summary, 'summary_view'): summary.refresh()
            self._apply_calculation_visibility()
            if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
                self._ai_analysis_workspace.state['template'].method = method_labels[method.get()]
            try:
                self._save_calculation_preferences()
            except OSError:
                notice.set('Đã áp dụng, nhưng chưa lưu được cấu hình cho lần khởi động sau. Bấm Áp dụng để thử lại.'); return
            self.status_text.set('Đã áp dụng và lưu thiết lập tính toán')
            window.destroy()
        bar = ttk.Frame(body); bar.pack(fill='x', pady=(8, 0))
        ttk.Button(bar, text='Áp dụng', command=apply, style='Accent.TButton').pack(side='right')
        ttk.Button(bar, text='Hủy', command=window.destroy).pack(side='right', padx=8)
        window.update_idletasks()
        width = min(max(480, body.winfo_reqwidth()+24), max(1, window.winfo_screenwidth()-40))
        height = min(body.winfo_reqheight()+16, max(1, window.winfo_screenheight()-90))
        x=max(0, (window.winfo_screenwidth()-width)//2)
        y=max(0, (window.winfo_screenheight()-height)//2)
        window.geometry(f'{width}x{height}+{x}+{y}'); window.grab_set()

    def _update_stepper(self, active_group: int):
        """Cập nhật chỉ thị tiến trình: ● đang ở, ✓ đã qua, ○ chưa tới."""
        n = len(self.nav_group_buttons)
        if n == 0:
            return
        self._visited_groups.add(active_group)
        for i, btn in enumerate(self.nav_group_buttons):
            if i == active_group:
                indicator = '●'
                fg_color = 'white'
                bg_color = COLORS['nav_active']
            elif i in self._visited_groups:
                indicator = '✓'
                fg_color = '#7DD3FC'
                bg_color = COLORS['nav']
            else:
                indicator = '○'
                fg_color = '#60819A'
                bg_color = COLORS['nav']
            # Bỏ số thứ tự cũ, thêm indicator
            raw = btn.cget('text')
            # text có dạng "N. Tên nhóm" hoặc đã có indicator ở đầu
            import re as _re
            clean = _re.sub(r'^[●✓○]\s*', '', raw)
            btn.configure(text=f'{indicator} {clean}',
                          bg=bg_color, fg=fg_color,
                          activebackground=COLORS['nav_active'] if i == active_group else COLORS['nav_hover'],
                          activeforeground='white')
        # Cập nhật thanh tiến trình
        canvas = getattr(self, '_progress_bar_canvas', None)
        if canvas and canvas.winfo_exists():
            total_w = canvas.winfo_width() or (int(self.sidebar.cget('width')) - 16)
            fill_w = max(4, int(total_w * (active_group + 1) / n))
            canvas.coords(self._progress_bar_fill, 0, 0, fill_w, 4)
            canvas.coords(self._progress_bar_track, 0, 0, total_w, 4)

    def _rebuild_workflow_navigation(self):
        from design_workflow import navigation_groups, display_group_title
        self.navigation_groups = self._configured_navigation_groups()
        self._group_last_step = {i: steps[0] for i, (_, steps) in enumerate(self.navigation_groups)}
        self._visited_groups = set()  # reset khi rebuild (đổi chế độ hoặc nạp dự án mới)
        for child in self.nav_groups_host.winfo_children(): child.destroy()
        self.nav_group_buttons = []
        for group, (title, steps) in enumerate(self.navigation_groups):
            button = tk.Button(self.nav_groups_host, text=f'{group+1}. {display_group_title(title)}',
                font=(UI_FONT, 10, 'bold'), anchor='w', justify='left',
                wraplength=int(self.sidebar.cget('width'))-40, padx=8, relief='flat', bd=0, cursor='hand2',
                command=lambda g=group: self.switch_step(self._group_last_step[g]))
            button.pack(fill='x', padx=5, pady=2, ipady=7)
            self.nav_group_buttons.append(button)
        self.step_buttons = [next((self.nav_group_buttons[g] for g, (_, steps)
            in enumerate(self.navigation_groups) if i in steps), None) for i in range(len(self.step_frames))]

    def _sync_project_metadata(self, *_):
        if getattr(self, '_loading_project', False) or getattr(self, '_loading_workflow', False):
            return
        workspace = getattr(self, '_ai_analysis_workspace', None)
        template = workspace.state.get('template') if workspace is not None else None
        for key in ('name', 'design_stage', 'work_item'):
            value = self.vars[key].get()
            setattr(self.project, key, value)
            if template is not None and self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
                setattr(template, key, value)

    def change_design_mode(self, event=None):
        from design_workflow import capture_workspace, restore_workspace
        target = self.design_mode.get()
        previous = getattr(self, '_workflow_mode', 'TÍNH MỘT ĐOẠN')
        workspace = getattr(self, '_ai_analysis_workspace', None)
        if target != previous and getattr(self, '_single_batch_busy', False):
            self.design_mode.set(previous)
            messagebox.showinfo('Đang tính toán', 'Chờ tính toán xong trước khi đổi luồng tính.', parent=self)
            return
        if target != previous and workspace is not None and workspace.busy:
            self.design_mode.set(previous)
            messagebox.showinfo('Đang xử lý', 'Dừng hoặc chờ tác vụ hiện tại xong trước khi đổi luồng tính.', parent=self)
            return
        if target != previous:
            self._loading_workflow = True
            try:
                self.collect()
                if previous == 'TÍNH MỘT ĐOẠN':
                    self._single_workspace = capture_workspace(self)
                else:
                    self.route_section_selector.stash()
                    self._route_workspace = capture_workspace(self)
                self._sync_geology_session(target, refresh=False)
                self.route_section_selector.active = None
                self.route_section_selector.group = None
                self.route_section_selector._visible_group = None
                self.route_section_selector.base = None
                saved = getattr(self, '_single_workspace' if target == 'TÍNH MỘT ĐOẠN' else '_route_workspace', None)
                if saved:
                    restore_workspace(self, saved)
                else:
                    self.project = deepcopy(workspace.state['template'])
                    self.populate()
                    self._step_result_cache = {}
                    self._choice_group_results = {}
                    self._cdm_reports = {}
                    self._section_excel_path = workspace.state.get('source') or None
                    self._active_section_no = None
                    self._active_section_length = 0
                    self.last_rows = []; self.last_result_view = None; self.chart_data = {}
            finally:
                self._loading_workflow = False
        self._workflow_mode = target
        self._sync_geology_session(target)
        self._rebuild_workflow_navigation()
        self.switch_step(12 if target == 'TÍNH TOÀN TUYẾN' else 0)
        self.status_text.set(target + ' · Đã nạp dữ liệu riêng của luồng tính')

    def toggle_diagram_panel(self):
        if self.current_step in (0,7,8,9,10,11,12,13,14,15,16,17,18):return
        self._diagram_hidden=not getattr(self,'_diagram_hidden',False)
        right=str(self.right_container)
        if self._diagram_hidden and right in self.paned.panes():self.paned.forget(self.right_container)
        elif not self._diagram_hidden and right not in self.paned.panes():self.paned.add(self.right_container,weight=4)

    def switch_step(self, index: int):
        if self.design_mode.get() == 'TÍNH TOÀN TUYẾN' and index in (8, 13):
            index = 9
        visible = {step for _, steps in self.navigation_groups for step in steps}
        if index not in visible and index in (3, 4, 5, 6, 15, 16):
            index = next((step for _, steps in self.navigation_groups for step in steps
                          if step in (4, 5, 6, 18, 9)), next(iter(self.navigation_groups[0][1])))
        if index not in visible:
            if index in (10,14) and self.calculation_settings()['data_processed'] and self.design_mode.get()=='TÍNH TOÀN TUYẾN':
                index=11
            elif self.design_mode.get() == 'TÍNH MỘT ĐOẠN' and index == 14:
                index = 2
            elif self.design_mode.get() == 'TÍNH MỘT ĐOẠN' and index in (7,8,9,13,16,17,18):
                index = next((step for _, steps in self.navigation_groups for step in steps
                              if step in (4, 5, 6)), self.navigation_groups[0][1][0])
            elif self.design_mode.get() == 'TÍNH TOÀN TUYẾN' and index == 7:
                index = 16
            elif self.design_mode.get() == 'TÍNH TOÀN TUYẾN' and index in (0,1,2,3):
                index = 12 if index == 0 else 15 if index == 3 else 11
            else:
                messagebox.showinfo('Quy trình thiết kế', 'Chức năng này thuộc chế độ TÍNH TOÀN TUYẾN.', parent=self)
                return
        if (5 <= index <= 9 or index in (13,15,16,17,18)) and not self.require_full_license():
            return

        for button in getattr(self, 'project_batch_buttons', []):
            if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':button.pack(side='left',padx=5)
            else:button.pack_forget()
        previous_step = getattr(self, 'current_step', None)
        self._switching_step = True
        if (self.design_mode.get() == 'TÍNH TOÀN TUYẾN'
                and previous_step in (4,5,6) and previous_step != index):
            self.route_section_selector.leave()
        self.current_step = index
        if index in (4, 5) and hasattr(self, 'treatment_group'):
            if index == 4 and previous_step != 4 and self.treatment_group.get() == 'drainage':
                self._drainage_pause_values = [row[2].get() for row in self.stage_vars]
            self.treatment_group.set('mechanical' if index == 4 else 'drainage')
            if index == 5 and not getattr(self, '_drainage_mode_initialized', False):
                self.treatment_vars['treatment'].set('PVD')
                self._drainage_mode_initialized = True
            if previous_step == 4 and index == 5 and hasattr(self, '_drainage_pause_values'):
                for row, pause in zip(self.stage_vars, self._drainage_pause_values):
                    row[2].set(pause)
            self.update_treatment_visibility()
            if previous_step != index:
                self._cad_settlement_elements = None
                self._cad_metric_values = {}
                self._cad_stage_totals = None
                self._cad_stage_project = None
                self._cad_default_totals = None
                self._cad_default_project = None
                self._cad_default_remaining = None
                self._cad_vacuum_active = 0.0
                self._cad_default_vacuum = 0.0
                self._treated_residual = None
                if hasattr(self, 'post_tree'):
                    self.post_tree.delete(*self.post_tree.get_children())
        if index in (1, 2):
            self.cad_plot_mode.set('Mặt cắt')
        elif index in (4, 5) and getattr(self, '_previous_cad_step', None) != index:
            self.cad_plot_mode.set('Mặt cắt')
        elif index == 3 and getattr(self, '_previous_cad_step', None) != 3:
            self.cad_plot_mode.set('Độ lún')
        self._previous_cad_step = index
        group=next(g for g,(_,steps) in enumerate(self.navigation_groups) if index in steps)
        self._group_last_step[group]=index
        from design_workflow import display_group_title
        original_heading = self.navigation_groups[group][0]
        heading = display_group_title(original_heading)
        if original_heading == 'Địa chất và chỉ tiêu':
            heading += ' (hỗ trợ phân tích số liệu)'
        self.workspace_heading.set(heading)
        self.workspace_subtitle.set(self.step_descriptions[index])
        if index in (3, 4, 5, 6):
            scope = 'natural' if index == 3 else 'cdm' if index == 6 else 'treated'
            self.workspace_pdf_button.configure(
                text='Xuất báo cáo trộn sâu' if index == 6 else 'Xuất báo cáo',
                command=lambda selected_scope=scope: self.export_pdf(selected_scope))
            self.workspace_pdf_button.place_forget()
        else:
            self.workspace_pdf_button.place_forget()
        self.status_text.set(f'{self.design_mode.get()} · Mục {group+1}/{len(self.navigation_groups)} · {self.step_headings[index]}')
        self._update_stepper(group)
        labels={0:'Dữ liệu dự án',1:'Hình học nền đắp',2:'Địa tầng',3:'Kiểm toán lún',4:'Xử lý cơ học',5:'Cố kết và thoát nước',6:'CDM / ALiCC',7:'AI phân tích & chọn phương án',8:'Tổng hợp phương án',9:'Khối lượng xử lý nền',10:'Thống kê số liệu',11:'Khai báo lỗ khoan' if self.calculation_settings()['data_processed'] else 'Địa tầng lỗ khoan',12:'Phân đoạn tính toán',13:'Xuất hồ sơ',14:'Bảng tổng hợp chỉ tiêu',15:'Kiểm toán các phân đoạn',16:'Bảng tổng hợp xử lý',17:'Lựa chọn phương án',18:'Tổng hợp kết quả xử lý'}
        group_steps = tuple(self.navigation_groups[group][1])
        if len(group_steps) > 1:
            if not self.workspace_tab_strip.winfo_manager():
                self.workspace_tab_strip.pack(fill='x', pady=(0,6))
        elif self.workspace_tab_strip.winfo_manager():
            self.workspace_tab_strip.pack_forget()
        if getattr(self, '_workspace_tab_signature', None) != group_steps:
            for child in self.workspace_tabs.winfo_children():
                child.destroy()
            self._workspace_tab_buttons = {}
            for target in group_steps if len(group_steps) > 1 else ():
                button = tk.Button(self.workspace_tabs, text=labels[target],
                    font=(UI_FONT,10), fg='#163047', relief='flat', bd=0,
                    padx=12, pady=7, command=lambda t=target:self.switch_step(t))
                button.pack(side='left',padx=(0,4))
                self._workspace_tab_buttons[target] = button
            self._workspace_tab_signature = group_steps
        for target, button in self._workspace_tab_buttons.items():
            button.configure(bg=COLORS['tab_selected'] if target==index else COLORS['tab_idle'],
                             activebackground=COLORS['tab_hover'], activeforeground=COLORS['control_text'],
                             font=(UI_FONT,10,'bold' if target==index else 'normal'))
        target_frame = self.step_frames[index]
        old_frame = getattr(self, '_visible_step_frame', None)
        if old_frame is not None and old_frame is not target_frame:
            old_frame.pack_forget()
        route_editor = self.design_mode.get() == 'TÍNH TOÀN TUYẾN' and index in (4,5,6)
        if route_editor:
            self.route_section_selector.refresh(index)
            if not self.route_section_selector.winfo_manager():
                opts = {'before': target_frame} if target_frame.winfo_manager() else {}
                self.route_section_selector.pack(fill='x', **opts)
        elif self.route_section_selector.winfo_manager():
            self.route_section_selector.pack_forget()
        if not target_frame.winfo_manager():
            target_frame.pack(fill='both', expand=True)
        self._visible_step_frame = target_frame
        panes = tuple(str(pane) for pane in self.paned.panes())
        right_id = str(self.right_container)
        if not panes or panes[0] != str(self.left_container):
            self.paned.insert(0, self.left_container, weight=6)
        self._diagram_hidden = False
        if index in (0,7,8,9,10,11,12,13,14,15,16,17,18):
            if right_id in panes:
                self.paned.forget(self.right_container)
        else:
            if right_id not in panes:
                self.paned.add(self.right_container, weight=4)
            # Reopening a pane from a full-width table needs a settled geometry
            # before restoring the sash and repainting the diagram.
            self.after_idle(self._refresh_visible_section)

        show_saved_panels = (index in (3,4,5) and index in self._step_result_cache
                             or index == 6 and bool(self._cdm_reports))
        if hasattr(self, 'box_kpi') and not show_saved_panels:
            if self.box_kpi.winfo_manager(): self.box_kpi.pack_forget()
            if self.box_chart.winfo_manager(): self.box_chart.pack_forget()
            if not self.box_geom.winfo_manager():
                self.box_geom.pack(fill='both', expand=True, pady=4)

        if index in (3, 4, 5):
            self._show_residual_for_step()
        if index == 6 and (self.design_mode.get() != 'TÍNH TOÀN TUYẾN'
                           or self.route_section_selector.active is None):
            self.refresh_cdm_inputs()
        if index == 8:
            self.refresh_result_summary()
        elif index == 9:
            self.refresh_treatment_boq()
        if index in (4, 5):
            self._show_natural_kpis()
        if hasattr(self, 'cad_stage_select'):
            if index in (4, 5) and not (index == 4 and not
                                        (self.mechanical_wait.get() or self.mechanical_surcharge.get())):
                self.cad_stage_select.pack(side='right', padx=(2, 8))
                self.cad_stage_label.pack(side='right')
                self._refresh_cad_stage_options()
            else:
                self.cad_stage_select.pack_forget()
                self.cad_stage_label.pack_forget()
                
        if index not in (6,7,8,9,10,11,12,13,14,15,16,17,18):
            self.draw_live_diagram()
        if index == 10:self.geology_statistics_view.refresh()
        if index in (10,14) and self.design_mode.get()=='TÍNH MỘT ĐOẠN':
            self._sync_geology_session(refresh=False)
            self._ai_analysis_workspace.refresh()
        if index == 15:self.batch_before_view.refresh()
        if index == 16:self.batch_design_view.refresh()
        if index == 17:self.single_selection_view.refresh()
        if index == 18:self.single_treatment_summary_view.refresh()
        self._switching_step = False
        if index<10:self.restore_step_result(index)
        self.after_idle(self._sync_workspace_split)
        refresh_job = getattr(self, '_section_refresh_job', None)
        if refresh_job is not None:self.after_cancel(refresh_job)
        self._section_refresh_job = (self.after(60, self._refresh_visible_section)
                                     if index in (1,2,3,4,5,6) else None)
        language_job = getattr(self, '_tab_language_job', None)
        if language_job is not None: self.after_cancel(language_job)
        self._tab_language_job = self.after_idle(self._translate_visible_tab)

    def _translate_visible_tab(self):
        self._tab_language_job = None
        self._apply_ui_language()

    def _set_ui_language(self, _event=None):
        self._apply_ui_language()
        if not getattr(self, '_language_tick_active', False):
            self._language_tick_active = True
            self.after(800, self._language_tick)

    def _language_tick(self):
        self._apply_ui_language()
        self.after(800, self._language_tick)

    def _install_language_messages(self):
        # Các hộp thoại sinh sau khi đổi ngôn ngữ cũng dùng lựa chọn hiện tại.
        for name in ('showinfo', 'showerror', 'showwarning', 'askyesno',
                     'askokcancel', 'askretrycancel', 'askquestion'):
            original = getattr(messagebox, name)
            if getattr(original, '_sf_language_wrapper', False):
                continue
            def localized_message(title=None, message=None, *args, _original=original, **kwargs):
                if getattr(self, 'ui_language', None) is not None and self.ui_language.get() == 'English':
                    title = _english_ui(title) if title is not None else title
                    message = _english_ui(message) if message is not None else message
                return _original(title, message, *args, **kwargs)
            localized_message._sf_language_wrapper = True
            setattr(messagebox, name, localized_message)

    def _apply_ui_language(self):
        english_mode = self.ui_language.get() == 'English'

        def localized(source):
            return _english_ui(source) if english_mode else source

        if hasattr(self, 'cad_plot_select'):
            plot_values = ('Mặt cắt', 'Độ lún', 'Ứng suất tăng thêm', 'Ứng suất bản thân',
                           'Áp lực nước tĩnh', 'Áp lực nước lỗ rỗng', 'Áp lực nước thặng dư')
            self.cad_plot_select.configure(values=tuple(localized(v) for v in plot_values))
            self.cad_plot_display.set(localized(self.cad_plot_mode.get()))
            self.cad_stage_select.configure(values=tuple(localized(v) for v in
                                                     self._cad_stage_days))
            self.cad_stage_display.set(localized(self.cad_stage_mode.get()))

        def update_var(var):
            current = var.get()
            key = str(var)
            source, prior_translation = self._ui_var_sources.get(key, (current, None))
            if current != prior_translation:
                source = current
            translated = localized(source)
            if current != translated:
                var.set(translated)
            self._ui_var_sources[key] = (source, translated)

        if not hasattr(self, '_ui_var_sources'):
            self._ui_var_sources = {}
        for var in (getattr(self, 'workspace_heading', None),
                    getattr(self, 'workspace_subtitle', None),
                    getattr(self, 'status_text', None)):
            if var is not None:
                update_var(var)

        def walk(widget):
            if hasattr(widget, '_sf_refresh_scope_display'):
                widget._sf_refresh_scope_display()
                return
            if getattr(widget, '_sf_language_selector', False):
                return
            if isinstance(widget, tk.Toplevel):
                current_title = widget.title()
                source, last = getattr(widget, '_sf_title_source', (current_title, None))
                if current_title != last:
                    source = current_title
                desired_title = localized(source)
                if current_title != desired_title:
                    widget.title(desired_title)
                widget._sf_title_source = (source, desired_title)
            if (isinstance(widget, ttk.Combobox) and
                    widget not in (getattr(self, 'cad_plot_select', None),
                                   getattr(self, 'cad_stage_select', None))):
                adapter = getattr(widget, '_sf_combo_adapter', None)
                values_now = tuple(widget['values'])
                if adapter is None and english_mode and widget.cget('textvariable'):
                    original_var = tk.StringVar(master=self, name=widget.cget('textvariable'))
                    display_var = tk.StringVar(master=self, value=original_var.get())
                    adapter = {'original': original_var, 'display': display_var,
                               'values': values_now, 'rendered': values_now, 'busy': False}
                    widget._sf_combo_adapter = adapter
                    widget.configure(textvariable=display_var)
                    def from_display(*_args, info=adapter):
                        if info['busy']:
                            return
                        shown = info['display'].get()
                        canonical = next((v for v in info['values']
                                          if shown in (v, _english_ui(v))), shown)
                        if info['original'].get() != canonical:
                            info['original'].set(canonical)
                    def from_original(*_args, info=adapter):
                        if info['busy']:
                            return
                        shown = (_english_ui(info['original'].get())
                                 if self.ui_language.get() == 'English'
                                 else info['original'].get())
                        if info['display'].get() != shown:
                            info['busy'] = True
                            info['display'].set(shown)
                            info['busy'] = False
                    display_var.trace_add('write', from_display)
                    original_var.trace_add('write', from_original)
                if adapter is not None:
                    if values_now != adapter['rendered']:
                        adapter['values'] = values_now
                    rendered = tuple(localized(v) for v in adapter['values'])
                    if values_now != rendered:
                        widget.configure(values=rendered)
                    adapter['rendered'] = rendered
                    shown = localized(adapter['original'].get())
                    if adapter['display'].get() != shown:
                        adapter['busy'] = True
                        adapter['display'].set(shown)
                        adapter['busy'] = False
            try:
                current = widget.cget('text')
                if isinstance(widget, (ttk.Button, tk.Button)):
                    lower = str(current).casefold()
                    restricted = any(word in lower for word in ('tối ưu', 'optimiz', 'hàng loạt', 'batch', 'pdf'))
                    if restricted and hasattr(self, 'current_user_tier'):
                        widget.configure(state='disabled' if self.is_trial() else 'normal')
                    is_navigation = (isinstance(widget, tk.Button) and (
                        str(widget).startswith(str(self.sidebar)) or
                        str(widget).startswith(str(self.workspace_tabs))))
                    if not is_navigation:
                        primary = any(word in lower for word in
                            ('tính', 'calculat', 'tối ưu', 'optimiz', 'kiểm toán', 'assess'))
                        style_action_button(widget, primary)
                previous = getattr(widget, '_sf_original_text', None)
                if previous is None or current != getattr(widget, '_sf_last_rendered', None):
                    widget._sf_original_text = current
                desired = display_math(localized(widget._sf_original_text))
                if current != desired:
                    widget.configure(text=desired)
                apply_math_label(widget, localized(widget._sf_original_text))
                widget._sf_last_rendered = desired
            except (tk.TclError, AttributeError):
                pass
            if isinstance(widget, (tk.Canvas,)):
                cache = getattr(widget, '_sf_canvas_text', {})
                for item in widget.find_all():
                    if widget.type(item) != 'text':
                        continue
                    current = widget.itemcget(item, 'text')
                    source, prior_translation = cache.get(item, (current, None))
                    if current != prior_translation:
                        source = current
                    desired = display_math(localized(source))
                    if current != desired:
                        widget.itemconfigure(item, text=desired)
                    cache[item] = (source, desired)
                widget._sf_canvas_text = cache
            if isinstance(widget, ttk.Treeview):
                sources = getattr(widget, '_sf_heading_sources', {})
                for col in widget['columns']:
                    current = widget.heading(col, 'text')
                    source, prior_translation = sources.get(col, (current, None))
                    if current != prior_translation:
                        source = current
                    desired = display_math(localized(source))
                    if current != desired:
                        widget.heading(col, text=desired)
                    sources[col] = (source, desired)
                widget._sf_heading_sources = sources
            for child in widget.winfo_children():
                walk(child)

        walk(self)
        try:
            menu = self.nametowidget(self.cget('menu'))
        except (tk.TclError, KeyError):
            menu = None
        def walk_menu(menu_widget):
            if menu_widget is None:
                return
            sources = getattr(menu_widget, '_sf_label_sources', {})
            last = menu_widget.index('end')
            for idx in range((last if last is not None else -1)+1):
                try:
                    current = menu_widget.entrycget(idx, 'label')
                except tk.TclError:
                    continue
                source, prior_translation = sources.get(idx, (current, None))
                if current != prior_translation:
                    source = current
                desired = localized(source)
                if current != desired:
                    menu_widget.entryconfigure(idx, label=desired)
                sources[idx] = (source, desired)
                if menu_widget.type(idx) == 'cascade':
                    walk_menu(menu_widget.nametowidget(menu_widget.entrycget(idx, 'menu')))
            menu_widget._sf_label_sources = sources
        walk_menu(menu)

    def _menu(self):
        m = tk.Menu(self)

        fm = tk.Menu(m, tearoff=False)
        fm.add_command(label='Tạo dự án mới', command=self.new)
        fm.add_command(label='Mở dự án', command=self.open)
        fm.add_command(label='Lưu dự án', command=self.save_file)
        fm.add_command(label='Lưu dự án mới', command=self.save_as)
        def undo_data_import():
            undo=getattr(self._ai_analysis_workspace,'_undo_last_import',None)
            if undo:undo()
            else:messagebox.showinfo('Hoàn tác nhập dữ liệu','Chưa có lần nhập để hoàn tác.',parent=self)
        fm.add_command(label='Hoàn tác nhập dữ liệu',command=undo_data_import)
        fm.add_separator()
        fm.add_command(label='Xuất mẫu nhập liệu', command=self.save_import_template)
        data_menu = tk.Menu(fm, tearoff=False)
        data_menu.add_command(label='Xuất bảng đang xem', command=self.export_visible_table)
        data_menu.add_command(label='Xuất thống kê chỉ tiêu',
                             command=lambda: self.geology_statistics_view.export_all_statistics())
        def sync_route_exports():
            last = data_menu.index('end')
            if last is not None and last >= 2: data_menu.delete(2, 'end')
            data_menu._sf_label_sources = {}
            if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
                for label, kind in (('Xuất bảng tổng hợp xử lý', 'summary'),
                                    ('Xuất bảng khối lượng', 'table'),
                                    ('Xuất mẫu khối lượng', 'template')):
                    if self.ui_language.get() == 'English': label = _english_ui(label)
                    data_menu.add_command(label=label, command=lambda k=kind: self.export_treatment_data(k))
        data_menu.configure(postcommand=sync_route_exports)
        sync_route_exports()
        fm.add_cascade(label='Xuất dữ liệu', menu=data_menu)
        pdf_menu = tk.Menu(fm, tearoff=False)
        pdf_menu.add_command(label='Xuất PDF theo phân đoạn', command=lambda: self.export_workflow_pdf(False))
        pdf_menu.add_command(label='Xuất PDF toàn tuyến', command=lambda: self.export_workflow_pdf(True))
        fm.add_cascade(label='Xuất báo cáo PDF', menu=pdf_menu)
        m.add_cascade(label='Tệp', menu=fm)

        m.add_command(label='Thiết lập tính toán', command=self.open_calculation_settings)

        hm = tk.Menu(m, tearoff=False)
        hm.add_command(label='Giới thiệu SOILFIRM PRO (30 giây)', command=self.show_software_intro)
        hm.add_command(label='Hướng dẫn sử dụng', command=lambda: show_help_dialog(self))
        m.add_cascade(label='Hướng dẫn', menu=hm)

        am = tk.Menu(m, tearoff=False)
        am.add_command(label='Giới thiệu và cập nhật', command=self.about)
        m.add_cascade(label='Giới thiệu', menu=am)


        if getattr(self, 'current_user_role', None) == 'admin':
            sys_m = tk.Menu(m, tearoff=False)
            sys_m.add_command(label='Quản lý tài khoản', command=self.open_admin_panel)
            m.add_cascade(label='Quản trị', menu=sys_m)

        m.add_command(label='Thoát', command=self.exit_app)
        self.config(menu=m)

    def open_ai_support(self):
        from chat_dialog import show_ai_dialog
        try:
            self._ai_support_window = show_ai_dialog(self)
        except ValueError as exc:
            messagebox.showwarning('Hỗ trợ AI', str(exc), parent=self)

    def open_chat(self, selected_user=''):
        from chat_dialog import show_chat_dialog
        try:
            existing = getattr(self, '_support_window', None)
            if existing is not None and existing.winfo_exists():
                existing.deiconify(); existing.lift()
                if selected_user:
                    existing.select_peer(selected_user)
                return
            self._support_window = show_chat_dialog(self, admin=self.current_user_role == 'admin',
                                                    selected_user=selected_user)
        except ValueError as exc:
            messagebox.showwarning('Chat', str(exc), parent=self)

    def open_admin_panel(self):
        if self.current_user_role != 'admin' or not getattr(self, 'admin_key_cached', None):
            messagebox.showwarning("Không có quyền", "Chức năng này chỉ dành cho tài khoản Admin đã đăng nhập!", parent=self)
            return
            
        admin_win = tk.Toplevel(self)
        admin_win.title("Quản Trị Người Dùng & Key - SOILFIRM PRO")
        admin_win._popup_fit_scheduled = True
        
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = max(1, min(900, sw - 40))
        h = max(1, min(560, sh - 80))
        x = int((sw - w) / 2)
        y = int((sh - h) / 2)
        
        admin_win.geometry(f"{w}x{h}+{x}+{y}")
        admin_win.transient(self)
        
        headers = {"admin-key": self.admin_key_cached}

        # Bảng có thanh cuộn riêng; nút lệnh luôn nằm ở đáy cửa sổ.
        inner = ttk.Frame(admin_win)
        inner.pack(fill='both', expand=True)

        top_info = tk.Frame(inner, bg='#FEF3C7', padx=20, pady=12)
        top_info.pack(fill='x', side='top', pady=(0, 10))
        tk.Label(top_info, text="QUẢN LÝ HỆ THỐNG — TÀI KHOẢN D1",
                 font=(UI_FONT, 10, 'bold'), fg='#92400E', bg='#FEF3C7').pack()
        tk.Label(top_info, text=f"👑 Xin chào Admin: {self.current_fullname}  •  Thời hạn: Vô hạn",
                 font=(UI_FONT, 9, 'italic'), fg='#B45309', bg='#FEF3C7').pack(pady=(4, 0))
        activity_note = tk.StringVar(value='Trạng thái được lấy khi làm mới danh sách.')
        tk.Label(top_info, textvariable=activity_note, font=(UI_FONT, 9),
                 fg='#92400E', bg='#FEF3C7').pack(pady=(3, 0))

        bottom_frame = tk.Frame(inner, pady=6)
        bottom_frame.pack(side='bottom', fill='x')

        f_action = tk.Frame(bottom_frame, padx=10, pady=4)
        f_action.pack()

        # Dòng 1: Họ tên & User
        tk.Label(f_action, text="Họ và tên:", font=(UI_FONT, 9, 'bold')).grid(row=0, column=0, padx=5, pady=4, sticky='e')
        e_fullname = ttk.Entry(f_action, width=28, font=(UI_FONT, 10))
        e_fullname.grid(row=0, column=1, padx=5, pady=4)

        tk.Label(f_action, text="Tên tài khoản (User):", font=(UI_FONT, 9, 'bold')).grid(row=0, column=2, padx=5, pady=4, sticky='e')
        e_user = ttk.Entry(f_action, width=22, font=(UI_FONT, 10))
        e_user.grid(row=0, column=3, padx=5, pady=4)

        # Dòng 2: Mật khẩu, Phân loại & Thời hạn dùng
        tk.Label(f_action, text="Mật khẩu (Key):", font=(UI_FONT, 9, 'bold')).grid(row=1, column=0, padx=5, pady=4, sticky='e')
        e_key = ttk.Entry(f_action, width=28, font=(UI_FONT, 10))
        e_key.grid(row=1, column=1, padx=5, pady=4)

        tk.Label(f_action, text="Phân loại:", font=(UI_FONT, 9, 'bold')).grid(row=1, column=2, padx=5, pady=4, sticky='e')
        cb_tier = ttk.Combobox(f_action, values=('trial', 'oem'), state='readonly', width=20, font=(UI_FONT, 10))
        cb_tier.set('trial')
        cb_tier.grid(row=1, column=3, padx=5, pady=4)

        tk.Label(f_action, text="Thời hạn dùng:", font=(UI_FONT, 9, 'bold')).grid(row=2, column=0, padx=5, pady=4, sticky='e')
        cb_expiry = ttk.Combobox(f_action, values=('Vĩnh viễn', '30 ngày', '90 ngày', '180 ngày', '1 năm'), width=26, font=(UI_FONT, 10))
        cb_expiry.set('1 năm')
        cb_expiry.grid(row=2, column=1, padx=5, pady=4)
        tk.Label(f_action, text="(Hoặc gõ ngày YYYY-MM-DD)", font=(UI_FONT, 9, 'italic'), fg='#64748B').grid(row=2, column=2, sticky='w')

        btn_row = tk.Frame(bottom_frame, pady=4)
        btn_row.pack()
        
        tree_frame = tk.Frame(inner, padx=20, pady=6)
        tree_frame.pack(side='top', fill='both', expand=True)
        table_area = ttk.Frame(tree_frame)
        table_area.pack(fill='both', expand=True)
        table_area.columnconfigure(0, weight=1)
        table_area.rowconfigure(0, weight=1)

        style = ttk.Style(admin_win)
        _admin_stripe = configure_treeview_style(style, 'Admin.Treeview', font_size=9, row_height=22)

        tree = ttk.Treeview(table_area, columns=("Fullname", "User", "Key", "Tier", "Expiry", "Status", "LastSeen", "Usage"), show="headings", height=14, style="Admin.Treeview")
        admin_headers = {'Fullname': 'Họ và tên', 'User': 'Tên tài khoản (User)',
                         'Key': 'Khóa kích hoạt (Password)', 'Tier': 'Phân loại',
                         'Expiry': 'Thời hạn dùng', 'Status': 'Trạng thái hoạt động',
                         'LastSeen': 'Hoạt động gần nhất', 'Usage': 'Thời gian sử dụng'}
        admin_font = tkfont.Font(admin_win, family=UI_FONT, size=9, weight='bold')
        admin_body_font = tkfont.Font(admin_win, family=UI_FONT, size=9)
        admin_caps = {'Fullname': 220, 'User': 175, 'Key': 210,
                      'Tier': 90, 'Expiry': 125, 'Status': 155,
                      'LastSeen': 155, 'Usage': 155}
        for cid, label in admin_headers.items():
            display = _compact_heading(label, admin_font)
            tree.heading(cid, text=display)
            width = max(60, _heading_width(display, admin_font)+14)
            tree.column(cid, width=width, minwidth=width,
                        anchor='w' if cid == 'Fullname' else 'center', stretch=False)
        
        sb_y = ttk.Scrollbar(table_area, orient='vertical', command=tree.yview)
        sb_x = ttk.Scrollbar(table_area, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        
        tree.grid(row=0, column=0, sticky='nsew')
        sb_y.grid(row=0, column=1, sticky='ns')
        sb_x.grid(row=1, column=0, sticky='ew')

        def fit_admin_window():
            if not admin_win.winfo_exists():
                return
            admin_win.update_idletasks()
            count = len(tree.get_children())
            fixed_height = top_info.winfo_reqheight() + bottom_frame.winfo_reqheight() + 95
            available_rows = max(3, (sh - 100 - fixed_height) // 22)
            visible = min(14, max(3, count), available_rows)
            tree.configure(height=visible)
            width = min(sw - 40, max(740, sum(tree.column(cid, 'width') for cid in admin_headers) + 65,
                                     f_action.winfo_reqwidth() + 55, top_info.winfo_reqwidth() + 25))
            height = min(sh - 80, fixed_height + 22 * visible)
            admin_win.geometry(f'{width}x{height}+{max(0, (sw-width)//2)}+{max(0, (sh-height)//2)}')

        def load_users():
            tree.delete(*tree.get_children())
            try:
                resp = requests.get(f"{self.API_BASE_URL}/api/admin/users", headers=headers, timeout=5)
                data = resp.json()
                if data.get("success"):
                    users = data.get('users', [])
                    available = sum(any(k in u for k in ('is_online', 'online', 'last_seen_at',
                                                          'last_activity_at', 'last_login_at',
                                                          'total_usage_seconds', 'usage_seconds'))
                                    for u in users)
                    activity_note.set('Đã nhận trạng thái hoạt động từ máy chủ.' if available
                                      else 'Máy chủ chưa cung cấp trạng thái hoạt động; cần cập nhật API.')
                    for u in users:
                        fn = u.get("fullname", u.get("username", ""))
                        t = u.get("tier", "trial")
                        exp = u.get("expires_at", "Vĩnh viễn")
                        status, last_seen, usage = _user_activity(u)
                        tree.insert("", "end", values=(fn, u.get("username"), u.get("key"),
                                                        t, exp, status, last_seen, usage))
                    for i, cid in enumerate(admin_headers):
                        heading = tree.heading(cid, 'text')
                        width = _heading_width(heading, admin_font) + 14
                        for item in tree.get_children():
                            width = max(width, admin_body_font.measure(str(tree.item(item, 'values')[i]))+14)
                        width = min(admin_caps[cid], max(60, width))
                        tree.column(cid, minwidth=40)
                        tree.column(cid, width=width, stretch=False)
                    admin_win.after_idle(fit_admin_window)
            except Exception as e:
                messagebox.showerror("Lỗi", str(e), parent=admin_win)

        load_users()

        def fill_user_fields(_event=None):
            selected = tree.selection()
            if not selected:
                return
            values = tree.item(selected[0], 'values')
            if len(values) < 5:
                return
            for entry, value in ((e_fullname, values[0]), (e_user, values[1]),
                                 (e_key, values[2])):
                entry.delete(0, 'end')
                entry.insert(0, value)
            cb_tier.set(values[3])
            cb_expiry.set(values[4])

        tree.bind('<<TreeviewSelect>>', fill_user_fields)

        def create_user():
            fn, u, k, t = e_fullname.get().strip(), e_user.get().strip(), e_key.get().strip(), cb_tier.get()
            exp_choice = cb_expiry.get().strip()

            if not u:
                messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập đủ User và Key!", parent=admin_win)
                return
            if not fn: fn = u

            today = datetime.now()
            if exp_choice == '30 ngày':
                final_expiry = (today + timedelta(days=30)).strftime('%Y-%m-%d')
            elif exp_choice == '90 ngày':
                final_expiry = (today + timedelta(days=90)).strftime('%Y-%m-%d')
            elif exp_choice == '180 ngày':
                final_expiry = (today + timedelta(days=180)).strftime('%Y-%m-%d')
            elif exp_choice == '1 năm':
                final_expiry = (today + timedelta(days=365)).strftime('%Y-%m-%d')
            elif exp_choice in ('Vĩnh viễn', 'Vô hạn', ''):
                final_expiry = 'Vĩnh viễn'
            else:
                final_expiry = exp_choice

            try:
                resp = requests.post(f"{self.API_BASE_URL}/api/admin/users", json={
                    "username": u, "key": k, "fullname": fn, "tier": t, "expires_at": final_expiry
                }, headers=headers)
                messagebox.showinfo("Báo cáo", resp.json().get("message"), parent=admin_win)
                e_fullname.delete(0, 'end')
                e_user.delete(0, 'end')
                e_key.delete(0, 'end')
                load_users()
            except Exception as e:
                messagebox.showerror("Lỗi", str(e), parent=admin_win)

        def delete_user():
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("Chọn dòng", "Vui lòng chọn 1 tài khoản trong bảng để xóa!", parent=admin_win)
                return
            u = tree.item(selected[0])["values"][1] 
            if messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc muốn xóa tài khoản '{u}' khỏi máy chủ?", parent=admin_win):
                try:
                    resp = requests.delete(f"{self.API_BASE_URL}/api/admin/users?username={u}", headers=headers)
                    messagebox.showinfo("Báo cáo", resp.json().get("message"), parent=admin_win)
                    load_users()
                except Exception as e:
                    messagebox.showerror("Lỗi", str(e), parent=admin_win)

        ttk.Button(btn_row, text="➕ Tạo / Sửa Tài khoản", command=create_user, style='Accent.TButton').pack(side='left', padx=10)
        ttk.Button(btn_row, text="🗑 Xóa Tài khoản chọn", command=delete_user).pack(side='left', padx=10)
        ttk.Button(btn_row, text="🔄 Làm mới danh sách", command=load_users).pack(side='left', padx=10)
        ttk.Button(btn_row, text='Chat với tài khoản chọn',
                   command=lambda: self.open_chat(
                       str(tree.item(tree.selection()[0], 'values')[1]) if tree.selection() else ''
                   )).pack(side='left', padx=10)
        ttk.Button(btn_row, text='Nhắn tất cả thành viên',
                   command=self.open_admin_broadcast).pack(side='left', padx=10)
        admin_win.after_idle(fit_admin_window)

    def open_admin_broadcast(self):
        if self.current_user_role != 'admin' or not self.admin_key_cached:
            messagebox.showwarning('Không có quyền', 'Chỉ Admin được gửi tin nhắn toàn bộ thành viên.', parent=self)
            return
        import threading
        import uuid
        from queue import Queue, Empty
        window = tk.Toplevel(self)
        window.title('Nhắn tin tất cả thành viên')
        window.geometry('580x380')
        window.transient(self)
        ttk.Label(window, text='Tin nhắn sẽ được gửi đến tất cả tài khoản thành viên, kể cả đang offline.',
                  wraplength=540).pack(anchor='w', padx=16, pady=(16, 8))
        editor = tk.Text(window, height=10, wrap='word', font=(UI_FONT, 12))
        editor.pack(fill='both', expand=True, padx=16, pady=8)
        status = tk.StringVar(value='Nhập nội dung, tối đa 2000 ký tự.')
        ttk.Label(window, textvariable=status, wraplength=540).pack(anchor='w', padx=16, pady=6)
        controls = ttk.Frame(window)
        controls.pack(fill='x', padx=16, pady=(4, 16))
        queue = Queue()
        state = {'busy': False, 'id': None, 'text': None}
        key = self.admin_key_cached
        url = self.API_BASE_URL + '/api/admin/broadcast'

        def close():
            if not state['busy']:
                window.destroy()

        def send():
            text = editor.get('1.0', 'end-1c').strip()
            if not text or len(text) > 2000:
                status.set('Vui lòng nhập từ 1 đến 2000 ký tự.')
                return
            if state['busy']:
                return
            if text != state['text']:
                state['id'] = uuid.uuid4().hex
                state['text'] = text
            state['busy'] = True
            editor.config(state='disabled')
            button.config(state='disabled')
            status.set('Đang gửi đến tất cả thành viên…')
            payload = {'text': text, 'client_id': state['id']}

            def worker():
                try:
                    response = requests.post(url, headers={'admin-key': key}, json=payload, timeout=(5, 45))
                    try:
                        data = response.json()
                    except ValueError:
                        data = {}
                    if not response.ok or not data.get('success'):
                        raise ValueError(data.get('message') or f'Máy chủ trả lỗi HTTP {response.status_code}.')
                    queue.put((True, data))
                except Exception as exc:
                    queue.put((False, str(exc)))
            threading.Thread(target=worker, daemon=True).start()

        def drain():
            if not window.winfo_exists():
                return
            try:
                success, data = queue.get_nowait()
            except Empty:
                window.after(100, drain)
                return
            state['busy'] = False
            editor.config(state='normal')
            button.config(state='normal')
            if success:
                status.set(f"Đã gửi tin nhắn đến {int(data.get('recipient_count', 0))} thành viên.")
                editor.delete('1.0', 'end')
                state['id'] = state['text'] = None
            else:
                status.set('Chưa xác nhận gửi thành công: ' + data + ' Có thể bấm Gửi lại cùng nội dung để tránh gửi trùng.')
            window.after(100, drain)

        button = ttk.Button(controls, text='Gửi tất cả thành viên', command=send, style='Accent.TButton')
        button.pack(side='left')
        ttk.Button(controls, text='Đóng', command=close).pack(side='right')
        window.protocol('WM_DELETE_WINDOW', close)
        window.after(100, drain)

    def _build_tab_proj(self):
        scroll_frame = _PopupScrollFrame(self.tab_proj)
        scroll_frame.pack(fill='both', expand=True)
        inner = scroll_frame.scrollable_frame

        box_proj = ttk.Frame(inner, padding=(16, 14))
        box_proj.pack(fill='x', expand=False, pady=10, padx=12)
        box_proj.columnconfigure(0, weight=0, minsize=140)
        box_proj.columnconfigure(1, weight=1)

        self.vars['name'] = tk.StringVar()
        self.vars['design_stage'] = tk.StringVar()
        self.vars['work_item'] = tk.StringVar()
        self.vars['station_from'] = tk.StringVar()
        self.vars['station_to'] = tk.StringVar()
        self.vars['station'] = tk.StringVar()
        self.vars['road_class'] = tk.StringVar(value='A1 · cao tốc hoặc Vtk ≥ 80 km/h')
        self.vars['road_location'] = tk.StringVar(value='Nền đắp thông thường')
        self.vars['assessment_days'] = tk.StringVar(value='0')
        self.vars['residual_limit_cm'] = tk.StringVar(value='20.0')

        self.excel_section_no = tk.StringVar()
        self.project_batch_buttons = []
        self.ai_processing_bar = None
        self.ai_processing_label = None
        self.set_ai_processing(getattr(self,'_ai_processing_active',False),getattr(self,'_ai_processing_message',''))

        self.excel_section_notice = tk.StringVar(value='')

        ttk.Label(box_proj, text='Tên dự án:').grid(row=0, column=0, sticky='w', pady=7)
        ttk.Entry(box_proj, textvariable=self.vars['name']).grid(row=0, column=1, sticky='ew', pady=7)

        ttk.Label(box_proj, text='Bước thiết kế:').grid(row=1, column=0, sticky='w', pady=7)
        ttk.Entry(box_proj, textvariable=self.vars['design_stage']).grid(row=1, column=1, sticky='ew', pady=7)

        ttk.Label(box_proj, text='Hạng mục:').grid(row=2, column=0, sticky='w', pady=7)
        ttk.Entry(box_proj, textvariable=self.vars['work_item']).grid(row=2, column=1, sticky='ew', pady=7)

        ttk.Label(box_proj, text='Phân đoạn xử lý:').grid(row=3, column=0, sticky='w', pady=7)
        f_km_box = ttk.Frame(box_proj)
        ttk.Label(f_km_box, text='Từ KM').pack(side='left', padx=(0, 6))
        e_from = ttk.Entry(f_km_box, textvariable=self.vars['station_from'], width=14)
        e_from.pack(side='left', padx=(0, 20))
        ttk.Label(f_km_box, text='Đến KM').pack(side='left', padx=(0, 6))
        e_to = ttk.Entry(f_km_box, textvariable=self.vars['station_to'], width=14)
        e_to.pack(side='left')
        f_km_box.grid(row=3, column=1, sticky='w', pady=7)

        ttk.Label(box_proj, text='Mặt cắt tính toán:').grid(row=4, column=0, sticky='w', pady=7)
        s_km_box = ttk.Frame(box_proj)
        ttk.Label(s_km_box, text='KM', font=(UI_FONT, 9, 'bold'), foreground='#2563EB').pack(side='left', padx=(0, 6))
        e_st = ttk.Entry(s_km_box, textvariable=self.vars['station'], width=20, font=(UI_FONT, 9, 'bold'))
        e_st.pack(side='left')
        s_km_box.grid(row=4, column=1, sticky='w', pady=7)

        for ent, k in [(e_from, 'station_from'), (e_to, 'station_to'), (e_st, 'station')]:
            ent.bind('<FocusOut>', lambda _e, var=self.vars[k]: var.set(clean_km_str(var.get())))

        ttk.Label(box_proj, text='Cấp đường:').grid(row=5, column=0, sticky='w', pady=7)
        self.cb_rc = ttk.Combobox(box_proj, textvariable=self.vars['road_class'], state='readonly',
                                  values=('A1 · cao tốc hoặc Vtk ≥ 80 km/h', 'A1 · Vtk ≤ 60 km/h', 'Khác · nhập riêng'))
        self.cb_rc.grid(row=5, column=1, sticky='ew', pady=7)

        ttk.Label(box_proj, text='Vị trí đắp:').grid(row=6, column=0, sticky='w', pady=7)
        self.cb_loc = ttk.Combobox(box_proj, textvariable=self.vars['road_location'], state='readonly',
                                   values=('Nền đắp thông thường', 'Gần mố cầu', 'Hai bên cống hoặc cống chui'))
        self.cb_loc.grid(row=6, column=1, sticky='ew', pady=7)

        ttk.Label(box_proj, text='Độ lún cho phép [ΔS]:', font=(UI_FONT, 9, 'bold'), foreground='#B45309').grid(row=7, column=0, sticky='w', pady=7)
        f_limit = ttk.Frame(box_proj)
        self.ent_residual = ttk.Entry(f_limit, textvariable=self.vars['residual_limit_cm'], width=10, font=(UI_FONT, 9, 'bold'))
        self.ent_residual.pack(side='left')
        ttk.Label(f_limit, text='cm   ', font=(UI_FONT, 9, 'bold'), foreground='#B45309').pack(side='left')
        self.lbl_limit_hint = ttk.Label(f_limit, text='(Tự động theo TCVN 9355 / 22 TCN 262)', font=(UI_FONT, 9, 'italic'), foreground='#64748B')
        f_limit.grid(row=7, column=1, sticky='w', pady=7)
        ttk.Label(box_proj,
                  text='Lưu ý: Chọn chức năng tính toán phù hợp với số liệu đầu vào và thiết lập hiện tại.',
                  font=(UI_FONT, 9, 'italic'), foreground='#475569',
                  wraplength=760).grid(row=8, column=0, columnspan=2, sticky='w', pady=(4, 0))

        self.vars['road_class'].trace_add('write', self.update_residual_limit)
        self.vars['road_location'].trace_add('write', self.update_residual_limit)

    def update_residual_limit(self, *args):
        # Giới hạn trong Data là đầu vào của từng đoạn, không suy lại theo cấp đường.
        source = getattr(self.project, 'residual_limit_source', '')
        if source:
            text = str(self.project.residual_limit_cm)
            if self.vars['residual_limit_cm'].get() != text:
                self.vars['residual_limit_cm'].set(text)
            self.ent_residual.configure(state='readonly')
            if hasattr(self, 'lbl_limit_hint'):
                self.lbl_limit_hint.config(text=f'(Data import: {source})', foreground='#2563EB')
            if hasattr(self, 'card_limit'):
                self.card_limit.config(text=f'{self.project.residual_limit_cm:g} cm')
            return
        rc = self.vars.get('road_class', tk.StringVar()).get()
        loc = self.vars.get('road_location', tk.StringVar()).get()

        if rc == 'Khác · nhập riêng':
            self.ent_residual.configure(state='normal')
            if hasattr(self, 'lbl_limit_hint'):
                self.lbl_limit_hint.config(text='(Kỹ sư tự nhập độ lún cho phép)', foreground='#2563EB')
        else:
            self.ent_residual.configure(state='normal')
            if '≥ 80' in rc or 'cao tốc' in rc:
                val = 10.0 if 'mố cầu' in loc else 20.0
            elif '≤ 60' in rc:
                val = 10.0 if 'mố cầu' in loc else 20.0 if 'cống' in loc else 30.0
            else:
                val = 30.0

            self.vars['residual_limit_cm'].set(f"{val:.2f}")
            self.ent_residual.configure(state='readonly')
            if hasattr(self, 'lbl_limit_hint'):
                self.lbl_limit_hint.config(text='(Tự động theo TCVN 9355 / 22 TCN 262)', foreground='#64748B')

        if hasattr(self, 'card_limit'):
            self.card_limit.config(text=f"{self.vars['residual_limit_cm'].get()} cm")

    def _build_tab_params(self):
        scroll_frame = _PopupScrollFrame(self.tab_params)
        scroll_frame.pack(fill='both', expand=True)
        inner = scroll_frame.scrollable_frame

        box_emb = ttk.LabelFrame(inner, text='1. Kích thước nền đường chính', padding=12)
        box_emb.pack(fill='x', pady=5, padx=8)

        self.vars['h_design'] = tk.StringVar(value='3.0')
        self.vars['h_kcad'] = tk.StringVar(value='0.15')
        self.vars['crest_B'] = tk.StringVar(value='12.0')
        self.vars['slope_M'] = tk.StringVar(value='1.5')
        self.vars['gamma_fill'] = tk.StringVar(value='1.8')

        ttk.Label(box_emb, text='Chiều cao đắp thiết kế Htk (m):').grid(row=0, column=0, sticky='w', pady=5)
        ttk.Entry(box_emb, textvariable=self.vars['h_design'], width=18).grid(row=0, column=1, sticky='w', pady=5)

        ttk.Label(box_emb, text='Chiều dày áo đường Hkcad (m):').grid(row=1, column=0, sticky='w', pady=5)
        ttk.Entry(box_emb, textvariable=self.vars['h_kcad'], width=18).grid(row=1, column=1, sticky='w', pady=5)

        ttk.Label(box_emb, text='Bề rộng đỉnh nền B (m):').grid(row=2, column=0, sticky='w', pady=5)
        ttk.Entry(box_emb, textvariable=self.vars['crest_B'], width=18).grid(row=2, column=1, sticky='w', pady=5)

        ttk.Label(box_emb, text='Hệ số mái dốc chính M (1:M):').grid(row=3, column=0, sticky='w', pady=5)
        ttk.Entry(box_emb, textvariable=self.vars['slope_M'], width=18).grid(row=3, column=1, sticky='w', pady=5)

        ttk.Label(box_emb, text='Dung trọng đất đắp γ (T/m³):').grid(row=4, column=0, sticky='w', pady=5)
        ttk.Entry(box_emb, textvariable=self.vars['gamma_fill'], width=18).grid(row=4, column=1, sticky='w', pady=5)
        box_emb.columnconfigure(1, weight=1)

        box_cw = ttk.LabelFrame(inner, text='2. Bệ phản áp (Counterweight)', padding=12)
        box_cw.pack(fill='x', pady=5, padx=8)

        self.has_cw = tk.BooleanVar(value=False)
        cb_cw = ttk.Checkbutton(box_cw, text='Áp dụng bệ phản áp', variable=self.has_cw, command=self.toggle_cw)
        cb_cw.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 6))

        self.vars['counterweight_height'] = tk.StringVar(value='0.0')
        self.vars['counterweight_width'] = tk.StringVar(value='0.0')
        self.vars['counterweight_m'] = tk.StringVar(value='1.0')

        self.lbl_cw_h = ttk.Label(box_cw, text='Chiều cao bệ H (m):')
        self.lbl_cw_h.grid(row=1, column=0, sticky='w', pady=5)
        self.ent_cw_h = ttk.Entry(box_cw, textvariable=self.vars['counterweight_height'], width=18)
        self.ent_cw_h.grid(row=1, column=1, sticky='w', pady=5)

        self.lbl_cw_l = ttk.Label(box_cw, text='Chiều rộng bệ L (m):')
        self.lbl_cw_l.grid(row=2, column=0, sticky='w', pady=5)
        self.ent_cw_l = ttk.Entry(box_cw, textvariable=self.vars['counterweight_width'], width=18)
        self.ent_cw_l.grid(row=2, column=1, sticky='w', pady=5)

        self.lbl_cw_a = ttk.Label(box_cw, text='Hệ số mái bệ m (1:m):')
        self.lbl_cw_a.grid(row=3, column=0, sticky='w', pady=5)
        self.ent_cw_a = ttk.Entry(box_cw, textvariable=self.vars['counterweight_m'], width=18)
        self.ent_cw_a.grid(row=3, column=1, sticky='w', pady=5)
        box_cw.columnconfigure(1, weight=1)

        box_exp = ttk.LabelFrame(inner, text='3. Nền mở rộng', padding=12)
        box_exp.pack(fill='x', pady=5, padx=8)
        self.has_expansion = tk.BooleanVar(value=False)
        self.cb_has_expansion = ttk.Checkbutton(
            box_exp, text='Áp dụng nền mở rộng', variable=self.has_expansion,
            command=self.toggle_expansion)
        self.cb_has_expansion.grid(row=0, column=0, columnspan=2,
                                   sticky='w', pady=(0, 6))
        self.expansion_side = tk.StringVar(value='Hai bên')
        ttk.Label(box_exp, text='Bên mở rộng:').grid(row=1, column=0, sticky='w', pady=5)
        self.cb_expansion_side = ttk.Combobox(box_exp, textvariable=self.expansion_side,
                                              values=('Trái', 'Phải', 'Hai bên'),
                                              state='readonly', width=16)
        self.cb_expansion_side.grid(row=1, column=1, sticky='w', pady=5)
        self.cb_expansion_side.bind('<<ComboboxSelected>>', self.toggle_expansion)
        self.vars['expansion_width'] = tk.StringVar(value='2.0')
        ttk.Label(box_exp, text='Bề rộng mở rộng mỗi bên (m):').grid(row=2, column=0,
                                                                  sticky='w', pady=5)
        self.ent_expansion_width = ttk.Entry(box_exp, textvariable=self.vars['expansion_width'],
                                              width=18)
        self.ent_expansion_width.grid(row=2, column=1, sticky='w', pady=5)
        expansion_fields = (
            ('expansion_h_design', 'Chiều cao đắp Htk (m):', '3.0'),
            ('expansion_slope_m', 'Hệ số mái dốc M (1:M):', '1.5'),
            ('expansion_h_kcad', 'Chiều dày áo đường Hkcad (m):', '0.15'),
            ('expansion_gamma_fill', 'Dung trọng đất đắp γ (T/m³):', '1.8'),
        )
        self.expansion_entries = []
        self.expansion_entry_by_key = {}
        self.expansion_use_main = {
            'expansion_h_kcad': tk.BooleanVar(value=False),
            'expansion_gamma_fill': tk.BooleanVar(value=False),
        }
        for row, (key, label, default) in enumerate(expansion_fields, 3):
            self.vars[key] = tk.StringVar(value=default)
            ttk.Label(box_exp, text=label).grid(row=row, column=0, sticky='w', pady=5)
            entry = ttk.Entry(box_exp, textvariable=self.vars[key], width=18)
            entry.grid(row=row, column=1, sticky='w', pady=5)
            self.expansion_entries.append(entry)
            self.expansion_entry_by_key[key] = entry
            if key in self.expansion_use_main:
                ttk.Checkbutton(box_exp, text='Lấy như nền chính',
                                variable=self.expansion_use_main[key],
                                command=self.toggle_expansion_sources).grid(
                                    row=row, column=2, sticky='w', padx=(8, 0))
        self.vars['expansion_treatment_width'] = tk.StringVar(value='')
        bxl_frame = ttk.Frame(box_exp)
        bxl_frame.grid(row=18, column=0, columnspan=3, sticky='ew', pady=6)
        ttk.Label(bxl_frame, text='Bxl từ chân nền mở rộng (m):').pack(side='left')
        ttk.Entry(bxl_frame, textvariable=self.vars['expansion_treatment_width'], width=10).pack(side='left', padx=6)
        ttk.Label(bxl_frame, text='Để trống: xử lý đến vai đường chính', foreground='#64748B').pack(side='left')
        self.vars['expansion_treatment_width'].trace_add('write', lambda *_: self.draw_live_diagram())
        box_exp.columnconfigure(1, weight=1)
        ttk.Label(box_exp, text='Phương án đã xử lý của nền chính:').grid(row=7, column=0, sticky='w', pady=5)
        self.main_treatment_var = tk.StringVar(value='Chưa xử lý')
        self.cb_main_treatment = ttk.Combobox(
            box_exp, textvariable=self.main_treatment_var,
            values=('Chưa xử lý', 'PVD', 'SD', 'Chờ lún', 'Cơ học', 'CDM'),
            state='readonly', width=18)
        self.cb_main_treatment.grid(row=7, column=1, sticky='w', pady=5)
        self.cb_main_treatment.bind('<<ComboboxSelected>>', self.toggle_main_treatment)
        self.main_soils_button = ttk.Button(box_exp, text='Khai báo địa chất vùng đã xử lý',
                                            command=self.edit_main_zone_soils)
        self.main_soils_button.grid(row=8, column=0, columnspan=3, sticky='w', pady=5)
        ttk.Label(box_exp, text='PVD/SD/Chờ lún: tại vai; Cơ học: tại mép đáy đào; CDM: tại chân nền chính.',
                  foreground='#64748B').grid(row=9, column=0, columnspan=3, sticky='w')
        main_fields = (
            ('main_replacement_depth', 'Đào thay đất nền chính (m):', '0'),
            ('main_bamboo_depth', 'Cọc tre nền chính (m):', '0'),
            ('main_cajuput_depth', 'Cừ tràm nền chính (m):', '0'),
            ('main_cdm_depth', 'CDM nền chính (m):', '0'),
            ('main_age_days', 'Ngày từ khi xong nền chính đến hiện tại:', '0'),
            ('main_observed_residual_cm', 'Lún dư tại vai chính bên mở rộng (cm; có thể để trống):', ''),
        )
        self.main_entries = {}
        for row, (key, label, default) in enumerate(main_fields, 10):
            self.vars[key] = tk.StringVar(value=default)
            ttk.Label(box_exp, text=label).grid(row=row, column=0, sticky='w', pady=4)
            entry = ttk.Entry(box_exp, textvariable=self.vars[key], width=18)
            entry.grid(row=row, column=1, sticky='w', pady=4)
            self.main_entries[key] = entry
        ttk.Button(box_exp, text='Dự báo lún nền mở rộng',
                   command=self.calculate_expansion_forecast).grid(
                       row=16, column=0, columnspan=2, sticky='w', pady=(8, 4))
        forecast_frame = ttk.Frame(box_exp)
        forecast_frame.grid(row=17, column=0, columnspan=3, sticky='ew')
        columns = ('location', 'old_now', 'old_next', 'extension', 'total', 'remaining')
        self.expansion_forecast_tree = ttk.Treeview(
            forecast_frame, columns=columns, show='headings', height=7)
        for key, title, width in (
            ('location', 'Vị trí', 175), ('old_now', 'Dư cũ hiện tại (cm)', 105),
            ('old_next', 'Lún cũ tiếp (cm)', 100), ('extension', 'Lún mở rộng (cm)', 105),
            ('total', 'Tổng phát sinh (cm)', 110), ('remaining', 'Dư sau dự báo (cm)', 110)):
            self.expansion_forecast_tree.heading(key, text=title)
            self.expansion_forecast_tree.column(key, width=width, minwidth=width, stretch=False)
        scroll = ttk.Scrollbar(forecast_frame, orient='horizontal',
                               command=self.expansion_forecast_tree.xview)
        self.expansion_forecast_tree.configure(xscrollcommand=scroll.set)
        self.expansion_forecast_tree.pack(fill='x')
        scroll.pack(fill='x')
        # Keep Bxl immediately below the expansion width without overlapping rows.
        for child in box_exp.winfo_children():
            if child is bxl_frame:
                continue
            info=child.grid_info()
            if info and int(info.get('row',0)) >= 3:
                child.grid_configure(row=int(info['row'])+1)
        bxl_frame.grid_configure(row=3)
        self.expansion_details = tuple(
            child for child in box_exp.winfo_children()
            if child is not self.cb_has_expansion)

        box_other = ttk.LabelFrame(inner, text='4. Điều kiện địa chất thủy văn & Tính toán', padding=12)
        box_other.pack(fill='x', pady=5, padx=8)

        self.vars['ground_elevation'] = tk.StringVar(value='0.0')
        self.vars['water_elevation'] = tk.StringVar(value='0.0')
        self.vars['gamma_water'] = tk.StringVar(value='0.98')
        self.vars['method'] = tk.StringVar(value='Cc/Cs/Pc')
        self.vars['sublayer'] = tk.StringVar(value='1.0')
        self.vars['limit_ratio'] = tk.StringVar(value='0.15')




        ttk.Label(box_other, text='Cao độ mực nước ngầm MNN (m):').grid(row=1, column=0, sticky='w', pady=5)
        ttk.Entry(box_other, textvariable=self.vars['water_elevation'], width=18).grid(row=1, column=1, sticky='w', pady=5)

        ttk.Label(box_other, text='Dung trọng nước γw (T/m³):').grid(row=2, column=0, sticky='w', pady=5)
        ttk.Entry(box_other, textvariable=self.vars['gamma_water'], width=18).grid(row=2, column=1, sticky='w', pady=5)

        # Settlement method is selected in the calculation settings dialog.
        cb_m = ttk.Combobox(box_other, textvariable=self.vars['method'], values=('Cc/Cs/Pc', 'e–logP', 'Mv–logP'), state='readonly', width=18)
        # Retain the existing control and variable without displaying a duplicate selector.

        ttk.Label(box_other, text='Phân tố tối đa dz (m):').grid(row=4, column=0, sticky='w', pady=5)
        ttk.Entry(box_other, textvariable=self.vars['sublayer'], width=18).grid(row=4, column=1, sticky='w', pady=5)

        ttk.Label(box_other, text='Tỷ số giới hạn Δp/p₀:').grid(row=5, column=0, sticky='w', pady=5)
        ttk.Entry(box_other, textvariable=self.vars['limit_ratio'], width=18).grid(row=5, column=1, sticky='w', pady=5)
        box_other.columnconfigure(1, weight=1)

        for k in ['gamma_fill', 'h_design', 'h_kcad', 'crest_B', 'slope_M', 'counterweight_height',
                  'counterweight_width', 'counterweight_m', 'expansion_width',
                  'expansion_h_design', 'expansion_h_kcad', 'expansion_slope_m',
                  'expansion_gamma_fill',
                  'main_replacement_depth', 'main_bamboo_depth',
                  'main_cajuput_depth', 'main_cdm_depth',
                  'ground_elevation', 'water_elevation']:
            self.vars[k].trace_add('write', lambda *_: (self.draw_live_diagram(), self.refresh_soils()))
        for key, base in (('expansion_h_kcad', 'h_kcad'),
                          ('expansion_gamma_fill', 'gamma_fill')):
            self.vars[base].trace_add('write',
                lambda *_, k=key, b=base: self._sync_expansion_source(k, b))

        self.toggle_cw()
        self.toggle_expansion()

    def toggle_cw(self):
        state = 'normal' if hasattr(self, 'has_cw') and self.has_cw.get() else 'disabled'
        expanded = hasattr(self, 'has_expansion') and self.has_expansion.get()
        positions = (['Tim đường chính', 'Vai đường chính phải', 'Chân đường chính phải']
                     if expanded else ['Tim đường', 'Vai đường', 'Chân đường'])
        if state == 'normal':
            positions.extend(('Vai bệ phản áp', 'Chân bệ phản áp'))
        if expanded:
            positions.extend(('Vai đường chính trái', 'Chân đường chính trái'))
            if self.expansion_side.get() in ('Phải', 'Hai bên'):
                positions.extend(('Vai nền mở rộng phải', 'Chân nền mở rộng phải'))
            if self.expansion_side.get() in ('Trái', 'Hai bên'):
                positions.extend(('Vai nền mở rộng trái', 'Chân nền mở rộng trái'))
            if state == 'normal':
                positions.extend(('Vai bệ phản áp trái', 'Chân bệ phản áp trái'))
        if hasattr(self, 'ent_cw_h'):
            self.ent_cw_h.config(state=state)
            self.ent_cw_l.config(state=state)
            self.ent_cw_a.config(state=state)
        if hasattr(self, 'cb_before_pos'):
            self.cb_before_pos.configure(values=positions)
            if self.before_pos_var.get() not in positions:
                self.before_pos_var.set(positions[0])
        if hasattr(self, 'cb_post_pos'):
            self.cb_post_pos.configure(values=positions)
            if self.post_pos_var.get() not in positions:
                self.post_pos_var.set(positions[0])
        self.draw_live_diagram()

    def toggle_expansion(self, _event=None):
        enabled = self.has_expansion.get()
        if hasattr(self, 'cdm_scope_var'):
            self.cdm_scope_var.set('Nền mở rộng' if enabled else 'Nền đường')
            self.project.cdm_scope = self.cdm_scope_var.get()
        for child in self.expansion_details:
            if enabled:
                child.grid()
            else:
                child.grid_remove()
        self.cb_expansion_side.configure(state='readonly' if enabled else 'disabled')
        self.ent_expansion_width.configure(state='normal' if enabled else 'disabled')
        self.toggle_expansion_sources()
        self.toggle_main_treatment()
        self.toggle_cw()
        if hasattr(self, 'before_pos_var') and not getattr(self, '_loading_project', False):
            self.invalidate_assessment()

    def toggle_main_treatment(self, _event=None):
        enabled = self.has_expansion.get()
        treatment = self.main_treatment_var.get()
        self.cb_main_treatment.configure(state='readonly' if enabled else 'disabled')
        self.main_soils_button.configure(
            state='normal' if enabled and treatment in ('PVD', 'SD', 'Chờ lún')
            else 'disabled')
        for key, entry in self.main_entries.items():
            active = enabled and ((treatment == 'CDM' if key == 'main_cdm_depth'
                                  else treatment == 'Cơ học') if key.endswith('_depth') else True)
            entry.configure(state='normal' if active else 'disabled')
        if _event is not None and hasattr(self, 'before_pos_var'):
            self.invalidate_assessment()
        self.draw_live_diagram()

    def edit_main_zone_soils(self):
        if not self.project.soils:
            messagebox.showinfo('Địa chất vùng xử lý',
                                'Khai báo địa chất chung trước khi khai báo vùng đã xử lý.', parent=self)
            return
        if not self.project.main_soils:
            self.project.main_soils = deepcopy(self.project.soils)
        dialog = tk.Toplevel(self)
        dialog.title('Địa chất vùng đã xử lý của nền chính')
        dialog.geometry('640x380')
        dialog.transient(self)
        ttk.Label(dialog, text='PVD/SD/Chờ lún: khai báo chỉ tiêu từng lớp; bề dày giữ như địa chất chung.').pack(
            anchor='w', padx=12, pady=10)
        listing = tk.Listbox(dialog, height=12, font=(UI_FONT, 10))
        listing.pack(fill='both', expand=True, padx=12)

        def refresh():
            listing.delete(0, 'end')
            for i, soil in enumerate(self.project.main_soils):
                listing.insert('end', f'{i+1}. {soil.name}  |  H={soil.thickness:.2f} m  |  '
                                      f'γ={soil.gamma:.2f}  |  Cc={soil.cc:.3f}  |  Cv={soil.cv}')

        def edit(_event=None):
            selection = listing.curselection()
            if not selection:
                return
            idx = selection[0]
            def commit(soil):
                soil.thickness = self.project.soils[idx].thickness
                self.project.main_soils[idx] = soil
                refresh()
                self.invalidate_assessment()
                self.draw_live_diagram()
            SoilDialog(dialog, self.project.main_soils[idx], commit,
                       self.vars['method'].get(), self.main_treatment_var.get())

        listing.bind('<Double-1>', edit)
        controls = ttk.Frame(dialog)
        controls.pack(pady=8)
        ttk.Button(controls, text='Sửa lớp đã chọn', command=edit).pack(side='left', padx=4)
        def copy_common():
            self.project.main_soils = deepcopy(self.project.soils)
            refresh()
            self.invalidate_assessment()
        ttk.Button(controls, text='Sao chép địa chất',
                   command=copy_common).pack(side='left', padx=4)
        refresh()

    def _show_expansion_forecast(self, results):
        tree = self.expansion_forecast_tree
        tree.delete(*tree.get_children())
        for result in results:
            tree.insert('', 'end', values=(
                result['vị_trí'],
                f"{result['lún_dư_cũ_hiện_tại_cm']:.2f}",
                f"{result['lún_cũ_phát_sinh_cm']:.2f}",
                f"{result['lún_do_mở_rộng_cm']:.2f}",
                f"{result['lún_phát_sinh_tổng_cm']:.2f}",
                f"{result['lún_dư_sau_dự_báo_cm']:.2f}",
            ))

    @calculation_indicator
    def calculate_expansion_forecast(self):
        try:
            self.collect()
            if self.project.expansion_width <= 0:
                raise ValueError('Bật nền mở rộng để dự báo lún theo vùng.')
            days = number(self.vars['assessment_days'].get(), 'Thời gian dự báo')
            results = self._calculate_model(expansion_settlement_forecast, self.project, days)
            self._show_expansion_forecast(results)
            self._cad_natural_totals = [row['lún_dư_sau_dự_báo_cm'] for row in results]
            self.draw_live_diagram()
            self.report_result('Dự báo lún nền mở rộng', '\n'.join(
                f'{row["vị_trí"]}: Sᵣ = {row["lún_dư_sau_dự_báo_cm"]:.2f} cm'
                for row in results))
        except Exception as exc:
            self.report_result('Dự báo lún nền mở rộng', str(exc), error=True)
            messagebox.showerror('Dự báo lún nền mở rộng', str(exc), parent=self)

    def _sync_expansion_source(self, key, base):
        if self.expansion_use_main[key].get():
            self.vars[key].set(self.vars[base].get())

    def toggle_expansion_sources(self):
        enabled = self.has_expansion.get()
        for key, entry in self.expansion_entry_by_key.items():
            inherited = key in self.expansion_use_main and self.expansion_use_main[key].get()
            if inherited:
                base = 'h_kcad' if key == 'expansion_h_kcad' else 'gamma_fill'
                self._sync_expansion_source(key, base)
            entry.configure(state='normal' if enabled and not inherited else 'disabled')
        self.draw_live_diagram()

    # ==========================================================================
    # BƯỚC 3: BẢNG ĐỊA TẦNG CHO PHÉP NHẬP TRỰC TIẾP BỀ DÀY LỚP ĐẤT
    # ==========================================================================
    def _build_tab_soils(self):
        scroll_frame = _PopupScrollFrame(self.tab_soils)
        scroll_frame.pack(fill='both', expand=True)
        inner = scroll_frame.scrollable_frame
        top_bar = ttk.Frame(inner)
        top_bar.pack(fill='x', pady=(0, 6))

        lbl = ttk.Label(top_bar, text="DANH SÁCH ĐỊA TẦNG ĐỊA CHẤT", font=(UI_FONT, 10, 'bold'), foreground='#1E3A8A')
        lbl.pack(side='left')
        
        lbl_hint = ttk.Label(top_bar, text="(Nhấp đúp chuột vào ô 'Dày H (m)' để nhập trực tiếp)", font=(UI_FONT, 9, 'italic'), foreground='#2563EB')
        lbl_hint.pack(side='left', padx=10)

        mnn_info = ttk.Frame(top_bar)
        mnn_info.pack(side='right')
        ttk.Label(mnn_info, text="Ztn:", font=(UI_FONT, 9)).pack(side='left')
        ttk.Label(mnn_info, textvariable=self.vars['ground_elevation'], font=(UI_FONT, 9, 'bold'), foreground='#1E293B').pack(side='left', padx=(2, 10))
        ttk.Label(mnn_info, text="MNN:", font=(UI_FONT, 9)).pack(side='left')
        ttk.Label(mnn_info, textvariable=self.vars['water_elevation'], font=(UI_FONT, 9, 'bold'), foreground='#0284C7').pack(side='left', padx=2)
        ttk.Label(mnn_info, text="m", font=(UI_FONT, 9)).pack(side='left')

        borehole_bar = ttk.Frame(inner)
        borehole_bar.pack(fill='x', pady=(0, 8))
        ttk.Button(borehole_bar, text='Nhập lỗ khoan…', command=self.open_borehole_input,
                   style='Accent.TButton').pack(side='left')
        self.borehole_summary = tk.StringVar()
        ttk.Label(borehole_bar, textvariable=self.borehole_summary).pack(side='left', padx=12)

        soil_container = ttk.Frame(inner)
        soil_container.pack(fill='both', expand=True)

        style = ttk.Style(self)
        self._soil_body_font = tkfont.Font(self, family=UI_FONT, size=9)
        self._soil_heading_font = tkfont.Font(self, family=UI_FONT, size=9, weight='bold')
        self._soil_stripe_colors = configure_treeview_style(
            style, 'Soil.Treeview', heading_bg='#E4EDF3', font_size=9,
            row_height=max(23, self._soil_body_font.metrics('linespace') + 5))

        cols = ('stt', 'name', 'description', 'thick', 'z_bot', 'gamma', 'cat',
                'drain', 'e0', 'cc', 'cs', 'pc', 'co',
                'phi_cu_effective', 'source')
        self.soil_tree = ttk.Treeview(soil_container, columns=cols, show='headings', selectmode='browse', style="Soil.Treeview")
        
        headers = ['STT', 'Tên lớp đất', 'Mô tả', '✎ Dày H (m)', 'CĐ đáy (m)',
                   'γ (T/m³)', 'Loại đất', 'Thoát nước',
                   'e₀', 'Cc', 'Cs', 'Pc (T/m²)', 'Co (T/m²)', 'φ′ CU (độ)', 'Nguồn giá trị']
        widths = [42, 80, 190, 68, 75, 65, 75, 80,
                  55, 55, 55, 80, 80, 70, 150]
        self._soil_column_caps = [48, 170, 440, 80, 88, 85, 120, 110,
                                  85, 85, 85, 95, 95, 80, 220]
        self._soil_column_min = widths

        for c, h, w in zip(cols, headers, widths):
            display = _compact_heading(h, self._soil_heading_font, limit=max(65,w))
            width = max(w, _heading_width(display, self._soil_heading_font) + 12)
            self.soil_tree.heading(c, text=display, anchor='w' if c in ('name', 'description') else 'center')
            self.soil_tree.column(c, width=width, minwidth=width,
                                  anchor='w' if c in ('name', 'description') else 'center',
                                  stretch=False)

        s_scroll_y = ttk.Scrollbar(soil_container, orient='vertical', command=self.soil_tree.yview)
        s_scroll_x = ttk.Scrollbar(soil_container, orient='horizontal', command=self.soil_tree.xview)
        self._soil_h_cells = []
        self._soil_h_job = None
        self.soil_tree.configure(
            yscrollcommand=lambda first, last: (s_scroll_y.set(first, last), self._schedule_soil_h_cells()),
            xscrollcommand=lambda first, last: (s_scroll_x.set(first, last), self._schedule_soil_h_cells()))
        self.soil_tree.bind('<Configure>', lambda _e: self._schedule_soil_h_cells(), add='+')
        
        soil_container.rowconfigure(0, weight=1)
        soil_container.columnconfigure(0, weight=1)
        self.soil_tree.grid(row=0, column=0, sticky='nsew')
        s_scroll_y.grid(row=0, column=1, sticky='ns')
        s_scroll_x.grid(row=1, column=0, sticky='ew')
        
        # BẮT SỰ KIỆN NHẤP ĐÚP CHUỘT: SỬA TRỰC TIẾP Ô DÀY H HOẶC MỞ HỘP THOẠI CHI TIẾT
        self.soil_tree.bind('<Double-1>', self._on_soil_double_click)

        btn_soil = ttk.Frame(inner)
        btn_soil.pack(fill='x', pady=(10, 0))
        ttk.Button(btn_soil, text='+ Thêm lớp đất', command=self.add_soil, style='Accent.TButton').pack(side='left', padx=4)
        ttk.Button(btn_soil, text='Sửa chỉ tiêu đất', command=self.edit_soil).pack(side='left', padx=4)
        ttk.Button(btn_soil, text='🗑 Xóa lớp', command=self.delete_soil).pack(side='left', padx=4)

    def open_borehole_input(self):
        def commit(candidate):
            self.project.borehole_name = candidate.borehole_name
            self.project.soils = candidate.soils
            self.project.ground_elevation = candidate.ground_elevation
            self.vars['ground_elevation'].set(str(candidate.ground_elevation))
            self.invalidate_assessment()
            self.refresh_soils()
        BoreholeDialog(self, self.project, self.vars['ground_elevation'].get(), commit)

    def _on_soil_double_click(self, event):
        region = self.soil_tree.identify_region(event.x, event.y)
        if region != 'cell': return
        column = self.soil_tree.identify_column(event.x)
        item_id = self.soil_tree.identify_row(event.y)
        if not item_id: return
        idx = int(item_id)

        # Cột #4 tương ứng với cột Dày H (m) -> Cho phép nhập trực tiếp
        if column == '#4':
            self._spawn_inline_thickness_entry(idx, item_id, column)
        else:
            self.edit_soil()

    def _spawn_inline_thickness_entry(self, idx: int, item_id: str, column: str):
        bbox = self.soil_tree.bbox(item_id, column)
        if not bbox: return
        x, y, w, h = bbox
        cur_val = f"{self.project.soils[idx].thickness:.2f}"
        
        ent = ttk.Entry(self.soil_tree, font=self._soil_body_font, justify='center')
        ent.place(x=x, y=y, width=w, height=h)
        ent.insert(0, cur_val)
        ent.select_range(0, 'end')
        ent.focus_set()

        def save_and_destroy(_e=None):
            if not ent.winfo_exists(): return
            val_str = ent.get().strip()
            ent.destroy()
            try:
                new_thick = float(val_str)
                if new_thick <= 0: raise ValueError
                self.project.soils[idx].thickness = new_thick
                self.refresh_soils()
                self.invalidate_assessment()
                self.draw_live_diagram()
            except Exception:
                self.refresh_soils()

        ent.bind('<Return>', save_and_destroy)
        ent.bind('<FocusOut>', save_and_destroy)
        ent.bind('<Escape>', lambda _e: ent.destroy())

    def _schedule_soil_h_cells(self):
        if getattr(self, '_soil_h_job', None) is None:
            self._soil_h_job = self.after_idle(self._draw_soil_h_cells)

    def _draw_soil_h_cells(self):
        self._soil_h_job = None
        for cell in self._soil_h_cells:
            cell.destroy()
        self._soil_h_cells = []
        for item_id in self.soil_tree.get_children():
            bbox = self.soil_tree.bbox(item_id, 'thick')
            if not bbox:
                continue
            x, y, width, height = bbox
            value = self.soil_tree.set(item_id, 'thick')
            cell = tk.Label(self.soil_tree, text=value, bg='#FFF0BF', fg='#5C3B00',
                            font=self._soil_body_font, bd=0, cursor='xterm')
            cell.place(x=x, y=y, width=width, height=height)
            cell.bind('<Button-1>', lambda _e, row=item_id: self.soil_tree.selection_set(row))
            cell.bind('<Double-1>', lambda _e, row=item_id:
                      self._spawn_inline_thickness_entry(int(row), row, 'thick'))
            cell.bind('<MouseWheel>', lambda e: self.soil_tree.yview_scroll(
                -1 if e.delta > 0 else 1, 'units'))
            self._soil_h_cells.append(cell)

    def refresh_soils(self):
        self.soil_tree.delete(*self.soil_tree.get_children())
        apply_row_stripes(self.soil_tree, getattr(self, '_soil_stripe_colors', None))
        z_tn = number_or_zero(self.vars.get('ground_elevation', tk.StringVar(value='0.0')).get())
        if hasattr(self, 'borehole_summary'):
            self.borehole_summary.set(
                f'Lỗ khoan: {self.project.borehole_name or "—"} · '
                f'Chiều sâu tính: {self.project.borehole_depth:.3f} m · '
                f'Cao độ: {z_tn:.3f} m')
        cum_depth = 0.0

        for i, s in enumerate(self.project.soils):
            s.no = i + 1
            from weak_soil import initial_void_ratio
            displayed_e0 = initial_void_ratio(s)
            cum_depth += s.thickness
            z_bottom = z_tn - cum_depth
            is_clay = (s.category == 'Đất dính' or s.cc > 0)
            radial = (hasattr(self, 'treatment_group') and self.treatment_group.get() != 'mechanical'
                      and self.treatment_vars.get('treatment', tk.StringVar(value='Chờ lún')).get()
                      in ('PVD', 'SD'))
            ch_cv_val = f"{getattr(s, 'ch_cv', 2.0) if radial else 1.0:.2f}" if is_clay else "-"
            
            source_keys=[]
            for key,entry in s.parameter_sources.items():
                current=getattr(s,key,None)
                if isinstance(current,list):matches=all(v==entry.get('value') for v in current)
                else:matches=current==entry.get('value')
                if matches and entry.get('source')=='Thống kê':source_keys.append(key)
            source_hint='Thống kê: '+', '.join(source_keys) if source_keys else 'Nhập trực tiếp'
            self.soil_tree.insert('', 'end', iid=str(i), tags=('odd' if i % 2 else 'even',), values=(
                i + 1, s.name, getattr(s, 'description', ''), f"{s.thickness:.2f}", f"{z_bottom:.2f}", f"{s.gamma:.2f}", s.category,
                f"{s.drainage} mặt" if is_clay else "-",
                (f'{displayed_e0:.3f}' if displayed_e0 is not None else '—') if is_clay else '-', f'{s.cc:.3f}' if is_clay else '-',
                f'{s.cs:.3f}' if is_clay else '-', f'{s.pc:.2f}' if is_clay else '-',
                f'{s.co:.2f}' if is_clay else '-', f'{s.phi_cu_effective:.2f}' if s.phi_cu_effective is not None else '—', source_hint
            ))
        if hasattr(self,'drainage_parameter_tree'):self.refresh_drainage_parameters()
        for col_index, cid in enumerate(self.soil_tree['columns']):
            display = self.soil_tree.heading(cid, 'text')
            width = _heading_width(display, self._soil_heading_font) + 12
            for item in self.soil_tree.get_children():
                width = max(width, self._soil_body_font.measure(
                    str(self.soil_tree.item(item, 'values')[col_index])) + 12)
            width = min(self._soil_column_caps[col_index],
                        max(self._soil_column_min[col_index], width))
            self.soil_tree.column(cid, width=width, minwidth=width, stretch=False)
        self._schedule_soil_h_cells()
        self._schedule_unpenetrated_state()
        self.draw_live_diagram()

    def add_soil(self):
        def commit(s):
            self.project.soils.append(s)
            self.invalidate_assessment()
            self.refresh_soils()
        # Chuyển độ dày mặc định 2.0 để SoilDialog không bị trống giá trị
        SoilDialog(self, Soil(name=f'Lớp {len(self.project.soils)+1}', thickness=2.0), commit,
                   self.vars.get('method', tk.StringVar(value='Cc/Cs/Pc')).get(), self._soil_dialog_treatment())

    def _soil_dialog_treatment(self):
        if self.treatment_group.get() == 'mechanical':
            return 'Gia cường cơ học'
        return self.treatment_vars['treatment'].get()

    def edit_soil(self):
        sel = self.soil_tree.selection()
        if not sel: return
        idx = int(sel[0])
        def commit(s):
            previous=self.project.soils[idx]
            self.project.soils[idx] = s
            workspace=getattr(self,'_ai_analysis_workspace',None)
            if workspace is not None and self.design_mode.get()=='TÍNH MỘT ĐOẠN':
                from ai_analysis_data import SOIL_KEYS
                for material in workspace.state['materials']:
                    if material['code'].casefold()!=previous.name.casefold():continue
                    material['code']=s.name
                    for key in SOIL_KEYS:
                        if key not in ('name','thickness') and getattr(s,key,None)!=getattr(previous,key,None):
                            material['values'][key]=deepcopy(getattr(s,key))
                    material['average_edited']=True
                    material['category_source']='Người dùng sửa trong Địa tầng'
                if s.statistics_id and s.category in ('Đất dính','Đất rời'):
                    self.project.geology_statistics.setdefault('layer_categories',{})[s.statistics_id]=s.category
                workspace.invalidate('geology_approved')
            self.refresh_soils()
            self.invalidate_assessment()
        SoilDialog(self, self.project.soils[idx], commit,
                   self.vars.get('method', tk.StringVar(value='Cc/Cs/Pc')).get(), self._soil_dialog_treatment())

    def delete_soil(self):
        sel = self.soil_tree.selection()
        if sel:
            self.project.soils.pop(int(sel[0]))
            self.refresh_soils()
            self.invalidate_assessment()

    def _build_tab_before(self):
        scroll_frame = _PopupScrollFrame(self.tab_before)
        scroll_frame.pack(fill='both', expand=True)
        inner = scroll_frame.scrollable_frame
        box_hbl = ttk.LabelFrame(inner, text='1. Chiều cao tính toán Htt & Bù lún Hbl', padding=10)
        box_hbl.pack(fill='x', pady=(0, 4))
        
        self.htt_label = tk.StringVar(value='Htk = 3.00 m  |  Hkcad = 0.15 m  |  Hbl = 0.00 m  ==>  Htt = 3.15 m')
        ttk.Label(box_hbl, textvariable=self.htt_label, font=(UI_FONT, 10, 'bold'), foreground='#B45309').pack(anchor='w', pady=(0, 6))
        
        f_row = ttk.Frame(box_hbl)
        f_row.pack(fill='x', pady=2)
        
        ttk.Label(f_row, text='Hệ số m: S = m × Sc:').pack(side='left')
        self.settlement_factor_var = tk.StringVar(value='1.2')
        ttk.Combobox(f_row, textvariable=self.settlement_factor_var, values=('1.1', '1.2', '1.3', '1.4', '1.5', '1.6', '1.7'),
                     width=6, state='readonly').pack(side='left', padx=6)
                     
        ttk.Button(f_row, text='Tính chiều cao bù lún', command=self.calculate_hbl).pack(side='left', padx=10)

        box_calc = ttk.LabelFrame(inner, text='2. Kiểm toán độ lún tự nhiên trước xử lý', padding=10)
        box_calc.pack(fill='x', pady=4)
        r_bar = ttk.Frame(box_calc)
        r_bar.pack(fill='x', pady=2)
        ttk.Button(r_bar, text='Tính lún cố kết', command=self.calculate_settlement,
                   style='Accent.TButton').pack(side='left', padx=4)
        ttk.Button(r_bar, text='Tính lún theo thời gian', command=self.calculate_before).pack(side='left', padx=4)
        
        ttk.Label(r_bar, text='Thời gian t lún tự nhiên (ngày):').pack(side='left', padx=(10, 6))
        self.days = self.vars['assessment_days']
        ttk.Entry(r_bar, textvariable=self.days, width=8).pack(side='left')

        self.result_table_frame = ttk.LabelFrame(inner, text='Bảng kết quả kiểm toán lún tự nhiên', padding=8)
        self.result_table_frame.pack(fill='x', pady=(6, 2))
        
        f_tbl_head = ttk.Frame(self.result_table_frame)
        f_tbl_head.pack(fill='x', pady=(0, 6))
        self.lbl_tbl_title = ttk.Label(f_tbl_head, text='Kết quả phân tố đất · Tim', font=(UI_FONT, 9, 'bold'), foreground='#1E293B')
        self.lbl_tbl_title.pack(side='left')
        
        position_bar = ttk.Frame(f_tbl_head)
        position_bar.pack(side='right', padx=(8, 0))
        ttk.Label(position_bar, text='Vị trí tính toán:').pack(side='left', padx=(0, 2))
        self.before_pos_var = tk.StringVar(value='Tim đường')
        self.cb_before_pos = ttk.Combobox(position_bar, textvariable=self.before_pos_var,
            values=('Tim đường', 'Vai đường', 'Chân đường'), state='readonly', width=16)
        self.cb_before_pos.pack(side='left')
        self.cb_before_pos.bind('<<ComboboxSelected>>', self._on_before_position_change)

        self.ha_badge = tk.Label(f_tbl_head, text='ha = --- m', font=(UI_FONT, 9, 'bold'),
                                 fg='#0369A1', bg='#E0F2FE', padx=8, pady=2, relief='solid', bd=1)
        self.ha_badge.pack(side='right')

        result_area = ttk.Frame(self.result_table_frame)
        result_area.pack(fill='both', expand=True)
        result_area.columnconfigure(0, weight=1)
        result_area.rowconfigure(0, weight=1)
        tree_scroll_x = ttk.Scrollbar(result_area, orient='horizontal')
        tree_scroll_y = ttk.Scrollbar(result_area, orient='vertical')
        
        style = ttk.Style(self)
        configure_treeview_style(style, 'Res.Treeview', font_size=9, row_height=21)

        self.result_tree = ttk.Treeview(result_area, show='headings',
                                        xscrollcommand=tree_scroll_x.set, yscrollcommand=tree_scroll_y.set,
                                        style="Res.Treeview")
        self.result_tree.bind('<Configure>',
                              lambda _event: self._resize_tree_columns(self.result_tree), add='+')
        tree_scroll_x.config(command=self.result_tree.xview)
        tree_scroll_y.config(command=self.result_tree.yview)
        
        self.result_tree.grid(row=0, column=0, sticky='nsew')
        tree_scroll_y.grid(row=0, column=1, sticky='ns')
        tree_scroll_x.grid(row=1, column=0, sticky='ew')

    # ==========================================================================
    # BƯỚC 4: TÍNH LÚN THEO THỜI GIAN ĐẾN U = 99% (THEO THÁNG)
    # ==========================================================================
    @calculation_indicator
    def calculate_before(self):
        """Bảng và biểu đồ St(t) lấy cùng kết quả cố kết, đến U=99%."""
        try:
            self.config(cursor='watch')
            self.status_text.set('Đang xử lý: lún theo thời gian…')
            self.update_idletasks()
            self.collect()
            pos_str = self.before_pos_var.get() if hasattr(self, 'before_pos_var') else 'Tim đường'
            axis_idx = next((i for i, (name, _) in enumerate(axes(self.project))
                             if name == pos_str), 0)
            d_eval = number(self.days.get(), 'Thời gian')
            if d_eval < 0:
                raise ValueError('Thời gian đánh giá phải không âm.')
            _, initial = self._calculate_model(consolidation, self.project, 0.0,
                                               radial=False, axis_index=axis_idx)
            sc_final_cm = initial['Sc_cuối_cm']
            t_99 = self._calculate_model(time_to_consolidation, self.project,
                                         0.99, axis_index=axis_idx)
            times = {0.0, d_eval, t_99}
            if t_99 > 0:
                for target in (.05, .10, .15, .20, .30, .40, .50, .60,
                               .70, .80, .85, .90, .95):
                    low, high = 0.0, t_99
                    for _ in range(28):
                        mid = (low + high) / 2.0
                        _, value = self._calculate_model(consolidation, self.project, mid,
                                                         radial=False, axis_index=axis_idx)
                        if value['U_%'] < target * 100.0:
                            low = mid
                        else:
                            high = mid
                    times.add(high)
            else:
                times.add(max(1.0, d_eval))
            rows, chart_rows = [], []
            for day in sorted(times):
                _, value = self._calculate_model(consolidation, self.project, day,
                                                 radial=False, axis_index=axis_idx)
                month, year = day / 30.0, day / 365.25
                st_m = value['St_t_cm'] / 100.0
                residual_m = value['Sc_dư_cm'] / 100.0
                rows.append([f'{month:.2f}', f'{year:.2f}', f"{value['U_%']:.2f}%",
                             f"{value['Tv_avg']:.2f}", f'{st_m:.2f}', f'{residual_m:.2f}'])
                chart_rows.append({'ngày': day, 'tháng': month, 'năm': year,
                                   'u_pct': value['U_%'], 'tv': value['Tv_avg'],
                                   'sc_m': value['Sc_t_cm'] / 100.0,
                                   'st_m': st_m, 'dsc_m': residual_m})
            if hasattr(self, 'lbl_tbl_title'):
                self.lbl_tbl_title.config(text=f'Bảng lún theo thời gian · {pos_str}')
            self.show_table(self.result_tree,
                            ['Thời gian (tháng)', 'Thời gian (năm)', 'U (%)', 'Tv',
                             'St (m)', 'Sc dư (m)'], rows)
            self.last_result_view = 'time'
            _, res_eval = self._calculate_model(consolidation, self.project, d_eval,
                                                radial=False, axis_index=axis_idx)
            self._update_natural_cad_residual(d_eval, axis_idx, res_eval)
            if self._cad_settlement_elements is None:
                _, _, self._cad_settlement_elements = settlement(self.project, return_details=True)
            self._show_residual_for_step()
            self.draw_live_diagram()
            self.chart_data = {'type': 'natural', 'time_unit': 'years',
                               'assessment_day': d_eval, 'rows': chart_rows}
            self.render_chart()
            self.card_sc.configure(text=f'{sc_final_cm:.2f} cm')
            self.card_st.configure(text=f"{res_eval['St_t_cm']:.2f} cm")
            self.cache_step_result(3)
            text = (f'{pos_str}: S_c = {sc_final_cm:.2f} cm; '
                    f'U = 99% tại t = {t_99 / 365.25:.2f} năm.' if t_99 > 0 else
                    f'{pos_str}: không phát sinh lún cố kết; St = {res_eval["St_t_cm"]:.2f} cm.')
            self.status_text.set(text)
            self.report_result('Lún theo thời gian', text)
        except Exception as exc:
            self.report_result('Lún theo thời gian', str(exc), error=True)
            messagebox.showerror('Lỗi tính lún theo thời gian', str(exc))
        finally:
            self.config(cursor='')

    def _on_before_position_change(self, _event=None):
        self.invalidate_assessment()

    def _build_tab_after(self):
        self.treated_pdf_button = self.workspace_pdf_button
        scroll_frame = _PopupScrollFrame(self.tab_after)
        scroll_frame.pack(fill='both', expand=True)
        inner = scroll_frame.scrollable_frame
        self.cb_treatment_scope = self._build_treatment_scope_selector(inner)

        box_sol = self.box_sol = ttk.LabelFrame(inner, text='1. Phương án xử lý & Gia tải', padding=8)
        box_sol.pack(fill='x', pady=4, padx=8)
        f1 = ttk.Frame(box_sol)
        f1.pack(fill='x', pady=2)
        ttk.Label(f1, text='Phương án:').pack(side='left')
        mode = self.treatment_vars['treatment'] = tk.StringVar(value='PVD')
        ttk.Combobox(f1, textvariable=mode, values=('Chờ lún', 'PVD', 'SD'), state='readonly', width=12).pack(side='left', padx=6)

        self.treatment_group = tk.StringVar(value='drainage')
        self.box_mechanical = ttk.LabelFrame(inner, text='1. Đào thay đất và gia cường bằng cọc', padding=8)
        self.mechanical_enabled = {}
        self.mechanical_depth_entries = {}
        for row, (key, label, maximum) in enumerate((
                ('replacement_depth', 'Đào thay đất', 4),
                ('bamboo_depth', 'Cọc tre', 3),
                ('cajuput_depth', 'Cọc cừ tràm', 4))):
            flag = self.mechanical_enabled[key] = tk.BooleanVar(value=False)
            ttk.Checkbutton(self.box_mechanical, text=label, variable=flag,
                            command=self.update_treatment_visibility).grid(row=row, column=0, sticky='w', pady=2)
            self.treatment_vars[key] = tk.StringVar(value='0')
            ttk.Label(self.box_mechanical, text=f'Chiều sâu (m), tối đa {maximum}:').grid(row=row, column=1, padx=8)
            depth_entry = ttk.Entry(self.box_mechanical, textvariable=self.treatment_vars[key], width=9)
            depth_entry.grid(row=row, column=2)
            self.mechanical_depth_entries[key] = depth_entry
            self.treatment_vars[key].trace_add('write', lambda *_: self.draw_live_diagram())
        self.mechanical_wait = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.box_mechanical, text='Kết hợp chờ lún', variable=self.mechanical_wait,
                        command=self.update_treatment_visibility).grid(row=3, column=0, sticky='w', pady=3)
        self.mechanical_surcharge = tk.BooleanVar(value=False)
        self.cb_mechanical_surcharge = ttk.Checkbutton(
            self.box_mechanical, text='Có gia tải trước',
            variable=self.mechanical_surcharge, command=self.update_treatment_visibility)
        self.cb_mechanical_surcharge.grid(row=4, column=0, sticky='w', pady=3)
        
        self.surcharge_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(f1, text='Có gia tải trước', variable=self.surcharge_enabled,
                        command=self.draw_live_diagram).pack(side='left', padx=8)
        
        self.vacuum_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(f1, text='Có hút chân không', variable=self.vacuum_enabled,
                        command=self.draw_live_diagram).pack(side='left', padx=8)

        self.box_horiz_drain = ttk.LabelFrame(inner, text='2. Giải pháp thoát nước ngang mặt đất tự nhiên', padding=8)

        self.treatment_vars['horizontal_drain_type'] = tk.StringVar(value='Bấc thấm ngang')
        self.treatment_vars['h_sand_cushion'] = tk.StringVar(value='0.5')
        self.vars['sand_cushion_days'] = tk.StringVar(value='5.0')

        f_hd1 = ttk.Frame(self.box_horiz_drain)
        f_hd1.pack(fill='x', pady=2)
        ttk.Label(f_hd1, text='Chọn loại thoát nước ngang:', font=(UI_FONT, 9, 'bold')).pack(side='left')
        cb_hd = ttk.Combobox(f_hd1, textvariable=self.treatment_vars['horizontal_drain_type'],
                             values=('Bấc thấm ngang', 'Lớp đệm cát'), state='readonly', width=18)
        cb_hd.pack(side='left', padx=8)

        f_hd2 = ttk.Frame(self.box_horiz_drain)
        f_hd2.pack(fill='x', pady=4)

        self.lbl_h_sc = ttk.Label(f_hd2, text='Chiều dày đệm cát h (m):')
        self.lbl_h_sc.pack(side='left')
        self.ent_h_sc = ttk.Entry(f_hd2, textvariable=self.treatment_vars['h_sand_cushion'], width=8)
        self.ent_h_sc.pack(side='left', padx=(4, 16))

        self.lbl_t_sc = ttk.Label(f_hd2, text='Thời gian thi công đệm cát Tdc (ngày):')
        self.lbl_t_sc.pack(side='left')
        self.ent_t_sc = ttk.Entry(f_hd2, textvariable=self.vars['sand_cushion_days'], width=8)
        self.ent_t_sc.pack(side='left', padx=4)

        self.box_stages = ttk.LabelFrame(inner, text='3. Lịch trình đắp phân kỳ', padding=8)
        self.box_stages.pack(fill='x', pady=4, padx=8)
        
        stage_grid = ttk.Frame(self.box_stages)
        stage_grid.pack(fill='x')
        for col, label in enumerate(('Giai đoạn', 'Chiều cao đợt (m)', 'Tốc độ (cm/ngày)', 'Chờ sau đắp (ngày)')):
            ttk.Label(stage_grid, text=label, font=(UI_FONT, 9, 'bold')).grid(row=0, column=col, padx=4, pady=4)
        
        self.stage_vars: list[list[tk.StringVar]] = []
        self.stage_flags = {2: tk.BooleanVar(value=False), 3: tk.BooleanVar(value=False)}
        self.stage_entries = []
        for row in range(1, 4):
            if row == 1:
                ttk.Label(stage_grid, text='H1').grid(row=row, column=0)
            else:
                ttk.Checkbutton(stage_grid, text=f'H{row}', variable=self.stage_flags[row],
                                command=self.refresh_stage_inputs).grid(row=row, column=0, sticky='w')
            
            trio = [
                tk.StringVar(value=f"{self.project.height:.2f}" if row == 1 else ""),
                tk.StringVar(value="10"),
                tk.StringVar(value="180" if row == 1 else "0")
            ]
            self.stage_vars.append(trio)
            widgets = []
            for col, var in enumerate(trio, 1):
                entry = ttk.Entry(stage_grid, textvariable=var, width=14)
                entry.grid(row=row, column=col, padx=4, pady=4)
                widgets.append(entry)
            self.stage_entries.append(widgets)

        self.box_surcharge = ttk.LabelFrame(inner, text='4. Thông số gia tải', padding=8)
        for i, k in enumerate(['surcharge_height', 'surcharge_gamma', 'surcharge_days']):
            self.treatment_vars[k] = tk.StringVar(value='1.0' if k == 'surcharge_height' else '1.8' if k == 'surcharge_gamma' else '180.0')
            lbl_txt = {'surcharge_height': 'Chiều cao gia tải hs (m)',
                       'surcharge_gamma': 'Dung trọng gia tải γs (T/m³)',
                       'surcharge_days': 'Thời gian duy trì tải (ngày)'}[k]
            ttk.Label(self.box_surcharge, text=lbl_txt).grid(row=i, column=0, sticky='w', pady=2)
            ent_s = ttk.Entry(self.box_surcharge, textvariable=self.treatment_vars[k], width=15)
            ent_s.grid(row=i, column=1, sticky='w', pady=2, padx=6)
            self.treatment_vars[k].trace_add('write', lambda *_: self.draw_live_diagram())

        self.box_vacuum = ttk.LabelFrame(inner, text='5. Thông số hút chân không', padding=8)
        for i, k in enumerate(['vacuum_pressure', 'vacuum_days']):
            self.treatment_vars[k] = tk.StringVar(value='8.0' if k == 'vacuum_pressure' else '180.0')
            lbl_txt = {'vacuum_pressure': 'Áp lực chân không P_vac (T/m²)',
                       'vacuum_days': 'Thời gian duy trì bơm (ngày)'}[k]
            ttk.Label(self.box_vacuum, text=lbl_txt).grid(row=i, column=0, sticky='w', pady=2)
            ent_v = ttk.Entry(self.box_vacuum, textvariable=self.treatment_vars[k], width=15)
            ent_v.grid(row=i, column=1, sticky='w', pady=2, padx=6)
            self.treatment_vars[k].trace_add('write', lambda *_: self.draw_live_diagram())

        self.box_pvd = ttk.LabelFrame(inner, text='6. Thông số bố trí Bấc thấm đứng (PVD)', padding=8)
        self.treatment_vars['pvd_spacing'] = tk.StringVar(value='1.2')
        self.treatment_vars['pvd_pattern'] = tk.StringVar(value='Tam giác')
        self.treatment_vars['pvd_diameter'] = tk.StringVar(value='6.62')
        self.treatment_vars['pvd_length'] = tk.StringVar(value='0.0')

        ttk.Label(self.box_pvd, text='Khoảng cách cắm d (m):', font=(UI_FONT, 9, 'bold'), foreground='#1E3A8A').grid(row=0, column=0, sticky='w', pady=4)
        self.ent_pvd_d = ttk.Entry(self.box_pvd, textvariable=self.treatment_vars['pvd_spacing'], width=12, font=(UI_FONT, 9, 'bold'))
        self.ent_pvd_d.grid(row=0, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(self.box_pvd, text='Sơ đồ cắm bấc:').grid(row=0, column=2, sticky='w', padx=(14, 0), pady=4)
        ttk.Combobox(self.box_pvd, textvariable=self.treatment_vars['pvd_pattern'],
                     values=('Tam giác', 'Hình vuông'), state='readonly', width=12).grid(row=0, column=3, sticky='w', padx=6, pady=4)

        ttk.Label(self.box_pvd, text='Đường kính dw (cm):').grid(row=1, column=0, sticky='w', pady=4)
        ttk.Entry(self.box_pvd, textvariable=self.treatment_vars['pvd_diameter'], width=12).grid(row=1, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(self.box_pvd, text='Chiều dài cắm L (m):').grid(row=1, column=2, sticky='w', padx=(14, 0), pady=4)
        self.ent_pvd_l = ttk.Entry(self.box_pvd, textvariable=self.treatment_vars['pvd_length'], width=12)
        self.ent_pvd_l.grid(row=1, column=3, sticky='w', padx=6, pady=4)

        self.box_sd = ttk.LabelFrame(inner, text='6. Thông số bố trí Cọc cát (SD)', padding=8)
        self.treatment_vars['sd_spacing'] = tk.StringVar(value='2.5')
        self.treatment_vars['sd_pattern'] = tk.StringVar(value='Tam giác')
        self.treatment_vars['sd_diameter'] = tk.StringVar(value='40.0')
        self.treatment_vars['sd_length'] = tk.StringVar(value='0.0')

        ttk.Label(self.box_sd, text='Khoảng cách cọc d (m):', font=(UI_FONT, 9, 'bold'), foreground='#B45309').grid(row=0, column=0, sticky='w', pady=4)
        self.ent_sd_d = ttk.Entry(self.box_sd, textvariable=self.treatment_vars['sd_spacing'], width=12, font=(UI_FONT, 9, 'bold'))
        self.ent_sd_d.grid(row=0, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(self.box_sd, text='Sơ đồ cắm cọc:').grid(row=0, column=2, sticky='w', padx=(14, 0), pady=4)
        ttk.Combobox(self.box_sd, textvariable=self.treatment_vars['sd_pattern'],
                     values=('Tam giác', 'Hình vuông'), state='readonly', width=12).grid(row=0, column=3, sticky='w', padx=6, pady=4)

        ttk.Label(self.box_sd, text='Đường kính cọc D (cm):').grid(row=1, column=0, sticky='w', pady=4)
        ttk.Entry(self.box_sd, textvariable=self.treatment_vars['sd_diameter'], width=12).grid(row=1, column=1, sticky='w', padx=6, pady=4)

        ttk.Label(self.box_sd, text='Chiều dài cọc L (m):').grid(row=1, column=2, sticky='w', padx=(14, 0), pady=4)
        self.ent_sd_l = ttk.Entry(self.box_sd, textvariable=self.treatment_vars['sd_length'], width=12)
        self.ent_sd_l.grid(row=1, column=3, sticky='w', padx=6, pady=4)

        self.box_hansbo = ttk.Frame(inner)
        box_ign = self.box_ign = ttk.LabelFrame(self.box_hansbo, text='Bỏ qua (Ignor)', padding=8)
        box_ign.pack(side='left', fill='both', expand=True, padx=(0, 4))
        
        box_inf = ttk.LabelFrame(self.box_hansbo, text='Hệ số ảnh hưởng (TCVN 9355)', padding=8)
        box_inf.pack(side='right', fill='both', expand=True, padx=(4, 0))

        for k in ['ignore_uv', 'ignore_fs', 'ignore_fr', 'drain_cw_enabled', 'drain_upper_boundary']:
            self.treatment_flags[k] = tk.BooleanVar(value=False)

        ttk.Checkbutton(box_ign, text='Bỏ qua cố kết đứng (Uv)', variable=self.treatment_flags['ignore_uv']).grid(row=0, column=0, sticky='w', pady=2)
        ttk.Checkbutton(box_ign, text='Bỏ qua xáo động (Fs)', variable=self.treatment_flags['ignore_fs'], command=self.toggle_influence).grid(row=1, column=0, sticky='w', pady=2)
        ttk.Checkbutton(box_ign, text='Bỏ qua cản thấm (Fr)', variable=self.treatment_flags['ignore_fr'], command=self.toggle_influence).grid(row=2, column=0, sticky='w', pady=2)

        self.treatment_vars['smear_ratio'] = tk.StringVar(value='2.0')
        self.treatment_vars['permeability_ratio'] = tk.StringVar(value='3.0')
        self.treatment_vars['khqw'] = tk.StringVar(value='0.0001')

        ttk.Label(box_inf, text='ds/dw:').grid(row=0, column=0, sticky='w', pady=2)
        self.ent_dsdw = ttk.Entry(box_inf, textvariable=self.treatment_vars['smear_ratio'], width=10)
        self.ent_dsdw.grid(row=0, column=1, pady=2, padx=4)

        ttk.Label(box_inf, text='Kh/Ks:').grid(row=1, column=0, sticky='w', pady=2)
        self.ent_khks = ttk.Entry(box_inf, textvariable=self.treatment_vars['permeability_ratio'], width=10)
        self.ent_khks.grid(row=1, column=1, pady=2, padx=4)

        ttk.Label(box_inf, text='Kh/qw (m⁻²):').grid(row=1, column=2, sticky='w', pady=2, padx=(8, 0))
        self.ent_khqw = ttk.Entry(box_inf, textvariable=self.treatment_vars['khqw'], width=10)
        self.ent_khqw.grid(row=1, column=3, pady=2, padx=4)

        for k in ['drain_type', 'drain_cw_type', 'drain_cw_spacing', 'drain_cw_diameter', 'drain_cw_pattern', 'fill_speed_cm_day']:
            if k not in self.treatment_vars:
                self.treatment_vars[k] = tk.StringVar()

        self.mechanical_opt_vars = {
            'increment': tk.StringVar(value='0.5'),
            'bamboo_length': tk.StringVar(value='3'),
            'cajuput_length': tk.StringVar(value='4'),
        }
        f_act = ttk.Frame(inner)
        f_act.pack(fill='x', pady=8, padx=8)
        self.consolidation_button = ttk.Button(
            f_act, text='Tính lún cố kết', command=self.calculate_consolidation,
            style='Accent.TButton')
        self.consolidation_button.pack(side='left', padx=3)
        self.optimize_mechanical_button = ttk.Button(
            f_act, text='Tính toán tối ưu', style='Accent.TButton',
            command=self.optimize_mechanical_solution)
        self.optimize_drainage_button = ttk.Button(
            f_act, text='Tính toán tối ưu', style='Accent.TButton',
            command=self.optimize_drainage_solution)
        self.time_chart_button = ttk.Button(f_act, text='Lún theo thời gian',
                                            command=self.draw_treatment_chart)
        self.time_chart_button.pack(side='left', padx=3)
        self.optimization_feedback = tk.StringVar(value='')
        ttk.Label(inner, textvariable=self.optimization_feedback,
                  wraplength=760, foreground='#075985').pack(fill='x', padx=12, pady=(0, 4))
        self.treatment_extra_actions = ttk.Frame(inner)
        self.treatment_extra_actions.pack(fill='x', padx=8, pady=(0, 6))
        self.stage_strength_button = ttk.Button(
            self.treatment_extra_actions, text='Kiểm tra từng giai đoạn',
            command=self.show_stage_strength)
        self.stage_strength_button.pack(fill='x', pady=2)
        self.unp_button = ttk.Button(self.treatment_extra_actions, text='Lún dư chưa xử lý',
                                     command=self.manual_show_unpenetrated, state='disabled')
        self.unp_button.pack(fill='x', pady=2)

        self.post_tree_frame = ttk.LabelFrame(inner, text='Bảng kết quả sau xử lý', padding=6)
        self.post_tree_frame.pack(fill='x', pady=4, padx=8)
        position_bar = ttk.Frame(self.post_tree_frame)
        position_bar.pack(fill='x', pady=(0, 6))
        ttk.Label(position_bar, text='Vị trí tính toán:').pack(side='left', padx=(12, 3))
        self.post_pos_var = tk.StringVar(value='Tim đường')
        self.cb_post_pos = ttk.Combobox(position_bar, textvariable=self.post_pos_var,
                                        values=('Tim đường', 'Vai đường',
                                                'Chân đường'), state='readonly', width=25)
        self.cb_post_pos.pack(side='left', padx=3)
        self.cb_post_pos.bind('<<ComboboxSelected>>', lambda _event: self.invalidate_assessment())
        
        post_area = ttk.Frame(self.post_tree_frame)
        post_area.pack(fill='both', expand=True)
        post_area.columnconfigure(0, weight=1)
        post_area.rowconfigure(0, weight=1)
        post_scroll_x = ttk.Scrollbar(post_area, orient='horizontal')
        post_scroll_y = ttk.Scrollbar(post_area, orient='vertical')
        
        style = ttk.Style(self)
        style.configure("Post.Treeview.Heading", font=(UI_FONT, 9, 'bold'),
                        padding=(3, 5))
        style.configure("Post.Treeview", font=(UI_FONT, 9), rowheight=21)

        self.post_tree = ttk.Treeview(post_area, show='headings', height=5, 
                                      xscrollcommand=post_scroll_x.set, yscrollcommand=post_scroll_y.set,
                                      style="Post.Treeview")
        self.post_tree.bind('<Configure>',
                            lambda _event: self._resize_tree_columns(self.post_tree), add='+')
        post_scroll_x.config(command=self.post_tree.xview)
        post_scroll_y.config(command=self.post_tree.yview)
        
        self.post_tree.grid(row=0, column=0, sticky='nsew')
        post_scroll_y.grid(row=0, column=1, sticky='ns')
        post_scroll_x.grid(row=1, column=0, sticky='ew')

        self.mechanical_tree_frame = ttk.LabelFrame(inner, text='Bảng phân tố lún sau xử lý cơ học', padding=6)
        mechanical_area = ttk.Frame(self.mechanical_tree_frame)
        mechanical_area.pack(fill='both', expand=True)
        mechanical_area.columnconfigure(0, weight=1)
        mechanical_area.rowconfigure(0, weight=1)
        mechanical_x = ttk.Scrollbar(mechanical_area, orient='horizontal')
        mechanical_y = ttk.Scrollbar(mechanical_area, orient='vertical')
        self.mechanical_tree = ttk.Treeview(mechanical_area, show='headings', height=10,
                                            xscrollcommand=mechanical_x.set,
                                            yscrollcommand=mechanical_y.set, style='Post.Treeview')
        mechanical_x.configure(command=self.mechanical_tree.xview)
        mechanical_y.configure(command=self.mechanical_tree.yview)
        self.mechanical_tree.grid(row=0, column=0, sticky='nsew')
        mechanical_y.grid(row=0, column=1, sticky='ns')
        mechanical_x.grid(row=1, column=0, sticky='ew')

        mode.trace_add('write', lambda *_: self.update_treatment_visibility())
        self.surcharge_enabled.trace_add('write', lambda *_: self.update_treatment_visibility())
        self.vacuum_enabled.trace_add('write', lambda *_: self.update_treatment_visibility())
        self.treatment_vars['horizontal_drain_type'].trace_add('write', lambda *_: self.toggle_horizontal_drain())
        self.treatment_vars['h_sand_cushion'].trace_add('write', lambda *_: self.draw_live_diagram())
        
        for k in ['pvd_spacing', 'pvd_length', 'sd_spacing', 'sd_length']:
            self.treatment_vars[k].trace_add('write', lambda *_: self.draw_live_diagram())

        for var in (self.stage_vars[0][0], self.stage_vars[1][0]):
            var.trace_add('write', lambda *_: self.refresh_stage_inputs())

        self.build_drainage_parameter_table(inner)
        self.toggle_influence()
        self.toggle_horizontal_drain()
        self.update_treatment_visibility()

    def build_drainage_parameter_table(self, parent):
        self.drainage_parameters_frame=ttk.LabelFrame(parent,text='Thông số theo lớp dùng tính PVD / SD',padding=8)
        ttk.Label(self.drainage_parameters_frame,text='Ch/Cv và m là thông số tính. Có φ′ CU: m = tan(φ′ × π/180); thiếu CU: chọn m trực tiếp.').pack(anchor='w',pady=3)
        columns=('layer','ratio','phi','m','source')
        self.drainage_parameter_tree=ttk.Treeview(self.drainage_parameters_frame,columns=columns,show='headings',height=4)
        for key,label,width in zip(columns,('Lớp đất','Ch/Cv','φ′ CU (độ)','m','Cách lấy m'),(190,85,100,100,240)):
            self.drainage_parameter_tree.heading(key,text=label);self.drainage_parameter_tree.column(key,width=width,anchor='w')
        self.drainage_parameter_tree.pack(fill='x')
        self.drainage_parameter_tree.bind('<Double-1>',self.edit_drainage_parameters)
        ttk.Button(self.drainage_parameters_frame,text='Thiết lập cố kết ngang',command=self.edit_drainage_parameters).pack(anchor='w',pady=4)
        self.refresh_drainage_parameters()

    def refresh_drainage_parameters(self):
        from model import soil_strength_m
        tree=self.drainage_parameter_tree
        tree.delete(*tree.get_children())
        for i,soil in enumerate(self.project.soils):
            if soil.category!='Đất dính' and soil.cc<=0:continue
            phi=soil.phi_cu_effective
            tree.insert('', 'end',iid=str(i),values=(f'{i+1}. {soil.name}',f'{soil.ch_cv:g}',
                '—' if phi is None else f'{phi:g}',f'{soil_strength_m(soil):.5g}',
                'Chọn trực tiếp (không có CU)' if phi is None else 'Tính từ φ′ CU'))

    def edit_drainage_parameters(self,event=None):
        from model import soil_strength_m
        import math
        tree=self.drainage_parameter_tree
        if event is not None:
            row=tree.identify_row(event.y)
            if row:tree.selection_set(row)
        if not tree.selection():return
        soil=self.project.soils[int(tree.selection()[0])]
        popup=tk.Toplevel(self);popup.title('Thông số PVD / SD · '+soil.name);popup.transient(self);popup.grab_set()
        ratio=tk.StringVar(value=f'{soil.ch_cv:g}');factor=tk.StringVar(value=f'{soil_strength_m(soil):.8g}')
        phi=tk.StringVar(value='' if soil.phi_cu_effective is None else str(soil.phi_cu_effective))
        pc=tk.StringVar(value=str(soil.pc))
        ttk.Label(popup,text='Ch/Cv (> 0)').grid(row=0,column=0,padx=12,pady=8)
        ttk.Entry(popup,textvariable=ratio).grid(row=0,column=1,padx=12,pady=8)
        ttk.Label(popup,text='φ′ hữu hiệu CU (độ)').grid(row=1,column=0,padx=12,pady=8)
        ttk.Entry(popup,textvariable=phi).grid(row=1,column=1,padx=12,pady=8)
        ttk.Label(popup,text='Hệ số sức kháng m').grid(row=2,column=0,padx=12,pady=8)
        factor_entry=ttk.Entry(popup,textvariable=factor);factor_entry.grid(row=2,column=1,padx=12,pady=8)
        extra_pc=self.vars['method'].get() != 'Cc/Cs/Pc'
        if extra_pc:
            ttk.Label(popup,text='Pc dùng tính sức kháng (T/m²)').grid(row=3,column=0,padx=12,pady=8)
            ttk.Entry(popup,textvariable=pc).grid(row=3,column=1,padx=12,pady=8)
        ttk.Label(popup,text='Có φ′ CU: m tính từ φ′. Không có CU: để trống φ′ và nhập m.',
                  wraplength=420).grid(row=4,column=0,columnspan=2,padx=12,pady=8)
        def update_factor(*_):
            factor_entry.configure(state='readonly' if phi.get().strip() else 'normal')
            try:
                angle=number(phi.get(),'φ′ CU')
                if math.isfinite(angle) and 0<=angle<90:
                    factor.set(f'{soil_strength_m(replace(soil,phi_cu_effective=angle)):.8g}')
            except (ValueError,TypeError):pass
        phi.trace_add('write',update_factor);update_factor()
        def save():
            try:
                r=number(ratio.get(),'Ch/Cv')
                angle=number(phi.get(),'φ′ CU') if phi.get().strip() else None
                if angle is not None and (not math.isfinite(angle) or not 0<=angle<90):
                    raise ValueError('φ′ CU phải từ 0 đến dưới 90 độ và hữu hạn.')
                m=soil_strength_m(replace(soil,phi_cu_effective=angle)) if angle is not None else number(factor.get(),'m')
                pressure=number(pc.get(),'Pc') if extra_pc else soil.pc
                if not math.isfinite(pressure) or pressure<0:raise ValueError('Pc phải không âm và hữu hạn.')
                if not math.isfinite(r) or r<=0:raise ValueError('Ch/Cv phải lớn hơn 0 và hữu hạn.')
                if not math.isfinite(m) or m<0:raise ValueError('m phải không âm và hữu hạn.')
                soil.ch_cv=r;soil.strength_m=m;soil.phi_cu_effective=angle;soil.pc=pressure
                self.invalidate_assessment();self.refresh_drainage_parameters();popup.destroy()
            except Exception as exc:messagebox.showerror('Thông số PVD / SD',str(exc),parent=popup)
        ttk.Button(popup,text='Lưu thông số',command=save).grid(row=5,column=0,columnspan=2,pady=10)

    def toggle_horizontal_drain(self):
        is_sand = self.treatment_vars['horizontal_drain_type'].get() == 'Lớp đệm cát'
        state = 'normal' if is_sand else 'disabled'
        self.ent_h_sc.config(state=state)
        self.ent_t_sc.config(state=state)
        self.draw_live_diagram()

    def toggle_influence(self):
        state_fs = 'disabled' if hasattr(self, 'treatment_flags') and self.treatment_flags['ignore_fs'].get() else 'normal'
        if hasattr(self, 'ent_dsdw'):
            self.ent_dsdw.config(state=state_fs)
            self.ent_khks.config(state=state_fs)

        state_fr = 'disabled' if hasattr(self, 'treatment_flags') and self.treatment_flags['ignore_fr'].get() else 'normal'
        if hasattr(self, 'ent_khqw'):
            self.ent_khqw.config(state=state_fr)

    def update_treatment_visibility(self):
        mode = self.treatment_vars.get('treatment', tk.StringVar(value='Chờ lún')).get()
        mechanical = hasattr(self, 'treatment_group') and self.treatment_group.get() == 'mechanical'
        self.project.treatment_group = 'mechanical' if mechanical else 'drainage'
        if hasattr(self, 'box_stages') and not self.box_stages.winfo_manager():
            opts = {'before': self.post_tree_frame} if hasattr(self, 'post_tree_frame') and self.post_tree_frame.winfo_manager() == 'pack' else {}
            self.box_stages.pack(fill='x', pady=4, padx=8, **opts)
        if hasattr(self,'drainage_parameters_frame'):
            self.drainage_parameters_frame.pack_forget()
            if not mechanical and mode in ('PVD','SD'):
                self.drainage_parameters_frame.pack(fill='x',padx=8,pady=4,before=self.box_stages)
                self.refresh_drainage_parameters()
        if hasattr(self, 'box_stages'):
            self.box_stages.configure(text=('2. Lịch trình đắp phân kỳ' if mechanical
                                             else '3. Lịch trình đắp phân kỳ'))
        if hasattr(self, 'stage_entries'):
            allow_pause = not mechanical or self.mechanical_wait.get()
            if mechanical and not allow_pause:
                for row in self.stage_vars:
                    if row[2].get() != '0':
                        row[2].set('0')
            for entries in self.stage_entries:
                entries[2].configure(state='normal' if allow_pause else 'disabled')
        if hasattr(self, 'mechanical_depth_entries'):
            for key, entry in self.mechanical_depth_entries.items():
                entry.configure(state='normal' if mechanical and self.mechanical_enabled[key].get() else 'disabled')
        if hasattr(self, 'cb_mechanical_surcharge'):
            replacement_selected = self.mechanical_enabled['replacement_depth'].get()
            self.cb_mechanical_surcharge.configure(state='normal' if replacement_selected else 'disabled')
            if mechanical and not replacement_selected:
                self.mechanical_surcharge.set(False)
        if hasattr(self, 'treated_pdf_button'):
            self.treated_pdf_button.configure(text='Xuất báo cáo')
        if hasattr(self, 'consolidation_button'):
            self.consolidation_button.configure(text='Tính lún cố kết', state='normal')
        if hasattr(self, 'optimize_mechanical_button'):
            self.optimize_mechanical_button.pack_forget()
            self.optimize_drainage_button.pack_forget()
            (self.optimize_mechanical_button if mechanical else
             self.optimize_drainage_button).pack(side='left', padx=3)
        if hasattr(self, 'post_tree_frame'):
            self.post_tree_frame.configure(text=('3. Bảng tổng hợp lún sau xử lý cơ học' if mechanical
                                                 else '7. Bảng tổng hợp lún cố kết thoát nước'))
        if hasattr(self, 'mechanical_tree_frame'):
            if mechanical:
                self.mechanical_tree_frame.pack(fill='x', pady=4, padx=8, after=self.post_tree_frame)
            else:
                self.mechanical_tree_frame.pack_forget()
        if hasattr(self, 'treatment_extra_actions'):
            if mechanical:
                self.treatment_extra_actions.pack_forget()
            else:
                self.treatment_extra_actions.pack(fill='x', padx=8, pady=(0, 6),
                                                  before=self.post_tree_frame)
        if hasattr(self, 'box_sol'):
            if mechanical:
                self.box_sol.pack_forget()
            else:
                self.box_sol.pack(fill='x', padx=8, pady=4, before=self.box_stages)
        if hasattr(self, 'box_mechanical'):
            if mechanical:
                self.box_mechanical.pack(fill='x', padx=8, pady=4, before=self.box_stages)
                if self.mechanical_wait.get() or self.mechanical_surcharge.get():
                    self.box_stages.pack(fill='x', padx=8, pady=4, after=self.box_mechanical)
                else:
                    self.box_stages.pack_forget()
                self.box_horiz_drain.pack_forget()
                self.box_pvd.pack_forget()
                self.box_sd.pack_forget()
                self.box_hansbo.pack_forget()
                if self.mechanical_surcharge.get():
                    self.box_surcharge.pack(fill='x', padx=8, pady=4, after=self.box_stages)
                else:
                    self.box_surcharge.pack_forget()
                self.box_vacuum.pack_forget()
                self._renumber_treatment_sections(True, mode)
                if hasattr(self, 'soil_tree'):
                    self.refresh_soils()
                self.draw_live_diagram()
                return
            self.box_mechanical.pack_forget()
        surcharge = self.surcharge_enabled.get()
        vacuum = getattr(self, 'vacuum_enabled', tk.BooleanVar(value=False)).get()

        if surcharge:
            self.box_surcharge.pack(fill='x', pady=4, padx=8, after=self.box_stages)
        else:
            self.box_surcharge.pack_forget()

        anchor = self.box_surcharge if surcharge else self.box_stages

        if vacuum and mode == 'PVD':
            self.box_vacuum.pack(fill='x', pady=4, padx=8, after=anchor)
            anchor = self.box_vacuum
        else:
            self.box_vacuum.pack_forget()

        if mode == 'Chờ lún':
            self.box_horiz_drain.pack_forget()
            self.box_pvd.pack_forget()
            self.box_sd.pack_forget()
            self.box_hansbo.pack_forget()
        elif mode == 'PVD':
            self.box_horiz_drain.pack(fill='x', pady=4, padx=8, before=self.box_stages)
            self.box_sd.pack_forget()
            self.box_pvd.pack(fill='x', pady=4, padx=8, after=anchor)
            self.box_hansbo.pack(fill='x', pady=4, padx=8, after=self.box_pvd)
            
            if hasattr(self, 'treatment_flags'):
                self.treatment_flags['ignore_uv'].set(False)
                self.treatment_flags['ignore_fs'].set(False)
                self.treatment_flags['ignore_fr'].set(False)
                self.toggle_influence()
        elif mode == 'SD':
            self.box_horiz_drain.pack(fill='x', pady=4, padx=8, before=self.box_stages)
            self.box_pvd.pack_forget()
            self.box_sd.pack(fill='x', pady=4, padx=8, after=anchor)
            self.box_hansbo.pack(fill='x', pady=4, padx=8, after=self.box_sd)
            
            if hasattr(self, 'treatment_flags'):
                self.treatment_flags['ignore_uv'].set(True)
                self.treatment_flags['ignore_fs'].set(True)
                self.treatment_flags['ignore_fr'].set(True)
                self.toggle_influence()

        self._renumber_treatment_sections(False, mode)

        if hasattr(self, 'soil_tree'):
            self.refresh_soils()

        self.draw_live_diagram()

    def _renumber_treatment_sections(self, mechanical, mode):
        if mechanical:
            self.box_mechanical.configure(text='1. Đào thay đất và gia cường bằng cọc')
            offset = int(self.mechanical_wait.get() or self.mechanical_surcharge.get())
            self.box_stages.configure(text='2. Lịch trình đắp phân kỳ')
            if self.mechanical_surcharge.get():
                self.box_surcharge.configure(text=f'{2+offset}. Thông số gia tải trước')
            section = 2 + offset + int(self.mechanical_surcharge.get())
            self._treatment_result_section = section
            self.post_tree_frame.configure(text=f'{section}. Bảng tổng hợp lún sau xử lý cơ học')
            self.mechanical_tree_frame.configure(text=f'{section+1}. Kết quả phân tố lún sau xử lý cơ học')
            return
        n = 1
        self.box_sol.configure(text='1. Phương án cố kết thoát nước')
        if mode in ('PVD', 'SD'):
            n += 1
            self.box_horiz_drain.configure(text=f'{n}. Giải pháp thoát nước ngang')
        n += 1
        self.box_stages.configure(text=f'{n}. Lịch trình đắp phân kỳ')
        if self.surcharge_enabled.get():
            n += 1
            self.box_surcharge.configure(text=f'{n}. Thông số gia tải')
        if self.vacuum_enabled.get() and mode == 'PVD':
            n += 1
            self.box_vacuum.configure(text=f'{n}. Thông số hút chân không')
        if mode in ('PVD', 'SD'):
            n += 1
            (self.box_pvd if mode == 'PVD' else self.box_sd).configure(
                text=f'{n}. Thông số bố trí {"Bấc thấm đứng (PVD)" if mode == "PVD" else "Cọc cát (SD)"}')
            n += 1
            self.box_ign.configure(text=f'{n}. Bỏ qua (Ignor)')
        self._treatment_result_section = n+1
        self.post_tree_frame.configure(text=f'{n+1}. Bảng tổng hợp lún sau xử lý')

    def _build_dashboard(self, parent):
        self.box_kpi = ttk.LabelFrame(parent, text='CHỈ TIÊU THIẾT KẾ  /  KẾT QUẢ NHANH', padding=8)
        self.box_kpi.pack(fill='x', pady=(0, 6))

        kpi_grid = tk.Frame(self.box_kpi, bg=COLORS['surface'])
        kpi_grid.pack(fill='x')
        self.card_sc = self._create_kpi_card(kpi_grid, 'Sc', '--- cm', '#147B95', 0)
        self.card_st = self._create_kpi_card(kpi_grid, 'S', '--- cm', '#2B5C92', 1)
        self.card_res = self._create_kpi_card(kpi_grid, 'Sc dư', '--- cm', '#B27631', 2)
        self.card_limit = self._create_kpi_card(kpi_grid, 'GIỚI HẠN', '20.0 cm', '#168062', 3)
        self.card_status = self._create_kpi_card(kpi_grid, 'ĐÁNH GIÁ', 'CHƯA TÍNH', '#607487', 4)

        self.box_geom = ttk.LabelFrame(parent, text='MẶT CẮT KỸ THUẬT  /  NỀN ĐẮP & ĐỊA CHẤT', padding=6)
        self.box_geom.pack(fill='both', expand=True, pady=4)

        cad_bar = tk.Frame(self.box_geom, bg=COLORS['surface_soft'])
        cad_bar.pack(fill='x', side='top', pady=(0, 4))
        tk.Label(cad_bar, text='CUỘN: THU PHÓNG     •     KÉO: DI CHUYỂN     •     NHẤP ĐÚP: VỀ MẶC ĐỊNH',
                 font=(UI_FONT, 9), fg=COLORS['muted'], bg=COLORS['surface_soft']).pack(side='left', padx=8, pady=4)
        self.cad_plot_select = ttk.Combobox(
            cad_bar, textvariable=self.cad_plot_display, state='readonly', width=25,
            values=('Mặt cắt', 'Độ lún', 'Ứng suất tăng thêm', 'Ứng suất bản thân', 'Áp lực nước tĩnh',
                    'Áp lực nước lỗ rỗng', 'Áp lực nước thặng dư'))
        self.cad_plot_select.pack(side='right', padx=8)
        tk.Label(cad_bar, text='Biểu đồ:', bg=COLORS['surface_soft'],
                 font=(UI_FONT, 9)).pack(side='right')
        self.cad_plot_select.bind('<<ComboboxSelected>>', self._choose_cad_plot)
        metric_select = ttk.Combobox(cad_bar, textvariable=self.cad_settlement_metric,
                                       values=('Sc dư', 'S', 'St', 'Sc'), state='readonly', width=7)
        metric_select.pack(side='right', padx=4)
        metric_select.bind('<<ComboboxSelected>>', lambda _e: self.draw_live_diagram())
        self.cad_stage_select = ttk.Combobox(cad_bar, textvariable=self.cad_stage_display,
                                             state='readonly', width=25, values=())
        self.cad_stage_label = tk.Label(cad_bar, text='Giai đoạn:', bg=COLORS['surface_soft'],
                                         font=(UI_FONT, 9))
        self.cad_stage_select.bind('<<ComboboxSelected>>', self._choose_cad_stage)

        self.canvas_diag = tk.Canvas(self.box_geom, bg=COLORS['surface_soft'], highlightthickness=1,
                                     highlightbackground=COLORS['border'])
        self.canvas_diag.pack(fill='both', expand=True)

        self.canvas_diag.bind('<Configure>', lambda _e: self.draw_live_diagram())
        self.canvas_diag.bind('<MouseWheel>', self._on_cad_zoom)
        self.canvas_diag.bind('<ButtonPress-1>', self._on_cad_pan_start)
        self.canvas_diag.bind('<B1-Motion>', self._on_cad_pan_move)
        self.canvas_diag.bind('<Double-Button-1>', self._on_cad_reset_view)

        self.box_chart = ttk.LabelFrame(parent, text='DIỄN BIẾN ĐẮP & LÚN  /  THEO THỜI GIAN', padding=6)
        self.box_chart.pack(fill='both', expand=True, pady=4)
        self.chart = tk.Canvas(self.box_chart, bg=COLORS['surface'], height=240, highlightthickness=1,
                               highlightbackground=COLORS['border'])
        self.chart.pack(fill='both', expand=True)
        self.chart.bind('<Configure>', lambda _e: self.render_chart())
        self.chart_data = {}
        self._dashboard_parent = parent
        self._dashboard_balance_job = None
        parent.bind('<Configure>', self._queue_dashboard_balance, add='+')
        for panel in (self.box_geom, self.box_chart, self.box_kpi):
            panel.bind('<Map>', self._queue_dashboard_balance, add='+')
            panel.bind('<Unmap>', self._queue_dashboard_balance, add='+')
        self._queue_dashboard_balance()

    def _queue_dashboard_balance(self, event=None):
        if getattr(self, '_dashboard_balance_job', None) is None:
            self._dashboard_balance_job = self.after_idle(self._balance_dashboard)

    def _balance_dashboard(self):
        self._dashboard_balance_job = None
        parent = getattr(self, '_dashboard_parent', None)
        if parent is None or not parent.winfo_exists() or parent.winfo_height() <= 1:
            return

        def vertical_padding(panel):
            value = panel.pack_info().get('pady', 0)
            if isinstance(value, (tuple, list)):
                return sum(panel.winfo_pixels(str(part)) for part in value)
            parts = panel.tk.splitlist(str(value))
            return (sum(panel.winfo_pixels(str(part)) for part in parts)
                    if len(parts) > 1 else 2*panel.winfo_pixels(str(value)))

        available = parent.winfo_height()
        if self.box_kpi.winfo_manager() == 'pack':
            available -= self.box_kpi.winfo_reqheight()+vertical_padding(self.box_kpi)
        panels = [panel for panel in (self.box_geom, self.box_chart)
                  if panel.winfo_manager() == 'pack']
        if not panels:
            return
        available -= sum(vertical_padding(panel) for panel in panels)
        available = max(len(panels), available)
        geometry_height = max(1, round(available*0.6)) if len(panels) == 2 else available
        for index, panel in enumerate(panels):
            target = (geometry_height if index == 0 else max(1, available-geometry_height))
            panel.pack_propagate(False)
            panel.pack_configure(fill='both', expand=False)
            if int(panel.cget('height')) != target:
                panel.configure(height=target)

    def _create_kpi_card(self, parent, title, val, color, col):
        card = tk.Frame(parent, bg=COLORS['surface_soft'], relief='flat', bd=0, padx=6, pady=5,
                        highlightthickness=1, highlightbackground=COLORS['border'])
        card.grid(row=0, column=col, sticky='nsew', padx=2, pady=2)
        for column in range(5):
            parent.grid_columnconfigure(column, weight=1, uniform='kpi')

        tk.Frame(card, bg=color, width=3).pack(side='left', fill='y', padx=(0, 8))
        info_box = tk.Frame(card, bg=COLORS['surface_soft'])
        info_box.pack(side='left', fill='both', expand=True)
        caption = tk.Label(info_box, text=title, font=(UI_FONT, 7, 'bold'), fg=COLORS['muted'],
                           bg=COLORS['surface_soft'])
        caption.pack(anchor='w')
        if title == 'Sc dư':
            self.card_res_caption = caption
            self.card_res_context = tk.Label(info_box, text='', font=(UI_FONT, 7),
                                             fg=COLORS['muted'], bg=COLORS['surface_soft'])
            self.card_res_context.pack(anchor='w')
        lbl = tk.Label(info_box, text=val, font=(UI_FONT, 10, 'bold'), fg=color,
                       bg=COLORS['surface_soft'])
        lbl.pack(anchor='w', pady=(2, 0))
        return lbl

    def _show_natural_kpis(self, *, force=False):
        # Chỉ sử dụng kết quả đã bấm tính của mục hiện tại.
        return

    def cache_step_result(self, index=None):
        index = self.current_step if index is None else index
        if index not in (3, 4, 5, 6):
            return
        attrs = ('_natural_residual', '_treated_residual', '_natural_totals',
                 '_cad_settlement_elements', '_cad_natural_totals', '_cad_stage_totals',
                 '_cad_stage_project', '_cad_default_totals', '_cad_default_project',
                 '_cad_default_remaining', '_cad_pore_remaining', '_cad_vacuum_active',
                 '_cad_default_vacuum', '_cad_metric_values')
        cards = {name: (getattr(self, name).cget('text'), getattr(self, name).cget('fg'))
                 for name in ('card_sc', 'card_st', 'card_res', 'card_limit', 'card_status')}
        trees = {}
        for name in ('result_tree', 'post_tree', 'mechanical_tree'):
            tree = getattr(self, name, None)
            if tree is not None:
                trees[name] = (tuple(tree['columns']),
                               {col: tree.heading(col, 'text') for col in tree['columns']},
                               [tree.item(i, 'values') for i in tree.get_children()])
        self._step_result_cache[index] = {
            'cards': cards, 'chart': deepcopy(self.chart_data), 'trees': trees,
            'attrs': {name: deepcopy(getattr(self, name, None)) for name in attrs},
            'context': self.card_res_context.cget('text'),
        }
        self.restore_step_result(index)

    def restore_step_result(self, index):
        self.box_kpi.pack_forget()
        self.box_chart.pack_forget()
        item = self._step_result_cache.get(index)
        if index not in (3, 4, 5, 6) or item is None:
            self._cad_metric_values = {}
            self.chart_data = {}
            self.chart.delete('all')
            for name in ('card_sc', 'card_st', 'card_res'):
                getattr(self, name).configure(text='--- cm')
            self.card_status.configure(text='CHƯA TÍNH', fg='#607487')
            return
        for name, value in item['attrs'].items():
            setattr(self, name, deepcopy(value))
        for name, (text, color) in item['cards'].items():
            getattr(self, name).configure(text=text, fg=color)
        self.card_res_context.configure(text=item['context'])
        for name, (cols, headings, rows) in item['trees'].items():
            tree = getattr(self, name)
            self.show_table(tree, [headings[c] for c in cols], rows)
        self.chart_data = deepcopy(item['chart'])
        self._display_result_panels()
        self.draw_live_diagram()

    def _display_result_panels(self, *, show_cards=True):
        if show_cards:
            if not self.box_kpi.winfo_manager():
                opts = {'before': self.box_geom} if self.box_geom.winfo_manager() else {}
                self.box_kpi.pack(side='top', fill='x', pady=2, **opts)
        elif self.box_kpi.winfo_manager():
            self.box_kpi.pack_forget()
        if self.chart_data:
            if not self.box_chart.winfo_manager():
                self.box_chart.pack(side='bottom', fill='both', expand=True, pady=4)
            chart_job = getattr(self, '_result_chart_job', None)
            if chart_job is not None: self.after_cancel(chart_job)
            self._result_chart_job = self.after_idle(self._render_visible_result_chart)
        elif self.box_chart.winfo_manager():
            self.box_chart.pack_forget()
        if not self.box_geom.winfo_manager():
            self.box_geom.pack(side='top', fill='both', expand=True, pady=4)
        self._queue_dashboard_balance()

    def _render_visible_result_chart(self):
        self._result_chart_job = None
        if self.box_chart.winfo_manager(): self.render_chart()

    def show_cdm_quick_result(self, report, method):
        result = report['result']
        if method == 'standard':
            sc, st = result['sum_sc'], result['total_s']
        else:
            sc, st = result['S2_cm'], result['S_total_cm']
        residual = sc
        limit = report.get('limit', self.project.residual_limit_cm)
        self.card_sc.configure(text=f'{sc:.2f} cm')
        self.card_st.configure(text=f'{st:.2f} cm')
        self.card_res.configure(text=f'{residual:.2f} cm')
        self.card_limit.configure(text=f'{limit:.2f} cm')
        self.card_res_context.configure(text='CDM · ' + method)
        passed = residual <= limit
        if method == 'standard':
            stress = result['stress']
            passed = passed and stress['qu_tt1'] <= stress['qu_allow'] and stress['sigma_p'] <= stress['qu_allow'] and stress['sigma_s'] <= stress['Rtc']
            if result.get('geo'):
                passed = passed and result['geo']['Tr'] <= result['geo']['Td_fn']
        else:
            passed = passed and result['S_total_cm'] <= limit and result['pile_ok'] and result.get('differential_ok') is True
            if result.get('reinforcement'):
                passed = passed and result['reinforcement']['ok']
            if result.get('surface'):
                passed = passed and result['surface']['shear_ok'] and result['surface']['ok_k']
        incomplete = method == 'alicc' and not result.get('differential_checked',False)
        self.card_status.configure(text='CHƯA KIỂM TRA CHÊNH LÚN' if incomplete else 'ĐẠT' if passed else 'CHƯA ĐẠT',
                                   fg='#168062' if passed else '#B42318')
        local = cdm_design_project(report.get('project_snapshot', self.project), report['scope'])
        curve = self._calculate_model(cdm_time_history, local, result, method, report['params']['Lc'])
        self.chart_data = {'type': 'natural', 'metric': 'residual',
                           'assessment_day': 0.0, 'rows': curve} if curve else {}
        if curve:
            self.box_chart.pack(fill='both', expand=True, pady=4, after=self.box_geom)
            self.render_chart()
        else:
            self.box_chart.pack_forget()
        axis_values = axes(self.project)
        footprint = treatment_ranges(self.project)
        si = result['sum_si'] if method == 'standard' else max(0.0, st-sc)
        self._cad_metric_values = {
            name: [value if any(lo <= x <= hi for lo,hi in footprint) else 0.0
                   for _,x in axis_values]
            for name,value in (('S',st), ('St',si), ('Sc',sc), ('Sc dư',sc))
        }
        self._show_cad_settlement_plot()
        self.cache_step_result(6)
        if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
            self.after_idle(lambda: self.route_section_selector.calculated(method))


    def _on_cad_zoom(self, event):
        if event.delta > 0:
            self.cad_zoom = min(self.cad_zoom * 1.15, 3.5)
        else:
            self.cad_zoom = max(self.cad_zoom / 1.15, 0.4)
        self.draw_live_diagram()

    def _on_cad_pan_start(self, event):
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_cad_pan_move(self, event):
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y
        self.cad_pan_x += dx
        self.cad_pan_y += dy
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self.draw_live_diagram()

    def _on_cad_reset_view(self, _event):
        self.cad_zoom = 1.0
        self.cad_pan_x = 0.0
        self.cad_pan_y = 0.0
        self.draw_live_diagram()

    def _store_cad_metrics(self, results):
        self._cad_metric_values = {
            'S': [r.get('St_cuối_cm', r.get('Sc_cuối_cm', 0)+r.get('Si_cm', 0)) for r in results],
            'St': [r.get('St_t_cm', r.get('St_cm', 0)) for r in results],
            'Sc': [r.get('Sc_t_cm', r.get('Sc_cm', 0)) for r in results],
            'Sc dư': [r.get('Sc_dư_cm', 0) for r in results],
        }

    def _selected_cad_totals(self):
        if self.current_step not in (3, 4, 5, 6):
            return None
        return self._cad_metric_values.get(self.cad_settlement_metric.get())

    def draw_live_diagram(self):
        if not hasattr(self, 'canvas_diag'):
            return
        job = getattr(self, '_diagram_draw_job', None)
        if job is not None:
            self.after_cancel(job)
        self._diagram_draw_job = self.after(45, self._flush_live_diagram)

    def _flush_live_diagram(self):
        self._diagram_draw_job = None
        if getattr(self, '_switching_step', False):
            self._diagram_draw_job = self.after(45, self._flush_live_diagram)
            return
        if str(self.right_container) not in tuple(str(p) for p in self.paned.panes()):
            return
        self._draw_live_diagram_now()

    def _draw_live_diagram_now(self):
        if not hasattr(self, 'canvas_diag'): return
        mechanical_surcharge = getattr(self, 'mechanical_surcharge', None)
        drainage_surcharge = getattr(self, 'surcharge_enabled', None)
        preview = replace(self.project)
        for key, var_name in (('h_design', 'h_design'), ('h_kcad', 'h_kcad'),
                              ('slope_m', 'slope_M'), ('gamma_fill', 'gamma_fill')):
            if var_name in self.vars:
                setattr(preview, key, number_or_zero(self.vars[var_name].get()))
        if 'crest_B' in self.vars:
            preview.crest_half_width = number_or_zero(self.vars['crest_B'].get())/2
        if hasattr(self, 'has_cw') and self.has_cw.get():
            for key in ('counterweight_height', 'counterweight_width', 'counterweight_m'):
                setattr(preview, key, number_or_zero(self.vars[key].get()))
        else:
            preview.counterweight_height = 0.0
            preview.counterweight_width = 0.0
        if hasattr(self, 'has_expansion'):
            preview.expansion_side = (self.expansion_side.get()
                                      if self.has_expansion.get() else 'Không')
            preview.expansion_width = (number_or_zero(self.vars['expansion_width'].get())
                                       if self.has_expansion.get() else 0.0)
            for key in ('expansion_h_design', 'expansion_h_kcad',
                        'expansion_slope_m', 'expansion_gamma_fill'):
                inherited = key in self.expansion_use_main and self.expansion_use_main[key].get()
                setattr(preview, key, (0.0 if key == 'expansion_h_design' else None)
                        if inherited else number_or_zero(self.vars[key].get()))
            preview.main_treatment = (self.main_treatment_var.get()
                                      if self.has_expansion.get() else 'Chưa xử lý')
            for key in ('main_replacement_depth', 'main_bamboo_depth',
                        'main_cajuput_depth', 'main_cdm_depth'):
                setattr(preview, key, number_or_zero(self.vars[key].get()))
        raw_bxl = self.vars.get('expansion_treatment_width')
        preview.expansion_treatment_width = (number_or_zero(raw_bxl.get()) or None) if raw_bxl is not None else None
        preview.update_geometry()
        draw_enhanced_cad_diagram(
            self.canvas_diag, preview, self.vars, self.treatment_vars, self.treatment_flags,
            has_cw_flag=(hasattr(self, 'has_cw') and self.has_cw.get()),
            surcharge_enabled=((self.project.treatment_group == 'mechanical' and
                                mechanical_surcharge is not None and mechanical_surcharge.get()) or
                               (self.project.treatment_group != 'mechanical' and
                                drainage_surcharge is not None and drainage_surcharge.get())),
            vacuum_enabled=(self.project.treatment_group != 'mechanical' and
                            hasattr(self, 'vacuum_enabled') and self.vacuum_enabled.get()),
            pan_x=getattr(self, 'cad_pan_x', 0.0), pan_y=getattr(self, 'cad_pan_y', 0.0), zoom=getattr(self, 'cad_zoom', 1.0),
            current_step=getattr(self, 'current_step', 4),
            plot_mode=self.cad_plot_mode.get(),
            settlement_elements=self._cad_settlement_elements,
            pore_remaining=self._cad_pore_remaining.get(getattr(self, 'current_step', 3), 1.0),
            settlement_totals=self._selected_cad_totals(),
            stage_label=self.cad_stage_mode.get() if self._cad_stage_totals is not None else '',
            analysis_project=self._cad_stage_project if getattr(self, 'current_step', 0) in (4, 5) else None,
            settlement_label=self.cad_settlement_metric.get(),
            vacuum_active=self._cad_vacuum_active if getattr(self, 'current_step', 0) in (4, 5) else 0.0,
            cdm_overlay=(self._cdm_diagram_data()
                         if getattr(self, 'current_step', 0) == 6 else None)
        )

    def _show_cad_settlement_plot(self):
        self.cad_settlement_metric.set('Sc dư')
        self.cad_plot_mode.set('Độ lún')
        self.cad_plot_display.set(_english_ui('Độ lún') if self.ui_language.get() == 'English'
                                  else 'Độ lún')

    def _update_natural_cad_residual(self, days, axis_index, selected_result=None):
        if self.project.expansion_width > 0:
            forecast = self._calculate_model(expansion_settlement_forecast, self.project, days)
            self._show_expansion_forecast(forecast)
            self._cad_natural_totals = [r['lún_dư_sau_dự_báo_cm'] for r in forecast]
            self._natural_residual = (days, forecast[axis_index]['lún_dư_sau_dự_báo_cm'])
            results = [selected_result if i == axis_index and selected_result is not None
                       else self._calculate_model(consolidation, self.project, days,
                                                  radial=False, axis_index=i)[1]
                       for i in range(len(forecast))]
            self._cad_pore_remaining[3] = [max(0.0, 1.0-r['U_%']/100.0) for r in results]
            self._store_cad_metrics(results)
            self._cad_metric_values['Sc dư'] = list(self._cad_natural_totals)
            self._choice_group_results['natural'] = {
                'project': deepcopy(self.project), 'days': days,
                'results': deepcopy(forecast), 'kind': 'expansion'}
            self._show_cad_settlement_plot()
            return
        results = [selected_result if i == axis_index and selected_result is not None
                   else self._calculate_model(consolidation, self.project, days,
                                              radial=False, axis_index=i)[1]
                   for i in range(len(axes(self.project)))]
        self._store_cad_metrics(results)
        self._cad_natural_totals = [r['Sc_dư_cm'] for r in results]
        self._natural_residual = (days, results[axis_index]['Sc_dư_cm'])
        self._cad_pore_remaining[3] = [max(0.0, 1.0-r['U_%']/100.0) for r in results]
        self._choice_group_results['natural'] = {
            'project': deepcopy(self.project), 'days': days,
            'results': deepcopy(results), 'kind': 'consolidation'}
        self._show_cad_settlement_plot()

    def _cad_load_project(self, row):
        fill_h = row['đắp_m']
        surcharge_h = row['gia_tải_m']
        load_h = fill_h+surcharge_h*self.project.surcharge_gamma/max(self.project.gamma_fill,0.01)
        ext_h, ext_slope, ext_gamma = expansion_parameters(self.project)
        return replace(self.project,h_design=load_h,h_kcad=0.0,h_bl=0.0,
                       expansion_h_design=ext_h*fill_h/max(self.project.height, 0.001),
                       expansion_h_kcad=0.0, expansion_slope_m=ext_slope,
                       expansion_gamma_fill=ext_gamma,
                       counterweight_height=min(self.project.counterweight_height,
                                                max(0.0,fill_h-0.001)))

    def _vacuum_at_day(self, day):
        if self.project.treatment_group == 'mechanical' or 'chân không' not in self.project.treatment.lower():
            return 0.0
        schedule = stage_schedule(self.project)
        start = schedule[-1]['chờ_đến'] if schedule else 0.0
        return (self.project.vacuum_pressure if start <= day <= start+self.project.vacuum_days
                else 0.0)

    def _refresh_cad_stage_options(self):
        if not hasattr(self, 'cad_stage_select'):
            return
        days = {}
        if self.project.treatment_group == 'mechanical' and not (self.project.mechanical_wait or self.project.mechanical_surcharge):
            self._cad_stage_days = days
            self.cad_stage_select.configure(values=())
            self.cad_stage_mode.set('')
            self.cad_stage_display.set('')
            self._cad_stage_totals = self._cad_default_totals
            self._cad_stage_project = self._cad_default_project
            return
        try:
            schedule = stage_schedule(self.project)
            for stage in schedule:
                n = stage['giai_đoạn']
                days[f'Sau đắp GĐ{n} · {stage["kết_thúc"]:.2f} ngày'] = stage['kết_thúc']
                if stage['chờ_đến'] > stage['kết_thúc']:
                    days[f'Sau chờ GĐ{n} · {stage["chờ_đến"]:.2f} ngày'] = stage['chờ_đến']
            start = schedule[-1]['chờ_đến'] if schedule else 0.0
            if ((self.mechanical_surcharge.get() if self.project.treatment_group == 'mechanical'
                 else self.surcharge_enabled.get()) and self.project.surcharge_days > 0):
                end = start + self.project.surcharge_days
                days[f'Sau gia tải · {end:.2f} ngày'] = end
            if self.vacuum_enabled.get() and self.project.vacuum_days > 0:
                end = start + self.project.vacuum_days
                days[f'Sau hút chân không · {end:.2f} ngày'] = end
        except (ValueError, AttributeError):
            pass
        self._cad_stage_days = days
        self.cad_stage_select.configure(values=tuple(_english_ui(v) if self.ui_language.get() == 'English' else v
                                                     for v in days))
        if self.cad_stage_mode.get() not in days:
            self.cad_stage_mode.set(max(days,key=days.get) if days else '')
        self.cad_stage_display.set(_english_ui(self.cad_stage_mode.get()) if self.ui_language.get() == 'English'
                                   else self.cad_stage_mode.get())

    def _choose_cad_plot(self, _event=None):
        display = self.cad_plot_display.get()
        values = ('Mặt cắt', 'Độ lún', 'Ứng suất tăng thêm', 'Ứng suất bản thân',
                  'Áp lực nước tĩnh', 'Áp lực nước lỗ rỗng', 'Áp lực nước thặng dư')
        self.cad_plot_mode.set(next((v for v in values if display in (v, _english_ui(v))), display))
        self.draw_live_diagram()

    def _choose_cad_stage(self, _event=None):
        display = self.cad_stage_display.get()
        values = tuple(self._cad_stage_days)
        self.cad_stage_mode.set(next((v for v in values if display in (v, _english_ui(v))), display))
        self._select_cad_stage()
        self._apply_ui_language()

    def _select_cad_stage(self, _event=None):
        label = self.cad_stage_mode.get()
        if not label:
            return
        try:
            self.collect()
            self._refresh_cad_stage_options()
            days = self._cad_stage_days[label]
            results = [self._calculate_model(treatment_history, self.project, days,
                                             max(1.0, days), self.project.treatment, i)[0][-1]
                       for i in range(len(axes(self.project)))]
            self._store_cad_metrics(results)
            self._cad_stage_totals = [r['Sc_dư_cm'] for r in results]
            if self.project.expansion_width > 0:
                forecast = self._calculate_model(expansion_settlement_forecast, self.project, days)
                self._cad_stage_totals = [r['lún_dư_sau_dự_báo_cm'] for r in forecast]
                self._show_expansion_forecast(forecast)
            self._cad_pore_remaining[4] = [max(0.0, 1.0-r['U_%']/100.0) for r in results]
            self._cad_stage_project = self._cad_load_project(results[0])
            self._cad_vacuum_active = self._vacuum_at_day(days)
            self.draw_live_diagram()
        except (ValueError, KeyError, IndexError) as exc:
            self._cad_stage_totals = None
            self._cad_stage_project = None
            messagebox.showerror('Biểu đồ giai đoạn', str(exc), parent=self)

    def render_chart(self):
        if not hasattr(self, 'chart'): return
        render_chart_view(self.chart, self.chart_data)

    def _calculate_model(self, fn, *args, **kwargs):
        """Tính mô hình ở luồng nền để cửa sổ và thanh chạy vẫn cập nhật."""
        executor = getattr(self, '_calculation_executor', None)
        if executor is None:
            return fn(*args, **kwargs)
        if args and args[0] is self.project:
            args = (deepcopy(self.project), *args[1:])
        future = executor.submit(fn, *args, **kwargs)
        while not future.done():
            self.update()
            time.sleep(0.01)
        return future.result()

    def run_processing(self, label, action):
        return _processing_call(self, label, action)

    def report_result(self, title, detail, error=False):
        """Hiển thị kết quả ngay dưới mục đang làm việc, giữ được khi hộp xử lý đóng."""
        self._result_serial = getattr(self, '_result_serial', 0) + 1
        self._last_result_notice = (str(title), str(detail), error)
        content = f'{title}\n{detail}'
        output = getattr(self, 'result_output', None)
        if output is not None:
            output.configure(state='normal')
            output.delete('1.0', 'end')
            output.insert('end', content)
            output.configure(state='disabled')
            output.see('1.0')
        if hasattr(self, 'status_text'):
            self.status_text.set(('Lỗi xử lý: ' if error else 'Đã xử lý: ') + str(title))

    def _treatment_completion_day(self):
        if self.project.treatment_group == 'mechanical' and not (self.project.mechanical_wait or self.project.mechanical_surcharge):
            return 0.0
        schedule = stage_schedule(self.project)
        end_wait = schedule[-1]['chờ_đến'] if schedule else 0.0
        mode = self.project.treatment.lower()
        extra = 0.0
        if 'gia tải' in mode:
            extra = max(extra, self.project.surcharge_days)
        if 'chân không' in mode:
            extra = max(extra, self.project.vacuum_days)
        return end_wait + extra

    def _treatment_time_description(self):
        if self.project.treatment_group == 'mechanical' and not (self.project.mechanical_wait or self.project.mechanical_surcharge):
            return 'Sc của các lớp đất chưa xử lý'
        schedule = stage_schedule(self.project)
        end_fill = sum(st['kết_thúc']-st['bắt_đầu'] for st in schedule)
        wait_days = sum(st['chờ_đến']-st['kết_thúc'] for st in schedule)
        end_wait = end_fill + wait_days
        other = self._treatment_completion_day() - end_wait
        parts = [f'đắp {end_fill:.2f}', f'chờ {wait_days:.2f}']
        if other > 0:
            parts.append(f'gia tải/hút chân không {other:.2f}')
        return ' + '.join(parts)

    def _post_axis_index(self):
        chosen = self.post_pos_var.get() if hasattr(self, 'post_pos_var') else 'Tim đường'
        return next((i for i, (name, _) in enumerate(axes(self.project))
                     if name == chosen), 0)

    @calculation_indicator
    def draw_natural_result_chart(self, evaluation_day, axis_index):
        horizon = max(1.0, evaluation_day)
        rows = []
        for i in range(31):
            day = horizon*i/30
            _, result = self._calculate_model(consolidation, self.project, day,
                                             radial=False, axis_index=axis_index)
            rows.append({'ngày': day, 'tháng': day/30, 'sc_m': result['Sc_t_cm']/100,
                         'st_m': result['St_t_cm']/100, 'dsc_m': result['Sc_dư_cm']/100,
                         'u_pct': result['U_%']})
        self.chart_data = {'type': 'natural', 'metric': 'residual', 'time_unit': 'years',
                           'assessment_day': evaluation_day, 'rows': rows}
        self.render_chart()

    def draw_treatment_chart(self):
        try:
            self.collect()
            assessment_day = self._treatment_completion_day()
            axis_index = self._post_axis_index()
            if self.project.treatment_group == 'mechanical' and not (self.project.mechanical_wait or self.project.mechanical_surcharge):
                t99 = self._calculate_model(time_to_consolidation, self.project,
                                            0.99, axis_index=axis_index, treated=True)
                horizon = max(t99, 1.0)
                # Cùng dạng St–t của lún tự nhiên; lấy thêm các mốc U để
                # đường cong không bị dồn sát trục khi Cv của các lớp khác nhau.
                days = {horizon*i/30 for i in range(31)}
                for target in (.05, .10, .15, .20, .30, .40, .50, .60,
                               .70, .80, .85, .90, .95):
                    days.add(self._calculate_model(time_to_consolidation, self.project,
                                                   target, axis_index=axis_index, treated=True))
                days.add(0.0)
                days = sorted(days)
                chart_rows = []
                for day in days:
                    _, r = self._calculate_model(consolidation, self.project, day,
                                                 axis_index=axis_index, treated=True)
                    chart_rows.append({'ngày': day, 'tháng': day/30.0,
                                       'st_m': r['St_t_cm']/100.0,
                                       'sc_m': r['Sc_t_cm']/100.0,
                                       'dsc_m': r['Sc_dư_cm']/100.0,
                                       'u_pct': r['U_%']})
                self.chart_data = {'type': 'natural', 'metric': 'residual',
                                   'assessment_day': 0.0, 'rows': chart_rows}
                self._display_result_panels(show_cards=self.current_step in self._step_result_cache
                                            or self._treated_residual is not None)
                if self.current_step in self._step_result_cache:
                    self.cache_step_result()
                self.status_text.set(f'{self.post_pos_var.get()}: U=99% tại {t99:.2f} ngày')
                return
            schedule = stage_schedule(self.project)
            if not schedule:
                messagebox.showwarning('Cảnh báo', 'Vui lòng khai báo phân kỳ đắp ở Bước 5.')
                return

            total_duration = assessment_day
            if total_duration <= 0: total_duration = 1.0

            history, _ = self._calculate_model(treatment_history, self.project, total_duration,
                                               step_days=max(1.0, total_duration / 250),
                                               mode=self.project.treatment, axis_index=axis_index)
            if not any(abs(row['ngày']-assessment_day) < 1e-6 for row in history):
                at_day, _ = self._calculate_model(treatment_history, self.project,
                                                  assessment_day, max(1.0, assessment_day),
                                                  self.project.treatment, axis_index)
                history.append(at_day[-1])
                history.sort(key=lambda row: row['ngày'])

            chart_rows = []
            for r in history:
                day = r['ngày']
                hne = correct_fill_height(schedule, day)
                sc_val = r['Sc_cm']
                st_val = r['St_cm']
                he = hne + (st_val / 100.0)

                chart_rows.append({
                    'ngày': day, 'hne_m': hne, 'he_m': he,
                    'sc_cm': sc_val, 'st_cm': st_val, 'sc_du_cm': r['Sc_dư_cm']
                })

            self.chart_data = {'type': 'pvd', 'assessment_day': assessment_day,
                               'stages': deepcopy(schedule), 'rows': chart_rows}
            self._display_result_panels(show_cards=self.current_step in self._step_result_cache
                                        or self._treated_residual is not None)
            if self.current_step in self._step_result_cache:
                self.cache_step_result()
            self.status_text.set(f'{self.post_pos_var.get()}: Sc dư tại kết thúc xử lý, ngày {assessment_day:.2f}')
        except Exception as exc:
            messagebox.showerror('Lỗi vẽ biểu đồ', str(exc))

    @calculation_indicator
    def show_stage_strength(self):
        try:
            self.collect()
            tdc = number_or_zero(self.vars.get('sand_cushion_days', tk.StringVar(value='5.0')).get())
            horiz_type = self.treatment_vars.get('horizontal_drain_type', tk.StringVar()).get() if self.project.treatment != 'Chờ lún' else "Tự nhiên"
            show_stage_strength_dialog(self, self.project, tdc, horiz_type,
                                       compute=self._calculate_model)
        except Exception as exc:
            messagebox.showerror('Lỗi', str(exc))

    @calculation_indicator
    def manual_show_unpenetrated(self):
        try:
            if str(self.unp_button['state']) == 'disabled':
                return
            self.collect()
            if self.project.treatment.startswith('Chờ lún'):
                self.calculate_consolidation()
                return
            unp_res = self._calculate_model(
                get_unpenetrated_data, self.project, sublayer_max=1.0,
                eval_days=self._treatment_completion_day())
            is_sd = ("SD" in self.project.treatment or self.project.drain_type == 'Cọc cát')
            drain_title = "cọc cát SD" if is_sd else "bấc thấm PVD"
            
            if unp_res.get('has_unpenetrated', False) and \
                    max(unp_res.get('sum_sc_tim',0),unp_res.get('sum_sc_vai',0)) > 1e-6:
                show_unpenetrated_window(self, self.project, unp_res)
            else:
                messagebox.showinfo(
                    'Thông báo',
                    f'{drain_title.capitalize()} đã cắm xuyên suốt chiều sâu các lớp đất có Cc, Cs, Pc.\n'
                    'Không tồn tại đới đất nén lún chưa xử lý bên dưới đáy.'
                )
        except Exception as exc:
            messagebox.showerror('Lỗi', str(exc))

    def _schedule_unpenetrated_state(self):
        if not hasattr(self, 'unp_button'):
            return
        pending = getattr(self, '_unp_state_job', None)
        if pending is not None:
            self.after_cancel(pending)
        self._unp_state_job = self.after(250, self._update_unpenetrated_button)

    def _update_unpenetrated_button(self):
        self._unp_state_job = None
        if not hasattr(self, 'unp_button'):
            return
        self.unp_button.configure(state='disabled')
        self.consolidation_button.configure(state='disabled')
        try:
            self.collect()
            if self.project.treatment.startswith('Chờ lún'):
                self.unp_button.configure(state='normal')
                return
            self.consolidation_button.configure(state='normal')
            data = get_unpenetrated_data(
                self.project, sublayer_max=1.0,
                eval_days=self._treatment_completion_day())
            if data.get('has_unpenetrated') and \
                    max(data.get('sum_sc_tim',0),data.get('sum_sc_vai',0)) > 1e-6:
                self.unp_button.configure(state='normal')
        except (ValueError, ZeroDivisionError, OverflowError):
            pass

    def populate(self):
        self._loading_project = True
        if hasattr(self, 'cdm_scope_var'):
            selected_scope = getattr(self.project, 'cdm_scope', 'Nền đường')
            if self.project.expansion_width <= 0:
                selected_scope = 'Nền đường'
            self.project.cdm_scope = selected_scope
            self.cdm_scope_var.set(selected_scope)
            self._cdm_reports.clear()
        for k in ['name', 'design_stage', 'work_item', 'station', 'station_from', 'station_to',
                  'road_class', 'road_location', 'assessment_days', 'residual_limit_cm',
                  'gamma_fill', 'h_design', 'h_kcad',
                  'counterweight_height', 'counterweight_width', 'counterweight_m',
                  'gamma_water', 'sublayer', 'limit_ratio', 'method']:
            val = getattr(self.project, k, '')
            if k in ('station', 'station_from', 'station_to'): val = str(val).replace('KM', '').strip()
            if k in self.vars: self.vars[k].set(format_number(val, k))
            
        self.vars['crest_B'].set(f"{self.project.crest_half_width * 2.0:.2f}")
        self.vars['slope_M'].set(f"{self.project.slope_m:.2f}")
        self.vars['ground_elevation'].set(f"{self.project.ground_elevation:.2f}")
        self.vars['water_elevation'].set(f'{(-self.project.water_depth if self.project.water_depth else 0.0):.2f}')
        self.settlement_factor_var.set(f"{self.project.settlement_factor:.2f}")
        self.has_cw.set(self.project.counterweight_height > 0)
        self.has_expansion.set(getattr(self.project, 'expansion_width', 0.0) > 0)
        self.expansion_side.set(getattr(self.project, 'expansion_side', 'Hai bên')
                                if self.has_expansion.get() else 'Hai bên')
        if getattr(self.project, 'main_treatment', '') == 'Cơ học/CDM':
            self.project.main_treatment = ('CDM' if self.project.main_cdm_depth > 0 else 'Cơ học')
        if self.project.main_treatment == 'CDM' and self.project.main_cdm_depth <= 0:
            self.project.main_cdm_depth = sum(s.thickness for s in self.project.soils)
        self.main_treatment_var.set(getattr(self.project, 'main_treatment', 'Chưa xử lý'))
        for key in ('main_replacement_depth', 'main_bamboo_depth',
                    'main_cajuput_depth', 'main_cdm_depth', 'main_age_days'):
            self.vars[key].set(f'{getattr(self.project, key, 0.0):.2f}')
        observed = getattr(self.project, 'main_observed_residual_cm', None)
        self.vars['main_observed_residual_cm'].set('' if observed is None else f'{observed:.2f}')
        bxl = getattr(self.project, 'expansion_treatment_width', None)
        self.vars['expansion_treatment_width'].set('' if bxl is None else f'{bxl:.2f}')
        self.vars['expansion_width'].set(format_number(getattr(self.project, 'expansion_width', 2.0) or 2.0))
        for key, base in (('expansion_h_design', 'h_design'),
                          ('expansion_h_kcad', 'h_kcad'),
                          ('expansion_slope_m', 'slope_m'),
                          ('expansion_gamma_fill', 'gamma_fill')):
            value = getattr(self.project, key, None)
            if value is None or (key == 'expansion_h_design' and value <= 0):
                value = getattr(self.project, base)
            self.vars[key].set(format_number(value, key))
        for key in self.expansion_use_main:
            self.expansion_use_main[key].set(getattr(self.project, key, None) is None)
        self.toggle_expansion_sources()

        curr_treatment = getattr(self.project, 'treatment', 'Chờ lún') or 'Chờ lún'
        self.treatment_group.set(getattr(self.project, 'treatment_group', 'drainage'))
        for key, flag in self.mechanical_enabled.items():
            value = getattr(self.project, key, 0.0)
            flag.set(value > 0)
            self.treatment_vars[key].set(format_number(value, key))
        self.mechanical_wait.set(getattr(self.project, 'mechanical_wait', False))
        self.mechanical_surcharge.set(getattr(self.project, 'mechanical_surcharge', False)
                                      or (self.treatment_group.get() == 'mechanical'
                                          and 'gia tải' in curr_treatment.lower()))
        self.treatment_vars['treatment'].set('Chờ lún' if self.treatment_group.get() == 'mechanical' or 'Chờ lún' in curr_treatment else curr_treatment.split(' ')[0])
        
        if hasattr(self, 'surcharge_enabled'):
            self.surcharge_enabled.set(self.treatment_group.get() != 'mechanical'
                                        and 'gia tải' in curr_treatment.lower())
        if hasattr(self, 'vacuum_enabled'):
            self.vacuum_enabled.set('chân không' in curr_treatment.lower())

        self.treatment_vars['pvd_spacing'].set(str(getattr(self.project, 'drain_spacing', '1.2') or '1.2'))
        self.treatment_vars['pvd_pattern'].set(str(getattr(self.project, 'drain_pattern', 'Tam giác') or 'Tam giác'))
        self.treatment_vars['pvd_diameter'].set(str(getattr(self.project, 'drain_diameter', '6.62') or '6.62'))
        self.treatment_vars['pvd_length'].set(str(getattr(self.project, 'drain_length', '0.0') or '0.0'))

        is_sd = ('SD' in self.project.treatment or self.project.drain_type == 'Cọc cát')
        self.treatment_vars['sd_spacing'].set(str(getattr(self.project, 'drain_spacing', '2.5') if is_sd else '2.5'))
        self.treatment_vars['sd_pattern'].set(str(getattr(self.project, 'drain_pattern', 'Tam giác') if is_sd else 'Tam giác'))
        self.treatment_vars['sd_diameter'].set(str(getattr(self.project, 'drain_diameter', '40.0') if is_sd else '40.0'))
        self.treatment_vars['sd_length'].set(str(getattr(self.project, 'drain_length', '0.0') if is_sd else '0.0'))

        for k in ['smear_ratio', 'permeability_ratio', 'khqw', 'resistance',
                  'fill_speed_cm_day', 'surcharge_height', 'surcharge_gamma', 'surcharge_days',
                  'vacuum_pressure', 'vacuum_days',
                  'horizontal_drain_type', 'h_sand_cushion']:
            if k in self.treatment_vars:
                self.treatment_vars[k].set(str(getattr(self.project, k, '')))

        for k in ['ignore_uv', 'ignore_fs', 'ignore_fr']:
            if k in self.treatment_flags:
                self.treatment_flags[k].set(bool(getattr(self.project, k, False)))

        total_htt = self.project.h_design + self.project.h_kcad + self.project.h_bl
        if hasattr(self, 'htt_label'):
            self.htt_label.set(
                f"Htk = {self.project.h_design:.2f} m  |  Hkcad = {self.project.h_kcad:.2f} m  |  Hbl = {self.project.h_bl:.2f} m  ==>  Htt = {total_htt:.2f} m"
            )

        if hasattr(self, 'stage_vars') and self.stage_vars:
            if not self.stage_flags[2].get() and not self.stage_flags[3].get():
                self.stage_vars[0][0].set(f"{total_htt:.2f}")
            for i in range(3):
                if not self.stage_vars[i][1].get().strip():
                    self.stage_vars[i][1].set('10')

        self._loading_project = False
        self._update_file_identity()
        self.refresh_soils()
        self._natural_totals = None
        if self.current_step in (4, 5):
            self._show_natural_kpis()
        self.toggle_cw()
        self.toggle_expansion()
        self.toggle_horizontal_drain()
        self.update_treatment_visibility()
        self.update_residual_limit()

    def collect(self):
        for k in ['name', 'design_stage', 'work_item', 'station', 'station_from', 'station_to',
                  'road_class', 'road_location', 'assessment_days', 'residual_limit_cm',
                  'gamma_fill', 'h_design', 'h_kcad',
                  'gamma_water', 'sublayer', 'limit_ratio', 'method']:
            raw = self.vars[k].get().strip()
            if k == 'residual_limit_cm' and self.project.residual_limit_source:
                # collect() cũng chạy từ callback nền; không phát trace xóa kết quả
                # khi chỉ đọc lại giới hạn Data không thay đổi.
                text = str(self.project.residual_limit_cm)
                if self.vars[k].get() != text:
                    self.vars[k].set(text)
                continue
            if k in ('station', 'station_from', 'station_to'):
                clean = clean_km_str(raw)
                setattr(self.project, k, f"KM {clean}" if clean and not clean.startswith('KM') else clean)
            elif k in ('name', 'design_stage', 'work_item', 'method', 'road_class', 'road_location'):
                setattr(self.project, k, raw)
            else:
                setattr(self.project, k, number(raw, k))

        self.project.crest_half_width = number(self.vars['crest_B'].get(), 'B') / 2.0
        if self.has_expansion.get():
            width = number(self.vars['expansion_width'].get(), 'Bề rộng nền mở rộng')
            if width <= 0:
                raise ValueError('Bề rộng nền mở rộng phải lớn hơn 0.')
            self.project.expansion_side = self.expansion_side.get()
            self.project.expansion_width = width
            raw_bxl = self.vars['expansion_treatment_width'].get().strip()
            self.project.expansion_treatment_width = number(raw_bxl, 'Bxl') if raw_bxl else None
            if self.project.expansion_treatment_width is not None and self.project.expansion_treatment_width <= 0:
                raise ValueError('Bxl phải lớn hơn 0.')
            self.project.main_treatment = self.main_treatment_var.get()
            self.project.main_age_days = number(self.vars['main_age_days'].get(), 'Thời gian nền chính')
            if self.project.main_age_days < 0:
                raise ValueError('Thời gian nền chính phải không âm.')
            observed = self.vars['main_observed_residual_cm'].get().strip()
            self.project.main_observed_residual_cm = (
                number(observed, 'Lún dư quan trắc') if observed else None)
            if self.project.main_observed_residual_cm is not None and self.project.main_observed_residual_cm < 0:
                raise ValueError('Lún dư quan trắc phải không âm.')
            for key in ('main_replacement_depth', 'main_bamboo_depth',
                        'main_cajuput_depth', 'main_cdm_depth'):
                active = (self.project.main_treatment == 'CDM' if key == 'main_cdm_depth'
                          else self.project.main_treatment == 'Cơ học')
                setattr(self.project, key,
                        number(self.vars[key].get(), key) if active else 0.0)
            for key, label, allow_zero in (
                ('expansion_h_design', 'Htk nền mở rộng', False),
                ('expansion_h_kcad', 'Hkcad nền mở rộng', True),
                ('expansion_slope_m', 'M nền mở rộng', False),
                ('expansion_gamma_fill', 'Dung trọng nền mở rộng', False),
            ):
                if key in self.expansion_use_main and self.expansion_use_main[key].get():
                    setattr(self.project, key, None)
                    continue
                value = number(self.vars[key].get(), label)
                if value < 0 or (value == 0 and not allow_zero):
                    raise ValueError(f'{label} phải {"không âm" if allow_zero else "lớn hơn 0"}.')
                setattr(self.project, key, value)
        else:
            self.project.expansion_side = 'Không'
            self.project.expansion_width = 0.0
            self.project.main_treatment = 'Chưa xử lý'
        self.project.slope_m = number(self.vars['slope_M'].get(), 'M')
        self.project.ground_elevation = number(self.vars['ground_elevation'].get(), 'Cao độ Ztn')
        water_elevation = number(self.vars['water_elevation'].get(), 'Cao độ MNN')
        self.project.water_depth = -water_elevation if water_elevation else 0.0
        self.project.settlement_factor = number(self.settlement_factor_var.get(), 'Hệ số m lún')
        
        if self.has_cw.get():
            self.project.counterweight_height = number(self.vars['counterweight_height'].get(), 'H bệ')
            self.project.counterweight_width = number(self.vars['counterweight_width'].get(), 'L bệ')
            self.project.counterweight_m = number(self.vars['counterweight_m'].get(), 'm bệ')
        else:
            self.project.counterweight_height = 0.0
            self.project.counterweight_width = 0.0
            self.project.counterweight_m = 0.0
            
        self.project.update_geometry()
        if self.has_expansion.get() and expansion_parameters(self.project)[0] > self.project.height + 1e-7:
            raise ValueError('Chiều cao nền mở rộng không được vượt Htt của nền chính.')

        mode_name = self.treatment_vars['treatment'].get()
        self.project.treatment_group = self.treatment_group.get()
        for key, flag in self.mechanical_enabled.items():
            setattr(self.project, key, number(self.treatment_vars[key].get(), key) if flag.get() else 0.0)
        self.project.mechanical_wait = self.mechanical_wait.get() if self.project.treatment_group == 'mechanical' else False
        self.project.mechanical_surcharge = (self.mechanical_surcharge.get()
                                             if self.project.treatment_group == 'mechanical' else False)
        if self.project.mechanical_surcharge and self.project.replacement_depth <= 0:
            raise ValueError('Gia tải trước chỉ dùng khi chọn Đào thay đất.')
        if self.project.treatment_group == 'mechanical':
            selected = [label for key, label in (('replacement_depth', 'Đào thay đất'),
                        ('bamboo_depth', 'Cọc tre'), ('cajuput_depth', 'Cọc cừ tràm'))
                        if getattr(self.project, key) > 0]
            mode = (' + '.join(selected) + (' + chờ lún' if self.project.mechanical_wait else '')
                    + (' + gia tải' if self.project.mechanical_surcharge else ''))
        else:
            mode = mode_name + (' + gia tải' if self.surcharge_enabled.get() else '')
        if self.project.treatment_group != 'mechanical' and getattr(self, 'vacuum_enabled', tk.BooleanVar()).get():
            mode += ' + chân không'
        self.project.treatment = mode
        
        if mode_name == 'SD':
            self.project.drain_type = 'Cọc cát'
            self.project.drain_spacing = number_or_zero(self.treatment_vars['sd_spacing'].get()) or 2.5
            self.project.drain_pattern = self.treatment_vars['sd_pattern'].get()
            self.project.drain_diameter = number_or_zero(self.treatment_vars['sd_diameter'].get()) or 40.0
            self.project.drain_length = number_or_zero(self.treatment_vars['sd_length'].get())
        else:
            self.project.drain_type = 'Bấc thấm'
            self.project.drain_spacing = number_or_zero(self.treatment_vars['pvd_spacing'].get()) or 1.2
            self.project.drain_pattern = self.treatment_vars['pvd_pattern'].get()
            self.project.drain_diameter = number_or_zero(self.treatment_vars['pvd_diameter'].get()) or 6.62
            self.project.drain_length = number_or_zero(self.treatment_vars['pvd_length'].get())

        for k, var in self.treatment_vars.items():
            if k in ('pvd_spacing', 'pvd_pattern', 'pvd_diameter', 'pvd_length',
                     'sd_spacing', 'sd_pattern', 'sd_diameter', 'sd_length',
                     'replacement_depth', 'bamboo_depth', 'cajuput_depth'):
                continue
            raw = var.get().strip()
            if raw:
                try:
                    setattr(self.project, k, raw if k in ('horizontal_drain_type',) else number(raw, k))
                except ValueError: pass

        if self.project.mechanical_surcharge:
            for key in ('surcharge_height', 'surcharge_gamma', 'surcharge_days'):
                value = number(self.treatment_vars[key].get(), key)
                if value <= 0:
                    raise ValueError(f'{key} phải lớn hơn 0 khi gia tải trước.')
                setattr(self.project, key, value)

        for k, flag in self.treatment_flags.items():
            setattr(self.project, k, flag.get())

        if self.project.treatment_group == 'mechanical' and not (self.project.mechanical_wait or self.project.mechanical_surcharge):
            self.project.stages = []
            return
        count = 3 if self.stage_flags[3].get() else 2 if self.stage_flags[2].get() else 1
        stages = []
        height = 0.0
        for i, (increment, speed, pause) in enumerate(self.stage_vars[:count], 1):
            amount = number(increment.get(), f'H{i}')
            if amount <= 0: 
                raise ValueError(f'H{i} phải lớn hơn 0.')
            height += amount
            stages.append(FillStage(
                target_height=height, 
                speed_cm_day=number(speed.get() or '10', f'Tốc độ {i}'), 
                pause_days=(number(pause.get() or '0', f'Chờ {i}')
            if self.project.treatment_group != 'mechanical' or self.project.mechanical_wait else 0.0)
            ))
            
        if count > 1:
            diff = abs(height - self.project.height)
            if diff > 0.01:
                raise ValueError(
                    f'Tổng phân kỳ = {height:.2f} m phải bằng Htt = {self.project.height:.2f} m '
                    f'(hiện lệch {diff * 100:.2f} cm).'
                )
            stages[-1].target_height = self.project.height
            
        self.project.stages = stages

    @calculation_indicator
    def calculate_hbl(self):
        try:
            self.collect()
            res = self._calculate_model(trial_compensation, self.project)
            self.project.h_bl = res['h_bl_m']
            self.project.update_geometry()
            self.htt_label.set(
                f"Htk = {self.project.h_design:.2f} m  |  Hkcad = {self.project.h_kcad:.2f} m  |  Hbl = {res['h_bl_m']:.2f} m  ==>  Htt = {res['h_tt_m']:.2f} m"
            )
            self.refresh_stage_inputs()
            self.draw_live_diagram()
            self.calculate_settlement()
        except Exception as exc:
            messagebox.showerror('Lỗi tính Hbl', str(exc))

    @calculation_indicator
    def calculate_settlement(self):
        try:
            self.collect()
            layers, summary, elements = self._calculate_model(
                settlement, self.project, return_details=True)
            self._cad_settlement_elements = elements
            pos_str = self.before_pos_var.get() if hasattr(self, 'before_pos_var') else 'Tim đường'
            axis_idx = next((i for i, (name, _) in enumerate(axes(self.project))
                             if name == pos_str), 0)
            
            headers = [
                'Lớp', 'Z (m)', 'h (m)', 'γ′ (T/m³)', 'e₀', 'Cc', 'Cs', 'Pc (T/m²)', 'P₀ (T/m²)',
                f'Δp {pos_str} (T/m²)', f'Sc {pos_str} (cm)', f'S {pos_str} (cm)'
            ]
            
            rows = []
            for x in elements:
                dp = x.get('dp_list', [x['dp_t_m2'], x['dp_t_m2'], x['dp_t_m2']])
                sc, st = x['Sc_list'], x['St_list']
                rows.append([
                    x['lớp'], f"{x['z_m']:.2f}", f"{x['h_m']:.2f}", f"{x['gamma_eff_list'][axis_idx]:.2f}",
                    f"{x['e0_list'][axis_idx]:.3f}", f"{x['cc_list'][axis_idx]:.3f}",
                    f"{x['cs_list'][axis_idx]:.3f}", f"{x['pc_list'][axis_idx]:.2f}",
                    f"{x['p0_list'][axis_idx]:.2f}",
                    f"{dp[axis_idx]:.2f}", f"{sc[axis_idx]:.2f}", f"{st[axis_idx]:.2f}"
                ])

            sum_sc = sum(e['Sc_list'][axis_idx] for e in elements)
            sum_st = sum(e['St_list'][axis_idx] for e in elements)
            
            rows.append(['TỔNG', '', '', '', '', '', '', '', '', '', f'{sum_sc:.2f}', f'{sum_st:.2f}'])
            
            ha_val = max((x['depth_m'] for x in elements), default=0.0)
            if hasattr(self, 'ha_badge'):
                self.ha_badge.config(text=f"Chiều sâu nén lún ha = {ha_val:.2f} m (Δp ≤ {self.project.limit_ratio:.2f}·P₀)")
            if hasattr(self, 'lbl_tbl_title'):
                self.lbl_tbl_title.config(text=f"Kết quả phân tố đất · {pos_str}")

            self.show_table(self.result_tree, headers, rows)
            
            self.last_result_view = 'settlement'
            self.card_sc.config(text=f"{sum_sc:.2f} cm")
            self.card_st.config(text=f"{sum_st:.2f} cm")
            self._natural_totals = (sum_sc, sum_st)
            d_eval = number(self.days.get(), 'Thời gian')
            if d_eval < 0:
                raise ValueError('Thời gian đánh giá phải không âm.')
            self._update_natural_cad_residual(d_eval, axis_idx)
            self._show_residual_for_step()
            self.draw_live_diagram()
            self.draw_natural_result_chart(d_eval, axis_idx)
            self.cache_step_result(3)
            self.report_result('Lún khi chưa xử lý',
                               f'{pos_str}: S_c = {sum_sc:.2f} cm; S = {sum_st:.2f} cm; '
                               f'chiều sâu nén lún hₐ = {ha_val:.2f} m.')
        except Exception as exc:
            self.report_result('Lún khi chưa xử lý', str(exc), error=True)
            messagebox.showerror('Lỗi kiểm toán lún', str(exc))

    def optimize_mechanical_solution(self):
        if not self.require_full_license():
            return
        window = tk.Toplevel(self)
        window.title('Thiết lập tối ưu xử lý cơ học')
        window.transient(self)
        window.resizable(False, False)
        body = ttk.Frame(window, padding=16)
        body.pack(fill='both', expand=True)
        step = tk.StringVar(value=self.mechanical_opt_vars['increment'].get())
        for row, (label, variable, readonly) in enumerate((
            ('Bước đào (m):', step, False),
            ('Chiều dài cọc tre (m):', self.mechanical_opt_vars['bamboo_length'], True),
            ('Chiều dài cừ tràm (m):', self.mechanical_opt_vars['cajuput_length'], True),
        )):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky='w', padx=(0,12), pady=6)
            entry = ttk.Entry(body, textvariable=variable, width=12,
                              state='readonly' if readonly else 'normal')
            entry.grid(row=row, column=1, sticky='w', pady=6)
            if row == 0:
                first_entry = entry
        def calculate():
            try:
                increment = float(step.get().replace(',', '.'))
                if not math.isfinite(increment) or increment <= 0:
                    raise ValueError('Bước đào phải là số lớn hơn 0.')
            except ValueError:
                messagebox.showerror('Bước đào', 'Nhập bước đào là số lớn hơn 0.', parent=window)
                return
            self.mechanical_opt_vars['increment'].set(str(increment))
            window.destroy()
            self.after_idle(self._run_mechanical_optimization)
        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=2, sticky='e', pady=(12,0))
        ttk.Button(buttons, text='Tính tối ưu', command=calculate, style='Accent.TButton').pack(side='left', padx=4)
        ttk.Button(buttons, text='Hủy', command=window.destroy).pack(side='left', padx=4)
        window.bind('<Return>', lambda _event: calculate())
        window.bind('<Escape>', lambda _event: window.destroy())
        window.grab_set()
        first_entry.focus_set()

    @calculation_indicator
    def _run_mechanical_optimization(self):
        if not self.require_full_license():
            return
        try:
            self.collect()
            result = self._calculate_model(
                optimize_mechanical, deepcopy(self.project), self.project.residual_limit_cm,
                float(self.mechanical_opt_vars['increment'].get().replace(',', '.')))
            if result['status'] == 'fail':
                self.optimization_feedback.set(
                    f'Không dùng được phương án cơ học: đã thử {result["attempts"]} cấu hình '
                    f'theo thứ tự đào thay → cọc tre → cừ tràm; '
                    f'lún dư cuối {result["residual_cm"]:.2f} cm vẫn vượt '
                    f'{self.project.residual_limit_cm:.2f} cm.')
                self.report_result('Tối ưu cơ học', self.optimization_feedback.get())
                return
            if result['status'] == 'untreated':
                self.optimization_feedback.set(
                    f'Ở chiều sâu đào 0 m, lún dư {result["residual_cm"]:.2f} cm '
                    'đã đạt; không cần phương án cơ học.')
                self.report_result('Tối ưu cơ học', self.optimization_feedback.get())
                return
            for key in ('replacement_depth', 'bamboo_depth', 'cajuput_depth'):
                depth = result[key]
                self.mechanical_enabled[key].set(depth > 0)
                self.treatment_vars[key].set(f'{depth:.2f}')
            self.mechanical_wait.set(False)
            self.mechanical_surcharge.set(False)
            self.update_treatment_visibility()
            self.collect()
            self.calculate_consolidation()
            labels = {'replacement': 'Đào thay đất', 'bamboo': f'Cọc tre {result["bamboo_depth"]:.2f} m + đào thay',
                      'cajuput': f'Cừ tràm {result["cajuput_depth"]:.2f} m + đào thay'}
            self.optimization_feedback.set(
                f'Đạt: {labels[result["group"]]}, chiều sâu đào '
                f'{result["replacement_depth"]:.2f} m; chiều dày xử lý '
                f'{result["treatment_depth"]:.2f} m; lún dư lớn nhất '
                f'{result["residual_cm"]:.2f} cm ≤ {self.project.residual_limit_cm:.2f} cm. '
                f'Đã thử {result["attempts"]} cấu hình theo bước {self.mechanical_opt_vars["increment"].get()} m.')
            self.report_result('Tối ưu cơ học', self.optimization_feedback.get())
        except Exception as exc:
            self.report_result('Tối ưu cơ học', str(exc), error=True)
            messagebox.showerror('Tối ưu xử lý cơ học', str(exc), parent=self)

    @calculation_indicator
    def optimize_drainage_solution(self):
        if not self.require_full_license():
            return
        try:
            self.collect()
            result = self._calculate_model(
                optimize_drainage_time, deepcopy(self.project), self.project.residual_limit_cm)
            if result['status'] != 'pass':
                self.optimization_feedback.set(
                    f'Không tìm được thời gian đáp ứng đồng thời lún dư '
                    f'≤ {self.project.residual_limit_cm:.2f} cm và U > 90%: '
                    f'{result["reason"]}. Tại ngày {result["day"]:.2f}, '
                    f'lún dư {result["residual_cm"]:.2f} cm, U={result["u_pct"]:.2f}%.')
                self.report_result('Tối ưu thoát nước', self.optimization_feedback.get())
                return
            if self.treatment_vars['treatment'].get() == 'PVD':
                self.treatment_vars['pvd_length'].set(f'{result["drain_length"]:.2f}')
            elif self.treatment_vars['treatment'].get() == 'SD':
                self.treatment_vars['sd_length'].set(f'{result["drain_length"]:.2f}')
            count = 3 if self.stage_flags[3].get() else 2 if self.stage_flags[2].get() else 1
            wait_days = math.ceil(result['wait_days']*1000)/1000
            surcharge = self.surcharge_enabled.get()
            vacuum = self.vacuum_enabled.get()
            self.stage_vars[count-1][2].set('0' if surcharge or vacuum else f'{wait_days:.2f}')
            if surcharge:
                self.treatment_vars['surcharge_height'].set(f'{result["surcharge_height"]:.2f}')
                self.treatment_vars['surcharge_days'].set(f'{max(0.1, wait_days):.2f}')
            if vacuum:
                self.treatment_vars['vacuum_days'].set(f'{max(0.1, wait_days):.2f}')
            self.collect()
            self.calculate_consolidation()
            self.optimization_feedback.set(
                f'Đạt: chiều dài xử lý đến đáy lớp đất yếu sâu nhất '
                f'L={result["drain_length"]:.2f} m; thời gian sớm nhất '
                f'{result["day"]:.2f} ngày tính từ lúc bắt đầu đắp '
                f'(chờ sau đắp {wait_days:.2f} ngày). '
                f'Lún dư {result["residual_cm"]:.2f} cm, U={result["u_pct"]:.2f}% > 90%. '
                + (f'Hgh={result["hgh"]:.2f} m.' if result['hgh'] is not None else ''))
            self.report_result('Tối ưu thoát nước', self.optimization_feedback.get())
        except Exception as exc:
            self.report_result('Tối ưu thoát nước', str(exc), error=True)
            messagebox.showerror('Tối ưu thời gian thoát nước', str(exc), parent=self)

    @calculation_indicator
    def calculate_consolidation(self):
        if self.is_trial() and (self.current_step != 4 or self.treatment_group.get() != 'mechanical'):
            self.require_full_license()
            return
        try:
            if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
                self.route_section_selector.require_section()
            self.collect()
            if self.project.treatment_group == 'mechanical':
                _, _, mechanical_elements = self._calculate_model(
                    settlement, self.project, return_details=True, treated=True)
                self._cad_settlement_elements = mechanical_elements
                display_elements = mechanical_display_elements(mechanical_elements)
                axis_index = self._post_axis_index()
                position = axes(self.project)[axis_index][0]
                headers = ['Lớp đất', 'Tên lớp đất', 'Xử lý', 'Z (m)', 'h (m)', 'γ′ (T/m³)', 'e₀', 'Cc', 'Cs',
                           'Pc (T/m²)', 'P₀ (T/m²)', f'Δp {position} (T/m²)',
                           f'Sc {position} (cm)', f'S {position} (cm)']
                rows = [[e['lớp'], e['tên'], e['xử_lý'], f'{e["z_m"]:.2f}', f'{e["h_m"]:.2f}',
                         f'{e["gamma_eff_list"][axis_index]:.2f}',
                         f'{e["e0_list"][axis_index]:.3f}',
                         f'{e["cc_list"][axis_index]:.3f}', f'{e["cs_list"][axis_index]:.3f}',
                         f'{e["pc_list"][axis_index]:.2f}',
                         f'{e["p0_list"][axis_index]:.2f}', f'{e["dp_list"][axis_index]:.2f}',
                         f'{e["Sc_list"][axis_index]:.2f}', f'{e["St_list"][axis_index]:.2f}']
                        for e in display_elements]
                rows.append(['TỔNG', '', '', '', '', '', '', '', '', '', '', '',
                             f'{sum(e["Sc_list"][axis_index] for e in mechanical_elements):.2f}',
                             f'{sum(e["St_list"][axis_index] for e in mechanical_elements):.2f}'])
                self.show_table(self.mechanical_tree, headers, rows)
            evaluation_day = self._treatment_completion_day()
            results = self._calculate_model(assess_locations, self.project,
                                            evaluation_day, self.project.treatment)
            self._refresh_cad_stage_options()
            if self._cad_settlement_elements is None:
                _, _, self._cad_settlement_elements = settlement(self.project, return_details=True, treated=True)
            waiting = self.project.treatment.startswith('Chờ lún')
            self.post_tree_frame.configure(
                text=f'{self._treatment_result_section}. Bảng kết quả {"chờ lún" if waiting else "sau xử lý"} · ngày {evaluation_day:.2f} '
                     f'({self._treatment_time_description()})')
            mechanical = self.project.treatment_group == 'mechanical'
            radial_mode = not mechanical and self.project.treatment.startswith(('PVD', 'SD'))
            headers = (['Vị trí', 'Sc = Sc dư (cm)', 'St (cm)', 'U (%)', 'Đánh giá']
                       if mechanical else
                       ['Vị trí', 'Sc (cm)', 'St (cm)', 'Sc dư vùng PVD/SD (cm)',
                        'Sc dư chưa xử lý (cm)', 'Sc dư (cm)', 'U (%)', 'Đánh giá']
                       if radial_mode else
                       ['Vị trí', 'Sc (cm)', 'St (cm)', 'Sc dư (cm)', 'U (%)', 'Đánh giá'])
            residuals = [(x, max(0.0, x['Sc_cuối_cm']-x['Sc_t_cm']))
                         for x in results]
            rows = [[x['vị_trí'], f'{residual:.2f}', f"{x['St_t_cm']:.2f}",
                     f"{x['U_%']:.2f}",
                     'ĐẠT' if residual <= self.project.residual_limit_cm else 'CHƯA ĐẠT']
                    if mechanical else
                    [x['vị_trí'], f"{x['Sc_cuối_cm']:.2f}", f"{x['St_t_cm']:.2f}",
                     f"{x['Sc_dư_trong_vùng_thoát_nước_cm']:.2f}",
                     f"{x['Sc_dư_chưa_xử_lý_cm']:.2f}",
                     f'{residual:.2f}', f"{x['U_%']:.2f}",
                     'ĐẠT' if residual <= self.project.residual_limit_cm else 'CHƯA ĐẠT']
                    if radial_mode else
                    [x['vị_trí'], f"{x['Sc_cuối_cm']:.2f}", f"{x['St_t_cm']:.2f}",
                     f'{residual:.2f}', f"{x['U_%']:.2f}",
                     'ĐẠT' if residual <= self.project.residual_limit_cm else 'CHƯA ĐẠT']
                    for x, residual in residuals]
            self.show_table(self.post_tree, headers, rows)
            worst_residual = max((residual for _, residual in residuals), default=0.0)
            self._treated_residual = (evaluation_day, worst_residual)
            self.report_result(self.project.treatment,
                               f'S_r lớn nhất = {worst_residual:.2f} cm; '
                               f'[S_r] = {self.project.residual_limit_cm:.2f} cm; '
                               f't = {evaluation_day:.2f} ngày.\n'
                               f'Kết quả kiểm tra: {"ĐẠT" if worst_residual <= self.project.residual_limit_cm else "CHƯA ĐẠT"}.')
            self._choice_group_results[self.project.treatment_group] = {
                'project': deepcopy(self.project), 'days': evaluation_day,
                'results': deepcopy(results), 'kind': 'treated'}
            if results:
                current = results[self._post_axis_index()]
                self.card_sc.configure(text=f'{current["Sc_cuối_cm"]:.2f} cm')
                self.card_st.configure(text=f'{current["St_t_cm"]:.2f} cm')
            if results:
                self._store_cad_metrics(results)
                self._cad_default_totals = [r['Sc_dư_cm'] for r in results]
                self._cad_default_remaining = [max(0.0,1.0-r['U_%']/100.0) for r in results]
                if mechanical and not (self.project.mechanical_wait or self.project.mechanical_surcharge):
                    self._cad_default_project = self.project
                else:
                    stage_rows,_ = self._calculate_model(treatment_history,self.project,
                                                        evaluation_day,max(1.0,evaluation_day),
                                                        self.project.treatment,0)
                    self._cad_default_project = self._cad_load_project(stage_rows[-1])
                self._cad_default_vacuum = self._vacuum_at_day(evaluation_day)
                self._cad_stage_totals = self._cad_default_totals
                self._cad_stage_project = self._cad_default_project
                self._cad_vacuum_active = self._cad_default_vacuum
                self._cad_pore_remaining[4] = self._cad_default_remaining
                if self._cad_stage_days:
                    label = max(self._cad_stage_days,key=self._cad_stage_days.get)
                    self.cad_stage_mode.set(label)
                    self.cad_stage_display.set(_english_ui(label) if self.ui_language.get() == 'English'
                                               else label)
            self._show_residual_for_step()
            self.draw_treatment_chart()
            self._show_cad_settlement_plot()
            self.draw_live_diagram()
            
            self._update_unpenetrated_button()
            self.cache_step_result()
            self.route_section_selector.calculated()
                    
        except Exception as exc:
            self.report_result('Lỗi tính toán', str(exc), error=True)
            messagebox.showerror('Lỗi tính toán', str(exc))

    def _resize_tree_columns(self, tree):
        preferred = getattr(tree, '_preferred_widths', None)
        if not preferred:
            return
        for cid,width in zip(tree['columns'],preferred):
            tree.column(cid,minwidth=40)
            if tree.column(cid,'width') != width:
                tree.column(cid,width=width,stretch=False)

    def show_table(self, tree, headers, rows):
        tree.delete(*tree.get_children())
        tree.configure(height=min(18, max(3, len(rows))))
        apply_row_stripes(tree)
        tree['columns'] = tuple(str(i) for i in range(len(headers)))

        heading_font = tkfont.Font(family=UI_FONT, size=9, weight='bold')
        data_font = tkfont.Font(family=UI_FONT, size=9)
        preferred = []
        
        for i, h in enumerate(headers):
            display = _compact_heading(str(h), heading_font, limit=100)
            max_width = _heading_width(display, heading_font) + 14
            for r in rows:
                if i < len(r):
                    cell_w = data_font.measure(str(r[i])) + 14
                    if cell_w > max_width:
                        max_width = cell_w
            
            final_width = min(240, max(48, max_width))
            preferred.append(final_width)
            tree.heading(str(i), text=display)
            tree.column(str(i), minwidth=40)
            tree.column(str(i), width=final_width, minwidth=40,
                        anchor='center', stretch=False)
            
        for index, r in enumerate(rows):
            tree.insert('', 'end', values=r, tags=('odd' if index % 2 else 'even',))
        tree._preferred_widths = preferred
        tree.after_idle(lambda: self._resize_tree_columns(tree))
            
        self.last_rows = [headers, *rows]

    def invalidate_assessment(self):
        if getattr(self, '_switching_step', False):
            return
        if hasattr(self, '_step_result_cache'):
            self._step_result_cache.clear()
        if hasattr(self, 'box_kpi'):
            self.box_kpi.pack_forget()
            self.box_chart.pack_forget()
        if hasattr(self, '_cdm_reports') and not getattr(self, '_loading_project', False):
            self._cdm_reports.clear()
        self._natural_residual = None
        self._treated_residual = None
        self._natural_totals = None
        self._cad_natural_totals = None
        self._cad_stage_totals = None
        self._cad_stage_project = None
        self._cad_default_totals = None
        self._cad_default_project = None
        self._cad_default_remaining = None
        self._cad_vacuum_active = 0.0
        self._cad_default_vacuum = 0.0
        self._cad_settlement_elements = None
        self._cad_metric_values = {}
        self._cad_pore_remaining = {3: 1.0, 4: 1.0}
        self._schedule_unpenetrated_state()
        if hasattr(self, 'card_res') and self.current_step in (3, 4, 5):
            self._show_residual_for_step()
        if self.current_step in (4, 5) and hasattr(self, 'card_sc'):
            self.card_sc.config(text='--- cm')
            self.card_st.config(text='--- cm')
        if hasattr(self, 'card_status'):
            self.card_status.config(text="DỮ LIỆU ĐỔI", fg="#64748B")

    def _show_residual_for_step(self):
        if not hasattr(self, 'card_res_caption'):
            return
        if self.current_step == 3:
            item = getattr(self, '_natural_residual', None)
            context = f'Sau t = {item[0]:.2f} ngày (tự nhiên)' if item else 'Sau thời gian t (tự nhiên)'
        elif self.current_step in (4, 5):
            item = getattr(self, '_treated_residual', None)
            if self.project.treatment_group == 'mechanical' and not (self.project.mechanical_wait or self.project.mechanical_surcharge):
                context = 'Phần đất chưa xử lý'
            elif self.project.treatment.startswith('Chờ lún') or self.project.mechanical_wait:
                context = (f'Sau chờ lún, ngày {item[0]:.2f}' if item else 'Sau chờ lún')
            else:
                context = (f'Kết thúc xử lý, ngày {item[0]:.2f}'
                           if item else 'Sau xử lý')
        else:
            return
        self.card_res_caption.config(text='Sc dư')
        self.card_res_context.config(text=context)
        self.card_res.config(text=f'{item[1]:.2f} cm' if item else '--- cm')
        if hasattr(self, 'card_status'):
            if item:
                passed = item[1] <= self.project.residual_limit_cm
                if self.current_step == 3:
                    status = 'ĐẠT (TỰ NHIÊN)' if passed else 'CẦN XỬ LÝ NỀN'
                elif self.project.treatment.startswith('Chờ lún'):
                    status = 'ĐẠT (CHỜ LÚN)' if passed else 'CHƯA ĐẠT'
                else:
                    status = 'ĐẠT SAU XỬ LÝ' if passed else 'CHƯA ĐẠT'
                self.card_status.config(text=status,
                                        fg='#16A34A' if passed else '#DC2626')
            else:
                self.card_status.config(text='CHƯA TÍNH', fg='#64748B')

    def export_treatment_data(self, kind):
        if self.design_mode.get() != 'TÍNH TOÀN TUYẾN': return
        if not self.require_full_license():
            return
        callback = getattr(self, '_treatment_export_commands', {}).get(kind)
        if callback is not None:
            try:
                callback()
            except Exception as exc:
                messagebox.showerror('Xuất dữ liệu', str(exc), parent=self)

    def export_visible_table(self):
        if not self.require_full_license():
            return
        dialog = getattr(self, '_active_export_dialog', None)
        if (dialog is not None and dialog.winfo_exists() and dialog.winfo_viewable()
                and dialog._soilfirm_export_mode == self.design_mode.get()):
            dialog._soilfirm_export_table()
            return
        if self.current_step == 9:
            self.export_treatment_data('table')
            return
        tab = self.step_frames[self.current_step] if hasattr(self, 'step_frames') else None
        # A table shown in the current workspace is the authoritative export source.
        trees = []
        def find_tables(widget):
            if isinstance(widget, ttk.Treeview) and widget.winfo_viewable():
                trees.append(widget)
            for child in widget.winfo_children():
                find_tables(child)
        if tab is not None:
            find_tables(tab)
        if not trees:
            messagebox.showinfo('Xuất bảng đang xem', 'Mở bảng cần xuất trước khi chọn lệnh này.', parent=self)
            return
        def write_table(tree):
            dest = filedialog.asksaveasfilename(parent=self, defaultextension='.csv',
                                              filetypes=[('CSV Document', '*.csv')])
            if not dest:
                return
            columns = tree['columns']
            with open(dest, 'w', newline='', encoding='utf-8-sig') as stream:
                writer = csv.writer(stream)
                writer.writerow([tree.heading(c, 'text') for c in columns])
                for item in tree.get_children():
                    writer.writerow(tree.item(item, 'values'))
            messagebox.showinfo('Xuất bảng đang xem', 'Đã xuất bảng dữ liệu.', parent=self)
        if len(trees) == 1:
            write_table(trees[0])
            return
        popup = tk.Toplevel(self)
        popup.title('Chọn bảng cần xuất')
        names = []
        for i, tree in enumerate(trees):
            title = ''
            owner = tree.master
            while owner is not None and owner is not tab:
                if isinstance(owner, ttk.LabelFrame):
                    title = owner.cget('text');break
                owner = owner.master
            names.append(f'{i+1}. {title or ", ".join(tree.heading(c, "text") for c in tree["columns"][:3])}')
        selected = tk.StringVar(value=names[0])
        ttk.Combobox(popup, textvariable=selected, values=names, state='readonly', width=65).pack(padx=12, pady=12)
        def choose():
            tree = trees[names.index(selected.get())]
            popup.destroy()
            write_table(tree)
        ttk.Button(popup, text='Xuất dữ liệu', command=choose).pack(pady=(0, 12))

    def export(self):
        if getattr(self, 'current_user_tier', 'trial') == 'trial' and getattr(self, 'current_user_role', 'user') != 'admin':
            messagebox.showwarning("Khóa tính năng (Trial)", 
                                   "Tính năng Xuất kết quả CSV bị khóa ở phiên bản Dùng thử (Trial).\nVui lòng mua bản quyền (SĐT/Zalo: 0869233097) để mở khóa.", 
                                   parent=self)
            return

        if not self.last_rows:
            messagebox.showwarning('Cảnh báo', 'Vui lòng thực hiện tính toán trước khi xuất bảng.')
            return
        dest = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV Document', '*.csv')])
        if dest:
            with open(dest, 'w', newline='', encoding='utf-8-sig') as f:
                csv.writer(f).writerows(self.last_rows)
            messagebox.showinfo('Thành công', f'Đã xuất dữ liệu ra tệp: {dest}')

    # ==========================================================================
    # XUẤT BÁO CÁO PDF ĐỒNG BỘ TOÀN DIỆN MỌI GIẢI PHÁP
    # ==========================================================================
    def export_workflow_pdf(self, whole=False):
        from design_workflow import export_workflow_pdf
        export_workflow_pdf(self, whole)

    def export_pdf(self, scope='full'):
        """Xuất báo cáo A4 tổng hợp hoặc riêng theo mục đang tính."""
        if not self.require_full_license():
            return
        if self.current_step == 6:
            scope = 'cdm'
        special = None
        if scope == 'cdm':
            special = self._cdm_reports.get(self._cdm_active_method)
            if special is None or special.get('scope') != self.cdm_scope_var.get():
                messagebox.showinfo('Báo cáo CDM',
                                    'Bấm tính toán trong thẻ CDM hoặc ALiCC trước khi xuất PDF.',
                                    parent=self)
                return
        if getattr(self, 'current_user_tier', 'trial') == 'trial' and getattr(self, 'current_user_role', 'user') != 'admin':
            messagebox.showwarning('Khóa tính năng (Trial)',
                                   'Tính năng Xuất báo cáo PDF bị khóa ở phiên bản Dùng thử (Trial).\nVui lòng mua bản quyền (SĐT/Zalo: 0869233097) để mở khóa.',
                                   parent=self)
            return
        if not HAS_REPORTLAB:
            messagebox.showerror('Thiếu thư viện', 'Vui lòng cài đặt ReportLab: pip install reportlab', parent=self)
            return
        try:
            self.collect_cdm_inputs() if scope == 'cdm' else self.collect()
            if not self.project.soils:
                messagebox.showwarning('Chưa có số liệu', 'Vui lòng khai báo ít nhất một lớp đất trước khi xuất báo cáo.', parent=self)
                return
        except Exception as exc:
            messagebox.showerror('Số liệu không hợp lệ', str(exc), parent=self)
            return
        dest = filedialog.asksaveasfilename(defaultextension='.pdf',
                                            filetypes=[('PDF Document', '*.pdf')],
                                            title={'natural': 'Lưu PDF mục 4 - Lún tự nhiên',
                                                   'cdm': 'Lưu PDF mục 7 - Trộn sâu CDM',
                                                   'treated': ('Lưu PDF mục 5 - Thay thế & gia cường cơ học'
                                                               if self.project.treatment_group == 'mechanical'
                                                               else 'Lưu PDF mục 6 - Cố kết & Thoát nước')}.get(
                                                               scope, 'Lưu báo cáo PDF tổng hợp'),
                                            parent=self)
        if not dest:
            return
        include_logo = messagebox.askyesno('Logo PDF', 'Hiển thị logo SOILFIRM PRO trên PDF? Chọn Không để xuất PDF không có logo.', parent=self)
        temp_path = None
        try:
            from report_pdf import create_report
            fd, temp_path = tempfile.mkstemp(suffix='.pdf', dir=os.path.dirname(os.path.abspath(dest)))
            os.close(fd)
            create_report(self.project, temp_path, scope=scope, show_logo=include_logo,
                          special_method=self._cdm_active_method if scope == 'cdm' else None,
                          special_data=special,
                          language='en' if self.ui_language.get() == 'English' else 'vi')
            os.replace(temp_path, dest)
            temp_path = None
            messagebox.showinfo('Thành công', f'Đã xuất báo cáo PDF:\n{dest}', parent=self)
        except Exception as exc:
            messagebox.showerror('Lỗi xuất báo cáo', str(exc), parent=self)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def new(self):
        if not self._confirm_save_changes():
            return
        self.project, self.path = Project(h_design=3.0, h_kcad=0.15, crest_half_width=6.0, slope_m=1.5,
                                          treatment='Chờ lún', horizontal_drain_type='Bấc thấm ngang', drain_spacing=1.2,
                                          ignore_uv=False, ignore_fs=False, ignore_fr=False), None
        from ai_analysis_data import new_session
        self._ai_analysis_state = new_session(Project())
        self._geology_sessions = {}
        self._geology_session_mode = None
        self._saved_sections_data = []
        self._single_batch_records = []
        self._single_batch_failures = []
        self._batch_candidates={};self._batch_runs={}
        self._route_manual_designs = {}
        self._single_workspace = None
        self._route_workspace = None
        self.route_section_selector.active = None
        self.route_section_selector._visible_group = None
        self.route_section_selector.group = None
        self._single_selected_option=None;self._before_section_results={}
        self._calculation_settings = dict(self._calculation_preferences.get('stages', {}))
        self.project.method = self._calculation_preferences.get('method', 'Cc/Cs/Pc')
        self._apply_calculation_visibility()
        self._rebuild_workflow_navigation()
        self._section_excel_path = None
        self._sync_geology_session()
        self.populate()
        self._cdm_reports.clear()
        self._choice_group_results.clear()
        self._step_result_cache.clear()
        self.restore_step_result(self.current_step)
        self.chart_data = {}
        self.render_chart()
        self._mark_project_saved()

    def open(self):
        p = filedialog.askopenfilename(filetypes=[('Dự án SoilFirm Pro', '*.json'), ('All Files', '*.*')])
        if p:
            if not self._confirm_save_changes():
                return
            try:
                with open(p, encoding='utf-8') as stream:
                    document = json.load(stream)
                if document.get('format') == 'soilfirm_batch':
                    records = self._unpack_saved_result(document.get('records', []))
                    if not records:
                        raise ValueError('Hồ sơ hàng loạt không có phân đoạn.')
                    self._saved_sections_data = records
                    self.project = records[0]['project_snapshot']
                    self.path = None
                    source = document.get('source', '')
                    self._section_excel_path = source if os.path.isfile(source) else None
                else:
                    self.project = load(p)
                    self.path = p
                self._choice_group_results.clear()
                self.populate()
                if document.get('format') == 'soilfirm_batch':
                    self.refresh_result_summary()
                    self.refresh_treatment_boq()
                else:
                    self._restore_calculation_results()
                self._mark_project_saved()
            except Exception as exc:
                messagebox.showerror('Không mở được tệp', str(exc))

    def _pack_saved_result(self, value):
        from dataclasses import fields
        if isinstance(value, Project):
            return {'__soilfirm_project__': {f.name: self._pack_saved_result(getattr(value, f.name))
                    for f in fields(value) if f.name != 'calculation_results'}}
        from dataclasses import is_dataclass, asdict
        if is_dataclass(value):
            return self._pack_saved_result(asdict(value))
        if isinstance(value, dict):
            return {str(k): self._pack_saved_result(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._pack_saved_result(v) for v in value]
        return value

    def _unpack_saved_result(self, value):
        if isinstance(value, dict):
            if '__soilfirm_project__' in value:
                from model import project_from_dict
                return project_from_dict(value['__soilfirm_project__'])
            return {k: self._unpack_saved_result(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._unpack_saved_result(v) for v in value]
        return value

    def _cdm_saved_widgets(self, restore=None):
        result = []
        def walk(widget, path):
            if restore is None:
                for option in ('textvariable', 'variable'):
                    if option in widget.keys():
                        variable = str(widget.cget(option))
                        if variable:
                            result.append({'path': path, 'type': 'variable', 'option': option,
                                           'value': widget.getvar(variable)})
                if isinstance(widget, ttk.Notebook):
                    result.append({'path': path, 'type': 'notebook',
                                   'selected': widget.index(widget.select())})
                if isinstance(widget, ttk.Treeview):
                    result.append({'path': path, 'type': 'tree', 'columns': list(widget['columns']),
                                   'headings': {c: widget.heading(c, 'text') for c in widget['columns']},
                                   'rows': [widget.item(i) for i in widget.get_children()]})
                elif isinstance(widget, tk.Text):
                    result.append({'path': path, 'type': 'text', 'text': widget.get('1.0', 'end-1c'),
                                   'tags': {tag: [str(v) for v in widget.tag_ranges(tag)] for tag in widget.tag_names() if tag != 'sel'}})
                elif isinstance(widget, (ttk.Label, tk.Label)):
                    result.append({'path': path, 'type': 'label', 'text': widget.cget('text'),
                                   'foreground': str(widget.cget('foreground'))})
            for index, child in enumerate(widget.winfo_children()):
                walk(child, path + [index])
        if restore is None:
            walk(self.tab_cdm, [])
            return result
        for item in restore:
            widget = self.tab_cdm
            try:
                for index in item['path']:
                    widget = widget.winfo_children()[index]
                if item['type'] == 'variable':
                    variable = str(widget.cget(item['option']))
                    if variable: widget.setvar(variable, item['value'])
                elif item['type'] == 'notebook' and isinstance(widget, ttk.Notebook):
                    widget.select(item['selected'])
                elif item['type'] == 'tree' and isinstance(widget, ttk.Treeview):
                    widget.configure(columns=item['columns'])
                    for c, text in item['headings'].items():
                        widget.heading(c, text=text)
                    widget.delete(*widget.get_children())
                    for row in item['rows']:
                        widget.insert('', 'end', text=row.get('text', ''), values=row.get('values', []), tags=row.get('tags', []))
                elif item['type'] == 'text' and isinstance(widget, tk.Text):
                    old_state = widget.cget('state')
                    widget.configure(state='normal')
                    widget.delete('1.0', 'end')
                    widget.insert('1.0', item['text'])
                    for tag, ranges in item.get('tags', {}).items():
                        for i in range(0, len(ranges), 2):
                            widget.tag_add(tag, ranges[i], ranges[i+1])
                    widget.configure(state=old_state)
                elif item['type'] == 'label' and isinstance(widget, (ttk.Label, tk.Label)):
                    widget.configure(text=item['text'])
                    if item['foreground']:
                        widget.configure(foreground=item['foreground'])
            except (IndexError, tk.TclError):
                continue

    def _store_calculation_results(self):
        self._sync_geology_session(refresh=False)
        from design_workflow import capture_workspace
        if self.design_mode.get() == 'TÍNH TOÀN TUYẾN':
            self.route_section_selector.stash()
            self._route_workspace = capture_workspace(self)
        else:
            self._single_workspace = capture_workspace(self)
        self.project.calculation_results = self._pack_saved_result({
            'version': 2, 'design_mode': self.design_mode.get(),
            'single_selected': getattr(self, '_single_selected_option', None),
            'single_batch_records': getattr(self, '_single_batch_records', []),
            'single_batch_failures': getattr(self, '_single_batch_failures', []),
            'before_sections': getattr(self, '_before_section_results', {}),
            'cdm_reports': self._cdm_reports,
            'cdm_method': self._cdm_active_method,
            'cdm_widgets': self._cdm_saved_widgets(),
            'steps': self._step_result_cache,
            'choice': self._choice_group_results,
            'saved_sections': getattr(self, '_saved_sections_data', []),
            'ai_analysis': getattr(self, '_ai_analysis_state', None),
            'geology_sessions': getattr(self, '_geology_sessions', {}),
            'section_excel_path': self._section_excel_path,
            'batch_candidates':getattr(self,'_batch_candidates',{}),
            'batch_runs':getattr(self,'_batch_runs',{}),
            'route_manual_designs':getattr(self,'_route_manual_designs',{}),
            'single_workspace':getattr(self,'_single_workspace',None),
            'route_workspace':getattr(self,'_route_workspace',None),
            'ai_support_settings':getattr(self,'_ai_support_settings',{}),
            'calculation_settings':self._stored_calculation_settings(),
            'results_folders':getattr(self,'_results_folders',{}),
            'last_rows': getattr(self, 'last_rows', []),
            'last_result_view': getattr(self, 'last_result_view', None),
        })

    def _restore_calculation_results(self):
        data = self._unpack_saved_result(self.project.calculation_results or {})
        self._single_workspace = data.get('single_workspace')
        self._route_workspace = data.get('route_workspace')
        self._ai_support_settings = data.get('ai_support_settings',{})
        self._calculation_settings = data.get('calculation_settings', {})
        self._apply_calculation_visibility()
        self._results_folders = data.get('results_folders',{})
        self._single_selected_option = data.get('single_selected')
        self._single_batch_records = data.get('single_batch_records', [])
        self._single_batch_failures = data.get('single_batch_failures', [])
        self._before_section_results = {int(k):v for k,v in data.get('before_sections', {}).items()}
        from design_workflow import normalize_mode
        self.design_mode.set(normalize_mode(data.get('design_mode', 'TÍNH MỘT ĐOẠN')))
        self._workflow_mode = self.design_mode.get()
        self._rebuild_workflow_navigation()
        self._cdm_reports = data.get('cdm_reports', {})
        self._batch_candidates={int(k):v for k,v in data.get('batch_candidates',{}).items()}
        self._batch_runs={int(k):v for k,v in data.get('batch_runs',{}).items()}
        self._route_manual_designs={int(k): {int(g): item for g,item in v.items()} for k,v in data.get('route_manual_designs',{}).items()}
        self.route_section_selector.active = None
        self.route_section_selector._visible_group = None
        self.route_section_selector.base = None
        self._cdm_active_method = data.get('cdm_method', 'standard')
        self._step_result_cache = {int(k): v for k, v in data.get('steps', {}).items()}
        self._choice_group_results = data.get('choice', {})
        if 'saved_sections' in data:
            self._saved_sections_data = data['saved_sections']
        from ai_analysis_data import new_session
        self._ai_analysis_state = data.get('ai_analysis') or new_session(Project())
        self._geology_sessions = data.get('geology_sessions') or {'TÍNH TOÀN TUYẾN': self._ai_analysis_state}
        self._geology_session_mode = None
        self._sync_geology_session(refresh=False)
        self._apply_calculation_visibility()
        if 'saved_sections' not in data: self._saved_sections_data = []
        if not data.get('section_excel_path'): self._section_excel_path = None
        if data.get('section_excel_path'):
            self._section_excel_path = data['section_excel_path']
        if hasattr(self, 'refresh_ai_analysis'):
            self.refresh_ai_analysis()
        self.last_rows = data.get('last_rows', [])
        self.last_result_view = data.get('last_result_view')
        self._cdm_saved_widgets(data.get('cdm_widgets', []))
        self.switch_step(0)
        self.draw_live_diagram()

    def save_file(self):
        if not self.path: return self.save_as()
        try:
            self.collect()
            self._store_calculation_results()
            save(self.project, self.path)
            self._mark_project_saved()
            self._update_file_identity()
            messagebox.showinfo('Lưu dự án', 'Đã lưu dự án thành công.')
            return True
        except Exception as exc:
            messagebox.showerror('Lỗi lưu', str(exc))
            return False

    def save_as(self):
        p = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('Dự án SoilFirm Pro', '*.json')])
        if not p:return False
        previous_path=self.path
        self.path=p
        saved=self.save_file()
        if not saved:self.path=previous_path
        return saved

    def close_window(self):
        self.exit_app()

    def _project_change_snapshot(self):
        from dataclasses import fields
        invalid_inputs = None
        try:
            self.collect()
        except (ValueError, TypeError):
            # Incomplete edited inputs also count as unsaved changes.
            invalid_inputs = {
                'inputs': {k: v.get() for k, v in self.vars.items()},
                'treatment': {k: v.get() for k, v in self.treatment_vars.items()},
                'stages': [[v.get() for v in row] for row in self.stage_vars],
            }
        project = {f.name: self._pack_saved_result(getattr(self.project, f.name))
                   for f in fields(self.project) if f.name != 'calculation_results'}
        # Compare project data and calculation results, excluding display state.
        results = {
            'single_selected': getattr(self, '_single_selected_option', None),
            'before_sections': getattr(self, '_before_section_results', {}),
            'cdm_reports': getattr(self, '_cdm_reports', {}),
            'steps': getattr(self, '_step_result_cache', {}),
            'choice': getattr(self, '_choice_group_results', {}),
            'saved_sections': getattr(self, '_saved_sections_data', []),
            'ai_analysis': getattr(self, '_ai_analysis_state', None),
            'batch_candidates': getattr(self, '_batch_candidates', {}),
            'batch_runs': getattr(self, '_batch_runs', {}),
            'single_workspace': getattr(self, '_single_workspace', None),
            'route_workspace': getattr(self, '_route_workspace', None),
            'route_manual_designs': getattr(self, '_route_manual_designs', {}),
        }
        return json.dumps({'project': project, 'results': self._pack_saved_result(results),
                           'incomplete_inputs': invalid_inputs},
                          sort_keys=True, ensure_ascii=False, default=str)

    def _mark_project_saved(self):
        self._saved_project_snapshot = self._project_change_snapshot()

    def _has_unsaved_changes(self):
        current = self._project_change_snapshot()
        return current != getattr(self, '_saved_project_snapshot', current)

    def _confirm_save_changes(self):
        # Tiếp tục thao tác theo yêu cầu; lưu dự án vẫn dùng các nút lưu hiện có.
        return True

    def exit_app(self):
        if not messagebox.askyesno('Thoát phần mềm', 'Bạn có muốn thoát phần mềm không?', parent=self):
            return
        if not self._confirm_save_changes():
            return
        workspace=getattr(self,'_ai_analysis_workspace',None)
        if workspace is not None:workspace.cancel_event.set()
        self.presence.stop()
        self.support_background.stop()
        self.destroy()

    def about(self):
        dlg = tk.Toplevel(self)
        dlg.title("About & Update - SoilFirm Pro")
        
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w = min(840, sw - 40)
        h = min(780, sh - 60)
        dlg.geometry(f"{w}x{h}+{int((sw - w) / 2)}+{int((sh - h) / 2)}")
        dlg.transient(self)
        dlg.grab_set()

        sf = _PopupScrollFrame(dlg)
        sf.pack(fill='both', expand=True)
        f_main = sf.scrollable_frame

        c_head = tk.Canvas(f_main, width=160, height=150, bg=COLORS['nav'], highlightthickness=0)
        c_head.pack(side='top', pady=(16, 0))

        lx, ly = 80, 75
        c_head.create_rectangle(lx - 55, ly + 20, lx + 55, ly + 40, fill='#162B44', outline='#244163', width=1.5)
        c_head.create_rectangle(lx - 55, ly + 40, lx + 55, ly + 60, fill='#112338', outline='#1F3A58', width=1.5)

        for dx in [lx - 36, lx - 18, lx, lx + 18, lx + 36]:
            c_head.create_line(dx, ly + 20, dx, ly + 50, fill=COLORS['accent'], width=2)
            c_head.create_polygon(dx - 4, ly + 50, dx + 4, ly + 50, dx, ly + 58, fill=COLORS['accent'], outline='')

        trap_pts = [lx - 25, ly - 30, lx + 25, ly - 30, lx + 50, ly + 20, lx - 50, ly + 20]
        c_head.create_polygon(trap_pts, fill='#17384D', outline=COLORS['accent'], width=2)
        c_head.create_text(lx, ly - 6, text="SF", fill='#FFFFFF', font=(UI_FONT, 18, 'bold'))

        for arr_x in [lx - 15, lx, lx + 15]:
            c_head.create_line(arr_x, ly - 50, arr_x, ly - 35, fill='#E5A642', width=2, arrow='last', arrowshape=(5, 8, 3))

        try:
            from PIL import Image, ImageTk
            with Image.open(os.path.join(os.path.dirname(__file__), 'logo.png')) as source:
                dlg._brand_image = ImageTk.PhotoImage(source.convert('RGBA').resize((140, 140), Image.Resampling.LANCZOS), master=dlg)
            c_head.delete('all')
            c_head.create_image(80, 75, image=dlg._brand_image)
        except (OSError, ValueError):
            pass

        tk.Label(f_main, text="SOILFIRM PRO", fg='white', bg=COLORS['nav'],
                 font=(UI_FONT, 14, 'bold'), pady=12).pack(fill='x')

        f_info = tk.Frame(f_main, bg=COLORS['background'], padx=40, pady=30)
        f_info.pack(fill='both', expand=True)

        info_text = (
            "Hệ Thống Phân Tích Lún & Thiết Kế Xử Lý Nền Đất Yếu\n"
            "Phiên bản: Build 2026.11\n\n"
            "Tác giả: Vũ Ngọc Ánh\n"
            "SĐT Hỗ trợ & Kích hoạt Key: 0869233097\n\n"
            "Cơ sở tham khảo mô hình tính toán:\n"
            "• TCCS 41:2022/TCĐBVN - Thiết kế đường ô tô trên nền đất yếu.\n"
            "• TCVN 9355:2013 - Gia cố nền đất yếu bằng bấc thấm.\n"
            "• 22 TCN 262-2000 - Khảo sát thiết kế nền đường ô tô đắp trên đất yếu."
        )

        tk.Label(f_info, text=info_text, justify='left', font=(UI_FONT, 9), bg=COLORS['background']).pack(anchor='w', pady=(0, 20))

        btn_box = tk.Frame(f_info, bg=COLORS['background'])
        btn_box.pack(fill='x', side='bottom', pady=(0, 10))

        ttk.Button(btn_box, text="Kiểm tra cập nhật", command=self.check_update).pack(side='left', padx=(0, 10))
        ttk.Button(btn_box, text="Đóng", command=dlg.destroy).pack(side='right')

    def check_update(self):
        CURRENT_VERSION = "2026.11"
        try:
            self.status_text.set('Đang kiểm tra bản cập nhật mới...')
            self.update_idletasks()
            data = self._fetch_latest_release()
            latest_version = str(data.get('tag_name', '')).lstrip('vV')
            if _version_key(latest_version) > _version_key(CURRENT_VERSION):
                asset = _release_installer_asset(data)
                msg = (f"Phát hiện bản phát hành mới: SoilFirm Pro v{latest_version}\n"
                       f"Phiên bản của bạn: v{CURRENT_VERSION}\n\n"
                       f"Nội dung mới:\n{data.get('body') or 'Xem chi tiết trên GitHub Releases.'}\n\n"
                       f"Bạn có muốn phần mềm tự tải và mở bộ cài không?")
                if asset is None:
                    messagebox.showwarning('Update',
                                           'Bản phát hành chưa có bộ cài EXE trong Assets.', parent=self)
                elif messagebox.askyesno('Update SOILFIRM PRO', msg, parent=self):
                    self._download_and_run_update(asset)
            else:
                messagebox.showinfo('Cập nhật',
                                    f'Phiên bản đang dùng: v{CURRENT_VERSION}\n'
                                    f'Phiên bản mới nhất trên GitHub: v{latest_version}.', parent=self)
        except (requests.RequestException, ValueError, KeyError) as exc:
            msg = (f'Không thể kiểm tra GitHub Releases: {exc}\n\n'
                   'Mở trang phát hành để xem trực tiếp?')
            if messagebox.askyesno("Lỗi mạng", msg, parent=self):
                webbrowser.open("https://github.com/vuanh97nd/SoilFirm/releases/latest")
        finally:
            self.status_text.set('Sẵn sàng')

    @staticmethod
    def _fetch_latest_release():
        response = requests.get(
            'https://api.github.com/repos/vuanh97nd/SoilFirm/releases/latest',
            headers={'Accept': 'application/vnd.github+json',
                     'User-Agent': 'SoilFirm-Professional'}, timeout=10)
        response.raise_for_status()
        return response.json()

    def _check_update_automatically(self):
        """Kiểm tra một lần khi đăng nhập, không khóa giao diện lúc gọi mạng."""
        def worker():
            try:
                self._update_check_queue.put(self._fetch_latest_release())
            except (requests.RequestException, ValueError):
                self._update_check_queue.put(None)
        threading.Thread(target=worker, daemon=True).start()
        self.after(200, self._finish_automatic_update_check)

    def _finish_automatic_update_check(self):
        try:
            release = self._update_check_queue.get_nowait()
        except queue.Empty:
            self.after(200, self._finish_automatic_update_check)
            return
        if release is None:
            return  # Mất mạng: mở phần mềm bình thường; nút Update vẫn dùng được.
        try:
            latest = str(release.get('tag_name', '')).lstrip('vV')
            if _version_key(latest) <= _version_key('2026.11'):
                return
        except ValueError:
            return
        asset = _release_installer_asset(release)
        if asset is None:
            messagebox.showinfo('Update SOILFIRM PRO',
                                f'Đã có bản {latest}, nhưng bản phát hành chưa có bộ cài EXE.',
                                parent=self)
            return
        if messagebox.askyesno('Update SOILFIRM PRO',
                               f'Đã có SoilFirm Pro v{latest}. Bạn có muốn tải và cài bản mới ngay không?',
                               parent=self):
            self._download_and_run_update(asset)

    def _download_and_run_update(self, asset):
        """Tải bộ cài vào thư mục tạm, xác thực kích thước/hash rồi khởi chạy."""
        url = asset['browser_download_url']
        expected_size = int(asset.get('size') or 0)
        digest = str(asset.get('digest') or '')
        fd, installer = tempfile.mkstemp(prefix='SoilFirm_Update_', suffix='.exe')
        os.close(fd)
        try:
            self.status_text.set('Đang tải bản Update...')
            self.update_idletasks()
            sha = hashlib.sha256()
            total = 0
            with requests.get(url, stream=True, timeout=(10, 60),
                              headers={'User-Agent': 'SoilFirm-Professional'}) as response:
                response.raise_for_status()
                with open(installer, 'wb') as target:
                    for chunk in response.iter_content(chunk_size=256 * 1024):
                        if not chunk:
                            continue
                        target.write(chunk)
                        sha.update(chunk)
                        total += len(chunk)
                        if expected_size:
                            self.status_text.set(f'Đang tải Update: {total * 100 // expected_size}%')
                            self.update_idletasks()
            if not total or (expected_size and total != expected_size):
                raise ValueError('Bộ cài tải về không đủ dung lượng.')
            if digest.startswith('sha256:') and sha.hexdigest().lower() != digest[7:].lower():
                raise ValueError('Mã SHA-256 của bộ cài không khớp bản phát hành.')
            subprocess.Popen([installer], cwd=os.path.dirname(installer))
            self.after_idle(self.destroy)
        except (OSError, ValueError, requests.RequestException) as exc:
            try:
                os.remove(installer)
            except OSError:
                pass
            messagebox.showerror('Update', f'Không thể tải hoặc mở bộ cài:\n{exc}', parent=self)

    def refresh_stage_inputs(self):
        if not hasattr(self, 'stage_entries') or getattr(self, '_updating_stages', False): return
        self._updating_stages = True
        try:
            second = self.stage_flags[2].get() or self.stage_flags[3].get()
            third = self.stage_flags[3].get()
            if third and not self.stage_flags[2].get(): self.stage_flags[2].set(True)
            
            total = sum(number_or_zero(self.vars[k].get()) for k in ('h_design', 'h_kcad')) + self.project.h_bl
            h1 = number_or_zero(self.stage_vars[0][0].get())
            h2 = number_or_zero(self.stage_vars[1][0].get())
            
            for i in range(3):
                if not self.stage_vars[i][1].get().strip():
                    self.stage_vars[i][1].set('10')

            self.stage_entries[0][0].configure(state='normal' if second else 'readonly')
            if not second: self.stage_vars[0][0].set(f'{total:.2f}')
                
            self.stage_entries[1][0].configure(state='normal' if third else 'readonly' if second else 'disabled')
            self.stage_entries[2][0].configure(state='readonly' if third else 'disabled')
            
            if second and not third: self.stage_vars[1][0].set(f'{max(0.0, total - h1):.2f}')
            if third: self.stage_vars[2][0].set(f'{max(0.0, total - h1 - h2):.2f}')
            else: self.stage_vars[2][0].set('')
                
            for i, active in ((0, True), (1, second), (2, third)):
                for entry in self.stage_entries[i][1:]:
                    entry.configure(state='normal' if active else 'disabled')
        finally:
            self._updating_stages = False


if __name__ == '__main__':
    app = App()
    app.new()
    app.mainloop()
