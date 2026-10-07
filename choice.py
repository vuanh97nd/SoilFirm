"""Tổng hợp các phương án đã tính và khối lượng theo từng mặt cắt."""
from __future__ import annotations

import csv
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from utils import ScrollableFrame
from ui_theme import COLORS, UI_FONT, UI_FONT_MONO
from result_summary import collect_calculated_options, project_signature
from treatment_boq import calculate_section_boq


def parse_km_to_meters(km_str: str) -> float | None:
    """Quy đổi chuỗi lý trình KM (ví dụ: '1+200', 'KM 1+200', '1200') ra mét."""
    clean = str(km_str).strip().upper().replace("KM", "").strip()
    if "+" in clean:
        parts = clean.split("+")
        try:
            km = float(parts[0].replace(",", "."))
            m = float(parts[1].replace(",", "."))
            return km * 1000.0 + m
        except Exception:
            return None
    try:
        val = float(clean.replace(",", "."))
        return val if val >= 100 else val * 1000.0
    except Exception:
        return None


def build_view(parent: tk.Misc) -> None:
    app = parent.winfo_toplevel()

    tabs_main = ttk.Notebook(parent)
    tabs_main.pack(fill='both', expand=True, padx=8, pady=6)

    tab_current = ttk.Frame(tabs_main)
    tab_summary = ttk.Frame(tabs_main)

    tabs_main.add(tab_current, text="  Kết quả đã tính & Đánh giá mặt cắt  ")
    # Bảng tổng hợp và BOQ được mở qua menu 9 và 10.

    # =========================================================================
    # TAB 1: MA TRẬN TỐI ƯU MẶT CẮT HIỆN TẠI
    # =========================================================================
    scroll_cur = ScrollableFrame(tab_current)
    scroll_cur.pack(fill='both', expand=True)
    root_cur = scroll_cur.scrollable_frame

    f_top = tk.Frame(root_cur, bg=COLORS['background'])
    f_top.pack(fill='x', padx=12, pady=(6, 2))
    tk.Label(f_top, text="TỔNG HỢP KẾT QUẢ CÁC PHƯƠNG ÁN ĐÃ TÍNH",
             font=(UI_FONT, 12, 'bold'), fg=COLORS['nav'], bg=COLORS['background']).pack(anchor='w')
    tk.Label(f_top, text="Sử dụng kết quả tính tại các bước trước; nhóm chưa tính sẽ không được đánh giá.",
             font=(UI_FONT, 9, 'italic'), fg=COLORS['muted'], bg=COLORS['background']).pack(anchor='w')

    box_cfg = ttk.LabelFrame(root_cur, text="Chọn các nhóm kết quả cần tổng hợp", padding=8)
    box_cfg.pack(fill='x', padx=12, pady=4)

    # Nhóm 1
    f_g1 = ttk.Frame(box_cfg)
    f_g1.pack(fill='x', pady=2)
    var_chk_g1 = tk.BooleanVar(value=True)
    ttk.Checkbutton(f_g1, text="Nhóm 1 - Nền tự nhiên:", variable=var_chk_g1, width=28).pack(side='left')
    ttk.Label(f_g1, text="Chờ lún tự nhiên theo thời gian t (Kiểm tra điều kiện không cần xử lý)", font=(UI_FONT, 9, 'bold')).pack(side='left', padx=6)

    # Nhóm 2
    f_g2 = ttk.Frame(box_cfg)
    f_g2.pack(fill='x', pady=2)
    var_chk_g2 = tk.BooleanVar(value=True)
    ttk.Checkbutton(f_g2, text="Nhóm 2 - Gia cường cơ học:", variable=var_chk_g2, width=28).pack(side='left')
    ttk.Label(f_g2, text="Lấy chiều sâu đào, cọc tre/cừ tràm và lún dư từ lần tính cơ học.", font=(UI_FONT, 9, 'bold'), foreground='#0369A1').pack(side='left', padx=6)

    # Nhóm 3
    f_g3 = ttk.Frame(box_cfg)
    f_g3.pack(fill='x', pady=2)
    var_chk_g3 = tk.BooleanVar(value=True)
    ttk.Checkbutton(f_g3, text="Nhóm 3 - Cố kết thoát nước:", variable=var_chk_g3, width=28).pack(side='left')
    ttk.Label(f_g3, text="Lấy PVD, SD hoặc chờ lún cùng U và lún dư của lần tính thoát nước.", font=(UI_FONT, 9, 'bold'), foreground='#7C3AED').pack(side='left', padx=6)

    # Nhóm 4
    f_g4 = ttk.Frame(box_cfg)
    f_g4.pack(fill='x', pady=2)
    var_chk_g4 = tk.BooleanVar(value=True)
    ttk.Checkbutton(f_g4, text="Nhóm 4 - Trộn sâu CDM:", variable=var_chk_g4, width=28).pack(side='left')
    ttk.Label(f_g4, text="Lấy kết quả TCVN/BS và ALiCC của phạm vi đang chọn tại Bước 7.", font=(UI_FONT, 9, 'bold'), foreground='#B45309').pack(side='left', padx=6)

    bar_action = tk.Frame(root_cur, bg='#E2E8F0', padx=12, pady=8, relief='solid', bd=1)
    bar_action.pack(fill='x', padx=12, pady=6)

    lbl_info_mcn = tk.Label(bar_action, text="Mặt cắt: ---  |  Htk: --- m  |  [ΔS] cho phép: --- cm  |  Thời gian: --- ngày",
                            font=(UI_FONT, 9, 'bold'), fg='#1E293B', bg='#E2E8F0')
    lbl_info_mcn.pack(side='left')

    btn_run_all = tk.Button(bar_action, text='Làm mới bảng',
                            bg='#0284C7', fg='white', activebackground='#0369A1', activeforeground='white',
                            font=(UI_FONT, 10, 'bold'), relief='flat', cursor='hand2')
    btn_run_all.pack(side='right', ipady=4, ipadx=10)

    box_matrix = ttk.LabelFrame(root_cur, text="Ma trận kết quả phương án & đánh giá", padding=8)
    box_matrix.pack(fill='both', expand=True, padx=12, pady=4)

    cols = ('stt', 'group', 'opt_name', 'params', 'residual', 'limit', 'time', 'cost', 'eval', 'notes')
    headers = [
        'STT', 'Nhóm giải pháp', 'Phương án đã tính', 'Thông số thiết kế',
        'Lún kiểm toán (cm)', 'Giới hạn [ΔS]', 'Thời gian', 'Chi phí tương đối', 'Kết luận', 'Chi tiết kiểm toán'
    ]
    widths = [36, 130, 190, 210, 100, 90, 110, 115, 120, 260]

    style = ttk.Style(parent)
    style.configure("Choice.Treeview.Heading", font=(UI_FONT, 9, 'bold'), padding=(3, 5))
    style.configure("Choice.Treeview", font=(UI_FONT, 9), rowheight=24)

    tree_frame = ttk.Frame(box_matrix)
    tree_frame.pack(fill='both', expand=True)
    tree_frame.rowconfigure(0, weight=1)
    tree_frame.columnconfigure(0, weight=1)

    tree = ttk.Treeview(tree_frame, columns=cols, show='headings', height=6,
                        selectmode='browse', style="Choice.Treeview")
    sb_y = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
    sb_x = ttk.Scrollbar(tree_frame, orient='horizontal', command=tree.xview)
    tree.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

    tree.grid(row=0, column=0, sticky='nsew')
    sb_y.grid(row=0, column=1, sticky='ns')
    sb_x.grid(row=1, column=0, sticky='ew')

    for cid, head, w in zip(cols, headers, widths):
        tree.heading(cid, text=head)
        tree.column(cid, width=w, minwidth=w,
                    anchor='w' if cid in ('opt_name', 'params', 'notes') else 'center', stretch=False)

    tree.tag_configure('pass', foreground='#047857', font=(UI_FONT, 9, 'bold'))
    tree.tag_configure('fail', foreground='#DC2626', font=(UI_FONT, 9, 'bold'))
    tree.tag_configure('even', background='#FFFFFF')
    tree.tag_configure('odd', background='#F8FAFC')

    box_recommend = ttk.LabelFrame(root_cur, text="Nhận xét kết quả đã tính cho mặt cắt", padding=8)
    box_recommend.pack(fill='x', padx=12, pady=4)

    txt_recommend = tk.Text(box_recommend, height=4, wrap='word', font=(UI_FONT, 9),
                            bg='#F1F5F9', fg='#0F172A', relief='solid', bd=1, padx=8, pady=6)
    txt_recommend.pack(fill='x')
    txt_recommend.insert('1.0', "Tính từng phương án tại các bước trước, sau đó bấm 'CẬP NHẬT KẾT QUẢ ĐÃ TÍNH'.")
    txt_recommend.configure(state='disabled')

    box_decision = ttk.LabelFrame(root_cur, text="Phương án lựa chọn cho mặt cắt", padding=10)
    box_decision.pack(fill='x', padx=12, pady=(4, 10))

    f_d1 = ttk.Frame(box_decision)
    f_d1.pack(fill='x', pady=3)
    ttk.Label(f_d1, text="Phương án lựa chọn:", font=(UI_FONT, 9, 'bold')).pack(side='left', padx=(0, 10))
    var_chosen = tk.StringVar()
    cb_chosen = ttk.Combobox(f_d1, textvariable=var_chosen, state='readonly', width=55, font=(UI_FONT, 9, 'bold'))
    cb_chosen.pack(side='left', padx=(0, 15))
    lbl_chosen_status = ttk.Label(f_d1, text="", font=(UI_FONT, 9, 'bold'))
    lbl_chosen_status.pack(side='left')

    f_d2 = ttk.Frame(box_decision)
    f_d2.pack(fill='x', pady=4)
    ttk.Label(f_d2, text="Chiều dài phân đoạn L (m):").pack(side='left', padx=(0, 4))
    var_section_len = tk.StringVar(value="100.0")
    ent_section_len = ttk.Entry(f_d2, textvariable=var_section_len, width=10, font=(UI_FONT, 9, 'bold'))
    ent_section_len.pack(side='left', padx=(0, 20))

    ttk.Label(f_d2, text="Ghi chú kỹ thuật:").pack(side='left', padx=(0, 6))
    var_note = tk.StringVar(value="Đạt độ lún dư cho phép, đảm bảo an toàn chịu lực và tối ưu chi phí đầu tư.")
    ent_note = ttk.Entry(f_d2, textvariable=var_note, width=50, font=(UI_FONT, 9))
    ent_note.pack(side='left', fill='x', expand=True)

    f_d3 = ttk.Frame(box_decision)
    f_d3.pack(fill='x', pady=(8, 2))
    btn_apply = tk.Button(f_d3, text='Xác nhận phương án',
                          bg='#047857', fg='white', activebackground='#065F46', activeforeground='white',
                          font=(UI_FONT, 9, 'bold'), relief='flat', cursor='hand2')
    btn_apply.pack(side='left', padx=(0, 15), ipady=5, ipadx=12)

    lbl_applied_msg = ttk.Label(f_d3, text="", font=(UI_FONT, 9, 'bold'), foreground='#047857')
    lbl_applied_msg.pack(side='left', padx=10)

    # =========================================================================
    # TAB 2: BẢNG TỔNG HỢP TOÀN TUYẾN & BẢNG KHỐI LƯỢNG BOQ
    # =========================================================================
    sub_tabs_summary = ttk.Notebook(tab_summary)
    sub_tabs_summary.pack(fill='both', expand=True, padx=6, pady=6)

    sub_tab_tech = ttk.Frame(sub_tabs_summary)
    sub_tab_boq = ttk.Frame(sub_tabs_summary)

    sub_tabs_summary.add(sub_tab_tech, text="  9. Bảng tổng hợp kết quả xử lý  ")
    sub_tabs_summary.add(sub_tab_boq, text="  10. Tính toán khối lượng xử lý  ")

    # 2.1 Bảng Giải pháp Kỹ thuật
    f_tech_table = ttk.Frame(sub_tab_tech, padding=8)
    f_tech_table.pack(fill='both', expand=True)
    f_tech_table.rowconfigure(0, weight=1)
    f_tech_table.columnconfigure(0, weight=1)

    sum_cols = ('stt', 'station', 'length', 'h_design', 'limit', 'group', 'opt_name', 'params', 'residual', 'status', 'notes')
    sum_headers = [
        'STT', 'Lý trình / Phân đoạn', 'L đoạn (m)', 'H đắp (m)', 'Giới hạn [ΔS]',
        'Nhóm giải pháp', 'Phương án đã chọn', 'Thông số kỹ thuật', 'Lún kiểm toán (cm)', 'Đánh giá', 'Ghi chú kỹ thuật'
    ]
    sum_widths = [36, 130, 80, 75, 85, 120, 180, 190, 100, 95, 200]

    tree_summary = ttk.Treeview(f_tech_table, columns=sum_cols, show='headings', selectmode='browse', style="Choice.Treeview")
    sb_sum_y = ttk.Scrollbar(f_tech_table, orient='vertical', command=tree_summary.yview)
    sb_sum_x = ttk.Scrollbar(f_tech_table, orient='horizontal', command=tree_summary.xview)
    tree_summary.configure(yscrollcommand=sb_sum_y.set, xscrollcommand=sb_sum_x.set)

    tree_summary.grid(row=0, column=0, sticky='nsew')
    sb_sum_y.grid(row=0, column=1, sticky='ns')
    sb_sum_x.grid(row=1, column=0, sticky='ew')

    for cid, head, w in zip(sum_cols, sum_headers, sum_widths):
        tree_summary.heading(cid, text=head)
        tree_summary.column(cid, width=w, minwidth=w,
                            anchor='w' if cid in ('opt_name', 'params', 'notes') else 'center', stretch=False)

    tree_summary.tag_configure('pass', foreground='#047857', font=(UI_FONT, 9, 'bold'))
    tree_summary.tag_configure('fail', foreground='#DC2626', font=(UI_FONT, 9, 'bold'))
    tree_summary.tag_configure('even', background='#FFFFFF')
    tree_summary.tag_configure('odd', background='#F8FAFC')

    # 2.2 Bảng Tổng hợp Khối lượng (BOQ)
    f_boq_table = ttk.Frame(sub_tab_boq, padding=8)
    f_boq_table.pack(fill='both', expand=True)
    f_boq_table.rowconfigure(0, weight=1)
    f_boq_table.columnconfigure(0, weight=1)

    boq_cols = ('stt', 'station', 'length', 'opt_name', 'v_exc', 'v_sand', 'a_geo', 'l_pvd', 'n_pile', 'v_cdm', 'v_sur')
    boq_headers = [
        'STT', 'Lý trình / Phân đoạn', 'L đoạn (m)', 'Giải pháp xử lý',
        'Đào thay đất (m³)', 'Cát đệm / Đắp trả (m³)', 'Vải địa KT (m²)', 'Bấc/cọc thoát nước (m)',
        'Cọc tre/tràm (cây)', 'Cọc CDM (m³)', 'Đất gia tải (m³)'
    ]
    boq_widths = [36, 130, 80, 180, 110, 130, 110, 110, 110, 100, 100]

    tree_boq = ttk.Treeview(f_boq_table, columns=boq_cols, show='headings', selectmode='browse', style="Choice.Treeview")
    sb_boq_y = ttk.Scrollbar(f_boq_table, orient='vertical', command=tree_boq.yview)
    sb_boq_x = ttk.Scrollbar(f_boq_table, orient='horizontal', command=tree_boq.xview)
    tree_boq.configure(yscrollcommand=sb_boq_y.set, xscrollcommand=sb_boq_x.set)

    tree_boq.grid(row=0, column=0, sticky='nsew')
    sb_boq_y.grid(row=0, column=1, sticky='ns')
    sb_boq_x.grid(row=1, column=0, sticky='ew')

    for cid, head, w in zip(boq_cols, boq_headers, boq_widths):
        tree_boq.heading(cid, text=head)
        tree_boq.column(cid, width=w, minwidth=w,
                        anchor='w' if cid == 'opt_name' else 'center', stretch=False)

    tree_boq.tag_configure('even', background='#FFFFFF')
    tree_boq.tag_configure('odd', background='#F8FAFC')
    tree_boq.tag_configure('total', background='#FEF3C7', font=(UI_FONT, 9, 'bold'))

    f_sum_actions = tk.Frame(tab_summary, padx=12, pady=8)
    f_sum_actions.pack(fill='x')

    btn_export_tech = ttk.Button(f_sum_actions, text='Xuất bảng phương án')
    btn_export_tech.pack(side='left', padx=(0, 8), ipady=3)

    btn_export_boq = ttk.Button(f_sum_actions, text='Xuất bảng khối lượng', style='Accent.TButton')
    btn_export_boq.pack(side='left', padx=(0, 16), ipady=3)

    btn_del_section = ttk.Button(f_sum_actions, text="🗑 Xóa phân đoạn chọn", style='Danger.TButton')
    btn_del_section.pack(side='left', padx=(0, 8), ipady=3)

    btn_clear_all = ttk.Button(f_sum_actions, text="🔄 Xóa toàn bộ danh sách", style='Danger.TButton')
    btn_clear_all.pack(side='left', ipady=3)

    results_list = []
    if not hasattr(app, '_saved_sections_data'):
        app._saved_sections_data = []

    def sync_bar():
        p = getattr(app, 'project', None)
        if not p:
            return
        lbl_info_mcn.config(
            text=f'Mặt cắt: {p.station or "Chưa nhập"}  |  Htk = {p.h_design:.2f} m  |  '
                 f'Giới hạn [ΔS] = {p.residual_limit_cm:.1f} cm  |  '
                 f'Thời gian đánh giá t = {p.assessment_days:.0f} ngày')
        start = parse_km_to_meters(p.station_from)
        end = parse_km_to_meters(p.station_to)
        if start is not None and end is not None and end > start:
            var_section_len.set(f'{end-start:.1f}')
        elif getattr(app, '_active_section_length', None):
            var_section_len.set(f'{app._active_section_length:.2f}')

    def execute_auto_calculations():
        try:
            app.collect()
            sync_bar()
            selected = (var_chk_g1.get(), var_chk_g2.get(),
                        var_chk_g3.get(), var_chk_g4.get())
            options, missing = collect_calculated_options(app, selected)
            results_list[:] = options
            tree.delete(*tree.get_children())
            choices = []
            for idx, item in enumerate(results_list, 1):
                tree.insert('', 'end', iid=str(idx),
                            tags=('pass' if item.is_pass else 'fail',
                                  'even' if idx % 2 == 0 else 'odd'), values=(
                    idx, item.group_name, item.opt_name, item.opt_params_desc,
                    f'{item.residual_cm:.2f}', f'{item.limit_cm:.1f}', item.time_desc,
                    item.cost_level, 'ĐẠT' if item.is_pass else 'KHÔNG ĐẠT',
                    item.tech_notes))
                choices.append(f'{idx}. [{item.group_name}] {item.opt_name}')
            cb_chosen['values'] = choices
            var_chosen.set('')
            lbl_applied_msg.config(text='')
            if results_list:
                auto_recommend()
            else:
                txt_recommend.configure(state='normal')
                txt_recommend.delete('1.0', 'end')
                txt_recommend.insert('1.0', 'Chưa có kết quả phù hợp với dữ liệu hiện tại. Hãy bấm Tính ở từng nhóm.')
                txt_recommend.configure(state='disabled')
            app.status_text.set('Chưa lấy: ' + '; '.join(missing) if missing
                                else 'Đã đồng bộ các kết quả đã tính.')
            app.report_result('Lựa chọn phương án',
                              f'{len(options)} phương án đã tính; '
                              f'{sum(item.is_pass for item in options)} phương án đạt.'
                              + (' Chưa lấy: ' + '; '.join(missing) if missing else ''))
        except Exception as ex:
            app.report_result('Lựa chọn phương án', str(ex), error=True)
            messagebox.showerror('Lỗi tổng hợp phương án', str(ex), parent=app)

    def auto_recommend():
        txt_recommend.configure(state='normal')
        txt_recommend.delete('1.0', 'end')
        passing = [item for item in results_list if item.is_pass]
        lines = ([f'{len(passing)}/{len(results_list)} phương án đã tính thỏa các kiểm tra được hiển thị.']
                 if results_list else ['Chưa có kết quả đã tính.'])
        for item in results_list:
            lines.append(f'• {item.opt_name}: {item.residual_cm:.2f} cm / '
                         f'{item.limit_cm:.2f} cm — {"ĐẠT" if item.is_pass else "KHÔNG ĐẠT"}. '
                         f'{item.tech_notes}')
        lines.append('Chi phí chỉ được so sánh sau khi khai báo đơn giá; bảng này không tự xếp hạng kinh tế.')
        txt_recommend.insert('1.0', '\n'.join(lines))
        txt_recommend.configure(state='disabled')
        if results_list:
            best = next((i for i, item in enumerate(results_list) if item.is_pass), 0)
            cb_chosen.current(best)
            update_status_label()

    def update_status_label(_event=None):
        sel = cb_chosen.get()
        if not sel: return
        try:
            idx = int(sel.split('.')[0].strip()) - 1
            item = results_list[idx]
            if item.is_pass:
                lbl_chosen_status.config(text="[Kỹ thuật: ĐẠT TIÊU CHUẨN]", foreground='#047857')
            else:
                lbl_chosen_status.config(text="[Cảnh báo: Phương án KHÔNG ĐẠT]", foreground='#DC2626')
        except Exception:
            pass

    def on_tree_select(_event=None):
        sel = tree.selection()
        if not sel: return
        idx = int(sel[0]) - 1
        if 0 <= idx < len(cb_chosen['values']):
            cb_chosen.current(idx)
            update_status_label()

    tree.bind('<<TreeviewSelect>>', on_tree_select)
    cb_chosen.bind('<<ComboboxSelected>>', update_status_label)

    # =========================================================================
    # PHÊ DUYỆT & LƯU VÀO BẢNG TỔNG HỢP VÀ TỰ ĐỘNG TÍNH KHỐI LƯỢNG (BOQ)
    # =========================================================================
    def apply_and_save_to_summary():
        sel = cb_chosen.get()
        if not sel:
            messagebox.showwarning("Chưa chọn", "Vui lòng chọn một phương án trong danh sách.", parent=app)
            return

        idx = int(sel.split('.')[0].strip()) - 1
        item = results_list[idx]
        p = getattr(app, 'project', None)
        if not p: return

        if not item.is_pass:
            if not messagebox.askyesno("Cảnh báo", f"Phương án '{item.opt_name}' chưa đạt yêu cầu kỹ thuật.\nBạn vẫn muốn chọn phương án này?", parent=app):
                return

        try:
            length_val = float(var_section_len.get().replace(",", "."))
            if length_val <= 0: raise ValueError
        except Exception:
            length_val = 100.0
            var_section_len.set("100.0")

        # Lưu bản tính đã chọn; không ghi ngược vào nền chính hay xóa kết quả CDM.
        try:
            app.collect()
        except ValueError as exc:
            messagebox.showerror('Dữ liệu hiện tại', str(exc), parent=app)
            return
        if project_signature(app.project) != project_signature(item.source_project):
            messagebox.showwarning('Kết quả đã cũ',
                                   'Dữ liệu nền/địa chất đã thay đổi. Hãy tính lại phương án và cập nhật bảng.',
                                   parent=app)
            return
        payload = item.apply_payload.copy()
        p = deepcopy(item.source_project)

        # 2. Tự động tính toán khối lượng BOQ
        st_from = getattr(p, 'station_from', '')
        st_to = getattr(p, 'station_to', '')
        st_station = getattr(p, 'station', '')
        if st_from and st_to:
            station_display = f"{st_from} - {st_to}"
        elif st_station:
            station_display = st_station
        else:
            station_display = f"MCN_{len(app._saved_sections_data)+1}"

        record_tech = {
            'section_no': getattr(app, '_active_section_no', None),
            'station': station_display,
            'length': length_val,
            'h_design': p.h_design,
            'limit': item.limit_cm,
            'group': item.group_name,
            'opt_name': item.opt_name,
            'params': item.opt_params_desc,
            'residual': item.residual_cm,
            'status': "ĐẠT" if item.is_pass else "KHÔNG ĐẠT",
            'notes': var_note.get().strip(),
            'payload': payload,
            'project_snapshot': deepcopy(p),
        }

        boq_data = calculate_section_boq(record_tech, length_val, p)
        record_tech['boq'] = boq_data

        existing_idx = next((i for i, row in enumerate(app._saved_sections_data) if row['station'] == station_display), None)
        if existing_idx is not None:
            app._saved_sections_data[existing_idx] = record_tech
        else:
            app._saved_sections_data.append(record_tech)

        refresh_all_summary_trees()
        if hasattr(app, 'refresh_treatment_boq'):
            app.refresh_treatment_boq()

        lbl_applied_msg.config(text=f"✔ Đã lưu: {station_display} ➔ {item.opt_name}")
        messagebox.showinfo(
            "Đã lưu phương án và khối lượng",
            f"ĐÃ LƯU PHƯƠNG ÁN VÀ TÍNH KHỐI LƯỢNG (BOQ):\n\n"
            f"• Phân đoạn: {station_display} (Chiều dài L = {length_val:.1f} m)\n"
            f"• Phương án chọn: {item.opt_name}\n"
            f"• Thông số đã tính: {item.opt_params_desc}\n\n"
            f"Khối lượng chính bóc tách:\n"
            f" - Đào thay đất: {boq_data['v_excavation']:.1f} m³\n"
            f" - Cát đệm/thay: {boq_data['v_sand_fill']:.1f} m³\n"
            f" - Vải địa kỹ thuật: {boq_data['a_geotextile']:.1f} m²\n"
            f" - Bấc/cọc thoát nước: {boq_data['l_pvd']:.1f} m\n"
            f" - Cọc CDM: {boq_data['v_cdm']:.1f} m³\n"
            f" - Cọc tre/tràm: "
            f"{'tre theo 25 cọc/m²; cừ tràm cần nhập mật độ ở bảng KL' if payload.get('treatment_group') == 'mechanical' and (p.bamboo_depth or p.cajuput_depth) else 'không áp dụng'}\n\n"
            f"Đã cập nhật đồng bộ vào Bảng tổng hợp BOQ toàn tuyến.",
            parent=app
        )

    def refresh_all_summary_trees():
        tree_summary.delete(*tree_summary.get_children())
        tree_boq.delete(*tree_boq.get_children())

        tot_len = 0.0
        tot_exc = 0.0
        tot_sand = 0.0
        tot_geo = 0.0
        tot_pvd = 0.0
        tot_pile = 0
        tot_cdm = 0.0
        tot_sur = 0.0

        for i, rec in enumerate(app._saved_sections_data, 1):
            eval_tag = 'pass' if rec['status'] == "ĐẠT" else 'fail'
            row_tag = 'even' if i % 2 == 0 else 'odd'
            res_str = f"{rec['residual']:.2f}" if rec['residual'] < 900 else "---"

            tree_summary.insert('', 'end', iid=f"tech_{i}", tags=(eval_tag, row_tag), values=(
                i, rec['station'], f"{rec['length']:.1f}", f"{rec['h_design']:.2f}", f"{rec['limit']:.1f}",
                rec['group'], rec['opt_name'], rec['params'], res_str,
                rec['status'], rec['notes']
            ))

            boq = rec.get('boq', {})
            l_val = boq.get('length_m', rec.get('length', 100.0))
            v_exc = boq.get('v_excavation', 0.0)
            v_sand = boq.get('v_sand_fill', 0.0)
            a_geo = boq.get('a_geotextile', 0.0)
            l_pvd_val = boq.get('l_pvd', 0.0)
            n_pile_val = boq.get('n_piles', 0)
            v_cdm_val = boq.get('v_cdm', 0.0)
            v_sur_val = boq.get('v_surcharge', 0.0)

            tot_len += l_val
            tot_exc += v_exc
            tot_sand += v_sand
            tot_geo += a_geo
            tot_pvd += l_pvd_val
            tot_pile += n_pile_val
            tot_cdm += v_cdm_val
            tot_sur += v_sur_val

            tree_boq.insert('', 'end', iid=f"boq_{i}", tags=(row_tag,), values=(
                i, rec['station'], f"{l_val:.1f}", rec['opt_name'],
                f"{v_exc:.1f}" if v_exc > 0 else "-",
                f"{v_sand:.1f}" if v_sand > 0 else "-",
                f"{a_geo:.1f}" if a_geo > 0 else "-",
                f"{l_pvd_val:.1f}" if l_pvd_val > 0 else "-",
                f"{n_pile_val}" if n_pile_val > 0 else "-",
                f"{v_cdm_val:.1f}" if v_cdm_val > 0 else "-",
                f"{v_sur_val:.1f}" if v_sur_val > 0 else "-"
            ))

        if app._saved_sections_data:
            tree_boq.insert('', 'end', iid="boq_total", tags=('total',), values=(
                "TỔNG", f"{len(app._saved_sections_data)} đoạn", f"{tot_len:.1f}", "TOÀN TUYẾN",
                f"{tot_exc:.1f}", f"{tot_sand:.1f}", f"{tot_geo:.1f}", f"{tot_pvd:.1f}",
                f"{int(tot_pile)}", f"{tot_cdm:.1f}", f"{tot_sur:.1f}"
            ))

    def delete_selected_section():
        sel_tech = tree_summary.selection()
        sel_boq = tree_boq.selection()
        sel = sel_tech or sel_boq
        if not sel:
            messagebox.showwarning("Chọn dòng", "Vui lòng chọn một phân đoạn trong bảng để xóa.", parent=app)
            return

        item_id = sel[0]
        if item_id == "boq_total": return
        idx = int(item_id.split('_')[1]) - 1

        st_name = app._saved_sections_data[idx]['station']
        if messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc muốn xóa phân đoạn '{st_name}' khỏi bảng tổng hợp?", parent=app):
            app._saved_sections_data.pop(idx)
            refresh_all_summary_trees()

    def clear_all_sections():
        if not app._saved_sections_data: return
        if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn xóa toàn bộ danh sách các phân đoạn đã lưu?", parent=app):
            app._saved_sections_data.clear()
            refresh_all_summary_trees()

    def export_summary_tech_csv():
        if not app._saved_sections_data:
            messagebox.showwarning("Trống", "Chưa có phân đoạn nào được lưu.", parent=app)
            return
        dest = filedialog.asksaveasfilename(parent=app, defaultextension='.csv',
                                            filetypes=[('CSV Document', '*.csv')],
                                            initialfile='Bang_Tong_Hop_Phuong_An_Ky_Thuat.csv')
        if not dest: return
        try:
            with open(dest, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(sum_headers)
                for i, r in enumerate(app._saved_sections_data, 1):
                    res_val = f"{r['residual']:.2f}" if r['residual'] < 900 else "---"
                    w.writerow([
                        i, r['station'], f"{r['length']:.1f}", f"{r['h_design']:.2f}", f"{r['limit']:.1f}",
                        r['group'], r['opt_name'], r['params'], res_val,
                        r['status'], r['notes']
                    ])
            messagebox.showinfo("Thành công", f"Đã xuất Bảng giải pháp kỹ thuật:\n{dest}", parent=app)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e), parent=app)

    def export_summary_boq_csv():
        if not app._saved_sections_data:
            messagebox.showwarning("Trống", "Chưa có phân đoạn nào được lưu.", parent=app)
            return
        dest = filedialog.asksaveasfilename(parent=app, defaultextension='.csv',
                                            filetypes=[('CSV Document', '*.csv')],
                                            initialfile='Bang_Tong_Hop_Khoi_Luong_BOQ.csv')
        if not dest: return
        try:
            with open(dest, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow(boq_headers)
                tot_len = tot_exc = tot_sand = tot_geo = tot_pvd = tot_pile = tot_cdm = tot_sur = 0.0

                for i, r in enumerate(app._saved_sections_data, 1):
                    boq = r.get('boq', {})
                    l_val = boq.get('length_m', r.get('length', 100.0))
                    v_exc = boq.get('v_excavation', 0.0)
                    v_sand = boq.get('v_sand_fill', 0.0)
                    a_geo = boq.get('a_geotextile', 0.0)
                    l_pvd_val = boq.get('l_pvd', 0.0)
                    n_pile_val = boq.get('n_piles', 0)
                    v_cdm_val = boq.get('v_cdm', 0.0)
                    v_sur_val = boq.get('v_surcharge', 0.0)

                    tot_len += l_val
                    tot_exc += v_exc
                    tot_sand += v_sand
                    tot_geo += a_geo
                    tot_pvd += l_pvd_val
                    tot_pile += n_pile_val
                    tot_cdm += v_cdm_val
                    tot_sur += v_sur_val

                    w.writerow([
                        i, r['station'], f"{l_val:.1f}", r['opt_name'],
                        f"{v_exc:.1f}" if v_exc > 0 else "-",
                        f"{v_sand:.1f}" if v_sand > 0 else "-",
                        f"{a_geo:.1f}" if a_geo > 0 else "-",
                        f"{l_pvd_val:.1f}" if l_pvd_val > 0 else "-",
                        f"{n_pile_val}" if n_pile_val > 0 else "-",
                        f"{v_cdm_val:.1f}" if v_cdm_val > 0 else "-",
                        f"{v_sur_val:.1f}" if v_sur_val > 0 else "-"
                    ])

                w.writerow([
                    "TỔNG", f"{len(app._saved_sections_data)} đoạn", f"{tot_len:.1f}", "TOÀN TUYẾN",
                    f"{tot_exc:.1f}", f"{tot_sand:.1f}", f"{tot_geo:.1f}", f"{tot_pvd:.1f}",
                    f"{int(tot_pile)}", f"{tot_cdm:.1f}", f"{tot_sur:.1f}"
                ])

            messagebox.showinfo("Thành công", f"Đã xuất Bảng tổng hợp khối lượng (BOQ):\n{dest}", parent=app)
        except Exception as e:
            messagebox.showerror("Lỗi", str(e), parent=app)

    btn_run_all.config(command=lambda: app.run_processing('Lựa chọn phương án', execute_auto_calculations))
    btn_apply.config(command=apply_and_save_to_summary)
    btn_export_tech.config(command=export_summary_tech_csv)
    btn_export_boq.config(command=export_summary_boq_csv)
    btn_del_section.config(command=delete_selected_section)
    btn_clear_all.config(command=clear_all_sections)

    def on_view_mapped(_event=None):
        sync_bar()
        refresh_all_summary_trees()
        if not results_list:
            execute_auto_calculations()

    parent.bind('<Map>', on_view_mapped, add='+')
