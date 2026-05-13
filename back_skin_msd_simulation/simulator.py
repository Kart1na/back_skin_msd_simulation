"""Dynamics integrator with stick-slip friction for back skin MSD.

Implements semi-implicit Euler integration, Kelvin-Voigt spring force
accumulation, probe collision resolution, and stick/slip friction switching
with hysteresis.
"""

import numpy as np
import sys
import config


class Simulator:
    """Main dynamics loop for the back skin MSD simulation."""

    def __init__(self, model, springs, probe, cfg=None):
        if cfg is None:
            cfg = config
        self.model = model
        self.springs = springs
        self.probe = probe
        self.cfg = cfg

        self.dt = cfg.dt
        self.total_time = cfg.total_time
        self.global_damping = cfg.global_damping_factor
        self.max_vel = cfg.max_velocity_m_s
        self.max_disp = cfg.max_step_displacement_m

        self.contact_state = {}   # pid -> "stick" / "slip"
        self.snapshots = {}
        self._step_count = 0
        self._num_stick = 0
        self._num_slip = 0

    # ----------------------------------------------------------
    # Friction helpers
    # ----------------------------------------------------------

    def _compute_critical_friction(self, n_contacts):
        """Per-particle critical (static) friction force magnitude."""
        if n_contacts == 0:
            return 0.0
        cfg = self.cfg
        if cfg.friction_model == 'paper':
            R = cfg.probe_radius
            E = cfg.E_skin
            Fn = cfg.normal_force
            # Paper formula: F_fri = pi*tau0*(3R/(4E))^(2/3)*Fn^(2/3) + alpha*Fn
            F_fri = (np.pi * cfg.tau0
                     * ((3.0 * R) / (4.0 * E)) ** (2.0 / 3.0)
                     * Fn ** (2.0 / 3.0)
                     + cfg.alpha * Fn)
            return F_fri / n_contacts
        else:
            return cfg.mu_static * cfg.normal_force / n_contacts

    def _compute_dynamic_friction(self, n_contacts):
        if n_contacts == 0:
            return 0.0
        return self.cfg.mu_dynamic * self.cfg.normal_force / n_contacts

    def _apply_friction(self, contact_particles):
        n = len(contact_particles)
        if n == 0:
            self._num_stick = 0
            self._num_slip = 0
            return

        F_crit = self._compute_critical_friction(n)
        F_dyn = self._compute_dynamic_friction(n)
        slip_to_stick_thresh = 0.6 * F_crit

        probe_vel = self.probe.get_probe_velocity()
        k_tan = self.cfg.contact_tangent_gain
        n_stick = 0
        n_slip = 0

        for p in contact_particles:
            pid = p.pid
            state = self.contact_state.get(pid, 'stick')

            rel_v = probe_vel - p.velocity
            tangent_force = k_tan * rel_v
            tangent_mag = np.linalg.norm(tangent_force)

            if state == 'stick':
                if tangent_mag > F_crit > 0:
                    state = 'slip'
                else:
                    p.force += tangent_force
                    n_stick += 1

            if state == 'slip':
                probe_dir = probe_vel.copy()
                probe_speed = np.linalg.norm(probe_dir)
                if probe_speed > 1e-12:
                    probe_dir /= probe_speed
                    p.force += F_dyn * probe_dir
                n_slip += 1
                if tangent_mag < slip_to_stick_thresh:
                    state = 'stick'

            self.contact_state[pid] = state

        self._num_stick = n_stick
        self._num_slip = n_slip

    # ----------------------------------------------------------
    # Single time step
    # ----------------------------------------------------------

    def step(self, t):
        model = self.model

        # 1. Clear forces
        model.clear_forces()

        # 2. Spring forces
        for s in self.springs:
            s.apply_force()

        # 3. Update probe
        self.probe.update(t, self.dt)

        # 4-5. Collision detection & resolution
        self.probe.resolve_collision(model)
        contact_particles = self.probe.get_contact_particles(model)

        # 6. Friction
        self._apply_friction(contact_particles)

        # 7. Semi-implicit Euler
        for p in model.iter_particles():
            if p.fixed:
                continue
            acc = p.force / p.mass
            p.velocity += acc * self.dt
            p.velocity *= self.global_damping

            speed = np.linalg.norm(p.velocity)
            if speed > self.max_vel:
                p.velocity *= self.max_vel / speed

            dx = p.velocity * self.dt
            dx_norm = np.linalg.norm(dx)
            if dx_norm > self.max_disp:
                dx *= self.max_disp / dx_norm
            p.position += dx

        # 8. Fix bone layer
        model.reset_fixed_particles()
        self._step_count += 1

    # ----------------------------------------------------------
    # Snapshot
    # ----------------------------------------------------------

    def save_snapshot(self, label):
        self.snapshots[label] = {
            'skin_positions': self.model.get_skin_positions(),
            'skin_initial_positions': self.model.get_skin_initial_positions(),
            'skin_displacements': self.model.get_skin_displacements(),
            'probe_center': self.probe.center.copy(),
            'num_stick': self._num_stick,
            'num_slip': self._num_slip,
        }

    # ----------------------------------------------------------
    # Main run loop
    # ----------------------------------------------------------

    def run(self):
        total_steps = int(np.ceil(self.total_time / self.dt))
        print('Starting simulation: {} steps, dt={}, total_time={:.2f} s'.format(
            total_steps, self.dt, self.total_time))

        press_steps = int(np.ceil(self.cfg.press_duration_s / self.dt))
        slide_steps = max(total_steps - press_steps, 1)

        t0_step = press_steps
        t1_step = press_steps + slide_steps // 4
        t2_step = press_steps + slide_steps // 2
        t3_step = press_steps + 3 * slide_steps // 4

        for step_i in range(total_steps):
            t = step_i * self.dt
            self.step(t)

            # NaN / inf check
            if step_i % 500 == 0:
                sample = self.model.get_skin_positions()
                if not np.all(np.isfinite(sample)):
                    print('ERROR: NaN or Inf in particle positions!')
                    print('  Try: reduce dt, increase damping, '
                          'lower stiffness, or reduce indentation_depth.')
                    sys.exit(1)

            if step_i == t0_step:
                self.save_snapshot('t0')
                print('  [step {}] Snapshot t0 (end of press)'.format(step_i))
            elif step_i == t1_step:
                self.save_snapshot('t1')
                print('  [step {}] Snapshot t1 (early slide)'.format(step_i))
            elif step_i == t2_step:
                self.save_snapshot('t2')
                print('  [step {}] Snapshot t2 (mid slide)'.format(step_i))
            elif step_i == t3_step:
                self.save_snapshot('t3')
                print('  [step {}] Snapshot t3 (late slide)'.format(step_i))

            if step_i % 2000 == 0 and step_i > 0:
                pct = 100.0 * step_i / total_steps
                print('  Progress: {:.1f}%  (step {}/{})'.format(
                    pct, step_i, total_steps))

        if 't3' not in self.snapshots:
            self.save_snapshot('t3')
            print('  [final] Snapshot t3 saved')
        print('Simulation complete.')

    # ----------------------------------------------------------
    # Summary statistics
    # ----------------------------------------------------------

    def compute_basic_stats(self):
        disp = self.model.get_skin_displacements()
        dx = disp[:, :, 0]
        dz = disp[:, :, 2]
        total = np.linalg.norm(disp, axis=2)
        return {
            'max_indentation_m': float(np.max(np.abs(dz))),
            'max_x_displacement_m': float(np.max(np.abs(dx))),
            'max_z_displacement_m': float(np.max(np.abs(dz))),
            'max_total_displacement_m': float(np.max(total)),
            'num_stick_contacts': self._num_stick,
            'num_slip_contacts': self._num_slip,
        }
