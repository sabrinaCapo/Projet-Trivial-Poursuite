"""
Enrichissement : pose chaque question au modèle (LM Studio) et écrit
data/silver/model_answers.parquet.

Une ligne par (question, modèle, prompt) : question_id, model, prompt_id,
correct_letter, ai_answer, response_time, error.
`ai_correct` est calculé plus tard, dans dbt (couche intermediate).

"""

import argparse
import json
import random
import time
from pathlib import Path

import pandas as pd
import requests

# --- Configuration ---
API_URL = "http://localhost:1234/v1/chat/completions"  # serveur LM Studio
MODELS = ["llama-3.2-1b-instruct"]  # ajouter d'autres modèles ici
QUESTIONS_PATH = Path("data/silver/questions_clean.parquet")
OUTPUT_PATH = Path("data/silver/model_answers.parquet")
SAVE_EVERY = 50  # sauvegarde régulière pour pouvoir reprendre

LETTERS = "ABCDEFGH"  # lettres attribuées aux choix
FREE_PROMPT = "p3_libre"  # prompt sans choix : réponse libre

# Prompts standardisés (le prompt_id est conservé dans le dataset).
# Ne jamais renommer ni modifier un prompt après un run.
PROMPTS = {
    "p1_english": (
        "Answer with the letter of the correct choice only, nothing else.\n"
        "Question: {question}\n{choices}\nAnswer:"
    ),
    "p2_français": (
        "Réponds uniquement par la lettre du bon choix, rien d'autre.\n"
        "Question : {question}\n{choices}\nRéponse :"
    ),
    FREE_PROMPT: (
        "Answer with the answer only, a few words, no explanation.\n"
        "Question: {question}\nAnswer:"
    ),
}


def build_prompt(prompt_id: str, row) -> tuple[str, str]:
    """Retourne (prompt, lettre de la bonne réponse)."""
    # Prompt libre : pas de choix, donc pas de lettre
    if prompt_id == FREE_PROMPT:
        return PROMPTS[prompt_id].format(question=row.question), ""

    # Bonne réponse + mauvaises réponses
    choices = json.loads(row.incorrect_answers) + [row.correct_answer]
    # Mélange stable : même ordre pour une même question
    random.Random(row.question_id).shuffle(choices)
    # Lettre de la bonne réponse après mélange
    correct_letter = LETTERS[choices.index(row.correct_answer)]
    # Format "A: ...", "B: ..."
    formatted = "\n".join(f"{LETTERS[i]}: {c}" for i, c in enumerate(choices))
    prompt = PROMPTS[prompt_id].format(question=row.question, choices=formatted)
    return prompt, correct_letter


def ask_model(model: str, prompt: str, max_tokens: int = 16) -> tuple[str | None, float, str | None]:
    """Retourne (réponse, temps en secondes, erreur éventuelle)."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,  # réponses reproductibles
        "max_tokens": max_tokens,  # 16 pour une lettre, 40 pour une réponse libre
    }
    start = time.perf_counter()  # début du chronomètre
    try:
        r = requests.post(API_URL, json=payload, timeout=120)
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"].strip()
        return answer, time.perf_counter() - start, None
    except Exception as e:  # on note l'erreur et on continue
        return None, time.perf_counter() - start, str(e)[:200]


def save(rows: list[dict]) -> None:
    """Écrit tous les résultats en Parquet (couche silver)."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(OUTPUT_PATH, index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50,
                        help="nombre de questions (0 = toutes)")
    args = parser.parse_args()

    questions = pd.read_parquet(QUESTIONS_PATH)
    if args.limit > 0:
        # Échantillon aléatoire mais reproductible
        questions = questions.sample(args.limit, random_state=42)

    # Reprise : on charge l'existant et on saute ce qui est déjà fait
    rows = pd.read_parquet(OUTPUT_PATH).to_dict("records") if OUTPUT_PATH.exists() else []
    done = {(r["question_id"], r["model"], r["prompt_id"]) for r in rows}

    total = len(questions) * len(MODELS) * len(PROMPTS)
    count = len(done)

    # Boucle : question x modèle x prompt
    for row in questions.itertuples():
        for model in MODELS:
            for prompt_id in PROMPTS:
                if (row.question_id, model, prompt_id) in done:
                    continue
                prompt, correct_letter = build_prompt(prompt_id, row)
                max_tokens = 40 if prompt_id == FREE_PROMPT else 16
                answer, seconds, error = ask_model(model, prompt, max_tokens)
                rows.append({
                    "question_id": row.question_id,
                    "model": model,
                    "prompt_id": prompt_id,
                    "correct_letter": correct_letter,
                    "ai_answer": answer,
                    "response_time": round(seconds, 3),
                    "error": error,
                })
                count += 1
                if count % SAVE_EVERY == 0:
                    save(rows)
                    print(f"{count}/{total} réponses")

    save(rows)
    errors = sum(1 for r in rows if pd.notna(r["error"]))
    print(f"Terminé : {len(rows)} réponses, {errors} erreurs -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()