"""
Interprétation des réponses brutes du modèle -> ai_answer, ai_correct, parse_ok.

Règles (documentées dans docs/data_contract.md) :
  - prompts QCM (p3, p4) : on extrait la lettre A-D, puis l'option correspondante.
  - prompts libres (p1, p2) : texte normalisé (minuscules, sans accents, sans
    ponctuation, sans articles). La réponse est juste si la bonne réponse y figure
    ET qu'aucune mauvaise réponse n'y figure (un modèle qui "cite tout" ne gagne pas).
  - parse_ok = False quand la réponse n'a pas pu être interprétée.
"""
import re
import unicodedata

LETTERS = "ABCD"
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def strip_reasoning(text):
    """Retire les blocs <think>...</think> des modèles qui « réfléchissent » (qwen3, deepseek-r1...)."""
    return _THINK.sub("", text or "").strip()


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    text = re.sub(r"\b(the|a|an)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def contains(haystack, needle):
    """True si `needle` apparaît comme mot(s) entier(s) dans `haystack` (déjà normalisés)."""
    return bool(needle) and re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None


def parse_letter(raw, options):
    """Retourne l'option choisie (texte) ou None si illisible."""
    valid = LETTERS[:len(options)]
    text = raw.strip()
    m = re.match(rf"^\W*([{valid}])(?:\W|$)", text)                        # "B", "B.", "(B)", "**B**"
    if not m:
        m = re.search(rf"\b(?:answer|option)\s*(?:is|:)?\s*\(?([{valid}])\b", text, re.I)  # "The answer is B"
    if m:
        return options[valid.index(m.group(1).upper())]
    # repli : le modèle a recopié le texte d'une option au lieu de la lettre
    norm = normalize(text)
    hits = [o for o in options if contains(norm, normalize(o))]
    return hits[0] if len(hits) == 1 else None


def parse_free(raw, q):
    """Retourne (ai_answer, ai_correct) pour une réponse libre."""
    norm = normalize(raw)
    if q["type"] == "boolean":
        first = norm.split(" ")[0] if norm else ""
        mapping = {"true": "True", "yes": "True", "false": "False", "no": "False"}
        answer = mapping.get(first)
        if answer is None:
            has_true, has_false = contains(norm, "true"), contains(norm, "false")
            if has_true != has_false:
                answer = "True" if has_true else "False"
        return (answer or raw.strip()), answer == q["correct_answer"]

    good = contains(norm, normalize(q["correct_answer"]))
    bad = any(contains(norm, normalize(w)) for w in q["incorrect_answers"])
    return raw.strip(), good and not bad


def score(raw, q, answer_format):
    """Point d'entrée : retourne un dict {ai_answer, ai_correct, parse_ok}."""
    raw = strip_reasoning(raw)
    if answer_format == "letter":
        answer = parse_letter(raw, list(q["options"]))
        return {"ai_answer": answer if answer is not None else raw,
                "ai_correct": answer == q["correct_answer"],
                "parse_ok": answer is not None}
    answer, correct = parse_free(raw, q)
    return {"ai_answer": answer, "ai_correct": bool(correct), "parse_ok": bool(raw)}