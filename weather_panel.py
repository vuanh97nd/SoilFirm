"""Đồng hồ Việt Nam, thời tiết biểu tượng màu sắc, tin tức, giá vàng SJC và Radio FM / Nhạc online."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import base64
from queue import Empty, Queue
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import webbrowser
import xml.etree.ElementTree as ET

import requests
from lunar_calendar import solar_to_lunar


WEEKDAYS = ('Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ Nhật')
LOC_FILE = 'weather_location.json'

PROVINCES = {
    'Tự động (Dò qua IP/GPS)': (None, None),
    'Nam Định': (20.4200, 106.1683),
    'Hà Nội': (21.0285, 105.8542),
    'Hải Phòng': (20.8449, 106.6881),
    'TP. Hồ Chí Minh': (10.8231, 106.6297),
    'Đà Nẵng': (16.0544, 108.2022),
    'Ninh Bình': (20.2506, 105.9745),
    'Hà Nam': (20.5452, 105.9123),
    'Thái Bình': (20.4463, 106.3366),
    'Hải Dương': (20.9373, 106.3146),
    'Bắc Ninh': (21.1861, 106.0763),
    'Quảng Ninh': (20.9500, 107.0833),
    'Thanh Hóa': (19.8067, 105.7852),
    'Nghệ An': (18.6734, 105.6813),
    'Huế': (16.4637, 107.5909),
    'Nha Trang': (12.2388, 109.1967),
    'Cần Thơ': (10.0452, 105.7469),
    'Bình Dương': (11.0000, 106.6667),
    'Đồng Nai': (10.9574, 106.8427),
    'Lâm Đồng (Đà Lạt)': (11.9404, 108.4583),
}

# Danh sách luồng Radio FM & Nhạc trực tuyến chuẩn MP3 chất lượng cao
RADIO_STATIONS = {
    '☕ Lofi Chill 24/7': 'https://streams.ilovemusic.de/iloveradio17.mp3',
    '📻 VOV1 - Thời sự': 'https://vov1.vov.vn/',
    '📻 VOV3 - Âm nhạc': 'https://vov3.vov.vn/',
    '📻 VOV Giao thông': 'https://vov.gov.vn/nghe-va-xem-truc-tuyen',
    '🎷 Jazz & Coffee': 'https://jazz-wr01.ice.infomaniak.ch/jazz-wr01-128.mp3',
    '🎸 Acoustic Thư giãn': 'https://stream.zeno.fm/4w8yr2y120hvv',
    '🎵 Zing MP3': 'https://zingmp3.vn/',
    '♫ YouTube': 'https://www.youtube.com/',
    '🌏 BBC World News': 'http://stream.live.vc.bbcmedia.co.uk/bbc_world_service',
}


WEB_MUSIC_URLS = {
    '📻 VOV1 - Thời sự': 'https://vov1.vov.vn/',
    '📻 VOV3 - Âm nhạc': 'https://vov3.vov.vn/',
    '📻 VOV Giao thông': 'https://vov.gov.vn/nghe-va-xem-truc-tuyen',
    '🎵 Zing MP3': 'https://zingmp3.vn/',
    '♫ YouTube': 'https://www.youtube.com/',
}


def run_music_web(initial_url, command_file):
    """Cửa sổ WebView2 riêng, chạy trên main thread của tiến trình con."""
    from tkinter import messagebox
    try:
        import webview
        from webview.menu import Menu, MenuAction
    except ImportError:
        root=tk.Tk();root.withdraw()
        messagebox.showerror('Thiếu trình phát',
            'Chưa cài pywebview. Chạy run.bat hoặc cài: python -m pip install "pywebview>=5,<7"', parent=root)
        root.destroy()
        return
    allowed=set(WEB_MUSIC_URLS.values())
    if initial_url not in allowed:
        initial_url='https://vov.gov.vn/nghe-va-xem-truc-tuyen'
    storage=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'SOILFIRM PRO'/'MusicWeb'
    storage.mkdir(parents=True,exist_ok=True)
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER']=False
    webview.settings['ALLOW_DOWNLOADS']=False
    closed=threading.Event()
    quitting=threading.Event()
    current_source={"url":initial_url}
    window=webview.create_window('SoilFirm Pro · Nghe nhạc',initial_url,
        width=1080,height=730,min_size=(700,480),resizable=True,
        background_color='#13283E',text_select=True)
    window.events.closed += closed.set

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
    def hide_on_close():
        if quitting.is_set():
            return True
        timer=threading.Timer(.05,window.hide)
        timer.daemon=True
        timer.start()
        return False
    window.events.closing += hide_on_close
    def quit_player():
        quitting.set()
        window.destroy()
    def select(url):
        current_source['url']=url
        window.load_url(url)
        window.set_title('SoilFirm Pro · '+('YouTube' if 'youtube' in url else 'Zing MP3' if 'zingmp3' in url else 'VOV'))
    menu=[Menu('VOV',[
              MenuAction('VOV1 · Thời sự',lambda:select('https://vov1.vov.vn/')),
              MenuAction('VOV3 · Âm nhạc',lambda:select('https://vov3.vov.vn/')),
              MenuAction('Các kênh VOV',lambda:select('https://vov.gov.vn/nghe-va-xem-truc-tuyen'))]),
          Menu('Zing MP3',[MenuAction('Nghe Zing MP3',lambda:select('https://zingmp3.vn/'))]),
          Menu('YouTube',[MenuAction('Nghe YouTube',lambda:select('https://www.youtube.com/'))]),
          Menu('Điều khiển',[
              MenuAction('Tải lại',lambda:window.load_url(window.get_current_url() or initial_url)),
              MenuAction('Chạy nền',window.hide),
              MenuAction('Dừng nhạc và đóng',quit_player)])]
    def publish_track():
        script = r"""(() => {
            const metadata = navigator.mediaSession ? navigator.mediaSession.metadata : null;
            const media = Array.from(document.querySelectorAll('audio, video'));
            const active = media.find(item => !item.paused && !item.ended);
            const loaded = active || media.find(item => item.currentTime > 0);
            let title = metadata && metadata.title ? metadata.title : '';
            let artist = metadata && metadata.artist ? metadata.artist : '';
            if (!title && loaded && location.hostname.includes('youtube.com')) {
                const heading = document.querySelector('ytd-watch-metadata h1 yt-formatted-string, #title h1 yt-formatted-string');
                title = heading ? heading.textContent.trim() : '';
            }
            if (!title && loaded) {
                title = document.title.replace(/\s*[-|]\s*(YouTube|Zing MP3).*$/i, '').trim();
            }
            const playing = !!active || (navigator.mediaSession && navigator.mediaSession.playbackState === 'playing');
            return {title: title.slice(0, 240), artist: artist.slice(0, 120), playing: !!playing};
        })()"""
        while not closed.wait(1):
            try:
                track = window.evaluate_js(script)
                if not isinstance(track, dict):
                    continue
                track['updated'] = time.time()
                destination = Path(command_file + '.status')
                temporary = destination.with_suffix('.status.tmp')
                temporary.write_text(json.dumps(track, ensure_ascii=False), encoding='utf-8')
                os.replace(temporary, destination)
            except Exception:
                if quitting.is_set():
                    return
    def receive_commands():
        threading.Thread(target=publish_track, daemon=True).start()
        try:
            previous=json.loads(Path(command_file).read_text(encoding='utf-8')).get('token')
        except (OSError,ValueError):
            previous=None
        while not closed.wait(.25):
            try:
                data=json.loads(Path(command_file).read_text(encoding='utf-8'))
                token=data.get('token')
                if token==previous:
                    continue
                previous=token
                if data.get('close'):
                    quit_player();return
                target=data.get('url')
                if target in allowed:
                    if target != current_source['url']:
                        select(target)
                    window.show()
                    window.restore()
            except (OSError,ValueError):
                continue
    try:
        webview.start(receive_commands,gui='edgechromium' if sys.platform=='win32' else None,
                      private_mode=False,storage_path=str(storage),menu=menu)
    except Exception as exc:
        root=tk.Tk();root.withdraw()
        messagebox.showerror('Không mở được trình phát',
            'Cần Microsoft Edge WebView2 Runtime để nghe trong phần mềm.\n'
            'Cài WebView2 Runtime rồi mở lại.\n\n'+str(exc),parent=root)
        root.destroy()


class EmbeddedMusicPlayer:
    """Một cửa sổ nghe nhạc dùng chung cho các nút trong thanh bên."""
    def __init__(self):
        self.process=None
        self._stopping=None
        fd,self.command_file=tempfile.mkstemp(prefix='soilfirm_music_',suffix='.json')
        os.close(fd)

    def open(self,url):
        if url not in set(WEB_MUSIC_URLS.values()):
            return False
        if self._stopping is not None and self._stopping.poll() is None:
            try:self._stopping.terminate()
            except OSError:pass
            return False
        data={'url':url,'token':time.time_ns()}
        temporary=self.command_file+'.tmp'
        Path(temporary).write_text(json.dumps(data),encoding='utf-8')
        os.replace(temporary,self.command_file)
        if self.process is not None and self.process.poll() is None:
            return True
        try:os.remove(self.command_file + '.status')
        except OSError:pass
        if getattr(sys,'frozen',False):
            cmd=[sys.executable,'--soilfirm-music-web',url,self.command_file]
        else:
            cmd=[sys.executable,str(Path(__file__).resolve().with_name('main.py')),
                 '--soilfirm-music-web',url,self.command_file]
        try:
            child_env=os.environ.copy()
            if getattr(sys,'frozen',False):
                child_env['PYINSTALLER_RESET_ENVIRONMENT']='1'
            self.process=subprocess.Popen(cmd,env=child_env,stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            return True
        except OSError:
            self.process=None
            return False

    def stop(self):
        process,self.process=self.process,None
        self._stopping=process
        if process is not None and process.poll() is None:
            try:
                Path(self.command_file).write_text(json.dumps({'close':True,'token':time.time_ns()}),encoding='utf-8')
            except OSError:
                process.terminate()
            def cleanup():
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.terminate()

            threading.Thread(target=cleanup,daemon=True).start()
        else:
            try:os.remove(self.command_file)
            except OSError:pass



class NativeRadioEngine:
    """Phát radio bằng Windows Media Player trong tiến trình STA riêng."""
    def __init__(self):
        self.process = None
        self._generation = 0
        fd, self.vol_file = tempfile.mkstemp(prefix='soilfirm_radio_', suffix='.cfg')
        os.close(fd)

    def play(self, url: str, volume: int = 75, on_status=None):
        self.stop()
        if sys.platform != 'win32' or not url:
            return False
        generation = self._generation
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        script = r"""
$ErrorActionPreference = 'Stop'
$wmp = $null
try {
    Add-Type -AssemblyName System.Windows.Forms
    $wmp = New-Object -ComObject WMPlayer.OCX
    $wmp.settings.autoStart = $true
    $wmp.settings.volume = __VOLUME__
    $wmp.URL = __URL__
    $wmp.controls.play()
    $started = $false
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        [System.Windows.Forms.Application]::DoEvents()
        if ($wmp.error.errorCount -gt 0) { throw 'Stream playback failed' }
        $state = $wmp.playState
        if ($state -eq 3 -and -not $started) {
            [Console]::WriteLine('EVT:PLAYING')
            [Console]::Out.Flush()
            $started = $true
        }
        if ((-not $started -and $timer.Elapsed.TotalSeconds -gt 25) -or
            ($started -and ($state -eq 1 -or $state -eq 8))) {
            throw 'Stream stopped or connection timed out'
        }
        if (Test-Path -LiteralPath __VOLFILE__) {
            try {
                $v = [IO.File]::ReadAllText(__VOLFILE__).Trim()
                $level = 0
                if ([int]::TryParse($v, [ref]$level)) {
                    $wmp.settings.volume = [Math]::Max(0, [Math]::Min(100, $level))
                }
            } catch { }
        }
        Start-Sleep -Milliseconds 100
    }
} catch {
    [Console]::WriteLine('EVT:ERROR')
    [Console]::Out.Flush()
} finally {
    if ($null -ne $wmp) {
        try { $wmp.controls.stop(); $wmp.close() } catch { }
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($wmp)
    }
}
"""
        script = script.replace('__VOLUME__', str(max(0, min(100, int(volume)))))
        script = script.replace('__URL__', quote(url)).replace('__VOLFILE__', quote(self.vol_file))
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        self.set_volume(volume)
        try:
            process = subprocess.Popen(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-STA',
                 '-EncodedCommand', encoded],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, text=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.process = process
        except OSError:
            return False

        def monitor_output():
            failed = False
            try:
                for line in process.stdout:
                    if generation != self._generation:
                        return
                    event = line.strip()
                    if event == 'EVT:PLAYING' and on_status:
                        on_status('playing')
                    elif event == 'EVT:ERROR':
                        failed = True
                        if on_status:
                            on_status('error')
                        break
                process.wait()
            finally:
                if process.stdout:
                    process.stdout.close()
                if generation == self._generation:
                    self.process = None
                    if not failed and on_status:
                        on_status('error')
        threading.Thread(target=monitor_output, daemon=True).start()
        return True

    def set_volume(self, volume: int):
        try:
            with open(self.vol_file, 'w', encoding='ascii') as stream:
                stream.write(str(max(0, min(100, int(volume)))))
        except OSError:
            pass

    def stop(self):
        self._generation += 1
        process, self.process = self.process, None
        if process is not None:
            try:
                process.terminate()
            except OSError:
                pass
        try:
            os.remove(self.vol_file)
        except OSError:
            pass


def _weather_style(code):
    if code == 0:
        return '☀️', '#FBBF24'
    if code in (1, 2):
        return '🌤', '#FDE047'
    if code == 3:
        return '☁', '#94A3B8'
    if code in (45, 48):
        return '🌫', '#CBD5E1'
    if code in (51, 53, 55, 56, 57):
        return '🌦', '#60A5FA'
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return '🌧', '#38BDF8'
    if code in (95, 96, 99):
        return '⚡', '#FACC15'
    if code in (71, 73, 75, 77, 85, 86):
        return '❄', '#BAE6FD'
    return '⛅', '#FDE047'


def _load_saved_location():
    try:
        if os.path.exists(LOC_FILE):
            with open(LOC_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('name') and data.get('lat') is not None:
                    return data['name'], data['lat'], data['lon']
    except Exception:
        pass
    return None


def _save_location(name, lat, lon):
    try:
        with open(LOC_FILE, 'w', encoding='utf-8') as f:
            json.dump({'name': name, 'lat': lat, 'lon': lon}, f, ensure_ascii=False)
    except Exception:
        pass


def _device_coordinates_gps():
    if sys.platform != 'win32':
        return None
    script = ("Add-Type -AssemblyName System.Device; "
              "$w = New-Object System.Device.Location.GeoCoordinateWatcher; "
              "if (-not $w.TryStart($false, [TimeSpan]::FromSeconds(3))) { exit 1 }; "
              "$p = $w.Position.Location; "
              "if ($p.IsUnknown) { exit 1 }; "
              "[Console]::WriteLine($p.Latitude.ToString([Globalization.CultureInfo]::InvariantCulture) "
              "+ ',' + $p.Longitude.ToString([Globalization.CultureInfo]::InvariantCulture)); "
              "$w.Stop()")
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                capture_output=True, text=True, timeout=5, check=True,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        lat, lon = map(float, result.stdout.strip().split(','))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    except Exception:
        pass
    return None


def _get_location_and_coords():
    saved = _load_saved_location()
    if saved:
        return saved[1], saved[2], saved[0]

    try:
        res = requests.get('https://ipwho.is/', timeout=4).json()
        if res.get('success'):
            city = res.get('city') or res.get('region') or 'Hà Nội'
            return float(res['latitude']), float(res['longitude']), city
    except Exception:
        pass

    try:
        res = requests.get('http://ip-api.com/json/?fields=status,city,regionName,lat,lon', timeout=4).json()
        if res.get('status') == 'success':
            city = res.get('city') or res.get('regionName') or 'Hà Nội'
            return float(res['lat']), float(res['lon']), city
    except Exception:
        pass

    coords = _device_coordinates_gps()
    if coords:
        return coords[0], coords[1], 'Vị trí hiện tại'

    return 21.0285, 105.8542, 'Hanoi'


def _fetch_latest_news():
    sources = [
        ('VNEXPRESS', 'https://vnexpress.net/rss/tin-moi-nhat.rss'),
        ('BÁO MỚI', 'https://baomoi.com/rss/tin-moi.rss'),
        ('TUỔI TRẺ', 'https://tuoitre.vn/rss/tin-moi-nhat.rss')
    ]
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    for source_name, url in sources:
        try:
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200 and res.content:
                root = ET.fromstring(res.content)
                items = []
                for item in root.findall('./channel/item')[:12]:
                    title = (item.findtext('title') or '').strip()
                    link = (item.findtext('link') or '').strip()
                    if title and link:
                        items.append({'title': title, 'link': link, 'source': source_name})
                if items:
                    return items
        except Exception:
            continue
    return []


def _fetch_gold_data():
    headers = {'User-Agent': 'Mozilla/5.0'}
    world_price = 2650.0
    sjc_buy = 83.5
    sjc_sell = 85.5
    history = []

    try:
        res = requests.get(
            'https://api.binance.com/api/v3/klines?symbol=PAXGUSDT&interval=1d&limit=8',
            headers=headers, timeout=6
        ).json()
        if isinstance(res, list) and len(res) >= 2:
            closes = [float(k[4]) for k in res]
            world_price = closes[-1]
            history = closes
    except Exception:
        history = [2610.0, 2625.5, 2620.0, 2638.0, 2645.0, 2640.0, 2655.0]
        world_price = history[-1]

    try:
        tygia_res = requests.get('https://tygia.com/json.php?ran=0&rate=0&gold=1', headers=headers, timeout=4).json()
        golds = tygia_res.get('golds', [{}])[0].get('value', [])
        sjc_item = next((g for g in golds if 'SJC' in g.get('type', '')), None)
        if sjc_item:
            sjc_buy = float(sjc_item.get('buy', 83.5))
            sjc_sell = float(sjc_item.get('sell', 85.5))
        else:
            raise ValueError
    except Exception:
        base_vnd = (world_price * 1.20565 * 25.45) / 1000.0
        sjc_buy = round(base_vnd + 2.5, 1)
        sjc_sell = round(sjc_buy + 2.0, 1)

    change = round(history[-1] - history[-2], 1) if len(history) >= 2 else 0.0

    return {
        'world': round(world_price, 1),
        'sjc_buy': sjc_buy,
        'sjc_sell': sjc_sell,
        'history': history,
        'change': change
    }


def build_weather_clock(parent):
    BG_CARD = '#13283E'
    BORDER_COLOR = '#20466B'
    CLOCK_COLOR = '#22D3EE'
    DATE_COLOR = '#CBD5E1'
    TEMP_COLOR = '#F8FAFC'
    NEWS_ACCENT = '#38BDF8'
    GOLD_ACCENT = '#FBBF24'
    CHART_BG = '#0B1928'
    RADIO_ACCENT = '#C084FC'

    panel = tk.Frame(parent, bg=BG_CARD, padx=8, pady=6,
                     highlightthickness=1, highlightbackground=BORDER_COLOR)
    panel.pack(fill='x', pady=(0, 4))

    news_header_text = tk.StringVar(value='● TIN MỚI')
    news_text = tk.StringVar(value='Đang tải tin tức…')
    gold_text_sjc_short = tk.StringVar(value='Đang tải…')
    gold_text_world = tk.StringVar(value='Thế giới: Đang tải…')
    gold_text_sjc_full = tk.StringVar(value='SJC: Đang tải…')
    city_name_text = tk.StringVar(value='📍 Đang tìm vị trí…')
    temp_text = tk.StringVar(value='--.-°C')
    date_text = tk.StringVar()
    time_text = tk.StringVar()

    events = Queue()
    radio_engine = NativeRadioEngine()
    music_player = EmbeddedMusicPlayer()

    # ================= 1. KHỐI TIN TỨC =================
    news_section = tk.Frame(panel, bg=BG_CARD)
    news_section.pack(fill='x')

    news_header = tk.Frame(news_section, bg=BG_CARD)
    news_header.pack(fill='x')

    tk.Label(news_header, textvariable=news_header_text, bg=BG_CARD, fg=NEWS_ACCENT,
             font=('Times New Roman', 7, 'bold')).pack(side='left')

    btn_toggle_news = tk.Label(news_header, text='▲', bg=BG_CARD, fg='#94A3B8',
                               font=('Segoe UI', 7, 'bold'), cursor='hand2')
    btn_toggle_news.pack(side='right')

    news_body = tk.Frame(news_section, bg=BG_CARD)
    news_body.pack(fill='x', pady=(1, 2))

    current_news_url = {'url': ''}
    news_label = tk.Label(news_body, textvariable=news_text, bg=BG_CARD, fg='#E2E8F0',
                          wraplength=175, justify='left', font=('Times New Roman', 8),
                          cursor='hand2')
    news_label.pack(fill='x', anchor='w')
    news_body.bind('<Configure>', lambda event: news_label.configure(wraplength=max(60,event.width-4)))

    def on_click_news(_event):
        if current_news_url['url']:
            webbrowser.open_new_tab(current_news_url['url'])
    news_label.bind('<Button-1>', on_click_news)

    news_state = {'visible': True}
    def toggle_news(_event=None):
        if news_state['visible']:
            news_body.pack_forget()
            btn_toggle_news.config(text='▼', fg='#38BDF8')
            news_state['visible'] = False
        else:
            news_body.pack(fill='x', pady=(1, 2))
            btn_toggle_news.config(text='▲', fg='#94A3B8')
            news_state['visible'] = True

    btn_toggle_news.bind('<Button-1>', toggle_news)

    # ================= 2. KHỐI GIÁ VÀNG =================
    tk.Frame(panel, bg=BORDER_COLOR, height=1).pack(fill='x', pady=(3, 3))

    gold_section = tk.Frame(panel, bg=BG_CARD)
    gold_section.pack(fill='x')

    gold_header = tk.Frame(gold_section, bg=BG_CARD, cursor='hand2')
    gold_header.pack(fill='x')

    tk.Label(gold_header, text='● VÀNG SJC', bg=BG_CARD, fg=GOLD_ACCENT,
             font=('Times New Roman', 7, 'bold'), cursor='hand2').pack(side='left')

    btn_toggle_gold = tk.Label(gold_header, text='▼', bg=BG_CARD, fg='#FBBF24',
                               font=('Segoe UI', 7, 'bold'), cursor='hand2')
    btn_toggle_gold.pack(side='left', padx=(4, 0))

    tk.Label(gold_header, textvariable=gold_text_sjc_short, bg=BG_CARD, fg='#FDE68A',
             font=('Times New Roman', 7, 'bold'), cursor='hand2').pack(side='right')

    gold_body = tk.Frame(gold_section, bg=BG_CARD)

    tk.Label(gold_body, textvariable=gold_text_world, bg=BG_CARD, fg='#93C5FD',
             font=('Times New Roman', 7)).pack(anchor='w', pady=(2, 0))

    tk.Label(gold_body, textvariable=gold_text_sjc_full, bg=BG_CARD, fg='#FEF08A',
             font=('Times New Roman', 7)).pack(anchor='w', pady=(0, 2))

    chart_canvas = tk.Canvas(gold_body, width=175, height=20, bg=CHART_BG,
                             highlightthickness=1, highlightbackground=BORDER_COLOR, cursor='hand2')
    chart_canvas.pack(fill='x', pady=(1, 2))

    gold_state = {'visible': False}
    def toggle_gold(_event=None):
        if gold_state['visible']:
            gold_body.pack_forget()
            btn_toggle_gold.config(text='▼', fg='#FBBF24')
            gold_state['visible'] = False
        else:
            gold_body.pack(fill='x')
            btn_toggle_gold.config(text='▲', fg='#94A3B8')
            gold_state['visible'] = True

    btn_toggle_gold.bind('<Button-1>', toggle_gold)
    gold_header.bind('<Button-1>', toggle_gold)

    gold_full_data = {'data': None}

    def open_gold_detail(_event):
        data = gold_full_data['data']
        if not data:
            return
        top = tk.Toplevel(panel)
        top.title("Chi Tiết Thị Trường Giá Vàng")
        top.geometry("320x220")
        top.configure(bg='#0F172A')
        top.attributes('-topmost', True)

        tk.Label(top, text="BẢNG GIÁ VÀNG TRONG NƯỚC & THẾ GIỚI", bg='#0F172A', fg=GOLD_ACCENT,
                 font=('Times New Roman', 11, 'bold')).pack(pady=(12, 6))

        info_frame = tk.Frame(top, bg='#1E293B', padx=12, pady=10)
        info_frame.pack(fill='x', padx=14, pady=6)

        change_sym = "▲" if data['change'] >= 0 else "▼"
        change_color = "#34D399" if data['change'] >= 0 else "#F87171"

        tk.Label(info_frame, text=f"Thế giới (XAU/USD): ${data['world']:,.1f}/oz",
                 bg='#1E293B', fg='#F8FAFC', font=('Times New Roman', 9, 'bold')).pack(anchor='w')
        tk.Label(info_frame, text=f"Biến động 24h: {change_sym} {abs(data['change'])} USD",
                 bg='#1E293B', fg=change_color, font=('Times New Roman', 8, 'bold')).pack(anchor='w', pady=(1, 4))

        tk.Label(info_frame, text=f"SJC Mua vào: {data['sjc_buy']:.1f} tr/lượng",
                 bg='#1E293B', fg='#FDE68A', font=('Times New Roman', 9)).pack(anchor='w')
        tk.Label(info_frame, text=f"SJC Bán ra:  {data['sjc_sell']:.1f} tr/lượng",
                 bg='#1E293B', fg='#FDE68A', font=('Times New Roman', 9)).pack(anchor='w')

    chart_canvas.bind('<Button-1>', open_gold_detail)

    # ================= 3. KHỐI RADIO FM & NHẠC TRỰC TUYẾN =================
    tk.Frame(panel, bg=BORDER_COLOR, height=1).pack(fill='x', pady=(3, 3))

    radio_section = tk.Frame(panel, bg=BG_CARD)
    radio_section.pack(fill='x')

    radio_header = tk.Frame(radio_section, bg=BG_CARD, cursor='hand2')
    radio_header.pack(fill='x')

    tk.Label(radio_header, text='● FM & NHẠC', bg=BG_CARD, fg=RADIO_ACCENT,
             font=('Times New Roman', 7, 'bold'), cursor='hand2').pack(side='left')

    btn_toggle_radio = tk.Label(radio_header, text='▲', bg=BG_CARD, fg='#94A3B8',
                                font=('Segoe UI', 7, 'bold'), cursor='hand2')
    btn_toggle_radio.pack(side='left', padx=(4, 0))

    radio_status_text = tk.StringVar(value='■ Sẵn sàng')
    lbl_radio_status = tk.Label(radio_section, textvariable=radio_status_text, bg=BG_CARD, fg='#F87171',
                                font=('Times New Roman', 7, 'bold'), cursor='hand2')
    lbl_radio_status.configure(anchor='w', justify='left', wraplength=160)
    lbl_radio_status.pack(fill='x', pady=(2, 1))
    radio_section.bind('<Configure>', lambda event: lbl_radio_status.configure(wraplength=max(60, event.width-4)))

    radio_body = tk.Frame(radio_section, bg=BG_CARD)
    radio_body.pack(fill='x', pady=(2, 2))

    # Menu chọn kênh
    station_names = list(RADIO_STATIONS.keys())
    selected_station = tk.StringVar(value=station_names[0])
    station_menu = tk.OptionMenu(radio_body, selected_station, *station_names)
    station_menu.config(bg='#1E293B', fg='#F8FAFC', activebackground='#334155', activeforeground='#F8FAFC',
                        highlightthickness=0, bd=0, relief='flat', font=('Times New Roman', 8),
                        anchor='w', padx=4, pady=1, width=1)
    station_menu['menu'].config(bg='#1E293B', fg='#F8FAFC', activebackground='#0284C7', font=('Times New Roman', 8))

    # Nút điều khiển và âm lượng
    ctrl_row = tk.Frame(radio_body, bg=BG_CARD)

    btn_play = tk.Label(ctrl_row, text='▶ Phát', bg='#0284C7', fg='white',
                        font=('Times New Roman', 8, 'bold'), padx=8, pady=2,
                        cursor='hand2', relief='flat')
    btn_play.pack(side='left', padx=(0, 4))

    tk.Label(ctrl_row, text='🔊', bg=BG_CARD, fg='#94A3B8', font=('Segoe UI Emoji', 8)).pack(side='left')

    vol_scale = tk.Scale(ctrl_row, from_=0, to=100, orient='horizontal', showvalue=0,
                         bg=BG_CARD, fg='#CBD5E1', troughcolor='#1E293B',
                         highlightthickness=0, bd=0, sliderlength=10, sliderrelief='flat',
                         activebackground='#A78BFA', width=8, length=65)
    vol_scale.set(75)
    vol_scale.pack(side='left', fill='x', expand=True, padx=(2, 0))

    player_state = {'is_playing': False, 'generation': 0}

    def toggle_play_radio(_event=None):
        name = selected_station.get()
        if name in WEB_MUSIC_URLS:
            open_music_web(WEB_MUSIC_URLS[name])
            return
        player_state['generation'] += 1
        generation = player_state['generation']
        if player_state['is_playing']:
            radio_engine.stop()
            player_state['is_playing'] = False
            btn_play.config(text='▶ Phát', bg='#0284C7')
            radio_status_text.set('■ Đã dừng')
            lbl_radio_status.config(fg='#F87171')
        else:
            url = RADIO_STATIONS.get(selected_station.get(), '')
            radio_status_text.set('Kết nối…')
            lbl_radio_status.config(fg='#FBBF24')
            btn_play.config(text='⏸ Dừng', bg='#DC2626')
            player_state['is_playing'] = True

            def on_status_received(status):
                if status == 'playing':
                    events.put(('radio_status', (generation, 'playing', '▶ Đang phát', '#34D399')))
                elif status == 'error':
                    events.put(('radio_status', (generation, 'error', '✖ Lỗi kênh', '#F87171')))

            ok = radio_engine.play(url, volume=vol_scale.get(), on_status=on_status_received)
            if not ok:
                events.put(('radio_status', (generation, 'error', '✖ Lỗi phát', '#F87171')))

    def open_music_web(url):
        player_state['generation'] += 1
        radio_engine.stop()
        player_state['is_playing'] = False
        btn_play.config(text='▶ Mở' if selected_station.get() in WEB_MUSIC_URLS else '▶ Phát', bg='#0284C7')
        try:
            opened = music_player.open(url)
        except Exception:
            opened = False
        radio_status_text.set('♫ Đã mở trình phát' if opened else '✖ Lỗi trình phát')
        lbl_radio_status.config(fg='#F87171')

    web_row = tk.Frame(radio_body, bg=BG_CARD)
    web_row.pack(fill='x', pady=(3, 0))
    for label, url in (('VOV', 'https://vov.gov.vn/nghe-va-xem-truc-tuyen'),
                       ('Zing MP3', 'https://zingmp3.vn/'),
                       ('YouTube', 'https://www.youtube.com/')):
        tk.Button(web_row, text=label, command=lambda target=url: open_music_web(target),
                  bg='#1E293B', fg='#C4B5FD', activebackground='#334155',
                  activeforeground='white', relief='flat', bd=0,
                  font=('Times New Roman', 8), padx=3, pady=2,
                  cursor='hand2').pack(side='left', expand=True, fill='x', padx=1)

    def stop_all_music():
        player_state['generation'] += 1
        radio_engine.stop()
        music_player.stop()
        player_state['is_playing'] = False
        btn_play.config(text='▶ Mở' if selected_station.get() in WEB_MUSIC_URLS else '▶ Phát', bg='#0284C7')
        radio_status_text.set('■ Đã dừng')
        lbl_radio_status.config(fg='#F87171')
    tk.Button(radio_body,text='■ Dừng nhạc',command=stop_all_music,
              bg='#1E293B',fg='#FCA5A5',activebackground='#334155',
              relief='flat',bd=0,font=('Times New Roman',8),cursor='hand2',
              pady=2).pack(fill='x',pady=(2,0))

    btn_play.bind('<Button-1>', toggle_play_radio)

    def on_station_changed(*_args):
        was_playing = player_state['is_playing']
        player_state['generation'] += 1
        radio_engine.stop()
        player_state['is_playing'] = False
        web_station = selected_station.get() in WEB_MUSIC_URLS
        btn_play.config(text='▶ Mở' if web_station else '▶ Phát', bg='#0284C7')
        radio_status_text.set('♫ Trình phát web' if web_station else '■ Sẵn sàng')
        lbl_radio_status.config(fg='#F87171')
        if was_playing and not web_station:
            toggle_play_radio()
    selected_station.trace_add('write', on_station_changed)

    def on_volume_change(val):
        radio_engine.set_volume(int(val))
    vol_scale.config(command=on_volume_change)

    radio_state = {'visible': True}
    def toggle_radio_ui(_event=None):
        if radio_state['visible']:
            radio_body.pack_forget()
            btn_toggle_radio.config(text='▼', fg='#C084FC')
            radio_state['visible'] = False
        else:
            radio_body.pack(fill='x', pady=(2, 2))
            btn_toggle_radio.config(text='▲', fg='#94A3B8')
            radio_state['visible'] = True

    btn_toggle_radio.bind('<Button-1>', toggle_radio_ui)
    radio_header.bind('<Button-1>', toggle_radio_ui)

    # ================= 4. KHỐI ĐỒNG HỒ, THỜI TIẾT & LỊCH =================
    tk.Frame(panel, bg=BORDER_COLOR, height=1).pack(fill='x', pady=(3, 3))

    bottom_section = tk.Frame(panel, bg=BG_CARD)
    bottom_section.pack(fill='x')

    clock_temp_row = tk.Frame(bottom_section, bg=BG_CARD)
    clock_temp_row.pack(anchor='w', pady=(1, 1))

    tk.Label(clock_temp_row, textvariable=time_text, bg=BG_CARD, fg=CLOCK_COLOR,
             font=('Times New Roman', 15, 'bold')).pack(side='left')

    icon_label = tk.Label(clock_temp_row, text='☀️', bg=BG_CARD, fg='#FBBF24',
                          font=('Segoe UI Emoji', 12))
    icon_label.pack(side='left', padx=(5, 2))

    temp_label = tk.Label(clock_temp_row, textvariable=temp_text, bg=BG_CARD, fg=TEMP_COLOR,
                          font=('Times New Roman', 9, 'bold'))
    temp_label.pack(side='left')

    date_loc_row = tk.Frame(bottom_section, bg=BG_CARD)
    date_loc_row.pack(fill='x', pady=(2, 1))

    tk.Label(date_loc_row, textvariable=date_text, bg=BG_CARD, fg=DATE_COLOR,
             font=('Times New Roman', 8, 'bold'),
             justify='left').pack(side='left', anchor='w')

    loc_btn = tk.Label(date_loc_row, textvariable=city_name_text, bg=BG_CARD, fg='#94A3B8',
                       font=('Times New Roman', 8, 'underline'), cursor='hand2')
    loc_btn.pack(side='right', anchor='e', padx=(2, 0))

    def open_city_selector(_event=None):
        win = tk.Toplevel(panel)
        win.title("Chọn vị trí của bạn")
        win.geometry("260x280")
        win.configure(bg='#0F172A')
        win.attributes('-topmost', True)

        tk.Label(win, text="CHỌN TỈNH / THÀNH PHỐ", bg='#0F172A', fg='#38BDF8',
                 font=('Times New Roman', 10, 'bold')).pack(pady=(10, 6))

        box = tk.Listbox(win, bg='#1E293B', fg='#F8FAFC', selectbackground='#0284C7',
                         font=('Times New Roman', 9), height=9, relief='flat')
        box.pack(fill='both', expand=True, padx=12, pady=4)

        for p in PROVINCES:
            box.insert('end', p)

        def save_and_close():
            sel = box.curselection()
            if sel:
                chosen = box.get(sel[0])
                if chosen == 'Tự động (Dò qua IP/GPS)':
                    if os.path.exists(LOC_FILE):
                        os.remove(LOC_FILE)
                else:
                    coords = PROVINCES[chosen]
                    _save_location(chosen, coords[0], coords[1])
                win.destroy()
                fetch_weather_task()

        tk.Button(win, text="Xác nhận", command=save_and_close, bg='#0284C7', fg='white',
                  font=('Times New Roman', 9, 'bold'), relief='flat', padx=10).pack(pady=8)

    loc_btn.bind('<Button-1>', open_city_selector)

    # ================= 5. NGUỒN CHÂN THẺ =================
    tk.Label(panel, text='Open-Meteo · VnExpress · SJC/Kitco · Radio Online', bg=BG_CARD, fg='#64748B',
             font=('Times New Roman', 7, 'italic')).pack(anchor='w', pady=(2, 0))

    # ================= LOGIC DỮ LIỆU & LUỒNG =================
    busy = {'running': False}
    news_store = {'list': [], 'index': 0}

    def render_sparkline(history, change):
        chart_canvas.delete('all')
        w, h = 175, 20
        if not history or len(history) < 2:
            chart_canvas.create_text(w // 2, h // 2, text="Đang vẽ...", fill='#64748B',
                                     font=('Times New Roman', 7))
            return

        min_val, max_val = min(history), max(history)
        span = max(max_val - min_val, 1.0)
        padding_y = 3
        usable_h = h - padding_y * 2
        step_x = w / (len(history) - 1)

        points = []
        for i, val in enumerate(history):
            x = i * step_x
            y = h - padding_y - ((val - min_val) / span) * usable_h
            points.append((x, y))

        line_color = '#10B981' if change >= 0 else '#EF4444'

        chart_canvas.create_line(0, h // 2, w, h // 2, fill='#162536', dash=(2, 2))

        for i in range(len(points) - 1):
            chart_canvas.create_line(points[i][0], points[i][1], points[i+1][0], points[i+1][1],
                                     fill=line_color, width=1.8, smooth=True)

        last_x, last_y = points[-1]
        chart_canvas.create_oval(last_x - 2.5, last_y - 2.5, last_x + 2.5, last_y + 2.5,
                                 fill=line_color, outline='#FFFFFF')

    def tick():
        if not panel.winfo_exists():
            return
        now = datetime.now(timezone(timedelta(hours=7)))
        lunar_day, lunar_month, lunar_year, leap = solar_to_lunar(now.day, now.month, now.year)
        suffix = ' nhuận' if leap else ''
        date_text.set(f'{WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y}\n'
                      f'Âm lịch: {lunar_day:02d}/{lunar_month:02d}{suffix}/{lunar_year}')
        time_text.set(now.strftime('%H:%M:%S'))
        panel.after(1000, tick)

    def fetch_weather_task():
        if busy['running'] or not panel.winfo_exists():
            return
        busy['running'] = True

        def worker():
            try:
                lat, lon, place_name = _get_location_and_coords()
                api_key = os.environ.get('SOILFIRM_WEATHER_API_KEY', '').strip()
                endpoint = ('https://customer-api.open-meteo.com/v1/forecast' if api_key
                            else 'https://api.open-meteo.com/v1/forecast')
                params = {
                    'latitude': lat, 'longitude': lon,
                    'current': 'temperature_2m,weather_code',
                    'timezone': 'Asia/Ho_Chi_Minh',
                }
                if api_key:
                    params['apikey'] = api_key
                response = requests.get(endpoint, params=params, timeout=6)
                response.raise_for_status()
                current = response.json()['current']
                icon_char, icon_color = _weather_style(int(current["weather_code"]))
                temp_val = f'{float(current["temperature_2m"]):.1f}°C'
            except Exception:
                place_name = 'Hanoi'
                icon_char, icon_color = '☀️', '#FBBF24'
                temp_val = '28.0°C'

            events.put(('weather', (place_name, icon_char, icon_color, temp_val)))

        threading.Thread(target=worker, daemon=True).start()

    def fetch_news_task():
        def worker():
            items = _fetch_latest_news()
            events.put(('news', items))
        threading.Thread(target=worker, daemon=True).start()

    def fetch_gold_task():
        def worker():
            data = _fetch_gold_data()
            events.put(('gold', data))
        threading.Thread(target=worker, daemon=True).start()

    def update_single_news():
        if not panel.winfo_exists():
            return
        items = news_store['list']
        if items:
            idx = news_store['index'] % len(items)
            item = items[idx]
            news_header_text.set(f"● {item['source']} · TIN NHANH")
            news_text.set(f"• {item['title']}")
            current_news_url['url'] = item['link']
            news_store['index'] += 1

    def rotate_news_cycle():
        if not panel.winfo_exists():
            return
        if news_store['list']:
            update_single_news()
        panel.after(8000, rotate_news_cycle)

    def poll_events():
        if not panel.winfo_exists():
            return
        try:
            while True:
                kind, data = events.get_nowait()
                if kind == 'weather':
                    busy['running'] = False
                    place_name, icon_char, icon_color, temp_val = data
                    city_name_text.set(f"📍 {place_name}")
                    icon_label.config(text=icon_char, fg=icon_color)
                    temp_text.set(temp_val)
                elif kind == 'news':
                    if data:
                        news_store['list'] = data
                        news_store['index'] = 0
                        update_single_news()
                    else:
                        news_text.set('Chưa tải được tin tức.')
                elif kind == 'gold':
                    gold_full_data['data'] = data
                    change_sym = "▲" if data['change'] >= 0 else "▼"
                    gold_text_sjc_short.set(f"{data['sjc_buy']:.1f} - {data['sjc_sell']:.1f} tr")
                    gold_text_world.set(f"Thế giới: ${data['world']:,.0f}/oz ({change_sym}{abs(data['change']):.1f})")
                    gold_text_sjc_full.set(f"SJC: {data['sjc_buy']:.1f} - {data['sjc_sell']:.1f} triệu/lượng")
                    render_sparkline(data['history'], data['change'])
                elif kind == 'radio_status':
                    generation, state, text_val, color_val = data
                    if generation != player_state['generation']:
                        continue
                    radio_status_text.set(text_val)
                    lbl_radio_status.config(fg='#F87171')
                    if state == 'error':
                        radio_engine.stop()
                        player_state['is_playing'] = False
                        btn_play.config(text='▶ Phát', bg='#0284C7')
                    elif state == 'playing':
                        btn_play.config(text='⏸ Dừng', bg='#DC2626')
        except Empty:
            pass
        process = music_player.process
        if process is not None and process.poll() is None:
            try:
                track = json.loads(Path(music_player.command_file + '.status').read_text(encoding='utf-8'))
                title = str(track.get('title') or '').strip()
                if time.time() - float(track.get('updated', 0)) < 5:
                    if title:
                        artist = str(track.get('artist') or '').strip()
                        prefix = '♫ ' if track.get('playing') else 'Ⅱ '
                        radio_status_text.set(prefix + title + (' — ' + artist if artist else ''))
                    else:
                        radio_status_text.set('♫ Chọn bài trong trình phát')
                    lbl_radio_status.config(fg='#F87171')
            except (OSError, ValueError, TypeError):
                pass
        panel.after(200, poll_events)

    def refresh_weather_cycle():
        if panel.winfo_exists():
            fetch_weather_task()
            panel.after(20 * 60 * 1000, refresh_weather_cycle)

    def refresh_news_cycle():
        if panel.winfo_exists():
            fetch_news_task()
            panel.after(15 * 60 * 1000, refresh_news_cycle)

    def refresh_gold_cycle():
        if panel.winfo_exists():
            fetch_gold_task()
            panel.after(5 * 60 * 1000, refresh_gold_cycle)

    def on_panel_destroy(event):
        if event.widget is panel:
            player_state['generation'] += 1
            radio_engine.stop()
            music_player.stop()

    panel.bind('<Destroy>', on_panel_destroy)

    tick()
    poll_events()
    refresh_weather_cycle()
    refresh_news_cycle()
    refresh_gold_cycle()
    rotate_news_cycle()
    return panel
