"""Coordinate alignment utilities for image, MSD back, and robot frames.

Public units are intentionally explicit:
    - Image points are pixels.
    - Back/MSD points returned by this module are millimetres.
    - Robot input points are metres, matching common robot SDK output.

The transform named ``T_back_robot`` maps homogeneous robot coordinates in mm
into homogeneous back coordinates in mm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:
    from back_region_map import locate_region
except ImportError:  # pragma: no cover - supports package-style imports too.
    from .back_region_map import locate_region


DEFAULT_IMAGE_TO_BACK_AFFINE: Optional[np.ndarray] = None


def _as_points(points: Sequence[Sequence[float]], dim: int, name: str) -> np.ndarray:
    arr = np.asarray(points, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != dim:
        raise ValueError(f"{name} must have shape (N, {dim})")
    if arr.shape[0] < dim:
        raise ValueError(f"{name} must contain at least {dim} points")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains NaN or Inf")
    return arr


def compute_image_to_back_affine(
    image_keypoints_px: Sequence[Sequence[float]],
    back_keypoints_mm: Sequence[Sequence[float]],
) -> np.ndarray:
    """Estimate a 2D affine transform from image pixels to back mm.

    Returns a 3x3 homogeneous matrix ``A`` such that:
        ``[x_mm, y_mm, 1]^T = A @ [x_px, y_px, 1]^T``

    Three non-collinear point pairs are sufficient; extra pairs are solved by
    least squares.
    """
    src = _as_points(image_keypoints_px, 2, "image_keypoints_px")
    dst = _as_points(back_keypoints_mm, 2, "back_keypoints_mm")
    if src.shape[0] != dst.shape[0]:
        raise ValueError("image_keypoints_px and back_keypoints_mm must match")

    src_h = np.column_stack([src, np.ones(src.shape[0], dtype=np.float64)])
    coeff, residuals, rank, _ = np.linalg.lstsq(src_h, dst, rcond=None)
    if rank < 3:
        raise ValueError("image keypoints are degenerate for affine fitting")

    matrix = np.eye(3, dtype=np.float64)
    matrix[:2, :] = coeff.T
    return matrix


def set_default_image_to_back_affine(affine_matrix: Sequence[Sequence[float]]) -> None:
    """Set the module-level affine used by ``image_to_back_xy``."""
    global DEFAULT_IMAGE_TO_BACK_AFFINE
    matrix = np.asarray(affine_matrix, dtype=np.float64)
    if matrix.shape != (3, 3):
        raise ValueError("affine_matrix must have shape (3, 3)")
    DEFAULT_IMAGE_TO_BACK_AFFINE = matrix


def image_to_back_xy(
    x_px: float,
    y_px: float,
    affine_matrix: Optional[Sequence[Sequence[float]]] = None,
) -> Tuple[float, float]:
    """Map one image pixel coordinate to the standard back 2D frame in mm."""
    matrix = DEFAULT_IMAGE_TO_BACK_AFFINE if affine_matrix is None else affine_matrix
    if matrix is None:
        raise ValueError("No affine matrix provided or configured")

    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.shape != (3, 3):
        raise ValueError("affine_matrix must have shape (3, 3)")

    out = matrix @ np.array([float(x_px), float(y_px), 1.0], dtype=np.float64)
    if abs(out[2]) < 1e-12:
        raise ValueError("Invalid affine output with zero homogeneous scale")
    return float(out[0] / out[2]), float(out[1] / out[2])


def _skin_positions_from_snapshot(snapshot: Any) -> np.ndarray:
    if snapshot is None:
        raise ValueError("snapshot is required")
    if isinstance(snapshot, dict):
        if "skin_positions" not in snapshot:
            raise ValueError("snapshot dict must contain 'skin_positions'")
        positions = snapshot["skin_positions"]
    elif hasattr(snapshot, "get_skin_positions"):
        positions = snapshot.get_skin_positions()
    else:
        positions = snapshot

    arr = np.asarray(positions, dtype=np.float64)
    if arr.ndim != 3 or arr.shape[2] < 3:
        raise ValueError("skin positions must have shape (ny, nx, 3)")
    if not np.all(np.isfinite(arr)):
        raise ValueError("skin positions contain NaN or Inf")

    # The existing MSD model stores coordinates in metres. Convert likely-metre
    # arrays into mm while leaving already-mm point clouds untouched.
    max_abs = float(np.max(np.abs(arr[:, :, :3]))) if arr.size else 0.0
    if max_abs <= 5.0:
        arr = arr[:, :, :3] * 1000.0
    else:
        arr = arr[:, :, :3].copy()
    return arr


def interpolate_skin_z_mm(snapshot: Any, x_mm: float, y_mm: float) -> float:
    """Interpolate the skin surface height z at a back-frame (x, y) in mm.

    For the regular MSD grid this uses bilinear interpolation. If the queried
    point lies outside the grid, the result is clamped to the nearest edge.
    """
    positions = _skin_positions_from_snapshot(snapshot)
    xs = positions[0, :, 0]
    ys = positions[:, 0, 1]
    zs = positions[:, :, 2]

    x = float(x_mm)
    y = float(y_mm)

    if len(xs) < 2 or len(ys) < 2:
        flat_xy = positions[:, :, :2].reshape(-1, 2)
        flat_z = zs.reshape(-1)
        idx = int(np.argmin(np.sum((flat_xy - np.array([x, y])) ** 2, axis=1)))
        return float(flat_z[idx])

    if xs[0] > xs[-1]:
        xs = xs[::-1]
        zs = zs[:, ::-1]
    if ys[0] > ys[-1]:
        ys = ys[::-1]
        zs = zs[::-1, :]

    x = float(np.clip(x, xs[0], xs[-1]))
    y = float(np.clip(y, ys[0], ys[-1]))
    i1 = int(np.searchsorted(xs, x, side="right"))
    j1 = int(np.searchsorted(ys, y, side="right"))
    i0 = max(0, min(i1 - 1, len(xs) - 2))
    j0 = max(0, min(j1 - 1, len(ys) - 2))
    i1 = i0 + 1
    j1 = j0 + 1

    x0, x1 = xs[i0], xs[i1]
    y0, y1 = ys[j0], ys[j1]
    tx = 0.0 if abs(x1 - x0) < 1e-12 else (x - x0) / (x1 - x0)
    ty = 0.0 if abs(y1 - y0) < 1e-12 else (y - y0) / (y1 - y0)

    z00 = zs[j0, i0]
    z10 = zs[j0, i1]
    z01 = zs[j1, i0]
    z11 = zs[j1, i1]
    z0 = (1.0 - tx) * z00 + tx * z10
    z1 = (1.0 - tx) * z01 + tx * z11
    return float((1.0 - ty) * z0 + ty * z1)


def compute_T_back_robot(
    robot_calibration_xyz_m: Sequence[Sequence[float]],
    back_calibration_xyz_mm: Sequence[Sequence[float]],
) -> np.ndarray:
    """Estimate rigid transform from robot coordinates to back coordinates.

    ``T_back_robot`` maps ``[robot_x_mm, robot_y_mm, robot_z_mm, 1]`` to
    ``[back_x_mm, back_y_mm, back_z_mm, 1]``.
    """
    robot_mm = _as_points(robot_calibration_xyz_m, 3, "robot_calibration_xyz_m") * 1000.0
    back_mm = _as_points(back_calibration_xyz_mm, 3, "back_calibration_xyz_mm")
    if robot_mm.shape[0] != back_mm.shape[0]:
        raise ValueError("robot and back calibration point counts must match")
    if robot_mm.shape[0] < 3:
        raise ValueError("at least 3 calibration point pairs are required")

    src_centroid = np.mean(robot_mm, axis=0)
    dst_centroid = np.mean(back_mm, axis=0)
    src_centered = robot_mm - src_centroid
    dst_centered = back_mm - dst_centroid

    h = src_centered.T @ dst_centered
    u, _, vt = np.linalg.svd(h)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1.0
        rotation = vt.T @ u.T
    translation = dst_centroid - rotation @ src_centroid

    matrix = np.eye(4, dtype=np.float64)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation
    return matrix


def robot_to_back_mm(
    robot_xyz_m: Sequence[float],
    T_back_robot: Sequence[Sequence[float]],
) -> Tuple[float, float, float]:
    """Apply ``T_back_robot`` to one robot end-effector point."""
    point_m = np.asarray(robot_xyz_m, dtype=np.float64)
    matrix = np.asarray(T_back_robot, dtype=np.float64)
    if point_m.shape != (3,):
        raise ValueError("robot_xyz_m must have shape (3,)")
    if matrix.shape != (4, 4):
        raise ValueError("T_back_robot must have shape (4, 4)")
    out = matrix @ np.array(
        [point_m[0] * 1000.0, point_m[1] * 1000.0, point_m[2] * 1000.0, 1.0],
        dtype=np.float64,
    )
    return float(out[0]), float(out[1]), float(out[2])


@dataclass
class MassageCoordinateSystem:
    """High-level coordinate interface for real-time massage analysis."""

    image_keypoints_px: Optional[Sequence[Sequence[float]]] = None
    back_keypoints_mm: Optional[Sequence[Sequence[float]]] = None
    robot_calibration_xyz_m: Optional[Sequence[Sequence[float]]] = None
    back_calibration_xyz_mm: Optional[Sequence[Sequence[float]]] = None
    acupoints: Optional[Sequence[Dict[str, Any]]] = None
    snapshot: Any = None

    def __post_init__(self) -> None:
        self.image_to_back_affine: Optional[np.ndarray] = None
        self.T_back_robot: Optional[np.ndarray] = None
        self.records: List[Dict[str, Any]] = []

        if self.image_keypoints_px is not None or self.back_keypoints_mm is not None:
            if self.image_keypoints_px is None or self.back_keypoints_mm is None:
                raise ValueError("Both image and back keypoints are required")
            self.image_to_back_affine = compute_image_to_back_affine(
                self.image_keypoints_px,
                self.back_keypoints_mm,
            )

        if self.robot_calibration_xyz_m is not None or self.back_calibration_xyz_mm is not None:
            if self.robot_calibration_xyz_m is None or self.back_calibration_xyz_mm is None:
                raise ValueError("Both robot and back calibration points are required")
            self.T_back_robot = compute_T_back_robot(
                self.robot_calibration_xyz_m,
                self.back_calibration_xyz_mm,
            )

    def image_to_back_xy(self, x_px: float, y_px: float) -> Tuple[float, float]:
        if self.image_to_back_affine is None:
            raise ValueError("image-to-back affine has not been configured")
        return image_to_back_xy(x_px, y_px, self.image_to_back_affine)

    def robot_to_back_mm(self, robot_xyz_m: Sequence[float]) -> Tuple[float, float, float]:
        if self.T_back_robot is None:
            raise ValueError("T_back_robot has not been configured")
        return robot_to_back_mm(robot_xyz_m, self.T_back_robot)

    def find_nearest_acupoint(self, x_mm: float, y_mm: float) -> Optional[Dict[str, Any]]:
        """Return nearest acupoint dictionary with distance_mm, or None."""
        if not self.acupoints:
            return None

        best: Optional[Dict[str, Any]] = None
        best_dist = float("inf")
        x = float(x_mm)
        y = float(y_mm)

        for item in self.acupoints:
            if "x_mm" not in item or "y_mm" not in item:
                continue
            dx = x - float(item["x_mm"])
            dy = y - float(item["y_mm"])
            dist = float(np.hypot(dx, dy))
            if dist < best_dist:
                best_dist = dist
                best = dict(item)

        if best is None:
            return None
        best["distance_mm"] = best_dist
        return best

    def analyze_robot_tip(
        self,
        timestamp_s: float,
        robot_xyz_m: Sequence[float],
        force_N: Optional[float] = None,
        indentation_mm: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Convert a robot tip sample into synchronized back-frame context."""
        x_mm, y_mm, z_mm = self.robot_to_back_mm(robot_xyz_m)
        if self.snapshot is not None:
            z_mm = interpolate_skin_z_mm(self.snapshot, x_mm, y_mm)

        region = locate_region(x_mm, y_mm)
        acupoint = self.find_nearest_acupoint(x_mm, y_mm)
        record = {
            "timestamp_s": float(timestamp_s),
            "robot_xyz_m": [float(v) for v in robot_xyz_m],
            "back_xyz_mm": [float(x_mm), float(y_mm), float(z_mm)],
            "region": region,
            "acupoint": acupoint,
            "force_N": None if force_N is None else float(force_N),
            "indentation_mm": None if indentation_mm is None else float(indentation_mm),
        }
        self.records.append(record)
        return record
