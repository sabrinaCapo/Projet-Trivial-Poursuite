"""
Dashboard Streamlit : lit la couche gold (data/gold/benchmark.duckdb).
Lancer : streamlit run app/streamlit_app.py
"""

from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gold" / "benchmark.duckdb"

st.set_page_config(page_title="Benchmark LLM", layout="wide")


@st.cache_data(ttl=60)  # cache court : les nouvelles données apparaissent vite
def load(table: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.sql(f"select * from main_mart.{table}").df()
    finally:
        con.close()  # libère le fichier pour dbt


def wavg(df: pd.DataFrame, col: str) -> float:
    """Moyenne pondérée par le nombre de réponses."""
    return (df[col] * df["nb_answers"]).sum() / df["nb_answers"].sum()


# --- Chargement des marts ---
try:
    by_prompt = load("accuracy_by_prompt")
    by_category = load("accuracy_by_category")
    by_difficulty = load("accuracy_by_difficulty")
except Exception as e:
    st.error(f"Impossible de lire la base gold : {e}\nLancez d'abord `dbt run`.")
    st.stop()

st.title("Benchmark d'un LLM local : culture générale")

# --- Filtres (barre latérale) ---
st.sidebar.header("Filtres")
models = st.sidebar.multiselect(
    "Modèle", sorted(by_prompt["model"].unique()), default=sorted(by_prompt["model"].unique())
)
prompts = st.sidebar.multiselect(
    "Prompt", sorted(by_prompt["prompt_id"].unique()), default=sorted(by_prompt["prompt_id"].unique())
)


def filt(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["model"].isin(models) & df["prompt_id"].isin(prompts)]


p, c, d = filt(by_prompt), filt(by_category), filt(by_difficulty)
if p.empty:
    st.warning("Aucune donnée pour ces filtres.")
    st.stop()

# --- Indicateurs clés ---
# Hasard : 25 % en QCM (4 choix), 50 % en vrai/faux
n_by_type = d.groupby("question_type")["nb_answers"].sum()
chance = (n_by_type.get("multiple", 0) * 25 + n_by_type.get("boolean", 0) * 50) / max(n_by_type.sum(), 1)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Réponses", f"{int(p['nb_answers'].sum()):,}")
k2.metric("Bonnes réponses", f"{wavg(p, 'accuracy_pct'):.1f} %")
k3.metric("Niveau du hasard", f"{chance:.1f} %")
k4.metric("Format respecté", f"{wavg(p, 'valid_format_pct'):.1f} %")
k5.metric("Temps moyen", f"{wavg(p, 'avg_response_time'):.1f} s")

tab1, tab2, tab3 = st.tabs(["Prompts", "Catégories", "Difficulté"])

# --- Onglet 1 : quel prompt est le meilleur ? ---
with tab1:
    st.subheader("Quel prompt donne les meilleures réponses ?")
    fig = px.bar(p, x="prompt_id", y="accuracy_pct", color="model", barmode="group",
                 text="accuracy_pct", labels={"accuracy_pct": "Bonnes réponses (%)", "prompt_id": "Prompt"})
    fig.add_hline(y=chance, line_dash="dash", annotation_text="hasard")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(p, use_container_width=True, hide_index=True)

# --- Onglet 2 : forces et faiblesses par catégorie ---
with tab2:
    st.subheader("Dans quelles catégories le modèle est-il le plus fort ?")
    cat = (
        c.assign(correct=c["accuracy_pct"] * c["nb_answers"])
        .groupby("category", as_index=False)[["correct", "nb_answers"]].sum()
    )
    cat["accuracy_pct"] = (cat["correct"] / cat["nb_answers"]).round(1)
    cat = cat.sort_values("accuracy_pct")
    fig = px.bar(cat, x="accuracy_pct", y="category", orientation="h",
                 hover_data=["nb_answers"], labels={"accuracy_pct": "Bonnes réponses (%)", "category": ""})
    fig.update_layout(height=max(400, 25 * len(cat)))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Attention : peu de réponses par catégorie = score peu fiable (voir nb_answers au survol).")

# --- Onglet 3 : difficulté et type de question ---
with tab3:
    st.subheader("La difficulté et le type de question changent-ils le score ?")
    diff = (
        d.assign(correct=d["accuracy_pct"] * d["nb_answers"])
        .groupby(["difficulty", "question_type"], as_index=False)[["correct", "nb_answers"]].sum()
    )
    diff["accuracy_pct"] = (diff["correct"] / diff["nb_answers"]).round(1)
    order = {"difficulty": ["easy", "medium", "hard"]}
    fig = px.bar(diff, x="difficulty", y="accuracy_pct", color="question_type", barmode="group",
                 category_orders=order, hover_data=["nb_answers"],
                 labels={"accuracy_pct": "Bonnes réponses (%)", "difficulty": "Difficulté"})
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(diff.drop(columns="correct"), use_container_width=True, hide_index=True)