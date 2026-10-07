"""
Bronze -> Silver : nettoie data/bronze/questions_raw.csv
et écrit data/silver/questions_clean.parquet (avec un question_id stable).
"""

import hashlib
from pathlib import Path

import pandas as pd

BRONZE_PATH = Path("data/bronze/questions_raw.csv")
SILVER_PATH = Path("data/silver/questions_clean.parquet")


def make_id(text: str) -> str:
    """Identifiant stable : même question -> même id, à chaque exécution."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def main() -> None:
    df = pd.read_csv(BRONZE_PATH)
    n_raw = len(df)

    # Nettoyage des textes
    text_cols = ["category", "type", "difficulty", "question", "correct_answer"]
    for col in text_cols:
        df[col] = df[col].astype("string").str.strip()
    df["type"] = df["type"].str.lower()
    df["difficulty"] = df["difficulty"].str.lower()

    # Suppression des lignes inutilisables
    df = df.dropna(subset=["question", "correct_answer", "category"])

    # Identifiant et déduplication
    df["question_id"] = df["question"].map(make_id)
    df = df.drop_duplicates(subset="question_id")

    # Types et ordre des colonnes
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], utc=True)
    df = df[
        [
            "question_id",
            "category",
            "type",
            "difficulty",
            "question",
            "correct_answer",
            "incorrect_answers",
            "scraped_at",
        ]
    ]

    SILVER_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(SILVER_PATH, index=False)

    print(f"{n_raw} lignes en bronze -> {len(df)} en silver")
    print(df["type"].value_counts().to_string())
    print(df["difficulty"].value_counts().to_string())
    print(f"Écrit : {SILVER_PATH}")


if __name__ == "__main__":
    main()