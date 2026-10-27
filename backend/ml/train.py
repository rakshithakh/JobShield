"""Train the TF-IDF + logistic-regression text model on EMSCAD and write artifacts + model_metadata.json.

    python -m ml.train --data /path/to/fake_job_postings.csv

Protocol: dedupe -> stratified 60/20/20 split -> choose C on the validation set by PR-AUC -> refit on train+validation ->
report metrics on the untouched test set. The deployed artifact is that train+validation model, so the reported test numbers
describe exactly the shipped model. Scores are NOT calibrated probabilities (class_weight='balanced').
"""
import argparse
import datetime as dt
import hashlib
import json
import pickle
from pathlib import Path

import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score

from .common import SEED, load_dataset, sha256_file, split

CS = (1, 4, 10, 30)


def make(C: float):
    return (TfidfVectorizer(max_features=50000, ngram_range=(1, 2), stop_words="english", min_df=3, sublinear_tf=True),
            LogisticRegression(class_weight="balanced", max_iter=3000, C=C))


def threshold_table(y, p, thresholds=(0.5, 0.7, 0.8, 0.9)):
    rows = []
    for t in thresholds:
        pr, rc, f1, _ = precision_recall_fscore_support(y, p >= t, average="binary", zero_division=0)
        rows.append({"threshold": t, "precision": round(float(pr), 3), "recall": round(float(rc), 3), "f1": round(float(f1), 3),
                     "flagged": int((p >= t).sum()), "of": int(len(y))})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="path to EMSCAD fake_job_postings.csv")
    ap.add_argument("--out", default="ml/artifacts")
    a = ap.parse_args()

    df = load_dataset(a.data)
    train, val, test, trainval = split(df)
    scores = {}
    for C in CS:
        vec, clf = make(C)
        clf.fit(vec.fit_transform(train["text"]), train["fraudulent"])
        scores[C] = float(average_precision_score(val["fraudulent"], clf.predict_proba(vec.transform(val["text"]))[:, 1]))
    best_C = max(scores, key=scores.get)

    vec, clf = make(best_C)
    clf.fit(vec.fit_transform(trainval["text"]), trainval["fraudulent"])
    p = clf.predict_proba(vec.transform(test["text"]))[:, 1]
    y = test["fraudulent"]

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, obj in (("scam_model.pkl", clf), ("vectorizer.pkl", vec)):
        (out / name).write_bytes(pickle.dumps(obj))
    meta = {
        "trained_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
        "dataset": {"name": "EMSCAD (fake_job_postings.csv)", "sha256": sha256_file(a.data), "rows_after_dedupe": int(len(df)),
                    "fraud_rows": int(df["fraudulent"].sum()), "train": len(train), "validation": len(val), "test": len(test), "seed": SEED},
        "hyperparameters": {"C": best_C, "validation_pr_auc_by_C": {str(k): round(v, 4) for k, v in scores.items()},
                            "tfidf": "word 1-2grams, 50k features, min_df=3, sublinear_tf"},
        "test_metrics": {"base_rate": round(float(y.mean()), 4), "roc_auc": round(float(roc_auc_score(y, p)), 4),
                         "pr_auc": round(float(average_precision_score(y, p)), 4), "thresholds": threshold_table(y, p)},
        "caveats": ["Scores are not calibrated probabilities.",
                    "EMSCAD is mostly US/UK English postings (~4% fraud); Indian WhatsApp/UPI-style scams are under-represented.",
                    "Test numbers hold for EMSCAD-like postings only."],
        "sha256": {n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in ("scam_model.pkl", "vectorizer.pkl")},
    }
    (out / "model_metadata.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta["test_metrics"], indent=2), "\nbest C:", best_C)


if __name__ == "__main__":
    main()
