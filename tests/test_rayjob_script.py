import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "k8s" / "ray" / "sim.py"


def test_rayjob_script_is_deterministic(tmp_path):
    fixture = tmp_path / "fixture.csv"
    fixture.write_text(
        "sa4_code,ffdi,tmax_c\n"
        "101,20,22\n101,55,34\n101,80,40\n101,10,18\n"
        "201,15,20\n201,60,36\n201,70,38\n201,25,24\n"
    )
    env = os.environ.copy()
    env.pop("RAY_ADDRESS", None)
    env.update(
        {
            "FIXTURE_PATH": str(fixture),
            "N_SEASONS": "6",
            "SEASON_DAYS": "8",
            "SEED": "15",
            "BETA": "0.8",
        }
    )
    first = subprocess.run([sys.executable, str(SIM)], check=True, capture_output=True, text=True, env=env)
    second = subprocess.run([sys.executable, str(SIM)], check=True, capture_output=True, text=True, env=env)
    assert "RAYJOB_OK" in first.stdout
    assert first.stdout.strip() == second.stdout.strip()
