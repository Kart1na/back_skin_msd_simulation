import numpy as np
import config


class Spring:
    """Kelvin-Voigt spring-damper connecting two particles.

    Force = k * (length - rest_length) + c * relative_velocity_along_axis
    """
    __slots__ = [
        'particle_i', 'particle_j',
        'rest_length', 'stiffness', 'damping', 'spring_type'
    ]

    def __init__(self, pi, pj, stiffness, damping, spring_type='stretch'):
        self.particle_i = pi
        self.particle_j = pj
        self.rest_length = float(np.linalg.norm(pj.position - pi.position))
        self.stiffness = stiffness
        self.damping = damping
        self.spring_type = spring_type

    def apply_force(self):
        d = self.particle_j.position - self.particle_i.position
        length = np.linalg.norm(d)
        if length < 1e-12:
            return
        direction = d / length
        extension = length - self.rest_length
        rel_vel = np.dot(
            self.particle_j.velocity - self.particle_i.velocity,
            direction
        )
        # Kelvin-Voigt viscoelastic force
        force_mag = self.stiffness * extension + self.damping * rel_vel
        force_vec = force_mag * direction
        # i is pulled toward j when stretched, pushed away when compressed
        self.particle_i.force += force_vec
        self.particle_j.force -= force_vec


def _layer_stiffness(layer_id, cfg):
    if layer_id == 0:
        return cfg.k_skin_N_m
    elif layer_id == 1:
        return cfg.k_muscle_fat_N_m
    else:
        return cfg.k_bone_support_N_m


def create_springs(model, cfg=None):
    """Build the complete spring network for the three-layer model."""
    if cfg is None:
        cfg = config
    springs = []
    nx, ny = model.nx, model.ny
    damp = cfg.damping

    for layer_id in range(model.num_layers):
        k = _layer_stiffness(layer_id, cfg)
        for j in range(ny):
            for i in range(nx):
                pi = model.get_particle(layer_id, j, i)

                # Stretch springs (4-connected neighbours)
                if i + 1 < nx:
                    pj = model.get_particle(layer_id, j, i + 1)
                    springs.append(Spring(pi, pj, k, damp, 'stretch'))
                if j + 1 < ny:
                    pj = model.get_particle(layer_id, j + 1, i)
                    springs.append(Spring(pi, pj, k, damp, 'stretch'))

                # Shear springs (diagonals, half stiffness)
                if i + 1 < nx and j + 1 < ny:
                    pj = model.get_particle(layer_id, j + 1, i + 1)
                    springs.append(Spring(pi, pj, k * 0.5, damp, 'shear'))
                if i - 1 >= 0 and j + 1 < ny:
                    pj = model.get_particle(layer_id, j + 1, i - 1)
                    springs.append(Spring(pi, pj, k * 0.5, damp, 'shear'))

                # Bend springs (skip one node, quarter stiffness)
                if i + 2 < nx:
                    pj = model.get_particle(layer_id, j, i + 2)
                    springs.append(Spring(pi, pj, k * 0.25, damp, 'bend'))
                if j + 2 < ny:
                    pj = model.get_particle(layer_id, j + 2, i)
                    springs.append(Spring(pi, pj, k * 0.25, damp, 'bend'))

    # Vertical springs between adjacent layers
    for layer_id in range(model.num_layers - 1):
        k_upper = _layer_stiffness(layer_id, cfg)
        k_lower = _layer_stiffness(layer_id + 1, cfg)
        k_vert = 0.5 * (k_upper + k_lower)
        for j in range(ny):
            for i in range(nx):
                pi = model.get_particle(layer_id, j, i)
                pj = model.get_particle(layer_id + 1, j, i)
                springs.append(Spring(pi, pj, k_vert, damp, 'vertical'))

    return springs
