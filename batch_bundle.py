"""Một bộ hồ sơ hàng loạt: Excel Data, JSON TXL/SXL và PDF ghép."""
from pathlib import Path
from dataclasses import asdict, is_dataclass
from copy import deepcopy
import json
import math
import os
import tempfile


def pack(value):
    from model import Project
    if isinstance(value, Project):
        from dataclasses import fields
        return {'__soilfirm_project__': {f.name: pack(getattr(value, f.name))
                for f in fields(value) if f.name != 'calculation_results'}}
    if is_dataclass(value):
        return pack(asdict(value))
    if isinstance(value, dict):
        return {str(k): pack(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [pack(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def export_bundle(source, stem, records, failures=(), priorities=(), individual=False):
    """Xuất theo STT, trước xử lý rồi phương án đạt; tùy chọn hồ sơ từng đoạn."""
    from section_excel import export_data_results
    from report_pdf import create_report
    from pypdf import PdfWriter
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    selected = sorted([r for r in records if r.get('section_no') is not None],key=lambda r:int(r['section_no']))
    if not selected:
        raise ValueError('Chưa có kết quả phân đoạn để lưu.')
    sections = []
    individual_dir=stem.parent/'Ho_so_tung_doan'
    if individual:individual_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='soilfirm_bundle_') as directory:
        work = Path(directory)
        export_data_results(source, work/'data.xlsx', selected, [r['section_no'] for r in selected])
        writer = PdfWriter()
        try:
            for index, rec in enumerate(selected):
                before_project = rec.get('before_project')
                if before_project is None:
                    from section_excel import import_section
                    before_project, _ = import_section(source, rec['section_no'])
                before_project = deepcopy(before_project)
                before_project.calculation_results = {}
                natural_pdf = work/f'{index}_txl.pdf'
                create_report(before_project, str(natural_pdf), scope='natural')
                writer.append(str(natural_pdf), outline_item=f'STT {rec["section_no"]} - TXL')
                before_pass=rec.get('before_pass',bool((rec.get('before') or {}).get('pass_check')))
                after = None
                treated_pdf=None
                if not before_pass and rec.get('status') == 'ĐẠT':
                    project = rec['project_snapshot']
                    payload = rec.get('payload', {})
                    report = rec.get('calculation_report')
                    treated_pdf = work/f'{index}_sxl.pdf'
                    if payload.get('treatment_group') == 'cdm':
                        if not report:
                            raise ValueError(f'STT {rec["section_no"]}: thiếu kết quả CDM/ALiCC đã tính.')
                        create_report(project, str(treated_pdf), scope='cdm',
                                      special_method=payload.get('method', 'standard'), special_data=report)
                    else:
                        create_report(project, str(treated_pdf), scope='treated')
                    writer.append(str(treated_pdf), outline_item=f'STT {rec["section_no"]} - SXL')
                    after = {'option': rec.get('opt_name'), 'project': pack(project),
                             'payload': pack(payload), 'calculation': pack(report),
                             'residual_cm': rec.get('residual'), 'status': rec.get('status')}
                sections.append({'section_no': rec['section_no'],
                                 'before': {'project': pack(before_project), 'metrics': pack(rec.get('before')),
                                            'pass': bool(before_pass)},
                                 'optimized_after': after,
                                 'status': rec.get('status'), 'notes': rec.get('notes')})
                if individual:
                    section=sections[-1]
                    section['calculation_order']=['before']+(['optimized_after'] if after else [])
                    name=f'STT_{int(rec["section_no"]):04d}'
                    per_pdf=PdfWriter()
                    try:
                        per_pdf.append(str(natural_pdf),outline_item='Trước xử lý')
                        if treated_pdf is not None:per_pdf.append(str(treated_pdf),outline_item=rec.get('opt_name') or 'Phương án đạt')
                        with (work/(name+'.pdf')).open('wb') as output:per_pdf.write(output)
                    finally:per_pdf.close()
                    per_document={'format':'soilfirm_batch','version':'2026.11','source':str(source),
                        'priorities':list(priorities),'sections':[section],'records':pack([rec]),
                        'failures':pack([f for f in failures if f.get('section_no')==rec['section_no']])}
                    (work/(name+'.json')).write_text(json.dumps(per_document,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
                    for suffix in ('.pdf','.json'):os.replace(work/(name+suffix),individual_dir/(name+suffix))
            with (work/'report.pdf').open('wb') as stream:
                writer.write(stream)
        finally:
            writer.close()
        document = {'format': 'soilfirm_batch', 'version': '2026.11',
                    'source': str(source), 'priorities': list(priorities),
                    'sections': sections, 'records': pack(selected), 'failures': pack(failures)}
        (work/'results.json').write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        for name, suffix in [('data.xlsx', '.xlsx'), ('results.json', '.json'), ('report.pdf', '.pdf')]:
            os.replace(work/name, stem.with_suffix(suffix))
    return [str(stem.with_suffix(suffix)) for suffix in ('.xlsx', '.json', '.pdf')]
