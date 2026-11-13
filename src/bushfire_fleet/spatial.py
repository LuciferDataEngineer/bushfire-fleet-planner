"""Point-in-polygon and H3 dedupe on Sedona, timed against DuckDB spatial."""

from __future__ import annotations

import os
import time
from pathlib import Path

import duckdb
import pandas as pd

from bushfire_fleet.assumptions import H3_RESOLUTION, SEDONA_PACKAGES


def run_spatial(
    hotspots_path: Path,
    region_wkts: list[dict],
) -> tuple[pd.DataFrame, dict]:
    """Assign detections to regions and collapse them to one H3 cell per day.

    Returns the event table and a timing note that also counts the same
    point-in-polygon test in DuckDB.
    """
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    from sedona.spark import SedonaContext

    spark = (
        SedonaContext.builder()
        .master("local[2]")
        .appName("bushfire-fleet")
        .config("spark.jars.packages", SEDONA_PACKAGES)
        .config("spark.ui.enabled", "false")
        .config("spark.driver.memory", "2g")
        .config("spark.driver.host", "127.0.0.1")
        .config("spark.sql.shuffle.partitions", "8")
        .getOrCreate()
    )
    perf: dict = {"h3_resolution": H3_RESOLUTION}
    try:
        sedona = SedonaContext.create(spark)
        spark.sparkContext.setLogLevel("ERROR")
        regions = sedona.createDataFrame(region_wkts)
        regions.createOrReplaceTempView("regions")
        hot = sedona.read.parquet(str(hotspots_path))
        hot.createOrReplaceTempView("hot_raw")
        sedona.sql(
            """
            CREATE OR REPLACE TEMP VIEW hot AS
            SELECT
              hotspot_id,
              longitude,
              latitude,
              day_local,
              satellite,
              confidence,
              ST_Point(CAST(longitude AS DOUBLE), CAST(latitude AS DOUBLE)) AS geom
            FROM hot_raw
            """
        )
        sedona.sql(
            """
            CREATE OR REPLACE TEMP VIEW region_geom AS
            SELECT sa4_code, ST_GeomFromWKT(wkt) AS geom
            FROM regions
            """
        )
        started = time.perf_counter()
        joined = sedona.sql(
            f"""
            SELECT hotspot_id, sa4_code, day_local, satellite, confidence, longitude, latitude, h3
            FROM (
              SELECT
                h.hotspot_id,
                r.sa4_code,
                h.day_local,
                h.satellite,
                h.confidence,
                h.longitude,
                h.latitude,
                CAST(element_at(ST_H3CellIDs(h.geom, {H3_RESOLUTION}, false), 1) AS STRING) AS h3,
                row_number() OVER (PARTITION BY h.hotspot_id ORDER BY r.sa4_code) AS rn
              FROM hot h
              JOIN region_geom r
                ON ST_Intersects(r.geom, h.geom)
            )
            WHERE rn = 1 AND h3 IS NOT NULL
            """
        )
        joined.createOrReplaceTempView("joined")
        pip_count = joined.count()
        perf["sedona_seconds"] = round(time.perf_counter() - started, 3)
        perf["sedona_points_in_regions"] = int(pip_count)
        events = sedona.sql(
            """
            SELECT
              sa4_code,
              day_local,
              h3 AS cell,
              count(*) AS n_detections,
              max(confidence) AS confidence_max,
              array_join(array_sort(collect_set(satellite)), ',') AS satellites,
              round(avg(longitude), 5) AS lon,
              round(avg(latitude), 5) AS lat
            FROM joined
            GROUP BY sa4_code, day_local, h3
            ORDER BY sa4_code, day_local, h3
            """
        ).toPandas()
    finally:
        spark.stop()

    started = time.perf_counter()
    duck_count = _duckdb_pip_count(hotspots_path, region_wkts)
    perf["duckdb_seconds"] = round(time.perf_counter() - started, 3)
    perf["duckdb_points_in_regions"] = int(duck_count)
    if perf["sedona_points_in_regions"]:
        perf["count_gap_pct"] = round(
            100.0
            * abs(perf["sedona_points_in_regions"] - perf["duckdb_points_in_regions"])
            / perf["sedona_points_in_regions"],
            3,
        )
    else:
        perf["count_gap_pct"] = 0.0
    return events, perf


def _duckdb_pip_count(hotspots_path: Path, region_wkts: list[dict]) -> int:
    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial")
        con.execute("LOAD spatial")
        con.register("region_rows", pd.DataFrame(region_wkts))
        con.execute(
            f"""
            SELECT count(*)
            FROM read_parquet('{hotspots_path.as_posix()}') h
            JOIN (
              SELECT sa4_code, ST_GeomFromText(wkt) AS geom
              FROM region_rows
            ) r
              ON ST_Intersects(r.geom, ST_Point(h.longitude, h.latitude))
            """
        )
        return int(con.fetchone()[0])
    finally:
        con.close()
