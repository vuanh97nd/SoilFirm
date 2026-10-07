"""
Module: splash.py
Màn hình khởi động (Splash Screen) hiển thị Logo kỹ thuật SOILFIRM PRO.
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from ui_theme import COLORS, UI_FONT, UI_FONT_MONO


class SplashScreen(tk.Toplevel):
    def __init__(self, root: tk.Tk, duration_ms: int = 1800):
        super().__init__(root)
        self.root = root
        self.duration_ms = duration_ms

        # Cấu hình cửa sổ không viền, nằm chính giữa màn hình
        self.overrideredirect(True)
        self.configure(bg=COLORS['nav'])
        self.attributes('-topmost', True)

        # Mở rộng cửa sổ lên 720x420 để chứa logo lớn hơn
        width, height = 720, 420
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = int((sw - width) / 2)
        y = int((sh - height) / 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

        self._build_ui(width, height)

    def _build_ui(self, w: int, h: int):
        canvas = tk.Canvas(self, width=w, height=h, bg=COLORS['nav'], highlightthickness=0)
        canvas.pack(fill='both', expand=True)

        # 1. Khung viền kỹ thuật vi mô
        canvas.create_rectangle(2, 2, w - 3, h - 3, outline='#1F3A58', width=1)
        canvas.create_rectangle(6, 6, w - 7, h - 7, outline='#172D46', width=1)

        from pathlib import Path
        from tkinter import font as tkfont
        try:
            from PIL import Image, ImageTk
            with Image.open(Path(__file__).with_name('logo.png')) as source:
                self._brand_image = ImageTk.PhotoImage(source.convert('RGBA').resize((215, 215), Image.Resampling.LANCZOS), master=self)
            canvas.create_image(145, 155, image=self._brand_image)
        except (OSError, ValueError):
            canvas.create_text(145, 155, text='AI', fill='#00D4E8', font=(UI_FONT, 50, 'bold'))
        # Repaint the pile area as canvas layers so only the piles animate.
        left, top, scale = 37.5, 47.5, 215.0/1280.0
        # Lớp chữ riêng cho màn hình khởi động; ảnh nhận diện gốc giữ nguyên.
        canvas.create_polygon(*[coordinate for px, py in
            ((425, 491), (830, 491), (936, 742), (915, 785),
             (350, 785), (315, 742))
            for coordinate in (left+px*scale, top+py*scale)],
            fill='#073A53', outline='')
        self._logo_ai_font = tkfont.Font(root=self, family=UI_FONT,
                                          size=-4, weight='bold')
        self._logo_ai_a = canvas.create_text(145, top+620*scale, text='A',
            fill='#FFFFFF', font=self._logo_ai_font, anchor='w')
        self._logo_ai_i = canvas.create_text(145, top+620*scale, text='I',
            fill='#00D4E8', font=self._logo_ai_font, anchor='w')
        x1, x2 = left+180*scale, left+1050*scale
        pile_top, pile_bottom = top+755*scale, top+1030*scale
        split = top+875*scale
        canvas.create_rectangle(x1, pile_top, x2, split, fill='#68696D', outline='')
        canvas.create_rectangle(x1, split, x2, top+1060*scale, fill='#37373B', outline='')
        for row in range(5):
            y = pile_top+5+row*9
            for column in range(12):
                x = x1+4+column*12+(row%2)*3
                radius = 1.1 if row < 2 else 1.5
                canvas.create_oval(x-radius, y-radius, x+radius, y+radius,
                                   fill='#97989A' if row < 2 else '#747578', outline='')
        self._animated_piles = []
        for center in (386, 568, 752, 936):
            x = left+center*scale
            half = 35*scale
            face = canvas.create_polygon(x-half, pile_top, x+half, pile_top,
                x+half, pile_top, x, pile_top, x-half, pile_top,
                fill='#94A3B8', outline='#4B6372', width=.7)
            highlight = canvas.create_line(x-half+1.8, pile_top, x-half+1.8, pile_top,
                                           fill='#D8E2E8', width=1.8)
            self._animated_piles.append((face, highlight, x, half, pile_top, pile_bottom))

        font = tkfont.Font(root=self, family=UI_FONT, size=29, weight='bold')
        ai_font = tkfont.Font(root=self, family=UI_FONT, size=11, weight='bold')
        # Đo theo DPI hiện tại để toàn bộ tên và AI luôn nằm trong khung.
        available_width = w - 270 - 30
        while (font.measure('SOILFIRM PRO') + 6 + ai_font.measure('AI') > available_width
               and font.actual('size') > 12):
            font.configure(size=font.actual('size') - 1)
        x, y = 270, 155
        self._soilfirm_letters = []
        word = 'SOILFIRM'
        word_width = max(1, font.measure(word))
        for index, letter in enumerate(word):
            offset = font.measure(word[:index])
            glow = [canvas.create_text(x+offset+dx, y+dy, text=letter,
                       fill=COLORS['nav'], font=font, anchor='w', state='hidden')
                    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2))]
            item = canvas.create_text(x+offset, y, text=letter,
                                      fill='#A9BDCF', font=font, anchor='w')
            self._soilfirm_letters.append((item,
                (offset+font.measure(letter)/2)/word_width, glow))
        x += font.measure('SOILFIRM')
        canvas.create_text(x, y, text=' PRO', fill='#00D4E8', font=font, anchor='w')
        x += font.measure(' PRO')
        self._ai_text = canvas.create_text(x+3, y-font.metrics('ascent')*0.45, text='AI',
                           fill='#00D4E8', font=ai_font, anchor='w')
        self._brand_fonts = (font, ai_font)
        subtitle_font = tkfont.Font(root=self, family=UI_FONT, size=13)
        while (subtitle_font.measure('Hỗ trợ thiết kế xử lý nền đất yếu') > available_width
               and subtitle_font.actual('size') > 8):
            subtitle_font.configure(size=subtitle_font.actual('size') - 1)
        self._brand_fonts += (subtitle_font,)
        canvas.create_text(270, 205, text='Hỗ trợ thiết kế xử lý nền đất yếu',
                           fill='#B8CEDD', font=subtitle_font, anchor='w')

        # 4. Thanh tiến trình và nhãn trạng thái khởi động (Luôn bám đáy theo h)
        
        # Nhãn trạng thái (Cách đáy 65px)
        self.lbl_status = canvas.create_text(45, h - 65, text="Đang khởi động SoilFirm Pro…",
                                             fill='#8DA8BB', font=(UI_FONT, 10), anchor='w')
        # Nhãn phiên bản
        canvas.create_text(w - 45, h - 65, text="v2026.11", fill='#5C7A92',
                           font=(UI_FONT, 10, 'bold'), anchor='e')

        # Thanh tiến trình loading tùy biến (Cách đáy 45px)
        self.bar_bg = canvas.create_rectangle(45, h - 45, w - 45, h - 39, fill='#1A344E', outline='')
        self.bar_fg = canvas.create_rectangle(45, h - 45, 45, h - 39, fill=COLORS['accent'], outline='')
        self._progress_light = canvas.create_oval(42, h-46, 48, h-38,
                                                  fill='#D7FCFF', outline='')
        self.canvas = canvas
        self.animate_logo_letters(0.0)

        # Bản quyền (Cách đáy 18px)
        canvas.create_text(w / 2, h - 18, text="© 2026 SoilFirm Engineering Systems. All rights reserved.",
                           fill='#47637A', font=(UI_FONT, 9), anchor='center')

    def animate_logo_letters(self, fraction):
        fraction = min(1.0, max(0.0, fraction))
        # Kích thước đi cùng tiến trình thật, không đạt gần cực đại quá sớm.
        size = round(4+56*fraction)
        if getattr(self, '_logo_ai_size', None) != size:
            self._logo_ai_font.configure(size=-size)
            self._logo_ai_size = size
            width_a = self._logo_ai_font.measure('A')
            width_i = self._logo_ai_font.measure('I')
            x = 145-(width_a+width_i)/2
            y = 47.5+620*(215.0/1280.0)
            self.canvas.coords(self._logo_ai_a, x, y)
            self.canvas.coords(self._logo_ai_i, x+width_a, y)

    def animate_wordmark(self, elapsed):
        """Dải sáng qua lại liên tục trong nét chữ, đổi hướng mềm ở hai đầu."""
        import math
        center = -0.10+1.20*(1-math.cos(elapsed*math.pi/0.85))/2
        for item, position, glow in self._soilfirm_letters:
            intensity = math.exp(-((position-center)/0.22)**2)
            core = min(1.0, intensity*1.15)
            color = '#' + ''.join(f'{round(a+(b-a)*core):02x}'
                                 for a, b in zip((185, 205, 221), (247, 252, 255)))
            self.canvas.itemconfigure(item, fill=color)
            glow_color = '#' + ''.join(f'{round(a+(b-a)*intensity):02x}'
                for a, b in zip((23, 45, 70), (105, 180, 201)))
            for halo in glow:
                self.canvas.itemconfigure(halo, fill=glow_color,
                    state='normal' if intensity > 0.08 else 'hidden')

    def set_progress(self, progress, message, flush=True):
        """Cập nhật sau mỗi giai đoạn khởi tạo thực tế, không theo bộ đếm."""
        progress = min(1.0, max(0.0, progress))
        self.animate_logo_letters(progress)
        self.canvas.coords(self.bar_fg, 45, 375, 45+630*progress, 381)
        if getattr(self, '_last_status', None) != message:
            self.canvas.itemconfigure(self.lbl_status, text=message)
            self._last_status = message
        head = 45+630*progress
        self.canvas.coords(self._progress_light, head-3, 374, head+3, 382)
        start, finish = '#94A3B8', '#00D4E8'
        a = tuple(int(start[i:i+2], 16) for i in (1, 3, 5))
        b = tuple(int(finish[i:i+2], 16) for i in (1, 3, 5))
        color = '#' + ''.join(f'{round(x+(y-x)*progress):02x}' for x, y in zip(a, b))
        for index, (face, highlight, x, half, top, bottom) in enumerate(self._animated_piles):
            pile_progress = min(1.0, max(0.0, (progress-index*0.08)/0.76))
            end = top+(bottom-top)*pile_progress
            tip = min(3.0, (end-top)/3.0)
            self.canvas.coords(face, x-half, top, x+half, top,
                               x+half, end-tip, x, end, x-half, end-tip)
            self.canvas.itemconfigure(face, fill=color)
            self.canvas.coords(highlight, x-half+1.8, top, x-half+1.8, end-tip)
        if flush:
            self.update_idletasks()

    def start_animation(self, on_complete):
        steps = [
            (0.25, 'Đang khởi động SoilFirm Pro…'),
            (0.55, 'Đang tải giao diện…'),
            (0.95, 'Đang chuẩn bị không gian làm việc…'),
            (1.00, 'Sẵn sàng làm việc.'),
        ]
        started = time.perf_counter()
        duration = max(1, self.duration_ms)/1000.0
        def color_between(start, end, progress):
            a = tuple(int(start[i:i+2], 16) for i in (1,3,5))
            b = tuple(int(end[i:i+2], 16) for i in (1,3,5))
            return '#' + ''.join(f'{round(x+(y-x)*progress):02x}' for x,y in zip(a,b))
        def tick():
            if not self.winfo_exists():
                return
            progress = min(1.0, max(0.0, (time.perf_counter()-started)/duration))
            self.canvas.coords(self.bar_fg, 45, 375, 45+630*progress, 381)
            message = next((message for limit,message in steps if progress <= limit), steps[-1][1])
            self.canvas.itemconfigure(self.lbl_status, text=message)
            color = color_between('#94A3B8', '#00D4E8', progress)
            for face,highlight,x,half,top,bottom in self._animated_piles:
                end = top+(bottom-top)*progress
                tip = min(3.0, (end-top)/3.0)
                self.canvas.coords(face, x-half,top,x+half,top,
                    x+half,end-tip,x,end,x-half,end-tip)
                self.canvas.itemconfigure(face, fill=color)
                self.canvas.coords(highlight, x-half+1.8,top,x-half+1.8,end-tip)
            if progress < 1.0:
                self.after(16, tick)
            else:
                self.canvas.itemconfigure(self.lbl_status, text=steps[-1][1])
                def complete():
                    if self.winfo_exists():
                        self.destroy()
                        on_complete()
                self.after_idle(complete)
        tick()


class StartupSplashProcess:
    """Gửi tiến trình thực sang cửa sổ logo độc lập, không chặn Tk chính."""
    def __init__(self):
        import subprocess
        import sys
        from pathlib import Path
        command = [sys.executable]
        if not getattr(sys, 'frozen', False):
            command.append(str(Path(__file__).with_name('main.py')))
        command.append('--soilfirm-startup-splash')
        self._process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        self._closed = False

    def winfo_exists(self):
        return not self._closed and self._process.poll() is None

    def _send(self, data):
        import json
        if not self.winfo_exists():
            return
        try:
            self._process.stdin.write(json.dumps(data, ensure_ascii=False) + '\n')
            self._process.stdin.flush()
        except (OSError, ValueError):
            self._closed = True

    def set_progress(self, progress, message):
        self._send({'p': min(1.0, max(0.0, progress)), 'm': message})

    def destroy(self):
        if self._closed:
            return
        self._send({'close': True})
        self._closed = True
        try:
            self._process.stdin.close()
        except (OSError, ValueError):
            pass


def run_startup_splash():
    """Tk và hoạt ảnh chỉ chạy trong tiến trình con; stdin chỉ đọc ở worker."""
    import json
    import math
    import queue
    import sys
    import threading
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    root.withdraw()
    splash = SplashScreen(root)
    splash.deiconify()
    splash.lift()
    messages = queue.Queue()

    def receive():
        try:
            input_stream = getattr(sys.stdin, 'buffer', None)
            if input_stream is None:
                # EXE --noconsole có thể đặt sys.stdin=None dù đã nhận pipe.
                import os
                if sys.platform == 'win32':
                    import ctypes
                    from ctypes import wintypes
                    import msvcrt
                    get_handle = ctypes.windll.kernel32.GetStdHandle
                    get_handle.argtypes = [wintypes.DWORD]
                    get_handle.restype = wintypes.HANDLE
                    handle = get_handle(0xFFFFFFF6)  # STD_INPUT_HANDLE
                    if not handle or handle == ctypes.c_void_p(-1).value:
                        return
                    descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | os.O_BINARY)
                    input_stream = os.fdopen(descriptor, 'rb')
                else:
                    input_stream = os.fdopen(0, 'rb')
            for line in input_stream:
                try:
                    value = json.loads(line.decode('utf-8'))
                    if isinstance(value, dict):
                        messages.put(value)
                except (ValueError, UnicodeError):
                    continue
        except (OSError, ValueError):
            pass
        finally:
            messages.put({'close': True})

    threading.Thread(target=receive, daemon=True).start()
    state = {'p': 0.0, 'target': 0.0, 'm': 'Đang khởi động SoilFirm Pro…',
             'last': time.perf_counter(), 'next_frame': time.perf_counter(),
             'closing': False}
    started = state['last']

    def frame():
        while True:
            try:
                value = messages.get_nowait()
            except queue.Empty:
                break
            if value.get('close'):
                state['closing'] = True
                state['target'] = 1.0
                state['m'] = 'Sẵn sàng làm việc.'
                continue
            if isinstance(value.get('p'), (float, int)):
                state['target'] = max(state['target'], min(1.0, value['p']))
            if isinstance(value.get('m'), str):
                state['m'] = value['m']
        now = time.perf_counter()
        dt = min(0.1, max(0.0, now-state['last']))
        state['last'] = now
        # Làm dịu bước nhảy; không tự tiến lên khi chưa nhận giai đoạn mới.
        if state['closing']:
            # Vẽ cả phần còn lại thay vì nhảy 100% rồi đóng trong cùng một frame.
            state['p'] = min(1.0, state['p']+dt*1.8)
        else:
            state['p'] += (state['target']-state['p'])*(1-math.exp(-dt/0.65))
        splash.set_progress(state['p'], state['m'], flush=False)
        splash.animate_wordmark(now-started)
        pulse = (1+math.sin((now-started)*math.pi))/2
        color = '#' + ''.join(f'{round(a+(b-a)*pulse):02x}'
                             for a, b in zip((0, 150, 177), (130, 240, 248)))
        palette = ((0, 212, 232), (167, 139, 250), (244, 114, 182),
                   (245, 196, 81), (74, 222, 128))
        phase = ((now-started)%6)/6*len(palette)
        index = int(phase)
        blend = phase-index
        blend = blend*blend*(3-2*blend)
        ai_color = '#' + ''.join(f'{round(a+(b-a)*blend):02x}'
            for a, b in zip(palette[index], palette[(index+1)%len(palette)]))
        splash.canvas.itemconfigure(splash._ai_text, fill=ai_color)
        splash.canvas.itemconfigure(splash._progress_light, fill=color)
        if state['closing'] and state['p'] >= 1.0:
            # Giữ mức đầy qua một chu kỳ vẽ màn hình trước khi báo kết thúc.
            root.after(34, root.destroy)
            return
        # Cọc vẫn có ánh sáng nhẹ khi chờ, chiều dài không vượt tiến trình thật.
        for index, (_, highlight, _, _, _, _) in enumerate(splash._animated_piles):
            light = (1+math.sin((now-started)*math.pi-index*0.45))/2
            shade = '#' + ''.join(f'{round(a+(b-a)*light):02x}'
                                 for a, b in zip((92, 162, 178), (216, 248, 252)))
            splash.canvas.itemconfigure(highlight, fill=shade)
        # Giữ nhịp khung hình theo đồng hồ, không cộng dồn thời gian vẽ.
        state['next_frame'] = max(state['next_frame']+1/60, time.perf_counter())
        delay = max(1, round((state['next_frame']-time.perf_counter())*1000))
        root.after(delay, frame)

    frame()
    root.mainloop()
    return 0
