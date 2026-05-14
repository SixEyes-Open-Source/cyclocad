"""
Phase 1.5 - strict analytic cycloidal generation tied to a mating gear.

This file replaces the transition-bridge approach with direct analytic
hypocycloid/epicycloid segments parameterized from a gear pair definition.
No smoothing spline is used at the pitch join.

Outputs:
- One closed tooth polygon for the primary gear (mm units).
- One full closed gear outline built by rotating that tooth around the center.
- Plot for visual validation.
- CSV and DXF export for downstream CAD import.
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

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


@dataclass(frozen=True)
class MeshSanityReport:
    center_distance: float
    pitch_circle_closure_error: float
    primary_tip_to_mate_root_clearance: float
    mate_tip_to_primary_root_clearance: float
    estimated_transverse_contact_ratio: float

    @property
    def has_radial_interference_risk(self) -> bool:
        return (
            self.primary_tip_to_mate_root_clearance < 0.0
            or self.mate_tip_to_primary_root_clearance < 0.0
        )


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
        rr_min = float(np.min(rr))
        rr_max = float(np.max(rr))
        j = int(np.argmin(np.abs(f)))
        # Allow exact/near-exact tangency; otherwise fail loudly instead of silently
        # returning an incorrect nearest point.
        if abs(float(f[j])) <= 1e-9:
            return float(scan[j])
        raise ValueError(
            f"Could not bracket radius intersection for target={target_radius:.6f} mm "
            f"within sampled curve radius range [{rr_min:.6f}, {rr_max:.6f}] mm. "
            "Try a different tooth pair/module or increase the parameter search window."
        )

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


def build_full_gear_outline(tooth_points: np.ndarray, z_gear: int) -> np.ndarray:
    """Replicate one closed tooth around the center to form a full closed gear outline."""
    if z_gear < 6:
        raise ValueError("z_gear must be >= 6")
    if len(tooth_points) < 4:
        raise ValueError("tooth_points must contain at least 4 points")

    # Drop the closing point to avoid duplicate vertices when stitching teeth.
    tooth_open = tooth_points[:-1]
    all_pts = []
    for k in range(z_gear):
        ang = (2.0 * math.pi * k) / float(z_gear)
        all_pts.append(_rotate(tooth_open, ang))

    full = np.vstack(all_pts)
    full = np.vstack((full, full[:1]))
    return full


def evaluate_mesh_sanity(
    z_gear: int,
    z_mate: int,
    module: float,
    *,
    addendum_factor: float = 1.0,
    dedendum_factor: float = 1.25,
) -> MeshSanityReport:
    """Compute conservative pair-level mesh sanity metrics.

    These are radial and kinematic checks, not a full contact simulation.
    """
    if z_gear < 6 or z_mate < 6:
        raise ValueError("z_gear and z_mate must both be >= 6")
    if module <= 0.0:
        raise ValueError("module must be > 0")

    g1 = GearSpec(z=z_gear, module=module, addendum_factor=addendum_factor, dedendum_factor=dedendum_factor)
    g2 = GearSpec(z=z_mate, module=module, addendum_factor=addendum_factor, dedendum_factor=dedendum_factor)

    center_distance = g1.pitch_radius + g2.pitch_radius
    pitch_circle_closure_error = abs(center_distance - (g1.pitch_radius + g2.pitch_radius))

    # Conservative radial tip/root clearance checks for both directions.
    primary_tip_to_mate_root_clearance = (center_distance - g1.addendum_radius) - g2.root_radius
    mate_tip_to_primary_root_clearance = (center_distance - g2.addendum_radius) - g1.root_radius

    # Approximate transverse contact ratio from radial approach/recess lengths.
    # This is a rough screening metric and not exact cycloidal contact ratio.
    path_len_est = max(0.0, g1.addendum_radius - g1.pitch_radius) + max(0.0, g2.addendum_radius - g2.pitch_radius)
    base_pitch = math.pi * module
    contact_ratio_est = path_len_est / base_pitch if base_pitch > 0.0 else 0.0

    return MeshSanityReport(
        center_distance=center_distance,
        pitch_circle_closure_error=pitch_circle_closure_error,
        primary_tip_to_mate_root_clearance=primary_tip_to_mate_root_clearance,
        mate_tip_to_primary_root_clearance=mate_tip_to_primary_root_clearance,
        estimated_transverse_contact_ratio=contact_ratio_est,
    )


def _is_closed_polygon(points: np.ndarray, tol: float = 1e-8) -> bool:
    if len(points) < 4:
        return False
    return float(np.linalg.norm(points[0] - points[-1])) <= tol


def run_regression_checks() -> None:
    """Run lightweight geometry regressions for representative gear pairs."""
    cases = [
        (25, 10, 2.0, 500),
        (30, 12, 1.5, 420),
        (40, 16, 1.0, 420),
    ]

    mismatch_threshold = 1.0e-2
    radius_tol = 5.0e-3

    for z_gear, z_mate, module, samples in cases:
        tooth = strict_cycloidal_tooth_points(z_gear, z_mate, module, samples)
        if not _is_closed_polygon(tooth.points):
            raise RuntimeError(f"Regression failed ({z_gear},{z_mate},m={module}): polygon not closed")
        if not np.all(np.isfinite(tooth.points)):
            raise RuntimeError(f"Regression failed ({z_gear},{z_mate},m={module}): non-finite points")
        if tooth.join_tangent_mismatch > mismatch_threshold:
            raise RuntimeError(
                f"Regression failed ({z_gear},{z_mate},m={module}): tangent mismatch "
                f"{tooth.join_tangent_mismatch:.3e} exceeds {mismatch_threshold:.3e}"
            )

        rr = _curve_radius(tooth.points)
        gear = GearSpec(z=z_gear, module=module)
        if float(np.min(rr)) < (gear.root_radius - radius_tol):
            raise RuntimeError(f"Regression failed ({z_gear},{z_mate},m={module}): below root radius tolerance")
        if float(np.max(rr)) > (gear.addendum_radius + radius_tol):
            raise RuntimeError(f"Regression failed ({z_gear},{z_mate},m={module}): above addendum radius tolerance")

        mesh = evaluate_mesh_sanity(z_gear=z_gear, z_mate=z_mate, module=module)
        if mesh.has_radial_interference_risk:
            raise RuntimeError(f"Regression failed ({z_gear},{z_mate},m={module}): radial interference risk")


def export_points_csv(points: np.ndarray, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="ascii") as f:
        w = csv.writer(f)
        w.writerow(["index", "x_mm", "y_mm"])
        for i, (x, y) in enumerate(points):
            w.writerow([i, f"{x:.8f}", f"{y:.8f}"])


def export_points_dxf_polyline(points: np.ndarray, out_path: Path, layer: str = "CYCLOIDAL") -> None:
    """Export closed polyline points to a minimal ASCII DXF (R12-style entities)."""
    if len(points) < 4:
        raise ValueError("points must contain at least 4 points")

    closed = points
    if float(np.linalg.norm(points[0] - points[-1])) > 1e-8:
        closed = np.vstack((points, points[:1]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="ascii", newline="\n") as f:
        # Minimal DXF structure with one POLYLINE and VERTEX entries.
        f.write("0\nSECTION\n2\nHEADER\n0\nENDSEC\n")
        f.write("0\nSECTION\n2\nTABLES\n0\nENDSEC\n")
        f.write("0\nSECTION\n2\nBLOCKS\n0\nENDSEC\n")
        f.write("0\nSECTION\n2\nENTITIES\n")

        f.write("0\nPOLYLINE\n")
        f.write(f"8\n{layer}\n")
        f.write("66\n1\n")
        f.write("70\n1\n")
        f.write("10\n0.0\n20\n0.0\n30\n0.0\n")

        for x, y in closed:
            f.write("0\nVERTEX\n")
            f.write(f"8\n{layer}\n")
            f.write(f"10\n{x:.8f}\n")
            f.write(f"20\n{y:.8f}\n")
            f.write("30\n0.0\n")

        f.write("0\nSEQEND\n")
        f.write(f"8\n{layer}\n")
        f.write("0\nENDSEC\n0\nEOF\n")


def plot_tooth(tooth: StrictCycloidalTooth, z_gear: int, z_mate: int, module: float) -> None:
    import matplotlib.pyplot as plt

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strict analytic cycloidal tooth/gear generator")
    parser.add_argument("--z-gear", type=int, default=25, help="Primary gear tooth count")
    parser.add_argument("--z-mate", type=int, default=10, help="Mating gear tooth count")
    parser.add_argument("--module", type=float, default=2.0, help="Metric module in mm")
    parser.add_argument("--samples", type=int, default=500, help="Point budget for one tooth")
    parser.add_argument(
        "--tooth-csv",
        type=Path,
        default=Path(__file__).with_name("strict_cycloidal_tooth_points.csv"),
        help="Output CSV path for one tooth polygon",
    )
    parser.add_argument(
        "--full-gear-csv",
        type=Path,
        default=Path(__file__).with_name("strict_cycloidal_gear_outline_points.csv"),
        help="Output CSV path for full gear outline polygon",
    )
    parser.add_argument(
        "--tooth-dxf",
        type=Path,
        default=Path(__file__).with_name("strict_cycloidal_tooth_points.dxf"),
        help="Output DXF path for one tooth polygon",
    )
    parser.add_argument(
        "--full-gear-dxf",
        type=Path,
        default=Path(__file__).with_name("strict_cycloidal_gear_outline_points.dxf"),
        help="Output DXF path for full gear outline polygon",
    )
    parser.add_argument(
        "--no-dxf",
        action="store_true",
        help="Skip DXF export",
    )
    parser.add_argument("--no-plot", action="store_true", help="Skip matplotlib visualization")
    parser.add_argument("--run-regression-checks", action="store_true", help="Run built-in geometry regression checks")
    parser.add_argument("--report-mesh-sanity", action="store_true", help="Print conservative pair-level mesh sanity metrics")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.run_regression_checks:
        run_regression_checks()
        print("Regression checks passed.")

    result = strict_cycloidal_tooth_points(
        z_gear=args.z_gear,
        z_mate=args.z_mate,
        module=args.module,
        n_samples=args.samples,
    )

    full_outline = build_full_gear_outline(result.points, z_gear=args.z_gear)

    export_points_csv(result.points, args.tooth_csv)
    export_points_csv(full_outline, args.full_gear_csv)
    if not args.no_dxf:
        export_points_dxf_polyline(result.points, args.tooth_dxf, layer="CYCL_TOOTH")
        export_points_dxf_polyline(full_outline, args.full_gear_dxf, layer="CYCL_GEAR")

    print(f"Saved tooth CSV: {args.tooth_csv}")
    print(f"Saved full-gear CSV: {args.full_gear_csv}")
    if not args.no_dxf:
        print(f"Saved tooth DXF: {args.tooth_dxf}")
        print(f"Saved full-gear DXF: {args.full_gear_dxf}")
    print(f"Pitch-join tangent mismatch norm: {result.join_tangent_mismatch:.6e}")

    if args.report_mesh_sanity:
        mesh = evaluate_mesh_sanity(z_gear=args.z_gear, z_mate=args.z_mate, module=args.module)
        print("Mesh sanity report (conservative):")
        print(f"  center distance: {mesh.center_distance:.6f} mm")
        print(f"  pitch-circle closure error: {mesh.pitch_circle_closure_error:.3e} mm")
        print(f"  primary tip -> mate root clearance: {mesh.primary_tip_to_mate_root_clearance:.6f} mm")
        print(f"  mate tip -> primary root clearance: {mesh.mate_tip_to_primary_root_clearance:.6f} mm")
        print(f"  estimated transverse contact ratio: {mesh.estimated_transverse_contact_ratio:.6f}")
        print(f"  radial interference risk: {mesh.has_radial_interference_risk}")

    if not args.no_plot:
        plot_tooth(result, z_gear=args.z_gear, z_mate=args.z_mate, module=args.module)
