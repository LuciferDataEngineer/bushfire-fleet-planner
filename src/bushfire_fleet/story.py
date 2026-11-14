"""Stakeholder wording. Numbers in, plain sentences out."""

from __future__ import annotations


def people(n: float) -> str:
    value = int(round(n))
    if abs(value) >= 1_000_000:
        text = f"{value / 1_000_000:.1f}"
        if text.endswith(".0"):
            text = text[:-2]
        return f"{text} million"
    return f"{value:,}"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def signed_pp(value: float) -> str:
    return f"{value:+.1f}"


def build_copy(facts: dict) -> dict:
    opt = facts["optimal"]
    base = facts["baseline"]
    people_pp = opt["people_pct"] - base["people_pct"]
    heat_pp = opt["heat_pct"] - base["heat_pct"]
    top_state = facts["top_heat_state"]["short"]
    worst = facts["worst_region"]["name"]
    busiest = facts["busiest_heat_region"]["name"]
    uplift = facts["sim_uplift_pct"]
    ordinary_days = facts["sim_uniform"]
    hotter_days = facts["sim_hotter"]
    tight = facts["optimal_60"]["people_pct"]

    if abs(people_pp) < 1:
        shift_tone = "info"
    elif people_pp > 0:
        shift_tone = "good"
    else:
        shift_tone = "watch"

    risk_banner = (
        f"{people(facts['high_quarter_population'])} people live in the regions with the most dangerous fire weather. "
        f"{pct(facts['high_quarter_heat_share'])} of this week's satellite heat is in those same regions."
    )
    where_banner = (
        f"The darker regions are where fire weather has been dangerous most often since 2022. "
        f"{worst} is at the top of that list."
    )
    fleet_banner = (
        f"Put six aircraft at {_and(facts['recommended_labels'])}. "
        f"Within 90 minutes that reaches {pct(opt['people_pct'])} of people and {pct(opt['heat_pct'])} of this week's satellite heat. "
        f"The biggest-cities airports reach {pct(base['people_pct'])} of people and only {pct(base['heat_pct'])} of that heat."
    )
    week_banner = (
        f"The satellite feed runs from {facts['heat_day_start']} to {facts['heat_day_end']} "
        f"({facts['tz_label']}). {top_state} has the most of that heat."
    )

    return {
        "risk": {
            "banner": risk_banner,
            "kpis": [
                _kpi("People in the fiercest quarter", people(facts["high_quarter_population"]), "Regions with dangerous fire weather at least as often as the worst quarter of the country.", "high" if facts["high_quarter_pop_share"] >= 25 else "watch"),
                _kpi("This week's heat sitting there", pct(facts["high_quarter_heat_share"]), "Share of clearer satellite heat detections in that same quarter.", "high" if facts["high_quarter_heat_share"] >= 40 else "watch"),
                _kpi(
                    "Hotter-day season",
                    f"{hotter_days:.0f} vs {ordinary_days:.0f}",
                    "Severe fire-weather days in a 120-day season where people live, if hotter days from the record are drawn more often, against an ordinary draw.",
                    "high" if uplift >= 50 else "watch",
                ),
                _kpi("Busiest state this week", top_state, f"{pct(facts['top_heat_state']['share'])} of the satellite heat in this reading.", "watch"),
                _region_kpi(
                    "Worst fire-weather region",
                    worst,
                    f"{facts['worst_region']['severe_days']:.1f} dangerous days a year, on average, from 2022 to 2025.",
                    "high",
                ),
            ],
            "charts": [
                f"{worst} leads the country for how often fire weather turns dangerous",
                (
                    f"{facts['top_heat_state']['name']} holds most of this week's satellite heat"
                    if facts["top_heat_state"]["share"] >= 50
                    else f"{facts['top_heat_state']['name']} has the largest share of this week's satellite heat"
                ),
                f"People in {facts['fiercest_state']['name']} see dangerous fire weather more often than people in the other states",
            ],
            "meaning": (
                f"The people and the heat are not in the same places. "
                f"{people(facts['high_quarter_population'])} live where dangerous weather is most common, "
                f"and {pct(facts['high_quarter_heat_share'])} of the latest satellite heat falls there. "
                f"Where people live, a season that replays more of the hotter days on record has about {hotter_days:.0f} severe fire-weather days in 120 days, against about {ordinary_days:.0f} in an ordinary draw."
            ),
        },
        "where": {
            "banner": where_banner,
            "kpis": [
                _kpi("Regions on the map", str(facts["n_regions"]), "Regions across the states and the ACT. Offshore territories are left off.", "info"),
                _kpi("People in darker-than-average regions", people(facts["median_danger_population"]), f"{pct(facts['median_danger_pop_share'])} of the population lives where dangerous weather is above the national middle.", "watch"),
                _kpi("Heat in those regions", pct(facts["median_danger_heat_share"]), "Share of this week's satellite heat in the above-average half of the map.", "high" if facts["median_danger_heat_share"] >= 50 else "watch"),
                _kpi("Aircraft on the map", str(facts["n_aircraft"]), "Filled markers are the recommended bases. Hollow markers are the biggest-cities line-up where it differs.", "info"),
                _region_kpi(
                    "Highest planning priority",
                    facts["top_plan_region"]["name"],
                    "The region that counts most once people, dangerous weather and this week's heat are looked at together.",
                    "high",
                ),
            ],
            "charts": {
                "weather": "Regions with the most dangerous fire weather in a typical year",
                "people": "Where the people are",
                "heat": "Where this week's satellite heat is concentrated",
                "plan": "Regions that matter most for placing the aircraft",
            },
            "meaning": (
                "Use the filters to switch the shading between fire weather, people, this week's heat, and the mix used to place aircraft. "
                "A base is only useful if it sits within 90 minutes of the places that light up."
            ),
        },
        "fleet": {
            "banner": fleet_banner,
            "kpis": [
                _kpi("People within 90 minutes", pct(opt["people_pct"]), f"{people(opt['people'])} people, counting a whole region once its main point is in range.", "good" if opt["people_pct"] >= 70 else "watch"),
                _kpi("This week's heat in range", pct(opt["heat_pct"]), "Share of clearer satellite heat detections within 90 minutes of a recommended base.", "good" if opt["heat_pct"] >= 70 else "watch"),
                _kpi("Dangerous weather in range", pct(opt["weather_pct"]), "Share of dangerous-weather days, over 2022–2025, in regions a recommended base can reach.", "good" if opt["weather_pct"] >= 70 else "watch"),
                _kpi("People, recommended vs cities", f"{pct(opt['people_pct'])} vs {pct(base['people_pct'])}", "Share of people within 90 minutes.", "info" if abs(people_pp) < 1 else shift_tone),
                _kpi("Heat, recommended vs cities", f"{pct(opt['heat_pct'])} vs {pct(base['heat_pct'])}", "This week's satellite heat within 90 minutes.", "good" if heat_pp > 10 else "info"),
            ],
            "charts": [
                "Recommended bases against a biggest-cities line-up",
                "People for whom each recommended base is the closest cover",
            ],
            "meaning": (
                f"The recommended bases reach {pct(opt['people_pct'])} of people against {pct(base['people_pct'])} for the biggest cities, "
                f"{pct(opt['heat_pct'])} of this week's heat against {pct(base['heat_pct'])}, "
                f"and {pct(opt['weather_pct'])} of the dangerous-weather record against {pct(base['weather_pct'])}. "
                f"At 60 minutes those recommended bases reach only {pct(tight)} of people, "
                f"while the city airports still reach {pct(facts['baseline_60']['people_pct'])}. "
                "A 90-minute flight is what lets an inland aircraft still count a capital as covered."
            ),
        },
        "week": {
            "banner": week_banner,
            "kpis": [
                _kpi("Clearer heat detections", f"{facts['heat_events']:,}", "One count per patch of country per day, so the same fire is not counted once for every satellite pass.", "watch"),
                _kpi("Busiest state", top_state, f"{facts['top_heat_state']['heat']:,} of those detections.", "high"),
                _region_kpi(
                    "Busiest region",
                    busiest,
                    f"{facts['busiest_heat_region']['heat']:,} detections in {facts['busiest_heat_region']['state']}.",
                    "high",
                ),
                _kpi("Outlook window", f"{len(facts['forecast_days'])} days", f"{facts['forecast_days'][0]} to {facts['forecast_days'][-1]}, {facts['tz_label']}.", "info"),
                _kpi(
                    "States heading for severe weather",
                    str(facts["severe_forecast_states"]),
                    _forecast_detail(facts),
                    "high" if facts["severe_forecast_states"] else "good",
                ),
            ],
            "charts": [
                "How many heat detections fell on each day",
                "Regions with the most satellite heat in this feed",
                "The most dangerous spot in each state, day by day",
            ],
            "meaning": _week_meaning(facts),
        },
    }


def _forecast_detail(facts: dict) -> str:
    peak = facts["forecast_peak"]
    if facts["severe_forecast_states"] == 0:
        return f"The highest score in the outlook is {peak['score']:.0f} ({peak['band'].lower()}) in {peak['state']} on {peak['day']}."
    return f"At least one day reaches severe or worse. The peak is {peak['score']:.0f} ({peak['band'].lower()}) in {peak['state']} on {peak['day']}."


def _week_meaning(facts: dict) -> str:
    peak = facts["forecast_peak"]
    if facts["severe_forecast_states"] == 0:
        return (
            f"This reading does not show a state reaching severe fire weather in the coming week. "
            f"The hottest outlook number is {peak['score']:.0f} in {peak['state']} on {peak['day']}. "
            "The fleet decision still leans on where dangerous weather has returned year after year, not only on this week."
        )
    return (
        f"{facts['severe_forecast_states']} state"
        f"{'' if facts['severe_forecast_states'] == 1 else 's'} "
        f"{'is' if facts['severe_forecast_states'] == 1 else 'are'} forecast to reach severe fire weather. "
        f"The peak is {peak['score']:.0f} in {peak['state']} on {peak['day']}. "
        "Treat the dots as heat the satellites saw, not as confirmed fires on the ground."
    )


def _and(labels: list[str]) -> str:
    if len(labels) <= 1:
        return "".join(labels)
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def _kpi(label: str, value: str, detail: str, tone: str) -> dict:
    return {"label": label, "value": value, "detail": detail, "tone": tone}


# Official region names are "State - place". The state is shortened so the
# headline fits a KPI card; the full name stays in the card's sub-text.
_STATE_PREFIXES = (
    ("Western Australia - ", "WA "),
    ("Northern Territory - ", "NT "),
    ("South Australia - ", "SA "),
    ("New South Wales - ", "NSW "),
    ("Queensland - ", "Qld "),
    ("Victoria - ", "Vic "),
    ("Tasmania - ", "Tas "),
    ("Australian Capital Territory", "ACT"),
)


def _place(name: str) -> str:
    for prefix, short in _STATE_PREFIXES:
        if name.startswith(prefix):
            return (short + name[len(prefix):]).strip()
    return name


def _region_kpi(label: str, name: str, detail: str, tone: str) -> dict:
    shown = _place(name)
    if shown != name:
        detail = f"{name}. {detail}"
    return _kpi(label, shown, detail, tone)
