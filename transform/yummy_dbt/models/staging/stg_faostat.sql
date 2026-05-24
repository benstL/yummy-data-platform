-- stg_faostat.sql — Production agricole FAOSTAT (FAO). Proxy carbone SECONDAIRE.
-- ⚠️ Non substituable à Agribalyse pour l'impact CO2 ; volumes de production seulement.
-- Fichier mondial 1961-2024 énorme -> on FILTRE dès le staging (France, Production,
-- années récentes) pour ne matérialiser que l'utile.
-- ⚠️ Deux extractions existent sur MinIO -> on ne garde que la plus récente
--    (MAX(extraction_date)) pour éviter de doubler les lignes.
WITH source AS (
    SELECT * FROM {{ source('minio_bronze', 'raw_faostat') }}
),

latest AS (
    SELECT MAX(extraction_date) AS max_extraction FROM source
),

filtered AS (
    SELECT s.*
    FROM source s, latest
    WHERE s.extraction_date = latest.max_extraction   -- une seule extraction
      AND s."Area" = 'France'                          -- périmètre France
      AND s."Element" = 'Production'                   -- volumes produits
      AND s."Year" >= 2018                             -- années récentes
)

SELECT
    "Area"        AS area,
    "Item"        AS product,            -- ex. "Wheat", "Apples"
    "Item Code"   AS item_code,
    "Year"        AS year,
    "Element"     AS element,
    "Unit"        AS unit,               -- ex. "t" (tonnes)
    "Value"       AS production_value,
    "Flag"        AS flag,               -- qualité de la donnée FAO
    extraction_date
FROM filtered
WHERE "Value" IS NOT NULL