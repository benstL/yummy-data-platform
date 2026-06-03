{{
  config(
    materialized = 'external',
    location     = 's3://yummy/gold/dbt_yummy_recommendations.parquet',
    format       = 'parquet'
  )
}}

-- Reproduces the yummy_score formula from ml/README §6 in pure SQL.
-- Writes to s3://yummy/gold/dbt_yummy_recommendations.parquet (distinct from
-- gold_yummy_recommendations.parquet produced by the Python pipeline) so both
-- outputs coexist and can be compared without either overwriting the other.
--
-- Formula (all normalised scores ∈ [0,1] before weighting):
--   yummy_score = ( 0.35 × weighted_rating_score
--                 + 0.25 × (shrunk_sentiment / 100)
--                 + 0.20 × popularity_score
--                 + 0.20 × simplicity_score ) × 100  [rounded to 2 dp]
--
-- Sentiment is consumed read-only from stg_sentiment (VADER stays in Python).
-- Clustering (KMeans, Step 4) reads this parquet unchanged — column names and
-- types are kept identical to the Python output.

WITH

-- ── 1. Bayesian parameters ────────────────────────────────────────────────────
-- Scalar subquery computed once, then broadcast to every recipe row.
--
-- C = mean(aggregatedrating) — the global prior rating all low-review recipes
--     are pulled toward.  Canonical value from ml/README §6.2: C ≈ 4.5354.
--
-- m = p80(reviewcount) — the "credibility threshold": 80 % of recipes have
--     ≤ m reviews, so the prior C dominates for the long tail.
--     Canonical value: m = 5.0.
params AS (
    SELECT
        AVG(aggregatedrating)                    AS C,
        QUANTILE_CONT(reviewcount::DOUBLE, 0.80) AS m
    FROM {{ ref('stg_recipes') }}
),

-- ── 2. Bayesian weighted rating (IMDB formula) ────────────────────────────────
-- weighted_rating = (v / (v + m)) × R  +  (m / (v + m)) × C
--
-- A low-review recipe is pulled toward C; a high-review recipe is barely affected.
-- Worked examples from §6.2:
--   v=2,    R=5.0 → WR = (2/7)×5.0  + (5/7)×4.54 = 4.67
--   v=3063, R=5.0 → WR ≈ 4.9992
--
-- CROSS JOIN broadcasts the two scalar parameters to every row.
bayesian_rating AS (
    SELECT
        r.*,
        p.C,
        p.m,
        (r.reviewcount::DOUBLE / (r.reviewcount::DOUBLE + p.m)) * r.aggregatedrating
        + (p.m              / (r.reviewcount::DOUBLE + p.m)) * p.C
            AS weighted_rating
    FROM {{ ref('stg_recipes') }} r
    CROSS JOIN params p
),

-- ── 3. Min-max normalisation of three component scores ────────────────────────
-- Each score is scaled to [0, 1] over the full corpus before weighting.
-- Window aggregates ignore NULLs by default (SQL standard), so MIN/MAX of
-- totaltime exclude NULL rows — same behaviour as pandas Series.min().
--
-- NULLIF guards the denominator for degenerate corpora (all-equal values → 0.0),
-- matching the Python normalize_series() early-exit: `if hi == lo: return 0.0`.
--
-- NULL totaltime → simplicity_score = NULL → yummy_score = NULL (propagated).
-- This matches Python NaN propagation (see ml/README §9, "Scripts require
-- project-root execution" limitation note about NULL handling).
normalized AS (
    SELECT
        *,

        -- weighted_rating_score: normalised Bayesian rating.
        -- Also stored as rating_score (alias forwarded to the KMeans clustering step).
        (weighted_rating - MIN(weighted_rating) OVER ())
            / NULLIF(MAX(weighted_rating) OVER () - MIN(weighted_rating) OVER (), 0)
            AS weighted_rating_score,

        -- popularity_score: normalised review count.
        -- The recipe with the most reviews scores 1.0 (Bourbon Chicken, 3,063 reviews).
        (reviewcount::DOUBLE - MIN(reviewcount::DOUBLE) OVER ())
            / NULLIF(MAX(reviewcount::DOUBLE) OVER () - MIN(reviewcount::DOUBLE) OVER (), 0)
            AS popularity_score,

        -- simplicity_score: inverse of normalised cook time (fastest recipe = 1.0).
        -- Computed as 1 − normalised_time so that short recipes score high.
        1.0 - (totaltime::DOUBLE - MIN(totaltime::DOUBLE) OVER ())
            / NULLIF(MAX(totaltime::DOUBLE) OVER () - MIN(totaltime::DOUBLE) OVER (), 0)
            AS simplicity_score

    FROM bayesian_rating
),

-- ── 4. Sentiment join + Bayesian shrinkage ────────────────────────────────────
-- LEFT JOIN: recipes absent from stg_sentiment (3,354 data-gap rows) receive 50.0,
-- the median of a uniform percentile distribution — a neutral prior (§6.4).
--
-- Shrunk sentiment applies the same Bayesian formula as the rating, shrinking the
-- raw percentile toward 50 proportionally to review credibility:
--   shrunk = (v / (v + m)) × percentile  +  (m / (v + m)) × 50
--
-- Worked examples from §6.3:
--   v=2,    pct=99   → (2/7)×99   + (5/7)×50   = 64.0
--   v=3063, pct=29.79 → (3063/3068)×29.79 + (5/3068)×50 ≈ 29.82
sentiment_joined AS (
    SELECT
        n.*,
        COALESCE(s.sentiment_percentile, 50.0) AS sentiment_percentile,
        (n.reviewcount::DOUBLE / (n.reviewcount::DOUBLE + n.m))
            * COALESCE(s.sentiment_percentile, 50.0)
        + (n.m / (n.reviewcount::DOUBLE + n.m)) * 50.0
            AS shrunk_sentiment
    FROM normalized n
    LEFT JOIN {{ ref('stg_sentiment') }} s ON n.recipeid = s.recipeid
)

-- ── 5. Final score assembly ───────────────────────────────────────────────────
-- Column order and names mirror the Python columns_to_keep list so that the
-- downstream consumers (query_duckdb.py, recipe_clusterer.py) need no changes.
--
-- ingredient_count: whitespace-token count matching Python `str.split()` semantics
-- (splits on any whitespace run, strips leading/trailing).
-- string_split_regex(str, '\s+') handles multi-space gaps in the raw ingredient string.
SELECT
    recipeid,
    name,
    recipecategory,
    recipeingredientparts,
    recipeinstructions,
    totaltime,
    CASE
        WHEN TRIM(COALESCE(recipeingredientparts, '')) = '' THEN 0
        ELSE len(
                 string_split_regex(
                     TRIM(COALESCE(recipeingredientparts, '')),
                     '\s+'
                 )
             )
    END                                           AS ingredient_count,
    aggregatedrating,
    reviewcount,
    ROUND(weighted_rating,  4)                    AS weighted_rating,
    sentiment_percentile,
    ROUND(shrunk_sentiment, 2)                    AS shrunk_sentiment,
    weighted_rating_score                         AS rating_score,   -- alias for clustering
    popularity_score,
    simplicity_score,
    ROUND(
        (   0.35 * weighted_rating_score
          + 0.25 * (shrunk_sentiment / 100.0)
          + 0.20 * popularity_score
          + 0.20 * simplicity_score
        ) * 100.0,
        2
    )                                             AS yummy_score,
    CURRENT_TIMESTAMP                             AS processed_at
FROM sentiment_joined
ORDER BY yummy_score DESC NULLS LAST
