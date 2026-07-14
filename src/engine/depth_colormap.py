from __future__ import annotations
import numpy as np


def depth_to_color(depth_m: float, max_depth_m: float) -> tuple[float, float, float]:
    if max_depth_m <= 0:
        return (0.30, 0.62, 1.00)

    t = max(0.0, min(1.0, depth_m / max_depth_m))

    stops = [
        (0.00, (1.00, 0.82, 0.25)),
        (0.30, (0.54, 0.89, 0.20)),
        (0.65, (0.30, 0.62, 1.00)),
        (1.00, (0.17, 0.10, 0.43)),
    ]

    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= t <= t1:
            alpha = (t - t0) / (t1 - t0)
            r = c0[0] + alpha * (c1[0] - c0[0])
            g = c0[1] + alpha * (c1[1] - c0[1])
            b = c0[2] + alpha * (c1[2] - c0[2])
            return (r, g, b)

    return stops[-1][1]


def depth_to_hex(depth_m: float, max_depth_m: float) -> str:
    r, g, b = depth_to_color(depth_m, max_depth_m)
    return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))


def build_depth_colormap() -> "np.ndarray":
    colors = []
    for i in range(256):
        t = i / 255.0
        colors.append(depth_to_color(t, 1.0))
    return np.array(colors, dtype=np.float32)
