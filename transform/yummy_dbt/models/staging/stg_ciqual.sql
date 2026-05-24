-- stg_ciqual.sql — Nutrition (ANSES). Socle Nutri-Score + macros.
-- Nettoie : virgule décimale FR, valeurs censurées ('< X', '-', 'traces').
-- Renommage métier fait ICI (Silver), pas en Bronze.

WITH source AS (
    SELECT * FROM {{ source('minio_bronze', 'raw_ciqual') }}
),

renamed AS (
    SELECT
        CAST("alim_code" AS INTEGER)        AS ingredient_id,
        LOWER(TRIM("alim_nom_fr"))          AS ingredient_name,
        LOWER(TRIM("alim_grp_nom_fr"))      AS category_name,

        {{ ciqual_num('"Energie, Règlement UE N° 1169 2011 (kcal 100 g)"') }} AS energy_kcal_100g,
        {{ ciqual_num('"Protéines, N x 6.25 (g 100 g)"') }}                   AS proteins_100g,
        {{ ciqual_num('"Glucides (g 100 g)"') }}                              AS carbs_100g,
        {{ ciqual_num('"Lipides (g 100 g)"') }}                               AS fat_100g,
        {{ ciqual_num('"Sucres (g 100 g)"') }}                                AS sugars_100g,
        {{ ciqual_num('"AG saturés (g 100 g)"') }}                            AS saturated_fat_100g,
        {{ ciqual_num('"Fibres alimentaires (g 100 g)"') }}                   AS fiber_100g,
        {{ ciqual_num('"Sel chlorure de sodium (g 100 g)"') }}                AS salt_100g,
        {{ ciqual_num('"Sodium (mg 100 g)"') }}                               AS sodium_mg_100g
    FROM source
)

SELECT * FROM renamed
WHERE ingredient_id IS NOT NULL