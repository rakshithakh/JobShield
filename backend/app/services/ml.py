"""ML inference with an explicit fallback chain: DistilBERT (optional, weights not shipped) -> TF-IDF + logistic regression.

Model files are pickles. Unpickling executes code, so artifacts are only loaded after their SHA-256 matches
the value recorded in model_metadata.json (written by ml/train.py). Never point MODEL_ARTIFACT_DIR at untrusted files.
"""
import hashlib
import json
import logging
from pathlib import Path
from typing import Protocol

from ..config import Settings
from .types import DetectionPath

log = logging.getLogger("jobsentinel.ml")


class MlUnavailable(Exception):
    pass


class Predictor(Protocol):
    name: str
    version: str
    max_points: int
    def predict(self, text: str) -> float: ...


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TfidfPredictor:
    name = "tfidf"
    max_points = 40  # see scoring.py: justified by held-out EMSCAD precision

    def __init__(self, artifact_dir: str):
        d = Path(artifact_dir)
        meta_path = d / "model_metadata.json"
        if not meta_path.exists():
            raise MlUnavailable("model_metadata.json missing")
        meta = json.loads(meta_path.read_text())
        files = meta.get("sha256", {})
        for fname in ("scam_model.pkl", "vectorizer.pkl"):
            p = d / fname
            if not p.exists():
                raise MlUnavailable(f"{fname} missing")
            if files.get(fname) != _sha256(p):
                raise MlUnavailable(f"{fname} failed integrity check")
        import pickle
        with open(d / "scam_model.pkl", "rb") as f:
            self._model = pickle.load(f)  # noqa: S301 - integrity-checked above
        with open(d / "vectorizer.pkl", "rb") as f:
            self._vec = pickle.load(f)  # noqa: S301
        self.meta = meta
        self.version = f"tfidf-lr:{files['scam_model.pkl'][:8]}"

    def predict(self, text: str) -> float:
        return float(self._model.predict_proba(self._vec.transform([text]))[0][1])


class DistilBertPredictor:
    """Implemented from the original app's code path but NOT verified here: no fine-tuned weights exist in the repo
    and torch/transformers are not installed in the test environment."""
    name = "distilbert"
    max_points = 40

    def __init__(self, model_dir: str):
        try:
            import torch  # noqa: F401
            from transformers import DistilBertForSequenceClassification, DistilBertTokenizerFast
        except ImportError as e:
            raise MlUnavailable("torch/transformers not installed") from e
        if not (Path(model_dir) / "config.json").exists():
            raise MlUnavailable("model directory missing")
        try:
            self._tok = DistilBertTokenizerFast.from_pretrained(model_dir)
            self._model = DistilBertForSequenceClassification.from_pretrained(model_dir)
            self._model.eval()
        except Exception as e:  # weights absent/corrupt
            raise MlUnavailable("could not load DistilBERT weights") from e
        self.version = "distilbert:" + Path(model_dir).name

    def predict(self, text: str) -> float:
        import torch
        inputs = self._tok(text, return_tensors="pt", truncation=True, max_length=256, padding=True)
        with torch.no_grad():
            logits = self._model(**inputs).logits
        return float(torch.softmax(logits, dim=1)[0][1].item())


class MlService:
    """Holds loaded predictors in priority order and records which succeeded."""

    def __init__(self, predictors: list[Predictor], load_paths: list[DetectionPath]):
        self.predictors = predictors
        self.load_paths = load_paths

    @classmethod
    def from_settings(cls, s: Settings) -> "MlService":
        predictors: list[Predictor] = []
        paths: list[DetectionPath] = []
        if s.distilbert_model_dir:
            try:
                predictors.append(DistilBertPredictor(s.distilbert_model_dir))
                paths.append(DetectionPath("distilbert", "ok", "loaded"))
            except MlUnavailable as e:
                paths.append(DetectionPath("distilbert", "unavailable", str(e)))
        else:
            paths.append(DetectionPath("distilbert", "not_configured", "DISTILBERT_MODEL_DIR not set; no weights are shipped"))
        try:
            predictors.append(TfidfPredictor(s.model_artifact_dir))
            paths.append(DetectionPath("tfidf", "ok", "loaded"))
        except (MlUnavailable, OSError, ValueError, Exception) as e:  # corrupted pickle etc.
            log.warning("tfidf_unavailable", extra={"outcome": type(e).__name__})
            paths.append(DetectionPath("tfidf", "unavailable", str(e) if isinstance(e, MlUnavailable) else "could not load artifacts"))
        return cls(predictors, paths)

    def predict(self, text: str) -> tuple[float | None, Predictor | None, list[DetectionPath]]:
        """Try predictors in order. Returns (probability, predictor_used, per-path statuses for this request)."""
        paths = [p for p in self.load_paths if p.status != "ok"]
        for pred in self.predictors:
            try:
                prob = pred.predict(text)
                paths.append(DetectionPath(pred.name, "ok", "inference succeeded"))
                return prob, pred, paths
            except Exception as e:
                log.warning("ml_inference_failed", extra={"provider": pred.name, "outcome": type(e).__name__})
                paths.append(DetectionPath(pred.name, "failed", "inference failed; fell back"))
        return None, None, paths
