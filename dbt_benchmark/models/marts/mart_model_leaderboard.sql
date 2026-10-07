-- MART (gold) : « Quel modèle et quel prompt répondent le mieux, et à quelle vitesse ? »
-- Grain : 1 ligne = 1 modèle x 1 prompt.

select
    model,
    prompt_id,
    answer_mode,
    count(*)                                             as n_questions,
    round(100 * avg(ai_correct::int), 2)                 as accuracy_pct,
    round(100 * avg(random_baseline), 2)                 as random_baseline_pct,
    round(100 * (avg(ai_correct::int) - avg(random_baseline)), 2)
                                                         as gain_vs_random_pts,
    round(avg(response_time), 3)                         as avg_response_time_s,
    round(median(response_time), 3)                      as median_response_time_s,
    round(quantile_cont(response_time, 0.95), 3)         as p95_response_time_s,
    round(100 * avg(parse_ok::int), 2)                   as parse_rate_pct,
    round(avg(answer_length_words), 1)                   as avg_answer_words,
    sum(has_error::int)                                  as n_errors,
    rank() over (order by avg(ai_correct::int) desc)     as rank_accuracy
from {{ ref('int_responses_enriched') }}
group by model, prompt_id, answer_mode