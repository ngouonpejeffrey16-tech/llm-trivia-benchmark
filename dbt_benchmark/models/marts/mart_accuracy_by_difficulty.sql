-- MART (gold) : « La difficulté annoncée par OpenTDB se retrouve-t-elle chez les LLM ? »
-- Grain : 1 ligne = 1 modèle x 1 prompt x 1 difficulté x 1 type de question.

select
    model,
    prompt_id,
    difficulty,
    difficulty_rank,
    question_type,
    count(*)                                as n_questions,
    round(100 * avg(ai_correct::int), 2)    as accuracy_pct,
    round(100 * avg(random_baseline), 2)    as random_baseline_pct,
    round(avg(response_time), 3)            as avg_response_time_s
from {{ ref('int_responses_enriched') }}
group by model, prompt_id, difficulty, difficulty_rank, question_type