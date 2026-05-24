-- stg_recipes.sql — Catalogue de recettes Food.com (anglais).
-- Les champs tags/ingredients/steps sont des listes Python sérialisées en texte
-- (ex: "['butter', 'sugar']"). On les convertit en VRAIES listes DuckDB pour
-- pouvoir les exploiter en aval (compter, filtrer, exploser). Le parsing fin
-- (ex: matcher les ingrédients sur CIQUAL) reste pour la couche intermediate.
WITH source AS (
    SELECT * FROM {{ source('minio_bronze', 'raw_recipes') }}
)

SELECT
    CAST(id AS BIGINT)              AS recipe_id,
    LOWER(TRIM(name))              AS recipe_name,
    CAST(minutes AS INTEGER)       AS total_minutes,
    CAST(submitted AS DATE)        AS submitted_at,
    CAST(n_steps AS INTEGER)       AS n_steps,
    CAST(n_ingredients AS INTEGER) AS n_ingredients,
    TRIM(description)              AS description,
    -- Listes Python "['a','b']" -> liste DuckDB. On nettoie crochets et quotes,
    -- puis split sur la virgule. C'est de la conversion de FORMAT (liste lisible),
    -- pas de la transformation métier.
    string_split(
        REPLACE(REPLACE(REPLACE(TRIM(ingredients), '[', ''), ']', ''), '''', ''),
        ', '
    ) AS ingredients,
    string_split(
        REPLACE(REPLACE(REPLACE(TRIM(tags), '[', ''), ']', ''), '''', ''),
        ', '
    ) AS tags,
    nutrition AS nutrition_raw      -- liste de 7 valeurs, parsée en intermediate
FROM source
WHERE id IS NOT NULL
  AND name IS NOT NULL