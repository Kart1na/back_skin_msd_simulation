"""Grade back stiffness values for massage-parameter reference reports."""

import argparse
import json
import os

import config


GRADE_RULES = [
    ("A", "Mild", 0.0, 0.85),
    ("B", "Moderate", 0.85, 1.15),
    ("C", "High", 1.15, 1.45),
    ("D", "Severe", 1.45, float("inf")),
]

ABSOLUTE_REFERENCE_STIFFNESS_N_M = 2200.0


def grade_score(score):
    """Return A/B/C/D grade metadata for a normalized stiffness score."""
    for grade, label, min_score, max_score in GRADE_RULES:
        if min_score <= score < max_score:
            return {
                "grade": grade,
                "label": label,
                "score": round(score, 3),
            }
    return {
        "grade": "D",
        "label": "Severe",
        "score": round(score, 3),
    }


def _safe_average(values):
    clean_values = [float(v) for v in values if v is not None]
    if not clean_values:
        return 0.0
    return sum(clean_values) / len(clean_values)


def grade_stiffness_value(
    stiffness_N_m,
    reference_stiffness_N_m,
):
    """Grade a single stiffness value against a reference stiffness."""
    if reference_stiffness_N_m <= 0:
        reference_stiffness_N_m = ABSOLUTE_REFERENCE_STIFFNESS_N_M
    score = float(stiffness_N_m) / float(reference_stiffness_N_m)
    result = grade_score(score)
    result["stiffness_N_m"] = round(float(stiffness_N_m), 2)
    result["reference_stiffness_N_m"] = round(float(reference_stiffness_N_m), 2)
    return result


def grade_stiffness_stats(stats, mode="relative"):
    """Grade point, region, and section stiffness statistics.

    relative mode uses the user's overall mean stiffness as the reference.
    absolute mode uses a fixed reference value in N/m.
    """
    if mode not in ("relative", "absolute"):
        raise ValueError("mode must be 'relative' or 'absolute'")

    overall_mean = float(stats.get("overall", {}).get("mean_stiffness_N_m", 0.0))
    if mode == "relative":
        reference = overall_mean or ABSOLUTE_REFERENCE_STIFFNESS_N_M
    else:
        reference = ABSOLUTE_REFERENCE_STIFFNESS_N_M

    point_grades = []
    for point in stats.get("points", []):
        graded = grade_stiffness_value(point["mean_stiffness_N_m"], reference)
        graded.update({
            "point_id": point["point_id"],
            "region": point.get("region", "unknown"),
            "section": point.get("section", "Unknown"),
            "x_mm": point.get("x_mm"),
            "y_mm": point.get("y_mm"),
        })
        point_grades.append(graded)

    region_grades = []
    for region in stats.get("regions", []):
        graded = grade_stiffness_value(region["mean_stiffness_N_m"], reference)
        graded.update({
            "region": region["region"],
            "display_name": region.get("display_name", region["region"]),
            "section": region.get("section", "Unknown"),
        })
        region_grades.append(graded)

    section_grades = []
    for section in stats.get("sections", []):
        graded = grade_stiffness_value(section["mean_stiffness_N_m"], reference)
        graded.update({"section": section["section"]})
        section_grades.append(graded)

    overall_grade = grade_stiffness_value(overall_mean, reference)
    overall_grade["grade_mode"] = mode

    return {
        "user_id": stats.get("user_id"),
        "grade_mode": mode,
        "reference_stiffness_N_m": round(reference, 2),
        "absolute_reference_stiffness_N_m": ABSOLUTE_REFERENCE_STIFFNESS_N_M,
        "overall": overall_grade,
        "points": point_grades,
        "regions": region_grades,
        "sections": section_grades,
    }


def load_stats(user_id, stats_path=None):
    if stats_path is None:
        stats_path = os.path.join(config.output_dir, f"{user_id}_stiffness_stats.json")
    with open(stats_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_grades(grades, user_id):
    os.makedirs(config.output_dir, exist_ok=True)
    output_path = os.path.join(config.output_dir, f"{user_id}_stiffness_grades.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(grades, f, ensure_ascii=False, indent=2)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Grade back stiffness statistics.")
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--stats", default=None, help="Path to stiffness stats JSON.")
    parser.add_argument(
        "--mode",
        choices=["relative", "absolute"],
        default="relative",
        help="Grade relative to user average or fixed N/m reference.",
    )
    args = parser.parse_args()

    stats = load_stats(args.user_id, args.stats)
    grades = grade_stiffness_stats(stats, mode=args.mode)
    save_grades(grades, args.user_id)
    print(json.dumps(grades, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
