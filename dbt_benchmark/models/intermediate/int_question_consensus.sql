-- INTERMEDIATE : difficulté "observée" de chaque question,
-- mesurée par le taux de réussite de tous les modèles et prompts réunis.
-- Grain : 1 ligne = 1 question.

select
    question_id,
    count(*)                        as n_attempts,
    count(distinct model)           as n_models,
    sum(ai_correct::int)            as n_correct,
    avg(ai_correct::int)            as pct_correct,
    bool_and(not ai_correct)        as failed_by_all,
    bool_and(ai_correct)            as solved_by_all
from {{ ref('int_responses_enriched') }}
where not has_error
group by question_id