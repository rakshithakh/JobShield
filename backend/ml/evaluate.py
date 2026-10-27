"""End-to-end evaluation of the real pipeline on the held-out EMSCAD test split (same split as ml.train).

    python -m ml.evaluate --data /path/to/fake_job_postings.csv

Reports precision/recall of the final *risk level* (not just the model), plus ablations (rules only / model only / combined) and an
out-of-domain smoke test on the synthetic India file. EMSCAD has no company names, contact emails or salary text in most rows,
so contact/salary/company stages contribute little here; those stages are evaluated by unit tests, not by this script.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

from app.config import Settings
from app.services import rules as rules_mod
from app.services.company import Mca21Provider
from app.services.ml import MlService
from app.services.pipeline import Detector, run_pipeline
from app.services.scoring import compute_score
from app.services.types import AnalysisInput

from .common import TEXT_COLS, load_dataset, sha256_file, split


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    """95% Wilson score interval for a proportion k/n."""
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def prf(y, pred):
    tp = int(((y == 1) & pred).sum()); fp = int(((y == 0) & pred).sum()); fn = int(((y == 1) & ~pred).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 3), "precision_ci95": wilson(tp, tp + fp), "recall": round(r, 3), "recall_ci95": wilson(tp, tp + fn), "flagged": tp + fp, "true_positives": tp, "false_positives": fp, "missed": fn}


def dataset_provenance(data_path: str, artifacts_dir: str) -> dict:
    """Report whether the artifact metadata names the same source dataset as this evaluation."""
    data_hash = sha256_file(data_path)
    metadata_path = Path(artifacts_dir) / "model_metadata.json"
    training_hash = None
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        training_hash = metadata.get("dataset", {}).get("sha256")
    matches = data_hash == training_hash if training_hash else None
    return {
        "evaluation_dataset_sha256": data_hash,
        "model_training_dataset_sha256": training_hash,
        "training_data_hash_matches_evaluation": matches,
    }


def run(df, det, only=None):
    rows = []
    for t, title in zip(df["text"], df["title"]):
        r = run_pipeline(AnalysisInput(text=t, job_title=title), det)
        sig = r.signals
        if only == "rules":
            sig = [s for s in sig if s.source == "rules"]
        elif only == "ml":
            sig = [s for s in sig if s.source == "ml"]
        rows.append(compute_score(sig)[0])
    return pd.Series(rows, index=df.index)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--artifacts", default="ml/artifacts")
    a = ap.parse_args()
    s = Settings(database_url="sqlite://", model_artifact_dir=a.artifacts)
    det = Detector(ml=MlService.from_settings(s), registry=Mca21Provider(s))
    assert det.ml.predictors, "model artifacts failed to load"

    df = load_dataset(a.data)
    _, _, test, _ = split(df)
    provenance = dataset_provenance(a.data, a.artifacts)
    y = test["fraudulent"]
    out = {"dataset_sha256": sha256_file(a.data), "data_provenance": provenance,
           "test_rows": int(len(test)), "test_fraud": int(y.sum()),
           "base_rate": round(float(y.mean()), 4), "scoring_version": None, "rules_version": rules_mod.RULES_VERSION, "levels": {}}
    full = run(test, det)
    out["scoring_version"] = run_pipeline(AnalysisInput(text="x" * 30), det).versions["scoring"]
    for name, thr in (("medium_or_high (>=35)", 35), ("high (>=60)", 60)):
        out["levels"][name] = prf(y, full >= thr)
    out["ablation_at_medium_35"] = {k: prf(y, run(test, det, only) >= 35) for k, only in (("rules_only", "rules"), ("model_only", "ml"))}
    out["ablation_at_medium_35"]["combined"] = out["levels"]["medium_or_high (>=35)"]
    out["rule_hit_rate"] = {"fraud": round(float((test[y == 1]["text"].map(lambda t: bool(rules_mod.detect_rule_signals(t)))).mean()), 3),
                            "genuine": round(float((test[y == 0]["text"].map(lambda t: bool(rules_mod.detect_rule_signals(t)))).mean()), 4)}

    smoke_path = Path(__file__).parent / "data" / "synthetic_india_smoke.csv"
    sm = pd.read_csv(smoke_path).fillna("")
    sm["text"] = sm[TEXT_COLS].apply(lambda r: " ".join(r), axis=1)
    sc = run(sm, det)
    out["synthetic_india_smoke"] = {"note": "SYNTHETIC templated text; out-of-domain smoke test only", "rows": len(sm),
                                    **{"medium_or_high": prf(sm["fraudulent"], sc >= 35)}}
    out["caveats"] = ["EMSCAD is mostly US/UK English postings with ~4% fraud.",
                      "No company/contact/salary evidence in most EMSCAD rows, so only text stages are exercised.",
                      "Real-world precision depends on the prevalence of scams among postings users submit, which is not 4%."]
    if provenance["training_data_hash_matches_evaluation"] is False:
        out["caveats"].append("Model training-data hash differs from this evaluation dataset; independence from training data is not verified.")
    Path(a.artifacts, "evaluation.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
