"""Nhập THSH/CTDY theo STT, trao đổi BTH và dữ liệu bóc khối lượng."""
from __future__ import annotations

from copy import deepcopy
import json
import math
import re

from model import Project, Soil
from treatment_boq import calculate_section_boq


def _excel():
    try:
        import openpyxl
    except ImportError as exc:
        raise ValueError('Cần cài openpyxl để đọc và ghi bảng Excel.') from exc
    return openpyxl


def _num(value, default=0.0):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value).replace(',', '.'))
    except (ValueError, TypeError):
        return default


def _pressure_headers(sheet, row, scale):
    """Ô cấp áp lực trống/chữ không tạo điểm P=0; số 0 nhập rõ vẫn hợp lệ."""
    headers = []
    for col in range(2, sheet.max_column + 1):
        raw = sheet.cell(row, col).value
        if raw is None or isinstance(raw, bool) or not str(raw).strip():
            continue
        pressure = _num(raw, float('nan'))
        if math.isfinite(pressure) and pressure >= 0:
            headers.append((col, pressure * scale))
    return headers


def _header_strength(sheet, column):
    # Tiêu đề có thể là ô gộp và dùng font TCVN3; mẫu số không phụ thuộc font.
    for row in range(8, 11):
        value = sheet[f'{column}{row}'].value
        if value is None:
            for merged in sheet.merged_cells.ranges:
                if sheet[f'{column}{row}'].coordinate in merged:
                    value = sheet.cell(merged.min_row, merged.min_col).value
                    break
        text = str(value or '')
        match = re.search(r'(\d+(?:[.,]\d+)?)\s*[x×/X]\s*(\d+(?:[.,]\d+)?)', text)
        if match:
            values = [float(v.replace(',', '.')) for v in match.groups()]
            if all(v > 0 for v in values):
                return min(values)  # Cường độ bảo thủ khi hai phương khác nhau.
        match = re.search(r'(\d+(?:[.,]\d+)?)\s*k[nN]\s*/\s*m', text, re.I)
        if match and float(match.group(1).replace(',', '.')) > 0:
            return float(match.group(1).replace(',', '.'))
    return None


def _import_reinforcement_headers(project, sheet):
    fabric = _header_strength(sheet, 'CP')
    grid = _header_strength(sheet, 'CQ')
    strengths = {}
    if fabric is not None:
        strengths['Tmax'] = str(fabric)
    if grid is not None:
        strengths['T_char_kn'] = str(grid)
    if not strengths:
        return
    for attr, flat_key in (('cdm_inputs', 'cdm'), ('alicc_inputs', 'D')):
        states = deepcopy(getattr(project, attr, {}) or {})
        scoped = flat_key not in states
        if scoped:
            states.setdefault('Nền đường', {})
        targets = states.values() if scoped else [states]
        for state in targets:
            if not isinstance(state, dict):
                continue
            if attr == 'cdm_inputs':
                state.setdefault('geo', {}).update(strengths)
            else:
                state.update(strengths)
        setattr(project, attr, states)


def _station(value):
    if value is None:
        return ''
    if isinstance(value, (int, float)):
        km, metres = divmod(float(value), 1000)
        return f'KM {int(km)}+{metres:06.2f}'
    return str(value).strip()


def _metadata(book, cell, prefix):
    value = book['THSH'][cell].value
    if not isinstance(value, str) or '#REF!' in value:
        return ''
    return re.sub(prefix, '', value.strip(), flags=re.I).strip()


def _cv_curves(book):
    sheet = next((s for s in book if 'ecv' in s.title.casefold().replace(' ', '')), None)
    if sheet is None:
        return {}
    label_row = next((r for r in range(1, sheet.max_row + 1)
                      if 'hệ số cố kết' in str(sheet.cell(r, 1).value or '').casefold()), None)
    if label_row is None:
        return {}
    units = str(sheet.cell(label_row, 1).value or '').replace(' ', '').replace('⁻', '-').replace('⁴', '4').replace('³', '3')
    cv_scale = .1 if '10^-4' in units or '10-4' in units else 1.0
    pressure_units = str(sheet.cell(label_row + 1, 2).value or '').casefold().replace(' ', '').replace('²', '2').replace('^', '')
    if 'kg/cm2' in pressure_units:
        pressure_scale = 1.0
    elif 't/m2' in pressure_units:
        pressure_scale = .1
    else:
        raise ValueError('Sheet eCV-P: thiếu đơn vị cấp áp lực của bảng Cv.')
    headers = _pressure_headers(sheet, label_row + 2, pressure_scale)
    curves = {}
    for r in range(label_row + 3, sheet.max_row + 1):
        code = str(sheet.cell(r, 1).value or '').strip().casefold()
        if not code or code == '0':
            continue
        points = {}
        for c, pressure in headers:
            cv = _num(sheet.cell(r, c).value, -1)
            if pressure >= 0 and cv > 0:
                value = cv * cv_scale
                if pressure in points and abs(points[pressure] - value) > 1e-6:
                    raise ValueError(f'eCV-P: lớp {code} có Cv khác nhau ở cùng cấp áp lực.')
                points[pressure] = value
        if points:
            curves[code] = sorted(points.items())
    return curves


def _compression_curves(book):
    """Đọc e–log P theo mã lớp; chỉ chấp nhận cấp áp lực có đơn vị rõ ràng."""
    sheet = next((s for s in book if 'ecv' in s.title.casefold().replace(' ', '')),
                 None)
    if sheet is None:
        return {}
    label = (str(sheet['B2'].value or '').casefold().replace('²', '2')
             .replace('^', '').replace(' ', ''))
    if 't/m2' in label:
        pressure_scale = .1  # T/m² trên Excel → kg/cm² trong Soil.ep
    elif 'kg/cm2' in label:
        pressure_scale = 1.0
    else:
        raise ValueError('Sheet eCV-P: ghi rõ đơn vị cấp áp lực T/m² hoặc kg/cm² tại B2.')
    headers = _pressure_headers(sheet, 3, pressure_scale)
    curves = {}
    for row in range(4, min(sheet.max_row, 13) + 1):
        code = str(sheet.cell(row, 1).value or '').strip().casefold()
        if not code or code == '0':
            continue
        points = {}
        for col, pressure in headers:
            raw = sheet.cell(row, col).value
            ratio = _num(raw, -1.0)
            if pressure >= 0 and ratio > 0:
                if pressure in points and abs(points[pressure] - ratio) > 1e-6:
                    raise ValueError(f'eCV-P: lớp {code} có hệ số rỗng khác nhau ở cùng cấp áp lực.')
                points[pressure] = ratio
        if len(points) >= 2:
            curves[code] = sorted(points.items())
    return curves


def _section_rows(sheet):
    """Đọc đến cuối bảng; bỏ dòng chữ và tiêu đề gộp tại cột STT."""
    rows = {}
    for row in sheet.iter_rows(min_row=11, max_row=sheet.max_row):
        value = row[0].value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not math.isfinite(value) or value <= 0 or int(value) != value:
            continue
        no = int(value)
        if no in rows:
            raise ValueError(f'STT {no} bị trùng trong THSH.')
        rows[no] = row[0].row
    return rows


def _phi_degrees(value):
    # Mẫu Data dùng DDMM: 430 = 4°30′, 3000 = 30°00′.
    raw = _num(value)
    if raw >= 90:
        degrees, minutes = divmod(raw, 100)
        if minutes >= 60:
            raise ValueError(f'Góc ma sát DDMM không hợp lệ: {value}.')
        raw = degrees + minutes / 60
    if not 0 <= raw < 90:
        raise ValueError(f'Góc ma sát không hợp lệ: {value}.')
    return raw


def _drainage_faces(value):
    if value is None or str(value).strip() == '':
        return 1
    text = str(value).strip().casefold()
    if text in ('1', '1.0', '1 chiều', '1 mặt', 'một mặt'):
        return 1
    if text in ('2', '2.0', '2 chiều', '2 mặt', 'hai mặt'):
        return 2
    raise ValueError(f'Điều kiện thoát nước phải là 1 hoặc 2 mặt: {value}.')


def normalize_data_sheet_names(book):
    """Resolve fixed template tabs in memory; do not rewrite the input file."""
    import unicodedata
    for expected in ('THSH','CTDY'):
        if expected in book:continue
        matches=[name for name in book.sheetnames if ''.join(unicodedata.normalize('NFKC',name).split()).upper()==expected]
        if len(matches)>1:raise ValueError('Tên trang '+expected+' không duy nhất: '+', '.join(matches))
        if len(matches)==1:book[matches[0]].title=expected
    if 'THSH' not in book:
        raise ValueError('Không tìm thấy trang THSH trong tệp Data. Các trang hiện có: '+', '.join(book.sheetnames)+'. Chọn tệp Data phân đoạn theo mẫu; bảng thí nghiệm đọc tại mục chỉ tiêu đất. Không sử dụng AI để suy đoán cột.')


def list_sections(path):
    """Đọc cả giá trị công thức đã lưu và chuỗi STT hiển thị."""
    xl = _excel()
    book = xl.load_workbook(path, read_only=False, data_only=True)
    try:
        normalize_data_sheet_names(book)
        sheet = book['THSH']
        rows = _section_rows(sheet)
        return rows
    finally:
        book.close()


def import_section(path, number, template=None, *, load_geology=True):
    xl = _excel()
    book = xl.load_workbook(path, read_only=False, data_only=True)
    try:
        normalize_data_sheet_names(book)
        section = book['THSH']
        found = _section_rows(section).get(number)
        if found is None:
            raise ValueError(f'Không tìm thấy STT {number} trong THSH.')
        p = deepcopy(template) if template is not None else Project()
        p.name = _metadata(book, 'A3', r'^DỰ\s*ÁN\s*:?\s*')
        p.design_stage = _metadata(book, 'A4', r'^BƯỚC\s*:?\s*')
        p.work_item = _metadata(book, 'A5', r'^HẠNG\s*MỤC\s*:?\s*')
        _import_reinforcement_headers(p, section)
        p.h_bl = 0.0
        p.station_from = _station(section.cell(found, 2).value)
        p.station_to = _station(section.cell(found, 4).value)
        p.station = _station(section.cell(found, 6).value)
        p.h_design = _num(section.cell(found, 9).value)
        pavement = _num(section.cell(found, 33).value) - p.h_design
        if pavement >= 0:
            p.h_kcad = pavement
        p.crest_half_width = _num(section.cell(found, 10).value)/2
        p.slope_m = _num(section['K9'].value, p.slope_m) or p.slope_m
        p.ground_elevation = _num(section.cell(found, 8).value)
        p.borehole_name = str(section.cell(found, 7).value or '').strip()
        p.gamma_fill = _num(book['CTDY']['D9'].value, p.gamma_fill) if 'CTDY' in book else p.gamma_fill
        limit_cell = section.cell(found, 59)  # BG: giới hạn lún cho phép, cm
        limit = _num(limit_cell.value, float('nan'))
        if isinstance(limit_cell.value, bool) or not math.isfinite(limit) or limit <= 0:
            raise ValueError(f'STT {number}: THSH!{limit_cell.coordinate} thiếu hoặc sai '
                             'độ lún cho phép [ΔS] (cm), phải là số lớn hơn 0. '
                             'Nếu ô có công thức, hãy tính và lưu bằng Excel trước khi import.')
        p.residual_limit_cm = limit
        p.residual_limit_source = f'THSH!{limit_cell.coordinate} · STT {number}'
        from model import sync_data_settlement_limits
        sync_data_settlement_limits(p)
        if p.h_design <= 0 or p.crest_half_width <= 0:
            raise ValueError(f'STT {number}: thiếu chiều cao đắp hoặc bề rộng nền ở THSH.')
        if load_geology:
            if 'CTDY' not in book:
                raise ValueError('Import thủ công cần sheet CTDY chứa chỉ tiêu đất.')
            parameters = {}
            curves = _compression_curves(book)
            cv_curves = _cv_curves(book)
            for row in book['CTDY'].iter_rows(min_row=10):
                code = row[0].value
                if code is not None:
                    parameters[str(code).strip().casefold()] = row
            soils = []
            for column in range(14, 31):  # N:AD; AE là điều kiện thoát nước
                thickness = _num(section.cell(found, column).value)
                if thickness <= 0:
                    continue
                label = section.cell(10, column).value
                code = str(label or '').strip()
                if not code:
                    raise ValueError(f'STT {number}: lớp {xl.utils.get_column_letter(column)} thiếu mã ở hàng 10.')
                props = parameters.get(code.casefold())
                if props is None:
                    raise ValueError(f'STT {number}: lớp {code} chưa có chỉ tiêu trong CTDY.')
                def val(idx):
                    return props[idx-1].value if len(props) >= idx else None
                clay = str(val(2) or '').strip().casefold() == 'clay' or _num(val(9)) > 0
                curve = curves.get(code.casefold(), [])
                e0 = _num(val(8))
                if e0 <= 0 and curve:
                    e0 = curve[0][1]
                soil = Soil(no=len(soils)+1, name=code,
                            thickness=thickness, gamma=_num(val(4)),
                            category='Đất dính' if clay else 'Đất rời',
                            state='Quá cố kết' if _num(val(12)) > 0 else 'Cố kết thường',
                            e0=e0, cc=_num(val(9)), cs=_num(val(10)),
                            pc=_num(val(12)), co=_num(val(7)),
                            cohesion_c=_num(val(5)), friction_phi=_phi_degrees(val(6)),
                            drainage=_drainage_faces(section.cell(found, 31).value),
                            spt_n=int(_num(val(14))))
                if soil.gamma <= 0:
                    raise ValueError(f'STT {number}: lớp {code} thiếu γ trong CTDY.')
                soil.weak_indicators = {
                    'soil_description': ' '.join(str(val(i) or '') for i in (2, 3)),
                    'natural_state': str(val(3) or ''),
                    'e0': _num(val(8), float('nan')),
                    'c_kpa': _num(val(5), float('nan')) * 9.80665,
                    'phi': _phi_degrees(val(6)) if val(6) is not None else None,
                    'cu_kpa': _num(val(7), float('nan')) * 9.80665,
                    'spt': _num(val(14), float('nan')),
                }
                soil.weak_indicators = {k: v for k, v in soil.weak_indicators.items()
                                        if not isinstance(v, float) or math.isfinite(v)}
                # Chỉ tiêu bổ sung được nhận qua ký hiệu tiêu đề, không suy từ ô trống.
                aliases = {'w': 'w', 'wl': 'wl', 'wp': 'wp', 'b': 'liquidity', 'qc': 'qc_mpa', 'cu': 'cu_kpa'}
                for col in range(15, book['CTDY'].max_column + 1):
                    symbols = [str(book['CTDY'].cell(r, col).value or '').strip().casefold().replace('_', '') for r in (6, 7)]
                    key = next((aliases[v] for v in symbols if v in aliases), None)
                    if key and val(col) is not None:
                        soil.weak_indicators[key] = _num(val(col), float('nan'))
                if clay:
                    cv = _num(val(11))
                    if cv > 0: soil.cv_constant = cv
                    if code.casefold() in cv_curves:
                        soil.cvp = [pressure for pressure, _ in cv_curves[code.casefold()]]
                        soil.cv = [value for _, value in cv_curves[code.casefold()]]
                    elif cv > 0:
                        soil.cv = [cv]*len(soil.cvp)  # CTDY: 10⁻³ cm²/s.
                    if curve:
                        soil.ep = [pressure for pressure, _ in curve]
                        soil.e = [ratio for _, ratio in curve]
                    elif not (soil.e0 > 0 and soil.cc > 0):
                        soil.e0 = soil.cc = soil.cs = soil.pc = 0.0
                        soil.e = [0.0]*len(soil.ep)
                else:
                    soil.e0 = soil.cc = soil.cs = soil.pc = 0.0
                soils.append(soil)
            if not soils:
                raise ValueError(f'STT {number}: không có bề dày lớp đất ở THSH.')
            p.soils = soils
            if p.method not in ('Cc/Cs/Pc', 'e–logP', 'Mv–logP') and any(s.category == 'Đất dính' and s.cc <= 0 and s.name.casefold() in curves
                   for s in soils):
                p.method = 'e–logP'
        else:
            p.soils = []
            p.main_soils = []
        p.calculation_results = {}
        p.update_geometry()
        from model import FillStage
        p.stages = []
        previous = 0.0
        for height_col, speed_col, wait_col in ((72, 74, 76), (77, 79, 81), (85, 87, 89)):
            height = _num(section.cell(found, height_col).value)
            if height <= previous:
                continue
            target = height
            if target > previous:
                p.stages.append(FillStage(target, _num(section.cell(found, speed_col).value, p.fill_speed_cm_day) or p.fill_speed_cm_day,
                                          max(0.0, _num(section.cell(found, wait_col).value))))
                previous = target
        if p.stages and previous > p.height:
            p.h_bl = previous - p.h_design - p.h_kcad
            p.update_geometry()
        if p.stages and previous < p.height:
            p.stages.append(FillStage(p.height, p.fill_speed_cm_day, 0.0))
        length = _num(section.cell(found, 5).value)
        if length <= 0:
            length = _num(section.cell(found, 4).value) - _num(section.cell(found, 2).value)
        return p, max(length, 0.0)
    finally:
        book.close()


def export_data_results(source, destination, records, section_numbers=None):
    """Điền kết quả vào bản sao Data; không sửa nguồn và không thay ô đầu vào."""
    xl = _excel()
    book = xl.load_workbook(source)
    try:
        if 'THSH' not in book:
            raise ValueError('Tệp Data thiếu sheet THSH.')
        sheet = book['THSH']
        selected = set(section_numbers) if section_numbers is not None else None
        indexed = {int(rec['section_no']): rec for rec in records
                   if rec.get('section_no') is not None and
                   (selected is None or int(rec['section_no']) in selected)}
        if not indexed:
            raise ValueError('Chưa có kết quả của STT được chọn để xuất Data.')
        rows = list_sections(source)
        missing = indexed.keys() - rows.keys()
        if missing:
            raise ValueError(f'STT không có trong sheet THSH: {sorted(missing)}.')
        if selected is not None and selected - indexed.keys():
            raise ValueError(f'STT chưa được tính: {sorted(selected-indexed.keys())}.')

        # Chỉ tác động lên những cột kết quả có mô hình tính tương ứng.
        before_columns = tuple(xl.utils.get_column_letter(i) for i in range(34, 59))  # AH:BF
        after_columns = tuple(xl.utils.get_column_letter(i) for i in range(60, 103))  # BH:CX
        columns = before_columns + after_columns
        for number, row in rows.items():
            if number not in indexed:
                if selected is not None:
                    sheet.row_dimensions[row].hidden = True
                continue
            rec = indexed[number]
            for col in columns:
                sheet[f'{col}{row}'] = None
            before = rec.get('before')
            if before is None:
                from batch_calculation import natural_metrics
                raw_project, _ = import_section(source, number)
                before = natural_metrics(raw_project)
                before_pass = before['total_cm'] <= raw_project.residual_limit_cm
            else:
                before_pass = rec.get('before_pass', False)
            trial = rec.get('project_snapshot')
            for col, value in {
                'AI': before.get('sc_cm'), 'AJ': before.get('si_cm'),
                'AK': before.get('sand_si_cm'), 'AL': before.get('total_cm'),
                'AM': before.get('height_m'),
            }.items():
                if value is not None:
                    sheet[f'{col}{row}'] = value
            if before_pass or rec.get('status') == 'ĐẠT':
                sheet[f'CO{row}'] = 1
                if trial is not None and trial.counterweight_height > 0 and trial.counterweight_width > 0:
                    sheet[f'CR{row}'] = trial.counterweight_width
                    sheet[f'CS{row}'] = trial.counterweight_height
            if before_pass or rec.get('status') != 'ĐẠT':
                continue
            payload = rec.get('payload', {})
            group = payload.get('treatment_group')
            layers = payload.get('cdm_n_layer') or payload.get('reinforcement_layers') or None
            kind = payload.get('reinforcement_kind') or payload.get('kind')
            details = {
                'CP': layers if kind == 'Vải địa kỹ thuật' else None,
                'CQ': layers if kind == 'Lưới địa kỹ thuật' else None,
                'CR': trial.counterweight_width if trial is not None and trial.counterweight_height > 0 and trial.counterweight_width > 0 else None,
                'CS': trial.counterweight_height if trial is not None and trial.counterweight_height > 0 and trial.counterweight_width > 0 else None,
                'BH': rec.get('opt_name'),
                'BI': payload.get('drain_spacing') if group == 'drainage' else
                      payload.get('cdm_s') if group == 'cdm' else None,
                'BJ': payload.get('drain_length') if group == 'drainage' else
                      payload.get('cdm_lc') if group == 'cdm' else None,
                'BL': payload.get('bamboo_depth'),
                'BR': payload.get('surcharge_height'),
                'CM': payload.get('replacement_depth'),
                'CN': payload.get('bamboo_depth'),
                'CU': rec.get('after_u_pct'),
                'CV': rec.get('after_pile_settlement_cm'),
                'CW': rec.get('residual'),
                'CX': getattr(trial, 'h_bl', None) if trial is not None else None,
            }
            if trial is not None and group == 'drainage':
                from model import stage_schedule, treatment_history
                schedule = stage_schedule(trial)
                if len(schedule) > 3:
                    raise ValueError(f'STT {number}: mẫu Data chỉ có chỗ cho 3 giai đoạn đắp.')
                surcharge = 'gia tải' in trial.treatment.lower() and trial.surcharge_height > 0
                finish = schedule[-1]['chờ_đến']
                end_day = finish + (trial.surcharge_days if surcharge else 0.0)
                history, _ = treatment_history(trial, end_day, max(1.0, end_day / 40), trial.treatment, 0)
                def at(day):
                    return min(history, key=lambda item: abs(item['ngày'] - day))
                for stg, cols in zip(schedule, (('BT', 'BU', 'BV', 'BX'),
                                              ('BY', 'BZ', 'CA', 'CC'),
                                              ('CG', 'CH', 'CI', 'CK'))):
                    height_col, elevation_col, speed_col, wait_col = cols
                    current = at(stg['kết_thúc'])
                    details.update({height_col: stg['h_cuối'],
                                    elevation_col: trial.ground_elevation + stg['h_cuối'] - current['St_cm'] / 100,
                                    speed_col: stg['tốc_độ'],
                                    wait_col: stg['chờ_đến'] - stg['kết_thúc']})
                details.update({'CD': trial.surcharge_height if surcharge else 0.0,
                                'CF': trial.surcharge_days if surcharge else 0.0,
                                'CL': end_day,
                                'CU': rec.get('after_u_pct') if rec.get('after_u_pct') is not None else at(end_day)['U_%'],
                                'BK': trial.h_sand_cushion,
                                'BP': trial.ground_elevation,
                                'BQ': trial.ground_elevation - _num(payload.get('drain_length'), trial.drain_length)})
            for col, value in details.items():
                if value is not None and value != '':
                    sheet[f'{col}{row}'] = value
        # Phạm vi Data A:DD: chỉ xét các phân đoạn thực sự xuất, không xét tiêu đề.
        data_rows = [rows[number] for number in indexed]
        def has_value(value):
            return value is not None and (not isinstance(value, str) or bool(value.strip()))
        from openpyxl.worksheet.dimensions import ColumnDimension
        last_col = max(108, sheet.max_column)
        for dimension in sheet.column_dimensions.values():
            dimension.hidden = False
        for index in range(1, last_col + 1):
            col = xl.utils.get_column_letter(index)
            old = sheet.column_dimensions[col]
            width = old.width
            sheet.column_dimensions[col] = ColumnDimension(sheet, index=col, min=index, max=index,
                                                            width=width, hidden=not any(
                has_value(sheet.cell(row, index).value) for row in data_rows))
        first, last = min(data_rows), max(data_rows)
        for row in range(11, max(rows.values()) + 1):
            sheet.row_dimensions[row].hidden = row not in data_rows and (
                row in rows.values() or not any(has_value(sheet.cell(row, col).value)
                                                for col in range(1, last_col + 1)))
        for row in data_rows:
            sheet.row_dimensions[row].hidden = False
        sheet.print_area = f'A1:{xl.utils.get_column_letter(last_col)}{last}'
        book.save(destination)
    finally:
        book.close()


HEADERS = ('STT', 'Tên dự án', 'Từ KM', 'Đến KM', 'Mặt cắt', 'L đoạn (m)',
           'H đắp (m)', 'B nền (m)', 'Phương án', 'Nhóm', 'Thông số',
           'Lún dư (cm)', 'Giới hạn (cm)', 'Kết luận', 'Dữ liệu phương án JSON',
           'Dữ liệu mặt cắt JSON', 'Đào thay (m3)', 'Thoát nước (m)',
           'Cọc CDM (m)', 'CDM (m3)', 'Vải địa (m2)', 'Gia tải (m3)',
           'SD (m)', 'Chờ lún (ngày)', 'CIRCLE CDM từ CAD', 'Nguồn DXF',
           'Cách tính số cọc CDM')


def _snapshot(project):
    from dataclasses import asdict
    return json.dumps(asdict(project), ensure_ascii=False)


def _restore(text):
    data = json.loads(text)
    data['soils'] = [Soil(**entry) for entry in data.get('soils', [])]
    data['main_soils'] = [Soil(**entry) for entry in data.get('main_soils', [])]
    from model import FillStage
    data['stages'] = [FillStage(**entry) for entry in data.get('stages', [])]
    return Project(**data)


def export_bth(path, records):
    xl = _excel()
    book = xl.Workbook()
    sheet = book.active
    sheet.title = 'BTH'
    sheet.append(HEADERS)
    for index, rec in enumerate(records, 1):
        project = rec.get('project_snapshot')
        if project is None:
            continue
        boq = calculate_section_boq(rec, _num(rec.get('length')), project)
        sheet.append((rec.get('section_no') or index, project.name, project.station_from,
                      project.station_to, project.station, rec.get('length', 0),
                      project.h_design, 2*project.crest_half_width,
                      rec.get('opt_name', ''), rec.get('group', ''), rec.get('params', ''),
                      rec.get('residual', 0), rec.get('limit', 0), rec.get('status', ''),
                      json.dumps(rec.get('payload', {}), ensure_ascii=False),
                      _snapshot(project), boq['v_excavation'], boq['l_pvd'],
                      boq['l_cdm'], boq['v_cdm'], boq['a_geotextile'], boq['v_surcharge'],
                      boq['l_sd'], boq['wait_days'], rec.get('cad_cdm_count'),
                      rec.get('cad_cdm_source', ''), rec.get('cdm_count_mode', 'formula')))
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = xl.styles.Font(name='Times New Roman', bold=True, color='FFFFFF')
        cell.fill = xl.styles.PatternFill('solid', fgColor='1E3A5F')
    for column in range(1, len(HEADERS)+1):
        letter = xl.utils.get_column_letter(column)
        sheet.column_dimensions[letter].width = 18 if column < 15 else 24
    sheet.column_dimensions['O'].hidden = True
    sheet.column_dimensions['P'].hidden = True
    book.save(path)


def import_bth(path):
    xl = _excel()
    book = xl.load_workbook(path, read_only=True, data_only=True)
    try:
        if 'BTH' not in book:
            raise ValueError('Không tìm thấy sheet BTH (tệp xuất từ phần mềm).')
        sheet = book['BTH']
        if tuple(c.value for c in sheet[1])[:6] != HEADERS[:6]:
            raise ValueError('Các cột đầu của BTH không đúng cấu trúc.')
        records = []
        seen = set()
        for row in sheet.iter_rows(min_row=2, values_only=True):
            if row[0] is None:
                continue
            number = int(_num(row[0], -1))
            if number < 1 or number in seen:
                raise ValueError(f'STT {row[0]} không hợp lệ hoặc bị trùng trong BTH.')
            seen.add(number)
            if not row[14] or not row[15]:
                raise ValueError(f'STT {number}: thiếu dữ liệu phương án/mặt cắt để bóc khối lượng.')
            project = _restore(row[15])
            payload = json.loads(row[14])
            length = _num(row[5])
            if length <= 0:
                raise ValueError(f'STT {number}: chiều dài phân đoạn phải lớn hơn 0.')
            record = {'section_no': number, 'station': f'{row[2]} - {row[3]}',
                      'length': length, 'h_design': project.h_design,
                      'limit': _num(row[12]), 'group': row[9] or '',
                      'opt_name': row[8] or '', 'params': row[10] or '',
                      'residual': _num(row[11]), 'status': row[13] or '',
                      'notes': '', 'payload': payload, 'project_snapshot': project}
            if len(row) > 24 and row[24] is not None:
                record['cad_cdm_count'] = int(_num(row[24]))
                record['cad_cdm_source'] = row[25] if len(row) > 25 else ''
            record['cdm_count_mode'] = row[26] if len(row) > 26 and row[26] else (
                'cad' if record.get('cad_cdm_count') is not None else 'formula')
            record['boq'] = calculate_section_boq(record, length, project)
            records.append(record)
        return records
    finally:
        book.close()
