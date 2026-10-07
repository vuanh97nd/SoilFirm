"""Fast support notifications and badges; Tk updates stay on the UI thread."""
from queue import Empty, Queue
import threading
import time
import tkinter as tk
from ui_theme import UI_FONT, UI_FONT_MONO
from tkinter import ttk
import requests
from PIL import Image, ImageDraw, ImageFont, ImageTk
from pathlib import Path


class SupportBackground:
    def __init__(self,app):
        self.app=app;self.queue=Queue();self.job=None;self.poll_job=None
        self.busy=False;self.generation=0;self.seen={};self.popup=None
        self.running=False;self.badge_revision=0;self.session=requests.Session();self.badge_count=None
        self.badge_icon=None;self.base_title=None;self.last_sound=0.0
    def T(self,vn,en):return en if self.app.ui_language.get()=='English' else vn
    def start(self):
        self.stop();self.running=True;self.seen={};self._drain();self._poll()
    def stop(self):
        self.running=False;self.generation+=1;self.badge_revision+=1;self.busy=False
        for name in ('job','poll_job'):
            job=getattr(self,name)
            if job is not None:
                try:self.app.after_cancel(job)
                except tk.TclError:pass
                setattr(self,name,None)
        if self.popup is not None:
            try:self.popup.destroy()
            except tk.TclError:pass
            self.popup=None
        if self.badge_count is not None:self._badge(0)
    def unread_updated(self,count):
        # Ignore a poll started before the server acknowledged reading a message.
        self.badge_revision+=1
        self._badge(count)
        self.refresh_now()
    def refresh_now(self):
        if not self.running:return
        if self.poll_job is not None:
            self.app.after_cancel(self.poll_job);self.poll_job=None
        self._poll()
    def _poll(self):
        if not self.running:return
        user=self.app.current_username;key=self.app.current_login_key
        if user and key and not self.busy:
            self.busy=True;generation=self.generation;revision=self.badge_revision
            payload={'username':user,'key':key};url=self.app.API_BASE_URL+'/api/chat/unread'
            def worker():
                try:
                    response=self.session.post(url,json=payload,timeout=(4,8));response.raise_for_status()
                    self.queue.put((generation,revision,response.json()))
                except Exception:self.queue.put((generation,revision,None))
            threading.Thread(target=worker,daemon=True).start()
        self.poll_job=self.app.after(1000,self._poll)
    def _badge(self,count):
        count=max(0,int(count));label=self.T('Hỗ trợ Admin','Admin support')
        self.app.chat_sidebar_button.configure(text=label+(f' ({count})' if count else ''))
        if self.badge_count==count:return
        self.badge_count=count
        if self.base_title is None:self.base_title=self.app.title()
        self.app.title(self.base_title+(f' · {count} '+self.T('tin chưa đọc','unread messages') if count else ''))
        try:
            with Image.open(Path(__file__).with_name('logo.png')) as source:
                image=source.convert('RGBA').resize((64,64),Image.Resampling.LANCZOS)
        except (OSError,ValueError):
            image=Image.new('RGBA',(64,64),'#17384D')
            fallback=ImageDraw.Draw(image)
            fallback.polygon([(7,34),(19,13),(41,13),(53,34)],fill='#0284C7')
            for x in (15,30,45):fallback.line([(x,34),(x,56)],fill='white',width=4)
        draw=ImageDraw.Draw(image)
        if count:
            draw.ellipse((28,0,63,35),fill='#DC2626',outline='white',width=2)
            text='99+' if count>99 else str(count)
            try:font=ImageFont.truetype('DejaVuSans-Bold.ttf',14)
            except OSError:font=ImageFont.load_default()
            box=draw.textbbox((0,0),text,font=font)
            draw.text((46-(box[2]-box[0])/2,17-(box[3]-box[1])/2-box[1]),text,font=font,fill='white')
        self.badge_icon=ImageTk.PhotoImage(image,master=self.app)
        self.app.iconphoto(True,self.badge_icon)
        self._taskbar_overlay(image if count else None, count)
    def _taskbar_overlay(self,image,count):
        """Native Windows taskbar badge, including grouped/pinned app icons."""
        import sys
        if sys.platform != 'win32':return
        import ctypes
        import uuid
        from io import BytesIO
        ole=ctypes.windll.ole32
        initialized=False;interface=ctypes.c_void_p();icon=None
        try:
            initialized=ole.CoInitializeEx(None,2) in (0,1)
            clsid=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID('56FDF344-FD6D-11D0-958A-006097C9A090').bytes_le)
            iid=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID('EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF').bytes_le)
            ole.CoCreateInstance.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)]
            if ole.CoCreateInstance(ctypes.byref(clsid),None,1,ctypes.byref(iid),ctypes.byref(interface)) != 0:return
            table=ctypes.cast(interface,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p)(table[3])(interface)
            user=ctypes.windll.user32
            if image is not None:
                buffer=BytesIO();image.save(buffer,format='ICO',sizes=[(32,32)])
                blob=buffer.getvalue();size=int.from_bytes(blob[14:18],'little');offset=int.from_bytes(blob[18:22],'little')
                resource=ctypes.create_string_buffer(blob[offset:offset+size])
                user.CreateIconFromResourceEx.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong,ctypes.c_int,ctypes.c_int,ctypes.c_uint]
                user.CreateIconFromResourceEx.restype=ctypes.c_void_p
                icon=user.CreateIconFromResourceEx(resource,size,1,0x00030000,32,32,0)
            user.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint];user.GetAncestor.restype=ctypes.c_void_p
            hwnd=user.GetAncestor(self.app.winfo_id(),2)
            setter=ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_wchar_p)(table[18])
            setter(interface,hwnd,icon,str(count) if count else '')
        except (AttributeError,OSError,ValueError,tk.TclError):pass
        finally:
            if icon:
                ctypes.windll.user32.DestroyIcon.argtypes=[ctypes.c_void_p]
                ctypes.windll.user32.DestroyIcon(icon)
            if interface.value:
                table=ctypes.cast(interface,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
                ctypes.WINFUNCTYPE(ctypes.c_ulong,ctypes.c_void_p)(table[2])(interface)
            if initialized:ole.CoUninitialize()

    def message_arrived(self,sender,latest):
        latest=int(latest)
        if latest<=self.seen.get(sender,0):return
        self.seen[sender]=latest
        now=time.monotonic()
        if now-self.last_sound<1.5:return
        self.last_sound=now
        import sys
        if sys.platform!='win32':
            try:self.app.bell()
            except tk.TclError:pass
            return
        def play():
            try:
                import io, math, struct, wave, winsound
                stream=io.BytesIO();rate=22050;samples=[]
                for i in range(int(rate*.26)):
                    t=i/rate;envelope=min(1,t/.012)*max(0,1-t/.26)**2
                    value=int(6500*envelope*(math.sin(2*math.pi*880*t)+.3*math.sin(2*math.pi*1320*t)))
                    samples.append(struct.pack('<h',value))
                with wave.open(stream,'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(b''.join(samples))
                winsound.PlaySound(stream.getvalue(),winsound.SND_MEMORY|winsound.SND_NODEFAULT)
            except Exception:pass
        threading.Thread(target=play,daemon=True).start()

    def _notify(self,thread):
        sender=str(thread.get('sender',''))
        # Threads originate solely from saved incoming messages, never user accounts.
        if not sender or not int(thread.get('latest_id',0)):return
        active=getattr(self.app,'_support_window',None)
        if active is not None and active.winfo_exists() and active.state()!='withdrawn':
            current=getattr(active,'current_peer',lambda:'')()
            if current==sender:return
        if self.popup is not None:
            try:self.popup.destroy()
            except tk.TclError:pass
        popup=self.popup=tk.Toplevel(self.app)
        popup._popup_fit_scheduled=True
        popup.title(self.T('Tin nhắn hỗ trợ','Support message'));popup.attributes('-topmost',True)
        width,height=340,150;button=self.app.chat_sidebar_button
        self.app.update_idletasks()
        x=max(0,min(button.winfo_rootx(),self.app.winfo_screenwidth()-width))
        y=max(0,min(button.winfo_rooty()-height-8,self.app.winfo_screenheight()-height-40))
        popup.geometry(f'{width}x{height}+{x}+{y}')
        ttk.Label(popup,text=sender,font=(UI_FONT,12,'bold')).pack(anchor='w',padx=14,pady=(12,6))
        count=int(thread.get('unread_count',1))
        ttk.Label(popup,text=f'{count} '+self.T('tin nhắn mới','new messages')).pack(anchor='w',padx=14)
        controls=ttk.Frame(popup);controls.pack(fill='x',padx=14,pady=12)
        def close():
            if popup.winfo_exists():popup.destroy()
            if self.popup is popup:self.popup=None
        def open_message():
            close();self.restore();self.app.open_chat(selected_user=sender if self.app.current_user_role=='admin' else 'admin')
        ttk.Button(controls,text=self.T('Xem tin nhắn','Open conversation'),style='Accent.TButton',command=open_message).pack(side='left')
        ttk.Button(controls,text=self.T('Đóng','Close'),command=close).pack(side='right')
        popup.after(15000,close)
    def _drain(self):
        if not self.running:return
        try:
            while True:
                generation,revision,data=self.queue.get_nowait()
                if generation!=self.generation:continue
                self.busy=False
                if revision!=self.badge_revision:continue
                if not data or not data.get('success'):continue
                threads=data.get('threads',[])
                self._badge(data.get('unread_count',sum(int(t.get('unread_count',0)) for t in threads)))
                fresh=[]
                for thread in threads:
                    sender=str(thread.get('sender',''));latest=int(thread.get('latest_id',0))
                    if latest>self.seen.get(sender,0):fresh.append(thread)
                    if latest>self.seen.get(sender,0):self.message_arrived(sender,latest)
                if fresh:self._notify(fresh[0])
        except Empty:pass
        self.job=self.app.after(50,self._drain)
    def restore(self):self.app.deiconify();self.app.lift()
