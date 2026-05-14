"""
Phase 1.5 - strict analytic cycloidal generation tied to a mating gear.

This file replaces the transition-bridge approach with direct analytic
hypocycloid/epicycloid segments parameterized from a gear pair definition.
No smoothing spline is used at the pitch join.

Outputs:
- One closed tooth polygon for the primary gear (mm units).
- Plot for visual validation.
- CSV export for downstream SolidWorks macro import.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np


@dataclass(frozen=True)
class GearSpec:
    z: int
    module: float
    addendum_factor: float = 1.0
    dedendum_factor: float = 1.25

    @property
    def pitch_radius(self) -> float:
        return 0.5 * self.module * self.z

    @property
    def addendum_radius(self) -> float:
        return self.pitch_radius + self.addendum_factor * self.module

    @property
    def root_radius(self) -> float:
        return max(0.05 * self.module, self.pitch_radius - self.dedendum_factor * self.module)


@dataclass(frozen=True)
class StrictCycloidalTooth:
    points: np.ndarray
    left_flank: np.ndarray
    right_flank: np.ndarray
    pitch_point_left: np.ndarray
    pitch_point_right: np.ndarray
    join_tangent_mismatch: float


def _rotate(points: np.ndarray, angle: float) -> np.ndarray:
    c = math.cos(angle)
    s = math.sin(angle)
    rot = np.array([[c, -s], [s, c]])
    return points @ rot.T


def _epicycloid(R: float, r: float, t: np.ndarray) -> np.ndarray:
    x = (R + r) * np.cos(t) - r * np.cos(((R + r) / r) * t)
    y = (R + r) * np.sin(t) - r * np.sin(((R + r) / r) * t)
    return np.column_stack((x, y))


def _hypocycloid(R: float, r: float, t: np.ndarray) -> np.ndarray:
    x = (R - r) * np.cos(t) + r * np.cos(((R - r) / r) * t)
    y = (R - r) * np.sin(t) - r * np.sin(((R - r) / r) * t)
    return np.column_stack((x, y))


def _curve_radius(points: np.ndarray) -> np.ndarray:
    return np.sqrt(points[:, 0] ** 2 + points[:, 1] ** 2)


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    if n < 1e-14:
        return np.array([1.0, 0.0])
    return v / n


def _find_t_for_radius(
    curve_fn: Callable[[float, float, np.ndarray], np.ndarray],
    R: float,
    r: float,
    target_radius: float,
    t_max: float,
) -> float:
    # Coarse search first for a bracket.
    scan = np.linspace(0.0, t_max, 500)
    pts = curve_fn(R, r, scan)
    rr = _curve_radius(pts)
    f = rr - target_radius

    bracket_idx = None
    for i in range(len(f) - 1):
        if f[i] == 0.0:
            return float(scan[i])
        if f[i] * f[i + 1] <= 0.0:
            bracket_idx = i
            break

    if bracket_idx is None:
        # Fallback to nearest value if monotonic range did not cross exactly.
        j = int(np.argmin(np.abs(f)))
        return float(scan[j])

    a = float(scan[bracket_idx])
    b = float(scan[bracket_idx + 1])

    # Bisection refinement.
    for _ in range(60):
        m = 0.5 * (a + b)
        fm = float(_curve_radius(curve_fn(R, r, np.array([m])))[0] - target_radius)
        fa = float(_curve_radius(curve_fn(R, r, np.array([a])))[0] - target_radius)
        if fa * fm <= 0.0:
            b = m
        else:
            a = m
    return 0.5 * (a + b)


def _arc_points(radius: float, theta_start: float, theta_end: float, n: int) -> np.ndarray:
    t = np.linspace(theta_start, theta_end, n)
    return np.column_stack((radius * np.cos(t), radius * np.sin(t)))


def strict_cycloidal_tooth_points(
    z_gear: int,
    z_mate: int,
    module: float,
    n_samples: int = 420,
) -> StrictCycloidalTooth:
    if z_gear < 6 or z_mate < 6:
        raise ValueError("z_gear and z_mate must both be >= 6")
    if module <= 0.0:
        raise ValueError("module must be > 0")
    if n_samples < 180:
        raise ValueError("n_samples must be >= 180")

    gear = GearSpec(z=z_gear, module=module)
    mate = GearSpec(z=z_mate, module=module)

    R = gear.pitch_radius
    # Strict mating-gear tie: generating rolling radius from mating pitch radius.
    r_gen = mate.pitch_radius

    if r_gen >= R:
        raise ValueError(
            "For this direct construction, mating pitch radius must be smaller than target gear pitch radius. "
            "Swap z_gear and z_mate if needed."
        )

    # Tooth half-thickness at pitch circle for standard thickness.
    half_tooth_pitch_angle = math.pi / (2.0 * z_gear)

    # Use conservative parameter window; solve for root/tip intersections.
    t_tip = _find_t_for_radius(_epicycloid, R, r_gen, gear.addendum_radius, t_max=0.9)
    t_root = _find_t_for_radius(_hypocycloid, R, r_gen, gear.root_radius, t_max=0.9)

    # Split point budget across segments.
    n_h = max(40, n_samples // 4)
    n_e = max(40, n_samples // 4)
    n_tip_arc = max(24, n_samples // 8)
    n_root_arc = max(24, n_samples // 8)

    eps = 1e-4
    t_h = np.linspace(t_root, eps, n_h)
    t_e = np.linspace(eps, t_tip, n_e)

    h_seg = _hypocycloid(R, r_gen, t_h)
    e_seg = _epicycloid(R, r_gen, t_e)

    # Left flank from root -> pitch -> tip.
    left_flank = np.vstack((h_seg, e_seg))
    left_flank = _rotate(left_flank, +half_tooth_pitch_angle)

    # Mirror for right flank, tip -> pitch -> root then reverse to root -> ... -> tip.
    right_flank = left_flank.copy()
    right_flank[:, 1] *= -1.0
    right_flank = right_flank[::-1]

    # Connect tip side with addendum arc and root side with root arc.
    left_tip = left_flank[-1]
    right_tip = right_flank[0]
    left_root = left_flank[0]
    right_root = right_flank[-1]

    th_lt = math.atan2(left_tip[1], left_tip[0])
    th_rt = math.atan2(right_tip[1], right_tip[0])
    th_lr = math.atan2(left_root[1], left_root[0])
    th_rr = math.atan2(right_root[1], right_root[0])

    tip_arc = _arc_points(gear.addendum_radius, th_lt, th_rt, n_tip_arc)
    root_arc = _arc_points(gear.root_radius, th_rr, th_lr, n_root_arc)

    # Closed tooth polygon (clockwise): left root -> left tip -> right tip -> right root -> left root.
    tooth = np.vstack((
        left_flank,
        tip_arc[1:-1],
        right_flank,
        root_arc[1:-1],
        left_flank[:1],
    ))

    # Numeric tangent mismatch near pitch join from each analytic side.
    lh = _rotate(_hypocycloid(R, r_gen, np.array([2.2e-3, 1.2e-3])), +half_tooth_pitch_angle)
    le = _rotate(_epicycloid(R, r_gen, np.array([1.2e-3, 2.2e-3])), +half_tooth_pitch_angle)
    t_h_join = _unit(lh[1] - lh[0])
    t_e_join = _unit(le[1] - le[0])
    mismatch = float(np.linalg.norm(t_h_join - t_e_join))

    pitch_left = _rotate(np.array([[R, 0.0]]), +half_tooth_pitch_angle)[0]
    pitch_right = np.array([pitch_left[0], -pitch_left[1]])

    return StrictCycloidalTooth(
        points=tooth,
        left_flank=left_flank,
        right_flank=right_flank,
        pitch_point_left=pitch_left,
        pitch_point_right=pitch_right,
        join_tangent_mismatch=mismatch,
    )


def export_points_csv(points: np.ndarray, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="ascii") as f:
        w = csv.writer(f)
        w.writerow(["index", "x_mm", "y_mm"])
        for i, (x, y) in enumerate(points):
            w.writerow([i, f"{x:.8f}", f"{y:.8f}"])


def plot_tooth(tooth: StrictCycloidalTooth, z_gear: int, z_mate: int, module: float) -> None:
    R = 0.5 * module * z_gear
    Ra = R + module
    Rf = max(0.05 * module, R - 1.25 * module)

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.plot(tooth.points[:, 0], tooth.points[:, 1], lw=2.0, label="Strict analytic tooth")

    for rad, lbl, ls in [
        (R, "Pitch", "--"),
        (Ra, "Addendum", ":"),
        (Rf, "Root", ":"),
    ]:
        c = plt.Circle((0.0, 0.0), rad, fill=False, linestyle=ls, alpha=0.55, label=f"{lbl} circle")
        ax.add_patch(c)

    ax.scatter([tooth.pitch_point_left[0], tooth.pitch_point_right[0]], [tooth.pitch_point_left[1], tooth.pitch_point_right[1]], s=30)

    ax.set_aspect("equal", "box")
    ax.grid(True, alpha=0.25)
    ax.set_title(
        f"Strict Cycloidal Tooth (z1={z_gear}, z2={z_mate}, m={module}) | "
        f"pitch-join tangent mismatch={tooth.join_tangent_mismatch:.3e}"
    )
    ax.legend(loc="upper right")
    plt.show()


if __name__ == "__main__":
    # Primary gear is the larger wheel; mating gear is the smaller pinion.
    Z_GEAR = 25
    Z_MATE = 10
    MODULE = 2.0
    SAMPLES = 500

    result = strict_cycloidal_tooth_points(
        z_gear=Z_GEAR,
        z_mate=Z_MATE,
        module=MODULE,
        n_samples=SAMPLES,
    )

    out_csv = Path(__file__).with_name("strict_cycloidal_tooth_points.csv")
    export_points_csv(result.points, out_csv)

    print(f"Saved CSV: {out_csv}")
    print(f"Pitch-join tangent mismatch norm: {result.join_tangent_mismatch:.6e}")

    plot_tooth(result, z_gear=Z_GEAR, z_mate=Z_MATE, module=MODULE)
