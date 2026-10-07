-- MART (gold) : « Quel est l'effet du prompt, à modèle constant ? »
-- Le gain est mesuré par rapport au prompt de référence p1_open.
-- Grain : 1 ligne = 1 modèle x 1 prompt.

with by_prompt as (

    select
        model,
        prompt_id,
        count(*)                    as n_questions,
        avg(ai_correct::int)        as accuracy,
        avg(response_time)          as avg_time,
        avg(answer_length_words)    as avg_words,
        avg(parse_ok::int)          as parse_rate
    from {{ ref('int_responses_enriched') }}
    group by model, prompt_id

)

select
    model,
    prompt_id,
    n_questions,
    round(100 * accuracy, 2)                                    as accuracy_pct,
    round(100 * (accuracy - max(case when prompt_id = 'p1_open' then accuracy end)
                            over (partition by model)), 2)      as delta_vs_p1_pts,
    round(avg_time, 3)                                          as avg_response_time_s,
    round(avg_words, 1)                                         as avg_answer_words,
    round(100 * parse_rate, 2)                                  as parse_rate_pct
from by_prompt