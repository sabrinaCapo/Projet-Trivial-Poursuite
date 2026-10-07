# Benchmark d'un LLM local sur des questions de culture générale

Pipeline de data engineering qui évalue un modèle d'IA local (LM Studio) sur le dataset Open Trivia Database (OpenTDB). Architecture en médaillon (bronze, silver, gold), transformations avec dbt et dashboard Streamlit.

**Auteurs** : CAPO Kale & MUGISHA Chirac 

---

## 1. Objectif

Mesurer les performances d'un modèle d'IA sur des questions de culture générale et répondre à six questions métier :

| Question métier | Table gold |
|---|---|
| Quel prompt donne les meilleurs résultats, et le modèle suit-il le format demandé ? | `accuracy_by_prompt` |
| Dans quelles catégories le modèle est-il le plus fort ou le plus faible ? | `accuracy_by_category` |
| La difficulté et le type de question changent-ils le score ? | `accuracy_by_difficulty` |
| Le temps de réponse dépend-il de la réussite et de la difficulté ? | `response_time_analysis` |
| Le modèle réagit-il de la même façon à une consigne en anglais et en français ? | `prompt_consistency` |
| Combien de questions, d'appels et d'erreurs dans le run ? | `run_summary` |

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
lms load llama-3.2-1b-instruct      # à refaire après chaque redémarrage
lms server start
lms ps                              # vérifie que le modèle est bien chargé
```

## 5. Exécution du pipeline

```bash
python src/scrap.py                       # bronze
python src/build_silver.py                # silver : questions
python src/run_benchmark.py --limit 300   # silver : réponses du modèle (0 = tout)

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

Trois prompts standardisés, identifiés par `prompt_id` et jamais modifiés après le premier run :

| `prompt_id` | Libellé | Choix proposés | Réponse attendue | Langue de la consigne |
|---|---|---|---|---|
| `p1_english` | Encodé EN | Oui, encodés A, B, C, D | Une lettre | Anglais |
| `p2_français` | Encodé FR | Oui, encodés A, B, C, D | Une lettre | Français |
| `p3_libre` | Libre | Non | Quelques mots | Anglais |

- **Encodé EN contre FR** : isole l'effet de la langue de la consigne.
- **Encodé contre Libre** : isole l'effet de l'encodage (reconnaître la bonne réponse contre la retrouver).
- Les questions restent en anglais dans tous les prompts.
- **Encodage** : la bonne et les mauvaises réponses sont mélangées (ordre stable par question) puis présentées en choix A, B, C, D.
- Paramètres : `temperature` = 0 (reproductibilité), `max_tokens` = 16 (lettre) ou 40 (réponse libre).
- Colonnes écrites : `question_id`, `model`, `prompt_id`, `correct_letter`, `ai_answer`, `response_time`, `error`.
- Les appels échoués sont enregistrés dans `error` (erreur technique) et exclus du score.
- Reprise automatique : les combinaisons déjà traitées sont ignorées.
- **Échantillon** : en raison du temps de réponse (environ 6,7 s par appel, soit environ 30 h pour les 5 246 questions avec 3 prompts), le run final porte sur un échantillon aléatoire reproductible (`random_state=42`) de **300 questions**.

### 6.4 Gold : dbt

**Staging** (remise en forme, sans calcul)
- `stg_questions` : questions silver.
- `stg_model_answers` : réponses du modèle.

**Intermediate**
- `int_answers_scored` : jointure réponses et questions, exclusion des appels en erreur, puis calcul de `is_valid_format` et `ai_correct` :
  - **Prompts encodés** : lecture de la première lettre A à H en majuscule, seule ou suivie de `.`, `:` ou `)`. La réponse est juste si cette lettre est égale à `correct_letter`. Une phrase (par exemple « A cause de... ») n'est pas comptée.
  - **Prompt libre** : textes normalisés (minuscules, sans accents ni ponctuation). QCM : la bonne réponse doit apparaître comme **mot entier** dans la réponse. Vrai/faux : la réponse doit être exactement `true` ou `false`.

**Marts** (une question métier chacun)

| Table | Contenu |
|---|---|
| `accuracy_by_prompt` | Score, format respecté et temps moyen par prompt |
| `accuracy_by_category` | Score par catégorie et par prompt |
| `accuracy_by_difficulty` | Score par difficulté, type de question et prompt |
| `response_time_analysis` | Temps moyen et médian selon la difficulté et la réussite |
| `prompt_consistency` | Comparaison question par question entre Encodé EN et Encodé FR : même résultat, juste dans les deux, faux dans les deux, juste dans une seule langue |
| `run_summary` | Nombre de questions traitées, d'appels et d'erreurs techniques |

**Tests** (`dbt test`) : `question_id` unique et non nul, valeurs acceptées pour `difficulty` et `question_type`.

### 6.5 Dashboard Streamlit
- Lit les 6 marts en lecture seule (cache de 60 s), filtres par modèle et par prompt.
- Indicateurs : questions traitées (sur le total du dataset), réponses, bonnes réponses, niveau du hasard, format respecté, temps moyen.
- Cinq onglets d'analyse (prompts, catégories, difficulté, temps, robustesse), chacun avec sa question métier, une aide à la lecture et les nuances à connaître.
- Un onglet « Méthode » : pipeline, prompts, définitions, tables métier, limites.
- Les scores agrégés sont des moyennes pondérées par le nombre de réponses ; les écarts entre prompts sont accompagnés d'une marge d'erreur à 95 %.
- Un avertissement s'affiche quand prompts encodés et libre sont mélangés dans une même moyenne.

