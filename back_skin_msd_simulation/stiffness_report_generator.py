"""Generate EMMA-style back stiffness reference reports."""

import argparse
import json
import os
import uuid
from datetime import datetime

import config
from stiffness_estimator import estimate_stiffness, save_stiffness_stats
from stiffness_grader import grade_stiffness_stats, save_grades


SECTION_ORDER = ["Upper Back", "Mid Back", "Lower Back"]

SECTION_DISPLAY_NAMES = {
    "Upper Back": "Upper Back",
    "Mid Back": "Mid Back",
    "Lower Back": "Lower Back",
    "Unknown": "Unknown",
}

GRADE_PRIORITY = {
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
}

DISCLAIMER = (
    "本报告仅用于僵硬程度参考和按摩参数参考，不构成医疗诊断。"
    "如存在疼痛、麻木、外伤、炎症或其他不适，应咨询专业医生或康复治疗师。"
)


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_or_create_stats(user_id, data_path=None):
    stats_path = os.path.join(config.output_dir, f"{user_id}_stiffness_stats.json")
    if data_path is None and os.path.isfile(stats_path):
        return _load_json(stats_path)
    stats = estimate_stiffness(user_id, data_path)
    save_stiffness_stats(stats, user_id)
    return stats


def _grade_lookup(items, key_name):
    return {item[key_name]: item for item in items}


def _top_point(points, grades_by_point_id, section=None):
    candidates = points
    if section is not None:
        candidates = [point for point in points if point.get("section") == section]
    if not candidates:
        return None

    point = max(candidates, key=lambda item: item["max_stiffness_N_m"])
    grade = grades_by_point_id.get(point["point_id"], {})
    return {
        "point_id": point["point_id"],
        "region": point.get("region", "unknown"),
        "display_name": point.get("display_name", "未知区域"),
        "x_mm": point.get("x_mm"),
        "y_mm": point.get("y_mm"),
        "mean_stiffness_N_m": point["mean_stiffness_N_m"],
        "max_stiffness_N_m": point["max_stiffness_N_m"],
        "grade": grade.get("grade"),
        "label": grade.get("label"),
        "score": grade.get("score"),
    }


def _side_difference(points, section=None):
    candidates = points
    if section is not None:
        candidates = [point for point in points if point.get("section") == section]

    left_values = [
        point["mean_stiffness_N_m"]
        for point in candidates
        if point.get("x_mm") is not None and point["x_mm"] < 0
    ]
    right_values = [
        point["mean_stiffness_N_m"]
        for point in candidates
        if point.get("x_mm") is not None and point["x_mm"] > 0
    ]

    left_mean = sum(left_values) / len(left_values) if left_values else None
    right_mean = sum(right_values) / len(right_values) if right_values else None
    difference = None
    higher_side = "insufficient_data"
    if left_mean is not None and right_mean is not None:
        difference = abs(left_mean - right_mean)
        higher_side = "left" if left_mean > right_mean else "right"
        if difference < 1e-6:
            higher_side = "balanced"

    return {
        "left_mean_stiffness_N_m": round(left_mean, 2) if left_mean is not None else None,
        "right_mean_stiffness_N_m": round(right_mean, 2) if right_mean is not None else None,
        "difference_N_m": round(difference, 2) if difference is not None else None,
        "higher_stiffness_side": higher_side,
    }


def _section_results(stats, grades):
    section_stats_by_name = _grade_lookup(stats.get("sections", []), "section")
    section_grades_by_name = _grade_lookup(grades.get("sections", []), "section")
    grades_by_point_id = _grade_lookup(grades.get("points", []), "point_id")

    results = []
    for section in SECTION_ORDER:
        section_stats = section_stats_by_name.get(section)
        section_grade = section_grades_by_name.get(section)

        if section_stats is None:
            results.append({
                "section": section,
                "display_name": SECTION_DISPLAY_NAMES[section],
                "sample_count": 0,
                "mean_stiffness_N_m": None,
                "max_stiffness_N_m": None,
                "std_stiffness_N_m": None,
                "grade": None,
                "label": "No Data",
                "highest_stiffness_point": None,
                "left_right_difference": _side_difference(stats.get("points", []), section),
            })
            continue

        results.append({
            "section": section,
            "display_name": SECTION_DISPLAY_NAMES[section],
            "sample_count": section_stats["sample_count"],
            "mean_stiffness_N_m": section_stats["mean_stiffness_N_m"],
            "max_stiffness_N_m": section_stats["max_stiffness_N_m"],
            "std_stiffness_N_m": section_stats["std_stiffness_N_m"],
            "grade": section_grade.get("grade") if section_grade else None,
            "label": section_grade.get("label") if section_grade else None,
            "score": section_grade.get("score") if section_grade else None,
            "highest_stiffness_point": _top_point(
                stats.get("points", []),
                grades_by_point_id,
                section,
            ),
            "left_right_difference": _side_difference(stats.get("points", []), section),
        })
    return results


def _recommended_focus_points(stats, grades, limit=5):
    grades_by_point_id = _grade_lookup(grades.get("points", []), "point_id")
    graded_points = []
    for point in stats.get("points", []):
        grade = grades_by_point_id.get(point["point_id"], {})
        graded_points.append({
            "point_id": point["point_id"],
            "region": point.get("region", "unknown"),
            "display_name": point.get("display_name", "未知区域"),
            "section": point.get("section", "Unknown"),
            "x_mm": point.get("x_mm"),
            "y_mm": point.get("y_mm"),
            "mean_stiffness_N_m": point["mean_stiffness_N_m"],
            "max_stiffness_N_m": point["max_stiffness_N_m"],
            "grade": grade.get("grade"),
            "label": grade.get("label"),
            "score": grade.get("score", 0.0),
        })

    graded_points.sort(
        key=lambda item: (
            GRADE_PRIORITY.get(item.get("grade"), 0),
            item.get("score", 0.0),
            item["mean_stiffness_N_m"],
        ),
        reverse=True,
    )
    return graded_points[:limit]


def _massage_suggestions(overall_grade, focus_points):
    suggestions = [
        "以低到中等力度逐步加压，优先观察压入深度和主观反馈。",
        "对 C/D 等级关注点采用短时、多次、渐进式放松，避免长时间固定重压。",
        "左右差异明显时，可先从僵硬程度较低一侧热身，再过渡到较高一侧。",
        "配合温和肩背伸展和呼吸放松，作为按摩参数参考而非治疗方案。",
    ]
    if overall_grade == "D" or any(point.get("grade") == "D" for point in focus_points):
        suggestions.insert(0, "存在 Severe 参考等级点位，建议降低初始力度并缩短单点停留时间。")
    return suggestions


def build_report(user_id, stats, grades):
    """Build structured stiffness report data."""
    focus_points = _recommended_focus_points(stats, grades)
    overall = grades["overall"]

    report = {
        "report_id": f"stiffness-{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "overall_grade": overall["grade"],
        "overall_label": overall["label"],
        "overall_score": overall["score"],
        "grade_mode": grades["grade_mode"],
        "reference_stiffness_N_m": grades["reference_stiffness_N_m"],
        "overall_mean_stiffness_N_m": stats["overall"]["mean_stiffness_N_m"],
        "overall_max_stiffness_N_m": stats["overall"]["max_stiffness_N_m"],
        "overall_std_stiffness_N_m": stats["overall"]["std_stiffness_N_m"],
        "valid_sample_count": stats["valid_sample_count"],
        "skipped_sample_count": stats["skipped_sample_count"],
        "sections": _section_results(stats, grades),
        "regions": grades.get("regions", []),
        "left_right_difference": _side_difference(stats.get("points", [])),
        "recommended_focus_points": focus_points,
        "stretching_and_massage_suggestions": _massage_suggestions(
            overall["grade"],
            focus_points,
        ),
        "disclaimer": DISCLAIMER,
    }
    return report


def save_report_json(report, user_id):
    os.makedirs(config.output_dir, exist_ok=True)
    output_path = os.path.join(config.output_dir, f"{user_id}_stiffness_report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return output_path


def _format_value(value, suffix=""):
    if value is None:
        return "No Data"
    return f"{value}{suffix}"


def render_markdown(report):
    lines = [
        f"# 背部僵硬程度参考报告 - {report['user_id']}",
        "",
        f"- Report ID: `{report['report_id']}`",
        f"- Created At: {report['created_at']}",
        f"- Overall: {report['overall_grade']} / {report['overall_label']}",
        f"- Grade Mode: {report['grade_mode']}",
        f"- Reference Stiffness: {report['reference_stiffness_N_m']} N/m",
        f"- Overall Mean Stiffness: {report['overall_mean_stiffness_N_m']} N/m",
        "",
        "## 分区结果",
        "",
        "| Section | Grade | Mean N/m | Max N/m | Highest Point | Left/Right Difference |",
        "|---|---:|---:|---:|---|---:|",
    ]

    for section in report["sections"]:
        top_point = section.get("highest_stiffness_point")
        if top_point:
            top_point_text = (
                f"{top_point['point_id']} "
                f"({top_point.get('grade')}/{top_point.get('label')})"
            )
        else:
            top_point_text = "No Data"
        diff = section["left_right_difference"].get("difference_N_m")
        lines.append(
            "| {section} | {grade} | {mean} | {max_value} | {top_point} | {diff} |".format(
                section=section["section"],
                grade=section.get("grade") or "No Data",
                mean=_format_value(section.get("mean_stiffness_N_m")),
                max_value=_format_value(section.get("max_stiffness_N_m")),
                top_point=top_point_text,
                diff=_format_value(diff),
            )
        )

    lines.extend([
        "",
        "## 推荐关注点",
        "",
    ])

    for index, point in enumerate(report["recommended_focus_points"], start=1):
        lines.append(
            f"{index}. {point['point_id']} - {point['section']} / "
            f"{point['display_name']}: {point['grade']} {point['label']}, "
            f"mean {point['mean_stiffness_N_m']} N/m, score {point['score']}"
        )

    lines.extend([
        "",
        "## 拉伸 / 按摩建议",
        "",
    ])
    for suggestion in report["stretching_and_massage_suggestions"]:
        lines.append(f"- {suggestion}")

    lines.extend([
        "",
        "## Disclaimer",
        "",
        report["disclaimer"],
        "",
    ])
    return "\n".join(lines)


def save_report_markdown(report, user_id):
    output_path = os.path.join(config.output_dir, f"{user_id}_stiffness_report.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))
    return output_path


def generate_report(user_id, data_path=None, mode="relative"):
    stats = load_or_create_stats(user_id, data_path)
    grades = grade_stiffness_stats(stats, mode=mode)
    save_grades(grades, user_id)
    report = build_report(user_id, stats, grades)
    json_path = save_report_json(report, user_id)
    markdown_path = save_report_markdown(report, user_id)
    return report, json_path, markdown_path


def main():
    parser = argparse.ArgumentParser(description="Generate back stiffness report.")
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--data", default=None, help="Optional source CSV path.")
    parser.add_argument(
        "--mode",
        choices=["relative", "absolute"],
        default="relative",
        help="Grade relative to user average or fixed N/m reference.",
    )
    args = parser.parse_args()

    report, _, _ = generate_report(args.user_id, args.data, args.mode)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
