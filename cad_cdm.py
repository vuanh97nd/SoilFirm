"""Đếm đối tượng CIRCLE theo layer CDM<STT> trong bản vẽ DXF."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re


LAYER = re.compile(r'^CDM\s*0*([1-9]\d*)$', re.IGNORECASE)


def count_cdm_circles(path):
    """Trả {STT: số vòng tròn}; đếm cả CIRCLE trong INSERT khi có ezdxf."""
    path = Path(path)
    if path.suffix.lower() != '.dxf':
        raise ValueError('Hãy xuất bản vẽ CAD sang DXF rồi chọn tệp .dxf.')
    counts = Counter()

    def add(layer):
        matched = LAYER.fullmatch(str(layer).strip())
        if matched:
            counts[int(matched.group(1))] += 1

    try:
        import ezdxf
    except ImportError:
        ezdxf = None
    if ezdxf is not None:
        drawing = ezdxf.readfile(str(path))

        def visit(entities, layer_override=None, depth=0):
            if depth > 12:
                return
            for entity in entities:
                layer = entity.dxf.layer
                if layer == '0' and layer_override:
                    layer = layer_override
                if entity.dxftype() == 'CIRCLE':
                    add(layer)
                elif entity.dxftype() == 'INSERT':
                    try:
                        visit(entity.virtual_entities(), layer, depth+1)
                    except (ValueError, TypeError):
                        continue
        visit(drawing.modelspace())
    else:
        # DXF ASCII: mỗi cặp mã nhóm nằm trên hai dòng. Chỉ xét ENTITIES.
        with path.open('r', encoding='utf-8', errors='replace') as stream:
            lines = iter(stream)
            pairs = zip(lines, lines)
            section = None
            pending = None
            layer = ''
            expect_section = False
            for code, value in pairs:
                code, value = code.strip(), value.strip()
                if expect_section and code == '2':
                    section = value.upper()
                    expect_section = False
                    continue
                if code == '0':
                    if pending == 'CIRCLE' and section == 'ENTITIES':
                        add(layer)
                    pending, layer = value.upper(), ''
                    if pending == 'SECTION':
                        expect_section = True
                    elif pending == 'ENDSEC':
                        section = None
                elif code == '8' and pending == 'CIRCLE':
                    layer = value
            if pending == 'CIRCLE' and section == 'ENTITIES':
                add(layer)
    if not counts:
        raise ValueError('Không tìm thấy CIRCLE trên layer CDM1, CDM2… trong DXF.')
    return dict(sorted(counts.items()))
