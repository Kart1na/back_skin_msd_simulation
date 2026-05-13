"""User back-model loader with priority-based fallback.

Loading priority:
    1. Calibrated model  (outputs/{user_id}_calibrated_back_model.json)
    2. Initial model     (outputs/{user_id}_initial_back_model.json)
    3. Default config    (config.py defaults)
"""

import json
import os
import types

import config as default_config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")


def _load_json(filepath):
    if os.path.isfile(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_user_back_model(user_id=None):
    """Return a config-like module/namespace with user-specific parameters.

    Falls back through calibrated -> initial -> default config.
    Returns (cfg, model_type) where model_type is one of
    "calibrated", "initial", or "default".
    """
    if user_id is None:
        return default_config, "default"

    calibrated_path = os.path.join(OUTPUT_DIR, f"{user_id}_calibrated_back_model.json")
    initial_path = os.path.join(OUTPUT_DIR, f"{user_id}_initial_back_model.json")

    model_data = _load_json(calibrated_path)
    if model_data is not None:
        model_type = "calibrated"
    else:
        model_data = _load_json(initial_path)
        if model_data is not None:
            model_type = "initial"
        else:
            return default_config, "default"

    cfg = _overlay_on_config(model_data)
    return cfg, model_type


def _overlay_on_config(model_data):
    """Create a config-like SimpleNamespace that overrides default_config
    with values from the model JSON, keeping all other config values intact."""
    cfg = types.SimpleNamespace()

    for attr in dir(default_config):
        if attr.startswith("_"):
            continue
        setattr(cfg, attr, getattr(default_config, attr))

    # Copy helper functions
    cfg.mm_to_m = default_config.mm_to_m
    cfg.kPa_to_Pa = default_config.kPa_to_Pa

    param_map = {
        "k_skin_N_m": "k_skin_N_m",
        "k_muscle_fat_N_m": "k_muscle_fat_N_m",
        "k_bone_support_N_m": "k_bone_support_N_m",
        "damping": "damping",
        "mu_static": "mu_static",
        "mu_dynamic": "mu_dynamic",
        "contact_tangent_gain": "contact_tangent_gain",
        "E_skin_kPa": "E_skin_kPa",
        "E_muscle_fat_kPa": "E_muscle_fat_kPa",
        "E_bone_support_kPa": "E_bone_support_kPa",
        "skin_thickness_mm": "skin_thickness_mm",
        "muscle_fat_thickness_mm": "muscle_fat_thickness_mm",
        "bone_support_thickness_mm": "bone_support_thickness_mm",
    }

    for json_key, cfg_attr in param_map.items():
        if json_key in model_data:
            setattr(cfg, cfg_attr, model_data[json_key])

    # Recompute derived values that depend on overridden params
    if "skin_thickness_mm" in model_data:
        cfg.skin_thickness = cfg.mm_to_m(cfg.skin_thickness_mm)
    if "muscle_fat_thickness_mm" in model_data:
        cfg.muscle_fat_thickness = cfg.mm_to_m(cfg.muscle_fat_thickness_mm)
    if "bone_support_thickness_mm" in model_data:
        cfg.bone_support_thickness = cfg.mm_to_m(cfg.bone_support_thickness_mm)
    if "E_skin_kPa" in model_data:
        cfg.E_skin = cfg.kPa_to_Pa(cfg.E_skin_kPa)
    if "E_muscle_fat_kPa" in model_data:
        cfg.E_muscle_fat = cfg.kPa_to_Pa(cfg.E_muscle_fat_kPa)
    if "E_bone_support_kPa" in model_data:
        cfg.E_bone_support = cfg.kPa_to_Pa(cfg.E_bone_support_kPa)

    # Attach metadata
    cfg._user_model_data = model_data

    return cfg
