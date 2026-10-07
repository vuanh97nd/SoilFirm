"""Báo cáo tính lún A4 dọc, đen trắng, chừa lề trái để đóng gáy.

Không phụ thuộc vào kích thước cửa sổ Tk hoặc ảnh chụp màn hình.
Hỗ trợ xuất báo cáo song ngữ Việt / Anh qua tham số `language`.
"""
from __future__ import annotations

import math
from io import BytesIO
from functools import lru_cache
from math_format import inline_tex
import os
from copy import deepcopy
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable, KeepTogether, LongTable, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)

from model import (
    assess_locations, axes, consolidation, effective_overburden, settlement,
    cdm_design_project, stage_schedule, treatment_history, mechanical_depth, crest_half_widths,
    expansion_geometry, expansion_parameters, side_reach, main_zone_boundary,
    main_treated_depth,
    mechanical_display_elements, expansion_settlement_forecast, time_to_consolidation, treatment_ranges, cdm_time_history,
    time_to_treatment_consolidation,
)
from ui_i18n import english as _english_ui

INK = colors.black
GRID = colors.black
# 30 mm lề trái để đóng gáy, 15 mm lề phải.
LEFT = 85.04
RIGHT = 42.52
W = A4[0] - LEFT - RIGHT


def _draw_pdf_brand(canvas, enabled=True):
    if not enabled:
        return
    canvas.saveState()
    right, top = A4[0] - RIGHT, A4[1] - 19
    from pathlib import Path
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase.pdfmetrics import stringWidth
    canvas.setFillColor(colors.HexColor('#17384D'))
    name = 'SOILFIRM PRO'
    size = 8
    text_width = stringWidth(name, 'SFReportBold', size)
    text_x = right - text_width - 10
    icon = Path(__file__).with_name('logo.png')
    if icon.is_file():
        canvas.drawImage(ImageReader(str(icon)), text_x-21, top-8, width=18, height=18, mask='auto')
    canvas.setFont('SFReportBold', size)
    canvas.drawString(text_x, top, name)
    canvas.setFont('SFReportBold', 4.5)
    canvas.drawString(right-8, top+3, 'AI')
    canvas.restoreState()


def _fonts():
    candidates = [
        ('C:/Windows/Fonts/times.ttf', 'C:/Windows/Fonts/timesbd.ttf'),
        ('/opt/codex/runtimes/codex-primary-runtime/dependencies/native/libreoffice-headless/libreoffice/share/fonts/truetype/LiberationSerif-Regular.ttf',
         '/opt/codex/runtimes/codex-primary-runtime/dependencies/native/libreoffice-headless/libreoffice/share/fonts/truetype/LiberationSerif-Bold.ttf'),
        ('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
         '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf'),
    ]
    for regular, bold in candidates:
        if os.path.isfile(regular) and os.path.isfile(bold):
            pdfmetrics.registerFont(TTFont('SFReport', regular))
            pdfmetrics.registerFont(TTFont('SFReportBold', bold))
            pdfmetrics.registerFontFamily('SFReport', normal='SFReport', bold='SFReportBold')
            return 'SFReport', 'SFReportBold'
    raise RuntimeError('Không tìm thấy Times New Roman hoặc phông serif dự phòng hỗ trợ tiếng Việt.')


def _p(value, style):
    import re
    text = inline_tex(str(value))
    text = escape(text).replace('\n', '<br/>')
    def symbol(match):
        token = match.group(1)
        token = re.sub(r'([A-Za-z])_\{([^}]+)\}', r'\1<sub>\2</sub>', token)
        token = re.sub(r'([A-Za-z])_([A-Za-z0-9]+)', r'\1<sub>\2</sub>', token)
        token = token.replace(r"\sigma'", 'σ′').replace(r'\sigma', 'σ')
        token = re.sub(r'σ(′?)_([a-z])', r'σ\1<sub>\2</sub>', token)
        return token
    text = re.sub(r'\$([^$]+)\$', symbol, text)
    return Paragraph(text, style)


@lru_cache(maxsize=256)
def _math_png(expression, fontsize):
    from matplotlib.mathtext import math_to_image
    from matplotlib.font_manager import FontProperties
    from matplotlib import rc_context
    from reportlab.lib.utils import ImageReader
    stream = BytesIO()
    with rc_context({'mathtext.fontset': 'stix', 'savefig.transparent': True}):
        math_to_image(expression, stream, prop=FontProperties(family='STIXGeneral', size=fontsize),
                      dpi=400, format='png')
    content = stream.getvalue()
    image = ImageReader(BytesIO(content))
    px_w, px_h = image.getSize()
    return content, px_w * 72 / 400, px_h * 72 / 400


class MathFormula(Flowable):
    """Công thức dàn bằng MathText, giữ tỉ lệ khi đặt trong bảng PDF."""
    def __init__(self, expression, fontsize=10):
        super().__init__()
        self.content, self.natural_width, self.natural_height = _math_png(expression, fontsize)
        self.width, self.height = self.natural_width, self.natural_height + 4
    def wrap(self, availWidth, availHeight):
        self.scale = min(1.0, max(1, availWidth) / max(1, self.natural_width))
        self.width = self.natural_width * self.scale
        self.height = self.natural_height * self.scale + 4
        return self.width, self.height
    def draw(self):
        from reportlab.lib.utils import ImageReader
        self.canv.drawImage(ImageReader(BytesIO(self.content)), 0, 2,
                            width=self.width, height=self.height - 4, mask='auto')


_MATH_FORMULAS = {
 's² (vuông) hoặc 0,866025·s² (tam giác)': r'$A=s^2$  /  $A=\frac{\sqrt{3}}{2}s^2$',
 'π·D²/4': r'$A_c=\frac{\pi D^2}{4}$',
 'Ac/A': r'$a_p=\frac{A_c}{A}$',
 'ap·Ec + (1−ap)·Es': r'$E_{eq}=a_p E_c+(1-a_p)E_s$',
 'ffs·qT + fq·qH': r"$\sigma'_v=f_{fs}q_T+f_q q_H$",
 'σ′v·(Cc·D/H)²': r"$\sigma_p=\sigma'_v\left(\frac{C_c D}{H}\right)^2$",
 'max(0; (γ·H + qH − σp·ap)/(1−ap))': r'$\sigma_s=\max\left(0,\frac{\gamma H+q_H-\sigma_p a_p}{1-a_p}\right)$',
 'qu28/Fs; qu28 = qu90/n nếu khai báo qu90': r'$[q_u]=\frac{q_{u28}}{F_s},\quad q_{u28}=\frac{q_{u90}}{n}$',
 '(qT+qH)/ap ≤ [qu]': r'$q_{u,tt1}=\frac{q_T+q_H}{a_p}\leq[q_u]$',
 'σp=σ′v·(Cc·D/H)² ≤ [qu]': r"$\sigma_p=\sigma'_v\left(\frac{C_cD}{H}\right)^2\leq[q_u]$",
 'm·(A·γ′·Bxl + B·q móng + D·c)': r"$R_{tc}=m\left(A\gamma'B_{xl}+Bq_{mong}+Dc\right)$",
 'σs ≤ Rtc': r'$\sigma_s\leq R_{tc}$',
 '0,15·s·σ′v': r"$W_{T,min}=0.15s\sigma'_v$",
 'WT·(s−D)/(2D)·√(1+1/(6ε))': r'$T_{rp}=\frac{W_T(s-D)}{2D}\sqrt{1+\frac{1}{6\varepsilon}}$',
 'tan²(45°−φ/2)': r'$K_a=\tan^2\left(45^\circ-\frac{\varphi}{2}\right)$',
 '0,5·Ka·(ffs·γ·H+2fq·qH)·H': r'$T_{ds}=\frac{1}{2}K_a(f_{fs}\gamma H+2f_qq_H)H$',
 'Tr=Trp+Tds; Td/fn=Tchar·n_lớp/(fm·fn)': r'$T_r=T_{rp}+T_{ds};\quad\frac{T_d}{f_n}=\frac{T_{char}n}{f_mf_n}$',
 'A theo sơ đồ; Ac = n·πD²/4': r'$A_c=\frac{n\pi D^2}{4}$',
 '(s−D)·tanθ/2 (lưới vuông)': r'$h_a=\frac{(s-D)\tan\theta}{2}$',
 'A·H − Vs': r'$V_c=AH-V_s$',
 'Vs·γ/(A−Ac) + qH': r'$P_{soil}=\frac{V_s\gamma}{A-A_c}+q_H$',
 'Vc·γ/Ac + qH': r'$P_{col}=\frac{V_c\gamma}{A_c}+q_H$',
 '(γ·H+qH)·Lc/Eeq·100': r'$S_1=\frac{(\gamma H+q_H)L_c}{E_{eq}}\times100$',
 'Σ(ε·h·100) với cọc treo; cọc chống = 0': r'$S_2=\sum_i\varepsilon_i h_i\times100$  /  $S_2=0$',
 'S1 + S2': r'$S=S_1+S_2$',
 'Scol=Pcol·Lc/Ec·100; Ssoil=Psoil·Lc/Es·100': r'$S_{col}=\frac{P_{col}L_c}{E_c}100;\quad S_{soil}=\frac{P_{soil}L_c}{E_s}100$',
 '|Ssoil−Scol|': r'$\Delta S=|S_{soil}-S_{col}|$',
 'qu/Fs': r'$[q_u]=\frac{q_u}{F_s}$',
 'Pcol ≤ qu/Fs': r'$P_{col}\leq\frac{q_u}{F_s}$',
 'Vs=2[V1−(V2+2V3−V4−2V5)]': r'$V_s=2[V_1-(V_2+2V_3-V_4-2V_5)]$',
 'Vs=[(s−D)s²/2−π(s³−D³)/24+(4−π)(√2−1)s³/24]tanθ': r'$V_s=\left[\frac{(s-D)s^2}{2}-\frac{\pi(s^3-D^3)}{24}+\frac{(4-\pi)(\sqrt{2}-1)s^3}{24}\right]\tan\theta$',
 'Vs=s²H−π[(H/tanθ+D/2)²(Dtanθ/2+H)−(D/2)³tanθ]/3': r'$V_s=s^2H-\frac{\pi}{3}\left[\left(\frac{H}{\tan\theta}+\frac{D}{2}\right)^2\left(\frac{D\tan\theta}{2}+H\right)-\left(\frac{D}{2}\right)^3\tan\theta\right]$',
 'Vs=Vs(κ)+κ(s−κ)/4·[(√2+1)κ/2+√((s/2)²+(κ/2)²)+s/2−2D]tanθ': r'$V_s=V_s(\kappa)+\frac{\kappa(s-\kappa)}{4}\left[\frac{(\sqrt{2}+1)\kappa}{2}+\sqrt{\left(\frac{s}{2}\right)^2+\left(\frac{\kappa}{2}\right)^2}+\frac{s}{2}-2D\right]\tan\theta$',
 'Vs=Vs(vuông)+(s−D)²·D·tanθ/4': r'$V_s=V_{s,square}+\frac{(s-D)^2D\tan\theta}{4}$',
}

_MATH_FORMULAS['Vs=[(s−D)s²/2−π(s³−D³)/24+(4−π)(√2−1)s³/24]tanθ'] = (
    r'$V_s=(V_1-V_2+V_3)\tan\theta$',
    r'$V_1=\frac{(s-D)s^2}{2},\quad V_2=\frac{\pi(s^3-D^3)}{24}$',
    r'$V_3=\frac{(4-\pi)(\sqrt{2}-1)s^3}{24}$')
_MATH_FORMULAS['Vs=s²H−π[(H/tanθ+D/2)²(Dtanθ/2+H)−(D/2)³tanθ]/3'] = (
    r'$V_s=s^2H-\frac{\pi}{3}(V_1-V_2)$',
    r'$V_1=\left(\frac{H}{\tan\theta}+\frac{D}{2}\right)^2\left(\frac{D\tan\theta}{2}+H\right)$',
    r'$V_2=\left(\frac{D}{2}\right)^3\tan\theta$')
_MATH_FORMULAS['Vs=Vs(κ)+κ(s−κ)/4·[(√2+1)κ/2+√((s/2)²+(κ/2)²)+s/2−2D]tanθ'] = (
    r'$V_s=V_s(\kappa)+\frac{\kappa(s-\kappa)}{4}B\tan\theta$',
    r'$B=\frac{(\sqrt{2}+1)\kappa}{2}+\sqrt{\frac{s^2+\kappa^2}{4}}+\frac{s}{2}-2D$')
_MATH_FORMULAS['Theo nhánh H > 1,4(s−D) hoặc nhánh nền thấp; WT ≥ 0,15·s·σ′v'] = (
    r'$H>1.4(s-D):$',
    r'$W_T=\frac{1.4s f_{fs}\gamma(s-D)}{s^2-D^2}\left[s^2-D^2\left(\frac{C_cD}{H}\right)^2\right]$',
    r'$H\leq1.4(s-D):$',
    r"$W_T=\frac{s\sigma'_v}{s^2-D^2}\left[s^2-D^2\left(\frac{C_cD}{H}\right)^2\right]$",
    r"$W_T\geq0.15s\sigma'_v$")


_MATH_FORMULAS.update({
 'qu28 = qu90/n': r'$q_{u28}=\frac{q_{u90}}{n}$',
 'qu28/2': r'$S_{uc}=\frac{q_{u28}}{2}$',
 'qu28/Fs': r'$[q_u]=\frac{q_{u28}}{F_s}$',
 '(qT+qH)/ap': r'$q_{u,tt1}=\frac{q_T+q_H}{a_p}$',
 'σp=σ′v·(Cc·D/H)²': r"$\sigma_p=\sigma'_v\left(\frac{C_cD}{H}\right)^2$",
 'Ac = n·πD²/4': r'$A_c=\frac{n\pi D^2}{4}$',
 'Trp+Tds': r'$T_r=T_{rp}+T_{ds}$',
 'Tchar·n_lớp/fm': r'$T_d=\frac{T_{char}n}{f_m}$',
 'Tchar·n_lớp/(fm·fn)': r'$\frac{T_d}{f_n}=\frac{T_{char}n}{f_mf_n}$',
})

_MATH_FORMULAS.update({
 'q=γ·H+qH': r'$q=\gamma H+q_H$',
 'S1=q·Lc/(ap·Ec+(1−ap)·Es)·100': r'$S_1=\frac{qL_c}{a_pE_c+(1-a_p)E_s}\times100$',
 'Sc2=ΣSc2,i': r'$S_{c2}=\sum_i S_{c2,i}$', 'S2=Sc2': r'$S_2=S_{c2}$',
 'Si=S1': r'$S_i=S_1$', 'Si=S1+0.2·S2': r'$S_i=S_1+0.2S_2$',
 'Sc=0': r'$S_c=0$', 'Sc=Sc2': r'$S_c=S_{c2}$',
 'S=S1+S2; S2=0': r'$S=S_1+S_2,\quad S_2=0$', 'S=Si+Sc': r'$S=S_i+S_c$',
})

def _formula_cell(value):
    if isinstance(value, str) and value.startswith('$'):
        parts = value.split('\n')
        return [MathFormula(part) for part in parts] if len(parts) > 1 else MathFormula(value)
    expression = _MATH_FORMULAS.get(value)
    if expression is None and str(value).startswith('1.95*'):
        expression = r'$C_c=1.95\frac{H}{D}-0.18$'
    elif expression is None and str(value).startswith('1.50*'):
        expression = r'$C_c=1.50\frac{H_{tt}}{D}-0.07$'
    return [MathFormula(x) for x in expression] if isinstance(expression, tuple) else MathFormula(expression) if expression else value


class Section(Flowable):
    def __init__(self, label, width=W):
        super().__init__()
        self.label, self.width, self.height = label, width, 23
        self.keepWithNext = 1

    def draw(self):
        c = self.canv
        c.setStrokeColor(INK)
        c.setLineWidth(.8)
        c.line(0, self.height - 2, self.width, self.height - 2)
        c.setFont('SFReportBold', 10)
        c.setFillColor(INK)
        c.drawString(2, 5, self.label)


class CrossSection(Flowable):
    def __init__(self, project, width, height=190, show_treatment=False, cdm_data=None,
                 language='vi'):
        super().__init__()
        self.p, self.width, self.height = project, width, height
        self.show_treatment = show_treatment
        self.cdm_data = cdm_data
        self.language = language

    def _L(self, text):
        return _english_ui(text) if self.language == 'en' else text

    def draw(self):
        c, p = self.canv, self.p
        w, h = self.width, self.height
        c.setStrokeColor(GRID)
        c.rect(0, 0, w, h, stroke=1, fill=0)
        c.setFont('SFReportBold', 7)
        c.setFillColor(INK)
        c.drawCentredString(w/2, h-14,
                            self._L('SƠ ĐỒ MẶT CẮT NỀN ĐẮP')
                            if self.language == 'en'
                            else 'SƠ ĐỒ MẶT CẮT NỀN ĐẮP')

        cy, top = h*.48, h-46
        reach = max(side_reach(p, 'Trái'), side_reach(p, 'Phải'))
        scale = w*.44/max(reach, 1)
        half_l = half_r = p.crest_half_width*scale
        slope = p.slope_width*scale
        cx = w/2
        c.setLineWidth(1.3)
        c.lines([(12,cy,w-12,cy), (cx-half_l-slope,cy,cx-half_l,top),
                 (cx-half_l,top,cx+half_r,top), (cx+half_r,top,cx+half_r+slope,cy)])
        total_depth = sum(max(0, s.thickness) for s in p.soils)
        if total_depth > 0:
            bottom, depth = 12, 0.0
            c.setLineWidth(.45)
            for i, soil in enumerate(p.soils, 1):
                start = cy-(cy-bottom)*depth/total_depth
                depth += max(0, soil.thickness)
                end = cy-(cy-bottom)*depth/total_depth
                c.line(12,end,w-12,end)
                if start-end >= 11:
                    c.setFont('SFReport',6.2)
                    if self.cdm_data:
                        label = f'{soil.name or "Lớp đất"} ({soil.thickness:.2f} m)'
                    else:
                        label = f'{i}. {soil.name or "Lớp đất"} ({soil.thickness:.2f} m)'
                    while pdfmetrics.stringWidth(label,'SFReport',6.2) > w-38 and len(label)>8:
                        label = label[:-2]+'…'
                    c.drawString(18,(start+end)/2-2,label)
            c.setLineWidth(1.3)
        extension_cdm = (self.cdm_data is not None and
                         self.cdm_data.get('scope') == 'Nền mở rộng')
        boundary = None if extension_cdm or p.expansion_width > 0 else main_zone_boundary(p)
        if boundary is not None and total_depth > 0:
            old_left, old_right = cx-boundary*scale, cx+boundary*scale
            c.saveState()
            c.setStrokeColor(colors.HexColor('#AAB4BF'))
            c.setLineWidth(.5)
            if p.main_treatment in ('PVD', 'SD'):
                depth = min(total_depth, max(0.0, p.drain_length or total_depth))
                tip = cy-(cy-12)*depth/total_depth
                for i in range(9):
                    x = old_left+(i+.5)*(old_right-old_left)/9
                    if p.main_treatment == 'SD':
                        c.rect(x-1.2, tip, 2.4, cy-tip, stroke=1, fill=0)
                    else:
                        c.line(x, cy, x, tip)
            else:
                excavation = min(total_depth, max(0.0, p.main_replacement_depth))
                pile_end = min(total_depth, excavation+max(
                    p.main_bamboo_depth, p.main_cajuput_depth))
                cdm_end = min(total_depth, max(0.0, p.main_cdm_depth)) if p.main_treatment == 'CDM' else 0.0
                def old_edge(depth):
                    toe = p.crest_half_width+p.slope_width
                    return max(0.0, toe-0.5*depth)*scale
                if cdm_end > 0:
                    tip = cy-(cy-12)*cdm_end/total_depth
                    c.setDash(2, 3)
                    toe_edge = (p.crest_half_width+p.slope_width)*scale
                    c.rect(cx-toe_edge, tip, 2*toe_edge, cy-tip, stroke=1, fill=0)
                    c.setDash()
                if p.main_treatment == 'Cơ học' and excavation > 0:
                    base = cy-(cy-12)*excavation/total_depth
                    edge = old_edge(excavation)
                    path = c.beginPath()
                    toe_edge = (p.crest_half_width+p.slope_width)*scale
                    path.moveTo(cx-toe_edge, cy)
                    path.lineTo(cx+toe_edge, cy)
                    path.lineTo(cx+edge, base)
                    path.lineTo(cx-edge, base)
                    path.close()
                    c.setFillColor(colors.HexColor('#EDF0F2'))
                    c.drawPath(path, stroke=1, fill=1)
                    c.setFillColor(colors.HexColor('#718096'))
                    c.setFont('SFReport', 5.5)
                    c.drawCentredString(cx, (cy+base)/2,
                                        self._L('Đào thay đất'))
                if p.main_treatment == 'Cơ học' and pile_end > excavation:
                    start = cy-(cy-12)*excavation/total_depth
                    tip = cy-(cy-12)*pile_end/total_depth
                    top_edge = bottom_edge = old_edge(excavation or pile_end)
                    c.lines([(cx-top_edge,start,cx-bottom_edge,tip),
                             (cx+top_edge,start,cx+bottom_edge,tip)])
                    for i in range(9):
                        x = cx+(-.9+1.8*i/8)*bottom_edge
                        c.line(x, start, x, tip)
                    c.setFillColor(colors.HexColor('#718096'))
                    c.setFont('SFReport', 5.5)
                    c.drawCentredString(cx, tip-7,
                                        self._L('Cọc tre') if p.main_bamboo_depth
                                        else self._L('Cừ tràm'))
            c.restoreState()
            c.setFillColor(colors.HexColor('#718096'))
            c.setFont('SFReport', 6)
            c.drawCentredString(cx, cy-10,
                                self._L('Phương án đã xử lý của nền chính:')
                                + f' {p.main_treatment}')
            c.setFillColor(INK)
        if p.counterweight_height > 0:
            by = cy + min(25, (top-cy)*p.counterweight_height/max(p.height,.1))
            for sign in (-1, 1):
                edge = cx + sign*(half_l+slope)
                c.lines([(edge,cy,edge-sign*12,by),
                         (edge-sign*12,by,edge-sign*(12+p.counterweight_width*5),by)])
        c.setFont('SFReport', 7)
        c.drawCentredString(cx, top+6, 'B = %.2f m' % (2*p.crest_half_width))
        if p.expansion_width > 0 and p.expansion_side != 'Không':
            vertical = (top-cy)/max(p.height, .001)
            ext_h, ext_slope, _ = expansion_parameters(p)
            ext_htk = p.expansion_h_design or p.h_design
            y = cy+ext_h*vertical
            for side, sign in (('Trái', -1), ('Phải', 1)):
                geometry = expansion_geometry(p, side)
                if geometry is None:
                    continue
                inner, outer, toe = geometry
                x_inner, x_outer, x_toe = (cx+sign*x*scale for x in geometry)
                c.saveState()
                x_main_toe = cx+sign*(p.crest_half_width+p.slope_m*p.height)*scale
                main_join_y = cy+min(ext_h,p.height)*vertical
                patch = c.beginPath()
                patch.moveTo(x_inner, y)
                patch.lineTo(x_outer, y)
                patch.lineTo(x_toe, cy)
                patch.lineTo(x_main_toe, cy)
                patch.lineTo(x_inner, main_join_y)
                patch.close()
                c.setFillColor(colors.HexColor('#DDEDEF'))
                c.drawPath(patch, stroke=0, fill=1)
                c.setStrokeColor(colors.HexColor('#34747C'))
                c.setDash(3, 2)
                c.setLineWidth(1)
                c.lines([(x_inner,y,x_outer,y), (x_outer,y,x_toe,cy)])
                c.line(x_inner, main_join_y, x_main_toe, cy)
                if y > main_join_y:
                    c.line(x_inner, main_join_y, x_inner, y)
                x_dim = x_outer+sign*5
                y_htk = cy+ext_htk*vertical
                c.line(x_dim, cy, x_dim, y_htk)
                c.restoreState()
                c.setFont('SFReport', 6)
                c.drawCentredString((x_inner+x_outer)/2, y+3,
                                    f'b={p.expansion_width:.2f}m')
                c.drawCentredString((x_outer+x_toe)/2, (cy+y)/2+3,
                                    f'1:{ext_slope:.2f}')
                if sign > 0:
                    c.drawString(x_dim+3, (cy+y_htk)/2, f'htk={ext_htk:.2f}m')
                else:
                    c.drawRightString(x_dim-3, (cy+y_htk)/2,
                                      f'htk={ext_htk:.2f}m')
        if self.cdm_data and total_depth > 0:
            data = self.cdm_data
            params = data['params']
            tip = cy-(cy-12)*min(total_depth, params['Lc'])/total_depth
            if data['scope'] == 'Nền mở rộng' or p.expansion_width > 0:
                ranges = []
                for side, sign in (('Trái', -1), ('Phải', 1)):
                    geometry = expansion_geometry(p, side)
                    if geometry:
                        ranges = [(cx+lo*scale,cx+hi*scale) for lo,hi in treatment_ranges(p)]
                        break
            else:
                ranges = [[cx-half_l-slope, cx+half_l+slope]]
            c.saveState()
            c.setStrokeColor(colors.HexColor('#34747C'))
            c.setLineWidth(.7)
            for left, right in ranges:
                count = max(1, min(35, int((right-left)/max(params['s']*scale, 1))))
                for i in range(count):
                    x = left+(i+.5)*(right-left)/count
                    radius = min(params['D']*scale/2, (right-left)/(count*3))
                    c.rect(x-radius, tip, 2*radius, cy-tip, fill=0, stroke=1)
                dimension_x = min(w-15,right+9)
                c.line(dimension_x,cy,dimension_x,tip)
                c.line(dimension_x-3,cy,dimension_x+3,cy)
                c.line(dimension_x-3,tip,dimension_x+3,tip)
                c.setFont('SFReportBold',7)
                c.drawCentredString((left+right)/2,tip-9,f'Lc = {params["Lc"]:.2f} m')
            c.restoreState()
        if boundary is not None:
            c.saveState()
            c.setStrokeColor(colors.HexColor('#AAB4BF'))
            c.setDash(4, 3)
            for sign in (-1, 1):
                bx = cx+sign*boundary*scale
                c.line(bx, cy, bx, 15)
            c.restoreState()
            c.setFont('SFReport', 6)
            c.setFillColor(colors.HexColor('#718096'))
            c.drawCentredString(cx, 5,
                                self._L('Ranh giới nền chính xử lý')
                                + f' {p.main_treatment}')
        c.setStrokeColor(INK)
        c.line(cx, cy, cx, top)
        c.setFillColor(INK)
        c.drawString(cx+4, (cy+top)/2, 'Htt %.2f m' % p.height)
        ranges = [(cx+left*scale, cx+right*scale) for left,right in treatment_ranges(p)]
        if p.expansion_width > 0 and p.expansion_side != 'Không':
            c.saveState()
            c.setStrokeColor(colors.HexColor('#075985'))
            c.setFillColor(colors.HexColor('#075985'))
            c.setFont('SFReportBold',8)
            for left,right in ranges:
                dimension_y=cy+12
                c.line(left,cy,left,dimension_y+3)
                c.line(right,cy,right,dimension_y+3)
                c.line(left,dimension_y,right,dimension_y)
                for xp in (left,right):
                    c.line(xp-2,dimension_y-2,xp+2,dimension_y+2)
                c.drawCentredString((left+right)/2,dimension_y+4,
                                    f'Bxl = {(right-left)/scale:.2f} m')
            c.restoreState()

        if self.show_treatment and p.treatment.startswith(('PVD', 'SD')):
            length = p.drain_length if p.drain_length > 0 else total_depth
            tip = cy-(cy-12)*min(total_depth,length)/max(total_depth,.01)
            for left,right in ranges:
                for i in range(9):
                    x = left+(i+.5)*(right-left)/9
                    if p.treatment.startswith('SD'):
                        c.rect(x-2,tip,4,cy-tip,stroke=1,fill=0)
                    else:
                        c.line(x,cy,x,tip)
                c.line(left,cy+2,right,cy+2)
        if self.show_treatment and p.treatment_group == 'mechanical' and total_depth > 0:
            excavation_bottom = cy-(cy-12)*min(total_depth,p.replacement_depth)/total_depth
            for left,right in ranges:
                inset = (0.0 if p.expansion_width > 0 else
                         min(p.replacement_depth*scale,(right-left)/2))
                bottom_left,bottom_right = left+inset,right-inset
                if p.expansion_width > 0:
                    inset = min(p.replacement_depth*scale, right-left)
                    if (left+right)/2 < cx:
                        bottom_left = left+inset
                    else:
                        bottom_right = right-inset
                if p.replacement_depth > 0:
                    excavation = c.beginPath()
                    excavation.moveTo(left,cy)
                    excavation.lineTo(right,cy)
                    excavation.lineTo(bottom_right,excavation_bottom)
                    excavation.lineTo(bottom_left,excavation_bottom)
                    excavation.close()
                    c.drawPath(excavation,stroke=1,fill=0)
                for depth,label in ((p.bamboo_depth,self._L('Cọc tre')),
                                    (p.cajuput_depth,self._L('Cọc cừ tràm'))):
                    if depth <= 0:
                        continue
                    tip = cy-(cy-12)*min(total_depth,p.replacement_depth+depth)/total_depth
                    for i in range(9):
                        x = bottom_left+(i+.5)*(bottom_right-bottom_left)/9
                        c.line(x,excavation_bottom,x,tip)
                    c.setFont('SFReport',6)
                    c.drawCentredString((left+right)/2,tip-8,f'{label}: {depth:.2f} m')


class SettlementChart(Flowable):
    def __init__(self, rows, width=W, height=220, treated=False,
                 residual=False, assessment_day=None, language='vi'):
        super().__init__()
        self.rows, self.width, self.height, self.treated = rows, width, height, treated
        self.residual, self.assessment_day = residual, assessment_day
        self.language = language

    def _L(self, text):
        return _english_ui(text) if self.language == 'en' else text

    def draw(self):
        c, rows, w, h = self.canv, self.rows, self.width, self.height
        left, right, bottom, top = 66, w-21, 33, h-37
        c.setStrokeColor(GRID)
        c.rect(0, 0, w, h, fill=0, stroke=1)
        c.setFont('SFReportBold', 10)
        c.setFillColor(INK)
        c.drawCentredString(w/2, h-17,
                            self._L('BIỂU ĐỒ LÚN THEO THỜI GIAN')
                            if self.language == 'en'
                            else 'BIỂU ĐỒ LÚN THEO THỜI GIAN')
        if not rows:
            return
        xs = [max(0.0, float(r[0])) for r in rows]
        ys = [max(0.0, float(r[1])) for r in rows]
        xmax = max(xs+[1.0]); ymax = max(ys+[.01])*1.1
        c.setFont('SFReport', 7)
        c.setLineWidth(.35)
        for i in range(6):
            x = left+(right-left)*i/5
            y = top-(top-bottom)*i/5
            c.setStrokeColor(INK)
            c.setLineWidth(.2)
            c.line(x,bottom,x,top); c.line(left,y,right,y)
            c.setFillColor(INK)
            c.drawCentredString(x,bottom-12,'%.0f' % (xmax*i/5))
            c.drawRightString(left-5,y-2,'%.2f' % (0 if i == 0 else
                              (ymax*i/5 if self.residual else -ymax*i/5)))
        c.setFont('SFReportBold', 8)
        if self.treated:
            axis_text = self._L('THỜI GIAN (NGÀY)')
        else:
            axis_text = self._L('THỜI GIAN (NĂM)')
        c.drawCentredString(w/2, 6, axis_text)
        c.saveState(); c.translate(13,(bottom+top)/2); c.rotate(90)
        c.drawCentredString(0,0,
                            self._L('Sc dư (m)') if self.residual else self._L('St (m)'))
        c.restoreState()
        points = [(left+(right-left)*x/xmax, top-(top-bottom)*y/ymax)
                  for x,y in zip(xs,ys)]
        c.setStrokeColor(INK); c.setFillColor(colors.white)
        c.setLineWidth(1.0)
        for a,b in zip(points,points[1:]): c.line(*a,*b)
        for x,y in points: c.rect(x-2.2,y-2.2,4.4,4.4,stroke=1,fill=1)
        if self.residual and self.assessment_day is not None:
            reference = self.assessment_day/(1.0 if self.treated else 365.25)
            index = min(range(len(rows)), key=lambda i: abs(xs[i]-reference))
            xp, yp = points[index]
            c.setDash(2,2); c.line(xp,bottom,xp,top); c.setDash()
            c.setFillColor(INK)
            c.circle(xp,yp,2.8,stroke=1,fill=1)
            c.setFont('SFReportBold',6.8)
            c.drawRightString(right-3,top-10,
                              self._L('Sc dư') + f' = {ys[index]*100:.2f} cm')


class StagedSettlementChart(Flowable):
    def __init__(self, rows, width=W, height=270, assessment_day=None, language='vi', stages=None):
        super().__init__()
        self.rows,self.width,self.height=rows,width,max(240,height)
        self.assessment_day=assessment_day
        self.language=language
        self.stages=stages or []

    def _L(self,text):
        return _english_ui(text) if self.language=='en' else text

    def draw(self):
        c,rows,w,h=self.canv,self.rows,self.width,self.height
        if not rows:
            return
        left,right,bottom,top=58,w-15,39,h-34
        xmax=max(1.0,max(r['ngày'] for r in rows))
        ymax=max(1.0,math.ceil(max(max(r['hne_m'],r['he_m']) for r in rows)*1.1))
        ymin=-max(1.0,math.ceil(max(r['st_cm']/100 for r in rows)*1.15))
        x=lambda day:left+(right-left)*day/xmax
        y=lambda value:bottom+(top-bottom)*(value-ymin)/(ymax-ymin)
        c.saveState()
        c.setFont('SFReportBold',10)
        c.setFillColor(INK)
        c.drawCentredString(w/2,h-15,self._L('Biểu đồ tiến trình đắp và độ lún theo thời gian'))
        c.setFont('SFReport',7)
        for i in range(9):
            value=ymin+(ymax-ymin)*i/8
            yp=y(value)
            c.setStrokeColor(GRID);c.setLineWidth(.3);c.setDash(1,2)
            c.line(left,yp,right,yp)
            c.setFillColor(INK);c.drawRightString(left-6,yp-2,f'{value:.1f}')
        for i in range(7):
            day=xmax*i/6;xp=x(day)
            c.setStrokeColor(GRID);c.setLineWidth(.3);c.setDash(1,2)
            c.line(xp,bottom,xp,top)
            c.setFillColor(INK);c.drawCentredString(xp,bottom-12,f'{day:.0f}')
        c.setDash();c.setStrokeColor(INK);c.setLineWidth(.7)
        c.rect(left,bottom,right-left,top-bottom,stroke=1,fill=0)
        c.line(left,y(0),right,y(0))
        c.setFont('SFReportBold',8)
        c.drawCentredString((left+right)/2,9,self._L('Thời gian (ngày)'))
        for text,mid in (('Chiều cao (m)',(y(0)+top)/2),('Độ lún (m)',(bottom+y(0))/2)):
            c.saveState();c.translate(14,mid);c.rotate(90)
            c.drawCentredString(0,0,self._L(text));c.restoreState()
        series=[('hne_m',1,'#111111',(5,3),'Tổng chiều dày đắp'),
                ('he_m',1,'#FF0000',(),'Chiều cao đắp thực tế'),
                ('st_cm',-.01,'#0000FF',(7,3),'Độ lún')]
        for key,factor,color,dash,label in series:
            c.setStrokeColor(colors.HexColor(color));c.setLineWidth(1.5);c.setDash(*dash)
            for one,two in zip(rows,rows[1:]):
                c.line(x(one['ngày']),y(one[key]*factor),x(two['ngày']),y(two[key]*factor))
            c.setDash();c.setFillColor(colors.HexColor(color))
            stride=max(1,len(rows)//12)
            for row in rows[::stride]:
                c.circle(x(row['ngày']),y(row[key]*factor),1.3,stroke=0,fill=1)
        lw,lh=172,58
        lx,ly=right-lw-5,max(bottom+5,y(0)-10)
        ly=min(ly,top-lh-5)
        c.setFillColor(colors.white);c.setStrokeColor(INK);c.setLineWidth(.4)
        c.rect(lx,ly,lw,lh,stroke=1,fill=1)
        for i,(_,_,color,dash,label) in enumerate(series):
            yp=ly+lh-13-i*17
            c.setStrokeColor(colors.HexColor(color));c.setLineWidth(1.5);c.setDash(*dash)
            c.line(lx+10,yp,lx+43,yp);c.setDash()
            c.setFillColor(INK);c.setFont('SFReport',7)
            c.drawString(lx+49,yp-2,self._L(label))
        c.restoreState()


def _table(rows, widths, normal, bold, *, header=1,
           last=False, font_size=7.3, padding=3):
    cell = ParagraphStyle('cell', parent=normal, fontSize=font_size,
                          leading=font_size+2, alignment=TA_CENTER)
    head = ParagraphStyle('head', parent=bold, fontSize=font_size,
                          leading=font_size+2, alignment=TA_CENTER)
    data = [[v if isinstance(v, Flowable) or (isinstance(v, list) and all(isinstance(x, Flowable) for x in v)) else _p(v, head if i < header or (last and i == len(rows)-1) else cell)
             for v in row] for i,row in enumerate(rows)]
    t = LongTable(data, colWidths=widths, repeatRows=header, hAlign='LEFT')
    commands = [
        ('GRID',(0,0),(-1,-1),.35,GRID),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),1.5),
        ('RIGHTPADDING',(0,0),(-1,-1),1.5),
        ('TOPPADDING',(0,0),(-1,-1),padding),
        ('BOTTOMPADDING',(0,0),(-1,-1),padding),
    ]
    if last:
        commands.append(('LINEABOVE',(0,-1),(-1,-1),.8,INK))
    t.setStyle(TableStyle(commands))
    return t


def _kv(items, normal, bold, width):
    rows = [[_p(label, bold), _p(value, normal)] for label,value in items]
    t = Table(rows, colWidths=[width*.53,width*.47])
    t.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2),
        ('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2),
    ]))
    return t


def _time_rows(project, language='vi'):
    # Các mốc tăng dần đến 50 năm hoặc khi U đạt 99%; trục năm như ảnh mẫu.
    months = [0,1,2,3,6,9,12,18,24,36,48,60,84,120,180,240,360,480,600]
    rows = []
    for m in months:
        _, r = consolidation(project, m*365.25/12, radial=False, axis_index=0)
        rows.append((m/12, r))
        if r['U_%'] >= 99 and m >= 12:
            break
    return rows


def _e_at_zero(soil):
    """e₀ của hồ sơ là mẫu thí nghiệm e tại P=0, không phải e(Po)."""
    for pressure, void in zip(soil.ep, soil.e):
        if abs(pressure) < 1e-9 and void > 0:
            return void
    return soil.e0 if soil.e0 > 0 else None


def _report_events(project, schedule, language='vi'):
    """Tạo mốc có kết quả riêng cho mỗi đợt đắp và thời gian chờ được khai báo."""
    L = lambda s: _english_ui(s) if language == 'en' else s
    events = []
    for s in schedule:
        number = s['giai_đoạn']
        if language == 'en':
            events.append((f'AFTER FILL STAGE {number}', s['bắt_đầu'], s['kết_thúc']))
            if s['chờ_đến'] > s['kết_thúc'] + 1e-7:
                events.append((f'AFTER WAITING STAGE {number}',
                               s['kết_thúc'], s['chờ_đến']))
        else:
            events.append((f'SAU ĐẮP GIAI ĐOẠN {number}',
                           s['bắt_đầu'], s['kết_thúc']))
            if s['chờ_đến'] > s['kết_thúc'] + 1e-7:
                events.append((f'SAU CHỜ LÚN GIAI ĐOẠN {number}',
                               s['kết_thúc'], s['chờ_đến']))

    mode = project.treatment.lower()
    start = schedule[-1]['chờ_đến'] if schedule else 0.0
    if 'gia tải' in mode:
        events.append((L('BẮT ĐẦU GIA TẢI'), start, start))
        if project.surcharge_days > 0:
            events.append((L('SAU CHỜ GIA TẢI'),
                           start, start+project.surcharge_days))
    if 'chân không' in mode:
        events.append((L('BẮT ĐẦU HÚT CHÂN KHÔNG'), start, start))
        if project.vacuum_days > 0:
            events.append((L('SAU CHỜ HÚT CHÂN KHÔNG'),
                           start, start+project.vacuum_days))
    return sorted(events, key=lambda item: item[2])


def _translate_flowable(flowable):
    """Dịch tiêu đề và nội dung bảng cho chế độ English."""
    if isinstance(flowable, Paragraph):
        return Paragraph(_english_ui(flowable.text), flowable.style)
    if isinstance(flowable, Section):
        flowable.label = _english_ui(flowable.label)
    if isinstance(flowable, (CrossSection, SettlementChart, StagedSettlementChart)):
        flowable.language = 'en'
    if isinstance(flowable, (Table, LongTable)):
        flowable._cellvalues = [[_translate_flowable(cell) if isinstance(cell, Flowable)
                                 else _english_ui(cell) if isinstance(cell, str) else cell
                                 for cell in row] for row in flowable._cellvalues]
    if isinstance(flowable, KeepTogether):
        flowable._content = [_translate_flowable(item) for item in flowable._content]
    return flowable


def _report_identity(project,method,normal,bold,L):
    station=(' — '.join(v for v in (project.station_from,project.station_to) if v)
             or project.station or '—')
    return _kv([(L('Lý trình'),station),(L('Hạng mục'),project.work_item or '—'),
                (L('Bước thiết kế'),project.design_stage or '—')],normal,bold,W)


def _geology_tables(project,normal,bold,L,include_spt=True):
    rows=[[L('STT'),L('Lớp đất'),L('Loại đất'),'h (m)',L('Đáy')+' (m)',
           'γ (T/m³)','N-SPT','e₀','Cc','Cs','Pc (T/m²)','cᵤ (T/m²)',
           'Cv (10⁻³ cm²/s)','Ch/Cv']]
    depth=0.0
    for index,soil in enumerate(project.soils,1):
        depth+=soil.thickness
        e=_e_at_zero(soil)
        rows.append([index,soil.name or f'{L("Lớp")} {index}',L(soil.category),
                     f'{soil.thickness:.2f}',f'{depth:.2f}',f'{soil.gamma:.2f}',
                     soil.spt_n or '—',f'{e:.3f}' if e is not None else '—',
                     f'{soil.cc:.3f}',f'{soil.cs:.3f}',f'{soil.pc:.2f}',
                     f'{soil.co:.2f}',f'{soil.cv[0]:.3f}' if soil.cv else '—',
                     f'{soil.ch_cv:.2f}'])
    weights=[3,10,9,5,5,6,5,5,5,5,6,6,9,6]
    if not include_spt:
        rows = [row[:6] + row[7:] for row in rows]
        weights = weights[:6] + weights[7:]
    widths=[W*v/sum(weights) for v in weights]
    info = (L('Tên lỗ khoan') + f': {project.borehole_name or "—"}; '
            + L('Cao độ lỗ khoan (m)') + f': {project.ground_elevation:.3f}; '
            + L('Chiều sâu lỗ khoan tính toán (m)') + f': {project.borehole_depth:.3f}')
    return [_p(info,normal),Spacer(1,4),
            _table(rows,widths,normal,bold,font_size=6.2,padding=3),Spacer(1,8)]


def _check_text(symbol,value,allowed_symbol,allowed,unit,L):
    passed=value<=allowed
    sign='≤' if passed else '>'
    return (f'{symbol} = {value:.2f} {unit} {sign} '
            f'{allowed_symbol} = {allowed:.2f} {unit} — '
            + L('ĐẠT' if passed else 'CHƯA ĐẠT'))


def _settlement_formulas(normal,bold,L,radial=False):
    entries=[(L('Lún cố kết tổng'),r'$S_c=\sum_i S_{c,i}$'),
             (L('Tổng lún tại thời điểm t'),r'$S_t(t)=S_i+S_c(t)$'),
             (L('Lún cố kết còn lại'),r'$S_{c,du}(t)=S_{c,\infty}-S_c(t)$'),
             (L('Hệ số thời gian cố kết đứng'),r'$T_v=\frac{C_vt}{H_{dr}^2}$')]
    if radial:
        entries.extend([(L('Cố kết hướng tâm'),r'$U_h=1-\exp\left(-\frac{8C_ht}{D_e^2F}\right)$'),
                        (L('Cố kết kết hợp đứng và hướng tâm'),r'$U=1-(1-U_v)(1-U_h)$')])
    return [Section(L('CÔNG THỨC TÍNH TOÁN')),
            _table([[L('Nội dung'),L('Công thức')]]+[(label,MathFormula(eq)) for label,eq in entries],
                   [W*.43,W*.57],normal,bold,font_size=8,padding=4),Spacer(1,8)]


def _create_cdm_only_report(project, destination, method, data, language='vi', show_logo=True):
    """Báo cáo riêng cho lần tính CDM/ALiCC, không tính lại lún tự nhiên."""
    L = lambda s: _english_ui(s) if language == 'en' else s
    if method not in ('standard', 'alicc') or not data:
        raise ValueError(L('Chưa có kết quả CDM/ALiCC để xuất báo cáo.'))
    normal = ParagraphStyle('cdm_normal', fontName='SFReport', fontSize=9.2, leading=12.5)
    bold = ParagraphStyle('cdm_bold', parent=normal, fontName='SFReportBold')
    title = ParagraphStyle('cdm_title', parent=bold, fontSize=11, leading=15,
                           alignment=TA_CENTER, spaceAfter=7)
    doc = SimpleDocTemplate(destination, pagesize=A4, leftMargin=LEFT, rightMargin=RIGHT,
                            topMargin=42, bottomMargin=39,
                            title=f'{project.name or "Dự án"} — phương án xử lý CDM')
    result, params = data['result'], data['params']
    scope = data['scope']
    name = 'ALiCC' if method == 'alicc' else 'TCVN 9906 + BS 8006'
    story = [_p(project.name or L('DỰ ÁN ...'), title),
             _p(L('PHƯƠNG ÁN XỬ LÝ: CỌC XI MĂNG ĐẤT CDM — ') + name, title),
             Section(L('THÔNG SỐ PHƯƠNG ÁN'))]

    def details(items):
        story.append(_kv(items, normal, bold, W))
        story.append(Spacer(1, 6))

    def formula(rows):
        rows = [(label, _formula_cell(expression), result) for label, expression, result in rows]
        story.append(_table([[L('Nội dung'), L('Công thức tính'), L('Kết quả')]] + rows,
                            [W*.25, W*.51, W*.24], normal, bold,
                            font_size=8.2, padding=4))
        story.append(Spacer(1, 7))

    details([(L('Lý trình'), ' — '.join(v for v in (project.station_from, project.station_to) if v) or project.station or '—'),
             (L('Hạng mục'), project.work_item or '—'),
             (L('Bước thiết kế'), project.design_stage or '—')])
    if scope == 'Nền mở rộng':
        ext_h, ext_slope, ext_gamma = expansion_parameters(project)
        details([(L('Phạm vi xử lý'),
                  L('Nền mở rộng') + ' ' + project.expansion_side.lower()),
                 (L('Bề rộng mở rộng b'),
                  f'{project.expansion_width:.2f} m'),
                 (L('Chiều cao nền mở rộng'), f'{ext_h:.2f} m'),
                 (L('Độ dốc mái nền mở rộng'), f'1:{ext_slope:.2f}'),
                 (L('Dung trọng đất đắp mở rộng'), f'{ext_gamma:.2f} T/m³'),
                 (L('Nền chính đã xử lý'),
                  f'{project.main_treatment}')])
    else:
        details([(L('Phạm vi xử lý'), L('Nền đường')),
                 (L('Bề rộng mặt nền B'), f'{2*project.crest_half_width:.2f} m'),
                 (L('Chiều cao nền đắp'), f'{project.height:.2f} m'),
                 (L('Độ dốc mái nền đắp'), f'1:{project.slope_m:.2f}'),
                 (L('Dung trọng đất đắp'), f'{project.gamma_fill:.2f} T/m³')])
    details([(L('Loại cọc'), params['pile_type']),
             (L('Đường kính cọc D'), f'{params["D"]:.2f} m'),
             (L('Khoảng cách cọc s'), f'{params["s"]:.2f} m'),
             (L('Chiều dài cọc Lc'), f'{params["Lc"]:.2f} m'),
             (L('Sơ đồ bố trí cọc'), params['pattern'])])
    story.append(CrossSection(project, W, 190, cdm_data=data, language=language))
    story.extend([Spacer(1, 8), Section(L('ĐỊA CHẤT TRONG PHẠM VI TÍNH'))])
    soil_rows = [[L('STT'), L('Lớp đất'), L('Loại'), L('Dày') + '\n(m)',
                  L('Đáy') + '\n(m)', 'γ\n(T/m³)', 'N-SPT', 'e₀', 'Cc', 'Cs',
                  'Pc\n(T/m²)', 'cᵤ\n(T/m²)', 'Cv\n(10⁻³ cm²/s)']]
    depth = 0.0
    for i, soil in enumerate(project.soils, 1):
        depth += soil.thickness
        soil_rows.append([str(i), soil.name or f'{L("Lớp")} {i}',
                          L('Dính') if soil.category == 'Đất dính' else L('Rời'),
                          f'{soil.thickness:.2f}', f'{depth:.2f}', f'{soil.gamma:.2f}',
                          str(soil.spt_n) if soil.spt_n > 0 else '—',
                          f'{soil.e0:.3f}' if soil.e0 > 0 else '—',
                          f'{soil.cc:.3f}' if soil.cc > 0 else '—',
                          f'{soil.cs:.3f}' if soil.cs > 0 else '—',
                          f'{soil.pc:.2f}' if soil.pc > 0 else '—',
                          f'{soil.co:.2f}' if soil.co > 0 else '—',
                          f'{soil.cv[0]:.3f}' if soil.cv and soil.cv[0] > 0 else '—'])
    story.extend(_geology_tables(project,normal,bold,L))

    if method == 'standard':
        st = result['stress']
        loads, base = data['stress_params'], data['subgrade_params']
        area = params['s']**2 if params['pattern'] == 'Lưới vuông' else .866025*params['s']**2
        first = result['rows_lun'][0]
        story.append(Section(L('1. TÍNH TOÁN ĐỘ LÚN')))
        details([(L('Chiều cao nền đắp thiết kế Htk'), f'{result["H_tk"]:.2f} m'),
                 (L('Chiều dày kết cấu áo đường Hkcad'), f'{result["H_kcad"]:.2f} m'),
                 (L('Chiều cao bù lún Hbl'), f'{result["H_bl"]:.2f} m'),
                 (L('Chiều cao tính toán cọc H'), f'{result["H_cdm"]:.2f} m'),
                 (L('Dung trọng đất đắp γ'), f'{result["gamma_fill"]:.2f} T/m³'),
                 (L('Hoạt tải xe qH'), f'{loads["qH"]:.2f} T/m²'),
                 (L('Mô đun đàn hồi cọc Ec'), f'{params["Ec"]:.2f} T/m²'),
                 (L('Mô đun đất trung bình Es'), f'{first["e_soil"]:.2f} T/m²')])
        formula([(L('Diện tích ô cọc A'), 's² (vuông) hoặc 0,866025·s² (tam giác)', f'{area:.2f} m²'),
                 (L('Diện tích tiết diện cọc Ac'), 'π·D²/4', f'{math.pi*params["D"]**2/4:.2f} m²'),
                 (L('Tỷ lệ diện tích thay thế ap'), 'Ac/A', f'{result["ap"]*100:.2f} %'),
                 (L('Mô đun tương đương Etđ'), 'ap·Ec + (1−ap)·Es', f'{first["e_td"]:.2f} T/m²')])
        end_bearing = 'Cọc chống' in params['pile_type']
        s1 = result['S1_cm']
        s2, sc2 = result['S2_cm'], result['Sc2_cm']
        story.append(Section(L('1.1. LÚN S1 CỦA KHỐI GIA CỐ — TCVN 9403:2012')))
        formula([(L('Tải truyền lên khối gia cố q'), 'q=γ·H+qH', f'{result["q_cdm"]:.2f} T/m²'),
                 (L('Lún khối gia cố S1'), 'S1=q·Lc/(ap·Ec+(1−ap)·Es)·100', f'{s1:.2f} cm')])
        block = [[L('Khối gia cố'), 'Lc (m)', 'ap', 'q (T/m²)', 'Ec (T/m²)', 'Es (T/m²)', 'S1 (cm)'],
                 ['CDM', f'{params["Lc"]:.2f}', f'{result["ap"]:.2f}', f'{result["q_cdm"]:.2f}',
                  f'{params["Ec"]:.2f}', f'{first["e_soil"]:.2f}', f'{s1:.2f}']]
        story.append(_table(block,[W*.16]+[W*.14]*6,normal,bold,font_size=8.0,padding=3))
        story.append(Spacer(1,6))
        story.append(Section(L('1.2. LÚN S2 CỦA ĐẤT DƯỚI MŨI CỌC')))
        if end_bearing:
            details([(L('Loại cọc'),L('Cọc chống')),
                     (L('Lún dưới mũi cọc S2'), '0.00 cm'),
                     (L('Lún cố kết dưới mũi cọc Sc2'), '0.00 cm')])
        else:
            def cell_number(value, digits=2):
                if value == '' or value is None:
                    return '—'
                try:
                    return f'{float(value):.{digits}f}'
                except (ValueError,TypeError):
                    return str(value)
            # Chỉ phân tố dưới mũi cọc, không trộn hàng khối CDM S1.
            headings = [L('Phân tố đất'), 'h (m)', L('Đáy')+' (m)', 'e₀', 'Cc', 'Cs',
                        'Pc (T/m²)', 'Δp (T/m²)', 'Sc2 (cm)']
            rows = [headings]
            for row in result['rows_lun'][1:]:
                rows.append([row['name'],cell_number(row['thick']),cell_number(row['bot_z']),
                             cell_number(row['e0'],3),cell_number(row['cc'],3),cell_number(row['cr'],3),
                             cell_number(row['pc']),cell_number(row['dp']),cell_number(row['sc'])])
            rows.append([L('TỔNG'),'','','','','','','',f'{sc2:.2f}'])
            story.append(_table(rows,[W*.24]+[W*.095]*8,normal,bold,font_size=7.8,padding=3,last=True))
            story.append(Spacer(1, 10))
            formula([(L('Lún cố kết dưới mũi cọc Sc2'), 'Sc2=ΣSc2,i',f'{sc2:.2f} cm'),
                     (L('Lún dưới mũi cọc S2'), 'S2=Sc2',f'{s2:.2f} cm')])
        story.append(Spacer(1, 10))
        formula([(L('Tổng lún tức thời Si'), 'Si=S1' if end_bearing else 'Si=S1+0.2·S2',f'{result["sum_si"]:.2f} cm'),
                 (L('Tổng lún cố kết Sc'), 'Sc=0' if end_bearing else 'Sc=Sc2',f'{result["sum_sc"]:.2f} cm'),
                 (L('Tổng độ lún S'), 'S=S1+S2; S2=0' if end_bearing else 'S=Si+Sc',f'{result["total_s"]:.2f} cm')])
        details([(L('Giới hạn lún dư cho phép'),f'{project.residual_limit_cm:.2f} cm'),
                 (L('Đánh giá lún'),_check_text('Sc',result['sum_sc'],'[Sc]',project.residual_limit_cm,'cm',L))])

        story.append(Section(L('2.1. KIỂM TOÁN ỨNG SUẤT ĐẦU CỌC — TTGH1')))
        details([(L('Cường độ kháng nén cọc ')+params['qu_type'],f'{params["qu_val"]:.2f} T/m²'),
                 (L('Hệ số quy đổi cường độ 28–90 ngày n'),f'{loads["n"]:.2f}'),
                 (L('Hệ số an toàn cọc Fs'),f'{loads["Fs"]:.2f}'),
                 (L('Tải trọng nền đắp qT'),f'{st["qT"]:.2f} T/m²'),
                 (L('Hoạt tải xe qH'),f'{loads["qH"]:.2f} T/m²')])
        formula([(L('Cường độ kiểm toán qu28'),'qu28 = qu90/n' if params['qu_type']=='qu90' else 'qu28 theo số liệu khai báo',f'{st["qu_check"]:.2f} T/m²'),
                 (L('Sức kháng cắt không thoát nước cọc Suc'),'qu28/2',f'{st["qu_check"]/2:.2f} T/m²'),
                 (L('Cường độ cọc cho phép'),'qu28/Fs',f'{st["qu_allow"]:.2f} T/m²'),
                 (L('Ứng suất đầu cọc TTGH1'),'(qT+qH)/ap',f'{st["qu_tt1"]:.2f} T/m²')])
        details([(L('Đánh giá đầu cọc TTGH1'),_check_text('qu,tt1',st['qu_tt1'],'[qu]',st['qu_allow'],'T/m²',L))])
        story.append(Section(L('2.2. KIỂM TOÁN ỨNG SUẤT ĐẦU CỌC — TTGH2')))
        details([(L('Hệ số vượt tải nền đắp ffs'),f'{loads["f_fs"]:.2f}'),
                 (L('Hệ số vượt tải hoạt tải xe fq'),f'{loads["f_q"]:.2f}')])
        formula([(L('Hệ số tạo vòm Cc'),st['cc_formula'],f'{st["Cc"]:.2f}'),
                 (L('Ứng suất đứng có hệ số σ′v'),'ffs·qT + fq·qH',f'{st["sigma_v_prime"]:.2f} T/m²'),
                 (L('Cường độ cọc cho phép'),'qu28/Fs',f'{st["qu_allow"]:.2f} T/m²'),
                 (L('Ứng suất đầu cọc TTGH2'),'σp=σ′v·(Cc·D/H)²',f'{st["sigma_p"]:.2f} T/m²')])
        details([(L('Đánh giá đầu cọc TTGH2'),_check_text('σp',st['sigma_p'],'[qu]',st['qu_allow'],'T/m²',L))])

        story.append(Section(L('3. ỨNG SUẤT ĐẤT NỀN')))
        details([(L('Hệ số điều kiện làm việc m'), f'{base["m"]:.2f}'),
                 (L('Dung trọng hữu hiệu đất nền γ′'), f'{base["gamma_sub"]:.2f} T/m³'),
                 (L('Bề rộng xử lý Bxl'), f'{result["b_val"]:.2f} m'),
                 (L('Tải trọng bên móng q'), f'{base["q_mong"]:.2f} T/m²'),
                 (L('Lực dính đất nền c'), f'{base["c_val"]:.2f} T/m²'),
                 (L('Góc ma sát trong đất nền φ'), f'{base["phi_val"]:.2f}°'),
                 (L('Hệ số sức chịu tải theo dung trọng A'), f'{result["A_fac"]:.2f}'),
                 (L('Hệ số sức chịu tải theo tải bên móng B'), f'{result["B_fac"]:.2f}'),
                 (L('Hệ số sức chịu tải theo lực dính D'), f'{result["D_fac"]:.2f}')])
        formula([(L('Ứng suất đất giữa cọc σs'), 'max(0; (γ·H + qH − σp·ap)/(1−ap))', f'{st["sigma_s"]:.2f} T/m²'),
                 (L('Sức chịu tải đất nền Rtc'), 'm·(A·γ′·Bxl + B·q móng + D·c)', f'{st["Rtc"]:.2f} T/m²')])
        details([(L('Đánh giá đất nền'), _check_text('σs',st['sigma_s'],'Rtc',st['Rtc'],'T/m²',L))])
        checks = [(L('Độ lún'), result['sum_sc'] <= project.residual_limit_cm),
                  (L('Đầu cọc TTGH1'), st['qu_tt1'] <= st['qu_allow']),
                  (L('Đầu cọc TTGH2'), st['sigma_p'] <= st['qu_allow']),
                  (L('Đất nền'), st['sigma_s'] <= st['Rtc'])]
    else:
        stress = data['stress_params']
        story.append(Section(L('1. TÍNH TOÁN ĐỘ LÚN — ALiCC')))
        details([(L('Chiều cao tính toán H'), f'{params["H"]:.2f} m'),
                 (L('Dung trọng đất đắp γ'), f'{params["gamma"]:.2f} T/m³'),
                 (L('Hoạt tải xe qH'), f'{stress["qH"]:.2f} T/m²'),
                 (L('Mô đun đàn hồi cọc Ec'), f'{params["Ec"]:.2f} T/m²'),
                 (L('Mô đun đàn hồi đất Es'), f'{params["Es"]:.2f} T/m²')])
        formula([(L('Diện tích ô cọc A'), 'A theo sơ đồ bố trí cọc', f'{result["area"]:.2f} m²'),
                 (L('Diện tích tiết diện cọc Ac'), 'Ac = n·πD²/4', f'{result["Ac"]:.2f} m²'),
                 (L('Tỷ lệ diện tích thay thế ap'), 'Ac/A', f'{result["ap"]*100:.2f} %'),
                 (L('Mô đun tương đương Eeq'), 'ap·Ec + (1−ap)·Es', f'{result["Eeq"]:.2f} T/m²'),
                 (L('Lún khối gia cố S1'), '(γ·H+qH)·Lc/Eeq·100', f'{result["S1_cm"]:.2f} cm'),
                 (L('Lún dưới mũi cọc S2'), 'Σ(ε·h·100) với cọc treo; cọc chống = 0', f'{result["S2_cm"]:.2f} cm'),
                 (L('Tổng độ lún S'), 'S1 + S2', f'{result["S_total_cm"]:.2f} cm')])
        if 'Es_used' in result:
            details([(L('Căn cứ tính Es'), f"Es = 250 × Co = 250 × {result['Co_used']:.4g} = {result['Es_used']:.2f} T/m²; lớp {result['es_layer_no']}: {result['es_layer_name']}")])
        if 'differential_cm' in result:
            details([(L('Lún đất Ssoil'), f"{result['Ssoil_cm']:.2f} cm"),(L('Lún cọc Scol'),f"{result['Scol_cm']:.2f} cm"),
                     (L('Kiểm tra chênh lún'), _check_text('ΔS = |Ssoil − Scol|',result['differential_cm'],'[ΔS]',result['differential_limit_cm'],'cm',L) if result.get('differential_checked') else L('Chưa nhập [ΔS]: chưa kiểm tra chênh lún'))])
        if result.get('settlement_rows'):
            rows = [[L('Lớp đất'), L('Đỉnh')+' (m)', L('Đáy')+' (m)', 'Δp (T/m²)', 'S2 (cm)']]
            rows += [[r['layer'], f'{r["z0"]:.2f}', f'{r["z1"]:.2f}', f'{r["dp"]:.2f}', f'{r["cm"]:.2f}']
                     for r in result['settlement_rows']]
            story.append(_table(rows,[W*.32]+[W*.17]*4,normal,bold,font_size=8.2,padding=3))
        details([(L('Giới hạn tổng lún cho phép'), f'{data["limit"]:.2f} cm'),
                 (L('Đánh giá lún'), _check_text('S',result['S_total_cm'],'[S]',data['limit'],'cm',L))])

        story.append(Section(L('2. ỨNG SUẤT ĐẦU CỌC — ALiCC')))
        details([(L('Cường độ kháng nén cọc qu'), f'{params["qu"]:.2f} T/m²'),
                 (L('Hệ số an toàn cọc Fs'), f'{params["Fs"]:.2f}'),
                 (L('Góc tạo vòm θ'), f'{params["theta"]:.2f}°')])
        if params['pattern'] == 'Lưới chữ nhật':
            details([(L('Bước cọc ngắn κ'), f'{params["s_short"]:.2f} m')])
        rise = result['arch_rise']
        if params['pattern'] == 'Lưới vuông':
            vs_equation = ('Vs=[(s−D)s²/2−π(s³−D³)/24+(4−π)(√2−1)s³/24]tanθ'
                           if rise <= params['H'] else
                           'Vs=s²H−π[(H/tanθ+D/2)²(Dtanθ/2+H)−(D/2)³tanθ]/3')
        elif params['pattern'] == 'Lưới tam giác':
            vs_equation = 'Vs=2[V1−(V2+2V3−V4−2V5)]'
        elif params['pattern'] == 'Lưới chữ nhật':
            vs_equation = 'Vs=Vs(κ)+κ(s−κ)/4·[(√2+1)κ/2+√((s/2)²+(κ/2)²)+s/2−2D]tanθ'
        else:
            vs_equation = 'Vs=Vs(vuông)+(s−D)²·D·tanθ/4'
        formula([(L('Chiều cao vòm'), '(s−D)·tanθ/2 (lưới vuông)', f'{rise:.2f} m'),
                 (L('Thể tích đất giữa cọc Vs'), vs_equation, f'{result["Vs"]:.2f} m³'),
                 (L('Thể tích truyền về cọc Vc'), 'A·H − Vs', f'{result["Vc"]:.2f} m³'),
                 (L('Cường độ cọc cho phép'), 'qu/Fs', f'{params["qu"]/params["Fs"]:.2f} T/m²'),
                 (L('Ứng suất đầu cọc Pcol'), 'Vc·γ/Ac + qH', f'{result["Pcol"]:.2f} T/m²')])
        details([(L('Nhánh hiệu ứng vòm'), result['branch'])])
        term_names = {'V1':'Thể tích khối đất V1','V2':'Thể tích thành phần vòm V2',
                      'V3':'Thể tích thành phần vòm V3','V4':'Thể tích thành phần vòm V4',
                      'V5':'Thể tích thành phần vòm V5'}
        details([(L(term_names.get(k,'Thể tích thành phần vòm '+k)),f'{v:.2f} m³')
                 for k,v in result.get('terms',{}).items()])
        details([(L('Đánh giá sức chịu tải đầu cọc'), _check_text('Pcol',result['Pcol'],'qu/Fs',params['qu']/params['Fs'],'T/m²',L))])
        story.append(Section(L('3. ỨNG SUẤT ĐẤT NỀN — ALiCC')))
        formula([(L('Ứng suất đất giữa cọc Psoil'), 'Vs·γ/(A−Ac) + qH', f'{result["Psoil"]:.2f} T/m²')])
        checks = [(L('Độ lún'), result['S_total_cm'] <= data['limit']),
                  (L('Sức chịu tải đầu cọc'), result['pile_ok']),
                  (L('Chênh lún cọc và đất'), result.get('differential_ok') is True)]

    reinforcement = result.get('geo') if method == 'standard' else result.get('reinforcement')
    if reinforcement:
        inp = data['geo_params']
        story.append(Section(L('4. KIỂM TOÁN VẢI ĐỊA KỸ THUẬT / LƯỚI')))
        labels = [('eps','Độ giãn dài cho phép ε',' %'), ('phi_dap','Góc ma sát trong đất đắp φ','°'),
                  ('T_char_kn','Cường độ kéo lưới địa Tchar (nhập trực tiếp)',' kN/m'), ('Tmax','Cường độ kéo tối đa Tmax',' kN/m'), ('eps_max','Độ giãn dài tối đa εmax',' %'),
                  ('T_char','Cường độ kéo tại độ giãn dài kiểm toán Tchar',' T/m'), ('n_layer','Số lớp vải hoặc lưới n',''),
                  ('fm11','Hệ số sản xuất fm11',''),('fm12','Hệ số ngoại suy fm12',''),
                  ('fm21','Hệ số hư hỏng khi thi công fm21',''),('fm22','Hệ số ảnh hưởng môi trường fm22',''),
                  ('fn','Hệ số kinh tế fn',''),('f_fs','Hệ số vượt tải nền đắp ffs',''),
                  ('f_q','Hệ số vượt tải hoạt tải xe fq','')]
        details([(L(label), f'{float(inp[key]):.2f}{unit}')
                 for key,label,unit in labels if key in inp
                 and (key not in ('Tmax','eps_max') or inp.get('kind') != 'Lưới địa kỹ thuật')
                 and (key != 'T_char_kn' or inp.get('kind') == 'Lưới địa kỹ thuật')])
        g = reinforcement
        rows = [(L('Hệ số tạo vòm Cc'), 'Theo mô hình tạo vòm BS 8006', f'{g["Cc"]:.2f}') ] if 'Cc' in g else []
        if inp.get('kind') == 'Lưới địa kỹ thuật':
            rows += [(L('Cường độ kéo lưới địa Tchar'), 'Nhập trực tiếp; quy đổi Tchar (kN/m) / 9,80665', f'{g["T_char"]:.2f} T/m')]
        elif 'Tmax' in inp and 'eps_max' in inp:
            expression = (r'$T_{char}=\frac{0.9\varepsilon T_{max}}{\varepsilon_{max}\times9.80665}$'
                          + '\n' + rf'$T_{{char}}=\frac{{0.9\times{inp["eps"]:.2f}\times{inp["Tmax"]:.2f}}}{{{inp["eps_max"]:.2f}\times9.80665}}$')
            rows += [(L('Cường độ kiểm toán của vải') + f' {inp["Tmax"]:g}×{inp["Tmax"]:g} ' + L('tại độ giãn dài') + f' {inp["eps"]:g}%, Tchar', expression, f'{g["T_char"]:.2f} T/m')]
        rows += [(L('Tải truyền giữa cọc WT'), 'Theo nhánh H > 1,4(s−D) hoặc nhánh nền thấp; WT ≥ 0,15·s·σ′v', f'{g["WT"]:.2f} T/m')]
        if 'WT_min' in g:
            rows.append((L('Tải tối thiểu WT,min'), '0,15·s·σ′v', f'{g["WT_min"]:.2f} T/m'))
        rows += [(L('Lực kéo do võng Trp'), 'WT·(s−D)/(2D)·√(1+1/(6ε))', f'{g["Trp"]:.2f} T/m'),
                 (L('Hệ số áp lực ngang Ka'), 'tan²(45°−φ/2)', f'{g["Ka"]:.2f}'),
                 (L('Lực kéo do áp lực ngang Tds'), '0,5·Ka·(ffs·γ·H+2fq·qH)·H', f'{g["Tds"]:.2f} T/m'),
                 (L('Tổng lực kéo Tr'), 'Trp+Tds', f'{g["Tr"]:.2f} T/m')]
        if 'Td' in g:
            rows.append((L('Cường độ kéo thiết kế Td'), 'Tchar·n_lớp/fm', f'{g["Td"]:.2f} T/m'))
        rows.append((L('Cường độ kéo cho phép Td/fn'), 'Tchar·n_lớp/(fm·fn)', f'{g["Td_fn"]:.2f} T/m'))
        formula(rows)
        ok = g['Tr'] <= g['Td_fn']
        details([(L('Đánh giá vải hoặc lưới'), _check_text('Tr',g['Tr'],'Td/fn',g['Td_fn'],'T/m',L))])
        checks.append((L('Vải địa kỹ thuật hoặc lưới'),ok))
    if method == 'alicc' and result.get('surface'):
        sf, inp = result['surface'], data['surface_params']
        story.append(Section(L('4. KIỂM TOÁN ĐỆM GIA CỐ XI MĂNG')))
        labels = [('thickness','Chiều dày đệm gia cố Hse',' m'),
                  ('q_allow','Ứng suất đất nền cho phép dưới đệm',' T/m²'),
                  ('shear_strength','Sức kháng cắt đệm',' T/m²'),
                  ('su_soil','Sức kháng cắt đất dưới đệm',' T/m²'),
                  ('Esa','Mô đun nền đàn hồi Esa',' T/m²'),
                  ('spt_n','Chỉ số xuyên tiêu chuẩn N-SPT',''),('qu_surface','Cường độ kháng nén đệm quse',' T/m²'),
                  ('alpha','Hệ số đàn hồi đệm α',''),('bend_ratio','Tỷ số cường độ kéo uốn',''),
                  ('Fs_surface','Hệ số an toàn đệm','')]
        details([(L(label),f'{float(inp[key]):.2f}{unit}') for key,label,unit in labels if key in inp])
        details([(L('Ứng suất cắt đệm τ'),f'{sf["shear"]:.2f} T/m²'),
                 (L('Ứng suất cắt cho phép'),f'{sf["shear_allow"]:.2f} T/m²'),
                 (L('Ứng suất uốn khi xét nền đàn hồi'),f'{sf["sigma_k"]:.2f} T/m²'),
                 (L('Ứng suất uốn khi không xét nền đàn hồi'),f'{sf["sigma_no_k"]:.2f} T/m²'),
                 (L('Ứng suất uốn cho phép'),f'{sf["bending_allow"]:.2f} T/m²'),
                 (L('Đánh giá cắt đệm'),_check_text('τ',sf['shear'],'[τ]',sf['shear_allow'],'T/m²',L)),
                 (L('Đánh giá uốn đệm'),_check_text('σk',sf['sigma_k'],'[σ]',sf['bending_allow'],'T/m²',L))])
        checks += [(L('Cắt đệm gia cố'),sf['shear_ok']),(L('Uốn đệm gia cố'),sf['ok_k'])]
    def footer(canvas, document):
        _draw_pdf_brand(canvas, show_logo)
        canvas.saveState()
        canvas.setStrokeColor(INK)
        canvas.line(LEFT, 29, A4[0]-RIGHT, 29)
        canvas.setFont('SFReport', 7)
        canvas.drawString(LEFT, 18, str(project.name or 'DỰ ÁN ...'))
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def create_report(project, destination, evaluation_days=None, scope='full', language='vi',
                  special_method=None, special_data=None, show_logo=True):
    """Xuất báo cáo A4 dọc có ngắt trang và hàng tiêu đề lặp lại."""
    if scope not in ('full', 'natural', 'treated', 'cdm'):
        raise ValueError('Phạm vi xuất PDF không hợp lệ.')
    L = lambda s: _english_ui(s) if language == 'en' else s
    _fonts()
    project = deepcopy(project)
    project.update_geometry()
    if scope == 'cdm':
        _create_cdm_only_report(project, destination, special_method, special_data,
                                language=language, show_logo=show_logo)
        return
    mode = project.treatment
    natural_mode = mode == 'Chờ lún'
    _, _, elements = settlement(project, return_details=True)
    sc_natural = sum(e['Sc_list'][0] for e in elements)
    total_natural = sum(e['St_list'][0] for e in elements)
    comp = {'h_bl_m': project.h_bl, 'h_tt_m': project.height,
            'Sc_cm': sc_natural, 'Si_cm': total_natural-sc_natural,
            'lún_cm': total_natural}
    limit = project.residual_limit_cm
    selected_day = float(project.assessment_days if evaluation_days is None
                         else evaluation_days)
    if selected_day < 0 or not math.isfinite(selected_day):
        raise ValueError('Thời gian đánh giá phải là số ngày không âm.')

    def append_expansion_forecast(target):
        if project.expansion_width <= 0 or scope == 'cdm':
            return
        results = expansion_settlement_forecast(project, selected_day)
        rows = [[L('Vị trí'), L('Dư cũ nay') + ' (cm)',
                 L('Cũ lún tiếp') + ' (cm)', L('Do mở rộng') + ' (cm)',
                 L('Tổng tiếp') + ' (cm)', L('Dư sau') + ' (cm)']]
        for r in results:
            rows.append([L(r['vị_trí']),
                         f'{r["lún_dư_cũ_hiện_tại_cm"]:.2f}',
                         f'{r["lún_cũ_phát_sinh_cm"]:.2f}',
                         f'{r["lún_do_mở_rộng_cm"]:.2f}',
                         f'{r["lún_phát_sinh_tổng_cm"]:.2f}',
                         f'{r["lún_dư_sau_dự_báo_cm"]:.2f}'])
        target.append(Paragraph(
            L('Dự báo sau') + f' {selected_day:.2f} '
            + L('ngày kể từ hiện tại: tải nền chính cũ và tải mở rộng'), bold))
        target.append(_table(rows, [W*.29]+[W*.142]*5, normal, bold,
                             font_size=5.8, padding=2))

    normal = ParagraphStyle('n', fontName='SFReport', fontSize=9.2, leading=12.5,
                            textColor=INK)
    bold = ParagraphStyle('b', parent=normal, fontName='SFReportBold')
    table_caption = ParagraphStyle('table_caption', parent=bold,
                                   alignment=TA_CENTER)
    title = ParagraphStyle('title', parent=bold, fontSize=13, leading=17,
                           textColor=INK, alignment=TA_CENTER, spaceAfter=8)
    cover_title = ParagraphStyle('cover_title', parent=title, fontSize=10.3,
                                 leading=13, spaceAfter=4)
    note = ParagraphStyle('note', parent=normal, fontSize=8.3, leading=13,
                          spaceBefore=3, spaceAfter=5)
    doc = SimpleDocTemplate(destination, pagesize=A4, leftMargin=LEFT,
                            rightMargin=RIGHT, topMargin=38, bottomMargin=38,
                            title=L('Bảng tính dự báo lún')
                            if language == 'en' else 'Bảng tính dự báo lún')
    story = []

    def build_story():
        if language == 'en':
            output = [_translate_flowable(item) for item in story]
        else:
            output = story
        doc.build(output, onFirstPage=decorate, onLaterPages=decorate)

    def decorate(c, d):
        _draw_pdf_brand(c, show_logo)
        c.saveState()
        c.setStrokeColor(INK); c.setLineWidth(.6)
        c.line(LEFT,29,A4[0]-RIGHT,29)
        c.setFont('SFReport',7)
        c.drawString(LEFT,18,str(project.name or L('DỰ ÁN ...')))
        c.drawRightString(A4[0]-RIGHT,18,
                          (L('Trang') if language == 'en' else 'Trang')
                          + f' {d.page}')
        c.restoreState()

    story.append(_p(project.name or L('DỰ ÁN ...'), cover_title))
    if scope == 'cdm':
        heading = L('MỤC 7. TRỘN SÂU CDM — THÔNG SỐ BAN ĐẦU')
    else:
        heading = 'PRE-TREATMENT VERIFICATION' if language == 'en' else 'KIỂM TOÁN TRƯỚC XỬ LÝ'
    story.append(_p(heading, cover_title))
    story.append(Section(L('I. SỐ LIỆU TÍNH TOÁN')))
    story.append(Paragraph(L('1. Số liệu chung:'), bold))
    general = [
        (L('Hạng mục'), project.work_item or '—'),
        (L('Bước thiết kế'), project.design_stage or '—'),
        (L('Lý trình'),
         (' - '.join(x for x in (project.station_from, project.station_to) if x) or '—')),
        (L('MCN tính toán'), project.station or '—'),
        (L('Bề rộng mặt nền B'), f'{2*project.crest_half_width:.2f} m'),
        (L('Độ dốc mái taluy'), f'1 : {project.slope_m:.2f}'),
        (L('Chiều cao đắp Htk'), f'{project.h_design:.2f} m'),
        (L('Chiều cao bù lún Hbl'), f'{comp["h_bl_m"]:.2f} m'),
        (L('Chiều cao tính toán Htt'), f'{comp["h_tt_m"]:.2f} m'),
        (L('Dung trọng đất đắp γ'), f'{project.gamma_fill:.2f} T/m³'),
        (L('Chiều dày kết cấu áo đường'), f'{project.h_kcad:.2f} m'),
        (L('Chiều sâu mực nước ngầm'),
         f'{(project.water_depth if project.water_depth else 0.0):.2f} m'),
        (L('Bệ phản áp'),
         f'{project.counterweight_height:.2f} × {project.counterweight_width:.2f} m'),
        (L('Chiều sâu tính lún'),
         f'{elements[-1]["depth_m"]:.2f} m' if elements else '—'),
    ]
    if project.expansion_width > 0:
        general.extend([
            (L('Nền mở rộng'),
             f'{L(project.expansion_side)}: {project.expansion_width:.2f} m/' + L('bên')),
            (L('Phương án đã xử lý của nền chính'), L(project.main_treatment)),
            (L('Tuổi nền chính'), f'{project.main_age_days:.2f} ' + L('ngày')),
            (L('Lún dư quan trắc tại vai'),
             f'{project.main_observed_residual_cm:.2f} cm'
             if project.main_observed_residual_cm is not None
             else L('Không khai báo')),
            (L('Htk nền mở rộng'),
             f'{(project.expansion_h_design or project.h_design):.2f} m'),
            (L('Hkcad nền mở rộng'),
             f'{(project.h_kcad if project.expansion_h_kcad is None else project.expansion_h_kcad):.2f} m'),
            (L('Mái dốc nền mở rộng'),
             f'1 : {(project.slope_m if project.expansion_slope_m is None else project.expansion_slope_m):.2f}'),
            (L('Dung trọng nền mở rộng'),
             f'{(project.gamma_fill if project.expansion_gamma_fill is None else project.expansion_gamma_fill):.2f} T/m³'),
        ])
        if main_zone_boundary(project) is not None:
            general.append((L('Ranh giới vùng xử lý'),
                            f'±{main_zone_boundary(project):.2f} m'))
        if project.main_treatment in ('CDM', 'Cơ học'):
            details = ((('main_cdm_depth', L('CDM nền chính')),)
                       if project.main_treatment == 'CDM'
                       else (('main_replacement_depth', L('Đào thay đất nền chính')),
                             ('main_bamboo_depth', L('Cọc tre nền chính')),
                             ('main_cajuput_depth', L('Cừ tràm nền chính'))))
            general.extend((label, f'{getattr(project, key):.2f} m')
                           for key, label in details if getattr(project, key) > 0)
    story.extend([_kv(general,normal,bold,W),Spacer(1,8),
                  Section(L('MẶT CẮT NGANG TÍNH TOÁN')),
                  CrossSection(project,W,190,language=language),Spacer(1,8),
                  Section(L('ĐỊA CHẤT TRONG PHẠM VI TÍNH'))])
    soil_rows = [[L('Lớp'), L('Tên lớp'), L('Dày') + '\n(m)',
                  L('Đáy') + '\n(m)', 'γ\n(T/m³)', L('Loại đất'),
                  'e₀', 'Cc', 'Cs', 'Pc\n(T/m²)', 'Cv\n(10^-3 cm²/s)']]
    depth = 0
    for i, s in enumerate(project.soils, 1):
        depth += s.thickness
        e_zero = _e_at_zero(s)
        soil_rows.append([i, s.name, f'{s.thickness:.2f}', f'{depth:.2f}',
                          f'{s.gamma:.2f}', L(s.category),
                          f'{e_zero:.2f}' if e_zero is not None else '—',
                          f'{s.cc:.3f}', f'{s.cs:.3f}', f'{s.pc:.2f}',
                          f'{s.cv[0]:.3f}' if s.cv else '—'])
    soil_widths = [24, 74, 35, 35, 40, 68, 33, 30, 30, 42, W-411]
    story.extend(_geology_tables(project,normal,bold,L))
    if (project.expansion_width > 0
            and project.main_treatment in ('PVD', 'SD', 'Chờ lún')
            and project.main_soils):
        zone_rows = [soil_rows[0]]
        zone_depth = 0.0
        for i, s in enumerate(project.main_soils, 1):
            zone_depth += s.thickness
            e_zero = _e_at_zero(s)
            zone_rows.append([i, s.name, f'{s.thickness:.2f}',
                              f'{zone_depth:.2f}', f'{s.gamma:.2f}',
                              L(s.category),
                              f'{e_zero:.2f}' if e_zero is not None else '—',
                              f'{s.cc:.3f}', f'{s.cs:.3f}', f'{s.pc:.2f}',
                              f'{s.cv[0]:.3f}' if s.cv else '—'])
        story.append(Paragraph(
            L('Địa chất vùng đã xử lý của nền chính') + f' ({project.main_treatment}):',
            bold))
        story.append(_table(zone_rows, soil_widths, normal, bold,
                            font_size=6.2, padding=2.2))
    story.append(Section(L('II. KẾT QUẢ KIỂM TOÁN LÚN')))
    detail = [[L('Lớp'), 'h\n(m)', 'Z\n(m)', 'γ′\n(T/m³)', 'e₀', 'Cc', 'Cs',
               'P₀\n(T/m²)', 'Δp Tim\n(T/m²)', 'Δp Vai\n(T/m²)',
               'Sc Tim\n(cm)', 'Sc Vai\n(cm)', 'Sc Chân\n(cm)']]
    for e in elements:
        e_zero = _e_at_zero(project.soils[e['lớp']-1])
        detail.append([e['lớp'], f'{e["h_m"]:.2f}', f'{e["z_m"]:.2f}',
                       f'{e["gamma_eff_t_m3"]:.2f}',
                       f'{e_zero:.2f}' if e_zero is not None else '—',
                       f'{e["cc"]:.3f}', f'{e["cs"]:.3f}',
                       f'{e["p0_t_m2"]:.2f}', f'{e["dp_list"][0]:.2f}',
                       f'{e["dp_list"][1]:.2f}', f'{e["Sc_list"][0]:.2f}',
                       f'{e["Sc_list"][1]:.2f}', f'{e["Sc_list"][2]:.2f}'])
    detail.append([L('TỔNG')] + ['']*9 +
                  [f'{sum(e["Sc_list"][0] for e in elements):.2f}',
                   f'{sum(e["Sc_list"][1] for e in elements):.2f}',
                   f'{sum(e["Sc_list"][2] for e in elements):.2f}'])
    story.append(Paragraph(L('1. Thông số phân tố, ứng suất và lún:'), bold))
    story.append(_table(detail, [22,31,31,38,30,28,28,37,37,37,46,46,W-411],
                        normal, bold, last=True, font_size=5.9, padding=1.6))
    if project.expansion_width > 0:
        position_rows = [[L('Vị trí'), 'x (m)',
                          L('Δp tại Z đầu') + ' (T/m²)',
                          'Sc (cm)', 'S (cm)']]
        for i, (name, x) in enumerate(axes(project)):
            position_rows.append([L(name), f'{x:+.2f}',
                                  f'{elements[0]["dp_list"][i]:.2f}' if elements else '—',
                                  f'{sum(e["Sc_list"][i] for e in elements):.2f}',
                                  f'{sum(e["St_list"][i] for e in elements):.2f}'])
        story.append(Paragraph(
            L('Ứng suất tăng thêm và lún theo vị trí nền chính / nền mở rộng:'),
            bold))
        story.append(_table(position_rows, [W*.38,W*.12,W*.24,W*.13,W*.13],
                            normal, bold, font_size=6.2, padding=2))
    story.append(Paragraph(
        f'<b>Sc:</b> {comp["Sc_cm"]:.2f} cm  |  '
        f'<b>Si:</b> {comp["Si_cm"]:.2f} cm  |  '
        f'<b>S:</b> {comp["lún_cm"]:.2f} cm', note))

    natural_project = deepcopy(project)
    natural_project.treatment_group = 'drainage'
    natural_results = [consolidation(natural_project, selected_day, axis_index=i)[1]
                       for i in range(len(axes(natural_project)))]
    peak_sc = max((r['Sc_dư_cm'] for r in natural_results), default=0.0)
    natural_rows = [[L('Vị trí'), 'Sc (cm)', L('Sc dư') + ' (cm)',
                     L('Giới hạn') + ' (cm)', L('Đánh giá')]]
    for r in natural_results:
        natural_rows.append([L(r['vị_trí']), f'{r["Sc_cuối_cm"]:.2f}',
                             f'{r["Sc_dư_cm"]:.2f}', f'{limit:.2f}',
                             _check_text('Sc dư',r['Sc_dư_cm'],'[Sc dư]',limit,'cm',L)])
    condition = (L('Sc dư sau') + f' {selected_day:.2f} ' + L('ngày')
                 if selected_day > 0 else L('Sc dư còn lại'))
    conclusion = (L('Kết luận lún tự nhiên:') + f' {condition} '
                  + L('lớn nhất') + ': '
                  + _check_text('Sc dư',peak_sc,'[Sc dư]',limit,'cm',L) + '.')
    story.append(Paragraph(conclusion, bold))
    story.append(Spacer(1, 10))
    story.append(KeepTogether([
        Paragraph(L('Bảng tổng hợp kết quả kiểm tra độ lún'), table_caption),
        Spacer(1, 4),
        _table(natural_rows, [W*.16,W*.14,W*.14,W*.14,W*.42], normal, bold, padding=3),
    ]))
    append_expansion_forecast(story)

    story.append(Section(L('III. DỰ BÁO ĐỘ LÚN THEO THỜI GIAN')))
    time_data = _time_rows(project, language)
    time_table = [['t (' + L('năm') + ')', 'Tv', 'U (%)',
                   'St (m)', L('Sc dư') + ' (m)']]
    for yr, r in time_data:
        time_table.append([f'{yr:.2f}', f'{r["Tv_avg"]:.2f}',
                           f'{r["U_%"]:.2f}',
                           f'{r["Sc_t_cm"]/100:.2f}',
                           f'{r["Sc_dư_cm"]/100:.2f}'])
    time_flowable = _table(time_table, [43, 38, 39, 44, 46], normal, bold,
                           font_size=6.5, padding=2.0)
    if language == 'en':
        time_flowable = _translate_flowable(time_flowable)
    _, time_height = time_flowable.wrap(210, 1000)
    chart = SettlementChart([(yr, r['Sc_t_cm']/100) for yr, r in time_data],
                            W-222, time_height, language=language)
    pair = Table([[time_flowable, '', chart]],
                 colWidths=[210, 12, W-222])
    pair.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
                              ('LEFTPADDING',(0,0),(-1,-1),0),
                              ('RIGHTPADDING',(0,0),(-1,-1),0)]))
    story.extend([pair, Spacer(1, 7)])

    mechanical_direct = (project.treatment_group == 'mechanical' and
                         not (project.mechanical_wait or project.mechanical_surcharge))
    schedule = [] if mechanical_direct else stage_schedule(project)
    events = _report_events(project, schedule, language)
    schedule_end = max((end for _, _, end in events), default=0.0)
    end_fill = sum(st['kết_thúc']-st['bắt_đầu'] for st in schedule)
    wait_days = sum(st['chờ_đến']-st['kết_thúc'] for st in schedule)
    end_wait = end_fill + wait_days
    if mechanical_direct:
        time_parts = [L('Lớp đất chưa xử lý')]
    else:
        time_parts = [L('đắp') + f' {end_fill:.2f}',
                      L('chờ') + f' {wait_days:.2f}']
    if schedule_end > end_wait:
        time_parts.append(L('gia tải/hút chân không')
                          + f' {schedule_end-end_wait:.2f}')
    evaluation_breakdown = ' + '.join(time_parts)

    if scope == 'natural':
        build_story()
        return
    if scope == 'treated':
        story = []
    else:
        story.append(PageBreak())
    story.append(_p(project.name or L('DỰ ÁN ...'), cover_title))
    if project.treatment_group == 'mechanical':
        treatment_name = ', '.join(
            label for depth, label in (
                (project.replacement_depth, L('Đào thay đất')),
                (project.bamboo_depth, L('Cọc tre')),
                (project.cajuput_depth, L('Cọc cừ tràm')),
            ) if depth > 0)
    else:
        treatment_name = mode
    heading = L('PHƯƠNG ÁN XỬ LÝ:') + ' ' + treatment_name.upper()
    if (project.treatment_group == 'mechanical' and project.mechanical_surcharge):
        heading += ' + ' + L('GIA TẢI')
    story.append(_p(heading, cover_title))
    radial_report = (project.treatment_group != 'mechanical'
                     and mode.startswith(('PVD', 'SD')))
    if radial_report:
        treated_soil_rows = ([soil_rows[0]+['Ch/Cv']] +
                             [row+[f'{soil.ch_cv:.2f}']
                              for row, soil in zip(soil_rows[1:], project.soils)])
    else:
        treated_soil_rows = soil_rows
    treated_soil_widths = ([22,64,34,34,36,54,30,27,27,39,60,W-427]
                           if radial_report else soil_widths)
    if mechanical_direct:
        section_heading = L('I. SỐ LIỆU SAU XỬ LÝ CƠ HỌC')
    else:
        section_heading = L('I. PHƯƠNG ÁN VÀ LỊCH TRÌNH ĐẮP')
    story.append(Section(section_heading))
    story.append(Paragraph(L('1. Số liệu chung:'), bold))
    cfg = [
        (L('Hạng mục'), project.work_item or '—'),
        (L('Bước thiết kế'), project.design_stage or '—'),
        (L('Lý trình'),
         ' - '.join(x for x in (project.station_from, project.station_to) if x) or '—'),
        (L('MCN tính toán'), project.station or '—'),
        (L('Phương án'), L(mode)),
    ]
    if project.expansion_width > 0:
        cfg.extend([
            (L('Nền mở rộng'),
             f'{L(project.expansion_side)}: {project.expansion_width:.2f} m/' + L('bên')),
            (L('Phương án đã xử lý của nền chính'), L(project.main_treatment)),
            (L('Tuổi nền chính'), f'{project.main_age_days:.2f} ' + L('ngày')),
            (L('Lún dư quan trắc tại vai'),
             f'{project.main_observed_residual_cm:.2f} cm'
             if project.main_observed_residual_cm is not None
             else L('Không khai báo')),
            (L('Htk nền mở rộng'),
             f'{(project.expansion_h_design or project.h_design):.2f} m'),
            (L('Hkcad nền mở rộng'),
             f'{(project.h_kcad if project.expansion_h_kcad is None else project.expansion_h_kcad):.2f} m'),
            (L('Mái dốc nền mở rộng'),
             f'1 : {(project.slope_m if project.expansion_slope_m is None else project.expansion_slope_m):.2f}'),
            (L('Dung trọng nền mở rộng'),
             f'{(project.gamma_fill if project.expansion_gamma_fill is None else project.expansion_gamma_fill):.2f} T/m³'),
        ])
        if main_zone_boundary(project) is not None:
            cfg.append((L('Ranh giới vùng xử lý'),
                        f'±{main_zone_boundary(project):.2f} m'))
        if project.main_treatment in ('CDM', 'Cơ học'):
            details = ((('main_cdm_depth', L('CDM nền chính')),)
                       if project.main_treatment == 'CDM'
                       else (('main_replacement_depth', L('Đào thay đất nền chính')),
                             ('main_bamboo_depth', L('Cọc tre nền chính')),
                             ('main_cajuput_depth', L('Cừ tràm nền chính'))))
            cfg.extend((label, f'{getattr(project, key):.2f} m')
                       for key, label in details if getattr(project, key) > 0)
    if mode.startswith(('PVD', 'SD')):
        is_sd = mode.startswith('SD')
        cfg.extend([
            (L('Thoát nước ngang'), L(project.horizontal_drain_type)),
            (L('Sơ đồ bố trí'), L(project.drain_pattern)),
            (L('Khoảng cách d'), f'{project.drain_spacing:.2f} m'),
            (L('Chiều dài cọc') if is_sd else L('Chiều dài bấc'),
             f'{project.drain_length:.2f} m'),
            (L('Đường kính cọc') if is_sd else L('Đường kính tương đương'),
             f'{project.drain_diameter:.2f} cm'),
        ])
        if mode.startswith('PVD'):
            cfg.extend([(L('Tỷ số ds/dw'), f'{project.smear_ratio:.2f}'),
                        (L('Tỷ số Kh/Ks'), f'{project.permeability_ratio:.2f}')])
    if project.treatment_group == 'mechanical':
        cfg.extend((label, f'{depth:.2f} m') for label, depth in (
            (L('Chiều sâu đào thay đất'), project.replacement_depth),
            (L('Chiều sâu cọc tre'), project.bamboo_depth),
            (L('Chiều sâu cọc cừ tràm'), project.cajuput_depth)) if depth > 0)
        cfg.append((L('Chiều sâu không tính lún'),
                    f'{mechanical_depth(project):.2f} m'))
        if project.replacement_depth:
            cfg.append((L('Dung trọng vùng thay đất'),
                        f'{project.gamma_fill:.2f} T/m³'))
        if project.bamboo_depth or project.cajuput_depth:
            cfg.append((L('Dung trọng vùng đóng cọc'),
                        L('Theo từng lớp đất địa chất')))
        cfg.append((L('Chờ lún'),
                    L('Có') if project.mechanical_wait else L('Không')))
        if project.mechanical_surcharge:
            cfg.extend([(L('Gia tải trước'), L('Có')),
                        (L('Chiều cao gia tải'),
                         f'{project.surcharge_height:.2f} m'),
                        (L('Dung trọng gia tải'),
                         f'{project.surcharge_gamma:.2f} T/m³'),
                        (L('Thời gian gia tải'),
                         f'{project.surcharge_days:.2f} ' + L('ngày'))])
    story.extend([_kv(cfg,normal,bold,W),Spacer(1,8),
                  Section(L('MẶT CẮT NGANG TÍNH TOÁN')),
                  CrossSection(project,W,190,show_treatment=True,language=language),Spacer(1,8),
                  Section(L('ĐỊA CHẤT TRONG PHẠM VI TÍNH'))])
    story.extend(_geology_tables(project,normal,bold,L,
                                 include_spt=project.treatment_group == 'mechanical'))
    if (project.expansion_width > 0
            and project.main_treatment in ('PVD', 'SD', 'Chờ lún')
            and project.main_soils):
        zone_rows = [soil_rows[0]]
        zone_depth = 0.0
        for i, soil in enumerate(project.main_soils, 1):
            zone_depth += soil.thickness
            zone_rows.append([i, soil.name, f'{soil.thickness:.2f}',
                              f'{zone_depth:.2f}', f'{soil.gamma:.2f}',
                              L(soil.category),
                              f'{_e_at_zero(soil):.2f}' if _e_at_zero(soil) is not None else '—',
                              f'{soil.cc:.3f}', f'{soil.cs:.3f}',
                              f'{soil.pc:.2f}',
                              f'{soil.cv[0]:.3f}' if soil.cv else '—'])
        story.append(Spacer(1, 7))
        story.append(Paragraph(
            L('Địa chất vùng đã xử lý của nền chính') + f' ({project.main_treatment}):',
            bold))
        story.append(_table(zone_rows, soil_widths, normal, bold,
                            font_size=6.2, padding=2.2))
    story.append(Spacer(1, 8))
    if not mechanical_direct:
        story.append(Paragraph(L('2. Các giai đoạn thi công:'), bold))
        st_rows = [[L('Giai đoạn'), L('Bắt đầu') + '\n(' + L('ngày') + ')',
                    L('Kết thúc') + '\n(' + L('ngày') + ')',
                    L('Chiều cao đầu') + '\n(m)',
                    L('Chiều cao cuối') + '\n(m)',
                    L('Tốc độ') + '\n(cm/' + L('ngày') + ')',
                    L('Chờ đến') + '\n(' + L('ngày') + ')',
                    L('Thông số bổ sung')]]
        for s in schedule:
            st_rows.append([L(f'Đắp {s["giai_đoạn"]}'),
                            f'{s["bắt_đầu"]:.2f}', f'{s["kết_thúc"]:.2f}',
                            f'{s["h_đầu"]:.2f}', f'{s["h_cuối"]:.2f}',
                            f'{s["tốc_độ"]:.2f}', f'{s["chờ_đến"]:.2f}', ''])
        extra_start = schedule[-1]['chờ_đến'] if schedule else 0.0
        if 'gia tải' in mode.lower():
            st_rows.append([L('Gia tải'), f'{extra_start:.2f}',
                            f'{extra_start+project.surcharge_days:.2f}',
                            '', '', '', '',
                            f'hs {project.surcharge_height:.2f} m; '
                            f'γs {project.surcharge_gamma:.2f} T/m³'])
        if 'chân không' in mode.lower():
            st_rows.append([L('Hút chân không'), f'{extra_start:.2f}',
                            f'{extra_start+project.vacuum_days:.2f}',
                            '', '', '', '',
                            f'P_vac {project.vacuum_pressure:.2f} T/m²'])
        story.append(_table(st_rows, [64,48,48,50,50,55,48,W-363],
                            normal, bold, font_size=6.6, padding=3))
    if project.treatment_group == 'mechanical':
        _, _, shallow_elements = settlement(project, return_details=True, treated=True)
        shallow_rows = [[L('Lớp'), L('Tên lớp'), L('Xử lý'), 'Z (m)',
                         'h (m)', 'γ′ (T/m³)', 'P₀ (T/m²)', 'Δp (T/m²)',
                         'Sc Tim (cm)', 'Sc Vai (cm)', 'Sc Chân (cm)']]
        for e in mechanical_display_elements(shallow_elements):
            shallow_rows.append([e['lớp'], e['tên'], L(e['xử_lý']),
                                 f'{e["z_m"]:.2f}', f'{e["h_m"]:.2f}',
                                 f'{e["gamma_eff_t_m3"]:.2f}',
                                 f'{e["p0_t_m2"]:.2f}', f'{e["dp_t_m2"]:.2f}',
                                 *(f'{x:.2f}' for x in e['Sc_list'][:3])])
        step_no = 2 if mechanical_direct else 3
        story.extend([Spacer(1, 7),
                      Paragraph(f'{step_no}. ' + L('Phân tố lún sau xử lý:'), bold),
                      _table(shallow_rows,
                             [25,48,72,35,34,43,45,48,44,44,W-438],
                             normal, bold, font_size=5.9, padding=1.6)])
    if mechanical_direct:
        story.append(Section(L('II. KẾT QUẢ KIỂM TOÁN LÚN SAU XỬ LÝ')))
        result_rows = [[L('Vị trí'), L('Sc = Sc dư') + ' (cm)',
                        'St (cm)', 'U (%)', L('Đánh giá')]]
        for result in assess_locations(project, 0.0, mode):
            result_rows.append([L(result['vị_trí']),
                                f'{result["Sc_dư_cm"]:.2f}',
                                f'{result["Sc_t_cm"]:.2f}',
                                f'{result["U_%"]:.2f}',
                                _check_text('Sc dư',result['Sc_dư_cm'],'[Sc dư]',limit,'cm',L)])
        story.append(KeepTogether([
            Paragraph(L('Bảng tổng hợp kết quả kiểm tra độ lún'), table_caption),
            Paragraph(L('Sc dư là Sc của các lớp đất chưa xử lý bên dưới.'),
                      normal),
            Spacer(1, 4),
            _table(result_rows, [W*.16,W*.14,W*.14,W*.14,W*.42], normal, bold, padding=3),
        ]))
        append_expansion_forecast(story)
        build_story()
        return
    forecast_heading = Section(L('II. DỰ BÁO ĐỘ LÚN CỐ KẾT'))
    evaluation_day = schedule_end
    horizon = max(schedule_end, evaluation_day)
    history, info = treatment_history(project, horizon, max(1, horizon/22), mode, 0)
    if not any(abs(row['ngày']-evaluation_day) < 1e-6 for row in history):
        at_day, _ = treatment_history(project, evaluation_day,
                                      max(1, evaluation_day), mode, 0)
        history.append(at_day[-1])
        history.sort(key=lambda row: row['ngày'])
    staged_rows = [{'ngày': r['ngày'],
                    'hne_m': r['đắp_m']+r.get('gia_tải_m',0.0),
                    'he_m': r['đắp_m']+r.get('gia_tải_m',0.0)-r['St_cm']/100,
                    'sc_cm': r['Sc_t_cm'], 'st_cm': r['St_cm'],
                    'sc_du_cm': r['Sc_dư_cm']}
                   for r in history]
    if project.treatment_group == 'mechanical':
        story.append(Section(L('II. KẾT QUẢ KIỂM TOÁN LÚN SAU XỬ LÝ')))
    else:
        story.append(KeepTogether([forecast_heading,
                                   StagedSettlementChart(staged_rows, W, 162,
                                                         assessment_day=evaluation_day,
                                                         language=language,
                                                         stages=stage_schedule(project))]))
        story.append(Spacer(1, 7))
    results = assess_locations(project, evaluation_day, mode)
    mechanical_summary = project.treatment_group == 'mechanical'
    if mechanical_summary:
        result_rows = [[L('Vị trí'), L('Sc = Sc dư') + ' (cm)',
                        'St (cm)', 'U (%)', L('Đánh giá')]]
    else:
        result_rows = [[L('Vị trí'), 'Sc (cm)', 'St (cm)',
                        L('Sc dư') + ' (cm)', 'U (%)', L('Đánh giá')]]
    for r in results:
        if mechanical_summary:
            result_rows.append([L(r['vị_trí']), f'{r["Sc_dư_cm"]:.2f}',
                                f'{r["Sc_t_cm"]:.2f}', f'{r["U_%"]:.2f}',
                                _check_text('Sc dư',r['Sc_dư_cm'],'[Sc dư]',limit,'cm',L)])
        else:
            result_rows.append([L(r['vị_trí']), f'{r["Sc_cuối_cm"]:.2f}',
                                f'{r["Sc_t_cm"]:.2f}', f'{r["Sc_dư_cm"]:.2f}',
                                f'{r["U_%"]:.2f}',
                                _check_text('Sc dư',r['Sc_dư_cm'],'[Sc dư]',limit,'cm',L)])
    caption = Paragraph(L('Bảng tổng hợp kết quả kiểm tra độ lún'), table_caption)
    meta = Paragraph(L('Thời gian tính:') + f' {evaluation_breakdown} = '
                     + L('ngày') + f' {evaluation_day:.2f}.', normal)
    settlement_note = []
    if not mechanical_summary:
        note = ('Note: Sc is the initial consolidation settlement; '
                'St is the consolidation settlement achieved after treatment; '
                'Sc residual is the consolidation settlement remaining after treatment. '
                'All settlement values are in cm.' if language == 'en' else
                'Ghi chú: Sc là độ lún cố kết ban đầu; '
                'St là độ lún cố kết đạt được sau xử lý; '
                'Sc dư là độ lún cố kết còn lại sau xử lý. '
                'Các giá trị độ lún có đơn vị cm.')
        settlement_note = [Spacer(1, 4), Paragraph(note, normal)]
    story.append(KeepTogether([
        caption, meta, Spacer(1, 4),
        _table(result_rows, [W*.16,W*.14,W*.14,W*.14,W*.42] if mechanical_summary else [W*.14,W*.11,W*.11,W*.11,W*.11,W*.42],
               normal, bold, padding=3),
    ] + settlement_note))
    append_expansion_forecast(story)
    story.append(Section(L('III. KẾT QUẢ TỪNG MỐC THI CÔNG VÀ CHỜ LÚN')))
    summary = [[L('Mốc'), L('Từ - đến') + '\n(' + L('ngày') + ')',
                L('H đắp') + '\n(m)', L('Gia tải') + '\n(m)',
                'P_vac\n(T/m²)', L('U tổng') + '\n(%)',
                'St\n(cm)', L('Sc dư') + '\n(cm)']]
    event_rows = []
    computed_days = {round(row['ngày'], 7): row for row in history}
    for label, start, end in events:
        key = round(end, 7)
        row = computed_days.get(key)
        if row is None:
            at_day, _ = treatment_history(project, end, max(1, end/22), mode, 0)
            row = at_day[-1]
            computed_days[key] = row
        event_rows.append((label, start, end, row))
        surcharge = (project.surcharge_height
                     if 'gia tải' in mode.lower()
                     and schedule[-1]['chờ_đến'] <= end
                     <= schedule[-1]['chờ_đến']+project.surcharge_days else 0.0)
        vacuum = (project.vacuum_pressure
                  if 'chân không' in mode.lower()
                  and schedule[-1]['chờ_đến'] <= end
                  <= schedule[-1]['chờ_đến']+project.vacuum_days else 0.0)
        summary.append([label, f'{start:.2f} - {end:.2f}',
                        f'{row["đắp_m"]:.2f}', f'{surcharge:.2f}',
                        f'{vacuum:.2f}', f'{row["U_%"]:.2f}',
                        f'{row["Sc_t_cm"]:.2f}', f'{row["Sc_dư_cm"]:.2f}'])
    story.append(_table(summary, [110,67,47,50,52,37,53,W-416], normal, bold,
                        font_size=6.4, padding=2.4))
    story.append(Spacer(1, 8))
    for event_index, (label, start, end, row) in enumerate(event_rows):
        layer_rows = [[L('Lớp'), L('Tên lớp'), L('Dày') + '\n(m)',
                       'Cv ' + L('tính') + '\n(10^-3 cm²/s)',
                       'U ' + L('lớp') + '\n(%)',
                       'Sc\n(cm)', 'St\n(cm)',
                       L('Sc dư') + '\n(cm)', 'Cu\n(T/m²)']]
        for i, s in enumerate(project.soils):
            final = info[i]['Sc_cuối_cm']
            achieved = row['Sc_lớp_cm'][i]
            layer_rows.append([i+1, s.name, f'{s.thickness:.2f}',
                               f'{info[i]["Cv_cm2_ngày"]/86.4:.2f}',
                               f'{100*achieved/final:.2f}' if final > 0 else '—',
                               f'{final:.2f}', f'{achieved:.2f}',
                               f'{max(0,final-achieved):.2f}',
                               f'{row["C_t_m2"][i]:.2f}'])
        layer_rows.append([L('TỔNG'), '', '', '', '%.1f' % row['U_%'],
                           f'{row["Sc_cuối_cm"]:.2f}',
                           f'{row["Sc_t_cm"]:.2f}',
                           f'{row["Sc_dư_cm"]:.2f}', ''])
        heading = Paragraph(escape(label), bold)
        meta = Paragraph(f'{start:.2f}–{end:.2f} ' + L('ngày') + '; '
                         + f'H {row["đắp_m"]:.2f} m; '
                         + f'Sc {row["Sc_cuối_cm"]:.2f}; '
                         + f'St {row["Sc_t_cm"]:.2f}; '
                         + L('Sc dư') + f' {row["Sc_dư_cm"]:.2f}; '
                         + f'Si {row["Si_cm"]:.2f}; '
                         + f'S {row["St_cm"]:.2f} cm; '
                         + f'U {row["U_%"]:.2f}%.', normal)
        layer_table = _table(layer_rows,
                             [28,80,38,55,41,57,55,55,W-409],
                             normal, bold, last=True,
                             font_size=6.4, padding=2.0)
        story.append(heading)
        story.append(layer_table)
        if event_index < len(event_rows)-1:
            story.append(Spacer(1, 7))
    build_story()
