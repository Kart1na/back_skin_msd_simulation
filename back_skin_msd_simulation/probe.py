import numpy as np
import config


class SphericalProbe:
    """Rigid hemispherical massage probe.

    Phase 1 (press):  linear descent to target indentation depth.
    Phase 2 (slide):  constant-depth travel along +X.
    """

    def __init__(self, cfg=None):
        if cfg is None:
            cfg = config
        self.radius = cfg.probe_radius
        self.normal_force = cfg.normal_force
        self.indentation_depth = cfg.indentation_depth
        self.press_duration = cfg.press_duration_s
        self.probe_velocity_scalar = cfg.probe_velocity
        self.travel_distance = cfg.travel_distance
        self.motion_direction = np.array([1.0, 0.0, 0.0])

        x0 = -self.travel_distance / 2.0
        y0 = 0.0
        z0 = self.radius + 0.008   # start 8 mm above skin surface
        self.initial_center = np.array([x0, y0, z0], dtype=np.float64)
        self.center = self.initial_center.copy()
        self.target_z = self.radius - self.indentation_depth
        self._velocity = np.zeros(3, dtype=np.float64)

    def update(self, t, dt):
        """Update probe centre position based on simulation time."""
        if t <= self.press_duration:
            # Phase 1: linear press-down
            frac = t / self.press_duration
            z = self.initial_center[2] + frac * (self.target_z - self.initial_center[2])
            self.center[0] = self.initial_center[0]
            self.center[1] = self.initial_center[1]
            self.center[2] = z
            self._velocity[:] = 0.0
            self._velocity[2] = (self.target_z - self.initial_center[2]) / self.press_duration
        else:
            # Phase 2: constant-depth slide along +X
            elapsed = t - self.press_duration
            self.center[0] = self.initial_center[0] + self.probe_velocity_scalar * elapsed
            self.center[1] = self.initial_center[1]
            self.center[2] = self.target_z
            self._velocity[:] = 0.0
            self._velocity[0] = self.probe_velocity_scalar

    def get_probe_velocity(self):
        return self._velocity.copy()

    def get_contact_particles(self, model):
        """Return skin-layer particles currently inside the probe sphere."""
        contacts = []
        for p in model.skin_particles():
            d = p.position - self.center
            dist = np.linalg.norm(d)
            if dist < self.radius:
                contacts.append(p)
        return contacts

    def resolve_collision(self, model):
        """Push penetrating skin particles onto sphere surface
        and remove inward normal velocity component."""
        for p in model.skin_particles():
            d = p.position - self.center
            dist = np.linalg.norm(d)
            if dist < 1e-12:
                p.position = self.center + np.array([0.0, 0.0, self.radius])
                p.velocity[:] = 0.0
                continue
            if dist < self.radius:
                normal = d / dist
                p.position = self.center + normal * self.radius
                v_normal = np.dot(p.velocity, normal)
                if v_normal < 0.0:
                    p.velocity -= v_normal * normal
