"""ALiCC cho nền đường: hiệu ứng vòm, lún cọc CDM và lớp gia cường.

Module độc lập với màn hình TCVN 9906 + BS 8006; chỉ dùng công thức
BS 8006 khi người dùng chọn vải hoặc lưới địa kỹ thuật.
Đơn vị giao diện: m, T/m², T/m³, T/m, cm.
"""
from __future__ import annotations

import math
from copy import deepcopy
import tkinter as tk
from ui_theme import UI_FONT, UI_FONT_MONO
from tkinter import ttk, messagebox

from utils import ScrollableFrame, number
from model import pressure, effective_overburden, void_ratio

REINFORCEMENT_NONE = 'Không dùng'
REINFORCEMENT_FABRIC = 'Vải địa kỹ thuật'
REINFORCEMENT_GRID = 'Lưới địa kỹ thuật'
REINFORCEMENT_SURFACE = 'Đệm gia cố xi măng'


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


def _alicc_square_vs(lam: float, d: float, h: float, t: float) -> tuple[float, str, float]:
    """Chỉ dẫn ALiCC (3.6) và (3.7), thể tích trên một ô vuông[cite: 1, 2]."""
    rise = (lam - d) * t / 2
    if rise <= h:
        vs = ((lam - d) * lam**2 / 2 - math.pi * (lam**3 - d**3) / 24
              + (4 - math.pi) * (math.sqrt(2) - 1) * lam**3 / 24) * t
        return vs, '(3.6) vòm đủ chiều cao', rise
    vs = lam**2 * h - (math.pi * (h / t + d / 2)**2 * (d * t / 2 + h)
                      - math.pi * (d / 2)**3 * t) / 3
    return vs, '(3.7) nền đắp thấp', rise


def calculate_alicc_volumes(pattern: str, lam: float, d: float, h: float,
                            theta: float, short_s: float | None = None) -> dict:
    """V_s từ hình 3.4 và phụ lục R; V_c = V_ô − V_s[cite: 1, 2]."""
    if min(lam, d, h) <= 0 or d >= lam or not 0 < theta < 90:
        raise ValueError('ALiCC yêu cầu λ > d > 0, H > 0 và 0° < θ < 90°.')
    t = math.tan(math.radians(theta))
    ac = math.pi * d * d / 4
    terms = {}
    if pattern == 'Lưới vuông':
        area, n_col = lam**2, 1
        vs, branch, rise = _alicc_square_vs(lam, d, h, t)
    elif pattern == 'Lưới tam giác':
        mu = math.sqrt(3) * lam / 2
        R = lam / math.sqrt(3)
        r = d / 2
        gamma = 2 * math.degrees(math.atan(lam / (2 * mu)))
        alpha = (180 - gamma) / 2
        beta = math.degrees(math.atan((-lam**2 + 4 * mu**2) / (4 * lam * mu)))
        D1 = math.sqrt(mu**2 + (lam / 2)**2) / 2
        D2, D3 = D1 - r, lam / 2
        h1, h6 = (R - r) * t, r * t
        h2, h3 = (D2 - r) * t, (D3 - r) * t
        h4, h5 = h1 - h2, h1 - h3
        if h < h1:
            raise ValueError(f'H ({h:.2f} m) thấp hơn chiều cao vòm tam giác h1={h1:.2f} m; '
                             f'cần giảm khoảng cách cọc s hoặc giảm góc vòm θ (chỉ dẫn ALiCC khuyến nghị θ ≈ 80°)[cite: 3, 9].')
        v1 = lam * mu * h1 / 2
        sector = math.pi * (R**2 * (h1 + h6) - r**2 * h6) / 3
        v2, v3 = gamma / 360 * sector, alpha / 360 * sector
        v4 = (beta / 360 * math.pi * R**2 - D1**2 * math.tan(math.radians(beta)) / 2) * 2 * h4 / 3
        v5 = ((gamma / 2) / 360 * math.pi * R**2
              - D3**2 * math.tan(math.radians(gamma / 2)) / 2) * 2 * h5 / 3
        vs = 2 * (v1 - (v2 + 2 * v3 - v4 - 2 * v5))
        area, n_col, rise = math.sqrt(3) * lam**2 / 2, 1, h1
        branch = 'Hình R.1–R.2: 2·[V1−(V2+2V3−V4−2V5)]'
        terms = dict(V1=v1, V2=v2, V3=v3, V4=v4, V5=v5)
    elif pattern == 'Lưới chữ nhật':
        kappa = short_s if short_s is not None else lam
        if not d < kappa <= lam:
            raise ValueError('Bố trí chữ nhật yêu cầu d < κ ≤ λ.')
        square_vs, _, rise = _alicc_square_vs(kappa, d, h, t)
        if h < (lam - d) * t / 2:
            raise ValueError('H thấp hơn chiều cao vòm chữ nhật; phụ lục không có nhánh nền đắp thấp.')
        correction = kappa * (lam - kappa) / 4 * (
            (math.sqrt(2) + 1) * kappa / 2
            + math.hypot(lam / 2, kappa / 2) + lam / 2 - 2 * d) * t
        vs = square_vs + correction
        area, n_col = lam * kappa, 1
        branch = 'Hình R.3: ô vuông cạnh κ + phần hiệu chỉnh chữ nhật'
        terms = dict(V_square=square_vs, V_extra=correction)
    elif pattern == 'Hai trục':
        square_vs, _, rise = _alicc_square_vs(lam, d, h, t)
        if h < rise:
            raise ValueError('H thấp hơn chiều cao vòm hai trục; phụ lục không có nhánh nền đắp thấp.')
        correction = (lam - d)**2 * d * t / 4
        vs = square_vs + correction
        area, n_col = lam**2, 2
        branch = 'Hình R.4: ô vuông + phần hiệu chỉnh hai trục'
        terms = dict(V_square=square_vs, V_extra=correction)
    else:
        raise ValueError('Sơ đồ cọc ALiCC chưa được hỗ trợ.')
    ac_total = n_col * ac
    if ac_total >= area or not -1e-8 <= vs <= (area - ac_total) * h + 1e-8:
        raise ValueError('V_s ngoài giới hạn ô cọc; kiểm tra sơ đồ, khoảng cách, H và θ.')
    vs = max(0, vs)
    return dict(Vs=vs, Vc=area * h - vs, Vtotal=area * h, area=area,
                Ac=ac_total, ap=ac_total / area, arch_rise=rise,
                branch=branch, terms=terms, columns=n_col)


def calculate_alicc_underlying_settlement(project, lc: float) -> tuple[list[dict], float]:
    """S2 dưới mũi cọc treo, phân tố địa chất và áp lực từ mô hình dự án[cite: 1]."""
    if project is None or not getattr(project, 'soils', None):
        raise ValueError('Cọc treo cần hồ sơ địa chất để tính lún S2 dưới mũi cọc.')
    dz = max(float(getattr(project, 'sublayer', 1.0) or 1.0), .1)
    rows = []
    top = 0.0
    for soil in project.soils:
        bottom = top + soil.thickness
        start = max(top, lc)
        if bottom > start:
            n = math.ceil((bottom - start) / dz)
            for i in range(n):
                z0 = start + i * (bottom - start) / n
                z1 = start + (i + 1) * (bottom - start) / n
                z = (z0 + z1) / 2
                po = max(effective_overburden(project, z), 1e-9)
                dp = max(pressure(project, z, 0.0), 0.0)
                if getattr(soil, 'category', '') == 'Đất dính':
                    method = getattr(project, 'method', 'Cc/Cs/Pc')
                    if method == 'Mv–logP':
                        e_before = void_ratio(soil, po)
                        e_after = void_ratio(soil, po + dp)
                        strain = max(0., e_before - e_after) / (1 + e_before)
                    else:
                        pc = max(float(getattr(soil, 'pc', 0.) or 0.), po)
                        e0 = void_ratio(soil, po)
                        cc = float(getattr(soil, 'cc', 0.) or 0.)
                        cs = float(getattr(soil, 'cs', 0.) or 0.)
                        if cc + cs <= 0 and dp > 0:
                            raise ValueError(f'Lớp {getattr(soil,"name","đất dính")} thiếu Cc/Cs để tính S2.')
                        if getattr(soil, 'state', '') == 'Cố kết thường' or po >= pc:
                            numerator = cc * math.log10((po + dp) / po)
                        elif po + dp <= pc:
                            numerator = cs * math.log10((po + dp) / po)
                        else:
                            numerator = cs * math.log10(pc / po) + cc * math.log10((po + dp) / pc)
                        strain = numerator / (1 + e0)
                    cm = strain * (z1 - z0) * 100
                else:
                    modulus = 100 * float(getattr(soil, 'spt_n', 0.) or 0.)
                    if modulus <= 0:
                        raise ValueError(f'Lớp {getattr(soil,"name","đất rời")} thiếu SPT để tính S2.')
                    cm = dp * (z1 - z0) / modulus * 100
                rows.append(dict(layer=getattr(soil, 'name', 'Lớp đất'), z0=z0, z1=z1, dp=dp, cm=cm))
        top = bottom
    if top < lc:
        raise ValueError('Chiều dài cọc vượt quá độ sâu địa chất đã khảo sát.')
    return rows, sum(row['cm'] for row in rows)


def calculate_bs8006_reinforcement(d: float, s: float, h: float, gamma: float,
                                   qh: float, end_bearing: bool, geo: dict) -> dict:
    """Kiểm toán sức kéo vải/lưới địa kỹ thuật theo BS 8006[cite: 1]."""
    t6, tchar = fabric_strength_at_allowable_strain(geo) if 'Tmax' in geo else (geo['T_char'] * 9.80665, geo['T_char'])
    if min(d, s, h, gamma, geo['eps'], tchar, geo['n_layer']) <= 0 or d >= s:
        raise ValueError('Gia cường BS 8006 yêu cầu d, s, H, γ, ε, T_char, số lớp > 0.')
    if not 0 <= geo['phi_dap'] < 90 or min(geo['f_fs'], geo['f_q']) <= 0:
        raise ValueError('BS 8006 yêu cầu 0° ≤ φ < 90° và hệ số tải > 0.')
    if any(geo[key] <= 0 for key in ('fm11', 'fm12', 'fm21', 'fm22', 'fn')):
        raise ValueError('Các hệ số vật liệu BS 8006 phải > 0.')
    cc = max(0., (1.95 if end_bearing else 1.50) * h / d - (.18 if end_bearing else .07))
    ffs, fq = geo['f_fs'], geo['f_q']
    sig = ffs * gamma * h + fq * qh
    stress_ratio = (cc * d / h)**2
    clear = s - d
    den = s * s - d * d
    bracket = s * s - d * d * stress_ratio
    wt = (1.4 * s * ffs * gamma * clear / den * bracket if h > 1.4 * clear else s * sig / den * bracket)
    wt = max(wt, .15 * s * sig)
    trp = wt * clear / (2 * d) * math.sqrt(1 + 1 / (6 * geo['eps'] / 100))
    ka = math.tan(math.pi / 4 - math.radians(geo['phi_dap']) / 2)**2
    tds = .5 * ka * (ffs * gamma * h + 2 * fq * qh) * h
    tr = trp + tds
    fm = geo['fm11'] * geo['fm12'] * geo['fm21'] * geo['fm22']
    fn = geo['fn']
    if min(fm, fn) > 0:
        td = tchar * geo['n_layer'] / fm / fn
    else:
        raise ValueError('Hệ số vật liệu fm và fn phải > 0.')
    return dict(T_allow_kN_m=t6, T_char=tchar, Cc=cc, WT=wt, Trp=trp, Ka=ka, Tds=tds, Tr=tr, Td_fn=td, ok=tr <= td)


def calculate_alicc_surface(psoil: float, area: float, ac: float,
                            columns: int, d: float, lam: float, surface: dict,
                            es_soil: float = 0.0) -> dict:
    """Kiểm toán cắt thủng (Hình 3.9) và kiểm toán ứng suất kéo uốn[cite: 2, 10]."""
    th, qa, tau, su = (surface[k] for k in
                    ('thickness', 'q_allow', 'shear_strength', 'su_soil'))
    if min(th, tau) <= 0 or qa < 0 or su < 0:
        raise ValueError('Đệm xi măng yêu cầu Hse, τu > 0; qa và Su không âm.')
    
    # 1. CẮT THỦNG: τse = (Psoil − qa)(Aô − Ac) / (n · π · d · Hse)[cite: 2]
    net = psoil - qa
    shear = max(net, 0.) * (area - ac) / (columns * math.pi * d * th)
    shear_allow = tau / 1.2
    shear_ok = shear <= shear_allow

    # 2. KIỂM TOÁN ỨNG SUẤT KÉO UỐN[cite: 10]
    qu = surface.get('qu_surface', 120.0)
    alpha_mod = surface.get('alpha', 75.0)
    ratio = surface.get('bend_ratio', 0.25)
    fs_bend = surface.get('Fs_surface', 1.2)

    clear_l = max(0.001, lam - d)
    b = 1.0  # Dải rộng 1 m[cite: 10]
    ise = (b * th**3) / 12.0  #[cite: 10]
    wse = (b * th**2) / 6.0   #[cite: 10]

    # [σ_base] = ratio * qu / FS[cite: 2, 10]
    bending_allow = ratio * qu / fs_bend

    # Trường hợp A: Bỏ qua ảnh hưởng nền đàn hồi (Dầm đơn giản M_max = Psoil * l^2 / 8)[cite: 10]
    m_no_k = psoil * (clear_l**2) / 8.0  #[cite: 10]
    sigma_no_k = m_no_k / wse  #[cite: 10]
    ok_no_k = sigma_no_k <= bending_allow  #[cite: 10]

    # Trường hợp B: Có xét ảnh hưởng nền đàn hồi (Dầm Winkler)[cite: 10]
    esa = surface.get('Esa', 0.0)
    spt = surface.get('spt_n', 0.0)
    if esa <= 0:
        if spt > 0:
            esa = (2800.0 * spt) / 9.80665
        elif es_soil > 0:
            esa = es_soil
        else:
            esa = 500.0

    # k = (1 / 0.3) * Es * (λ / 0.3)^(-3/4)[cite: 10]
    kv = (1.0 / 0.30) * esa * (lam / 0.30)**(-0.75)  #[cite: 10]
    ese = alpha_mod * qu

    denom_alpha = 4.0 * ese * ise
    if denom_alpha > 0 and kv > 0:
        alpha_d = (kv / denom_alpha)**0.25  #[cite: 10]
        u = alpha_d * clear_l
        u2 = u / 2.0
        num = psoil * math.sinh(u2) * math.sin(u2)  #[cite: 10]
        den = (alpha_d**2) * (math.cosh(u) + math.cos(u))  #[cite: 10]
        m_k = num / den if den != 0 else m_no_k
    else:
        alpha_d = 0.0
        m_k = m_no_k

    sigma_k = m_k / wse  #[cite: 10]
    ok_k = sigma_k <= bending_allow  #[cite: 10]

    return dict(shear=shear, shear_allow=shear_allow, net_pressure=net, shear_ok=shear_ok,
                clear_l=clear_l, Ise=ise, Wse=wse, Esa=esa, kv=kv, ese=ese, alpha_d=alpha_d,
                M_max_k=m_k, sigma_k=sigma_k, ok_k=ok_k,
                M_max_no_k=m_no_k, sigma_no_k=sigma_no_k, ok_no_k=ok_no_k,
                bending_allow=bending_allow, Fs_surface=fs_bend)


def es_layer_index(value):
    text=str(value).strip()
    if '.' in text and text.split('.',1)[0].isdigit():return int(text.split('.',1)[0])-1
    try:return int(text or '0')
    except ValueError:raise ValueError('Chọn lớp đất lấy Co để tính Es.')


def alicc_soil_modulus(project,layer_index=0):
    if project is None or not project.soils:raise ValueError('Chưa có địa chất để tính Es = 250 × Co.')
    index=es_layer_index(layer_index)
    if index<0 or index>=len(project.soils):raise ValueError('Lớp đất tính Es không còn trong địa chất.')
    soil=project.soils[index];co=float(soil.co)
    if not math.isfinite(co) or co<=0:raise ValueError('Co của lớp đất tính Es phải dương và hữu hạn.')
    return {'Es':250.0*co,'Co':co,'layer_index':index,'layer_name':soil.name,'layer_no':index+1}


def calculate_alicc_road(params: dict, stress: dict, geo: dict, surface: dict,
                         project=None) -> dict:
    """Ba kiểm toán chính: Lún (S1+S2), Đầu cọc (Vc), Gia cường/Đệm bề mặt[cite: 1]."""
    params=dict(params)
    es_source=alicc_soil_modulus(project,params.get('es_layer_index',0))
    params['Es']=es_source['Es']
    d, lam, h, lc = params['D'], params['s'], params['H'], params['Lc']
    if min(lc, params['Ec'], params['Es'], params['qu'], params['Fs']) <= 0:
        raise ValueError('Lc, Ec, Es, qu và Fs phải > 0.')
    if params['gamma'] <= 0 or stress['qH'] < 0:
        raise ValueError('Dung trọng đắp phải > 0 và hoạt tải không âm.')
    
    volumes = calculate_alicc_volumes(params['pattern'], lam, d, h, params['theta'], params.get('s_short'))
    vs, vc, area, ac = volumes['Vs'], volumes['Vc'], volumes['area'], volumes['Ac']
    psoil = vs * params['gamma'] / (area - ac) + stress['qH']
    pcol = vc * params['gamma'] / ac + stress['qH']
    ap = volumes['ap']
    eeq = ap * params['Ec'] + (1 - ap) * params['Es']
    s1 = (params['gamma'] * h + stress['qH']) * lc / eeq * 100
    
    if params.get('pile_type') == 'Cọc treo':
        under_rows, s2 = calculate_alicc_underlying_settlement(project, lc)
    else:
        under_rows, s2 = [], 0.
        
    # ALiCC (3.8), (3.9), (3.12): H trong (3.8) là chiều dày khối đất
    # giữa các cọc (Lc), không phải chiều cao nền đắp H tính hiệu ứng vòm.
    scol = pcol * lc / params['Ec'] * 100
    ssoil = psoil * lc / params['Es'] * 100
    
    result = dict(**volumes, Psoil=psoil, Pcol=pcol, Eeq=eeq, S1_cm=s1, S2_cm=s2,
                  settlement_rows=under_rows, S_total_cm=s1 + s2, Scol_cm=scol, Ssoil_cm=ssoil,
                  pile_ok=pcol * params['Fs'] <= params['qu'],
                  warnings=[])
    
    if not .10 <= ap <= .30:
        result['warnings'].append('ap ngoài khoảng 10–30% khuyến nghị ALiCC[cite: 2].')
    if lam >= h:
        result['warnings'].append('λ ≥ H; chỉ dẫn ALiCC khuyến nghị bước cọc nhỏ hơn chiều cao đắp[cite: 2].')
    differential=abs(ssoil-scol)
    raw_limit=params.get('differential_limit_cm')
    delta_limit=None if raw_limit is None or str(raw_limit).strip()=='' else float(str(raw_limit).replace(',','.'))
    if delta_limit is not None and (not math.isfinite(delta_limit) or delta_limit<=0):
        raise ValueError('Giới hạn chênh lún cho phép phải dương và hữu hạn.')
    result.update(Es_used=params['Es'],Co_used=es_source['Co'],es_layer_no=es_source['layer_no'],es_layer_name=es_source['layer_name'],
                  differential_cm=differential,differential_limit_cm=delta_limit,
                  differential_checked=delta_limit is not None,differential_ok=differential<=delta_limit if delta_limit is not None else None)
    if delta_limit is None:result['warnings'].append('Chưa nhập giới hạn chênh lún [ΔS]; chưa kiểm tra ΔS = |Ssoil − Scol|.')

    if geo.get('kind') in (REINFORCEMENT_FABRIC, REINFORCEMENT_GRID):
        if params['pattern'] in ('Lưới chữ nhật', 'Hai trục'):
            raise ValueError('Vải/lưới BS 8006 trên ô chữ nhật hoặc hai trục cần kiểm toán hai phương riêng; chưa hỗ trợ trong bảng này.')
        result['reinforcement'] = calculate_bs8006_reinforcement(
            d, lam, h, params['gamma'], stress['qH'], params.get('pile_type') == 'Cọc chống', geo)
    if surface.get('enabled'):
        result['surface'] = calculate_alicc_surface(
            psoil, area, ac, volumes['columns'], d, lam, surface, es_soil=params['Es'])
    return result


def solve_alicc_hbl(project, base_h: float, calculate_result,
                    tolerance_m: float = .0005, max_iter: int = 35) -> tuple[float, int]:
    """Giải Hbl = S1 + S2 cho cọc treo; khôi phục dữ liệu nếu không hội tụ[cite: 1]."""
    previous_hbl = getattr(project, 'h_bl', 0.)
    had_height = hasattr(project, 'height')
    previous_height = getattr(project, 'height', None)
    guess = 0.
    try:
        for iteration in range(1, max_iter + 1):
            project.h_bl = guess
            project.height = base_h + guess
            result = calculate_result()
            target = result['S_total_cm'] / 100
            if abs(target - guess) < tolerance_m:
                project.h_bl = round(target, 3)
                project.height = base_h + project.h_bl
                return project.h_bl, iteration
            guess = .5 * (guess + target)
        raise ValueError('Hbl không hội tụ trong 35 vòng lặp; kiểm tra thông số đất và tải trọng.')
    except Exception:
        project.h_bl = previous_hbl
        if had_height:
            project.height = previous_height
        elif hasattr(project, 'height'):
            delattr(project, 'height')
        raise


def get_project_embankment_params(project) -> dict:
    """Trích xuất an toàn các thông số nền đắp từ project[cite: 1]."""
    if not project:
        return {
            'B': 10.0, 'm': 1.5, 'Bxl': 19.0,
            'Htk': 3.0, 'Hbl': 0.0, 'Hkcad': 0.6,
            'gamma_fill': 1.8, 'qh': 1.5
        }
    
    Htk = getattr(project, 'h_design', 3.0)
    if Htk <= 0: Htk = 3.0
    m_slope = getattr(project, 'slope_m', 1.5)
    if m_slope <= 0: m_slope = 1.5
    crest_half = getattr(project, 'crest_half_width', 5.0)
    B_val = crest_half * 2.0 if crest_half > 0 else getattr(project, 'b_crest', 10.0)
    Bxl_val = 2.0 * Htk * m_slope + B_val
    
    Hbl = getattr(project, 'h_bl', getattr(project, 'h_settlement', getattr(project, 'bu_lun', 0.0)))
    Hkcad = getattr(project, 'h_kcad', getattr(project, 'pavement_h', 0.6))
    gamma_fill = getattr(project, 'gamma_fill', 1.8)
    qh = getattr(project, 'qh', getattr(project, 'surcharge_q', 1.5))
    
    return {
        'B': B_val, 'm': m_slope, 'Bxl': Bxl_val,
        'Htk': Htk, 'Hbl': Hbl, 'Hkcad': Hkcad,
        'gamma_fill': gamma_fill, 'qh': qh
    }


def build_view(parent: tk.Misc) -> None:
    """Màn hình ALiCC độc lập cho nền đường; thiết kế đồng bộ với module TCVN 9906[cite: 1, 4]."""
    app = parent.winfo_toplevel()
    scroll = ScrollableFrame(parent)
    scroll.pack(fill='both', expand=True)
    root = scroll.scrollable_frame
    
    title_frame = ttk.Frame(root)
    title_frame.pack(fill='x', padx=5, pady=(5, 0))
    tk.Label(title_frame, text='THIẾT KẾ XỬ LÝ NỀN BẰNG CỌC XI MĂNG ĐẤT (CDM) - CHỈ DẪN ALiCC',
             font=(UI_FONT, 13, 'bold'), anchor='w').pack(fill='x', padx=5, pady=5)
    
    ttk.Separator(root, orient='horizontal').pack(fill='x', padx=5, pady=2)
              
    v = {key: tk.StringVar(value=value) for key, value in {
        'Htk': '3.00', 'Hkcad': '0.50', 'Hbl': '0.055', 'Htt': '3.555', 'H': '3.555',
        'gamma': '1.90', 'qH': '1.50', 'pile_type': 'Cọc treo', 'theta': '80.0',
        'D': '0.80', 's': '1.30', 's_short': '1.4', 'Lc': '9.00',
        'pattern': 'Lưới tam giác', 'Ec': '14000.00', 'Es': '', 'es_layer_idx': '0', 'differential_limit_cm': '', 'qu': '70.00',
        'Fs': '1.2', 'delta_limit': '5', 'settlement_limit': '20.0',
        'kind': REINFORCEMENT_NONE, 'eps': '6.0', 'phi_dap': '30.0', 'T_char_kn': '200', 'Tmax': '400', 'eps_max': '10.0',
        'n_layer': '2', 'fm11': '1.37', 'fm12': '1.02', 'fm21': '1.01', 'fm22': '1.03',
        'fn': '1.0', 'f_fs': '1.30', 'f_q': '1.30',
        'surface_h': '0.50', 'q_allow': '4.5', 'su_soil': '1.25',
        'shear_strength': '120', 'qu_surface': '120', 'alpha': '75',
        'bend_ratio': '0.25', 'Esa': '0', 'spt_n': '0'
    }.items()}

    def field(box, row, col, label, key, readonly=False, width=10):
        ttk.Label(box, text=label).grid(row=row, column=2 * col, sticky='w', padx=(15 if col else 5, 2), pady=3)
        entry = ttk.Entry(box, textvariable=v[key], width=width,
                          state='readonly' if readonly else 'normal')
        entry.grid(row=row, column=2 * col + 1, sticky='w', pady=3)
        return entry

    btn_style_teal = {'bg': '#0C6175', 'fg': 'white', 'font': (UI_FONT, 10, 'bold'), 
                      'relief': 'flat', 'activebackground': '#0284C7', 'activeforeground': 'white',
                      'padx': 12, 'pady': 7,
                      'cursor': 'hand2'}

    # 1. THÔNG SỐ NỀN ĐẮP
    base = ttk.LabelFrame(root, text='1. Thông số tính toán nền đắp')
    base.pack(fill='x', padx=10, pady=4)
    
    for row, items in enumerate((
        (('Chiều cao đắp Htk (m):', 'Htk'), ('Bù lún Hbl (m):', 'Hbl'), ('Chiều dày Hkcad (m):', 'Hkcad'), ('Chiều cao tính Htt (m):', 'Htt')),
        (('Chiều cao tính vòm (m):', 'H'), ('γ đắp (T/m³):', 'gamma'), ('Tải trọng đắp qT (T/m²):', 'qH'))
    )):
        for col, (label, key) in enumerate(items):
            field(base, row, col, label, key, key != 'qH', width=12)

    frame_hbl = ttk.Frame(base)
    frame_hbl.grid(row=2, column=0, columnspan=8, sticky='w', padx=5, pady=(5, 8))
    btn_hbl = tk.Button(frame_hbl, text='Tính chiều cao bù lún', **btn_style_teal)
    btn_hbl.pack(side='left', padx=(0, 10))
    ttk.Label(frame_hbl, text='(*) Cọc treo: tính theo Htt = Hkcad + Htk + Hbl', 
              foreground='#0078D7', font=(UI_FONT, 9, 'italic')).pack(side='left')

    # 2. THÔNG SỐ CỌC CDM & GÓC VÒM
    geom = ttk.LabelFrame(root, text='2. Thông số cọc CDM & Hiệu ứng vòm')
    geom.pack(fill='x', padx=10, pady=4)
    
    ttk.Label(geom, text='Loại cọc ALiCC:').grid(row=0, column=0, sticky='w', padx=(5, 2), pady=3)
    ttk.Combobox(geom, textvariable=v['pile_type'], values=('Cọc chống', 'Cọc treo'),
                 state='readonly', width=12).grid(row=0, column=1, sticky='w', pady=3)
    short_entry = field(geom, 0, 1, 'Bước cọc ngắn κ (m):', 's_short', width=12)
    field(geom, 0, 2, 'Góc ma sát đắp φ (°):', 'phi_dap', width=12)
    for row, items in enumerate((
        (('Đường kính cọc D (m):', 'D'), ('Khoảng cách cọc s (m):', 's'), ('Chiều dài cọc Lc (m):', 'Lc')),
        (('Cường độ cọc qu (T/m²):', 'qu'), ('Mô đun đàn hồi Ec (T/m²):', 'Ec'), ('Es = 250Co (T/m²):', 'Es')),
        (('Hệ số an toàn Fs:', 'Fs'), ('GH lún tổng S (cm):', 'settlement_limit'), ('Góc ma sát vòm θ (°):', 'theta'))
    ), 1):
        for col, (label, key) in enumerate(items):
            field(geom, row, col, label, key, readonly=key=='Es', width=12)

    ttk.Label(geom,text='Lớp đất lấy Co:').grid(row=4,column=0,sticky='w',padx=5)
    es_selector=ttk.Combobox(geom,textvariable=v['es_layer_idx'],state='readonly',width=26)
    es_selector.grid(row=4,column=1,columnspan=3,sticky='w',padx=5)
    field(geom,4,2,'Giới hạn chênh lún [ΔS] (cm):','differential_limit_cm',width=12)
    frame_pattern = ttk.Frame(geom)
    frame_pattern.grid(row=5, column=0, columnspan=8, sticky='w', padx=5, pady=3)
    ttk.Label(frame_pattern, text='Sơ đồ bố trí cọc:').pack(side='left', padx=(0, 5))
    ttk.Combobox(frame_pattern, textvariable=v['pattern'],
                 values=('Lưới vuông', 'Lưới tam giác', 'Lưới chữ nhật', 'Hai trục'),
                 state='readonly', width=15).pack(side='left')
    ttk.Label(frame_pattern, 
              text='   Es = 250 × Co của lớp được chọn; ΔS = |Ssoil − Scol| ≤ [ΔS].',
              foreground='#005580', font=(UI_FONT, 9, 'italic')).pack(side='left')

    def pile_type_suggest_theta(*_):
        try:
            phi_val = float(v['phi_dap'].get())
        except Exception:
            phi_val = 30.0
            
        if v['pile_type'].get() == 'Cọc chống':
            theta_calc = max(1.0, min(89.0, 90.0 - phi_val))  #[cite: 9]
            v['theta'].set(f"{theta_calc:.2f}")
        else:
            v['theta'].set("80.0")  #[cite: 9]

    v['pile_type'].trace_add('write', pile_type_suggest_theta)

    # 3. GIẢI PHÁP GIA CƯỜNG
    selector = ttk.LabelFrame(root, text='3. Giải pháp gia cường phía trên đầu cọc (ALiCC / BS 8006)')
    selector.pack(fill='x', padx=10, pady=4)
    
    frame_mat_select = ttk.Frame(selector)
    frame_mat_select.pack(fill='x', padx=5, pady=5)
    ttk.Label(frame_mat_select, text='Chọn vật liệu:').pack(side='left', padx=(0, 10))
    ttk.Combobox(frame_mat_select, textvariable=v['kind'], state='readonly', width=25,
                 values=(REINFORCEMENT_NONE, REINFORCEMENT_FABRIC,
                         REINFORCEMENT_GRID, REINFORCEMENT_SURFACE)).pack(side='left')
                         
    mats_container = ttk.Frame(selector)
    mats_container.pack(fill='x')

    # Vải/lưới địa
    geo_box = ttk.Frame(mats_container)
    geo_material_entries = {}
    for row, items in enumerate((
        (('Độ giãn dài cho phép ε (%):', 'eps'), ('Góc ma sát đất đắp φ\' (°):', 'phi_dap'), ('Cường độ vải Tmax (kN/m):', 'Tmax'), ('Số lớp gia cường n:', 'n_layer')),
        (('Hệ số sx fm11:', 'fm11'), ('Hệ số n.suy fm12:', 'fm12'), ('Hệ số thi công fm21:', 'fm21'), ('Hệ số MT fm22:', 'fm22')),
        (('Hệ số kinh tế fn:', 'fn'), ('Hệ số tải đắp f_fs:', 'f_fs'), ('Hệ số tải xe f_q:', 'f_q'), ('Độ giãn dài tối đa εmax (%):', 'eps_max'))
    )):
        for col, (label, key) in enumerate(items): 
            if key:
                geo_material_entries[key] = field(geo_box, row, col, label, key, width=12)

    geo_material_entries['T_char_kn'] = field(geo_box, 3, 0, 'Tchar lưới địa (kN/m):', 'T_char_kn', width=12)
    ttk.Label(geo_box, text='Vải 400×400: nhập Tmax = 400 kN/m. Tchar = 0,9 × ε × Tmax / εmax; ε là độ giãn dài cho phép (%).',
              foreground='#92400E').grid(row=3, column=0, columnspan=8, sticky='w', pady=(5, 0))

    # Đệm xi măng
    surface_box = ttk.Frame(mats_container)
    for row, items in enumerate((
        (('Chiều dày đệm Hse (m):', 'surface_h'), ('SCT đất nền qa (T/m²):', 'q_allow'), ('Kháng cắt đệm τu (T/m²):', 'shear_strength'), ('Kháng cắt nền Su (T/m²):', 'su_soil')),
        (('Cường độ đệm quse (T/m²):', 'qu_surface'), ('Hệ số ĐH đệm α:', 'alpha'), ('Tỷ số kéo uốn:', 'bend_ratio'), ('', '')),
        (('Mô đun nền Esa (T/m²):', 'Esa'), ('Chỉ số SPT-N nền:', 'spt_n'), ('', ''), ('', ''))
    )):
        for col, (label, key) in enumerate(items): 
            if key: field(surface_box, row, col, label, key, width=12)

    # NÚT ĐIỀU KHIỂN & KẾT QUẢ TỔNG HỢP
    controls = ttk.Frame(root)
    controls.pack(fill='x', padx=10, pady=(10, 5))
    
    btn_calc = tk.Button(controls, text='Kiểm toán cọc trộn sâu', **btn_style_teal)
    btn_calc.pack(side='left', padx=(0, 10))
    
    btn_opt = tk.Button(controls, text='Tính toán tối ưu', 
                        bg='#0C6175', fg='white', font=(UI_FONT, 10, 'bold'),
                        activebackground='#0284C7', activeforeground='white', padx=12, pady=7,
                        relief='flat', cursor='hand2')
    btn_opt.pack(side='left')

    result_tabs = ttk.Notebook(root)
    result_tabs.pack(fill='both', expand=True, padx=10, pady=5)
    outputs = {}
    
    for title, key in (('Kết quả 1: Lún CDM', 'settlement'),
                      ('Kết quả 2: Ứng suất (ALiCC)', 'pile'),
                      ('Kết quả 3: Vật liệu gia cường', 'material')):
        panel = ttk.Frame(result_tabs)
        result_tabs.add(panel, text=title)
        
        body = tk.Text(panel, height=18, width=110, wrap='word', state='disabled', 
                       font=(UI_FONT, 11), bg='#F0F0F0', relief='flat')
        body.pack(fill='both', expand=True, padx=10, pady=10)
        
        body.tag_configure('title', font=(UI_FONT, 12, 'bold'), foreground='#003399', spacing1=5, spacing3=5)
        body.tag_configure('bold', font=(UI_FONT, 11, 'bold'), foreground='black')
        body.tag_configure('ok', font=(UI_FONT, 11, 'bold'), foreground='#008000')
        body.tag_configure('ng', font=(UI_FONT, 11, 'bold'), foreground='#CC0000')
        body.tag_configure('blue_bold', font=(UI_FONT, 11, 'bold'), foreground='#003399')
        body.tag_configure('italic', font=(UI_FONT, 11, 'italic'), foreground='#555555')
        
        outputs[key] = body

    def display(key, lines):
        body = outputs[key]
        body.configure(state='normal')
        body.delete('1.0', 'end')
        for item in lines:
            if isinstance(item, tuple):
                body.insert('end', item[0] + '\n', item[1])
            else:
                body.insert('end', item + '\n')
        body.configure(state='disabled')

    loaded_project = [None]
    loaded_scope = [None]
    restoring = [False]
    auto_fields = {'Htk', 'Hkcad', 'Hbl', 'Htt', 'H', 'gamma', 'Es'}
    defaults = {key: var.get() for key, var in v.items() if key not in auto_fields}

    def scoped_states(project):
        states = getattr(project, 'alicc_inputs', {}) or {}
        return ({'Nền đường': states} if 'D' in states else dict(states))

    def save_inputs(*_):
        if not restoring[0] and getattr(app, 'project', None) is not None:
            states = scoped_states(app.project)
            scope = app.cdm_scope_var.get()
            current = {key: var.get() for key, var in v.items()
                       if key not in auto_fields}
            if current != states.get(scope):
                states[scope] = current
                app.project.alicc_inputs = states
                app._cdm_reports.pop('alicc', None)

    def refresh_project():
        project = app.cdm_calculation_project()
        emb = get_project_embankment_params(project)
        if (getattr(app, 'project', None) is not loaded_project[0] or
                app.cdm_scope_var.get() != loaded_scope[0]):
            restoring[0] = True
            saved = scoped_states(app.project).get(app.cdm_scope_var.get(), defaults)
            for key, var in v.items():
                if key not in auto_fields:
                    var.set(saved.get(key, defaults[key]))
            restoring[0] = False
            loaded_project[0] = getattr(app, 'project', None)
            loaded_scope[0] = app.cdm_scope_var.get()
        h = emb['Htk'] + emb['Hkcad']
        htt = h + emb['Hbl']
        for key, val in (('Htk', emb['Htk']), ('Hkcad', emb['Hkcad']),
                         ('Hbl', emb['Hbl']), ('Htt', htt),
                         ('H', htt if v['pile_type'].get() == 'Cọc treo' else h),
                         ('gamma', emb['gamma_fill'])):
            v[key].set(f'{val:.2f}')
        refresh_es()

    def refresh_es(*_):
        project=app.cdm_calculation_project()
        choices=tuple(str(i+1)+'. '+soil.name for i,soil in enumerate(project.soils)) if project else ()
        es_selector.configure(values=choices)
        try:
            index=es_layer_index(v['es_layer_idx'].get())
            if index<0 or index>=len(choices):index=0
            if choices and v['es_layer_idx'].get()!=choices[index]:v['es_layer_idx'].set(choices[index])
            v['Es'].set(f"{alicc_soil_modulus(project,index)['Es']:.2f}")
        except ValueError:v['Es'].set('')
    v['es_layer_idx'].trace_add('write',refresh_es)

    def pattern_changed(*_):
        if short_entry:
            short_entry.configure(state='normal' if v['pattern'].get() == 'Lưới chữ nhật' else 'disabled')
    v['pattern'].trace_add('write', pattern_changed)
    pattern_changed()

    def kind_changed(*_):
        kind = v['kind'].get()
        for key in ('Tmax', 'eps_max'):
            geo_material_entries[key].configure(state='disabled' if kind == REINFORCEMENT_GRID else 'normal')
        geo_material_entries['T_char_kn'].configure(state='normal' if kind == REINFORCEMENT_GRID else 'disabled')
        geo_box.pack_forget()
        surface_box.pack_forget()
        if kind in (REINFORCEMENT_FABRIC, REINFORCEMENT_GRID):
            geo_box.pack(fill='x', padx=5, pady=5)
            btn_opt.configure(text=' ⟳ TỐI ƯU HÓA (Lc, s, Số lớp vải) ')
        elif kind == REINFORCEMENT_SURFACE:
            surface_box.pack(fill='x', padx=5, pady=5)
            btn_opt.configure(text=' ⟳ TỐI ƯU HÓA (Lc, s, Chiều dày đệm) ')
        else:
            btn_opt.configure(text=' ⟳ TỐI ƯU HÓA (Lc, s) ')
            
    v['kind'].trace_add('write', kind_changed)
    kind_changed()
    def reload_ai_inputs():
        loaded_project[0]=None
        refresh_project()
    app._reload_alicc_ai_inputs=reload_ai_inputs
    app._capture_alicc_state = save_inputs
    for key, var in v.items():
        if key not in auto_fields:
            var.trace_add('write', save_inputs)
    refresh_project()

    def payload(include_material=True):
        app.collect_cdm_inputs()
        refresh_project()
        project = app.cdm_calculation_project()
        if project is None:
            raise ValueError('Cần mở dự án nền đường trước khi tính toán ALiCC.')
        def val(key, label=None): return number(v[key].get(), label or key)
        params = {key: val(key) for key in ('D', 's', 'Lc', 'H', 'gamma', 'Ec', 'Es', 'qu', 'Fs', 'theta')}
        params.update(pattern=v['pattern'].get(), pile_type=v['pile_type'].get())
        params['es_layer_index']=es_layer_index(v['es_layer_idx'].get())
        params['Es']=alicc_soil_modulus(project,params['es_layer_index'])['Es']
        params['differential_limit_cm']=val('differential_limit_cm') if v['differential_limit_cm'].get().strip() else None
        
        if params['pattern'] == 'Lưới chữ nhật': params['s_short'] = val('s_short')
        limit = val('settlement_limit')
        if limit <= 0: raise ValueError('Độ lún tổng cho phép phải > 0.')
        
        geo = {'kind': v['kind'].get() if include_material else REINFORCEMENT_NONE,
               'phi_dap': val('phi_dap')}
        surface = {'enabled': include_material and geo['kind'] == REINFORCEMENT_SURFACE}
        
        if geo['kind'] in (REINFORCEMENT_FABRIC, REINFORCEMENT_GRID):
            layers = val('n_layer')
            if layers < 1 or layers != int(layers):
                raise ValueError('Số lớp vải/lưới địa kỹ thuật phải là số nguyên dương.')
            geo.update({key: val(key) for key in ('phi_dap', 'fm11', 'fm12', 'fm21', 'fm22', 'fn', 'f_fs', 'f_q')})
            if geo['kind'] == REINFORCEMENT_GRID:
                geo.update(T_char_kn=val('T_char_kn'), Tmax=400.0, eps_max=10.0)
            else:
                geo.update(Tmax=val('Tmax'), eps_max=val('eps_max'))
            geo['eps'] = val('eps')
            geo['n_layer'] = int(layers)
            
        if surface['enabled']:
            surface.update(thickness=val('surface_h'), q_allow=val('q_allow'),
                           shear_strength=val('shear_strength'), su_soil=val('su_soil'),
                           qu_surface=val('qu_surface'), alpha=val('alpha'),
                           bend_ratio=val('bend_ratio'), Esa=val('Esa'), spt_n=val('spt_n'))
        return project, params, {'qH': val('qH')}, geo, surface, limit

    def calculate():
        project, p, stress, geo, surface, limit = payload()
        r = calculate_alicc_road(p, stress, geo, surface, project)
        app._cdm_reports['alicc'] = {
            'result': r, 'params': p, 'stress_params': stress,
            'geo_params': geo, 'surface_params': surface,
            'limit': limit, 'scope': app.cdm_scope_var.get(),
            'project_snapshot': deepcopy(app.project)}
        app._cdm_active_method = 'alicc'
        if hasattr(app, 'show_cdm_quick_result'):
            app.show_cdm_quick_result(app._cdm_reports['alicc'], 'alicc')
        app.draw_live_diagram()
        
        # --- TAB 1: LÚN ---
        lines_1 = [
            (f"A. KIỂM TOÁN ĐỘ LÚN ({p['pile_type'].upper()})", 'title'),
            f"Tỷ lệ diện tích thay thế (ap) = {r['ap']*100:.2f}%",
            f"Mô đun đàn hồi tương đương (Eeq) = {r['Eeq']:.2f} T/m²",
            f"Độ lún bản thân khối gia cố (S1) = {r['S1_cm']:.2f} cm",
            f"Độ lún các lớp đất dưới mũi cọc (S2) = {r['S2_cm']:.2f} cm (gồm {len(r['settlement_rows'])} phân tố)",
            ""
        ]
        tong_lun = r['S_total_cm']
        lines_1.append((f"[{p['pile_type']}] Độ lún dư ΔSr = {tong_lun:.2f} cm <= {limit:.2f} cm "
                        f"=> {'ĐẢM BẢO YÊU CẦU' if tong_lun <= limit else 'KHÔNG ĐẠT'}", 
                        'ok' if tong_lun <= limit else 'ng'))
        
        lines_1.extend([
            f"Es = 250 × Co = 250 × {r['Co_used']:.4g} = {r['Es_used']:.2f} T/m²; lớp {r['es_layer_no']}: {r['es_layer_name']}",
            f"Lún đất Ssoil = {r['Ssoil_cm']:.2f} cm; lún cọc Scol = {r['Scol_cm']:.2f} cm",
            (f"ΔS = |Ssoil − Scol| = {r['differential_cm']:.2f} cm ≤ [ΔS] = {r['differential_limit_cm']:.2f} cm: "+('ĐẠT' if r['differential_ok'] else 'CHƯA ĐẠT'),'ok' if r['differential_ok'] else 'ng') if r['differential_checked'] else ('Chưa nhập [ΔS]: CHƯA KIỂM TRA CHÊNH LÚN','ng')])

        # --- TAB 2: ỨNG SUẤT ---
        lines_2 = [
            (f"Chiều cao tính toán ALiCC (H = Htt): {p['H']:.2f} m", 'blue_bold'),
            (f"Hoạt tải qH: {stress['qH']:.2f} T/m²", 'bold'),
            "",
            ("B. ỨNG SUẤT ĐẤT NỀN", 'title'),
            f"Ứng suất đất giữa cọc P_soil = {r['Psoil']:.2f} T/m²"

        ]
        
        # --- TAB 3: GIA CƯỜNG (CẮT THỦNG & KÉO UỐN) ---
        kind = geo['kind']
        if kind in (REINFORCEMENT_FABRIC, REINFORCEMENT_GRID):
            g = r['reinforcement']
            lines_3 = [
                (f"KIỂM TOÁN VẬT LIỆU GIA CƯỜNG - {kind.upper()}", 'title'),
                f"Lực kéo do lún lệch võng (WT): {g['WT']:.2f} T/m",
                f"Lực kéo căng màng (Trp): {g['Trp']:.2f} T/m",
                f"Lực kéo do áp lực ngang (Tds): {g['Tds']:.2f} T/m",
                "",
                (f"Tổng lực kéo lớn nhất (Tr = Trp + Tds): {g['Tr']:.2f} T/m", 'blue_bold'),
                ((f"Tchar = {g['T_allow_kN_m']:.2f} kN/m = {g['T_char']:.2f} T/m (nhập trực tiếp)" if kind == REINFORCEMENT_GRID else f"Tchar = 0,9 × {geo['eps']:.2f} × {geo['Tmax']:.2f} / {geo['eps_max']:.2f} = {g['T_allow_kN_m']:.2f} kN/m = {g['T_char']:.2f} T/m"), 'bold'),
                (f"Cường độ thiết kế chịu lực (Td/fn): {g['Td_fn']:.2f} T/m", 'bold'),
                (f"=> Đánh giá: Tr <= Td/fn => {'ĐẢM BẢO KHẢ NĂNG CHỊU LỰC' if g['ok'] else 'KHÔNG ĐẠT'}", 
                 'ok' if g['ok'] else 'ng')
            ]
        elif kind == REINFORCEMENT_SURFACE:
            sf = r['surface']
            lines_3 = [
                (f"KIỂM TOÁN ĐỆM GIA CỐ XI MĂNG (ALiCC)", 'title'),
                f"Chiều dày đệm (Hse): {surface['thickness']:.2f} m | Nhịp tĩnh không (l = λ - d): {sf['clear_l']:.2f} m[cite: 10]",
                f"Mômen quán tính Ise: {sf['Ise']:.2f} m⁴ | Mômen kháng uốn Wse: {sf['Wse']:.2f} m³[cite: 10]",
                "-------------------------------------------------------------------------------------------------",
                (f"1. KIỂM TOÁN CẮT THỦNG", 'title'),
                f"Sức chịu tải tịnh nền (Psoil − qa): {sf['net_pressure']:.2f} T/m²[cite: 2]",
                f"Ứng suất cắt phát sinh (τ_se): {sf['shear']:.2f} T/m²[cite: 2]",
                f"Sức kháng cắt cho phép [τ] = τu/1.2: {sf['shear_allow']:.2f} T/m²",
                (f"=> Đánh giá Cắt thủng (τ_se <= [τ]): {'ĐẢM BẢO YÊU CẦU' if sf['shear_ok'] else 'KHÔNG ĐẠT'}", 
                 'ok' if sf['shear_ok'] else 'ng'),
                "-------------------------------------------------------------------------------------------------",
                (f"2. KIỂM TOÁN ỨNG SUẤT KÉO DO UỐN (THEO CHỈ DẪN KỸ THUẬT)", 'title'),
                f"Cường độ đệm quse = {surface['qu_surface']:.2f} T/m² | Hệ số ĐH Ese = {sf['ese']:.2f} T/m²[cite: 2]",
                f"Ứng suất kéo uốn cho phép [σ_base] = {sf['bending_allow']:.2f} T/m² (FS = {sf['Fs_surface']:.2f})[cite: 2, 10]",
                "",
                (f"Trường hợp A: Có xét ảnh hưởng của nền đàn hồi (Hệ số nền k = {sf['kv']:.2f} T/m³)[cite: 10]:", 'bold'),
                f"  + Hệ số đặc trưng dầm α = {sf['alpha_d']:.2f} (1/m)[cite: 10]",
                f"  + Momen uốn lớn nhất M_max = {sf['M_max_k']:.2f} T·m[cite: 10]",
                f"  + Ứng suất kéo lớn nhất σ_se = {sf['sigma_k']:.2f} T/m²[cite: 10]",
                (f"  => Kiểm tra (σ_se <= [σ_base]): {'ĐẠT' if sf['ok_k'] else 'KHÔNG ĐẠT'}[cite: 10]", 
                 'ok' if sf['ok_k'] else 'ng'),
                "",
                (f"Trường hợp B: Bỏ qua ảnh hưởng nền đàn hồi (Dầm đơn giản, M_max = Ps·l²/8)[cite: 10]:", 'bold'),
                f"  + Momen uốn lớn nhất M_max = {sf['M_max_no_k']:.2f} T·m[cite: 10]",
                f"  + Ứng suất kéo lớn nhất σ_se = {sf['sigma_no_k']:.2f} T/m²[cite: 10]",
                (f"  => Kiểm tra (σ_se <= [σ_base]): {'ĐẠT' if sf['ok_no_k'] else 'KHÔNG ĐẠT'}[cite: 10]", 
                 'ok' if sf['ok_no_k'] else 'ng')
            ]
        else: 
            lines_3 = [("Chưa cấu hình giải pháp gia cường phía trên đầu cọc.", 'italic')]
            
        display('settlement', lines_1)
        display('pile', lines_2)
        display('material', lines_3)
        app.report_result('ALiCC · kiểm toán',
                          f'S = {r["S_total_cm"]:.2f} cm; '
                          f'aₚ = {r["ap"]:.2f}; '
                          f'P_cọc = {r["Pcol"]:.2f} T/m².\n'
                          f'Kết quả kiểm tra: {app.card_status.cget("text")}.')
        return r

    def run_calculation():
        try: calculate()
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            app.report_result('ALiCC · kiểm toán', str(exc), error=True)
            messagebox.showerror('Lỗi Tính Toán ALiCC', str(exc), parent=app)

    lc_opt_step = tk.StringVar(value='0.5')
    ttk.Label(frame_pattern, text='Bước tối ưu Lc (m):').pack(side='left', padx=(10, 2))
    ttk.Entry(frame_pattern, textvariable=lc_opt_step, width=6).pack(side='left')

    def run_optimization():
        if hasattr(app, 'require_full_license') and not app.require_full_license():
            return
        """Tự động tối ưu hóa đồng thời Chiều dài cọc Lc, Khoảng cách cọc s và Giải pháp gia cường."""
        try:
            refresh_project()
            project = getattr(app, 'project', None)
            if project is None:
                raise ValueError('Cần mở dự án nền đường trước khi thực hiện tối ưu hóa.')

            def val(key, label=None): return number(v[key].get(), label or key)
            d = val('D')
            h = val('H')
            limit_s = val('settlement_limit')
            kind = v['kind'].get()
            pattern = v['pattern'].get()

            # 1. Xác định phạm vi quét chiều dài cọc Lc (từ 5.0m đến chiều sâu khảo sát, bước 0.5m)
            max_depth = 18.0
            if project and getattr(project, 'soils', None):
                max_depth = min(22.0, sum(getattr(s, 'thickness', 0.0) for s in project.soils))
            lc_min = 5.0
            lc_max = max(lc_min + 1.0, max_depth)
            lc_step = float(lc_opt_step.get().replace(',', '.'))
            if not math.isfinite(lc_step) or lc_step <= 0:
                raise ValueError('Bước tối ưu Lc phải là số dương hữu hạn.')
            lc_steps = []
            curr_l = lc_min
            while curr_l <= lc_max:
                lc_steps.append(round(curr_l, 8))
                curr_l += lc_step

            # 2. Xác định phạm vi quét khoảng cách cọc s (từ d + 0.3m đến min(h - 0.05, 2.5m), bước 0.1m)
            s_min = round(d + 0.3, 2)
            s_max = round(min(h - 0.05, 2.5), 2)
            if s_max < s_min:
                s_max = s_min + 0.2
            s_steps = []
            curr_s = s_min
            while curr_s <= s_max:
                s_steps.append(round(curr_s, 2))
                curr_s += 0.1

            best_solution = None
            best_cost = float('inf')

            orig_state = {
                's': v['s'].get(),
                'Lc': v['Lc'].get(),
                'n_layer': v['n_layer'].get(),
                'surface_h': v['surface_h'].get()
            }

            # 3. Tiến hành quét tổ hợp đa biến
            for s_try in s_steps:
                v['s'].set(f"{s_try:.2f}")
                if pattern == 'Lưới chữ nhật':
                    v['s_short'].set(f"{max(d + 0.1, s_try - 0.2):.2f}")

                for lc_try in lc_steps:
                    v['Lc'].set(f"{lc_try:.2f}")

                    if kind in (REINFORCEMENT_FABRIC, REINFORCEMENT_GRID):
                        for n_try in range(1, 6):
                            v['n_layer'].set(str(n_try))
                            try:
                                pr, p, st, g, sf, lim = payload(include_material=True)
                                r = calculate_alicc_road(p, st, g, sf, pr)
                                rein = r.get('reinforcement', {})
                                if r['pile_ok'] and r.get('differential_ok') is True and r['S_total_cm'] <= lim and rein.get('ok', False):
                                    # Hàm mục tiêu: Giảm thiểu thể tích CDM (ap * Lc) + trọng số vải địa
                                    cost = r['ap'] * lc_try + 0.08 * n_try
                                    if cost < best_cost:
                                        best_cost = cost
                                        best_solution = {
                                            's': s_try, 'Lc': lc_try,
                                            'n_layer': n_try, 'surface_h': v['surface_h'].get(),
                                            'result': r
                                        }
                                    break  # Với (s, Lc) này đã tìm được n nhỏ nhất đạt yêu cầu
                            except Exception:
                                continue

                    elif kind == REINFORCEMENT_SURFACE:
                        for hse_try in [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00]:
                            v['surface_h'].set(f"{hse_try:.2f}")
                            try:
                                pr, p, st, g, sf, lim = payload(include_material=True)
                                r = calculate_alicc_road(p, st, g, sf, pr)
                                surf = r.get('surface', {})
                                if r['pile_ok'] and r.get('differential_ok') is True and r['S_total_cm'] <= lim and surf.get('shear_ok', False) and surf.get('ok_k', False):
                                    cost = r['ap'] * lc_try + 0.5 * hse_try
                                    if cost < best_cost:
                                        best_cost = cost
                                        best_solution = {
                                            's': s_try, 'Lc': lc_try,
                                            'n_layer': v['n_layer'].get(), 'surface_h': f"{hse_try:.2f}",
                                            'result': r
                                        }
                                    break
                            except Exception:
                                continue

                    else:  # REINFORCEMENT_NONE
                        try:
                            pr, p, st, g, sf, lim = payload(include_material=False)
                            r = calculate_alicc_road(p, st, g, sf, pr)
                            if r['pile_ok'] and r.get('differential_ok') is True and r['S_total_cm'] <= lim:
                                cost = r['ap'] * lc_try
                                if cost < best_cost:
                                    best_cost = cost
                                    best_solution = {
                                        's': s_try, 'Lc': lc_try,
                                        'n_layer': v['n_layer'].get(), 'surface_h': v['surface_h'].get(),
                                        'result': r
                                    }
                        except Exception:
                            continue

            # 4. Áp dụng kết quả tối ưu
            if best_solution:
                v['s'].set(f"{best_solution['s']:.2f}")
                v['Lc'].set(f"{best_solution['Lc']:.2f}")
                if kind in (REINFORCEMENT_FABRIC, REINFORCEMENT_GRID):
                    v['n_layer'].set(str(best_solution['n_layer']))
                elif kind == REINFORCEMENT_SURFACE:
                    v['surface_h'].set(best_solution['surface_h'])

                calculate()
                r_best = best_solution['result']
                
                detail = [
                    "ĐÃ TÌM THẤY BỘ THÔNG SỐ TỐI ƯU NHẤT:",
                    "",
                    f"• Khoảng cách cọc tối ưu: s = {best_solution['s']:.2f} m (ap = {r_best['ap']*100:.2f}%)",
                    f"• Chiều dài cọc tối ưu: Lc = {best_solution['Lc']:.2f} m"
                ]
                if kind in (REINFORCEMENT_FABRIC, REINFORCEMENT_GRID):
                    detail.append(f"• Số lớp vải/lưới tối ưu: n = {best_solution['n_layer']} lớp")
                    rein = r_best.get('reinforcement', {})
                    detail.append(f"  (Lực kéo Tr = {rein['Tr']:.2f} T/m <= Td/fn = {rein['Td_fn']:.2f} T/m)")
                elif kind == REINFORCEMENT_SURFACE:
                    detail.append(f"• Chiều dày đệm tối ưu: Hse = {best_solution['surface_h']} m")
                    surf = r_best.get('surface', {})
                    detail.append(f"  (Cắt thủng τ = {surf['shear']:.2f} T/m² <= Cho phép; Uốn σ = {surf['sigma_k']:.2f} T/m² <= Cho phép)")

                detail.extend([
                    "",
                    "KIỂM TOÁN TỔNG THỂ:",
                    f"• Tổng lún S = {r_best['S_total_cm']:.2f} cm <= [S] = {limit_s:.2f} cm (ĐẠT)",
                    f"• Ứng suất cọc P_col = {r_best['Pcol']:.2f} T/m² <= [qu] = {p['qu']/p['Fs']:.2f} T/m² (ĐẠT)",
                    f"• Suất hao CDM: {r_best['ap']*best_solution['Lc']:.2f} m³ cọc / m² nền đường"
                ])
                app.report_result('ALiCC · tối ưu', '\n'.join(detail))
            else:
                for k, val_orig in orig_state.items():
                    v[k].set(val_orig)
                calculate()
                messagebox.showwarning('Tối ưu hóa ALiCC', 
                                       'Không tìm thấy bộ thông số nào thỏa mãn đồng thời các điều kiện (Lún, Cường độ cọc, Gia cường) trong phạm vi quét!\n\n'
                                       'Gợi ý kỹ thuật:\n'
                                       '• Tăng cường độ cọc qu hoặc tăng cường độ vải Tmax.\n'
                                       '• Nới lỏng giới hạn lún cho phép hoặc tăng cường độ đệm xi măng.', parent=app)

        except Exception as exc:
            messagebox.showerror('Lỗi tối ưu hóa', str(exc), parent=app)

    def run_hbl():
        try:
            project = app.cdm_calculation_project()
            if project is None or v['pile_type'].get() != 'Cọc treo':
                raise ValueError('Chức năng này yêu cầu chọn "Cọc treo" và mở dự án đã có dữ liệu địa chất.')
            emb = get_project_embankment_params(project)
            base_h = emb['Htk'] + emb['Hkcad']
            def trial():
                pr, p, s, g, sf, _ = payload(include_material=False)
                p['H'] = base_h + project.h_bl
                return calculate_alicc_road(p, s, g, sf, project)
            hbl, count = solve_alicc_hbl(project, base_h, trial)
            if app.cdm_scope_var.get() == 'Nền mở rộng':
                app.project.expansion_h_bl = hbl
            refresh_project()
            try: calculate()
            except ValueError as exc:
                display('material', [(f'Đã tính Hbl = {hbl:.2f} m; Cảnh báo vật liệu: {exc}', 'italic')])
            app.report_result('ALiCC · bù lún',
                                f'Chiều cao bù lún (Hbl) = {hbl:.2f} m (đạt hội tụ sau {count} vòng lặp).\n'
                                f'Chiều cao tổng (Htt) = {base_h + hbl:.2f} m.')
        except (ValueError, ZeroDivisionError, OverflowError) as exc:
            refresh_project()
            messagebox.showerror('Lỗi Tính Hbl - ALiCC', str(exc), parent=app)

    btn_calc.configure(command=lambda: app.run_processing('Kiểm toán ALiCC', run_calculation))
    btn_opt.configure(command=lambda: app.run_processing('Tối ưu ALiCC', run_optimization))
    btn_hbl.configure(command=lambda: app.run_processing('Bù lún ALiCC', run_hbl))
    def clear_results():
        for key in outputs:
            display(key, [('Chờ tính toán theo phạm vi đã chọn', 'italic')])

    return refresh_project, clear_results
