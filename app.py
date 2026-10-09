import os
import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

# -----------------------------------------------------------------------------
# CONFIGURATION DE LA PAGE STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Benchmark LLM - OpenTDB Analytics",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Chemin absolu dynamique vers la base DuckDB (Gold Layer)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "3_gold", "analytics.duckdb")

# -----------------------------------------------------------------------------
# FONCTION DE CHARGEMENT DES DONNÉES (couche gold uniquement)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)  # cache court : les nouvelles données apparaissent vite
def load_table(table: str) -> pd.DataFrame:
    """Lit une table de la couche gold (construite par dbt)."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = duckdb.connect(DB_PATH, read_only=True)
    try:
        return conn.execute(f"SELECT * FROM {table}").fetchdf()
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()  # libère le fichier pour dbt

df_raw = load_table("mart_questions_detail")

if df_raw.empty:
    st.error("⚠️ Aucune donnée disponible. Exécutez d'abord `python scripts/02_run_inference.py` puis, depuis `dbt_project`, `dbt run --profiles-dir .`.")
    st.stop()

# -----------------------------------------------------------------------------
# BARRE LATÉRALE - FILTRES INTERACTIFS
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 Filtres du Benchmark")

# Indication de la méthode de prompting
prompt_type = df_raw["ai_prompt_type"].iloc[0] if "ai_prompt_type" in df_raw.columns else "n/a"
st.sidebar.info(f"💡 **Méthode d'Inférence :** Few-Shot Prompting (exemples guidés en anglais)\n\nPrompt : `{prompt_type}`")
st.sidebar.caption("Données lues dans la couche gold (DuckDB, construite par dbt).")

# Filtre Modèle LLM
available_models = df_raw["ai_model"].unique().tolist() if "ai_model" in df_raw.columns else ["N/A"]
selected_model = st.sidebar.selectbox("Modèle LLM", available_models)

# Filtre Catégorie
categories = ["Toutes"] + sorted(df_raw["category"].dropna().unique().tolist())
selected_category = st.sidebar.selectbox("Catégorie", categories)

# Filtre Difficulté
difficulties = ["Toutes"] + sorted(df_raw["difficulty"].dropna().unique().tolist())
selected_difficulty = st.sidebar.selectbox("Difficulté", difficulties)

# Application des filtres
df_filtered = df_raw.copy()
if selected_model != "N/A":
    df_filtered = df_filtered[df_filtered["ai_model"] == selected_model]
if selected_category != "Toutes":
    df_filtered = df_filtered[df_filtered["category"] == selected_category]
if selected_difficulty != "Toutes":
    df_filtered = df_filtered[df_filtered["difficulty"] == selected_difficulty]

# -----------------------------------------------------------------------------
# EN-TÊTE PRINCIPAL
# -----------------------------------------------------------------------------
st.title("📊 Benchmark & Analyse Approfondie des LLMs")
st.markdown(
    f"Analyse des performances du modèle **{selected_model}** évalué via la méthode **Few-Shot Prompting** sur **OpenTDB**."
)

st.caption("🚀 **Méthodologie :** Envoi d'un System Prompt enrichi par 2 exemples concrets (Few-Shot) pour contraindre le format et maximiser la précision.")
st.markdown("---")

# -----------------------------------------------------------------------------
# BLOC 1 : CARTE DE KPIS GLOBAUX
# -----------------------------------------------------------------------------
total_questions = len(df_filtered)
correct_count = df_filtered["ai_correct"].sum() if "ai_correct" in df_filtered.columns else 0
accuracy_pct = (correct_count / total_questions * 100) if total_questions > 0 else 0.0

avg_latency = df_filtered["response_time"].mean() if "response_time" in df_filtered.columns else 0.0
hallu_count = df_filtered["is_hallucination"].sum() if "is_hallucination" in df_filtered.columns else 0
hallu_pct = (hallu_count / total_questions * 100) if total_questions > 0 else 0.0
total_kwh = df_filtered["estimated_cpu_kwh"].sum() if "estimated_cpu_kwh" in df_filtered.columns else 0.0

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Questions Analysées", f"{total_questions:,}")
col2.metric("Précision Globale", f"{accuracy_pct:.2f} %")
n_multiple = (df_filtered["type"] == "multiple").sum()
n_boolean = (df_filtered["type"] == "boolean").sum()
chance_pct = (n_multiple * 25 + n_boolean * 50) / max(n_multiple + n_boolean, 1)
col6.metric("Niveau du hasard", f"{chance_pct:.1f} %", help="25 % en QCM (4 choix), 50 % en vrai/faux.")
col3.metric("Temps Moyen / Q", f"{avg_latency:.2f} s")
col4.metric("Taux d'Hallucination", f"{hallu_pct:.2f} %")
col5.metric("Énergie CPU (i5)", f"{total_kwh:.6f} kWh")

st.markdown("---")

# -----------------------------------------------------------------------------
# BLOC 2 : ANALYSE DES ERREURS & DE LA QUALITÉ DES RÉPONSES
# -----------------------------------------------------------------------------
st.header("🎯 Analyse Détaillée de la Qualité des Réponses (Few-Shot)")

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Répartition des Types d'Erreurs")
    if "error_type" in df_filtered.columns:
        error_df = df_filtered["error_type"].value_counts().reset_index()
        error_df.columns = ["Type d'Erreur", "Nombre"]
        
        labels_map = {
            "correct": "Bonne Réponse",
            "plausible_wrong_choice": "Mauvais Choix (Plausible)",
            "hallucination_out_of_options": "Hallucination (Hors-Options)"
        }
        error_df["Type d'Erreur"] = error_df["Type d'Erreur"].map(labels_map).fillna(error_df["Type d'Erreur"])
        
        fig_pie = px.pie(
            error_df,
            names="Type d'Erreur",
            values="Nombre",
            color="Type d'Erreur",
            color_discrete_map={
                "Bonne Réponse": "#2ca02c",
                "Mauvais Choix (Plausible)": "#ff7f0e",
                "Hallucination (Hors-Options)": "#d62728"
            },
            hole=0.4
        )
        fig_pie.update_traces(textinfo='percent+label')
        st.plotly_chart(fig_pie, use_container_width=True)

with col_right:
    st.subheader("Précision par Niveau de Difficulté")
    if "difficulty" in df_filtered.columns and "ai_correct" in df_filtered.columns:
        diff_df = df_filtered.groupby("difficulty")["ai_correct"].agg(
            total="count",
            correct="sum"
        ).reset_index()
        diff_df["accuracy_pct"] = (diff_df["correct"] / diff_df["total"]) * 100
        
        fig_diff = px.bar(
            diff_df,
            x="difficulty",
            y="accuracy_pct",
            text="accuracy_pct",
            color="difficulty",
            category_orders={"difficulty": ["easy", "medium", "hard"]},
            labels={"accuracy_pct": "Précision (%)", "difficulty": "Difficulté"},
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        fig_diff.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig_diff.update_layout(yaxis_range=[0, 105])
        st.plotly_chart(fig_diff, use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# BLOC 2 BIS : TYPE DE QUESTION ET NIVEAU DU HASARD
# -----------------------------------------------------------------------------
st.header("🎲 Type de question : QCM contre vrai/faux")
if "type" in df_filtered.columns and not df_filtered.empty:
    type_df = df_filtered.groupby("type")["ai_correct"].agg(total="count", correct="sum").reset_index()
    type_df["accuracy_pct"] = type_df["correct"] / type_df["total"] * 100
    type_df["chance_pct"] = type_df["type"].map({"multiple": 25.0, "boolean": 50.0})
    fig_type = px.bar(
        type_df, x="type", y="accuracy_pct", text="accuracy_pct",
        labels={"type": "Type de question", "accuracy_pct": "Précision (%)"},
        color_discrete_sequence=["#1f77b4"],
    )
    fig_type.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_type.add_scatter(x=type_df["type"], y=type_df["chance_pct"], mode="markers",
                         marker=dict(symbol="line-ew", size=60, line=dict(width=3, color="#d62728")),
                         name="Niveau du hasard")
    fig_type.update_layout(yaxis_range=[0, 105])
    st.plotly_chart(fig_type, use_container_width=True)
    st.caption("Le trait rouge est le score qu'obtiendrait un joueur qui répond au hasard. "
               "Un score sous le trait (vrai/faux) révèle un biais du modèle, par exemple répondre presque toujours « False ».")

st.markdown("---")

# -----------------------------------------------------------------------------
# BLOC 3 : PERFORMANCE PAR CATÉGORIE (GRADUATION & COULEUR CORRIGÉES)
# -----------------------------------------------------------------------------
st.header("📚 Performance par Catégorie de Culture Générale")

if "category" in df_filtered.columns and "ai_correct" in df_filtered.columns:
    cat_df = df_filtered.groupby("category").agg(
        total_q=("ai_correct", "count"),
        accuracy_pct=("ai_correct", lambda x: (x.sum() / x.count()) * 100),
        avg_time=("response_time", "mean")
    ).reset_index().sort_values(by="accuracy_pct", ascending=True)

    # Graphique horizontal avec graduation exacte de 0 à 100% et échelle de couleur cohérente
    fig_cat = px.bar(
        cat_df,
        x="accuracy_pct",
        y="category",
        orientation="h",
        text="accuracy_pct",
        color="accuracy_pct",  # La couleur reflète directement la précision (%)
        color_continuous_scale="RdYlGn",  # Rouge (faible) vers Vert (élevé)
        range_color=[0, 100],  # Fixe l'échelle de couleurs de 0 à 100%
        labels={
            "accuracy_pct": "Précision (%)",
            "category": "Catégorie",
            "avg_time": "Temps Moyen (s)"
        }
    )
    
    fig_cat.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
    
    # Configuration de l'axe X (Graduation stricte de 0 à 100% avec pas de 10%)
    fig_cat.update_layout(
        height=550,
        xaxis=dict(
            range=[0, 105],
            dtick=10,
            title="Précision (%)"
        ),
        coloraxis_colorbar=dict(title="Précision (%)")
    )
    st.plotly_chart(fig_cat, use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# BLOC 4 : LATENCE CPU vs LONGUEUR DE LA QUESTION (FINOPS / INFRA)
# -----------------------------------------------------------------------------
st.header("⚡ Latence & Empreinte Énergétique (Analyse CPU Core i5)")

col_lat1, col_lat2 = st.columns(2)

with col_lat1:
    st.subheader("Impact de la Longueur du Prompt sur la Latence")
    if "prompt_length_chars" in df_filtered.columns and "response_time" in df_filtered.columns:
        fig_scatter = px.scatter(
            df_filtered,
            x="prompt_length_chars",
            y="response_time",
            color="ai_correct",
            color_discrete_map={True: "#2ca02c", False: "#d62728"},
            labels={
                "prompt_length_chars": "Longueur du Prompt (Caractères)",
                "response_time": "Temps de Réponse (s)",
                "ai_correct": "Correct"
            },
            hover_data=["question", "ai_answer"]
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

with col_lat2:
    st.subheader("Distribution du Temps de Réponse (Seconds)")
    if "response_time" in df_filtered.columns:
        fig_hist = px.histogram(
            df_filtered,
            x="response_time",
            nbins=20,
            color_discrete_sequence=["#1f77b4"],
            labels={"response_time": "Temps de Réponse (s)"}
        )
        st.plotly_chart(fig_hist, use_container_width=True)

st.markdown("---")

# -----------------------------------------------------------------------------
# BLOC 5 : EXPLORATEUR DE DONNÉES BRUTES
# -----------------------------------------------------------------------------
st.header("🔎 Explorateur des Réponses Few-Shot")

tab_all, tab_hallu, tab_errors = st.tabs(["Toutes les questions", "Focus Hallucinations", "Erreurs Plausibles"])

display_cols = [
    "question", "correct_answer", "ai_answer", "ai_correct", 
    "error_type", "response_time", "category", "difficulty"
]
existing_cols = [col for col in display_cols if col in df_filtered.columns]

with tab_all:
    st.dataframe(df_filtered[existing_cols], use_container_width=True)

with tab_hallu:
    df_hallu = df_filtered[df_filtered["error_type"] == "hallucination_out_of_options"] if "error_type" in df_filtered.columns else pd.DataFrame()
    if not df_hallu.empty:
        st.warning(f"Nombre d'hallucinations détectées : {len(df_hallu)}")
        st.dataframe(df_hallu[existing_cols], use_container_width=True)
    else:
        st.success("Aucune hallucination détectée sur cet échantillon !")

with tab_errors:
    df_err = df_filtered[df_filtered["error_type"] == "plausible_wrong_choice"] if "error_type" in df_filtered.columns else pd.DataFrame()
    if not df_err.empty:
        st.info(f"Nombre de mauvais choix plausibles : {len(df_err)}")
        st.dataframe(df_err[existing_cols], use_container_width=True)
    else:
        st.success("Aucune erreur plausible détectée !")