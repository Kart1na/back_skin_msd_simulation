"""Estimate local back stiffness from massage force-displacement CSV data."""

import argparse
import csv
import json
import os
from collections import defaultdict
from statistics import mean, pstdev

import config
from back_region_map import get_region_by_name, locate_region


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = os.path.join(BASE_DIR, "user_data")


def _float_or_none(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_coordinate(row, primary, fallback):
    value = _float_or_none(row.get(primary))
    if value is not None:
        return value
    return _float_or_none(row.get(fallback))


def infer_section(y_mm):
    if y_mm is None:
        return "Unknown"
    if y_mm >= 50:
        return "Upper Back"
    if y_mm >= -40:
        return "Mid Back"
    return "Lower Back"


def infer_point_id(row, x_mm, y_mm, row_index):
    point_id = row.get("point_id")
    if point_id:
        return point_id
    if x_mm is not None and y_mm is not None:
        return f"x{round(x_mm, 1)}_y{round(y_mm, 1)}"
    return f"row_{row_index}"


def resolve_input_path(user_id, data_path=None):
    """Resolve explicit data path or default user first-massage/test CSV."""
    if data_path:
        if os.path.isabs(data_path):
            return data_path
        local_path = os.path.join(BASE_DIR, data_path)
        if os.path.isfile(local_path):
            return local_path
        return os.path.abspath(data_path)

    first_massage_path = os.path.join(USER_DATA_DIR, f"{user_id}_first_massage.csv")
    if os.path.isfile(first_massage_path):
        return first_massage_path

    stiffness_test_path = os.path.join(BASE_DIR, "stiffness_test.csv")
    if os.path.isfile(stiffness_test_path):
        return stiffness_test_path

    raise FileNotFoundError(
        f"No stiffness input CSV found for {user_id}. "
        f"Expected {first_massage_path} or stiffness_test.csv."
    )


def load_stiffness_records(user_id, data_path=None):
    """Read CSV rows and compute stiffness_N_m for valid indentation points."""
    input_path = resolve_input_path(user_id, data_path)
    records = []
    skipped_rows = 0

    with open(input_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for index, row in enumerate(reader, start=1):
            force_N = _float_or_none(row.get("normal_force_N"))
            indentation_mm = _float_or_none(row.get("indentation_mm"))

            if force_N is None or indentation_mm is None or indentation_mm <= 0:
                skipped_rows += 1
                continue

            x_mm = _get_coordinate(row, "x_mm", "probe_x_mm")
            y_mm = _get_coordinate(row, "y_mm", "probe_y_mm")
            region_name = row.get("region") or None
            if region_name:
                region = get_region_by_name(region_name)
                if region["name"] == "unknown":
                    located_region = (
                        locate_region(x_mm, y_mm)
                        if x_mm is not None and y_mm is not None
                        else region
                    )
                    region = {
                        **located_region,
                        "name": region_name,
                        "display_name": region_name,
                    }
            else:
                region = (
                    locate_region(x_mm, y_mm)
                    if x_mm is not None and y_mm is not None
                    else get_region_by_name("unknown")
                )

            section = row.get("section") or infer_section(y_mm)
            stiffness_N_m = force_N / (indentation_mm / 1000.0)

            records.append({
                "row_index": index,
                "point_id": infer_point_id(row, x_mm, y_mm, index),
                "region": region["name"],
                "display_name": region["display_name"],
                "section": section,
                "x_mm": x_mm,
                "y_mm": y_mm,
                "normal_force_N": force_N,
                "indentation_mm": indentation_mm,
                "stiffness_N_m": stiffness_N_m,
            })

    return input_path, records, skipped_rows


def _summarize_records(records, group_key):
    grouped = defaultdict(list)
    for record in records:
        grouped[record[group_key]].append(record)

    summaries = []
    for key, group_records in grouped.items():
        stiffness_values = [record["stiffness_N_m"] for record in group_records]
        x_values = [record["x_mm"] for record in group_records if record["x_mm"] is not None]
        y_values = [record["y_mm"] for record in group_records if record["y_mm"] is not None]
        first_record = group_records[0]

        summary = {
            group_key: key,
            "sample_count": len(group_records),
            "mean_stiffness_N_m": round(mean(stiffness_values), 2),
            "max_stiffness_N_m": round(max(stiffness_values), 2),
            "std_stiffness_N_m": round(pstdev(stiffness_values), 2)
            if len(stiffness_values) > 1 else 0.0,
            "x_mm": round(mean(x_values), 2) if x_values else None,
            "y_mm": round(mean(y_values), 2) if y_values else None,
        }

        if group_key != "region":
            summary["region"] = first_record.get("region", "unknown")
            summary["display_name"] = first_record.get("display_name", "未知区域")
        else:
            summary["display_name"] = first_record.get("display_name", key)

        if group_key != "section":
            summary["section"] = first_record.get("section", "Unknown")

        summaries.append(summary)

    return sorted(
        summaries,
        key=lambda item: item["mean_stiffness_N_m"],
        reverse=True,
    )


def estimate_stiffness(user_id, data_path=None):
    """Estimate per-point, per-region, and per-section stiffness statistics."""
    input_path, records, skipped_rows = load_stiffness_records(user_id, data_path)
    stiffness_values = [record["stiffness_N_m"] for record in records]

    if not stiffness_values:
        raise ValueError("No valid stiffness rows found. Check indentation_mm > 0.")

    stats = {
        "user_id": user_id,
        "source_csv": input_path,
        "valid_sample_count": len(records),
        "skipped_sample_count": skipped_rows,
        "overall": {
            "mean_stiffness_N_m": round(mean(stiffness_values), 2),
            "max_stiffness_N_m": round(max(stiffness_values), 2),
            "std_stiffness_N_m": round(pstdev(stiffness_values), 2)
            if len(stiffness_values) > 1 else 0.0,
        },
        "points": _summarize_records(records, "point_id"),
        "regions": _summarize_records(records, "region"),
        "sections": _summarize_records(records, "section"),
        "records": [
            {
                **record,
                "stiffness_N_m": round(record["stiffness_N_m"], 2),
            }
            for record in records
        ],
    }
    return stats


def save_stiffness_stats(stats, user_id):
    os.makedirs(config.output_dir, exist_ok=True)
    output_path = os.path.join(config.output_dir, f"{user_id}_stiffness_stats.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Estimate back stiffness from CSV.")
    parser.add_argument("--user_id", required=True)
    parser.add_argument(
        "--data",
        default=None,
        help="CSV path. Defaults to user_data/{user_id}_first_massage.csv.",
    )
    args = parser.parse_args()

    stats = estimate_stiffness(args.user_id, args.data)
    save_stiffness_stats(stats, args.user_id)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
