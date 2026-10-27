"""The landing page claims its sample is real engine output. Enforce it: parse frontend/src/lib/sample.js and compare."""
import re
from pathlib import Path

from app.services.pipeline import run_pipeline
from app.services.types import AnalysisInput
from tests.conftest import make_detector

SAMPLE_JS = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "sample.js").read_text(encoding="utf-8")


def sample_text() -> str:
    parts = re.search(r"SAMPLE_PARTS = \[(.*?)\n\];", SAMPLE_JS, re.S).group(1)
    return "".join(re.findall(r'\bt: "((?:[^"\\]|\\.)*)"', parts))


def test_sample_signals_and_total_match_the_real_engine():
    result = run_pipeline(AnalysisInput(sample_text()), make_detector([]))   # rules/contact/salary only (no ML stage)
    shown = dict(re.findall(r'title: "([^"]+)", points: (\d+)', SAMPLE_JS))
    actual = {s.title: s.points for s in result.signals if s.points > 0}
    assert {k: int(v) for k, v in shown.items()} == actual
    raw, capped = map(int, re.search(r"raw: (\d+), capped: (\d+)", SAMPLE_JS).groups())
    assert (raw, capped) == (result.score_breakdown["raw_total"], result.risk_score)
