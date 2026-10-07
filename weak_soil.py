"""Nhận dạng đất yếu, TCCS 41:2022 phần 4; một chỉ tiêu yếu là đủ theo cấu hình dự án."""
import math


def initial_void_ratio(soil):
    """Lấy e tại P=0 hoặc đường e–P hằng; không giả định áp lực nội suy."""
    points = []
    for pressure, ratio in zip(getattr(soil, 'ep', []), getattr(soil, 'e', [])):
        try:
            pressure, ratio = float(pressure), float(ratio)
        except (TypeError, ValueError):
            continue
        if math.isfinite(pressure) and pressure >= 0 and math.isfinite(ratio) and ratio > 0:
            points.append((pressure, ratio))
    if points:
        if all(math.isclose(ratio, points[0][1], rel_tol=1e-9, abs_tol=1e-12)
               for _, ratio in points):
            return points[0][1]
        for pressure, ratio in points:
            if pressure == 0:
                return ratio
    try:
        value = float(soil.e0)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def weak_criteria(soil):
    data = dict(getattr(soil, 'weak_indicators', {}) or {})
    data.update(e0=initial_void_ratio(soil), spt=soil.spt_n, c_kpa=soil.cohesion_c * 9.80665, phi=soil.friction_phi)
    sources = getattr(soil, 'parameter_sources', {}) or {}
    source = sources.get('co', {})
    try:
        co = float(soil.co)
        default_co = 1.0
        try:
            from dataclasses import fields, is_dataclass
            if is_dataclass(soil):
                default_co = next(item.default for item in fields(soil) if item.name == 'co')
        except (StopIteration, TypeError):
            pass
        documented = isinstance(source, dict) and bool(source.get('source')) and source.get('value') == co
        # Co khác mặc định hoặc có nguồn xác nhận là số liệu đã nhập/đọc.
        # Không dùng Co mặc định để tự kết luận mọi lớp là đất yếu.
        if math.isfinite(co) and co > 0 and ('cu_kpa' in data or documented or co != default_co):
            data['cu_kpa'] = co * 9.80665
    except (TypeError, ValueError):
        pass
    def val(key, fallback=None):
        raw = data.get(key, fallback)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value > 0 else None
    text = str(data.get('soil_description') or getattr(soil, 'description', '') or soil.name).casefold()
    cohesive = soil.category == 'Đất dính' or any(t in text for t in ('sét', 'clay', 'than bùn'))
    sandy_mud = 'bùn cát' in text
    reasons = []
    e = val('e0', soil.e0)
    threshold = 1.0 if any(t in text for t in ('sét pha', 'silty clay', 'clayey')) else 1.5
    if cohesive and e is not None and e >= threshold:
        reasons.append(f'e={e:g} ≥ {threshold:g}')
    if sandy_mud and e is not None and e > 1.0:
        reasons.append(f'e={e:g} > 1,0 (bùn cát)')
    if cohesive:
        for key, limit, label, strict in [('c_kpa', 15, 'c (kPa)', False), ('phi', 10, 'φ (°)', True),
                                          ('cu_kpa', 35, 'Cu (kPa)', False), ('qc_mpa', .1, 'qc (MPa)', False)]:
            fallback = soil.cohesion_c * 9.80665 if key == 'c_kpa' else soil.friction_phi if key == 'phi' else None
            value = val(key, fallback)
            if value is not None and (value < limit if strict else value <= limit):
                reasons.append(f'{label}={value:g} {"<" if strict else "≤"} {limit:g}')
        w, wl, wp = val('w'), val('wl'), val('wp')
        if w is not None and wl is not None and w >= wl:
            reasons.append(f'W={w:g} ≥ WL={wl:g}')
        b = val('liquidity')
        if b is None and None not in (w, wl, wp) and wl > wp:
            b = (w-wp)/(wl-wp)
        if b is not None and b > .75:
            reasons.append(f'B={b:g} > 0,75')
        state = str(data.get('natural_state', '')).casefold()
        if 'dẻo chảy' in state or 'chảy' in state:
            reasons.append('Trạng thái dẻo chảy/chảy')
    n = val('spt', soil.spt_n)
    if n is not None and n < 5:
        reasons.append(f'N_SPT={n:g} < 5')
    return reasons


def first_weak_layer(project):
    depth = 0.0
    for index, soil in enumerate(project.soils):
        reasons = weak_criteria(soil)
        if reasons and soil.thickness > 0:
            return index, depth, soil.thickness, reasons
        depth += max(0.0, soil.thickness)
    return None
