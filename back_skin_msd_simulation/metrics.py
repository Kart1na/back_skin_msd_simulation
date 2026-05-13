"""Error evaluation utilities for comparing simulation with experiments.

Not called in the default simulation pipeline; reserved for future use
when real back surface point-cloud data becomes available.
"""

import numpy as np


def compute_mae_and_sd(sim_points, exp_points):
    """Compute per-axis and total MAE / SD between simulation and experiment.

    Parameters
    ----------
    sim_points : ndarray, shape (N, 3)
    exp_points : ndarray, shape (N, 3)

    Returns
    -------
    dict with keys: mae, sd, mae_total, sd_total
    """
    diff = sim_points - exp_points                     # (N, 3)
    mae = np.mean(np.abs(diff), axis=0)                # (3,)
    sd = np.std(diff, axis=0)                          # (3,)
    err_norm = np.linalg.norm(diff, axis=1)            # (N,)
    mae_total = float(np.mean(err_norm))
    sd_total = float(np.std(err_norm))

    return {
        'mae': mae,
        'sd': sd,
        'mae_total': mae_total,
        'sd_total': sd_total,
    }
