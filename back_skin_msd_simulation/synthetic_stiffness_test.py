"""Generate realistic multi-region stiffness-test data for EMMA-style reports."""

import argparse
import csv
import json
import os

import numpy as np

import config
from back_region_map import locate_region
from user_model import load_user_back_model


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")

CSV_FIELDS = [
    "time_s",
    "point_id",
    "section",
    "region",
    "x_mm",
    "y_mm",
    "normal_force_N",
    "indentation_mm",
    "stiffness_ground_truth_N_m",
    "stiffness_factor",
    "risk_level",
    "is_hotspot",
    "sample_index",
]

DETECTION_POINTS = [
    {"point_id": "upper_back_left", "section": "Upper Back", "region": "upper_back_left", "x_mm": -55.0, "y_mm": 105.0},
    {"point_id": "upper_back_right", "section": "Upper Back", "region": "upper_back_right", "x_mm": 55.0, "y_mm": 105.0},
    {"point_id": "shoulder_left", "section": "Upper Back", "region": "shoulder_left", "x_mm": -85.0, "y_mm": 125.0},
    {"point_id": "shoulder_right", "section": "Upper Back", "region": "shoulder_right", "x_mm": 85.0, "y_mm": 125.0},
    {"point_id": "middle_back_left", "section": "Mid Back", "region": "middle_back_left", "x_mm": -45.0, "y_mm": 10.0},
    {"point_id": "middle_back_right", "section": "Mid Back", "region": "middle_back_right", "x_mm": 45.0, "y_mm": 10.0},
    {"point_id": "mid_paraspinal_left", "section": "Mid Back", "region": "mid_paraspinal_left", "x_mm": -25.0, "y_mm": 20.0},
    {"point_id": "mid_paraspinal_right", "section": "Mid Back", "region": "mid_paraspinal_right", "x_mm": 25.0, "y_mm": 20.0},
    {"point_id": "lower_back_left", "section": "Lower Back", "region": "lower_back_left", "x_mm": -45.0, "y_mm": -95.0},
    {"point_id": "lower_back_right", "section": "Lower Back", "region": "lower_back_right", "x_mm": 45.0, "y_mm": -95.0},
    {"point_id": "lumbar_left", "section": "Lower Back", "region": "lumbar_left", "x_mm": -25.0, "y_mm": -115.0},
    {"point_id": "lumbar_right", "section": "Lower Back", "region": "lumbar_right", "x_mm": 25.0, "y_mm": -115.0},
]

REGION_STIFFNESS_FACTORS = {
    "upper_back_left": 1.00,
    "upper_back_right": 1.05,
    "shoulder_left": 1.10,
    "shoulder_right": 1.12,
    "middle_back_left": 1.05,
    "middle_back_right": 1.12,
    "mid_paraspinal_left": 1.08,
    "mid_paraspinal_right": 1.20,
    "lower_back_left": 1.15,
    "lower_back_right": 1.25,
    "lumbar_left": 1.18,
    "lumbar_right": 1.35,
}

PROFILES = {
    "realistic",
    "mild_asymmetry",
    "severe_right_lower",
    "upper_shoulder_tension",
}


def compute_user_base_k_eff(user_model):
    """Compute user base effective stiffness using skin and muscle-fat springs."""
    k_skin = float(getattr(user_model, "k_skin_N_m", config.k_skin_N_m))
    k_muscle_fat = float(
        getattr(user_model, "k_muscle_fat_N_m", config.k_muscle_fat_N_m)
    )
    if k_skin <= 0 or k_muscle_fat <= 0:
        k_skin = float(config.k_skin_N_m)
        k_muscle_fat = float(config.k_muscle_fat_N_m)
    return 1.0 / (1.0 / k_skin + 1.0 / k_muscle_fat)


def _profile_factor(region, profile):
    factor = 1.0
    is_hotspot = False

    if profile == "mild_asymmetry":
        if region.endswith("_right"):
            factor *= 1.10
        elif region.endswith("_left"):
            factor *= 0.98
    elif profile == "severe_right_lower":
        if region == "lower_back_right":
            factor *= 1.45
            is_hotspot = True
        elif region == "lumbar_right":
            factor *= 1.60
            is_hotspot = True
        elif region == "middle_back_right":
            factor *= 1.25
            is_hotspot = True
    elif profile == "upper_shoulder_tension":
        if region in ("shoulder_left", "shoulder_right"):
            factor *= 1.40
            is_hotspot = True
        elif region in ("upper_back_left", "upper_back_right"):
            factor *= 1.25
            is_hotspot = True

    return factor, is_hotspot


def _risk_level_for_factor(stiffness_factor):
    if stiffness_factor >= 1.45:
        return "high"
    if stiffness_factor >= 1.15:
        return "medium"
    return "low"


def generate_synthetic_stiffness_test(
    user_id,
    profile="realistic",
    repeats=5,
    force_steps=7,
    seed=20260515,
):
    """Generate a multi-point, multi-repeat stiffness-test CSV."""
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of: {', '.join(sorted(PROFILES))}")

    rng = np.random.default_rng(seed)
    user_model, model_type = load_user_back_model(user_id)
    base_k_eff = compute_user_base_k_eff(user_model)

    rows = []
    time_s = 0.0
    sample_index = 0

    for point in DETECTION_POINTS:
        if -12.0 <= point["x_mm"] <= 12.0:
            continue

        base_factor = REGION_STIFFNESS_FACTORS[point["region"]]
        profile_factor, profile_hotspot = _profile_factor(point["region"], profile)
        point_random_factor = rng.uniform(0.95, 1.05)
        nominal_factor = base_factor * profile_factor * point_random_factor
        nominal_k = base_k_eff * nominal_factor
        anatomical_region = locate_region(point["x_mm"], point["y_mm"])

        for repeat_index in range(repeats):
            repeat_k = nominal_k * rng.uniform(0.97, 1.03)
            hysteresis_offset_mm = rng.uniform(-0.15, 0.15)

            for force in np.linspace(2.0, 12.0, force_steps):
                measured_force = max(0.1, force + rng.normal(0.0, 0.15))
                nonlinear_factor = 1.0 + 0.015 * max(measured_force - 6.0, 0.0)
                effective_k = repeat_k * nonlinear_factor
                indentation_mm = measured_force / effective_k * 1000.0
                indentation_mm += hysteresis_offset_mm
                indentation_mm += rng.normal(0.0, 0.08)
                indentation_mm = max(indentation_mm, 0.2)

                stiffness_factor = effective_k / base_k_eff
                rows.append({
                    "time_s": round(time_s, 4),
                    "point_id": point["point_id"],
                    "section": point["section"],
                    "region": point["region"],
                    "x_mm": round(point["x_mm"], 2),
                    "y_mm": round(point["y_mm"], 2),
                    "normal_force_N": round(measured_force, 4),
                    "indentation_mm": round(indentation_mm, 4),
                    "stiffness_ground_truth_N_m": round(effective_k, 2),
                    "stiffness_factor": round(stiffness_factor, 4),
                    "risk_level": anatomical_region.get(
                        "risk_level",
                        _risk_level_for_factor(stiffness_factor),
                    ),
                    "is_hotspot": bool(profile_hotspot),
                    "sample_index": sample_index,
                })
                time_s += 0.08
                sample_index += 1

    os.makedirs(USER_DATA_DIR, exist_ok=True)
    output_path = os.path.join(USER_DATA_DIR, f"{user_id}_stiffness_test.csv")
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    return output_path, {
        "user_id": user_id,
        "profile": profile,
        "model_type": model_type,
        "base_k_eff_N_m": round(base_k_eff, 2),
        "row_count": len(rows),
        "point_count": len(DETECTION_POINTS),
        "repeats": repeats,
        "force_steps": force_steps,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate realistic multi-region back stiffness test data."
    )
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="realistic")
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--force_steps", type=int, default=7)
    parser.add_argument("--seed", type=int, default=20260515)
    args = parser.parse_args()

    output_path, summary = generate_synthetic_stiffness_test(
        user_id=args.user_id,
        profile=args.profile,
        repeats=args.repeats,
        force_steps=args.force_steps,
        seed=args.seed,
    )
    summary["output_path"] = output_path
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
