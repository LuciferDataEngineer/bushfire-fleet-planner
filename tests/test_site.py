"""Checks that run after the pipeline has written the site."""

import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGES = ["index.html", "where.html", "fleet.html", "week.html"]
FORBIDDEN = re.compile(
    r"\b(sedona|duckdb|pyspark|spark|or-tools|ortools|kubernetes|argocd|kuberay|"
    r"monte carlo|ffdi|mcarthur|geohash|parquet|pipeline|schema)\b",
    re.I,
)

pytestmark = pytest.mark.contract


def test_pages_exist_and_stay_in_plain_language():
    for name in PAGES:
        text = (SITE / name).read_text()
        assert "<h1>" in text
        assert "What this means" in text
        assert "Exact values" in text
        assert FORBIDDEN.search(text) is None
        assert "As at " in text
        assert "AEDT" in text or "AEST" in text


def test_each_page_has_three_to_five_kpis_and_at_most_three_visible_charts():
    for name in PAGES:
        text = (SITE / name).read_text()
        assert 3 <= text.count('class="kpi"') <= 5
        visible = _visible_charts(text)
        assert 1 <= visible <= 3, name


def test_chart_labels_sit_inside_the_viewbox():
    for name in PAGES:
        for view_box, texts in _svgs((SITE / name).read_text()):
            min_x, min_y, width, height = view_box
            max_x, max_y = min_x + width, min_y + height
            for x, y, label in texts:
                assert min_x - 1 <= x <= max_x + 1
                assert min_y - 2 <= y <= max_y + 2
                assert x + len(label) * 6.4 <= max_x + 8


def test_snapshot_hashes_match_the_manifest():
    manifest = json.loads((ROOT / "data" / "snapshot" / "manifest.json").read_text())
    for item in manifest["files"]:
        path = ROOT / "data" / "snapshot" / item["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == item["sha256"]
        assert item["rows"] > 0
        assert item["licence"]


class _ChartCounter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.charts = 0
        self._stack = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        hidden = "hidden" in attr
        classes = attr.get("class", "")
        self._stack.append((tag, hidden))
        if hidden:
            self.hidden += 1
        if tag == "section" and "chart-card" in classes and "map-card" not in classes and self.hidden == 0:
            self.charts += 1

    def handle_endtag(self, tag):
        while self._stack:
            opened, hidden = self._stack.pop()
            if hidden:
                self.hidden -= 1
            if opened == tag:
                break


def _visible_charts(text: str) -> int:
    parser = _ChartCounter()
    parser.feed(text)
    return parser.charts


def _svgs(text: str):
    for match in re.finditer(r"<svg\b([^>]*)>(.*?)</svg>", text, re.S):
        header, body = match.group(1), match.group(2)
        view = re.search(r'viewBox="([\d.\-]+) ([\d.\-]+) ([\d.\-]+) ([\d.\-]+)"', header)
        if not view:
            continue
        box = tuple(float(part) for part in view.groups())
        texts = []
        for text_tag in re.finditer(r"<text\b([^>]*)>([^<]*)</text>", body):
            attrs, label = text_tag.group(1), text_tag.group(2)
            x = float(re.search(r'\bx="([\d.\-]+)"', attrs).group(1))
            y = float(re.search(r'\by="([\d.\-]+)"', attrs).group(1))
            texts.append((x, y, label))
        yield box, texts
