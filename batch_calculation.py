"""Tính nhiều mặt cắt theo các lựa chọn ưu tiên (tối đa 5, có thể để trống) và lưu hồ sơ từng lần tính."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
import json
import math
from pathlib import Path
import re

from model import (FillStage, assess_locations, axes, cdm_design_project,
                   save, settlement, stage_schedule)
from section_excel import export_data_results, import_section
from treatment_boq import calculate_section_boq
from treatment_optimizer import optimize_drainage_time


OPTIONS = (
    'Đào thay đất', 'Cọc tre + đào thay đất', 'Cừ tràm + đào thay đất',
    'CDM (TCVN/BS)', 'CDM (ALiCC)', 'Chờ lún', 'Chờ lún + gia tải',
    'PVD', 'PVD + gia tải', 'SD', 'SD + gia tải',
)
DEFAULT_PRIORITY = ('Đào thay đất', 'Cọc tre + đào thay đất',
                    'Cừ tràm + đào thay đất', 'CDM (TCVN/BS)', 'PVD')


def _scope(project):
    return 'Nền mở rộng' if project.expansion_width > 0 else 'Nền đường'


def _positions(project):
    names = [i for i, (name, _) in enumerate(axes(project))
             if project.expansion_width <= 0 or 'nền mở rộng' in name.lower()]
    if not names:
        raise ValueError('Không có vị trí tính toán thuộc phạm vi xử lý.')
    return names


def natural_metrics(project):
    """Lún tại tim trước xử lý; tách lún cát theo Nₛₚₜ."""
    from ai_analysis_data import validate_analysis_project
    validate_analysis_project(project)
    _, _, elements = settlement(project, return_details=True)
    sc = sum(row['Sc_list'][0] for row in elements)
    si = sum(row['Si_list'][0] for row in elements)
    sand_si = sum(row['Si_list'][0] for row in elements
                  if project.soils[row['lớp']-1].category == 'Đất rời')
    return {'sc_cm': sc, 'si_cm': si, 'sand_si_cm': sand_si,
            'total_cm': sc+si, 'height_m': project.height}


def _number(data, key, required=True, default=None):
    raw = data.get(key, default)
    try:
        result = float(str(raw).strip().replace(',', '.'))
    except (TypeError, ValueError):
        if not required and default is not None:
            return float(default)
        raise ValueError(f'Thiếu thông số {key} của phương án đã khai báo.')
    if not math.isfinite(result):
        raise ValueError(f'Thông số {key} không hợp lệ.')
    return result


def _mechanical(project, variant, limit, settings):
    increment = _number(settings, 'excavation_step', default=.5)
    pile = 3.0 if 'Cọc tre' in variant else 4.0 if 'Cừ tràm' in variant else 0.0
    if increment <= 0 or pile < 0:
        raise ValueError('Bước đào phải dương và chiều dài cọc không được âm.')
    # Đạt TXL thì không đào, kể cả khi gọi phương án trực tiếp.
    baseline = natural_metrics(project)
    if baseline['total_cm'] <= limit:
        return dict(pass_check=True, residual_cm=baseline['total_cm'], project=deepcopy(project),
                    payload={'treatment_group': 'none', 'replacement_depth': 0.0}, details={'before': baseline})
    from weak_soil import first_weak_layer
    layer = first_weak_layer(project)
    if layer is None:
        raise ValueError('Chưa nhận dạng được lớp đất yếu từ các chỉ tiêu khác 0 theo TCCS 41.')
    index, top, thickness, reasons = layer
    if thickness < 4.0:
        depths = [round(top + thickness, 8)]
    else:
        # Không đào hết lớp >=4 m; chiều sâu tối đa trong lớp nhỏ hơn bề dày.
        maximum = min(4.0, thickness - min(increment, thickness / 2))
        partial = [i * increment for i in range(1, int(maximum / increment) + 1)]
        if not partial or partial[-1] < maximum:
            partial.append(maximum)
        depths = [round(top + value, 8) for value in partial]

    for step, depth in enumerate(depths):
        trial = deepcopy(project)
        trial.treatment_group = 'mechanical'
        trial.mechanical_wait = False
        trial.mechanical_surcharge = False
        trial.replacement_depth = depth
        trial.bamboo_depth = pile if 'Cọc tre' in variant else 0.0
        trial.cajuput_depth = pile if 'Cừ tràm' in variant else 0.0
        trial.treatment = variant
        if depth == 0 and pile == 0:
            trial.treatment_group = 'drainage'
            trial.treatment = 'Chờ lún'
        rows = assess_locations(trial, 0.0, trial.treatment)
        residual = max((rows[i]['Sc_dư_cm'] for i in _positions(trial)), default=0.0)
        if residual <= limit:
            payload = {'treatment_group': 'mechanical' if depth + pile > 0 else 'natural',
                       'replacement_depth': trial.replacement_depth,
                       'bamboo_depth': trial.bamboo_depth,
                       'cajuput_depth': trial.cajuput_depth,
                       'bamboo_density': 25.0, 'cajuput_density': 25.0,
                       'treatment_depth': depth + pile}
            return dict(pass_check=True, residual_cm=residual, project=trial,
                        payload=payload, details={'positions': rows, 'trial_depths': step})
    return dict(pass_check=False, residual_cm=residual, project=trial,
                payload={}, details={'positions': rows, 'trial_depths': len(depths),
                                     'reason': 'Đào theo phạm vi lớp đất yếu vẫn vượt lún cho phép.',
                                     'weak_layer': index + 1, 'weak_criteria': reasons})


def _drainage(project, variant, limit, settings):
    trial = deepcopy(project)
    trial.treatment_group = 'drainage'
    trial.treatment = variant
    trial.replacement_depth = trial.bamboo_depth = trial.cajuput_depth = 0.0
    ratio=settings.get('ch_cv')
    if ratio is not None and (not math.isfinite(ratio) or ratio<=0):
        raise ValueError('Ch/Cv phải lớn hơn 0.')
    for index,soil in enumerate(trial.soils):
        if ratio is not None:soil.ch_cv=ratio
        elif index in getattr(trial,'ai_ch_cv_default_layers',[]) and soil.ch_cv==1:
            soil.ch_cv=2.0 if variant.startswith(('PVD','SD')) else 1.0
    if variant.startswith('PVD'):
        trial.drain_type = 'Bấc thấm'
        trial.drain_spacing = settings['pvd_spacing']
        trial.drain_diameter = settings['pvd_diameter']
    elif variant.startswith('SD'):
        trial.drain_type = 'Cọc cát'
        trial.drain_spacing = settings['sd_spacing']
        trial.drain_diameter = settings['sd_diameter']
    if 'gia tải' in variant:
        if settings['surcharge_height'] <= 0:
            raise ValueError('Gia tải cần nhập chiều cao gia tải dương.')
        trial.surcharge_height = settings['surcharge_height']
    else:
        trial.surcharge_height = 0.0
    if not trial.stages:
        trial.stages = [FillStage(target_height=trial.height,
                                  speed_cm_day=trial.fill_speed_cm_day, pause_days=0.0)]
    trial.stages[-1].pause_days = 0.0
    outcome = optimize_drainage_time(trial, limit)
    if outcome['status'] == 'pass':
        trial.stages[-1].pause_days = 0.0 if 'gia tải' in variant else outcome['wait_days']
        trial.drain_length = outcome['drain_length']
        if 'gia tải' in variant:
            trial.surcharge_height = outcome['surcharge_height']
            trial.surcharge_days = outcome['wait_days']
    payload = {'treatment_group': 'drainage', 'treatment': variant,
               'drain_spacing': trial.drain_spacing,
               'drain_pattern': trial.drain_pattern,
               'drain_length': outcome['drain_length'],
               'wait_days': outcome.get('wait_days', 0.0),
               'surcharge_height': trial.surcharge_height if 'gia tải' in variant else 0.0}
    return dict(pass_check=outcome['status'] == 'pass',
                residual_cm=outcome['residual_cm'], project=trial,
                payload=payload, details=outcome)


def _cdm_standard(project, scope=None):
    from cdm import calculate_cdm_all
    scope = scope or _scope(project)
    states = project.cdm_inputs or {}
    saved = states.get(scope) if 'cdm' not in states else (
        states if scope == 'Nền đường' else None)
    if not saved or not saved.get('cdm'):
        raise ValueError(f'Chưa khai báo và lưu thông số CDM cho {scope}.')
    p = cdm_design_project(project, scope)
    cdm, stress, sub, geo = (saved.get(k, {}) for k in ('cdm', 'stress', 'subgrade', 'geo'))
    params = {k: _number(cdm, k) for k in ('D', 's', 'Lc', 'qu_val', 'Ec')}
    params.update(qu_type=cdm.get('qu_type', 'qu28'),
                  pattern=cdm.get('pattern', 'Lưới vuông'),
                  pile_type=cdm.get('pile_type', 'Cọc treo'))
    emb_h = p.h_design+p.h_kcad + (0 if 'Cọc chống' in params['pile_type'] else p.h_bl)
    loads = {k: _number(stress, k) for k in ('n', 'Fs', 'qH', 'f_fs', 'f_q')}
    loads['qT'] = p.gamma_fill*emb_h
    layer_text = str(sub.get('layer_idx', '')).strip()
    matched_layer = re.match(r'^(\d+)\.', layer_text)
    idx = int(matched_layer.group(1))-1 if matched_layer else 0
    idx = max(0, min(idx, len(p.soils)-1))
    soil = p.soils[idx]
    depth_mid = sum(s.thickness for s in p.soils[:idx])+soil.thickness/2
    gamma_sub = max(.2, soil.gamma-p.gamma_water) if depth_mid >= p.water_depth else soil.gamma
    manual = sub.get('rtc_method') == 'Nhập c, φ cắt nhanh'
    foundation = {'m': _number(sub, 'm'), 'gamma_sub': gamma_sub,
                  'q_mong': p.soils[0].gamma*_number(sub, 'hm', required=False, default=.3),
                  'c_val': _number(sub, 'c_manual') if manual else soil.cohesion_c,
                  'phi_val': _number(sub, 'phi_manual') if manual else soil.friction_phi}
    geo_on = bool(saved.get('use_geo', False))
    geo_params = {}
    if geo_on:
        kind = saved.get('reinforcement', 'Vải địa kỹ thuật')
        keys = ('eps', 'phi_dap', 'n_layer', 'fm11', 'fm12', 'fm21', 'fm22', 'fn')
        geo_params = {k: _number(geo, k) for k in keys}
        geo_params['kind'] = kind
        if kind == 'Lưới địa kỹ thuật':
            geo_params.update(T_char_kn=_number(geo, 'T_char_kn'), Tmax=400., eps_max=10.)
        else:
            geo_params.update(Tmax=_number(geo, 'Tmax'), eps_max=_number(geo, 'eps_max'))
        geo_params['n_layer'] = int(geo_params['n_layer'])
    result = calculate_cdm_all(p, params, loads, foundation, geo_params, geo_on)
    stress_result = result['stress']
    passed = (result['sum_sc'] <= project.residual_limit_cm
              and stress_result['qu_tt1'] <= stress_result['qu_allow']
              and stress_result['sigma_p'] <= stress_result['qu_allow']
              and stress_result['sigma_s'] <= stress_result['Rtc']
              and (not geo_on or result['geo']['Tr'] <= result['geo']['Td_fn']))
    area = params['s']**2 if params['pattern'] == 'Lưới vuông' else .866025*params['s']**2
    payload = {'treatment_group': 'cdm', 'method': 'standard', 'scope': scope,
               'cdm_d': params['D'], 'cdm_s': params['s'], 'cdm_lc': params['Lc'],
               'cdm_cell_area': area, 'cdm_area_pile': math.pi*params['D']**2/4,
               'reinforcement_kind': geo_params.get('kind'),
               'cdm_n_layer': geo_params.get('n_layer', 0)}
    return dict(pass_check=passed, residual_cm=result['sum_sc'], project=project,
                payload=payload, details={'result': result, 'params': params,
                                          'stress_params': loads, 'subgrade_params': foundation,
                                          'geo_params': geo_params, 'scope': scope})


def _cdm_alicc(project, scope=None):
    from alicc import (calculate_alicc_road, alicc_soil_modulus, es_layer_index, REINFORCEMENT_NONE,
                       REINFORCEMENT_FABRIC, REINFORCEMENT_GRID, REINFORCEMENT_SURFACE)
    scope = scope or _scope(project)
    from model import sync_data_settlement_limits
    sync_data_settlement_limits(project)
    states = project.alicc_inputs or {}
    saved = states.get(scope) if 'D' not in states else (
        states if scope == 'Nền đường' else None)
    if not saved:
        raise ValueError(f'Chưa khai báo và lưu thông số ALiCC cho {scope}.')
    p = cdm_design_project(project, scope)
    params = {k: _number(saved, k) for k in
              ('D', 's', 'Lc', 'Ec', 'qu', 'Fs', 'theta')}
    params['es_layer_index']=es_layer_index(saved.get('es_layer_idx','0'))
    params['Es']=alicc_soil_modulus(p,params['es_layer_index'])['Es']
    params['differential_limit_cm']=_number(saved,'differential_limit_cm') if saved.get('differential_limit_cm') is not None and str(saved.get('differential_limit_cm','')).strip() else None
    params.update(H=p.height, gamma=p.gamma_fill,
                  pattern=saved.get('pattern', 'Lưới vuông'),
                  pile_type=saved.get('pile_type', 'Cọc treo'))
    if params['pile_type'] == 'Cọc chống':
        params['H'] = p.h_design+p.h_kcad
    if params['pattern'] == 'Lưới chữ nhật':
        params['s_short'] = _number(saved, 's_short')
    limit = _number(saved, 'settlement_limit')
    kind = saved.get('kind', REINFORCEMENT_NONE)
    geo = {'kind': kind, 'phi_dap': _number(saved, 'phi_dap', default=30)}
    if kind in (REINFORCEMENT_FABRIC, REINFORCEMENT_GRID):
        geo.update({k: _number(saved, k) for k in
                    ('eps', 'phi_dap', 'n_layer', 'fm11', 'fm12',
                     'fm21', 'fm22', 'fn', 'f_fs', 'f_q')})
        if kind == REINFORCEMENT_GRID:
            geo.update(T_char_kn=_number(saved, 'T_char_kn'), Tmax=400., eps_max=10.)
        else:
            geo.update(Tmax=_number(saved, 'Tmax'), eps_max=_number(saved, 'eps_max'))
        geo['n_layer'] = int(geo['n_layer'])
    surface = {'enabled': kind == REINFORCEMENT_SURFACE}
    if surface['enabled']:
        mapping = {'surface_h': 'thickness', 'q_allow': 'q_allow',
                   'shear_strength': 'shear_strength', 'su_soil': 'su_soil',
                   'qu_surface': 'qu_surface', 'alpha': 'alpha',
                   'bend_ratio': 'bend_ratio', 'Esa': 'Esa', 'spt_n': 'spt_n'}
        surface.update({target: _number(saved, source) for source, target in mapping.items()})
    stress = {'qH': _number(saved, 'qH')}
    result = calculate_alicc_road(params, stress, geo, surface, p)
    reinforcement = result.get('reinforcement')
    cover = result.get('surface')
    passed = (result['S_total_cm'] <= limit and result['pile_ok'] and result.get('differential_ok') is True
              and
              (reinforcement is None or reinforcement['ok']) and
              (cover is None or (cover['shear_ok'] and cover['ok_k'])))
    payload = {'treatment_group': 'cdm', 'method': 'alicc', 'scope': scope,
               'cdm_d': params['D'], 'cdm_s': params['s'], 'cdm_lc': params['Lc'],
               'cdm_cell_area': result['area'], 'cdm_area_pile': result['Ac'],
               'reinforcement_kind': kind,
               'cdm_n_layer': geo.get('n_layer', 0) if reinforcement else 0}
    return dict(pass_check=passed, residual_cm=result['S_total_cm'],
                project=project, payload=payload,
                details={'result': result, 'params': params,
                         'stress_params': stress, 'geo_params': geo,
                         'surface_params': surface, 'limit': limit, 'scope': scope})


def _optimize_batch_cdm(project, name, settings):
    increment = _number(settings, 'cdm_length_step', default=.5)
    if increment <= 0:
        raise ValueError('Bước chiều dài CDM phải lớn hơn 0.')
    scope = _scope(project)
    depth = sum(s.thickness for s in cdm_design_project(project, scope).soils)
    if depth < increment:
        raise ValueError('Bước chiều dài CDM vượt chiều sâu địa chất.')
    standard = 'TCVN' in name
    attempts = 0
    last = None
    for i in range(1, int(depth / increment) + 1):
        trial = deepcopy(project)
        states = trial.cdm_inputs if standard else trial.alicc_inputs
        saved = states if ('cdm' if standard else 'D') in states else states.get(scope)
        if not saved:
            raise ValueError(f'Chưa khai báo thông số CDM cho {scope}.')
        inputs = saved.get('cdm') if standard else saved
        if not inputs:
            raise ValueError(f'Chưa khai báo thông số CDM cho {scope}.')
        inputs['Lc'] = round(i * increment, 8)
        last = _cdm_standard(trial) if standard else _cdm_alicc(trial)
        attempts += 1
        last['details']['length_step_m'] = increment
        last['details']['length_attempts'] = attempts
        if last['pass_check']:
            return last
    return last


def run_option(project, name, settings):
    if name in ('Đào thay đất', 'Cọc tre + đào thay đất', 'Cừ tràm + đào thay đất'):
        return _mechanical(project, name, project.residual_limit_cm, settings)
    if name in ('CDM (TCVN/BS)', 'CDM (ALiCC)'):
        return _optimize_batch_cdm(project, name, settings)
    return _drainage(project, name, project.residual_limit_cm, settings)


def _safe_name(name):
    result = re.sub(r'[^\w.-]+', '_', str(name), flags=re.UNICODE).strip('._')
    return result[:65] or 'MCN'


def _json(path, value):
    def clean(item):
        if isinstance(item, float) and not math.isfinite(item):
            return None
        if isinstance(item, dict):
            return {key: clean(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(val) for val in item]
        return item
    with Path(path).open('w', encoding='utf-8') as stream:
        json.dump(clean(value), stream, ensure_ascii=False, indent=2, default=str,
                  allow_nan=False)


def run_batch(source, numbers, priorities, template, output, settings,
              cad_counts=None, progress=None):
    # Lọc danh sách giải pháp hợp lệ: bỏ qua các mục để trống hoặc '(Trống)'
    clean_priorities = tuple(p for p in priorities if p and p != '(Trống)')
    if len(clean_priorities) > 5:
        raise ValueError('Tối đa 5 giải pháp ưu tiên.')
    if len(clean_priorities) != len(set(clean_priorities)):
        raise ValueError('Các giải pháp ưu tiên được chọn không được trùng nhau.')
    if any(x not in OPTIONS for x in clean_priorities):
        raise ValueError('Có giải pháp ưu tiên không hợp lệ trong danh sách.')
    if not numbers or len(numbers) != len(set(numbers)):
        raise ValueError('Danh sách STT phải có ít nhất một dòng và không được trùng.')

    if settings.get('ai_optimize'):numbers=sorted(numbers)
    no_export = bool(settings.get('no_export', False))
    run_dir = None
    if not no_export:
        root = Path(output)
        root.mkdir(parents=True, exist_ok=True)
        run_dir = root / ('Loat_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        run_dir.mkdir()
    records, failures = [], []
    for count, number in enumerate(numbers, 1):
        if progress:
            progress(count, len(numbers), number, 'Đang nạp số liệu')
        try:
            project, length = import_section(source, number, template)
            label = f'{number:03d}_{_safe_name(project.station)}'
            before = natural_metrics(project)
            from soilfirm_ai_engine import before_treatment
            evaluation=before_treatment(project)
            before.update(residual_cm=evaluation['residual_cm'],
                          evaluation_day=evaluation['evaluation_day'],
                          locations=evaluation['locations'])
            before_pass = evaluation['pass_check']
            if before_pass:
                rec = {'section_no': number,
                       'station': f'{project.station_from} - {project.station_to}',
                       'length': length, 'h_design': project.h_design,
                       'limit': project.residual_limit_cm,
                       'group': 'Chưa xử lý', 'opt_name': 'Không cần xử lý',
                       'params': 'Lún trước xử lý đã đạt',
                       'residual': before['residual_cm'], 'status': 'ĐẠT',
                       'notes': 'Đã đạt trước xử lý; không tính sau xử lý.',
                       'payload': {'treatment_group': 'none'},
                       'before': before, 'before_pass': True,
                       'project_snapshot': project}
                rec['boq'] = calculate_section_boq(rec, length, project)
                rec['before_project'] = deepcopy(project)
                records.append(rec)
                continue
            attempts = []
            selected = None
            for rank, name in enumerate(clean_priorities, 1):
                if progress:
                    progress(count, len(numbers), number, f'{rank}/{len(clean_priorities)} {name}')
                try:
                    if settings.get('ai_optimize'):
                        from soilfirm_ai_engine import optimize_cdm, optimize_drains
                        notify=(lambda message:progress(count,len(numbers),number,message)) if progress else None
                        if name.startswith('CDM'):result=optimize_cdm(deepcopy(project),name,settings,notify)
                        elif name in OPTIONS[5:]:result=optimize_drains(deepcopy(project),name,settings,'priority',notify)
                        else:result=run_option(project,name,settings)
                    else:result = run_option(project, name, settings)
                    if (result['payload'].get('treatment_group') == 'cdm' and
                            settings.get('cdm_count_mode') == 'cad' and
                            (not cad_counts or number not in cad_counts)):
                        raise ValueError(f'Không có CIRCLE trên layer CDM{number} trong DXF.')
                    trial = result['project']
                    info = {'rank': rank, 'option': name,
                            'status': 'ĐẠT' if result['pass_check'] else 'KHÔNG ĐẠT',
                            'residual_cm': result['residual_cm'],
                            'limit_cm': project.residual_limit_cm,
                            'payload': result['payload'],
                            'calculation': result['details'],
                            'input_project': asdict(project),
                            'calculated_project': asdict(trial)}
                    if result['pass_check']:
                        selected = (name, result)
                except Exception as exc:
                    info = {'rank': rank, 'option': name, 'status': 'LỖI DỮ LIỆU',
                            'error': str(exc), 'input_project': asdict(project)}
                attempts.append(info)
                if selected:
                    break
            if selected:
                name, result = selected
                trial = result['project']
                rec = {'section_no': number,
                       'station': f'{project.station_from} - {project.station_to}',
                       'length': length, 'h_design': trial.h_design,
                       'limit': project.residual_limit_cm,
                       'group': 'Trộn sâu CDM' if 'CDM' in name else
                                'Thay thế & gia cường cơ học' if 'đất' in name or 'Cọc tre' in name or 'Cừ tràm' in name else
                                'Cố kết & Thoát nước',
                       'opt_name': name, 'params': str(result['payload']),
                       'residual': result['residual_cm'], 'status': 'ĐẠT',
                       'notes': f'Tính hàng loạt; hồ sơ: {label}',
                       'payload': result['payload'], 'project_snapshot': trial,
                       'before': before, 'before_pass': False}
                if result['payload'].get('treatment_group') == 'drainage':
                    rec['after_u_pct'] = result['details'].get('u_pct')
                if result['payload'].get('treatment_group') == 'cdm':
                    cdm_result = result['details'].get('result', {})
                    rec['after_pile_settlement_cm'] = cdm_result.get('S1_cm', cdm_result.get('sum_si'))
                if result['payload'].get('treatment_group') == 'cdm':
                    rec['cdm_count_mode'] = settings.get('cdm_count_mode', 'formula')
                if cad_counts and number in cad_counts and result['payload'].get('treatment_group') == 'cdm':
                    rec['cad_cdm_count'] = cad_counts[number]
                    rec['cad_cdm_source'] = settings.get('cad_source', '')
                rec['calculation_report'] = result['details']
                rec['attempts'] = attempts
                rec['boq'] = calculate_section_boq(rec, length, trial)
                rec['before_project'] = deepcopy(project)
                records.append(rec)
            else:
                reason = ('Không có phương án đạt trong các lựa chọn đã tính.'
                          if clean_priorities else 'Không chọn phương án xử lý (để trống các ưu tiên).')
                failures.append({'section_no': number, 'station': project.station,
                                 'reason': reason})
                finite = [a['residual_cm'] for a in attempts
                          if isinstance(a.get('residual_cm'), (int, float)) and
                          math.isfinite(a['residual_cm'])]
                rec = {'section_no': number,
                       'station': f'{project.station_from} - {project.station_to}',
                       'length': length, 'h_design': project.h_design,
                       'limit': project.residual_limit_cm,
                       'group': 'Chưa chọn',
                       'opt_name': 'Chưa có phương án đạt' if clean_priorities else 'Chưa xử lý',
                       'params': 'Xem các phép tính trong JSON tổng hợp' if clean_priorities else 'Chỉ kiểm toán lún tự nhiên (trước xử lý)',
                       'residual': min(finite) if finite else before['residual_cm'],
                       'status': 'KHÔNG ĐẠT',
                       'notes': f'Hồ sơ tổng hợp; STT {number}',
                       'payload': {'treatment_group': 'none'},
                       'before': before, 'before_pass': False,
                       'project_snapshot': project}
                rec['attempts'] = attempts
                rec['boq'] = calculate_section_boq(rec, length, project)
                rec['before_project'] = deepcopy(project)
                records.append(rec)
        except Exception as exc:
            failures.append({'section_no': number, 'reason': str(exc)})
    if records and not no_export:
        from batch_bundle import export_bundle
        if settings.get('ai_optimize') and progress:progress(len(numbers),len(numbers),numbers[-1],'Đang xuất PDF/JSON theo STT…')
        export_bundle(source, run_dir/'Ket_qua_hang_loat', records, failures, clean_priorities, individual=bool(settings.get('export_individual')))
    return str(run_dir) if run_dir is not None else '', records, failures
