"""Không gian riêng cho phương pháp xử lý nền bằng CDM (Xi măng đất).

- Phần 1 hiển thị thông số nền đắp: B, m, Bxl, Htk, Hbl, Htt, gamma đắp, Hkcad (Chỉ đọc, link từ Dự án).
- Bổ sung ô Tải trọng đắp qT cạnh Hoạt tải xe qH trong Mục 3 (tự động tính theo gamma_dap * H).
- Chiều cao tính toán phân biệt theo loại cọc:
  + Cọc chống: tính theo Htk + Hkcad (không cộng bù lún).
  + Cọc treo:   tính theo Htt = Hkcad + Htk + Hbl (có cộng lớp KCAĐ và bù lún).
- Khoảng cách cọc s làm tròn 1 chữ số sau dấu phẩy (bước 0.1m).
- Bố trí ô Cường độ cọc (qu28/qu90) rõ ràng, trực quan, không bị đè cột.
- Kiểm toán cường độ cọc:
  + Chọn qu28: lấy luôn qu28 để kiểm toán ([qu] = qu28 / Fs).
  + Chọn qu90: quy đổi về kiểm toán ([qu] = (qu90 / n) / Fs).
- Công thức ứng suất đất nền dùng chung cho cả 2 trường hợp:
  sigma_s = (gamma*H + q - sigma_p * ap) / (1 - ap), tải KHÔNG nhân hệ số vượt tải, có cộng q (cả cọc chống và cọc treo);
    sigma'_v vẫn giữ nguyên cho sigma_p.
- Dung trọng đất nền gamma_sub tính Rtc: tự động lấy từ lớp đất chọn, nếu dưới MNN tự động trừ 1.0 T/m3.
- Tải trọng q móng: tự động tính q = gamma_dao * hm với hm nhập tay.
- Tối ưu hóa quét lưới (Lc, s, n_layer):
  + Cọc treo: thỏa lún dư <= giới hạn, ứng suất và vải địa.
  + Cọc chống: kéo dài cọc đến khi KHÔNG còn lún dư dưới mũi cọc (Sc <= END_BEARING_RESIDUAL_TOL_CM), đồng thời thỏa ứng suất và vải địa.
"""
from __future__ import annotations

import math
from copy import deepcopy
import tkinter as tk
from tkinter import ttk, messagebox

from utils import ScrollableFrame, number
from ui_theme import COLORS
from model import pressure, effective_overburden, void_ratio
from ui_i18n import english as _english_ui

# Cọc chống: coi là 'không còn lún dư dưới mũi cọc' khi tổng Sc các lớp dưới mũi <= ngưỡng này (cm)
END_BEARING_RESIDUAL_TOL_CM = 0.01


def fabric_strength_at_allowable_strain(geo):
    """Cường độ bảo thủ tại độ giãn dài cho phép, kN/m đầu vào; đổi sang T/m để kiểm toán."""
    if geo.get('kind') == 'Lưới địa kỹ thuật':
        direct = float(geo['T_char_kn'])
        if not math.isfinite(direct) or direct <= 0 or float(geo['eps']) <= 0:
            raise ValueError('Lưới địa: Tchar và độ giãn dài cho phép phải > 0.')
        return direct, direct / 9.80665
    tmax = float(geo['Tmax'])
    epsmax = float(geo['eps_max'])
    allowable = float(geo['eps'])
    if not math.isfinite(tmax) or not math.isfinite(epsmax) or not math.isfinite(allowable) or tmax <= 0 or allowable <= 0 or epsmax < allowable:
        raise ValueError('Tmax phải > 0 kN/m; 0 < độ giãn dài cho phép ε ≤ độ giãn dài tối đa εmax.')
    t6 = 0.9 * allowable * tmax / epsmax
    return t6, t6 / 9.80665


def _get_language(widget):
    """Lấy ngôn ngữ UI hiện tại từ widget cha."""
    try:
        top = widget.winfo_toplevel()
        if hasattr(top, 'ui_language'):
            return 'en' if top.ui_language.get() == 'English' else 'vi'
    except (tk.TclError, AttributeError):
        pass
    return 'vi'


def _L(text, language='vi'):
    """Dịch text nếu đang ở chế độ English."""
    return _english_ui(text) if language == 'en' else text


def get_project_embankment_params(project) -> dict:
    """Trích xuất an toàn các thông số nền đắp từ project."""
    if not project:
        return {
            'B': 10.0, 'm': 1.5, 'Bxl': 19.0,
            'Htk': 3.0, 'Hbl': 0.0, 'Hkcad': 0.6,
            'gamma_fill': 1.8, 'qh': 1.5
        }

    Htk = getattr(project, 'h_design', 3.0)
    if Htk <= 0:
        Htk = 3.0
    m_slope = getattr(project, 'slope_m', 1.5)
    if m_slope <= 0:
        m_slope = 1.5
    crest_half = getattr(project, 'crest_half_width', 5.0)
    B_val = crest_half * 2.0 if crest_half > 0 else getattr(project, 'b_crest', 10.0)
    Bxl_val = 2.0 * Htk * m_slope + B_val

    Hbl = getattr(project, 'h_bl', getattr(project, 'h_settlement', getattr(project, 'bu_lun', 0.0)))
    Hkcad = getattr(project, 'h_kcad', getattr(project, 'pavement_h', 0.6))
    gamma_fill = getattr(project, 'gamma_fill', 1.8)
    qh = getattr(project, 'qh', getattr(project, 'surcharge_q', 1.5))

    return {
        'B': B_val,
        'm': m_slope,
        'Bxl': Bxl_val,
        'Htk': Htk,
        'Hbl': Hbl,
        'Hkcad': Hkcad,
        'gamma_fill': gamma_fill,
        'qh': qh
    }


def get_abd_factors(phi_deg: float) -> tuple[float, float, float]:
    """Nội suy tuyến tính các hệ số D, B, A(1/4) dựa trên góc ma sát phi."""
    if phi_deg <= 0.0:
        return 3.14, 1.0, 0.0

    table = [
        (0, 3.14, 1.00, 0.00), (2, 3.32, 1.12, 0.03), (4, 3.51, 1.25, 0.06),
        (6, 3.71, 1.39, 0.10), (8, 3.93, 1.55, 0.14), (10, 4.17, 1.73, 0.18),
        (12, 4.42, 1.94, 0.23), (14, 4.69, 2.17, 0.29), (16, 5.00, 2.43, 0.36),
        (18, 5.31, 2.72, 0.43), (20, 5.66, 3.06, 0.51), (22, 6.04, 3.44, 0.61),
        (24, 6.45, 3.87, 0.72), (26, 6.90, 4.37, 0.84), (28, 7.40, 4.93, 0.98),
        (30, 7.95, 5.59, 1.15), (32, 8.55, 6.35, 1.34), (34, 9.21, 7.21, 1.55),
        (36, 9.98, 8.25, 1.81), (38, 10.80, 9.44, 2.11), (40, 11.73, 10.84, 2.46),
        (42, 12.77, 12.50, 2.87), (44, 13.96, 14.48, 3.37)
    ]

    if phi_deg >= 44:
        return table[-1][1], table[-1][2], table[-1][3]

    for i in range(len(table) - 1):
        p1, d1, b1, a1 = table[i]
        p2, d2, b2, a2 = table[i+1]
        if p1 <= phi_deg <= p2:
            ratio = (phi_deg - p1) / (p2 - p1)
            D_val = d1 + ratio * (d2 - d1)
            B_val = b1 + ratio * (b2 - b1)
            A_val = a1 + ratio * (a2 - a1)
            return D_val, B_val, A_val

    return 3.14, 1.0, 0.0


def _get_e0_at_zero(s):
    """Lấy e0 từ biểu đồ nén lún tại P=0."""
    for pressure_val, void_val in zip(s.ep, s.e):
        if abs(pressure_val) < 1e-9 and void_val > 0:
            return void_val
    return s.e0 if s.e0 > 0 else 0.0


def bind_mousewheel(widget):
    """Tích hợp cuộn chuột mượt mà cho bảng (Treeview)."""
    def _on_mousewheel(event):
        widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
    widget.bind("<MouseWheel>", _on_mousewheel)
    widget.bind("<Button-4>", lambda e: widget.yview_scroll(-1, "units"))
    widget.bind("<Button-5>", lambda e: widget.yview_scroll(1, "units"))


def calculate_cdm_all(project, params: dict, stress_params: dict,
                      subgrade_params: dict, geo_params: dict,
                      use_geo: bool) -> dict:
    """Thuật toán tính toán tổng hợp Lún, Ứng suất và Vải địa CDM."""
    if project is None or not project.soils:
        raise ValueError("Chưa có số liệu dự án và địa chất. Vui lòng khai báo tại Bước 1 đến 3.")

    # =========================================================================
    # 1. THÔNG SỐ NỀN ĐẮP VÀ CHIỀU CAO TÍNH TOÁN (H_cdm)
    # =========================================================================
    emb_params = get_project_embankment_params(project)
    H_tk = emb_params['Htk']
    H_bl = emb_params['Hbl']
    b_val = emb_params['Bxl']
    gamma_fill = emb_params['gamma_fill']

    pile_type = params.get('pile_type', 'Cọc treo (Friction pile)')
    is_end_bearing = ('Cọc chống' in pile_type)

    # Htt = Hkcad + Htk + Hbl ; Cọc chống lấy theo Htk + Hkcad, Cọc treo lấy theo Htt
    H_kcad = emb_params['Hkcad']
    H_tt = H_kcad + H_tk + H_bl
    H_cdm = (H_tk + H_kcad) if is_end_bearing else H_tt
    if H_cdm <= 0:
        H_cdm = 3.0

    # =========================================================================
    # 2. THÔNG SỐ CƠ BẢN VÀ NỀN TƯƠNG ĐƯƠNG
    # =========================================================================
    D_pile = params['D']
    s = round(params['s'], 1)
    Lc = params['Lc']
    qu_type = params['qu_type']
    qu_val = params['qu_val']
    Ec = params['Ec']
    pattern = params['pattern']
    n_fac = stress_params['n']

    if D_pile <= 0 or s <= 0 or Lc <= 0:
        raise ValueError("Đường kính (D), khoảng cách (s) và chiều dài cọc (Lc) phải > 0.")
    if D_pile >= s:
        raise ValueError("Khoảng cách cọc (s) phải lớn hơn đường kính cọc (D).")

    # Kiểm toán qu
    if qu_type == 'qu28':
        qu_check = qu_val
        qu28 = qu_val
        qu90 = qu_val * n_fac
    else:
        qu90 = qu_val
        qu28 = qu_val / n_fac if n_fac > 0 else qu_val
        qu_check = qu28

    Ac = math.pi * (D_pile ** 2) / 4.0
    A = (s ** 2) if pattern == 'Lưới vuông' else (0.866025 * (s ** 2))
    ap = Ac / A
    Suc = qu28 / 2.0

    Es_total, Su_total, L_effective = 0.0, 0.0, 0.0
    current_depth = 0.0
    c_under_pile = 0.0

    for soil in project.soils:
        if current_depth + soil.thickness > Lc and c_under_pile == 0.0:
            c_under_pile = getattr(soil, 'co', 0.0) if getattr(soil, 'category', '') == "Đất dính" else 0.0

        if current_depth >= Lc:
            break

        layer_in_pile = min(soil.thickness, Lc - current_depth)
        if layer_in_pile <= 0:
            continue

        if getattr(soil, 'category', '') == "Đất dính":
            Su_layer = getattr(soil, 'co', 0.0)
            Es_layer = 250.0 * Su_layer
        else:
            Su_layer = 0.0
            Es_layer = 100.0 * getattr(soil, 'spt_n', 0.0)

        Es_total += Es_layer * layer_in_pile
        Su_total += Su_layer * layer_in_pile
        L_effective += layer_in_pile
        current_depth += soil.thickness

    Es_avg = Es_total / L_effective if L_effective > 0 else 150.0
    Su_avg = Su_total / L_effective if L_effective > 0 else 1.0

    E_td = ap * Ec + (1 - ap) * Es_avg
    Su_td = ap * Suc + (1 - ap) * Su_avg

    # =========================================================================
    # 3. KIỂM TOÁN LÚN CDM
    # =========================================================================
    rows_lun = []
    dz = getattr(project, 'sublayer', 1.0)
    if dz <= 0:
        dz = 1.0

    z_cdm = Lc / 2.0
    # TCVN 9403:2012, Phụ lục C: q là tải truyền lên khối, H = Lc.
    dp_cdm = gamma_fill * H_cdm + stress_params['qH']
    si_cdm = (dp_cdm * Lc / E_td) * 100.0 if E_td > 0 else 0.0
    e0_cdm = _get_e0_at_zero(project.soils[0]) if project.soils else 0.0

    rows_lun.append({
        'name': f'CDM ({pile_type.split()[0]})', 'thick': Lc, 'bot_z': Lc,
        'gamma': gamma_fill, 'spt': '', 'e0': f"{e0_cdm:.3f}", 'cc': '',
        'cr': '', 'pc': '', 'ap': f"{ap:.2f}", 'dp': dp_cdm,
        'su_soil': Su_avg, 'su_td': Su_td, 'e_soil': Es_avg, 'e_td': E_td,
        'si': si_cdm, 'sc': 0.0
    })

    current_depth = 0.0
    for i, soil in enumerate([] if is_end_bearing else project.soils):
        bot_depth = current_depth + soil.thickness
        if bot_depth <= Lc:
            current_depth = bot_depth
            continue

        start_z = max(current_depth, Lc)
        remain_h = bot_depth - start_z

        num_sub = math.ceil(remain_h / dz)
        cur_top = start_z

        for j in range(num_sub):
            h_step = min(dz, bot_depth - cur_top)
            z_mid = cur_top + h_step / 2.0

            po = effective_overburden(project, z_mid)
            dp = pressure(project, z_mid, 0.0)
            pc = max(getattr(soil, 'pc', 0.0), po) if getattr(soil, 'pc', 0.0) > 0 else po

            su_layer = getattr(soil, 'co', 0.0) if getattr(soil, 'category', '') == 'Đất dính' else 0.0
            e_layer = ((250.0 * su_layer)
                       if getattr(soil, 'category', '') == 'Đất dính'
                       else (100.0 * getattr(soil, 'spt_n', 0.0)))

            si_layer = (dp * h_step / e_layer) * 100.0 if e_layer > 0 else 0.0
            sc_layer = 0.0
            e0_val = 0.0
            if getattr(soil, 'category', '') == 'Đất dính':
                method = getattr(project, 'method', 'Cc/Cs/Pc')
                e0_val = (getattr(soil, 'e0', 0.0)
                          if method == "Mv–logP" else void_ratio(soil, po))

                if getattr(soil, 'cc', 0.0) > 0 or getattr(soil, 'cs', 0.0) > 0:
                    if getattr(soil, 'state', '') == 'Cố kết thường' or po >= pc:
                        strain = soil.cc * math.log10((po + dp) / max(po, 1e-9)) / (1 + e0_val)
                    elif po + dp <= pc:
                        strain = soil.cs * math.log10((po + dp) / max(po, 1e-9)) / (1 + e0_val)
                    else:
                        strain = (soil.cs * math.log10(pc / max(po, 1e-9))
                                  + soil.cc * math.log10((po + dp) / max(pc, 1e-9))) / (1 + e0_val)
                    sc_layer = strain * h_step * 100.0

            sub_name = (f"{soil.name or f'Lớp {i+1}'} ({j+1})"
                        if num_sub > 1 else (soil.name or f"Lớp {i+1}"))

            rows_lun.append({
                'name': sub_name, 'thick': h_step, 'bot_z': cur_top + h_step,
                'gamma': soil.gamma,
                'spt': (getattr(soil, 'spt_n', '')
                        if getattr(soil, 'category', '') == 'Đất rời' else ''),
                'e0': f"{e0_val:.3f}" if getattr(soil, 'category', '') == 'Đất dính' else '',
                'cc': (getattr(soil, 'cc', '')
                       if getattr(soil, 'category', '') == 'Đất dính' else ''),
                'cr': (getattr(soil, 'cs', '')
                       if getattr(soil, 'category', '') == 'Đất dính' else ''),
                'pc': pc if getattr(soil, 'category', '') == 'Đất dính' else '',
                'ap': '', 'dp': dp,
                'su_soil': su_layer if su_layer > 0 else '',
                'su_td': '', 'e_soil': e_layer, 'e_td': '',
                'si': 0.2 * sc_layer, 'sc': sc_layer
            })
            cur_top += h_step
        current_depth = bot_depth

    s1_cm = si_cdm
    sc2_cm = 0.0 if is_end_bearing else sum(r['sc'] for r in rows_lun[1:])
    s2_cm = sc2_cm
    sum_si = s1_cm if is_end_bearing else s1_cm + 0.2*s2_cm
    sum_sc = sc2_cm

    # =========================================================================
    # 4. TÍNH TOÁN ỨNG SUẤT ĐẦU CỌC & ĐẤT NỀN
    # =========================================================================
    Fs = stress_params['Fs']
    qH = stress_params['qH']
    f_fs = stress_params['f_fs']
    f_q = stress_params['f_q']

    qT = stress_params.get('qT', gamma_fill * H_cdm)
    if qT <= 0:
        qT = gamma_fill * H_cdm

    m = subgrade_params['m']
    gamma_sub = subgrade_params['gamma_sub']
    q_mong = subgrade_params['q_mong']
    c_under_pile = subgrade_params['c_val']
    phi_mong = subgrade_params['phi_val']

    D_fac, B_fac, A_fac = get_abd_factors(phi_mong)
    a = D_pile

    sigma_v_prime = f_fs * qT + f_q * qH

    if is_end_bearing:
        Cc = max(0.0, 1.95 * (H_cdm / a) - 0.18)
        cc_formula = f"1.95*(H/a) - 0.18 (Cọc chống, H = Htk + Hkcad = {H_cdm:.2f}m)"
    else:
        Cc = max(0.0, 1.50 * (H_cdm / a) - 0.07)
        cc_formula = f"1.50*(Htt/a) - 0.07 (Cọc treo, Htt = {H_cdm:.2f}m)"

    # --- A. ỨNG SUẤT ĐẦU CỌC ---
    sigma_p = sigma_v_prime * ((Cc * a) / H_cdm) ** 2

    # --- B. ỨNG SUẤT ĐẤT NỀN ---
    sigma_v = gamma_fill * H_cdm + qH
    sigma_s_formula = "(γH + q − σ_p·ap)/(1−ap)"
    sigma_s_calc = (sigma_v - sigma_p * ap) / (1.0 - ap) if ap < 1.0 else 0.0
    sigma_s = max(0.0, sigma_s_calc)

    # =========================================================================
    # 5. KIỂM TOÁN VẢI ĐỊA KỸ THUẬT GIA CƯỜNG ĐẦU CỌC (BS 8006)
    # =========================================================================
    geo = {}
    if use_geo:
        eps = geo_params['eps'] / 100.0
        phi_rad = math.radians(geo_params['phi_dap'])
        t6, T_char = fabric_strength_at_allowable_strain(geo_params) if 'Tmax' in geo_params else (geo_params['T_char'] * 9.80665, geo_params['T_char'])
        n_layer = geo_params['n_layer']
        fm = geo_params['fm11'] * geo_params['fm12'] * geo_params['fm21'] * geo_params['fm22']
        fn = geo_params['fn']

        clear_s = s - a
        den = (s**2 - a**2) if (s**2 - a**2) != 0 else 0.0001

        stress_ratio = (Cc * a / H_cdm) ** 2
        bracket = s**2 - (a**2) * stress_ratio

        if H_cdm > 1.4 * clear_s:
            WT = (1.4 * s * f_fs * gamma_fill * clear_s / den) * bracket
        else:
            WT = (s * sigma_v_prime / den) * bracket

        WT_min = 0.15 * s * sigma_v_prime
        WT = max(WT, WT_min)

        Trp = (WT * clear_s / (2 * a)) * math.sqrt(1 + 1 / (6 * eps)) if (eps > 0 and a > 0) else 0
        Ka = math.tan(math.radians(45) - phi_rad / 2.0) ** 2
        Tds = 0.5 * Ka * (f_fs * gamma_fill * H_cdm + 2 * f_q * qH) * H_cdm

        Tr = Trp + Tds
        Td = (T_char * n_layer) / fm if fm > 0 else 0
        Td_fn = Td / fn if fn > 0 else 0

        geo = {
            'T_allow_kN_m': t6, 'T_char': T_char, 'WT': WT, 'WT_min': WT_min, 'Trp': Trp, 'Ka': Ka, 'Tds': Tds,
            'Tr': Tr, 'fm': fm, 'Td': Td, 'Td_fn': Td_fn, 'n_layer': n_layer
        }

    qu_allow = qu_check / Fs if Fs > 0 else 0
    Rtc = m * (A_fac * gamma_sub * b_val + B_fac * q_mong + D_fac * c_under_pile)
    qu_tt1 = (qT + qH) / ap if ap > 0 else 0

    return {
        'pile_type': pile_type,
        'H_tk': H_tk,
        'H_kcad': H_kcad,
        'H_bl': H_bl,
        'H_tt': H_tt,
        'H_cdm': H_cdm,
        'gamma_fill': gamma_fill,
        'ap': ap, 'c_under_pile': c_under_pile, 'phi_mong': phi_mong,
        'D_fac': D_fac, 'B_fac': B_fac, 'A_fac': A_fac, 'b_val': b_val,
        'rows_lun': rows_lun, 'sum_si': sum_si, 'sum_sc': sum_sc,
        'S1_cm': s1_cm, 'S2_cm': s2_cm, 'Sc2_cm': sc2_cm, 'q_cdm': dp_cdm,
        'total_s': sum_si + sum_sc,
        'use_geo': use_geo,
        'stress': {
            'qT': qT, 'qu_type': qu_type, 'qu_check': qu_check, 'qu90': qu90,
            'qu_allow': qu_allow, 'qu_tt1': qu_tt1,
            'Cc': Cc, 'cc_formula': cc_formula,
            'sigma_v_prime': sigma_v_prime,
            'sigma_v': sigma_v, 'sigma_s_formula': sigma_s_formula,
            'sigma_p': sigma_p,
            'sigma_s': sigma_s,
            'Rtc': Rtc
        },
        'geo': geo
    }


def optimize_cdm_dimensions(
    project,
    base_params: dict,
    stress_params: dict,
    subgrade_params: dict,
    geo_params: dict,
    use_geo: bool,
    s_range: tuple[float, float, float] = (1.1, 2.5, 0.1),
    lc_range: tuple[float, float, float] = (3.0, 20.0, 0.5),
    n_layer_range: tuple[int, int] = (1, 4),
    settlement_limit_cm: float = 30.0
) -> dict | None:
    """Thuật toán quét lưới thử dần tìm cặp (Lc, s, n_layer) tối ưu nhất."""
    if project is None or not project.soils:
        raise ValueError("Chưa có số liệu dự án và địa chất.")
    if 'Cọc chống' in base_params.get('pile_type', ''):
        settlement_limit_cm = END_BEARING_RESIDUAL_TOL_CM

    s_min, s_max, s_step = s_range
    lc_min, lc_max, lc_step = lc_range
    if any(not math.isfinite(v) for v in (*s_range, *lc_range)) or s_step <= 0 or lc_step <= 0:
        raise ValueError('Bước tối ưu s và Lc phải là số dương hữu hạn.')
    if s_min <= 0 or lc_min <= 0 or s_max < s_min or lc_max < lc_min:
        raise ValueError('Phạm vi tìm kiếm tối ưu không hợp lệ.')
    n_min, n_max = n_layer_range
    D_pile = base_params['D']

    s_min = max(s_min, round(D_pile + 0.1, 1))

    best_solution = None
    min_cost_index = float('inf')

    s_candidates = []
    cur_s = s_min
    while cur_s <= s_max + 1e-5:
        s_candidates.append(round(cur_s, 1))
        cur_s += s_step

    lc_candidates = []
    cur_lc = lc_min
    while cur_lc <= lc_max + 1e-5:
        lc_candidates.append(round(cur_lc, 2))
        cur_lc += lc_step

    for s_val in s_candidates:
        for lc_val in lc_candidates:
            n_layers_to_try = range(n_min, n_max + 1) if use_geo else [1]

            for n_lay in n_layers_to_try:
                trial_params = base_params.copy()
                trial_params['s'] = s_val
                trial_params['Lc'] = lc_val

                trial_geo_params = geo_params.copy()
                trial_geo_params['n_layer'] = n_lay

                try:
                    res = calculate_cdm_all(
                        project, trial_params, stress_params,
                        subgrade_params, trial_geo_params, use_geo
                    )
                except Exception:
                    continue

                if res['sum_sc'] > settlement_limit_cm:
                    continue

                str_res = res['stress']
                if str_res['sigma_p'] > str_res['qu_allow']:
                    continue
                if str_res['qu_tt1'] > str_res['qu_allow']:
                    continue
                if str_res['sigma_s'] > str_res['Rtc']:
                    continue

                if use_geo and res.get('geo'):
                    geo_res = res['geo']
                    if geo_res['Tr'] > geo_res['Td_fn']:
                        continue

                ap_val = res['ap']
                cost_index = ap_val * lc_val + (0.005 * n_lay if use_geo else 0.0)

                if cost_index < min_cost_index:
                    min_cost_index = cost_index
                    best_solution = {
                        's': s_val,
                        'Lc': lc_val,
                        'n_layer': n_lay,
                        'ap': ap_val,
                        'cost_index': cost_index,
                        'res': res
                    }
                break

    return best_solution


def _build_tcvn_bs_view(parent: tk.Misc) -> None:
    """Dựng giao diện phương pháp Trộn sâu CDM."""
    app = parent.winfo_toplevel()
    language = _get_language(parent)
    L = lambda s: _english_ui(s) if language == 'en' else s

    scroll_frame = ScrollableFrame(parent)
    scroll_frame.pack(fill='both', expand=True)
    inner = scroll_frame.scrollable_frame

    header = tk.Frame(inner, bg=COLORS['background'])
    header.pack(fill='x', pady=(4, 6), padx=10)
    tk.Label(header,
             text=L("THIẾT KẾ XỬ LÝ NỀN BẰNG CỌC XI MĂNG ĐẤT (CDM) - BS 8006 & TCVN 9906"),
             bg=COLORS['background'], fg=COLORS['nav'],
             font=('Times New Roman', 12, 'bold')).pack(anchor='w')

    input_frame = tk.Frame(inner, bg=COLORS['background'])
    input_frame.pack(fill='x', padx=10)

    def add_field(parent_frame, row, col, label, var, width=11):
        ttk.Label(parent_frame, text=label).grid(
            row=row, column=col*2, sticky='w',
            padx=(10 if col > 0 else 0, 4), pady=3)
        entry = ttk.Entry(parent_frame, textvariable=var, width=width)
        entry.grid(row=row, column=col*2+1, sticky='w', pady=3)
        return entry

    def add_readonly_field(parent_frame, row, col, label, var, width=11):
        ttk.Label(parent_frame, text=label).grid(
            row=row, column=col*2, sticky='w',
            padx=(10 if col > 0 else 0, 4), pady=3)
        entry = ttk.Entry(parent_frame, textvariable=var, width=width,
                          state='readonly')
        entry.grid(row=row, column=col*2+1, sticky='w', pady=3)
        return entry

    # =========================================================================
    # 1. THÔNG SỐ NỀN ĐẮP (LIÊN KẾT TRỰC TIẾP - CHỈ ĐỌC)
    # =========================================================================
    box_emb = ttk.LabelFrame(
        input_frame,
        text=L("1. Thông số tính toán nền đắp (Liên kết từ Dự án - Chỉ đọc)"),
        padding=8)
    box_emb.pack(fill='x', pady=(0, 6))

    vars_emb = {
        'B': tk.StringVar(value='10.00'),
        'm': tk.StringVar(value='1.50'),
        'Bxl': tk.StringVar(value='19.00'),
        'Hkcad': tk.StringVar(value='0.60'),
        'Htk': tk.StringVar(value='3.00'),
        'Hbl': tk.StringVar(value='0.00'),
        'Htt': tk.StringVar(value='3.00'),
        'gamma_fill': tk.StringVar(value='1.80')
    }

    add_readonly_field(box_emb, 0, 0, L("Bề rộng đỉnh B (m):"), vars_emb['B'], width=9)
    add_readonly_field(box_emb, 0, 1, L("Mái dốc đắp m:"), vars_emb['m'], width=9)
    add_readonly_field(box_emb, 0, 2, L("Bề rộng đáy Bxl (m):"), vars_emb['Bxl'], width=9)
    add_readonly_field(box_emb, 0, 3, L("Chiều dày H_kcad (m):"), vars_emb['Hkcad'], width=9)

    add_readonly_field(box_emb, 1, 0, L("Chiều cao Htk (m):"), vars_emb['Htk'], width=9)
    add_readonly_field(box_emb, 1, 1, L("Bù lún H_bl (m):"), vars_emb['Hbl'], width=9)
    add_readonly_field(box_emb, 1, 2, L("Chiều cao tính Htt (m):"), vars_emb['Htt'], width=9)
    add_readonly_field(box_emb, 1, 3, L("γ đắp (T/m³):"), vars_emb['gamma_fill'], width=9)

    btn_calc_hbl = ttk.Button(box_emb, text=L('Tính chiều cao bù lún'),
                              style='Accent.TButton')
    btn_calc_hbl.grid(row=2, column=0, columnspan=2, sticky='w', pady=(6, 2))

    lbl_htt_note = ttk.Label(
        box_emb,
        text=L("(*) Cọc treo: H_tt = H_kcad + H_tk + H_bl | Cọc chống: H_tk + H_kcad"),
        font=('Times New Roman', 9, 'italic'), foreground='#0369A1')
    lbl_htt_note.grid(row=2, column=2, columnspan=6, sticky='w',
                      padx=10, pady=(6, 2))

    # =========================================================================
    # 2. THÔNG SỐ CỌC CDM
    # =========================================================================
    box_cdm = ttk.LabelFrame(input_frame, text=L("2. Thông số cọc CDM"), padding=8)
    box_cdm.pack(fill='x', pady=(0, 6))

    vars_cdm = {
        'D': tk.StringVar(value='0.80'), 's': tk.StringVar(value='1.5'),
        'Lc': tk.StringVar(value='8.00'),
        'qu_type': tk.StringVar(value='qu28'), 'qu_val': tk.StringVar(value='70.00'),
        'Ec': tk.StringVar(value='14000.00'), 'pattern': tk.StringVar(value='Lưới vuông'),
        'pile_type': tk.StringVar(value='Cọc treo (Friction pile)')
    }

    add_field(box_cdm, 0, 0, L("Đường kính cọc D (m):"), vars_cdm['D'])
    add_field(box_cdm, 0, 1, L("Khoảng cách cọc s (m):"), vars_cdm['s'])
    add_field(box_cdm, 0, 2, L("Chiều dài cọc Lc (m):"), vars_cdm['Lc'])

    ttk.Label(box_cdm, text=L("Loại cọc (BS8006):")).grid(
        row=2, column=0, sticky='w', padx=(0, 4), pady=3)
    cb_pile_type = ttk.Combobox(
        box_cdm, textvariable=vars_cdm['pile_type'],
        values=('Cọc treo (Friction pile)', 'Cọc chống (End-bearing)'),
        state='readonly', width=22
    )
    cb_pile_type.grid(row=2, column=1, sticky='w', pady=3)

    ttk.Label(box_cdm, text=L("Sơ đồ bố trí cọc:")).grid(
        row=1, column=0, sticky='w', pady=3)
    cb_pattern = ttk.Combobox(
        box_cdm, textvariable=vars_cdm['pattern'],
        values=('Lưới vuông', 'Lưới tam giác'),
        state='readonly', width=9)
    cb_pattern.grid(row=1, column=1, sticky='w', pady=3)

    # Cụm Cường độ cọc CDM
    f_qu = ttk.Frame(box_cdm)
    f_qu.grid(row=1, column=2, columnspan=2, sticky='w', padx=(10, 4), pady=3)
    ttk.Label(f_qu, text=L("Cường độ:")).pack(side='left', padx=(0, 4))
    cb_qu = ttk.Combobox(f_qu, textvariable=vars_cdm['qu_type'],
                         values=('qu28', 'qu90'), state='readonly', width=6)
    cb_qu.pack(side='left', padx=(0, 2))
    ent_qu = ttk.Entry(f_qu, textvariable=vars_cdm['qu_val'], width=8)
    ent_qu.pack(side='left', padx=2)
    ttk.Label(f_qu, text="(T/m²)").pack(side='left', padx=2)

    ttk.Label(box_cdm, text=L("Mô đun đàn hồi Ec (T/m²):")).grid(
        row=1, column=4, sticky='w', padx=(10, 4), pady=3)
    ttk.Entry(box_cdm, textvariable=vars_cdm['Ec'], width=11).grid(
        row=1, column=5, sticky='w', pady=3)

    # =========================================================================
    # 3. TẢI TRỌNG TÍNH TOÁN & HỆ SỐ VƯỢT TẢI
    # =========================================================================
    f_mid = ttk.Frame(input_frame)
    f_mid.pack(fill='x', pady=2)

    box_stress = ttk.LabelFrame(
        f_mid, text=L("3. Tải trọng tính toán & Hệ số vượt tải"), padding=8)
    box_stress.pack(fill='x')

    vars_stress = {
        'n': tk.StringVar(value='1.43'), 'Fs': tk.StringVar(value='1.2'),
        'qT': tk.StringVar(value='5.40'), 'qH': tk.StringVar(value='1.50'),
        'f_fs': tk.StringVar(value='1.30'), 'f_q': tk.StringVar(value='1.30')
    }

    ent_n = add_field(box_stress, 0, 0,
                      L("Hệ số quy đổi n (28->90 ngày):"), vars_stress['n'])

    def on_qu_change(*args):
        if vars_cdm['qu_type'].get() == 'qu28':
            ent_n.config(state='disabled')
        else:
            ent_n.config(state='normal')
    vars_cdm['qu_type'].trace_add('write', on_qu_change)
    on_qu_change()

    add_field(box_stress, 0, 1, L("Hệ số an toàn Fs:"), vars_stress['Fs'])
    add_field(box_stress, 1, 0, L("Tải trọng đắp q_T (T/m²):"), vars_stress['qT'])
    add_field(box_stress, 1, 1, L("Hoạt tải xe qH (T/m²):"), vars_stress['qH'])
    add_field(box_stress, 2, 0, L("Hệ số tải đắp f_fs:"), vars_stress['f_fs'])
    add_field(box_stress, 2, 1, L("Hệ số tải xe f_q:"), vars_stress['f_q'])

    def update_htt_and_qt(*args):
        """Cập nhật Htt = Hkcad + Htk + Hbl và tự động tính qT = gamma_dap * H_cdm."""
        try:
            hkcad_val = float(vars_emb['Hkcad'].get() or 0.0)
            htk_val = float(vars_emb['Htk'].get() or 3.0)
            hbl_val = float(vars_emb['Hbl'].get() or 0.0)
            gamma_val = float(vars_emb['gamma_fill'].get() or 1.8)
        except ValueError:
            hkcad_val, htk_val, hbl_val, gamma_val = 0.0, 3.0, 0.0, 1.8

        htt_val = hkcad_val + htk_val + hbl_val
        vars_emb['Htt'].set(f"{htt_val:.2f}")
        if 'Cọc chống' in vars_cdm['pile_type'].get():
            lbl_htt_note.config(
                text=L("(*) Cọc chống: tính theo Htk + Hkcad") + f" = {htk_val:.2f} + {hkcad_val:.2f} = {htk_val + hkcad_val:.2f} m " + L("(không cộng bù lún)"))
            h_calc = htk_val + hkcad_val
        else:
            lbl_htt_note.config(
                text=L("(*) Cọc treo: tính theo Htt = Hkcad + Htk + Hbl") + f" = {hkcad_val:.2f} + {htk_val:.2f} + {hbl_val:.2f} = {htt_val:.2f} m")
            h_calc = htt_val

        qt_auto = gamma_val * h_calc
        vars_stress['qT'].set(f"{qt_auto:.2f}")

    vars_cdm['pile_type'].trace_add('write', update_htt_and_qt)

    # =========================================================================
    # 4. ỨNG SUẤT ĐẤT NỀN (Rtc)
    # =========================================================================
    box_subgrade = ttk.LabelFrame(input_frame, text=L("4. Ứng suất đất nền (Rtc)"), padding=8)
    box_subgrade.pack(fill='x', pady=(6, 4))

    vars_subgrade = {
        'hm': tk.StringVar(value='0.30'),
        'q_mong': tk.StringVar(value='0.54'),
        'gamma_sub': tk.StringVar(value='0.80'),
        'm': tk.StringVar(value='1.00'),
        'rtc_method': tk.StringVar(value='Dùng Co lớp đất (φ = 0)'),
        'c_manual': tk.StringVar(value='1.50'),
        'phi_manual': tk.StringVar(value='10.0'),
        'layer_idx': tk.StringVar()
    }

    add_field(box_subgrade, 0, 0, L("Chiều sâu đào đất hm (m):"), vars_subgrade['hm'], width=9)
    add_readonly_field(box_subgrade, 0, 1, L("Tải móng q = γ_đào*hm:"), vars_subgrade['q_mong'], width=9)
    lbl_q_note = ttk.Label(box_subgrade, text="", font=('Times New Roman', 8, 'italic'),
                           foreground='#0369A1')
    lbl_q_note.grid(row=0, column=4, sticky='w', padx=4)

    add_readonly_field(box_subgrade, 1, 0, L("Dung trọng γ' (T/m³):"), vars_subgrade['gamma_sub'], width=9)
    lbl_gamma_note = ttk.Label(box_subgrade, text="", font=('Times New Roman', 8, 'italic'),
                               foreground='#0369A1')
    lbl_gamma_note.grid(row=1, column=2, columnspan=3, sticky='w', padx=4)

    add_field(box_subgrade, 2, 0, L("Hệ số ĐKLV m:"), vars_subgrade['m'], width=9)

    ttk.Label(box_subgrade, text=L("Nguồn c, φ:")).grid(
        row=2, column=2, sticky='w', padx=(10, 4), pady=3)
    cb_method = ttk.Combobox(
        box_subgrade, textvariable=vars_subgrade['rtc_method'],
        values=('Dùng Co lớp đất (φ = 0)', 'Nhập c, φ cắt nhanh'),
        state='readonly', width=20)
    cb_method.grid(row=2, column=3, sticky='w', pady=3)

    f_co = ttk.Frame(box_subgrade)
    f_co.grid(row=3, column=0, columnspan=5, sticky='w', pady=4)
    ttk.Label(f_co, text=L("Chọn lớp đất:")).pack(side='left', padx=(0, 4))
    cb_layer = ttk.Combobox(f_co, textvariable=vars_subgrade['layer_idx'],
                            state='readonly', width=12)
    cb_layer.pack(side='left', padx=4)
    lbl_co_disp = ttk.Label(f_co, text=L("Co = --- T/m² (Mặc định φ = 0)"),
                            font=('Times New Roman', 9, 'bold'),
                            foreground=COLORS['nav_active'])
    lbl_co_disp.pack(side='left', padx=10)

    f_c_phi = ttk.Frame(box_subgrade)
    f_c_phi.grid(row=3, column=0, columnspan=5, sticky='w', pady=4)
    ttk.Label(f_c_phi, text=L("Lực dính c (T/m²):")).pack(side='left', padx=(0, 4))
    ttk.Entry(f_c_phi, textvariable=vars_subgrade['c_manual'], width=10).pack(side='left', padx=4)
    ttk.Label(f_c_phi, text=L("Góc ma sát φ (°):")).pack(side='left', padx=(20, 4))
    ttk.Entry(f_c_phi, textvariable=vars_subgrade['phi_manual'], width=10).pack(side='left', padx=4)

    def on_rtc_method_change(*args):
        if vars_subgrade['rtc_method'].get() == 'Nhập c, φ cắt nhanh':
            f_co.grid_remove()
            f_c_phi.grid()
        else:
            f_c_phi.grid_remove()
            f_co.grid()

    vars_subgrade['rtc_method'].trace_add('write', on_rtc_method_change)
    on_rtc_method_change()

    def update_subgrade_auto(*args):
        """Tự động tính gamma_sub theo MNN và q_mong theo hm."""
        project = getattr(app, 'project', None)
        if not project or not project.soils:
            return
        idx = cb_layer.current()
        if idx < 0 or idx >= len(project.soils):
            idx = 0
        soil = project.soils[idx]

        co_val = getattr(soil, 'co', 0.0)
        lbl_co_disp.config(text=f"Co = {co_val:.2f} T/m² (φ = 0)")

        depth_top = sum(getattr(s, 'thickness', 0.0) for s in project.soils[:idx])
        depth_mid = depth_top + getattr(soil, 'thickness', 0.0) / 2.0

        try:
            gw_val = getattr(project, 'water_table',
                             getattr(project, 'groundwater_depth',
                                     getattr(project, 'zw', 0.0)))
            gw_depth = float(gw_val) if gw_val is not None and gw_val != '' else 0.0
        except (ValueError, TypeError):
            gw_depth = 0.0

        try:
            gamma_raw = float(getattr(soil, 'gamma', 1.8) or 1.8)
        except (ValueError, TypeError):
            gamma_raw = 1.8

        if depth_mid >= gw_depth:
            gamma_sub_val = max(0.2, gamma_raw - 1.0)
            lbl_gamma_note.config(text=f"(" + L("Dưới MNN =") + f" {gw_depth:.2f}m: γ' = γ - 1.0 = {gamma_sub_val:.2f})")
        else:
            gamma_sub_val = gamma_raw
            lbl_gamma_note.config(text=f"(" + L("Trên MNN =") + f" {gw_depth:.2f}m: γ' = γ = {gamma_sub_val:.2f})")
        vars_subgrade['gamma_sub'].set(f"{gamma_sub_val:.2f}")

        try:
            hm_val = float(vars_subgrade['hm'].get() or 0.3)
        except ValueError:
            hm_val = 0.3

        try:
            gamma_top = float(getattr(project.soils[0], 'gamma', 1.8) or 1.8)
        except (ValueError, TypeError):
            gamma_top = 1.8

        q_calc = gamma_top * hm_val
        vars_subgrade['q_mong'].set(f"{q_calc:.2f}")
        lbl_q_note.config(text=f"({gamma_top:.2f} × {hm_val:.2f})")

    vars_subgrade['layer_idx'].trace_add('write', update_subgrade_auto)
    vars_subgrade['hm'].trace_add('write', update_subgrade_auto)

    # =========================================================================
    # 5. VẢI / LƯỚI ĐỊA KỸ THUẬT GIA CƯỜNG ĐẦU CỌC
    # =========================================================================
    box_geo = ttk.LabelFrame(
        input_frame,
        text=L("5. Vải / lưới địa kỹ thuật gia cường đầu cọc (BS 8006)"),
        padding=8)
    box_geo.pack(fill='x', pady=6)

    var_use_geo = tk.BooleanVar(value=True)
    chk_geo = ttk.Checkbutton(
        box_geo, text=L('Gia cường đầu cọc'),
        variable=var_use_geo)
    chk_geo.grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 6))
    chk_geo.grid_remove()

    var_reinforcement = tk.StringVar(value='Vải địa kỹ thuật')
    ttk.Label(box_geo, text=L('Chọn vật liệu:')).grid(row=0, column=0, sticky='w')
    cb_reinf = ttk.Combobox(
        box_geo, textvariable=var_reinforcement,
        values=('Không dùng', 'Vải địa kỹ thuật', 'Lưới địa kỹ thuật'),
        state='readonly', width=23)
    cb_reinf.grid(row=0, column=1, sticky='w', pady=(0, 6))

    vars_geo = {
        'eps': tk.StringVar(value='6.0'), 'phi_dap': tk.StringVar(value='30.0'),
        'T_char_kn': tk.StringVar(value='200'), 'Tmax': tk.StringVar(value='400'), 'eps_max': tk.StringVar(value='10.0'),
        'n_layer': tk.StringVar(value='2'), 'fm11': tk.StringVar(value='1.37'),
        'fm12': tk.StringVar(value='1.02'),
        'fm21': tk.StringVar(value='1.01'), 'fm22': tk.StringVar(value='1.03'),
        'fn': tk.StringVar(value='1.0')
    }

    geo_entries = []
    geo_entries.append(add_field(box_geo, 1, 0, L('Độ giãn dài cho phép ε (%):'), vars_geo['eps']))
    geo_entries.append(add_field(box_geo, 1, 1, L("Góc ma sát đất đắp φ' (độ):"), vars_geo['phi_dap']))
    geo_entries.append(add_field(box_geo, 1, 2, L("Cường độ vải Tmax (kN/m):"), vars_geo['Tmax']))
    geo_entries.append(add_field(box_geo, 4, 0, L("Số lớp gia cường n:"), vars_geo['n_layer']))
    geo_entries.append(add_field(box_geo, 2, 0, L("Hệ số sx fm11:"), vars_geo['fm11']))
    geo_entries.append(add_field(box_geo, 2, 1, L("Hệ số n.suy fm12:"), vars_geo['fm12']))
    geo_entries.append(add_field(box_geo, 2, 2, L("Hệ số thi công fm21:"), vars_geo['fm21']))
    geo_entries.append(add_field(box_geo, 4, 1, L("Hệ số MT fm22:"), vars_geo['fm22']))
    geo_entries.append(add_field(box_geo, 3, 0, L("Hệ số kinh tế fn:"), vars_geo['fn']))
    geo_entries.append(add_field(box_geo, 3, 1, L('Độ giãn dài tối đa εmax (%):'), vars_geo['eps_max']))
    geo_entries.append(add_field(box_geo, 3, 2, L('Tchar lưới địa (kN/m):'), vars_geo['T_char_kn']))
    ttk.Label(box_geo, text=L('Vải 400×400: nhập Tmax = 400 kN/m. Tchar = 0,9 × ε × Tmax / εmax; ε là độ giãn dài cho phép (%).'),
              foreground='#92400E').grid(row=5, column=0, columnspan=8, sticky='w', pady=(5, 0))

    def toggle_geo():
        state = 'normal' if var_use_geo.get() else 'disabled'
        for ent in geo_entries:
            ent.config(state=state)
        if var_use_geo.get():
            is_grid = var_reinforcement.get() == 'Lưới địa kỹ thuật'
            for index in (2, 9):
                geo_entries[index].config(state='disabled' if is_grid else 'normal')
            geo_entries[10].config(state='normal' if is_grid else 'disabled')

    var_use_geo.trace_add('write', lambda *_: toggle_geo())

    def sync_reinforcement(*_):
        var_use_geo.set(var_reinforcement.get() != 'Không dùng')
        toggle_geo()
    var_reinforcement.trace_add('write', sync_reinforcement)
    sync_reinforcement()

    def refresh_project_data():
        project = app.cdm_calculation_project()
        params = get_project_embankment_params(project)
        vars_emb['B'].set(f"{params['B']:.2f}")
        vars_emb['m'].set(f"{params['m']:.2f}")
        vars_emb['Bxl'].set(f"{params['Bxl']:.2f}")
        vars_emb['Htk'].set(f"{params['Htk']:.2f}")
        vars_emb['Hbl'].set(f"{params['Hbl']:.2f}")
        vars_emb['gamma_fill'].set(f"{params['gamma_fill']:.2f}")
        vars_emb['Hkcad'].set(f"{params['Hkcad']:.2f}")
        vars_stress['qH'].set(f"{params['qh']:.2f}")
        update_htt_and_qt()

        if not project or not project.soils:
            cb_layer['values'] = []
            cb_layer.set('')
            lbl_co_disp.config(text=L("Co = --- T/m²"))
            return

        layer_list = [f"{i+1}. {s.name or 'Lớp '+str(i+1)}"
                      for i, s in enumerate(project.soils)]
        cb_layer['values'] = layer_list
        if cb_layer.current() == -1:
            cb_layer.current(0)
        update_subgrade_auto()

    # --- KHU VỰC CÁC NÚT HÀNH ĐỘNG ---
    f_btn_actions = ttk.Frame(input_frame)
    f_btn_actions.pack(anchor='w', pady=(4, 10))

    btn_calc = ttk.Button(f_btn_actions,
                          text=L('Kiểm toán cọc trộn sâu'),
                          style='Accent.TButton')
    btn_calc.pack(side='left', padx=(0, 10))

    btn_optimize = ttk.Button(f_btn_actions,
                              text=L('Tính toán tối ưu'))
    btn_optimize.pack(side='left')

    # =========================================================================
    # KHUNG KẾT QUẢ
    # =========================================================================
    result_tabs = ttk.Notebook(inner)
    result_tabs.pack(fill='both', expand=True, padx=10, pady=5)

    tab_lun = ttk.Frame(result_tabs, padding=10)
    tab_stress = ttk.Frame(result_tabs, padding=15)
    tab_geo = ttk.Frame(result_tabs, padding=15)

    result_tabs.add(tab_lun, text=L("Kết quả 1: Lún CDM"))
    result_tabs.add(tab_stress, text=L("Kết quả 2: Ứng suất (TCVN & BS 8006)"))
    result_tabs.add(tab_geo, text=L("Kết quả 3: Vải / lưới địa (BS 8006)"))

    # --- TAB 1: KẾT QUẢ LÚN ---
    cols_lun = ('layer', 'h', 'z', 'gamma', 'spt', 'e0', 'cc', 'cr', 'pc',
                'ap', 'dp', 'su_soil', 'su_td', 'e_soil', 'e_td', 'si', 'sc')
    headers_lun = [L('Lớp/Phân tố'), L('Chiều dày') + '\n(m)',
                   L('Cao độ đáy') + '\n(m)', 'γ\n(T/m³)', 'Nspt', 'e₀', 'Cc',
                   'Cr', 'Pc\n(T/m²)', 'ap', 'ΔP\n(T/m²)', 'Su, soil',
                   'Su, tđ', 'Esoil', 'Etđ', 'Si (cm)', 'Sc (cm)']
    widths_lun = [105, 55, 60, 50, 45, 45, 45, 45, 60, 45, 55, 65, 65, 65, 75, 60, 60]

    tree_lun = ttk.Treeview(tab_lun, columns=cols_lun, show='headings', height=8)
    sb_y_lun = ttk.Scrollbar(tab_lun, orient='vertical', command=tree_lun.yview)
    tree_lun.configure(yscrollcommand=sb_y_lun.set)

    for c, h, w in zip(cols_lun, headers_lun, widths_lun):
        tree_lun.heading(c, text=h)
        tree_lun.column(c, width=w, minwidth=40, anchor='center', stretch=False)

    tree_lun.tag_configure('even', background='#FFFFFF')
    tree_lun.tag_configure('odd', background='#F8FAFC')
    tree_lun.tag_configure('total', background='#FEF3C7',
                           font=('Times New Roman', 8, 'bold'))
    tree_lun.tag_configure('cdm_row', background='#E0F2FE',
                           font=('Times New Roman', 8, 'bold'))

    bind_mousewheel(tree_lun)
    tree_lun.pack(side='top', fill='x')

    lbl_eval_lun = ttk.Label(tab_lun,
                             text=L("Đánh giá Lún dư: Chờ tính toán"),
                             font=('Times New Roman', 11, 'bold'),
                             foreground='#64748B')
    lbl_eval_lun.pack(anchor='w', pady=(10, 0))

    # --- TAB 2: KẾT QUẢ ỨNG SUẤT ---
    def create_res_lbl(parent, row, col, text, color='#1E293B'):
        lbl = ttk.Label(parent, text=text, font=('Times New Roman', 10, 'bold'),
                        foreground=color)
        lbl.grid(row=row, column=col, sticky='w', padx=(0, 30), pady=6)
        return lbl

    lbl_htt_res = create_res_lbl(tab_stress, 0, 0,
                                 L("Chiều cao tính toán CDM (H): --- m"),
                                 color='#0369A1')
    lbl_qt = create_res_lbl(tab_stress, 0, 1,
                            L("Tải trọng đất đắp q_T: --- T/m²"))
    lbl_load_used = create_res_lbl(tab_stress, 1, 0,
                                   L("Tải tính toán có HS vượt tải σ'_v: --- T/m²"),
                                   color='#B45309')
    lbl_cc = create_res_lbl(tab_stress, 1, 1,
                            L("Hệ số tạo vòm Cc (BS 8006): ---"))

    ttk.Separator(tab_stress, orient='horizontal').grid(row=2, column=0,
                                                        columnspan=2, sticky='ew', pady=10)
    ttk.Label(tab_stress,
              text=L("A. KIỂM TOÁN CƯỜNG ĐỘ CỌC (TTGH1 & TTGH2)"),
              font=('Times New Roman', 11, 'bold'),
              foreground='#1E3A8A').grid(row=3, column=0, columnspan=2,
                                         sticky='w', pady=4)

    lbl_qu_status = create_res_lbl(tab_stress, 4, 0,
                                   L("Cường độ kiểm toán: --- T/m²"))
    lbl_qu_allow = create_res_lbl(tab_stress, 4, 1,
                                  L("Cường độ cho phép [qu]: --- T/m²"))
    lbl_qu_tt1 = create_res_lbl(tab_stress, 5, 0,
                                L("Cường độ tác dụng TTGH1: --- T/m²"))
    lbl_eval_tt1 = create_res_lbl(tab_stress, 5, 1,
                                  L("=> Đánh giá TTGH 1 (Cường độ cọc): Chờ tính"))

    lbl_sigma_p = create_res_lbl(tab_stress, 6, 0,
                                 L("Ứng suất tác dụng đầu cọc (σ_p / P'c): --- T/m²"))
    lbl_eval_tt2_p = create_res_lbl(tab_stress, 6, 1,
                                    L("=> Kiểm tra Ứng suất đầu cọc (σ_p <= [qu]): Chờ tính"))

    ttk.Separator(tab_stress, orient='horizontal').grid(row=7, column=0,
                                                        columnspan=2, sticky='ew', pady=10)
    ttk.Label(tab_stress,
              text=L("B. KIỂM TOÁN ỨNG SUẤT ĐẤT NỀN"),
              font=('Times New Roman', 11, 'bold'),
              foreground='#1E3A8A').grid(row=8, column=0, columnspan=2,
                                         sticky='w', pady=4)

    lbl_sigma_s = create_res_lbl(tab_stress, 9, 0,
                                 L("Ứng suất lên đất nền (σ_s): --- T/m²"))
    lbl_Rtc = create_res_lbl(tab_stress, 9, 1,
                             L("Sức chịu tải đất nền (Rtc): --- T/m²"))

    lbl_c_soil = ttk.Label(
        tab_stress,
        text=L("Bề rộng Bxl = --- m | Lực dính c = --- T/m² | Góc ma sát φ = ---°")
             + '\n' + L("Tra bảng: A = ---, B = ---, D = ---"),
        font=('Times New Roman', 9, 'italic'),
        foreground=COLORS['muted'])
    lbl_c_soil.grid(row=10, column=0, columnspan=2, sticky='w', pady=2)

    lbl_eval_tt2_s = create_res_lbl(tab_stress, 11, 0,
                                    L("=> Kiểm tra Ứng suất đất nền (σ_s <= Rtc): Chờ tính"))
    lbl_eval_tt2_s.grid(columnspan=2)

    # --- TAB 3: KẾT QUẢ VẢI ĐỊA ---
    lbl_geo_wt = create_res_lbl(tab_geo, 0, 0,
                                L("Lực kéo do võng bệ tính toán (WT): --- T/m"))
    lbl_geo_wtmin = create_res_lbl(tab_geo, 0, 1,
                                   L("Lực kéo võng bệ tối thiểu (WT_min): --- T/m"))
    lbl_geo_trp = create_res_lbl(tab_geo, 1, 0,
                                 L("Lực kéo căng màng do lún võng (Trp): --- T/m"))
    lbl_geo_ka = create_res_lbl(tab_geo, 1, 1,
                                L("Hệ số áp lực ngang (Ka): ---"))
    lbl_geo_tds = create_res_lbl(tab_geo, 2, 0,
                                 L("Lực kéo do áp lực đất ngang (Tds): --- T/m"))
    lbl_geo_tr = create_res_lbl(tab_geo, 2, 1,
                                L("Tổng lực kéo lớn nhất (Tr = Trp + Tds): --- T/m"),
                                color='#0369A1')

    ttk.Separator(tab_geo, orient='horizontal').grid(row=3, column=0,
                                                     columnspan=2, sticky='ew', pady=10)
    lbl_geo_fm = create_res_lbl(tab_geo, 4, 0,
                                L("Hệ số vật liệu tổng hợp (fm): ---"))
    lbl_geo_td = create_res_lbl(tab_geo, 4, 1,
                                L("Cường độ thiết kế của vải (Td): --- T/m"))
    lbl_geo_tdfn = create_res_lbl(tab_geo, 5, 0,
                                  L("Cường độ thiết kế chịu lực (Td/fn): --- T/m"),
                                  color='#B45309')
    lbl_eval_geo = create_res_lbl(tab_geo, 5, 1,
                                  L("=> Đánh giá thiết kế Vải địa: Chờ tính"),
                                  color='#64748B')

    lbl_geo_t6 = create_res_lbl(tab_geo, 6, 0, L('Cường độ tại độ giãn dài cho phép Tchar: --- kN/m'))
    lbl_geo_t6.grid(columnspan=2)

    lbl_no_geo = ttk.Label(tab_geo,
                           text=L("Không sử dụng vật liệu gia cường."),
                           font=('Times New Roman', 12, 'italic'),
                           foreground=COLORS['muted'])

    refresh_project_data()

    # =========================================================================
    # LƯU / KHÔI PHỤC THÔNG SỐ CDM VÀO project.cdm_inputs
    # =========================================================================
    _state_groups = {'cdm': vars_cdm, 'stress': vars_stress,
                     'subgrade': vars_subgrade, 'geo': vars_geo}
    _auto_keys = {('stress', 'qT'), ('subgrade', 'q_mong'),
                  ('subgrade', 'gamma_sub')}
    _busy = {'restoring': False, 'project': None, 'scope': None}
    _default_state = {g: {k: v.get() for k, v in vs.items()
                          if (g, k) not in _auto_keys}
                      for g, vs in _state_groups.items()}
    _default_state['use_geo'] = bool(var_use_geo.get())
    _default_state['reinforcement'] = var_reinforcement.get()

    def scoped_states(project):
        states = getattr(project, 'cdm_inputs', {}) or {}
        return ({'Nền đường': states} if 'cdm' in states else dict(states))

    def save_cdm_state(*_):
        if _busy['restoring']:
            return
        project = getattr(app, 'project', None)
        if project is None:
            return
        state = {g: {k: v.get() for k, v in vs.items()
                     if (g, k) not in _auto_keys}
                 for g, vs in _state_groups.items()}
        state['use_geo'] = bool(var_use_geo.get())
        state['reinforcement'] = var_reinforcement.get()
        try:
            scope = app.cdm_scope_var.get()
            states = scoped_states(project)
            if state != states.get(scope):
                states[scope] = state
                project.cdm_inputs = states
                if hasattr(app, '_cdm_reports'):
                    app._cdm_reports.pop('standard', None)
        except Exception:
            pass

    def restore_cdm_state():
        project = getattr(app, 'project', None)
        _busy['project'] = project
        scope = app.cdm_scope_var.get()
        _busy['scope'] = scope
        state = scoped_states(project).get(scope) if project is not None else None
        state = state if isinstance(state, dict) else _default_state
        if isinstance(state, dict):
            _busy['restoring'] = True
            try:
                for g, vs in _state_groups.items():
                    saved = state.get(g) or _default_state[g]
                    for k, v in vs.items():
                        if (g, k) not in _auto_keys and k in saved:
                            v.set(saved[k])
                if 'use_geo' in state:
                    var_use_geo.set(bool(state['use_geo']))
                if state.get('reinforcement') in ('Không dùng', 'Vải địa kỹ thuật',
                                                   'Lưới địa kỹ thuật'):
                    var_reinforcement.set(state['reinforcement'])
                elif 'use_geo' in state:
                    var_reinforcement.set('Vải địa kỹ thuật' if state['use_geo']
                                          else 'Không dùng')
            finally:
                _busy['restoring'] = False
        refresh_project_data()

    app._capture_cdm_state = save_cdm_state
    restore_cdm_state()
    for _g, _vs in _state_groups.items():
        for _k, _v in _vs.items():
            if (_g, _k) not in _auto_keys:
                _v.trace_add('write', save_cdm_state)
    var_use_geo.trace_add('write', save_cdm_state)
    var_reinforcement.trace_add('write', save_cdm_state)

    def on_show(event=None):
        if (getattr(app, 'project', None) is not _busy['project'] or
                app.cdm_scope_var.get() != _busy['scope']):
            restore_cdm_state()
    parent.bind('<Map>', on_show, add='+')

    def get_calc_input_payload():
        app.collect_cdm_inputs()
        refresh_project_data()
        project = app.cdm_calculation_project()
        if not project or not project.soils:
            raise ValueError("Chưa có số liệu địa chất. Vui lòng khai báo tại Bước 3.")

        if vars_subgrade['rtc_method'].get() == 'Nhập c, φ cắt nhanh':
            c_val = number(vars_subgrade['c_manual'].get(),
                           "Lực dính c (cắt nhanh)")
            phi_val = number(vars_subgrade['phi_manual'].get(),
                             "Góc ma sát φ (cắt nhanh)")
        else:
            idx = cb_layer.current()
            c_val = (getattr(project.soils[idx], 'cohesion_c', 0.0)
                     if 0 <= idx < len(project.soils) else 0.0)
            phi_val = (getattr(project.soils[idx], 'friction_phi', 0.0)
                       if 0 <= idx < len(project.soils) else 0.0)

        params = {
            'D': number(vars_cdm['D'].get(), "Đường kính cọc"),
            's': round(number(vars_cdm['s'].get(), "Khoảng cách cọc"), 1),
            'Lc': number(vars_cdm['Lc'].get(), "Chiều dài cọc"),
            'qu_type': vars_cdm['qu_type'].get(),
            'qu_val': number(vars_cdm['qu_val'].get(), "Cường độ cọc"),
            'Ec': number(vars_cdm['Ec'].get(), "Mô đun Ec"),
            'pattern': vars_cdm['pattern'].get(),
            'pile_type': vars_cdm['pile_type'].get()
        }

        stress_params = {
            'n': number(vars_stress['n'].get(), "Hệ số n"),
            'Fs': number(vars_stress['Fs'].get(), "Hệ số an toàn Fs"),
            'qT': number(vars_stress['qT'].get(), "Tải trọng đắp qT"),
            'qH': number(vars_stress['qH'].get(), "Hoạt tải qH"),
            'f_fs': number(vars_stress['f_fs'].get(), "Hệ số tải trọng đắp"),
            'f_q': number(vars_stress['f_q'].get(), "Hệ số tải trọng xe")
        }

        subgrade_params = {
            'gamma_sub': number(vars_subgrade['gamma_sub'].get(),
                                "Dung trọng đất gamma'"),
            'q_mong': number(vars_subgrade['q_mong'].get(), "Tải bên móng q"),
            'm': number(vars_subgrade['m'].get(), "Hệ số m"),
            'c_val': c_val,
            'phi_val': phi_val
        }

        is_grid = var_reinforcement.get() == 'Lưới địa kỹ thuật'
        geo_params = {
            'kind': var_reinforcement.get(),
            'T_char_kn': number(vars_geo['T_char_kn'].get(), 'Tchar lưới địa') if is_grid and var_use_geo.get() else 200.0,
            'eps': number(vars_geo['eps'].get(), 'Độ giãn dài cho phép ε') if var_use_geo.get() else 10.0,
            'phi_dap': number(vars_geo['phi_dap'].get(), "Góc ma sát đắp"),
            'Tmax': number(vars_geo['Tmax'].get(), 'Cường độ vải Tmax') if var_use_geo.get() and not is_grid else 400.0,
            'eps_max': number(vars_geo['eps_max'].get(), 'Độ giãn dài tối đa εmax') if var_use_geo.get() and not is_grid else 10.0,
            'n_layer': int(number(vars_geo['n_layer'].get(), "Số lớp vải")),
            'fm11': number(vars_geo['fm11'].get(), "Hệ số fm11"),
            'fm12': number(vars_geo['fm12'].get(), "Hệ số fm12"),
            'fm21': number(vars_geo['fm21'].get(), "Hệ số fm21"),
            'fm22': number(vars_geo['fm22'].get(), "Hệ số fm22"),
            'fn': number(vars_geo['fn'].get(), "Hệ số kinh tế fn")
        }
        return project, params, stress_params, subgrade_params, geo_params

    # =========================================================================
    # LOGIC NÚT TÍNH TOÁN
    # =========================================================================
    def on_calculate():
        try:
            refresh_project_data()
            project, params, stress_params, subgrade_params, geo_params = get_calc_input_payload()

            res = calculate_cdm_all(project, params, stress_params,
                                    subgrade_params, geo_params, var_use_geo.get())
            app._cdm_reports['standard'] = {
                'result': res, 'params': params,
                'stress_params': stress_params,
                'subgrade_params': subgrade_params,
                'geo_params': geo_params,
                'scope': app.cdm_scope_var.get(), 'use_geo': var_use_geo.get(),
                'project_snapshot': deepcopy(app.project)}
            app._cdm_active_method = 'standard'
            if hasattr(app, 'show_cdm_quick_result'):
                app.show_cdm_quick_result(app._cdm_reports['standard'], 'standard')
            app.draw_live_diagram()

            # --- 1. CẬP NHẬT TAB LÚN ---
            tree_lun.delete(*tree_lun.get_children())
            for idx, r in enumerate(res['rows_lun']):
                tag = 'cdm_row' if idx == 0 else ('odd' if idx % 2 else 'even')
                tree_lun.insert('', 'end', values=(
                    r['name'], f"{r['thick']:.2f}", f"{r['bot_z']:.2f}",
                    f"{r['gamma']:.2f}",
                    r['spt'] if r['spt'] != '' else '-',
                    r['e0'] if r['e0'] != '' else '-',
                    f"{r['cc']:.3f}" if r['cc'] != '' else '-',
                    f"{r['cr']:.3f}" if r['cr'] != '' else '-',
                    f"{r['pc']:.2f}" if r['pc'] != '' else '-',
                    r['ap'] if r['ap'] != '' else '-',
                    f"{r['dp']:.2f}",
                    f"{r['su_soil']:.2f}" if r['su_soil'] != '' else '-',
                    f"{r['su_td']:.2f}" if r['su_td'] != '' else '-',
                    f"{r['e_soil']:.2f}",
                    f"{r['e_td']:.2f}" if r['e_td'] != '' else '-',
                    f"{r['si']:.2f}", f"{r['sc']:.2f}"
                ), tags=(tag,))

            tree_lun.insert('', 'end', values=(
                L('TỔNG') if language == 'en' else 'Tổng Si, Sc',
                '', '', '', '', '', '', '', '', '', '', '', '', '', '',
                f"{res['sum_si']:.2f}", f"{res['sum_sc']:.2f}"), tags=('total',))

            limit_cm = getattr(project, 'residual_limit_cm', 30.0) if project else 30.0
            if 'Cọc chống' in res['pile_type']:
                if res['sum_sc'] <= END_BEARING_RESIDUAL_TOL_CM:
                    lbl_eval_lun.config(
                        text=L("[Cọc chống] Không còn lún dư dưới mũi cọc")
                             + f" (ΔS_r = {res['sum_sc']:.2f} cm) ⇒ "
                             + L("ĐẢM BẢO YÊU CẦU"),
                        foreground='#047857')
                else:
                    lbl_eval_lun.config(
                        text=L("[Cọc chống] Còn lún dư dưới mũi cọc") + f" ΔS_r = {res['sum_sc']:.2f} cm ⇒ "
                             + L("KHÔNG ĐẢM BẢO (cần kéo dài cọc, dùng Tối ưu hóa)"),
                        foreground='#DC2626')
            else:
                if res['sum_sc'] <= limit_cm:
                    lbl_eval_lun.config(
                        text=L("[Cọc treo] Độ lún dư") + f" ΔS_r = {res['sum_sc']:.2f} cm ≤ {limit_cm} cm ⇒ "
                             + L("ĐẢM BẢO YÊU CẦU"),
                        foreground='#047857')
                else:
                    lbl_eval_lun.config(
                        text=L("[Cọc treo] Độ lún dư") + f" ΔS_r = {res['sum_sc']:.2f} cm > {limit_cm} cm ⇒ "
                             + L("KHÔNG ĐẢM BẢO"),
                        foreground='#DC2626')

            # --- 2. CẬP NHẬT TAB ỨNG SUẤT ---
            str_res = res['stress']
            if 'Cọc chống' in res['pile_type']:
                lbl_htt_res.config(
                    text=L("Chiều cao tính toán CDM (H = Htk + Hkcad):")
                         + f" {res['H_cdm']:.2f} m (Htk = {res['H_tk']:.2f} + Hkcad = {res['H_kcad']:.2f})")
            else:
                lbl_htt_res.config(
                    text=L("Chiều cao tính toán CDM (H = Htt):")
                         + f" {res['H_cdm']:.2f} m (Hkcad = {res['H_kcad']:.2f} + Htk = {res['H_tk']:.2f} + Hbl = {res['H_bl']:.2f})")

            lbl_qt.config(text=L("Tải trọng đất đắp q_T:") + f" {str_res['qT']:.2f} T/m²")
            lbl_load_used.config(text=L("Tải tính toán có HS vượt tải σ'_v:") + f" {str_res['sigma_v_prime']:.2f} T/m²")
            lbl_cc.config(text=L("Hệ số tạo vòm Cc:") + f" {str_res['Cc']:.3f} = {str_res['cc_formula']}")

            lbl_sigma_p.config(text=L("Ứng suất đầu cọc (σ_p = σ'_v·(Cc·a/H)²):") + f" {str_res['sigma_p']:.2f} T/m²")
            lbl_sigma_s.config(
                text=L("Ứng suất đất nền (σ_s = (γH + q − σ_p·ap)/(1−ap)):")
                     + f" {str_res['sigma_s']:.2f} T/m²")

            if str_res['qu_type'] == 'qu28':
                lbl_qu_status.config(text=L("Cường độ kiểm toán (qu28 trực tiếp):") + f" {str_res['qu_check']:.2f} T/m²")
                lbl_qu_allow.config(text=L("Cường độ cho phép [qu] = qu28/Fs:") + f" {str_res['qu_allow']:.2f} T/m²")
            else:
                lbl_qu_status.config(text=L("Cường độ kiểm toán (qu90/n quy đổi):") + f" {str_res['qu_check']:.2f} T/m²")
                lbl_qu_allow.config(text=L("Cường độ cho phép [qu] = (qu90/n)/Fs:") + f" {str_res['qu_allow']:.2f} T/m²")

            lbl_qu_tt1.config(text=L("Cường độ tác dụng TTGH1:") + f" {str_res['qu_tt1']:.2f} T/m²")

            if str_res['qu_tt1'] <= str_res['qu_allow']:
                lbl_eval_tt1.config(text=L("=> Đánh giá TTGH 1 (Cường độ cọc): ĐẢM BẢO YÊU CẦU"),
                                    foreground='#047857')
            else:
                lbl_eval_tt1.config(text=L("=> Đánh giá TTGH 1 (Cường độ cọc): KHÔNG ĐẢM BẢO"),
                                    foreground='#DC2626')

            if str_res['sigma_p'] <= str_res['qu_allow']:
                lbl_eval_tt2_p.config(text=L("=> Kiểm tra Ứng suất đầu cọc (<= [qu]): ĐẢM BẢO YÊU CẦU"),
                                      foreground='#047857')
            else:
                lbl_eval_tt2_p.config(text=L("=> Kiểm tra Ứng suất đầu cọc (<= [qu]): KHÔNG ĐẢM BẢO"),
                                      foreground='#DC2626')

            lbl_Rtc.config(text=L("Cường độ chịu tải đất nền (Rtc):") + f" {str_res['Rtc']:.2f} T/m²")
            lbl_c_soil.config(
                text=L("Bề rộng Bxl =") + f" {res['b_val']:.2f} m | "
                     + L("Lực dính c =") + f" {res['c_under_pile']:.2f} T/m² | "
                     + L("Góc ma sát φ =") + f" {res['phi_mong']:.2f}°\n"
                     + L("Tra bảng: A =") + f" {res['A_fac']:.2f}, B = {res['B_fac']:.2f}, D = {res['D_fac']:.2f}")

            if str_res['sigma_s'] <= str_res['Rtc']:
                lbl_eval_tt2_s.config(text=L("=> Kiểm tra Ứng suất đất nền (σ_s <= Rtc): ĐẢM BẢO YÊU CẦU"),
                                      foreground='#047857')
            else:
                lbl_eval_tt2_s.config(text=L("=> Kiểm tra Ứng suất đất nền (σ_s <= Rtc): KHÔNG ĐẢM BẢO"),
                                      foreground='#DC2626')

            # --- 3. CẬP NHẬT TAB VẢI ĐỊA KỸ THUẬT ---
            if res['use_geo']:
                lbl_no_geo.place_forget()
                geo_res = res['geo']
                if geo_params.get('kind') == 'Lưới địa kỹ thuật':
                    lbl_geo_t6.config(text=f"Tchar = {geo_res['T_allow_kN_m']:.2f} kN/m = {geo_res['T_char']:.2f} T/m (nhập trực tiếp)")
                else:
                    lbl_geo_t6.config(text=f"Tchar = 0,9 × {geo_params['eps']:.2f} × {geo_params['Tmax']:.2f} / {geo_params['eps_max']:.2f} = {geo_res['T_allow_kN_m']:.2f} kN/m = {geo_res['T_char']:.2f} T/m")
                lbl_geo_wt.config(text=L("Lực kéo do võng bệ (WT):") + f" {geo_res['WT']:.2f} T/m")
                lbl_geo_wtmin.config(text=L("Lực kéo võng bệ tối thiểu (WT_min):") + f" {geo_res['WT_min']:.2f} T/m")
                lbl_geo_trp.config(text=L("Lực kéo căng màng do lún võng (Trp):") + f" {geo_res['Trp']:.2f} T/m")
                lbl_geo_ka.config(text=L("Hệ số áp lực ngang (Ka):") + f" {geo_res['Ka']:.2f}")
                lbl_geo_tds.config(text=L("Lực kéo do áp lực đất ngang (Tds):") + f" {geo_res['Tds']:.2f} T/m")
                lbl_geo_tr.config(text=L("Tổng lực kéo lớn nhất (Tr = Trp + Tds):") + f" {geo_res['Tr']:.2f} T/m")
                lbl_geo_fm.config(text=L("Hệ số vật liệu tổng hợp (fm):") + f" {geo_res['fm']:.2f}")
                lbl_geo_td.config(text=L("Cường độ thiết kế của vải (Td):") + f" {geo_res['Td']:.2f} T/m")
                lbl_geo_tdfn.config(text=L("Cường độ thiết kế chịu lực (Td/fn):") + f" {geo_res['Td_fn']:.2f} T/m")

                if geo_res['Tr'] <= geo_res['Td_fn']:
                    lbl_eval_geo.config(text=L("=> Đánh giá: Tr <= Td/fn => ĐẢM BẢO KHẢ NĂNG CHỊU LỰC"),
                                        foreground='#047857')
                else:
                    lbl_eval_geo.config(text=L("=> Đánh giá: Tr > Td/fn => KHÔNG ĐẢM BẢO CHỊU LỰC"),
                                        foreground='#DC2626')
            else:
                lbl_no_geo.place(relx=0.5, rely=0.5, anchor='center')
                for lbl in (lbl_geo_wt, lbl_geo_wtmin, lbl_geo_trp, lbl_geo_ka,
                            lbl_geo_tds, lbl_geo_tr, lbl_geo_fm, lbl_geo_td,
                            lbl_geo_tdfn, lbl_eval_geo, lbl_geo_t6):
                    lbl.config(text="")

            app.report_result('CDM · kiểm toán',
                              f'S_c = {res["sum_sc"]:.2f} cm; '
                              f'S = {res["total_s"]:.2f} cm; '
                              f'σₚ = {res["stress"]["sigma_p"]:.2f} T/m²; '
                              f'σₛ = {res["stress"]["sigma_s"]:.2f} T/m².\n'
                              f'Kết quả kiểm tra: {app.card_status.cget("text")}.')

        except ValueError as e:
            app.report_result('CDM · kiểm toán', str(e), error=True)
            messagebox.showwarning(L("Lỗi dữ liệu đầu vào"), str(e), parent=app)
        except Exception as e:
            app.report_result('CDM · kiểm toán', str(e), error=True)
            messagebox.showerror(L("Lỗi tính toán"),
                                 L("Đã xảy ra lỗi hệ thống:") + f"\n{str(e)}",
                                 parent=app)

    # =========================================================================
    # TÍNH LẶP BÙ LÚN Hbl
    # =========================================================================
    def on_calculate_hbl():
        try:
            refresh_project_data()
            project, params, stress_params, subgrade_params, geo_params = get_calc_input_payload()

            if 'Cọc chống' in params['pile_type']:
                if messagebox.askyesno(
                    L("Loại cọc"),
                    L("Cọc chống tựa tầng cứng tính theo Htk + Hkcad (không cộng bù lún Hbl).")
                    + "\n\n"
                    + L("Bạn có muốn chuyển sang 'Cọc treo' để tính lặp bù lún tắt lún không?"),
                    parent=app
                ):
                    vars_cdm['pile_type'].set('Cọc treo (Friction pile)')
                    params['pile_type'] = 'Cọc treo (Friction pile)'
                else:
                    return

            H_tk = number(vars_emb['Htk'].get(), "Chiều cao thiết kế Htk")
            H_kcad = number(vars_emb['Hkcad'].get(), "Chiều dày Hkcad")
            hbl_guess = 0.0
            tol = 0.0005
            max_iter = 35
            last_total_s = 0.0
            it = 0

            for it in range(1, max_iter + 1):
                project.h_bl = hbl_guess
                project.height = H_kcad + H_tk + hbl_guess

                gamma_val = float(vars_emb['gamma_fill'].get() or 1.8)
                stress_params['qT'] = gamma_val * (H_kcad + H_tk + hbl_guess)

                res = calculate_cdm_all(project, params, stress_params,
                                        subgrade_params, geo_params,
                                        var_use_geo.get())
                total_s_m = res['total_s'] / 100.0
                last_total_s = res['total_s']

                diff = abs(total_s_m - hbl_guess)
                if diff < tol:
                    hbl_guess = total_s_m
                    break

                hbl_guess = 0.5 * hbl_guess + 0.5 * total_s_m

            hbl_final = round(hbl_guess, 3)
            project.h_bl = hbl_final
            project.height = H_kcad + H_tk + hbl_final
            if app.cdm_scope_var.get() == 'Nền mở rộng':
                app.project.expansion_h_bl = hbl_final

            vars_emb['Hbl'].set(f"{hbl_final:.2f}")
            vars_emb['Htt'].set(f"{H_kcad + H_tk + hbl_final:.2f}")
            vars_stress['qT'].set(f"{gamma_val * (H_kcad + H_tk + hbl_final):.2f}")

            on_calculate()

            msg = (
                L("TÍNH TOÁN BÙ LÚN TẮT LÚN THÀNH CÔNG!") + "\n\n"
                + "• " + L("Số bước lặp:") + f" {it} " + L("bước") + "\n"
                + "• " + L("Tổng độ lún tắt lún S =") + f" {last_total_s:.2f} cm ({last_total_s/100.0:.2f} m)\n"
                + "• " + L("Chiều cao bù lún Hbl =") + f" {hbl_final:.2f} m ({hbl_final*100.0:.2f} cm)\n"
                + "• " + L("Chiều cao tính toán Htt = Hkcad + Htk + Hbl =")
                + f" {H_kcad:.2f} + {H_tk:.2f} + {hbl_final:.2f} = {H_kcad + H_tk + hbl_final:.2f} m"
            )
            app.report_result('CDM · bù lún', msg)

        except ValueError as e:
            messagebox.showwarning(L("Lỗi dữ liệu đầu vào"), str(e), parent=app)
        except Exception as e:
            messagebox.showerror(L("Lỗi tính toán"),
                                 L("Đã xảy ra lỗi hệ thống:") + f"\n{str(e)}",
                                 parent=app)

    # =========================================================================
    # HỘP THOẠI TỐI ƯU HÓA
    # =========================================================================
    def on_open_optimize_dialog():
        if hasattr(app, 'require_full_license') and not app.require_full_license():
            return
        try:
            refresh_project_data()
            project, params, stress_params, subgrade_params, geo_params = get_calc_input_payload()
        except Exception as e:
            messagebox.showwarning(L("Lỗi dữ liệu đầu vào"), str(e), parent=app)
            return

        total_soil_h = sum(getattr(soil, 'thickness', 0.0) for soil in project.soils)
        default_max_lc = max(10.0, round(total_soil_h, 1))
        limit_cm = getattr(project, 'residual_limit_cm', 30.0)

        dlg = tk.Toplevel(app)
        dlg.title(L("🎯 Cài đặt phạm vi tìm kiếm tối ưu (Lc, s, Số lớp vải)"))
        dlg.geometry("520x390")
        dlg.transient(app)
        dlg.grab_set()

        f_dlg = ttk.Frame(dlg, padding=15)
        f_dlg.pack(fill='both', expand=True)

        var_s_min = tk.StringVar(value=f"{max(1.1, round(params['D'] + 0.1, 1)):.2f}")
        var_s_max = tk.StringVar(value="2.5")
        var_s_step = tk.StringVar(value="0.1")

        var_lc_min = tk.StringVar(value="4.00")
        var_lc_max = tk.StringVar(value=f"{default_max_lc:.2f}")
        var_lc_step = tk.StringVar(value="0.50")

        var_n_min = tk.StringVar(value="1")
        var_n_max = tk.StringVar(value="4")

        var_s_limit = tk.StringVar(value=f"{limit_cm:.2f}")

        def add_dlg_row(r, label, var):
            ttk.Label(f_dlg, text=label).grid(row=r, column=0, sticky='w', pady=2)
            ent = ttk.Entry(f_dlg, textvariable=var, width=12)
            ent.grid(row=r, column=1, sticky='e', pady=2)
            return ent

        ttk.Label(f_dlg,
                  text=L("1. Khoảng cách cọc s (m) [làm tròn 1 số thập phân]:"),
                  font=('Times New Roman', 9, 'bold')).grid(
                      row=0, column=0, columnspan=2, sticky='w', pady=(0, 2))
        add_dlg_row(1, L("  • s nhỏ nhất (m):"), var_s_min)
        add_dlg_row(2, L("  • s lớn nhất (m):"), var_s_max)
        add_dlg_row(3, L("  • Bước nhảy s (m):"), var_s_step)

        ttk.Label(f_dlg, text=L("2. Chiều dài cọc Lc (m):"),
                  font=('Times New Roman', 9, 'bold')).grid(
                      row=4, column=0, columnspan=2, sticky='w', pady=(6, 2))
        add_dlg_row(5, L("  • Lc nhỏ nhất (m):"), var_lc_min)
        add_dlg_row(6, L("  • Lc lớn nhất (m):"), var_lc_max)
        add_dlg_row(7, L("  • Bước nhảy Lc (m):"), var_lc_step)

        is_chong = 'Cọc chống' in params['pile_type']
        if is_chong:
            lim_txt = L("Lún dư dưới mũi cọc (cm) [cọc chống: tự kéo dài cọc đến khi hết lún dư]:")
            var_s_limit.set(f"{END_BEARING_RESIDUAL_TOL_CM:.2f}")
        else:
            lim_txt = L("Giới hạn lún dư cho phép (cm):")

        if var_use_geo.get():
            ttk.Label(f_dlg, text=L("3. Số lớp vải địa kỹ thuật n:"),
                      font=('Times New Roman', 9, 'bold')).grid(
                          row=8, column=0, columnspan=2, sticky='w', pady=(6, 2))
            add_dlg_row(9, L("  • Số lớp nhỏ nhất (lớp):"), var_n_min)
            add_dlg_row(10, L("  • Số lớp lớn nhất (lớp):"), var_n_max)
            ent_lim = add_dlg_row(11, "4. " + lim_txt, var_s_limit)
            btn_row = 12
        else:
            ent_lim = add_dlg_row(8, "3. " + lim_txt, var_s_limit)
            btn_row = 9
        if is_chong:
            ent_lim.config(state='disabled')

        def run_search():
            try:
                s_rng = (float(var_s_min.get()), float(var_s_max.get()),
                         float(var_s_step.get()))
                lc_rng = (float(var_lc_min.get()), float(var_lc_max.get()),
                          float(var_lc_step.get()))
                n_rng = ((int(var_n_min.get()), int(var_n_max.get()))
                         if var_use_geo.get() else (1, 1))
                s_lim = float(var_s_limit.get())

                opt_res = optimize_cdm_dimensions(
                    project=project,
                    base_params=params,
                    stress_params=stress_params,
                    subgrade_params=subgrade_params,
                    geo_params=geo_params,
                    use_geo=var_use_geo.get(),
                    s_range=s_rng,
                    lc_range=lc_rng,
                    n_layer_range=n_rng,
                    settlement_limit_cm=s_lim
                )

                if not opt_res:
                    messagebox.showwarning(
                        L("Không tìm thấy nghiệm"),
                        L("Trong phạm vi đã khảo sát không có phương án nào thỏa mãn đồng thời điều kiện lún và các điều kiện ứng suất.")
                        + "\n\n" + L("Gợi ý: Tăng Lc_max hoặc giảm s_min, hoặc tăng cường độ cọc qu."),
                        parent=dlg
                    )
                    return

                vars_cdm['s'].set(f"{opt_res['s']:.2f}")
                vars_cdm['Lc'].set(f"{opt_res['Lc']:.2f}")
                if var_use_geo.get():
                    vars_geo['n_layer'].set(str(opt_res['n_layer']))

                dlg.destroy()
                on_calculate()

                r = opt_res['res']
                geo_txt = (L("• Số lớp vải địa tối ưu:") + f" {opt_res['n_layer']} " + L("lớp") + "\n"
                           if var_use_geo.get() else "")
                app.report_result(
                    "CDM · " + L("phương án tối ưu"),
                    L("PHƯƠNG ÁN TỐI ƯU CHI PHÍ ĐÃ ĐƯỢC CẬP NHẬT:") + "\n\n"
                    + "• " + L("Chiều dài cọc tối ưu Lc =") + f" {opt_res['Lc']:.2f} m\n"
                    + "• " + L("Khoảng cách cọc tối ưu s =") + f" {opt_res['s']:.2f} m "
                    + L("(Tỷ lệ diện tích ap =") + f" {opt_res['ap']*100:.2f}%)\n"
                    + geo_txt
                    + "• " + L("Độ lún dư đạt:") + f" ΔSr = {r['sum_sc']:.2f} cm ≤ {s_lim:.2f} cm\n"
                    + "• " + L("Ứng suất đầu cọc:") + f" σ_p = {r['stress']['sigma_p']:.2f} T/m² ≤ [qu] = {r['stress']['qu_allow']:.2f} T/m²\n"
                    + "• " + L("Ứng suất đất nền:") + f" σ_s = {r['stress']['sigma_s']:.2f} T/m² ≤ Rtc = {r['stress']['Rtc']:.2f} T/m²",
                )
            except Exception as ex:
                messagebox.showerror(L("Lỗi tính toán"), str(ex), parent=dlg)

        btn_run = ttk.Button(
            f_dlg, text=L('Tính toán tối ưu'),
            command=lambda: app.run_processing('Tối ưu CDM', run_search),
            style='Accent.TButton')
        btn_run.grid(row=btn_row, column=0, columnspan=2, pady=(15, 0), sticky='ew')

    btn_calc.config(command=lambda: app.run_processing('Kiểm toán CDM', on_calculate))
    btn_calc_hbl.config(command=lambda: app.run_processing('Bù lún CDM', on_calculate_hbl))
    btn_optimize.config(command=on_open_optimize_dialog)

    def clear_results():
        tree_lun.delete(*tree_lun.get_children())
        for label in (lbl_eval_lun, lbl_eval_tt1, lbl_eval_tt2_p,
                      lbl_eval_tt2_s, lbl_eval_geo):
            label.configure(text=L('Chờ tính toán theo phạm vi đã chọn'),
                            foreground='#64748B')

    return restore_cdm_state, clear_results


def build_view(parent: tk.Misc) -> None:
    """Điểm vào CDM cũ; hiển thị TCVN/BS và ALiCC từ hai module riêng."""
    import alicc

    methods = ttk.Notebook(parent)
    methods.pack(fill='both', expand=True)
    tab_cdm = ttk.Frame(methods)
    tab_alicc = ttk.Frame(methods)
    methods.add(tab_cdm, text='TCVN 9906 + BS 8006')
    methods.add(tab_alicc, text='ALiCC — cọc CDM')
    refresh_standard, clear_standard = _build_tcvn_bs_view(tab_cdm)
    refresh_alicc, clear_alicc = alicc.build_view(tab_alicc)
    app = parent.winfo_toplevel()

    def selected(_event):
        app._cdm_active_method = ('alicc' if methods.index(methods.select()) == 1
                                  else 'standard')
        app.draw_live_diagram()
    methods.bind('<<NotebookTabChanged>>', selected)
    app.refresh_cdm_inputs = lambda: (refresh_standard(), refresh_alicc(),
                                       app.draw_live_diagram())
    app.clear_cdm_results = lambda: (clear_standard(), clear_alicc())