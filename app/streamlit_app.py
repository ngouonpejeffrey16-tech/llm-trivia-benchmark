"""
Dashboard du benchmark LLM — lit UNIQUEMENT la couche gold (schéma mart de benchmark.duckdb).

Lancement (depuis la racine du projet, après `dbt build`) :
    streamlit run app/streamlit_app.py
"""
import streamlit as st

from data import DB_PATH, PROMPT_LABELS, filter_df, load, model_colors
from tabs_analyses import render_explorer, render_pieges, render_prompts, render_temps
from tabs_performance import render_categories, render_classement, render_difficulte

st.set_page_config(page_title="Benchmark LLM · Culture générale", page_icon="🧠", layout="wide")

if not DB_PATH.exists():
    st.error(f"Base gold introuvable : `{DB_PATH}`\n\n"
             "Lance d'abord : `cd dbt_benchmark` puis `dbt build --profiles-dir .`")
    st.stop()

leaderboard = load("mart_model_leaderboard")
by_category = load("mart_accuracy_by_category")
by_difficulty = load("mart_accuracy_by_difficulty")
prompt_impact = load("mart_prompt_impact")
question_difficulty = load("mart_question_difficulty")
response_log = load("mart_response_log")

all_models = sorted(leaderboard["model"].unique())
all_prompts = sorted(leaderboard["prompt_id"].unique())
colors = model_colors(all_models)  # calculé sur TOUS les modèles : la couleur ne change pas avec les filtres

# ---------------------------------------------------------------- filtres
with st.sidebar:
    st.header("Filtres")
    models = st.multiselect("Modèles", all_models, default=all_models)
    prompts = st.multiselect("Prompts", all_prompts, default=all_prompts,
                             format_func=lambda p: PROMPT_LABELS.get(p, p))
    st.divider()
    st.caption("**p1** question brute · **p2** réponse courte imposée · **p3** QCM (lettre) · "
               "**p4** QCM + rôle système + 2 exemples")
    st.caption("Données : OpenTDB · échantillon stratifié de 300 questions · température 0 · "
               "réponses limitées à 64 tokens.")
    if st.button("🔄 Recharger les données"):
        st.cache_data.clear()
        st.rerun()

if not models or not prompts:
    st.warning("Sélectionne au moins un modèle et un prompt.")
    st.stop()

lb = filter_df(leaderboard, models, prompts)
log = filter_df(response_log, models, prompts)

# ---------------------------------------------------------------- en-tête + KPI
st.title("🧠 Benchmark LLM · questions de culture générale")
st.caption("Pipeline : OpenTDB → bronze (CSV) → silver (parquet) → dbt → gold (DuckDB) → ce dashboard")

best = lb.sort_values("accuracy_pct", ascending=False).iloc[0]
k1, k2, k3, k4 = st.columns(4)
k1.metric("Meilleure configuration", f"{best['accuracy_pct']:.1f} %",
          f"{best['model']} · {PROMPT_LABELS.get(best['prompt_id'], best['prompt_id'])}", delta_color="off")
k2.metric("Questions par configuration", f"{int(lb['n_questions'].max())}")
k3.metric("Réponses analysées", f"{len(log):,}".replace(",", " "))
k4.metric("Exactitude moyenne", f"{100 * log['ai_correct'].mean():.1f} %")

tabs = st.tabs(["🏆 Classement", "📚 Catégories", "🎚️ Difficulté", "✍️ Prompts",
                "⏱️ Temps de réponse", "🪤 Questions pièges", "🔎 Explorer"])
with tabs[0]:
    render_classement(lb, colors)
with tabs[1]:
    render_categories(filter_df(by_category, models, prompts), prompts)
with tabs[2]:
    render_difficulte(filter_df(by_difficulty, models, prompts), colors, prompts)
with tabs[3]:
    render_prompts(filter_df(prompt_impact, models, prompts), colors)
with tabs[4]:
    render_temps(lb, log, colors)
with tabs[5]:
    render_pieges(question_difficulty)
with tabs[6]:
    render_explorer(log)