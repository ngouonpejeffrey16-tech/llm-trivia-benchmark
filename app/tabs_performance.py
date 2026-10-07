"""
Onglets de performance : Classement, Catégories, Difficulté.
"""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data import DIFFICULTY_LABELS, PROMPT_LABELS, SEQUENTIAL_BLUE, ci95, weighted_accuracy


def render_classement(lb, colors):
    st.subheader("Quel modèle et quel prompt répondent le mieux ?")
    df = lb.copy()
    df["prompt"] = df["prompt_id"].map(PROMPT_LABELS)
    df["marge"] = [ci95(a, n) for a, n in zip(df["accuracy_pct"], df["n_questions"])]

    fig = go.Figure()
    for model in sorted(df["model"].unique()):
        d = df[df["model"] == model].sort_values("prompt_id")
        fig.add_bar(
            name=model, x=d["prompt"], y=d["accuracy_pct"], marker_color=colors[model],
            error_y=dict(type="data", array=d["marge"], thickness=1.5, width=4),
            customdata=d[["n_questions", "marge", "gain_vs_random_pts"]],
            hovertemplate="<b>%{fullData.name}</b> · %{x}<br>Exactitude : %{y:.1f} %"
                          "<br>Marge 95 % : ± %{customdata[1]:.1f} pts"
                          "<br>Gain vs hasard : %{customdata[2]:+.1f} pts"
                          "<br>Questions : %{customdata[0]}<extra></extra>",
        )
    baseline = df["random_baseline_pct"].mean()
    fig.add_hline(y=baseline, line_dash="dot", line_color="#898781",
                  annotation_text=f"Hasard ≈ {baseline:.0f} %", annotation_position="right",
                  annotation_font_color="#52514e")
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08, height=430,
                      yaxis_title="Exactitude (%)", yaxis_range=[0, 100], xaxis_title=None,
                      legend_title_text="Modèle", margin=dict(t=20, r=110))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Barres d'erreur : intervalle de confiance à 95 %. Deux barres dont les intervalles se "
               "chevauchent largement ne sont pas significativement différentes.")

    table = df.sort_values("rank_accuracy")[[
        "rank_accuracy", "model", "prompt", "n_questions", "accuracy_pct", "marge",
        "gain_vs_random_pts", "avg_response_time_s", "parse_rate_pct", "n_errors"]]
    st.dataframe(
        table, hide_index=True, use_container_width=True,
        column_config={
            "rank_accuracy": st.column_config.NumberColumn("Rang", width="small"),
            "model": "Modèle", "prompt": "Prompt", "n_questions": "Questions",
            "accuracy_pct": st.column_config.ProgressColumn("Exactitude", format="%.1f %%", min_value=0, max_value=100),
            "marge": st.column_config.NumberColumn("Marge 95 %", format="± %.1f"),
            "gain_vs_random_pts": st.column_config.NumberColumn("Gain vs hasard", format="%+.1f pts"),
            "avg_response_time_s": st.column_config.NumberColumn("Temps moyen", format="%.2f s"),
            "parse_rate_pct": st.column_config.NumberColumn("Format respecté", format="%.0f %%"),
            "n_errors": "Erreurs",
        },
    )


def render_categories(by_cat, prompts):
    st.subheader("Sur quels thèmes les modèles sont-ils forts ou faibles ?")
    c1, c2 = st.columns([2, 1])
    prompt = c1.selectbox("Prompt", prompts, index=len(prompts) - 1,
                          format_func=lambda p: PROMPT_LABELS.get(p, p), key="cat_prompt")
    level = c2.radio("Niveau", ["Grands thèmes", "Catégories détaillées"], horizontal=True)
    d = by_cat[by_cat["prompt_id"] == prompt]
    key = "category_group" if level == "Grands thèmes" else "category"
    agg = weighted_accuracy(d, [key, "model"])

    min_n = st.slider("Masquer les lignes avec moins de N questions", 1, 30, 5,
                      help="Sur 4 questions, 100 % ne veut pas dire grand-chose.")
    counts = agg.groupby(key)["n_questions"].max()
    keep = counts[counts >= min_n].index
    agg = agg[agg[key].isin(keep)]
    if agg.empty:
        st.info("Aucune ligne avec assez de questions : baisse le seuil.")
        return

    pivot = agg.pivot(index=key, columns="model", values="accuracy_pct")
    pivot = pivot.loc[pivot.mean(axis=1).sort_values().index]
    n_pivot = agg.pivot(index=key, columns="model", values="n_questions").loc[pivot.index]
    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns, y=pivot.index, zmin=0, zmax=100,
        colorscale=[[i / (len(SEQUENTIAL_BLUE) - 1), c] for i, c in enumerate(SEQUENTIAL_BLUE)],
        text=pivot.values, texttemplate="%{text:.0f}", customdata=n_pivot.values,
        xgap=2, ygap=2, colorbar=dict(title="%"),
        hovertemplate="<b>%{y}</b> · %{x}<br>Exactitude : %{z:.1f} %<br>Questions : %{customdata}<extra></extra>",
    ))
    fig.update_layout(height=max(320, 30 * len(pivot) + 80), margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Lignes triées de la moins bien réussie (en bas) à la mieux réussie (en haut). "
               "Survoler une case pour voir le nombre de questions.")


def render_difficulte(by_diff, colors, prompts):
    st.subheader("La difficulté annoncée par OpenTDB se retrouve-t-elle chez les LLM ?")
    prompt = st.selectbox("Prompt", prompts, index=len(prompts) - 1,
                          format_func=lambda p: PROMPT_LABELS.get(p, p), key="diff_prompt")
    d = by_diff[by_diff["prompt_id"] == prompt]
    agg = weighted_accuracy(d, ["model", "difficulty", "difficulty_rank"]).sort_values("difficulty_rank")
    agg["Difficulté"] = agg["difficulty"].map(DIFFICULTY_LABELS)
    fig = px.line(agg, x="Difficulté", y="accuracy_pct", color="model", markers=True,
                  color_discrete_map=colors, custom_data=["n_questions"],
                  labels={"accuracy_pct": "Exactitude (%)", "model": "Modèle"})
    fig.update_traces(line_width=2, marker_size=9,
                      hovertemplate="%{x} : %{y:.1f} %<br>Questions : %{customdata[0]}<extra></extra>")
    fig.update_layout(yaxis_range=[0, 100], height=380, margin=dict(t=10), xaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("**QCM (4 choix) vs Vrai/Faux (2 choix)**")
    t = weighted_accuracy(d, ["model", "question_type"])
    t["Type"] = t["question_type"].map({"multiple": "QCM · hasard 25 %", "boolean": "Vrai/Faux · hasard 50 %"})
    fig2 = px.bar(t, x="Type", y="accuracy_pct", color="model", barmode="group",
                  color_discrete_map=colors, custom_data=["n_questions"],
                  labels={"accuracy_pct": "Exactitude (%)", "model": "Modèle"})
    fig2.update_traces(hovertemplate="%{x}<br>%{y:.1f} %<br>Questions : %{customdata[0]}<extra></extra>")
    fig2.update_layout(yaxis_range=[0, 100], height=320, margin=dict(t=10), xaxis_title=None)
    st.plotly_chart(fig2, use_container_width=True)