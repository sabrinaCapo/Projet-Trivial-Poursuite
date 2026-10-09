import os
import time
import requests
import pandas as pd

BRONZE_PATH = os.path.join("data", "1_bronze", "questions_raw.csv")

def get_session_token() -> str:
    """Récupère un jeton de session pour éviter de recevoir des doublons."""
    url = "https://opentdb.com/api_token.php?command=request"
    res = requests.get(url).json()
    if res.get("response_code") == 0:
        token = res.get("token")
        print(f" Jeton de session initialisé : {token}")
        return token
    else:
        raise Exception("Impossible d'obtenir un token de session OpenTDB.")

def fetch_all_opentdb_questions(target_count: int = 5299) -> pd.DataFrame:
    base_url = "https://opentdb.com/api.php"
    token = get_session_token()
    all_results = []
    
    batch_size = 50  # Limite maximale autorisée par requête
    fetched = 0

    print(f"Début du scraping de {target_count} questions...")

    while fetched < target_count:
        amount = min(batch_size, target_count - fetched)
        params = {
            "amount": amount,
            "token": token
        }
        
        try:
            res = requests.get(base_url, params=params)
            if res.status_code == 200:
                data = res.json()
                code = data.get("response_code")
                
                if code == 0:  # Success
                    results = data.get("results", [])
                    all_results.extend(results)
                    fetched += len(results)
                    print(f" [OK] {fetched}/{target_count} questions récupérées.")
                    
                elif code == 1:  # No Results (Pas assez de questions pour le filtre)
                    print(" Pas assez de questions disponibles pour ce critère.")
                    break
                    
                elif code == 4:  # Token Empty (Toutes les questions uniques ont été vues)
                    print(" Toutes les questions uniques d'OpenTDB ont été récupérées.")
                    break
                    
                elif code == 5:  # Rate Limit Exceeded
                    print(" Rate limit atteint. Attente de 5 secondes...")
                    time.sleep(5.5)
                    continue
                else:
                    print(f" Code réponse inattendu : {code}. Interruption.")
                    break
            else:
                print(f" Erreur HTTP {res.status_code}. Pause avant retry...")
                time.sleep(5)
                continue

        except Exception as e:
            print(f" Erreur réseau : {e}")
            time.sleep(5)
            continue

        # RTFM : Respect strict du rate limit de l'API (1 requete / 5 secondes)
        time.sleep(5.1)

    return pd.DataFrame(all_results)

def main():
    os.makedirs(os.path.dirname(BRONZE_PATH), exist_ok=True)
    
    # Lancement du scraping
    df_raw = fetch_all_opentdb_questions(target_count=5299)
    
    if not df_raw.empty:
        df_raw.to_csv(BRONZE_PATH, index=False, encoding="utf-8")
        print(f"\n Étape 1 terminée : {len(df_raw)} questions brutes enregistrées dans '{BRONZE_PATH}'.")
    else:
        print("\n Échec de la récupération des données.")

if __name__ == "__main__":
    main()