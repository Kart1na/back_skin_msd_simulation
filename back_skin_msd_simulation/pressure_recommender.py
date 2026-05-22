"""Pressure recommendation based on personalized back model and region risk."""

import argparse
import json

import config
from back_region_map import get_region_by_name
from user_model import load_user_back_model


RISK_MULTIPLIERS = {
    "low": 1.0,
    "medium": 0.85,
    "high": 0.5,
}

RISK_MESSAGES = {
    "low": "低风险区域，仍需保持渐进加力并监测反馈。",
    "medium": "中风险区域，建议采用保守力度并持续观察压入深度。",
    "high": "高风险区域或避让区域，不建议主动施加按摩力。",
}


def clamp(value, min_value, max_value):
    """Clamp value into the inclusive range [min_value, max_value]."""
    return max(min_value, min(value, max_value))


def compute_effective_stiffness_N_m(user_model):
    """Compute effective stiffness using a two-spring series approximation."""
    k_skin = float(getattr(user_model, "k_skin_N_m", config.k_skin_N_m))
    k_muscle_fat = float(
        getattr(user_model, "k_muscle_fat_N_m", config.k_muscle_fat_N_m)
    )

    if k_skin <= 0 or k_muscle_fat <= 0:
        k_skin = float(config.k_skin_N_m)
        k_muscle_fat = float(config.k_muscle_fat_N_m)

    return 1.0 / (1.0 / k_skin + 1.0 / k_muscle_fat)


def recommend_pressure(user_id, region_name):
    """Recommend a safe normal force for the user and anatomical region."""
    model, model_type = load_user_back_model(user_id)
    region = get_region_by_name(region_name)
    target_min, target_max = region["target_indentation_range_mm"]
    target_mid = (target_min + target_max) / 2.0
    k_eff = compute_effective_stiffness_N_m(model)

    if region["avoid"]:
        force = 0.0
    else:
        raw_force = k_eff * (target_mid / 1000.0)
        multiplier = RISK_MULTIPLIERS.get(region["risk_level"], 0.5)
        force = raw_force * multiplier
        safe_min, safe_max = region["base_force_range_N"]
        force = clamp(force, safe_min, safe_max)

    return {
        "user_id": user_id,
        "region": region["name"],
        "display_name": region["display_name"],
        "recommended_force_N": round(force, 2),
        "safe_force_range_N": region["base_force_range_N"],
        "target_indentation_range_mm": region["target_indentation_range_mm"],
        "target_indentation_mm": round(target_mid, 2),
        "risk_level": region["risk_level"],
        "risk_message": RISK_MESSAGES.get(region["risk_level"], RISK_MESSAGES["high"]),
        "avoid": region["avoid"],
        "model_type": model_type,
        "k_eff_N_m": round(k_eff, 2),
    }


def main():
    parser = argparse.ArgumentParser(description="Recommend massage pressure.")
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args()

    result = recommend_pressure(args.user_id, args.region)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
