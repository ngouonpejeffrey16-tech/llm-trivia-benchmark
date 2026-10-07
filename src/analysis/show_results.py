"""
Affiche les résultats principaux du benchmark, lus dans la couche gold (schéma mart).

Usage (depuis la racine du projet, après `dbt build`) :
    python src/analysis/show_results.py              # tous les tableaux
    python src/analysis/show_results.py classement   # un seul tableau
Tableaux disponibles : classement, prompts, difficulte, categories,
                       officiel_vs_observe, pieges, echantillon
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

DB = Path(__file__).resolve().parents[2] / "data" / "gold" / "benchmark.duckdb"
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 60)

QUERIES = {
    "classement": (
        "a) Classement modèle x prompt",
        """
        select model, prompt_id, n_questions, accuracy_pct, gain_vs_random_pts,
               avg_response_time_s, parse_rate_pct
        from mart.mart_model_leaderboard
        order by rank_accuracy
        """,
    ),
    "prompts": (
        "b) Effet du prompt à modèle constant (écart vs p1_open)",
        """
        select model, prompt_id, accuracy_pct, delta_vs_p1_pts,
               avg_response_time_s, avg_answer_words
        from mart.mart_prompt_impact
        order by model, prompt_id
        """,
    ),
    "difficulte": (
        "c) Exactitude par difficulté (prompt p4_mcq_fewshot)",
        """
        select model, difficulty,
               round(sum(accuracy_pct * n_questions) / sum(n_questions), 1) as exactitude,
               sum(n_questions) as n
        from mart.mart_accuracy_by_difficulty
        where prompt_id = 'p4_mcq_fewshot'
        group by model, difficulty, difficulty_rank
        order by model, difficulty_rank
        """,
    ),
    "categories": (
        "d) Exactitude par catégorie (prompt p4_mcq_fewshot, moyenne des modèles)",
        """
        select category, round(avg(accuracy_pct), 1) as exactitude_moy,
               sum(n_questions) as n
        from mart.mart_accuracy_by_category
        where prompt_id = 'p4_mcq_fewshot'
        group by category
        order by exactitude_moy desc
        """,
    ),
    "officiel_vs_observe": (
        "e) Difficulté officielle (lignes) vs difficulté observée chez les LLM (colonnes)",
        """
        pivot mart.mart_question_difficulty
        on observed_difficulty using count(*)
        group by official_difficulty
        order by official_difficulty
        """,
    ),
    "pieges": (
        "f) Questions ratées par tous les modèles et tous les prompts (10 premières)",
        """
        select category, official_difficulty, question, correct_answer
        from mart.mart_question_difficulty
        where failed_by_all
        order by category
        limit 10
        """,
    ),
    "echantillon": (
        "g) Contrôle manuel : 20 réponses au hasard (ai_correct est-il juste ?)",
        """
        select model, prompt_id, correct_answer,
               left(ai_answer_raw, 60) as reponse_brute, ai_correct
        from mart.mart_response_log
        using sample 20
        """,
    ),
}


def main():
    if not DB.exists():
        sys.exit(f"Base introuvable : {DB}\nLance d'abord : cd dbt_benchmark ; dbt build --profiles-dir .")
    wanted = sys.argv[1:] or list(QUERIES)
    unknown = [w for w in wanted if w not in QUERIES]
    if unknown:
        sys.exit(f"Tableau inconnu : {unknown}. Choix possibles : {', '.join(QUERIES)}")

    with duckdb.connect(str(DB), read_only=True) as con:
        for key in wanted:
            title, sql = QUERIES[key]
            print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
            print(con.sql(sql).df().to_string(index=False))


if __name__ == "__main__":
    main()