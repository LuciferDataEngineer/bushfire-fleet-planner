#!/usr/bin/env python3
"""Download public inputs and write data/snapshot.

CI does not run this. It rebuilds the study from the committed snapshot.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import ijson
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from bushfire_fleet.assumptions import BBOX, CONFIDENCE_MIN  # noqa: E402
from bushfire_fleet.bases import (  # noqa: E402
    in_study,
    is_candidate,
    longest_paved_runway_m,
)

SNAPSHOT = ROOT / "data" / "snapshot"
RAW = ROOT / "data" / "raw"
SYD = ZoneInfo("Australia/Sydney")
UA = "bushfire-fleet-planner/1.0 (educational portfolio; github.com/LuciferDataEngineer)"

SA4_URL = (
    "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/SA4/MapServer/1/query"
    "?where=1%3D1&outFields=sa4_code_2021,sa4_name_2021,gccsa_code_2021,gccsa_name_2021,"
    "state_code_2021,state_name_2021,area_albers_sqkm"
    "&returnGeometry=true&outSR=4326&f=geojson&geometryPrecision=4&maxAllowableOffset=0.02"
)
SA4_PT_URL = (
    "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/SA4/MapServer/2/query"
    "?where=1%3D1&outFields=sa4_code_2021,sa4_name_2021,state_name_2021"
    "&returnGeometry=true&outSR=4326&f=geojson"
)
ERP_URL = (
    "https://www.abs.gov.au/statistics/people/population/regional-population/"
    "2024-25/32180DS0003_2001-25.xlsx"
)
AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"
HOTSPOTS_URL = "https://hotspots.dea.ga.gov.au/data/recent-hotspots.json"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


def main() -> None:
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    now = datetime.now(SYD)
    label = "AEDT" if now.utcoffset() == timedelta(hours=11) else "AEST"
    print(f"snapshot clock {now.isoformat()} {label}")

    boundaries = _load_json(_download(SA4_URL, RAW / "sa4_gen.geojson"))
    points = _load_json(_download(SA4_PT_URL, RAW / "sa4_pt.geojson"))
    _download(ERP_URL, RAW / "erp.xlsx")
    _download(AIRPORTS_URL, RAW / "airports.csv")
    _download(RUNWAYS_URL, RAW / "runways.csv")
    hotspots_src = Path("/tmp/srcdata/recent-hotspots.json")
    if not hotspots_src.exists():
        hotspots_src = _download(HOTSPOTS_URL, RAW / "recent-hotspots.json")

    population = _population(RAW / "erp.xlsx")
    population_by_code = {row["sa4_code"]: row for row in population}
    candidates = _candidates(RAW / "airports.csv", RAW / "runways.csv")
    study_codes = _study_codes(boundaries)
    point_rows = _point_rows(points)
    weather_places = []
    for code in sorted(study_codes):
        if code not in point_rows or code not in population_by_code:
            print(f"skip {code}: missing point or population")
            continue
        weather_places.append(point_rows[code])
    print(f"study regions with a point and a population: {len(weather_places)}")

    archive_end = (now.date() - timedelta(days=1)).isoformat()
    daily = _weather(
        weather_places,
        ARCHIVE_URL,
        "2021-01-01",
        archive_end,
        RAW / "openmeteo" / "archive",
    )
    forecast_start = now.date().isoformat()
    forecast_end = (now.date() + timedelta(days=6)).isoformat()
    forecast = _weather(
        weather_places,
        FORECAST_URL,
        forecast_start,
        forecast_end,
        RAW / "openmeteo" / "forecast",
    )
    hot_rows, hot_meta = _hotspots(hotspots_src)

    boundary_path = SNAPSHOT / "sa4_boundaries.geojson"
    boundary_path.write_text(json.dumps(boundaries, separators=(",", ":")))
    point_path = SNAPSHOT / "sa4_points.geojson"
    point_path.write_text(json.dumps(points, separators=(",", ":")))
    pop_path = SNAPSHOT / "population_sa4.csv"
    _write_csv(pop_path, population, ["sa4_code", "sa4_name", "state_code", "state_name", "gccsa_code", "gccsa_name", "erp_2025"])
    base_path = SNAPSHOT / "airports.csv"
    _write_csv(
        base_path,
        candidates,
        ["ident", "name", "municipality", "type", "latitude", "longitude", "icao", "scheduled_service", "runway_m", "iso_region"],
    )
    hot_path = SNAPSHOT / "hotspots.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(hot_rows), preserve_index=False), hot_path)
    weather_path = SNAPSHOT / "weather_daily.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(daily), preserve_index=False), weather_path)
    forecast_path = SNAPSHOT / "weather_forecast.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(forecast), preserve_index=False), forecast_path)

    manifest = {
        "name": "bushfire-fleet-planner snapshot",
        "accessed_at_utc": now.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "accessed_at_aedt": _clock(now, label),
        "tz_label": label,
        "hotspot_min_utc": hot_meta["min_utc"],
        "hotspot_max_utc": hot_meta["max_utc"],
        "forecast_start": forecast_start,
        "forecast_end": forecast_end,
        "archive_start": "2021-01-01",
        "archive_end": archive_end,
        "files": [
            _entry(
                boundary_path,
                "Australian Bureau of Statistics",
                "ASGS Edition 3 SA4 generalised boundaries, 2021",
                SA4_URL,
                "CC BY 4.0",
                len(boundaries["features"]),
                "SA4_GEN from the ABS ArcGIS service with maxAllowableOffset=0.02 degrees and geometryPrecision=4. "
                "Migratory and no-usual-address codes have null geometry in the service and are kept as empty features.",
            ),
            _entry(
                point_path,
                "Australian Bureau of Statistics",
                "ASGS Edition 3 SA4 representative points, 2021",
                SA4_PT_URL,
                "CC BY 4.0",
                len(points["features"]),
                "Official representative point for each SA4, used as the place an aircraft has to reach.",
            ),
            _entry(
                pop_path,
                "Australian Bureau of Statistics",
                "Regional population, 2024–25, ERP by SA4 at 30 June 2025",
                ERP_URL,
                "CC BY 4.0",
                len(population),
                "Table 3 of Population estimates by SA2 and above, 2001 to 2025. The 2025 estimates are preliminary.",
            ),
            _entry(
                base_path,
                "OurAirports",
                "Airports and runways",
                AIRPORTS_URL,
                "Public domain",
                len(candidates),
                "Runways from "
                + RUNWAYS_URL
                + ". Candidates: Australia, large or medium airport, paved runway at least 1,800 m, "
                "and scheduled service or a large airport or a RAAF name, plus YPTN and YSNW.",
            ),
            _entry(
                hot_path,
                "Geoscience Australia",
                "Digital Earth Australia Hotspots, recent feed",
                HOTSPOTS_URL,
                "CC BY 4.0",
                len(hot_rows),
                f"Confidence at least {CONFIDENCE_MIN} and inside longitude {BBOX[0]}–{BBOX[2]}, "
                f"latitude {BBOX[1]}–{BBOX[3]}. Raw feed had {hot_meta['raw']} features; "
                f"{hot_meta['kept']} passed the filter. Satellites: {hot_meta['satellites']}.",
            ),
            _entry(
                weather_path,
                "Open-Meteo",
                "Historical daily weather at SA4 representative points",
                ARCHIVE_URL,
                "CC BY 4.0",
                len(daily),
                "Daily maximum temperature, minimum relative humidity, maximum wind and precipitation, "
                f"timezone=auto, { '2021-01-01' } to {archive_end}. Default archive model.",
            ),
            _entry(
                forecast_path,
                "Open-Meteo",
                "Week-ahead daily forecast at SA4 representative points",
                FORECAST_URL,
                "CC BY 4.0",
                len(forecast),
                f"Same daily variables, timezone=auto, {forecast_start} to {forecast_end}, captured with this snapshot.",
            ),
        ],
        "historical_hotspots_note": (
            "The DEA product description points at a historic archive under "
            "https://hotspots.dea.ga.gov.au/files/historic (all-data-csv.zip and related files) "
            "and at WFS. On 13 November 2026, WFS GetCapabilities listed only recent layers "
            "(public:hotspots, public:hotspots_three_days, satellite-pass layers). GetFeature "
            "requests returned no bytes before timing out. The advertised zip URLs returned the "
            "website HTML shell (about 12 KB), not an archive. The public ga-sentinel bucket listing "
            "contains raw satellite granules, not the hotspot table. Historical fire activity in "
            "this project is therefore the fire-weather record. Satellite heat is the recent feed only."
        ),
    }
    (SNAPSHOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("wrote", SNAPSHOT)
    print("population sum", sum(int(r["erp_2025"]) for r in population))
    print("hotspots", len(hot_rows), "weather rows", len(daily), "forecast rows", len(forecast), "bases", len(candidates))


def _download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"reuse {dest.name}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as resp, dest.open("wb") as handle:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    return dest


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _population(path: Path) -> list[dict]:
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Table 3"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    year_row = next(row for row in rows if row and 2025 in row)
    col = list(year_row).index(2025)
    header = next(i for i, row in enumerate(rows) if row and "SA4 code" in row)
    out = []
    for row in rows[header + 1 :]:
        if not row or row[4] is None:
            continue
        try:
            code = f"{int(row[4]):03d}"
        except (TypeError, ValueError):
            continue
        pop = row[col]
        if pop is None:
            continue
        try:
            pop_i = int(pop)
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "sa4_code": code,
                "sa4_name": str(row[5]),
                "state_code": str(int(row[0])) if row[0] is not None else "",
                "state_name": str(row[1]),
                "gccsa_code": str(row[2] or ""),
                "gccsa_name": str(row[3] or ""),
                "erp_2025": pop_i,
            }
        )
    out.sort(key=lambda r: r["sa4_code"])
    return out


def _candidates(airports_path: Path, runways_path: Path) -> list[dict]:
    runways: dict[str, list[dict]] = {}
    with runways_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            runways.setdefault(row["airport_ident"], []).append(row)
    chosen = []
    with airports_path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            runway_m = longest_paved_runway_m(runways.get(row["ident"], []))
            if not is_candidate(row, runway_m):
                continue
            chosen.append(
                {
                    "ident": row["ident"],
                    "name": row["name"],
                    "municipality": row.get("municipality") or "",
                    "type": row["type"],
                    "latitude": round(float(row["latitude_deg"]), 5),
                    "longitude": round(float(row["longitude_deg"]), 5),
                    "icao": row.get("icao_code") or "",
                    "scheduled_service": row.get("scheduled_service") or "",
                    "runway_m": int(round(runway_m)),
                    "iso_region": row.get("iso_region") or "",
                }
            )
    chosen.sort(key=lambda r: r["ident"])
    return chosen


def _study_codes(boundaries: dict) -> set[str]:
    codes = set()
    for feature in boundaries["features"]:
        props = feature["properties"]
        if in_study(props.get("state_code_2021"), props.get("sa4_name_2021"), feature.get("geometry") is not None):
            codes.add(str(props["sa4_code_2021"]).zfill(3))
    return codes


def _point_rows(points: dict) -> dict[str, dict]:
    out = {}
    for feature in points["features"]:
        geom = feature.get("geometry")
        if not geom:
            continue
        code = str(feature["properties"]["sa4_code_2021"]).zfill(3)
        coords = geom["coordinates"]
        if geom["type"] == "MultiPoint":
            coords = coords[0]
        lon, lat = coords
        out[code] = {"sa4_code": code, "lon": float(lon), "lat": float(lat)}
    return out


def _weather(places: list[dict], endpoint: str, start: str, end: str, cache: Path) -> list[dict]:
    cache.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    batch_size = 8
    for offset in range(0, len(places), batch_size):
        batch = places[offset : offset + batch_size]
        payload = _weather_batch(batch, endpoint, start, end, cache)
        for place, item in zip(batch, payload, strict=True):
            daily = item["daily"]
            for i, day in enumerate(daily["time"]):
                rows.append(
                    {
                        "sa4_code": place["sa4_code"],
                        "date": day,
                        "tmax_c": _num(daily["temperature_2m_max"][i]),
                        "rh_min_pct": _num(daily["relative_humidity_2m_min"][i]),
                        "wind_max_kmh": _num(daily["wind_speed_10m_max"][i]),
                        "precip_mm": _num(daily["precipitation_sum"][i]),
                    }
                )
        time.sleep(0.4)
    rows.sort(key=lambda r: (r["sa4_code"], r["date"]))
    return rows


def _weather_batch(batch: list[dict], endpoint: str, start: str, end: str, cache: Path) -> list[dict]:
    if len(batch) == 1:
        return [_one_place(batch[0], endpoint, start, end, cache)]
    try:
        return _request_places(batch, endpoint, start, end, cache)
    except Exception as exc:
        print(f"batch failed ({exc}); splitting {len(batch)}")
        out = []
        for place in batch:
            out.extend(_weather_batch([place], endpoint, start, end, cache))
        return out


def _request_places(batch: list[dict], endpoint: str, start: str, end: str, cache: Path) -> list[dict]:
    lats = ",".join(f"{p['lat']:.4f}" for p in batch)
    lons = ",".join(f"{p['lon']:.4f}" for p in batch)
    url = (
        f"{endpoint}?latitude={lats}&longitude={lons}&start_date={start}&end_date={end}"
        "&daily=temperature_2m_max,relative_humidity_2m_min,wind_speed_10m_max,precipitation_sum"
        "&timezone=auto"
    )
    data = _cached_json(url, cache)
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(data.get("reason"))
    if isinstance(data, dict) and "daily" in data:
        if len(batch) != 1:
            raise RuntimeError("expected a list of locations")
        return [data]
    if not isinstance(data, list) or len(data) != len(batch):
        raise RuntimeError(f"unexpected weather payload type {type(data).__name__}")
    return data


def _one_place(place: dict, endpoint: str, start: str, end: str, cache: Path) -> dict:
    return _request_places([place], endpoint, start, end, cache)[0]


def _cached_json(url: str, cache: Path) -> dict | list:
    digest = hashlib.sha256(url.encode()).hexdigest()[:20]
    path = cache / f"{digest}.json"
    if path.exists():
        return json.loads(path.read_text())
    delay = 1.0
    last_error: Exception | None = None
    for _ in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = json.loads(resp.read().decode())
            if isinstance(payload, dict) and payload.get("error"):
                raise RuntimeError(payload.get("reason"))
            path.write_text(json.dumps(payload))
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"weather fetch failed: {last_error}")


def _num(value):
    if value is None:
        return None
    return round(float(value), 3)


def _hotspots(path: Path) -> tuple[list[dict], dict]:
    lon_min, lat_min, lon_max, lat_max = BBOX
    rows = []
    satellites: dict[str, int] = {}
    raw = 0
    min_utc = None
    max_utc = None
    with path.open("rb") as handle:
        for feature in ijson.items(handle, "features.item"):
            raw += 1
            props = feature["properties"]
            confidence = props.get("confidence")
            if confidence is None or int(confidence) < CONFIDENCE_MIN:
                continue
            lon = props.get("longitude")
            lat = props.get("latitude")
            if lon is None or lat is None:
                continue
            lon = float(lon)
            lat = float(lat)
            if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
                continue
            observed = props.get("datetime") or props.get("start_dt")
            if not observed:
                continue
            satellite = (props.get("satellite") or "").strip()
            satellites[satellite] = satellites.get(satellite, 0) + 1
            if min_utc is None or observed < min_utc:
                min_utc = observed
            if max_utc is None or observed > max_utc:
                max_utc = observed
            power = props.get("power")
            temp = props.get("temp_kelvin")
            rows.append(
                {
                    "hotspot_id": int(props["id"]),
                    "longitude": round(lon, 5),
                    "latitude": round(lat, 5),
                    "observed_at": observed,
                    "satellite": satellite,
                    "confidence": int(confidence),
                    "power": None if power is None else round(float(power), 2),
                    "temp_kelvin": None if temp is None else round(float(temp), 2),
                    "state_name": (props.get("australian_state") or "").strip(),
                }
            )
    frame = pd.DataFrame(rows).sort_values(["hotspot_id", "observed_at"])
    frame = frame.drop_duplicates("hotspot_id", keep="first")
    kept = frame.to_dict("records")
    meta = {
        "raw": raw,
        "kept": len(kept),
        "min_utc": min_utc,
        "max_utc": max_utc,
        "satellites": dict(sorted(satellites.items())),
    }
    print("hotspots", meta)
    return kept, meta


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _entry(path: Path, publisher: str, title: str, url: str, licence: str, rows: int, note: str) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": path.name,
        "sha256": digest,
        "bytes": path.stat().st_size,
        "rows": rows,
        "publisher": publisher,
        "title": title,
        "source_url": url,
        "licence": licence,
        "note": note,
    }


def _clock(moment: datetime, label: str) -> str:
    hour = str(int(moment.strftime("%I")))
    ampm = moment.strftime("%p").lower()
    return f"{moment.day} {moment.strftime('%B')} {moment.year}, {hour}:{moment.strftime('%M')} {ampm} {label}"


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        print(exc, file=sys.stderr)
        raise
