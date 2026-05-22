"""First-massage data logger and synthetic data generator.

Records force-displacement data during the first massage session for later
parameter calibration.

Usage:
    python first_massage_logger.py --user_id user_001 --synthetic
"""

import argparse
import csv
import os

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")

CSV_FIELDS = [
    "time_s",
    "normal_force_N",
    "indentation_mm",
    "probe_x_mm",
    "probe_y_mm",
    "probe_z_mm",
    "tangential_force_N",
    "x_displacement_mm",
]


class FirstMassageLogger:
    """Accumulate per-timestep massage data and flush to CSV."""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._rows = []

    def record(
        self,
        time_s: float,
        normal_force_N: float,
        indentation_mm: float,
        probe_x_mm: float,
        probe_y_mm: float,
        probe_z_mm: float,
        tangential_force_N: float = 0.0,
        x_displacement_mm: float = 0.0,
    ):
        self._rows.append({
            "time_s": round(time_s, 6),
            "normal_force_N": round(normal_force_N, 4),
            "indentation_mm": round(indentation_mm, 4),
            "probe_x_mm": round(probe_x_mm, 4),
            "probe_y_mm": round(probe_y_mm, 4),
            "probe_z_mm": round(probe_z_mm, 4),
            "tangential_force_N": round(tangential_force_N, 4),
            "x_displacement_mm": round(x_displacement_mm, 4),
        })

    def save(self) -> str:
        os.makedirs(USER_DATA_DIR, exist_ok=True)
        filepath = os.path.join(USER_DATA_DIR, f"{self.user_id}_first_massage.csv")
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(self._rows)
        return filepath


# ---------------------------------------------------------------------------
# Synthetic data generation (for testing the calibration pipeline)
# ---------------------------------------------------------------------------

def generate_synthetic_first_massage_data(
    user_id: str,
    k_eff: float = 2200.0,
    damping_coeff: float = 0.05,
    noise_std_mm: float = 0.08,
    duration_s: float = 3.0,
    dt: float = 0.01,
    max_force_N: float = 15.0,
    ramp_fraction: float = 0.4,
    probe_travel_mm: float = 80.0,
) -> str:
    """Generate a plausible force-indentation CSV for pipeline testing.

    The synthetic curve uses:
        indentation = F / k_eff  +  damping_coeff * dF/dt  +  noise

    Phase 1 (ramp):   force ramps linearly from 0 to max_force.
    Phase 2 (hold):   force held at max_force while probe slides.
    """
    np.random.seed(42)

    n_steps = int(duration_s / dt)
    ramp_steps = int(n_steps * ramp_fraction)

    logger = FirstMassageLogger(user_id)
    prev_force = 0.0
    probe_x = -probe_travel_mm / 2.0

    for i in range(n_steps):
        t = i * dt

        if i < ramp_steps:
            frac = i / ramp_steps
            force = max_force_N * frac
        else:
            force = max_force_N

        dF_dt = (force - prev_force) / dt
        prev_force = force

        indentation = (force / k_eff) * 1000.0 + damping_coeff * dF_dt
        indentation += np.random.normal(0, noise_std_mm)
        indentation = max(indentation, 0.0)

        if i >= ramp_steps:
            slide_frac = (i - ramp_steps) / max(n_steps - ramp_steps, 1)
            probe_x = -probe_travel_mm / 2.0 + probe_travel_mm * slide_frac
            tangential_force = 0.45 * force
            x_disp = 0.15 * indentation * slide_frac
        else:
            tangential_force = 0.0
            x_disp = 0.0

        logger.record(
            time_s=t,
            normal_force_N=force,
            indentation_mm=indentation,
            probe_x_mm=probe_x,
            probe_y_mm=0.0,
            probe_z_mm=-indentation,
            tangential_force_N=tangential_force,
            x_displacement_mm=x_disp,
        )

    filepath = logger.save()
    return filepath


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Record or generate first-massage force-displacement data."
    )
    parser.add_argument("--user_id", required=True)
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Generate synthetic test data instead of recording from robot.",
    )
    parser.add_argument("--k_eff", type=float, default=2200.0)
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--max_force", type=float, default=15.0)
    args = parser.parse_args()

    if args.synthetic:
        path = generate_synthetic_first_massage_data(
            user_id=args.user_id,
            k_eff=args.k_eff,
            duration_s=args.duration,
            max_force_N=args.max_force,
        )
        print(f"Synthetic first-massage data saved to: {path}")
    else:
        print(
            "Real-time recording not yet implemented. "
            "Use --synthetic for test data."
        )


if __name__ == "__main__":
    main()
