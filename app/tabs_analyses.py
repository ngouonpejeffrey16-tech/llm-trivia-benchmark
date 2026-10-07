"""
Onglets d'analyse : Prompts, Temps de réponse, Questions pièges, Explorer.
"""
import plotly.express as px
import streamlit as st

from data import PROMPT_LABELS


def render_prompts(impact, colors):
    st.subheader("Quel est l'effet du prompt, à modèle constant ?")
    d = impact.copy()
    d["prompt"] = d["prompt_id"].map(PROMPT_LABELS)
    d = d.sort_values("prompt_id")
    fig = px.bar(d, x="prompt", y="delta_vs_p1_pts", color="model", barmode="group",
                 color_discrete_map=colors,
                 labels={"delta_vs_p1_pts": "Gain vs p1 (points)", "prompt": "", "model": "Modèle"})
    fig.update_traces(hovertemplate="%{x}<br>%{y:+.1f} pts<extra></extra>")
    fig.add_hline(y=0, line_color="#898781", line_width=1)
    fig.update_layout(height=380, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2 = st.columns(2)
    f1 = px.bar(d, x="prompt", y="avg_answer_words", color="model", barmode="group",
                color_discrete_map=colors, title="Longueur des réponses (mots)",
                labels={"avg_answer_words": "Mots par réponse", "prompt": "", "model": "Modèle"})
    f1.update_layout(height=320, showlegend=False)
    c1.plotly_chart(f1, use_container_width=True)
    f2 = px.bar(d, x="prompt", y="parse_rate_pct", color="model", barmode="group",
                color_discrete_map=colors, title="Réponses au bon format (%)",
                labels={"parse_rate_pct": "%", "prompt": "", "model": "Modèle"})
    f2.update_layout(height=320, yaxis_range=[0, 100], showlegend=False)
    c2.plotly_chart(f2, use_container_width=True)
    st.caption("Le taux de format n'est vraiment informatif que pour p3 et p4 : "
               "en réponse libre, toute réponse non vide est considérée comme lisible.")


def render_temps(lb, log, colors):
    st.subheader("Vitesse et exactitude : quel compromis ?")
    st.info("Chaque modèle a tourné sur un PC différent : comparez les temps **entre prompts "
            "d'un même modèle**, pas d'un modèle à l'autre.", icon="ℹ️")
    d = lb.copy()
    d["prompt"] = d["prompt_id"].map(PROMPT_LABELS)
    fig = px.scatter(d, x="avg_response_time_s", y="accuracy_pct", color="model", symbol="prompt",
                     color_discrete_map=colors, hover_data={"p95_response_time_s": ":.2f"},
                     labels={"avg_response_time_s": "Temps moyen (s)", "accuracy_pct": "Exactitude (%)",
                             "model": "Modèle", "prompt": "Prompt"})
    fig.update_traces(marker=dict(size=13, line=dict(width=2, color="white")))
    fig.update_layout(height=420, yaxis_range=[0, 100], margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**Le modèle met-il plus de temps quand il se trompe ?**")
    l = log[~log["has_error"]].copy()
    l["Réponse"] = l["ai_correct"].map({True: "Juste", False: "Fausse"})
    l["prompt"] = l["prompt_id"].map(PROMPT_LABELS)
    fig2 = px.box(l, x="prompt", y="response_time", color="Réponse", facet_col="model", points=False,
                  color_discrete_map={"Juste": "#2a78d6", "Fausse": "#eb6834"},
                  labels={"response_time": "Temps (s)", "prompt": ""})
    fig2.update_layout(height=380, margin=dict(t=30))
    st.plotly_chart(fig2, use_container_width=True)


def render_pieges(questions):
    st.subheader("Quelles questions piègent les modèles ?")
    order = ["facile", "moyenne", "difficile"]
    cross = (questions.pivot_table(index="official_difficulty", columns="observed_difficulty",
                                   values="question_id", aggfunc="count", fill_value=0)
             .reindex(index=["easy", "medium", "hard"], columns=order, fill_value=0))
    cross.index = ["Facile (OpenTDB)", "Moyen (OpenTDB)", "Difficile (OpenTDB)"]
    cross.columns = ["Facile pour les LLM", "Moyenne pour les LLM", "Difficile pour les LLM"]
    st.markdown("**Difficulté officielle vs difficulté observée** (nombre de questions)")
    st.dataframe(cross, use_container_width=True)

    failed = questions[questions["failed_by_all"]].sort_values("category")
    st.markdown(f"**{len(failed)} questions ratées par tous les modèles avec tous les prompts**")
    st.dataframe(failed[["category", "official_difficulty", "question", "correct_answer"]],
                 hide_index=True, use_container_width=True,
                 column_config={"category": "Catégorie", "official_difficulty": "Difficulté",
                                "question": "Question", "correct_answer": "Bonne réponse"})


def render_explorer(log):
    st.subheader("Explorer les réponses une par une")
    c1, c2, c3 = st.columns(3)
    only_wrong = c1.toggle("Uniquement les erreurs", value=True)
    category = c2.selectbox("Catégorie", ["(toutes)"] + sorted(log["category"].unique()))
    search = c3.text_input("Rechercher dans la question")
    d = log
    if only_wrong:
        d = d[~d["ai_correct"]]
    if category != "(toutes)":
        d = d[d["category"] == category]
    if search:
        d = d[d["question"].str.contains(search, case=False, na=False)]
    st.caption(f"{len(d)} réponses")
    st.dataframe(
        d[["model", "prompt_id", "category", "difficulty", "question", "correct_answer",
           "ai_answer_raw", "ai_correct", "response_time"]].head(1000),
        hide_index=True, use_container_width=True,
        column_config={"model": "Modèle", "prompt_id": "Prompt", "category": "Catégorie",
                       "difficulty": "Difficulté", "question": "Question",
                       "correct_answer": "Bonne réponse", "ai_answer_raw": "Réponse brute du modèle",
                       "ai_correct": "Juste ?",
                       "response_time": st.column_config.NumberColumn("Temps", format="%.2f s")},
    )