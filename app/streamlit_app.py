"""
Dashboard Streamlit : lit la couche gold (data/gold/benchmark.duckdb).
Lancer : streamlit run app/streamlit_app.py
"""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gold" / "benchmark.duckdb"

# Langue de la consigne pour chaque prompt_id
LANG = {"p1_english": "English", "p2_français": "Français"}
COLORS = {"English": "#4C78A8", "Français": "#F58518"}

st.set_page_config(page_title="Benchmark LLM", page_icon="📊", layout="wide")

# --- Style des cartes ---
st.markdown(
    """
    <style>
    .card {border-radius: 14px; padding: 18px 22px; border-left: 8px solid var(--c);
           background: rgba(128,128,128,0.10);}
    .card h3 {margin: 0 0 6px 0; font-size: 1.15rem;}
    .card .big {font-size: 2.4rem; font-weight: 700; line-height: 1.1;}
    .card .sub {opacity: 0.75; font-size: 0.9rem; margin-top: 6px;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=60)  # cache court : les nouvelles données apparaissent vite
def load(table: str) -> pd.DataFrame:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        df = con.sql(f"select * from main_mart.{table}").df()
    finally:
        con.close()  # libère le fichier pour dbt
    df["langue"] = df["prompt_id"].map(lambda x: LANG.get(x, x))
    return df


def wavg(df: pd.DataFrame, col: str) -> float:
    """Moyenne pondérée par le nombre de réponses."""
    return (df[col] * df["nb_answers"]).sum() / df["nb_answers"].sum()


def ci95(acc_pct: float, n: int) -> float:
    """Marge d'erreur à 95 % (en points) d'un pourcentage."""
    p = acc_pct / 100
    return 1.96 * np.sqrt(p * (1 - p) / max(n, 1)) * 100


# --- Chargement des marts ---
try:
    by_prompt = load("accuracy_by_prompt")
    by_category = load("accuracy_by_category")
    by_difficulty = load("accuracy_by_difficulty")
except Exception as e:
    st.error(f"Impossible de lire la base gold : {e}\nLancez d'abord `dbt run`.")
    st.stop()

st.title("📊 Benchmark d'un LLM local : culture générale")
st.caption("Le modèle répond à des QCM et des vrai/faux en choisissant une lettre. "
           "On compare une consigne en anglais et une consigne en français.")

# --- Filtres (barre latérale) ---
st.sidebar.header("Filtres")
all_models = sorted(by_prompt["model"].unique())
all_langs = sorted(by_prompt["langue"].unique())
models = st.sidebar.multiselect("Modèle", all_models, default=all_models)
langs = st.sidebar.multiselect("Langue de la consigne", all_langs, default=all_langs)


def filt(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["model"].isin(models) & df["langue"].isin(langs)]


p, c, d = filt(by_prompt), filt(by_category), filt(by_difficulty)
if p.empty:
    st.warning("Aucune donnée pour ces filtres.")
    st.stop()

# Niveau du hasard : 25 % en QCM (4 choix), 50 % en vrai/faux
n_by_type = d.groupby("question_type")["nb_answers"].sum()
chance = (n_by_type.get("multiple", 0) * 25 + n_by_type.get("boolean", 0) * 50) / max(n_by_type.sum(), 1)

# --- Indicateurs globaux ---
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Réponses", f"{int(p['nb_answers'].sum()):,}")
k2.metric("Bonnes réponses", f"{wavg(p, 'accuracy_pct'):.1f} %")
k3.metric("Niveau du hasard", f"{chance:.1f} %")
k4.metric("Format respecté", f"{wavg(p, 'valid_format_pct'):.1f} %")
k5.metric("Temps moyen", f"{wavg(p, 'avg_response_time'):.1f} s")

tab1, tab2, tab3 = st.tabs(["🌍 Prompts : English vs Français", "📚 Catégories", "🎯 Difficulté"])

# =====================================================================
# Onglet 1 : comparaison des deux langues de consigne
# =====================================================================
with tab1:
    st.subheader("Quelle langue de consigne donne les meilleurs résultats ?")

    rows = []
    for lang, g in p.groupby("langue"):
        acc = wavg(g, "accuracy_pct")
        n = int(g["nb_answers"].sum())
        rows.append({
            "langue": lang,
            "nb_answers": n,
            "accuracy_pct": acc,
            "ci": ci95(acc, n),
            "valid_format_pct": wavg(g, "valid_format_pct"),
            "avg_response_time": wavg(g, "avg_response_time"),
        })
    lang_df = pd.DataFrame(rows)

    # Une carte par langue
    cols = st.columns(len(lang_df))
    for col, r in zip(cols, lang_df.itertuples()):
        color = COLORS.get(r.langue, "#888888")
        col.markdown(
            f"""
            <div class="card" style="--c:{color}">
              <h3>{r.langue}</h3>
              <div class="big">{r.accuracy_pct:.1f} %</div>
              <div class="sub">de bonnes réponses (± {r.ci:.1f} pts)</div>
              <div class="sub">Format respecté : {r.valid_format_pct:.1f} %</div>
              <div class="sub">Temps moyen : {r.avg_response_time:.1f} s</div>
              <div class="sub">{r.nb_answers} réponses</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Écart entre les deux langues
    if len(lang_df) == 2:
        a, b = lang_df.iloc[0], lang_df.iloc[1]
        gap = a["accuracy_pct"] - b["accuracy_pct"]
        margin = np.sqrt(a["ci"] ** 2 + b["ci"] ** 2)
        verdict = "significatif" if abs(gap) > margin else "non significatif"
        st.info(f"Écart {a['langue']} − {b['langue']} : **{gap:+.1f} points** "
                f"(marge d'erreur ≈ ± {margin:.1f}). Écart **{verdict}** (approximation à 95 %).")

    st.write("")
    g1, g2 = st.columns(2)

    fig = px.bar(lang_df, x="langue", y="accuracy_pct", color="langue", error_y="ci",
                 text=lang_df["accuracy_pct"].round(1).astype(str) + " %",
                 color_discrete_map=COLORS,
                 labels={"accuracy_pct": "Bonnes réponses (%)", "langue": ""},
                 title="Bonnes réponses par langue")
    fig.add_hline(y=chance, line_dash="dash", annotation_text=f"hasard ({chance:.0f} %)")
    fig.update_layout(showlegend=False, yaxis_range=[0, 100])
    g1.plotly_chart(fig, use_container_width=True)

    fig = px.bar(lang_df, x="langue", y="avg_response_time", color="langue",
                 text=lang_df["avg_response_time"].round(2).astype(str) + " s",
                 color_discrete_map=COLORS,
                 labels={"avg_response_time": "Secondes par réponse", "langue": ""},
                 title="Temps de réponse moyen")
    fig.update_layout(showlegend=False)
    g2.plotly_chart(fig, use_container_width=True)

    with st.expander("Voir les données détaillées"):
        st.dataframe(p.drop(columns="langue"), use_container_width=True, hide_index=True)

# =====================================================================
# Onglet 2 : catégories
# =====================================================================
with tab2:
    st.subheader("Dans quelles catégories le modèle est-il le plus fort ?")
    cat = (
        c.assign(correct=c["accuracy_pct"] * c["nb_answers"])
        .groupby(["category", "langue"], as_index=False)[["correct", "nb_answers"]].sum()
    )
    cat["accuracy_pct"] = (cat["correct"] / cat["nb_answers"]).round(1)
    order = cat.groupby("category").apply(
        lambda g: (g["correct"].sum() / g["nb_answers"].sum()), include_groups=False
    ).sort_values().index.tolist()
    fig = px.bar(cat, x="accuracy_pct", y="category", color="langue", orientation="h",
                 barmode="group", color_discrete_map=COLORS, hover_data=["nb_answers"],
                 category_orders={"category": order},
                 labels={"accuracy_pct": "Bonnes réponses (%)", "category": "", "langue": "Consigne"})
    fig.update_layout(height=max(450, 45 * len(order)))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Peu de réponses par catégorie = score peu fiable (voir nb_answers au survol).")

# =====================================================================
# Onglet 3 : difficulté et type de question
# =====================================================================
with tab3:
    st.subheader("La difficulté et le type de question changent-ils le score ?")
    diff = (
        d.assign(correct=d["accuracy_pct"] * d["nb_answers"])
        .groupby(["difficulty", "question_type", "langue"], as_index=False)[["correct", "nb_answers"]].sum()
    )
    diff["accuracy_pct"] = (diff["correct"] / diff["nb_answers"]).round(1)
    fig = px.bar(diff, x="difficulty", y="accuracy_pct", color="langue", barmode="group",
                 facet_col="question_type", color_discrete_map=COLORS,
                 category_orders={"difficulty": ["easy", "medium", "hard"]},
                 hover_data=["nb_answers"],
                 labels={"accuracy_pct": "Bonnes réponses (%)", "difficulty": "Difficulté",
                         "langue": "Consigne", "question_type": "Type"})
    fig.update_layout(yaxis_range=[0, 100])
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Voir les données détaillées"):
        st.dataframe(diff.drop(columns="correct"), use_container_width=True, hide_index=True)