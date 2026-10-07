-- MART (gold) : « Quelles questions piègent les modèles ? »
-- Compare la difficulté officielle OpenTDB à la difficulté observée chez les LLM.
-- Grain : 1 ligne = 1 question.

select
    q.question_id,
    q.category,
    q.difficulty                            as official_difficulty,
    q.question_type,
    q.question,
    q.correct_answer,
    c.n_attempts,
    c.n_models,
    round(100 * c.pct_correct, 2)           as pct_correct,
    case
        when c.pct_correct >= 0.75 then 'facile'
        when c.pct_correct >= 0.40 then 'moyenne'
        else 'difficile'
    end                                     as observed_difficulty,
    c.failed_by_all,
    c.solved_by_all
from {{ ref('int_question_consensus') }} c
inner join {{ ref('stg_questions') }} q using (question_id)