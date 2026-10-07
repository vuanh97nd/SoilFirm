"""Phát video giới thiệu SOILFIRM PRO có giọng đọc, bằng WebView2 trong tiến trình riêng."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
import os
import re
import subprocess
import sys
import threading

VIDEO_NAME = 'SoilFirm_Gioi_thieu_30s.mp4'


def video_path():
    roots = [Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)),
             Path(sys.executable).resolve().parent, Path(__file__).resolve().parent]
    path = next((root / VIDEO_NAME for root in roots if (root / VIDEO_NAME).is_file()), None)
    if path is None:
        raise FileNotFoundError(f'Thiếu video {VIDEO_NAME} trong bộ cài.')
    return path


def show_intro(parent, duration_seconds=30, on_complete=None):
    existing = getattr(parent, '_soilfirm_intro_process', None)
    if existing is not None and existing.poll() is None:
        return existing
    path = video_path()
    args = [sys.executable, '--soilfirm-intro-video', str(path)]
    if not getattr(sys, 'frozen', False):
        args.insert(1, str(Path(__file__).resolve().with_name('main.py')))
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
    process = subprocess.Popen(args, creationflags=flags)
    parent._soilfirm_intro_process = process
    def poll():
        try:
            if not parent.winfo_exists():
                if process.poll() is None:
                    process.terminate()
                return
            if process.poll() is None:
                parent.after(100, poll)
            elif on_complete:
                parent.after_idle(on_complete)
        except Exception:
            if process.poll() is None:
                process.terminate()
    def on_destroy(event):
        if event.widget is parent and process.poll() is None:
            process.terminate()
    parent.bind('<Destroy>', on_destroy, add='+')
    parent.after(100, poll)
    return process


def run_video(path):
    import webview
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    # Quyền tự phát có tiếng chỉ áp dụng cho trình phát giới thiệu này.
    flags = os.environ.get('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', '')
    os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'] = flags + ' --autoplay-policy=no-user-gesture-required'
    page = '''<!doctype html><html lang="vi"><meta charset="utf-8">
    <style>html,body{margin:0;background:#0b1828;color:#fff;height:100%;font-family:Segoe UI,Arial}
    video{width:100%;height:calc(100% - 54px);object-fit:contain;background:#0b1828}
    footer{height:54px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;box-sizing:border-box}
    button{border:0;border-radius:5px;background:#235875;color:white;padding:9px 16px;cursor:pointer}
    #start{position:fixed;inset:0;background:#0b1828dd;display:none;align-items:center;justify-content:center}</style>
    <video id="video" src="/media.mp4" autoplay playsinline controls preload="auto"></video>
    <footer><span>SOILFIRM PRO · Giới thiệu phần mềm</span><button onclick="closeIntro()">Bỏ qua / Vào phần mềm</button></footer>
    <div id="start"><button onclick="play()">Phát video có giọng đọc</button></div>
    <script>const video=document.getElementById('video');
    function closeIntro(){video.pause();window.pywebview.api.close();}
    function play(){video.muted=false;video.volume=1;video.play().then(()=>document.getElementById('start').style.display='none').catch(()=>document.getElementById('start').style.display='flex');}
    video.onended=closeIntro;window.addEventListener('pywebviewready',play);
    document.addEventListener('keydown',e=>{if(e.key==='Escape')closeIntro();});</script></html>'''
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.path == '/':
                content = page.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return
            if self.path != '/media.mp4':
                self.send_error(404)
                return
            size = path.stat().st_size
            start, end = 0, size-1
            requested = self.headers.get('Range')
            if requested:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
                if not match or not any(match.groups()):
                    self.send_error(416)
                    return
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = min(int(right), size-1) if right else size-1
                else:
                    start = max(0, size-int(right))
                if start > end or start >= size:
                    self.send_error(416)
                    return
            self.send_response(206 if requested else 200)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Content-Length', str(end-start+1))
            self.send_header('Accept-Ranges', 'bytes')
            if requested:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            try:
                with path.open('rb') as stream:
                    stream.seek(start)
                    remaining = end-start+1
                    while remaining:
                        block = stream.read(min(262144, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        remaining -= len(block)
            except (BrokenPipeError, ConnectionResetError):
                pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    class Api:
        def close(self):
            window.destroy()
    window = webview.create_window('SoilFirm Pro · Giới thiệu phần mềm',
        f'http://127.0.0.1:{server.server_port}/', width=1060, height=670,
        min_size=(720, 480), background_color='#0B1828', js_api=Api())

    # Cùng nguồn nhận diện với cửa sổ chính và bộ cài.
    def apply_brand_icon():
        if sys.platform != 'win32':
            return
        try:
            from System import Action
            from System.Drawing import Icon
            icon_path = Path(__file__).with_name('logo.ico')
            if not icon_path.is_file():
                return
            native = window.native
            def assign_icon():
                window._sf_brand_icon = Icon(str(icon_path))
                native.Icon = window._sf_brand_icon
            if native.InvokeRequired:
                native.Invoke(Action(assign_icon))
            else:
                assign_icon()
        except Exception:
            # Không ngăn mở cửa sổ nếu nền tảng không hỗ trợ icon WinForms.
            return
    icon_event = getattr(window.events, 'before_show', window.events.shown)
    icon_event += apply_brand_icon
    try:
        webview.start()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    run_video(sys.argv[1] if len(sys.argv)>1 else video_path())
