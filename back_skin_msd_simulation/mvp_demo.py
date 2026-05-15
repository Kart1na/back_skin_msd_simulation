"""Run the intelligent massage MVP loop end to end."""

import argparse
import json
import os

import config
from back_region_map import locate_region
from force_analysis import analyze_force
from pressure_recommender import recommend_pressure


def run_mvp(user_id, x_mm, y_mm, force_N, indentation_mm):
    """Run region detection, recommendation, and force-risk analysis."""
    region = locate_region(x_mm, y_mm)
    region_name = region["name"]
    recommendation = recommend_pressure(user_id, region_name)
    analysis = analyze_force(user_id, region_name, force_N, indentation_mm)

    return {
        "user_id": user_id,
        "input": {
            "x_mm": float(x_mm),
            "y_mm": float(y_mm),
            "force_N": float(force_N),
            "indentation_mm": float(indentation_mm),
        },
        "region_detection": region,
        "pressure_recommendation": recommendation,
        "force_analysis": analysis,
    }


def save_report(report):
    """Save MVP report to outputs/{user_id}_mvp_report.json."""
    output_dir = getattr(config, "output_dir", os.path.join(os.getcwd(), "outputs"))
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, f"{report['user_id']}_mvp_report.json")

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return report_path


def main():
    parser = argparse.ArgumentParser(description="Run intelligent massage MVP demo.")
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--x", required=True, type=float)
    parser.add_argument("--y", required=True, type=float)
    parser.add_argument("--force", required=True, type=float)
    parser.add_argument("--indentation", required=True, type=float)
    args = parser.parse_args()

    report = run_mvp(args.user_id, args.x, args.y, args.force, args.indentation)
    save_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
