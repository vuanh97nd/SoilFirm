"""Chuyển ngày dương lịch sang âm lịch Việt Nam (UTC+7).

Các phép tính thiên văn dựa trên thuật toán lịch âm của Hồ Ngọc Đức:
https://www.informatik.uni-leipzig.de/~duc/amlich/calrules.html
"""
from math import floor, pi, sin


def _jd(day, month, year):
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def _new_moon(k):
    t = k / 1236.85
    t2, t3 = t * t, t * t * t
    rad = pi / 180
    jd = 2415020.75933 + 29.53058868 * k + 0.0001178 * t2 - 0.000000155 * t3
    jd += 0.00033 * sin((166.56 + 132.87 * t - 0.009173 * t2) * rad)
    m = 359.2242 + 29.10535608 * k - 0.0000333 * t2 - 0.00000347 * t3
    mp = 306.0253 + 385.81691806 * k + 0.0107306 * t2 + 0.00001236 * t3
    f = 21.2964 + 390.67050646 * k - 0.0016528 * t2 - 0.00000239 * t3
    c = ((0.1734 - 0.000393 * t) * sin(m * rad) + 0.0021 * sin(2 * m * rad)
         - 0.4068 * sin(mp * rad) + 0.0161 * sin(2 * mp * rad)
         - 0.0004 * sin(3 * mp * rad) + 0.0104 * sin(2 * f * rad)
         - 0.0051 * sin((m + mp) * rad) - 0.0074 * sin((m - mp) * rad)
         + 0.0004 * sin((2 * f + m) * rad) - 0.0004 * sin((2 * f - m) * rad)
         - 0.0006 * sin((2 * f + mp) * rad) + 0.0010 * sin((2 * f - mp) * rad)
         + 0.0005 * sin((2 * mp + m) * rad))
    delta = (0.001 + 0.000839 * t + 0.0002261 * t2 - 0.00000845 * t3
             - 0.000000081 * t * t3 if t < -11 else
             -0.000278 + 0.000265 * t + 0.000262 * t2)
    return floor(jd + c - delta + 0.5 + 7 / 24)


def _sun_longitude(jdn):
    t = (jdn - 2451545.5 - 7 / 24) / 36525
    t2 = t * t
    m = 357.52910 + 35999.05030 * t - 0.0001559 * t2 - 0.00000048 * t * t2
    l0 = 280.46645 + 36000.76983 * t + 0.0003032 * t2
    dl = ((1.914600 - 0.004817 * t - 0.000014 * t2) * sin(m * pi / 180)
          + (0.019993 - 0.000101 * t) * sin(2 * m * pi / 180)
          + 0.000290 * sin(3 * m * pi / 180))
    return floor(((l0 + dl) * pi / 180) % (2 * pi) / pi * 6)


def _month_11(year):
    k = floor((_jd(31, 12, year) - 2415021) / 29.530588853)
    moon = _new_moon(k)
    return _new_moon(k - 1) if _sun_longitude(moon) >= 9 else moon


def _leap_offset(a11):
    k = floor((a11 - 2415021.076998695) / 29.530588853 + 0.5)
    previous = None
    for i in range(1, 15):
        current = _sun_longitude(_new_moon(k + i))
        if current == previous:
            return i - 1
        previous = current
    return 13


def solar_to_lunar(day, month, year):
    """Trả về (ngày, tháng, năm, có_tháng_nhuận)."""
    day_number = _jd(day, month, year)
    k = floor((day_number - 2415021.076998695) / 29.530588853)
    start = _new_moon(k + 1)
    if start > day_number:
        start = _new_moon(k)
    a11 = _month_11(year)
    b11 = a11
    if a11 >= start:
        lunar_year = year
        a11 = _month_11(year - 1)
    else:
        lunar_year = year + 1
        b11 = _month_11(year + 1)
    lunar_day = day_number - start + 1
    diff = floor((start - a11) / 29)
    lunar_month = diff + 11
    leap = False
    if b11 - a11 > 365:
        leap_diff = _leap_offset(a11)
        if diff >= leap_diff:
            lunar_month = diff + 10
        leap = diff == leap_diff
    if lunar_month > 12:
        lunar_month -= 12
    if lunar_month >= 11 and diff < 4:
        lunar_year -= 1
    return lunar_day, lunar_month, lunar_year, leap
