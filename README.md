# Projet-Trivial-Poursuite

# Benchmark d'un LLM local sur des questions de culture générale

Pipeline de data engineering qui évalue un ou plusieurs modèles d'IA locaux (LM Studio) sur le dataset Open Trivia Database (OpenTDB). Architecture en médaillon (bronze, silver, gold), transformations avec dbt et dashboard Streamlit.

**Auteurs** : _à compléter (noms du binôme)_
**Avancement** : bronze OK, silver questions OK, enrichissement en cours, dbt et Streamlit à faire.

---

## 1. Objectif

Mesurer les performances de modèles d'IA sur des questions de culture générale :
- taux de bonnes réponses global, par catégorie, par difficulté,
- temps de réponse,
- impact de la formulation du prompt (langue, format),
- comparaison de modèles _(à compléter si plusieurs modèles)_.

## 2. Architecture

| Couche | Contenu | Format | Emplacement |
|---|---|---|---|
| Bronze | Questions brutes issues du scraping | CSV | `data/bronze/questions_raw.csv` |
| Silver | Questions nettoyées + réponses brutes des modèles | Parquet | `data/silver/` |
| Gold | Tables métier (staging, intermediate, mart) | DuckDB | `data/gold/benchmark.duckdb` |

Lignage dbt : `staging -> intermediate -> mart`.

```
data/        bronze, silver, gold
src/         scrap.py, build_silver.py, run_benchmark.py
dbt_project/ models/{staging, intermediate, marts}
app/         dashboard Streamlit
```

## 3. Outils utilisés

| Outil | Rôle |
|---|---|
| Python 3.11 | Langage des scripts |
| requests, truststore | Appels à l'API OpenTDB (truststore : certificats du système) |
| pandas, pyarrow | Nettoyage et fichiers Parquet |
| LM Studio | Exécute le modèle en local (serveur compatible OpenAI) |
| DuckDB | Base analytique (couche gold) |
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
python src/scrap.py                      # bronze : data/bronze/questions_raw.csv
python src/build_silver.py               # silver : questions_clean.parquet
python src/run_benchmark.py --limit 50   # silver : model_answers.parquet (0 = tout)
# dbt (gold)      : à compléter
# Streamlit       : à compléter
```

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
- Résultat : 5 250 lignes en bronze, 5 246 en silver (4 doublons retirés).

### 6.3 Silver : enrichissement par le modèle
- Pour chaque question, les bonnes et mauvaises réponses sont mélangées (ordre stable par question) puis présentées en choix A, B, C, D.
- Le modèle ne répond que par une lettre (`max_tokens` = 16, `temperature` = 0).
- Prompts standardisés, identifiés par `prompt_id` :
  - `p1_en_lettre` : consigne en anglais,
  - `p2_fr_lettre` : consigne en français.
- Colonnes écrites : `question_id`, `model`, `prompt_id`, `correct_letter`, `ai_answer`, `response_time`, `error`.
- Reprise automatique : les combinaisons déjà traitées sont ignorées.
- `ai_correct` est calculé dans dbt (première lettre de `ai_answer` comparée à `correct_letter`).

### 6.4 Gold : dbt
_À compléter : modèles staging, intermediate, marts, tests._

### 6.5 Dashboard
_À compléter._

## 7. Résultats

_À compléter après le run complet : taux de réussite global, par catégorie, par difficulté, par prompt, temps de réponse._

## 8. Limites connues

- Scraping : 5 250 questions récupérées sur 5 299 annoncées par le site (environ 49 manquantes).
- Fournir les choix rend la tâche plus facile que la réponse libre : le hasard donne 25 % de bonnes réponses en QCM et 50 % en vrai/faux. Les scores se lisent par rapport à ces seuils.
- Petit modèle (1B paramètres) choisi pour des contraintes matérielles.
- Les questions sont en anglais dans tous les prompts, seule la consigne change de langue.

## 9. Pistes d'amélioration

- Ajouter un prompt sans choix (réponse libre) pour comparer reconnaissance et rappel.
- Comparer plusieurs modèles.
- Compléter les 49 questions manquantes.