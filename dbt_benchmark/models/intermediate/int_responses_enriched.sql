-- INTERMEDIATE : chaque réponse IA enrichie du contexte de sa question.
-- C'est la table de référence sur laquelle s'appuient toutes les marts.
-- Grain : 1 ligne = 1 modèle x 1 prompt x 1 question.

with responses as (
    select * from {{ ref('stg_ai_responses') }}
),

questions as (
    select * from {{ ref('stg_questions') }}
)

select
    r.model,
    r.prompt_id,
    case when r.prompt_id in ('p3_mcq', 'p4_mcq_fewshot') then 'qcm' else 'libre' end
                                                    as answer_mode,
    r.question_id,
    q.category,
    q.category_group,
    q.question_type,
    q.difficulty,
    q.difficulty_rank,
    q.question,
    q.correct_answer,
    q.n_options,
    q.question_length_words,
    1.0 / q.n_options                               as random_baseline,   -- score d'un modèle qui répondrait au hasard
    r.ai_answer_raw,
    r.ai_answer,
    r.ai_correct,
    r.parse_ok,
    r.has_error,
    r.response_time,
    r.eval_count,
    len(string_split(trim(coalesce(r.ai_answer_raw, '')), ' '))
                                                    as answer_length_words,
    r.created_at
from responses r
inner join questions q using (question_id)