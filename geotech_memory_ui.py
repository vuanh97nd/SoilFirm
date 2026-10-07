"""Xem lịch sử và xác nhận kiến thức của riêng dự án đang mở."""
import json
import sqlite3
import threading
import tkinter as tk
from ui_theme import UI_FONT, UI_FONT_MONO
from pathlib import Path
from tkinter import ttk, messagebox
from geotech_memory import GeotechMemory, active_project, project_scope


def show_memory_dialog(app):
    project=active_project(app);actor=app.current_username or 'Người dùng'
    scope=project_scope(project,app.current_username or '')
    memory=GeotechMemory()
    popup=tk.Toplevel(app);popup.title('Bộ nhớ AI của dự án');popup.transient(app)
    sw,sh=popup.winfo_screenwidth(),popup.winfo_screenheight()
    w,h=min(1200,sw-40),min(700,sh-80)
    popup.geometry(f'{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2)}')
    ttk.Label(popup,text='Kiến thức tin cậy cần xác nhận. Biểu mẫu chỉ gợi ý nhãn cột; trị số đã sửa không dùng để điền file khác.',wraplength=w-30,padding=8).pack(fill='x')
    book=ttk.Notebook(popup);book.pack(fill='both',expand=True,padx=8,pady=8)
    history=ttk.Frame(book);knowledge=ttk.Frame(book)
    book.add(history,text='Lịch sử sửa');book.add(knowledge,text='Kiến thức')
    templates=ttk.Frame(book);book.add(templates,text='Biểu mẫu')
    template_tree=ttk.Treeview(templates,columns=('source','columns','type'),show='headings',height=8)
    for key,label,width in [('source','Nguồn biểu mẫu',500),('columns','Số cột',70),('type','Loại ghi nhớ',180)]:
        template_tree.heading(key,text=label);template_tree.column(key,width=width)
    template_tree.pack(fill='both',expand=True,padx=8,pady=5)
    template_detail=tk.Text(templates,wrap='word',height=10,font=(UI_FONT,10));template_detail.pack(fill='both',expand=True,padx=8,pady=5)
    template_items={};template_notice=tk.StringVar()
    ttk.Label(templates,textvariable=template_notice,wraplength=w-35).pack(fill='x',padx=8)
    def template_refresh():
        try:
            registry=json.loads(Path(__file__).with_name('parameter_registry.json').read_text(encoding='utf-8'))
            memory.load_reference_templates(scope,registry)
            template_tree.delete(*template_tree.get_children());template_items.clear()
            for item in memory.template_list(scope):
                ident=item['signature'];template_items[ident]=item
                template_tree.insert('','end',iid=ident,values=(item['source'],len(item['columns']),
                    'Tham khảo' if ident.startswith('reference:') else 'Đã gặp khi đọc'))
            template_notice.set('Biểu mẫu không tự trở thành ánh xạ đã xác nhận; luôn kiểm tra file và đơn vị hiện tại.')
        except (ValueError,OSError,sqlite3.Error,KeyError) as exc:template_notice.set(str(exc))
    def select_template(_event):
        selected=template_tree.selection()
        if not selected:return
        item=template_items[selected[0]]
        template_detail.configure(state='normal');template_detail.delete('1.0','end')
        template_detail.insert('end',json.dumps({'source':item['source'],'columns':item['columns']},ensure_ascii=False,indent=2))
        template_detail.configure(state='disabled')
    template_tree.bind('<<TreeviewSelect>>',select_template)
    ttk.Button(templates,text='Làm mới',command=template_refresh).pack(anchor='e',padx=8,pady=5)
    tree=ttk.Treeview(history,columns=('time','kind','actor','source'),show='headings',height=9)
    for key,label in [('time','Thời điểm'),('kind','Loại ghi nhớ'),('actor','Người xác nhận'),('source','Nguồn')]:
        tree.heading(key,text=label);tree.column(key,width=160)
    tree.pack(fill='both',expand=True)
    detail=tk.Text(history,wrap='word',height=10,font=(UI_FONT,10));detail.pack(fill='both',expand=True)
    events={}
    def history_refresh():
        tree.delete(*tree.get_children());events.clear()
        for event in memory.history(scope):
            ident=str(event['id']);events[ident]=event
            tree.insert('','end',iid=ident,values=(event['created_at'],event['kind'],event['actor'],event['source']))
    def select_event(_e):
        selected=tree.selection()
        if not selected:return
        item=events[selected[0]]
        detail.configure(state='normal');detail.delete('1.0','end')
        detail.insert('end',json.dumps({**item,'original':json.loads(item['original']),
            'corrected':json.loads(item['corrected']),'context':json.loads(item['context'])},ensure_ascii=False,indent=2))
        detail.configure(state='disabled')
    tree.bind('<<TreeviewSelect>>',select_event)
    ttk.Button(history,text='Làm mới',command=history_refresh).pack(anchor='e',pady=5)
    def disable_rule():
        selected=tree.selection()
        if not selected or events[selected[0]]['kind']!='column_mapping':
            messagebox.showinfo('Quy tắc ánh xạ','Chọn một mục column_mapping trong lịch sử.',parent=popup);return
        if messagebox.askyesno('Ngừng dùng quy tắc','Ngừng áp dụng quy tắc ánh xạ này?',parent=popup):
            memory.disable_mapping(scope,int(selected[0]),actor);history_refresh()
    ttk.Button(history,text='Ngừng dùng quy tắc',command=disable_rule).pack(anchor='e',pady=5)

    topic=tk.StringVar(value='Chỉ tiêu đất');title=tk.StringVar();source=tk.StringVar();confirmed=tk.BooleanVar(value=False)
    topics=('Địa tầng','Chỉ tiêu đất','Lỗ khoan và độ sâu','e–logP và Cv–logP','Nhóm thí nghiệm','Xử lý nền','Kết quả kiểm toán')
    form=ttk.Frame(knowledge,padding=8);form.pack(fill='x');form.columnconfigure(1,weight=1)
    for row,(label,var) in enumerate([('Chủ đề',topic),('Tên kiến thức',title),('Nguồn căn cứ',source)]):
        ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',padx=5,pady=4)
        widget=ttk.Combobox(form,textvariable=var,values=topics,state='readonly') if row==0 else ttk.Entry(form,textvariable=var)
        widget.grid(row=row,column=1,sticky='ew',padx=5)
    body=tk.Text(knowledge,wrap='word',height=7,font=(UI_FONT,10));body.pack(fill='x',padx=12)
    ttk.Checkbutton(knowledge,text='Tôi xác nhận nội dung và nguồn',variable=confirmed).pack(anchor='w',padx=12,pady=5)
    notice=tk.StringVar();ttk.Label(knowledge,textvariable=notice,wraplength=w-35).pack(fill='x',padx=12)
    table=ttk.Treeview(knowledge,columns=('topic','title','confirmed','active'),show='headings',height=6)
    for key,label in [('topic','Chủ đề'),('title','Tên kiến thức'),('confirmed','Đã xác nhận'),('active','Đang dùng')]:table.heading(key,text=label)
    table.pack(fill='both',expand=True,padx=12,pady=5)
    def refresh():
        table.delete(*table.get_children())
        for row in memory.knowledge_list(scope):table.insert('','end',iid=str(row['id']),values=(row['topic'],row['title'],'Có' if row['confirmed'] else 'Chưa','Có' if row['active'] else 'Không'))
    def save():
        try:
            memory.add_knowledge(scope,topic.get(),title.get().strip(),body.get('1.0','end').strip(),
                source=source.get().strip(),actor=actor,confirmed=confirmed.get())
            notice.set('Đã lưu kiến thức đã xác nhận.' if confirmed.get() else 'Đã lưu bản nháp; AI chưa được sử dụng.')
            refresh();confirmed.set(False)
        except (ValueError,OSError,sqlite3.Error) as exc:notice.set(str(exc))
    def disable():
        selected=table.selection()
        if selected and messagebox.askyesno('Ngừng dùng kiến thức','Ngừng dùng kiến thức đã chọn trong AI?',parent=popup):
            memory.disable_knowledge(scope,int(selected[0]));refresh()
    actions=ttk.Frame(knowledge);actions.pack(fill='x',padx=12,pady=5)
    ttk.Button(actions,text='Lưu kiến thức',command=save).pack(side='left')
    ttk.Button(actions,text='Ngừng sử dụng',command=disable).pack(side='left',padx=5)
    shared=ttk.Frame(book);book.add(shared,text='Bộ nhớ chung')
    eligible=not app.is_trial();credentials={'username':app.current_username,'key':app.current_login_key}
    memory.set_shared_access(scope,eligible,app.current_username or '')
    is_admin=getattr(app,'current_user_role','')=='admin'
    shared_status=tk.StringVar(value='Quy tắc mới chờ quản trị viên xác nhận trước khi dùng chung.' if eligible else 'Tài khoản dùng thử không được dùng bộ nhớ chung.')
    ttk.Label(shared,textvariable=shared_status,wraplength=w-35,padding=8).pack(fill='x')
    shared_tree=ttk.Treeview(shared,columns=('kind','state','owner'),show='headings',height=8)
    for key,label in [('kind','Nội dung'),('state','Trạng thái'),('owner','Người gửi / xác nhận')]:shared_tree.heading(key,text=label)
    shared_tree.pack(fill='both',expand=True,padx=8)
    shared_detail=tk.Text(shared,wrap='word',height=10,font=(UI_FONT,10));shared_detail.pack(fill='both',expand=True,padx=8,pady=5)
    shared_items={};shared_busy={'value':False};shared_offset={'value':0};shared_buttons=[]
    def show_shared(items=None):
        shared_tree.delete(*shared_tree.get_children());shared_items.clear()
        with memory.connection() as db:
            records=db.execute('SELECT id,kind,payload,reviewer FROM shared_memory_cache ORDER BY seq DESC').fetchall() if eligible else []
            queued=db.execute('SELECT id,kind,payload,account FROM shared_memory_outbox WHERE account=? ORDER BY created_at',(app.current_username or '',)).fetchall() if eligible else []
        combined=[{**dict(row),'payload':json.loads(row['payload']),'state':'approved','owner':row['reviewer']} for row in records]
        combined.extend({**dict(row),'payload':json.loads(row['payload']),'state':'local_pending','owner':row['account']} for row in queued)
        combined.extend(items or [])
        for item in combined:shared_items[item['id']]=item
        counts={'approved':0,'pending':0,'local_pending':0}
        for item in shared_items.values():
            title=('Ánh xạ biểu mẫu' if item['kind']=='mapping' else item['payload']['title'])
            state=item['state'];counts[state]=counts.get(state,0)+1
            shared_tree.insert('','end',iid=item['id'],values=(title,{'approved':'Đã công bố','pending':'Chờ server duyệt','local_pending':'Chờ gửi từ máy này','disabled':'Ngừng sử dụng','rejected':'Không chấp nhận'}.get(state,state),item.get('owner','')))
        base=shared_status.get().split(' | Danh sách:')[0]
        shared_status.set(base+' | Danh sách: '+str(counts['approved'])+' đã công bố, '+str(counts['pending'])+' chờ server duyệt, '+str(counts['local_pending'])+' chờ gửi.')
        shared_detail.configure(state='normal');shared_detail.delete('1.0','end')
        if not shared_items:
            shared_detail.insert('end','Chưa có mục bộ nhớ chung trong dữ liệu vừa tải. Nếu đồng bộ lỗi, xem thông báo phía trên. Admin dùng Xem đề xuất để kiểm tra các mục chờ duyệt trên server; Nạp biểu mẫu để gửi metadata biểu mẫu. Chưa gửi hoặc chưa công bố không đồng nghĩa bộ nhớ đã sẵn sàng dùng chung.')
        shared_detail.configure(state='disabled')
    def select_shared(_event):
        selected=shared_tree.selection()
        if not selected:return
        shared_detail.configure(state='normal');shared_detail.delete('1.0','end')
        shared_detail.insert('end',json.dumps(shared_items[selected[0]],ensure_ascii=False,indent=2));shared_detail.configure(state='disabled')
    shared_tree.bind('<<TreeviewSelect>>',select_shared)
    def run_shared(operation):
        if not eligible or app.is_trial() or shared_busy['value']:return
        shared_busy['value']=True;shared_status.set('Đang đồng bộ bộ nhớ chung…')
        for button in shared_buttons:button.configure(state='disabled')
        account=app.current_username
        def done(result,error):
            if not popup.winfo_exists() or app.current_username!=account:return
            shared_busy['value']=False
            for button in shared_buttons:button.configure(state='normal')
            if error:
                shared_status.set(str(error));show_shared();return
            shared_status.set(result.get('message','Đã cập nhật bộ nhớ chung.'))
            show_shared(result.get('items'))
        def work():
            result=None;error=None
            try:result=operation()
            except Exception as exc:error=exc
            try:app.after(0,lambda r=result,e=error:done(r,e))
            except (tk.TclError,RuntimeError):pass
        threading.Thread(target=work,daemon=True).start()
    def synchronize():
        from geotech_memory_sync import sync_shared_memory
        def operation():
            result=sync_shared_memory(app.API_BASE_URL,credentials,scope,eligible,max_pages=5)
            if is_admin and result.get('success'):
                from geotech_memory_sync import shared_request
                try:
                    proposal=shared_request(app.API_BASE_URL,credentials,'/api/memory/shared/pending',{'offset':0})
                    result['items']=proposal.get('items',[])
                    result['message']+=' Đã tải đề xuất chờ duyệt.'
                except Exception as exc:
                    result['message']+=' Chưa tải được đề xuất admin: '+str(exc)
            return result
        run_shared(operation)
    def queue_knowledge():
        if not eligible:return
        selected=table.selection()
        if not selected:messagebox.showinfo('Bộ nhớ chung','Chọn kiến thức đã xác nhận trong thẻ Kiến thức.',parent=popup);return
        if not messagebox.askyesno('Gửi kiến thức dùng chung','Nội dung và nguồn sẽ được gửi lên máy chủ để quản trị viên xem xét. Gửi kiến thức này?',parent=popup):return
        try:memory.share_knowledge(scope,int(selected[0]),app.current_username);synchronize()
        except (ValueError,sqlite3.Error) as exc:shared_status.set(str(exc))
    def import_references(all_batches=True):
        from geotech_memory_sync import upload_all_template_references,shared_request
        stopped=threading.Event()
        popup.bind('<Destroy>',lambda e:stopped.set() if e.widget is popup else None,add='+')
        def progress(message):
            def update():
                if popup.winfo_exists() and app.current_username==credentials['username']:shared_status.set(message)
            try:app.after(0,update)
            except (tk.TclError,RuntimeError):pass
        def operation():
            result=upload_all_template_references(app.API_BASE_URL,credentials,scope,eligible,
                progress=progress,cancel=lambda:stopped.is_set() or app.current_username!=credentials['username'],max_batches=None if all_batches else 1)
            if is_admin and result.get('success'):
                try:
                    proposal=shared_request(app.API_BASE_URL,credentials,'/api/memory/shared/pending',{'offset':0})
                    result['items']=proposal.get('items',[])
                except Exception as exc:result['message']+=' Chưa tải được danh sách đề xuất: '+str(exc)
            return result
        run_shared(operation)
    def pending(delta=0):
        from geotech_memory_sync import shared_request
        shared_offset['value']=max(0,shared_offset['value']+delta)
        offset=shared_offset['value']
        run_shared(lambda:shared_request(app.API_BASE_URL,credentials,'/api/memory/shared/pending',{'offset':offset}))
    def review(state):
        from geotech_memory_sync import shared_request,sync_shared_memory
        selected=shared_tree.selection()
        if not selected:return
        ident=selected[0]
        if shared_items[ident].get('state')=='local_pending':
            shared_status.set('Mục đang chờ gửi từ máy này; Đồng bộ trước khi duyệt trên server.');return
        if not messagebox.askyesno('Bộ nhớ chung','Áp dụng quyết định này cho tất cả tài khoản đầy đủ?',parent=popup):return
        def action():
            result=shared_request(app.API_BASE_URL,credentials,'/api/memory/shared/review',{'id':ident,'state':state})
            sync_shared_memory(app.API_BASE_URL,credentials,scope,eligible,max_pages=5)
            return result
        run_shared(action)
    bar=ttk.Frame(shared);bar.pack(fill='x',padx=8,pady=5)
    for index,(label,command) in enumerate([('Đồng bộ',synchronize),('Gửi kiến thức',queue_knowledge)]+([('Nạp một lô',lambda:import_references(False)),('Nạp toàn bộ',lambda:import_references(True)),('Xem đề xuất',pending),('Trang trước',lambda:pending(-50)),('Trang sau',lambda:pending(50)),('Công bố',lambda:review('approved')),('Từ chối',lambda:review('rejected')),('Ngừng sử dụng',lambda:review('disabled'))] if is_admin else [])):
        button=ttk.Button(bar,text=label,command=command);button.grid(row=0,column=index,padx=2,pady=3,sticky='ew');shared_buttons.append(button)
        if not eligible:button.configure(state='disabled')
    show_shared()
    if eligible and app.current_username and app.current_login_key:popup.after(0,synchronize)

    history_refresh();refresh();template_refresh()
    return popup
