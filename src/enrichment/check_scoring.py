"""
Auto-test du scoring : vérifie que ai_correct est calculé correctement
sur des réponses typiques de LLM. À lancer après chaque modification de scoring.py :
    python src/enrichment/check_scoring.py
"""
from scoring import score

QCM = {"type": "multiple", "correct_answer": "Leonardo da Vinci",
       "incorrect_answers": ["Michelangelo", "Raphael", "Donatello"],
       "options": ["Michelangelo", "Leonardo da Vinci", "Raphael", "Donatello"]}   # bonne = B
VF = {"type": "boolean", "correct_answer": "False", "incorrect_answers": ["True"],
      "options": ["True", "False"]}                                                 # bonne = B

CASES = [
    # (réponse brute du modèle, question, format, ai_correct attendu, parse_ok attendu)
    ("B", QCM, "letter", True, True),
    ("B.", QCM, "letter", True, True),
    ("**B**", QCM, "letter", True, True),
    ("The answer is B", QCM, "letter", True, True),
    ("Leonardo da Vinci", QCM, "letter", True, True),            # a recopié l'option
    ("A", QCM, "letter", False, True),
    ("<think>hmm...</think>B", QCM, "letter", True, True),       # modèle qui raisonne
    ("I don't know", QCM, "letter", False, False),               # illisible
    ("Leonardo da Vinci", QCM, "free", True, True),
    ("It was painted by Leonardo da Vinci.", QCM, "free", True, True),
    ("leonardo DA vinci", QCM, "free", True, True),              # casse
    ("Michelangelo", QCM, "free", False, True),
    ("Leonardo da Vinci or Michelangelo", QCM, "free", False, True),   # cite 2 réponses
    ("False", VF, "free", True, True),
    ("False. The Great Wall is not visible.", VF, "free", True, True),
    ("No", VF, "free", True, True),
    ("True", VF, "free", False, True),
    ("B", VF, "letter", True, True),
]

errors = 0
for raw, q, fmt, exp_correct, exp_parse in CASES:
    r = score(raw, q, fmt)
    ok = r["ai_correct"] == exp_correct and r["parse_ok"] == exp_parse
    errors += not ok
    print(f"{'OK ' if ok else 'ERR'}  [{fmt:6}] {raw!r:45} -> correct={r['ai_correct']!s:5} parse_ok={r['parse_ok']}")
print(f"\n{len(CASES) - errors}/{len(CASES)} cas corrects")
raise SystemExit(1 if errors else 0)