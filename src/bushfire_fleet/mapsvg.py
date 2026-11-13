"""Australia map in a local Albers projection. No tile server."""

from __future__ import annotations

import html
import math

from shapely.geometry import shape


def render_map(regions: list[dict], bases: list[dict], width: int = 920, height: int = 760) -> str:
    project = _albers()
    projected = []
    for region in regions:
        geom = shape(region["geometry"])
        projected.append((region, geom, _project_geom(geom, project)))
    xs = [x for _r, _g, pts in projected for x, _y in pts]
    ys = [y for _r, _g, pts in projected for _x, y in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad_x = (max_x - min_x) * 0.04
    pad_y = (max_y - min_y) * 0.06
    min_x -= pad_x
    max_x += pad_x + (max_x - min_x) * 0.12
    min_y -= pad_y
    max_y += pad_y
    span_x = max_x - min_x
    span_y = max_y - min_y
    scale = min(width / span_x, height / span_y)

    def px(x: float, y: float) -> tuple[float, float]:
        return (x - min_x) * scale, (max_y - y) * scale

    used_h = span_y * scale
    parts = [
        f'<svg id="aus-map" viewBox="0 0 {width:.0f} {used_h:.0f}" role="img" xmlns="http://www.w3.org/2000/svg">',
        "<title>Australia shaded by fire weather, with recommended aircraft bases</title>",
    ]
    for region, geom, _pts in projected:
        d = _path(geom, project, px)
        title = html.escape(
            f"{region['name']}: {region['severe_days']:.1f} dangerous days a year, "
            f"{int(region['population']):,} people"
        )
        fills = " ".join(
            f'data-fill-{mode}="{html.escape(region["fills"][mode])}"' for mode in region["fills"]
        )
        parts.append(
            f'<path class="region" data-sa4="{html.escape(region["code"])}" {fills} '
            f'fill="{html.escape(region["fills"]["weather"])}" d="{d}">'
            f"<title>{title}</title></path>"
        )
    labels = []
    for base in bases:
        x, y = px(*project(base["lon"], base["lat"]))
        kind = base["kind"]
        if kind == "baseline":
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" fill="none" stroke="#ffb020" stroke-width="2"/>'
            )
            continue
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6.5" fill="#07110e" stroke="#7ef0ff" stroke-width="2.5"/>'
        )
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.4" fill="#7ef0ff"/>')
        if kind == "both":
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="none" stroke="#ffb020" stroke-width="1.5"/>'
            )
        labels.append((x, y, base["label"]))
    _draw_labels(parts, labels, width, used_h)
    parts.append("</svg>")
    return "".join(parts)


def _draw_labels(parts: list[str], labels: list[tuple[float, float, str]], width: float, height: float) -> None:
    boxes: list[tuple[float, float, float, float]] = []
    for x, y, text in sorted(labels, key=lambda item: (item[1], item[0])):
        w = 6.6 * len(text) + 6
        h = 14
        options = [(x + 12, y - 4), (x + 12, y + 16), (x - w - 8, y - 4), (x + 12, y - 20), (x - w - 8, y + 16)]
        chosen = options[0]
        for cx, cy in options:
            box = (cx, cy - 11, w, h)
            inside = 2 <= cx and cx + w <= width - 2 and 14 <= cy <= height - 2
            if inside and not any(_hits(box, other) for other in boxes):
                chosen = (cx, cy)
                break
        boxes.append((chosen[0], chosen[1] - 11, w, h))
        parts.append(
            f'<text x="{chosen[0]:.1f}" y="{chosen[1]:.1f}" fill="#f7fbff" font-size="13" '
            f'font-family="Segoe UI, Helvetica, Arial, sans-serif">{html.escape(text)}</text>'
        )


def _hits(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[0] + a[2] < b[0] or b[0] + b[2] < a[0] or a[1] + a[3] < b[1] or b[1] + b[3] < a[1])


def _path(geom, project, px) -> str:
    polygons = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    chunks = []
    for poly in polygons:
        chunks.append(_ring(poly.exterior.coords, project, px))
        for hole in poly.interiors:
            chunks.append(_ring(hole.coords, project, px))
    return " ".join(chunks)


def _ring(coords, project, px) -> str:
    bits = []
    for i, (lon, lat) in enumerate(coords):
        x, y = px(*project(lon, lat))
        bits.append(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}")
    bits.append("Z")
    return " ".join(bits)


def _project_geom(geom, project) -> list[tuple[float, float]]:
    polygons = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    pts = []
    for poly in polygons:
        pts.extend(project(lon, lat) for lon, lat in poly.exterior.coords)
    return pts


def _albers():
    phi1 = math.radians(-18.0)
    phi2 = math.radians(-36.0)
    phi0 = 0.0
    lam0 = math.radians(132.0)
    n = 0.5 * (math.sin(phi1) + math.sin(phi2))
    c = math.cos(phi1) ** 2 + 2 * n * math.sin(phi1)
    rho0 = math.sqrt(c - 2 * n * math.sin(phi0)) / n

    def project(lon: float, lat: float) -> tuple[float, float]:
        rho = math.sqrt(max(c - 2 * n * math.sin(math.radians(lat)), 0.0)) / n
        theta = n * (math.radians(lon) - lam0)
        return rho * math.sin(theta), rho0 - rho * math.cos(theta)

    return project
