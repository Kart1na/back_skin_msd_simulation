"""Generate a smart back massage assessment PDF report.

Recommended dependencies:
    pip install reportlab matplotlib pillow qrcode

The module degrades gracefully when matplotlib or qrcode is unavailable:
charts are drawn with Pillow and QR blocks become styled placeholders.
"""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import warnings
from datetime import datetime
from xml.sax.saxutils import escape

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - dependency guard.
    raise SystemExit(
        "Missing dependency: pillow. Install with: "
        "pip install reportlab matplotlib pillow qrcode"
    ) from exc

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph, Table, TableStyle
except ImportError as exc:  # pragma: no cover - dependency guard.
    raise SystemExit(
        "Missing dependency: reportlab. Install with: "
        "pip install reportlab matplotlib pillow qrcode"
    ) from exc

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
except ImportError:  # pragma: no cover - exercised only without matplotlib.
    plt = None
    font_manager = None

try:
    import qrcode
except ImportError:  # pragma: no cover - exercised only without qrcode.
    qrcode = None

try:
    import config
except ImportError:  # pragma: no cover - supports direct execution nearby.
    class _FallbackConfig:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

    config = _FallbackConfig()

try:
    from spatial_temporal_alignment import run_spatial_temporal_alignment
except ImportError:  # pragma: no cover - supports package execution fallback.
    try:
        from .spatial_temporal_alignment import run_spatial_temporal_alignment
    except ImportError:
        run_spatial_temporal_alignment = None


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = getattr(config, "output_dir", os.path.join(BASE_DIR, "outputs"))
ASSET_DIR = os.path.join(BASE_DIR, "report_assets")
SKELETON_IMAGE_PATH = os.path.abspath(os.path.join(BASE_DIR, os.pardir, "骨骼图片.png"))
BODY_SKELETON_IMAGE_PATH = os.path.join(ASSET_DIR, "back_skeleton_body.png")
FINAL_REPORT_INTERFACE_DIR = os.path.abspath(os.path.join(BASE_DIR, os.pardir, "lscure_report_interface"))
FINAL_REPORT_INTERFACE_PATH = os.path.join(FINAL_REPORT_INTERFACE_DIR, "lscure_smart_massage_report.html")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 14 * mm

COLOR_NAVY = "#0B2A4A"
COLOR_TEAL = "#008C95"
COLOR_TEAL_2 = "#009E9A"
COLOR_LINE = "#D7E3EA"
COLOR_GREEN = "#34A853"
COLOR_YELLOW = "#F5D547"
COLOR_ORANGE = "#FB8C00"
COLOR_RED = "#E53935"
COLOR_TEXT = "#263238"
COLOR_MUTED = "#6B7C85"
COLOR_LIGHT = "#F7FAFC"

PRIMARY = COLOR_NAVY
ACCENT = COLOR_TEAL
ACCENT_LIGHT = "#E6F7F8"
LINE = COLOR_LINE
TEXT = COLOR_TEXT
MUTED = COLOR_MUTED
GREEN = COLOR_GREEN
YELLOW = COLOR_YELLOW
ORANGE = COLOR_ORANGE
RED = COLOR_RED
CARD_BG = COLOR_LIGHT

FONT_NAME = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_REGULAR = FONT_NAME
CHINESE_FONT_PATH = None

SECTION_ORDER = ["Upper Back", "Mid Back", "Lower Back"]
SECTION_CN = {
    "Upper Back": "上背部",
    "Mid Back": "中背部",
    "Lower Back": "下背部",
}
SECTION_TODO = {
    "Upper Back": "Stretches",
    "Mid Back": "Posture Care",
    "Lower Back": "Release + Stretch",
}
SECTION_Y_RANGE = {
    "Upper Back": (55, 150),
    "Mid Back": (-35, 50),
    "Lower Back": (-150, -45),
}
VERTEBRAE_BY_SECTION = {
    "Upper Back": ["C7", "T1", "T2", "T3", "T4", "T5"],
    "Mid Back": ["T6", "T7", "T8", "T9", "T10", "T11", "T12"],
    "Lower Back": ["L1", "L2", "L3", "L4", "L5", "S1"],
}
VERTEBRAE = [
    vertebra
    for section in SECTION_ORDER
    for vertebra in VERTEBRAE_BY_SECTION[section]
]

ACUPOINTS = {
    "Upper Back": [
        ("BL12", "Feng Men（风门）", "Trapezius / Rhomboid"),
        ("BL13", "Fei Shu（肺俞）", "Trapezius / Rhomboid"),
        ("BL14", "Jue Yin Shu（厥阴俞）", "Trapezius"),
        ("BL15", "Xin Shu（心俞）", "Trapezius"),
        ("BL16", "Du Shu（督俞）", "Trapezius"),
    ],
    "Mid Back": [
        ("BL17", "Ge Shu（膈俞）", "Latissimus dorsi"),
        ("EXB3", "Wei Wan Xia Shu（胃脘下俞）", "Latissimus dorsi"),
        ("BL18", "Gan Shu（肝俞）", "Latissimus dorsi"),
        ("BL19", "Dan Shu（胆俞）", "Latissimus dorsi"),
        ("BL20", "Pi Shu（脾俞）", "Latissimus dorsi"),
        ("BL21", "Wei Shu（胃俞）", "Latissimus dorsi"),
    ],
    "Lower Back": [
        ("BL22", "San Jiao Shu（三焦俞）", "Thoracolumbar fascia"),
        ("BL23", "Shen Shu（肾俞）", "Thoracolumbar fascia"),
        ("BL24", "Qi Hai Shu（气海俞）", "Thoracolumbar fascia"),
        ("BL25", "Da Chang Shu（大肠俞）", "Thoracolumbar fascia"),
        ("BL26", "Guan Yuan Shu（关元俞）", "Thoracolumbar fascia"),
    ],
}

RECOMMENDATIONS = {
    "Upper Back": ["肩胛稳定训练", "胸椎伸展", "泡沫轴放松"],
    "Mid Back": ["坐姿旋转拉伸", "背阔肌放松", "胸腰段活动训练"],
    "Lower Back": ["腘绳肌拉伸", "抱膝拉伸", "骨盆稳定训练", "腰背放松"],
}


def _hex(value):
    return colors.HexColor(value)


def register_fonts():
    """Register a Chinese-capable font for ReportLab and matplotlib."""
    global FONT_NAME, FONT_BOLD, FONT_REGULAR, CHINESE_FONT_PATH

    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont("FONT_REGULAR", path))
                pdfmetrics.registerFont(TTFont("FONT_BOLD", path))
                FONT_NAME = "FONT_REGULAR"
                FONT_BOLD = "FONT_BOLD"
                FONT_REGULAR = FONT_NAME
                CHINESE_FONT_PATH = path
                if font_manager is not None:
                    try:
                        font_manager.fontManager.addfont(path)
                        matplotlib.rcParams["font.family"] = "sans-serif"
                        matplotlib.rcParams["font.sans-serif"] = [
                            font_manager.FontProperties(fname=path).get_name()
                        ]
                        matplotlib.rcParams["axes.unicode_minus"] = False
                    except Exception:
                        pass
                return
            except Exception as exc:
                warnings.warn(f"Chinese font registration failed for {path}: {exc}")

    warnings.warn("No Chinese font found. PDF will still be generated if fonts permit.")


def _font(size=28):
    if CHINESE_FONT_PATH and os.path.isfile(CHINESE_FONT_PATH):
        return ImageFont.truetype(CHINESE_FONT_PATH, size)
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _create_clean_skeleton_asset(output_path=None):
    """Extract only the spine skeleton from the reference screenshot image."""
    output_path = output_path or os.path.join(ASSET_DIR, "spine_skeleton_clean.png")
    if not os.path.isfile(SKELETON_IMAGE_PATH):
        return None

    os.makedirs(ASSET_DIR, exist_ok=True)
    src = Image.open(SKELETON_IMAGE_PATH).convert("RGBA")
    width, height = src.size
    crop = src.crop((int(width * 0.38), 0, int(width * 0.66), height)).convert("RGBA")
    pix = crop.load()
    w, h = crop.size

    for y in range(h):
        for x in range(w):
            r, g, b, a = pix[x, y]
            near_white = r > 242 and g > 242 and b > 242
            dark_label = r < 120 and g < 150 and b < 175
            saturated_artifact = (
                (g > 150 and r < 120 and b < 120)
                or (r > 180 and g > 150 and b < 85)
                or (r > 170 and g < 105 and b < 105)
            )
            bone_fill = r > 145 and g > 125 and b > 105 and not near_white
            blue_outline = b > 135 and g > 100 and r < 215

            if near_white or dark_label or saturated_artifact:
                pix[x, y] = (255, 255, 255, 0)
            elif bone_fill or blue_outline:
                pix[x, y] = (r, g, b, 255)
            else:
                pix[x, y] = (255, 255, 255, 0)

    # Remove long horizontal divider lines from the screenshot crop.
    for y in range(h):
        run = 0
        max_run = 0
        for x in range(w):
            r, g, b, a = pix[x, y]
            if a and b > 110 and g > 80 and r < 190:
                run += 1
                max_run = max(max_run, run)
            else:
                run = 0
        if max_run > int(w * 0.55):
            for yy in range(max(0, y - 1), min(h, y + 2)):
                for x in range(w):
                    r, g, b, a = pix[x, yy]
                    if a and b > 100 and g > 70 and r < 200:
                        pix[x, yy] = (255, 255, 255, 0)

    bbox = crop.getbbox()
    if bbox:
        crop = crop.crop(bbox)
    crop.save(output_path)
    return output_path


def prepare_body_skeleton_asset(body_image_path=None):
    """Persist the preferred full-back skeleton image for all future reports."""
    os.makedirs(ASSET_DIR, exist_ok=True)
    if body_image_path:
        source = os.path.abspath(body_image_path)
        if not os.path.isfile(source):
            raise FileNotFoundError(f"body_image_path not found: {source}")
        if os.path.abspath(source) != os.path.abspath(BODY_SKELETON_IMAGE_PATH):
            shutil.copyfile(source, BODY_SKELETON_IMAGE_PATH)
        return BODY_SKELETON_IMAGE_PATH
    if os.path.isfile(BODY_SKELETON_IMAGE_PATH):
        return BODY_SKELETON_IMAGE_PATH
    return None


def _style(size=9, color=COLOR_TEXT, leading=None, alignment=TA_LEFT):
    return ParagraphStyle(
        name=f"s{size}_{color}_{alignment}",
        fontName=FONT_NAME,
        fontSize=size,
        leading=leading or size + 3,
        textColor=_hex(color),
        alignment=alignment,
    )


def _draw_wrapped(c, text, x, y, width, size=9, color=COLOR_TEXT, leading=None):
    p = Paragraph(text, _style(size=size, color=color, leading=leading))
    _, h = p.wrap(width, 200)
    p.drawOn(c, x, y - h)
    return y - h


def _make_demo_stats(user_id):
    sections = [
        {
            "section": "Upper Back",
            "sample_count": 120,
            "mean_stiffness_N_m": 3200.0,
            "max_stiffness_N_m": 4200.0,
            "std_stiffness_N_m": 420.0,
            "x_mm": 0.0,
            "y_mm": 110.0,
        },
        {
            "section": "Mid Back",
            "sample_count": 120,
            "mean_stiffness_N_m": 3600.0,
            "max_stiffness_N_m": 5200.0,
            "std_stiffness_N_m": 610.0,
            "x_mm": 0.0,
            "y_mm": 10.0,
        },
        {
            "section": "Lower Back",
            "sample_count": 120,
            "mean_stiffness_N_m": 4900.0,
            "max_stiffness_N_m": 6900.0,
            "std_stiffness_N_m": 980.0,
            "x_mm": 0.0,
            "y_mm": -100.0,
        },
    ]
    points = [
        {"point_id": "upper_left", "section": "Upper Back", "x_mm": -55, "y_mm": 105, "mean_stiffness_N_m": 3000},
        {"point_id": "upper_right", "section": "Upper Back", "x_mm": 55, "y_mm": 105, "mean_stiffness_N_m": 3400},
        {"point_id": "mid_left", "section": "Mid Back", "x_mm": -45, "y_mm": 10, "mean_stiffness_N_m": 3100},
        {"point_id": "mid_right", "section": "Mid Back", "x_mm": 45, "y_mm": 10, "mean_stiffness_N_m": 4200},
        {"point_id": "lower_left", "section": "Lower Back", "x_mm": -45, "y_mm": -95, "mean_stiffness_N_m": 3800},
        {"point_id": "lower_right", "section": "Lower Back", "x_mm": 45, "y_mm": -95, "mean_stiffness_N_m": 5600},
    ]
    return {
        "user_id": user_id,
        "source": "demo",
        "overall": {"mean_stiffness_N_m": 3900.0, "max_stiffness_N_m": 6900.0},
        "sections": sections,
        "points": points,
        "regions": [],
        "records": [],
        "_is_demo": True,
    }


def _resolve_output_dir(output_dir="outputs"):
    if output_dir in (None, "outputs"):
        return OUTPUT_DIR
    if os.path.isabs(output_dir):
        return output_dir
    return os.path.join(BASE_DIR, output_dir)


def load_alignment_summary(user_id, output_dir="outputs"):
    """Load spatial-temporal alignment summary if available."""
    output_dir = _resolve_output_dir(output_dir)
    alignment_path = os.path.join(output_dir, f"{user_id}_spatial_temporal_alignment.json")
    if not os.path.isfile(alignment_path):
        return None
    with open(alignment_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_stiffness_stats(user_id, output_dir="outputs"):
    """Load stiffness stats if available."""
    output_dir = _resolve_output_dir(output_dir)
    stiffness_path = os.path.join(output_dir, f"{user_id}_stiffness_stats.json")
    if not os.path.isfile(stiffness_path):
        return None
    with open(stiffness_path, "r", encoding="utf-8") as f:
        stats = json.load(f)
    stats["_stats_path"] = stiffness_path
    return stats


def load_report_data(user_id):
    """Load report sources with alignment preferred, preserving demo fallback."""
    alignment = load_alignment_summary(user_id)
    stiffness = load_stiffness_stats(user_id)
    if alignment and stiffness:
        mode = "alignment+stiffness"
    elif alignment:
        mode = "alignment"
    elif stiffness:
        mode = "stiffness"
    else:
        mode = "demo"
    return {
        "user_id": user_id,
        "alignment": alignment,
        "stiffness": stiffness,
        "mode": mode,
    }


def _alignment_force_to_visual_stiffness(force_n):
    """Map force values into the existing stiffness chart scale for legacy visuals."""
    if force_n is None:
        return 2500.0
    return max(1200.0, float(force_n) * 550.0)


def _detection_grade(score):
    if score >= 86:
        return "D", "Severe"
    if score >= 70:
        return "C", "Higher"
    if score >= 55:
        return "B", "Moderate"
    return "A", "Mild"


def _section_detection_score(item):
    """Build a stiffness-like detection score from trajectory/force alignment.

    The current TCP trajectory format has force and 3D position but no direct
    indentation/deformation channel. This score is therefore a report-level
    stiffness proxy, not physical N/m stiffness.
    """
    mean_force = float(item.get("mean_force_N") or 0.0)
    max_force = float(item.get("max_force_N") or mean_force)
    duration_s = float(item.get("duration_s") or 0.0)
    contact_count = float(item.get("contact_count") or 0.0)
    score = 40.0 + mean_force * 2.5 + max_force * 1.5 + duration_s * 3.0 + contact_count * 0.25
    return round(max(35.0, min(96.0, score)), 1)


def _build_detection_report(user_id, alignment, sections):
    section_cn = {
        "Upper Back": "上背",
        "Mid Back": "中背",
        "Lower Back": "腰背",
    }
    section_en = {
        "Upper Back": "Upper Back",
        "Mid Back": "Mid Back",
        "Lower Back": "Lower Back",
    }
    top_regions = []
    for index, section in enumerate(sections, start=1):
        score = _section_detection_score(section)
        grade, label = _detection_grade(score)
        mean_force = section.get("mean_force_N")
        max_force = section.get("max_force_N")
        contact_count = int(section.get("contact_count") or 0)
        duration_s = float(section.get("duration_s") or 0)
        recommended_force = section.get("recommended_force_N")
        safe_range = section.get("safe_force_range_N") or [None, None]
        sub_scores = {
            "muscle": round(min(98, score + 4)),
            "acupoint": round(min(98, 50 + contact_count * 1.1)),
            "spine": round(max(35, score - 8)),
            "circulation": round(min(98, 58 + duration_s * 7 + float(max_force or 0))),
        }
        fatigue = round(min(98, (sub_scores["muscle"] + sub_scores["circulation"]) / 2 + 4))
        five_profile = [
            {"name": "僵硬", "score": sub_scores["muscle"], "grade": _detection_grade(sub_scores["muscle"])[0]},
            {"name": "疼痛", "score": round(min(98, score + float(max_force or 0))), "grade": _detection_grade(min(98, score + float(max_force or 0)))[0]},
            {"name": "淤堵", "score": sub_scores["acupoint"], "grade": _detection_grade(sub_scores["acupoint"])[0]},
            {"name": "筋膜", "score": sub_scores["spine"], "grade": _detection_grade(sub_scores["spine"])[0]},
            {"name": "疲劳", "score": fatigue, "grade": _detection_grade(fatigue)[0]},
        ]
        top_regions.append({
            "rank": index,
            "section": section.get("section"),
            "nameCN": section_cn.get(section.get("section"), section.get("section")),
            "nameEN": section_en.get(section.get("section"), section.get("section")),
            "totalScore": round(score),
            "grade": grade,
            "label": label,
            "subScores": sub_scores,
            "fiveDimensionalProfile": five_profile,
            "mean_force_N": mean_force,
            "max_force_N": max_force,
            "duration_s": duration_s,
            "contact_count": contact_count,
            "recommended_force_N": recommended_force,
            "safe_force_range_N": safe_range,
            "main_acupoints": section.get("main_acupoints", [])[:5],
            "suggestion": (
                f"{section_cn.get(section.get('section'), section.get('section'))}检测到{label}级僵硬倾向，"
                f"建议下一轮以 {recommended_force or '--'} N 左右启动，"
                f"优先处理 {', '.join(section.get('main_acupoints', [])[:3]) or '主要接触区域'}。"
            ),
        })

    top_regions.sort(key=lambda item: item["totalScore"], reverse=True)
    for index, item in enumerate(top_regions, start=1):
        item["rank"] = index
    overall_score = round(sum(item["totalScore"] for item in top_regions) / len(top_regions)) if top_regions else 0
    health_grade, health_label = _detection_grade(overall_score)
    return {
        "user": {
            "name": "张女士",
            "surname": "张",
            "phone": "13700137003",
            "gender": "女",
            "age": 28,
            "serviceCount": 3,
            "lastServiceDate": "2025-05-30",
            "healthGrade": health_grade,
            "healthLabel": health_label,
        },
        "overallScore": overall_score,
        "topRegions": top_regions,
        "alignmentOverall": alignment.get("overall", {}),
        "parameters": alignment.get("parameters", {}),
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "note": "当前输入未包含 indentation_mm，僵硬程度为基于力、接触时长、穴位密度与轨迹匹配质量的检测评分。",
    }


def _alignment_to_report_stats(user_id, alignment, alignment_path):
    """Convert spatial-temporal alignment JSON into the report's stats shape."""
    aligned_records = alignment.get("aligned_records", [])
    coords_by_name = {}
    for record in aligned_records:
        name = record.get("nearest_acupoint")
        if name and name not in coords_by_name:
            coords_by_name[name] = {
                "x_mm": (record.get("nearest_acupoint_x") or 0.0) * 1000.0,
                "y_mm": (record.get("nearest_acupoint_y") or 0.0) * 1000.0,
            }

    sections = []
    by_section = {item.get("section"): item for item in alignment.get("by_section", [])}
    for section in SECTION_ORDER:
        item = dict(by_section.get(section, {}))
        if not item:
            item = {
                "section": section,
                "contact_count": 0,
                "duration_s": 0.0,
                "mean_force_N": None,
                "max_force_N": None,
                "main_acupoints": [],
                "grade": "A",
                "label": "Mild",
                "to_do": SECTION_TODO.get(section, "Care"),
            }
        mean_force = item.get("mean_force_N")
        max_force = item.get("max_force_N") or mean_force
        item.update({
            "section": section,
            "sample_count": item.get("contact_count", 0),
            "mean_stiffness_N_m": _alignment_force_to_visual_stiffness(mean_force),
            "max_stiffness_N_m": _alignment_force_to_visual_stiffness(max_force),
            "std_stiffness_N_m": 0.0,
            "x_mm": 0.0,
            "y_mm": {"Upper Back": 110.0, "Mid Back": 10.0, "Lower Back": -100.0}[section],
        })
        sections.append(item)

    points = []
    for item in alignment.get("by_acupoint", []):
        name = item.get("name") or "unknown"
        coord = coords_by_name.get(name, {})
        points.append({
            "point_id": name,
            "section": item.get("section", "Unknown"),
            "region": item.get("region", "unknown"),
            "display_name": name,
            "sample_count": item.get("contact_count", 0),
            "mean_force_N": item.get("mean_force_N"),
            "max_force_N": item.get("max_force_N"),
            "mean_distance_mm": item.get("mean_distance_mm"),
            "min_distance_mm": item.get("min_distance_mm"),
            "force_level": item.get("force_level"),
            "attention_level": item.get("attention_level"),
            "x_mm": coord.get("x_mm"),
            "y_mm": coord.get("y_mm"),
            "mean_stiffness_N_m": _alignment_force_to_visual_stiffness(item.get("mean_force_N")),
            "max_stiffness_N_m": _alignment_force_to_visual_stiffness(item.get("max_force_N")),
        })

    detection_report = _build_detection_report(user_id, alignment, sections)
    return {
        "user_id": user_id,
        "source": "spatial_temporal_alignment",
        "overall": alignment.get("overall", {}),
        "sections": sections,
        "points": points,
        "regions": alignment.get("by_region", []),
        "records": aligned_records,
        "_alignment_summary_path": alignment_path,
        "_alignment_raw": alignment,
        "_detection_report": detection_report,
    }


def _stats_from_report_data(report_data):
    """Convert the unified report source structure into legacy report stats."""
    user_id = report_data.get("user_id")
    alignment = report_data.get("alignment")
    stiffness = report_data.get("stiffness")
    if alignment:
        alignment_path = os.path.join(OUTPUT_DIR, f"{user_id}_spatial_temporal_alignment.json")
        stats = _alignment_to_report_stats(user_id, alignment, alignment_path)
        if stiffness:
            stats["_stiffness_raw"] = stiffness
        stats["_report_mode"] = report_data.get("mode")
        return stats
    if stiffness:
        stiffness["_report_mode"] = report_data.get("mode")
        return stiffness

    alignment_path = os.path.join(OUTPUT_DIR, f"{user_id}_spatial_temporal_alignment.json")
    stiffness_path = os.path.join(OUTPUT_DIR, f"{user_id}_stiffness_stats.json")
    warnings.warn(
        f"{alignment_path} and {stiffness_path} not found. Run alignment or stiffness estimator first; "
        "using demo data for this report."
    )
    stats = _make_demo_stats(user_id)
    stats["_report_mode"] = "demo"
    return stats


def stiffness_to_grade(value):
    value = float(value or 0)
    if value < 2500:
        return "A"
    if value <= 4000:
        return "B"
    if value <= 6000:
        return "C"
    return "D"


def grade_to_color(grade):
    return {
        "A": "#FFFFFF",
        "B": COLOR_GREEN,
        "C": COLOR_YELLOW,
        "D": COLOR_RED,
    }.get(str(grade).upper(), "#FFFFFF")


def _grade_label(grade):
    return {
        "A": "Mild / 低刚度",
        "B": "Moderate / 中等",
        "C": "Higher / 偏高",
        "D": "Severe / 严重",
    }.get(grade, "Unknown")


def _section_map(stats):
    out = {}
    for item in stats.get("sections", []):
        section = item.get("section")
        if section:
            out[section] = item
    return out


def _points_for_section(stats, section_name):
    return [
        item for item in stats.get("points", [])
        if item.get("section") == section_name
    ]


def _side_delta(points):
    left = [
        float(p.get("mean_stiffness_N_m", 0))
        for p in points
        if p.get("x_mm") is not None and float(p.get("x_mm")) < 0
    ]
    right = [
        float(p.get("mean_stiffness_N_m", 0))
        for p in points
        if p.get("x_mm") is not None and float(p.get("x_mm")) > 0
    ]
    if not left or not right:
        return None, None, 0.0
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    return left_mean, right_mean, right_mean - left_mean


def _default_cover_analysis():
    return (
        "本报告重点指出了本次智能按摩评估中检测到的背部刚度偏高区域。"
        "局部肌肉与软组织如果长期处于紧张状态，可能会逐渐影响脊柱受力平衡，"
        "并增加肩背、胸腰段及下背部的不适风险。随着时间推移，身体可能会以代偿姿势适应这些变化，"
        "从而导致慢性酸痛、活动受限以及恢复效率下降。\n\n"
        "好消息是，这一切都是可以预防和改善的。通过持续进行灵手智能按摩，结合区域刚度识别、"
        "MSD软组织建模与个性化力度推荐，可以帮助释放深层紧张，维持更自然的脊柱对齐，"
        "并让背部肌肉在更安全的压力范围内逐步放松。\n\n"
        "不要等到不适演变成功能障碍。现在就开始重视姿势、负荷与背部软组织状态，"
        "让智能按摩成为日常健康管理的一部分。"
    )


def _analysis_payload(stats, user_id):
    sections = []
    for section in SECTION_ORDER:
        item = _section_map(stats).get(section, {})
        points = _points_for_section(stats, section)
        left_mean, right_mean, delta = _side_delta(points)
        sections.append({
            "section": section,
            "mean_stiffness_N_m": item.get("mean_stiffness_N_m"),
            "max_stiffness_N_m": item.get("max_stiffness_N_m"),
            "grade": stiffness_to_grade(item.get("mean_stiffness_N_m", 0)),
            "right_minus_left_N_m": None if left_mean is None else round(delta, 2),
        })
    return {
        "user_id": user_id,
        "overall": stats.get("overall", {}),
        "sections": sections,
    }


def generate_deepseek_analysis(stats, user_id, api_key=None, timeout_s=30):
    """Generate a continuous cover-page analysis paragraph with DeepSeek.

    The API key is read from the explicit argument or DEEPSEEK_API_KEY. It is
    intentionally not stored in source code or report metadata.
    """
    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return _default_cover_analysis()

    prompt = (
        "你是智能康复与按摩机器人项目的报告撰写助手。"
        "请根据背部刚度统计生成一段连续中文报告分析，风格参考高端智能按摩评估报告。"
        "不要标题，不要编号，不要项目符号，不要 JSON，不要 Markdown，不要提到 DeepSeek。"
        "输出 3 个自然段，段落之间用一个空行分隔，总字数约 260 到 360 个中文字符。"
        "第一段说明检测到的背部刚度偏高区域及可能带来的不适和负荷影响；"
        "第二段用积极语气说明通过灵手智能按摩、区域识别和个性化力度控制可以帮助改善；"
        "第三段用行动号召语气提醒现在开始重视姿势、健康与未来。"
        "必须保持非诊断性，不要宣称治疗疾病。"
    )
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": json.dumps(_analysis_payload(stats, user_id), ensure_ascii=False),
            },
        ],
        "temperature": 0.35,
        "max_tokens": 900,
    }
    request = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:].strip()
        content = content.replace("```", "").strip()
        if content:
            return content
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, ValueError, json.JSONDecodeError) as exc:
        warnings.warn(f"DeepSeek analysis unavailable, using local fallback: {exc}")
    return _default_cover_analysis()


def build_summary_table(stats):
    """Build cover-page section summary rows."""
    section_stats = _section_map(stats)
    rows = []
    defaults = {
        "Upper Back": ("B", "Moderate", "Stretches", 3200.0),
        "Mid Back": ("B", "Moderate", "Posture Care", 3600.0),
        "Lower Back": ("C", "Higher", "Release + Stretch", 4900.0),
    }
    for section in SECTION_ORDER:
        item = section_stats.get(section, {})
        if item.get("grade"):
            rows.append([
                section,
                item.get("grade", defaults[section][0]),
                item.get("label", defaults[section][1]),
                item.get("to_do", SECTION_TODO.get(section, defaults[section][2])),
            ])
            continue
        value = item.get("mean_stiffness_N_m", defaults[section][3])
        grade = stiffness_to_grade(value)
        label = _grade_label(grade).split(" / ")[0]
        rows.append([section, grade, label, SECTION_TODO.get(section, defaults[section][2])])
    return rows


def _save_placeholder_qr(content, output_path):
    img = Image.new("RGB", (300, 300), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 299, 299), outline=COLOR_TEAL, width=10)
    for x in range(24, 270, 42):
        for y in range(24, 270, 42):
            if (x * 3 + y * 5 + len(content)) % 4 in (0, 1):
                draw.rectangle((x, y, x + 22, y + 22), fill=COLOR_NAVY)
    for box in [(28, 28, 92, 92), (208, 28, 272, 92), (28, 208, 92, 272)]:
        draw.rectangle(box, outline=COLOR_TEAL, width=8)
    img.save(output_path)


def _create_qr(content, output_path):
    if qrcode is None:
        _save_placeholder_qr(content, output_path)
        return output_path
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color=COLOR_NAVY, back_color="white").convert("RGB")
    img.save(output_path)
    return output_path


def _draw_logo(c, logo_path, x, y, w, h):
    if logo_path and os.path.isfile(logo_path):
        try:
            c.drawImage(logo_path, x, y, width=w, height=h, preserveAspectRatio=True, mask="auto")
            return
        except Exception as exc:
            warnings.warn(f"Logo drawing failed, using text fallback: {exc}")

    c.setFillColor(_hex(COLOR_TEAL))
    c.setFont(FONT_BOLD, 18)
    c.drawString(x, y + h * 0.35, "LSCURE")
    c.setStrokeColor(_hex(COLOR_TEAL))
    c.setLineWidth(1.2)
    c.line(x, y + h * 0.25, x + 62, y + h * 0.25)


def draw_header(c, user_id, report_id, logo_path):
    """Draw unified page header."""
    top = PAGE_HEIGHT - MARGIN + 3 * mm
    _draw_logo(c, logo_path, MARGIN, top - 23 * mm, 48 * mm, 19 * mm)

    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 18.5)
    c.drawCentredString(PAGE_WIDTH / 2, top - 6 * mm, "灵手智能按摩报告")
    c.setFont(FONT_NAME, 9.5)
    c.setFillColor(_hex(COLOR_MUTED))
    c.drawCentredString(PAGE_WIDTH / 2, top - 12 * mm, "LingShou Smart Massage Report")

    qr_path = os.path.join(tempfile.gettempdir(), f"{report_id or user_id}_qr.png")
    _create_qr(report_id or user_id, qr_path)
    c.drawImage(qr_path, PAGE_WIDTH - MARGIN - 20 * mm, top - 22 * mm, 20 * mm, 20 * mm)

    c.setStrokeColor(_hex(COLOR_LINE))
    c.setLineWidth(0.6)
    c.line(MARGIN, top - 25 * mm, PAGE_WIDTH - MARGIN, top - 25 * mm)


def draw_footer(c, page_num=None):
    """Draw disclaimer footer."""
    y = 11 * mm
    c.setStrokeColor(_hex(COLOR_LINE))
    c.setLineWidth(0.6)
    c.line(MARGIN, y + 8 * mm, PAGE_WIDTH - MARGIN, y + 8 * mm)
    c.setFillColor(_hex(COLOR_MUTED))
    c.setFont(FONT_NAME, 7.8)
    c.drawString(MARGIN, y, "本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。")
    if page_num is not None:
        c.drawRightString(PAGE_WIDTH - MARGIN, y, f"{page_num}")


def _make_table(data, col_widths, header=True, font_size=8.5, row_height=None):
    table = Table(data, colWidths=col_widths, rowHeights=row_height)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("TEXTCOLOR", (0, 0), (-1, -1), _hex(COLOR_TEXT)),
        ("GRID", (0, 0), (-1, -1), 0.45, _hex(COLOR_LINE)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6.5),
        ("TOPPADDING", (0, 0), (-1, -1), 5.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
    ]
    if header:
        style.extend([
            ("BACKGROUND", (0, 0), (-1, 0), _hex("#EEF6F8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), _hex(COLOR_NAVY)),
            ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ])
    table.setStyle(TableStyle(style))
    return table


def wrap_text_to_width(text, font_name, font_size, max_width):
    """Wrap text into lines that fit the provided ReportLab width."""
    lines = []
    current = ""
    for char in str(text or ""):
        candidate = current + char
        if pdfmetrics.stringWidth(candidate, font_name, font_size) <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def draw_round_rect_card(c, x, y, w, h, title=None, fill_color=CARD_BG, stroke_color=LINE):
    c.saveState()
    c.setFillColor(_hex(fill_color))
    c.setStrokeColor(_hex(stroke_color))
    c.roundRect(x, y, w, h, 8, stroke=1, fill=1)
    if title:
        c.setFillColor(_hex(PRIMARY))
        c.setFont(FONT_BOLD, 11)
        c.drawString(x + 12, y + h - 18, str(title))
    c.restoreState()


def draw_badge(c, x, y, text, color, text_color=colors.white):
    c.saveState()
    c.setFillColor(_hex(color) if isinstance(color, str) else color)
    c.roundRect(x, y, 34, 20, 10, stroke=0, fill=1)
    c.setFillColor(text_color)
    c.setFont(FONT_BOLD, 9)
    c.drawCentredString(x + 17, y + 6, str(text))
    c.restoreState()


def draw_metric_card(c, x, y, w, h, title, value, subtitle, color=ACCENT):
    draw_round_rect_card(c, x, y, w, h, fill_color=CARD_BG, stroke_color=LINE)
    c.saveState()
    c.setFillColor(_hex(color))
    c.circle(x + 18, y + h - 22, 5, stroke=0, fill=1)
    c.setFillColor(_hex(MUTED))
    c.setFont(FONT_NAME, 8.5)
    c.drawString(x + 32, y + h - 27, str(title))
    c.setFillColor(_hex(PRIMARY))
    c.setFont(FONT_BOLD, 17)
    c.drawString(x + 12, y + 25, str(value))
    c.setFillColor(_hex(MUTED))
    c.setFont(FONT_NAME, 7.5)
    c.drawString(x + 12, y + 11, str(subtitle))
    c.restoreState()


def draw_grade_legend(c, x, y):
    labels = [("A", "Mild", "#FFFFFF"), ("B", "Moderate", GREEN), ("C", "Higher", YELLOW), ("D", "Severe", RED)]
    for index, (grade, label, color) in enumerate(labels):
        bx = x + index * 48
        c.setStrokeColor(_hex(LINE))
        c.setFillColor(_hex(color))
        c.roundRect(bx, y, 40, 18, 8, stroke=1, fill=1)
        c.setFillColor(_hex(PRIMARY) if grade in ("A", "C") else colors.white)
        c.setFont(FONT_BOLD, 7.5)
        c.drawCentredString(bx + 20, y + 5, f"{grade} {label}")


def draw_section_table(c, x, y, w, h, rows):
    draw_round_rect_card(c, x, y, w, h, fill_color="white", stroke_color=LINE)
    table = _make_table(rows, [w * 0.34, w * 0.18, w * 0.22, w * 0.26], font_size=8)
    _, table_h = table.wrapOn(c, w - 18, h - 18)
    table.drawOn(c, x + 9, y + h - table_h - 9)


def draw_force_scale_bar(c, x, y, w, mean_force_N):
    c.saveState()
    segment_w = w / 3
    for index, color in enumerate([GREEN, YELLOW, RED]):
        c.setFillColor(_hex(color))
        c.roundRect(x + index * segment_w, y, segment_w, 8, 4, stroke=0, fill=1)
    value = max(0, min(20, float(mean_force_N or 0)))
    marker_x = x + (value / 20) * w
    c.setFillColor(_hex(PRIMARY))
    c.circle(marker_x, y + 4, 5, stroke=0, fill=1)
    c.setFillColor(_hex(MUTED))
    c.setFont(FONT_NAME, 7)
    for index, label in enumerate(["Low", "Medium", "High"]):
        c.drawCentredString(x + segment_w * (index + 0.5), y - 10, label)
    c.restoreState()


def draw_page_header(c, title=None, logo_path=None):
    c.saveState()
    if logo_path and os.path.isfile(logo_path):
        c.drawImage(logo_path, MARGIN, PAGE_HEIGHT - 26 * mm, 24 * mm, 12 * mm, preserveAspectRatio=True, mask="auto")
    else:
        c.setFillColor(_hex(ACCENT))
        c.roundRect(MARGIN, PAGE_HEIGHT - 25 * mm, 26 * mm, 9 * mm, 4, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(FONT_BOLD, 8)
        c.drawCentredString(MARGIN + 13 * mm, PAGE_HEIGHT - 22 * mm, "LSCURE")
    if title:
        c.setFillColor(_hex(PRIMARY))
        c.setFont(FONT_BOLD, 13)
        c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 21 * mm, title)
    c.setStrokeColor(_hex(LINE))
    c.line(MARGIN, PAGE_HEIGHT - 31 * mm, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 31 * mm)
    c.restoreState()


def draw_page_footer(c, page_num):
    draw_footer(c, page_num=page_num)


def _section_value(stats, section_name, field, default=0.0):
    return float(_section_map(stats).get(section_name, {}).get(field, default) or default)


def _vertebra_stiffness_values(stats):
    """Return deterministic per-vertebra stiffness values in N/m."""
    section_offsets = {
        "Upper Back": [-0.15, 0.05, 0.20, 0.35, 0.15, -0.05],
        "Mid Back": [-0.10, 0.05, 0.22, 0.35, 0.45, 0.20, -0.05],
        "Lower Back": [-0.05, 0.15, 0.40, 0.62, 0.52, 0.10],
    }
    values = {}
    for section in SECTION_ORDER:
        mean_v = _section_value(stats, section, "mean_stiffness_N_m", 3000.0)
        max_v = _section_value(stats, section, "max_stiffness_N_m", mean_v)
        spread = max(250.0, min(max_v - mean_v, mean_v * 0.65))
        for vertebra, offset in zip(VERTEBRAE_BY_SECTION[section], section_offsets[section]):
            values[vertebra] = max(900.0, mean_v + spread * offset)
    return values


def create_spine_stiffness_chart(stats, output_path, body_image_path=None):
    """Create a spine stiffness distribution chart PNG."""
    sections = {}
    visual_values = {}
    for section in SECTION_ORDER:
        mean_v = _section_value(stats, section, "mean_stiffness_N_m", 3000.0)
        max_v = _section_value(stats, section, "max_stiffness_N_m", mean_v)
        sections[section] = mean_v
        visual_values[section] = max(mean_v, max_v * 0.85)
    labels = ["C7", "T1", "T3", "T5", "T7", "T9", "T11", "T12", "L1", "L2", "L3", "L4", "L5", "S1"]
    yvals = list(range(len(labels)))[::-1]

    body_asset = prepare_body_skeleton_asset(body_image_path)
    if body_asset:
        img = Image.new("RGB", (860, 760), "white")
        draw = ImageDraw.Draw(img)
        body = Image.open(body_asset).convert("RGBA")
        body.thumbnail((430, 650))
        bx = 28
        by = 58
        img.paste(body, (bx, by), body)

        small = _font(17)
        label_font = _font(25)
        label_small = _font(15)
        vertebra_font = _font(17)
        body_h = body.height
        spine_x = bx + int(body.width * 0.50)
        vertebra_top = by + int(body_h * 0.16)
        vertebra_bottom = by + int(body_h * 0.88)
        denom = max(len(VERTEBRAE) - 1, 1)
        vertebra_y = {
            vertebra: int(vertebra_top + (vertebra_bottom - vertebra_top) * idx / denom)
            for idx, vertebra in enumerate(VERTEBRAE)
        }
        section_slots = {}
        for section, vertebrae in VERTEBRAE_BY_SECTION.items():
            section_slots[section] = (
                vertebra_y[vertebrae[0]] - 13,
                vertebra_y[vertebrae[-1]] + 13,
            )
        section_labels = {
            "Upper Back": ("上背部", "Upper Back"),
            "Mid Back": ("中背部", "Mid Back"),
            "Lower Back": ("下背部", "Lower Back"),
        }
        values_by_vertebra = _vertebra_stiffness_values(stats)
        label_left_x = spine_x - 58
        bar_x = bx + body.width + 18
        value_x = bar_x + 58
        bracket_x = value_x + 82
        label_x = bracket_x + 24

        draw.text((bar_x, by + 8), "kN/m", font=small, fill=COLOR_MUTED)
        for vertebra in VERTEBRAE:
            y = vertebra_y[vertebra]
            value = values_by_vertebra[vertebra]
            grade = stiffness_to_grade(value)
            color = grade_to_color(grade)
            draw.text((label_left_x, y - 9), vertebra, font=vertebra_font, fill=COLOR_NAVY)
            draw.line((label_left_x + 31, y, spine_x - 6, y), fill="#A8C7E8", width=1)
            draw.rounded_rectangle(
                (bar_x, y - 8, bar_x + 40, y + 9),
                radius=3,
                fill=color,
                outline=COLOR_LINE,
            )
            draw.text((value_x, y - 10), f"{value / 1000.0:.2f}", font=small, fill=COLOR_TEXT)

        for section, (y0, y1) in section_slots.items():
            draw.line((bracket_x, y0, bracket_x, y1), fill="#6FA8DC", width=3)
            draw.line((bracket_x - 12, y0, bracket_x, y0), fill="#6FA8DC", width=3)
            draw.line((bracket_x - 12, y1, bracket_x, y1), fill="#6FA8DC", width=3)
            cn_label, en_label = section_labels[section]
            label_y = (y0 + y1) // 2 - 35
            draw.text((label_x, label_y), cn_label, font=label_font, fill=COLOR_NAVY)
            draw.text((label_x, label_y + 31), en_label, font=label_small, fill=COLOR_NAVY)
            draw.text((label_x, label_y + 51), f"{sections[section]:.0f} N/m", font=small, fill=COLOR_MUTED)

        upper_end = section_slots["Upper Back"][1]
        mid_end = section_slots["Mid Back"][1]
        for y in (upper_end + 7, mid_end + 7):
            draw.line((18, y, 820, y), fill="#A8C7E8", width=2)
        img.save(output_path)
        return output_path

    clean_skeleton_path = _create_clean_skeleton_asset()
    if clean_skeleton_path and os.path.isfile(clean_skeleton_path):
        img = Image.new("RGB", (540, 620), "white")
        draw = ImageDraw.Draw(img)
        spine = Image.open(clean_skeleton_path).convert("RGBA")
        spine.thumbnail((130, 560))
        sx = 170
        sy = 30
        img.paste(spine, (sx, sy), spine)

        small = _font(18)
        bold = _font(28)
        section_slots = {
            "Upper Back": (58, 205),
            "Mid Back": (225, 375),
            "Lower Back": (405, 570),
        }
        for section, (y0, y1) in section_slots.items():
            mean_v = sections[section]
            grade = stiffness_to_grade(mean_v)
            draw.line((365, y0, 365, y1), fill="#6FA8DC", width=3)
            draw.line((355, y0, 365, y0), fill="#6FA8DC", width=3)
            draw.line((355, y1, 365, y1), fill="#6FA8DC", width=3)
            draw.text((398, (y0 + y1) // 2 - 34), section.replace(" ", "\n"), font=bold, fill=COLOR_NAVY)
            draw.text((398, (y0 + y1) // 2 + 30), f"{mean_v:.0f} N/m  {grade}", font=small, fill=COLOR_MUTED)

        for y in (215, 390):
            draw.line((45, y, 500, y), fill="#A8C7E8", width=2)
        img.save(output_path)
        return output_path

    if plt is not None:
        fig, ax = plt.subplots(figsize=(4.2, 5.1), dpi=180)
        ax.set_facecolor("white")
        ax.plot([0] * len(yvals), yvals, color=COLOR_NAVY, linewidth=3, solid_capstyle="round")
        ax.scatter([0] * len(yvals), yvals, s=20, color="white", edgecolor=COLOR_NAVY, linewidth=1.2, zorder=3)
        for label, y in zip(labels, yvals):
            ax.text(-0.25, y, label, ha="right", va="center", fontsize=7.5, color=COLOR_MUTED)

        section_slots = {
            "Upper Back": yvals[0:5],
            "Mid Back": yvals[5:9],
            "Lower Back": yvals[9:],
        }
        for section, slots in section_slots.items():
            value = sections[section]
            visual_value = visual_values[section]
            grade = stiffness_to_grade(visual_value)
            color = grade_to_color(grade)
            bar_len = min(1.8, max(0.35, visual_value / 6500.0 * 1.8))
            for y in slots:
                ax.barh(y, bar_len, left=0.28, height=0.42, color=color, edgecolor=COLOR_LINE, linewidth=0.6)
            ax.text(2.25, sum(slots) / len(slots), section, va="center", fontsize=8.2, color=COLOR_NAVY)
            ax.text(2.25, sum(slots) / len(slots) - 0.45, f"{value:.0f} N/m  {grade}", va="center", fontsize=7, color=COLOR_MUTED)

        ax.set_xlim(-0.8, 3.2)
        ax.set_ylim(-0.8, len(labels) - 0.2)
        ax.axis("off")
        fig.tight_layout(pad=0.2)
        fig.savefig(output_path, transparent=False, facecolor="white")
        plt.close(fig)
        return output_path

    img = Image.new("RGB", (760, 920), "white")
    draw = ImageDraw.Draw(img)
    font = _font(24)
    small = _font(18)
    x0, y0, gap = 240, 80, 56
    draw.line((x0, y0, x0, y0 + gap * (len(labels) - 1)), fill=COLOR_NAVY, width=8)
    for i, label in enumerate(labels):
        y = y0 + i * gap
        draw.ellipse((x0 - 10, y - 10, x0 + 10, y + 10), fill="white", outline=COLOR_NAVY, width=3)
        draw.text((x0 - 90, y - 12), label, font=small, fill=COLOR_MUTED)

    slots = {"Upper Back": (0, 4), "Mid Back": (5, 8), "Lower Back": (9, 13)}
    for section, (start, end) in slots.items():
        value = sections[section]
        visual_value = visual_values[section]
        grade = stiffness_to_grade(visual_value)
        color = grade_to_color(grade)
        for i in range(start, end + 1):
            y = y0 + i * gap - 12
            width = int(max(70, min(280, visual_value / 6500.0 * 280)))
            draw.rounded_rectangle((x0 + 55, y, x0 + 55 + width, y + 24), radius=5, fill=color, outline=COLOR_LINE)
        mid_y = y0 + ((start + end) / 2) * gap
        draw.text((x0 + 370, mid_y - 26), section, font=font, fill=COLOR_NAVY)
        draw.text((x0 + 370, mid_y + 4), f"{value:.0f} N/m  {grade}", font=small, fill=COLOR_MUTED)
    img.save(output_path)
    return output_path


def create_section_body_chart(section_name, stats, output_path, body_image_path=None):
    """Create a simple body-back section chart PNG."""
    points = _points_for_section(stats, section_name)
    if not points:
        y0, y1 = SECTION_Y_RANGE.get(section_name, (-40, 50))
        points = [{"x_mm": -45, "y_mm": (y0 + y1) / 2, "mean_stiffness_N_m": 3000},
                  {"x_mm": 45, "y_mm": (y0 + y1) / 2, "mean_stiffness_N_m": 3800}]

    body_asset = prepare_body_skeleton_asset(body_image_path)
    if body_asset:
        img = Image.new("RGB", (650, 800), "white")
        body = Image.open(body_asset).convert("RGBA")
        body.thumbnail((430, 740))
        bx = (650 - body.width) // 2
        by = 24
        img.paste(body, (bx, by), body)
        overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(overlay)
        highlight_y = {
            "Upper Back": (165, 330),
            "Mid Back": (315, 485),
            "Lower Back": (455, 670),
        }[section_name]
        draw.rounded_rectangle(
            (155, highlight_y[0], 495, highlight_y[1]),
            radius=18,
            fill=(0, 140, 149, 28),
            outline=COLOR_TEAL,
            width=4,
        )
        for p in points:
            x = 325 + float(p.get("x_mm", 0)) / 110.0 * 150
            y = 410 - float(p.get("y_mm", 0)) / 160.0 * 305
            color = grade_to_color(stiffness_to_grade(float(p.get("mean_stiffness_N_m", 0))))
            draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=color, outline=COLOR_NAVY, width=3)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.text((120, 735), f"{section_name} / {SECTION_CN.get(section_name, '')}", font=_font(28), fill=COLOR_NAVY)
        img.save(output_path)
        return output_path

    if plt is not None:
        fig, ax = plt.subplots(figsize=(3.6, 4.5), dpi=180)
        ax.set_facecolor("white")
        body = plt.Circle((0, 0), 1, fill=False, color=COLOR_NAVY, linewidth=2)
        ax.add_patch(body)
        ax.plot([0, 0], [-0.82, 0.82], color=COLOR_NAVY, linewidth=2)
        ax.plot([-0.48, 0.48], [0.55, 0.55], color=COLOR_LINE, linewidth=8, solid_capstyle="round")
        ax.plot([-0.58, 0.58], [-0.55, -0.55], color=COLOR_LINE, linewidth=8, solid_capstyle="round")

        highlight = {
            "Upper Back": (0.33, 0.46),
            "Mid Back": (-0.13, 0.46),
            "Lower Back": (-0.62, 0.46),
        }[section_name]
        rect = plt.Rectangle((-0.46, highlight[0]), 0.92, highlight[1], facecolor="#EAF7F7", edgecolor=COLOR_TEAL, linewidth=1.5)
        ax.add_patch(rect)

        for p in points:
            x = float(p.get("x_mm", 0)) / 110.0 * 0.55
            y = float(p.get("y_mm", 0)) / 160.0 * 0.86
            value = float(p.get("mean_stiffness_N_m", 0))
            grade = stiffness_to_grade(value)
            ax.scatter([x], [y], s=95, color=grade_to_color(grade), edgecolor=COLOR_NAVY, linewidth=0.8, zorder=4)

        ax.text(0, -1.12, f"{section_name} / {SECTION_CN.get(section_name, '')}", ha="center", color=COLOR_NAVY, fontsize=9)
        ax.set_xlim(-0.9, 0.9)
        ax.set_ylim(-1.2, 1.05)
        ax.axis("off")
        fig.tight_layout(pad=0.2)
        fig.savefig(output_path, transparent=False, facecolor="white")
        plt.close(fig)
        return output_path

    img = Image.new("RGB", (650, 800), "white")
    draw = ImageDraw.Draw(img)
    draw.ellipse((180, 55, 470, 695), outline=COLOR_NAVY, width=5)
    draw.line((325, 125, 325, 650), fill=COLOR_NAVY, width=5)
    highlight_y = {"Upper Back": (170, 320), "Mid Back": (320, 470), "Lower Back": (470, 630)}[section_name]
    draw.rounded_rectangle((200, highlight_y[0], 450, highlight_y[1]), radius=20, fill="#EAF7F7", outline=COLOR_TEAL, width=4)
    for p in points:
        x = 325 + float(p.get("x_mm", 0)) / 110.0 * 145
        y = 400 - float(p.get("y_mm", 0)) / 160.0 * 320
        color = grade_to_color(stiffness_to_grade(float(p.get("mean_stiffness_N_m", 0))))
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=color, outline=COLOR_NAVY, width=3)
    draw.text((150, 720), f"{section_name} / {SECTION_CN.get(section_name, '')}", font=_font(28), fill=COLOR_NAVY)
    img.save(output_path)
    return output_path


def _draw_grade_legend(c, x, y, w):
    c.setFont(FONT_BOLD, 10)
    c.setFillColor(_hex(COLOR_NAVY))
    c.drawString(x, y, "Stiffness Grade:")
    labels = [("A", "Mild"), ("B", ""), ("C", ""), ("D", "Severe")]
    box_w = (w - 95 * mm) / 4.0
    start_x = x + 40 * mm
    for idx, (grade, label) in enumerate(labels):
        bx = start_x + idx * (box_w + 4 * mm)
        color = grade_to_color(grade)
        c.setFillColor(_hex(color))
        c.setStrokeColor(_hex(COLOR_LINE if grade == "A" else color))
        c.roundRect(bx, y - 3 * mm, box_w, 7 * mm, 2 * mm, fill=1, stroke=1)
        c.setFillColor(_hex(COLOR_NAVY if grade in ("A", "C") else "#FFFFFF"))
        c.setFont(FONT_BOLD, 8)
        c.drawCentredString(bx + box_w / 2, y - 0.8 * mm, f"{grade} {label}".strip())


def _draw_info_block(c, x, y, title, text, icon_text):
    c.setFillColor(_hex(COLOR_TEAL))
    c.circle(x + 6 * mm, y - 5 * mm, 5 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont(FONT_BOLD, 8)
    c.drawCentredString(x + 6 * mm, y - 6.5 * mm, icon_text)
    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 10)
    c.drawString(x + 16 * mm, y - 1 * mm, title)
    return _draw_wrapped(c, text, x + 16 * mm, y - 6 * mm, PAGE_WIDTH - MARGIN - x - 16 * mm, size=8.2, color=COLOR_TEXT, leading=12)


def _draw_analysis_paragraph(c, text, x, y, width):
    style = ParagraphStyle(
        name="cover_analysis_paragraph",
        fontName=FONT_NAME,
        fontSize=11.8,
        leading=18.2,
        textColor=_hex(COLOR_TEXT),
        firstLineIndent=0,
        spaceAfter=8,
    )
    current_y = y
    for paragraph in str(text).splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            current_y -= 4 * mm
            continue
        p = Paragraph(escape(paragraph), style)
        _, h = p.wrap(width, current_y - 30 * mm)
        p.drawOn(c, x, current_y - h)
        current_y -= h + 5 * mm
    return current_y


def _draw_cover_header(c, user_id, report_id, logo_path):
    top = PAGE_HEIGHT - 13 * mm
    _draw_logo(c, logo_path, MARGIN - 1 * mm, top - 23 * mm, 50 * mm, 20 * mm)

    qr_path = os.path.join(tempfile.gettempdir(), f"{report_id or user_id}_cover_qr.png")
    _create_qr(report_id or user_id, qr_path)
    c.drawImage(qr_path, PAGE_WIDTH - MARGIN - 24 * mm, top - 24 * mm, 24 * mm, 24 * mm)

    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 26)
    c.drawCentredString(PAGE_WIDTH / 2, top - 9 * mm, "灵手智能按摩报告")
    c.setFillColor(_hex("#314B6C"))
    c.setFont(FONT_NAME, 13)
    c.drawCentredString(PAGE_WIDTH / 2, top - 20 * mm, "LingShou Smart Massage Report")

    c.setStrokeColor(_hex("#2C6DB4"))
    c.setLineWidth(0.7)
    c.line(PAGE_WIDTH / 2 - 66 * mm, top - 18 * mm, PAGE_WIDTH / 2 - 54 * mm, top - 18 * mm)
    c.line(PAGE_WIDTH / 2 + 54 * mm, top - 18 * mm, PAGE_WIDTH / 2 + 66 * mm, top - 18 * mm)

    y = top - 38 * mm
    c.setStrokeColor(_hex("#2C6DB4"))
    c.line(MARGIN, y + 3 * mm, PAGE_WIDTH / 2 - 26 * mm, y + 3 * mm)
    c.line(PAGE_WIDTH / 2 + 26 * mm, y + 3 * mm, PAGE_WIDTH - MARGIN, y + 3 * mm)
    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 10.8)
    c.drawCentredString(PAGE_WIDTH / 2, y, f"报告编号：{report_id}")
    c.setFillColor(_hex(COLOR_MUTED))
    c.setFont(FONT_NAME, 8.8)
    c.drawCentredString(PAGE_WIDTH / 2, y - 8 * mm, f"用户编号：{user_id}  |  生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return y - 18 * mm


def _draw_section_icon(c, cx, cy):
    c.setStrokeColor(_hex("#2F7DD3"))
    c.setLineWidth(1.0)
    c.circle(cx, cy, 5 * mm, stroke=1, fill=0)
    c.circle(cx, cy + 2 * mm, 1.2 * mm, stroke=1, fill=0)
    c.line(cx, cy + 0.8 * mm, cx, cy - 3 * mm)
    c.line(cx - 3 * mm, cy - 2 * mm, cx - 4 * mm, cy - 4 * mm)
    c.line(cx + 3 * mm, cy - 2 * mm, cx + 4 * mm, cy - 4 * mm)
    c.line(cx - 2 * mm, cy, cx + 2 * mm, cy)


def _draw_cover_summary_table(c, x, y, rows):
    col_w = [32 * mm, 20 * mm, 24 * mm, 31 * mm]
    row_h = 21 * mm
    table_w = sum(col_w)
    headers = ["Section", "Grade", "Label", "To Do"]
    c.setFillColor(_hex("#168AA2"))
    c.roundRect(x, y - row_h, table_w, row_h, 2.5 * mm, fill=1, stroke=0)
    c.setStrokeColor(_hex(COLOR_LINE))
    c.setLineWidth(0.5)
    x_pos = x
    c.setFont(FONT_BOLD, 10)
    c.setFillColor(colors.white)
    for idx, header in enumerate(headers):
        c.drawCentredString(x_pos + col_w[idx] / 2, y - 11 * mm, header)
        if idx:
            c.line(x_pos, y, x_pos, y - row_h * 4)
        x_pos += col_w[idx]

    c.setFillColor(colors.white)
    c.rect(x, y - row_h * 4, table_w, row_h * 3, fill=1, stroke=0)
    c.setStrokeColor(_hex(COLOR_LINE))
    c.roundRect(x, y - row_h * 4, table_w, row_h * 4, 2.5 * mm, fill=0, stroke=1)
    for i in range(1, 4):
        c.line(x, y - row_h * i, x + table_w, y - row_h * i)
    x_pos = x
    for w in col_w[:-1]:
        x_pos += w
        c.line(x_pos, y, x_pos, y - row_h * 4)

    c.setFont(FONT_NAME, 9.5)
    for r, row in enumerate(rows):
        cy = y - row_h * (r + 1.5)
        _draw_section_icon(c, x + 7 * mm, cy)
        c.setFillColor(_hex(COLOR_NAVY))
        c.drawString(x + 14 * mm, cy - 2 * mm, row[0])
        c.setFont(FONT_BOLD, 12)
        c.drawCentredString(x + col_w[0] + col_w[1] / 2, cy - 2 * mm, row[1])
        c.setFont(FONT_NAME, 9.5)
        c.drawCentredString(x + col_w[0] + col_w[1] + col_w[2] / 2, cy - 2 * mm, row[2])
        c.drawCentredString(x + col_w[0] + col_w[1] + col_w[2] + col_w[3] / 2, cy - 2 * mm, row[3])
    return table_w, row_h * 4


def draw_cover_page(c, stats, user_id, report_id, logo_path, analysis_blocks=None, body_image_path=None):
    """Draw the first page of the report."""
    analysis_text = analysis_blocks or _default_cover_analysis()
    top_y = _draw_cover_header(c, user_id, report_id, logo_path)

    left_x = MARGIN
    right_x = PAGE_WIDTH - MARGIN - 78 * mm
    rows = build_summary_table(stats)
    _, table_h = _draw_cover_summary_table(c, left_x, top_y - 5 * mm, rows)

    chart_path = os.path.join(OUTPUT_DIR, f"{user_id}_spine_stiffness_chart.png")
    create_spine_stiffness_chart(stats, chart_path, body_image_path=body_image_path)
    c.drawImage(chart_path, right_x, top_y - 92 * mm, 78 * mm, 84 * mm, preserveAspectRatio=True, mask="auto")

    legend_y = top_y - table_h - 12 * mm
    _draw_grade_legend(c, MARGIN, legend_y, PAGE_WIDTH - 2 * MARGIN)

    section_y = legend_y - 15 * mm
    c.setStrokeColor(_hex(COLOR_LINE))
    c.setLineWidth(0.7)
    c.line(MARGIN, section_y + 4 * mm, PAGE_WIDTH - MARGIN, section_y + 4 * mm)
    _draw_analysis_paragraph(
        c,
        analysis_text,
        MARGIN + 2 * mm,
        section_y - 2 * mm,
        PAGE_WIDTH - 2 * MARGIN - 4 * mm,
    )

    draw_footer(c, page_num=1)


def _draw_gradient_bar(c, x, y, w, h):
    steps = 64
    for i in range(steps):
        t = i / max(steps - 1, 1)
        if t < 0.5:
            r1, g1, b1 = colors.HexColor("#E9F7EF").rgb()
            r2, g2, b2 = colors.HexColor(COLOR_YELLOW).rgb()
            local = t * 2
        else:
            r1, g1, b1 = colors.HexColor(COLOR_YELLOW).rgb()
            r2, g2, b2 = colors.HexColor(COLOR_RED).rgb()
            local = (t - 0.5) * 2
        c.setFillColor(colors.Color(
            r1 + (r2 - r1) * local,
            g1 + (g2 - g1) * local,
            b1 + (b2 - b1) * local,
        ))
        c.rect(x + w * i / steps, y, w / steps + 0.5, h, stroke=0, fill=1)
    c.setStrokeColor(_hex(COLOR_LINE))
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.setFillColor(_hex(COLOR_MUTED))
    c.setFont(FONT_NAME, 8)
    c.drawString(x, y - 10, "Low")
    c.drawRightString(x + w, y - 10, "High")


def _section_summary_text(section_name, section_stats, points):
    if "mean_force_N" in section_stats:
        mean_force = section_stats.get("mean_force_N")
        max_force = section_stats.get("max_force_N")
        duration_s = float(section_stats.get("duration_s", 0) or 0)
        main_acupoints = section_stats.get("main_acupoints") or []
        frequent = main_acupoints[0] if main_acupoints else "No contact acupoint"
        nearest = ""
        section_points = [p for p in points if p.get("min_distance_mm") is not None]
        if section_points:
            nearest_point = min(section_points, key=lambda p: float(p.get("min_distance_mm") or 999999))
            nearest = (
                f" The nearest matched acupoint is {nearest_point.get('point_id')} "
                f"({float(nearest_point.get('min_distance_mm') or 0):.1f} mm)."
            )
        force_text = "no valid force" if mean_force is None else f"mean force {float(mean_force):.2f} N"
        max_text = "no max force" if max_force is None else f"max force {float(max_force):.2f} N"
        return (
            f"{section_name} was aligned from robot TCP trajectory, 3D acupoint coordinates, "
            f"and real-time force samples. The section recorded {force_text}, {max_text}, "
            f"and {duration_s:.2f} s of valid contact. The most frequently contacted acupoint "
            f"is {frequent}.{nearest} Force level is {section_stats.get('force_level', 'low')}; "
            f"attention level is {section_stats.get('attention_level', 'normal')}."
        )

    mean_v = float(section_stats.get("mean_stiffness_N_m", 0) or 0)
    max_v = float(section_stats.get("max_stiffness_N_m", 0) or 0)
    grade = stiffness_to_grade(mean_v)
    left_mean, right_mean, delta = _side_delta(points)
    if left_mean is None:
        side_text = "当前数据未形成明确左右侧差异，建议结合触诊或后续多点采样继续观察。"
    elif abs(delta) < 300:
        side_text = "左右侧刚度差异较小，整体负荷分布相对均衡。"
    elif delta > 0:
        side_text = f"右侧平均刚度较左侧高约 {abs(delta):.0f} N/m，提示右侧负荷或紧张累积更明显。"
    else:
        side_text = f"左侧平均刚度较右侧高约 {abs(delta):.0f} N/m，提示左侧负荷或紧张累积更明显。"

    return (
        f"{SECTION_CN.get(section_name, section_name)}平均刚度约 {mean_v:.0f} N/m，"
        f"最高刚度约 {max_v:.0f} N/m，综合等级为 {grade}（{_grade_label(grade)}）。"
        f"{side_text}"
    )


def draw_section_page(c, section_name, section_stats, acupoints):
    """Draw a section analysis page.

    The caller should draw header/footer around this content.
    """
    y = PAGE_HEIGHT - 45 * mm
    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 20)
    c.drawString(MARGIN, y, f"{section_name} / {SECTION_CN.get(section_name, '')}分析")
    c.setStrokeColor(_hex(COLOR_LINE))
    c.line(MARGIN, y - 6 * mm, PAGE_WIDTH - MARGIN, y - 6 * mm)

    left_x = MARGIN
    right_x = PAGE_WIDTH - MARGIN - 78 * mm
    table_y = y - 16 * mm

    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 12)
    c.drawString(left_x, table_y, "穴位参考")
    acu_data = [["Label", "Acupoint Name", "Muscle / Region"]] + [list(row) for row in acupoints]
    acu_table = _make_table(acu_data, [18 * mm, 39 * mm, 44 * mm], font_size=7.8)
    _, acu_h = acu_table.wrapOn(c, 104 * mm, 80 * mm)
    acu_table.drawOn(c, left_x, table_y - acu_h - 5 * mm)

    chart_path = section_stats.get("_chart_path")
    if chart_path and os.path.isfile(chart_path):
        c.drawImage(chart_path, right_x, table_y - 86 * mm, 78 * mm, 92 * mm, preserveAspectRatio=True, mask="auto")

    section_grade = section_stats.get("grade") or stiffness_to_grade(section_stats.get("mean_stiffness_N_m", 0))
    label = section_stats.get("label") or _grade_label(section_grade).split(" / ")[0]
    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 12)
    c.drawString(left_x, table_y - acu_h - 18 * mm, "Section")
    sec_data = [
        ["Section", "Grade", "Label", "To Do"],
        [section_name, section_grade, label, section_stats.get("to_do") or SECTION_TODO.get(section_name, "Care")],
    ]
    sec_table = _make_table(sec_data, [31 * mm, 16 * mm, 22 * mm, 34 * mm], font_size=8.8)
    _, sec_h = sec_table.wrapOn(c, 106 * mm, 34 * mm)
    sec_table.drawOn(c, left_x, table_y - acu_h - 22 * mm - sec_h)

    bar_y = table_y - acu_h - 47 * mm
    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 11)
    c.drawString(left_x, bar_y + 12 * mm, "刚度条")
    _draw_gradient_bar(c, left_x, bar_y, 118 * mm, 7 * mm)

    summary_y = bar_y - 25 * mm
    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 12)
    c.drawString(left_x, summary_y, "Summary")
    _draw_wrapped(
        c,
        section_stats.get("_summary_text", ""),
        left_x,
        summary_y - 7 * mm,
        PAGE_WIDTH - 2 * MARGIN,
        size=9.4,
        leading=14.2,
    )

    rec_y = summary_y - 38 * mm
    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 12)
    c.drawString(left_x, rec_y, "Recommendation")
    recs = section_stats.get("_recommendations", RECOMMENDATIONS.get(section_name, []))
    for idx, item in enumerate(recs, start=1):
        y_item = rec_y - (idx * 9.8 * mm)
        c.setFillColor(_hex(COLOR_TEAL))
        c.circle(left_x + 3 * mm, y_item + 1.5 * mm, 2.3 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(FONT_BOLD, 6)
        c.drawCentredString(left_x + 3 * mm, y_item, str(idx))
        c.setFillColor(_hex(COLOR_TEXT))
        c.setFont(FONT_NAME, 10)
        c.drawString(left_x + 9 * mm, y_item, item)


def _create_cover_preview(stats, user_id, report_id, logo_path, output_path, analysis_blocks=None, body_image_path=None):
    analysis_text = analysis_blocks or _default_cover_analysis()
    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    title_font = _font(54)
    sub_font = _font(27)
    body_font = _font(24)
    small_font = _font(22)

    def pil_wrapped(text, xy, font, fill, max_width, line_gap=8):
        x0, y0 = xy
        line = ""
        lines = []
        for ch in str(text):
            test = line + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width or not line:
                line = test
            else:
                lines.append(line)
                line = ch
        if line:
            lines.append(line)
        y = y0
        for item in lines:
            draw.text((x0, y), item, font=font, fill=fill)
            bbox = draw.textbbox((0, 0), item, font=font)
            y += bbox[3] - bbox[1] + line_gap
        return y

    if logo_path and os.path.isfile(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((275, 105))
            img.paste(logo, (75, 62), logo)
        except Exception:
            draw.text((90, 95), "LSCURE", font=title_font, fill=COLOR_TEAL)
    else:
        draw.text((90, 95), "LSCURE", font=title_font, fill=COLOR_TEAL)

    qr_path = os.path.join(tempfile.gettempdir(), f"{report_id or user_id}_preview_qr.png")
    _create_qr(report_id or user_id, qr_path)
    try:
        qr_img = Image.open(qr_path).convert("RGB")
        qr_img.thumbnail((135, 135))
        img.paste(qr_img, (1025, 62))
    except Exception:
        draw.rectangle((1025, 62, 1160, 197), outline=COLOR_TEAL, width=5)

    draw.text((360, 75), "灵手智能按摩报告", font=title_font, fill=COLOR_NAVY)
    draw.text((410, 135), "LingShou Smart Massage Report", font=sub_font, fill=COLOR_MUTED)
    draw.line((75, 215, 430, 215), fill="#2C6DB4", width=2)
    draw.line((805, 215, 1165, 215), fill="#2C6DB4", width=2)

    draw.text((470, 198), f"报告编号：{report_id}", font=body_font, fill=COLOR_NAVY)
    draw.text((380, 245), f"用户编号：{user_id}  |  生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", font=small_font, fill=COLOR_MUTED)

    draw.text((75, 372), "Section Summary", font=sub_font, fill=COLOR_NAVY)
    rows = build_summary_table(stats)
    y = 425
    for row in [["Section", "Grade", "Label", "To Do"]] + rows:
        fill = "#168AA2" if y == 425 else "white"
        draw.rectangle((75, y, 710, y + 70), fill=fill, outline=COLOR_LINE, width=2)
        x_positions = [98, 300, 390, 500]
        for x, value in zip(x_positions, row):
            draw.text((x, y + 21), str(value), font=small_font, fill="white" if y == 425 else COLOR_TEXT)
        y += 70

    chart_path = os.path.join(OUTPUT_DIR, f"{user_id}_spine_stiffness_chart.png")
    create_spine_stiffness_chart(stats, chart_path, body_image_path=body_image_path)
    if os.path.isfile(chart_path):
        chart = Image.open(chart_path).convert("RGB")
        chart.thumbnail((535, 680))
        img.paste(chart, (700, 315))

    draw.text((75, 785), "Stiffness Grade:", font=small_font, fill=COLOR_NAVY)
    legend = [("A", "Mild", "#FFFFFF"), ("B", "", COLOR_GREEN), ("C", "", COLOR_YELLOW), ("D", "Severe", COLOR_RED)]
    x = 285
    for grade, label, fill in legend:
        draw.rounded_rectangle((x, 776, x + 118, 818), radius=8, fill=fill, outline=COLOR_LINE)
        draw.text((x + 24, 786), f"{grade} {label}".strip(), font=small_font, fill=COLOR_NAVY if grade in ("A", "C") else "white")
        x += 120

    draw.line((75, 895, 1165, 895), fill=COLOR_LINE, width=2)
    y = 935
    for paragraph in str(analysis_text).splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            y += 26
            continue
        y = pil_wrapped(paragraph, (75, y), small_font, COLOR_TEXT, 1090, line_gap=13)
        y += 22

    draw.line((90, 1660, 1150, 1660), fill=COLOR_LINE, width=2)
    draw.text((90, 1680), "本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。", font=small_font, fill=COLOR_MUTED)
    img.save(output_path)
    return output_path


def _draw_gradient_rect(draw, box, left_color, right_color, radius=0):
    x1, y1, x2, y2 = [int(v) for v in box]
    w = max(1, x2 - x1)
    h = max(1, y2 - y1)
    grad = Image.new("RGB", (w, h), left_color)
    lp = tuple(int(left_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    rp = tuple(int(right_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    pix = grad.load()
    for x in range(w):
        t = x / max(w - 1, 1)
        color = tuple(int(lp[i] + (rp[i] - lp[i]) * t) for i in range(3))
        for y in range(h):
            pix[x, y] = color
    if radius:
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=radius, fill=255)
        canvas_img = Image.new("RGB", draw.im.size, "white")
        canvas_img.paste(grad, (x1, y1), mask)
        draw.bitmap((0, 0), canvas_img.convert("1"))
    else:
        draw.bitmap((x1, y1), grad.convert("1"))


def _pil_text(draw, xy, text, size=28, fill=COLOR_TEXT, bold=False, anchor=None):
    draw.text(xy, str(text), font=_font(size if not bold else size + 1), fill=fill, anchor=anchor)


def _score_grade_color(grade):
    return {"A": "#22C55E", "B": "#13B8C8", "C": "#F0445C", "D": "#8B2E0F"}.get(grade, "#13B8C8")


def _section_cn_from_detection(section):
    return {"Upper Back": "上背", "Mid Back": "中背", "Lower Back": "腰背"}.get(section, section)


def _draw_metric_card(draw, box, label, value):
    draw.rounded_rectangle(box, radius=22, fill="#F8FAFC")
    x1, y1, x2, _ = box
    _pil_text(draw, ((x1 + x2) / 2, y1 + 30), label, size=22, fill="#94A3B8", anchor="mm")
    _pil_text(draw, ((x1 + x2) / 2, y1 + 72), value, size=30, fill="#1E293B", bold=True, anchor="mm")


def _draw_profile_bar(draw, x, y, name, score, grade):
    _pil_text(draw, (x, y + 10), name, size=22, fill="#64748B", bold=True)
    track = (x + 78, y + 9, x + 500, y + 31)
    draw.rounded_rectangle(track, radius=11, fill="#EEF2F7")
    fill_w = int((track[2] - track[0]) * max(0, min(100, score)) / 100.0)
    bar_color = "#8B2E0F" if grade == "D" else "#F0445C" if grade == "C" else "#13B8C8"
    draw.rounded_rectangle((track[0], track[1], track[0] + fill_w, track[3]), radius=11, fill=bar_color)
    _pil_text(draw, (track[0] + fill_w - 12, y + 20), str(int(score)), size=16, fill="white", bold=True, anchor="rm")
    badge_color = _score_grade_color(grade)
    draw.rounded_rectangle((x + 530, y - 4, x + 590, y + 44), radius=16, fill=badge_color)
    _pil_text(draw, (x + 560, y + 20), grade, size=24, fill="white", bold=True, anchor="mm")


def create_massage_detection_report_image(stats, user_id, output_path):
    """Create a mobile-card style stiffness/massage detection report image."""
    detection = stats.get("_detection_report")
    if not detection:
        return None
    user = detection["user"]
    top_regions = detection.get("topRegions", [])[:3]
    page_h = 620 + max(1, len(top_regions)) * 650
    img = Image.new("RGB", (930, page_h), "#F7F9FC")
    draw = ImageDraw.Draw(img)

    # Header card.
    card = (60, 18, 870, 350)
    draw.rounded_rectangle(card, radius=34, fill="white")
    draw.rounded_rectangle((78, 18, 852, 27), radius=5, fill="#27D3C3")
    draw.rounded_rectangle((720, 18, 852, 27), radius=5, fill="#11AEEA")
    draw.rounded_rectangle((100, 78, 205, 183), radius=26, fill="#27C9C3")
    _pil_text(draw, (152, 132), user["surname"], size=38, fill="white", bold=True, anchor="mm")
    _pil_text(draw, (240, 106), user["name"], size=36, fill="#0F172A", bold=True)
    _pil_text(draw, (240, 156), f"☎ {user['phone']}    ♀ {user['gender']} {user['age']}岁", size=24, fill="#64748B")
    _draw_metric_card(draw, (100, 225, 310, 318), "服务次数", f"{user['serviceCount']}次")
    _draw_metric_card(draw, (360, 225, 570, 318), "上次服务", user["lastServiceDate"])
    _draw_metric_card(draw, (620, 225, 830, 318), "健康等级", user["healthGrade"])

    y = 425
    _pil_text(draw, (76, y), "◎", size=38, fill="#27C9C3", bold=True)
    _pil_text(draw, (125, y + 4), "身体重点部位分析", size=32, fill="#0F172A", bold=True)
    draw.rounded_rectangle((380, y - 4, 475, y + 38), radius=20, fill="#CCFBF1")
    _pil_text(draw, (428, y + 18), "TOP 3", size=22, fill="#0F766E", bold=True, anchor="mm")

    y += 78
    for region in top_regions:
        h = 610
        draw.rounded_rectangle((60, y, 870, y + h), radius=30, fill="white")
        draw.rounded_rectangle((78, y, 852, y + 8), radius=4, fill="#27D3C3")
        draw.rounded_rectangle((720, y, 852, y + 8), radius=4, fill="#11AEEA")
        rank_color = "#F0445C" if region["rank"] == 1 else "#F59E0B" if region["rank"] == 2 else "#13B8C8"
        draw.rounded_rectangle((100, y + 52, 178, y + 130), radius=20, fill=rank_color)
        _pil_text(draw, (139, y + 92), str(region["rank"]), size=28, fill="white", bold=True, anchor="mm")
        _pil_text(draw, (205, y + 67), region["nameCN"], size=32, fill="#0F172A", bold=True)
        _pil_text(draw, (205, y + 108), region["nameEN"], size=21, fill="#94A3B8")
        _pil_text(draw, (600, y + 82), "综合", size=22, fill="#94A3B8")
        _pil_text(draw, (660, y + 82), str(region["totalScore"]), size=36, fill="#F0445C", bold=True)
        draw.rounded_rectangle((735, y + 55, 790, y + 112), radius=18, fill=_score_grade_color(region["grade"]))
        _pil_text(draw, (762, y + 84), region["grade"], size=26, fill="white", bold=True, anchor="mm")

        sub = region["subScores"]
        draw.rounded_rectangle((100, y + 170, 830, y + 255), radius=24, fill="#FFF1F2")
        labels = [("肌肉", "muscle"), ("穴位", "acupoint"), ("脊柱", "spine"), ("循环", "circulation")]
        for idx, (label, key) in enumerate(labels):
            cx = 180 + idx * 175
            _pil_text(draw, (cx, y + 200), label, size=20, fill="#94A3B8", anchor="mm")
            _pil_text(draw, (cx, y + 235), str(sub[key]), size=28, fill="#1E293B", bold=True, anchor="mm")

        _pil_text(draw, (110, y + 305), "五维画像", size=28, fill="#0F172A", bold=True)
        _pil_text(draw, (520, y + 307), "S=优秀 A=良好 B=一般 C=较差 D=严重", size=16, fill="#94A3B8")
        for idx, item in enumerate(region["fiveDimensionalProfile"][:5]):
            _draw_profile_bar(draw, 110, y + 340 + idx * 50, item["name"], item["score"], item["grade"])
        y += h + 34

    if top_regions:
        first = top_regions[0]
        cta_y = min(page_h - 110, y + 8)
        draw.rounded_rectangle((38, cta_y, 892, cta_y + 86), radius=28, fill="#18BFD4")
        text = f"建议力度 {first.get('recommended_force_N', '--')} N  ·  现在就去理疗"
        _pil_text(draw, (465, cta_y + 43), text, size=30, fill="white", bold=True, anchor="mm")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path)
    return output_path


def _file_url(path):
    return os.path.abspath(path).replace("\\", "/")


def _force_to_grade(mean_force):
    if mean_force is None:
        return "A"
    value = float(mean_force or 0)
    if value < 5:
        return "A"
    if value < 10:
        return "B"
    if value < 15:
        return "C"
    return "D"


def _customer_grade_label(grade):
    return {
        "A": "Mild",
        "B": "Moderate",
        "C": "Higher",
        "D": "Severe",
    }.get(str(grade).upper(), "Mild")


def _customer_status_text(level):
    return {
        "normal": "正常",
        "attention": "需关注",
        "high": "高关注",
        "low": "偏轻",
        "medium": "适中",
    }.get(str(level or "").lower(), "正常")


def _customer_section_rows(stats):
    section_map = _section_map(stats)
    rows = []
    for section in SECTION_ORDER:
        item = dict(section_map.get(section, {}))
        grade = item.get("grade") or _force_to_grade(item.get("mean_force_N"))
        label = item.get("label") or _customer_grade_label(grade)
        rows.append({
            "section": section,
            "section_cn": SECTION_CN.get(section, section),
            "grade": grade,
            "label": label,
            "to_do": item.get("to_do") or SECTION_TODO.get(section, "Care"),
            "contact_count": int(item.get("contact_count") or item.get("sample_count") or 0),
            "duration_s": float(item.get("duration_s") or 0),
            "mean_force_N": item.get("mean_force_N"),
            "max_force_N": item.get("max_force_N"),
            "main_acupoints": item.get("main_acupoints") or [],
        })
    return rows


def create_spine_summary_chart(data, output_path):
    """Create a clean customer-facing spine summary chart."""
    rows = data if isinstance(data, list) else _customer_section_rows(data)
    grade_colors = {"A": "#FFFFFF", "B": COLOR_GREEN, "C": COLOR_YELLOW, "D": COLOR_RED}
    img = Image.new("RGB", (720, 520), "white")
    draw = ImageDraw.Draw(img)
    title_font = _font(30)
    body_font = _font(22)
    small_font = _font(18)
    draw.text((42, 30), "Back Section Overview", font=title_font, fill=COLOR_NAVY)
    draw.line((42, 76, 678, 76), fill=COLOR_LINE, width=2)
    spine_x = 255
    draw.line((spine_x, 120, spine_x, 430), fill=COLOR_NAVY, width=8)
    for y in range(125, 431, 34):
        draw.ellipse((spine_x - 11, y - 11, spine_x + 11, y + 11), fill="white", outline=COLOR_NAVY, width=3)
    section_slots = {
        "Upper Back": (118, 205),
        "Mid Back": (215, 315),
        "Lower Back": (325, 425),
    }
    for row in rows:
        section = row["section"]
        y0, y1 = section_slots.get(section, (120, 200))
        color = grade_colors.get(row["grade"], "#FFFFFF")
        draw.rounded_rectangle((398, y0, 642, y1), radius=18, fill=color, outline=COLOR_LINE, width=2)
        text_color = "white" if row["grade"] in ("B", "D") else COLOR_NAVY
        draw.text((420, y0 + 19), f"{section}", font=body_font, fill=text_color)
        draw.text((420, y0 + 51), f"{SECTION_CN.get(section, '')}  {row['grade']} · {row['label']}", font=small_font, fill=text_color)
        draw.line((spine_x + 18, (y0 + y1) // 2, 398, (y0 + y1) // 2), fill=COLOR_LINE, width=3)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path)
    return output_path


def _alignment_plot_paths(raw, user_id):
    plot_paths = raw.get("plot_paths", {}) if isinstance(raw, dict) else {}
    return {
        "xy": plot_paths.get("xy") or os.path.join(OUTPUT_DIR, f"{user_id}_trajectory_acupoints_xy.png"),
        "3d": plot_paths.get("3d") or os.path.join(OUTPUT_DIR, f"{user_id}_trajectory_acupoints_3d.png"),
    }


def _customer_section_summary(row):
    points = "、".join(row.get("main_acupoints") or []) or "主要接触点"
    mean_force = "--" if row.get("mean_force_N") is None else f"{float(row.get('mean_force_N')):.2f}"
    max_force = "--" if row.get("max_force_N") is None else f"{float(row.get('max_force_N')):.2f}"
    if row["section"] == "Upper Back":
        return f"本次上背部按摩覆盖了 {points} 等区域，平均按压力为 {mean_force} N，整体处于 {row['label']} 水平。建议关注肩胛带周围放松与胸椎伸展。"
    if row["section"] == "Mid Back":
        return f"本次中背部按摩主要作用于 {points} 等区域，平均按压力为 {mean_force} N。若该区域接触时长较长或最大力度偏高，建议后续降低初始力度并采用渐进加力策略。"
    return f"本次下背部按摩接触时长为 {row.get('duration_s', 0):.2f} s，最大按压力为 {max_force} N。下背部通常对姿势负荷较敏感，建议后续重点进行腰背放松与柔韧性维护，同时避免靠近脊柱中线强按。"


def _safety_recommendations(stats):
    raw = stats.get("_alignment_raw") or {}
    overall = raw.get("overall", stats.get("overall", {}))
    max_force = float(overall.get("max_contact_force_N") or overall.get("max_force_N") or 0)
    high_force_count = 0
    for record in raw.get("aligned_records", []) or stats.get("records", []):
        try:
            if float(record.get("force_N") or record.get("force") or 0) >= 15:
                high_force_count += 1
        except (TypeError, ValueError):
            pass
    high_points = [
        item for item in raw.get("by_acupoint", [])
        if str(item.get("attention_level", "")).lower() == "high" or float(item.get("max_force_N") or 0) >= 15
    ]
    high_risk = any(
        "spine_center" in str(item.get("section", "")).lower()
        or "spine_center" in str(item.get("region", "")).lower()
        or "high risk" in str(item.get("region", "")).lower()
        for item in (raw.get("by_acupoint", []) + raw.get("by_region", []))
    )
    focus = [row["section_cn"] for row in _customer_section_rows(stats) if row["grade"] in ("C", "D")]
    maintain = [row["section_cn"] for row in _customer_section_rows(stats) if row["grade"] in ("A", "B")]
    return {
        "mean_force": overall.get("mean_contact_force_N") or overall.get("mean_force_N"),
        "max_force": max_force,
        "high_force_count": high_force_count,
        "high_point_count": len(high_points),
        "force_text": (
            "本次存在局部较高力度接触，建议下次在相关区域降低初始力度并采用渐进加力。"
            if max_force >= 15 else
            "本次未检测到持续高力度按压，整体力度处于较保守范围。"
        ),
        "risk_text": (
            "检测到靠近脊柱中线或高风险区域的接触，建议后续路径规划中增加避让距离。"
            if high_risk else
            "本次未检测到明显靠近脊柱中线的高风险接触。"
        ),
        "focus": "、".join(focus) if focus else "暂无明显高关注区域",
        "maintain": "、".join(maintain) if maintain else "暂无维持区域",
    }


def create_customer_report_html(stats, user_id, output_path, logo_path=None, report_id=None):
    """Create a customer-readable smart massage report for browser and PDF output."""
    raw = stats.get("_alignment_raw") or {}
    has_alignment = stats.get("source") == "spatial_temporal_alignment"
    overall = raw.get("overall", stats.get("overall", {}))
    sections = _customer_section_rows(stats)
    report_id = report_id or f"DEMO-{datetime.now().year}-001"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    spine_path = os.path.join(OUTPUT_DIR, f"{user_id}_spine_summary.png")
    create_spine_summary_chart(sections, spine_path)
    plots = _alignment_plot_paths(raw, user_id)
    logo_html = (
        f'<img class="logo-img" src="file:///{_file_url(logo_path)}" alt="logo" />'
        if logo_path and os.path.isfile(logo_path)
        else '<div class="logo-text">LSCURE</div>'
    )
    qr_path = os.path.join(OUTPUT_DIR, f"{user_id}_report_qr.png")
    _create_qr(f"LSCURE report {user_id} {report_id}", qr_path)
    qr_html = f'<img class="qr" src="file:///{_file_url(qr_path)}" alt="report qr" />'

    def esc(value):
        return escape(str(value if value is not None else ""))

    def num(value, digits=2):
        if value is None:
            return "--"
        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return "--"

    section_rows = "".join(
        f"<tr><td>{esc(row['section'])}</td><td><span class='grade grade-{row['grade']}'>{row['grade']}</span></td><td>{esc(row['label'])}</td><td>{esc(row['to_do'])}</td></tr>"
        for row in sections
    )
    legend = "".join(
        f"<span class='legend-item legend-{grade}'>{grade} {label}</span>"
        for grade, label in [("A", "Mild"), ("B", "Moderate"), ("C", "Higher"), ("D", "Severe")]
    )
    grade_rank = {"A": 1, "B": 2, "C": 3, "D": 4}
    overall_row = max(sections, key=lambda row: grade_rank.get(row["grade"], 1))
    overall_grade = overall_row["grade"]
    overall_label_cn = {"A": "轻度紧张", "B": "中度紧张", "C": "偏高紧张", "D": "高关注"}.get(overall_grade, "中度紧张")
    focus_row = max(sections, key=lambda row: (grade_rank.get(row["grade"], 1), row.get("duration_s") or 0, row.get("max_force_N") or 0))
    overview_cards = [
        ("总体等级", overall_grade, overall_label_cn, "status"),
        ("平均按压力", f"{num(overall.get('mean_contact_force_N') or overall.get('mean_force_N'))} N", "本次有效接触平均值", "force"),
        ("有效接触时长", f"{num(overall.get('contact_duration_s'))} s", "基于轨迹与穴位距离判断", "time"),
        ("重点关注区域", focus_row["section"], focus_row["section_cn"], "focus"),
    ]
    overview_html = "".join(
        f"<div class='overview-card'><i class='icon-dot icon-{kind}'></i><span>{esc(title)}</span><strong>{esc(value)}</strong><p>{esc(subtitle)}</p></div>"
        for title, value, subtitle, kind in overview_cards
    )
    metric_cards = [
        ("总采样点数", overall.get("total_samples", "--")),
        ("有效接触点", overall.get("contact_samples", "--")),
        ("有效接触比例", f"{float(overall.get('contact_ratio') or 0) * 100:.0f}%"),
        ("总按摩时长", f"{num(overall.get('total_duration_s'))} s"),
        ("有效接触时长", f"{num(overall.get('contact_duration_s'))} s"),
        ("平均按压力", f"{num(overall.get('mean_contact_force_N') or overall.get('mean_force_N'))} N"),
        ("最大按压力", f"{num(overall.get('max_contact_force_N') or overall.get('max_force_N'))} N"),
    ]
    metric_html = "".join(f"<div class='metric-card'><span>{esc(k)}</span><strong>{esc(v)}</strong></div>" for k, v in metric_cards)
    top_points = sorted(raw.get("by_acupoint", []), key=lambda p: (p.get("contact_count") or 0, p.get("duration_s") or 0), reverse=True)[:5]
    top1_point = top_points[0].get("name") if top_points else "暂无"
    point_rows = "".join(
        f"<tr><td>{esc(p.get('name'))}</td><td>{esc(p.get('section'))}</td><td>{num(p.get('duration_s'))} s</td><td>{num(p.get('mean_force_N'))} N</td><td>{num(p.get('max_force_N'))} N</td><td><span class='status status-{esc(p.get('attention_level') or 'normal')}'>{_customer_status_text(p.get('attention_level'))}</span></td></tr>"
        for p in top_points
    ) or "<tr><td colspan='6'>暂无穴位对齐数据</td></tr>"
    plot_html = ""
    existing_plots = [path for path in [plots["xy"], plots["3d"]] if os.path.isfile(path)]
    if existing_plots:
        plot_html = "".join(f"<img src='file:///{_file_url(path)}' alt='trajectory plot' />" for path in existing_plots)
    else:
        plot_html = "<div class='empty-plot'>未检测到轨迹可视化图，请先运行空间时间对齐模块。</div>"

    section_pages = ""
    for row in sections:
        point_names = "、".join(row.get("main_acupoints") or []) or "暂无主要穴位统计"
        stat_cards = [
            ("本区接触时长", f"{row['duration_s']:.2f} s"),
            ("平均力度", f"{num(row.get('mean_force_N'))} N"),
            ("最大力度", f"{num(row.get('max_force_N'))} N"),
            ("主要按摩穴位", point_names),
            ("状态等级", f"{row['grade']} · {row['label']}"),
        ]
        acupoint_rows = "".join(f"<tr><td>{code}</td><td>{name}</td><td>{muscle}</td></tr>" for code, name, muscle in ACUPOINTS[row["section"]])
        stat_html = "".join(f"<div class='metric-card'><span>{esc(k)}</span><strong>{esc(v)}</strong></div>" for k, v in stat_cards)
        rec_html = "".join(f"<li>{esc(item)}</li>" for item in RECOMMENDATIONS.get(row["section"], []))
        mean_force = float(row.get("mean_force_N") or 0)
        marker_pct = max(2, min(98, mean_force / 20 * 100))
        section_pages += f"""
        <section class="report-page">
          <header class="page-head"><div>{logo_html}</div><span>背部智能按摩评估报告</span></header>
          <div class="section-title-row">
            <h2>{esc(row['section'])} / {esc(row['section_cn'])}分析</h2>
            <span class="big-grade grade-{row['grade']}">{esc(row['grade'])} <em>{esc(row['label'])}</em></span>
          </div>
          <div class="section-layout">
            <div class="panel">
              <h3>穴位参考</h3>
              <table><thead><tr><th>Label</th><th>Acupoint Name</th><th>Muscle / Region</th></tr></thead><tbody>{acupoint_rows}</tbody></table>
            </div>
            <div class="panel">
              <h3>分区统计</h3>
              <div class="metric-grid section-metrics">{stat_html}</div>
            </div>
          </div>
          <div class="panel force-panel">
            <h3>力度区间</h3>
            <div class="force-scale"><span>Low</span><span>Medium</span><span>High</span><i style="left:{marker_pct}%"></i></div>
            <p>当前平均按压力：{num(row.get('mean_force_N'))} N。建议从舒适力度开始，根据反馈逐步调整。</p>
          </div>
          <div class="two-card">
            <div class="panel summary-card"><h3>Summary</h3><p class="analysis">{esc(_customer_section_summary(row))}</p></div>
            <div class="panel summary-card"><h3>Recommendation</h3><ul class="rec-list">{rec_html}</ul></div>
          </div>
          <footer>本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。<b></b></footer>
        </section>
        """

    safety = _safety_recommendations(stats)
    alignment_page = ""
    if has_alignment:
        alignment_metric_cards = [
            ("总采样点数", overall.get("total_samples", "--")),
            ("有效接触比例", f"{float(overall.get('contact_ratio') or 0) * 100:.0f}%"),
            ("平均按压力", f"{num(overall.get('mean_contact_force_N') or overall.get('mean_force_N'))} N"),
            ("最大按压力", f"{num(overall.get('max_contact_force_N') or overall.get('max_force_N'))} N"),
            ("TOP 1 穴位", top1_point),
        ]
        alignment_metric_html = "".join(
            f"<div class='metric-card'><span>{esc(k)}</span><strong>{esc(v)}</strong></div>"
            for k, v in alignment_metric_cards
        )
        alignment_page = f"""
        <section class="report-page">
          <header class="page-head"><div>{logo_html}</div><span>背部智能按摩评估报告</span></header>
          <h2>机械臂按摩轨迹与穴位对齐</h2>
          <p class="lead">该图展示机械臂 TCP 轨迹与穴位 3D 点云坐标的空间匹配关系，用于判断每个时刻按摩探头作用的位置。</p>
          <div class="plot-frame">{plot_html}</div>
          <div class="metric-grid alignment-metrics">{alignment_metric_html}</div>
          <h3>TOP 5 主要按摩穴位</h3>
          <div class="table-card"><table><thead><tr><th>穴位</th><th>分区</th><th>接触时长</th><th>平均力度</th><th>最大力度</th><th>状态</th></tr></thead><tbody>{point_rows}</tbody></table></div>
          <footer>本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。<b></b></footer>
        </section>
        """

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>背部智能按摩评估报告 - {esc(user_id)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin:0; background:white; color:{COLOR_TEXT}; font-family:"Microsoft YaHei","Segoe UI",Arial,sans-serif; counter-reset:page; }}
    .report-page {{ position:relative; width:210mm; min-height:297mm; margin:0 auto 18px; padding:16mm 15mm 18mm; background:white; page-break-after:always; counter-increment:page; overflow:hidden; }}
    .page-head,.cover-head {{ display:grid; grid-template-columns:112px 1fr 70px; align-items:center; border-bottom:1px solid {COLOR_LINE}; padding-bottom:12px; margin-bottom:18px; color:{COLOR_NAVY}; font-weight:800; }}
    .page-head span {{ text-align:right; font-size:12px; color:{COLOR_MUTED}; }}
    .cover-title {{ text-align:center; }}
    .logo-text {{ width:84px; height:30px; border-radius:8px; display:grid; place-items:center; color:white; background:{COLOR_TEAL}; font-weight:900; letter-spacing:0; font-size:13px; }}
    .logo-img {{ max-width:102px; max-height:38px; object-fit:contain; }}
    .qr {{ width:58px; height:58px; justify-self:end; border:1px solid {COLOR_LINE}; border-radius:8px; padding:4px; }}
    h1 {{ color:{COLOR_NAVY}; font-size:28px; margin:0 0 4px; letter-spacing:0; }}
    h2 {{ color:{COLOR_NAVY}; font-size:21px; margin:6px 0 14px; letter-spacing:0; }}
    h3 {{ color:{COLOR_NAVY}; font-size:13px; margin:0 0 10px; }}
    .subtitle {{ color:{COLOR_TEAL}; font-size:13px; font-weight:700; }}
    .info-line {{ display:flex; justify-content:center; gap:18px; flex-wrap:wrap; color:{COLOR_MUTED}; font-size:11px; margin:10px 0 18px; }}
    .overview-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-bottom:14px; }}
    .overview-card {{ min-height:82px; border:1px solid {COLOR_LINE}; border-radius:12px; background:{CARD_BG}; padding:12px 12px 10px; }}
    .overview-card span {{ display:block; margin-top:8px; color:{COLOR_MUTED}; font-size:10.5px; }}
    .overview-card strong {{ display:block; color:{COLOR_NAVY}; font-size:21px; line-height:1.15; margin-top:4px; }}
    .overview-card p {{ margin:4px 0 0; color:{COLOR_MUTED}; font-size:10px; line-height:1.35; }}
    .icon-dot {{ display:block; width:10px; height:10px; border-radius:99px; background:{COLOR_TEAL}; }}
    .icon-focus {{ background:{COLOR_RED}; }} .icon-force {{ background:{COLOR_GREEN}; }} .icon-time {{ background:{COLOR_YELLOW}; }}
    .cover-grid {{ display:grid; grid-template-columns:1.08fr .92fr; gap:14px; align-items:start; }}
    .panel,.table-card {{ border:1px solid {COLOR_LINE}; border-radius:12px; padding:14px; background:white; }}
    table {{ width:100%; border-collapse:separate; border-spacing:0; font-size:11px; overflow:hidden; }}
    th,td {{ border-bottom:1px solid {COLOR_LINE}; padding:9px 9px; text-align:left; vertical-align:middle; }}
    th {{ color:white; background:{COLOR_TEAL}; font-weight:800; }}
    tr:last-child td {{ border-bottom:0; }}
    .grade {{ display:inline-grid; place-items:center; width:28px; height:28px; border-radius:50%; font-weight:900; border:1px solid {COLOR_LINE}; }}
    .grade-A {{ background:#fff; color:{COLOR_NAVY}; }} .grade-B {{ background:{COLOR_GREEN}; color:white; }} .grade-C {{ background:{COLOR_YELLOW}; color:{COLOR_NAVY}; }} .grade-D {{ background:{COLOR_RED}; color:white; }}
    .spine-chart {{ width:100%; border:1px solid {COLOR_LINE}; border-radius:12px; padding:10px; }}
    .chart-note {{ margin-top:8px; color:{COLOR_MUTED}; font-size:10px; text-align:center; }}
    .legend {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:14px; }}
    .legend-item {{ border-radius:8px; padding:8px 10px; font-size:12px; font-weight:800; border:1px solid {COLOR_LINE}; }}
    .legend-A {{ background:#fff; color:{COLOR_NAVY}; }} .legend-B {{ background:{COLOR_GREEN}; color:white; }} .legend-C {{ background:{COLOR_YELLOW}; color:{COLOR_NAVY}; }} .legend-D {{ background:{COLOR_RED}; color:white; }}
    .lead,.analysis {{ color:#455A64; line-height:1.65; font-size:11.2px; margin:0 0 12px; }}
    .analysis-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:14px; }}
    .analysis-card {{ border:1px solid {COLOR_LINE}; border-radius:12px; background:{CARD_BG}; padding:13px; min-height:112px; }}
    .analysis-card i {{ display:grid; place-items:center; width:24px; height:24px; border-radius:50%; background:{ACCENT_LIGHT}; color:{COLOR_TEAL}; font-style:normal; font-weight:900; margin-bottom:9px; }}
    .analysis-card p {{ margin:0; color:#455A64; font-size:10.5px; line-height:1.62; }}
    .metric-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:14px 0 16px; }}
    .section-metrics {{ grid-template-columns:1fr; margin:0; }}
    .metric-card {{ min-height:66px; border:1px solid {COLOR_LINE}; border-radius:12px; padding:11px; background:#FBFDFE; }}
    .metric-card span {{ display:block; color:{COLOR_MUTED}; font-size:11px; margin-bottom:8px; }}
    .metric-card strong {{ color:{COLOR_NAVY}; font-size:16px; line-height:1.35; }}
    .plot-frame {{ border:1px solid {COLOR_LINE}; border-radius:14px; background:{CARD_BG}; padding:14px; text-align:center; margin-bottom:12px; }}
    .plot-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }}
    .plot-frame img {{ max-width:48%; margin:0 1%; border:1px solid {COLOR_LINE}; border-radius:10px; background:white; vertical-align:middle; }}
    .empty-plot {{ grid-column:1 / -1; border:1px dashed {COLOR_LINE}; border-radius:10px; padding:36px; color:{COLOR_MUTED}; text-align:center; }}
    .status {{ display:inline-block; border-radius:999px; padding:4px 8px; font-size:10px; font-weight:800; background:{COLOR_GREEN}; color:white; }}
    .status-attention {{ background:{COLOR_ORANGE}; }} .status-high {{ background:{COLOR_RED}; }}
    .section-title-row {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }}
    .big-grade {{ display:inline-flex; align-items:center; gap:8px; border-radius:999px; padding:8px 12px; font-weight:900; }}
    .big-grade em {{ font-style:normal; font-size:11px; font-weight:700; }}
    .section-layout {{ display:grid; grid-template-columns:1.08fr .92fr; gap:12px; align-items:start; }}
    .force-panel {{ margin-top:12px; }}
    .force-scale {{ position:relative; display:grid; grid-template-columns:repeat(3,1fr); height:30px; border-radius:999px; overflow:visible; background:linear-gradient(90deg,{COLOR_GREEN},{COLOR_YELLOW},{COLOR_RED}); color:white; font-size:10px; font-weight:800; align-items:center; text-align:center; margin:8px 5px 10px; }}
    .force-scale i {{ position:absolute; top:-4px; width:10px; height:38px; border-radius:6px; background:{COLOR_NAVY}; transform:translateX(-50%); box-shadow:0 0 0 3px white; }}
    .force-panel p {{ margin:0; color:{COLOR_MUTED}; font-size:10.5px; }}
    .two-card {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:12px; }}
    .summary-card {{ min-height:128px; }}
    .rec-list {{ margin:0; padding-left:0; list-style:none; color:#455A64; line-height:1.9; font-size:11px; }}
    .rec-list li::before {{ content:"✓"; color:{COLOR_TEAL}; font-weight:900; margin-right:8px; }}
    .safety-overview,.next-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:14px 0; }}
    .safety-note {{ border-radius:12px; border:1px solid {COLOR_LINE}; padding:14px; background:#FBFDFE; margin:10px 0; color:#455A64; line-height:1.7; font-size:11.5px; }}
    .safety-note.ok {{ border-color:{COLOR_GREEN}; background:#F1FAF4; }}
    .safety-note.warn {{ border-color:{COLOR_ORANGE}; background:#FFF7ED; }}
    .next-card {{ border:1px solid {COLOR_LINE}; border-radius:12px; padding:13px; background:{CARD_BG}; min-height:90px; }}
    .next-card span {{ display:block; color:{COLOR_MUTED}; font-size:10.5px; margin-bottom:9px; }}
    .next-card strong {{ color:{COLOR_NAVY}; font-size:13px; line-height:1.45; }}
    footer {{ position:absolute; left:18mm; right:18mm; bottom:10mm; border-top:1px solid {COLOR_LINE}; padding-top:8px; color:#78909C; font-size:10px; display:flex; justify-content:space-between; }}
    footer b::after {{ content:"Page " counter(page); font-weight:700; color:{COLOR_NAVY}; }}
    @page {{ size:A4; margin:0; }}
    @media print {{ body {{ background:white; }} .report-page {{ margin:0; }} }}
  </style>
</head>
<body>
  <section class="report-page">
    <header class="cover-head">
      <div>{logo_html}</div>
      <div class="cover-title">
        <h1>背部智能按摩评估报告</h1>
        <div class="subtitle">Smart Back Massage Assessment Report</div>
      </div>
      {qr_html}
    </header>
    <div class="info-line"><span>报告编号：{esc(report_id)}</span><span>用户编号：{esc(user_id)}</span><span>生成时间：{esc(created_at)}</span></div>
    <div class="overview-grid">{overview_html}</div>
    <div class="cover-grid">
      <div class="panel">
        <h3>Section Summary</h3>
        <table><thead><tr><th>Section</th><th>Grade</th><th>Label</th><th>To Do</th></tr></thead><tbody>{section_rows}</tbody></table>
        <div class="legend">{legend}</div>
      </div>
      <div>
        <img class="spine-chart" src="file:///{_file_url(spine_path)}" alt="spine summary" />
        <p class="chart-note">颜色表示本次按摩数据中各区域的关注等级。</p>
      </div>
    </div>
    <div class="analysis-grid">
      <div class="analysis-card"><i>1</i><h3>区域识别与时空对齐</h3><p>系统基于统一相机坐标系下的机械臂 TCP 轨迹、穴位 3D 点云坐标与实时按压力数据，判断每个采样时刻对应的按摩位置。</p></div>
      <div class="analysis-card"><i>2</i><h3>按摩覆盖与力度分析</h3><p>报告统计各穴位和背部区域的接触次数、接触时长、平均力度与最大力度，用于评估本次按摩覆盖范围和力度稳定性。</p></div>
      <div class="analysis-card"><i>3</i><h3>安全力度与后续建议</h3><p>系统根据区域风险、接触距离和按压力水平生成安全提示，辅助规划下一次按摩重点区域、推荐力度和避让区域。</p></div>
    </div>
    <footer>本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。<b></b></footer>
  </section>
  {alignment_page}
  {section_pages}
  <section class="report-page">
    <header class="page-head"><div>{logo_html}</div><span>背部智能按摩评估报告</span></header>
    <h2>安全力度与下次按摩建议</h2>
    <div class="safety-overview">
      <div class="metric-card"><span>最大按压力</span><strong>{num(safety['max_force'])} N</strong></div>
      <div class="metric-card"><span>是否出现高力度接触</span><strong>{'是' if safety['high_force_count'] else '否'}</strong></div>
      <div class="metric-card"><span>是否靠近脊柱中线</span><strong>{'需避让' if '靠近脊柱中线' in safety['risk_text'] else '未见明显风险'}</strong></div>
      <div class="metric-card"><span>整体安全评价</span><strong>{'建议渐进加力' if safety['max_force'] >= 15 else '力度较保守'}</strong></div>
    </div>
    <div class="safety-note {'warn' if safety['max_force'] >= 15 else 'ok'}">{esc(safety['force_text'])}</div>
    <div class="safety-note">{esc(safety['risk_text'])}</div>
    <h3>下次按摩建议</h3>
    <div class="next-grid">
      <div class="next-card"><span>建议优先关注区域</span><strong>{esc(safety['focus'])}</strong></div>
      <div class="next-card"><span>建议起始力度范围</span><strong>低力度起步，逐步增加</strong></div>
      <div class="next-card"><span>建议避让区域</span><strong>脊柱中线及未知区域</strong></div>
      <div class="next-card"><span>建议护理动作</span><strong>拉伸、放松、稳定训练</strong></div>
    </div>
    <footer>本报告为项目演示生成，仅用于研究与功能展示，不构成医疗建议。<b></b></footer>
  </section>
</body>
</html>
"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def create_browser_report_html(stats, user_id, output_path):
    """Create the browser-first massage detection report HTML."""
    detection = stats.get("_detection_report") or {}
    raw = stats.get("_alignment_raw") or {}
    user = detection.get("user", {})
    overall = raw.get("overall", {})
    params = raw.get("parameters", {})
    top_regions = detection.get("topRegions", [])
    top_points = raw.get("by_acupoint", [])[:8]
    def esc_html(value):
        return escape(str(value if value is not None else ""))

    def num(value, digits=2):
        if value is None:
            return "--"
        try:
            return f"{float(value):.{digits}f}"
        except (TypeError, ValueError):
            return "--"

    def force_text(level):
        return {"low": "偏轻", "medium": "适中", "high": "偏高"}.get(level, "未知")

    def section_card(region):
        profiles = "".join(
            f"""
            <div class="profile-row">
              <span>{esc_html(item.get('name'))}</span>
              <div class="bar"><i style="width:{min(100, max(0, float(item.get('score', 0))))}%"></i></div>
              <b class="badge badge-{esc_html(item.get('grade'))}">{esc_html(item.get('grade'))}</b>
            </div>
            """
            for item in region.get("fiveDimensionalProfile", [])
        )
        chips = "".join(f"<em>{esc_html(name)}</em>" for name in region.get("main_acupoints", [])[:5])
        safe_range = region.get("safe_force_range_N") or [None, None]
        return f"""
        <section class="card region-card">
          <div class="rank rank-{region.get('rank')}">{region.get('rank')}</div>
          <div class="region-head">
            <div>
              <h3>{esc_html(region.get('nameCN'))}</h3>
              <p>{esc_html(region.get('nameEN'))}</p>
            </div>
            <div class="score">
              <span>综合</span><strong>{esc_html(region.get('totalScore'))}</strong><b class="badge badge-{esc_html(region.get('grade'))}">{esc_html(region.get('grade'))}</b>
            </div>
          </div>
          <div class="subgrid">
            <div><span>肌肉</span><b>{region.get('subScores', {}).get('muscle', '--')}</b></div>
            <div><span>穴位</span><b>{region.get('subScores', {}).get('acupoint', '--')}</b></div>
            <div><span>脊柱</span><b>{region.get('subScores', {}).get('spine', '--')}</b></div>
            <div><span>循环</span><b>{region.get('subScores', {}).get('circulation', '--')}</b></div>
          </div>
          <div class="recommend">
            <div><span>推荐力度</span><strong>{num(region.get('recommended_force_N'))} N</strong></div>
            <p>安全范围 {num(safe_range[0])}-{num(safe_range[1])} N · 平均力 {num(region.get('mean_force_N'))} N · 最大力 {num(region.get('max_force_N'))} N</p>
          </div>
          <div class="chips">{chips}</div>
          <div class="profile">
            <h4>五维画像</h4>
            {profiles}
          </div>
          <p class="suggestion">{esc_html(region.get('suggestion'))}</p>
        </section>
        """

    point_rows = "".join(
        f"""
        <tr>
          <td>{idx}</td>
          <td>{esc_html(point.get('name'))}</td>
          <td>{esc_html(point.get('section'))}</td>
          <td>{point.get('contact_count', 0)}</td>
          <td>{num(point.get('mean_force_N'))} N</td>
          <td>{num(point.get('recommended_force_N'))} N</td>
          <td>{force_text(point.get('force_level'))}</td>
        </tr>
        """
        for idx, point in enumerate(top_points, start=1)
    )
    cards = "".join(section_card(region) for region in top_regions)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>智能按摩检测报告 - {esc_html(user_id)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f3f7f8; color: #263238; font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", Arial, sans-serif; }}
    .page {{ width: min(100%, 920px); margin: 0 auto; padding: 28px 30px 44px; }}
    .hero {{ border: 1px solid #d7e3ea; border-top: 4px solid #008c95; border-radius: 14px; background: white; padding: 22px 24px; box-shadow: 0 8px 24px rgba(11, 42, 74, .055); }}
    .hero-grid {{ display: grid; grid-template-columns: auto 1fr auto; gap: 16px; align-items: center; }}
    .avatar {{ display: grid; place-items: center; width: 66px; height: 66px; border-radius: 16px; background: #008c95; color: white; font-size: 28px; font-weight: 900; }}
    h1,h2,h3,h4,p {{ margin: 0; }}
    h1 {{ font-size: 26px; color:#0b2a4a; line-height:1.25; letter-spacing: 0; font-weight: 900; }}
    .muted {{ color: #6b7c85; font-size: 14px; margin-top: 5px; }}
    .grade-pill {{ border-radius: 999px; background: #e6f7f8; color: #007f86; border:1px solid #cfe9ec; padding: 8px 14px; font-size: 16px; font-weight: 900; }}
    .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 18px; }}
    .stat {{ border-radius: 12px; background: #f7fafc; padding: 13px 14px; border: 1px solid #e3edf2; }}
    .stat span {{ display:block; color:#71828a; font-size: 11px; font-weight:700; }}
    .stat b {{ display:block; margin-top:5px; font-size: 19px; line-height:1.2; color:#0b2a4a; }}
    .section-title {{ display:flex; align-items:center; gap:10px; margin: 26px 2px 12px; }}
    .section-title h2 {{ font-size: 21px; color:#0b2a4a; letter-spacing:0; }}
    .tag {{ background:#e6f7f8; color:#008c95; border-radius:999px; padding:5px 11px; font-weight:900; font-size: 12px; }}
    .card {{ position: relative; border: 1px solid #d7e3ea; border-top: 4px solid #008c95; border-radius: 14px; background: white; padding: 20px 22px; margin: 12px 0; box-shadow: 0 8px 24px rgba(11, 42, 74, .05); break-inside: avoid; }}
    .rank {{ position:absolute; left:22px; top:23px; display:grid; place-items:center; width:46px; height:46px; border-radius:12px; color:white; font-size:20px; font-weight:900; background:#008c95; }}
    .rank-1 {{ background:#d94a4a; }} .rank-2 {{ background:#e08a22; }}
    .region-head {{ display:flex; justify-content:space-between; align-items:center; padding-left:74px; }}
    .region-head h3 {{ font-size: 23px; color:#0b2a4a; }}
    .region-head p {{ color:#71828a; font-size:13px; margin-top:3px; }}
    .score {{ display:flex; align-items:center; gap:9px; color:#71828a; font-size:13px; font-weight:800; }}
    .score strong {{ color:#d94a4a; font-size:28px; }}
    .badge {{ display:inline-grid; place-items:center; min-width:36px; height:36px; border-radius:10px; color:white; font-size:17px; font-weight:900; }}
    .badge-A {{ background:#34a853; }} .badge-B {{ background:#008c95; }} .badge-C {{ background:#d94a4a; }} .badge-D {{ background:#8a3a1a; }}
    .subgrid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-top:20px; border-radius:12px; background:#fff6f6; padding:14px; text-align:center; }}
    .subgrid span {{ color:#71828a; font-size:12px; }} .subgrid b {{ display:block; margin-top:5px; font-size:20px; color:#0b2a4a; }}
    .recommend {{ margin-top:14px; border-radius:12px; background:#f7fafc; padding:14px; border:1px solid #e3edf2; }}
    .recommend div {{ display:flex; justify-content:space-between; font-weight:900; }}
    .recommend strong {{ color:#008c95; }}
    .recommend p {{ margin-top:7px; color:#6b7c85; font-size:13px; line-height:1.55; }}
    .chips {{ display:flex; flex-wrap:wrap; gap:7px; margin-top:14px; }}
    .chips em {{ font-style:normal; border-radius:999px; background:#edfafa; color:#0f6670; padding:6px 11px; font-size:12px; font-weight:800; }}
    .profile {{ margin-top:16px; }}
    .profile h4 {{ font-size:17px; margin-bottom:9px; color:#0b2a4a; }}
    .profile-row {{ display:grid; grid-template-columns:54px 1fr 44px; gap:10px; align-items:center; margin:7px 0; color:#6b7c85; font-size:13px; }}
    .bar {{ height:10px; border-radius:999px; background:#edf2f7; overflow:hidden; }}
    .bar i {{ display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,#ef6b6b,#8a3a1a); }}
    .suggestion {{ margin-top:13px; color:#41525a; line-height:1.68; font-size:13px; }}
    table {{ width:100%; border-collapse: collapse; background:white; border-radius:12px; overflow:hidden; }}
    th,td {{ padding:10px 11px; border-bottom:1px solid #e3edf2; text-align:left; font-size:13px; line-height:1.45; }}
    th {{ background:#f2f8f9; color:#0b2a4a; font-weight:900; }}
    .note {{ margin-top:14px; color:#6b7c85; line-height:1.65; font-size:12px; }}
    @media print {{
      body {{ background:white; }}
      .page {{ width: 100%; padding: 18mm; }}
      .card,.hero {{ box-shadow:none; border:1px solid #e2e8f0; border-top:5px solid #18b7bd; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="hero-grid">
        <div class="avatar">{esc_html(user.get('surname', '张'))}</div>
        <div>
          <h1>智能按摩检测报告</h1>
          <p class="muted">{esc_html(user.get('name', user_id))} · {esc_html(user.get('phone', ''))} · {esc_html(user.get('gender', ''))} {esc_html(user.get('age', ''))}岁</p>
        </div>
        <div class="grade-pill">健康等级 {esc_html(user.get('healthGrade', '--'))}</div>
      </div>
      <div class="stats">
        <div class="stat"><span>总采样点</span><b>{overall.get('total_samples', 0)}</b></div>
        <div class="stat"><span>有效接触点</span><b>{overall.get('contact_samples', 0)}</b></div>
        <div class="stat"><span>接触占比</span><b>{round(float(overall.get('contact_ratio', 0))*100)}%</b></div>
        <div class="stat"><span>平均接触力</span><b>{num(overall.get('mean_contact_force_N'))} N</b></div>
      </div>
    </section>
    <div class="section-title"><h2>身体重点部位分析</h2><span class="tag">TOP 3</span></div>
    {cards}
    <section class="card">
      <h2>高频接触穴位与推荐力度</h2>
      <table>
        <thead><tr><th>#</th><th>穴位</th><th>分区</th><th>接触数</th><th>平均力</th><th>推荐力</th><th>力度状态</th></tr></thead>
        <tbody>{point_rows}</tbody>
      </table>
    </section>
    <section class="card">
      <h2>检测说明</h2>
      <p class="note">采样率 {params.get('sample_rate_hz', '--')} Hz，接触阈值 {params.get('contact_threshold_mm', '--')} mm。当前输入不含 indentation_mm，僵硬程度为基于按压力、停留时长、穴位密度与对齐质量的检测评分；如后续输入压入深度，可切换为物理刚度 N/m。</p>
    </section>
  </main>
</body>
</html>
"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def convert_html_to_pdf_with_browser(html_path, pdf_path):
    """Print HTML to PDF using an installed Chromium browser."""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    browser = next((path for path in candidates if os.path.isfile(path)), None)
    if not browser:
        return False
    if os.path.isfile(pdf_path):
        try:
            os.remove(pdf_path)
        except OSError:
            pass
    html_url = "file:///" + _file_url(html_path)
    cmd = [
        browser,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={os.path.abspath(pdf_path)}",
        html_url,
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    if result.returncode != 0:
        warnings.warn(f"Browser PDF conversion failed: {result.stderr or result.stdout}")
    return os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0


def draw_alignment_plot_page(c, stats, user_id):
    """Draw trajectory/acupoint alignment plots when available."""
    raw = stats.get("_alignment_raw", {})
    plot_paths = raw.get("plot_paths", {})
    xy_path = plot_paths.get("xy") or os.path.join(OUTPUT_DIR, f"{user_id}_trajectory_acupoints_xy.png")
    plot3d_path = plot_paths.get("3d") or os.path.join(OUTPUT_DIR, f"{user_id}_trajectory_acupoints_3d.png")
    if not os.path.isfile(xy_path) and not os.path.isfile(plot3d_path):
        return False

    y = PAGE_HEIGHT - 45 * mm
    c.setFillColor(_hex(COLOR_NAVY))
    c.setFont(FONT_BOLD, 19)
    c.drawString(MARGIN, y, "Robot Trajectory and Acupoint Alignment")
    c.setStrokeColor(_hex(COLOR_LINE))
    c.line(MARGIN, y - 6 * mm, PAGE_WIDTH - MARGIN, y - 6 * mm)

    overall = raw.get("overall", {})
    info = (
        f"Total samples: {overall.get('total_samples', 0)} | "
        f"Contact samples: {overall.get('contact_samples', 0)} | "
        f"Contact duration: {overall.get('contact_duration_s', 0)} s | "
        f"Mean contact force: {overall.get('mean_contact_force_N', 'N/A')} N"
    )
    c.setFillColor(_hex(COLOR_TEXT))
    c.setFont(FONT_NAME, 9.5)
    c.drawString(MARGIN, y - 14 * mm, info)

    image_y = y - 101 * mm
    if os.path.isfile(xy_path):
        c.drawImage(xy_path, MARGIN, image_y, 82 * mm, 70 * mm, preserveAspectRatio=True, mask="auto")
    if os.path.isfile(plot3d_path):
        c.drawImage(plot3d_path, PAGE_WIDTH - MARGIN - 82 * mm, image_y, 82 * mm, 70 * mm, preserveAspectRatio=True, mask="auto")

    by_section = raw.get("by_section", [])
    if by_section:
        rows = [["Section", "Mean Force", "Max Force", "Duration", "Main Acupoints"]]
        for item in by_section:
            rows.append([
                item.get("section", "Unknown"),
                "N/A" if item.get("mean_force_N") is None else f"{float(item.get('mean_force_N')):.2f} N",
                "N/A" if item.get("max_force_N") is None else f"{float(item.get('max_force_N')):.2f} N",
                f"{float(item.get('duration_s', 0) or 0):.2f} s",
                ", ".join(item.get("main_acupoints", [])[:3]),
            ])
        table = _make_table(rows, [29 * mm, 25 * mm, 25 * mm, 24 * mm, 58 * mm], font_size=7.8)
        _, table_h = table.wrapOn(c, PAGE_WIDTH - 2 * MARGIN, 60 * mm)
        table.drawOn(c, MARGIN, image_y - table_h - 10 * mm)
    return True


def generate_report(
    user_id,
    logo_path=None,
    report_id=None,
    deepseek_api_key=None,
    use_ai_analysis=True,
    body_image_path=None,
    acupoints=None,
    trajectory=None,
    sample_rate=20.0,
    threshold_mm=25.0,
):
    """Generate the PDF report and cover PNG preview."""
    register_fonts()
    report_id = report_id or f"DEMO-{datetime.now().year}-001"
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(ASSET_DIR, exist_ok=True)
    if acupoints and trajectory:
        if run_spatial_temporal_alignment is None:
            warnings.warn("spatial_temporal_alignment.py is unavailable; generating report without alignment refresh.")
        else:
            run_spatial_temporal_alignment(
                user_id=user_id,
                acupoint_path=acupoints,
                trajectory_path=trajectory,
                output_dir=OUTPUT_DIR,
                sample_rate_hz=sample_rate,
                contact_threshold_mm=threshold_mm,
            )
    report_data = load_report_data(user_id)
    stats = _stats_from_report_data(report_data)
    body_asset_path = prepare_body_skeleton_asset(body_image_path)
    analysis_blocks = (
        generate_deepseek_analysis(stats, user_id, api_key=deepseek_api_key)
        if use_ai_analysis else _default_cover_analysis()
    )
    if stats.get("source") == "spatial_temporal_alignment":
        alignment_intro = (
            "本报告基于统一相机坐标系下的机器人 TCP 轨迹、穴位 3D 点云坐标与实时按压力数据完成时空对齐。\n\n"
        )
        analysis_blocks = alignment_intro + str(analysis_blocks)

    pdf_path = os.path.join(OUTPUT_DIR, f"{user_id}_smart_massage_report.pdf")
    cover_preview_path = os.path.join(OUTPUT_DIR, f"{user_id}_report_cover_preview.png")
    detection_preview_path = os.path.join(OUTPUT_DIR, f"{user_id}_massage_detection_report.png")
    browser_html_path = os.path.join(OUTPUT_DIR, f"{user_id}_browser_report.html")

    create_customer_report_html(stats, user_id, browser_html_path, logo_path=logo_path, report_id=report_id)
    os.makedirs(FINAL_REPORT_INTERFACE_DIR, exist_ok=True)
    if stats.get("source") == "spatial_temporal_alignment":
        create_browser_report_html(stats, user_id, FINAL_REPORT_INTERFACE_PATH)
    else:
        shutil.copyfile(browser_html_path, FINAL_REPORT_INTERFACE_PATH)
    if convert_html_to_pdf_with_browser(browser_html_path, pdf_path):
        _create_cover_preview(
            stats,
            user_id,
            report_id,
            logo_path,
            cover_preview_path,
            analysis_blocks=analysis_blocks,
            body_image_path=body_asset_path,
        )
        return pdf_path, cover_preview_path

    c = canvas.Canvas(pdf_path, pagesize=A4)
    page_offset = 0
    detection_image = None
    if stats.get("source") == "spatial_temporal_alignment":
        detection_image = create_massage_detection_report_image(stats, user_id, detection_preview_path)
        if detection_image and os.path.isfile(detection_image):
            c.drawImage(detection_image, 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT, preserveAspectRatio=True, anchor="c", mask="auto")
            c.showPage()
            page_offset = 1

    draw_cover_page(
        c,
        stats,
        user_id,
        report_id,
        logo_path,
        analysis_blocks=analysis_blocks,
        body_image_path=body_asset_path,
    )
    c.showPage()

    sections = _section_map(stats)
    for page_index, section_name in enumerate(SECTION_ORDER, start=2 + page_offset):
        draw_header(c, user_id, report_id, logo_path)
        section_stats = dict(sections.get(section_name, {}))
        if not section_stats:
            section_stats = {
                "section": section_name,
                "mean_stiffness_N_m": {"Upper Back": 3200, "Mid Back": 3600, "Lower Back": 4900}[section_name],
                "max_stiffness_N_m": {"Upper Back": 4200, "Mid Back": 5200, "Lower Back": 6900}[section_name],
                "std_stiffness_N_m": 0,
            }
        chart_path = os.path.join(OUTPUT_DIR, f"{user_id}_{section_name.replace(' ', '_').lower()}_body_chart.png")
        create_section_body_chart(section_name, stats, chart_path, body_image_path=body_asset_path)
        points = _points_for_section(stats, section_name)
        section_stats["_chart_path"] = chart_path
        section_stats["_summary_text"] = _section_summary_text(section_name, section_stats, points)
        section_stats["_recommendations"] = RECOMMENDATIONS.get(section_name, [])
        draw_section_page(c, section_name, section_stats, ACUPOINTS[section_name])
        draw_footer(c, page_num=page_index)
        c.showPage()

    if stats.get("source") == "spatial_temporal_alignment":
        draw_header(c, user_id, report_id, logo_path)
        if draw_alignment_plot_page(c, stats, user_id):
            draw_footer(c, page_num=len(SECTION_ORDER) + 2 + page_offset)
            c.showPage()

    c.save()
    if detection_image and os.path.isfile(detection_image):
        shutil.copyfile(detection_image, cover_preview_path)
    else:
        _create_cover_preview(
            stats,
            user_id,
            report_id,
            logo_path,
            cover_preview_path,
            analysis_blocks=analysis_blocks,
            body_image_path=body_asset_path,
        )
    return pdf_path, cover_preview_path


def main():
    parser = argparse.ArgumentParser(description="Generate a smart massage PDF report.")
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--logo_path", default=None)
    parser.add_argument("--report_id", default=None)
    parser.add_argument(
        "--body_image_path",
        default=None,
        help=(
            "Path to the full-back skeleton image. When provided, it is copied "
            "to report_assets/back_skeleton_body.png and reused by future reports."
        ),
    )
    parser.add_argument(
        "--deepseek_api_key",
        default=None,
        help="DeepSeek API key. Prefer setting DEEPSEEK_API_KEY instead of passing this on the command line.",
    )
    parser.add_argument(
        "--no_ai_analysis",
        action="store_true",
        help="Disable DeepSeek analysis and use built-in local text.",
    )
    parser.add_argument("--acupoints", default=None, help="Optional 3D acupoint coordinate file.")
    parser.add_argument("--trajectory", default=None, help="Optional robot TCP trajectory file.")
    parser.add_argument("--sample_rate", type=float, default=20.0, help="Trajectory sample rate when time_s is absent.")
    parser.add_argument("--threshold_mm", type=float, default=25.0, help="Contact distance threshold in millimeters.")
    args = parser.parse_args()

    pdf_path, cover_preview_path = generate_report(
        user_id=args.user_id,
        logo_path=args.logo_path,
        report_id=args.report_id,
        deepseek_api_key=args.deepseek_api_key,
        use_ai_analysis=not args.no_ai_analysis,
        body_image_path=args.body_image_path,
        acupoints=args.acupoints,
        trajectory=args.trajectory,
        sample_rate=args.sample_rate,
        threshold_mm=args.threshold_mm,
    )
    print(f"Smart massage report saved to: outputs/{os.path.basename(pdf_path)}")
    print(f"Cover preview saved to: outputs/{os.path.basename(cover_preview_path)}")


if __name__ == "__main__":
    main()
