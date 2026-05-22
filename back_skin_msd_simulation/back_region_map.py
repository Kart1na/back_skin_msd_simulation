"""Simple 2D back-region map for massage MVP decisions."""

from copy import deepcopy


UNKNOWN_REGION = {
    "name": "unknown",
    "display_name": "未知区域",
    "risk_level": "high",
    "avoid": True,
    "base_force_range_N": [0, 0],
    "target_indentation_range_mm": [0, 0],
}


BACK_REGIONS = [
    {
        "name": "spine_center",
        "display_name": "脊柱中线",
        "x_range_mm": [-12, 12],
        "y_range_mm": [-160, 160],
        "risk_level": "high",
        "avoid": True,
        "base_force_range_N": [0, 3],
        "target_indentation_range_mm": [0, 2],
    },
    {
        "name": "upper_back_left",
        "display_name": "左上背区",
        "x_range_mm": [-90, -15],
        "y_range_mm": [50, 150],
        "risk_level": "medium",
        "avoid": False,
        "base_force_range_N": [5, 12],
        "target_indentation_range_mm": [3, 5],
    },
    {
        "name": "upper_back_right",
        "display_name": "右上背区",
        "x_range_mm": [15, 90],
        "y_range_mm": [50, 150],
        "risk_level": "medium",
        "avoid": False,
        "base_force_range_N": [5, 12],
        "target_indentation_range_mm": [3, 5],
    },
    {
        "name": "middle_back_left",
        "display_name": "左中背区",
        "x_range_mm": [-90, -15],
        "y_range_mm": [-40, 50],
        "risk_level": "low",
        "avoid": False,
        "base_force_range_N": [6, 14],
        "target_indentation_range_mm": [3, 6],
    },
    {
        "name": "middle_back_right",
        "display_name": "右中背区",
        "x_range_mm": [15, 90],
        "y_range_mm": [-40, 50],
        "risk_level": "low",
        "avoid": False,
        "base_force_range_N": [6, 14],
        "target_indentation_range_mm": [3, 6],
    },
    {
        "name": "lower_back_left",
        "display_name": "左侧腰背区",
        "x_range_mm": [-90, -15],
        "y_range_mm": [-150, -40],
        "risk_level": "medium",
        "avoid": False,
        "base_force_range_N": [5, 14],
        "target_indentation_range_mm": [3, 6],
    },
    {
        "name": "lower_back_right",
        "display_name": "右侧腰背区",
        "x_range_mm": [15, 90],
        "y_range_mm": [-150, -40],
        "risk_level": "medium",
        "avoid": False,
        "base_force_range_N": [5, 14],
        "target_indentation_range_mm": [3, 6],
    },
    {
        "name": "shoulder_left",
        "display_name": "左肩部区域",
        "x_range_mm": [-110, -70],
        "y_range_mm": [80, 160],
        "risk_level": "medium",
        "avoid": False,
        "base_force_range_N": [4, 10],
        "target_indentation_range_mm": [2, 5],
    },
    {
        "name": "shoulder_right",
        "display_name": "右肩部区域",
        "x_range_mm": [70, 110],
        "y_range_mm": [80, 160],
        "risk_level": "medium",
        "avoid": False,
        "base_force_range_N": [4, 10],
        "target_indentation_range_mm": [2, 5],
    },
]


def list_regions():
    """Return all known massage regions."""
    return deepcopy(BACK_REGIONS)


def get_region_by_name(name):
    """Return a region by name, or the high-risk unknown region."""
    for region in BACK_REGIONS:
        if region["name"] == name:
            return deepcopy(region)
    return deepcopy(UNKNOWN_REGION)


def _point_in_region(x_mm, y_mm, region):
    x_min, x_max = region["x_range_mm"]
    y_min, y_max = region["y_range_mm"]
    return x_min <= x_mm <= x_max and y_min <= y_mm <= y_max


def locate_region(x_mm, y_mm):
    """Locate the 2D back coordinate in the region map.

    The spine center is checked first because it is an avoid zone.
    """
    x_mm = float(x_mm)
    y_mm = float(y_mm)

    spine_region = get_region_by_name("spine_center")
    if _point_in_region(x_mm, y_mm, spine_region):
        return spine_region

    for region in BACK_REGIONS:
        if region["name"] == "spine_center":
            continue
        if _point_in_region(x_mm, y_mm, region):
            return deepcopy(region)

    return deepcopy(UNKNOWN_REGION)
