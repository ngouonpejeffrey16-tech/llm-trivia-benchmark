"""Nettoie les questions brutes (bronze) et les prépare pour le benchmark (silver).

Entrée  : data/bronze/questions_raw.csv
Sortie  : data/silver/questions_clean.parquet
Contrat : docs/data_contract.md (section SILVER — questions_clean)

Étapes :
  1. décodage des entités HTML (&quot; &#039; ...) et normalisation des espaces ;
  2. normalisation des valeurs (type, difficulté, groupe de catégorie) ;
  3. question_id = sha1(question + correct_answer)[:12], calculé sur le texte
     décodé, puis dédoublonnage ;
  4. options du QCM mélangées une seule fois (graine = question_id),
     boolean = ["True", "False"], et lettre de la bonne réponse ;
  5. enrichissement : nombre de mots de la question ;
  6. échantillon stratifié catégorie x difficulté (graine 42, 300 questions)
     -> colonne in_sample.

Usage :
    python src/processing/clean_questions.py
    python src/processing/clean_questions.py --sample-size 500
"""

import argparse
import hashlib
import html
import json
import random
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = ROOT / "data" / "bronze" / "questions_raw.csv"
OUTPUT_PATH = ROOT / "data" / "silver" / "questions_clean.parquet"

SAMPLE_SIZE = 300   # contrat : 300 questions par défaut
SEED = 42           # contrat : graine = 42
LETTERS = "ABCD"
STRATA = ["category", "difficulty"]

COLUMNS = [
    "question_id", "category_id", "category", "category_group", "type",
    "difficulty", "question", "correct_answer", "incorrect_answers",
    "options", "correct_letter", "n_options", "question_length_words", "in_sample",
]


def clean_text(value: str) -> str:
    text = html.unescape(value)
    text = text.replace("\xa0", " ")           # espaces insécables
    return re.sub(r"\s+", " ", text).strip()   # espaces multiples -> un seul


def make_id(question: str, answer: str) -> str:
    return hashlib.sha1((question + answer).encode("utf-8")).hexdigest()[:12]


def build_options(row) -> pd.Series:
    if row.type == "boolean":
        options = ["True", "False"]
    else:
        options = [row.correct_answer, *row.incorrect_answers]
        random.Random(row.question_id).shuffle(options)
    return pd.Series({
        "options": options,
        "correct_letter": LETTERS[options.index(row.correct_answer)],
        "n_options": len(options),
    })


def stratified_sample(df: pd.DataFrame, size: int, seed: int) -> pd.Series:
    """Booléen par ligne : True pour exactement `size` questions, réparties
    proportionnellement aux strates catégorie x difficulté (méthode du plus fort reste)."""
    counts = df.groupby(STRATA).size()
    quotas = counts * size / len(df)
    alloc = quotas.astype(int)
    remaining = size - alloc.sum()
    alloc[(quotas - alloc).sort_values(ascending=False).index[:remaining]] += 1

    shuffled = df.sample(frac=1, random_state=seed)
    rank = shuffled.groupby(STRATA).cumcount()
    quota = pd.Series(
        pd.MultiIndex.from_frame(shuffled[STRATA]).map(alloc), index=shuffled.index
    )
    return (rank < quota).reindex(df.index)


def clean(raw: pd.DataFrame, sample_size: int) -> pd.DataFrame:
    df = raw.copy()

    # 1. Décodage HTML + espaces
    for col in ["category", "question", "correct_answer"]:
        df[col] = df[col].map(clean_text)
    df["incorrect_answers"] = df["incorrect_answers"].map(
        lambda s: [clean_text(a) for a in json.loads(s)]
    )

    # 2. Normalisation
    df["type"] = df["type"].str.strip().str.lower()
    df["difficulty"] = df["difficulty"].str.strip().str.lower()
    df["category_id"] = df["category_id"].astype(int)
    df["category_group"] = df["category"].str.split(":").str[0].str.strip()
    df = df[(df.question != "") & (df.correct_answer != "")]

    # 3. Identifiant + dédoublonnage
    df["question_id"] = [make_id(q, a) for q, a in zip(df.question, df.correct_answer)]
    df = df.drop_duplicates("question_id", keep="first")
    # Tri stable : l'échantillon ne dépend pas de l'ordre du CSV
    df = df.sort_values("question_id").reset_index(drop=True)

    # 4. Options du QCM
    df = pd.concat([df, df.apply(build_options, axis=1)], axis=1)

    # 5. Enrichissement
    df["question_length_words"] = df["question"].str.split().str.len()

    # 6. Échantillon
    df["in_sample"] = stratified_sample(df, sample_size, SEED)

    return df[COLUMNS]


def check(df: pd.DataFrame, sample_size: int) -> None:
    assert df.question_id.is_unique, "question_id non unique"
    assert df.type.isin(["multiple", "boolean"]).all(), "type inattendu"
    assert df.difficulty.isin(["easy", "medium", "hard"]).all(), "difficulté inattendue"
    assert df.correct_letter.notna().all(), "correct_letter manquante"
    assert (df.n_options == df.type.map({"multiple": 4, "boolean": 2})).all(), "nombre d'options incorrect"
    assert df.in_sample.sum() == sample_size, "taille d'échantillon incorrecte"
    assert not df.question.str.contains(r"&(?:quot|#039|amp|lt|gt);").any(), "entités HTML restantes"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    args = parser.parse_args()

    raw = pd.read_csv(INPUT_PATH, dtype=str, keep_default_na=False)
    df = clean(raw, args.sample_size)
    check(df, args.sample_size)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUTPUT_PATH, index=False)

    print(f"{len(raw)} lignes bronze -> {len(df)} questions ({len(raw) - len(df)} doublons/invalides retirés)")
    print(f"{df.in_sample.sum()} questions dans l'échantillon")
    print(f"-> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
