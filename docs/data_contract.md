# LLM Trivia Benchmark

Benchmark de modèles de langage **exécutés en local avec Ollama** (`gemma3:4b` et `llama3.2:3b`) sur les questions de culture générale d'[Open Trivia Database](https://opentdb.com).

Le projet met en œuvre un pipeline complet de data engineering :
**collecte** (scraping d'API) → **enrichissement** par des LLM → **transformation** avec dbt → **visualisation** avec Streamlit,
organisé selon une **architecture médaillon** (bronze → silver → gold).

> **Question posée** : à quel point des petits LLM locaux répondent-ils juste à des questions de culture générale, et quelle est l'influence de la façon de poser la question (le *prompt*) ?

---

## Sommaire

1. [Architecture](#1-architecture)
2. [Structure du dépôt](#2-structure-du-dépôt)
3. [Installation](#3-installation)
4. [Exécution du pipeline](#4-exécution-du-pipeline)
   - [4.1 Ingestion : OpenTDB → bronze](#41-ingestion--opentdb--bronze)
   - [4.2 Nettoyage : bronze → silver](#42-nettoyage--bronze--silver)
   - [4.3 Benchmark Ollama → silver](#43-benchmark-ollama--silver)
   - [4.4 Transformation dbt → gold](#44-transformation-dbt--gold)
   - [4.5 Dashboard Streamlit](#45-dashboard-streamlit)
5. [Méthodologie](#5-méthodologie)
6. [Résultats](#6-résultats)
7. [Limites](#7-limites)
8. [Organisation du projet](#8-organisation-du-projet)
9. [Dépannage](#9-dépannage)

---

## 1. Architecture

```
OpenTDB (API publique)
   │  src/ingestion/scrape_opentdb.py
   ▼
BRONZE   data/bronze/questions_raw.csv                 données brutes, aucune transformation
   │  src/processing/clean_questions.py
   ▼
SILVER   data/silver/questions_clean.parquet           questions nettoyées + échantillon du benchmark
   │  src/enrichment/run_benchmark.py  (Ollama)
   ▼
SILVER   data/silver/ai_responses/<modele>__<prompt>.parquet   réponses brutes des LLM
   │  dbt : staging → intermediate → marts
   ▼
GOLD     data/gold/benchmark.duckdb  (schéma mart)     tables métier
   │
   ▼
DASHBOARD  app/streamlit_app.py                        lit uniquement la couche gold
```

| Couche | Format | Contenu | Produit par |
|---|---|---|---|
| **Bronze** | CSV | Questions telles que renvoyées par l'API (entités HTML conservées) | `scrape_opentdb.py` |
| **Silver** | Parquet | Questions propres et dédoublonnées · réponses des LLM, une ligne par modèle × prompt × question | `clean_questions.py`, `run_benchmark.py` |
| **Gold** | DuckDB | Tables qui répondent chacune à une question métier | dbt |

Le format exact de chaque fichier (colonnes, types, clés, règles) est défini dans le **contrat de données** : [`docs/data_contract.md`](docs/data_contract.md).

---

## 2. Structure du dépôt

```
llm-trivia-benchmark/
├── app/                          Dashboard Streamlit
│   ├── streamlit_app.py            point d'entrée : filtres, KPI, onglets
│   ├── data.py                     lecture de la couche gold, couleurs, calculs
│   ├── tabs_performance.py         onglets Classement, Catégories, Difficulté
│   └── tabs_analyses.py            onglets Prompts, Temps, Questions pièges, Explorer
├── data/
│   ├── bronze/questions_raw.csv
│   ├── silver/questions_clean.parquet
│   ├── silver/ai_responses/*.parquet
│   └── gold/benchmark.duckdb       (non versionné : régénéré par dbt)
├── dbt_benchmark/                Projet dbt
│   ├── dbt_project.yml
│   ├── profiles.yml                connexion DuckDB (versionnée dans le projet)
│   ├── macros/generate_schema_name.sql
│   ├── models/staging/             lecture typée des parquet silver
│   ├── models/intermediate/        jointures et enrichissements
│   ├── models/marts/               tables gold
│   └── tests/                      tests qualité personnalisés
├── docs/data_contract.md         Contrat de données entre les couches
├── src/
│   ├── ingestion/scrape_opentdb.py
│   ├── processing/clean_questions.py
│   ├── enrichment/
│   │   ├── prompt.py               les 4 variantes de prompt
│   │   ├── scoring.py              calcul de ai_answer / ai_correct / parse_ok
│   │   ├── check_scoring.py        tests du scoring
│   │   └── run_benchmark.py        boucle d'appel à Ollama
│   └── analysis/show_results.py  affichage des résultats gold en console
├── requirements.txt
└── README.md
```

---

## 3. Installation

### Prérequis

| Outil | Version | Remarque |
|---|---|---|
| Python | **3.12** | Éviter 3.13+/3.14 : certaines librairies n'y ont pas encore de version précompilée sous Windows |
| Git | récent | |
| Ollama | récent | Exécute les LLM en local |
| Accès Internet | | HTTPS vers `opentdb.com` (scraping uniquement) et `ollama.com` (téléchargement des modèles) |

> ⚠️ **Windows** : placer le projet **hors de OneDrive** (par exemple dans `C:\dev\`). Voir aussi la section [Dépannage](#9-dépannage) si Windows bloque pandas ou DuckDB.

### 3.1 Cloner le dépôt et créer l'environnement Python

```bash
git clone https://github.com/ngouonpejeffrey16-tech/llm-trivia-benchmark.git
cd llm-trivia-benchmark

py -3.12 -m venv .venv                # Windows  (macOS / Linux : python3.12 -m venv .venv)
.\.venv\Scripts\Activate.ps1          # Windows PowerShell
# source .venv/bin/activate           # macOS / Linux

python -m pip install --upgrade pip
pip install -r requirements.txt
```

Vérification :

```bash
python -c "import pandas, duckdb, pyarrow; print('OK')"
```

### 3.2 Installer Ollama et les modèles

1. Installer Ollama :
   - **Windows** : `irm https://ollama.com/install.ps1 | iex` dans PowerShell, ou l'installeur de [ollama.com/download](https://ollama.com/download)
   - **macOS / Linux** : voir [ollama.com/download](https://ollama.com/download)
2. Télécharger les deux modèles du benchmark :
   ```bash
   ollama pull gemma3:4b      # Google, 4 milliards de paramètres, ~3,3 Go
   ollama pull llama3.2:3b    # Meta,   3 milliards de paramètres, ~2 Go
   ```
3. Vérifier :
   ```bash
   ollama list
   ollama run gemma3:4b "Who painted the Mona Lisa? Answer with a name only."
   ```

Ollama doit rester lancé pendant tout le benchmark (icône dans la barre des tâches sous Windows).

---

## 4. Exécution du pipeline

Toutes les commandes se lancent **depuis la racine du projet**, avec l'environnement virtuel activé, **sauf les commandes dbt**, qui se lancent depuis `dbt_benchmark/`.

### Démarrage rapide

Les données bronze, silver et les réponses des modèles sont versionnées dans le dépôt. Pour voir les résultats **sans relancer le scraping ni le benchmark** :

```bash
cd dbt_benchmark
dbt build --profiles-dir .
cd ..
streamlit run app/streamlit_app.py
```

### 4.1 Ingestion : OpenTDB → bronze

```bash
python src/ingestion/scrape_opentdb.py
```

**Sortie** : `data/bronze/questions_raw.csv`, une ligne par question, telle que renvoyée par l'API (aucune transformation, entités HTML conservées).

**Fonctionnement :**
- OpenTDB ne demande pas de clé d'API. Le script demande un **session token** (`api_token.php`) : avec ce token, l'API ne renvoie jamais deux fois la même question, ce qui permet de récupérer tout le dataset sans doublon.
- Pour chacune des **24 catégories** (id 9 à 32), il lit le nombre de questions (`api_count.php`), puis les télécharge par **lots de 50**, le maximum autorisé.
- L'API limite à **1 requête toutes les 5 secondes** par IP : le script attend entre chaque appel et réessaie automatiquement en cas d'erreur 429 ou de coupure réseau.
- Le CSV est écrit après chaque catégorie. Si le script s'arrête, il suffit de le relancer : les catégories déjà présentes sont ignorées.

**Résultat** : **5 299 questions**, soit toutes les questions validées d'OpenTDB. Le site en affiche environ 21 000 au total, mais les questions en attente de validation ou rejetées ne sont pas accessibles par l'API.

**Durée** : environ 25 minutes, à cause de la limite de l'API.

| Option | Effet |
|---|---|
| `--categories 9 18` | ne scrape que ces catégories |
| `--restart` | ignore le CSV existant et repart de zéro |

> Réseau d'école ou d'entreprise : certains proxys interceptent le HTTPS et provoquent une erreur `CERTIFICATE_VERIFY_FAILED`. Le script s'arrête avec un message explicite : changer de réseau (partage de connexion) et relancer, il reprend là où il s'était arrêté.

### 4.2 Nettoyage : bronze → silver

```bash
python src/processing/clean_questions.py
```

**Sortie** : `data/silver/questions_clean.parquet`, une ligne par question unique.

**Étapes :**
1. **Décodage des entités HTML** (`&quot;` → `"`, `&#039;` → `'`) et normalisation des espaces (espaces insécables, espaces multiples).
2. **Normalisation** de `type` et `difficulty`, et création de `category_group` (`"Entertainment: Film"` → `"Entertainment"`).
3. **Identifiant** `question_id` = `sha1(question + correct_answer)`, 12 premiers caractères, calculé sur le texte décodé, puis **dédoublonnage**.
4. **Options du QCM** : bonne et mauvaises réponses mélangées **une seule fois**, avec `question_id` comme graine. L'ordre est donc identique pour tous les modèles et tous les prompts, et la bonne réponse n'est pas toujours en A. Les vrai/faux sont présentés en `A. True / B. False`.
5. **Enrichissement** : `question_length_words`, `n_options`, `correct_letter`.
6. **Échantillon** `in_sample` : **300 questions**, stratifiées par catégorie × difficulté, graine 42. Ce sont les questions posées à tous les modèles.

**Résultat** : **5 296 questions** (3 doublons retirés), dont 300 dans l'échantillon. Le script vérifie le contrat avant d'écrire (unicité de `question_id`, valeurs autorisées, taille de l'échantillon, absence d'entités HTML) et s'arrête si une règle n'est pas respectée.

| Option | Effet |
|---|---|
| `--sample-size 500` | change la taille de l'échantillon (300 par défaut) |

### 4.3 Benchmark Ollama → silver

```bash
python src/enrichment/run_benchmark.py --models gemma3:4b
python src/enrichment/run_benchmark.py --models llama3.2:3b
```

**Sortie** : `data/silver/ai_responses/<modele>__<prompt_id>.parquet`, un fichier par modèle et par prompt (par exemple `llama3.2-3b__p3_mcq.parquet`), une ligne par question.

Pour chaque **modèle × prompt × question** de l'échantillon, le script :
1. construit le prompt (`src/enrichment/prompt.py`) ;
2. interroge le modèle via l'**API Python d'Ollama** (`ollama.chat`), avec `temperature = 0`, `seed = 42` et `num_predict = 64` ;
3. chronomètre l'appel côté Python → `response_time` (secondes) ;
4. interprète la réponse (`src/enrichment/scoring.py`) → `ai_answer`, `ai_correct`, `parse_ok` ;
5. enregistre la ligne, avec la réponse brute (`ai_answer_raw`), le prompt exact envoyé (`prompt_text`) et le nombre de tokens générés (`eval_count`).

Le premier appel à chaque modèle sert à le charger en mémoire et **n'est pas chronométré**, pour ne pas fausser `response_time`.

#### Les 4 prompts

| `prompt_id` | Principe | Format de réponse |
|---|---|---|
| `p1_open` | question brute, sans consigne | texte libre |
| `p2_constrained` | consigne « réponse courte uniquement » | texte libre court |
| `p3_mcq` | QCM avec options A-D, « réponds par la lettre » | lettre A-D |
| `p4_mcq_fewshot` | QCM + rôle système (« trivia expert ») + 2 exemples résolus | lettre A-D |

Les prompts sont en anglais, comme les questions OpenTDB : le modèle n'a pas à traduire, et les réponses restent comparables aux réponses attendues.

#### Calcul de `ai_correct`

- **QCM (p3, p4)** : extraction de la lettre (`B`, `B.`, `**B**`, `The answer is B`…), puis comparaison de l'option correspondante avec la bonne réponse. Si la réponse est illisible, `parse_ok = False`.
- **Réponse libre (p1, p2)** : texte normalisé (minuscules, sans accents, ponctuation ni articles). La réponse est juste si la bonne réponse y figure **et** qu'aucune mauvaise réponse n'y figure : un modèle qui cite plusieurs réponses n'est pas récompensé.
- Les blocs `<think>…</think>` des modèles « raisonneurs » sont ignorés.

Après toute modification du scoring : `python src/enrichment/check_scoring.py` (tests sur des réponses types de LLM).

#### Options

| Option | Effet |
|---|---|
| `--models llama3.2:3b gemma3:4b` | un ou plusieurs modèles Ollama |
| `--prompts p3_mcq p4_mcq_fewshot` | ne lance que ces prompts (par défaut : les 4) |
| `--limit 10` | ne traite que les 10 premières questions (pour tester) |

#### Reprise et interruption

- Les questions déjà traitées sans erreur sont ignorées : relancer la même commande **reprend là où le script s'était arrêté**. Les appels en erreur sont retentés.
- Les réponses sont sauvegardées toutes les 20 questions, et à l'interruption (Ctrl+C). Sous Windows, le Ctrl+C n'est pris en compte qu'à la fin de l'appel en cours : attendre quelques secondes.

#### Durée

Sur un PC portable sans GPU, il faut compter environ **1 à 2,5 s par question** pour les prompts QCM (p3, p4), qui ne génèrent qu'une lettre. Les prompts à réponse libre sont plus longs, et p1 est le plus lent. Pour 300 questions × 4 prompts, prévoir **1 à 2 heures par modèle**.

#### Choix de `num_predict = 64`

`num_predict` est le nombre maximum de tokens que le modèle peut générer pour une réponse. Il est fixé à 64 pour tous les appels.

**Pourquoi limiter** : sans limite, sur le prompt libre `p1_open`, une partie des réponses partent dans de longues explications. Mesures sur les premières réponses de `llama3.2:3b` sans limite :

| | p1_open | p3_mcq | p4_mcq_fewshot |
|---|---|---|---|
| tokens générés (médiane) | 24 | 3 | 2 |
| réponses > 64 tokens | 15 % (jusqu'à 232) | 0,7 % | 0 % |

- Les réponses de plus de 64 tokens représentaient environ la moitié du temps de calcul de `p1_open`. Avec `gemma3:4b`, sans limite, on mesurait près d'**une minute par question** sur `p1_open`.
- **La réponse arrive en début de texte** : le modèle donne en général sa réponse dans la première phrase, puis développe. Couper au-delà de 64 tokens (environ 45 à 50 mots) retire l'explication, pas la réponse.
- **Quasiment aucun effet sur les QCM**, qui génèrent 2 à 3 tokens.
- **Même règle pour tous** : la limite s'applique à tous les modèles et tous les prompts, la comparaison reste équitable.

*Limite connue* : une réponse coupée avant d'avoir donné la bonne réponse est comptée fausse. On peut repérer les réponses tronquées avec `eval_count = 64`.

### 4.4 Transformation dbt → gold

```bash
cd dbt_benchmark
dbt build --profiles-dir .      # construit les 10 modèles et exécute les 30 tests
cd ..
```

`dbt build` lit les parquet silver directement (via `read_parquet` de DuckDB), construit les tables dans `data/gold/benchmark.duckdb` et exécute les tests qualité. **À relancer après chaque nouveau benchmark** : les tables gold ne se mettent pas à jour toutes seules.

> Les commandes dbt se lancent **depuis `dbt_benchmark/`** : les chemins des sources (`../data/silver/...`) sont relatifs à ce dossier. Le profil de connexion est versionné dans le projet (`--profiles-dir .`), pour que tous les membres aient la même configuration.

#### Lignage

```
sources silver          STAGING                 INTERMEDIATE                     MARTS (gold)
questions_clean  ──►  stg_questions  ──┬──►  int_responses_enriched ──┬──►  mart_model_leaderboard
ai_responses/*   ──►  stg_ai_responses ┘            │                 ├──►  mart_accuracy_by_category
                                                    │                 ├──►  mart_accuracy_by_difficulty
                                                    │                 ├──►  mart_prompt_impact
                                                    │                 └──►  mart_response_log
                                                    └──► int_question_consensus ──► mart_question_difficulty
```

| Couche | Schéma DuckDB | Matérialisation | Rôle |
|---|---|---|---|
| staging | `staging` | table | Lecture et typage des parquet, renommage. Aucune règle métier |
| intermediate | `intermediate` | table | Jointure réponses × questions, colonnes calculées (`random_baseline`, `answer_length_words`, `answer_mode`), consensus par question |
| marts | `mart` | table | Une table = une question métier, lue par le dashboard |

La macro `macros/generate_schema_name.sql` fait que les schémas s'appellent `staging`, `intermediate` et `mart`, au lieu de `main_staging`, etc.

#### Les tables gold

| Table | Grain | Question métier |
|---|---|---|
| `mart_model_leaderboard` | modèle × prompt | Quel modèle et quel prompt répondent le mieux, et à quelle vitesse ? |
| `mart_accuracy_by_category` | modèle × prompt × catégorie | Sur quels thèmes chaque modèle est-il fort ou faible ? |
| `mart_accuracy_by_difficulty` | modèle × prompt × difficulté × type | La difficulté annoncée par OpenTDB se retrouve-t-elle chez les LLM ? |
| `mart_prompt_impact` | modèle × prompt | Quel gain apporte chaque prompt, à modèle constant (écart vs `p1_open`) ? |
| `mart_question_difficulty` | question | Difficulté officielle vs difficulté observée, questions ratées par tous |
| `mart_response_log` | modèle × prompt × question | Exploration détaillée des réponses |

Indicateurs principaux : `accuracy_pct`, `gain_vs_random_pts` (écart avec un modèle qui répondrait au hasard : 50 % en vrai/faux, 25 % en QCM), `avg_response_time_s`, `p95_response_time_s`, `parse_rate_pct`, `delta_vs_p1_pts`.

#### Tests qualité (30)

| Type | Exemples |
|---|---|
| Génériques dbt | `unique` et `not_null` sur les clés, `accepted_values` sur `difficulty`, `question_type`, `prompt_id`, `correct_letter`… |
| Intégrité | `relationships` : chaque réponse pointe vers une question existante |
| Générique maison | `unique_combination` : une seule réponse par modèle × prompt × question |
| Singuliers | aucune entité HTML restante, taille de l'échantillon entre 250 et 350, exactitude entre 0 et 100 % |

#### Documentation et lignage interactif

```bash
cd dbt_benchmark
dbt docs generate --profiles-dir .
dbt docs serve --profiles-dir .
```

#### Afficher les résultats en console

```bash
python src/analysis/show_results.py                 # tous les tableaux
python src/analysis/show_results.py classement      # un seul tableau
```

Tableaux disponibles : `classement`, `prompts`, `difficulte`, `categories`, `officiel_vs_observe`, `pieges`, `echantillon`.

### 4.5 Dashboard Streamlit

```bash
streamlit run app/streamlit_app.py
```

Le dashboard s'ouvre sur `http://localhost:8501`. Il lit **uniquement la couche gold** (schéma `mart`), en lecture seule : aucun calcul lourd n'est fait dans l'application, les agrégations sont faites par dbt.

| Onglet | Contenu |
|---|---|
| 🏆 Classement | Exactitude par modèle × prompt, avec **intervalle de confiance à 95 %** et ligne du hasard ; tableau détaillé |
| 📚 Catégories | Heatmap thème × modèle, par grand thème ou catégorie détaillée, avec un seuil minimal de questions |
| 🎚️ Difficulté | Exactitude facile → difficile ; QCM vs vrai/faux |
| ✍️ Prompts | Gain vs `p1_open`, longueur des réponses, respect du format |
| ⏱️ Temps de réponse | Compromis vitesse / exactitude ; temps des réponses justes vs fausses |
| 🪤 Questions pièges | Difficulté officielle vs observée ; questions ratées par tous |
| 🔎 Explorer | Toutes les réponses, avec filtres et recherche |

Filtres par modèle et par prompt dans la barre latérale. Chaque modèle garde la même couleur quels que soient les filtres. Après un nouveau `dbt build`, utiliser le bouton **🔄 Recharger les données**.

---

## 5. Méthodologie

| Choix | Justification |
|---|---|
| **Échantillon stratifié de 300 questions** (graine 42) | 300 × 4 prompts = 1 200 appels par modèle, soit 1 à 2 h sur un PC sans GPU. La stratification par catégorie × difficulté garde les proportions du dataset complet. La graine fixe garantit que **tous les modèles répondent aux mêmes questions** |
| **`temperature = 0`, `seed = 42`** | Réponses déterministes : le benchmark est reproductible |
| **Options QCM mélangées une seule fois** | La bonne réponse n'est pas toujours en A, et l'ordre est identique pour tous les modèles |
| **4 prompts de plus en plus cadrés** | Mesurer l'effet du prompt à modèle constant, comme demandé par le sujet |
| **`prompt_id` et `prompt_text` stockés** | Traçabilité : on sait exactement ce qui a été envoyé au modèle |
| **`num_predict = 64`** | Voir [4.3](#choix-de-num_predict--64) |
| **Premier appel non chronométré** | Le chargement du modèle en mémoire ne fausse pas `response_time` |
| **Baseline aléatoire** (`random_baseline = 1 / n_options`) | Distinguer ce que le modèle **sait** de ce qu'il obtient par chance |
| **Intervalle de confiance à 95 %** | Savoir quels écarts sont significatifs (environ ± 5,5 points sur 300 questions) |
| **Contrat de données** | Les deux membres du binôme développent en parallèle sur un format fixé à l'avance |
| **DuckDB** | Base analytique embarquée, sans serveur, qui lit directement le parquet |
| **dbt** | Transformations SQL versionnées, testées, documentées, avec un lignage explicite |

---

## 6. Résultats

2 modèles × 4 prompts × 300 questions = **2 400 réponses**.

| Modèle | Prompt | Exactitude | Gain vs hasard | Format respecté |
|---|---|---|---|---|
| llama3.2:3b | p4 · QCM + exemples | **67,7 %** | +39,1 pts | 100 % |
| llama3.2:3b | p3 · QCM | 63,7 % | +35,1 pts | 97 % |
| gemma3:4b | p4 · QCM + exemples | 62,3 % | +33,8 pts | 100 % |
| gemma3:4b | p3 · QCM | 62,0 % | +33,4 pts | 100 % |
| llama3.2:3b | p1 · question brute | 42,3 % | +13,8 pts | 100 % |
| llama3.2:3b | p2 · réponse courte | 41,3 % | +12,8 pts | 100 % |
| gemma3:4b | p1 · question brute | 40,0 % | +11,4 pts | 100 % |
| gemma3:4b | p2 · réponse courte | 38,7 % | +10,1 pts | 100 % |

### Principaux constats

1. **Le format QCM fait gagner 21 à 25 points** sur les deux modèles. C'est le résultat le plus solide : reconnaître la bonne réponse parmi 4 est bien plus facile que la retrouver de mémoire.
2. **Le plus petit modèle fait mieux** : `llama3.2:3b` devance `gemma3:4b` sur les 4 prompts. Seul l'écart sur p4 (+5,3 pts) est à la limite de la significativité ; les autres écarts restent dans la marge d'erreur.
3. **L'effet du few-shot dépend du modèle** : +4 points pour Llama, qui corrige surtout son format (97 % → 100 % de réponses lisibles) ; +0,3 point pour Gemma, qui respectait déjà le format, et pour qui p4 est 2,4 fois plus lent que p3 (prompt plus long à lire).
4. **Imposer une réponse courte (p2) n'aide pas** : légèrement en dessous de p1 chez les deux modèles. Une réponse longue a plus de chances de contenir la bonne réponse, et le scoring en réponse libre le récompense.
5. **La difficulté OpenTDB est respectée, mais imparfaitement** (Gemma, p4 : 72 % en facile, 59 % en moyen, 53 % en difficile). La correspondance question par question entre difficulté officielle et difficulté observée est faible.
6. **Forts sur les savoirs « académiques »** (sciences, géographie, culture générale), **faibles sur la pop culture de niche** (dessins animés, célébrités, mangas, télévision).
7. **Les LLM reproduisent les idées reçues humaines** : « Dracula est détruit par la lumière du soleil » (faux dans le roman de Bram Stoker) et « Rich Uncle Pennybags porte un monocle » (effet Mandela) sont ratées par tous les modèles avec tous les prompts.

---

## 7. Limites

- **Marge d'erreur** : ± 5,5 points environ (IC 95 %) sur 300 questions. Les petits écarts entre modèles ne sont pas significatifs.
- **Temps de réponse** : chaque modèle a tourné sur un PC différent. Les temps sont comparables **entre prompts d'un même modèle**, pas d'un modèle à l'autre.
- **Scoring des réponses libres** : indulgent avec les réponses longues ou vagues (par exemple « environ 19-25 ans » compté juste pour « 19 »). En réponse libre, `parse_ok` est vrai dès que la réponse n'est pas vide.
- **Troncature à 64 tokens** : une réponse coupée avant la bonne réponse est comptée fausse (repérable avec `eval_count = 64`).
- **Échantillon** : 300 questions sur 5 296. Les catégories rares ne comptent que 2 à 5 questions et ne sont pas interprétables seules (le dashboard propose un seuil minimal).
- **Questions en anglais uniquement**, telles que fournies par OpenTDB.

---

## 8. Organisation du projet

### Répartition du binôme

| Membre | Responsabilités |
|---|---|
| **[Prénom Nom du binôme]** | Ingestion (scraping OpenTDB), nettoyage silver, boucle de benchmark Ollama, benchmark `llama3.2:3b` |
| **Jeffrey Gandhi** | Contrat de données, prompts et scoring, projet dbt (staging, intermediate, marts, tests), dashboard Streamlit, benchmark `gemma3:4b` |

Le travail a avancé **par étapes communes**. À chaque étape, chacun prenait une moitié du travail, puis un point de synchronisation validait le résultat sur les deux machines avant de passer à la suite :

| Étape | Livrable | Validation |
|---|---|---|
| 0 | Contrat de données, environnement, Ollama | `ollama list` sur les deux PC, contrat mergé |
| 1 | Bronze + initialisation dbt | Même nombre de questions sur les deux PC, `dbt debug` OK |
| 2 | Silver (questions) + `stg_questions` | Tests dbt verts, mêmes chiffres d'échantillon |
| 3 | Prompts, scoring, benchmark | 8 fichiers de réponses, contrôle manuel de 20 réponses |
| 4 | Couche gold (dbt) | `dbt build` : 40 succès, 0 erreur |
| 5 | Dashboard Streamlit | 7 onglets fonctionnels |

### Workflow Git

- Une **branche par tâche** (`feat/scraping`, `feat/dbt-gold`, `data/gemma3-4b`…), jamais de développement direct sur `main`.
- Intégration par **Pull Request relue par l'autre membre**.
- Résultats des modèles poussés sur des branches `data/<modele>` : les noms de fichiers étant différents par modèle, aucun conflit possible.
- Versionnés : code, contrat, CSV bronze, parquet silver. Non versionnés : `.venv/`, `data/gold/*.duckdb` (régénéré par dbt), `dbt_benchmark/target/` et `logs/`.

---

## 9. Dépannage

| Problème | Solution |
|---|---|
| `DLL load failed … Une stratégie de contrôle d'application a bloqué ce fichier` (pandas, DuckDB) | Windows 11 : le **Contrôle intelligent des applications** bloque des librairies Python. Le désactiver dans *Sécurité Windows → Contrôle des applications et du navigateur* (Defender reste actif), puis recréer le `.venv` en Python 3.12 avec `pip install --no-cache-dir -r requirements.txt`. Alternative : WSL (Ubuntu) |
| Erreurs aléatoires de fichiers manquants dans `.venv` | Le projet est dans OneDrive : le déplacer hors de OneDrive (par exemple `C:\dev\`) |
| `No dbt_project.yml found` | Lancer dbt depuis `dbt_benchmark/` |
| `No files found that match the pattern "../data/silver/..."` | Les parquet silver ne sont pas présents (`git pull`) ou dbt n'est pas lancé depuis `dbt_benchmark/` |
| `schema "mart" does not exist` | Lancer `dbt build --profiles-dir .` ; vérifier que `models/intermediate` et `models/marts` sont bien à côté de `models/staging`, pas dedans |
| `Modèles absents : [...]` | Utiliser le nom exact affiché par `ollama list`, ou `ollama pull <modele>` |
| Ollama ne répond pas | Lancer l'application Ollama |
| Benchmark très lent (> 30 s par question) | Vérifier `num_predict = 64` ; fermer les applications lourdes ; choisir un modèle plus petit |
| `python -c "..."` échoue sous PowerShell | PowerShell gère mal les guillemets imbriqués : utiliser `src/analysis/show_results.py` |
| Le dashboard n'affiche pas les dernières données | Relancer `dbt build`, puis cliquer sur **🔄 Recharger les données** |
