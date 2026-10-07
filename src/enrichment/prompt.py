"""
Catalogue des 4 variantes de prompt du benchmark (standardisées et versionnées).

Chaque variante a un identifiant stable (prompt_id) enregistré dans le dataset :
on peut ainsi comparer leur impact dans la couche gold.

  p1_open         question brute, réponse libre                 -> référence "naïve"
  p2_constrained  consigne : réponse courte uniquement           -> réponse libre mais cadrée
  p3_mcq          QCM avec options A/B/C/D, réponse = une lettre
  p4_mcq_fewshot  p3 + rôle système + 2 exemples (few-shot)      -> version optimisée

Les questions OpenTDB sont en anglais : les prompts sont donc en anglais,
pour que le modèle ne traduise pas (et ne déforme pas) les réponses attendues.
"""

LETTERS = "ABCD"

# prompt_id -> (description, format de réponse attendu)
VARIANTS = {
    "p1_open":        ("Question brute, réponse libre", "free"),
    "p2_constrained": ("Réponse courte imposée", "free"),
    "p3_mcq":         ("QCM, répondre par la lettre", "letter"),
    "p4_mcq_fewshot": ("QCM + rôle système + exemples", "letter"),
}

SYSTEM_EXPERT = (
    "You are a trivia expert taking a quiz. "
    "Reply with a single capital letter (A, B, C or D) and nothing else. "
    "No explanation, no punctuation."
)

# 2 exemples résolus montrés au modèle avant la vraie question (few-shot)
FEW_SHOT = [
    ("Question: What is the chemical symbol for gold?\n"
     "A. Ag\nB. Au\nC. Gd\nD. Go\nAnswer:", "B"),
    ("Statement: The Great Wall of China is visible from the Moon with the naked eye.\n"
     "A. True\nB. False\nAnswer:", "B"),
]


def _options_block(options):
    return "\n".join(f"{LETTERS[i]}. {opt}" for i, opt in enumerate(options))


def _header(q):
    label = "Statement" if q["type"] == "boolean" else "Question"
    return f"{label}: {q['question']}"


def build_messages(prompt_id, q):
    """Construit la liste de messages (format chat Ollama) pour une question."""
    if prompt_id == "p1_open":
        text = q["question"]
        if q["type"] == "boolean":
            text += " (True or False?)"
        return [{"role": "user", "content": text}]

    if prompt_id == "p2_constrained":
        if q["type"] == "boolean":
            rule = "Answer only with True or False. No explanation."
        else:
            rule = "Answer with the exact answer only (a few words at most). No sentence, no explanation."
        return [{"role": "user", "content": f"{rule}\n{_header(q)}\nAnswer:"}]

    body = f"{_header(q)}\n{_options_block(list(q['options']))}\nAnswer:"

    if prompt_id == "p3_mcq":
        return [{"role": "user", "content": "Answer with the letter of the correct option only.\n" + body}]

    if prompt_id == "p4_mcq_fewshot":
        messages = [{"role": "system", "content": SYSTEM_EXPERT}]
        for user, assistant in FEW_SHOT:
            messages.append({"role": "user", "content": user})
            messages.append({"role": "assistant", "content": assistant})
        messages.append({"role": "user", "content": body})
        return messages

    raise ValueError(f"prompt_id inconnu : {prompt_id}")


def render(messages):
    """Version texte du prompt, stockée dans la colonne prompt_text (traçabilité)."""
    return "\n".join(f"[{m['role']}] {m['content']}" for m in messages)