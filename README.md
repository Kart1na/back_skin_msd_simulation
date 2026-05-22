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

## 智能按摩 MVP

该 MVP 实现：

1. 背部区域识别
2. 加载个体化背部模型
3. 推荐区域按压力度
4. 判断当前力度风险

示例命令：

```bash
cd back_skin_msd_simulation
python mvp_demo.py --user_id user_001 --x -45 --y -80 --force 10 --indentation 5.1
```

说明：

- `x`, `y` 是背部二维坐标，单位 mm
- `force` 是当前法向力，单位 N
- `indentation` 是当前压入深度，单位 mm
- 输出结果保存在 `outputs/{user_id}_mvp_report.json`

## 背部刚度检测报告

该功能根据按摩过程中的力-位移数据，计算局部等效刚度，并生成僵硬程度参考报告和二维热力图。报告用于按摩参数参考，不构成医疗诊断。

### 输入数据格式

默认读取：

```bash
back_skin_msd_simulation/user_data/{user_id}_first_massage.csv
```

也可以指定 `stiffness_test.csv` 或其他 CSV。至少需要以下字段：

- `normal_force_N`：当前法向力，单位 N
- `indentation_mm`：当前压入深度，单位 mm

可选字段：

- `point_id`：检测点 ID
- `region`：背部区域名称
- `section`：Upper Back / Mid Back / Lower Back
- `x_mm`, `y_mm`：背部二维坐标，单位 mm
- `probe_x_mm`, `probe_y_mm`：如果没有 `x_mm`, `y_mm`，会作为坐标回退字段

如果 `indentation_mm <= 0`，该数据点会被跳过，避免除零。

### 如何运行

```bash
cd back_skin_msd_simulation

python synthetic_stiffness_test.py --user_id user_001 --profile severe_right_lower
python stiffness_estimator.py --user_id user_001 --data user_data/user_001_stiffness_test.csv
python stiffness_report_generator.py --user_id user_001 --data user_data/user_001_stiffness_test.csv
python back_stiffness_map.py --user_id user_001
```

`synthetic_stiffness_test.py` 会根据用户个体化模型生成覆盖 Upper / Mid / Lower Back 的多区域刚度测试数据。`profile` 可模拟不同僵硬分布，例如：

- `realistic`：温和真实差异
- `mild_asymmetry`：轻度左右不对称
- `severe_right_lower`：右下背明显僵硬
- `upper_shoulder_tension`：肩颈上背紧张

也可以直接使用已有首按摩数据：

```bash
cd back_skin_msd_simulation

python stiffness_estimator.py --user_id user_001 --data user_data/user_001_first_massage.csv
python stiffness_report_generator.py --user_id user_001
python back_stiffness_map.py --user_id user_001
```

输出文件保存在 `outputs/`：

- `outputs/{user_id}_stiffness_stats.json`
- `outputs/{user_id}_stiffness_grades.json`
- `outputs/{user_id}_stiffness_report.json`
- `outputs/{user_id}_stiffness_report.md`
- `outputs/{user_id}_stiffness_map.png`

### A/B/C/D 解释

默认使用 `relative` 模式，即相对于用户本次背部平均刚度进行分级：

| Grade | Score | Label |
|-------|-------|-------|
| A | `< 0.85` | Mild |
| B | `0.85 - 1.15` | Moderate |
| C | `1.15 - 1.45` | High |
| D | `>= 1.45` | Severe |

也可使用 `absolute` 模式，基于固定 N/m 参考刚度分级：

```bash
python stiffness_report_generator.py --user_id user_001 --mode absolute
```

**Disclaimer:** 刚度检测报告仅用于僵硬程度参考和按摩参数参考，不构成医疗诊断。如存在疼痛、麻木、外伤、炎症或其他不适，应咨询专业医生或康复治疗师。

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
  personalization.py     - Stage 1: demographics -> initial back model
  first_massage_logger.py - First-massage data recorder + synthetic generator
  parameter_fitting.py   - Stage 2: force-displacement -> calibrated model
  user_model.py          - Priority-based user model loader
  main.py                - Entry point (supports --user_id)
  outputs/               - Generated images and model JSONs
  user_data/             - Per-user first-massage CSV recordings
```

## Two-Stage Individualised Back Modelling

The system personalises the MSD back model in two stages:

### Stage 1: Demographics → Initial Model

Before the first massage, the system generates a **conservative initial model**
from the user's age, sex, BMI, and target region.

- BMI adjusts muscle-fat thickness, stiffness, and damping
- Age adjusts skin stiffness and damping
- Sex applies small corrections
- Region (upper / middle / lower back) shifts layer parameters

This model is a rough estimate — not a precision model.

### Stage 2: First-Massage Force-Displacement Curve → Calibrated Model

During the first massage the system records force-displacement data.
After the session, the recorded curve is used to **optimise MSD parameters**
(k_skin, k_muscle_fat, damping, friction coefficients) so the simulation
matches the measured indentation.

This calibrated model is the **precision personalised model**.

### Subsequent Sessions

On every subsequent massage, the system **automatically loads the calibrated
model** if it exists; otherwise it falls back to the initial model, then to
the global default.

### Quick-Start Example

```bash
cd back_skin_msd_simulation

# Stage 1: generate initial model
python personalization.py --user_id user_001 --age 25 --sex male --bmi 24.2 --region lower_back

# Record first massage (synthetic test data)
python first_massage_logger.py --user_id user_001 --synthetic

# Stage 2: fit parameters from first-massage data
python parameter_fitting.py --user_id user_001

# Run simulation with personalised model
python main.py --user_id user_001
```

> **Note:** Age, sex, and BMI can only produce an initial estimate.
> The force-displacement curve from the first massage is the key input
> for precision individualisation.

## Future Extensions

- Import real back surface point-cloud (RealSense / Azure Kinect)
- Full MSD simulation-in-the-loop parameter optimisation
- Use full paper stick-slip formula with fitted tau0 and alpha
- Add anatomical back curvature
- Individualised soft tissue thickness from ultrasound / MRI
- Compute MAE and SD against experimental point-clouds
- Integrate robot trajectory and force-control data
- Animation output (GIF / MP4) via matplotlib.animation
