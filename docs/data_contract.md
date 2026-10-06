# Contrat de données — LLM Trivia Benchmark

Version : 1.0 — date : 2026-10-06
Toute modification doit être validée par les deux membres du binôme
(PR relue par l'autre) et incrémenter la version.

---

## Règles générales
- Encodage : UTF-8. Dates : ISO 8601 (UTC).
- Noms de colonnes : snake_case, en anglais.
- Une colonne du contrat ne peut jamais être absente d'un fichier.
  Une valeur inconnue est NULL, jamais une chaîne vide ou "N/A".
- Les fichiers d'une couche ne sont écrits QUE par le script indiqué.

## Règles de reproductibilité du benchmark
- Échantillon : stratifié par catégorie × difficulté, graine = 42,
  taille identique pour tous les modèles (300 questions par défaut).
  -> Tous les modèles répondent EXACTEMENT aux mêmes question_id.
- Appels LLM : temperature = 0, seed = 42.
- Le premier appel à un modèle (chargement en mémoire) n'est pas chronométré.
- Ordre des options QCM : mélangé une seule fois en silver (graine = question_id),
  puis identique pour tous les modèles et tous les prompts.

---

## BRONZE — data/bronze/questions_raw.csv
Produit par : src/ingestion/scrape_opentdb.py
Grain : 1 ligne = 1 question telle que renvoyée par l'API OpenTDB.
Aucune transformation (entités HTML conservées : &quot; &#039; ...).

| colonne           | type        | description                                 |
|-------------------|-------------|---------------------------------------------|
| category_id       | entier      | id de catégorie OpenTDB (9 à 32)            |
| category          | texte       | nom brut de la catégorie                    |
| type              | texte       | multiple / boolean                          |
| difficulty        | texte       | easy / medium / hard                        |
| question          | texte       | texte brut (encodé HTML)                    |
| correct_answer    | texte       | bonne réponse brute                         |
| incorrect_answers | texte JSON  | liste des mauvaises réponses, ex. ["a","b"] |
| scraped_at        | date        | horodatage du scraping                      |

---

## SILVER — data/silver/questions_clean.parquet
Produit par : src/processing/clean_questions.py
Grain : 1 ligne = 1 question unique.
Clé : question_id (unique, non nul).

| colonne               | type        | description / valeurs autorisées                     |
|-----------------------|-------------|------------------------------------------------------|
| question_id           | texte       | sha1(question + correct_answer), 12 premiers car.   |
| category_id           | entier      | id OpenTDB                                           |
| category              | texte       | décodée, ex. "Entertainment: Film"                   |
| category_group        | texte       | partie avant ":", ex. "Entertainment"                |
| type                  | texte       | multiple / boolean                                   |
| difficulty            | texte       | easy / medium / hard                                 |
| question              | texte       | décodée (HTML -> texte), espaces normalisés          |
| correct_answer        | texte       | décodée                                              |
| incorrect_answers     | liste texte | décodées (3 pour multiple, 1 pour boolean)           |
| options               | liste texte | ordre affiché au modèle ; boolean = ["True","False"] |
| correct_letter        | texte       | A / B / C / D : position de la bonne réponse         |
| n_options             | entier      | 4 (multiple) ou 2 (boolean)                          |
| question_length_words | entier      | nombre de mots de la question                        |
| in_sample             | booléen     | True si la question fait partie de l'échantillon     |

---

## SILVER — data/silver/ai_responses/<modele>__<prompt_id>.parquet
Produit par : src/enrichment/run_benchmark.py
Nom de fichier : caractères spéciaux du modèle remplacés par "-",
ex. llama3.2-3b__p3_mcq.parquet
Grain : 1 ligne = 1 modèle × 1 prompt × 1 question.
Clé : (model, prompt_id, question_id) unique.
Lien : question_id doit exister dans questions_clean.

| colonne       | type    | description                                                  |
|---------------|---------|--------------------------------------------------------------|
| run_id        | texte   | identifiant de l'exécution (pour tracer les relances)        |
| model         | texte   | nom exact Ollama, ex. llama3.2:3b                            |
| prompt_id     | texte   | p1_open / p2_constrained / p3_mcq / p4_mcq_fewshot           |
| prompt_text   | texte   | prompt exact envoyé (messages système + utilisateur)         |
| question_id   | texte   | clé vers questions_clean                                     |
| ai_answer_raw | texte   | réponse brute du modèle, non modifiée                        |
| ai_answer     | texte   | réponse interprétée (texte de l'option choisie si QCM)       |
| ai_correct    | booléen | True si ai_answer correspond à correct_answer                |
| parse_ok      | booléen | False si la réponse n'a pas pu être interprétée              |
| response_time | décimal | temps de génération en secondes (mesure côté Python)         |
| eval_count    | entier  | nombre de tokens générés (renvoyé par Ollama), NULL possible |
| temperature   | décimal | toujours 0.0                                                 |
| error         | texte   | message d'erreur si l'appel a échoué, sinon NULL             |
| created_at    | date    | horodatage de la réponse                                     |

Règles de calcul de ai_correct :
- prompts QCM (p3, p4) : extraction de la lettre A-D -> option correspondante.
- prompts libres (p1, p2) : texte normalisé (minuscules, sans accents ni
  ponctuation ni articles) ; juste si la bonne réponse y figure ET
  qu'aucune mauvaise réponse n'y figure.
- en cas d'erreur d'appel : ai_correct = False, parse_ok = False.

---

## GOLD — data/gold/benchmark.duckdb (schéma "mart")
Produit par : dbt (dbt_benchmark/). Lu par : app/ (Streamlit), en lecture seule.

| table                       | grain                                        | question métier                           |
|-----------------------------|----------------------------------------------|-------------------------------------------|
| mart_model_leaderboard      | model × prompt_id                            | Quel modèle / prompt est le meilleur ?    |
| mart_accuracy_by_category   | model × prompt_id × category                 | Sur quels thèmes chaque modèle est fort ? |
| mart_accuracy_by_difficulty | model × prompt_id × difficulty × type        | La difficulté officielle est-elle juste ? |
| mart_prompt_impact          | model × prompt_id                            | Quel gain apporte chaque prompt ?         |
| mart_question_difficulty    | question_id                                  | Quelles questions piègent les modèles ?   |
| mart_response_log           | model × prompt_id × question_id              | Exploration détaillée des réponses        |

Colonnes communes des marts d'agrégat :
n_questions (entier), accuracy_pct (0-100, 2 décimales),
avg_response_time_s (secondes, 3 décimales).