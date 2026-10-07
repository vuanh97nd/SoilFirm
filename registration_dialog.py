"""Đăng ký Trial; máy chủ luôn quyết định role và tier."""
import re
import threading
from queue import Queue, Empty
import tkinter as tk
from tkinter import ttk, messagebox
import requests
from ui_i18n import english


def show_registration_dialog(login):
    app = login.parent
    T = lambda text: english(text) if app.ui_language.get() == 'English' else text
    window = tk.Toplevel(login)
    window.title(T('Tạo tài khoản dùng thử'))
    window.transient(login); window.grab_set()
    fields = {}
    for i, (key, label) in enumerate((('fullname', 'Họ và tên'), ('email', 'Email'),
                                     ('username', 'Tên tài khoản'), ('key', 'Mật khẩu'),
                                     ('confirm', 'Nhập lại mật khẩu'))):
        ttk.Label(window, text=T(label)).grid(row=i, column=0, sticky='w', padx=14, pady=7)
        fields[key] = tk.StringVar()
        ttk.Entry(window, textvariable=fields[key], show='*' if key in ('key','confirm') else '',
                  width=34).grid(row=i, column=1, padx=14, pady=7)
    status = tk.StringVar(value=T('Dùng thử: tính thông thường ở mục 4 và 5.'))
    ttk.Label(window, textvariable=status, wraplength=430).grid(row=5,column=0,columnspan=2,padx=14,pady=9)
    output = Queue()
    button = ttk.Button(window, text=T('Tạo tài khoản'), style='Accent.TButton')
    button.grid(row=6,column=0,columnspan=2,pady=14)

    def submit():
        data = {key: var.get().strip() for key,var in fields.items()}
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,40}',data['username']):
            status.set(T('Tên tài khoản gồm 3–40 ký tự chữ, số, dấu chấm, gạch dưới hoặc gạch ngang.')); return
        if len(data['key']) < 8 or data['key'] != data['confirm']:
            status.set(T('Mật khẩu ít nhất 8 ký tự và phải khớp.')); return
        if not data['fullname'] or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',data['email']):
            status.set(T('Nhập họ tên và email hợp lệ.')); return
        del data['confirm']
        button.configure(state='disabled')
        def worker():
            try:
                response=requests.post(login.api_url+'/api/register',json=data,timeout=20)
                if response.status_code==404:
                    raise ValueError(T('Máy chủ chưa hỗ trợ đăng ký tài khoản.'))
                response.raise_for_status()
                reply=response.json()
                if not reply.get('success'):
                    raise ValueError(reply.get('message',T('Đăng ký thất bại.')))
                output.put((data,None))
            except Exception as exc: output.put((None,str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def poll():
        if not window.winfo_exists(): return
        try:
            data,error=output.get_nowait()
            if error:
                status.set(error);button.configure(state='normal')
            else:
                login.ent_user.delete(0,'end');login.ent_user.insert(0,data['username'])
                login.ent_key.delete(0,'end');login.ent_key.insert(0,data['key'])
                messagebox.showinfo(T('Thành công'),T('Đã tạo tài khoản dùng thử. Bấm đăng nhập để sử dụng.'),parent=window)
                window.destroy();return
        except Empty: pass
        window.after(150,poll)
    button.configure(command=submit);poll()
    app._apply_ui_language()
    return window
