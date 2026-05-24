-- stg_eufic.sql — Saisonnalité fruits/légumes par pays. Mois normalisés en numéro.
WITH source AS (
    SELECT * FROM {{ source('minio_bronze', 'raw_eufic') }}
),

renamed AS (
    SELECT
        LOWER(TRIM(product_name))   AS product_name,
        LOWER(TRIM(product_type))   AS product_type,   -- fruit / vegetable
        LOWER(TRIM(country))        AS country,
        LOWER(TRIM(month))          AS month_name,
        CASE LOWER(TRIM(month))
            WHEN 'january' THEN 1 WHEN 'february' THEN 2 WHEN 'march' THEN 3
            WHEN 'april' THEN 4   WHEN 'may' THEN 5      WHEN 'june' THEN 6
            WHEN 'july' THEN 7    WHEN 'august' THEN 8   WHEN 'september' THEN 9
            WHEN 'october' THEN 10 WHEN 'november' THEN 11 WHEN 'december' THEN 12
        END AS month_num
    FROM source
)

SELECT * FROM renamed
WHERE month_num IS NOT NULL