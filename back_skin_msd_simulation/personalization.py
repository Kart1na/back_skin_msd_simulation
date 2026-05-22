"""Generate a conservative initial back model from user demographics.

Adjusts default MSD parameters based on age, sex, and BMI to produce
a first-pass personalised model *before* any massage data is available.

Usage:
    python personalization.py --user_id user_001 --age 25 --sex male --bmi 24.2 --region lower_back
"""

import argparse
import json
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

# ---- default baseline (mirrors config.py) --------------------------------

DEFAULTS = {
    "skin_thickness_mm": 3.0,
    "muscle_fat_thickness_mm": 25.0,
    "bone_support_thickness_mm": 8.0,
    "E_skin_kPa": 40.0,
    "E_muscle_fat_kPa": 45.0,
    "E_bone_support_kPa": 200.0,
    "k_skin_N_m": 1800.0,
    "k_muscle_fat_N_m": 3500.0,
    "k_bone_support_N_m": 15000.0,
    "damping": 0.85,
    "mu_static": 0.9,
    "mu_dynamic": 0.45,
    "contact_tangent_gain": 20.0,
}

# ---- region-specific scale factors ---------------------------------------

REGION_SCALES = {
    "upper_back": {
        "muscle_fat_thickness_mm": 0.85,
        "E_muscle_fat_kPa": 1.15,
        "k_muscle_fat_N_m": 1.10,
    },
    "middle_back": {
        "muscle_fat_thickness_mm": 1.0,
        "E_muscle_fat_kPa": 1.0,
        "k_muscle_fat_N_m": 1.0,
    },
    "lower_back": {
        "muscle_fat_thickness_mm": 1.20,
        "E_muscle_fat_kPa": 0.90,
        "k_muscle_fat_N_m": 0.90,
    },
}


def generate_initial_back_model(
    user_id: str,
    age: int,
    sex: str,
    bmi: float,
    region: str = "middle_back",
) -> dict:
    """Return a dict of MSD parameters adjusted for the given user profile.

    Adjustment rules (conservative, multiplicative):
        BMI  -> muscle_fat_thickness, E_muscle_fat, k_muscle_fat, damping
        age  -> E_skin, k_skin, damping
        sex  -> small corrections on stiffness and thickness
    """
    params = dict(DEFAULTS)

    # ---- BMI adjustments ---------------------------------------------------
    # Baseline BMI assumed 22.0 (normal).  Higher BMI => thicker / softer fat.
    bmi_ref = 22.0
    bmi_ratio = bmi / bmi_ref

    params["muscle_fat_thickness_mm"] *= 0.8 + 0.2 * bmi_ratio
    params["E_muscle_fat_kPa"] *= 1.1 - 0.1 * bmi_ratio
    params["k_muscle_fat_N_m"] *= 1.1 - 0.1 * bmi_ratio
    params["damping"] *= 0.95 + 0.05 * bmi_ratio

    # ---- age adjustments ---------------------------------------------------
    # Baseline age assumed 30.  Older skin is stiffer; damping increases.
    age_ref = 30
    age_ratio = age / age_ref

    params["E_skin_kPa"] *= 0.9 + 0.1 * age_ratio
    params["k_skin_N_m"] *= 0.9 + 0.1 * age_ratio
    params["damping"] *= 0.97 + 0.03 * age_ratio

    # ---- sex adjustments ---------------------------------------------------
    sex_lower = sex.strip().lower()
    if sex_lower == "female":
        params["muscle_fat_thickness_mm"] *= 1.08
        params["E_muscle_fat_kPa"] *= 0.95
        params["k_muscle_fat_N_m"] *= 0.95
        params["k_skin_N_m"] *= 0.97
    elif sex_lower == "male":
        params["muscle_fat_thickness_mm"] *= 0.95
        params["E_muscle_fat_kPa"] *= 1.03
        params["k_muscle_fat_N_m"] *= 1.03

    # ---- region adjustments ------------------------------------------------
    region_key = region.strip().lower()
    scales = REGION_SCALES.get(region_key, REGION_SCALES["middle_back"])
    for key, factor in scales.items():
        params[key] *= factor

    # ---- clamp to physically plausible ranges ------------------------------
    params["k_skin_N_m"] = max(800.0, min(params["k_skin_N_m"], 5000.0))
    params["k_muscle_fat_N_m"] = max(1500.0, min(params["k_muscle_fat_N_m"], 9000.0))
    params["damping"] = max(0.4, min(params["damping"], 1.5))
    params["mu_static"] = max(0.5, min(params["mu_static"], 1.2))
    params["mu_dynamic"] = max(0.2, min(params["mu_dynamic"], 0.8))

    # ---- assemble output ---------------------------------------------------
    model = {
        "user_id": user_id,
        "age": age,
        "sex": sex_lower,
        "bmi": round(bmi, 2),
        "region": region_key,
        "model_type": "initial",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    for k, v in params.items():
        model[k] = round(v, 4)

    return model


def save_initial_model(model: dict) -> str:
    """Persist the initial model JSON and return the file path."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{model['user_id']}_initial_back_model.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2, ensure_ascii=False)
    return filepath


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate conservative initial back model from user demographics."
    )
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--age", type=int, required=True)
    parser.add_argument("--sex", required=True, choices=["male", "female"])
    parser.add_argument("--bmi", type=float, required=True)
    parser.add_argument(
        "--region",
        default="middle_back",
        choices=["upper_back", "middle_back", "lower_back"],
    )
    args = parser.parse_args()

    model = generate_initial_back_model(
        user_id=args.user_id,
        age=args.age,
        sex=args.sex,
        bmi=args.bmi,
        region=args.region,
    )
    path = save_initial_model(model)
    print(f"Initial back model saved to: {path}")
    print(json.dumps(model, indent=2))


if __name__ == "__main__":
    main()
