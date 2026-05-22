import numpy as np
import os

def mm_to_m(v):
    return v * 1e-3

def kPa_to_Pa(v):
    return v * 1e3

# 1. Back region geometry
L_mm = 220.0
W_mm = 120.0
H_mm = 35.0
L = mm_to_m(L_mm)
W = mm_to_m(W_mm)
H = mm_to_m(H_mm)

# 2. Three-layer tissue thickness
skin_thickness_mm = 3.0
muscle_fat_thickness_mm = 25.0
bone_support_thickness_mm = 8.0
skin_thickness = mm_to_m(skin_thickness_mm)
muscle_fat_thickness = mm_to_m(muscle_fat_thickness_mm)
bone_support_thickness = mm_to_m(bone_support_thickness_mm)

# 3. Grid spacing
grid_spacing_x_mm = 5.0
grid_spacing_y_mm = 5.0
grid_spacing_x = mm_to_m(grid_spacing_x_mm)
grid_spacing_y = mm_to_m(grid_spacing_y_mm)
nx = int(round(L_mm / grid_spacing_x_mm)) + 1
ny = int(round(W_mm / grid_spacing_y_mm)) + 1

# 4. Particle mass
particle_mass_kg = 0.0015

# 5. Young modulus (kPa -> Pa)
E_skin_kPa = 40.0
E_muscle_fat_kPa = 45.0
E_bone_support_kPa = 200.0
E_skin = kPa_to_Pa(E_skin_kPa)
E_muscle_fat = kPa_to_Pa(E_muscle_fat_kPa)
E_bone_support = kPa_to_Pa(E_bone_support_kPa)

# 6. Poisson ratio
poisson_ratio = 0.48

# 7. Empirical spring stiffness (N/m)
k_skin_N_m = 1800.0
k_muscle_fat_N_m = 3500.0
k_bone_support_N_m = 15000.0

def compute_spring_stiffness(E_Pa, poisson, grid_spacing):
    """Reserved interface for calibration-based stiffness computation."""
    return E_Pa * grid_spacing / (1.0 - poisson ** 2)

# 8. Damping
damping = 0.85
global_damping_factor = 0.995

# 9. Massage probe
probe_radius_mm = 15.0
normal_force_N = 10.0
probe_velocity_mm_s = 5.0
travel_distance_mm = 120.0
indentation_depth_mm = 5.0
probe_radius = mm_to_m(probe_radius_mm)
normal_force = normal_force_N
probe_velocity = mm_to_m(probe_velocity_mm_s)
travel_distance = mm_to_m(travel_distance_mm)
indentation_depth = mm_to_m(indentation_depth_mm)

# 10. Press duration
press_duration_s = 1.0

# 11. Numerical integration
dt = 0.001
max_velocity_m_s = 0.5
max_step_displacement_m = 0.001
total_time = press_duration_s + travel_distance / probe_velocity

# 12. Friction
friction_model = 'simple'
mu_static = 0.9
mu_dynamic = 0.45
tau0 = 500.0
alpha = 0.3
contact_tangent_gain = 20.0

# 13. Snapshot interval
snapshot_interval = 200

# 14. Output directory
output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'outputs')
