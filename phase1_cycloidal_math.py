"""
Phase 1 - standalone cycloidal tooth math module.

This module builds a single cycloidal-style tooth polyline and plots it.
It includes a C1 continuity check at the epicycloid -> hypocycloid join
near the pitch circle.

Notes:
- Units are in millimeters.
- The profile uses classic epi/hypocycloid primitives with a local Hermite
  transition at the pitch join to remove the cusp and enforce C1 continuity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np


@dataclass(frozen=True)
class CycloidalProfile:
    points: np.ndarray
    flank_left: np.ndarray
    flank_right: np.ndarray
    join_point: np.ndarray
    join_tangent: np.ndarray
    c1_error: float


def _epicycloid(R: float, r: float, t: np.ndarray) -> np.ndarray:
    x = (R + r) * np.cos(t) - r * np.cos(((R + r) / r) * t)
    y = (R + r) * np.sin(t) - r * np.sin(((R + r) / r) * t)
    return np.column_stack((x, y))


def _hypocycloid(R: float, r: float, t: np.ndarray) -> np.ndarray:
    x = (R - r) * np.cos(t) + r * np.cos(((R - r) / r) * t)
    y = (R - r) * np.sin(t) - r * np.sin(((R - r) / r) * t)
    return np.column_stack((x, y))


def _numeric_tangent(points: np.ndarray) -> np.ndarray:
    d = points[1] - points[0]
    n = np.linalg.norm(d)
    if n < 1e-12:
        return np.array([1.0, 0.0])
    return d / n


def _hermite_bridge(
    p0: np.ndarray,
    p1: np.ndarray,
    t0: np.ndarray,
    t1: np.ndarray,
    n: int,
    tension: float,
) -> np.ndarray:
    # Cubic Hermite interpolation to enforce C1 continuity at the join region.
    s = np.linspace(0.0, 1.0, n)
    h00 = 2.0 * s**3 - 3.0 * s**2 + 1.0
    h10 = s**3 - 2.0 * s**2 + s
    h01 = -2.0 * s**3 + 3.0 * s**2
    h11 = s**3 - s**2

    m0 = tension * t0
    m1 = tension * t1

    out = (
        h00[:, None] * p0
        + h10[:, None] * m0
        + h01[:, None] * p1
        + h11[:, None] * m1
    )
    return out


def cycloidal_tooth_points(
    N: int,
    module: float,
    r_ratio: float,
    n_samples: int,
) -> np.ndarray:
    """
    Return an (x, y) point array for one tooth.

    Parameters:
    - N: number of teeth
    - module: metric module in mm
    - r_ratio: pitch_radius / rolling_radius
    - n_samples: total points for one tooth polyline
    """
    if N < 4:
        raise ValueError("N must be >= 4")
    if module <= 0.0:
        raise ValueError("module must be > 0")
    if r_ratio <= 1.2:
        raise ValueError("r_ratio should be > 1.2 for stable geometry")
    if n_samples < 80:
        raise ValueError("n_samples should be >= 80")

    R = 0.5 * module * N
    r = R / r_ratio

    # Half-tooth angular span around the centerline (pitch thickness ~= pi/(2N)).
    half_tooth_angle = math.pi / (2.0 * N)

    flank_pts = max(20, n_samples // 4)
    bridge_pts = max(12, n_samples // 8)

    # Build each primitive around t=0 then rotate to target half-tooth side.
    t_h = np.linspace(-half_tooth_angle, 0.0, flank_pts)
    t_e = np.linspace(0.0, half_tooth_angle, flank_pts)

    hypo = _hypocycloid(R, r, t_h)
    epi = _epicycloid(R, r, t_e)

    # Remove cusp neighborhood and replace with C1 Hermite bridge.
    trim = max(3, flank_pts // 5)
    hypo_keep = hypo[:-trim]
    epi_keep = epi[trim:]

    p0 = hypo[-trim]
    p1 = epi[trim]

    t0 = _numeric_tangent(hypo[-trim : -trim + 2])
    t1 = _numeric_tangent(epi[trim : trim + 2])

    chord = np.linalg.norm(p1 - p0)
    bridge = _hermite_bridge(p0, p1, t0, t1, bridge_pts, tension=0.6 * chord)

    half_flank = np.vstack((hypo_keep, bridge, epi_keep))

    # Rotate so the pitch join aligns near +X axis and tooth sits symmetric on X.
    theta = -half_tooth_angle
    c = math.cos(theta)
    s = math.sin(theta)
    rot = np.array([[c, -s], [s, c]])
    left_flank = half_flank @ rot.T

    # Mirror across X axis for opposite flank.
    right_flank = left_flank.copy()
    right_flank[:, 1] *= -1.0
    right_flank = right_flank[::-1]

    tooth = np.vstack((left_flank, right_flank[1:]))
    return tooth


def build_profile(
    N: int = 25,
    module: float = 2.0,
    r_ratio: float = 7.5,
    n_samples: int = 300,
) -> CycloidalProfile:
    pts = cycloidal_tooth_points(N, module, r_ratio, n_samples)

    mid = len(pts) // 2
    left = pts[: mid + 1]
    right = pts[mid:]

    # Rebuild the same transition bookkeeping used in cycloidal_tooth_points,
    # then evaluate C1 specifically at the two bridge interfaces.
    R = 0.5 * module * N
    r = R / r_ratio
    half_tooth_angle = math.pi / (2.0 * N)
    flank_pts = max(20, n_samples // 4)
    trim = max(3, flank_pts // 5)

    t_h = np.linspace(-half_tooth_angle, 0.0, flank_pts)
    t_e = np.linspace(0.0, half_tooth_angle, flank_pts)
    hypo = _hypocycloid(R, r, t_h)
    epi = _epicycloid(R, r, t_e)

    p0 = hypo[-trim]
    p1 = epi[trim]
    t_h_end = _numeric_tangent(hypo[-trim : -trim + 2])
    t_e_beg = _numeric_tangent(epi[trim : trim + 2])
    chord = np.linalg.norm(p1 - p0)
    bridge = _hermite_bridge(p0, p1, t_h_end, t_e_beg, n=max(12, n_samples // 8), tension=0.6 * chord)
    t_beg = _numeric_tangent(bridge[:2])
    t_b_end = _numeric_tangent(bridge[-2:])

    c1_in = float(np.linalg.norm(t_h_end - t_beg))
    c1_out = float(np.linalg.norm(t_b_end - t_e_beg))
    c1_error = max(c1_in, c1_out)

    join = 0.5 * (hypo[-trim] + epi[trim])
    tan = 0.5 * (t_h_end + t_e_beg)

    return CycloidalProfile(
        points=pts,
        flank_left=left,
        flank_right=right,
        join_point=join,
        join_tangent=tan,
        c1_error=c1_error,
    )


def plot_profile(profile: CycloidalProfile, N: int, module: float) -> None:
    R = 0.5 * module * N

    fig, ax = plt.subplots(figsize=(8, 8))
    ax.plot(profile.points[:, 0], profile.points[:, 1], lw=2.0, label="One tooth")

    pitch = plt.Circle((0.0, 0.0), R, fill=False, linestyle="--", alpha=0.6, label="Pitch circle")
    ax.add_patch(pitch)

    jp = profile.join_point
    jt = profile.join_tangent
    ax.scatter([jp[0]], [jp[1]], s=40, label="Join")
    ax.arrow(jp[0], jp[1], 2.0 * jt[0], 2.0 * jt[1], width=0.04, length_includes_head=True)

    ax.set_aspect("equal", "box")
    ax.grid(True, alpha=0.25)
    ax.set_title(f"Cycloidal Tooth (N={N}, m={module}) | C1 error={profile.c1_error:.3e}")
    ax.legend()
    plt.show()


if __name__ == "__main__":
    N = 25
    MODULE = 2.0
    R_RATIO = 7.5
    SAMPLES = 320

    profile_data = build_profile(N=N, module=MODULE, r_ratio=R_RATIO, n_samples=SAMPLES)
    print(f"C1 tangent mismatch norm: {profile_data.c1_error:.6e}")
    plot_profile(profile_data, N=N, module=MODULE)
