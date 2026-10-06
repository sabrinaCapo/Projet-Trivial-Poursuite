"""
Scraping complet d'OpenTDB -> couche bronze (data/bronze/questions_raw.csv).
Version corrigée du script scrap.py.
"""

# Doit être fait AVANT d'importer requests : Python utilise alors les
# certificats de Windows (corrige l'erreur SSL "self signed certificate").
import truststore
truststore.inject_into_ssl()

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import requests

PAUSE_SECONDS = 5.5   # l'API autorise 1 requête toutes les 5 secondes
MAX_RETRIES = 5
OUTPUT_PATH = Path("data/bronze/questions_raw.csv")

FIELDS = [
    "category",
    "type",               # multiple | boolean
    "difficulty",         # easy | medium | hard
    "question",
    "correct_answer",
    "incorrect_answers",  # liste encodée en chaîne JSON
    "scraped_at",
]


class OpenTDBClient:
    def __init__(self):
        # Les deux URL doivent pointer vers les bons fichiers de l'API
        self.base_url = "https://opentdb.com/api.php"
        self.token_url = "https://opentdb.com/api_token.php"
        self.token = self._get_session_token()

    def _get_session_token(self):
        """Récupère un jeton : l'API ne renverra jamais deux fois la même question."""
        response = requests.get(
            self.token_url, params={"command": "request"}, timeout=30
        )
        response.raise_for_status()
        data = response.json()
        if data.get("response_code") != 0:
            raise RuntimeError(f"Impossible d'obtenir un token : {data}")
        return data["token"]

    def get_questions(self, amount=50):
        """
        Retourne (response_code, résultats) pour un lot de questions.
        Gère le rate limit en réessayant avec une pause croissante.
        """
        params = {"amount": amount, "token": self.token, "encode": "url3986"}

        for attempt in range(1, MAX_RETRIES + 1):
            response = requests.get(self.base_url, params=params, timeout=30)
            time.sleep(PAUSE_SECONDS)  # pause obligatoire après chaque appel

            if response.status_code == 429:  # trop de requêtes (HTTP)
                time.sleep(PAUSE_SECONDS * attempt)
                continue
            response.raise_for_status()

            data = response.json()
            if data.get("response_code") == 5:  # trop de requêtes (API)
                time.sleep(PAUSE_SECONDS * attempt)
                continue
            return data["response_code"], data.get("results", [])

        raise RuntimeError("Rate limit persistant : trop de tentatives")


def decode(value):
    """Les champs texte arrivent encodés en url3986 : on les décode."""
    return unquote(value) if isinstance(value, str) else value


def to_row(item, scraped_at):
    return {
        "category": decode(item["category"]),
        "type": decode(item["type"]),
        "difficulty": decode(item["difficulty"]),
        "question": decode(item["question"]),
        "correct_answer": decode(item["correct_answer"]),
        "incorrect_answers": json.dumps(
            [decode(a) for a in item["incorrect_answers"]], ensure_ascii=False
        ),
        "scraped_at": scraped_at,
    }


def scrape_all():
    """Boucle jusqu'à épuisement du dataset et écrit le CSV bronze."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    client = OpenTDBClient()
    amount = 50  # maximum autorisé par appel
    total = 0

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()

        while True:
            code, results = client.get_questions(amount=amount)
            scraped_at = datetime.now(timezone.utc).isoformat()

            if results:
                writer.writerows(to_row(item, scraped_at) for item in results)
                f.flush()  # on ne perd rien si le script s'arrête
                total += len(results)
                print(f"{total} questions récupérées")

            if code == 0:
                continue
            if code == 4:
                print("Toutes les questions ont été récupérées.")
                break
            if code == 1:
                # Pas assez de questions restantes pour ce lot : on réduit
                if amount == 1:
                    print("Dataset épuisé.")
                    break
                amount = max(1, amount // 2)
                continue
            raise RuntimeError(f"Code de réponse inattendu : {code}")

    print(f"Total : {total} questions -> {OUTPUT_PATH}")


if __name__ == "__main__":
    scrape_all()