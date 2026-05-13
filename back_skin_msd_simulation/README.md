# Back Skin MSD Deformation Simulation

Three-layer Mass-Spring-Damper (MSD) simulation of human back skin deformation
under robotic massage with a hemispherical probe.

## Purpose

Simulate how back skin and shallow soft tissue deform (normal indentation,
tangential stretching, and anterior piling) when a robot massage probe applies
normal force and slides along the skin surface.

## Theoretical Basis

Based on the paper: *Mass-Spring-Damper model for 3D skin deformation
simulation during human-robot contact motion*.

Core modelling elements retained:

1. **Three-layer MSD model** — skin, muscle-fat, bone/support layers.
2. **Kelvin-Voigt viscoelastic springs** — elastic + viscous damping in each
   spring element.
3. **Spherical probe contact detection** — anti-penetration constraint by
   projecting particles onto the probe sphere surface.
4. **Stick-slip friction** — tangential force switches between stick (full
   drag) and slip (dynamic friction) with hysteresis.
5. **Semi-implicit Euler integration** — velocity-first update for numerical
   stability.

## Differences from the Original Paper

| Aspect | Original paper | This project |
|--------|---------------|-------------|
| Body region | Forearm (stretch) / Upper arm (piling) | Back (upper or lumbar) |
| Geometry | Arm circumference scan | Flat rectangular grid |
| Tissue thickness | Arm-specific | Back-specific (3 mm skin, 25 mm muscle-fat, 8 mm support) |
| Probe | R=10 mm, F=5 N | R=15 mm, F=10 N, depth=5 mm |
| Friction model | Full paper formula with fitted tau0, alpha | Simplified mu_static / mu_dynamic (paper formula available as option) |
| Force control | Closed-loop | Open-loop depth-based approximation |
| Surface | Point-cloud mesh | Regular planar grid |
| Material params | Subject-specific calibration | Literature-range initial estimates |

## Default Back Parameters

| Parameter | Value | Note |
|-----------|-------|------|
| skin_thickness | 3 mm | Back epidermis+dermis equivalent |
| muscle_fat_thickness | 25 mm | Subcutaneous fat + superficial back muscle |
| E_skin | 40 kPa | Low-frequency equivalent modulus |
| E_muscle_fat | 45 kPa | Mixed soft tissue equivalent |
| E_bone_support | 200 kPa | Deep constraint (not real bone modulus) |
| probe_radius | 15 mm | Hemispherical massage head |
| normal_force | 10 N | Typical massage contact force |
| indentation_depth | 5 mm | Target press-down depth |

**Important:** These are initial estimates from literature ranges and
simulation stability considerations. They must be calibrated through:

- Back indentation experiments
- 3D point-cloud measurements (RealSense / Azure Kinect)
- Force-displacement curve fitting
- Individualised medical imaging (MRI / ultrasound)

## Installation

```bash
pip install numpy matplotlib scipy
```

## Usage

```bash
cd back_skin_msd_simulation
python main.py
```

Output images are saved to the `outputs/` folder.

## Modifying Parameters

Edit `config.py` to change:

- Grid resolution (`grid_spacing_x_mm`, `grid_spacing_y_mm`)
- Tissue thickness and modulus
- Probe size, force, velocity
- Friction model (`"simple"` or `"paper"`)
- Time step and damping

## Output Files

| File | Description |
|------|-------------|
| `back_skin_surface_t0.png` | Skin surface after press-down |
| `back_skin_surface_t1.png` | Early sliding phase |
| `back_skin_surface_t2.png` | Mid sliding phase |
| `back_skin_surface_t3.png` | Late sliding phase |
| `back_xz_cross_section_t3.png` | X-Z profile at Y=0 |
| `back_displacement_t3_x.png` | X-direction displacement map |
| `back_displacement_t3_z.png` | Z-direction displacement map |
| `back_displacement_t3_magnitude.png` | Total displacement magnitude |

## Project Structure

```
back_skin_msd_simulation/
  config.py          - All simulation parameters
  model.py           - Three-layer particle grid
  spring.py          - Kelvin-Voigt spring network
  probe.py           - Spherical massage probe
  simulator.py       - Dynamics integrator + friction
  visualization.py   - 3D surface / cross-section / displacement plots
  metrics.py         - MAE / SD error metrics (for future experiments)
  main.py            - Entry point
  README.md          - This file
  outputs/           - Generated images
```

## Future Extensions

- Import real back surface point-cloud (RealSense / Azure Kinect)
- Calibrate E_skin, E_muscle_fat, damping from indentation experiments
- Use full paper stick-slip formula with fitted tau0 and alpha
- Add anatomical back curvature
- Individualised soft tissue thickness from ultrasound / MRI
- Compute MAE and SD against experimental point-clouds
- Integrate robot trajectory and force-control data
- Animation output (GIF / MP4) via matplotlib.animation
