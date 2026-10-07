"""
Boucle du benchmark : interroge les modèles Ollama, chronomètre et enregistre (silver).

Entrée  : data/silver/questions_clean.parquet (questions de l'échantillon, in_sample = True)
Sortie  : data/silver/ai_responses/<modele>__<prompt_id>.parquet
Contrat : docs/data_contract.md (section SILVER — ai_responses)

Pour chaque modèle x prompt x question :
  1. construit les messages (prompt.py) ;
  2. appelle Ollama via son API Python (temperature 0, seed 42) ;
  3. chronomètre l'appel côté Python (response_time, en secondes) ;
  4. interprète la réponse (scoring.py) -> ai_answer, ai_correct, parse_ok ;
  5. enregistre une ligne par question, en sauvegardant régulièrement.

Le premier appel à chaque modèle (chargement en mémoire) n'est pas chronométré.
Les questions déjà répondues sans erreur sont ignorées : le script peut être
relancé après une interruption, il reprend là où il s'était arrêté.

Usage :
    python src/enrichment/run_benchmark.py --models llama3.2:3b
    python src/enrichment/run_benchmark.py --models llama3.2:3b --prompts p3_mcq --limit 10
"""
import argparse
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import ollama
import pandas as pd
import pyarrow as pa
from tqdm import tqdm

from prompt import VARIANTS, build_messages, render
from scoring import score

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = ROOT / "data" / "silver" / "questions_clean.parquet"
RESPONSES_DIR = ROOT / "data" / "silver" / "ai_responses"

TEMPERATURE = 0.0   # contrat : temperature = 0
SEED = 42           # contrat : seed = 42
SAVE_EVERY = 20     # sauvegarde intermédiaire toutes les N réponses

SCHEMA = pa.schema([
    ("run_id", pa.string()),
    ("model", pa.string()),
    ("prompt_id", pa.string()),
    ("prompt_text", pa.string()),
    ("question_id", pa.string()),
    ("ai_answer_raw", pa.string()),
    ("ai_answer", pa.string()),
    ("ai_correct", pa.bool_()),
    ("parse_ok", pa.bool_()),
    ("response_time", pa.float64()),
    ("eval_count", pa.int64()),
    ("temperature", pa.float64()),
    ("error", pa.string()),
    ("created_at", pa.timestamp("us", tz="UTC")),
])


def output_path(model, prompt_id):
    """llama3.2:3b + p3_mcq -> llama3.2-3b__p3_mcq.parquet"""
    safe_model = re.sub(r"[^A-Za-z0-9._-]", "-", model)
    return RESPONSES_DIR / f"{safe_model}__{prompt_id}.parquet"


def check_models(models):
    try:
        installed = {m.model for m in ollama.list().models}
    except Exception as exc:  # Ollama non lancé
        raise SystemExit(f"Ollama ne répond pas ({exc}). Lancez l'application Ollama.")
    missing = [m for m in models if m not in installed and f"{m}:latest" not in installed]
    if missing:
        raise SystemExit(f"Modèles absents : {missing}. Installez-les avec `ollama pull <modele>`.")


def warm_up(model):
    """Charge le modèle en mémoire : ce premier appel n'est pas chronométré."""
    ollama.chat(model=model, messages=[{"role": "user", "content": "Hi"}], options={"num_predict": 1})


def ask(model, messages):
    """Appelle le modèle et chronomètre l'appel. Retourne (texte, eval_count, secondes)."""
    start = time.perf_counter()
    response = ollama.chat(
        model=model,
        messages=messages,
        options={"temperature": TEMPERATURE, "seed": SEED, "num_predict": 64},
    )
    elapsed = time.perf_counter() - start
    return response.message.content, response.eval_count, elapsed


def load_questions(limit):
    df = pd.read_parquet(QUESTIONS_PATH)
    df = df[df["in_sample"]].sort_values("question_id")
    return df.head(limit) if limit else df


def load_previous(path):
    """Réponses déjà obtenues sans erreur (les erreurs seront retentées)."""
    if not path.exists():
        return []
    previous = pd.read_parquet(path)
    return previous[previous["error"].isna()].to_dict("records")


def save(path, rows):
    df = pd.DataFrame(rows, columns=SCHEMA.names)
    df.to_parquet(path, index=False, schema=SCHEMA)


def run(model, prompt_id, questions, run_id):
    path = output_path(model, prompt_id)
    answer_format = VARIANTS[prompt_id][1]

    rows = load_previous(path)
    done = {r["question_id"] for r in rows}
    todo = questions[~questions["question_id"].isin(done)]
    if todo.empty:
        print(f"[{model} / {prompt_id}] déjà complet ({len(done)} réponses)")
        return

    n_new = 0
    try:
        for q in tqdm(todo.to_dict("records"), desc=f"{model} / {prompt_id}", unit="q"):
            messages = build_messages(prompt_id, q)
            row = {
                "run_id": run_id,
                "model": model,
                "prompt_id": prompt_id,
                "prompt_text": render(messages),
                "question_id": q["question_id"],
                "temperature": TEMPERATURE,
                "created_at": datetime.now(timezone.utc),
            }
            try:
                raw, eval_count, elapsed = ask(model, messages)
                row.update(ai_answer_raw=raw, eval_count=eval_count, response_time=elapsed, error=None)
                row.update(score(raw, q, answer_format))
            except Exception as exc:  # on garde la trace de l'échec, la ligne sera retentée au prochain run
                row.update(ai_answer_raw=None, ai_answer=None, ai_correct=False, parse_ok=False,
                           response_time=None, eval_count=None, error=repr(exc))

            rows.append(row)
            n_new += 1
            if n_new % SAVE_EVERY == 0:
                save(path, rows)
    except KeyboardInterrupt:
        # Ctrl+C : on sauvegarde tout ce qui a été fait avant de quitter
        save(path, rows)
        raise SystemExit(f"\nInterrompu : {len(rows)} réponses sauvegardées dans {path.name}. "
                         "Relancez la même commande pour reprendre.")

    save(path, rows)
    ok = [r for r in rows if r["error"] is None]
    accuracy = sum(r["ai_correct"] for r in ok) / len(ok) if ok else 0
    print(f"  -> {path.name} : {len(rows)} réponses, accuracy {accuracy:.1%}, "
          f"{len(rows) - len(ok)} erreur(s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", required=True, help="noms Ollama, ex. llama3.2:3b")
    parser.add_argument("--prompts", nargs="+", default=list(VARIANTS), choices=list(VARIANTS))
    parser.add_argument("--limit", type=int, default=None, help="nombre max de questions (pour tester)")
    args = parser.parse_args()

    check_models(args.models)
    questions = load_questions(args.limit)
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]
    print(f"Run {run_id} : {len(questions)} questions x {len(args.prompts)} prompts x {len(args.models)} modèle(s)")

    for model in args.models:
        print(f"\nChargement de {model}...")
        warm_up(model)
        for prompt_id in args.prompts:
            run(model, prompt_id, questions, run_id)


if __name__ == "__main__":
    main()
