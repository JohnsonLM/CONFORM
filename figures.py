import math
import os


def _format_tick(value, max_decimal_places=2):
    av = abs(value)
    # Always limit to max_decimal_places
    if av >= 1000:
        return f"{value:.0f}"
    if av >= 100:
        return f"{value:.1f}"
    if av >= 10:
        return f"{value:.2f}"
    # For small values, still limit to max_decimal_places
    fmt = f".{{0}}f".format(max_decimal_places)
    return format(value, fmt)


def _linspace(a, b, n):
    if n <= 1:
        return [a]
    return [a + (b - a) * (i / float(n - 1)) for i in range(n)]


def _regression_with_ci(xs, ys):
    n = len(xs)
    if n < 2:
        return None

    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    sxx = sum((x - x_mean) ** 2 for x in xs)
    if sxx <= 1e-12:
        return None

    sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean

    y_hat = [intercept + slope * x for x in xs]
    sse = sum((y - yh) ** 2 for y, yh in zip(ys, y_hat))
    if n > 2:
        sigma = math.sqrt(max(0.0, sse / (n - 2)))
    else:
        sigma = 0.0

    return {
        "slope": slope,
        "intercept": intercept,
        "x_mean": x_mean,
        "sxx": sxx,
        "sigma": sigma,
        "n": n,
    }


def _compute_pc1(scores):
    if not scores:
        return []
    features = [
        [s["lateral_area_cm2"], s["dorsal_area_cm2"],
            s["area3d_cm2"], s["volume_cm3"]]
        for s in scores
    ]
    rows = len(features)
    cols = len(features[0])

    means = [sum(features[r][c]
                 for r in range(rows)) / rows for c in range(cols)]
    stds = []
    for c in range(cols):
        var = sum((features[r][c] - means[c]) **
                  2 for r in range(rows)) / max(1, rows - 1)
        stds.append(math.sqrt(var) if var > 0.0 else 1.0)

    z = [[(features[r][c] - means[c]) / stds[c]
          for c in range(cols)] for r in range(rows)]

    cov = [[0.0 for _ in range(cols)] for _ in range(cols)]
    denom = max(1, rows - 1)
    for i in range(cols):
        for j in range(cols):
            cov[i][j] = sum(z[r][i] * z[r][j] for r in range(rows)) / denom

    vec = [1.0, 1.0, 1.0, 1.0]
    for _ in range(24):
        nxt = [sum(cov[i][j] * vec[j] for j in range(cols))
               for i in range(cols)]
        norm = math.sqrt(sum(v * v for v in nxt))
        if norm <= 1e-12:
            break
        vec = [v / norm for v in nxt]

    return [sum(z[r][c] * vec[c] for c in range(cols)) for r in range(rows)]


def _plot_bounds(values):
    v_min = min(values)
    v_max = max(values)
    if v_min == v_max:
        pad = 1.0 if v_min == 0.0 else abs(v_min) * 0.05
        return v_min - pad, v_max + pad

    span = v_max - v_min
    return v_min - (span * 0.08), v_max + (span * 0.08)


def _split_title(text, max_chars=34):
    if len(text) <= max_chars:
        return [text]

    parts = text.split()
    lines = []
    current = ""
    for part in parts:
        candidate = part if not current else f"{current} {part}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = part
    if current:
        lines.append(current)

    return lines[:2]


def _write_single_figure(filepath, title, x_label, y_label, xs, ys):
    if not xs or not ys or len(xs) != len(ys):
        return ""

    width = 900
    height = 900
    # Further increased padding for clarity and to avoid text overlap
    lpad = 200
    rpad = 100
    tpad = 170
    bpad = 200

    # Visual scale factors (make everything even bigger)
    axis_stroke = 4.0
    grid_stroke = 2.2
    tick_stroke = 2.2
    point_radius = 9.0
    point_stroke = 2.2
    trend_stroke = 6.0
    title_font = 38
    title_font2 = 32
    label_font = 34
    tick_font = 28

    ax_x0 = lpad
    ax_y0 = tpad
    ax_w = width - lpad - rpad
    ax_h = height - tpad - bpad

    x_min, x_max = _plot_bounds(xs)
    y_min, y_max = _plot_bounds(ys)

    def xp(v):
        # Clamp to plot area for blue line alignment
        x = ax_x0 + ((v - x_min) / (x_max - x_min)) * ax_w
        return min(max(x, ax_x0), ax_x0 + ax_w)

    def yp(v):
        y = ax_y0 + (1.0 - ((v - y_min) / (y_max - y_min))) * ax_h
        return min(max(y, ax_y0), ax_y0 + ax_h)

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
    )
    lines.append('<rect x="0" y="0" width="100%" height="100%" fill="white"/>')
    lines.append(
        f'<rect x="{ax_x0}" y="{ax_y0}" width="{ax_w}" height="{ax_h}" fill="#d9d9d9"/>'
    )

    # Axes.
    lines.append(
        f'<line x1="{ax_x0}" y1="{ax_y0 + ax_h}" x2="{ax_x0 + ax_w}" y2="{ax_y0 + ax_h}" stroke="#111" stroke-width="{axis_stroke}" vector-effect="non-scaling-stroke"/>'
    )
    lines.append(
        f'<line x1="{ax_x0}" y1="{ax_y0}" x2="{ax_x0}" y2="{ax_y0 + ax_h}" stroke="#111" stroke-width="{axis_stroke}" vector-effect="non-scaling-stroke"/>'
    )

    # Ticks and grid.
    y_ticks = 6 if "Body condition score" in y_label else 4
    for i in range(y_ticks + 1):
        t = i / float(y_ticks)
        v = y_min + (y_max - y_min) * t
        y = yp(v)
        lines.append(
            f'<line x1="{ax_x0 - 32}" y1="{y:.2f}" x2="{ax_x0}" y2="{y:.2f}" stroke="#111" stroke-width="{tick_stroke}"/>'
        )
        # Offset tick text further left and slightly down for clarity
        lines.append(
            f'<text x="{ax_x0 - 52}" y="{y + 18:.2f}" font-size="{tick_font}" font-weight="600" text-anchor="end" font-family="Helvetica, Arial, sans-serif" fill="#111">{_format_tick(v, 2)}</text>'
        )

    x_ticks = 4
    for i in range(x_ticks + 1):
        t = i / float(x_ticks)
        v = x_min + (x_max - x_min) * t
        x = xp(v)
        lines.append(
            f'<line x1="{x:.2f}" y1="{ax_y0 + ax_h}" x2="{x:.2f}" y2="{ax_y0 + ax_h + 32}" stroke="#111" stroke-width="{tick_stroke}"/>'
        )
        # Offset tick text further down for clarity
        lines.append(
            f'<text x="{x:.2f}" y="{ax_y0 + ax_h + 80}" font-size="{tick_font}" font-weight="600" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" fill="#111">{_format_tick(v, 2)}</text>'
        )

    # Show a trend line using measured values.
    reg = _regression_with_ci(xs, ys)
    if reg is not None:
        # Only draw the blue line within the plot area
        x_line = _linspace(x_min, x_max, 80)
        y_line = [reg["intercept"] + reg["slope"] * x for x in x_line]
        # Clip points to plot area
        clipped_pts = [
            (min(max(xp(x), ax_x0), ax_x0 + ax_w),
             min(max(yp(y), ax_y0), ax_y0 + ax_h))
            for x, y in zip(x_line, y_line)
        ]
        line_pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in clipped_pts)
        lines.append(
            f'<polyline points="{line_pts}" fill="none" stroke="#2f67ff" stroke-width="{trend_stroke}" vector-effect="non-scaling-stroke"/>'
        )

    for x, y in zip(xs, ys):
        lines.append(
            f'<circle cx="{xp(x):.2f}" cy="{yp(y):.2f}" r="{point_radius}" fill="#000" stroke="#fff" stroke-width="{point_stroke}" vector-effect="non-scaling-stroke"/>'
        )

    title_lines = _split_title(title, max_chars=30)
    if title_lines:
        if len(title_lines) == 1:
            lines.append(
                f'<text x="{width / 2:.2f}" y="{tpad // 2}" font-size="{title_font}" font-weight="700" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" fill="#111">{title_lines[0]}</text>'
            )
        else:
            lines.append(
                f'<text x="{width / 2:.2f}" y="{tpad // 2 - 12}" font-size="{title_font2}" font-weight="700" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" fill="#111">{title_lines[0]}</text>'
            )
            lines.append(
                f'<text x="{width / 2:.2f}" y="{tpad // 2 + 32}" font-size="{title_font2}" font-weight="700" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" fill="#111">{title_lines[1]}</text>'
            )
    lines.append(
        f'<text x="{ax_x0 + ax_w / 2:.2f}" y="{height - bpad // 2 + 20}" font-size="{label_font}" font-weight="700" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" fill="#111">{x_label}</text>'
    )
    lines.append(
        f'<text transform="translate({lpad // 2.5} {ax_y0 + ax_h / 2:.2f}) rotate(-90)" font-size="{label_font}" font-weight="700" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" fill="#111">{y_label}</text>'
    )
    lines.append("</svg>")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filepath


def _sequence_progress(samples):
    if not samples:
        return []

    if all("sequence_progress" in s for s in samples):
        return [s["sequence_progress"] for s in samples]

    if len(samples) == 1:
        return [0.0]

    return [i / float(len(samples) - 1) for i in range(len(samples))]


def _bcs_axis(samples):
    if not samples:
        return []
    if all("bcs" in s for s in samples):
        return [s["bcs"] for s in samples]
    return []


def _age_axis(samples):
    if not samples:
        return []
    if all("age_days" in s for s in samples):
        return [s["age_days"] for s in samples]
    return []


def export_figures(samples, output_dir, include_bbox):
    if not samples:
        return []

    figures_dir = os.path.join(output_dir, "figures")
    os.makedirs(figures_dir, exist_ok=True)

    bcs_values = _bcs_axis(samples)
    age_values = _age_axis(samples)
    use_bcs_axis = bool(bcs_values)
    use_age_axis = bool(age_values)

    lateral = [s["lateral_area_cm2"] for s in samples]
    dorsal = [s["dorsal_area_cm2"] for s in samples]
    surface = [s["area3d_cm2"] for s in samples]
    volume = [s["volume_cm3"] for s in samples]
    pc1 = _compute_pc1(samples)
    sum_ld = [l + d for l, d in zip(lateral, dorsal)]
    ratio_vs = [
        (v / a) if abs(a) > 1e-12 else 0.0
        for v, a in zip(volume, surface)
    ]

    metrics = [
        (
            "lateral_area",
            "Lateral Area",
            "2D Lateral Area (cm^2)",
            lateral,
        ),
        (
            "dorsal_area",
            "Dorsal Area",
            "2D Dorsal Area (cm^2)",
            dorsal,
        ),
        (
            "surface_area",
            "3D Surface Area",
            "3D Surface Area (cm^2)",
            surface,
        ),
        (
            "volume",
            "Volume",
            "Volume (cm^3)",
            volume,
        ),
        (
            "pc1",
            "Principal Component Axis 1",
            "PC1 score",
            pc1,
        ),
        (
            "lateral_plus_dorsal",
            "Lateral + Dorsal Area Sum",
            "Area sum (cm^2)",
            sum_ld,
        ),
        (
            "volume_surface_ratio",
            "Volume to Surface Area Ratio",
            "Volume / Surface Area (cm)",
            ratio_vs,
        ),
    ]

    if include_bbox and all(
        ("width_cm" in s and "height_cm" in s and "length_cm" in s)
        for s in samples
    ):
        metrics.extend([
            (
                "width",
                "Width",
                "Width (cm)",
                [s["width_cm"] for s in samples],
            ),
            (
                "height",
                "Height",
                "Height (cm)",
                [s["height_cm"] for s in samples],
            ),
            (
                "length",
                "Length",
                "Length (cm)",
                [s["length_cm"] for s in samples],
            ),
        ])

    figure_paths = []
    if use_bcs_axis:
        for slug, metric_title, metric_label, metric_values in metrics:
            path = _write_single_figure(
                os.path.join(figures_dir, f"bcs_vs_{slug}.svg"),
                metric_title,
                metric_label,
                "Body condition score",
                metric_values,
                bcs_values,
            )
            if path:
                figure_paths.append(path)
    elif use_age_axis:
        for slug, metric_title, metric_label, metric_values in metrics:
            path = _write_single_figure(
                os.path.join(figures_dir, f"age_vs_{slug}.svg"),
                metric_title,
                metric_label,
                "Age (days)",
                metric_values,
                age_values,
            )
            if path:
                figure_paths.append(path)
    else:
        x_values = _sequence_progress(samples)
        x_label = "Sequence progress (0 to 1)"
        for slug, metric_title, metric_label, metric_values in metrics:
            path = _write_single_figure(
                os.path.join(figures_dir, f"{slug}_vs_progress.svg"),
                metric_title,
                x_label,
                metric_label,
                x_values,
                metric_values,
            )
            if path:
                figure_paths.append(path)

    return figure_paths
