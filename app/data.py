"""
Accès aux données du dashboard : lecture de la couche GOLD (schéma `mart`) uniquement,
plus les constantes partagées (couleurs, libellés, filtres).
"""
import math
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "gold" / "benchmark.duckdb"

# Couleurs catégorielles attribuées dans un ORDRE FIXE (jamais selon le classement) :
# un modèle garde toujours la même couleur, quels que soient les filtres.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

PROMPT_LABELS = {
    "p1_open": "p1 · question brute",
    "p2_constrained": "p2 · réponse courte",
    "p3_mcq": "p3 · QCM",
    "p4_mcq_fewshot": "p4 · QCM + exemples",
}
DIFFICULTY_LABELS = {"easy": "Facile", "medium": "Moyen", "hard": "Difficile"}


@st.cache_data(ttl=600)
def load(table: str) -> pd.DataFrame:
    """Lit une table du schéma mart (lecture seule)."""
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute(f"select * from mart.{table}").df()


def model_colors(models) -> dict:
    """Associe à chaque modèle une couleur stable (ordre alphabétique -> slot fixe)."""
    return {m: SERIES_COLORS[i % len(SERIES_COLORS)] for i, m in enumerate(sorted(models))}


def ci95(pct: float, n: int) -> float:
    """Demi-largeur de l'intervalle de confiance à 95 % d'un pourcentage (en points)."""
    if not n:
        return 0.0
    p = pct / 100
    return 100 * 1.96 * math.sqrt(p * (1 - p) / n)


def weighted_accuracy(df: pd.DataFrame, by: list) -> pd.DataFrame:
    """Ré-agrège une exactitude en pondérant par le nombre de questions."""
    out = (
        df.assign(_hits=df["accuracy_pct"] * df["n_questions"] / 100)
        .groupby(by, as_index=False)
        .agg(n_questions=("n_questions", "sum"), _hits=("_hits", "sum"))
    )
    out["accuracy_pct"] = (100 * out["_hits"] / out["n_questions"]).round(1)
    return out.drop(columns="_hits")


def filter_df(df: pd.DataFrame, models: list, prompts: list) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    if "model" in df:
        mask &= df["model"].isin(models)
    if "prompt_id" in df:
        mask &= df["prompt_id"].isin(prompts)
    return df[mask]