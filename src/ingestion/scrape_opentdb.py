"""Scrape l'intégralité d'OpenTDB vers la couche bronze.

Sortie : data/bronze/questions_raw.csv

Fonctionnement :
  1. demande un session token (la "clé d'API" d'OpenTDB) : avec ce token,
     l'API ne renvoie jamais deux fois la même question ;
  2. pour chaque catégorie, récupère le nombre de questions puis les télécharge
     par lots de 50 (maximum de l'API) jusqu'à épuisement ;
  3. respecte la limite de l'API : 1 requête toutes les 5 secondes par IP.

Conformément au contrat de données (docs/data_contract.md), aucune
transformation n'est appliquée : les textes sont conservés tels que renvoyés
par l'API, avec leurs entités HTML (&quot; &#039; ...). Le décodage est fait
en silver par src/processing/clean_questions.py.

Usage :
    python src/ingestion/scrape_opentdb.py                  # toutes les catégories
    python src/ingestion/scrape_opentdb.py --categories 9 18
    python src/ingestion/scrape_opentdb.py --restart   # ignore le CSV existant

Si le script s'arrête (coupure réseau), il suffit de le relancer : les
catégories déjà présentes dans le CSV sont ignorées.
"""

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL = "https://opentdb.com"
OUTPUT_PATH = Path(__file__).resolve().parents[2] / "data" / "bronze" / "questions_raw.csv"

BATCH_SIZE = 50        # maximum autorisé par l'API
REQUEST_DELAY = 5.2    # limite : 1 requête / 5 s / IP
MAX_RETRIES = 8
MAX_BACKOFF = 120      # secondes

COLUMNS = [
    "category_id", "category", "type", "difficulty",
    "question", "correct_answer", "incorrect_answers", "scraped_at",
]

# Codes de réponse de l'API
SUCCESS, NO_RESULTS, INVALID_PARAMETER, TOKEN_NOT_FOUND, TOKEN_EMPTY, RATE_LIMIT = range(6)


class OpenTDBClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.last_request = 0.0
        self.token: str | None = None

    def get(self, endpoint: str, **params) -> dict:
        """GET avec respect du délai entre requêtes et réessais en cas d'erreur réseau / rate limit."""
        for attempt in range(1, MAX_RETRIES + 1):
            wait = REQUEST_DELAY - (time.monotonic() - self.last_request)
            if wait > 0:
                time.sleep(wait)
            self.last_request = time.monotonic()

            try:
                response = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.SSLError as exc:
                # Réessayer ne sert à rien : le réseau intercepte le HTTPS (proxy, antivirus...)
                raise SystemExit(
                    f"Erreur SSL : {exc}\n"
                    "Le réseau intercepte la connexion HTTPS. Changez de réseau puis relancez : "
                    "le script reprendra là où il s'est arrêté."
                )
            except (requests.RequestException, ValueError) as exc:
                backoff = min(MAX_BACKOFF, REQUEST_DELAY * 2 ** attempt)
                print(f"  erreur réseau ({exc}), essai {attempt}/{MAX_RETRIES}, attente {backoff:.0f} s")
                time.sleep(backoff)
                continue

            if data.get("response_code") == RATE_LIMIT:
                backoff = min(MAX_BACKOFF, REQUEST_DELAY * 2 ** attempt)
                print(f"  rate limit atteint, essai {attempt}/{MAX_RETRIES}, attente {backoff:.0f} s")
                time.sleep(backoff)
                continue
            return data

        raise RuntimeError(f"Échec après {MAX_RETRIES} essais : {endpoint} {params}")

    def request_token(self) -> str:
        data = self.get("api_token.php", command="request")
        if data.get("response_code") != SUCCESS:
            raise RuntimeError(f"Impossible d'obtenir un token : {data}")
        self.token = data["token"]
        return self.token

    def categories(self) -> list[dict]:
        return self.get("api_category.php")["trivia_categories"]

    def category_count(self, category_id: int) -> int:
        data = self.get("api_count.php", category=category_id)
        return data["category_question_count"]["total_question_count"]

    def global_count(self) -> int:
        return self.get("api_count_global.php")["overall"]["total_num_of_verified_questions"]

    def questions(self, category_id: int, amount: int) -> tuple[int, list[dict]]:
        data = self.get(
            "api.php", amount=amount, category=category_id, token=self.token
        )
        return data["response_code"], data.get("results", [])


def scrape_category(client: OpenTDBClient, category: dict) -> list[dict]:
    expected = client.category_count(category["id"])
    print(f"\n[{category['id']}] {category['name']} : {expected} questions attendues")

    rows: list[dict] = []
    amount = min(BATCH_SIZE, expected)

    while amount > 0:
        code, results = client.questions(category["id"], amount)

        if code == SUCCESS:
            scraped_at = datetime.now(timezone.utc).isoformat()
            for q in results:
                rows.append({
                    "category_id": category["id"],
                    "category": q["category"],
                    "type": q["type"],
                    "difficulty": q["difficulty"],
                    "question": q["question"],
                    "correct_answer": q["correct_answer"],
                    "incorrect_answers": json.dumps(q["incorrect_answers"], ensure_ascii=False),
                    "scraped_at": scraped_at,
                })
            print(f"  {len(rows)}/{expected}")
            amount = min(BATCH_SIZE, expected - len(rows))

        elif code in (NO_RESULTS, TOKEN_EMPTY):
            # Moins de questions restantes que demandé : on réduit la taille du lot.
            # Avec amount=1, ce code signifie que la catégorie est épuisée.
            amount = 0 if amount == 1 else amount // 2

        elif code == TOKEN_NOT_FOUND:
            # Token expiré (6 h d'inactivité) : on en redemande un. Les éventuels
            # doublons sont supprimés dans stg_questions.
            print("  token expiré, nouveau token demandé")
            client.request_token()

        else:
            raise RuntimeError(f"Réponse inattendue de l'API (code {code})")

    return rows


def write_csv(rows: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--categories", nargs="+", type=int, help="ids de catégories (défaut : toutes)")
    parser.add_argument("--restart", action="store_true", help="ignore le CSV existant et repart de zéro")
    args = parser.parse_args()

    # Reprise : le CSV n'est écrit qu'après chaque catégorie complète, donc toute
    # catégorie présente dans le fichier est terminée.
    rows: list[dict] = []
    if OUTPUT_PATH.exists() and not args.restart:
        with OUTPUT_PATH.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    done = {int(r["category_id"]) for r in rows}
    if done:
        print(f"Reprise : {len(rows)} questions déjà présentes ({len(done)} catégories terminées)")

    client = OpenTDBClient()
    token = client.request_token()
    print(f"Session token obtenu : {token}")

    categories = client.categories()
    if args.categories:
        categories = [c for c in categories if c["id"] in args.categories]
    categories = [c for c in categories if c["id"] not in done]
    print(f"{len(categories)} catégories à scraper")

    for category in categories:
        rows.extend(scrape_category(client, category))
        write_csv(rows)  # sauvegarde après chaque catégorie, au cas où le script s'arrête

    print(f"\n{len(rows)} questions écrites dans {OUTPUT_PATH} (l'API en annonce {client.global_count()})")


if __name__ == "__main__":
    main()
