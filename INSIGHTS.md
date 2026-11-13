# Findings and methods

Numbers are from the snapshot taken 14 November 2026, 9:33 am AEDT. The dashboard states the same results in plain language. This note is the technical version.

## What was measured

Study regions are the 88 ASGS Edition 3 SA4s with a polygon, a representative point and an estimated resident population, excluding Other Territories and the migratory / no-usual-address codes (those codes have null geometry in the ABS service). Population is the ABS preliminary ERP at 30 June 2025. The 88 regions sum to 27,608,641 people.

Satellite heat is the DEA recent feed. Of 177,798 features, 115,393 have confidence of at least 80 and lie inside longitude 112–154 and latitude −44.5 to −10. Sedona places 114,931 of those inside a study region. H3 resolution 7 then collapses them to 10,795 region-day-cells. Queensland has 5,302 of those cells, the Northern Territory 2,740, Western Australia 2,502, and the five southern jurisdictions together under 300. The busiest region is Queensland - Outback (3,394).

Dangerous fire weather is a day with a McArthur Mark 5 forest fire danger index of at least 50 (the severe band). The index is

```
FFDI = 2 * exp(-0.450 + 0.987 * ln(DF) - 0.0345 * RH + 0.0338 * T + 0.0234 * V)
```

with drought factor DF clamped to 1–10, RH the daily minimum relative humidity in percent, T the daily maximum temperature in °C, and V the daily maximum 10 m wind in km/h. Open-Meteo supplies those daily values in each location's own timezone.

DF is the Griffiths (1999) drought factor

```
DF = 0.191 * (I + 104) * (N + 1)^1.5 / (3.52 * (N + 1)^1.5 + P - 1)
```

where I is a metric Keetch-Byram drought index in mm, N is days since a day with at least 5 mm of rain, and P is that day's rainfall. The KBDI step is the metric form of Keetch and Byram (1968): US units converted at 0.254 mm per index point, a 5.08 mm interception allowance, daily maximum temperature, and the station's own mean annual rain. The index is capped at 203.2 mm. 2021 is spin-up from a zero start and is dropped before any rate is computed. A reference case used in the unit tests, DF 10, RH 10%, 35°C and 40 km/h, scores 72.95.

Bands shown on the dashboard follow the usual scale: low below 12, high from 12, very high from 25, severe from 50, extreme from 75, catastrophic from 100.

## Where the danger and the heat actually are

Population-weighted dangerous days per year, 2022–2025:

| State or territory | Dangerous days per year, weighted by population | Heat events this reading |
| --- | ---: | ---: |
| Northern Territory | 21.6 | 2,740 |
| Western Australia | 11.5 | 2,502 |
| South Australia | 5.0 | 39 |
| New South Wales | 1.1 | 163 |
| Victoria | 1.0 | 28 |
| Queensland | 0.4 | 5,302 |
| Tasmania | 0.0 | 21 |
| Australian Capital Territory | 0.0 | 0 |

Queensland can lead the heat table and sit near the bottom of the weather table at the same time. The heat is in a few inland and northern regions. The state average is weighted by people, and most Queenslanders live on the coast, where this four-year sample produced very few severe days at the representative point.

The unweighted 75th percentile of regional rates is 2.0 dangerous days a year. Regions at or above that line hold 6,576,145 people (6.6 million) and 80.3% of the heat events. The single highest rate is Western Australia - Outback (South), about 90 days a year, at a point with 128,306 residents and only 25 heat events this week. Treat that rate as a description of the official point, not of every community in a region the size of a country.

## Season simulation

For each region the fiercer half of the year is chosen from the data. If the month with the highest mean index falls in May–October, the season is April–October. Otherwise it is October–March. A season is 120 days drawn with replacement from that region's real days in 2022–2025.

The ordinary draw is uniform. The hotter-day draw uses the same days with weights proportional to `exp(0.8 * z)`, where z is the day's maximum temperature standardised inside that region. No synthetic weather is created. Both draws use the same NumPy seed (`15`, mixed with a CRC32 of the region code). Ray runs one task per region, 200 seasons each.

Population-weighted across the 88 regions, the ordinary draw averages 1.41 severe days per 120-day season and the hotter-day draw averages 4.88. That is about five days against about one, which is a 247% increase on a small base. The dashboard quotes the two day counts, not the percentage, because the percentage overstates a jump from a low starting point. The KubeRay job runs the same function on an 8-region extract (40 days each, 12 seasons of 30 days) so the cluster assertion is `RAYJOB_OK` plus a deterministic mean.

## Placement

Distance is haversine on a 6,371 km sphere. Flight time is 15 minutes plus distance / 450 km/h. A region is covered when at least one chosen base is within the limit. The objective is the sum of regional weights

```
0.50 * population share + 0.30 * dangerous-day share + 0.20 * heat-event share
```

CP-SAT maximises that sum with exactly 6 bases. A penalty of the base index (bases sorted by ident) breaks ties. `num_search_workers = 1` and `random_seed = 15`.

The optimum is Alice Springs (YBAS), Longreach (YLRE), Mildura (YMIA), Kalgoorlie (YPKG), Kununurra (YPKU) and Tamworth (YSTW).

The baseline keeps the longest runway in each of the six city clusters with the most people living within 100 km, and it will not pick a second airport within 150 km. That selects Melbourne (YMML), Sydney (YSSY), Brisbane (YBBN), Perth (YPPH), Adelaide (YPAD) and Newcastle (YWLM). Avalon and Western Sydney score well on nearby population but lose to the longer runway in the same city.

Coverage of the 27.6 million people, the 10,795 heat events, and the sum of dangerous-day rates:

| Window | Set | People | Heat | Dangerous weather | Planning mix |
| --- | --- | ---: | ---: | ---: | ---: |
| 90 min | Recommended | 93.0% | 96.6% | 87.3% | 92.0% |
| 90 min | Biggest cities | 93.5% | 9.5% | 32.7% | 51.8% |
| 60 min | Recommended | 34.0% | 1.5% | 34.1% | 27.5% |
| 60 min | Biggest cities | 90.0% | 3.8% | 29.8% | 48.9% |

At 90 minutes the inland set is slightly worse for people (0.5 percentage points) and much better for heat and for the weather record. At 60 minutes it is worse on every count that matters for people. The radius at 90 minutes is about 560 km, so Tamworth reaches Sydney and Brisbane, Mildura reaches Melbourne and Adelaide, and Kalgoorlie reaches Perth. The radius at 60 minutes is about 340 km, and the official points of the huge outback regions often sit further than that from even a local airport. The 1.5% heat coverage at 60 minutes is that geometry, not a solver failure.

## Spatial engines

Both engines use planar longitude/latitude and `ST_Intersects`. Sedona 1.7.2 on Spark 3.5.5 took 4.2 seconds and counted 114,931 points. DuckDB 1.0 spatial took 15.3 seconds and counted 114,939. The 8-point gap is 0.007%. The pipeline keeps the Sedona result. H3 is `ST_H3CellIDs(geom, 7, false)`; the third argument is required by this Sedona build. Geohash was checked and works, and was not needed once H3 did.

## Forecast week

The forecast snapshot is 14–20 November 2026. The highest state-day score is 53 in Western Australia on 17 November, which is just into the severe band. No other state-day in the snapshot reaches 50. State scores are the maximum across regions in that state, so they describe the most exposed point, not a state average.

## Reproducibility

`outputs/summary.json` and `outputs/perf.json` are rewritten on every pipeline run and are gitignored. The site and `k8s/ray/fixture.csv` are committed and checked by `git diff --exit-code` in CI. Soda Core 3.5.6 runs 27 checks against `outputs/fleet.duckdb`. On Python 3.12, Soda still imports `distutils`, so `setuptools` is pinned.
