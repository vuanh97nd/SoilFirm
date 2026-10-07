"""Input parsing and small Tk helpers shared by SoilFirm screens."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk


def number(value, label='Giá trị'):
    try:
        result = float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} phải là số hợp lệ.') from exc
    if not math.isfinite(result):
        raise ValueError(f'{label} phải là số hữu hạn.')
    return result


def number_or_zero(value):
    try:
        return number(value)
    except ValueError:
        return 0.0


def clean_km_str(value):
    return str(value).strip().upper().removeprefix('KM').strip()


def correct_fill_height(schedule, day):
    if not schedule or day <= 0:
        return 0.0
    previous = 0.0
    for stage in schedule:
        start, end = stage['bắt_đầu'], stage['kết_thúc']
        if day < start:
            return previous
        if day <= end:
            return stage['h_đầu'] + (stage['h_cuối']-stage['h_đầu']) * (
                (day-start)/max(end-start, 1e-9))
        previous = stage['h_cuối']
    return previous


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollable_frame = ttk.Frame(self.canvas)
        window = self.canvas.create_window(0, 0, window=self.scrollable_frame, anchor='nw')
        vertical = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.scrollable_frame.bind('<Configure>', lambda event:
            self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda event:
            self.canvas.itemconfigure(window, width=max(event.width, self.scrollable_frame.winfo_reqwidth())))

    @staticmethod
    def _route_wheel(event):
        widget = event.widget
        while widget is not None:
            if isinstance(widget, ScrollableFrame):
                delta = getattr(event, 'delta', 0)
                amount = -1 if delta > 0 or getattr(event, 'num', None) == 4 else 1
                if event.state & 1:
                    widget.canvas.xview_scroll(amount, 'units')
                else:
                    widget.canvas.yview_scroll(amount, 'units')
                return 'break'
            widget = getattr(widget, 'master', None)
