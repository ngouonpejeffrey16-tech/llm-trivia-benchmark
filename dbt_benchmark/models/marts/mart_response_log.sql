-- MART (gold) : journal détaillé des réponses, pour l'exploration dans le dashboard.
-- Grain : 1 ligne = 1 modèle x 1 prompt x 1 question.

select
    model,
    prompt_id,
    question_id,
    category,
    difficulty,
    question_type,
    question,
    correct_answer,
    ai_answer,
    ai_answer_raw,
    ai_correct,
    parse_ok,
    has_error,
    response_time,
    answer_length_words
from {{ ref('int_responses_enriched') }}