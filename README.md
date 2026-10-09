# Benchmark d'un LLM local sur des questions de culture générale (OpenTDB)

Pipeline de data engineering qui évalue un modèle d'IA local (`llama3.2:1b`, via Ollama) sur l'intégralité du dataset Open Trivia Database. Architecture en médaillon (bronze, silver, gold), transformations avec dbt et dashboard Streamlit qui lit la couche gold.

**Auteurs** : _à compléter (noms du binôme)_

---

## 1. Objectif

Faire passer un « examen » de culture générale à un petit modèle d'IA, puis analyser ses résultats :
- taux de bonnes réponses global, par catégorie, par difficulté et par type de question (QCM ou vrai/faux),
- temps de réponse et empreinte énergétique estimée,
- qualité des erreurs : mauvaise option plausible ou hallucination (réponse hors des options proposées).

## 2. Architecture

| Couche | Contenu | Format | Emplacement |
|---|---|---|---|
| Bronze | Questions brutes issues du scraping (5 299 lignes) | CSV | `data/1_bronze/questions_raw.csv` |
| Silver | Questions + réponses du modèle + métriques d'analyse (15 colonnes) | Parquet | `data/2_silver/questions_llm.parquet` |
| Gold | Vues de staging et intermédiaire, tables métier (marts) | DuckDB | `data/3_gold/analytics.duckdb` |

Lignage dbt :

```
silver_data.questions_llm -> stg_questions_llm -> int_llm_performance -> mart_global_performance
                                                                      -> mart_performance_by_category
                                                                      -> mart_performance_by_difficulty
                                                                      -> mart_performance_by_type
                                                                      -> mart_error_types
                                                                      -> mart_questions_detail  -> dashboard
```

```
scrapp.py                     scraping OpenTDB -> bronze
scripts/02_run_inference.py   inférence Ollama + métriques -> silver
dbt_project/                  models/{staging, intermediate, marts}
app.py                        dashboard Streamlit (lit la couche gold)
requirements.txt              dépendances Python
```

## 3. Outils utilisés

| Outil | Rôle |
|---|---|
| Python | Langage des scripts |
| requests, pandas | Scraping de l'API OpenTDB et manipulation des données |
| pyarrow | Lecture et écriture du Parquet |
| Ollama (`ollama` Python) | Exécute le modèle `llama3.2:1b` en local |
| DuckDB | Base analytique (couche gold) |
| dbt-core, dbt-duckdb | Transformations SQL, lignage et tests |
| Streamlit, Plotly | Dashboard interactif |

## 4. Installation

```bash
git clone https://github.com/sabrinaCapo/Projet-Trivial-Poursuite.git
cd Projet-Trivial-Poursuite
git checkout version2

python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt
```

Installer Ollama (https://ollama.com), puis télécharger le modèle :

```bash
ollama pull llama3.2:1b
```

## 5. Exécution du pipeline

```bash
python scrapp.py                          # bronze : data/1_bronze/questions_raw.csv
python scripts/02_run_inference.py        # silver : data/2_silver/questions_llm.parquet (environ 1 h 30)

cd dbt_project
dbt run --profiles-dir .                  # gold : data/3_gold/analytics.duckdb
dbt test --profiles-dir .                 # tests de qualité
cd ..

streamlit run app.py                      # dashboard
```

- Dans `scripts/02_run_inference.py`, la variable `MAX_QUESTIONS` limite le nombre de questions pour un test (`None` = tout le dataset).
- Lancer dbt depuis `dbt_project/` : les chemins des fichiers sont relatifs à ce dossier.
- Fermer le dashboard pendant `dbt run` (verrou DuckDB), puis recharger la page.

## 6. Méthodologie

### 6.1 Bronze : scraping (`scrapp.py`)
- API OpenTDB avec **session token** : aucune question n'est renvoyée deux fois.
- Lots de 50 questions, pause de 5,1 s entre les appels (limite de l'API : 1 requête toutes les 5 secondes), gestion du rate limit (code 5) et des erreurs réseau.
- Arrêt quand le token est épuisé (code 4) ou que 5 299 questions sont récupérées.
- Le fichier brut n'est pas modifié : 6 colonnes (`type`, `difficulty`, `category`, `question`, `correct_answer`, `incorrect_answers`).

### 6.2 Silver : inférence et enrichissement (`scripts/02_run_inference.py`)

**Prompt** : un seul prompt standardisé, en **few-shot**. Un message système en anglais demande de répondre uniquement par le texte exact de la bonne réponse, sans explication, et fournit 2 exemples. Le message utilisateur contient la question et la liste des options.

**Mélange des options** : l'ordre des options est mélangé de façon déterministe (une même question a toujours le même ordre). Sans mélange, la bonne réponse serait toujours placée en dernier, ce qui peut créer un biais de position. L'option est contrôlée par `SHUFFLE_OPTIONS` ; l'identifiant du prompt vaut `few_shot_en_shuffled_v2` avec mélange, `few_shot_en_analytics_v1` sans.

**Paramètres du modèle** : `temperature` = 0 (réponses reproductibles), `num_predict` = 12 (réponse courte), `num_thread` = 4.

**Colonnes ajoutées aux questions**

| Colonne | Contenu |
|---|---|
| `ai_model`, `ai_prompt_type` | Modèle utilisé et identifiant du prompt |
| `ai_answer` | Réponse brute du modèle |
| `ai_correct` | Booléen : la réponse correspond à la bonne réponse |
| `response_time` | Temps de génération (secondes) |
| `prompt_length_chars` | Longueur de la question en caractères |
| `is_hallucination` | La réponse n'est contenue dans aucune des options proposées |
| `error_type` | `correct`, `plausible_wrong_choice` (mauvaise option) ou `hallucination_out_of_options` |
| `estimated_cpu_kwh` | Énergie CPU estimée : TDP de 45 W (Core i5) multiplié par la durée |

**Règle de correction (`ai_correct`)** : la réponse du modèle est mise en minuscules et débarrassée de la ponctuation en début et fin de texte. Elle est juste si elle est égale à la bonne réponse, ou si la bonne réponse est contenue dans la réponse du modèle.

**Nettoyage** : les entités HTML (`&quot;`, `&#039;`, `&amp;`) sont décodées dans la question, la bonne réponse, les options et la catégorie.

### 6.3 Gold : dbt (`dbt_project/`)

| Modèle | Type | Question métier |
|---|---|---|
| `stg_questions_llm` | vue (staging) | Remise en forme de la silver : décode `&amp;` dans les catégories et supprime les questions en double |
| `int_llm_performance` | vue (intermediate) | Ajoute les indicateurs numériques (`is_correct_int`, `is_hallucination_int`) |
| `mart_global_performance` | table (mart) | Quel est le score global du modèle ? |
| `mart_performance_by_category` | table (mart) | Dans quelles catégories le modèle est-il le plus fort ou le plus faible ? |
| `mart_performance_by_difficulty` | table (mart) | La difficulté de la question change-t-elle le score ? |
| `mart_performance_by_type` | table (mart) | QCM ou vrai/faux : quel score par rapport au hasard (25 % et 50 %) ? |
| `mart_error_types` | table (mart) | Quand le modèle se trompe, choisit-il une mauvaise option plausible ou invente-t-il une réponse ? |
| `mart_questions_detail` | table (mart) | Une ligne par question, lue par le dashboard |

La silver est lue directement par DuckDB comme source externe (`silver_data.questions_llm`). Le profil dbt écrit dans `data/3_gold/analytics.duckdb`.

**Tests** (`dbt test`) : `question`, `correct_answer` et `is_correct` non nuls, valeurs acceptées pour `type`, `difficulty` et `error_type`, `ai_correct` non nul dans la table de détail.

### 6.4 Dashboard (`app.py`)
- Lit uniquement la couche gold (table `mart_questions_detail`), avec un cache de 60 s.
- Filtres : modèle, catégorie, difficulté.
- Indicateurs : questions analysées, précision globale, temps moyen, taux d'hallucination, énergie CPU estimée, niveau du hasard.
- Graphiques : répartition des types d'erreurs, précision par difficulté, précision par type de question comparée au hasard, précision par catégorie, latence en fonction de la longueur de la question, distribution des temps de réponse.
- Un explorateur des réponses avec trois onglets : toutes les questions, hallucinations, mauvais choix plausibles.

## 7. Résultats

Modèle `llama3.2:1b`, 5 295 questions (5 299 scrapées, 4 doublons retirés en staging), prompt few-shot.

> Ces résultats proviennent du run initial, **avant** le mélange des options (`few_shot_en_analytics_v1` : bonne réponse toujours en dernière position). Après un nouveau run avec `SHUFFLE_OPTIONS = True`, relancer `dbt run` et actualiser ce tableau.

| Indicateur | Valeur |
|---|---|
| Bonnes réponses | **51,4 %** (2 721 sur 5 295) |
| Niveau du hasard | environ 28,7 % (25 % en QCM, 50 % en vrai/faux) |
| Mauvaise option plausible | 46,8 % (2 477 réponses) |
| Hallucinations (réponse hors options) | 1,8 % (97 réponses) |
| Temps de réponse | moyenne 1,06 s, médiane 0,63 s |
| Durée totale d'inférence | environ 1 h 34 |
| Énergie CPU estimée | environ 0,07 kWh |

**Par difficulté** : facile 55,5 % (1 767 questions), moyenne 50,5 % (2 424), difficile 46,7 % (1 104). Le score diminue avec la difficulté, et le temps de réponse augmente (0,79 s, 1,17 s, 1,27 s).

**Par type de question** : QCM 53,9 % (4 506 questions, hasard 25 %), vrai/faux 37,3 % (789 questions, hasard 50 %). Le score en vrai/faux est inférieur au hasard : le modèle répond « False » à 552 des 789 questions vrai/faux, ce qui traduit un biais de réponse.

**Par catégorie** : les plus faibles sont Japanese Anime & Manga (39,2 %, 204 questions), Mathematics (43,0 %, 79 questions) et Video Games (43,4 %, 1 186 questions) ; les plus fortes sont Art (75,9 %, 58 questions), Musicals & Theatres (63,9 %, 36 questions) et Politics (62,3 %, 77 questions). Les catégories qui reposent sur peu de questions sont à lire avec prudence.

**Lecture** : le modèle fait nettement mieux que le hasard en QCM, mais reste modeste pour un modèle d'un milliard de paramètres, avec un biais marqué sur les questions vrai/faux.

## 8. Limites connues

- **Biais de position dans le run documenté** : les résultats ci-dessus ont été produits avec la bonne réponse toujours en dernier. Le script mélange maintenant les options, mais le run doit être relancé pour actualiser le silver, le gold et ces résultats.
- **Règle de correction** : tester si la bonne réponse est contenue dans la réponse du modèle peut compter à tort comme juste une réponse courte ou une réponse qui cite plusieurs options.
- **Un seul prompt et un seul modèle** : l'impact de la formulation du prompt et du choix du modèle n'est pas mesuré.
- **Temps de réponse** : un appel isolé a pris plus de 300 s, ce qui tire la moyenne vers le haut. La médiane est plus représentative.
- **Énergie** : estimation théorique à partir du TDP du processeur, pas une mesure.
- **Scraping** : la cible de 5 299 questions est écrite en dur dans `scrapp.py`.

## 9. Pistes d'amélioration

- Relancer l'inférence avec les options mélangées et comparer avec le run initial pour mesurer le biais de position.
- Comparer plusieurs prompts (sans exemples, en français, réponse par lettre) et plusieurs modèles.
- Ajouter une sauvegarde intermédiaire de l'inférence pour pouvoir reprendre après une interruption.
- Améliorer la règle de correction (correspondance sur mot entier ou mesure de similarité).
