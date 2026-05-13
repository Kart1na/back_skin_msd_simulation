"""Back skin MSD simulation entry point.

Usage:
    python main.py                        # default config
    python main.py --fast                  # reduced resolution quick demo
    python main.py --user_id user_001      # load user-specific model
"""

import argparse
import os
import sys
import time

import config
from model import BackSkinMSDModel
from spring import create_springs
from probe import SphericalProbe
from simulator import Simulator
from user_model import load_user_back_model
from visualization import (
    plot_deformation_snapshots,
    plot_xz_cross_section,
    plot_displacement_maps,
)


def apply_fast_settings(cfg):
    """Override config for a fast demo run with coarser grid and larger dt."""
    cfg.grid_spacing_x_mm = 15.0
    cfg.grid_spacing_y_mm = 15.0
    cfg.grid_spacing_x = cfg.mm_to_m(cfg.grid_spacing_x_mm)
    cfg.grid_spacing_y = cfg.mm_to_m(cfg.grid_spacing_y_mm)
    cfg.nx = int(round(cfg.L_mm / cfg.grid_spacing_x_mm)) + 1
    cfg.ny = int(round(cfg.W_mm / cfg.grid_spacing_y_mm)) + 1
    cfg.dt = 0.002
    cfg.probe_velocity_mm_s = 15.0
    cfg.probe_velocity = cfg.mm_to_m(cfg.probe_velocity_mm_s)
    cfg.total_time = cfg.press_duration_s + cfg.travel_distance / cfg.probe_velocity
    cfg.max_step_displacement_m = 0.002
    return cfg


def parse_args():
    parser = argparse.ArgumentParser(
        description="Back Skin MSD Deformation Simulation"
    )
    parser.add_argument("--fast", action="store_true", help="Coarser grid for quick demo")
    parser.add_argument("--user_id", default=None, help="Load personalised user model")
    return parser.parse_args()


def main():
    args = parse_args()

    cfg, model_type = load_user_back_model(args.user_id)

    if args.user_id:
        print('User: {}  |  Model type: {}'.format(args.user_id, model_type))

    if args.fast:
        print('*** FAST MODE: coarser grid, larger dt ***')
        cfg = apply_fast_settings(cfg)

    os.makedirs(cfg.output_dir, exist_ok=True)

    print('=' * 60)
    print('  Back Skin MSD Deformation Simulation')
    print('=' * 60)

    print('\n[1/6] Building three-layer MSD model ...')
    model = BackSkinMSDModel(cfg)
    print('  Grid: {} x {} = {} nodes/layer,  3 layers'.format(
        cfg.nx, cfg.ny, cfg.nx * cfg.ny))
    print('  Total particles: {}'.format(model.num_particles()))

    print('[2/6] Creating spring network ...')
    springs = create_springs(model, cfg)
    print('  Total springs: {}'.format(len(springs)))

    print('[3/6] Initializing probe ...')
    probe = SphericalProbe(cfg)
    print('  Radius: {:.1f} mm,  Indentation: {:.1f} mm'.format(
        cfg.probe_radius_mm, cfg.indentation_depth_mm))
    print('  Travel: {:.0f} mm at {:.1f} mm/s'.format(
        cfg.travel_distance_mm, cfg.probe_velocity_mm_s))

    print('[4/6] Initializing simulator ...')
    sim = Simulator(model, springs, probe, cfg)
    total_steps = int(cfg.total_time / cfg.dt)
    print('  dt = {} s,  total time = {:.2f} s,  steps = {}'.format(
        cfg.dt, cfg.total_time, total_steps))
    print('  Friction model: {}'.format(cfg.friction_model))

    print('[5/6] Running simulation ...')
    t_start = time.time()
    sim.run()
    elapsed = time.time() - t_start
    print('  Wall-clock time: {:.1f} s'.format(elapsed))

    print('[6/6] Generating visualizations ...')
    plot_deformation_snapshots(sim.snapshots, cfg)

    if 't3' in sim.snapshots:
        plot_xz_cross_section(sim.snapshots['t3'],
                              'back_xz_cross_section_t3.png', cfg)
        plot_displacement_maps(sim.snapshots['t3'],
                               'back_displacement_t3', cfg)

    stats = sim.compute_basic_stats()
    print('\n' + '=' * 60)
    print('  Simulation Summary')
    print('=' * 60)
    print('  Particles:            {}'.format(model.num_particles()))
    print('  Springs:              {}'.format(len(springs)))
    print('  Steps:                {}'.format(total_steps))
    print('  dt:                   {} s'.format(cfg.dt))
    print('  Total sim time:       {:.2f} s'.format(cfg.total_time))
    print('  Max indentation:      {:.3f} mm'.format(
        stats['max_indentation_m'] * 1000))
    print('  Max X displacement:   {:.3f} mm'.format(
        stats['max_x_displacement_m'] * 1000))
    print('  Max Z displacement:   {:.3f} mm'.format(
        stats['max_z_displacement_m'] * 1000))
    print('  Max total disp:       {:.3f} mm'.format(
        stats['max_total_displacement_m'] * 1000))
    print('  Friction model:       {}'.format(cfg.friction_model))
    print('  Stick contacts:       {}'.format(stats['num_stick_contacts']))
    print('  Slip contacts:        {}'.format(stats['num_slip_contacts']))
    print('=' * 60)
    print('  Output images saved to: {}'.format(cfg.output_dir))
    print('=' * 60)


if __name__ == '__main__':
    main()
