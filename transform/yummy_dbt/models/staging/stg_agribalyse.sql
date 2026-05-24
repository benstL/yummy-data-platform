-- stg_agribalyse.sql — Empreinte carbone (ADEME). Pilier CO2 + clé jointure CIQUAL.
WITH source AS (
    SELECT * FROM {{ source('minio_bronze', 'raw_agribalyse') }}
),

renamed AS (
    SELECT
        -- Clé de jointure vers stg_ciqual.ingredient_id (même type INTEGER)
        TRY_CAST("Code CIQUAL" AS INTEGER)                       AS ciqual_code,
        "Code AGB"                                               AS agb_code,
        LOWER(TRIM("Nom du Produit en Français"))                AS product_name,
        LOWER(TRIM("Groupe d'aliment"))                          AS food_group,

        -- Déjà numériques (DuckDB les a typés DOUBLE) : pas de nettoyage texte
        TRY_CAST("kg CO2 eq/kg de produit" AS DOUBLE)            AS co2_kg_per_kg,
        TRY_CAST("DQR - Note de qualité de la donnée (1 excellente ; 5 très faible)" AS DOUBLE) AS data_quality_score,

        -- Proxy saisonnalité fourni par ADEME
        TRY_CAST("code saison (0 : hors saison ; 1 : de saison ; 2 : mix de consommation FR)" AS INTEGER) AS season_code
    FROM source
)

SELECT * FROM renamed
WHERE ciqual_code IS NOT NULL