import hashlib
import re

import pandas as pd
from sklearn.model_selection import train_test_split

TEXT_COLS = [
    "title",
    "company_profile",
    "description",
    "requirements",
    "benefits",
]
SEED = 42
def sha256_file(path: str) -> str:
    """Calculate the SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
def load_dataset(path: str) -> pd.DataFrame:
    """
    Load EMSCAD, build the combined text column, remove duplicate postings,
    and normalize fraud labels to integers.

    Supported fraudulent labels:
        f / false / 0 -> 0 (genuine)
        t / true  / 1 -> 1 (fraudulent)
    """
    df = pd.read_csv(path)

    if "fraudulent" not in df.columns:
        raise ValueError(
            "Dataset must contain a 'fraudulent' column."
        )

    # Ensure all required text columns exist.
    for column in TEXT_COLS:
        if column not in df.columns:
            df[column] = ""

    # Handle missing text values.
    df[TEXT_COLS] = df[TEXT_COLS].fillna("").astype(str)

    # Combine text fields in the same order used by training.
    df["text"] = df[TEXT_COLS].apply(
        lambda row: " ".join(row),
        axis=1,
    )

    # Remove duplicate postings using title and normalized description.
    key = (
        df["title"].str.lower().str.strip()
        + "|"
        + df["description"].str.lower().map(
            lambda text: re.sub(r"\s+", " ", text).strip()
        )
    )

    out = (
        df.assign(_k=key)
        .drop_duplicates("_k")
        .drop(columns="_k")
        .reset_index(drop=True)
    )

    # Normalize labels from EMSCAD or numeric datasets.
    labels = (
        out["fraudulent"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    label_map = {
        "f": 0,
        "false": 0,
        "0": 0,
        "t": 1,
        "true": 1,
        "1": 1,
    }

    mapped = labels.map(label_map)

    if mapped.isna().any():
        invalid_labels = labels[mapped.isna()].unique().tolist()
        raise ValueError(
            f"Unknown or missing fraudulent labels: {invalid_labels}"
        )

    out["fraudulent"] = mapped.astype(int)

    return out


def split(df: pd.DataFrame):
    """
    Create stratified 60/20/20 train, validation, and test splits.

    Validation selects hyperparameters; the test set remains held out.
    """
    trainval, test = train_test_split(
        df,
        test_size=0.2,
        stratify=df["fraudulent"],
        random_state=SEED,
    )

    train, val = train_test_split(
        trainval,
        test_size=0.25,
        stratify=trainval["fraudulent"],
        random_state=SEED,
    )

    return train, val, test, trainval
random-