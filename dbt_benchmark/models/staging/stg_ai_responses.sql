-- STAGING : réponses brutes des modèles (couche silver), typées.
-- Grain : 1 ligne = 1 modèle x 1 prompt x 1 question.

with source as (

    select * from {{ source('silver', 'ai_responses') }}

)

select
    run_id,
    model,
    prompt_id,
    prompt_text,
    question_id,
    ai_answer_raw,
    ai_answer,
    cast(ai_correct as boolean)        as ai_correct,
    cast(parse_ok as boolean)          as parse_ok,
    cast(response_time as double)      as response_time,
    cast(eval_count as integer)        as eval_count,
    cast(temperature as double)        as temperature,
    error,
    error is not null                  as has_error,
    cast(created_at as timestamp)      as created_at
from source