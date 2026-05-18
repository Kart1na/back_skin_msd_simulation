"""Generate an EMMA-style back stiffness report image."""

import argparse
import json
import os
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont

import config
from stiffness_estimator import estimate_stiffness, save_stiffness_stats
from stiffness_grader import grade_stiffness_stats, save_grades
from stiffness_report_generator import build_report


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(BASE_DIR, "assets")
SPINE_REFERENCE_IMAGE = os.path.join(ASSET_DIR, "spine_report_reference.png")
SPINE_ONLY_IMAGE = os.path.join(ASSET_DIR, "spine_only_extracted.png")

PAGE_W = 930
PAGE_H = 700

BLACK = "#000000"
LINE = "#808080"
TABLE_HEADER = "#8fd0cf"
GREEN = "#00f018"
YELLOW = "#ffff00"
RED = "#ff0000"
BLUE_LINE = "#4e7f9d"

POINT_VERTEBRA_MAP = {
    "shoulder_left": "T2",
    "shoulder_right": "T3",
    "upper_back_left": "T4",
    "upper_back_right": "T5",
    "mid_paraspinal_left": "T8",
    "mid_paraspinal_right": "T9",
    "middle_back_left": "T10",
    "middle_back_right": "T11",
    "lower_back_left": "L2",
    "lower_back_right": "L3",
    "lumbar_left": "L4",
    "lumbar_right": "L5",
}


def _load_or_create_stats(user_id):
    stats_path = os.path.join(config.output_dir, f"{user_id}_stiffness_stats.json")
    if os.path.isfile(stats_path):
        with open(stats_path, "r", encoding="utf-8") as f:
            return json.load(f)
    stats = estimate_stiffness(user_id)
    save_stiffness_stats(stats, user_id)
    return stats


def _load_or_create_grades(user_id, stats):
    grades_path = os.path.join(config.output_dir, f"{user_id}_stiffness_grades.json")
    if os.path.isfile(grades_path):
        with open(grades_path, "r", encoding="utf-8") as f:
            return json.load(f)
    grades = grade_stiffness_stats(stats, mode="relative")
    save_grades(grades, user_id)
    return grades


def _load_report(user_id, stats, grades):
    report_path = os.path.join(config.output_dir, f"{user_id}_stiffness_report.json")
    if os.path.isfile(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return build_report(user_id, stats, grades)


def _font(size, bold=False, serif=False):
    if serif:
        candidates = [
            r"C:\Windows\Fonts\simsun.ttc",
            r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\timesbd.ttf" if bold else r"C:\Windows\Fonts\times.ttf",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\simhei.ttf" if bold else r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        ]
    for path in candidates:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _text(draw, xy, text, size=20, bold=False, anchor=None, serif=True, fill=BLACK):
    draw.text(xy, str(text), font=_font(size, bold, serif), fill=fill, anchor=anchor)


def _measure(draw, text, size=20, bold=False, serif=True):
    bbox = draw.textbbox((0, 0), str(text), font=_font(size, bold, serif))
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _center_text(draw, box, text, size=20, bold=False, serif=True):
    x1, y1, x2, y2 = box
    _text(
        draw,
        ((x1 + x2) / 2, (y1 + y2) / 2),
        text,
        size=size,
        bold=bold,
        anchor="mm",
        serif=serif,
    )


def _wrap_text(draw, text, max_width, size=22, bold=False):
    lines = []
    current = ""
    for char in str(text):
        trial = current + char
        if _measure(draw, trial, size, bold, serif=False)[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def _grade_color(grade):
    if grade == "A":
        return "#ffffff"
    if grade == "B":
        return GREEN
    if grade == "C":
        return YELLOW
    return RED


def _score_color(score):
    if score < 1.15:
        return GREEN
    if score < 1.45:
        return YELLOW
    return RED


def _section_lookup(report):
    return {section["section"]: section for section in report.get("sections", [])}


def _draw_table(draw, report):
    x0, y0 = 38, 186
    widths = [120, 120, 120, 120]
    row_h = 26
    headers = ["Section", "Grade", "Label", "To Do"]
    rows = []
    by_section = _section_lookup(report)
    for name in ["Upper Back", "Mid Back", "Lower Back"]:
        section = by_section.get(name, {})
        rows.append([
            name,
            section.get("grade") or "B",
            section.get("label") if section.get("label") != "No Data" else "Moderate",
            "Stretches",
        ])

    for row_index in range(4):
        y1 = y0 + row_index * row_h
        x = x0
        for col_index, width in enumerate(widths):
            fill = TABLE_HEADER if row_index == 0 else "#ffffff"
            draw.rectangle((x, y1, x + width, y1 + row_h), fill=fill, outline=BLACK, width=1)
            text = headers[col_index] if row_index == 0 else rows[row_index - 1][col_index]
            _center_text(draw, (x, y1, x + width, y1 + row_h), text, 18, bold=(row_index == 0))
            x += width


def _draw_grade_scale(draw):
    _text(draw, (210, 337), "Stiffness Grade:", 19, serif=True)
    x0, y0 = 38, 374
    seg_w, seg_h = 119, 23
    colors = ["#ffffff", GREEN, YELLOW, RED]
    labels = ["A (Mild)", "B", "C", "D (Severe)"]
    for index, color in enumerate(colors):
        x1 = x0 + index * seg_w
        draw.rectangle((x1, y0, x1 + seg_w, y0 + seg_h), fill=color, outline=BLACK, width=1)
        _center_text(draw, (x1, y0 + 28, x1 + seg_w, y0 + 55), labels[index], 18, bold=True)


def _is_dynamic_overlay_pixel(r, g, b):
    """Detect colored report overlays from the reference screenshot."""
    is_green = g > 170 and r < 80 and b < 80
    is_yellow = r > 200 and g > 200 and b < 80
    is_red = r > 180 and g < 80 and b < 80
    return is_green or is_yellow or is_red


def _extract_spine_from_reference():
    """Create a spine-only asset from the user-provided screenshot.

    The crop keeps the original screenshot's bone artwork and vertebra labels,
    then removes colored stiffness boxes from that image. The report later draws
    fresh color boxes from current stiffness scores.
    """
    if not os.path.isfile(SPINE_REFERENCE_IMAGE):
        return None

    source = Image.open(SPINE_REFERENCE_IMAGE).convert("RGB")
    width, height = source.size

    crop_box = (
        int(width * 0.36),
        0,
        int(width * 0.74),
        height,
    )
    spine_img = source.crop(crop_box)

    pixels = spine_img.load()
    for y in range(spine_img.height):
        for x in range(spine_img.width):
            r, g, b = pixels[x, y]
            if _is_dynamic_overlay_pixel(r, g, b):
                pixels[x, y] = (255, 255, 255)

    os.makedirs(ASSET_DIR, exist_ok=True)
    spine_img.save(SPINE_ONLY_IMAGE)
    return spine_img


def _load_spine_only():
    """Return the extracted screenshot spine artwork."""
    if os.path.isfile(SPINE_ONLY_IMAGE):
        return Image.open(SPINE_ONLY_IMAGE).convert("RGB")
    return _extract_spine_from_reference()


def _draw_fallback_spine(draw, cx, top, labels, positions):
    for i, label in enumerate(labels):
        y = positions[label]
        draw.ellipse((cx - 16, y - 8, cx + 16, y + 8), fill="#f4f7f8", outline="#8bb6c8", width=2)
        draw.rounded_rectangle((cx - 8, y - 11, cx + 8, y + 11), radius=4, fill="#ffffff", outline="#7faabd", width=1)
        _text(draw, (cx, y + 1), label, 11, anchor="mm", serif=False, fill="#27313a")
        if label.startswith("T") and i < 12:
            rib_len = max(26, 64 - abs(i - 6) * 4)
            draw.arc((cx - rib_len, y - 14, cx - 5, y + 20), 190, 340, fill="#9cc3d2", width=2)
            draw.arc((cx + 5, y - 14, cx + rib_len, y + 20), 200, 350, fill="#9cc3d2", width=2)

    draw.ellipse((cx - 34, positions["L5"] + 10, cx + 34, positions["L5"] + 64), fill="#f4f7f8", outline="#8bb6c8", width=2)
    draw.line((cx, top - 8, cx, positions["L5"] + 68), fill="#a7c9d6", width=2)


def _draw_spine(image, draw, stats, grades):
    labels = ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "T11", "T12", "L1", "L2", "L3", "L4", "L5"]
    spine_img = _load_spine_only()

    if spine_img is not None:
        spine_img.thumbnail((190, 500), Image.Resampling.LANCZOS)
        spine_x = 640
        spine_y = 4
        image.paste(spine_img, (spine_x, spine_y))
        cx = spine_x + spine_img.width // 2
        top = spine_y + 18
        usable_height = spine_img.height - 82
        gap = usable_height / (len(labels) - 1)
    else:
        cx = 690
        top = 18
        gap = 27

    positions = {label: int(top + i * gap) for i, label in enumerate(labels)}
    if spine_img is None:
        _draw_fallback_spine(draw, cx, top, labels, positions)

    upper_line_y = positions["T6"] + 14
    lower_line_y = positions["T12"] + 14
    draw.line((545, upper_line_y, 910, upper_line_y), fill=BLUE_LINE, width=2)
    draw.line((545, lower_line_y, 910, lower_line_y), fill=BLUE_LINE, width=2)
    _text(draw, (858, positions["T4"]), "Upper\nBack", 21, serif=False)
    _text(draw, (858, positions["T9"]), "Mid\nBack", 21, serif=False)
    _text(draw, (858, positions["L2"]), "Lower\nBack", 21, serif=False)

    point_grades = [
        point
        for point in grades.get("points", [])
        if point.get("point_id") in POINT_VERTEBRA_MAP
    ]
    point_grades.sort(
        key=lambda point: labels.index(POINT_VERTEBRA_MAP[point["point_id"]])
    )

    for point in point_grades:
        label = POINT_VERTEBRA_MAP[point["point_id"]]
        score = float(point.get("score", 1.0))
        y = positions[label]
        x_mm = point.get("x_mm")
        side = -1 if x_mm is not None and float(x_mm) < 0 else 1
        bar_len = int(16 + min(score, 1.8) * 48)
        color = _score_color(score)

        if side < 0:
            x2 = cx - 36
            x1 = x2 - bar_len
            value_x = x1 - 44
        else:
            x1 = cx + 36
            x2 = x1 + bar_len
            value_x = x2 + 18

        draw.rectangle((x1, y - 6, x2, y + 6), fill=color, outline=BLACK, width=1)
        _text(draw, (value_x, y - 10), f"{score:.2f}", 15, serif=True)


def _draw_title_blocks(draw, report):
    _text(draw, (60, 122), f"按摩报告: {report['report_id'].replace('stiffness-', '')}", 18, serif=True)
    draw.line((36, 316, 518, 316), fill=LINE, width=2)

    title = f"按摩分析 cus_points_three_fullback_thirty_minutes {datetime.now().strftime('%Y-%m-%d')}"
    _text(draw, (465, 505), title, 27, bold=True, anchor="mm", serif=False)

    start = datetime.now().replace(microsecond=0)
    end = start + timedelta(minutes=30, seconds=2)
    _text(draw, (465, 555), f"{start.strftime('%H:%M:%S')} - {end.strftime('%H:%M:%S')}", 27, bold=True, anchor="mm", serif=True)


def _draw_analysis_text(draw, report):
    paragraph = (
        "本报告重点指出了您本次 EMMA 按摩过程中检测到的脊柱旁肌僵硬区域。"
        "肌肉僵硬如果不及时处理，不仅仅会引起偶尔的不适，还会逐渐对脊柱造成不均衡的压力，"
        "影响椎间盘、韧带、血液循环，甚至神经。随着时间推移，身体可能会以不良的方式适应这些变化，"
        "从而导致慢性疼痛、活动受限以及长期的姿势失衡。"
    )
    y = 590
    for line in _wrap_text(draw, paragraph, 860, 21, False)[:4]:
        _text(draw, (36, y), line, 21, serif=False)
        y += 28


def draw_stiffness_map(user_id):
    """Save outputs/{user_id}_stiffness_map.png and return its path."""
    stats = _load_or_create_stats(user_id)
    grades = _load_or_create_grades(user_id, stats)
    report = _load_report(user_id, stats, grades)

    image = Image.new("RGB", (PAGE_W, PAGE_H), "#ffffff")
    draw = ImageDraw.Draw(image)

    _draw_title_blocks(draw, report)
    _draw_table(draw, report)
    _draw_grade_scale(draw)
    _draw_spine(image, draw, stats, grades)
    _draw_analysis_text(draw, report)

    os.makedirs(config.output_dir, exist_ok=True)
    output_path = os.path.join(config.output_dir, f"{user_id}_stiffness_map.png")
    image.save(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Draw EMMA-style stiffness report PNG.")
    parser.add_argument("--user_id", required=True)
    args = parser.parse_args()

    output_path = draw_stiffness_map(args.user_id)
    print(json.dumps({"user_id": args.user_id, "output_path": output_path}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
