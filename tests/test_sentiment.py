"""Tests for ml/sentiment/sentiment_analyzer.py using fixture data."""
import sys

import pandas as pd
import pytest

from ml.sentiment.sentiment_analyzer import aggregate_by_recipe, score_reviews

# ---------------------------------------------------------------------------
# score_reviews
# ---------------------------------------------------------------------------


def test_score_reviews_adds_column(reviews_df: pd.DataFrame) -> None:
    """score_reviews must add a 'sentiment_score' column to the DataFrame."""
    result = score_reviews(reviews_df)
    assert "sentiment_score" in result.columns


def test_sentiment_score_range(reviews_df: pd.DataFrame) -> None:
    """Every sentiment_score must be in [0, 100]."""
    result = score_reviews(reviews_df)
    assert result["sentiment_score"].between(0.0, 100.0).all()


def test_no_nulls_in_sentiment_score(reviews_df: pd.DataFrame) -> None:
    """score_reviews must not produce any null sentiment scores."""
    result = score_reviews(reviews_df)
    assert result["sentiment_score"].isna().sum() == 0


def test_null_review_defaults_to_50(reviews_df: pd.DataFrame) -> None:
    """Null and empty-string reviews must score exactly 50 (neutral default)."""
    df = reviews_df.copy()
    df.iloc[0, df.columns.get_loc("review")] = None
    df.iloc[1, df.columns.get_loc("review")] = ""
    result = score_reviews(df)
    assert result.iloc[0]["sentiment_score"] == 50.0
    assert result.iloc[1]["sentiment_score"] == 50.0


def test_positive_outscores_negative() -> None:
    """Unambiguously positive text must score higher than negative text."""
    df = pd.DataFrame({
        "reviewid": [1, 2],
        "recipeid": [1, 1],
        "rating":   [5.0, 1.0],
        "review": [
            "delicious amazing fantastic loved it perfect wonderful",
            "terrible bland awful disgusting horrible disappointment",
        ],
    })
    result = score_reviews(df)
    assert result.iloc[0]["sentiment_score"] > result.iloc[1]["sentiment_score"]


def test_score_reviews_does_not_mutate_input(reviews_df: pd.DataFrame) -> None:
    """score_reviews must return a new DataFrame without altering the original."""
    original_cols = list(reviews_df.columns)
    score_reviews(reviews_df)
    assert list(reviews_df.columns) == original_cols


# ---------------------------------------------------------------------------
# aggregate_by_recipe
# ---------------------------------------------------------------------------


def test_aggregate_required_columns(reviews_df: pd.DataFrame) -> None:
    """aggregate_by_recipe must produce the three required output columns."""
    agg = aggregate_by_recipe(score_reviews(reviews_df))
    for col in ("recipeid", "mean_sentiment_score", "review_count"):
        assert col in agg.columns, f"Missing column: {col}"


def test_aggregate_no_nulls(reviews_df: pd.DataFrame) -> None:
    """recipeid, mean_sentiment_score, and review_count must have no null values."""
    agg = aggregate_by_recipe(score_reviews(reviews_df))
    for col in ("recipeid", "mean_sentiment_score", "review_count"):
        assert agg[col].isna().sum() == 0, f"Unexpected nulls in '{col}'"


def test_aggregate_review_count_matches_fixture(reviews_df: pd.DataFrame) -> None:
    """Each recipe must show exactly 4 reviews (fixture generates 4 per recipe)."""
    agg = aggregate_by_recipe(score_reviews(reviews_df))
    assert (agg["review_count"] == 4).all()


def test_aggregate_score_range(reviews_df: pd.DataFrame) -> None:
    """mean_sentiment_score must remain in [0, 100] after aggregation."""
    agg = aggregate_by_recipe(score_reviews(reviews_df))
    assert agg["mean_sentiment_score"].between(0.0, 100.0).all()


def test_aggregate_std_non_negative(reviews_df: pd.DataFrame) -> None:
    """std_sentiment must be >= 0 for all recipes."""
    agg = aggregate_by_recipe(score_reviews(reviews_df))
    assert (agg["std_sentiment"] >= 0).all()


def test_aggregate_recipe_count_matches_fixture(reviews_df: pd.DataFrame) -> None:
    """Output row count must equal the number of distinct recipes in the fixture."""
    n_recipes = reviews_df["recipeid"].nunique()
    agg = aggregate_by_recipe(score_reviews(reviews_df))
    assert len(agg) == n_recipes


if __name__ == "__main__":
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-v", "--tb=short"]))
