"""Reviewed e-lgP and Cv-lgP averages, scalar fallback and bitmap clipboard."""
from copy import deepcopy
import csv
import io
import math
import statistics
import tkinter as tk
from tkinter import ttk,messagebox


def copy_widget_image(widget, picture=None):
    import os,ctypes
    from PIL import ImageGrab
    if os.name!='nt':raise ValueError('Copy ảnh trực tiếp hỗ trợ clipboard Windows.')
    widget.update_idletasks()
    if picture is None:
        x,y=widget.winfo_rootx(),widget.winfo_rooty()
        picture=ImageGrab.grab(bbox=(x,y,x+widget.winfo_width(),y+widget.winfo_height()),all_screens=True)
    picture=picture.convert('RGB')
    stream=io.BytesIO();picture.save(stream,format='BMP');data=stream.getvalue()[14:]
    user=ctypes.windll.user32;kernel=ctypes.windll.kernel32
    kernel.GlobalAlloc.argtypes=[ctypes.c_uint,ctypes.c_size_t];kernel.GlobalAlloc.restype=ctypes.c_void_p
    kernel.GlobalLock.argtypes=[ctypes.c_void_p];kernel.GlobalLock.restype=ctypes.c_void_p
    kernel.GlobalUnlock.argtypes=[ctypes.c_void_p];kernel.GlobalFree.argtypes=[ctypes.c_void_p]
    user.SetClipboardData.argtypes=[ctypes.c_uint,ctypes.c_void_p];user.SetClipboardData.restype=ctypes.c_void_p
    handle=kernel.GlobalAlloc(0x0002,len(data))
    if not handle:raise MemoryError('Không đủ bộ nhớ để copy ảnh.')
    pointer=kernel.GlobalLock(handle)
    if not pointer:kernel.GlobalFree(handle);raise RuntimeError('Không thể chuẩn bị ảnh clipboard.')
    ctypes.memmove(pointer,data,len(data));kernel.GlobalUnlock(handle)
    if not user.OpenClipboard(None):kernel.GlobalFree(handle);raise RuntimeError('Clipboard đang bận; thử copy lại.')
    transferred=False
    try:
        user.EmptyClipboard()
        if not user.SetClipboardData(8,handle):raise RuntimeError('Không đưa được ảnh vào clipboard.')
        transferred=True
    finally:
        user.CloseClipboard()
        if not transferred:kernel.GlobalFree(handle)


def copy_canvas_image(canvas):
    """Render the full drawing and data table, independent of scrolling or occlusion."""
    import os
    from pathlib import Path
    from PIL import Image,ImageDraw,ImageFont
    from tkinter import font as tkfont
    canvas.update_idletasks()
    bounds=canvas.bbox('all') or (0,0,canvas.winfo_width(),canvas.winfo_height())
    width=max(canvas.winfo_width(),int(bounds[2])+4)
    height=max(canvas.winfo_height(),int(bounds[3])+4)
    scale=2
    picture=Image.new('RGB',(width*scale,height*scale),'white');draw=ImageDraw.Draw(picture)
    def color(value):
        if not value:return None
        try:return tuple(channel//257 for channel in canvas.winfo_rgb(value))
        except tk.TclError:return (0,0,0)
    fonts={}
    def font_for(item):
        description=canvas.itemcget(item,'font')
        if description in fonts:return fonts[description]
        actual=tkfont.Font(font=description).actual()
        size=abs(actual['size'])
        pixels=round((size*canvas.winfo_fpixels('1i')/72 if actual['size']>0 else size)*scale)
        bold=actual.get('weight')=='bold';italic=actual.get('slant')=='italic'
        filename=('timesbi.ttf' if bold and italic else 'timesbd.ttf' if bold else 'timesi.ttf' if italic else 'times.ttf')
        candidates=[str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/filename),filename,'DejaVuSerif.ttf']
        face=None
        for path in candidates:
            try:face=ImageFont.truetype(path,max(1,pixels));break
            except OSError:continue
        fonts[description]=face or ImageFont.load_default()
        return fonts[description]
    for item in canvas.find_all():
        if canvas.itemcget(item,'state')=='hidden':continue
        kind=canvas.type(item);coords=canvas.coords(item)
        fill=color(canvas.itemcget(item,'fill'))
        if kind=='line':
            points=[(round(coords[i]*scale),round(coords[i+1]*scale)) for i in range(0,len(coords),2)]
            width_px=max(1,round(float(canvas.itemcget(item,'width'))*scale))
            draw.line(points,fill=fill or (0,0,0),width=width_px)
            arrow=canvas.itemcget(item,'arrow')
            for end in ([0] if arrow=='first' else [-1] if arrow=='last' else [0,-1] if arrow=='both' else []):
                x,y=points[end];other=points[1] if end==0 else points[-2]
                dx,dy=x-other[0],y-other[1];length=math.hypot(dx,dy)
                if length:
                    ux,uy=dx/length,dy/length;a=7*scale;b=3*scale
                    draw.polygon([(x,y),(x-a*ux+b*uy,y-a*uy-b*ux),(x-a*ux-b*uy,y-a*uy+b*ux)],fill=fill or (0,0,0))
        elif kind in ('rectangle','oval'):
            box=tuple(round(value*scale) for value in coords)
            outline=color(canvas.itemcget(item,'outline'));width_px=max(1,round(float(canvas.itemcget(item,'width'))*scale))
            method=draw.rectangle if kind=='rectangle' else draw.ellipse
            method(box,fill=fill,outline=outline,width=width_px)
        elif kind=='text':
            text=canvas.itemcget(item,'text');face=font_for(item)
            if not text:continue
            bbox=canvas.bbox(item)
            if not bbox:continue
            angle=float(canvas.itemcget(item,'angle') or 0)
            if angle:
                text_bounds=face.getbbox(text);tw=text_bounds[2]-text_bounds[0]+8;th=text_bounds[3]-text_bounds[1]+8
                stamp=Image.new('RGBA',(tw,th),(255,255,255,0));painter=ImageDraw.Draw(stamp)
                painter.text((4-text_bounds[0],4-text_bounds[1]),text,font=face,fill=fill or (0,0,0))
                stamp=stamp.rotate(angle,expand=True,resample=Image.Resampling.BICUBIC)
                x=round(coords[0]*scale-stamp.width/2);y=round(coords[1]*scale-stamp.height/2)
                picture.paste(stamp,(x,y),stamp)
            else:
                text_bounds=face.getbbox(text)
                draw.text((bbox[0]*scale-text_bounds[0],bbox[1]*scale-text_bounds[1]),text,font=face,fill=fill or (0,0,0))
    copy_widget_image(canvas,picture=picture)


def show_lab_statistics(view):
    from ui_theme import soil_parameter_keys
    uid=view.layer_id();project=view.data_project();soil=next((s for s in project.soils if s.statistics_id==uid),None)
    if not uid:messagebox.showinfo('Thí nghiệm','Chọn lớp đất trước.',parent=view);return
    layer_name=soil.name if soil is not None else view.layer.get()
    def source_lines():
        lines=[]
        for row in view.visible:
            if not row.get('use',True):continue
            sample=row.get('original',{});values=sample.get('values',{});points={}
            for grid,key in (('ep','e'),('cvp','cv')):
                for pressure,number in zip(values.get(grid,[]),values.get(key,[])):
                    if pressure is None or number is None:continue
                    points.setdefault(pressure,{})[key]=number*.001 if key=='cv' else number
            sample_id=str(row.get('hole',''))+'/'+str(row.get('sample') or row['id'])
            for pressure,values_at_pressure in sorted(points.items()):
                lines.append(';'.join([sample_id,str(pressure),str(values_at_pressure.get('e','')),str(values_at_pressure.get('cv',''))]))
        return '\n'.join(lines)
    data=view.store().setdefault('lab_curves',{});old=data.get(uid,{})
    popup=tk.Toplevel(view);popup.title('Thống kê e–lgP / Cv–lgP · '+layer_name);popup.geometry('960x660');popup.transient(view.app)
    modes=('Trung bình theo cấp áp lực','Dùng giá trị bảng tổng hợp')
    e_mode=tk.StringVar(value=old.get('e_mode',modes[0]));cv_mode=tk.StringVar(value=old.get('cv_mode',modes[0]))
    e0_mean=view.computed.get('e0',{}).get('mean');cv_mean=view.computed.get('cv',{}).get('mean')
    initial_text=old.get('text') or source_lines()
    if 'e_mode' not in old and not initial_text:e_mode.set(modes[1])
    if 'cv_mode' not in old and not any(line.split(';')[-1].strip() for line in initial_text.splitlines()):cv_mode.set(modes[1])
    e0=tk.StringVar(value=str(old.get('e0',e0_mean if e0_mean is not None else getattr(soil,'e0',''))))
    cv0=tk.StringVar(value=str(old.get('cv0',cv_mean if cv_mean is not None else (getattr(soil,'cv_constant',None)*.001 if getattr(soil,'cv_constant',None) is not None else None))) if old.get('cv0',cv_mean if cv_mean is not None else (getattr(soil,'cv_constant',None)*.001 if getattr(soil,'cv_constant',None) is not None else None)) is not None else '')
    top=ttk.Frame(popup,padding=8);top.pack(fill='x')
    for row,(label,mode,var,unit) in enumerate((('e–lgP',e_mode,e0,'e₀'),('Cv–lgP',cv_mode,cv0,'Cv TB (cm²/s)'))):
        ttk.Label(top,text=label).grid(row=row,column=0,padx=5,pady=5)
        allowed=soil_parameter_keys(project.method)
        if row==0 and 'ep' not in allowed:mode.set(modes[1])
        ttk.Combobox(top,textvariable=mode,values=modes,state='readonly' if row==1 or 'ep' in allowed else 'disabled',width=32).grid(row=row,column=1,padx=5)
        ttk.Label(top,text=unit).grid(row=row,column=2,padx=5)
        ttk.Entry(top,textvariable=var,width=15,state='normal' if row==1 or 'e0' in allowed else 'readonly').grid(row=row,column=3,padx=5)
    ttk.Label(popup,text='Mỗi hàng: Mã mẫu ; P (kg/cm²) ; e ; Cv (cm²/s). Có thể dán cột Excel bằng tab. Thiếu e hoặc Cv để trống; thiếu P bỏ qua, P < 0 không hợp lệ; P=0 giữ để xác định e₀. Các mẫu dùng cùng cấp áp lực mới được gộp.',padding=8,wraplength=920).pack(fill='x')
    raw=tk.Text(popup,height=9,wrap='none');raw.pack(fill='x',padx=8);raw.insert('1.0',initial_text)
    tables=ttk.Frame(popup);tables.pack(fill='both',expand=True,padx=8,pady=5)
    tree=ttk.Treeview(tables,columns=('p','e','ne','cv','nc'),show='headings',height=7)
    for key,label in [('p','P (kg/cm²)'),('e','e TB'),('ne','Số mẫu e'),('cv','Cv TB (cm²/s)'),('nc','Số mẫu Cv')]:tree.heading(key,text=label);tree.column(key,width=155)
    tree.pack(fill='both',expand=True)
    status=tk.StringVar();ttk.Label(popup,textvariable=status,padding=8,wraplength=920).pack(fill='x')
    def value(text):
        text=str(text).strip()
        if not text:return None
        number=float(text.replace(',','.'))
        if not math.isfinite(number):raise ValueError('Giá trị phải là số hữu hạn.')
        return number
    def parse():
        records=[];groups={'e':{},'cv':{}};skipped=0
        for line_number,line in enumerate(raw.get('1.0','end').splitlines(),1):
            if not line.strip():continue
            parts=line.split('\t') if '\t' in line else next(csv.reader([line],delimiter=';'))
            if len(parts)!=4:raise ValueError(f'Hàng {line_number}: cần đúng 4 cột Mã mẫu;P;e;Cv.')
            sample=parts[0].strip();pressure=value(parts[1])
            if pressure is None:skipped+=1;continue
            if pressure<0:raise ValueError(f'Hàng {line_number}: P phải không âm; P=0 là mốc e₀, không vẽ trên trục lgP.')
            if not sample:raise ValueError(f'Hàng {line_number}: thiếu mã mẫu.')
            record={'sample':sample,'p':pressure,'e':value(parts[2]),'cv':value(parts[3])};records.append(record)
            for key in groups:
                number=record[key]
                if number is None:continue
                if number<0:raise ValueError(f'Hàng {line_number}: {key} phải không âm.')
                groups[key].setdefault(pressure,{}).setdefault(sample,[]).append(number)
        curves={key:{p:(statistics.mean(statistics.mean(values) for values in samples.values()),len(samples)) for p,samples in group.items()} for key,group in groups.items()}
        return records,curves,skipped
    def preview():
        try:
            records,curves,skipped=parse();tree.delete(*tree.get_children())
            for pressure in sorted(set(curves['e'])|set(curves['cv'])):
                ev=curves['e'].get(pressure);cv=curves['cv'].get(pressure)
                tree.insert('','end',values=(f'{pressure:g}','—' if not ev else f'{ev[0]:.6g}',0 if not ev else ev[1],'—' if not cv else f'{cv[0]:.6g}',0 if not cv else cv[1]))
            status.set(f'{len(records)} hàng thí nghiệm; bỏ qua {skipped} hàng thiếu P. Lấy TB trong từng mẫu, sau đó TB các mẫu tại cùng P. Chưa áp dụng.')
            return records,curves
        except Exception as exc:messagebox.showerror('Thống kê cấp áp lực',str(exc),parent=popup)
    def apply():
        outcome=preview()
        if outcome is None:return
        records,curves=outcome
        try:
            allowed=soil_parameter_keys(project.method)
            evalue=value(e0.get()) if 'e0' in allowed else None;cvalue=value(cv0.get())
            if 'ep' in allowed and e_mode.get()==modes[0] and len(curves['e'])<2:raise ValueError('e–lgP cần ít nhất 2 cấp áp lực có e.')
            if cv_mode.get()==modes[0] and not curves['cv']:raise ValueError('Chưa có bảng Cv–lgP. Chọn Dùng giá trị bảng tổng hợp và nhập Cv TB.')
            if 'e0' in allowed and (evalue is None or evalue<=0):raise ValueError('Nhập e₀ từ bảng tổng hợp (> 0).')
            if cv_mode.get()==modes[1] and (cvalue is None or cvalue<=0):raise ValueError('Nhập Cv TB từ bảng tổng hợp (> 0).')
            if not messagebox.askyesno('Áp dụng thí nghiệm','Áp dụng chỉ tiêu thuộc phương pháp '+project.method+' cho lớp '+layer_name+'? Các kết quả tính cũ cần tính lại.',parent=popup):return
            if soil is not None:
                if 'ep' in allowed and e_mode.get()==modes[0]:
                    soil.ep=sorted(curves['e']);soil.e=[curves['e'][p][0] for p in soil.ep]
                if evalue is not None:soil.e0=evalue
                if cv_mode.get()==modes[0]:soil.cvp=sorted(curves['cv']);soil.cv=[curves['cv'][p][0]*1000 for p in soil.cvp]
                if cvalue is not None:soil.cv_constant=cvalue*1000
            data[uid]={'text':raw.get('1.0','end-1c'),'records':records,'e_mode':e_mode.get(),'cv_mode':cv_mode.get(),'e0':evalue,'cv0':cvalue,'history':old.get('history',[])+([deepcopy({k:v for k,v in old.items() if k!='history'})] if old else [])}
            if soil is not None:
                if 'ep' in allowed:soil.parameter_sources['e_curve']={'source':'Thống kê','mode':e_mode.get()}
                if evalue is not None:soil.parameter_sources['e0']={'source':'Thống kê','mode':modes[1]}
                soil.parameter_sources['cv_curve']={'source':'Thống kê','mode':cv_mode.get()}
            workspace=getattr(view.app,'_ai_analysis_workspace',None)
            state=getattr(workspace,'state',{}) if workspace is not None else {}
            selected_code=next((entry['code'] for entry in view.store().get('layer_catalog',{}).values() if entry['id']==uid),layer_name.split('. ',1)[-1])
            material=next((m for m in state.get('materials',[]) if str(m.get('code','')).casefold()==selected_code.casefold()),None)
            if material is not None:
                values=material['values']
                if 'ep' in allowed and e_mode.get()==modes[0]:
                    values['ep']=sorted(curves['e']);values['e']=[curves['e'][p][0] for p in values['ep']]
                if evalue is not None:values['e0']=evalue
                if cv_mode.get()==modes[0]:
                    values['cvp']=sorted(curves['cv']);values['cv']=[curves['cv'][p][0]*1000 for p in values['cvp']]
                if cvalue is not None:material['cv_constant']=values['cv_constant']=cvalue*1000
                material['curve_values']={k:deepcopy(values[k]) for k in ('ep','e','cvp','cv') if k in values}
                material['curve_source']='Thống kê cấp áp lực được người dùng áp dụng'
            view.app.invalidate_assessment();view.touch();view.app.refresh_soils();status.set('Đã áp dụng theo '+project.method+'. Giữ dữ liệu của phương pháp khác; Cv theo cấp áp lực được ưu tiên, Cv trung bình dùng khi thiếu đường cong hợp lệ.')
        except Exception as exc:messagebox.showerror('Áp dụng thí nghiệm',str(exc),parent=popup)
    def import_ai_samples():
        workspace=getattr(view.app,'_ai_analysis_workspace',None)
        materials=getattr(workspace,'state',getattr(view.app,'_ai_analysis_state',{})).get('materials',[])
        if not materials:
            messagebox.showinfo('Nguồn AI','Đọc và xác nhận thí nghiệm tại thẻ Đọc và xác nhận chỉ tiêu trước.',parent=popup);return
        picker=tk.Toplevel(popup);picker.title('Chọn nguồn lớp AI');picker.transient(popup)
        names=[str(m.get('code','')) for m in materials];chosen=tk.StringVar(value=names[0])
        ttk.Label(picker,text='Chọn mã lớp nguồn để đưa vào lớp '+layer_name,padding=8).pack()
        ttk.Combobox(picker,textvariable=chosen,values=names,state='readonly',width=35).pack(padx=8,pady=8)
        def load():
            material=materials[names.index(chosen.get())];lines=[]
            for index,sample in enumerate(material.get('samples') or [material],1):
                values=sample.get('values',{});points={}
                for grid,key in (('ep','e'),('cvp','cv')):
                    for pressure,number in zip(values.get(grid,[]),values.get(key,[])):
                        if pressure is None or number is None:continue
                        points.setdefault(pressure,{})[key]=number*.001 if key=='cv' else number
                sample_id=str(sample.get('sample_id') or sample.get('code') or index)+'_'+str(index)
                for pressure,values_at_pressure in sorted(points.items()):
                    lines.append(';'.join([sample_id,str(pressure),str(values_at_pressure.get('e','')),str(values_at_pressure.get('cv',''))]))
            raw.delete('1.0','end');raw.insert('1.0','\n'.join(lines))
            if material.get('values',{}).get('e0') is not None:e0.set(str(material['values']['e0']))
            if material.get('cv_constant') is not None:cv0.set(str(material['cv_constant']*.001))
            status.set('Đã lấy mẫu từ mã lớp '+chosen.get()+'. Chọn chế độ, xem bảng thống kê rồi áp dụng.');picker.destroy()
        ttk.Button(picker,text='Lấy mẫu theo lớp',command=load).pack(pady=8)
    actions=ttk.Frame(popup,padding=8);actions.pack(fill='x')
    ttk.Button(actions,text='Lấy mẫu đã xác nhận',command=import_ai_samples).pack(side='left',padx=3)
    ttk.Button(actions,text='Thống kê theo áp lực',command=preview).pack(side='left',padx=3)
    ttk.Button(actions,text='Áp dụng lựa chọn',command=apply).pack(side='left',padx=3)
    ttk.Button(actions,text='Đóng',command=popup.destroy).pack(side='right',padx=3)
    if initial_text:preview()
