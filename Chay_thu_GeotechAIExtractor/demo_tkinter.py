"""Chạy: python demo_tkinter.py — chỉ xem trước, không ghi số liệu vào SoilFirm."""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from geotech_ai_extractor import GeotechAIExtractor

class Demo(tk.Tk):
    def __init__(self):
        super().__init__();self.title('SoilFirm — đọc và xem trước số liệu');self.geometry('1050x720')
        self.extractor=None;self.job=None
        bar=ttk.Frame(self,padding=10);bar.pack(fill='x')
        self.provider=tk.StringVar(value=os.getenv('GEOTECH_PROVIDER', 'deepseek'))
        ttk.Combobox(bar,textvariable=self.provider,values=['deepseek','openai'],state='readonly',width=14).pack(side='left',padx=4)
        self.start_button=ttk.Button(bar,text='Đọc và xem trước',command=self.start);self.start_button.pack(side='left',padx=4)
        ttk.Button(bar,text='Hủy tác vụ',command=self.cancel).pack(side='left',padx=4)
        self.status=tk.StringVar(value='Khóa API lấy từ DEEPSEEK_API_KEY hoặc OPENAI_API_KEY.')
        ttk.Label(self,textvariable=self.status,padding=10).pack(fill='x')
        body=ttk.Frame(self);body.pack(fill='both',expand=True)
        self.output=tk.Text(body,wrap='none',font=('Consolas',10));self.output.grid(row=0,column=0,sticky='nsew')
        v=ttk.Scrollbar(body,orient='vertical',command=self.output.yview);v.grid(row=0,column=1,sticky='ns')
        h=ttk.Scrollbar(body,orient='horizontal',command=self.output.xview);h.grid(row=1,column=0,sticky='ew')
        self.output.configure(yscrollcommand=v.set,xscrollcommand=h.set);body.rowconfigure(0,weight=1);body.columnconfigure(0,weight=1)
        self.protocol('WM_DELETE_WINDOW',self.finish)
    def start(self):
        files=filedialog.askopenfilenames(parent=self,title='Chọn file địa kỹ thuật',filetypes=[('Excel/CSV/TSV','*.xlsx *.xlsm *.xls *.csv *.tsv')])
        if not files:return
        try:
            if self.extractor:self.extractor.close(wait=False)
            self.extractor=GeotechAIExtractor(provider=self.provider.get(),max_workers=5)
            self.job=self.extractor.extract_files_background(list(files))
        except Exception as exc:messagebox.showerror('Không bắt đầu được',str(exc),parent=self);return
        self.start_button.configure(state='disabled');self.output.delete('1.0','end')
        self.status.set(f'Đang đọc {len(files)} file; chờ AI xác nhận ánh xạ…')
        self.extractor.poll_tk(self,self.job,self.on_result,self.on_done)
    def on_result(self,item):
        self.output.insert('end','\nFILE: '+item.file+'\n')
        self.output.insert('end',item.result.to_json() if item.result else 'Không trả số liệu: '+str(item.error))
        self.output.insert('end','\n');self.output.see('end')
    def on_done(self):
        self.start_button.configure(state='normal')
        self.status.set('Đã hủy; không áp dụng kết quả.' if self.job.cancelled.is_set() else 'Đã xử lý xong. Đây là bản xem trước; cần kiểm tra ánh xạ và đơn vị trước khi áp dụng.')
    def cancel(self):
        if self.job:self.job.cancel()
    def finish(self):
        self.cancel()
        if self.extractor:self.extractor.close(wait=False)
        self.destroy()
if __name__=='__main__':Demo().mainloop()
