"""Safety analysis for current force and indentation state."""

import argparse
import json

from back_region_map import get_region_by_name
from pressure_recommender import recommend_pressure


def analyze_force(user_id, region_name, current_force_N, current_indentation_mm):
    """Judge current massage state and suggest the next normal force."""
    current_force_N = float(current_force_N)
    current_indentation_mm = float(current_indentation_mm)

    recommendation = recommend_pressure(user_id, region_name)
    region = get_region_by_name(region_name)

    if region["avoid"]:
        status = "avoid"
        suggested_next_force_N = 0.0
        message = "该区域为避让区域，不建议按摩。"
    else:
        safe_min, safe_max = recommendation["safe_force_range_N"]
        indent_min, indent_max = recommendation["target_indentation_range_mm"]

        if current_force_N > safe_max:
            status = "high_force"
            suggested_next_force_N = max(safe_min, current_force_N - 2.0)
            message = "当前力度超过该区域安全上限，建议降低力度。"
        elif current_indentation_mm > indent_max:
            status = "high_indentation"
            suggested_next_force_N = max(safe_min, current_force_N - 1.5)
            message = "当前压入深度偏大，建议降低力度。"
        elif current_force_N < safe_min:
            status = "low_force"
            suggested_next_force_N = min(safe_max, current_force_N + 1.0)
            message = "当前力度偏低，可小幅增加力度。"
        elif current_indentation_mm < indent_min:
            status = "low_indentation"
            suggested_next_force_N = min(safe_max, current_force_N + 1.0)
            message = "当前压入深度偏小，可小幅增加力度。"
        else:
            status = "safe"
            suggested_next_force_N = current_force_N
            message = "当前力度处于安全范围，可保持。"

    return {
        "user_id": user_id,
        "region": recommendation["region"],
        "display_name": recommendation["display_name"],
        "model_type": recommendation["model_type"],
        "current_force_N": current_force_N,
        "current_indentation_mm": current_indentation_mm,
        "recommended_force_N": recommendation["recommended_force_N"],
        "safe_force_range_N": recommendation["safe_force_range_N"],
        "target_indentation_range_mm": recommendation["target_indentation_range_mm"],
        "status": status,
        "risk_level": recommendation["risk_level"],
        "risk_message": recommendation["risk_message"],
        "avoid": recommendation["avoid"],
        "suggested_next_force_N": round(suggested_next_force_N, 2),
        "message": message,
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze massage force safety.")
    parser.add_argument("--user_id", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--force", required=True, type=float)
    parser.add_argument("--indentation", required=True, type=float)
    args = parser.parse_args()

    result = analyze_force(args.user_id, args.region, args.force, args.indentation)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
