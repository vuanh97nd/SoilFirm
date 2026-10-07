"""Ký hiệu hiển thị; không thay tên biến hoặc dữ liệu tính toán."""
import re

_SYMBOLS = {
    'Hkcad': 'Hₖ꜀ₐđ', 'Htk': 'Hₜₖ', 'Htt': 'Hₜₜ', 'Hbl': 'Hᵦₗ',
    'Scp': 'S꜀ₚ', 'Sc': 'S꜀', 'Si': 'Sᵢ', 'St': 'Sₜ', 'Sr': 'Sᵣ',
    'Cc': 'C꜀', 'Cs': 'Cₛ', 'Cr': 'Cᵣ', 'Cv': 'Cᵥ', 'Ch': 'Cₕ',
    'Pc': 'P꜀', 'e0': 'e₀', 'eo': 'e₀', 'Nspt': 'Nₛₚₜ', 'NspT': 'Nₛₚₜ',
    'Ac': 'A꜀', 'ap': 'aₚ', 'Ec': 'E꜀', 'Es': 'Eₛ', 'Eeq': 'Eₑq',
    'Lc': 'L꜀', 'qu': 'qᵤ', 'qu28': 'qᵤ₂₈', 'qu90': 'qᵤ₉₀',
    'Fs': 'Fₛ', 'qT': 'qₜ', 'qH': 'qₕ', 'ffs': 'fₛ', 'fq': 'fq',
    'WT': 'Wₜ', 'Trp': 'Tᵣₚ', 'Tds': 'Tₛ', 'Tr': 'Tᵣ', 'Td': 'Tₜ',
    'Tchar': 'T꜀ₕₐᵣ', 'Ka': 'Kₐ', 'Rtc': 'Rₜ꜀',
    'σp': 'σₚ', 'σs': 'σₛ', 'σv': 'σᵥ', 'σ′v': 'σ′ᵥ',
    'S1': 'S₁', 'S2': 'S₂', 'V1': 'V₁', 'V2': 'V₂', 'V3': 'V₃', 'V4': 'V₄', 'V5': 'V₅',
}
_PATTERN = re.compile(r'(?<![\w])(' + '|'.join(map(re.escape, sorted(_SYMBOLS, key=len, reverse=True))) + r')(?![\w])')

def display_math(text):
    if not isinstance(text, str):
        return text
    text = re.sub(r'\bm\^?2\b', 'm²', text)
    text = re.sub(r'\bm\^?3\b', 'm³', text)
    return _PATTERN.sub(lambda m: _SYMBOLS[m.group()], text)

_TEX_SYMBOLS = {
 'Hkcad': r'H_{kcad}', 'Htk': r'H_{tk}', 'Htt': r'H_{tt}', 'Hbl': r'H_{bl}',
 'Scp': r'S_{cp}', 'Sc': r'S_c', 'Si': r'S_i', 'St': r'S_t', 'Sr': r'S_r',
 'Cc': r'C_c', 'Cs': r'C_s', 'Cr': r'C_r', 'Cv': r'C_v', 'Ch': r'C_h',
 'Pc': r'P_c', 'e0': r'e_0', 'eo': r'e_0', 'Nspt': r'N_{SPT}', 'NspT': r'N_{SPT}',
 'Ac': r'A_c', 'ap': r'a_p', 'Ec': r'E_c', 'Es': r'E_s', 'Eeq': r'E_{eq}',
 'Lc': r'L_c', 'qu': r'q_u', 'qu28': r'q_{u28}', 'qu90': r'q_{u90}',
 'Fs': r'F_s', 'qT': r'q_T', 'qH': r'q_H', 'ffs': r'f_{fs}', 'fq': r'f_q',
 'WT': r'W_T', 'Trp': r'T_{rp}', 'Tds': r'T_{ds}', 'Tr': r'T_r', 'Td': r'T_d',
 'Tchar': r'T_{char}', 'Ka': r'K_a', 'Rtc': r'R_{tc}',
 'σp': r'\sigma_p', 'σs': r'\sigma_s', 'σv': r'\sigma_v', 'σ′v': r"\sigma'_v",
 'S1': r'S_1', 'S2': r'S_2', 'V1': r'V_1', 'V2': r'V_2', 'V3': r'V_3', 'V4': r'V_4', 'V5': r'V_5',
}

def inline_tex(text):
    return _PATTERN.sub(lambda m: '$' + _TEX_SYMBOLS[m.group()] + '$', text)


def apply_math_label(widget, text):
    """Tk Label dùng ảnh MathText; giá trị và tên biến không đổi."""
    import tkinter as tk
    from tkinter import ttk
    if not isinstance(widget, (tk.Label, ttk.Label)) or not isinstance(text, str):
        return
    if not _PATTERN.search(text) or len(text) > 160 or '\n' in text:
        if getattr(widget, '_sf_math_image', None) is not None:
            widget.configure(image='')
            widget._sf_math_image = None
        return
    from tkinter import font as tkfont
    style = ttk.Style(widget)
    font_value = widget.cget('font') or style.lookup(widget.cget('style') or widget.winfo_class(), 'font') or 'TkDefaultFont'
    actual = tkfont.Font(root=widget, font=font_value).actual()
    color = widget.cget('foreground') or style.lookup(widget.cget('style') or widget.winfo_class(), 'foreground') or '#000000'
    signature = (text, actual['family'], actual['size'], actual['weight'], actual['slant'], str(color))
    if getattr(widget, '_sf_math_source', None) == signature:
        return
    from io import BytesIO
    import base64
    from matplotlib.mathtext import math_to_image
    from matplotlib.font_manager import FontProperties, findfont
    from matplotlib import rc_context
    buffer = BytesIO()
    font = FontProperties(family=actual['family'], size=abs(actual['size']),
                          weight=actual['weight'], style='italic' if actual['slant'] == 'italic' else 'normal')
    font.set_file(findfont(font))
    with rc_context({'mathtext.fontset': 'stix', 'savefig.transparent': True}):
        math_to_image(inline_tex(text), buffer, prop=font,
                      dpi=widget.winfo_fpixels('1i'), format='png', color=str(color))
    image = tk.PhotoImage(master=widget, data=base64.b64encode(buffer.getvalue()).decode('ascii'))
    widget.configure(image=image, compound='none')
    widget._sf_math_image = image
    widget._sf_math_source = signature


def format_number(value, key=''):
    """Định dạng số liệu hiển thị; không thay giá trị trong mô hình."""
    import math
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if not math.isfinite(value):
        return str(value)
    digits = 3 if str(key).casefold() in ('cc', 'cs', 'e0', 'eo', 'cv') else 2
    return f'{value:.{digits}f}'
