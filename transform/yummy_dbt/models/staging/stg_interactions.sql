-- stg_interactions.sql — Notes et avis Food.com. Pilier satisfaction.
WITH source AS (
    SELECT * FROM {{ source('minio_bronze', 'raw_interactions') }}
)

SELECT
    CAST(recipe_id AS BIGINT)   AS recipe_id,
    CAST(user_id AS BIGINT)     AS user_id,
    CAST(date AS DATE)          AS reviewed_at,
    CAST(rating AS INTEGER)     AS rating,        -- 0 à 5
    TRIM(review)                AS review_text
FROM source
WHERE rating IS NOT NULL
  AND rating BETWEEN 0 AND 5     -- garde-fou : écarte les notes hors échelle