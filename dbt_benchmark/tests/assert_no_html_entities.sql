-- Test singulier : le nettoyage silver doit avoir décodé TOUTES les entités HTML.
-- Le test échoue si cette requête renvoie au moins une ligne.
select question_id, question, correct_answer
from {{ ref('stg_questions') }}
where regexp_matches(question, '&(quot|amp|#039|lt|gt|eacute|rsquo|ldquo|rdquo);')
   or regexp_matches(correct_answer, '&(quot|amp|#039|lt|gt|eacute|rsquo|ldquo|rdquo);')