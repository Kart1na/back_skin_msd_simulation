"""Spatial-temporal alignment between robot TCP trajectory and 3D acupoints."""

import argparse
import csv
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is expected but not required.
    np = None

try:
    from scipy.spatial import cKDTree
except ImportError:  # pragma: no cover - optional acceleration.
    cKDTree = None


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "outputs"
SECTION_ORDER = ["Upper Back", "Mid Back", "Lower Back"]

UPPER_BACK_NAMES = {
    "大椎", "风门", "肺俞", "厥阴俞", "心俞", "督俞",
    "肩", "肩井", "肩外俞", "肩中俞", "曲垣", "天宗", "秉风",
    "臑俞", "肩贞", "陶道", "身柱", "巨阙关", "神道", "灵台", "附分", "大杼", "大抒", "魄户",
}
MID_BACK_NAMES = {
    "膈俞", "肝俞", "胆俞", "脾俞", "胃俞", "胃脘下俞", "三焦俞",
    "至阳", "筋缩", "中枢", "脊中", "骨缝", "肓门", "意舍",
}
LOWER_BACK_NAMES = {
    "肾俞", "气海俞", "大肠俞", "关元俞", "小肠俞", "膀胱俞",
    "腰", "腰阳关", "志室", "腰宜", "命门", "悬枢", "上髎", "次髎", "中髎", "下髎",
}
CENTER_NAMES = {"大椎", "腰阳关", "命门", "至阳", "陶道", "身柱", "筋缩", "中枢", "脊中"}


def _read_text_lines(path):
    """Read text lines with UTF-8 first and a small compatibility fallback."""
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            with open(path, "r", encoding=encoding) as f:
                return f.readlines()
        except UnicodeDecodeError as exc:
            last_error = exc
    raise last_error


def _split_fields(line):
    return [item.strip() for item in re.split(r"[\s,]+", line.strip()) if item.strip()]


def _float_or_none(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_header(fields, required=()):
    lowered = {field.strip().lower() for field in fields}
    return any(field in lowered for field in required)


def load_acupoint_3d_file(path):
    """Load acupoint 3D coordinates from name,x,y,z rows."""
    records = []
    skipped_rows = 0
    header = None

    for raw in _read_text_lines(path):
        line = raw.strip()
        if not line:
            continue
        fields = _split_fields(line)
        if len(fields) < 4:
            skipped_rows += 1
            continue
        if header is None and _has_header(fields, required=("name", "x", "y", "z")):
            header = [field.lower() for field in fields]
            continue

        try:
            if header:
                row = {key: fields[idx] for idx, key in enumerate(header) if idx < len(fields)}
                name = row.get("name") or row.get("acupoint") or row.get("point")
                x = _float_or_none(row.get("x"))
                y = _float_or_none(row.get("y"))
                z = _float_or_none(row.get("z"))
            else:
                name = fields[0]
                x, y, z = (_float_or_none(fields[1]), _float_or_none(fields[2]), _float_or_none(fields[3]))
            if not name or x is None or y is None or z is None:
                skipped_rows += 1
                continue
            records.append({"name": name, "x": x, "y": y, "z": z})
        except (IndexError, ValueError):
            skipped_rows += 1

    load_acupoint_3d_file.skipped_rows = skipped_rows
    return records


def load_robot_trajectory_file(path, sample_rate_hz=20.0):
    """Load robot TCP trajectory rows with optional time_s and force columns."""
    records = []
    skipped_rows = 0
    header = None

    for raw in _read_text_lines(path):
        line = raw.strip()
        if not line:
            continue
        fields = _split_fields(line)
        if len(fields) < 4:
            skipped_rows += 1
            continue
        if header is None and _has_header(fields, required=("time_s", "force", "force_n")):
            header = [field.lower() for field in fields]
            continue

        try:
            sample_index = len(records)
            if header:
                row = {key: fields[idx] for idx, key in enumerate(header) if idx < len(fields)}
                time_s = _float_or_none(row.get("time_s"))
                x = _float_or_none(row.get("x"))
                y = _float_or_none(row.get("y"))
                z = _float_or_none(row.get("z"))
                force_n = _float_or_none(row.get("force_n", row.get("force")))
            else:
                time_s = None
                x, y, z = (_float_or_none(fields[0]), _float_or_none(fields[1]), _float_or_none(fields[2]))
                force_n = _float_or_none(fields[3])

            if x is None or y is None or z is None:
                skipped_rows += 1
                continue
            if time_s is None:
                time_s = sample_index / float(sample_rate_hz or 20.0)
            records.append({
                "sample_index": sample_index,
                "time_s": time_s,
                "x": x,
                "y": y,
                "z": z,
                "force_N": force_n,
            })
        except (IndexError, ValueError, ZeroDivisionError):
            skipped_rows += 1

    load_robot_trajectory_file.skipped_rows = skipped_rows
    return records


def infer_section_from_acupoint_name(name):
    """Infer Upper/Mid/Lower Back from Chinese acupoint names."""
    text = str(name or "")
    if any(item in text for item in UPPER_BACK_NAMES):
        return "Upper Back"
    if any(item in text for item in MID_BACK_NAMES):
        return "Mid Back"
    if any(item in text for item in LOWER_BACK_NAMES):
        return "Lower Back"
    return "Unknown"


def infer_region_from_xyz_or_name(acupoint):
    """Infer section, side, and coarse region from acupoint name and x coordinate."""
    name = str(acupoint.get("name", ""))
    section = infer_section_from_acupoint_name(name)
    x = _float_or_none(acupoint.get("x"))
    if any(item in name for item in CENTER_NAMES) or (x is not None and abs(x) < 0.01):
        side = "center"
        region = "spine_center"
    elif x is None:
        side = "unknown"
        region = "unknown"
    else:
        side = "left" if x < 0 else "right"
        section_key = {
            "Upper Back": "upper_back",
            "Mid Back": "middle_back",
            "Lower Back": "lower_back",
        }.get(section)
        region = f"{section_key}_{side}" if section_key else "unknown"
    return {"section": section, "side": side, "region": region}


def _distance(a, b):
    return math.sqrt(sum((float(a[idx]) - float(b[idx])) ** 2 for idx in range(3)))


def match_trajectory_to_acupoints(robot_records, acupoints, contact_threshold_mm=25.0):
    """Match each robot trajectory sample to its nearest 3D acupoint."""
    if not acupoints:
        raise ValueError("No acupoints found for spatial-temporal alignment.")

    acupoint_coords = [(item["x"], item["y"], item["z"]) for item in acupoints]
    threshold_m = float(contact_threshold_mm) / 1000.0
    tree = cKDTree(acupoint_coords) if cKDTree is not None else None
    np_coords = np.asarray(acupoint_coords, dtype=float) if np is not None and tree is None else None
    aligned = []

    for record in robot_records:
        point = (record["x"], record["y"], record["z"])
        if tree is not None:
            distance_m, nearest_idx = tree.query(point)
            nearest_idx = int(nearest_idx)
            distance_m = float(distance_m)
        elif np_coords is not None:
            diffs = np_coords - np.asarray(point, dtype=float)
            distances = np.sqrt(np.sum(diffs * diffs, axis=1))
            nearest_idx = int(np.argmin(distances))
            distance_m = float(distances[nearest_idx])
        else:
            nearest_idx, nearest_coord = min(
                enumerate(acupoint_coords),
                key=lambda item: _distance(point, item[1]),
            )
            distance_m = float(_distance(point, nearest_coord))

        nearest = acupoints[nearest_idx]
        region_info = infer_region_from_xyz_or_name(nearest)
        distance_mm = distance_m * 1000.0
        aligned.append({
            "sample_index": record.get("sample_index"),
            "time_s": record.get("time_s"),
            "robot_x": record.get("x"),
            "robot_y": record.get("y"),
            "robot_z": record.get("z"),
            "force_N": record.get("force_N"),
            "nearest_acupoint": nearest.get("name"),
            "nearest_acupoint_x": nearest.get("x"),
            "nearest_acupoint_y": nearest.get("y"),
            "nearest_acupoint_z": nearest.get("z"),
            "distance_m": round(distance_m, 6),
            "distance_mm": round(distance_mm, 3),
            "is_contact": distance_m <= threshold_m,
            **region_info,
        })
    return aligned


def _force_level(value):
    if value is None:
        return "low"
    if value < 5:
        return "low"
    if value < 12:
        return "medium"
    return "high"


def _section_grade(mean_force, duration_s):
    if mean_force is None:
        return "A", "Mild", "Stretches"
    if mean_force < 5 and duration_s < 5:
        return "A", "Mild", "Stretches"
    if mean_force < 10:
        return "B", "Moderate", "Posture Care"
    if mean_force < 15:
        return "C", "Higher", "Release + Stretch"
    return "D", "Severe", "Release + Stretch"


def _attention_level(mean_force, max_force, duration_s, contact_count):
    max_force = max_force or 0.0
    mean_force = mean_force or 0.0
    if max_force >= 15 or duration_s >= 10:
        return "high"
    if mean_force >= 10 or contact_count >= 100:
        return "attention"
    return "normal"


def _recommend_force(mean_force, force_level, attention_level):
    """Recommend a conservative next massage force range from measured force."""
    base = 5.0 if mean_force is None else float(mean_force)
    if attention_level == "high":
        target = min(base, 8.0)
    elif force_level == "high":
        target = min(base, 10.0)
    elif force_level == "low":
        target = max(4.0, min(base + 0.8, 7.0))
    else:
        target = max(5.0, min(base + 0.5, 9.0))
    low = max(3.0, target - 1.5)
    high = min(12.0, target + 1.5)
    return {
        "recommended_force_N": round(target, 2),
        "safe_force_range_N": [round(low, 2), round(high, 2)],
    }


def _mean(values):
    filtered = [float(value) for value in values if value is not None]
    return round(mean(filtered), 3) if filtered else None


def summarize_alignment(aligned_records, sample_rate_hz=20.0):
    """Summarize aligned records for report consumption."""
    sample_rate_hz = float(sample_rate_hz or 20.0)
    sample_duration = 1.0 / sample_rate_hz if sample_rate_hz > 0 else 0.0
    contacts = [item for item in aligned_records if item.get("is_contact")]
    forces = [item.get("force_N") for item in aligned_records if item.get("force_N") is not None]
    contact_forces = [item.get("force_N") for item in contacts if item.get("force_N") is not None]

    summary = {
        "overall": {
            "total_samples": len(aligned_records),
            "contact_samples": len(contacts),
            "contact_ratio": round(len(contacts) / len(aligned_records), 4) if aligned_records else 0.0,
            "total_duration_s": round(len(aligned_records) * sample_duration, 3),
            "contact_duration_s": round(len(contacts) * sample_duration, 3),
            "mean_force_N": _mean(forces),
            "max_force_N": round(max(forces), 3) if forces else None,
            "min_force_N": round(min(forces), 3) if forces else None,
            "mean_contact_force_N": _mean(contact_forces),
            "max_contact_force_N": round(max(contact_forces), 3) if contact_forces else None,
        },
        "by_acupoint": [],
        "by_section": [],
        "by_region": [],
    }

    for key, output_name in (
        ("nearest_acupoint", "by_acupoint"),
        ("section", "by_section"),
        ("region", "by_region"),
    ):
        grouped = defaultdict(list)
        for item in contacts:
            grouped[item.get(key) or "unknown"].append(item)

        rows = []
        for group_key, group in grouped.items():
            group_forces = [item.get("force_N") for item in group if item.get("force_N") is not None]
            distances = [item.get("distance_mm") for item in group if item.get("distance_mm") is not None]
            mean_force = _mean(group_forces)
            max_force = round(max(group_forces), 3) if group_forces else None
            duration_s = round(len(group) * sample_duration, 3)
            acupoint_counts = Counter(item.get("nearest_acupoint") for item in group)

            if output_name == "by_acupoint":
                first = group[0]
                force_level = _force_level(mean_force)
                attention_level = _attention_level(mean_force, max_force, duration_s, len(group))
                row = {
                    "name": group_key,
                    "section": first.get("section", "Unknown"),
                    "region": first.get("region", "unknown"),
                    "sample_count": sum(1 for item in aligned_records if item.get("nearest_acupoint") == group_key),
                    "contact_count": len(group),
                    "duration_s": duration_s,
                    "mean_force_N": mean_force,
                    "max_force_N": max_force,
                    "mean_distance_mm": _mean(distances),
                    "min_distance_mm": round(min(distances), 3) if distances else None,
                    "force_level": force_level,
                    "attention_level": attention_level,
                    **_recommend_force(mean_force, force_level, attention_level),
                }
            elif output_name == "by_section":
                grade, label, to_do = _section_grade(mean_force, duration_s)
                force_level = _force_level(mean_force)
                attention_level = _attention_level(mean_force, max_force, duration_s, len(group))
                row = {
                    "section": group_key,
                    "contact_count": len(group),
                    "duration_s": duration_s,
                    "mean_force_N": mean_force,
                    "max_force_N": max_force,
                    "main_acupoints": [name for name, _ in acupoint_counts.most_common(5) if name],
                    "grade": grade,
                    "label": label,
                    "to_do": to_do,
                    "force_level": force_level,
                    "attention_level": attention_level,
                    **_recommend_force(mean_force, force_level, attention_level),
                }
            else:
                force_level = _force_level(mean_force)
                attention_level = _attention_level(mean_force, max_force, duration_s, len(group))
                row = {
                    "region": group_key,
                    "section": group[0].get("section", "Unknown"),
                    "contact_count": len(group),
                    "duration_s": duration_s,
                    "mean_force_N": mean_force,
                    "max_force_N": max_force,
                    "main_acupoints": [name for name, _ in acupoint_counts.most_common(5) if name],
                    "force_level": force_level,
                    "attention_level": attention_level,
                    **_recommend_force(mean_force, force_level, attention_level),
                }
            rows.append(row)

        if output_name == "by_section":
            rows.sort(key=lambda item: SECTION_ORDER.index(item["section"]) if item["section"] in SECTION_ORDER else 99)
        else:
            rows.sort(key=lambda item: item.get("contact_count", 0), reverse=True)
        summary[output_name] = rows

    return summary


def create_alignment_plots(aligned_records, acupoints, output_dir, user_id):
    """Create XY and 3D trajectory/acupoint alignment plots."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    xy_path = output_dir / f"{user_id}_trajectory_acupoints_xy.png"
    plot3d_path = output_dir / f"{user_id}_trajectory_acupoints_3d.png"
    if not aligned_records or not acupoints:
        return str(xy_path), str(plot3d_path)

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return _create_alignment_plots_with_pillow(aligned_records, acupoints, xy_path, plot3d_path)

    ac_x = [item["x"] for item in acupoints]
    ac_y = [item["y"] for item in acupoints]
    ac_z = [item["z"] for item in acupoints]
    rb_x = [item["robot_x"] for item in aligned_records]
    rb_y = [item["robot_y"] for item in aligned_records]
    rb_z = [item["robot_z"] for item in aligned_records]
    contacts = [item for item in aligned_records if item.get("is_contact")]

    fig, ax = plt.subplots(figsize=(7.2, 5.4), dpi=160)
    ax.scatter(ac_x, ac_y, s=32, c="#1F77B4", label="Acupoints", zorder=3)
    ax.plot(rb_x, rb_y, color="#D62728", linewidth=1.2, alpha=0.8, label="Robot trajectory")
    if contacts:
        ax.scatter(
            [item["robot_x"] for item in contacts],
            [item["robot_y"] for item in contacts],
            s=16,
            c="#2CA02C",
            alpha=0.85,
            label="Contact",
            zorder=4,
        )
    for name, _ in Counter(item.get("nearest_acupoint") for item in contacts).most_common(5):
        point = next((item for item in acupoints if item.get("name") == name), None)
        if point:
            ax.annotate(name, (point["x"], point["y"]), xytext=(4, 4), textcoords="offset points", fontsize=8)
    ax.set_title("Robot Trajectory and Acupoint Alignment")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(xy_path)
    plt.close(fig)

    fig = plt.figure(figsize=(7.2, 5.4), dpi=160)
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(ac_x, ac_y, ac_z, s=32, c="#1F77B4", label="Acupoints")
    ax.plot(rb_x, rb_y, rb_z, color="#D62728", linewidth=1.0, alpha=0.8, label="Robot trajectory")
    if contacts:
        ax.scatter(
            [item["robot_x"] for item in contacts],
            [item["robot_y"] for item in contacts],
            [item["robot_z"] for item in contacts],
            s=15,
            c="#2CA02C",
            alpha=0.85,
            label="Contact",
        )
    ax.set_title("Robot Trajectory and Acupoint Alignment")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_zlabel("z (m)")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(plot3d_path)
    plt.close(fig)
    return str(xy_path), str(plot3d_path)


def _create_alignment_plots_with_pillow(aligned_records, acupoints, xy_path, plot3d_path):
    """Create simple alignment PNGs when matplotlib is unavailable."""
    from PIL import Image, ImageDraw, ImageFont

    def font(size=18):
        for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def scale(points, width=1000, height=720, pad=70):
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1e-9)
        span_y = max(max_y - min_y, 1e-9)

        def project(x, y):
            px = pad + (x - min_x) / span_x * (width - 2 * pad)
            py = height - pad - (y - min_y) / span_y * (height - 2 * pad)
            return int(px), int(py)

        return project

    def draw_common(points, out_path, title):
        img = Image.new("RGB", (1000, 720), "white")
        draw = ImageDraw.Draw(img)
        title_font = font(28)
        small_font = font(17)
        draw.text((55, 24), title, fill="#0B2A4A", font=title_font)
        draw.line((55, 62, 945, 62), fill="#D7E3EA", width=2)
        project = scale(points)

        trajectory = [project(x, y) for x, y, _ in points if _ == "robot"]
        if len(trajectory) > 1:
            draw.line(trajectory, fill="#D62728", width=3)
        for x, y, kind in points:
            px, py = project(x, y)
            if kind == "acupoint":
                draw.ellipse((px - 7, py - 7, px + 7, py + 7), fill="#1F77B4", outline="#0B2A4A")
            elif kind == "contact":
                draw.ellipse((px - 5, py - 5, px + 5, py + 5), fill="#2CA02C")

        contacts = [item for item in aligned_records if item.get("is_contact")]
        for name, _count in Counter(item.get("nearest_acupoint") for item in contacts).most_common(5):
            point = next((item for item in acupoints if item.get("name") == name), None)
            if point:
                px, py = project(point["x"], point["y"])
                draw.text((px + 8, py - 8), str(name), fill="#263238", font=small_font)

        legend_y = 650
        draw.ellipse((60, legend_y, 74, legend_y + 14), fill="#1F77B4")
        draw.text((82, legend_y - 2), "Acupoints", fill="#263238", font=small_font)
        draw.line((205, legend_y + 7, 245, legend_y + 7), fill="#D62728", width=3)
        draw.text((255, legend_y - 2), "Robot trajectory", fill="#263238", font=small_font)
        draw.ellipse((440, legend_y, 454, legend_y + 14), fill="#2CA02C")
        draw.text((462, legend_y - 2), "Contact", fill="#263238", font=small_font)
        img.save(out_path)

    xy_points = [(item["x"], item["y"], "acupoint") for item in acupoints]
    xy_points += [(item["robot_x"], item["robot_y"], "robot") for item in aligned_records]
    xy_points += [(item["robot_x"], item["robot_y"], "contact") for item in aligned_records if item.get("is_contact")]
    draw_common(xy_points, xy_path, "Robot Trajectory and Acupoint Alignment - XY")

    projected = []
    for item in acupoints:
        projected.append((item["x"] + item["z"] * 0.35, item["y"] + item["z"] * 0.18, "acupoint"))
    for item in aligned_records:
        projected.append((item["robot_x"] + item["robot_z"] * 0.35, item["robot_y"] + item["robot_z"] * 0.18, "robot"))
    for item in aligned_records:
        if item.get("is_contact"):
            projected.append((item["robot_x"] + item["robot_z"] * 0.35, item["robot_y"] + item["robot_z"] * 0.18, "contact"))
    draw_common(projected, plot3d_path, "Robot Trajectory and Acupoint Alignment - 3D Projection")
    return str(xy_path), str(plot3d_path)


def _write_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def save_alignment_outputs(aligned_records, summary, output_dir, user_id):
    """Save alignment CSV and JSON artifacts for report generation."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    alignment_csv = output_dir / f"{user_id}_trajectory_acupoint_alignment.csv"
    acupoint_csv = output_dir / f"{user_id}_acupoint_force_summary.csv"
    section_csv = output_dir / f"{user_id}_section_force_summary.csv"
    json_path = output_dir / f"{user_id}_spatial_temporal_alignment.json"

    _write_csv(alignment_csv, aligned_records, [
        "sample_index", "time_s", "robot_x", "robot_y", "robot_z", "force_N",
        "nearest_acupoint", "nearest_acupoint_x", "nearest_acupoint_y", "nearest_acupoint_z",
        "distance_m", "distance_mm", "is_contact", "section", "side", "region",
    ])
    _write_csv(acupoint_csv, summary.get("by_acupoint", []), [
        "name", "section", "region", "sample_count", "contact_count", "duration_s",
        "mean_force_N", "max_force_N", "mean_distance_mm", "min_distance_mm",
        "force_level", "attention_level", "recommended_force_N", "safe_force_range_N",
    ])
    _write_csv(section_csv, summary.get("by_section", []), [
        "section", "contact_count", "duration_s", "mean_force_N", "max_force_N",
        "main_acupoints", "grade", "label", "to_do", "force_level", "attention_level",
        "recommended_force_N", "safe_force_range_N",
    ])
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return str(json_path)


def run_spatial_temporal_alignment(
    user_id,
    acupoint_path,
    trajectory_path,
    output_dir=DEFAULT_OUTPUT_DIR,
    sample_rate_hz=20.0,
    contact_threshold_mm=25.0,
):
    """Run full alignment and return the summary JSON path."""
    acupoints = load_acupoint_3d_file(acupoint_path)
    robot_records = load_robot_trajectory_file(trajectory_path, sample_rate_hz=sample_rate_hz)
    aligned = match_trajectory_to_acupoints(robot_records, acupoints, contact_threshold_mm=contact_threshold_mm)
    summary = summarize_alignment(aligned, sample_rate_hz=sample_rate_hz)
    xy_path, plot3d_path = create_alignment_plots(aligned, acupoints, output_dir, user_id)
    skipped_rows = {
        "acupoints": getattr(load_acupoint_3d_file, "skipped_rows", 0),
        "trajectory": getattr(load_robot_trajectory_file, "skipped_rows", 0),
    }
    summary.update({
        "parameters": {
            "input_acupoint_file": str(acupoint_path),
            "input_trajectory_file": str(trajectory_path),
            "sample_rate_hz": float(sample_rate_hz),
            "contact_threshold_mm": float(contact_threshold_mm),
            "total_samples": len(robot_records),
            "skipped_rows": skipped_rows,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
        "plot_paths": {
            "xy": xy_path,
            "3d": plot3d_path,
        },
        "aligned_records": aligned,
    })
    return save_alignment_outputs(aligned, summary, output_dir, user_id)


def main():
    parser = argparse.ArgumentParser(description="Align robot TCP trajectory to 3D acupoint coordinates.")
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--acupoints", required=True, help="Path to rgbImage_back_acu_pointcloud.txt")
    parser.add_argument("--trajectory", required=True, help="Path to camera_posData_tcp.txt")
    parser.add_argument("--output_dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--sample_rate", type=float, default=20.0)
    parser.add_argument("--threshold_mm", type=float, default=25.0)
    args = parser.parse_args()

    json_path = run_spatial_temporal_alignment(
        user_id=args.user_id,
        acupoint_path=args.acupoints,
        trajectory_path=args.trajectory,
        output_dir=args.output_dir,
        sample_rate_hz=args.sample_rate,
        contact_threshold_mm=args.threshold_mm,
    )
    print(f"Spatial-temporal alignment saved to: outputs/{os.path.basename(json_path)}")


if __name__ == "__main__":
    main()
