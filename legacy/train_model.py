"""
STEP 1: Download dataset from Kaggle first:
  https://www.kaggle.com/datasets/shivamb/real-or-fake-jobs
  Save the CSV as: job_scam_detector/data/fake_job_postings.csv

STEP 2: Run this script:
  python train_model.py

This trains and saves the model to model/ folder.
"""

import pandas as pd
import pickle
import os
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score
from sklearn.pipeline import Pipeline

DATA_PATH = "data/fake_job_postings.csv"
MODEL_DIR = "model"


def prepare_text(df):
    text_cols = ['title', 'company_profile', 'description', 'requirements', 'benefits']
    for col in text_cols:
        if col not in df.columns:
            df[col] = ''
    df[text_cols] = df[text_cols].fillna('')
    df['combined_text'] = df[text_cols].apply(lambda x: ' '.join(x), axis=1)
    return df


def train():
    print("Loading dataset...")
    if not os.path.exists(DATA_PATH):
        print(f"ERROR: Dataset not found at {DATA_PATH}")
        print("Download from: https://www.kaggle.com/datasets/shivamb/real-or-fake-jobs")
        return

    df = pd.read_csv(DATA_PATH)
    print(f"Total records: {len(df)}")
    print(f"Scam jobs: {df['fraudulent'].sum()} | Real jobs: {(df['fraudulent'] == 0).sum()}")

    df = prepare_text(df)
    X = df['combined_text']
    y = df['fraudulent']

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    print("\nTraining model...")
    vectorizer = TfidfVectorizer(
        max_features=15000,
        ngram_range=(1, 2),
        stop_words='english',
        min_df=2
    )

    model = LogisticRegression(
        class_weight='balanced',
        max_iter=1000,
        C=1.0
    )

    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)
    model.fit(X_train_vec, y_train)

    y_pred = model.predict(X_test_vec)
    accuracy = accuracy_score(y_test, y_pred)

    print(f"\nModel Accuracy: {accuracy * 100:.2f}%")
    print("\nDetailed Report:")
    print(classification_report(y_test, y_pred, target_names=['Real Job', 'Scam Job']))

    os.makedirs(MODEL_DIR, exist_ok=True)
    with open(f"{MODEL_DIR}/scam_model.pkl", 'wb') as f:
        pickle.dump(model, f)
    with open(f"{MODEL_DIR}/vectorizer.pkl", 'wb') as f:
        pickle.dump(vectorizer, f)

    print(f"\nModel saved to {MODEL_DIR}/")
    print("Now run: streamlit run app.py")


if __name__ == "__main__":
    train()
