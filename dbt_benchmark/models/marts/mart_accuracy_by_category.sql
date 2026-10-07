-- MART (gold) : « Sur quels thèmes chaque modèle est-il fort ou faible ? »
-- Grain : 1 ligne = 1 modèle x 1 prompt x 1 catégorie.

select
    model,
    prompt_id,
    category_group,
    category,
    count(*)                                as n_questions,
    round(100 * avg(ai_correct::int), 2)    as accuracy_pct,
    round(avg(response_time), 3)            as avg_response_time_s
from {{ ref('int_responses_enriched') }}
group by model, prompt_id, category_group, category