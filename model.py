"""
Module: model.py
Lõi tính toán địa kỹ thuật:
- Tính lún cố kết Sc, lún tức thời Si, lún tổng cộng St.
- Hệ số F cố kết được tính chính xác bằng công thức TCVN 9355 (Fn + Fs + Fr).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
import math
import os
import tempfile


def sync_data_settlement_limits(project):
    """Copy the active imported Data limit into ALiCC input fields (cm)."""
    if not getattr(project,'residual_limit_source',''):return
    limit=float(project.residual_limit_cm)
    if not math.isfinite(limit) or limit<=0:
        raise ValueError('ΔS trong Data của đoạn hiện tại phải dương và hữu hạn.')
    states=project.alicc_inputs or {}
    targets=[states] if 'D' in states else [states.setdefault(scope,{}) for scope in ('Nền đường','Nền mở rộng')]
    for saved in targets:
        saved['differential_limit_cm']=str(limit)
        saved['settlement_limit']=str(limit)
        saved['settlement_limit_source']=project.residual_limit_source
    project.alicc_inputs=states


def soil_strength_m(soil):
    """CU angle in degrees, or the explicitly selected manual factor."""
    phi = getattr(soil, 'phi_cu_effective', None)
    if phi is None:
        return soil.strength_m
    if not math.isfinite(phi) or not 0 <= phi < 90:
        raise ValueError('φ′ CU phải từ 0 đến dưới 90 độ.')
    return math.tan(math.radians(phi))


@dataclass
class Soil:
    no: int = 0
    statistics_id: str = ""
    parameter_sources: dict = field(default_factory=dict)
    name: str = ""
    thickness: float = 0.0
    distance: float = 0.0  
    gamma: float = 0.0
    category: str = "Đất dính"
    state: str = "Quá cố kết"
    drainage: int = 1
    ep: list[float] = field(default_factory=lambda: [0.0, 0.125, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0])
    e: list[float] = field(default_factory=lambda: [0.0] * 8)
    e0: float = 0.0  
    cvp: list[float] = field(default_factory=lambda: [0.0625, 0.1875, 0.375, 0.75, 1.5, 3.0, 6.0])
    cv: list[float] = field(default_factory=lambda: [0.0] * 7)
    mvp: list[float] = field(default_factory=lambda: [0.0625, 0.1875, 0.375, 0.75, 1.5, 3.0, 6.0])
    mv: list[float] = field(default_factory=lambda: [0.0] * 7)  
    cc: float = 0.0
    cs: float = 0.0
    pc: float = 0.0
    ch_cv: float = 2.0
    co: float = 1.0
    cohesion_c: float = 0.0
    friction_phi: float = 0.0
    cv_constant: float | None = None
    phi_cu_effective: float | None = None
    strength_m: float = 0.1
    spt_n: float = 0.0
    sand_method: str = "De Beer"
    weak_indicators: dict = field(default_factory=dict)


@dataclass
class FillStage:
    target_height: float = 0.0
    speed_cm_day: float = 10.0
    pause_days: float = 0.0


@dataclass
class Project:
    name: str = ""
    design_stage: str = ""
    work_item: str = ""
    station: str = ""
    station_from: str = ""
    station_to: str = ""
    road_class: str = "A1 · cao tốc hoặc Vtk ≥ 80 km/h"
    road_location: str = "Nền đắp thông thường"
    pavement_type: str = "Mặt đường mềm"
    gamma_fill: float = 1.8
    h_design: float = 3.0  
    h_kcad: float = 0.15
    h_bl: float = 0.0  
    slope_m: float = 1.5
    height: float = 3.15
    crest_half_width: float = 6.0
    slope_width: float = 4.725
    expansion_side: str = "Không"
    expansion_width: float = 0.0
    expansion_treatment_width: float | None = None
    expansion_h_design: float = 0.0
    expansion_h_bl: float | None = None
    expansion_h_kcad: float | None = None
    expansion_slope_m: float | None = None
    expansion_gamma_fill: float | None = None
    main_treatment: str = "Chưa xử lý"
    main_soils: list[Soil] = field(default_factory=list)
    main_replacement_depth: float = 0.0
    main_bamboo_depth: float = 0.0
    main_cajuput_depth: float = 0.0
    main_cdm_depth: float = 0.0
    main_age_days: float = 0.0
    main_observed_residual_cm: float | None = None
    counterweight_height: float = 0.0
    counterweight_width: float = 0.0
    counterweight_m: float = 1.0
    counterweight_slope: float = 0.0  
    ground_elevation: float = 0.0
    borehole_name: str = ""
    water_depth: float = 0.0  
    gamma_water: float = 0.98
    sublayer: float = 1.0
    limit_ratio: float = 0.15
    settlement_factor: float = 1.2  
    method: str = "Cc/Cs/Pc"
    drain_spacing: float = 1.2
    drain_diameter: float = 6.62  
    drain_pattern: str = "Tam giác"
    smear_ratio: float = 2.0         
    permeability_ratio: float = 3.0  
    khqw: float = 0.0001              
    resistance: float = 0.0
    treatment: str = "PVD"
    treatment_group: str = "drainage"
    replacement_depth: float = 0.0
    bamboo_depth: float = 0.0
    cajuput_depth: float = 0.0
    mechanical_wait: bool = False
    mechanical_surcharge: bool = False
    fill_speed_cm_day: float = 10.0
    stages: list[FillStage] = field(default_factory=list)
    surcharge_height: float = 0.0
    surcharge_gamma: float = 1.8
    surcharge_days: float = 180.0
    vacuum_pressure: float = 8.0
    vacuum_days: float = 180.0
    drain_type: str = "Bấc thấm"
    drain_cw_enabled: bool = False
    drain_cw_type: str = "Bấc thấm"
    drain_cw_spacing: float = 0.0
    drain_cw_diameter: float = 5.5
    drain_cw_pattern: str = "Tam giác"
    drain_upper_boundary: bool = True
    drain_length: float = 0.0
    ignore_uv: bool = False
    ignore_fs: bool = False  
    ignore_fr: bool = False  
    legacy_z: float = 0.0
    legacy_us: float = 0.0
    assessment_days: float = 0.0
    residual_limit_cm: float = 20.0
    residual_limit_source: str = ""
    horizontal_drain_type: str = "Bấc thấm ngang"
    h_sand_cushion: float = 0.5
    cdm_scope: str = 'Nền đường'
    cdm_inputs: dict = field(default_factory=dict)
    alicc_inputs: dict = field(default_factory=dict)
    geology_statistics: dict = field(default_factory=dict)
    calculation_results: dict = field(default_factory=dict)
    ai_ch_cv_default_layers: list[int] = field(default_factory=list)
    soils: list[Soil] = field(default_factory=list)

    @property
    def borehole_depth(self) -> float:
        """Chiều sâu địa tầng tính toán, đồng bộ với bề dày từng lớp."""
        return sum(soil.thickness for soil in self.soils)

    def set_borehole(self, name, elevation, depth, layers) -> None:
        """Kiểm tra toàn bộ hồ sơ trước khi thay dữ liệu của mặt cắt tính."""
        if not math.isfinite(elevation):
            raise ValueError('Cao độ lỗ khoan phải là số hữu hạn.')
        if not math.isfinite(depth) or depth <= 0:
            raise ValueError('Chiều sâu lỗ khoan tính toán phải lớn hơn 0.')
        if not layers or any(not math.isfinite(s.thickness) or s.thickness <= 0 for s in layers):
            raise ValueError('Nhập ít nhất một lớp đất với bề dày lớn hơn 0.')
        total = sum(s.thickness for s in layers)
        if not math.isclose(total, depth, rel_tol=1e-9, abs_tol=1e-6):
            raise ValueError(f'Tổng bề dày các lớp ({total:.3f} m) không khớp chiều sâu '
                             f'lỗ khoan ({depth:.3f} m). Hãy sửa bề dày hoặc lấy tổng lớp.')
        self.borehole_name = name.strip()
        self.ground_elevation = elevation
        self.soils = [replace(s, no=i) for i, s in enumerate(layers, 1)]

    def update_geometry(self) -> None:
        self.height = self.h_design + self.h_kcad + self.h_bl
        self.slope_width = self.slope_m * self.height
        self.counterweight_slope = self.counterweight_m * self.counterweight_height


def cdm_design_project(project: Project, scope: str) -> Project:
    """Mặt cắt tính cục bộ dùng đúng thông số nền đắp của phạm vi đặt cọc."""
    if scope != 'Nền mở rộng':
        return project
    if project.expansion_width <= 0 or project.expansion_side == 'Không':
        raise ValueError('Khai báo và bật nền mở rộng trước khi tính CDM cho nền mở rộng.')
    local = replace(project, expansion_side='Không', expansion_width=0.0,
                    crest_half_width=project.expansion_width/2,
                    h_design=project.expansion_h_design or project.h_design,
                    h_bl=(project.h_bl if project.expansion_h_bl is None else project.expansion_h_bl),
                    h_kcad=(project.h_kcad if project.expansion_h_kcad is None
                            else project.expansion_h_kcad),
                    slope_m=(project.slope_m if project.expansion_slope_m is None
                             else project.expansion_slope_m),
                    gamma_fill=(project.gamma_fill if project.expansion_gamma_fill is None
                                else project.expansion_gamma_fill),
                    main_treatment='Chưa xử lý', main_soils=[])
    local.update_geometry()
    return local


def save(project: Project, path: str) -> None:
    project.update_geometry()
    # Serialize before opening the destination; replace only a complete file.
    payload = json.dumps({"format": "saspro-python-1", "project": asdict(project)},
                         ensure_ascii=False, indent=2)
    destination = os.path.abspath(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".tmp",
                dir=os.path.dirname(destination), delete=False) as stream:
            temporary = stream.name
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try: os.unlink(temporary)
            except FileNotFoundError: pass


def load(path: str) -> Project:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return project_from_dict(data["project"])


def project_from_dict(raw: dict) -> Project:
    p = dict(raw)
    soils = []
    for raw_soil in p["soils"]:
        soil_data = dict(raw_soil)
        if "ch_cv" not in soil_data:
            if "cv_ch" in soil_data:
                old_v = soil_data.pop("cv_ch")
                soil_data["ch_cv"] = (
                    old_v if old_v >= 1.0 else (1.0 / old_v if old_v > 0 else 2.0)
                )
            else:
                soil_data["ch_cv"] = 2.0
        else:
            soil_data.pop("cv_ch", None)
        soils.append(Soil(**soil_data))
    p["soils"] = soils
    if p.get('main_treatment') == 'CDM':
        if not p.get('main_cdm_depth'):
            p['main_cdm_depth'] = sum(s.thickness for s in soils)
    elif p.get('main_treatment') == 'Cơ học/CDM':
        p['main_treatment'] = ('CDM' if p.get('main_cdm_depth', 0) > 0 else 'Cơ học')
    p["main_soils"] = [Soil(**raw) for raw in p.get("main_soils", [])]
    p["stages"] = [FillStage(**s) for s in p.get("stages", [])]

    for old_key in ["drain_both_ends", "radial_method"]:
        p.pop(old_key, None)

    if "h_design" not in p:
        p["h_design"] = p.get("height", 0)
        p["slope_m"] = p.get("slope_width", 0) / max(p.get("height", 0.001), 0.001)
        p["h_bl"] = 0.0
        p["h_kcad"] = 0.15
    if "counterweight_m" not in p:
        p["counterweight_m"] = (
            p.get("counterweight_slope", 0.0) / p["counterweight_height"]
            if p.get("counterweight_height", 0) > 0
            else 1.0
        )
    result = Project(**p)
    result.update_geometry()
    return result


def interpolate_log(
    points: list[tuple[float, float]], p_val: float, logarithmic_y: bool = False
) -> float:
    pts = [(x, y) for x, y in points if x >= 0 and y > 0]
    if not pts:
        return 0.0
    p_val = max(pts[0][0], min(p_val, pts[-1][0]))
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= p_val <= x1:
            if x0 == 0:
                fraction = p_val / max(x1, 1e-6)
            else:
                fraction = math.log(max(p_val, 1e-6) / max(x0, 1e-6)) / math.log(
                    max(x1 / x0, 1.0001)
                )
            if logarithmic_y:
                return math.exp(math.log(y0) + fraction * math.log(y1 / y0))
            return y0 + fraction * (y1 - y0)
    return pts[-1][1]


def void_ratio(s: Soil, pressure_t_m2: float) -> float:
    p_val = max(pressure_t_m2 / 10.0, 0.0)
    if s.category == "Đất dính":
        if not any(value > 0 for value in s.e):
            return max(0.0, s.e0)
        return interpolate_log(list(zip(s.ep, s.e)), p_val)
    n = s.spt_n
    pressures = [0.20, 0.30, 0.50, 1.00, 2.00, 3.00, 5.00, 10.0, 20.0, 30.0, 50.0]
    if n <= 4:
        ratios = [0.967, 0.947, 0.922, 0.889, 0.855, 0.836, 0.811, 0.778, 0.744, 0.725, 0.700]
    elif n <= 10:
        ratios = [0.780, 0.760, 0.742, 0.714, 0.688, 0.678, 0.662, 0.640, 0.621, 0.611, 0.600]
    elif n <= 30:
        ratios = [0.586, 0.578, 0.567, 0.554, 0.540, 0.532, 0.521, 0.507, 0.493, 0.485, 0.475]
    elif n <= 50:
        ratios = [0.490, 0.484, 0.477, 0.467, 0.457, 0.451, 0.443, 0.433, 0.423, 0.417, 0.410]
    else:
        ratios = [0.395, 0.392, 0.388, 0.383, 0.378, 0.375, 0.372, 0.367, 0.362, 0.359, 0.355]
    return interpolate_log(list(zip(pressures, ratios)), p_val)


def cv_cm2_day(s: Soil, pressure_t_m2: float) -> float:
    if s.category != "Đất dính":
        return 0.0
    # Prefer the pressure-dependent test curve whenever complete pairs exist.
    if (len(s.cvp) >= 2 and len(s.cvp) == len(s.cv) and
            all(math.isfinite(p) and p >= 0 for p in s.cvp) and
            all(math.isfinite(v) and v > 0 for v in s.cv) and
            all(a < b for a, b in zip(s.cvp, s.cvp[1:]))):
        return 86.4 * interpolate_log(list(zip(s.cvp, s.cv)), pressure_t_m2 / 10.0, True)
    if s.cv_constant is not None:
        if not math.isfinite(s.cv_constant) or s.cv_constant<0:raise ValueError('Cv trung bình phải không âm và hữu hạn.')
        return 86.4*s.cv_constant
    raise ValueError(f'{s.name}: thiếu hoặc sai bảng Cv/Cv trung bình.')


def expansion_parameters(p: Project) -> tuple[float, float, float]:
    design = p.expansion_h_design if p.expansion_h_design and p.expansion_h_design > 0 else p.h_design
    pavement = p.h_kcad if p.expansion_h_kcad is None else p.expansion_h_kcad
    slope = p.slope_m if p.expansion_slope_m is None else p.expansion_slope_m
    gamma = p.gamma_fill if p.expansion_gamma_fill is None else p.expansion_gamma_fill
    h_bl = p.h_bl if p.expansion_h_bl is None else p.expansion_h_bl
    return design + pavement + h_bl, slope, gamma


def expansion_geometry(p: Project, side: str) -> tuple[float, float, float] | None:
    if p.expansion_width <= 0 or p.expansion_side not in (side, 'Hai bên'):
        return None
    ext_h, ext_slope, _ = expansion_parameters(p)
    inner = p.crest_half_width + p.slope_m * max(0.0, p.height - ext_h)
    outer = inner + p.expansion_width
    return inner, outer, outer + ext_slope * ext_h


def treatment_ranges(p: Project) -> list[tuple[float, float]]:
    """Phạm vi xử lý: vai nền chính đến chân nền mở rộng, đúng phía mở rộng."""
    if p.expansion_width > 0 and p.expansion_side != 'Không':
        out = []
        for side, sign in (('Trái', -1), ('Phải', 1)):
            geometry = expansion_geometry(p, side)
            if geometry is not None:
                width = p.expansion_treatment_width
                inner = (p.crest_half_width if width is None else
                         max(p.crest_half_width, geometry[2]-width))
                out.append(tuple(sorted((sign*inner, sign*geometry[2]))))
        return out
    reach = p.crest_half_width + p.slope_width
    return [(-reach, reach)]


def cdm_time_history(project: Project, result: dict, method: str, pile_length: float) -> list[dict]:
    """Phân bố lún theo thời gian từ chính phân tố lún dưới mũi cọc đã tính."""
    parts = []
    source = result['rows_lun'] if 'rows_lun' in result else result.get('rows', [])
    if method != 'standard':
        source = result.get('settlement_rows', [])
    for row in source:
        if method == 'standard':
            weight = max(0.0, float(row.get('sc', 0.0)))
            z = float(row.get('bot_z', 0.0)) - float(row.get('thick', 0.0))/2
        else:
            weight = max(0.0, float(row.get('cm', 0.0)))
            z = (row['z0'] + row['z1'])/2
        if weight <= 0:
            continue
        top = 0.0
        for soil in project.soils:
            bottom = top + soil.thickness
            if top <= z <= bottom:
                if soil.category == 'Đất dính':
                    cv = max(0.0, cv_cm2_day(soil, effective_overburden(project, z)
                                             + pressure(project, z, 0.0)/2))
                    path = 100.0*max(0.0, bottom-max(top, pile_length))/max(soil.drainage, 1)
                    parts.append((weight, cv, path))
                break
            top = bottom
    final_sc = sum(weight for weight, _, _ in parts)
    if final_sc <= 1e-12:
        return []
    total = result['total_s'] if method == 'standard' else result['S_total_cm']
    instantaneous = max(0.0, total-final_sc)
    def evaluate(day):
        achieved = sum(weight*degree_vertical(day*cv/path**2 if path > 0 else 0.0)
                       for weight, cv, path in parts)
        return achieved
    horizon = 1.0
    for _ in range(40):
        if evaluate(horizon) >= .99*final_sc:
            break
        horizon *= 2
    else:
        horizon = 365.25
    times = {horizon*i/120 for i in range(121)}
    times.add(0.0)
    for target in (.05,.1,.2,.3,.4,.5,.6,.7,.8,.9,.95,.99):
        if evaluate(horizon) < target*final_sc:
            continue
        low, high = 0.0, horizon
        for _ in range(28):
            mid = (low+high)/2
            if evaluate(mid) < target*final_sc:
                low = mid
            else:
                high = mid
        times.add(high)
    return [{'ngày': day, 'tháng': day/30.0,
             'st_m': (instantaneous+evaluate(day))/100.0,
             'sc_m': evaluate(day)/100.0,
             'dsc_m': max(0.0, final_sc-evaluate(day))/100.0,
             'u_pct': evaluate(day)*100.0/final_sc} for day in sorted(times)]


def load_at(p: Project, x: float) -> float:
    side = 'Trái' if x < 0 else 'Phải'
    x = abs(x)
    b, a, h = p.crest_half_width, p.slope_width, p.height
    main_h = h if x <= b else max(0.0, h * (b + a - x) / max(a, 0.001))
    q = p.gamma_fill * main_h
    geometry = expansion_geometry(p, side)
    if geometry:
        inner, outer, toe = geometry
        ext_h, ext_slope, ext_gamma = expansion_parameters(p)
        ext_profile = (ext_h if inner <= x <= outer else
                       max(0.0, (toe-x)/max(ext_slope, 0.001)) if outer < x <= toe else 0.0)
        q += ext_gamma * max(0.0, ext_profile-main_h)
    if p.counterweight_height > 0 and p.counterweight_width > 0:
        shoulder = b + a * (h - p.counterweight_height) / max(h, 0.001)
        toe = shoulder + p.counterweight_width
        if shoulder <= x <= toe:
            q = max(q, p.gamma_fill * p.counterweight_height)
        elif toe < x <= toe + p.counterweight_slope:
            q = max(
                q,
                p.gamma_fill
                * p.counterweight_height
                * (toe + p.counterweight_slope - x)
                / max(p.counterweight_slope, 0.001),
            )
    return q


def pressure(p: Project, depth: float, x: float) -> float:
    p.update_geometry()
    if depth <= 0:
        return load_at(p, x)
    left_reach, right_reach = side_reach(p, 'Trái'), side_reach(p, 'Phải')
    n = 400
    step = (left_reach + right_reach) / n
    total = 0.0
    for j in range(n + 1):
        source_x = -left_reach + j * step
        r2 = (source_x - x) ** 2 + depth**2
        kernel = 2 * depth**3 / (math.pi * r2**2)
        total += (1 if j in (0, n) else 4 if j % 2 else 2) * load_at(p, source_x) * kernel
    return total * step / 3


def main_zone_boundary(p: Project) -> float | None:
    """Ranh giới đất nền chính đã xử lý, tính từ tim đường."""
    if p.main_treatment == 'Chưa xử lý':
        return None
    if p.main_treatment == 'CDM':
        return p.crest_half_width + p.slope_width
    if p.main_treatment == 'Cơ học':
        depth = p.main_replacement_depth or max(p.main_bamboo_depth, p.main_cajuput_depth)
        return max(0.0, p.crest_half_width + p.slope_width - 0.5*depth)
    return p.crest_half_width


def in_main_zone(p: Project, x: float) -> bool:
    boundary = main_zone_boundary(p)
    # Mép trên của hố đào vươn ra chân đường; đường phân vùng nằm ở mép đáy đào.
    if p.main_treatment == 'Cơ học':
        return abs(x) <= p.crest_half_width + p.slope_width + 1e-9
    return boundary is not None and abs(x) <= boundary + 1e-9


def main_treated_depth(p: Project, x: float) -> float:
    if not in_main_zone(p, x) or p.main_treatment not in ('CDM', 'Cơ học'):
        return 0.0
    if p.main_treatment == 'CDM':
        return p.main_cdm_depth
    # Cọc được cắm dưới đáy đào, trong hai mép ngoài của đáy đào.
    toe = p.crest_half_width + p.slope_width
    excavation = min(p.main_replacement_depth, 2.0 * max(0.0, toe-abs(x)))
    piles = max(p.main_bamboo_depth, p.main_cajuput_depth)
    return p.main_replacement_depth+piles if abs(x) <= main_zone_boundary(p) else excavation


def soils_at(p: Project, x: float) -> list[Soil]:
    if in_main_zone(p, x) and p.main_treatment in ('PVD', 'SD', 'Chờ lún') and p.main_soils:
        return p.main_soils
    return p.soils


def axes(p: Project) -> list[tuple[str, float]]:
    p.update_geometry()
    b, toe = p.crest_half_width, p.crest_half_width + p.slope_width
    right_geom = expansion_geometry(p, 'Phải')
    left_geom = expansion_geometry(p, 'Trái')
    has_expansion = p.expansion_width > 0 and p.expansion_side in ('Trái', 'Phải', 'Hai bên')
    result = ([("Tim đường chính", 0.0), ("Vai đường chính phải", b),
               ("Chân đường chính phải", toe)] if has_expansion else
              [("Tim đường", 0.0), ("Vai đường", b), ("Chân đường", toe)])
    if p.counterweight_height > 0 and p.counterweight_width > 0:
        shoulder = p.crest_half_width + p.slope_width * (p.height - p.counterweight_height) / max(p.height, 0.001)
        outer_shoulder = shoulder + p.counterweight_width
        result += [("Vai bệ phản áp", outer_shoulder),
                   ("Chân bệ phản áp", outer_shoulder + p.counterweight_slope)]
    if has_expansion:
        result += [('Vai đường chính trái', -b), ('Chân đường chính trái', -toe)]
        if right_geom:
            result += [('Vai nền mở rộng phải', right_geom[1]),
                       ('Chân nền mở rộng phải', right_geom[2])]
        if left_geom:
            result += [('Vai nền mở rộng trái', -left_geom[1]),
                       ('Chân nền mở rộng trái', -left_geom[2])]
        if p.counterweight_height > 0 and p.counterweight_width > 0:
            shoulder = p.crest_half_width + p.slope_width * (p.height - p.counterweight_height) / max(p.height, 0.001)
            outer_shoulder = shoulder + p.counterweight_width
            result += [('Vai bệ phản áp trái', -outer_shoulder),
                       ('Chân bệ phản áp trái', -(outer_shoulder + p.counterweight_slope))]
    return result


def crest_half_widths(p: Project) -> tuple[float, float]:
    """Tọa độ vai ngoài cùng của nền ở mỗi phía."""
    left, right = expansion_geometry(p, 'Trái'), expansion_geometry(p, 'Phải')
    return (left[1] if left else p.crest_half_width,
            right[1] if right else p.crest_half_width)


def side_reach(p: Project, side: str) -> float:
    reach = p.crest_half_width + p.slope_width
    ext = expansion_geometry(p, side)
    if ext:
        reach = max(reach, ext[2])
    if p.counterweight_height > 0 and p.counterweight_width > 0:
        shoulder = (p.crest_half_width +
                    p.slope_width * (p.height-p.counterweight_height)/max(p.height, 0.001))
        reach = max(reach, shoulder+p.counterweight_width+p.counterweight_slope)
    return reach


def surface_height(p: Project, x: float) -> float:
    """Cao độ mặt đắp so với đất tự nhiên tại tọa độ ngang x."""
    side = 'Trái' if x < 0 else 'Phải'
    distance = abs(x)
    main = (p.height if distance <= p.crest_half_width else
            max(0.0, (p.crest_half_width+p.slope_width-distance)/max(p.slope_m, 0.001)))
    ext = expansion_geometry(p, side)
    if ext:
        inner, outer, toe = ext
        ext_h, ext_slope, _ = expansion_parameters(p)
        extra = (ext_h if inner <= distance <= outer else
                 max(0.0, (toe-distance)/max(ext_slope, 0.001))
                 if outer < distance <= toe else 0.0)
        main = max(main, extra)
    if p.counterweight_height > 0 and p.counterweight_width > 0:
        shoulder = (p.crest_half_width + p.slope_m*(p.height-p.counterweight_height))
        toe = shoulder+p.counterweight_width
        berm = (p.counterweight_height if shoulder <= distance <= toe else
                max(0.0, (toe+p.counterweight_slope-distance)/max(p.counterweight_m, 0.001))
                if toe < distance <= toe+p.counterweight_slope else 0.0)
        main = max(main, berm)
    return main


def mechanical_depth(p: Project) -> float:
    return (p.replacement_depth + max(p.bamboo_depth, p.cajuput_depth)
            if p.treatment_group == 'mechanical' else 0.0)


def mechanical_depth_at(p: Project, x: float) -> float:
    """Chỉ giảm lún vùng mở rộng; nền chính giữ phương án đã xử lý riêng."""
    if p.expansion_width > 0:
        side = 'Trái' if x < 0 else 'Phải'
        if (expansion_geometry(p, side) is None or
                not any(lo <= x <= hi for lo, hi in treatment_ranges(p))):
            return 0.0
    return mechanical_depth(p)


def validate_mechanical(p: Project) -> None:
    if p.treatment_group not in ('mechanical', 'drainage'):
        raise ValueError('Nhóm giải pháp xử lý không hợp lệ.')
    for value, maximum, label in ((p.replacement_depth, 4, 'Đào thay đất'),
                                  (p.bamboo_depth, 3, 'Cọc tre'),
                                  (p.cajuput_depth, 4, 'Cọc cừ tràm')):
        if not math.isfinite(value) or value < 0 or value > maximum:
            raise ValueError(f'{label}: chiều sâu phải từ 0 đến {maximum} m.')
    if p.bamboo_depth and p.cajuput_depth:
        raise ValueError('Chỉ chọn một loại cọc tre hoặc cọc cừ tràm.')
    if p.mechanical_surcharge and p.replacement_depth <= 0:
        raise ValueError('Gia tải trước chỉ dùng khi có Đào thay đất.')
    if p.treatment_group == 'mechanical' and not mechanical_depth(p):
        raise ValueError('Chọn chiều sâu đào thay đất hoặc cọc cho nhóm xử lý cơ học.')


def effective_overburden(p: Project, depth: float, treated: bool = False, x: float = 0.0) -> float:
    total = max(-p.water_depth, 0) * p.gamma_water
    replacement = max((p.replacement_depth if treated and p.treatment_group == 'mechanical'
                       and mechanical_depth_at(p, x) > 0
                       else 0.0),
                      (min(p.main_replacement_depth,
                           2.0 * max(0.0, p.crest_half_width + p.slope_width - abs(x)))
                       if in_main_zone(p, x)
                       and p.main_treatment == 'Cơ học' else 0.0))
    top = 0.0
    for s in soils_at(p, x):
        segment = max(0.0, min(s.thickness, depth - top))
        if replacement > top:
            replaced = max(0.0, min(segment, replacement - top))
            total += replaced * p.gamma_fill + (segment - replaced) * s.gamma
        else:
            total += segment * s.gamma
        top += s.thickness
        if top >= depth:
            break
    return total - max(0.0, depth - p.water_depth) * p.gamma_water


def validate_settlement_inputs(p: Project) -> None:
    if not p.soils:
        raise ValueError("Chưa khai báo lớp đất địa chất.")
    if p.method not in ("e–logP", "Cc/Cs/Pc", "Mv–logP"):
        raise ValueError(f"Phương pháp tính lún không hợp lệ: {p.method}.")
    for soil in p.soils + (p.main_soils if main_zone_boundary(p) is not None else []):
        label = soil.name or f'Lớp {soil.no}'
        if not math.isfinite(soil.gamma) or soil.gamma <= 0 or not math.isfinite(soil.thickness) or soil.thickness <= 0:
            raise ValueError(f'{label}: γ và bề dày phải dương và hữu hạn.')
        if soil.category == 'Đất rời':
            if not math.isfinite(soil.spt_n) or soil.spt_n <= 0:
                raise ValueError(f'{label}: thiếu hoặc sai N-SPT.')
            continue
        if soil.category != 'Đất dính':
            raise ValueError(f'{label}: loại đất không hợp lệ.')
        curve = valid_curve(soil.ep, soil.e, decreasing=True)
        cc = math.isfinite(soil.e0) and soil.e0 > 0 and math.isfinite(soil.cc) and soil.cc > 0
        if p.method == 'Mv–logP':
            if not valid_curve(soil.mvp, soil.mv):
                raise ValueError(f'{label}: thiếu hoặc sai bảng Mv–logP.')
        elif p.method == 'e–logP' and any(v > 0 for v in soil.e) and not curve:
            raise ValueError(f'{label}: đường cong e–logP không hợp lệ; kiểm tra cấp áp lực và e giảm theo áp lực.')
        elif not (curve or cc):
            raise ValueError(f'{label}: thiếu bảng e–logP hợp lệ hoặc e₀ và Cc.')
        if cc and (not math.isfinite(soil.cs) or soil.cs < 0 or not math.isfinite(soil.pc) or soil.pc < 0):
            raise ValueError(f'{label}: Cs và Pc phải không âm và hữu hạn.')
    if main_zone_boundary(p) is not None and p.main_treatment in ('PVD', 'SD', 'Chờ lún'):
        if len(p.main_soils) != len(p.soils) or any(
            abs(a.thickness-b.thickness) > 1e-6 for a, b in zip(p.main_soils, p.soils)
        ):
            raise ValueError('Địa chất vùng đã xử lý PVD/SD/Chờ lún phải khai báo đủ lớp, cùng bề dày với địa chất chung.')
    if p.main_treatment in ('CDM', 'Cơ học'):
        depths = ((p.main_cdm_depth,) if p.main_treatment == 'CDM' else
                  (p.main_replacement_depth, p.main_bamboo_depth,
                   p.main_cajuput_depth))
        if any(not math.isfinite(d) or d < 0 for d in depths):
            raise ValueError('Chiều sâu xử lý nền chính phải là số không âm.')
        if not any(depths):
            raise ValueError('Khai báo chiều sâu ít nhất một giải pháp xử lý nền chính.')
        if main_treated_depth(p, 0.0) > sum(s.thickness for s in p.soils) + 1e-6:
            raise ValueError('Chiều sâu xử lý nền chính vượt quá chiều sâu địa chất khai báo.')


def valid_curve(pressures, values, decreasing=False):
    return (len(pressures) == len(values) and len(values) >= 2
            and all(math.isfinite(v) and v >= 0 for v in pressures)
            and all(math.isfinite(v) and v > 0 for v in values)
            and all(a < b for a, b in zip(pressures, pressures[1:]))
            and (not decreasing or (all(a >= b for a, b in zip(values, values[1:]))
                                    and values[0] > values[-1])))



def settlement(p: Project, return_details: bool = False, locations=None, treated: bool = False):
    validate_settlement_inputs(p)
    if treated:
        validate_mechanical(p)
    locations = locations if locations is not None else axes(p)
    totals = [0.0] * len(locations)
    layers = []
    elements = []
    top = 0.0
    stopped = False
    qe = p.gamma_fill * p.height if p.height > 0 else 1.0

    for i, soil in enumerate(p.soils, 1):
        values = [0.0] * len(locations)
        step = p.sublayer if p.sublayer > 0 else soil.thickness
        boundaries = [top]
        while boundaries[-1] < top + soil.thickness - 1e-9:
            boundaries.append(min(top + soil.thickness, boundaries[-1] + step))
        treatment_end = mechanical_depth(p) if treated else 0.0
        treatment_boundaries = ([mechanical_depth_at(p, x) for _, x in locations]
                                if treated else [])
        for boundary in (treatment_end, p.replacement_depth if treated and p.treatment_group == 'mechanical' else 0.0,
                         *treatment_boundaries,
                         *(main_treated_depth(p, x) for _, x in locations)):
            if top < boundary < top + soil.thickness:
                boundaries = sorted(set(boundaries + [boundary]))
        for start, end in zip(boundaries, boundaries[1:]):
            h = end - start
            z = (start + end) / 2.0
            po = effective_overburden(p, z, treated)
            dp_center = pressure(p, z, 0)
            if z >= treatment_end and dp_center <= p.limit_ratio * po:
                stopped = True
                break
            e0 = (
                soil.e0
                if p.method == "Mv–logP" and soil.category == "Đất dính"
                else void_ratio(soil, po)
            )
            element_values = []
            dp_list = []
            po_list = []
            e0_list = []
            gamma_list = []
            cc_list = []
            cs_list = []
            pc_list = []
            for k, (_, x) in enumerate(locations):
                local_soil = soils_at(p, x)[i-1]
                dp = pressure(p, z, x)
                dp_list.append(dp)
                po_local = effective_overburden(p, z, treated, x)
                po_list.append(po_local)
                e0_local = (local_soil.e0 if p.method == 'Mv–logP' and local_soil.category == 'Đất dính'
                            else void_ratio(local_soil, po_local))
                e0_list.append(e0_local)
                gamma_list.append(local_soil.gamma-(p.gamma_water if z > p.water_depth else 0.0))
                cc_list.append(local_soil.cc)
                cs_list.append(local_soil.cs)
                pc_list.append(local_soil.pc)
                valid_ratios = [ratio for ratio in local_soil.e if ratio > 0]
                has_curve = (len(local_soil.ep) >= 2 and len(valid_ratios) >= 2
                             and max(valid_ratios) - min(valid_ratios) > 1e-9)
                has_cc = e0_local > 0 and local_soil.cc > 0
                has_mv = (p.method == 'Mv–logP' and len(local_soil.mvp) == len(local_soil.mv)
                          and len(local_soil.mv) >= 2 and any(v > 0 for v in local_soil.mv))
                if local_soil.category == "Đất rời" and local_soil.spt_n <= 0:
                    sc_cm = 0.0
                elif local_soil.category == "Đất rời" and local_soil.sand_method == "De Beer":
                    po_lab, dp_lab = po_local / 10.0, dp / 10.0
                    sc_cm = (
                        0.4 * po_lab / max(local_soil.spt_n, 1) * (100 * h) * math.log10((po_lab + dp_lab) / po_lab)
                        if po_lab > 0
                        else 0
                    )
                elif local_soil.category == "Đất dính" and not (has_curve or has_cc or has_mv):
                    sc_cm = 0.0
                elif p.method == "Mv–logP" and local_soil.category == "Đất dính" and any(
                        mv > 0 for mv in local_soil.mv):
                    mv = interpolate_log(list(zip(local_soil.mvp, local_soil.mv)), (po_local + dp / 2.0) / 10.0, True)
                    sc_cm = 100 * h * mv * dp
                elif local_soil.category == "Đất dính" and has_cc and (
                        p.method == "Cc/Cs/Pc" or not has_curve):
                    pc = max(local_soil.pc, po_local)
                    if local_soil.state == "Cố kết thường":
                        strain = local_soil.cc * math.log10((po_local + dp) / po_local) / (1 + e0_local)
                    elif po_local + dp <= pc:
                        strain = local_soil.cs * math.log10((po_local + dp) / po_local) / (1 + e0_local)
                    else:
                        strain = (
                            local_soil.cs * math.log10(pc / po_local) + local_soil.cc * math.log10((po_local + dp) / pc)
                        ) / (1 + e0_local)
                    sc_cm = 100 * h * strain
                else:
                    e1 = void_ratio(local_soil, po_local + dp)
                    strain = (e0_local - e1) / (1 + e0_local)
                    sc_cm = 100 * h * strain
                if treated and z < treatment_boundaries[k]:
                    sc_cm = 0.0
                if z < main_treated_depth(p, x):
                    sc_cm = 0.0
                values[k] += sc_cm
                element_values.append(sc_cm)

            gamma = p.gamma_fill if treated and z <= p.replacement_depth and p.treatment_group == 'mechanical' else soil.gamma
            gamma_effective = gamma - (p.gamma_water if z > p.water_depth else 0.0)
            sc_list = [v if soils_at(p, x)[i-1].category == "Đất dính" else 0.0
                       for v, (_, x) in zip(element_values, locations)]
            si_list = [
                v if soils_at(p, x)[i-1].category == "Đất rời" else (p.settlement_factor - 1.0) * v
                for v, (_, x) in zip(element_values, locations)
            ]

            elements.append(
                {
                    "lớp": i,
                    "tên": soil.name,
                    "xử_lý": (
                        'Đào thay đất' if treated and p.treatment_group == 'mechanical'
                        and z < p.replacement_depth else
                        'Cọc tre' if treated and p.treatment_group == 'mechanical'
                        and p.bamboo_depth and z < p.replacement_depth + p.bamboo_depth else
                        'Cọc cừ tràm' if treated and p.treatment_group == 'mechanical'
                        and p.cajuput_depth and z < p.replacement_depth + p.cajuput_depth else
                        'Đất chưa xử lý'
                    ),
                    "h_m": h,
                    "z_m": z,
                    "depth_m": end,
                    "gamma_eff_t_m3": gamma_effective,
                    "p0_t_m2": po,
                    "p0_list": po_list,
                    "e0": e0,
                    "e0_list": e0_list,
                    "cc": soil.cc,
                    "cc_list": cc_list,
                    "cs": soil.cs,
                    "cs_list": cs_list,
                    "pc_t_m2": soil.pc,
                    "pc_list": pc_list,
                    "gamma_eff_list": gamma_list,
                    "dp_t_m2": dp_center,
                    "dp_list": dp_list,
                    "I": dp_center / qe,
                    "Sc_list": sc_list,
                    "Si_list": si_list,
                    "St_list": [sc + si for sc, si in zip(sc_list, si_list)],
                    "Sc_cm": element_values[0] if soil.category == "Đất dính" else 0.0,
                    "Si_cm": si_list[0],
                    "S_cm": element_values[0],
                }
            )
        center = top + soil.thickness / 2.0
        row = {
            "lớp": i,
            "tên": soil.name,
            "z_m": center,
            "p0_t_m2": effective_overburden(p, center, treated),
            "dp_t_m2": pressure(p, center, 0),
            "lún_cm": values,
        }
        layers.append(row)
        totals = [a + b for a, b in zip(totals, values)]
        top += soil.thickness
        if stopped:
            break
    summary = [
        {"vị trí": label, "x_m": x, "lún_cm": totals[k]}
        for k, (label, x) in enumerate(locations)
    ]
    return (layers, summary, elements) if return_details else (layers, summary)


def mechanical_display_elements(elements: list[dict]) -> list[dict]:
    """Gộp hàng vùng xử lý theo lớp đất, giữ phân tố dz ở đất chưa xử lý."""
    displayed = []
    for element in elements:
        category = element.get('xử_lý', 'Đất chưa xử lý')
        if (category == 'Đất chưa xử lý' or not displayed or
                displayed[-1]['lớp'] != element['lớp'] or
                displayed[-1]['xử_lý'] != category):
            displayed.append(dict(element))
            continue
        previous = displayed[-1]
        old_h, add_h = previous['h_m'], element['h_m']
        total_h = old_h + add_h
        for field in ('z_m', 'gamma_eff_t_m3', 'p0_t_m2', 'dp_t_m2', 'e0'):
            previous[field] = (previous[field]*old_h + element[field]*add_h)/total_h
        for field in ('dp_list', 'p0_list', 'e0_list', 'gamma_eff_list',
                      'cc_list', 'cs_list', 'pc_list', 'I'):
            if field != 'I':
                previous[field] = [(a*old_h+b*add_h)/total_h for a,b in
                                   zip(previous[field],element[field])]
            else:
                previous[field] = (previous[field]*old_h+element[field]*add_h)/total_h
        for field in ('Sc_list', 'Si_list', 'St_list'):
            previous[field] = [a+b for a,b in zip(previous[field],element[field])]
        for field in ('Sc_cm', 'Si_cm', 'S_cm'):
            previous[field] += element[field]
        previous['h_m'] = total_h
        previous['depth_m'] = element['depth_m']
    return displayed


def trial_compensation(
    p: Project, tolerance_m: float = 0.001, max_iterations: int = 50
) -> dict:
    if not p.soils:
        raise ValueError("Chưa khai báo lớp đất.")
    original_hbl = p.h_bl
    current_hbl = 0.0
    try:
        for _ in range(1, max_iterations + 1):
            p.h_bl = current_hbl
            p.update_geometry()
            layers, _ = settlement(p)
            sc_tim = sum(
                row["lún_cm"][0]
                for s, row in zip(p.soils, layers)
                if s.category == "Đất dính"
            )
            si_sand = sum(
                row["lún_cm"][0]
                for s, row in zip(p.soils, layers)
                if s.category == "Đất rời"
            )
            si_clay = (p.settlement_factor - 1.0) * sc_tim
            st_tim_cm = sc_tim + si_clay + si_sand
            next_hbl = max(0.0, st_tim_cm / 100.0)
            diff = abs(next_hbl - current_hbl)
            if diff <= tolerance_m:
                p.h_bl = next_hbl
                p.update_geometry()
                return {
                    "h_bl_m": next_hbl,
                    "h_tt_m": p.height,
                    "a_m": p.slope_width,
                    "Sc_cm": sc_tim,
                    "Si_cm": si_clay + si_sand,
                    "lún_cm": st_tim_cm,
                }
            current_hbl = next_hbl
    except Exception:
        p.h_bl = original_hbl
        p.update_geometry()
        raise
    p.h_bl = original_hbl
    p.update_geometry()
    raise ValueError(f"Thử dần Hbl chưa tắt lún sau {max_iterations} lần lặp.")


TREATMENTS = (
    "Chờ lún",
    "Chờ lún + gia tải",
    "PVD",
    "SD",
    "PVD + gia tải",
    "SD + gia tải",
)
OLD_TREATMENTS = {
    "Cố kết tự nhiên": "Chờ lún",
    "Gia tải trước": "Chờ lún + gia tải",
    "Bấc thấm": "PVD",
    "Bấc thấm + gia tải": "PVD + gia tải",
    "Bấc thấm + đắp giai đoạn": "PVD",
}


def is_radial(mode: str) -> bool:
    return mode.startswith(("PVD", "SD"))


def effective_ch_cv(soil: Soil, radial: bool) -> float:
    """Ch/Cv chỉ tăng tốc thoát nước ngang PVD/SD; phương án khác lấy 1."""
    return max(getattr(soil, 'ch_cv', 2.0), 0.01) if radial else 1.0


def stage_schedule(p: Project) -> list[dict]:
    p.update_geometry()
    stages = p.stages if p.stages else [FillStage(p.height, p.fill_speed_cm_day, 0.0)]
    result = []
    time_val, previous = 0.0, 0.0
    for i, stage in enumerate(stages, 1):
        duration = 100 * (stage.target_height - previous) / max(stage.speed_cm_day, 0.1)
        pause = stage.pause_days if p.treatment_group != 'mechanical' or p.mechanical_wait else 0.0
        result.append(
            {
                "giai_đoạn": i,
                "bắt_đầu": time_val,
                "kết_thúc": time_val + duration,
                "h_đầu": previous,
                "h_cuối": stage.target_height,
                "tốc_độ": stage.speed_cm_day,
                "chờ_đến": time_val + duration + pause,
            }
        )
        time_val += duration + pause
        previous = stage.target_height
    return result


def fill_height(schedule: list[dict], days: float) -> float:
    if not schedule or days <= 0:
        return 0.0
    for item in schedule:
        if days < item["bắt_đầu"]:
            return item["h_đầu"]
        if days <= item["kết_thúc"]:
            dur = max(item["kết_thúc"] - item["bắt_đầu"], 1e-4)
            return (
                item["h_đầu"]
                + (days - item["bắt_đầu"]) * (item["h_cuối"] - item["h_đầu"]) / dur
            )
        if days <= item["chờ_đến"]:
            return item["h_cuối"]
    return schedule[-1]["h_cuối"]


def degree_vertical(tv: float) -> float:
    if tv <= 0:
        return 0.0
    if tv <= math.pi * 0.6**2 / 4.0:
        return math.sqrt(4.0 * tv / math.pi)
    return min(1.0, 1.0 - 10.0 ** (-(tv + 0.085) / 0.933))


def get_tv_from_u(u_percent: float) -> float:
    u = max(0.0, min(u_percent / 100.0, 0.999))
    return (math.pi / 4.0) * (u**2) if u < 0.6 else -0.933 * math.log10(1 - u) - 0.085


def ramp_consolidation_degree(
    t_from_start: float,
    t_fill: float,
    beta: float,
    tv_rate: float,
    radial: bool = True,
    ignore_uv: bool = False,
) -> tuple[float, float, float]:
    if t_from_start <= 0:
        return 0.0, 0.0, 0.0
    t_fill = max(t_fill, 0.01)
    t_eff = (
        t_from_start / 2.0
        if t_from_start <= t_fill
        else (t_from_start - t_fill) + (t_fill / 2.0)
    )
    uh = (
        max(0.0, min(1.0, 1.0 - math.exp(-beta * t_eff)))
        if (radial and beta > 0)
        else 0.0
    )
    uv = max(0.0, min(1.0, degree_vertical(tv_rate * t_eff))) if tv_rate > 0 else 0.0
    if radial and ignore_uv:
        uv = 0.0
    u = (1.0 - (1.0 - uv) * (1.0 - uh)) if radial else uv
    load_fraction = min(1.0, t_from_start / t_fill)
    return uv, uh, max(0.0, min(1.0, u * load_fraction))


def get_hansbo_f(p: Project, s: Soil, de_cm: float) -> float:
    """Tính chính xác hệ số sức cản F theo tiêu chuẩn TCVN 9355:2013."""
    if p.drain_diameter <= 0 or de_cm <= p.drain_diameter:
        raise ValueError(
            "Đường kính ảnh hưởng D phải lớn hơn đường kính tương đương bấc d_w > 0."
        )
    dw = p.drain_diameter
    n = de_cm / dw

    # 1. Tác dụng lý tưởng (Fn)
    fn = (n * n / (n * n - 1)) * math.log(n) - (3 * n * n - 1) / (4 * n * n)

    # 2. Xáo động (Fs)
    fs = (
        (max(p.permeability_ratio, 1.0) - 1.0) * math.log(max(p.smear_ratio, 1.0))
        if (not p.ignore_fs and p.drain_type != "Cọc cát")
        else 0.0
    )

    # 3. Cản thấm dọc trục (Fr)
    drain_len = (
        p.drain_length if p.drain_length > 0 else sum(lyr.thickness for lyr in p.soils)
    )
    if p.khqw < 0:
        raise ValueError("Kh/qw phải không âm.")
    fr = (
        (2.0 / 3.0) * math.pi * drain_len**2 * p.khqw
        if (not p.ignore_fr and p.drain_type != "Cọc cát")
        else 0.0
    )

    return fn + fs + fr


def treatment_history(
    p: Project,
    horizon_days: float,
    step_days: float = 10.0,
    mode: str | None = None,
    axis_index: int = 0,
) -> tuple[list[dict], list[dict]]:
    validate_consolidation_inputs(p)
    mode = OLD_TREATMENTS.get(mode or p.treatment, mode or p.treatment)
    radial = is_radial(mode)
    surcharge = "gia tải" in mode.lower()
    is_vacuum = "chân không" in mode.lower()
    locations = axes(p)
    x = locations[axis_index][1]
    local_soils = soils_at(p, x)

    is_cw = p.counterweight_height > 0 and p.counterweight_width > 0
    radial_here = radial and (not is_cw or 'bệ phản áp' not in locations[axis_index][0]
                              or p.drain_cw_enabled)
    if p.expansion_width > 0:
        side = 'Trái' if x < 0 else 'Phải'
        radial_here = (radial_here and expansion_geometry(p, side) is not None
                       and any(lo <= x <= hi for lo, hi in treatment_ranges(p)))
    schedule = stage_schedule(p)
    end_fill = schedule[-1]["kết_thúc"] if schedule else 0.0
    start_extra = schedule[-1]["chờ_đến"] if schedule else end_fill

    cached: dict[float, list[float]] = {0.0: [0.0] * len(p.soils)}

    def values(height):
        key = round(height, 7)
        if key not in cached:
            ext_height, ext_slope, ext_gamma = expansion_parameters(p)
            trial = replace(
                p,
                h_design=height,
                h_kcad=0,
                h_bl=0,
                expansion_h_design=ext_height*height/max(p.height, 0.001),
                expansion_h_kcad=0.0,
                expansion_slope_m=ext_slope,
                expansion_gamma_fill=ext_gamma,
                counterweight_height=(
                    min(p.counterweight_height, max(0, height - 0.0001))
                    if height > p.counterweight_height
                    else 0.0
                ),
            )
            trial.stages = []
            layers, _ = settlement(trial, locations=locations, treated=True)
            cached[key] = [
                layers[i]["lún_cm"][axis_index] if i < len(layers) else 0.0
                for i in range(len(p.soils))
            ]
        return cached[key]

    stage_increments = []
    for stg in schedule:
        before, after = values(stg["h_đầu"]), values(stg["h_cuối"])
        delta = [b - a for a, b in zip(before, after)]
        sc_inc = [v if s.category == "Đất dính" else 0.0 for s, v in zip(local_soils, delta)]
        si_inc = [
            v if s.category == "Đất rời" else (p.settlement_factor - 1.0) * v
            for s, v in zip(local_soils, delta)
        ]
        stage_increments.append((stg, sc_inc, si_inc))

    final = values(p.height)
    final_sc = sum(v for s, v in zip(local_soils, final) if s.category == "Đất dính")
    drain_eff_len = p.drain_length if p.drain_length > 0 else sum(s.thickness for s in local_soils)
    depth_top = 0.0
    radial_fractions = []
    for soil in local_soils:
        radial_fractions.append(max(0.0, min(1.0, (drain_eff_len-depth_top)/max(soil.thickness,.001)))
                                if radial_here else 0.0)
        depth_top += soil.thickness

    de_cm = (1.05 if p.drain_pattern == "Tam giác" else 1.13) * p.drain_spacing * 100.0
    betas, tv_rates, cvs, initial_stress, fill_increment = [], [], [], [], []

    for i, s in enumerate(local_soils):
        depth_mid = sum(x_s.thickness for x_s in local_soils[:i]) + s.thickness / 2.0
        p0 = effective_overburden(p, depth_mid, treated=True, x=x)
        dp_half = pressure(p, depth_mid, x) / 2.0
        cv_val = (
            cv_cm2_day(s, max(0.01, p0 + dp_half)) if s.category == "Đất dính" else 0.0
        )
        cvs.append(cv_val)
        initial_stress.append(p0)
        fill_increment.append(pressure(p, depth_mid, x))

        if s.category == "Đất dính" and cv_val > 0:
            hdr_cm = 100.0 * s.thickness / max(s.drainage, 1)
            tv_rates.append(cv_val / (hdr_cm**2))
            ch_val = cv_val * effective_ch_cv(s, radial)
            betas.append(
                (8.0 * ch_val)
                / (de_cm * de_cm * max(get_hansbo_f(p, s, de_cm), 0.001))
            )
        else:
            tv_rates.append(0.0)
            betas.append(0.0)

    timepoints = {0.0, float(horizon_days)}
    for x_stg in schedule:
        timepoints.update([x_stg["bắt_đầu"], x_stg["kết_thúc"], x_stg["chờ_đến"]])
    if surcharge:
        timepoints.update([start_extra, start_extra + p.surcharge_days])
    if is_vacuum:
        timepoints.update([start_extra, start_extra + p.vacuum_days])
    timepoints.update(
        min(horizon_days, j * step_days)
        for j in range(1, min(1200, math.ceil(horizon_days / step_days)) + 1)
    )

    rows = []
    for day in sorted(t for t in timepoints if 0 <= t <= horizon_days):
        by_layer_sc, by_layer_si = [0.0] * len(local_soils), [0.0] * len(local_soils)
        residual_radial, residual_unpenetrated = 0.0, 0.0

        for stg, sc_inc, si_inc in stage_increments:
            t_start, t_fill = stg["bắt_đầu"], stg["kết_thúc"] - stg["bắt_đầu"]
            if day < t_start:
                for i, increment in enumerate(sc_inc):
                    residual_radial += max(0.0,increment)*radial_fractions[i]
                    residual_unpenetrated += max(0.0,increment)*(1-radial_fractions[i])
                continue
            t_from_start = day - t_start

            for i, s in enumerate(local_soils):
                if s.category == "Đất dính" and sc_inc[i] > 0:
                    fraction = radial_fractions[i]

                    _, _, u_nat = ramp_consolidation_degree(
                        t_from_start,
                        t_fill,
                        0.0,
                        tv_rates[i],
                        radial=False,
                        ignore_uv=p.ignore_uv,
                    )
                    u_rad = u_nat
                    if fraction > 0:
                        _, _, u_rad = ramp_consolidation_degree(
                            t_from_start,
                            t_fill,
                            betas[i],
                            tv_rates[i],
                            radial=True,
                            ignore_uv=p.ignore_uv,
                        )
                        u_eff = u_nat + (u_rad - u_nat) * fraction
                    else:
                        u_eff = u_nat
                    by_layer_sc[i] += sc_inc[i] * u_eff
                    residual_radial += sc_inc[i]*fraction*(1.0-u_rad)
                    residual_unpenetrated += sc_inc[i]*(1.0-fraction)*(1.0-u_nat)
                if si_inc[i] > 0:
                    by_layer_si[i] += si_inc[i] * min(
                        1.0, max(0.0, (day - t_start) / max(t_fill, 0.01))
                    )

        sc_current, si_current = sum(by_layer_sc), sum(by_layer_si)
        residual_total = max(0.0,final_sc-sc_current)
        residual_parts = residual_radial+residual_unpenetrated
        if residual_parts > 0:
            residual_radial *= residual_total/residual_parts
            residual_unpenetrated = residual_total-residual_radial
        h = fill_height(schedule, day)

        hs = (
            p.surcharge_height
            if surcharge and start_extra <= day <= start_extra + p.surcharge_days
            else 0.0
        )
        p_vac = (
            p.vacuum_pressure
            if is_vacuum and start_extra <= day <= start_extra + p.vacuum_days
            else 0.0
        )

        strengths = []
        for i, s in enumerate(local_soils):
            if s.category == "Đất rời":
                strengths.append(0.0)
                continue
            deg = (
                max(0.0, min(1.0, by_layer_sc[i] / max(final[i], 1e-6)))
                if final[i] > 0
                else 0.0
            )
            pc = (
                initial_stress[i]
                if s.state == "Cố kết thường"
                else (s.pc if s.pc > 0 else initial_stress[i])
            )

            curr_load = (
                (
                    fill_increment[i]
                    * (h + hs * p.surcharge_gamma / p.gamma_fill)
                    / max(p.height, 0.001)
                    if p.height > 0
                    else 0.0
                )
                + p_vac
            )

            strengths.append(
                s.co
                + soil_strength_m(s)
                * max(0.0, initial_stress[i] + curr_load - pc)
                * deg
            )

        rows.append(
            {
                "ngày": day,
                "vị_trí": locations[axis_index][0],
                "x_m": x,
                "đắp_m": h,
                "gia_tải_m": hs,
                "Sc_cm": sc_current,
                "Sc_cuối_cm": final_sc,
                "Sc_t_cm": sc_current,
                "Sc_dư_cm": residual_total,
                "Sc_dư_trong_vùng_thoát_nước_cm": residual_radial,
                "Sc_dư_chưa_xử_lý_cm": residual_unpenetrated,
                "Si_cm": si_current,
                "St_cm": sc_current + si_current,
                "lún_cm": sc_current,
                "lún_dư_cm": max(0.0, final_sc - sc_current),
                "U_%": 100.0 * sc_current / final_sc if final_sc > 0 else 0,
                "lớp_cm": by_layer_sc,
                "Sc_lớp_cm": by_layer_sc,
                "Si_lớp_cm": by_layer_si,
                "St_lớp_cm": [a + b for a, b in zip(by_layer_sc, by_layer_si)],
                "C_t_m2": strengths,
            }
        )

    info = [
        {
            "lớp": i + 1,
            "tên": s.name,
            "Cv_cm2_ngày": cvs[i],
            "Sc_cuối_cm": final[i] if s.category == "Đất dính" else 0.0,
            "Si_cm": (
                final[i]
                if s.category == "Đất rời"
                else (p.settlement_factor - 1.0) * final[i]
            ),
            "lún_cuối_cm": final[i] if s.category == "Đất dính" else 0.0,
            "Co_t_m2": s.co,
            "m_cường_độ": soil_strength_m(s),
        }
        for i, s in enumerate(p.soils)
    ]
    return rows, info


def validate_consolidation_inputs(p):
    validate_settlement_inputs(p)
    for soil in p.soils + (p.main_soils if main_zone_boundary(p) is not None else []):
        if soil.category != 'Đất dính':continue
        if not valid_curve(soil.cvp, soil.cv) and not (soil.cv_constant is not None
                and math.isfinite(soil.cv_constant) and soil.cv_constant > 0):
            raise ValueError(f'{soil.name}: thiếu hoặc sai bảng Cv/Cv trung bình.')



def consolidation(
    p: Project, days: float, radial: bool = False, axis_index: int = 0,
    treated: bool = False,
) -> tuple[list[dict], dict]:
    if not math.isfinite(days) or days < 0:
        raise ValueError("Thời gian tính lún phải là số không âm.")
    validate_consolidation_inputs(p)
    layers, _ = settlement(p, treated=treated)
    positions = axes(p)
    details = []
    final_sc, final_si, current_sc = 0.0, 0.0, 0.0
    de_cm = (1.05 if p.drain_pattern == "Tam giác" else 1.13) * p.drain_spacing * 100.0

    depth_top = 0.0
    x = positions[axis_index][1]
    for soil, row in zip(soils_at(p, x), layers):
        base_settlement = row["lún_cm"][axis_index]
        treated_end = max(mechanical_depth_at(p, x) if treated else 0.0,
                          main_treated_depth(p, x))
        active_top = max(depth_top, min(depth_top + soil.thickness, treated_end))
        active_thickness = depth_top + soil.thickness - active_top
        z_active = (active_top + depth_top + soil.thickness) / 2.0
        if soil.category == "Đất dính":
            final_sc += base_settlement
            cv = cv_cm2_day(
                soil,
                effective_overburden(p, z_active, treated, x)
                + pressure(p, z_active, x) / 2.0,
            )
            path_cm = 100.0 * active_thickness / max(soil.drainage, 1)
            tv = days * cv / (path_cm**2) if path_cm > 0 else 0

            uv = degree_vertical(tv)
            u_nat = uv

            drain_eff_len = (
                p.drain_length
                if p.drain_length > 0
                else sum(lyr.thickness for lyr in p.soils)
            )
            fraction = (
                max(
                    0.0,
                    min(1.0, (drain_eff_len - depth_top) / max(soil.thickness, 0.001)),
                )
                if radial
                else 0.0
            )

            uh = 0.0
            if fraction > 0:
                ch = cv * effective_ch_cv(soil, radial)
                f_val = get_hansbo_f(p, soil, de_cm)
                th = (ch * days) / (de_cm**2) if de_cm > 0 else 0
                uh = (
                    1.0 - math.exp(-8.0 * th / max(f_val, 0.001))
                    if f_val > 0
                    else 1.0
                )

            u_rad = uh if p.ignore_uv else (1.0 - (1.0 - uv) * (1.0 - uh))
            u = u_nat + (u_rad - u_nat) * fraction
        else:
            final_si += base_settlement
            cv, tv, uv, u_nat, uh, u = 0.0, 0.0, 1.0, 1.0, 0.0, 1.0

        sc_t = base_settlement * u if soil.category == "Đất dính" else 0.0
        si_t = (
            base_settlement
            if soil.category == "Đất rời"
            else (p.settlement_factor - 1.0) * base_settlement
        )
        current_sc += sc_t
        depth_top += soil.thickness

        cu_val = 0.0
        if soil.category == "Đất dính":
            po = effective_overburden(p, z_active, treated, x)
            dp = pressure(p, z_active, x)
            pc = (
                po
                if soil.state == "Cố kết thường"
                else (soil.pc if soil.pc > 0 else po)
            )
            cu_val = soil.co + soil_strength_m(soil) * max(0.0, po + dp - pc) * u

        details.append(
            {
                "lớp": row["lớp"],
                "tên": soil.name,
                "Cv_cm2_ngày": cv,
                "Tv": tv,
                "Uv_%": uv
                * (1.0 - fraction if radial and p.ignore_uv else 1.0)
                * 100.0,
                "Uh_%": uh * 100.0,
                "U_%": u * 100.0,
                "Sc_cuối_cm": base_settlement if soil.category == "Đất dính" else 0.0,
                "Sc_t_cm": sc_t,
                "Si_cm": si_t,
                "lún_cuối_cm": base_settlement if soil.category == "Đất dính" else 0.0,
                "lún_t_cm": sc_t,
                "lún_còn_cm": (base_settlement - sc_t)
                if soil.category == "Đất dính"
                else 0.0,
                "Cu_t_m2": cu_val,
            }
        )

    final_si += (p.settlement_factor - 1.0) * final_sc
    final_total, current_total = final_sc + final_si, current_sc + final_si
    overall_u = 100.0 * current_sc / final_sc if final_sc > 0 else 0.0
    return details, {
        "ngày": days,
        "vị_trí": positions[axis_index][0],
        "Sc_cuối_cm": final_sc,
        "Sc_t_cm": current_sc,
        "Sc_dư_cm": max(0.0, final_sc - current_sc),
        "Si_cm": final_si,
        "St_cuối_cm": final_total,
        "St_t_cm": current_total,
        "St_cm": current_total,
        "lún_cuối_cm": final_sc,
        "lún_t_cm": current_sc,
        "lún_còn_cm": final_sc - current_sc,
        "U_%": overall_u,
        "Tv_avg": get_tv_from_u(overall_u),
    }


def expansion_settlement_forecast(p: Project, future_days: float) -> list[dict]:
    """Lún từ hiện tại: phần còn lại của tải cũ và phần tăng do mở rộng."""
    validate_settlement_inputs(p)
    if p.expansion_width <= 0 or p.expansion_side == 'Không':
        return []
    age = p.main_age_days
    if not math.isfinite(age) or age < 0 or not math.isfinite(future_days) or future_days < 0:
        raise ValueError('Thời gian nền chính và thời gian dự báo phải là số không âm.')
    if p.main_observed_residual_cm is not None and (
        not math.isfinite(p.main_observed_residual_cm) or p.main_observed_residual_cm < 0
    ):
        raise ValueError('Lún dư quan trắc nền chính phải là số không âm.')

    positions = axes(p)
    old = replace(p, expansion_side='Không', expansion_width=0.0)
    new_treated = p.treatment_group == 'mechanical'
    old_layers, _ = settlement(old, locations=positions, treated=False)
    combined_layers, _ = settlement(p, locations=positions, treated=new_treated)

    def degree(project, soil, x, top, days, radial):
        if soil.category != 'Đất dính':
            return 1.0
        bottom = top + soil.thickness
        treated_depth = max(main_treated_depth(project, x),
                            mechanical_depth_at(project, x) if new_treated else 0.0)
        active_top = max(top, min(bottom, treated_depth))
        active_h = bottom-active_top
        if days <= 0 or active_h <= 1e-9:
            return 0.0
        z = (active_top+bottom)/2.0
        cv = cv_cm2_day(soil, effective_overburden(project, z, treated=new_treated, x=x)
                        + pressure(project, z, x)/2.0)
        path_cm = 100.0*active_h/max(soil.drainage, 1)
        uv = degree_vertical(days*cv/(path_cm*path_cm)) if path_cm > 0 else 0.0
        if not radial:
            return uv
        drain_end = project.drain_length if project.drain_length > 0 else bottom
        fraction = min(1.0, max(0.0, (drain_end-active_top)/max(active_h, 1e-9)))
        if fraction <= 0:
            return uv
        de_cm = (1.05 if project.drain_pattern == 'Tam giác' else 1.13)*project.drain_spacing*100.0
        if de_cm <= 0:
            return uv
        ch = cv*effective_ch_cv(soil, True)
        uh = 1.0-math.exp(-8.0*ch*days/(de_cm*de_cm*max(get_hansbo_f(project, soil, de_cm), .001)))
        combined = uh if project.ignore_uv else 1.0-(1.0-uv)*(1.0-uh)
        return max(0.0, min(1.0, uv+(combined-uv)*fraction))

    raw = []
    for axis, (name, x) in enumerate(positions):
        old_now = old_future = new_accrued = new_remaining = 0.0
        depth = 0.0
        for i, base_soil in enumerate(p.soils):
            soil = soils_at(p, x)[i]
            old_final = old_layers[i]['lún_cm'][axis] if i < len(old_layers) else 0.0
            total_final = combined_layers[i]['lún_cm'][axis] if i < len(combined_layers) else 0.0
            added_final = max(0.0, total_final-old_final)
            if soil.category == 'Đất dính':
                factor = p.settlement_factor
                old_radial = p.main_treatment in ('PVD', 'SD') and in_main_zone(p, x)
                u_now = degree(old, soil, x, depth, age, old_radial)
                u_future = degree(old, soil, x, depth, age+future_days, old_radial)
                new_radial = is_radial(p.treatment)
                u_added = degree(p, soil, x, depth, future_days, new_radial)
                old_now += old_final*factor*(1-u_now)
                old_future += old_final*factor*(1-u_future)
                new_accrued += added_final*factor*u_added
                new_remaining += added_final*factor*(1-u_added)
            else:
                new_accrued += added_final
            depth += base_soil.thickness
        raw.append((name, x, old_now, old_future, new_accrued, new_remaining))

    ratio = 1.0
    if p.main_observed_residual_cm is not None:
        reference_name = ('Vai đường chính trái' if p.expansion_side == 'Trái'
                          else 'Vai đường chính phải')
        reference = next((row[2] for row in raw if row[0] == reference_name), 0.0)
        if reference <= 1e-9 and p.main_observed_residual_cm > 0:
            raise ValueError('Vùng xử lý tại vai chính có lún dư mô hình bằng 0; không thể hiệu chỉnh bằng số đo dương.')
        ratio = p.main_observed_residual_cm/reference if reference > 1e-9 else 1.0
    results = []
    for name, x, old_now, old_future, new_accrued, new_remaining in raw:
        old_now *= ratio
        old_future *= ratio
        results.append({
            'vị_trí': name, 'x_m': x,
            'lún_dư_cũ_hiện_tại_cm': old_now,
            'lún_cũ_phát_sinh_cm': max(0.0, old_now-old_future),
            'lún_do_mở_rộng_cm': new_accrued,
            'lún_phát_sinh_tổng_cm': max(0.0, old_now-old_future)+new_accrued,
            'lún_dư_sau_dự_báo_cm': old_future+new_remaining,
        })
    return results


def time_to_consolidation(p: Project, target: float = 0.99,
                          axis_index: int = 0, treated: bool = False) -> float:
    """Ngày đầu tiên U đạt mức yêu cầu theo cùng mô hình cố kết đứng."""
    if not 0 < target < 1:
        raise ValueError('Độ cố kết yêu cầu phải nằm giữa 0 và 1.')
    _, initial = consolidation(p, 0.0, axis_index=axis_index, treated=treated)
    if initial['Sc_cuối_cm'] <= 1e-12:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(40):
        _, result = consolidation(p, hi, axis_index=axis_index, treated=treated)
        if result['U_%'] >= target*100:
            break
        hi *= 2.0
    else:
        raise ValueError('Không xác định được thời gian đạt U=99% với các chỉ tiêu Cv hiện tại.')
    for _ in range(36):
        mid = (lo+hi)/2
        _, result = consolidation(p, mid, axis_index=axis_index, treated=treated)
        if result['U_%'] >= target*100:
            hi = mid
        else:
            lo = mid
    return hi


def time_to_treatment_consolidation(p: Project, mode: str | None = None,
                                    target: float = 0.99, axis_index: int = 0) -> float:
    """Thời điểm U đạt target kể cả tiến trình đắp/chờ đã khai báo."""
    if p.treatment_group == 'mechanical' and not (p.mechanical_wait or p.mechanical_surcharge):
        return time_to_consolidation(p, target, axis_index, treated=True)
    start = stage_schedule(p)[-1]['chờ_đến']
    lo, hi = 0.0, max(start, 1.0)
    def reached(day):
        history, _ = treatment_history(p, day, max(1.0, day/40), mode, axis_index)
        return history[-1]['U_%'] >= target*100
    for _ in range(35):
        if reached(hi):
            break
        hi *= 2
    else:
        raise ValueError('Không xác định được thời gian đạt U=99% với các chỉ tiêu Cv hiện tại.')
    for _ in range(30):
        mid = (lo+hi)/2
        if reached(mid):
            hi = mid
        else:
            lo = mid
    return hi


def assess_locations(
    p: Project, days: float, mode: str = "Chờ lún"
) -> list[dict]:
    mode = OLD_TREATMENTS.get(mode, mode)
    out = []
    for index, (name, _) in enumerate(axes(p)):
        if p.treatment_group == 'mechanical' and not (p.mechanical_wait or p.mechanical_surcharge):
            _, result = consolidation(p, days, axis_index=index, treated=True)
            out.append(result)
        else:
            history, _ = treatment_history(p, days, max(1.0, days / 30.0), mode, index)
            current = history[-1]
            final = current["Sc_cuối_cm"]
            achieved = min(final, max(0.0, current["Sc_t_cm"]))
            overall_u = current["U_%"]
            out.append(
                {
                    "ngày": days,
                    "vị_trí": name,
                    "Sc_cuối_cm": final,
                    "Sc_t_cm": achieved,
                    "Si_cm": current["Si_cm"],
                    "St_t_cm": current["St_cm"],
                    "St_cm": current["St_cm"],
                    "Sc_dư_cm": current["Sc_dư_cm"],
                    "Sc_dư_trong_vùng_thoát_nước_cm": current["Sc_dư_trong_vùng_thoát_nước_cm"],
                    "Sc_dư_chưa_xử_lý_cm": current["Sc_dư_chưa_xử_lý_cm"],
                    "lún_cuối_cm": final,
                    "lún_t_cm": achieved,
                    "lún_còn_cm": current["Sc_dư_cm"],
                    "U_%": overall_u,
                    "Tv_avg": get_tv_from_u(overall_u),
                }
            )
    return out


def settlement_unpenetrated_zone(
    p: Project, sublayer_max: float = 1.0, eval_days: float = 180.0
) -> dict:
    p.update_geometry()
    is_pvd_or_sd = is_radial(p.treatment)
    if not is_pvd_or_sd:
        return {
            "has_unpenetrated": False,
            "residual_thickness": 0.0,
            "elements": [],
            "sum_h": 0.0,
            "sum_sc_tim": 0.0,
            "sum_sc_vai": 0.0,
            "sum_res_tim": 0.0,
            "sum_res_vai": 0.0,
            "avg_u_pct": 0.0,
        }

    total_comp_depth = 0.0
    for s in p.soils:
        if s.cc > 0 or s.cs > 0 or s.category == "Đất dính":
            total_comp_depth += s.thickness

    l_drain = p.drain_length
    if l_drain <= 0 or l_drain >= total_comp_depth - 1e-4:
        return {
            "has_unpenetrated": False,
            "residual_thickness": 0.0,
            "elements": [],
            "sum_h": 0.0,
            "sum_sc_tim": 0.0,
            "sum_sc_vai": 0.0,
            "sum_res_tim": 0.0,
            "sum_res_vai": 0.0,
            "avg_u_pct": 0.0,
        }

    elements = []
    top = 0.0
    sum_sc_tim, sum_sc_vai = 0.0, 0.0
    sum_res_tim, sum_res_vai = 0.0, 0.0
    total_unp_h = 0.0
    stt = 1

    for i, s in enumerate(p.soils, 1):
        bot = top + s.thickness
        has_cc = s.cc > 0 or s.cs > 0 or s.category == "Đất dính"

        if has_cc and bot > l_drain:
            start_z = max(top, l_drain)
            remain_h = bot - start_z
            total_unp_h += remain_h

            count = math.ceil(remain_h / sublayer_max) if sublayer_max > 0 else 1
            cur_z_top = start_z

            for _ in range(count):
                h = min(sublayer_max, bot - cur_z_top)
                z_mid = cur_z_top + h / 2.0

                po = effective_overburden(p, z_mid)
                pc = (
                    po
                    if s.state == "Cố kết thường"
                    else (s.pc if s.pc > 0 else po)
                )
                dp_tim = pressure(p, z_mid, 0.0)
                dp_vai = pressure(p, z_mid, p.crest_half_width)

                e0 = (
                    s.e0
                    if p.method == "Mv–logP" and s.category == "Đất dính"
                    else void_ratio(s, po)
                )

                def calc_strain(dp_val):
                    if po <= 0:
                        return 0.0
                    # Use the same method branches/formulas as settlement().
                    if p.method == "Mv–logP" and any(v > 0 for v in s.mv):
                        mv = interpolate_log(list(zip(s.mvp, s.mv)), (po + dp_val / 2.0) / 10.0, True)
                        return mv * dp_val
                    if p.method == "e–logP" and len(s.ep) == len(s.e) and len(s.e) >= 2 and all(v > 0 for v in s.e):
                        return (e0 - void_ratio(s, po + dp_val)) / (1.0 + e0)
                    if s.state == "Cố kết thường":
                        return s.cc * math.log10((po + dp_val) / po) / (1.0 + e0)
                    elif po + dp_val <= pc:
                        return s.cs * math.log10((po + dp_val) / po) / (1.0 + e0)
                    else:
                        return (
                            s.cs * math.log10(pc / po)
                            + s.cc * math.log10((po + dp_val) / pc)
                        ) / (1.0 + e0)

                sc_tim = 100.0 * h * calc_strain(dp_tim)
                sc_vai = 100.0 * h * calc_strain(dp_vai)

                cv = (
                    cv_cm2_day(s, max(0.01, po + dp_tim / 2.0))
                    if s.category == "Đất dính"
                    else 0.0
                )
                hdr_cm = 100.0 * remain_h / max(s.drainage, 1)
                tv = (
                    (eval_days * cv / (hdr_cm**2))
                    if (hdr_cm > 0 and cv > 0)
                    else 0.0
                )
                uv = degree_vertical(tv)

                res_tim = sc_tim * (1.0 - uv)
                res_vai = sc_vai * (1.0 - uv)

                sum_sc_tim += sc_tim
                sum_sc_vai += sc_vai
                sum_res_tim += res_tim
                sum_res_vai += res_vai

                gamma_eff = s.gamma - (p.gamma_water if z_mid > p.water_depth else 0.0)

                elements.append(
                    {
                        "stt": stt,
                        "lớp": i,
                        "tên": s.name or f"Lớp {i}",
                        "z_m": z_mid,
                        "h_m": h,
                        "gamma_eff": gamma_eff,
                        "e0": e0,
                        "cc": s.cc,
                        "cs": s.cs,
                        "pc": pc,
                        "p0": po,
                        "dp_tim": dp_tim,
                        "dp_vai": dp_vai,
                        "sc_tim": sc_tim,
                        "sc_vai": sc_vai,
                        "uv_pct": uv * 100.0,
                        "res_tim": res_tim,
                        "res_vai": res_vai,
                    }
                )
                stt += 1
                cur_z_top += h

        top = bot

    avg_u = (100.0 * (1.0 - sum_res_tim / sum_sc_tim)) if sum_sc_tim > 0 else 0.0
    return {
        "has_unpenetrated": len(elements) > 0 and total_unp_h > 0.02,
        "residual_thickness": total_unp_h,
        "elements": elements,
        "sum_h": total_unp_h,
        "sum_sc_tim": sum_sc_tim,
        "sum_sc_vai": sum_sc_vai,
        "sum_res_tim": sum_res_tim,
        "sum_res_vai": sum_res_vai,
        "avg_u_pct": avg_u,
    }


# Bí danh tương thích ngược cho các mô-đun giao diện gọi hàm
get_unpenetrated_data = settlement_unpenetrated_zone
