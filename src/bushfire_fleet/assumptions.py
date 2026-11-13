"""Planning assumptions. These are choices, not measurements."""

N_AIRCRAFT = 6
CRUISE_KMH = 450.0
SCRAMBLE_MIN = 15.0
COVER_MINUTES = 90
ALT_COVER_MINUTES = 60
MIN_RUNWAY_M = 1800.0
CONFIDENCE_MIN = 80
H3_RESOLUTION = 7
SEED = 15
N_SEASONS = 200
SEASON_DAYS = 120
EL_NINO_TEMP_BETA = 0.8
W_POP = 0.50
W_WEATHER = 0.30
W_HOTSPOT = 0.20
CLIMATOLOGY_START = "2022-01-01"
CLIMATOLOGY_END = "2025-12-31"
SEVERE_FFDI = 50.0
VERY_HIGH_FFDI = 25.0
HIGH_FFDI = 12.0
EXTREME_FFDI = 75.0
CATASTROPHIC_FFDI = 100.0
# Military fields with a long runway whose OurAirports name does not contain "RAAF".
MILITARY_EXTRA_IDENTS = ("YPTN", "YSNW")
# Continental window used when keeping satellite detections. Offshore territories
# (Cocos, Christmas, Norfolk) sit outside it.
BBOX = (112.0, -44.5, 154.0, -10.0)

SEDONA_PACKAGES = (
    "org.apache.sedona:sedona-spark-shaded-3.5_2.12:1.7.2,"
    "org.datasyslab:geotools-wrapper:1.7.2-28.5"
)
