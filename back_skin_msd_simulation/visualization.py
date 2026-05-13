"""Visualization functions for back skin MSD deformation results.

All coordinates are displayed in mm.  Images are saved to the outputs/ folder.
"""

import numpy as np
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import config


def _ensure_output_dir(cfg=None):
    if cfg is None:
        cfg = config
    os.makedirs(cfg.output_dir, exist_ok=True)
    return cfg.output_dir


def plot_back_skin_surface(snapshot, filename, cfg=None):
    """3D surface plot of current skin-layer positions."""
    out_dir = _ensure_output_dir(cfg)
    pos = snapshot['skin_positions']  # (ny, nx, 3)

    X = pos[:, :, 0] * 1000.0  # m -> mm
    Y = pos[:, :, 1] * 1000.0
    Z = pos[:, :, 2] * 1000.0

    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection='3d')
    ax.plot_surface(X, Y, Z, cmap='coolwarm', edgecolor='k',
                    linewidth=0.2, alpha=0.9)
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_zlabel('Z (mm)')
    ax.set_title('Back Skin Surface Deformation')

    # Consistent z-axis range across snapshots
    z_min = np.min(Z)
    z_max = max(np.max(Z), 1.0)
    margin = max((z_max - z_min) * 0.2, 0.5)
    ax.set_zlim(z_min - margin, z_max + margin)

    path = os.path.join(out_dir, filename)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close(fig)
    print('  Saved: {}'.format(path))


def plot_deformation_snapshots(snapshots, cfg=None):
    """Output t0-t3 skin surface images."""
    for label in ['t0', 't1', 't2', 't3']:
        if label in snapshots:
            fname = 'back_skin_surface_{}.png'.format(label)
            plot_back_skin_surface(snapshots[label], fname, cfg)


def plot_xz_cross_section(snapshot, filename, cfg=None):
    """X-Z cross section at Y ~ 0 (middle row)."""
    out_dir = _ensure_output_dir(cfg)
    pos = snapshot['skin_positions']
    init_pos = snapshot['skin_initial_positions']

    ny = pos.shape[0]
    mid_j = ny // 2

    x_cur = pos[mid_j, :, 0] * 1000.0
    z_cur = pos[mid_j, :, 2] * 1000.0
    x_ini = init_pos[mid_j, :, 0] * 1000.0
    z_ini = init_pos[mid_j, :, 2] * 1000.0

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(x_ini, z_ini, 'b--', label='Initial', linewidth=1.0)
    ax.plot(x_cur, z_cur, 'r-', label='Deformed', linewidth=1.5)
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Z (mm)')
    ax.set_title('Back Skin X-Z Cross Section (Y=0)')
    ax.legend()
    ax.set_aspect('equal', adjustable='datalim')
    ax.grid(True, alpha=0.3)

    path = os.path.join(out_dir, filename)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close(fig)
    print('  Saved: {}'.format(path))


def plot_displacement_maps(snapshot, filename_prefix, cfg=None):
    """Displacement colour maps for X, Z, and magnitude."""
    out_dir = _ensure_output_dir(cfg)
    disp = snapshot['skin_displacements']  # (ny, nx, 3)
    init = snapshot['skin_initial_positions']

    X_grid = init[:, :, 0] * 1000.0
    Y_grid = init[:, :, 1] * 1000.0

    dx_mm = disp[:, :, 0] * 1000.0
    dz_mm = disp[:, :, 2] * 1000.0
    mag_mm = np.linalg.norm(disp, axis=2) * 1000.0

    titles = ['X Displacement (mm)', 'Z Displacement (mm)',
              'Total Displacement Magnitude (mm)']
    data = [dx_mm, dz_mm, mag_mm]
    suffixes = ['x', 'z', 'magnitude']
    cmaps = ['RdBu_r', 'RdBu_r', 'hot']

    for title, d, suffix, cmap in zip(titles, data, suffixes, cmaps):
        fig, ax = plt.subplots(figsize=(9, 5))
        vabs = max(np.max(np.abs(d)), 1e-6)
        if suffix == 'magnitude':
            im = ax.pcolormesh(X_grid, Y_grid, d, cmap=cmap,
                               vmin=0, vmax=vabs, shading='auto')
        else:
            im = ax.pcolormesh(X_grid, Y_grid, d, cmap=cmap,
                               vmin=-vabs, vmax=vabs, shading='auto')
        ax.set_xlabel('X (mm)')
        ax.set_ylabel('Y (mm)')
        ax.set_title('Back Skin ' + title)
        ax.set_aspect('equal')
        plt.colorbar(im, ax=ax, label='mm')

        fname = '{}_{}.png'.format(filename_prefix, suffix)
        path = os.path.join(out_dir, fname)
        plt.tight_layout()
        plt.savefig(path, dpi=150)
        plt.close(fig)
        print('  Saved: {}'.format(path))
