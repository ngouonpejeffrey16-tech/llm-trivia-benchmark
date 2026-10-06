-- Test singulier : l'échantillon du benchmark doit contenir entre 250 et 350 questions.
select count(*) as n_in_sample
from {{ ref('stg_questions') }}
where in_sample
having count(*) not between 250 and 350