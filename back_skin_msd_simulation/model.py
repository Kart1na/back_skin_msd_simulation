import numpy as np
import config


class Particle:
    """Single mass point in the MSD mesh."""
    __slots__ = [
        'position', 'initial_position', 'velocity', 'force',
        'mass', 'layer_id', 'fixed', 'index', 'pid'
    ]

    def __init__(self, position, mass, layer_id, fixed, index, pid):
        self.position = position.copy().astype(np.float64)
        self.initial_position = position.copy().astype(np.float64)
        self.velocity = np.zeros(3, dtype=np.float64)
        self.force = np.zeros(3, dtype=np.float64)
        self.mass = mass
        self.layer_id = layer_id
        self.fixed = fixed
        self.index = index
        self.pid = pid


class BackSkinMSDModel:
    """Three-layer rectangular MSD grid for a local back skin region.

    Layer 0 (skin):         z = 0
    Layer 1 (muscle-fat):   z = -skin_thickness
    Layer 2 (bone/support): z = -(skin_thickness + muscle_fat_thickness)
    """

    def __init__(self, cfg=None):
        if cfg is None:
            cfg = config
        self.cfg = cfg
        self.nx = cfg.nx
        self.ny = cfg.ny
        self.num_layers = 3
        self.layer_z = [
            0.0,
            -cfg.skin_thickness,
            -(cfg.skin_thickness + cfg.muscle_fat_thickness),
        ]
        self.layers = [[], [], []]
        self._all_particles = []
        self._build_grid(cfg)

    def _build_grid(self, cfg):
        pid = 0
        x_start = -cfg.L / 2.0
        y_start = -cfg.W / 2.0
        for layer_id in range(self.num_layers):
            z = self.layer_z[layer_id]
            fixed = (layer_id == 2)
            layer_rows = []
            for j in range(self.ny):
                row = []
                for i in range(self.nx):
                    x = x_start + i * cfg.grid_spacing_x
                    y = y_start + j * cfg.grid_spacing_y
                    pos = np.array([x, y, z], dtype=np.float64)
                    p = Particle(pos, cfg.particle_mass_kg, layer_id,
                                 fixed, (layer_id, j, i), pid)
                    row.append(p)
                    self._all_particles.append(p)
                    pid += 1
                layer_rows.append(row)
            self.layers[layer_id] = layer_rows

    def get_particle(self, layer, j, i):
        return self.layers[layer][j][i]

    def get_skin_positions(self):
        """Return skin-layer positions as (ny, nx, 3)."""
        out = np.empty((self.ny, self.nx, 3), dtype=np.float64)
        for j in range(self.ny):
            for i in range(self.nx):
                out[j, i] = self.layers[0][j][i].position
        return out

    def get_skin_initial_positions(self):
        out = np.empty((self.ny, self.nx, 3), dtype=np.float64)
        for j in range(self.ny):
            for i in range(self.nx):
                out[j, i] = self.layers[0][j][i].initial_position
        return out

    def get_skin_displacements(self):
        return self.get_skin_positions() - self.get_skin_initial_positions()

    def clear_forces(self):
        for p in self._all_particles:
            p.force[:] = 0.0

    def reset_fixed_particles(self):
        for p in self._all_particles:
            if p.fixed:
                p.position[:] = p.initial_position
                p.velocity[:] = 0.0
                p.force[:] = 0.0

    def num_particles(self):
        return len(self._all_particles)

    def iter_particles(self):
        return iter(self._all_particles)

    def skin_particles(self):
        for j in range(self.ny):
            for i in range(self.nx):
                yield self.layers[0][j][i]
