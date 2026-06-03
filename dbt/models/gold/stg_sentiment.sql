{{ config(materialized='view') }}

-- Read-only staging view over pre-computed VADER sentiment scores (Step 2 output).
-- VADER scoring and percentile ranking live entirely in Python:
--   ml/sentiment/sentiment_analyzer.py → data/gold/gold_sentiment_scores.parquet → MinIO.
-- This model only exposes the two columns needed downstream; it never recomputes sentiment.
--
-- 271,678 recipes have a row here. The 3,354 recipes that have reviews but are
-- absent from this table receive a neutral sentinel of 50.0 in yummy_recommendations.sql
-- (LEFT JOIN + COALESCE, consistent with ml/README §6.4).

SELECT
    CAST(recipeid             AS BIGINT) AS recipeid,
    CAST(sentiment_percentile AS DOUBLE) AS sentiment_percentile
FROM read_parquet('s3://yummy/gold/gold_sentiment_scores.parquet')
