
from __future__ import annotations
import os
import math
import datetime
from typing import Optional

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.graphics.shapes import Drawing, Line, Rect, String, Circle, Polygon
from reportlab.graphics import renderPDF


NAVY       = colors.HexColor("#0D1B2A")
BLUE       = colors.HexColor("#0078D4")
BLUE_LIGHT = colors.HexColor("#EDF6FF")
BLUE_MID   = colors.HexColor("#C5DCF5")
AMBER      = colors.HexColor("#C47A1A")
AMBER_LITE = colors.HexColor("#FFF4E0")
RED        = colors.HexColor("#C0392B")
RED_LITE   = colors.HexColor("#FDECEA")
GREEN      = colors.HexColor("#1E7A4A")
GREEN_LITE = colors.HexColor("#EAF5EE")
GRAY       = colors.HexColor("#6B7A8A")
GRAY_LIGHT = colors.HexColor("#F4F6F8")
WHITE      = colors.white
BLACK      = colors.HexColor("#1A1A1A")
DIVIDER    = colors.HexColor("#C5D5E8")


def style(name, **kwargs):
    base = dict(fontName="Helvetica", fontSize=9, leading=13,
                textColor=BLACK, spaceAfter=2)
    base.update(kwargs)
    return ParagraphStyle(name, **base)

TITLE_STYLE   = style("title",   fontName="Helvetica-Bold", fontSize=20, textColor=NAVY, leading=24, spaceAfter=0)
SUB_STYLE     = style("sub",     fontName="Helvetica",      fontSize=10, textColor=GRAY, leading=14, spaceAfter=0)
H2_STYLE      = style("h2",      fontName="Helvetica-Bold", fontSize=9,  textColor=WHITE, leading=12, spaceAfter=0)
BODY_STYLE    = style("body",    fontName="Helvetica",      fontSize=8,  textColor=BLACK, leading=11, spaceAfter=1)
BODY_B_STYLE  = style("bodyb",   fontName="Helvetica-Bold", fontSize=8,  textColor=BLACK, leading=11, spaceAfter=1)
VAL_STYLE     = style("val",     fontName="Helvetica-Bold", fontSize=11, textColor=BLUE,  leading=14, spaceAfter=0)
UNIT_STYLE    = style("unit",    fontName="Helvetica",      fontSize=7,  textColor=GRAY,  leading=10, spaceAfter=0)
LABEL_STYLE   = style("label",   fontName="Helvetica",      fontSize=7,  textColor=GRAY,  leading=10, spaceAfter=0)
HAZARD_STYLE  = style("hazard",  fontName="Helvetica-Bold", fontSize=8,  textColor=RED,   leading=11, spaceAfter=1)
WARN_STYLE    = style("warn",    fontName="Helvetica",      fontSize=7,  textColor=AMBER, leading=10, spaceAfter=1)
SMALL_STYLE   = style("small",   fontName="Helvetica",      fontSize=7,  textColor=GRAY,  leading=10, spaceAfter=0)
MONO_STYLE    = style("mono",    fontName="Courier",        fontSize=8,  textColor=NAVY,  leading=11, spaceAfter=1)
STATION_STYLE = style("station", fontName="Courier-Bold",   fontSize=7,  textColor=NAVY,  leading=10, spaceAfter=0)


def section_header(title: str, width: float) -> Table:
    t = Table([[Paragraph(title.upper(), H2_STYLE)]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), NAVY),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
        ("RIGHTPADDING",  (0,0), (-1,-1), 8),
    ]))
    return t


def kv_row(label: str, value: str, unit: str = "", bg=WHITE):
    return [
        Paragraph(label, LABEL_STYLE),
        Paragraph(f'<b>{value}</b>', BODY_B_STYLE),
        Paragraph(unit, SMALL_STYLE),
    ]


def draw_depth_profile(stations: dict, cave_max_depth: float,
                       width: float, height: float) -> Drawing:
    d = Drawing(width, height)

    if not stations:
        d.add(String(width/2, height/2, "No station data", fontSize=8,
                     fillColor=GRAY, textAnchor="middle"))
        return d

    sorted_st = sorted(stations.items(), key=lambda x: x[1].z)
    n = len(sorted_st)
    if n == 0:
        return d

    z_max = max(s.z for _, s in sorted_st) or 1.0
    real_max = cave_max_depth or z_max

    pad_l, pad_r, pad_t, pad_b = 32, 8, 8, 20
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    d.add(Rect(0, 0, width, height, fillColor=GRAY_LIGHT, strokeColor=None))
    d.add(Rect(pad_l, pad_b, plot_w, plot_h,
               fillColor=colors.HexColor("#EDF3FA"), strokeColor=DIVIDER, strokeWidth=0.5))

    for frac in [0.25, 0.5, 0.75, 1.0]:
        y = pad_b + plot_h * (1.0 - frac)
        d.add(Line(pad_l, y, pad_l + plot_w, y,
                   strokeColor=DIVIDER, strokeWidth=0.5))
        depth_label = f"{frac * real_max:.0f}m"
        d.add(String(pad_l - 2, y - 3, depth_label,
                     fontSize=5.5, fillColor=GRAY, textAnchor="end"))

    bar_w = max(1.5, plot_w / n - 1)
    xs = []
    for i, (name, st) in enumerate(sorted_st):
        x = pad_l + (i + 0.5) * (plot_w / n)
        depth_frac = st.z / z_max if z_max > 0 else 0
        bar_h = plot_h * depth_frac
        y_top = pad_b + plot_h - bar_h

        if depth_frac < 0.33:
            bar_color = colors.HexColor("#4DA8F0")
        elif depth_frac < 0.66:
            bar_color = colors.HexColor("#0078D4")
        else:
            bar_color = colors.HexColor("#004A8F")

        d.add(Rect(x - bar_w/2, y_top, bar_w, bar_h,
                   fillColor=bar_color, strokeColor=None))
        xs.append(x)

    d.add(String(pad_l + plot_w/2, 2, "Stations (depth order)",
                 fontSize=5.5, fillColor=GRAY, textAnchor="middle"))

    return d


def draw_cave_schematic(stations: dict, width: float, height: float) -> Drawing:
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=NAVY, strokeColor=None))

    if not stations or len(stations) < 2:
        d.add(String(width/2, height/2, "Survey map unavailable",
                     fontSize=8, fillColor=GRAY, textAnchor="middle"))
        return d

    positions = [(s.x, s.y) for s in stations.values()]
    xs = [p[0] for p in positions]
    ys = [p[1] for p in positions]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_range = (x_max - x_min) or 1
    y_range = (y_max - y_min) or 1

    pad = 12

    def to_screen(x, y):
        sx = pad + (x - x_min) / x_range * (width - 2*pad)
        sy = pad + (y - y_min) / y_range * (height - 2*pad)
        return sx, sy

    st_list = list(stations.items())
    for i in range(1, len(st_list)):
        _, s_prev = st_list[i-1]
        _, s_curr = st_list[i]
        x1, y1 = to_screen(s_prev.x, s_prev.y)
        x2, y2 = to_screen(s_curr.x, s_curr.y)
        d.add(Line(x1, y1, x2, y2,
                   strokeColor=colors.HexColor("#0078D4"), strokeWidth=1.0))

    for i, (name, st) in enumerate(st_list):
        sx, sy = to_screen(st.x, st.y)
        r = 2.0 if i > 0 and i < len(st_list)-1 else 3.0
        dot_color = BLUE if i > 0 and i < len(st_list)-1 else colors.HexColor("#FFD040")
        d.add(Circle(sx, sy, r, fillColor=dot_color, strokeColor=None))

    if st_list:
        sx, sy = to_screen(st_list[0][1].x, st_list[0][1].y)
        d.add(String(sx+4, sy-3, "ENTRY", fontSize=5, fillColor=colors.HexColor("#FFD040")))

    return d


def build_gas_table(cave, col_w: float) -> Table:
    max_depth = cave.metadata.max_depth_m if hasattr(cave, "metadata") else 30.0
    total_m   = cave.total_length_m()

    swim_speed_m_min = 15.0
    penetration_m    = total_m * 0.35
    dive_time_min    = (penetration_m / swim_speed_m_min) * 2

    sac_surface   = 20.0
    depth_factor  = 1 + max_depth / 10.0
    sac_depth     = sac_surface * depth_factor
    total_gas_l   = sac_depth * dive_time_min
    third         = total_gas_l / 3.0

    tanks = [
        ("Single AL80",    11.1, 207),
        ("Twin AL80",      22.2, 207),
        ("Single LP108",   15.3, 207),
        ("Twin LP108",     30.6, 207),
        ("Twin HP120",     33.1, 241),
    ]

    headers = ["Tank Config", "Volume (L)", "Turn Press", "Reserve", "Go/No-Go"]
    rows = [headers]
    for tname, vol_l, max_bar in tanks:
        usable      = vol_l * max_bar
        turn_bar    = int(max_bar * (2/3))
        reserve_bar = int(max_bar / 3)
        ok          = usable >= total_gas_l
        rows.append([
            tname,
            f"{usable:.0f} L",
            f"{turn_bar} bar",
            f"{reserve_bar} bar",
            "GO" if ok else "NO-GO",
        ])

    t = Table(rows, colWidths=[col_w*0.28, col_w*0.18, col_w*0.18, col_w*0.18, col_w*0.18])
    style_cmds = [
        ("BACKGROUND",    (0,0), (-1,0),  NAVY),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 7),
        ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, GRAY_LIGHT]),
        ("GRID",          (0,0), (-1,-1), 0.4, DIVIDER),
        ("TOPPADDING",    (0,0), (-1,-1), 3),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
    ]
    for i in range(1, len(rows)):
        val = rows[i][4]
        bg  = GREEN_LITE if val == "GO" else RED_LITE
        fc  = GREEN      if val == "GO" else RED
        style_cmds += [
            ("BACKGROUND", (4,i), (4,i), bg),
            ("TEXTCOLOR",  (4,i), (4,i), fc),
            ("FONTNAME",   (4,i), (4,i), "Helvetica-Bold"),
        ]
    t.setStyle(TableStyle(style_cmds))
    return t


def build_station_table(stations: dict, cave_max_depth: float,
                        col_w: float, max_rows: int = 18) -> Table:
    z_values   = [s.z for s in stations.values()]
    z_max      = max(z_values) if z_values else 1.0
    real_max   = cave_max_depth or z_max

    headers = ["Station", "Depth (m)", "Width (m)", "Height (m)", "Bearing"]
    rows    = [headers]

    sorted_st = sorted(stations.items(), key=lambda x: x[1].z, reverse=True)
    for name, st in sorted_st[:max_rows]:
        real_depth = (st.z / z_max * real_max) if z_max > 0 else 0.0
        lrud = st.lrud
        if lrud:
            w = lrud.left + lrud.right
            h = lrud.up + lrud.down
        else:
            w = h = 0.0
        bearing_str = "—"
        rows.append([
            name,
            f"{real_depth:.1f}",
            f"{w:.1f}" if w > 0 else "—",
            f"{h:.1f}" if h > 0 else "—",
            bearing_str,
        ])

    if len(stations) > max_rows:
        rows.append([f"... +{len(stations)-max_rows} more stations", "", "", "", ""])

    cw = col_w / 5
    t  = Table(rows, colWidths=[cw*1.2, cw*0.95, cw*0.95, cw*0.95, cw*0.95])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,0),  NAVY),
        ("TEXTCOLOR",     (0,0), (-1,0),  WHITE),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTNAME",      (0,1), (0,-1),  "Courier-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 7),
        ("ALIGN",         (1,0), (-1,-1), "CENTER"),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [WHITE, GRAY_LIGHT]),
        ("GRID",          (0,0), (-1,-1), 0.4, DIVIDER),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
    ]))
    return t


class BriefingCanvas(rl_canvas.Canvas):
    def __init__(self, *args, cave_name="", incident_ref="", **kwargs):
        super().__init__(*args, **kwargs)
        self._cave_name    = cave_name
        self._incident_ref = incident_ref

    def save(self):
        page_count = self._pageNumber
        self.setTitle(f"SAR Briefing — {self._cave_name}")
        super().save()

    def _draw_header_footer(self, cave_name, incident_ref):
        self.saveState()
        w, h = self._pagesize

        self.setFillColor(NAVY)
        self.rect(0, h - 22*mm, w, 22*mm, fill=1, stroke=0)

        self.setFillColor(BLUE)
        self.setFont("Helvetica-Bold", 14)
        self.drawString(12*mm, h - 13*mm, "TEHOM")

        self.setFillColor(WHITE)
        self.setFont("Helvetica-Bold", 11)
        self.drawCentredString(w/2, h - 10*mm, "SAR PRE-DIVE BRIEFING SHEET")
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#9BAAB8"))
        self.drawCentredString(w/2, h - 16*mm, cave_name.upper())

        self.setFillColor(colors.HexColor("#9BAAB8"))
        self.setFont("Helvetica", 7)
        ts  = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M")
        ref = f"Incident Ref: {incident_ref}   |   Generated: {ts}   |   CONFIDENTIAL — SAR USE ONLY"
        self.drawRightString(w - 12*mm, h - 13*mm, ref)

        self.setFillColor(GRAY_LIGHT)
        self.rect(0, 0, w, 8*mm, fill=1, stroke=0)
        self.setFillColor(GRAY)
        self.setFont("Helvetica", 6.5)
        self.drawString(12*mm, 2.8*mm,
            "This briefing is generated from survey data and AI reconstruction. "
            "Verify all dimensions with the most recent survey before entry. "
            "Not a substitute for site-specific knowledge.")
        self.drawRightString(w - 12*mm, 2.8*mm,
            f"TEHOM v2  |  {cave_name}  |  Page 1 of 1")

        self.restoreState()


def generate_briefing_pdf(cave, output_dir: str = None,
                          incident_ref: str = None) -> str:
    if output_dir is None:
        output_dir = os.path.expanduser("~/Desktop")
    os.makedirs(output_dir, exist_ok=True)

    if incident_ref is None:
        incident_ref = datetime.datetime.now().strftime("INC-%Y%m%d-%H%M")

    safe_name = cave.name.replace(" ", "_").replace("/", "-")
    filename  = f"SAR_Briefing_{safe_name}_{incident_ref}.pdf"
    filepath  = os.path.join(output_dir, filename)

    page_w, page_h = landscape(A4)
    margin = 10*mm

    meta       = cave.metadata if hasattr(cave, "metadata") else None
    stations   = cave.get_all_stations()
    max_depth  = meta.max_depth_m    if meta else 30.0
    visibility = meta.visibility_m   if meta else 0.0
    water_type = meta.water_type     if meta else "unknown"
    hazards    = meta.hazards        if meta else []
    total_m    = cave.total_length_m()
    n_stations = cave.station_count()
    n_surveys  = len(cave.surveys)   if hasattr(cave, "surveys") else 0

    content_w = page_w - 2*margin
    header_h  = 22*mm
    footer_h  = 8*mm
    content_h = page_h - header_h - footer_h - 4*mm

    col1_w = content_w * 0.22
    col2_w = content_w * 0.22
    col3_w = content_w * 0.32
    col4_w = content_w * 0.24

    def make_info_table():
        data = [
            kv_row("Cave System",   cave.name),
            kv_row("Location",      f"{meta.country}" if meta else "—"),
            kv_row("Max Depth",     f"{max_depth:.0f}", "m"),
            kv_row("Total Survey",  f"{total_m:.0f}",   "m"),
            kv_row("Stations",      str(n_stations)),
            kv_row("Surveys",       str(n_surveys)),
            kv_row("Water Type",    water_type.capitalize()),
            kv_row("Visibility",    f"{visibility:.0f}" if visibility else "—", "m"),
        ]
        t = Table(data, colWidths=[col1_w*0.38, col1_w*0.42, col1_w*0.20])
        t.setStyle(TableStyle([
            ("FONTSIZE",      (0,0), (-1,-1), 7.5),
            ("TOPPADDING",    (0,0), (-1,-1), 2),
            ("BOTTOMPADDING", (0,0), (-1,-1), 2),
            ("LEFTPADDING",   (0,0), (-1,-1), 3),
            ("ROWBACKGROUNDS",(0,0), (-1,-1), [WHITE, BLUE_LIGHT]),
            ("LINEBELOW",     (0,0), (-1,-1), 0.3, DIVIDER),
        ]))
        return t

    def make_hazard_block():
        items = []
        if not hazards:
            items.append(Paragraph("No specific hazards recorded.", SMALL_STYLE))
        else:
            for hz in hazards:
                items.append(Paragraph(f"! {hz.upper()}", HAZARD_STYLE))
        items.append(Spacer(1, 3))
        items.append(Paragraph(
            "Standard cave diving protocols apply at all times. "
            "Silt-out conditions may develop rapidly. "
            "Always maintain guideline contact.",
            WARN_STYLE))
        return items

    def make_checklist():
        items_go = [
            "Guideline reel — primary + safety",
            "Twin tanks or stage with Rule of Thirds gas",
            "3 lights minimum (primary + 2 backup)",
            "Slate/wrist slate with station map",
            "Cutting tool accessible",
            "Dive computer with depth alarm set",
            "Team briefed on lost diver protocol",
        ]
        rows = [[Paragraph("PRE-ENTRY CHECKLIST", BODY_B_STYLE), ""]]
        for item in items_go:
            rows.append([
                Paragraph(f"[ ]  {item}", BODY_STYLE),
                "",
            ])
        t = Table(rows, colWidths=[col2_w * 0.85, col2_w * 0.15])
        t.setStyle(TableStyle([
            ("SPAN",          (0,0), (1,0)),
            ("BACKGROUND",    (0,0), (1,0),  BLUE_LIGHT),
            ("FONTSIZE",      (0,0), (-1,-1), 7),
            ("TOPPADDING",    (0,0), (-1,-1), 2),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ("LEFTPADDING",   (0,0), (-1,-1), 4),
            ("LINEBELOW",     (0,0), (-1,-1), 0.3, DIVIDER),
        ]))
        return t


    c = BriefingCanvas(filepath, pagesize=landscape(A4),
                       cave_name=cave.name, incident_ref=incident_ref)
    c._draw_header_footer(cave.name, incident_ref)

    y_top = page_h - header_h - margin
    x     = margin

    x1 = margin
    _draw_section(c, "Cave Information", x1, y_top, col1_w)
    y1 = y_top - 7*mm
    info_rows = [
        ("Cave System",  cave.name),
        ("Location",     f"{meta.country}, {meta.region}" if meta and meta.region else (meta.country if meta else "—")),
        ("Max Depth",    f"{max_depth:.0f} m"),
        ("Total Survey", f"{total_m:.0f} m"),
        ("Stations",     str(n_stations)),
        ("Surveys",      str(n_surveys)),
        ("Water Type",   water_type.capitalize()),
        ("Visibility",   f"{visibility:.0f} m" if visibility else "Unknown"),
    ]
    for label, val in info_rows:
        c.setFont("Helvetica", 6.5)
        c.setFillColor(GRAY)
        c.drawString(x1 + 2*mm, y1, label)
        c.setFont("Helvetica-Bold", 7.5)
        c.setFillColor(NAVY)
        c.drawRightString(x1 + col1_w - 2*mm, y1, val)
        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.3)
        c.line(x1, y1 - 1*mm, x1 + col1_w, y1 - 1*mm)
        y1 -= 5.5*mm

    y1 -= 2*mm
    _draw_section(c, "Hazards", x1, y1 + 1*mm, col1_w)
    y1 -= 6*mm
    if hazards:
        for hz in hazards:
            c.setFont("Helvetica-Bold", 7)
            c.setFillColor(RED)
            c.drawString(x1 + 2*mm, y1, f"  {hz.upper()}")
            y1 -= 4.5*mm
    else:
        c.setFont("Helvetica", 7)
        c.setFillColor(GRAY)
        c.drawString(x1 + 2*mm, y1, "No specific hazards recorded.")
        y1 -= 4.5*mm

    y1 -= 2*mm
    c.setFont("Helvetica-Oblique", 6)
    c.setFillColor(AMBER)
    warn = ("Silt-out conditions may develop rapidly. "
            "Maintain guideline contact at all times.")
    _draw_wrapped(c, warn, x1 + 2*mm, y1, col1_w - 4*mm, 6, AMBER)

    x2 = x1 + col1_w + 3*mm
    _draw_section(c, "Pre-Entry Checklist", x2, y_top, col2_w)
    y2 = y_top - 7*mm
    checklist = [
        "Guideline reel (primary + safety)",
        "Gas: Rule of Thirds confirmed",
        "3 lights (primary + 2 backup)",
        "Wrist slate with station plan",
        "Cutting tool — accessible",
        "Dive computer depth alarm set",
        "Lost diver protocol briefed",
        "Surface team notified of plan",
        "Max penetration agreed",
        "Turn pressure agreed by team",
    ]
    for item in checklist:
        c.setFont("Helvetica", 7)
        c.setFillColor(BLACK)
        c.rect(x2 + 2*mm, y2 - 0.5*mm, 2.5*mm, 2.5*mm, fill=0, stroke=1)
        c.drawString(x2 + 6*mm, y2, item)
        y2 -= 5*mm

    y2 -= 3*mm
    _draw_section(c, "Gas Planning — Rule of Thirds", x2, y2 + 1*mm, col2_w)
    y2 -= 6*mm

    swim_speed = 15.0
    penetration = total_m * 0.35
    dive_time   = (penetration / swim_speed) * 2
    sac_depth   = 20.0 * (1 + max_depth / 10.0)
    total_gas   = sac_depth * dive_time

    gas_rows = [
        ("Est. penetration",    f"{penetration:.0f} m"),
        ("Est. dive time",      f"{dive_time:.0f} min"),
        ("SAC at depth",        f"{sac_depth:.0f} L/min"),
        ("Min gas required",    f"{total_gas:.0f} L"),
        ("Turn pressure (2/3)", "At 2/3 starting pressure"),
        ("Reserve (1/3)",       "Never below 1/3"),
    ]
    for label, val in gas_rows:
        c.setFont("Helvetica", 6.5)
        c.setFillColor(GRAY)
        c.drawString(x2 + 2*mm, y2, label)
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(BLUE)
        c.drawRightString(x2 + col2_w - 2*mm, y2, val)
        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.3)
        c.line(x2, y2 - 1*mm, x2 + col2_w, y2 - 1*mm)
        y2 -= 5*mm

    x3 = x2 + col2_w + 3*mm
    _draw_section(c, "Survey Map (Schematic)", x3, y_top, col3_w)
    map_h = content_h * 0.55
    map_drawing = draw_cave_schematic(stations, col3_w, map_h)
    renderPDF.draw(map_drawing, c, x3, y_top - map_h - 6*mm)

    prof_y   = y_top - map_h - 8*mm
    prof_h   = content_h * 0.28
    _draw_section(c, "Depth Profile", x3, prof_y, col3_w)
    prof_drawing = draw_depth_profile(stations, max_depth, col3_w, prof_h)
    renderPDF.draw(prof_drawing, c, x3, prof_y - prof_h - 6*mm)

    x4 = x3 + col3_w + 3*mm
    _draw_section(c, "Station Depth Reference", x4, y_top, col4_w)
    y4 = y_top - 7*mm

    z_values = [s.z for s in stations.values()]
    z_max    = max(z_values) if z_values else 1.0

    headers = ["Station", "Depth", "W", "H"]
    col_ws  = [col4_w*0.32, col4_w*0.25, col4_w*0.21, col4_w*0.22]
    for i, (hdr, cw) in enumerate(zip(headers, col_ws)):
        c.setFillColor(NAVY)
        c.rect(x4 + sum(col_ws[:i]), y4 - 4*mm, cw, 4.5*mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 6.5)
        c.setFillColor(WHITE)
        c.drawCentredString(x4 + sum(col_ws[:i]) + cw/2, y4 - 3*mm, hdr)
    y4 -= 4.5*mm

    sorted_st = sorted(stations.items(), key=lambda x: x[1].z, reverse=True)
    max_visible = int((content_h - 30*mm) / 4.5)

    for row_i, (name, st) in enumerate(sorted_st[:max_visible]):
        real_depth = (st.z / z_max * max_depth) if z_max > 0 else 0.0
        lrud       = st.lrud
        w_str      = f"{lrud.left+lrud.right:.1f}" if lrud else "—"
        h_str      = f"{lrud.up+lrud.down:.1f}"    if lrud else "—"
        vals       = [name, f"{real_depth:.1f}m", w_str, h_str]

        bg = BLUE_LIGHT if row_i % 2 == 0 else WHITE
        for i, (val, cw) in enumerate(zip(vals, col_ws)):
            c.setFillColor(bg)
            c.rect(x4 + sum(col_ws[:i]), y4 - 4*mm, cw, 4.2*mm, fill=1, stroke=0)
            c.setStrokeColor(DIVIDER)
            c.setLineWidth(0.3)
            c.line(x4 + sum(col_ws[:i]), y4 - 4*mm,
                   x4 + sum(col_ws[:i]) + cw, y4 - 4*mm)

            font = "Courier-Bold" if i == 0 else "Helvetica"
            c.setFont(font, 6.5)
            c.setFillColor(NAVY if i == 0 else BLACK)
            if i == 0:
                c.drawString(x4 + sum(col_ws[:i]) + 1.5*mm, y4 - 3*mm, val)
            else:
                c.drawCentredString(x4 + sum(col_ws[:i]) + cw/2, y4 - 3*mm, val)
        y4 -= 4.2*mm

    if len(stations) > max_visible:
        c.setFont("Helvetica-Oblique", 6)
        c.setFillColor(GRAY)
        c.drawString(x4 + 2*mm, y4 - 3*mm,
                     f"... +{len(stations)-max_visible} more stations")

    notes_y = margin + footer_h + 2*mm
    notes_h = 14*mm
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.5)
    c.setFillColor(AMBER_LITE)
    c.rect(margin, notes_y, content_w, notes_h, fill=1, stroke=1)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(AMBER)
    c.drawString(margin + 3*mm, notes_y + notes_h - 4*mm, "INCIDENT NOTES")
    c.setFont("Helvetica", 7)
    c.setFillColor(GRAY)
    note_fields = [
        "Last known position:", "Entry time:", "Gas at entry:",
        "Planned max penetration:", "Team lead:", "Surface contact:"
    ]
    field_w = content_w / len(note_fields)
    for i, field in enumerate(note_fields):
        fx = margin + 3*mm + i * field_w
        c.drawString(fx, notes_y + notes_h - 9*mm, field)
        c.setStrokeColor(GRAY)
        c.setLineWidth(0.4)
        c.line(fx, notes_y + 3*mm, fx + field_w - 4*mm, notes_y + 3*mm)

    c.save()
    return filepath


def _draw_section(c, title: str, x: float, y: float, width: float):
    bar_h = 5.5*mm
    c.setFillColor(NAVY)
    c.rect(x, y - bar_h, width, bar_h, fill=1, stroke=0)
    c.setFont("Helvetica-Bold", 7)
    c.setFillColor(WHITE)
    c.drawString(x + 2.5*mm, y - bar_h + 1.5*mm, title.upper())


def _draw_wrapped(c, text: str, x: float, y: float, width: float,
                  font_size: float, color):
    c.setFont("Helvetica-Oblique", font_size)
    c.setFillColor(color)
    words  = text.split()
    line   = ""
    char_w = font_size * 0.52
    max_chars = int(width / char_w)
    for word in words:
        if len(line) + len(word) + 1 > max_chars:
            c.drawString(x, y, line)
            y   -= font_size * 1.4
            line = word
        else:
            line = (line + " " + word).strip()
    if line:
        c.drawString(x, y, line)
