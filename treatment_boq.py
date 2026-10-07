"""Mục 10: Khối lượng xử lý từ phương án đã tính và mặt cắt tương ứng."""
from __future__ import annotations

import math
from model import expansion_geometry, treatment_ranges


def calculate_section_boq(record: dict, length_m: float, project) -> dict:
    """Tính khối lượng từ thông số đã tính, chỉ trong vùng mở rộng nếu có."""
    payload = record.get('payload', {})
    group = payload.get('treatment_group', '')
    main_toe = project.crest_half_width + project.slope_width
    if project.expansion_width > 0:
        width = sum(right-left for left, right in treatment_ranges(project))
    else:
        width = 2*main_toe
    area_treat = width*length_m
    data = dict(length_m=length_m, treatment_width_m=width, area_treat_m2=area_treat,
                v_excavation=0.0, v_sand_fill=0.0, a_geotextile=0.0,
                l_pvd=0.0, l_sd=0.0, n_drains=0, n_piles=0,
                v_cdm=0.0, l_cdm=0.0, v_surcharge=0.0,
                v_surcharge_removal=0.0, wait_days=0.0)
    if group == 'mechanical':
        h = max(0.0, payload.get('replacement_depth', 0.0))
        # Mái đào 1:1 mở rộng về đáy; giữ cùng biểu thức trong Excel KL.
        data['v_excavation'] = (width+(0.0 if project.expansion_width > 0 else h))*h*length_m if h else 0.0
        data['v_sand_fill'] = data['v_excavation']
        density = 25.0
        pile_width = max(0.0, width if project.expansion_width > 0 else width+2*h)
        pile_count = math.ceil(pile_width*length_m*density)
        data['pile_density_m2'] = density
        data['n_bamboo'] = pile_count if payload.get('bamboo_depth', 0) > 0 else 0
        data['n_cajuput'] = pile_count if payload.get('cajuput_depth', 0) > 0 else 0
        data['n_piles'] = data['n_bamboo'] + data['n_cajuput']
        data['l_bamboo'] = data['n_bamboo'] * payload.get('bamboo_depth', 0.0)
        data['l_cajuput'] = data['n_cajuput'] * payload.get('cajuput_depth', 0.0)
    elif group == 'drainage':
        mode = payload.get('treatment', '')
        if mode.startswith(('PVD', 'SD')):
            spacing = payload.get('drain_spacing', 0.0)
            length = payload.get('drain_length', 0.0) or sum(s.thickness for s in project.soils)
            factor = math.sqrt(3)/2 if payload.get('drain_pattern') == 'Tam giác' else 1.0
            if spacing > 0:
                data['n_drains'] = math.ceil(area_treat/(factor*spacing**2))
                data['l_sd' if mode.startswith('SD') else 'l_pvd'] = data['n_drains']*length
                cushion = max(0.0, getattr(project, 'h_sand_cushion', 0.0))
                data['v_sand_fill'] = area_treat*cushion
        data['wait_days'] = max(0.0, float(payload.get('wait_days', 0.0)))
    elif group == 'cdm':
        cell = payload.get('cdm_cell_area', 0.0)
        ac = payload.get('cdm_area_pile', 0.0)
        lc = payload.get('cdm_lc', 0.0)
        count_mode = record.get('cdm_count_mode',
                                'cad' if record.get('cad_cdm_count') is not None else 'formula')
        cad_count = record.get('cad_cdm_count') if count_mode == 'cad' else None
        if count_mode == 'cad' and cad_count is None:
            raise ValueError(f'STT {record.get("section_no", "?")}: chưa có CIRCLE trên layer CDM tương ứng.')
        if lc > 0 and (cad_count is not None or cell > 0):
            data['n_piles'] = int(cad_count) if cad_count is not None else math.ceil(area_treat/cell)
            data['l_cdm'] = data['n_piles']*lc
            data['v_cdm'] = data['l_cdm']*ac
        data['a_geotextile'] = area_treat*payload.get('cdm_n_layer', 0)
        # Đệm xi măng ALiCC không được ghi nhầm thành khối lượng cát.
    if group in ('mechanical', 'drainage'):
        h = max(0.0, payload.get('surcharge_height', 0.0))
        if h:
            top_width = (project.expansion_width*(1 if project.expansion_side != 'Hai bên' else 2)
                         if project.expansion_width > 0 else 2*project.crest_half_width)
            data['v_surcharge'] = (top_width*h+1.2*h*h)*length_m
            data['v_surcharge_removal'] = data['v_surcharge']
    return data


def build_view(parent):
    """Trang menu 10, bóc khối lượng của các phân đoạn đã chọn ở menu 8."""
    import csv
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    app = parent.winfo_toplevel()
    header = ttk.Frame(parent, padding=10)
    header.pack(fill='x')
    ttk.Label(header, text='TÍNH TOÁN KHỐI LƯỢNG XỬ LÝ',
              font=('Times New Roman', 12, 'bold')).pack(side='left')
    frame = ttk.Frame(parent, padding=(10, 3, 10, 10))
    frame.pack(fill='both', expand=True)
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    keys = ('station', 'option', 'length', 'wait', 'excavation', 'pvd', 'sd',
            'cdm_count', 'cdm_length', 'cdm_volume', 'geo', 'surcharge')
    headers = ('Lý trình', 'Phương án', 'L đoạn (m)', 'Chờ lún (ngày)',
               'Đào thay (m³)', 'PVD (m)', 'SD (m)', 'Số cọc CDM', 'Cọc CDM (m)',
               'CDM (m³)', 'Vải địa (m²)', 'Gia tải (m³)')
    widths = (160, 220, 90, 100, 115, 120, 120, 95, 110, 100, 100, 110)
    tree = ttk.Treeview(frame, columns=keys, show='headings')
    for key, title, width in zip(keys, headers, widths):
        tree.heading(key, text=title)
        tree.column(key, width=width, minwidth=width, stretch=False)
    scroll_x = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
    scroll_y = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
    tree.configure(xscrollcommand=scroll_x.set, yscrollcommand=scroll_y.set)
    tree.grid(row=0, column=0, sticky='nsew')
    scroll_y.grid(row=0, column=1, sticky='ns')
    scroll_x.grid(row=1, column=0, sticky='ew')
    notice = tk.StringVar(value='Chọn và lưu phương án tại mục 8 để tính khối lượng.')
    ttk.Label(parent, textvariable=notice, padding=(10, 0, 10, 10)).pack(anchor='w')
    source_bar = ttk.Frame(parent, padding=(10, 0, 10, 5))
    source_bar.pack(fill='x')
    ttk.Label(source_bar, text='Số cọc CDM:').pack(side='left')
    count_mode = tk.StringVar(value='formula')

    export_records = [None]

    def records_attribute():
        return '_saved_sections_data'

    def records():
        if app.design_mode.get() != 'TÍNH TOÀN TUYẾN': return []
        if export_records[0] is not None: return export_records[0]
        return [rec for rec in getattr(app, records_attribute(), [])
                if not rec.get('needs_review') and rec.get('status') == 'ĐẠT']

    def export_excel_bth():
        if not records():
            messagebox.showwarning('Chưa có dữ liệu', 'Chưa có phương án đã chọn tại mục 8.', parent=app)
            return
        dest = filedialog.asksaveasfilename(parent=app, defaultextension='.xlsx',
                                            initialfile='BTH_ket_qua_xu_ly.xlsx',
                                            filetypes=[('Excel', '*.xlsx')])
        if dest:
            try:
                from section_excel import export_bth
                export_bth(dest, records())
                messagebox.showinfo('BTH', f'Đã xuất bảng tổng hợp:\n{dest}', parent=app)
            except Exception as exc:
                messagebox.showerror('Xuất bảng tổng hợp', str(exc), parent=app)

    def import_excel_bth():
        if app.design_mode.get() != 'TÍNH TOÀN TUYẾN': return
        src = filedialog.askopenfilename(parent=app, title='Nhập bảng tổng hợp',
                                         filetypes=[('Excel', '*.xlsx')])
        if not src:
            return
        try:
            from section_excel import import_bth
            loaded = import_bth(src)
            current = {rec.get('section_no'): rec for rec in records()
                       if rec.get('section_no') is not None}
            for rec in loaded:
                current[rec['section_no']] = rec
            others = [rec for rec in records() if rec.get('section_no') is None]
            setattr(app, records_attribute(), others + [current[key] for key in sorted(current)])
            modes = {rec.get('cdm_count_mode', 'formula') for rec in records()
                     if rec.get('payload', {}).get('treatment_group') == 'cdm'}
            count_mode.set('cad' if modes == {'cad'} else 'formula')
            refresh()
            if hasattr(app, 'refresh_result_summary'):
                app.refresh_result_summary()
            notice.set(f'Đã import {len(loaded)} phân đoạn từ BTH; khối lượng đã tính lại.')
        except Exception as exc:
            messagebox.showerror('Nhập bảng tổng hợp', str(exc), parent=app)

    def import_cdm_dxf():
        src = filedialog.askopenfilename(parent=app, title='Đếm cọc CDM từ DXF',
                                         filetypes=[('Bản vẽ DXF', '*.dxf')])
        if not src:
            return
        try:
            from cad_cdm import count_cdm_circles
            counts = count_cdm_circles(src)
            matched = set()
            for rec in records():
                number = rec.get('section_no')
                if number in counts and rec.get('payload', {}).get('treatment_group') == 'cdm':
                    rec['cad_cdm_count'] = counts[number]
                    rec['cad_cdm_source'] = src
                    matched.add(number)
            if matched:
                count_mode.set('cad')
                set_cdm_count_source()
            else:
                refresh()
            remainder = ', '.join(f'CDM{i}' for i in counts if i not in matched)
            notice.set(f'Đã ghép {len(matched)} phân đoạn CDM; '
                       + (f'layer chưa ghép: {remainder}.' if remainder else 'số cọc lấy từ CIRCLE.'))
        except Exception as exc:
            messagebox.showerror('Import CAD CDM', str(exc), parent=app)

    def set_cdm_count_source():
        mode = count_mode.get()
        cdm_records = [r for r in records() if r.get('payload', {}).get('treatment_group') == 'cdm']
        if mode == 'cad':
            missing = [r.get('section_no') for r in cdm_records if r.get('cad_cdm_count') is None]
            if missing:
                count_mode.set('formula')
                messagebox.showwarning('Thiếu số cọc CAD',
                                       f'Chưa có CIRCLE trên layer CDM của STT {missing}.', parent=app)
                return
        for rec in cdm_records:
            rec['cdm_count_mode'] = mode
        refresh()

    ttk.Radiobutton(source_bar, text='Theo Bxl × L / A ô cọc', variable=count_mode,
                    value='formula', command=set_cdm_count_source).pack(side='left', padx=10)
    ttk.Radiobutton(source_bar, text='CIRCLE từ DXF (CDM1, CDM2…)', variable=count_mode,
                    value='cad', command=set_cdm_count_source).pack(side='left', padx=10)

    def export_excel_kl():
        if not records():
            messagebox.showwarning('Chưa có dữ liệu', 'Chưa có phân đoạn đã chọn.', parent=app)
            return
        dest = filedialog.asksaveasfilename(parent=app, defaultextension='.xlsx',
                                            initialfile='KL_xu_ly_dat_yeu.xlsx',
                                            filetypes=[('Excel', '*.xlsx')])
        if not dest:
            return
        try:
            from boq_excel import export_kl
            export_kl(dest, records())
            messagebox.showinfo('Bảng khối lượng', f'Đã xuất bảng KL có công thức:\n{dest}', parent=app)
        except Exception as exc:
            messagebox.showerror('Xuất KL Excel', str(exc), parent=app)

    def refresh():
        tree.delete(*tree.get_children())
        sums = [0.0]*10
        missing_lengths = []
        shown = 0
        for rec in records():
            if not rec.get('length') or rec['length'] <= 0:
                missing_lengths.append(str(rec.get('section_no', '—')))
                continue
            shown += 1
            snap = rec.get('project_snapshot')
            if snap is not None:
                rec['boq'] = calculate_section_boq(rec, rec['length'], snap)
            boq = rec.get('boq', {})
            numbers = [rec.get('length', 0.0), boq.get('wait_days', 0.0),
                       boq.get('v_excavation', 0.0), boq.get('l_pvd', 0.0),
                       boq.get('l_sd', 0.0), boq.get('n_piles', 0), boq.get('l_cdm', 0.0),
                       boq.get('v_cdm', 0.0), boq.get('a_geotextile', 0.0),
                       boq.get('v_surcharge', 0.0)]
            sums = [a+b for a,b in zip(sums, numbers)]
            tree.insert('', 'end', values=(rec['station'], rec['opt_name'],
                        *(f'{value:.2f}' for value in numbers)))
        if shown:
            tree.insert('', 'end', values=('TỔNG', 'CÁC PHÂN ĐOẠN',
                        *(f'{value:.2f}' for value in sums)), tags=('total',))
            notice.set(f'{shown} phân đoạn; công thức Excel được xuất theo từng mặt cắt. '
                       'Mật độ cọc tre và cừ tràm: 25 cọc/m².')
        else:
            notice.set('Chưa có phương án chọn để tính khối lượng.')
        if missing_lengths:
            notice.set(notice.get() + ' Chưa tính khối lượng STT ' + ', '.join(missing_lengths) + ': thiếu chiều dài phân đoạn.')
        app.report_result('Khối lượng xử lý', notice.get())
    tree.tag_configure('total', background='#FEF3C7', font=('Times New Roman', 9, 'bold'))

    def export_csv():
        if not records():
            messagebox.showwarning('Chưa có dữ liệu', 'Chưa có phân đoạn đã chọn.', parent=app)
            return
        dest = filedialog.asksaveasfilename(parent=app, defaultextension='.csv',
                                            filetypes=[('CSV Document', '*.csv')],
                                            initialfile='Khoi_luong_xu_ly.csv')
        if not dest:
            return
        refresh()
        with open(dest, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for item in tree.get_children():
                writer.writerow(tree.item(item, 'values'))
        messagebox.showinfo('Thành công', f'Đã lưu bảng khối lượng:\n{dest}', parent=app)

    def calculate_ai_quantities():
        if not app.require_full_license():
            return
        try:
            from ai_analysis_data import calculate_saved_quantities
            updated = calculate_saved_quantities(records())
            setattr(app, records_attribute(), updated)
            refresh()
            notice.set(f'AI đã tính khối lượng {len(updated)} đoạn từ các phương án chốt ở mục 9; '
                       'dùng hình học và thông số xử lý đã lưu của từng đoạn.')
            app.report_result('Khối lượng bằng AI', notice.get())
        except Exception as exc:
            messagebox.showerror('Khối lượng bằng AI', str(exc), parent=app)

    ttk.Button(header, text='Tính bằng AI',
               command=lambda: app.run_processing('Khối lượng bằng AI', calculate_ai_quantities),
               style='Accent.TButton').pack(side='right', padx=5)

    ttk.Button(header, text='Cập nhật khối lượng',
               command=lambda: app.run_processing('Khối lượng xử lý', refresh)).pack(side='right', padx=5)
    ttk.Button(header, text='Nhập bảng tổng hợp', command=import_excel_bth).pack(side='right', padx=5)
    ttk.Button(header, text='Đọc cọc từ bản vẽ', command=import_cdm_dxf).pack(side='right', padx=5)
    def export_for_workflow(callback):
        if app.design_mode.get() != 'TÍNH TOÀN TUYẾN': return
        from copy import deepcopy
        from design_workflow import workflow_pdf_records
        rows = []
        for entry in workflow_pdf_records(app):
            record = deepcopy(entry['record'])
            if not record or record.get('project_snapshot') is None:
                continue
            project = record['project_snapshot']
            record.setdefault('section_no', entry['number'])
            record.setdefault('station', project.station)
            record.setdefault('length', ((getattr(app, '_active_section_length', None) or 0.0)
                                        if entry['number'] == (getattr(app, '_active_section_no', None) or 1)
                                        else 0.0))
            if record['length'] <= 0:
                raise ValueError(f"STT {entry['number']}: chưa có chiều dài phân đoạn để xuất khối lượng.")
            rows.append(record)
        export_records[0] = rows
        try:
            callback()
        finally:
            export_records[0] = None
            refresh()
    app._treatment_export_commands = {
        'summary': lambda: export_for_workflow(export_excel_bth),
        'table': lambda: export_for_workflow(export_csv),
        'template': lambda: export_for_workflow(export_excel_kl),
    }
    return refresh
