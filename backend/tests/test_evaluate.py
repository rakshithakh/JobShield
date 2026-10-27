import json
from pathlib import Path

from ml.common import sha256_file
from ml.evaluate import dataset_provenance


def test_evaluation_reports_matching_model_training_dataset_hash(tmp_path: Path):
    data = tmp_path / "data.csv"
    data.write_text("title,fraudulent\nEngineer,0\n", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "model_metadata.json").write_text(
        json.dumps({"dataset": {"sha256": sha256_file(str(data))}}), encoding="utf-8"
    )

    report = dataset_provenance(str(data), str(artifacts))

    assert report["training_data_hash_matches_evaluation"] is True
    assert report["evaluation_dataset_sha256"] == report["model_training_dataset_sha256"]


def test_evaluation_reports_mismatched_or_missing_training_hash(tmp_path: Path):
    data = tmp_path / "data.csv"
    data.write_text("title,fraudulent\nEngineer,0\n", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    metadata = artifacts / "model_metadata.json"
    metadata.write_text(json.dumps({"dataset": {"sha256": "different"}}), encoding="utf-8")

    assert dataset_provenance(str(data), str(artifacts))["training_data_hash_matches_evaluation"] is False

    metadata.write_text(json.dumps({"dataset": {}}), encoding="utf-8")
    assert dataset_provenance(str(data), str(artifacts))["training_data_hash_matches_evaluation"] is None
