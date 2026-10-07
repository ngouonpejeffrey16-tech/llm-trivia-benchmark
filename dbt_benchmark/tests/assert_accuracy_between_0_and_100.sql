-- Test singulier : une exactitude est forcément comprise entre 0 et 100 %.
select model, prompt_id, accuracy_pct
from {{ ref('mart_model_leaderboard') }}
where accuracy_pct < 0 or accuracy_pct > 100