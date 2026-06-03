{% test accepted_range(model, column_name, min_value=none, max_value=none) %}
{#
  Generic test: fails (returns rows) when column_name falls outside [min_value, max_value].
  NULL values are skipped — use a separate not_null test if nulls must be forbidden.
  Used instead of dbt_utils.accepted_range to avoid adding a dependency.
#}
SELECT {{ column_name }}
FROM   {{ model }}
WHERE  {{ column_name }} IS NOT NULL
  AND (
        {% if min_value is not none %} {{ column_name }} < {{ min_value }} {% else %} FALSE {% endif %}
        OR
        {% if max_value is not none %} {{ column_name }} > {{ max_value }} {% else %} FALSE {% endif %}
      )
{% endtest %}
