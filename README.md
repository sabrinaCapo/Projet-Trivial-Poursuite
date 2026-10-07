# Benchmark d'un LLM local sur des questions de culture générale

Pipeline de data engineering qui évalue un modèle d'IA local (LM Studio) sur le dataset Open Trivia Database (OpenTDB). Architecture en médaillon (bronze, silver, gold), transformations avec dbt et dashboard Streamlit.

**Auteurs** : _à compléter (noms du binôme)_
**Avancement** : bronze OK, silver OK, dbt OK, dashboard OK. Run final sur échantillon en cours, résultats à compléter.

---

## 1. Objectif

Mesurer les performances d'un modèle d'IA sur des questions de culture générale :
- taux de bonnes réponses global, par catégorie, par difficulté et type de question,
- temps de réponse,
- impact de la formulation du prompt (langue de la consigne),
- respect du format de réponse demandé.

## 2. Architecture

| Couche | Contenu | Format | Emplacement |
|---|---|---|---|
| Bronze | Questions brutes issues du scraping | CSV | `data/bronze/questions_raw.csv` |
| Silver | Questions nettoyées + réponses brutes du modèle | Parquet | `data/silver/questions_clean.parquet`, `data/silver/model_answers.parquet` |
| Gold | Tables métier (staging, intermediate, mart) | DuckDB | `data/gold/benchmark.duckdb` |

Lignage dbt : `staging -> intermediate -> mart`. Schémas DuckDB : `main_staging`, `main_intermediate`, `main_mart`.

```
data/        bronze, silver, gold
src/         scrap.py, build_silver.py, run_benchmark.py
dbt_project/ models/{staging, intermediate, marts}
app/         streamlit_app.py
```

## 3. Outils utilisés

| Outil | Rôle |
|---|---|
| Python 3.11 | Langage des scripts |
| requests, truststore | Appels à l'API OpenTDB (truststore : certificats du système, réseau avec interception HTTPS) |
| pandas, pyarrow | Nettoyage et fichiers Parquet |
| LM Studio | Exécute le modèle en local (serveur compatible OpenAI) |
| DuckDB | Base analytique (couche gold) et lecture des Parquet |
| dbt-core, dbt-duckdb | Transformations SQL, lignage, tests |
| Streamlit, Plotly | Dashboard interactif |

## 4. Installation

```bash
git clone https://github.com/sabrinaCapo/Projet-Trivial-Poursuite.git
cd Projet-Trivial-Poursuite
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt
```

LM Studio (https://lmstudio.ai) puis, dans un terminal :

```bash
lms get https://huggingface.co/lmstudio-community/Llama-3.2-1B-Instruct-GGUF
lms load llama-3.2-1b-instruct
lms server start
```

## 5. Exécution du pipeline

```bash
python src/scrap.py                       # bronze
python src/build_silver.py                # silver : questions
python src/run_benchmark.py --limit 500   # silver : réponses du modèle (0 = tout)

cd dbt_project
dbt run --profiles-dir .                  # gold
dbt test --profiles-dir .
dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .
cd ..

streamlit run app/streamlit_app.py        # dashboard
```

Pour mettre à jour le dashboard après un nouveau run : relancer `run_benchmark.py`, puis `dbt run`, puis recharger la page. Fermer le dashboard pendant `dbt run` (verrou DuckDB).

## 6. Méthodologie

### 6.1 Bronze : scraping
- API OpenTDB avec **session token** (aucun doublon, signal d'arrêt fiable).
- Lots de 50 questions, pause de 5,5 s entre appels (limite de l'API), gestion du rate limit.
- Encodage `url3986` puis décodage : évite les entités HTML (`&quot;`, `&#039;`).
- Fichier écrit en UTF-8, au fil de l'eau.

### 6.2 Silver : nettoyage des questions
- Suppression des espaces superflus, normalisation de `type` et `difficulty` en minuscules.
- `question_id` : hash SHA-1 du texte de la question (12 premiers caractères), stable d'une exécution à l'autre.
- Déduplication sur `question_id` (première occurrence conservée).
- Résultat : 5 250 lignes en bronze, 5 246 en silver (4 doublons retirés). 4 459 QCM et 787 vrai/faux ; 1 750 faciles, 2 400 moyennes, 1 096 difficiles.

### 6.3 Silver : enrichissement par le modèle
- Pour chaque question, la bonne et les mauvaises réponses sont mélangées (ordre stable par question) puis présentées en choix A, B, C, D.
- Le modèle ne répond que par une lettre (`max_tokens` = 16, `temperature` = 0).
- Deux prompts standardisés, identifiés par `prompt_id` : `p1_en_lettre` (consigne en anglais) et `p2_fr_lettre` (consigne en français). Les questions restent en anglais.
- Colonnes écrites : `question_id`, `model`, `prompt_id`, `correct_letter`, `ai_answer`, `response_time`, `error`.
- Les appels échoués sont enregistrés dans `error` (erreur technique) et exclus du score.
- Reprise automatique : les combinaisons déjà traitées sont ignorées.
- **Échantillon** : en raison du temps de réponse (environ 6,7 s par appel, soit environ 20 h pour les 5 246 questions avec 2 prompts), le run final porte sur un échantillon aléatoire reproductible (`random_state=42`) de _500 questions (à ajuster)_.

### 6.4 Gold : dbt

**Staging** (remise en forme, sans calcul)
- `stg_questions` : questions silver.
- `stg_model_answers` : réponses du modèle.

**Intermediate**
- `int_answers_scored` : jointure réponses et questions, exclusion des appels en erreur, extraction de la lettre répondue (`ai_letter`), puis :
  - `is_valid_format` : une lettre exploitable a été trouvée,
  - `ai_correct` : `ai_letter` égale `correct_letter` (faux si format invalide).
- Règle d'extraction volontairement stricte : une lettre A à H en majuscule, seule ou suivie de `.`, `:` ou `)`. Les phrases (par exemple « A cause de... ») ne sont pas comptées.

**Marts** (une question métier chacun)

| Table | Question métier |
|---|---|
| `accuracy_by_prompt` | Quel prompt donne les meilleures réponses, et le modèle suit-il le format demandé ? |
| `accuracy_by_category` | Dans quelles catégories le modèle est-il le plus fort ou le plus faible ? |
| `accuracy_by_difficulty` | La difficulté et le type de question changent-ils le score ? |

**Tests** (`dbt test`) : `question_id` unique et non nul, valeurs acceptées pour `difficulty` et `question_type`.

### 6.5 Dashboard Streamlit
- Lit les 3 marts en lecture seule (cache de 60 s).
- Filtres par modèle et par prompt.
- Indicateurs : nombre de réponses, bonnes réponses, niveau du hasard, format respecté, temps moyen.
- Trois onglets : prompts, catégories, difficulté et type de question.
- Les scores agrégés sont des moyennes pondérées par le nombre de réponses.

## 7. Résultats

**Test préliminaire (50 questions)**

| Prompt | Bonnes réponses | Format valide | Temps moyen |
|---|---|---|---|
| `p1_en_lettre` | 50,0 % | 100 % | 6,9 s |
| `p2_fr_lettre` | 48,0 % | 98 % | 6,5 s |

Le niveau du hasard est d'environ 29 % sur ce dataset (25 % en QCM, 50 % en vrai/faux). L'écart entre les deux prompts correspond à une seule question sur 50 : il n'est pas significatif.

**Run final** : _à compléter (taux global, par prompt, par catégorie, par difficulté, temps de réponse)._

## 8. Limites connues

- Scraping : 5 250 questions récupérées sur 5 299 annoncées par le site (environ 49 manquantes).
- Fournir les choix rend la tâche plus facile que la réponse libre : le hasard donne 25 % en QCM et 50 % en vrai/faux. Les scores se lisent par rapport à ces seuils.
- Résultats calculés sur un échantillon, pas sur la totalité du dataset (contrainte de temps et de machine).
- Un seul petit modèle (1B paramètres) testé.
- Règle de lecture de la réponse stricte : une réponse correcte écrite en phrase (« The answer is B ») compte comme format invalide.
- Les questions sont en anglais dans tous les prompts, seule la consigne change de langue.
- Par catégorie, le nombre de réponses est faible : les scores sont à lire avec prudence.

## 9. Pistes d'amélioration

- Ajouter un prompt sans choix (réponse libre) pour comparer reconnaissance et rappel.
- Comparer plusieurs modèles.
- Mart sur la cohérence des réponses entre les deux prompts (robustesse).
- 