"""Static pages for the public site."""

from __future__ import annotations

import html
from pathlib import Path

from bushfire_fleet.charts import grouped_bars, horizontal_bars
from bushfire_fleet.ffdi import danger_band
from bushfire_fleet.mapsvg import render_map
from bushfire_fleet.story import build_copy, pct, people

RAMP = ["#1c3f38", "#3f7a52", "#e0b33a", "#ef7d32", "#ff4d3a"]
BAND_COLOR = {
    "Low": "#1d4e45",
    "High": "#8a6a2f",
    "Very high": "#c4842a",
    "Severe": "#e06a2c",
    "Extreme": "#ff4d3a",
    "Catastrophic": "#ff2a55",
}
NAV = [
    ("index.html", "The risk", "risk"),
    ("where.html", "Where", "where"),
    ("fleet.html", "Fleet plan", "fleet"),
    ("week.html", "This week", "week"),
]


def write_site(facts: dict, site: Path) -> None:
    site.mkdir(parents=True, exist_ok=True)
    (site / "data").mkdir(exist_ok=True)
    copy = build_copy(facts)
    when, tz = facts["when_label"], facts["tz_label"]
    (site / "index.html").write_text(_page("risk", "The risk", _risk_body(facts, copy), when, tz))
    (site / "where.html").write_text(_page("where", "Where", _where_body(facts, copy), when, tz))
    (site / "fleet.html").write_text(_page("fleet", "Fleet plan", _fleet_body(facts, copy), when, tz))
    (site / "week.html").write_text(_page("week", "This week", _week_body(facts, copy), when, tz))
    payload = {
        "generated_from": facts["when_label"],
        "cover_minutes": facts["cover_minutes"],
        "optimal_people_pct": facts["optimal"]["people_pct"],
        "baseline_people_pct": facts["baseline"]["people_pct"],
        "optimal_heat_pct": facts["optimal"]["heat_pct"],
        "optimal_weather_pct": facts["optimal"]["weather_pct"],
        "heat_events": facts["heat_events"],
        "sim_uplift_pct": facts["sim_uplift_pct"],
    }
    import json

    (site / "data" / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _risk_body(facts: dict, copy: dict) -> str:
    page = copy["risk"]
    severe = horizontal_bars(
        [(r["name"], r["severe_days"], f"{r['severe_days']:.1f} days") for r in facts["top_severe"]],
        "#ff7a32",
    )
    heat = horizontal_bars(
        [(r["name"], r["heat"], f"{r['heat']:,}") for r in facts["heat_by_state"]],
        "#ffb020",
    )
    states = horizontal_bars(
        [(r["name"], r["severe_days"], f"{r['severe_days']:.1f} days") for r in facts["severe_by_state"]],
        "#ff5d6c",
    )
    return "".join(
        [
            _banner(page["banner"]),
            _kpis(page["kpis"]),
            _chart(page["charts"][0], severe),
            _chart(page["charts"][1], heat),
            _chart(page["charts"][2], states),
            _meaning(page["meaning"]),
            _exact(_coverage_table(facts) + _region_table(facts["top_severe"], "Dangerous-weather days a year")),
        ]
    )


def _where_body(facts: dict, copy: dict) -> str:
    page = copy["where"]
    painted = _paint(facts["map_regions"])
    svg = render_map(painted, facts["map_bases"])
    panels = []
    for mode, rows, color, formatter in (
        ("weather", facts["top_severe"], "#ff7a32", lambda r: (r["name"], r["severe_days"], f"{r['severe_days']:.1f} days")),
        ("people", facts["top_people"], "#8ecbff", lambda r: (r["name"], r["population"], people(r["population"]))),
        ("heat", facts["top_heat"], "#ffb020", lambda r: (r["name"], r["heat"], f"{r['heat']:,}")),
        ("plan", facts["top_plan"], "#3ee0a2", lambda r: (r["name"], r["weight"] * 100, f"{r['weight'] * 100:.1f}")),
    ):
        hidden = "" if mode == "weather" else " hidden"
        chart = horizontal_bars([formatter(r) for r in rows], color)
        panels.append(
            f'<div class="chart-panel" data-chart-panel="{mode}"{hidden}>{_chart(page["charts"][mode], chart)}</div>'
        )
    legends = []
    captions = {
        "weather": ("Fewer dangerous days", "More dangerous days"),
        "people": ("Fewer people", "More people"),
        "heat": ("No heat this week", "Most heat this week"),
        "plan": ("Lower priority", "Higher priority"),
    }
    for mode, (left, right) in captions.items():
        hidden = "" if mode == "weather" else " hidden"
        swatches = "".join(f'<i style="background:{color}"></i>' for color in RAMP)
        legends.append(
            f'<div class="legend-panel" data-legend="{mode}"{hidden}><span>{left}</span><span class="ramp">{swatches}</span><span>{right}</span></div>'
        )
    pills = """
    <div class="pills" role="group" aria-label="Colour the map by">
      <button type="button" data-mode="weather" aria-pressed="true">Fire weather</button>
      <button type="button" data-mode="people" aria-pressed="false">People</button>
      <button type="button" data-mode="heat" aria-pressed="false">Heat this week</button>
      <button type="button" data-mode="plan" aria-pressed="false">Planning mix</button>
    </div>
    """
    return "".join(
        [
            _banner(page["banner"]),
            _kpis(page["kpis"]),
            '<section class="chart-card map-card"><h2>Where the risk sits, and where the aircraft would wait</h2>',
            pills,
            '<div class="map-frame" data-map-frame>',
            svg,
            "</div>",
            "".join(legends),
            '<p class="note">Filled markers are recommended bases. Hollow rings are biggest-city bases that the recommendation does not use. A gold ring means the base is in both lists.</p>',
            "</section>",
            "".join(panels),
            _meaning(page["meaning"]),
            _exact(_region_table(facts["top_plan"], "Share of the planning mix")),
        ]
    )


def _fleet_body(facts: dict, copy: dict) -> str:
    page = copy["fleet"]
    opt, base = facts["optimal"], facts["baseline"]
    grouped = grouped_bars(
        [
            ("People", opt["people_pct"], pct(opt["people_pct"]), base["people_pct"], pct(base["people_pct"])),
            ("This week's heat", opt["heat_pct"], pct(opt["heat_pct"]), base["heat_pct"], pct(base["heat_pct"])),
            ("Dangerous weather", opt["weather_pct"], pct(opt["weather_pct"]), base["weather_pct"], pct(base["weather_pct"])),
        ]
    )
    bases = horizontal_bars(
        [(b["label"], b["people"], people(b["people"])) for b in facts["base_loads"]],
        "#3ee0a2",
    )
    names = ", ".join(b["label"] for b in facts["base_loads"])
    intro = f'<p class="lede">Recommended bases: {html.escape(names)}.</p>'
    return "".join(
        [
            _banner(page["banner"]),
            _kpis(page["kpis"]),
            intro,
            _chart(page["charts"][0], grouped),
            _chart(page["charts"][1], bases),
            _meaning(page["meaning"]),
            _exact(_coverage_table(facts) + _base_table(facts) + _assumption_table(facts)),
        ]
    )


def _week_body(facts: dict, copy: dict) -> str:
    page = copy["week"]
    by_day = horizontal_bars(
        [(r["label"], r["count"], f"{r['count']:,}") for r in facts["heat_by_day"]],
        "#ffb020",
    )
    top = horizontal_bars(
        [(r["name"], r["heat"], f"{r['heat']:,}") for r in facts["top_heat"]],
        "#ff7a32",
    )
    return "".join(
        [
            _banner(page["banner"]),
            _kpis(page["kpis"]),
            _chart(page["charts"][2], _heatmap(facts)),
            _chart(page["charts"][0], by_day),
            _chart(page["charts"][1], top),
            _meaning(page["meaning"]),
            _exact(_forecast_table(facts)),
        ]
    )


def _heatmap(facts: dict) -> str:
    days = facts["forecast_days"]
    head = "<tr><th>State</th>" + "".join(f"<th>{html.escape(day)}</th>" for day in days) + "</tr>"
    body = []
    for state in facts["forecast_states"]:
        cells = []
        for score in state["scores"]:
            band = danger_band(score)
            color = BAND_COLOR[band]
            cells.append(
                f'<td style="background:{color}" title="{html.escape(band)}">{score:.0f}</td>'
            )
        body.append(f'<tr><th>{html.escape(state["short"])}</th>{"".join(cells)}</tr>')
    legend = " ".join(
        f'<span class="heat-key"><i style="background:{color}"></i>{html.escape(name)}</span>'
        for name, color in BAND_COLOR.items()
    )
    return (
        '<div class="heat-wrap"><table class="heat">'
        + head
        + "".join(body)
        + "</table></div><div class=\"heat-legend\">"
        + legend
        + '</div><p class="note">Each number is the danger score in the most exposed part of that state. '
        "Higher means hotter, drier and windier, after recent rain is taken into account.</p>"
    )


def _paint(regions: list[dict]) -> list[dict]:
    modes = {
        "weather": [r["severe_days"] for r in regions],
        "people": [r["population"] for r in regions],
        "heat": [r["heat"] for r in regions],
        "plan": [r["weight"] for r in regions],
    }
    colors = {mode: _colors(values) for mode, values in modes.items()}
    painted = []
    for i, region in enumerate(regions):
        item = dict(region)
        item["fills"] = {mode: colors[mode][i] for mode in modes}
        painted.append(item)
    return painted


def _colors(values: list[float]) -> list[str]:
    if not values:
        return []
    positive = [value for value in values if value > 0]
    if positive and len(positive) < len(values) * 0.75:
        cuts = _cuts(positive, 4)
        out = []
        for value in values:
            if value <= 0:
                out.append(RAMP[0])
            else:
                out.append(RAMP[1 + _bin(value, cuts)])
        return out
    cuts = _cuts(values, 5)
    return [RAMP[_bin(value, cuts)] for value in values]


def _cuts(values: list[float], bins: int) -> list[float]:
    ordered = sorted(values)
    cuts = []
    for i in range(1, bins):
        index = min(len(ordered) - 1, int(round(i * len(ordered) / bins)) - 1)
        cuts.append(ordered[max(index, 0)])
    return cuts


def _bin(value: float, cuts: list[float]) -> int:
    for i, cut in enumerate(cuts):
        if value <= cut:
            return i
    return len(cuts)


def _page(active: str, title: str, body: str, when: str, tz: str) -> str:
    links = []
    for href, label, key in NAV:
        cls = " active" if key == active else ""
        links.append(f'<a class="{cls.strip()}" href="{href}">{label}</a>' if cls else f'<a href="{href}">{label}</a>')
        if cls:
            links[-1] = f'<a class="active" href="{href}">{label}</a>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)} · Bushfire fleet planner</title>
<link rel="stylesheet" href="assets/style.css"/>
</head>
<body>
<header class="topbar">
  <div class="topbar-inner">
    <div class="brand">Bushfire fleet planner</div>
    <nav class="tabs">{''.join(links)}</nav>
  </div>
</header>
<main class="wrap">
{body}
{_footer(when, tz)}
</main>
<script src="assets/app.js"></script>
</body>
</html>
"""


def _banner(text: str) -> str:
    return f'<section class="banner"><h1>{html.escape(text)}</h1></section>'


def _kpis(items: list[dict]) -> str:
    cards = []
    for item in items:
        cards.append(
            "<article class=\"kpi\" style=\"--tone:{tone}\"><div class=\"value\">{value}</div>"
            "<div class=\"label\">{label}</div><p class=\"detail\">{detail}</p></article>".format(
                tone=_tone(item["tone"]),
                value=html.escape(item["value"]),
                label=html.escape(item["label"]),
                detail=html.escape(item["detail"]),
            )
        )
    return f'<section class="kpis">{"".join(cards)}</section>'


def _tone(name: str) -> str:
    return {"high": "#ff5d3a", "watch": "#ffb020", "good": "#3ee0a2", "info": "#8ecbff"}[name]


def _chart(title: str, body: str) -> str:
    return f'<section class="chart-card"><h2>{html.escape(title)}</h2>{body}</section>'


def _meaning(text: str) -> str:
    return f'<section class="meaning"><h2>What this means</h2><p>{html.escape(text)}</p></section>'


def _exact(inner: str) -> str:
    return f'<details class="exact"><summary>Exact values</summary>{inner}</details>'


def _coverage_table(facts: dict) -> str:
    rows = []
    for minutes, opt, base in (
        (90, facts["optimal"], facts["baseline"]),
        (60, facts["optimal_60"], facts["baseline_60"]),
    ):
        rows.append(
            f"<tr><td>{minutes} minutes</td><td>{pct(opt['people_pct'])}</td><td>{pct(base['people_pct'])}</td>"
            f"<td>{pct(opt['heat_pct'])}</td><td>{pct(base['heat_pct'])}</td>"
            f"<td>{pct(opt['weather_pct'])}</td><td>{pct(base['weather_pct'])}</td></tr>"
        )
    return (
        "<h3>Share of the country within flying time</h3>"
        "<table><thead><tr><th>Window</th><th>People, recommended</th><th>People, biggest cities</th>"
        "<th>Heat, recommended</th><th>Heat, biggest cities</th>"
        "<th>Dangerous weather, recommended</th><th>Dangerous weather, biggest cities</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _region_table(rows: list[dict], value_name: str) -> str:
    body = []
    for row in rows:
        body.append(
            "<tr><td>{name}</td><td>{state}</td><td>{population}</td><td>{heat}</td><td>{metric}</td></tr>".format(
                name=html.escape(row["name"]),
                state=html.escape(row.get("state", "")),
                population=f"{int(row.get('population', 0)):,}",
                heat=f"{int(row.get('heat', 0)):,}",
                metric=html.escape(str(row.get("metric", ""))),
            )
        )
    return (
        f"<h3>{html.escape(value_name)}</h3><table><thead><tr><th>Region</th><th>State</th>"
        f"<th>People</th><th>Heat detections</th><th>{html.escape(value_name)}</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _base_table(facts: dict) -> str:
    body = []
    for base in facts["base_detail"]:
        body.append(
            "<tr><td>{label}</td><td>{name}</td><td>{people}</td><td>{heat}</td><td>{role}</td></tr>".format(
                label=html.escape(base["label"]),
                name=html.escape(base["name"]),
                people=people(base["people"]),
                heat=f"{base['heat']:,}",
                role=html.escape(base["role"]),
            )
        )
    return (
        "<h3>Bases</h3><table><thead><tr><th>Place</th><th>Airport</th><th>People it is closest for</th>"
        f"<th>Heat it is closest for</th><th>Role</th></tr></thead><tbody>{''.join(body)}</tbody></table>"
    )


def _assumption_table(facts: dict) -> str:
    rows = "".join(f"<tr><td>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>" for k, v in facts["assumption_rows"])
    return f"<h3>Planning assumptions</h3><table><tbody>{rows}</tbody></table>"


def _forecast_table(facts: dict) -> str:
    head = "<tr><th>State</th>" + "".join(f"<th>{html.escape(d)}</th>" for d in facts["forecast_days"]) + "</tr>"
    body = []
    for state in facts["forecast_states"]:
        cells = "".join(f"<td>{score:.1f}</td>" for score in state["scores"])
        body.append(f"<tr><th>{html.escape(state['name'])}</th>{cells}</tr>")
    return f"<h3>Danger score by state and day</h3><table><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"


def _footer(when: str, tz: str) -> str:
    clock = html.escape(when)
    zone = "Australian Eastern Daylight Time (AEDT, UTC+11)" if tz == "AEDT" else "Australian Eastern Standard Time (AEST, UTC+10)"
    return f"""
<footer class="sources">
  <p class="clock">As at {clock}. Times are {html.escape(zone)}.</p>
  <p>Not a dispatch plan. Satellite heat is not a confirmed bushfire. Aircraft speed, the 15 minutes allowed to get airborne, and the 90-minute window are planning assumptions.</p>
  <ul>
    <li>Satellite heat: Digital Earth Australia Hotspots, Geoscience Australia, CC BY 4.0. Recent public feed only.</li>
    <li>Weather and the week ahead: Open-Meteo, CC BY 4.0.</li>
    <li>Population at 30 June 2025 and region boundaries: Australian Bureau of Statistics, CC BY 4.0. Population figures for 2025 are preliminary.</li>
    <li>Airports and runways: OurAirports, public domain.</li>
  </ul>
</footer>
"""
