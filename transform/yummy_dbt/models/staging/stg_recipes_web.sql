-- stg_recipes_web.sql — Recettes web FR (Marmiton/750g). Catalogue + satisfaction (notes).
-- Le JSON Bronze a la forme {site, extracted_at, count, recipes:[...]}.
-- On déplie la liste recipes (1 ligne par recette) via UNNEST.
-- Colonnes alignées sur stg_recipes (Kaggle) pour permettre un UNION en aval.
WITH source AS (
    SELECT
        site            AS source_site,
        extracted_at,
        UNNEST(recipes) AS r          -- déplie : une ligne par recette
    FROM {{ source('minio_bronze', 'raw_recipes_web') }}
),

renamed AS (
    SELECT
        r.recipe_id                     AS recipe_id,        -- VARCHAR (slug FR)
        source_site                     AS site,
        LOWER(TRIM(r.title))            AS recipe_name,
        r.url                           AS url,
        r.total_time                    AS total_minutes,
        r.prep_time                     AS prep_minutes,
        r.cook_time                     AS cook_minutes,
        r.yields                        AS yields,
        r.ingredients                   AS ingredients,      -- déjà VARCHAR[]
        len(r.ingredients)              AS n_ingredients,
        r.instructions                  AS instructions,
        r.category                      AS category,
        r.cuisine                       AS cuisine,
        r.ratings                       AS rating,           -- note (DOUBLE, peut être NULL)
        r.image                         AS image_url,
        extracted_at                    AS extracted_at
    FROM source
)

SELECT * FROM renamed
WHERE recipe_id IS NOT NULL
  AND recipe_name IS NOT NULL