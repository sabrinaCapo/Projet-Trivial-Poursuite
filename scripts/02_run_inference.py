import html
import json
import os
import random
import re
import time
import pandas as pd
import ollama

# Sentiers des fichiers
BRONZE_PATH = os.path.join("data", "1_bronze", "questions_raw.csv")
SILVER_PATH = os.path.join("data", "2_silver", "questions_llm.parquet")

# Configuration du modèle (traitement global)
MODEL_NAME = "llama3.2:1b"
MAX_QUESTIONS = None  # None = traite 100 % des questions du CSV

# Mélange des options : sans lui, la bonne réponse est toujours en dernier (biais de position).
# Le mélange est déterministe : une même question a toujours le même ordre d'options.
SHUFFLE_OPTIONS = True
PROMPT_TYPE = "few_shot_en_shuffled_v2" if SHUFFLE_OPTIONS else "few_shot_en_analytics_v1"

# System Prompt avec Few-Shot Prompting
SYSTEM_PROMPT = (
    "You are a general knowledge trivia assistant. "
    "Select and output ONLY the exact correct answer from the provided list. "
    "Do not add explanations, letters, punctuation, or any introductory text.\n\n"
    "Example 1:\n"
    "Q: What is the capital of France?\n"
    "Options: Lyon, Paris, Marseille, Nice\n"
    "Answer: Paris\n\n"
    "Example 2:\n"
    "Q: What is the chemical symbol for water?\n"
    "Options: CO2, H2O, O2, NaCl\n"
    "Answer: H2O"
)

def clean_html(text: str) -> str:
    """Décode les entités HTML (ex: &quot; -> ")."""
    if pd.isna(text):
        return ""
    return html.unescape(str(text))

def parse_incorrect_answers(val) -> list:
    """Parse la colonne incorrect_answers."""
    if isinstance(val, list):
        return val
    try:
        return json.loads(val.replace("'", '"'))
    except Exception:
        try:
            import ast
            return ast.literal_eval(val)
        except Exception:
            return []

def ask_llm(question: str, options: list) -> tuple[str, float]:
    """Interroge Ollama avec Few-Shot + contraintes CPU."""
    formatted_options = ", ".join(options)
    prompt = f"Q: {question}\nOptions: {formatted_options}\nAnswer:"

    start_time = time.time()
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            options={
                "temperature": 0.0,
                "num_predict": 12,
                "num_thread": 4
            }
        )
        ai_answer = response["message"]["content"].strip()
    except Exception as e:
        ai_answer = f"ERROR: {str(e)}"

    duration = time.time() - start_time
    return ai_answer, round(duration, 3)

def evaluate_answer(ai_answer: str, correct_answer: str) -> bool:
    """Vérification stricte de la réponse."""
    cleaned_ai = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', ai_answer.strip().lower())
    cleaned_correct = correct_answer.strip().lower()
    
    return cleaned_ai == cleaned_correct or cleaned_correct in cleaned_ai

# =====================================================================
# NOUVELLES FONCTIONS D'ANALYSE (4 AXES COMPLÉMENTAIRES)
# =====================================================================

def analyze_hallucination(ai_answer: str, options: list) -> bool:
    """Axe 4 : Détecte si le LLM a généré un texte absent des options fournies."""
    cleaned_ai = ai_answer.strip().lower()
    cleaned_options = [opt.strip().lower() for opt in options]
    
    # Si la réponse générée n'est contenue dans aucune des options autorisées
    return not any(opt in cleaned_ai or cleaned_ai in opt for opt in cleaned_options)

def analyze_error_type(ai_answer: str, correct_answer: str, options: list) -> str:
    """Axe 4 bis : Classe l'erreur (Correct, Mauvais choix plausible, ou Hallucination)."""
    if evaluate_answer(ai_answer, correct_answer):
        return "correct"
    if analyze_hallucination(ai_answer, options):
        return "hallucination_out_of_options"
    return "plausible_wrong_choice"

def estimate_energy_cost_kwh(duration_sec: float, cpu_tdp_watts: float = 45.0) -> float:
    """Axe 5 : Estimation FinOps/GreenIT de la consommation CPU (Core i5 TDP ~45W)."""
    hours = duration_sec / 3600.0
    kwh = (cpu_tdp_watts / 1000.0) * hours
    return round(kwh, 8)

# =====================================================================

def main():
    if not os.path.exists(BRONZE_PATH):
        print(f"Fichier introuvable : {BRONZE_PATH}. Exécute d'abord l'étape 1.")
        return

    print("Chargement de la couche Bronze...")
    df = pd.read_csv(BRONZE_PATH)
    
    if MAX_QUESTIONS:
        df = df.head(MAX_QUESTIONS)
        
    total_q = len(df)
    print(f"Total de questions à traiter : {total_q}")

    # Nettoyage des entités HTML
    df["question"] = df["question"].apply(clean_html)
    df["correct_answer"] = df["correct_answer"].apply(clean_html)
    df["category"] = df["category"].apply(clean_html)  # ex. "&amp;" -> "&"

    ai_answers = []
    ai_correct_flags = []
    response_times = []
    
    # Nouveaux conteneurs pour les 4 axes d'analyse
    prompt_length_chars = []
    is_hallucinations = []
    error_types = []
    energy_costs_kwh = []

    print(f"\nDébut de l'inférence globale enrichie sur {total_q} questions avec '{MODEL_NAME}'...\n")
    start_total = time.time()

    for idx, row in df.iterrows():
        question = row["question"]
        correct_ans = row["correct_answer"]
        incorrects = parse_incorrect_answers(row["incorrect_answers"])
        incorrects_clean = [clean_html(ans) for ans in incorrects]

        all_options = incorrects_clean + [correct_ans]
        if SHUFFLE_OPTIONS:
            random.Random(question).shuffle(all_options)  # ordre stable par question

        # 1. Inférence LLM
        ai_ans, duration = ask_llm(question, all_options)
        is_correct = evaluate_answer(ai_ans, correct_ans)

        # 2. Calculs des nouveaux axes d'analyse
        char_len = len(question)
        is_hallu = analyze_hallucination(ai_ans, all_options)
        err_type = analyze_error_type(ai_ans, correct_ans, all_options)
        kwh = estimate_energy_cost_kwh(duration)

        # Stockage
        ai_answers.append(ai_ans)
        ai_correct_flags.append(is_correct)
        response_times.append(duration)
        
        prompt_length_chars.append(char_len)
        is_hallucinations.append(is_hallu)
        error_types.append(err_type)
        energy_costs_kwh.append(kwh)

        # Suivi d'avancement
        if (idx + 1) % 10 == 0 or (idx + 1) == total_q:
            elapsed = round(time.time() - start_total, 1)
            print(f"[{idx + 1}/{total_q}] Traités — Temps : {elapsed}s | Type Erreur : {err_type}")

    # 3. Enrichissement du DataFrame (Couche Silver)
    df["ai_model"] = MODEL_NAME
    df["ai_prompt_type"] = PROMPT_TYPE
    df["ai_answer"] = ai_answers
    df["ai_correct"] = ai_correct_flags
    df["response_time"] = response_times
    
    # Colonnes ajoutées pour les nouveaux axes d'analyse
    df["prompt_length_chars"] = prompt_length_chars
    df["is_hallucination"] = is_hallucinations
    df["error_type"] = error_types
    df["estimated_cpu_kwh"] = energy_costs_kwh

    # 4. Sauvegarde dans la Couche Silver
    os.makedirs(os.path.dirname(SILVER_PATH), exist_ok=True)
    df.to_parquet(SILVER_PATH, index=False)

    print(f"\nSuccès : l'intégralité des {total_q} lignes avec métriques d'analyse enregistrée dans '{SILVER_PATH}'.")

if __name__ == "__main__":
    main()