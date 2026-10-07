"""Mục 9: Tổng hợp kết quả đã tính của các phương án xử lý."""
from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import asdict, dataclass
from model import stage_schedule


@dataclass
class CalculatedOption:
    group_id: int
    group_name: str
    opt_name: str
    opt_params_desc: str
    residual_cm: float
    limit_cm: float
    time_desc: str
    cost_level: str
    is_pass: bool
    tech_notes: str
    apply_payload: dict
    source_project: object


def project_signature(project) -> str:
    """Nhận dạng số liệu chung; phương án và thông số xử lý có thể khác nhau."""
    keys = ('name', 'station', 'station_from', 'station_to', 'h_design', 'h_kcad',
            'h_bl', 'crest_half_width', 'slope_m', 'gamma_fill', 'water_depth',
            'sublayer', 'method', 'settlement_factor', 'expansion_side',
            'expansion_width', 'expansion_h_design', 'expansion_h_kcad',
            'expansion_slope_m', 'expansion_gamma_fill', 'main_treatment',
            'main_replacement_depth', 'main_bamboo_depth', 'main_cajuput_depth',
            'main_cdm_depth', 'main_age_days', 'main_observed_residual_cm',
            'assessment_days', 'residual_limit_cm')
    values = [getattr(project, key, None) for key in keys]
    values.extend(([asdict(soil) for soil in project.soils],
                   [asdict(soil) for soil in project.main_soils]))
    return json.dumps(values, sort_keys=True, ensure_ascii=False, default=str)


def collect_calculated_options(app, enabled=(True, True, True, True)):
    """Chỉ lấy kết quả đã tính; trả về (phương án, nhóm thiếu/cũ)."""
    project = app.project
    signature = project_signature(project)
    limit = project.residual_limit_cm
    options, missing = [], []

    def snapshot(key, label):
        row = getattr(app, '_choice_group_results', {}).get(key)
        if row and project_signature(row['project']) == signature:
            return row
        missing.append(label + (' (số liệu chung đã thay đổi)' if row else ' (chưa tính)'))
        return None

    if enabled[0]:
        row = snapshot('natural', 'Lún khi chưa xử lý')
        if row:
            src, values = row['project'], row['results']
            residual = max((r['lún_dư_sau_dự_báo_cm'] if row['kind'] == 'expansion'
                            else r['Sc_dư_cm'] for r in values), default=0.0)
            scope = 'Nền mở rộng' if src.expansion_width else 'Nền đường'
            options.append(CalculatedOption(
                1, 'Nền chưa xử lý', 'Lún khi chưa xử lý',
                f'{scope}; {len(values)} vị trí đã tính', residual, limit,
                f'{row["days"]:.0f} ngày', 'Chưa định giá', residual <= limit,
                f'Lún dư lớn nhất tại các vị trí = {residual:.2f} cm',
                {'treatment_group': 'natural', 'scope': scope}, deepcopy(src)))

    if enabled[1]:
        row = snapshot('mechanical', 'Thay thế & gia cường cơ học')
        if row:
            src, values = row['project'], row['results']
            residual = max((max(0.0, r['Sc_cuối_cm'] - r['Sc_t_cm'])
                            for r in values), default=0.0)
            components = [name for depth, name in (
                (src.replacement_depth, 'Đào thay đất'),
                (src.bamboo_depth, 'Cọc tre'),
                (src.cajuput_depth, 'Cừ tràm')) if depth > 0]
            name = ' + '.join(components) or 'Chờ lún'
            desc = (f'Đào {src.replacement_depth:.2f} m; tre {src.bamboo_depth:.2f} m; '
                    f'cừ tràm {src.cajuput_depth:.2f} m')
            if src.mechanical_surcharge:
                desc += f'; gia tải {src.surcharge_height:.2f} m'
            options.append(CalculatedOption(
                2, 'Thay thế & gia cường cơ học', name, desc,
                residual, limit, f'{row["days"]:.0f} ngày', 'Chưa định giá',
                residual <= limit,
                f'Lún dư lớn nhất = {residual:.2f} cm; {len(values)} vị trí',
                {'treatment_group': 'mechanical',
                 'replacement_depth': src.replacement_depth,
                 'bamboo_depth': src.bamboo_depth,
                 'cajuput_depth': src.cajuput_depth,
                 'bamboo_density': 25.0, 'cajuput_density': 25.0,
                 'treatment_depth': src.replacement_depth + max(src.bamboo_depth, src.cajuput_depth),
                 'surcharge_height': src.surcharge_height if src.mechanical_surcharge else 0.0},
                deepcopy(src)))

    if enabled[2]:
        row = snapshot('drainage', 'Cố kết & thoát nước')
        if row:
            src, values = row['project'], row['results']
            residual = max((max(0.0, r['Sc_cuối_cm'] - r['Sc_t_cm'])
                            for r in values), default=0.0)
            u_min = min((r['U_%'] for r in values), default=0.0)
            is_radial = src.treatment.startswith(('PVD', 'SD'))
            ok = residual <= limit and u_min > 90.0
            drain_length = src.drain_length or sum(s.thickness for s in src.soils)
            desc = (f'{src.treatment}; d={src.drain_spacing:.2f} m; '
                    f'L={drain_length:.2f} m; gia tải={src.surcharge_height:.2f} m'
                    if is_radial else src.treatment)
            options.append(CalculatedOption(
                3, 'Cố kết & thoát nước', src.treatment, desc,
                residual, limit, f'{row["days"]:.0f} ngày', 'Chưa định giá', ok,
                f'Lún dư lớn nhất = {residual:.2f} cm; U nhỏ nhất = {u_min:.1f}%',
                {'treatment_group': 'drainage', 'treatment': src.treatment,
                 'drain_spacing': src.drain_spacing, 'drain_length': drain_length,
                 'drain_pattern': src.drain_pattern,
                 'wait_days': max(0.0, row['days']-stage_schedule(src)[-1]['kết_thúc']),
                 'surcharge_height': src.surcharge_height if 'gia tải' in src.treatment.lower() else 0.0},
                deepcopy(src)))

    if enabled[3]:
        cdm_scope = app.cdm_scope_var.get()
        for method, name in (('standard', 'TCVN 9906 + BS 8006'), ('alicc', 'ALiCC')):
            report = getattr(app, '_cdm_reports', {}).get(method)
            src = report.get('project_snapshot') if report else None
            if not report or not src or report.get('scope') != cdm_scope or project_signature(src) != signature:
                missing.append(name + ' (' + ('số liệu chung đã thay đổi' if report else 'chưa tính') + ')')
                continue
            r, params = report['result'], report['params']
            scope = report['scope']
            if method == 'standard':
                st = r['stress']
                residual = r['sum_sc']
                geo = r.get('geo', {})
                n_layer = geo.get('n_layer', 0)
                ok = (residual <= limit and st['sigma_p'] <= st['qu_allow']
                      and st['qu_tt1'] <= st['qu_allow'] and st['sigma_s'] <= st['Rtc']
                      and (not report.get('use_geo') or geo['Tr'] <= geo['Td_fn']))
                note = (f'Sc={residual:.2f} cm; σp={st["sigma_p"]:.2f}/[qu]={st["qu_allow"]:.2f}; '
                        f'σs={st["sigma_s"]:.2f}/Rtc={st["Rtc"]:.2f} T/m²')
                cell_area = (params['s']**2 if params['pattern'] == 'Lưới vuông'
                             else .866025*params['s']**2)
                area_pile = math.pi*params['D']**2/4
            else:
                residual = r['S_total_cm']
                geo = r.get('reinforcement')
                n_layer = report['geo_params'].get('n_layer', 0) if geo else 0
                surface = r.get('surface', {})
                ok = (residual <= report['limit'] and r['pile_ok']
                      and r['differential_ok'] and (not geo or geo['ok'])
                      and (not surface or surface['shear_ok'] and surface['ok_k']))
                note = (f'S={residual:.2f} cm; ΔS={r["delta_cm"]:.2f} cm; '
                        f'Pcol={r["Pcol"]:.2f}, Psoil={r["Psoil"]:.2f} T/m²')
                cell_area, area_pile = r['area'], r['Ac']
            desc = (f'{scope}; D={params["D"]:.2f} m; s={params["s"]:.2f} m; '
                    f'Lc={params["Lc"]:.2f} m; {params["pattern"]}')
            options.append(CalculatedOption(
                4 if method == 'standard' else 5, 'Trộn sâu CDM',
                f'Cọc CDM ({name})', desc, residual,
                report['limit'] if method == 'alicc' else limit,
                'Theo hồ sơ thi công', 'Chưa định giá', ok, note,
                {'treatment_group': 'cdm', 'method': method, 'scope': scope,
                 'cdm_d': params['D'], 'cdm_s': params['s'], 'cdm_lc': params['Lc'],
                 'reinforcement_kind': report.get('geo_params', {}).get('kind'),
                 'cdm_n_layer': n_layer, 'cdm_cell_area': cell_area,
                 'cdm_area_pile': area_pile,
                 'surface_h': (report.get('surface_params', {}).get('thickness', 0.0)
                               if method == 'alicc' and r.get('surface') else 0.0)},
                deepcopy(src)))
    return options, missing


def build_view(parent):
    from batch_hub import build_view as build_summary
    return build_summary(parent,parent.winfo_toplevel())
