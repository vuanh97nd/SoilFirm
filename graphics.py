"""
Module: graphics.py
Đồ họa kỹ thuật CAD nền đắp - địa tầng và biểu đồ lún SoilFirm Pro.
- Biểu đồ lún theo thời gian St - t: Chuẩn hóa theo phong cách Excel Geotechnical (ảnh thực tế).
  + Khung viền kỹ thuật màu đen bao quanh.
  + Tiêu đề: BIỂU ĐỒ LÚN THEO THỜI GIAN (Times New Roman In hoa Đậm).
  + Chú thích: —□— Đường lún (Nút vuông viền đen ruột xám).
  + Trục tung: ĐỘ LÚN (M) xoay dọc 90 độ, giá trị âm 0.00, -0.10, -0.20, ... hướng xuống.
  + Trục hoành: THỜI GIAN (NĂM), lưới 50, 100, 150, 200, 250.
"""
from __future__ import annotations

import math
import tkinter as tk
from ui_theme import UI_FONT, UI_FONT_MONO

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from model import Project, effective_overburden, pressure
from utils import number_or_zero
from ui_i18n import english as _english_ui

_ROTATED_TEXT_CACHE: list = []

SOIL_PALETTE = [
    {'fill': '#FDF2E9', 'hatch': '#D35400', 'border': '#E0A96D'},
    {'fill': '#EBF5FB', 'hatch': '#2980B9', 'border': '#85C1E9'},
    {'fill': '#FEF9E7', 'hatch': '#B7950B', 'border': '#F9E79F'},
    {'fill': '#EAFAF1', 'hatch': '#27AE60', 'border': '#A9DFBF'},
    {'fill': '#F4ECF7', 'hatch': '#8E44AD', 'border': '#D2B4DE'},
    {'fill': '#F2F4F4', 'hatch': '#7F8C8D', 'border': '#BDC3C7'},
]


def _L(text, language='vi'):
    """Dịch text nếu đang ở chế độ English."""
    return _english_ui(text) if language == 'en' else text


def draw_rotated_text(c: tk.Canvas, x: float, y: float, text: str, angle_deg: float,
                      color: str = '#000000', font_size: int = 11, font_name: str = "timesbd.ttf"):
    """Vẽ chữ xoay góc bằng PIL fallback nếu Tkinter canvas không hỗ trợ."""
    if not HAS_PIL:
        c.create_text(x, y, text=text, fill=color, font=(UI_FONT, font_size, 'bold'))
        return

    try:
        try:
            font = ImageFont.truetype(font_name, font_size)
        except Exception:
            try:
                font = ImageFont.truetype("times.ttf", font_size)
            except Exception:
                try:
                    font = ImageFont.truetype(
                        "/opt/codex/runtimes/codex-primary-runtime/dependencies/native/"
                        "libreoffice-headless/libreoffice/share/fonts/truetype/"
                        "LiberationSerif-Bold.ttf", font_size)
                except Exception:
                    font = ImageFont.load_default()

        dummy_img = Image.new('RGBA', (1, 1), (0, 0, 0, 0))
        draw_dummy = ImageDraw.Draw(dummy_img)
        bbox = draw_dummy.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        pad = 8
        txt_img = Image.new('RGBA', (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(txt_img)
        draw.text((pad - bbox[0], pad - bbox[1]), text, fill=color, font=font)

        rotated = txt_img.rotate(angle_deg, resample=Image.BICUBIC, expand=True)
        photo = ImageTk.PhotoImage(rotated)
        _ROTATED_TEXT_CACHE.append(photo)

        c.create_image(x, y, image=photo, anchor='center')
    except Exception:
        c.create_text(x, y, text=text, fill=color, font=(UI_FONT, font_size, 'bold'))


def draw_cad_grid(c: tk.Canvas, w: int, h: int, step: int = 35):
    c.create_rectangle(0, 0, w, h, fill='#F8FAFC', outline='')
    for x in range(0, w, step):
        c.create_line(x, 0, x, h, fill='#E2E8F0', width=1, dash=(1, 3))
    for y in range(0, h, step):
        c.create_line(0, y, w, y, fill='#E2E8F0', width=1, dash=(1, 3))


def draw_soil_hatching(c: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
                       soil_cat: str, hatch_color: str):
    width = x2 - x1
    height = y2 - y1
    if height < 12 or width < 20:
        return

    if 'rời' in soil_cat.lower() or 'cát' in soil_cat.lower() or 'granular' in soil_cat.lower():
        step_x, step_y = 22, 16
        for cur_y in range(int(y1) + 6, int(y2) - 4, step_y):
            offset = 11 if (int(cur_y / step_y) % 2 == 1) else 0
            for cur_x in range(int(x1) + 8 + offset, int(x2) - 8, step_x):
                c.create_oval(cur_x - 1, cur_y - 1, cur_x + 1, cur_y + 1, fill=hatch_color, outline='')
                c.create_oval(cur_x + 6, cur_y + 4, cur_x + 7, cur_y + 5, fill=hatch_color, outline='')
    else:
        step = 26
        start_x = int(x1) - int(height)
        for cur_x in range(start_x, int(x2), step):
            sx = max(x1, cur_x)
            sy = y1 + (sx - cur_x)
            ex = min(x2, cur_x + height)
            ey = y1 + (ex - cur_x)
            if sx < x2 and sy < y2:
                c.create_line(sx, sy, ex, ey, fill=hatch_color, width=1, dash=(6, 4))


def draw_dim_h(c: tk.Canvas, x1: float, x2: float, y: float, text: str, offset: float = 20):
    dy = y - offset
    c.create_line(x1, y - 2, x1, dy - 5, fill='#94A3B8', width=1)
    c.create_line(x2, y - 2, x2, dy - 5, fill='#94A3B8', width=1)
    c.create_line(x1, dy, x2, dy, fill='#1E293B', width=1.2)
    c.create_line(x1 - 3, dy + 4, x1 + 3, dy - 4, fill='#0F172A', width=1.6)
    c.create_line(x2 - 3, dy + 4, x2 + 3, dy - 4, fill='#0F172A', width=1.6)
    mid_x = (x1 + x2) / 2
    c.create_text(mid_x, dy - 8, text=text, fill='#0F172A',
                  font=(UI_FONT, 8, 'bold'))


def draw_dim_v(c: tk.Canvas, x: float, y1: float, y2: float, text: str, offset: float = 22):
    dx = x + offset
    c.create_line(x + 2, y1, dx + 6, y1, fill='#94A3B8', width=1)
    c.create_line(x + 2, y2, dx + 6, y2, fill='#94A3B8', width=1)
    c.create_line(dx, y1, dx, y2, fill='#1E293B', width=1.2)
    c.create_line(dx - 4, y1 - 3, dx + 4, y1 + 3, fill='#0F172A', width=1.6)
    c.create_line(dx - 4, y2 - 3, dx + 4, y2 + 3, fill='#0F172A', width=1.6)
    mid_y = (y1 + y2) / 2
    c.create_text(dx + 8, mid_y, text=text, fill='#0F172A',
                  font=(UI_FONT, 8, 'bold'), anchor='w')


def draw_cad_diagram(c: tk.Canvas, project: Project, vars_dict: dict, treatment_vars: dict,
                     treatment_flags: dict, has_cw_flag: bool,
                     pan_x: float = 0.0, pan_y: float = 0.0, zoom: float = 1.0,
                     current_step: int = 4, language: str = 'vi'):
    """Vẽ sơ đồ CAD nền đắp và địa tầng.

    Tham số:
        language: 'vi' hoặc 'en' — dùng để dịch nhãn hiển thị.
    """
    L = lambda s: _L(s, language)

    c.delete('all')
    _ROTATED_TEXT_CACHE.clear()

    w = max(350, c.winfo_width())
    h = max(240, c.winfo_height())
    if w < 100 or h < 100:
        return

    draw_cad_grid(c, w, h)

    htk = number_or_zero(vars_dict.get('h_design', tk.StringVar()).get())
    m_slope = number_or_zero(vars_dict.get('slope_M', tk.StringVar(value='1.5')).get())
    b_total = number_or_zero(vars_dict.get('crest_B', tk.StringVar(value='12.0')).get())
    b = b_total / 2.0

    hc = number_or_zero(vars_dict.get('counterweight_height', tk.StringVar()).get()) if has_cw_flag else 0.0
    wc = number_or_zero(vars_dict.get('counterweight_width', tk.StringVar()).get()) if has_cw_flag else 0.0
    mc_val = number_or_zero(vars_dict.get('counterweight_m', tk.StringVar(value='1.0')).get())
    mc = hc * mc_val if has_cw_flag else 0.0

    z_tn = number_or_zero(vars_dict.get('ground_elevation', tk.StringVar(value='0.0')).get())
    water_elevation = number_or_zero(vars_dict.get('water_elevation', tk.StringVar()).get())

    h_emb = htk if htk > 0 else 3.0
    a = m_slope * h_emb
    reach = b + a
    if hc > 0 and wc > 0 and h_emb > hc:
        reach = b + m_slope * (h_emb - hc) + wc + mc

    total_depth = sum(max(0, s.thickness) for s in project.soils)
    if total_depth <= 0:
        total_depth = 8.0

    margin_left = 135.0
    margin_right = 110.0
    margin_top = 70.0
    margin_bottom = 45.0

    avail_w = max(100.0, w - (margin_left + margin_right))
    avail_h = max(100.0, h - (margin_top + margin_bottom))

    fit_scale_x = avail_w / (2.0 * max(reach, 1.0))
    depth_repr_ratio = 1.25
    fit_scale_y = avail_h / (h_emb + min(total_depth, 14.0) * depth_repr_ratio)

    if current_step == 3:
        auto_base_scale = min(fit_scale_x * 0.70, fit_scale_y * 0.82, 19.0)
    else:
        auto_base_scale = min(fit_scale_x, fit_scale_y, 28.0)

    scale = max(2.5, auto_base_scale * zoom)

    cx = (w / 2) + pan_x + (5.0 if current_step != 3 else 0.0)

    if current_step in (1, 2):
        top_y = margin_top + 45.0 + pan_y
        ground_y = top_y + h_emb * scale
    else:
        ground_y = max(margin_top + h_emb * scale, (h * 0.42) + pan_y)
        top_y = ground_y - h_emb * scale

    bottom_y = ground_y + (total_depth * scale * depth_repr_ratio)

    soil_ext = max(reach * scale + 150.0, avail_w / 2.0 + 90.0)
    x_soil_left = cx - soil_ext
    x_soil_right = cx + soil_ext
    y_curr = ground_y
    cum_depth = 0.0

    # =================================================================
    # 1. Vẽ các lớp địa tầng
    # =================================================================
    if current_step >= 2:
        for i, s in enumerate(project.soils):
            layer_h = (bottom_y - ground_y) * (s.thickness / total_depth)
            next_y = y_curr + layer_h
            cum_depth += s.thickness
            palette = SOIL_PALETTE[i % len(SOIL_PALETTE)]

            c.create_rectangle(x_soil_left, y_curr, x_soil_right, next_y,
                               fill=palette['fill'], outline=palette['border'], width=1.2)
            draw_soil_hatching(c, x_soil_left, y_curr, x_soil_right, next_y,
                               s.category, palette['hatch'])

            if layer_h >= 14:
                s_name = s.name.strip() if s.name.strip() else L(f"Lớp {i+1}")
                c.create_text(x_soil_left + 14, (y_curr + next_y) / 2 - 2, anchor='w',
                              text=s_name, fill='#1E293B',
                              font=(UI_FONT, 8, 'bold'))

            c.create_text(x_soil_left + 14, next_y - 6,
                          text=f"▽ {z_tn - cum_depth:+.2f} m",
                          fill='#64748B', font=(UI_FONT, 7), anchor='w')
            y_curr = next_y

    # Đường mặt đất tự nhiên
    c.create_line(x_soil_left - 15, ground_y, x_soil_right + 15, ground_y,
                  fill='#0F172A', width=2.5)

    ztn_box_x = x_soil_left + 15
    c.create_polygon(ztn_box_x, ground_y, ztn_box_x - 5, ground_y - 7,
                     ztn_box_x + 5, ground_y - 7,
                     fill='#1E293B', outline='#0F172A')
    c.create_line(ztn_box_x - 8, ground_y - 7, ztn_box_x + 95, ground_y - 7,
                  fill='#0F172A', width=1.2)
    c.create_text(ztn_box_x + 8, ground_y - 16,
                  text=f"Ztn = {z_tn:+.2f} m",
                  fill='#0F172A', font=(UI_FONT, 8, 'bold'), anchor='w')

    # Trục tim đường
    c.create_line(cx, top_y - 36, cx, bottom_y + 10,
                  fill='#DC2626', dash=(12, 4, 3, 4), width=1.6)
    c.create_text(cx, top_y - 42, text=L("TIM ĐƯỜNG"),
                  fill='#DC2626', font=(UI_FONT, 8, 'bold'), anchor='s')

    # =================================================================
    # 2. Vẽ thân nền đắp chính
    # =================================================================
    if current_step >= 1:
        has_counterweight = (has_cw_flag and hc > 0 and wc > 0 and h_emb > hc)
        theta_deg = math.degrees(math.atan(1.0 / max(m_slope, 0.01)))

        if has_counterweight:
            by = ground_y - hc * scale
            shoulder_x = b * scale + m_slope * (h_emb - hc) * scale
            outer_x = shoulder_x + wc * scale
            toe_x = outer_x + mc * scale

            right_pts = [(cx + b * scale, top_y), (cx + shoulder_x, by),
                         (cx + outer_x, by), (cx + toe_x, ground_y)]
            left_pts = [(2 * cx - x, y) for x, y in reversed(right_pts)]
            c.create_polygon(left_pts + right_pts, fill='#FDF6E2',
                             outline='#78350F', width=2)

            main_toe_px = (b + a) * scale
            c.create_line(cx + shoulder_x, by, cx + main_toe_px, ground_y,
                          fill='#B45309', dash=(4, 3), width=1.5)
            c.create_line(cx - shoulder_x, by, cx - main_toe_px, ground_y,
                          fill='#B45309', dash=(4, 3), width=1.5)

            draw_dim_h(c, cx + shoulder_x, cx + outer_x, by, f"L={wc:g}m", offset=14)
            draw_dim_h(c, cx + outer_x, cx + toe_x, by, f"A={mc:g}m", offset=14)

            draw_rotated_text(c, cx + (b * scale + shoulder_x) / 2,
                              (top_y + by) / 2 - 10,
                              f"1:{m_slope:g}", -theta_deg, '#78350F', 10)
            draw_rotated_text(c, cx - (b * scale + shoulder_x) / 2,
                              (top_y + by) / 2 - 10,
                              f"1:{m_slope:g}", theta_deg, '#78350F', 10)

            theta_cw_deg = math.degrees(math.atan(1.0 / max(mc_val, 0.01)))
            draw_rotated_text(c, cx + (outer_x + toe_x) / 2,
                              (by + ground_y) / 2 - 10,
                              f"1:{mc_val:g}", -theta_cw_deg, '#B45309', 10)
            draw_rotated_text(c, cx - (outer_x + toe_x) / 2,
                              (by + ground_y) / 2 - 10,
                              f"1:{mc_val:g}", theta_cw_deg, '#B45309', 10)
        else:
            toe_x = b * scale + a * scale
            right_pts = [(cx + b * scale, top_y), (cx + toe_x, ground_y)]
            left_pts = [(2 * cx - x, y) for x, y in reversed(right_pts)]
            c.create_polygon(left_pts + right_pts, fill='#FDF6E2',
                             outline='#78350F', width=2)

            draw_rotated_text(c, cx + b * scale + (toe_x - b * scale) / 2 + 5,
                              (top_y + ground_y) / 2 - 11,
                              f"1:{m_slope:g}", -theta_deg, '#78350F', 11)
            draw_rotated_text(c, cx - b * scale - (toe_x - b * scale) / 2 - 5,
                              (top_y + ground_y) / 2 - 11,
                              f"1:{m_slope:g}", theta_deg, '#78350F', 11)

        # Đường kích thước B, a
        dim_y = top_y - 20
        main_reach_px = b * scale + a * scale

        c.create_line(cx - main_reach_px, dim_y, cx + main_reach_px, dim_y,
                      fill='#1E293B', width=1.2)
        for xp in (cx - main_reach_px, cx - b * scale,
                   cx + b * scale, cx + main_reach_px):
            c.create_line(xp, ground_y, xp, dim_y - 4,
                          fill='#CBD5E1', width=1, dash=(2, 2))
            c.create_line(xp - 3, dim_y + 3, xp + 3, dim_y - 3,
                          fill='#0F172A', width=1.6)

        if a > 0:
            c.create_text(cx - (b * scale + main_reach_px) / 2, dim_y - 8,
                          text=f"a={a:g}m", fill='#0F172A',
                          font=(UI_FONT, 8, 'bold'))
            c.create_text(cx + (b * scale + main_reach_px) / 2, dim_y - 8,
                          text=f"a={a:g}m", fill='#0F172A',
                          font=(UI_FONT, 8, 'bold'))
        if b_total > 0:
            c.create_text(cx, dim_y - 8, text=f"B={b_total:g}m",
                          fill='#0F172A', font=(UI_FONT, 8, 'bold'))

        if htk > 0:
            draw_dim_v(c, cx + toe_x, top_y, ground_y, f"Htk = {htk:g}m", offset=26)

    # =================================================================
    # 3. Mực nước ngầm
    # =================================================================
    if current_step >= 1:
        soil_scale = (bottom_y - ground_y) / total_depth
        if water_elevation <= 0:
            wy = ground_y - water_elevation * soil_scale
        else:
            wy = ground_y - water_elevation * scale
        wy = max(top_y, min(bottom_y, wy))

        right_toe_px = cx + (b * scale + a * scale if current_step >= 1 else 0)
        x_mnn = max(right_toe_px + 35, x_soil_right - 145)

        c.create_line(x_soil_left, wy, x_soil_right, wy,
                      fill='#0284C7', dash=(6, 3), width=1.5)

        c.create_polygon(x_mnn, wy, x_mnn - 6, wy - 9, x_mnn + 6, wy - 9,
                         fill='#0284C7', outline='#0369A1')
        c.create_line(x_mnn - 7, wy + 2, x_mnn + 7, wy + 2, fill='#0284C7', width=1.5)
        c.create_line(x_mnn - 4, wy + 4, x_mnn + 4, wy + 4, fill='#0284C7', width=1.5)
        c.create_line(x_mnn - 2, wy + 6, x_mnn + 2, wy + 6, fill='#0284C7', width=1.5)

        if abs(water_elevation) < 1e-4:
            txt_mnn = L("▽ MNN = ±0.00 m")
        else:
            txt_mnn = L("▽ MNN = ") + f"{water_elevation:+.2f} m"
        c.create_text(x_mnn + 12, wy - 10, text=txt_mnn,
                      fill='#0369A1', anchor='w',
                      font=(UI_FONT, 8, 'bold'))

    # =================================================================
    # 4. Biểu đồ ứng suất (mục 4)
    # =================================================================
    if current_step == 3 and project.soils:
        limit_ratio = number_or_zero(vars_dict.get('limit_ratio',
                                   tk.StringVar(value='0.15')).get()) or 0.15
        num_pts = 60
        dz_step = total_depth / num_pts
        samples = []
        ha_found = total_depth

        for s_idx in range(num_pts + 1):
            cur_z = s_idx * dz_step
            p0_val = effective_overburden(project, cur_z)
            dp_val = pressure(project, cur_z, 0.0)
            samples.append((cur_z, p0_val, dp_val))
            if cur_z >= 0.5 and dp_val <= limit_ratio * p0_val and ha_found == total_depth:
                ha_found = cur_z

        max_stress = max(max(s[1] for s in samples), max(s[2] for s in samples), 1.0)
        stress_w = min(120.0, max(65.0, avail_w * 0.25))
        scale_stress = stress_w / max_stress

        pts_p0 = [(cx, ground_y)]
        for z_val, p0_val, _ in samples:
            yk = ground_y + (bottom_y - ground_y) * (z_val / total_depth)
            xk = cx - p0_val * scale_stress
            pts_p0.append((xk, yk))
        pts_p0.append((cx, bottom_y))
        c.create_polygon(pts_p0, fill='', outline='#0284C7', width=1.8)

        pts_dp = [(cx, ground_y)]
        for z_val, _, dp_val in samples:
            yk = ground_y + (bottom_y - ground_y) * (z_val / total_depth)
            xk = cx + dp_val * scale_stress
            pts_dp.append((xk, yk))
        pts_dp.append((cx, bottom_y))
        c.create_polygon(pts_dp, fill='', outline='#D97706', width=1.8)

        arrow_count = max(5, min(9, int(total_depth / 1.5)))
        for a_i in range(1, arrow_count + 1):
            z_k = total_depth * (a_i / (arrow_count + 0.5))
            y_k = ground_y + (bottom_y - ground_y) * (z_k / total_depth)
            p0_k = effective_overburden(project, z_k)
            dp_k = pressure(project, z_k, 0.0)

            xk_p0 = cx - p0_k * scale_stress
            xk_dp = cx + dp_k * scale_stress

            c.create_line(xk_p0, y_k, cx - 2, y_k, fill='#0284C7', width=1.2,
                          arrow='last', arrowshape=(6, 8, 3))
            c.create_line(xk_dp, y_k, cx + 2, y_k, fill='#D97706', width=1.2,
                          arrow='last', arrowshape=(6, 8, 3))

        c.create_text(cx - 25, ground_y - 14, text="← P₀", fill='#0284C7',
                      font=(UI_FONT, 8, 'bold'), anchor='e')
        c.create_text(cx, ground_y - 14, text="(T/m²)", fill='#64748B',
                      font=(UI_FONT, 7), anchor='center')
        c.create_text(cx + 25, ground_y - 14, text="Δp →", fill='#D97706',
                      font=(UI_FONT, 8, 'bold'), anchor='w')

        dp_0 = pressure(project, 0.0, 0.0)
        xk_dp_0 = cx + dp_0 * scale_stress
        c.create_text(xk_dp_0 + 5, ground_y - 3, text=f"{dp_0:.2f}",
                      fill='#D97706', font=(UI_FONT, 7, 'bold'), anchor='w')

        cum_z = 0.0
        prev_y_label = ground_y
        for s_idx, soil in enumerate(project.soils):
            cum_z += soil.thickness
            if cum_z > total_depth + 1e-4:
                break
            y_layer_bot = ground_y + (bottom_y - ground_y) * (cum_z / total_depth)
            p0_bot = effective_overburden(project, cum_z)
            dp_bot = pressure(project, cum_z, 0.0)

            xk_p0_bot = cx - p0_bot * scale_stress
            xk_dp_bot = cx + dp_bot * scale_stress

            c.create_oval(xk_p0_bot - 2, y_layer_bot - 2, xk_p0_bot + 2, y_layer_bot + 2,
                          fill='#0284C7', outline='')
            c.create_oval(xk_dp_bot - 2, y_layer_bot - 2, xk_dp_bot + 2, y_layer_bot + 2,
                          fill='#D97706', outline='')

            is_last = (s_idx == len(project.soils) - 1)
            if (y_layer_bot - prev_y_label >= 14) or is_last:
                c.create_text(xk_p0_bot - 5, y_layer_bot, text=f"{p0_bot:.2f}",
                              fill='#0284C7', font=(UI_FONT, 7, 'bold'), anchor='e')
                c.create_text(xk_dp_bot + 5, y_layer_bot, text=f"{dp_bot:.2f}",
                              fill='#D97706', font=(UI_FONT, 7, 'bold'), anchor='w')
                prev_y_label = y_layer_bot

        if ha_found > 0:
            y_ha = ground_y + (bottom_y - ground_y) * (min(ha_found, total_depth) / total_depth)
            p0_ha = effective_overburden(project, ha_found)
            dp_ha = pressure(project, ha_found, 0.0)
            x_ha_left = cx - p0_ha * scale_stress
            x_ha_right = cx + dp_ha * scale_stress

            c.create_line(x_ha_left, y_ha, x_ha_right, y_ha,
                          fill='#DC2626', width=1.8, dash=(5, 3))

            if ha_found == int(ha_found):
                ha_txt = f"Ha = {ha_found:g}m"
            else:
                ha_txt = f"Ha = {ha_found:.1f}m"
            c.create_rectangle(cx + 4, y_ha - 16, cx + 64, y_ha - 1,
                               fill='#FFFFFF', outline='#DC2626', width=1)
            c.create_text(cx + 34, y_ha - 9, text=ha_txt,
                          fill='#DC2626', font=(UI_FONT, 7, 'bold'),
                          anchor='center')

    # =================================================================
    # 5. Phương án xử lý (bước 4+)
    # =================================================================
    if current_step >= 4:
        mode = treatment_vars.get('treatment', tk.StringVar(value='Chờ lún')).get()
        if mode not in ('Chờ lún', 'Waiting'):
            horiz_type = treatment_vars.get('horizontal_drain_type',
                                            tk.StringVar(value='Bấc thấm ngang')).get()
            t_x = b * scale + a * scale
            if has_cw_flag and hc > 0 and wc > 0 and h_emb > hc:
                t_x = (b * scale + m_slope * (h_emb - hc) * scale
                       + wc * scale + mc * scale)
            toe_l, toe_r = cx - t_x, cx + t_x

            # Lớp đệm cát hoặc bấc thấm ngang
            if horiz_type in ('Lớp đệm cát', 'Sand drainage blanket'):
                h_sc = number_or_zero(treatment_vars.get(
                    'h_sand_cushion', tk.StringVar(value='0.5')).get())
                if h_sc <= 0:
                    h_sc = 0.5
                sc_px = max(7.0, h_sc * scale)
                c.create_rectangle(toe_l - 12, ground_y - sc_px, toe_r + 12, ground_y,
                                   fill='#FDE68A', outline='#B45309', width=1.5)
                for dot_x in range(int(toe_l), int(toe_r), 18):
                    c.create_oval(dot_x, ground_y - sc_px / 2 - 1,
                                  dot_x + 2, ground_y - sc_px / 2 + 1,
                                  fill='#B45309', outline='')
                label_sc = L("LỚP ĐỆM CÁT THOÁT NƯỚC") + f" (h = {h_sc:g}m)"
                c.create_text(cx, ground_y - sc_px / 2, text=label_sc,
                              fill='#92400E', font=(UI_FONT, 7, 'bold'))
            else:
                c.create_line(toe_l - 15, ground_y - 4, toe_r + 15, ground_y - 4,
                              fill='#7C3AED', width=3.5, dash=(9, 3))
                c.create_text(cx, ground_y - 12, text=L("BẤC THẤM NGANG"),
                              fill='#6D28D9', font=(UI_FONT, 8, 'bold'))

            # Thoát nước đứng
            is_pvd = (mode in ('PVD',))
            prefix = 'pvd_' if is_pvd else 'sd_'
            l_drain = number_or_zero(treatment_vars.get(
                f'{prefix}length', tk.StringVar()).get())
            if l_drain <= 0:
                l_drain = sum(s.thickness for s in project.soils
                              if s.category == 'Đất dính')

            if l_drain > 0:
                end_drain = ground_y + (bottom_y - ground_y) * min(1.0, l_drain / total_depth)
                d_spacing = number_or_zero(treatment_vars.get(
                    f'{prefix}spacing',
                    tk.StringVar(value='1.2' if is_pvd else '2.5')).get())
                if d_spacing <= 0.1:
                    d_spacing = 1.2 if is_pvd else 2.5

                drain_cw_enabled = treatment_flags.get(
                    'drain_cw_enabled', tk.BooleanVar()).get()
                reach_drain = reach if (has_cw_flag and drain_cw_enabled) else (b + a)
                drain_xs = [0.0]
                cur_x = d_spacing
                while cur_x <= reach_drain + 1e-4:
                    drain_xs.append(cur_x)
                    drain_xs.append(-cur_x)
                    cur_x += d_spacing
                drain_xs.sort()

                color = '#7C3AED' if is_pvd else '#B45309'
                line_w = 2.0 if is_pvd else 5.0

                for x_val in drain_xs:
                    x_p = cx + x_val * scale
                    c.create_line(x_p, ground_y, x_p, end_drain, fill=color, width=line_w)
                    c.create_polygon(x_p - 3, ground_y, x_p + 3, ground_y, x_p, ground_y - 4,
                                     fill=color, outline='')

                lbl_name = L('Bấc thấm PVD') if is_pvd else L('Cọc cát SD')
                pvd_box_x = cx + reach_drain * scale + 8
                pvd_box_y = min(bottom_y - 20, end_drain - 10)

                c.create_text(pvd_box_x + 4, pvd_box_y, anchor='w',
                              text=f"{lbl_name} L = {l_drain:g}m\nd = {d_spacing:g}m",
                              fill=color, font=(UI_FONT, 8, 'bold'))

    # =================================================================
    # 6. Thước tỷ lệ
    # =================================================================
    c.create_line(20, h - 14, 120, h - 14, fill='#0F172A', width=2)
    c.create_line(20, h - 19, 20, h - 9, fill='#0F172A', width=2)
    c.create_line(120, h - 19, 120, h - 9, fill='#0F172A', width=2)
    scale_meters = (100 / max(scale, 1e-3))
    scale_text = L("Thước tỷ lệ:") + f" ~{scale_meters:.1f} m"
    c.create_text(70, h - 22, text=scale_text,
                  font=(UI_FONT, 7, 'bold'), fill='#475569')


def render_chart_view(c: tk.Canvas, chart_data: dict, language: str = 'vi'):
    """
    Kết xuất biểu đồ kỹ thuật SoilFirm.

    Tham số:
        language: 'vi' hoặc 'en'.
    """
    L = lambda s: _L(s, language)

    c.delete('all')
    w = max(550, c.winfo_width())
    h = max(240, c.winfo_height())
    if not chart_data:
        c.create_rectangle(0, 0, w, h, fill='#F8FAFC', outline='')
        c.create_text(w / 2, h / 2,
                      text=L('Vui lòng thực hiện tính toán để kết xuất biểu đồ kỹ thuật.'),
                      fill='#64748B', font=(UI_FONT, 9, 'bold'))
        return

    c_type = chart_data.get('type', 'pvd')
    rows = chart_data.get('rows', [])
    if not rows:
        return

    c.create_rectangle(0, 0, w, h, fill='#FFFFFF', outline='')

    if c_type == 'natural':
        # 1. Khung viền kỹ thuật ngoài cùng
        c.create_rectangle(3, 3, w - 4, h - 4, outline='#0F172A', width=2)

        # 2. Tiêu đề chính
        y_title = 18
        c.create_text(w / 2, y_title, text=L("BIỂU ĐỒ LÚN THEO THỜI GIAN"),
                      font=(UI_FONT, 10, 'bold'),
                      fill='#0F172A', anchor='center')

        # 3. Chú thích
        y_leg = 36
        residual_view = chart_data.get('metric') == 'residual'
        leg_text = L("Sc dư") if residual_view else "St"
        line_len = 22
        marker_sz = 3.5
        total_leg_w = line_len + 8 + 60
        start_leg_x = (w - total_leg_w) / 2
        line_mid_x = start_leg_x + line_len / 2

        c.create_line(start_leg_x, y_leg, start_leg_x + line_len, y_leg,
                      fill='#0F172A', width=1.5)
        c.create_rectangle(line_mid_x - marker_sz, y_leg - marker_sz,
                           line_mid_x + marker_sz, y_leg + marker_sz,
                           fill='#B0B0B0', outline='#0F172A', width=1.0)
        c.create_text(start_leg_x + line_len + 8, y_leg, text=leg_text,
                      font=(UI_FONT, 8, 'bold'),
                      fill='#0F172A', anchor='w')

        # 4. Vùng vẽ đồ thị
        left = 72
        right = w - 30
        top_y = 52
        bot_y = h - 46

        if bot_y <= top_y + 40 or right <= left + 60:
            return

        c.create_rectangle(left, top_y, right, bot_y,
                           fill='#FFFFFF', outline='#0F172A', width=1.6)

        # 5. Thang đo trục tung
        if residual_view:
            value_at = lambda r: r.get('dsc_m', 0.0)
        else:
            value_at = lambda r: r.get('st_m', r.get('sc_m', 0.0))

        max_sc = max((value_at(r) for r in rows), default=0.55)
        limit_sc = max(0.20, math.ceil(max_sc / 0.10) * 0.10)
        step_y = 0.10 if limit_sc <= 1.0 else 0.20
        num_steps_y = int(round(limit_sc / step_y))

        y_coord = lambda s: top_y + (bot_y - top_y) * (s / limit_sc)

        for i in range(num_steps_y + 1):
            val_s = i * step_y
            yp = y_coord(val_s)
            c.create_line(left, yp, right, yp, fill='#CBD5E1', width=1)
            if i == 0:
                val_str = "0.00"
            elif residual_view:
                val_str = f"{val_s:.2f}"
            else:
                val_str = f"{-val_s:.2f}"
            c.create_text(left - 8, yp, text=val_str, anchor='e',
                          font=(UI_FONT, 8), fill='#0F172A')

        # Tên trục tung xoay dọc
        lbl_y_pos = (top_y + bot_y) / 2
        y_label = L("Sc dư (m)") if residual_view else L("St (m)")
        try:
            c.create_text(26, lbl_y_pos, text=y_label, angle=90,
                          font=(UI_FONT, 8, 'bold'),
                          fill='#0F172A', anchor='center')
        except Exception:
            draw_rotated_text(c, 26, lbl_y_pos, y_label, 90, '#0F172A', 8)

        # 6. Thang đo trục hoành theo THÁNG
        years = chart_data.get('time_unit') == 'years'
        time_at = lambda r: r.get('ngày', r.get('tháng', 0.0)*30)/365.25 if years else r.get('tháng', 0.0)
        max_t = max((time_at(r) for r in rows), default=1.0)
        if max_t <= 24:
            step_x = 3.0
        elif max_t <= 60:
            step_x = 6.0
        elif max_t <= 120:
            step_x = 12.0
        elif max_t <= 240:
            step_x = 24.0
        elif max_t <= 600:
            step_x = 50.0
        else:
            step_x = 100.0

        if years:
            raw_step = max(max_t/6, 0.01)
            base = 10**math.floor(math.log10(raw_step))
            step_x = next(v*base for v in (1,2,5,10) if v*base >= raw_step)
        max_x = max(step_x * 2, math.ceil(max_t / step_x) * step_x)
        num_steps_x = int(round(max_x / step_x))

        x_coord = lambda t: left + (right - left) * (t / max_x)

        for j in range(num_steps_x + 1):
            val_x = j * step_x
            xp = x_coord(val_x)
            c.create_line(xp, top_y, xp, bot_y, fill='#CBD5E1', width=1)
            c.create_text(xp, bot_y + 11, text=f"{val_x:.2f}" if years else f"{int(val_x)}",
                          font=(UI_FONT, 8),
                          fill='#475569', anchor='center')

        c.create_text((left + right) / 2, bot_y + 26,
                      text=("TIME (YEARS)" if chart_data.get("language") == "en" else "THỜI GIAN (NĂM)") if years else L("THỜI GIAN (THÁNG)"),
                      font=(UI_FONT, 8, 'bold'),
                      fill='#0F172A', anchor='center')

        # 7. Đường nối các điểm lún
        for i in range(len(rows) - 1):
            r1, r2 = rows[i], rows[i + 1]
            t1, t2 = time_at(r1), time_at(r2)
            s1, s2 = value_at(r1), value_at(r2)
            c.create_line(x_coord(t1), y_coord(s1),
                          x_coord(t2), y_coord(s2),
                          fill='#0F172A', width=1.6)

        # 8. Nút đo hình vuông
        pt_sz = 3.2
        for r in rows:
            t_val = time_at(r)
            s_val = value_at(r)
            xp = x_coord(t_val)
            yp = y_coord(s_val)
            c.create_rectangle(xp - pt_sz, yp - pt_sz, xp + pt_sz, yp + pt_sz,
                               fill='#CBD5E1', outline='#0F172A', width=1.1)

        # 8b. Đường giới hạn [ΔS]
        limit_m = chart_data.get('residual_limit_m')
        if limit_m is not None and residual_view and limit_m > 0:
            y_lim = y_coord(limit_m)
            if top_y <= y_lim <= bot_y:
                c.create_line(left, y_lim, right, y_lim,
                              fill='#DC2626', width=1.8, dash=(8, 4))
                lim_lbl = f'[ΔS] = {limit_m * 100:.1f} cm'
                c.create_text(right - 5, y_lim - 6, text=lim_lbl, anchor='ne',
                              font=(UI_FONT, 8, 'bold'), fill='#DC2626')

        if 'assessment_day' in chart_data:
            day = chart_data['assessment_day']
            point = min(rows, key=lambda r: abs(r['ngày'] - day))
            xp, yp = x_coord(day/(365.25 if years else 30.0)), y_coord(value_at(point))
            c.create_line(left, yp, xp, yp, fill='#475569', dash=(3,3))
            c.create_line(xp, top_y, xp, bot_y, fill='#475569', dash=(3, 3))
            c.create_oval(xp - 4, yp - 4, xp + 4, yp + 4,
                          fill='#0F172A', outline='white')
            unit = ('năm' if years else L('ngày'))
            shown_time = day/365.25 if years else day
            label_txt = f'{leg_text} · t={shown_time:.2f} {unit}: {value_at(point)*100:.2f} cm'
            c.create_text(xp, bot_y+11, text=f't={shown_time:.2f}', anchor='n',
                          font=(UI_FONT,8,'bold'), fill='#B91C1C')
            c.create_text(right - 5, top_y + 11, anchor='ne', text=label_txt,
                          font=(UI_FONT, 8, 'bold'), fill='#0F172A')

    else:
        # Biểu đồ đắp phân kỳ và lún PVD / SD
        total_days = max(r['ngày'] for r in rows) or 365.0
        total_months = max(1.0, math.ceil(total_days / 30.0))

        left = 72
        right = w - 60
        mid_y = h * 0.44
        top_y = 34
        bot_y = h - 42

        max_h = max(max((r['hne_m'], r['he_m'])) for r in rows) * 1.25 or 1.0
        max_s = max(max(r['st_cm'], r.get('sc_du_cm', 0.0)) for r in rows) * 1.25 or 1.0

        x_func = lambda day: left + (right - left) * (day / total_days)
        y_h_func = lambda val: mid_y - (mid_y - top_y) * (val / max_h)
        y_s_func = lambda val: mid_y + (bot_y - mid_y) * (val / max_s)

        # Tiêu đề 2 panel
        c.create_text((left + right) / 2, top_y - 18, anchor='center',
                      text=L('DIỄN BIẾN ĐẮP & LÚN / THEO THỜI GIAN'),
                      font=(UI_FONT, 9, 'bold'), fill='#0F172A')
        c.create_text(left - 4, (top_y + mid_y) / 2, anchor='e',
                      text=L('ĐẮP'), font=(UI_FONT, 8, 'bold'), fill='#1E293B', angle=90)
        c.create_text(left - 4, (mid_y + bot_y) / 2, anchor='e',
                      text=L('LÚN'), font=(UI_FONT, 8, 'bold'), fill='#0369A1', angle=90)

        poly_pts = [(left, mid_y)]
        for r in rows:
            poly_pts.append((x_func(r['ngày']), y_h_func(r['hne_m'])))
        poly_pts.extend([(right, mid_y), (left, mid_y)])
        c.create_polygon(poly_pts, fill='#F8FAFC', outline='')

        plot_width = right - left
        min_label_gap = 42.0
        step_m = max(1, math.ceil((total_months * min_label_gap) / plot_width))

        for m_idx in range(0, int(total_months) + 1):
            day_val = min(total_days, m_idx * 30.0)
            xp = x_func(day_val)
            c.create_line(xp, top_y, xp, bot_y, fill='#F1F5F9', width=1)
            if m_idx % step_m == 0 or m_idx == int(total_months):
                c.create_text(xp, top_y - 12, text=f'{m_idx}',
                              font=(UI_FONT, 8), fill='#64748B')

        c.create_text(right + 8, top_y - 12, text=L('t (tháng)'), anchor='w',
                      font=(UI_FONT, 8, 'bold'), fill='#0F172A')

        for i in range(5):
            vh = max_h * i / 4
            yp = y_h_func(vh)
            c.create_line(left, yp, right, yp, fill='#F1F5F9', width=1)
            c.create_text(left - 8, yp, text=f'{vh:.1f}', anchor='e',
                          font=(UI_FONT, 8), fill='#1E293B')
        c.create_text(left - 8, top_y - 12, text='H (m)', anchor='e',
                      font=(UI_FONT, 8, 'bold'), fill='#1E293B')

        # Đường phân cách 2 panel (nổi bật hơn)
        c.create_rectangle(left, mid_y - 1, right, mid_y + 1, fill='#334155', outline='')
        c.create_line(left, mid_y, right, mid_y, fill='#334155', width=2.5)

        for i in range(1, 5):
            vs = max_s * i / 4
            yp = y_s_func(vs)
            c.create_line(left, yp, right, yp, fill='#F1F5F9', width=1)
            c.create_text(left - 8, yp, text=f'{vs:.0f}', anchor='e',
                          font=(UI_FONT, 8), fill='#0369A1')
        c.create_text(left - 8, bot_y + 12, text='S (cm)', anchor='e',
                      font=(UI_FONT, 8), fill='#0369A1')

        c.create_rectangle(left, top_y, right, bot_y, outline='#CBD5E1', width=1.5)

        for i in range(len(rows) - 1):
            r1, r2 = rows[i], rows[i + 1]
            x1, x2 = x_func(r1['ngày']), x_func(r2['ngày'])
            c.create_line(x1, y_h_func(r1['hne_m']), x2, y_h_func(r2['hne_m']),
                          fill='#0F172A', width=2.0)
            c.create_line(x1, y_h_func(r1['he_m']), x2, y_h_func(r2['he_m']),
                          fill='#64748B', width=1.4, dash=(3, 2))

        for i in range(len(rows) - 1):
            r1, r2 = rows[i], rows[i + 1]
            x1, x2 = x_func(r1['ngày']), x_func(r2['ngày'])
            c.create_line(x1, y_s_func(r1['sc_cm']), x2, y_s_func(r2['sc_cm']),
                          fill='#0284C7', width=2.2)
            c.create_line(x1, y_s_func(r1['st_cm']), x2, y_s_func(r2['st_cm']),
                          fill='#D97706', width=1.8, dash=(5, 3))
            if 'sc_du_cm' in r1 and 'sc_du_cm' in r2:
                c.create_line(x1, y_s_func(r1['sc_du_cm']),
                              x2, y_s_func(r2['sc_du_cm']),
                              fill='#7C3AED', width=2.0, dash=(2, 2))

        # Đường giới hạn [ΔS]
        limit_cm = chart_data.get('residual_limit_cm')
        if limit_cm is not None and limit_cm > 0:
            y_lim = y_s_func(limit_cm)
            if mid_y < y_lim < bot_y:
                c.create_line(left, y_lim, right, y_lim,
                              fill='#DC2626', width=1.8, dash=(8, 4))
                c.create_text(right - 5, y_lim - 6, text=f'[ΔS] = {limit_cm:.0f} cm',
                              anchor='ne', font=(UI_FONT, 8, 'bold'), fill='#DC2626')

        for index, stage in enumerate(chart_data.get('stages', [])):
            height = stage['h_cuối']
            fill_end, wait_end = stage['kết_thúc'], stage['chờ_đến']
            yp = y_h_func(height)
            c.create_line(left,yp,x_func(min(wait_end,total_days)),yp,
                          fill='#0369A1',dash=(4,3))
            for kind,day in (('đắp',fill_end),('chờ',wait_end)):
                if kind == 'chờ' and wait_end <= fill_end:
                    continue
                xp = x_func(day)
                c.create_line(xp,top_y,xp,bot_y,fill='#0369A1',dash=(4,3))
                c.create_oval(xp-3,yp-3,xp+3,yp+3,fill='#0369A1',outline='white')
                c.create_text(xp,top_y+8+(index%3)*13,anchor='n',
                              text=f'H{stage["giai_đoạn"]} {kind}: {day:.2f} ngày',
                              font=(UI_FONT,7,'bold'),fill='#0369A1')

        if 'assessment_day' in chart_data and rows and 'sc_du_cm' in rows[0]:
            day = chart_data['assessment_day']
            point = min(rows, key=lambda r: abs(r['ngày'] - day))
            xp, yp = x_func(point['ngày']), y_s_func(point['sc_du_cm'])
            c.create_line(xp, top_y, xp, bot_y, fill='#64748B', dash=(3, 3))
            c.create_oval(xp - 4, yp - 4, xp + 4, yp + 4,
                          fill='#7C3AED', outline='white')
            label_txt = (L("Sc dư ngày") + f" {day:.0f} = "
                         + f"{point['sc_du_cm']:.2f} cm")
            c.create_text(right - 3, mid_y + 10, anchor='ne', text=label_txt,
                          font=(UI_FONT, 8, 'bold'), fill='#7C3AED')

        leg_y = h - 14
        c.create_rectangle(left, leg_y - 11, right, leg_y + 11,
                           fill='#F8FAFC', outline='#E2E8F0')

        items = [
            (L('h đắp (m)'), '#0F172A', ()),
            (L('He (m)'), '#64748B', (3, 2)),
            ('Sc(t) (cm)', '#0284C7', ()),
            ('St(t) (cm)', '#D97706', (5, 3)),
            (L('Sc dư (cm)'), '#7C3AED', (2, 2)),
            ('[ΔS]', '#DC2626', (8, 4)),
        ]

        col_w = (right - left) / len(items)
        for idx, (name, col, dsh) in enumerate(items):
            box_cx = left + idx * col_w
            c.create_line(box_cx + 10, leg_y, box_cx + 28, leg_y,
                          fill=col, width=2.0, dash=dsh)
            c.create_text(box_cx + 34, leg_y, text=name, anchor='w',
                          font=(UI_FONT, 8, 'bold'), fill=col)