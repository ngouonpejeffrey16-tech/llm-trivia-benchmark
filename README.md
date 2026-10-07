# LLM Trivia Benchmark

Benchmark de modèles de langage locaux (via Ollama) sur les questions de culture
générale d'[Open Trivia Database](https://opentdb.com), avec une architecture
médaillon (bronze → silver → gold), dbt et un dashboard Streamlit.

Le format de chaque fichier produit est défini dans le
[contrat de données](docs/data_contract.md).

```
OpenTDB ──scrape_opentdb.py──► bronze/questions_raw.csv
                                   │ clean_questions.py
                                   ▼
                           silver/questions_clean.parquet
                                   │ run_benchmark.py (Ollama)
                                   ▼
                           silver/ai_responses/<modele>__<prompt>.parquet
                                   │ dbt
                                   ▼
                           gold/benchmark.duckdb ──► Streamlit
```

---

## Prérequis

- **Python 3.12**
- **Ollama** pour exécuter les modèles en local
- un accès internet qui laisse passer `opentdb.com` en HTTPS (scraping uniquement)

### Environnement Python

Depuis la racine du projet :

```powershell
python -m venv .venv
.venv\Scripts\activate          # Windows (macOS / Linux : source .venv/bin/activate)
pip install -r requirements.txt
```

### Ollama

1. Installer Ollama :
   - Windows : `irm https://ollama.com/install.ps1 | iex` dans PowerShell, ou l'installeur de [ollama.com/download](https://ollama.com/download)
   - macOS / Linux : voir [ollama.com/download](https://ollama.com/download)
2. Télécharger les modèles du benchmark :
   ```powershell
   ollama pull llama3.2:3b
   ollama pull gemma3:4b
   ```
3. Vérifier qu'Ollama tourne et que les modèles sont présents :
   ```powershell
   ollama list
   ```

Ollama doit rester lancé pendant tout le benchmark (icône dans la barre des tâches
sous Windows). Le script s'arrête avec un message clair si Ollama ne répond pas ou
si un modèle n'est pas installé.

---

## 1. Ingestion : scraping d'OpenTDB → bronze

```powershell
python src/ingestion/scrape_opentdb.py
```

**Sortie :** `data/bronze/questions_raw.csv`, une ligne par question, telle que
renvoyée par l'API (aucune transformation, entités HTML conservées).

**Fonctionnement :**

- OpenTDB ne demande **pas de clé d'API**. Le script demande un **session token**
  (`api_token.php`) : avec ce token, l'API ne renvoie jamais deux fois la même question,
  ce qui permet de récupérer tout le dataset sans doublon.
- Pour chacune des 24 catégories (id 9 à 32), il lit le nombre de questions
  (`api_count.php`) puis les télécharge par lots de 50, le maximum autorisé.
- L'API limite à **1 requête toutes les 5 secondes par IP** : le script attend entre
  chaque appel et réessaie automatiquement en cas d'erreur 429 ou de coupure réseau.
- Le CSV est écrit après chaque catégorie. **Si le script s'arrête, il suffit de le
  relancer** : les catégories déjà présentes dans le fichier sont ignorées.

**Résultat attendu : 5 299 questions**, soit toutes les questions *vérifiées* d'OpenTDB.
Le site en affiche environ 21 000 au total, mais les questions en attente de validation
ou rejetées ne sont pas accessibles par l'API.

**Durée :** environ 25 minutes, à cause de la limite de l'API.

| Option | Effet |
|---|---|
| `--categories 9 18` | ne scrape que ces catégories |
| `--restart` | ignore le CSV existant et repart de zéro |

> **Réseau d'école / d'entreprise :** certains proxys (par ex. Cato Networks)
> interceptent le HTTPS et provoquent une erreur `CERTIFICATE_VERIFY_FAILED`. Le script
> s'arrête alors avec un message explicite : changer de réseau (partage de connexion)
> et relancer, il reprend là où il s'était arrêté.

---

## 2. Nettoyage : bronze → silver

```powershell
python src/processing/clean_questions.py
```

**Sortie :** `data/silver/questions_clean.parquet`, une ligne par question unique.

**Étapes :**

1. **Décodage** des entités HTML (`&quot;` → `"`, `&#039;` → `'`) et normalisation des
   espaces (espaces insécables, espaces multiples).
2. **Normalisation** de `type` et `difficulty`, et création de `category_group`
   (`"Entertainment: Film"` → `"Entertainment"`).
3. **Identifiant** `question_id` = `sha1(question + correct_answer)`, 12 premiers
   caractères, calculé sur le texte décodé, puis **dédoublonnage**.
4. **Options du QCM** : bonne et mauvaises réponses mélangées une seule fois, avec
   `question_id` comme graine. L'ordre est donc identique pour tous les modèles et tous
   les prompts, et la bonne réponse n'est pas toujours en A. Les vrai/faux sont
   présentés en `A. True / B. False`.
5. **Enrichissement** : `question_length_words`.
6. **Échantillon** `in_sample` : 300 questions, stratifiées par catégorie × difficulté,
   graine 42. Ce sont les questions posées à tous les modèles.

**Résultat :** 5 296 questions (3 doublons retirés), dont 300 dans l'échantillon.
Le script vérifie le contrat avant d'écrire (unicité de `question_id`, valeurs
autorisées, taille de l'échantillon, absence d'entités HTML) et s'arrête si une règle
n'est pas respectée.

| Option | Effet |
|---|---|
| `--sample-size 500` | change la taille de l'échantillon (300 par défaut) |

---

## 3. Benchmark avec Ollama → silver

```powershell
python src/enrichment/run_benchmark.py --models llama3.2:3b
```

**Sortie :** `data/silver/ai_responses/<modele>__<prompt_id>.parquet`, un fichier par
modèle et par prompt (ex. `llama3.2-3b__p3_mcq.parquet`), une ligne par question.

**Pour chaque modèle × prompt × question de l'échantillon, le script :**

1. construit le prompt (`src/enrichment/prompt.py`) ;
2. interroge le modèle via l'**API Python d'Ollama** (`ollama.chat`), avec
   `temperature = 0` et `seed = 42` pour des réponses reproductibles ;
3. **chronomètre** l'appel côté Python → `response_time` (secondes) ;
4. interprète la réponse (`src/enrichment/scoring.py`) → `ai_answer`, `ai_correct`,
   `parse_ok` ;
5. enregistre la ligne, avec la réponse brute (`ai_answer_raw`), le prompt exact envoyé
   (`prompt_text`) et le nombre de tokens générés (`eval_count`).

Le premier appel à chaque modèle sert à le charger en mémoire et **n'est pas
chronométré**, pour ne pas fausser `response_time`.

### Les 4 prompts

| `prompt_id` | Principe | Format de réponse |
|---|---|---|
| `p1_open` | question brute | texte libre |
| `p2_constrained` | consigne « réponse courte uniquement » | texte libre court |
| `p3_mcq` | QCM, répondre par la lettre | lettre A-D |
| `p4_mcq_fewshot` | QCM + rôle système + 2 exemples résolus | lettre A-D |

Les règles de calcul de `ai_correct` sont détaillées dans le
[contrat de données](docs/data_contract.md). Pour vérifier le scoring après une
modification : `python src/enrichment/check_scoring.py`.

### Options

| Option | Effet |
|---|---|
| `--models llama3.2:3b gemma3:4b` | un ou plusieurs modèles Ollama |
| `--prompts p3_mcq p4_mcq_fewshot` | ne lance que ces prompts (par défaut : les 4) |
| `--limit 10` | ne traite que les 10 premières questions (pour tester) |

### Reprise et interruption

- Les questions déjà traitées sans erreur sont ignorées : **relancer la même commande
  reprend là où le script s'était arrêté**. Les appels en erreur sont retentés.
- Les réponses sont sauvegardées toutes les 20 questions, et à l'interruption
  (`Ctrl+C`). Sous Windows, le `Ctrl+C` n'est pris en compte qu'à la fin de l'appel en
  cours : attendre quelques secondes.

### Durée

Sur un PC portable sans GPU, avec `llama3.2:3b`, il faut compter environ **2,5 s par
question** pour les prompts QCM (p3, p4), qui ne génèrent qu'une lettre. Les prompts à
réponse libre sont plus longs : p1_open est le plus lent, car le modèle répond par des
phrases. Pour 300 questions × 4 prompts, prévoir **1 à 2 heures par modèle**.

### Choix de `num_predict = 64`

`num_predict` est le nombre maximum de tokens que le modèle peut générer pour une
réponse. Nous l'avons fixé à **64** pour tous les appels :

```python
options={"temperature": 0, "seed": 42, "num_predict": 64}
```

**Pourquoi limiter :** sans limite, sur le prompt libre `p1_open`, une partie des
réponses partent dans de longues explications. Mesures sur nos premières réponses de
`llama3.2:3b` sans limite :

| | p1_open | p3_mcq | p4_mcq_fewshot |
|---|---|---|---|
| tokens générés (médiane) | 24 | 3 | 2 |
| réponses > 64 tokens | 15 % (jusqu'à 232) | 0,7 % | 0 % |

- Les réponses de plus de 64 tokens représentaient environ **la moitié du temps de
  calcul** de `p1_open`. La limite fait gagner environ 25 à 30 % sur ce prompt, et
  évite qu'une seule réponse qui « déraille » bloque le benchmark.
- **La réponse arrive en début de texte :** en général, le modèle donne sa réponse dans
  la première phrase, puis développe. Couper au-delà de 64 tokens (environ 45 à 50 mots)
  retire l'explication, pas la réponse.
- **Quasiment aucun effet sur les QCM :** p3 et p4 génèrent 2 à 3 tokens. La limite
  n'est atteinte que par 0,7 % des réponses p3, quand le modèle explique au lieu de
  donner la lettre.
- **Même règle pour tous :** la limite s'applique à tous les modèles et tous les prompts,
  la comparaison reste équitable.

**Limite connue :** une réponse coupée avant d'avoir donné la bonne réponse est comptée
fausse. On peut repérer les réponses tronquées avec `eval_count = 64`.

---

## 4. Transformation dbt → gold

*À compléter.*

## 5. Dashboard Streamlit

*À compléter.*
