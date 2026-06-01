{{ config(materialized='view') }}

-- Staging view over the latest Silver Food.com recipes on MinIO.
-- The wildcard glob returns all date-partitioned files; the transform layer
-- writes one file per run, so in practice a single parquet is scanned.
--
-- reviewcount > 0 filter mirrors the Python Gold pipeline entry point
-- (build_gold_yummy_recommendations.py line 52–55): the 247,489 zero-review
-- recipes are excluded before any score is computed.
--
-- totaltime is left as-is (may be NULL): NULL propagates through
-- simplicity_score → yummy_score = NULL, consistent with Python NaN behaviour.

SELECT
    CAST(recipeid              AS BIGINT)  AS recipeid,
    CAST(name                  AS VARCHAR) AS name,
    CAST(recipecategory        AS VARCHAR) AS recipecategory,
    CAST(recipeingredientparts AS VARCHAR) AS recipeingredientparts,
    CAST(recipeinstructions    AS VARCHAR) AS recipeinstructions,
    CAST(aggregatedrating      AS DOUBLE)  AS aggregatedrating,
    CAST(reviewcount           AS BIGINT)  AS reviewcount,
    -- Already integer minutes after ISO-8601 conversion in the Silver transform.
    CAST(totaltime             AS BIGINT)  AS totaltime
FROM read_parquet('s3://yummy/silver/foodcom/silver_recipes_*.parquet')
WHERE reviewcount > 0
