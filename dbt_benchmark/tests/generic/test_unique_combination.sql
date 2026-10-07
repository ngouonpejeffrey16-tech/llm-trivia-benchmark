{#
  Test générique maison : vérifie qu'une combinaison de colonnes est unique.
  Ex. : une même question ne doit avoir qu'UNE réponse par modèle et par prompt.
#}
{% test unique_combination(model, columns) %}
select {{ columns | join(', ') }}, count(*) as n_lignes
from {{ model }}
group by {{ columns | join(', ') }}
having count(*) > 1
{% endtest %}