{% macro ciqual_num(col) %}
    CAST(
        CASE
            WHEN TRIM({{ col }}) IN ('-', '', 'traces') THEN NULL
            ELSE
                -- Retire le '<' (borne de détection) puis tout caractère non
                -- numérique de tête (espace, newline), normalise la virgule FR.
                NULLIF(
                    TRIM(
                        REPLACE(
                            REGEXP_REPLACE(TRIM({{ col }}), '^<\s*', ''),
                            ',', '.'
                        )
                    ),
                    ''
                )
        END AS DOUBLE
    )
{% endmacro %}