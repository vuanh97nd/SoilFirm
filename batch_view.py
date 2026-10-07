"""Hộp thoại import THSH/CTDY và tính hàng loạt với các vị trí ưu tiên (tối đa 5, có thể để trống)."""
from __future__ import annotations
from ui_theme import UI_FONT

from copy import deepcopy
from pathlib import Path
from queue import Empty, Queue
import threading
import math
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from batch_calculation import DEFAULT_PRIORITY, OPTIONS, run_batch
from cad_cdm import count_cdm_circles
from section_excel import export_data_results, list_sections

PRIORITY_OPTIONS = ('(Trống)', *OPTIONS)


def _parse_numbers(text, available):
    if not text.strip():
        return sorted(available)
    selected = []
    for part in text.replace(';', ',').split(','):
        part = part.strip()
        if '-' in part:
            left, right = part.split('-', 1)
            first, last = int(left), int(right)
            if first > last:
                raise ValueError(f'Khoảng STT {part} bị đảo ngược.')
            selected.extend(range(first, last+1))
        else:
            selected.append(int(part))
    if len(set(selected)) != len(selected):
        raise ValueError('STT trong danh sách đang bị lặp.')
    missing = sorted(set(selected)-set(available))
    if missing:
        raise ValueError(f'STT không có trong THSH: {missing}.')
    return sorted(selected)


def show_batch_dialog(app,ai_mode=False):
    single_flow = app.design_mode.get() == 'TÍNH MỘT ĐOẠN'
    allowed_options = app.calculation_options()
    records_attr = '_single_batch_records' if single_flow else '_saved_sections_data'
    if single_flow and getattr(app, '_single_batch_busy', False):
        messagebox.showinfo('Đang tính toán', 'Chờ lượt tính hiện tại hoàn thành.', parent=app)
        return
    window = tk.Toplevel(app)
    window.title('AI tính hàng loạt' if ai_mode else 'Import và xử lý hàng loạt')
    window.geometry('980x760')
    window.transient(app)
    window.columnconfigure(0, weight=1)
    window.rowconfigure(3, weight=1)
    source = tk.StringVar(value=getattr(app, '_section_excel_path', '') or '')
    destination = tk.StringVar(value='')
    cad_path = tk.StringVar(value='')
    count_mode = tk.StringVar(value='formula')
    selected = tk.StringVar(value='' if single_flow else ', '.join(str(n) for n in getattr(app,'_summary_selected_numbers',[])))
    status = tk.StringVar(value='Import THSH/CTDY, chọn STT và sắp thứ tự ưu tiên (có thể để trống).')
    available = {}
    queue = Queue()

    def load_source():
        filename = filedialog.askopenfilename(parent=window, title='Chọn THSH/CTDY',
                                               filetypes=[('Excel', '*.xlsx')])
        if filename:
            source.set(filename)
            scan()

    def scan():
        try:
            available.clear()
            available.update(list_sections(source.get()))
            app._section_excel_path = source.get()
            status.set(f'Đã nhận {len(available)} phân đoạn; để trống STT sẽ chạy toàn bộ.')
            if ai_mode:
                def ask_priorities():
                    if not window.winfo_exists():return
                    messagebox.showinfo('AI — Chọn giải pháp ưu tiên',
                        f'Đã nhận {len(available)} phân đoạn Excel. Anh muốn AI ưu tiên những giải pháp nào?\n'
                        'Chọn Ưu tiên 1 → 5 bên dưới. AI tính trước xử lý; nếu chưa đạt, tối ưu lần lượt và chọn phương án đầu tiên đạt.\n'
                        'PDF và JSON lưu theo STT: trước xử lý → phương án được chọn.',parent=window)
                    if priority_boxes:priority_boxes[0].focus_set()
                window.after_idle(ask_priorities)
        except Exception as exc:
            available.clear()
            messagebox.showerror('Nhập bảng dữ liệu', str(exc), parent=window)

    top = ttk.LabelFrame(window, text='1. Dữ liệu và nơi lưu', padding=10)
    top.grid(row=0, column=0, sticky='ew', padx=10, pady=8)
    top.columnconfigure(1, weight=1)
    ttk.Label(top, text='Bảng THSH/CTDY:').grid(row=0, column=0, sticky='w')
    ttk.Entry(top, textvariable=source).grid(row=0, column=1, sticky='ew', padx=6)
    ttk.Button(top, text='Nhập bảng dữ liệu', command=load_source).grid(row=0, column=2)
    ttk.Label(top, text='STT (ví dụ 1,3-6):').grid(row=1, column=0, sticky='w', pady=6)
    ttk.Entry(top, textvariable=selected).grid(row=1, column=1, sticky='ew', padx=6)
    ttk.Label(top, text='Thư mục lưu:').grid(row=2, column=0, sticky='w')
    ttk.Entry(top, textvariable=destination).grid(row=2, column=1, sticky='ew', padx=6)
    ttk.Button(top, text='Chọn thư mục', command=lambda: destination.set(
        filedialog.askdirectory(parent=window) or destination.get())).grid(row=2, column=2)
    ttk.Label(top, text='CAD CDM (tùy chọn):').grid(row=3, column=0, sticky='w', pady=6)
    ttk.Entry(top, textvariable=cad_path).grid(row=3, column=1, sticky='ew', padx=6)
    ttk.Button(top, text='Chọn bản vẽ cọc', command=lambda: cad_path.set(
        filedialog.askopenfilename(parent=window, filetypes=[('DXF', '*.dxf')]) or
        cad_path.get())).grid(row=3, column=2)
    modes = ttk.Frame(top)
    modes.grid(row=4, column=0, columnspan=3, sticky='w')
    ttk.Label(modes, text='Số cọc CDM:').pack(side='left')
    ttk.Radiobutton(modes, text='Bxl × L / A ô cọc', variable=count_mode,
                    value='formula').pack(side='left', padx=10)
    ttk.Radiobutton(modes, text='CIRCLE theo layer CDM<STT>', variable=count_mode,
                    value='cad').pack(side='left', padx=10)

    choices = ttk.LabelFrame(window, text='2. Các giải pháp ưu tiên theo thứ tự chạy (tối đa 5, có thể để trống)', padding=10)
    choices.grid(row=1, column=0, sticky='ew', padx=10, pady=5)
    priority_vars = [];priority_boxes=[]
    for i, label in enumerate(DEFAULT_PRIORITY, 1):
        saved_priorities=getattr(app,'_ai_batch_priorities',[]) if ai_mode else []
        var = tk.StringVar(value=saved_priorities[i-1] if i<=len(saved_priorities) and saved_priorities[i-1] in allowed_options else '')
        priority_vars.append(var)
        ttk.Label(choices, text=f'Ưu tiên {i}:').grid(row=i-1, column=0, sticky='w', pady=2)
        box=ttk.Combobox(choices,textvariable=var,values=('(Trống)', *allowed_options),state='readonly',width=37)
        box.grid(row=i-1,column=1,sticky='w',padx=10,pady=2);priority_boxes.append(box)

    def reset_default_priorities():
        for var, default in zip(priority_vars, DEFAULT_PRIORITY):
            var.set('')

    def clear_all_priorities():
        for var in priority_vars:
            var.set('')

    btn_bar = ttk.Frame(choices)
    btn_bar.grid(row=5, column=0, columnspan=2, sticky='w', pady=(6, 0))
    ttk.Button(btn_bar, text='Đặt lại', command=reset_default_priorities).pack(side='left', padx=(0, 6))
    ttk.Button(btn_bar, text='Xóa trống tất cả', command=clear_all_priorities, style='Danger.TButton').pack(side='left')

    if not app.calculation_settings()['after']:
        choices.grid_remove()

    config = ttk.Frame(choices)
    config.grid(row=0, column=2, rowspan=6, sticky='nw', padx=14)
    inputs = {}
    for i, (key, label, default) in enumerate((
        ('excavation_step', 'Bước đào thay (m)', .5),
        ('bamboo_length', 'Chiều dài cọc tre (m)', 3.0),
        ('cajuput_length', 'Chiều dài cừ tràm (m)', 4.0),
        ('cdm_length_step', 'Bước chiều dài CDM (m)', .5),
        ('pvd_spacing', 'Bước PVD (m)', 1.2),
        ('pvd_diameter', 'ĐK PVD (cm)', 6.62),
        ('sd_spacing', 'Bước SD (m)', 2.5),
        ('sd_diameter', 'ĐK SD (cm)', 40.0),
        ('surcharge_height', 'Gia tải (m)', app.project.surcharge_height or 1.0),
    )):
        ttk.Label(config, text=label).grid(row=i, column=0, sticky='w', pady=2)
        var = tk.StringVar(value=str(default))
        inputs[key] = var
        ttk.Entry(config, textvariable=var, width=9,
                  state='readonly' if key in ('bamboo_length', 'cajuput_length') else 'normal').grid(row=i, column=1, padx=4)

    ttk.Label(window, text='Lưu chung một Excel Data, một JSON TXL/SXL và một PDF ghép cho các phân đoạn; '
              'dừng tại giải pháp đạt đầu tiên (bỏ qua các mục để trống).', wraplength=850).grid(
                  row=2, column=0, sticky='w', padx=14, pady=(6, 0))
    output = tk.Text(window, height=11, font=(UI_FONT, 10), state='disabled')
    output.grid(row=3, column=0, sticky='nsew', padx=10, pady=6)
    footer = ttk.Frame(window, padding=10)
    footer.grid(row=4, column=0, sticky='ew')
    ttk.Label(footer, textvariable=status).pack(side='left', fill='x', expand=True)
    run_button = ttk.Button(footer, text='AI tính hàng loạt' if ai_mode else 'Chạy tính toán theo từng STT', style='Accent.TButton')
    run_button.pack(side='right')

    def export_data(single):
        try:
            if not source.get() or not available:
                raise ValueError('Import Data.xlsx trước khi xuất kết quả.')
            numbers = _parse_numbers(selected.get(), available)
            if single and len(numbers) != 1:
                raise ValueError('Để xuất một đoạn, nhập đúng một STT ở ô chọn đoạn.')
            records = getattr(app, records_attr, [])
            chosen = numbers
            records = [r for r in records if r.get('section_no') in chosen]
            dest = filedialog.asksaveasfilename(
                parent=window, defaultextension='.xlsx',
                initialfile=('Data_ket_qua_1_doan.xlsx' if single else 'Data_ket_qua_hang_loat.xlsx'),
                filetypes=[('Excel', '*.xlsx')])
            if not dest:
                return
            from batch_bundle import export_bundle
            export_bundle(source.get(), Path(dest).with_suffix(''), records)
            status.set(f'Đã xuất Data: {dest}')
            app.report_result('Xuất kết quả vào Data', status.get())
            log(status.get())
        except Exception as exc:
            app.report_result('Xuất kết quả vào Data', str(exc), error=True)
            messagebox.showerror('Xuất Data', str(exc), parent=window)

    def log(message):
        output.configure(state='normal')
        output.insert('end', message+'\n')
        output.see('end')
        output.configure(state='disabled')

    from ui_theme import ProcessingNotice
    processing_notice = None

    def close_processing_notice():
        nonlocal processing_notice
        if processing_notice is not None:
            processing_notice.close()
            processing_notice = None

    def close_window():
        if single_flow and getattr(app, '_single_batch_busy', False):
            messagebox.showinfo('Đang tính toán', 'Chờ tính toán xong trước khi đóng cửa sổ.', parent=window)
            return
        window.destroy()
    window.protocol('WM_DELETE_WINDOW', close_window)

    window.bind('<Destroy>', lambda event: close_processing_notice() if event.widget is window else None, add='+')

    def poll():
        try:
            while True:
                kind, value = queue.get_nowait()
                if kind == 'progress':
                    current, total, number, action = value
                    status.set(f'Đang xử lý {current}/{total} · STT {number}: {action}')
                    if hasattr(app,'summary_progress_text'):app.summary_progress_text.set(status.get())
                    log(status.get())
                elif kind == 'done':
                    close_processing_notice()
                    folder, records, failures = value
                    if single_flow:
                        app._single_batch_busy = False
                        app._single_batch_failures = failures
                    else:
                        app._batch_failures = failures
                    existing = {r.get('section_no'): r for r in
                                getattr(app, records_attr, []) if r.get('section_no') is not None}
                    for rec in records:
                        existing[rec['section_no']] = rec
                    others = [r for r in getattr(app, records_attr, [])
                              if r.get('section_no') is None]
                    setattr(app, records_attr, others + [existing[n] for n in sorted(existing)])
                    if single_flow:
                        app.single_treatment_summary_view.refresh()
                    if hasattr(app, 'refresh_treatment_boq'):
                        app.refresh_treatment_boq()
                    if hasattr(app, 'refresh_result_summary'):
                        app.refresh_result_summary()
                    if single_flow:
                        app._single_batch_data_export_path = str(Path(folder) / 'Ket_qua_hang_loat.xlsx')
                    else:
                        app._batch_data_export_path = str(Path(folder) / 'Ket_qua_hang_loat.xlsx')
                    if hasattr(app, 'refresh_data_preview'):
                        app.refresh_data_preview()
                    passed = sum(rec['status'] == 'ĐẠT' for rec in records)
                    status.set(f'Hoàn thành: {passed} đoạn đạt, {len(failures)} đoạn chưa đạt/lỗi.')
                    app.report_result('Xử lý hàng loạt', status.get())
                    log(f'Hồ sơ đã lưu: {folder}')
                    for failure in failures:
                        log(f'STT {failure["section_no"]}: {failure["reason"]}')
                    run_button.configure(state='normal')
                elif kind == 'error':
                    if single_flow:app._single_batch_busy = False
                    close_processing_notice()
                    status.set('Xử lý hàng loạt gặp lỗi.')
                    app.report_result('Xử lý hàng loạt', str(value), error=True)
                    run_button.configure(state='normal')
                    messagebox.showerror('Tính hàng loạt', str(value), parent=window)
        except Empty:
            pass
        if window.winfo_exists():
            window.after(100, poll)

    def start():
        nonlocal processing_notice
        try:
            if not available or not source.get():
                raise ValueError('Import bảng THSH/CTDY trước khi chạy.')
            if not destination.get().strip():
                raise ValueError('Chọn thư mục lưu hồ sơ các mặt cắt.')
            numbers = _parse_numbers(selected.get(), available)
            raw_priorities = [var.get().strip() for var in priority_vars]
            clean_priorities = [p for p in raw_priorities if p and p != '(Trống)']
            if len(clean_priorities) != len(set(clean_priorities)):
                raise ValueError('Các giải pháp ưu tiên được chọn không được trùng nhau.')
            if any(p not in OPTIONS for p in clean_priorities):
                raise ValueError('Có giải pháp ưu tiên không hợp lệ.')
            if not clean_priorities and app.calculation_settings()['after']:
                if not messagebox.askyesno('Xác nhận để trống ưu tiên',
                                           'Bạn đang để trống tất cả các giải pháp ưu tiên.\n'
                                           'Hệ thống sẽ chỉ kiểm toán lún tự nhiên (trước xử lý) cho các phân đoạn và xuất kết quả ra Data.xlsx.\n\n'
                                           'Bạn có chắc chắn muốn chạy không?', parent=window):
                    return
            settings = {key: float(var.get().replace(',', '.')) for key, var in inputs.items()}
            if any(not math.isfinite(value) or value <= 0 for value in settings.values()):
                raise ValueError('Bước tối ưu, chiều dài cọc, đường kính và chiều cao gia tải phải là số dương hữu hạn.')
            if count_mode.get() == 'cad' and any('CDM' in p for p in clean_priorities) and not cad_path.get().strip():
                raise ValueError('Chế độ CAD cho cọc CDM cần chọn tệp DXF có layer CDM<STT>.')
            cad = count_cdm_circles(cad_path.get()) if cad_path.get().strip() else {}
            settings['cad_source'] = cad_path.get().strip()
            settings['cdm_count_mode'] = count_mode.get()
            if ai_mode:
                app._ai_batch_priorities=list(clean_priorities)
                settings.update(getattr(app,'_ai_optimization_settings',{}) or {})
                settings['ai_optimize']=True
                settings['export_individual']=False
            app.collect()
            template = deepcopy(app.project)
            if single_flow:app._single_batch_busy = True
            run_button.configure(state='disabled')
            status.set(f'Đang xử lý 0/{len(numbers)} phân đoạn…')
            app.status_text.set(status.get())
            processing_notice=ProcessingNotice(app, 'Tính toán và xuất hồ sơ', detail=status)
            pri_desc = " → ".join(clean_priorities) if clean_priorities else "Chỉ kiểm toán lún tự nhiên (không xử lý)"
            log(f'Bắt đầu {len(numbers)} đoạn; ưu tiên: {pri_desc}')

            def worker():
                try:
                    finished = run_batch(source.get(), numbers, tuple(clean_priorities),
                                         template, destination.get(), settings, cad,
                                         lambda *args: queue.put(('progress', args)))
                    queue.put(('done', finished))
                except Exception as exc:
                    queue.put(('error', exc))
            threading.Thread(target=worker, daemon=True).start()
        except Exception as exc:
            if single_flow:app._single_batch_busy = False
            messagebox.showerror('Thiết lập tính hàng loạt', str(exc), parent=window)

    run_button.configure(command=start)
    if source.get() and Path(source.get()).is_file():
        scan()
    poll()
