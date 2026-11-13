"""SVG charts with reserved space so labels cannot collide with bars."""

from __future__ import annotations

import html


def horizontal_bars(
    rows: list[tuple[str, float, str]],
    color: str = "#ff8a3d",
    width: int = 760,
) -> str:
    """rows are (label, bar value, value text). Labels may be two lines."""
    prepared = [( _wrap(label), value, text) for label, value, text in rows]
    row_heights = [46 if len(lines) > 1 else 34 for lines, _v, _t in prepared]
    height = 12 + sum(row_heights) + 8
    peak = max((value for _l, value, _t in prepared), default=1.0) or 1.0
    label_w = 228
    value_w = 118
    bar_x = label_w + 12
    bar_max = width - bar_x - value_w
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" xmlns="http://www.w3.org/2000/svg">',
        f'<title>{html.escape(prepared[0][2] if prepared else "chart")}</title>',
    ]
    y = 10
    for (lines, value, text), row_h in zip(prepared, row_heights, strict=True):
        bar_w = 0 if peak == 0 else bar_max * max(value, 0) / peak
        bar_y = y + (row_h - 16) / 2
        parts.append(
            f'<rect x="{bar_x:.1f}" y="{bar_y:.1f}" width="{bar_w:.1f}" height="16" rx="3" fill="{color}"/>'
        )
        text_y = y + 14 if len(lines) == 1 else y + 12
        label = lines[0] if len(lines) == 1 else lines[0]
        parts.append(
            f'<text x="0" y="{text_y:.1f}" fill="#d5e6dc" font-size="13" font-family="Segoe UI, Helvetica, Arial, sans-serif">{html.escape(label)}</text>'
        )
        if len(lines) > 1:
            parts.append(
                f'<text x="0" y="{text_y + 16:.1f}" fill="#d5e6dc" font-size="13" font-family="Segoe UI, Helvetica, Arial, sans-serif">{html.escape(lines[1])}</text>'
            )
        parts.append(
            f'<text x="{bar_x + bar_w + 8:.1f}" y="{bar_y + 13:.1f}" fill="#f4f7f5" font-size="13" font-family="Segoe UI, Helvetica, Arial, sans-serif">{html.escape(text)}</text>'
        )
        y += row_h
    parts.append("</svg>")
    return "".join(parts)


def grouped_bars(
    rows: list[tuple[str, float, str, float, str]],
    legend: tuple[str, str] = ("Recommended", "Biggest cities"),
    colors: tuple[str, str] = ("#3ee0a2", "#ffb020"),
    width: int = 760,
) -> str:
    """rows are (label, value_a, text_a, value_b, text_b). Values are on a 0–100 scale."""
    row_h = 54
    legend_h = 28
    height = 12 + row_h * len(rows) + legend_h
    label_w = 168
    value_w = 150
    bar_x = label_w + 8
    bar_max = width - bar_x - value_w
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" xmlns="http://www.w3.org/2000/svg">',
    ]
    y = 8
    for label, a, a_text, b, b_text in rows:
        parts.append(
            f'<text x="0" y="{y + 24:.1f}" fill="#d5e6dc" font-size="13" font-family="Segoe UI, Helvetica, Arial, sans-serif">{html.escape(label)}</text>'
        )
        for offset, value, text, color in (
            (0, a, a_text, colors[0]),
            (18, b, b_text, colors[1]),
        ):
            bar_w = bar_max * max(min(value, 100), 0) / 100
            parts.append(
                f'<rect x="{bar_x:.1f}" y="{y + offset:.1f}" width="{bar_w:.1f}" height="14" rx="3" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{bar_x + bar_w + 8:.1f}" y="{y + offset + 12:.1f}" fill="#f4f7f5" font-size="12" font-family="Segoe UI, Helvetica, Arial, sans-serif">{html.escape(text)}</text>'
            )
        y += row_h
    lx = 8
    for name, color in zip(legend, colors, strict=True):
        parts.append(f'<rect x="{lx}" y="{height - 18}" width="12" height="12" rx="2" fill="{color}"/>')
        parts.append(
            f'<text x="{lx + 18}" y="{height - 8}" fill="#d5e6dc" font-size="12" font-family="Segoe UI, Helvetica, Arial, sans-serif">{html.escape(name)}</text>'
        )
        lx += 18 + 8 * len(name) + 28
    parts.append("</svg>")
    return "".join(parts)


def _wrap(text: str, limit: int = 30) -> list[str]:
    if len(text) <= limit:
        return [text]
    cut = text.rfind(" ", 0, limit)
    if cut < 8:
        cut = limit
    second = text[cut:].strip()
    if len(second) > limit:
        second = second[: limit - 1].rstrip() + "…"
    return [text[:cut].strip(), second]
