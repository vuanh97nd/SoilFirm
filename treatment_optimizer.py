"""Tối ưu phương án cơ học và thời gian thoát nước theo lún dư."""
from __future__ import annotations

from copy import deepcopy
import math

from model import assess_locations, axes, settlement, stage_schedule


U_LIMIT = 90.0


def _indices(project):
    positions = axes(project)
    if project.expansion_width > 0:
        selected = [i for i, (name, _) in enumerate(positions)
                    if 'nền mở rộng' in name.lower()]
        if not selected:
            raise ValueError('Không tìm thấy vị trí nền mở rộng để kiểm toán.')
        return selected
    return list(range(len(positions)))


def weak_layer_bottom(project):
    top = bottom = 0.0
    for soil in project.soils:
        top += max(0.0, soil.thickness)
        from weak_soil import weak_criteria
        if weak_criteria(soil):
            bottom = top
    return bottom


def optimize_mechanical(project, limit_cm, increment=0.5, bamboo_length=3.0, cajuput_length=4.0):
    """Đào 0–4 m; tre 3 m + đào; cừ tràm 4 m + đào, dừng lần đầu đạt."""
    bamboo_length, cajuput_length = 3.0, 4.0
    if not math.isfinite(increment) or increment <= 0:
        raise ValueError('Bước đào phải là số dương hữu hạn.')
    indices = _indices(project)
    attempts = 0
    base = deepcopy(project)
    base.treatment_group = 'mechanical'
    base.mechanical_wait = False
    base.mechanical_surcharge = False
    base.stages = []
    # Kiểm toán TXL trước khi quyết định đào.
    natural = deepcopy(project)
    natural.replacement_depth = natural.bamboo_depth = natural.cajuput_depth = 0.0
    _, _, elements = settlement(natural, return_details=True)
    untreated = max((sum(e['Sc_list'][i] + e['Si_list'][i] for e in elements)
                     for i in indices), default=0.0)
    if untreated <= limit_cm:
        return {'status': 'untreated', 'residual_cm': untreated, 'attempts': 1,
                'replacement_depth': 0.0, 'bamboo_depth': 0.0,
                'cajuput_depth': 0.0, 'treatment_depth': 0.0}
    from weak_soil import first_weak_layer
    layer = first_weak_layer(project)
    if layer is None:
        raise ValueError('Chưa nhận dạng được lớp đất yếu từ chỉ tiêu khác 0 theo TCCS 41.')
    index, top, thickness, reasons = layer
    if thickness < 4.0:
        depths = [round(top + thickness, 8)]
    else:
        maximum = min(4.0, thickness - min(increment, thickness / 2))
        partial = [i * increment for i in range(1, int(maximum / increment)+1)]
        if not partial or partial[-1] < maximum:
            partial.append(maximum)
        depths = [round(top + value, 8) for value in partial]
    last = None
    for group, pile_depth in (('replacement', 0.0), ('bamboo', bamboo_length), ('cajuput', cajuput_length)):
        for excavation in depths:
            if group == 'replacement' and excavation == 0:
                trial = deepcopy(base)
                trial.treatment_group = 'drainage'
                trial.treatment = 'Chờ lún'
                _, _, elements = settlement(trial, return_details=True)
                residual = max((sum(e['Sc_list'][i] for e in elements)
                                for i in indices), default=0.0)
                attempts += 1
                if residual <= limit_cm:
                    return {'status': 'untreated', 'residual_cm': residual,
                            'attempts': attempts, 'replacement_depth': 0.0,
                            'bamboo_depth': 0.0, 'cajuput_depth': 0.0, 'treatment_depth': 0.0}
                continue
            trial = deepcopy(base)
            trial.replacement_depth = excavation
            trial.bamboo_depth = pile_depth if group == 'bamboo' else 0.0
            trial.cajuput_depth = pile_depth if group == 'cajuput' else 0.0
            trial.treatment = group
            readings = assess_locations(trial, 0.0, trial.treatment)
            residual = max((readings[i]['Sc_dư_cm'] for i in indices), default=0.0)
            attempts += 1
            last = (group, excavation, residual)
            if residual <= limit_cm:
                return {'status': 'pass', 'group': group,
                        'replacement_depth': excavation,
                        'bamboo_depth': trial.bamboo_depth,
                        'cajuput_depth': trial.cajuput_depth,
                        'treatment_depth': excavation + pile_depth,
                        'residual_cm': residual, 'attempts': attempts}
    return {'status': 'fail', 'attempts': attempts,
            'residual_cm': last[2] if last else float('inf')}


def limiting_fill_height(project, nc=5.14, fs=1.3):
    """Hgh = Nc × cu / (γđắp × Fs), dùng cu nhỏ nhất đã khai báo trong đất yếu."""
    strengths = [s.co for s in project.soils
                 if s.thickness > 0 and s.co > 0 and __import__('weak_soil').weak_criteria(s)]
    if not strengths or project.gamma_fill <= 0 or fs <= 0:
        return None
    return nc * min(strengths)/(project.gamma_fill * fs)


def optimize_drainage_time(project, limit_cm, u_limit=U_LIMIT, nc=5.14, fs=1.3):
    """Thời gian sớm nhất thỏa đồng thời lún dư ≤ giới hạn và U > 90%."""
    p = deepcopy(project)
    p.treatment_group = 'drainage'
    indices = _indices(p)
    weak_bottom = weak_layer_bottom(p)
    if p.treatment.startswith(('PVD', 'SD')):
        if weak_bottom <= 0:
            raise ValueError('Chưa có lớp đất yếu cần cắm PVD/SD.')
        p.drain_length = weak_bottom
    if p.stages:
        p.stages[-1].pause_days = 0.0
    finish = stage_schedule(p)[-1]['kết_thúc']
    surcharge = 'gia tải' in p.treatment.lower()
    vacuum = 'chân không' in p.treatment.lower()
    hgh = limiting_fill_height(p, nc, fs)
    fill_height = (p.expansion_h_design if p.expansion_width > 0 and p.expansion_h_design > 0
                   else p.h_design) + p.h_kcad + p.h_bl
    max_surcharge = max(0.0, hgh - fill_height) if hgh is not None else None
    attempts = 0

    def search(height):
        nonlocal attempts
        def evaluate(day):
            nonlocal attempts
            trial = deepcopy(p)
            wait = max(0.1, day-finish)
            if surcharge:
                trial.surcharge_height = height
                trial.surcharge_days = wait
            if vacuum:
                trial.vacuum_days = wait
            rows = assess_locations(trial, day, trial.treatment)
            attempts += 1
            return (max((max(0.0, rows[i]['Sc_cuối_cm']-rows[i]['Sc_t_cm'])
                         for i in indices), default=0.0),
                    min((rows[i]['U_%'] for i in indices), default=0.0))

        low = finish
        high = max(finish+1.0, finish*1.2)
        residual, u = evaluate(high)
        while not (residual <= limit_cm and u > u_limit) and high < finish+36525:
            low, high = high, min(finish+36525, finish+2*(high-finish))
            residual, u = evaluate(high)
        if residual > limit_cm or u <= u_limit:
            return None, high, residual, u
        for _ in range(28):
            if high-low < 0.01:
                break
            mid = (low+high)/2
            mid_residual, mid_u = evaluate(mid)
            if mid_residual <= limit_cm and mid_u > u_limit:
                high, residual, u = mid, mid_residual, mid_u
            else:
                low = mid
        return high, high, residual, u

    if surcharge and max_surcharge is not None and max_surcharge <= 0:
        return {'status': 'fail', 'reason': f'H đắp {fill_height:.2f} m đã đạt/vượt Hgh {hgh:.2f} m',
                'day': finish, 'u_pct': 0.0, 'residual_cm': float('inf'),
                'drain_length': p.drain_length, 'attempts': attempts, 'hgh': hgh}
    height = p.surcharge_height
    if surcharge and max_surcharge is not None:
        height = min(height, max_surcharge)
    day, last_day, residual, u = search(height)
    if day is None and surcharge and max_surcharge is not None and max_surcharge > height+1e-6:
        height = max_surcharge
        day, last_day, residual, u = search(height)
    if day is None:
        reason = f'Không đạt lún dư và U > {u_limit:g}% trong thời gian khảo sát'
        if hgh is not None:
            reason += f'; Hgh={hgh:.2f} m (Nc={nc:g}, cu min, γđắp, Fs={fs:g})'
        return {'status': 'fail', 'reason': reason, 'day': last_day,
                'u_pct': u, 'residual_cm': residual, 'drain_length': p.drain_length,
                'attempts': attempts, 'hgh': hgh}
    return {'status': 'pass', 'day': day, 'wait_days': max(0.0, day-finish),
            'u_pct': u, 'residual_cm': residual, 'drain_length': p.drain_length,
            'attempts': attempts, 'hgh': hgh, 'surcharge_height': height}
