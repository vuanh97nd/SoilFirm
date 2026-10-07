"""Khởi động SOILFIRM PRO; báo và ghi lỗi thay vì tự đóng sau màn hình logo."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import traceback
from datetime import datetime


def record_error(exc_type, exc, tb):
    text = ''.join(traceback.format_exception(exc_type, exc, tb))
    roots = [Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'SoilFirm' / 'logs',
             Path(tempfile.gettempdir()) / 'SoilFirm' / 'logs']
    for root in roots:
        try:
            root.mkdir(parents=True, exist_ok=True)
            path = root / 'startup_error.log'
            with path.open('a', encoding='utf-8') as stream:
                stream.write(f'\n[{datetime.now().isoformat(timespec="seconds")}] Python {sys.version.split()[0]}\n{text}')
            return str(path)
        except OSError:
            continue
    return ''


def show_error(exc_type, exc, tb, parent=None):
    path = record_error(exc_type, exc, tb)
    message = f'SoilFirm Pro gặp lỗi:\n{exc}\n\n'
    message += f'Chi tiết đã lưu tại:\n{path}' if path else 'Không ghi được tệp lỗi. Hãy chụp thông báo này.'
    root = None
    try:
        import tkinter as tk
        from tkinter import messagebox
        if parent is None:
            root = tk.Tk()
            root.withdraw()
            parent = root
        messagebox.showerror('Lỗi SOILFIRM PRO', message, parent=parent)
    except Exception:
        if os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, message, 'Lỗi SOILFIRM PRO', 0x10)
            except Exception:
                pass
        elif sys.stderr is not None:
            print(message, file=sys.stderr)
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass


def run():
    if sys.version_info < (3, 8):
        raise RuntimeError('SOILFIRM PRO yêu cầu Python 3.8 trở lên.')
    # Thiết lập DPI trước cửa sổ đầu tiên; app.py dùng cùng chế độ này.
    # Nếu thiết lập sau khi logo xuất hiện, Windows đổi tỷ lệ giữa chừng.
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    import tkinter as tk
    from splash import SplashScreen, StartupSplashProcess
    startup_root = None
    splash = None
    try:
        try:
            splash = StartupSplashProcess()
        except OSError:
            # Giữ đường khởi động cũ nếu hệ điều hành không tạo được tiến trình.
            startup_root = tk.Tk()
            startup_root.withdraw()
            splash = SplashScreen(startup_root)
            splash.deiconify()
            splash.lift()
        splash.set_progress(0.0, 'Đang khởi động SoilFirm Pro…')
        if startup_root is not None:
            startup_root.update()
        from app import App
        app = App(startup_splash=splash)
        app.report_callback_exception = lambda et, ev, tb: show_error(et, ev, tb, app)
        app.mainloop()
    finally:
        if splash is not None:
            try:
                splash.destroy()
            except tk.TclError:
                pass
        if startup_root is not None:
            try:
                startup_root.destroy()
            except tk.TclError:
                pass
    return 0


def main():
    try:
        if len(sys.argv) >= 2 and sys.argv[1] == '--soilfirm-startup-splash':
            from splash import run_startup_splash
            return run_startup_splash()
        if len(sys.argv) >= 4 and sys.argv[1] == '--soilfirm-music-web':
            from weather_panel import run_music_web
            run_music_web(sys.argv[2], sys.argv[3])
            return 0
        if len(sys.argv) >= 3 and sys.argv[1] == '--soilfirm-intro-video':
            from soilfirm_intro import run_video
            run_video(sys.argv[2])
            return 0
        return run()
    except Exception:
        show_error(*sys.exc_info())
        return 1


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    sys.exit(main())
