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

# Libellé affiché pour chaque prompt_id
LANG = {
    "p1_english": "Encodé EN",
    "p2_français": "Encodé FR",
    "p3_libre": "Libre",
}
COLORS = {
    "Encodé EN": "#4C78A8",
    "Encodé FR": "#F58518",
    "Libre": "#54A24B",
}

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
    if "prompt_id" in df.columns:
        df["langue"] = df["prompt_id"].map(lambda x: LANG.get(x, x))
    return df


def wavg(df: pd.DataFrame, col: str, w: str = "nb_answers") -> float:
    """Moyenne pondérée par le nombre de réponses."""
    return (df[col] * df[w]).sum() / df[w].sum()


def ci95(acc_pct: float, n: int) -> float:
    """Marge d'erreur à 95 % (en points) d'un pourcentage."""
    p = acc_pct / 100
    return 1.96 * np.sqrt(p * (1 - p) / max(n, 1)) * 100


def explain(question: str, mart: str, how: str, notes: list[str]) -> None:
    """Bloc d'explication commun à chaque onglet."""
    st.markdown(f"**Question métier :** {question}")
    st.caption(f"Table gold utilisée : `main_mart.{mart}`")
    st.info(f"**Comment lire :** {how}")
    with st.expander("Nuances à connaître", expanded=True):
        st.markdown("\n".join(f"- {n}" for n in notes))


# --- Chargement des marts ---
try:
    by_prompt = load("accuracy_by_prompt")
    by_category = load("accuracy_by_category")
    by_difficulty = load("accuracy_by_difficulty")
    run_summary = load("run_summary")
    time_df = load("response_time_analysis")
    consistency = load("prompt_consistency")
except Exception as e:
    st.error(f"Impossible de lire la base gold : {e}\nLancez d'abord `dbt run`.")
    st.stop()

st.title("📊 Benchmark d'un LLM local : culture générale")
st.caption("Encodé : les choix sont encodés A, B, C, D et le modèle répond par une lettre. "
           "Libre : aucun choix, le modèle répond avec ses propres mots. "
           "EN / FR : langue de la consigne.")

# --- Filtres (barre latérale) ---
st.sidebar.header("Filtres")
all_models = sorted(by_prompt["model"].unique())
all_langs = sorted(by_prompt["langue"].unique())
models = st.sidebar.multiselect("Modèle", all_models, default=all_models)
langs = st.sidebar.multiselect("Prompt", all_langs, default=all_langs)


def filt(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["model"].isin(models) & df["langue"].isin(langs)]


p, c, d = filt(by_prompt), filt(by_category), filt(by_difficulty)
sm, t = filt(run_summary), filt(time_df)
if p.empty or sm.empty:
    st.warning("Aucune donnée pour ces filtres.")
    st.stop()

# Niveau du hasard : 25 % en QCM (4 choix), 50 % en vrai/faux
n_by_type = d.groupby("question_type")["nb_answers"].sum()
chance = (n_by_type.get("multiple", 0) * 25 + n_by_type.get("boolean", 0) * 50) / max(n_by_type.sum(), 1)

# Questions traitées (même échantillon pour tous les prompts : on prend le maximum)
n_questions = int(sm["nb_questions"].max())
total_questions = int(sm["total_questions"].iloc[0])

# Avertissement si prompts encodés et libre sont mélangés
mixed = "Libre" in langs and any(x.startswith("Encodé") for x in langs)
if mixed:
    st.warning("Les prompts **encodés** (avec choix) et **libre** (sans choix) sont mélangés dans les "
               "moyennes globales, alors que ce sont deux tâches de difficulté différente. "
               "Pour comparer proprement, filtrez par prompt dans la barre latérale.")

# --- Indicateurs globaux ---
k0, k1, k2, k3, k4, k5 = st.columns(6)
k0.metric("Questions traitées", f"{n_questions:,}",
          help=f"Échantillon aléatoire sur {total_questions:,} questions dans le dataset.")
k1.metric("Réponses", f"{int(p['nb_answers'].sum()):,}",
          help="Une question posée avec 3 prompts donne 3 réponses.")
k2.metric("Bonnes réponses", f"{wavg(p, 'accuracy_pct'):.1f} %")
k3.metric("Niveau du hasard", f"{chance:.1f} %",
          help="Score d'un joueur qui répondrait au hasard : 25 % en QCM (4 choix), 50 % en vrai/faux. "
               "Valable pour les prompts encodés. Pour le prompt libre, le hasard est proche de 0 %.")
k4.metric("Format respecté", f"{wavg(p, 'valid_format_pct'):.1f} %",
          help="Part des réponses exploitables (une lettre pour les prompts encodés, une réponse non vide pour le libre).")
k5.metric("Temps moyen", f"{wavg(p, 'avg_response_time'):.1f} s")
st.caption(f"{n_questions:,} questions sur {total_questions:,} "
           f"({100 * n_questions / total_questions:.1f} % du dataset), "
           f"{int(sm['nb_calls'].sum()):,} appels au modèle, "
           f"{int(sm['nb_errors'].sum()):,} erreurs techniques (exclues du score).")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["🔤 Prompts", "📚 Catégories", "🎯 Difficulté", "⏱️ Temps", "🔁 Robustesse", "ℹ️ Méthode"]
)

# =====================================================================
# Onglet 1 : comparaison des prompts
# =====================================================================
with tab1:
    st.subheader("Quelle formulation du prompt donne les meilleurs résultats ?")
    explain(
        "Quel prompt donne les meilleurs résultats, et le modèle suit-il le format demandé ?",
        "accuracy_by_prompt",
        "chaque carte donne le taux de bonnes réponses d'un prompt, avec sa marge d'erreur (± points). "
        "Un écart entre deux prompts n'est réel que s'il dépasse ces marges.",
        [
            "**Encodé EN contre Encodé FR** : même tâche, seule la langue de la consigne change. "
            "Cette comparaison isole l'effet de la langue.",
            "**Encodé contre Libre** : l'encodage change la tâche. Avec les choix, le modèle *reconnaît* la bonne "
            "réponse ; en libre, il doit la *retrouver*. Un score libre plus bas montre l'aide apportée par les "
            "choix, pas forcément un prompt moins bon.",
            "**Le hasard** (ligne pointillée) ne concerne que les prompts encodés : 25 % en QCM, 50 % en vrai/faux.",
            "**Correction du prompt libre** : la bonne réponse doit apparaître comme mot entier dans la réponse "
            "(vrai/faux : réponse exactement « true » ou « false »). Une réponse juste mais reformulée "
            "(« Da Vinci » pour « Leonardo da Vinci ») est comptée fausse : le score libre est plutôt sous-estimé.",
            "**Format respecté** : un prompt peut avoir un score faible parce que le modèle se trompe, "
            "ou parce qu'il ne suit pas la consigne. Les deux se lisent séparément.",
            "**Marge d'erreur** : avec peu de questions, elle est large. La marge vient de la taille de l'échantillon, "
            "pas d'un défaut du modèle.",
        ],
    )

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

    # Une carte par prompt
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

    # Écart entre les deux prompts encodés (effet de la langue de la consigne)
    by_name = lang_df.set_index("langue")
    if {"Encodé EN", "Encodé FR"} <= set(by_name.index):
        en, fr = by_name.loc["Encodé EN"], by_name.loc["Encodé FR"]
        gap = en["accuracy_pct"] - fr["accuracy_pct"]
        margin = np.sqrt(en["ci"] ** 2 + fr["ci"] ** 2)
        verdict = "significatif" if abs(gap) > margin else "non significatif"
        st.info(f"Effet de la langue (Encodé EN − Encodé FR) : **{gap:+.1f} points** "
                f"(marge d'erreur ≈ ± {margin:.1f}). Écart **{verdict}** (approximation à 95 %).")

    st.write("")
    g1, g2 = st.columns(2)

    fig = px.bar(lang_df, x="langue", y="accuracy_pct", color="langue", error_y="ci",
                 text=lang_df["accuracy_pct"].round(1).astype(str) + " %",
                 color_discrete_map=COLORS,
                 labels={"accuracy_pct": "Bonnes réponses (%)", "langue": ""},
                 title="Bonnes réponses par prompt")
    fig.add_hline(y=chance, line_dash="dash",
                  annotation_text=f"hasard, prompts encodés ({chance:.0f} %)")
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
    explain(
        "Dans quelles catégories le modèle est-il le plus fort ou le plus faible ?",
        "accuracy_by_category",
        "chaque barre est le taux de bonnes réponses dans une catégorie. Les catégories sont triées "
        "de la plus faible (en haut) à la plus forte (en bas).",
        [
            "**Peu de réponses par catégorie** : avec un échantillon, chaque catégorie ne compte que "
            "quelques dizaines de réponses. Les écarts entre catégories proches ne sont pas fiables "
            "(le nombre de réponses s'affiche au survol).",
            "**Toutes les catégories n'ont pas la même difficulté** : une catégorie peut sembler faible "
            "simplement parce qu'elle contient plus de questions difficiles.",
            "**Mélange de prompts** : si les prompts encodés et libre sont tous sélectionnés, la moyenne "
            "par catégorie mélange deux tâches. Filtrez par prompt pour comparer proprement.",
        ],
    )
    cat = (
        c.assign(correct=c["accuracy_pct"] * c["nb_answers"])
        .groupby(["category", "langue"], as_index=False)[["correct", "nb_answers"]].sum()
    )
    cat["accuracy_pct"] = (cat["correct"] / cat["nb_answers"]).round(1)
    # Catégories triées par score global
    tot = cat.groupby("category")[["correct", "nb_answers"]].sum()
    order = (tot["correct"] / tot["nb_answers"]).sort_values().index.tolist()
    fig = px.bar(cat, x="accuracy_pct", y="category", color="langue", orientation="h",
                 barmode="group", color_discrete_map=COLORS, hover_data=["nb_answers"],
                 category_orders={"category": order},
                 labels={"accuracy_pct": "Bonnes réponses (%)", "category": "", "langue": "Prompt"})
    fig.update_layout(height=max(450, 55 * len(order)))
    st.plotly_chart(fig, use_container_width=True)

# =====================================================================
# Onglet 3 : difficulté et type de question
# =====================================================================
with tab3:
    st.subheader("La difficulté et le type de question changent-ils le score ?")
    explain(
        "La difficulté d'une question et son type (QCM ou vrai/faux) changent-ils le score du modèle ?",
        "accuracy_by_difficulty",
        "chaque groupe de barres correspond à un niveau de difficulté (facile, moyen, difficile), "
        "séparé en deux graphiques : QCM (`multiple`) et vrai/faux (`boolean`). "
        "Un modèle qui comprend les questions doit mieux réussir les faciles que les difficiles.",
        [
            "**Le hasard n'est pas le même** : 25 % en QCM (4 choix) mais 50 % en vrai/faux. "
            "Un score de 55 % est bon en QCM, mais proche du hasard en vrai/faux.",
            "**Difficulté fixée par OpenTDB** : le niveau (easy, medium, hard) est donné par les contributeurs "
            "de la base, il n'est pas mesuré par notre benchmark.",
            "**Peu de réponses par groupe** : les vrai/faux sont environ 15 % des questions, donc leurs "
            "barres reposent sur peu de réponses (voir le nombre de réponses au survol).",
        ],
    )
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
                         "langue": "Prompt", "question_type": "Type"})
    fig.update_layout(yaxis_range=[0, 100])
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("Voir les données détaillées"):
        st.dataframe(diff.drop(columns="correct"), use_container_width=True, hide_index=True)

# =====================================================================
# Onglet 4 : temps de réponse
# =====================================================================
with tab4:
    st.subheader("Le modèle met-il plus de temps quand il se trompe ou quand la question est difficile ?")
    explain(
        "Le temps de réponse dépend-il de la réussite et de la difficulté de la question ?",
        "response_time_analysis",
        "le graphique de gauche compare le temps moyen des bonnes et des mauvaises réponses ; "
        "celui de droite le temps moyen selon la difficulté. Les temps sont en secondes par réponse.",
        [
            "**Le temps dépend de la machine** : processeur, autres applications ouvertes, chargement du modèle. "
            "Les valeurs ne sont comparables qu'au sein de ce benchmark, pas avec d'autres ordinateurs.",
            "**Le prompt libre est plus long** : le modèle écrit plus de mots qu'une simple lettre. "
            "Comparez les temps au sein d'un même type de prompt.",
            "**Un écart de temps n'est pas une preuve** : un modèle peut mettre le même temps pour toutes les "
            "questions, car sa vitesse dépend surtout du nombre de mots générés.",
        ],
    )
    t = t.assign(w=t["avg_response_time"] * t["nb_answers"])

    by_result = t.groupby(["langue", "ai_correct"], as_index=False)[["w", "nb_answers"]].sum()
    by_result["avg_response_time"] = (by_result["w"] / by_result["nb_answers"]).round(2)
    by_result["Résultat"] = by_result["ai_correct"].map({True: "Bonne réponse", False: "Mauvaise réponse"})

    by_diff_t = t.groupby(["difficulty", "langue"], as_index=False)[["w", "nb_answers"]].sum()
    by_diff_t["avg_response_time"] = (by_diff_t["w"] / by_diff_t["nb_answers"]).round(2)

    c1, c2 = st.columns(2)
    fig = px.bar(by_result, x="langue", y="avg_response_time", color="Résultat", barmode="group",
                 hover_data=["nb_answers"], title="Temps moyen selon le résultat",
                 labels={"avg_response_time": "Secondes par réponse", "langue": "Prompt"})
    c1.plotly_chart(fig, use_container_width=True)

    fig = px.bar(by_diff_t, x="difficulty", y="avg_response_time", color="langue", barmode="group",
                 color_discrete_map=COLORS, hover_data=["nb_answers"],
                 category_orders={"difficulty": ["easy", "medium", "hard"]},
                 title="Temps moyen selon la difficulté",
                 labels={"avg_response_time": "Secondes par réponse", "difficulty": "Difficulté",
                         "langue": "Prompt"})
    c2.plotly_chart(fig, use_container_width=True)

# =====================================================================
# Onglet 5 : robustesse entre les deux langues de consigne
# =====================================================================
with tab5:
    st.subheader("Le modèle donne-t-il le même résultat quand on change la langue de la consigne ?")
    explain(
        "Le modèle réagit-il de la même façon à une consigne en anglais et à la même consigne en français ?",
        "prompt_consistency",
        "pour chaque question, on compare le résultat avec la consigne EN et avec la consigne FR : "
        "juste dans les deux, faux dans les deux, ou juste dans une seule langue. "
        "Les barres montrent la part de chaque cas.",
        [
            "**Différent de l'onglet Prompts** : l'onglet Prompts compare les *scores moyens* de chaque prompt. "
            "Ici on compare les résultats *question par question*. Deux prompts peuvent avoir le même score "
            "sans réussir les mêmes questions.",
            "**« Même résultat » ne veut pas dire « bon »** : un modèle qui se trompe tout le temps dans les deux "
            "langues serait très cohérent. Regardez aussi la part « Juste dans les 2 langues ».",
            "**Le hasard crée du désaccord** : avec 4 choix, un modèle incertain peut tomber juste dans une "
            "langue et faux dans l'autre sans que la langue joue un rôle.",
            "**Seuls les deux prompts encodés sont comparés**, sur les mêmes questions. "
            "Le prompt libre n'entre pas dans cette analyse.",
        ],
    )
    cs = consistency[consistency["model"].isin(models)]
    if cs.empty:
        st.warning("Aucune donnée de robustesse pour ces filtres.")
    else:
        n_q = int(cs["nb_questions"].sum())
        r1, r2 = st.columns(2)
        r1.metric("Questions comparées (Encodé EN et FR)", f"{n_q:,}")
        r2.metric("Même résultat dans les 2 langues",
                  f"{wavg(cs, 'same_result_pct', 'nb_questions'):.1f} %",
                  help="Part des questions réussies dans les deux langues, ou ratées dans les deux.")

        cases = {
            "both_correct_pct": "Juste dans les 2 langues",
            "both_wrong_pct": "Faux dans les 2 langues",
            "only_en_correct_pct": "Juste en EN seulement",
            "only_fr_correct_pct": "Juste en FR seulement",
        }
        long = cs.melt(id_vars=["model", "nb_questions"], value_vars=list(cases),
                       var_name="cas", value_name="pct")
        long["cas"] = long["cas"].map(cases)
        fig = px.bar(long, x="model", y="pct", color="cas", barmode="stack", text="pct",
                     hover_data=["nb_questions"],
                     color_discrete_map={
                         "Juste dans les 2 langues": "#54A24B",
                         "Faux dans les 2 langues": "#E45756",
                         "Juste en EN seulement": "#4C78A8",
                         "Juste en FR seulement": "#F58518",
                     },
                     labels={"pct": "Part des questions (%)", "model": "Modèle", "cas": "Cas"})
        fig.update_traces(texttemplate="%{text:.1f}")
        fig.update_layout(yaxis_range=[0, 100])
        st.plotly_chart(fig, use_container_width=True)

# =====================================================================
# Onglet 6 : méthode
# =====================================================================
with tab6:
    st.subheader("Méthode : comment lire ce benchmark")

    st.markdown("### Pipeline")
    st.markdown(
        "**Bronze** (questions OpenTDB brutes, CSV) → **Silver** (questions nettoyées et réponses du modèle, Parquet) "
        "→ **Gold** (tables métier calculées avec dbt, DuckDB) → **Dashboard** (cette page)."
    )

    st.markdown("### Les trois prompts")
    st.markdown(
        """
| Libellé | Choix proposés | Réponse attendue | Langue de la consigne | Correction |
|---|---|---|---|---|
| Encodé EN | Oui, encodés A, B, C, D | Une lettre | Anglais | Lettre identique à la bonne lettre |
| Encodé FR | Oui, encodés A, B, C, D | Une lettre | Français | Lettre identique à la bonne lettre |
| Libre | Non | Quelques mots | Anglais | Bonne réponse trouvée comme mot entier dans la réponse (vrai/faux : exactement « true » ou « false ») |
        """
    )
    st.markdown(
        "- **Encodé EN contre FR** mesure l'effet de la **langue**.\n"
        "- **Encodé contre Libre** mesure l'effet de l'**encodage** (reconnaître contre retrouver la réponse).\n"
        "- Les questions restent toujours en anglais, seule la consigne change de langue."
    )

    st.markdown("### Définitions")
    st.markdown(
        "- **Bonne réponse** : la réponse du modèle correspond à la bonne réponse selon la règle de correction ci-dessus.\n"
        "- **Format respecté** : la réponse est exploitable (une lettre A à H pour les prompts encodés, "
        "une réponse non vide pour le libre). Une réponse hors format compte comme fausse.\n"
        "- **Erreur technique** : l'appel au modèle a échoué (serveur, délai). Ces appels sont exclus des scores.\n"
        "- **Niveau du hasard** : 25 % en QCM (4 choix), 50 % en vrai/faux.\n"
        "- **Marge d'erreur (± points)** : intervalle à 95 % lié à la taille de l'échantillon. "
        "Un écart plus petit que la marge peut venir du hasard de l'échantillon."
    )

    st.markdown("### Les tables métier (gold)")
    st.markdown(
        """
| Table | Question métier |
|---|---|
| `accuracy_by_prompt` | Quel prompt donne les meilleurs résultats, et le modèle suit-il le format demandé ? |
| `accuracy_by_category` | Dans quelles catégories le modèle est-il le plus fort ou le plus faible ? |
| `accuracy_by_difficulty` | La difficulté et le type de question changent-ils le score ? |
| `response_time_analysis` | Le temps de réponse dépend-il de la réussite et de la difficulté ? |
| `prompt_consistency` | Le modèle réagit-il de la même façon à une consigne en anglais et en français ? |
| `run_summary` | Combien de questions, d'appels et d'erreurs dans le run ? |
        """
    )

    st.markdown("### Limites")
    st.markdown(
        "- Les résultats portent sur un **échantillon aléatoire** de questions (voir « Questions traitées »), "
        "pas sur tout le dataset.\n"
        "- **Un seul petit modèle** (1 milliard de paramètres) est testé.\n"
        "- Donner les choix rend la tâche plus facile qu'une réponse libre.\n"
        "- La correction du prompt libre est approximative : une réponse juste mais reformulée est comptée fausse.\n"
        "- Les temps de réponse dépendent de la machine utilisée."
    )