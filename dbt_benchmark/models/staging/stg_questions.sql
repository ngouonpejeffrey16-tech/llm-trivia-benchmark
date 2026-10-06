-- STAGING : lecture typée des questions nettoyées (couche silver).
-- Règle du staging : on renomme et on type, mais on n'applique AUCUNE règle métier.

with source as (

    select * from {{ source('silver', 'questions_clean') }}

)

select
    question_id,
    cast(category_id as integer) as category_id,
    category,
    category_group,
    type as question_type,
    difficulty,
    case difficulty
        when 'easy'   then 1
        when 'medium' then 2
        when 'hard'   then 3
    end as difficulty_rank,
    question,
    correct_answer,
    incorrect_answers,
    options,
    correct_letter,
    cast(n_options as integer) as n_options,
    cast(question_length_words as integer) as question_length_words,
    cast(in_sample as boolean) as in_sample
from source