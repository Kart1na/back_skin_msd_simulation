"""Parameter fitting from first-massage force-displacement data.

Two-tier approach:
    1. Fast path:  fit effective stiffness k_eff from F = k_eff * indentation,
       then map k_eff to k_skin and k_muscle_fat via series-spring analogy.
    2. Full path:  run_simulation_and_compute_loss() interface reserved for
       future full MSD simulation-based optimisation.

Usage:
    python parameter_fitting.py --user_id user_001
"""

import argparse
import csv
import json
import os
from datetime import datetime, timezone

import numpy as np
from scipy.optimize import minimize

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")

# physically plausible bounds
BOUNDS = {
    "k_skin_N_m": (800.0, 5000.0),
    "k_muscle_fat_N_m": (1500.0, 9000.0),
    "damping": (0.4, 1.5),
    "mu_static": (0.5, 1.2),
    "mu_dynamic": (0.2, 0.8),
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_massage_csv(user_id):
    """Load the first-massage CSV into column arrays."""
    filepath = os.path.join(USER_DATA_DIR, "{}_first_massage.csv".format(user_id))
    if not os.path.isfile(filepath):
        raise FileNotFoundError("Massage CSV not found: {}".format(filepath))

    data = {}
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for key, val in row.items():
                data.setdefault(key, []).append(float(val))

    return {k: np.array(v) for k, v in data.items()}


def load_initial_model(user_id):
    filepath = os.path.join(OUTPUT_DIR, "{}_initial_back_model.json".format(user_id))
    if not os.path.isfile(filepath):
        raise FileNotFoundError("Initial model not found: {}".format(filepath))
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Simplified k_eff fitting (fast path)
# ---------------------------------------------------------------------------

def fit_effective_stiffness(force_N, indentation_mm):
    """Fit k_eff (N/m) from F = k_eff * indentation via least-squares.

    Only uses data where force > 0.5 N to avoid noisy near-zero region.
    """
    mask = force_N > 0.5
    F = force_N[mask]
    d = indentation_mm[mask] * 1e-3  # mm -> m

    if len(F) < 3:
        raise ValueError("Not enough valid data points for fitting.")

    k_eff = float(np.sum(F * d) / np.sum(d * d))
    return k_eff


def map_keff_to_layer_stiffness(k_eff, initial_model):
    """Map overall k_eff to individual layer stiffnesses.

    Series-spring model:  1/k_eff = 1/k_skin + 1/k_muscle_fat
    We keep the ratio k_skin / k_muscle_fat from the initial model and
    solve for absolute values that satisfy the series constraint.
    """
    k_skin_init = initial_model.get("k_skin_N_m", 1800.0)
    k_mf_init = initial_model.get("k_muscle_fat_N_m", 3500.0)
    ratio = k_skin_init / k_mf_init  # preserve ratio

    # 1/k_eff = 1/k_s + 1/k_mf,  k_s = ratio * k_mf
    # => 1/k_eff = 1/(ratio*k_mf) + 1/k_mf = (1 + 1/ratio)/k_mf
    k_mf = k_eff * (1.0 + 1.0 / ratio)
    k_skin = ratio * k_mf

    k_skin = float(np.clip(k_skin, *BOUNDS["k_skin_N_m"]))
    k_mf = float(np.clip(k_mf, *BOUNDS["k_muscle_fat_N_m"]))
    return k_skin, k_mf


# ---------------------------------------------------------------------------
# Full simulation-based optimisation (reserved interface)
# ---------------------------------------------------------------------------

def run_simulation_and_compute_loss(params, real_force, real_indentation_mm):
    """Run the MSD simulation with *params* and return MSE loss.

    Currently uses the simplified spring model for cost efficiency.
    Replace the body of this function with a full Simulator call when
    computational budget allows.
    """
    k_skin = params.get("k_skin_N_m", 1800.0)
    k_mf = params.get("k_muscle_fat_N_m", 3500.0)

    # series spring equivalent
    k_eq = 1.0 / (1.0 / k_skin + 1.0 / k_mf)

    sim_indentation_mm = (real_force / k_eq) * 1000.0  # m -> mm
    loss = float(np.mean((sim_indentation_mm - real_indentation_mm) ** 2))
    return loss


def _scipy_objective(x, real_force, real_indentation_mm):
    """Objective wrapper for scipy.optimize.minimize."""
    params = {
        "k_skin_N_m": x[0],
        "k_muscle_fat_N_m": x[1],
        "damping": x[2],
    }
    return run_simulation_and_compute_loss(params, real_force, real_indentation_mm)


def fit_full_optimization(real_force, real_indentation_mm, initial_model):
    """Run scipy L-BFGS-B optimisation over k_skin, k_muscle_fat, damping."""
    x0 = [
        initial_model.get("k_skin_N_m", 1800.0),
        initial_model.get("k_muscle_fat_N_m", 3500.0),
        initial_model.get("damping", 0.85),
    ]
    bounds_list = [
        BOUNDS["k_skin_N_m"],
        BOUNDS["k_muscle_fat_N_m"],
        BOUNDS["damping"],
    ]

    result = minimize(
        _scipy_objective,
        x0,
        args=(real_force, real_indentation_mm),
        method="L-BFGS-B",
        bounds=bounds_list,
        options={"maxiter": 500, "ftol": 1e-12},
    )

    best = {
        "k_skin_N_m": float(result.x[0]),
        "k_muscle_fat_N_m": float(result.x[1]),
        "damping": float(result.x[2]),
    }
    return best, float(result.fun)


# ---------------------------------------------------------------------------
# Friction parameter estimation
# ---------------------------------------------------------------------------

def estimate_friction_params(data, initial_model):
    """Rough friction coefficient estimation from tangential/normal force ratio."""
    F_n = data["normal_force_N"]
    F_t = data["tangential_force_N"]

    mask = F_n > 1.0
    if np.sum(mask) < 5:
        return {
            "mu_static": initial_model.get("mu_static", 0.9),
            "mu_dynamic": initial_model.get("mu_dynamic", 0.45),
        }

    ratio = F_t[mask] / F_n[mask]
    mu_est = float(np.median(ratio))
    mu_static = np.clip(mu_est * 1.3, *BOUNDS["mu_static"])
    mu_dynamic = np.clip(mu_est * 0.7, *BOUNDS["mu_dynamic"])
    return {"mu_static": float(mu_static), "mu_dynamic": float(mu_dynamic)}


# ---------------------------------------------------------------------------
# Main calibration pipeline
# ---------------------------------------------------------------------------

def calibrate_user_model(user_id, method="auto"):
    """End-to-end calibration: load data, fit params, save calibrated model.

    method: "fast" – k_eff only, "full" – scipy optimisation, "auto" – try full.
    """
    data = load_massage_csv(user_id)
    initial_model = load_initial_model(user_id)

    force = data["normal_force_N"]
    indentation = data["indentation_mm"]

    if method == "fast":
        k_eff = fit_effective_stiffness(force, indentation)
        k_skin, k_mf = map_keff_to_layer_stiffness(k_eff, initial_model)
        fitted = {
            "k_skin_N_m": k_skin,
            "k_muscle_fat_N_m": k_mf,
            "damping": initial_model.get("damping", 0.85),
        }
        loss = run_simulation_and_compute_loss(fitted, force, indentation)
    else:
        fitted, loss = fit_full_optimization(force, indentation, initial_model)

    friction = estimate_friction_params(data, initial_model)

    calibrated = {
        "user_id": user_id,
        "age": initial_model.get("age"),
        "sex": initial_model.get("sex"),
        "bmi": initial_model.get("bmi"),
        "region": initial_model.get("region"),
        "k_skin_N_m": round(fitted["k_skin_N_m"], 4),
        "k_muscle_fat_N_m": round(fitted["k_muscle_fat_N_m"], 4),
        "damping": round(fitted["damping"], 4),
        "mu_static": round(friction["mu_static"], 4),
        "mu_dynamic": round(friction["mu_dynamic"], 4),
        "contact_tangent_gain": initial_model.get("contact_tangent_gain", 20.0),
        "calibration_loss": round(loss, 6),
        "calibrated_from": f"{user_id}_first_massage.csv",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, f"{user_id}_calibrated_back_model.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(calibrated, f, indent=2, ensure_ascii=False)

    return filepath


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fit MSD parameters from first-massage force-displacement data."
    )
    parser.add_argument("--user_id", required=True)
    parser.add_argument(
        "--method",
        default="auto",
        choices=["fast", "full", "auto"],
        help="Fitting method: fast (k_eff only), full (scipy), auto.",
    )
    args = parser.parse_args()

    filepath = calibrate_user_model(args.user_id, method=args.method)
    print(f"Calibrated model saved to: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        print(json.dumps(json.load(f), indent=2))


if __name__ == "__main__":
    main()
