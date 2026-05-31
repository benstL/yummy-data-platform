"""Tests for ml/matching/ingredient_matcher.py using fixture data."""
import sys

import pandas as pd
import pytest

from ml.matching.ingredient_matcher import (
    SIMILARITY_THRESHOLD,
    STOPWORDS,
    build_matches_df,
    build_recipe_map,
    build_reference_vocab,
    build_vectorizer,
    extract_ingredient_tokens,
    match_tokens,
)

# Singular ingredient tokens present in fixture recipes that must resolve to
# an EUFIC term (EUFIC has "tomato" / "strawberry" / "potato"; FAOSTAT has
# the plural "tomatoes" / "strawberries" / "potatoes" — so singular forms
# land unambiguously in EUFIC).
EUFIC_TOKEN_CASES = [
    ("tomato",     "tomato"),
    ("strawberry", "strawberry"),
    ("potato",     "potato"),
]


# ---------------------------------------------------------------------------
# Module-scoped fixtures — TF-IDF is expensive, build it once per test module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def reference_data(eufic_df: pd.DataFrame, faostat_df: pd.DataFrame):
    """Fitted TF-IDF vectorizer + reference matrix, built once for this module."""
    terms, source_map = build_reference_vocab(eufic_df, faostat_df)
    vectorizer, matrix = build_vectorizer(terms)
    return terms, source_map, vectorizer, matrix


@pytest.fixture(scope="module")
def matches_df(recipes_df: pd.DataFrame, reference_data) -> pd.DataFrame:
    """Token-level gold_ingredient_matches DataFrame, computed once per module."""
    terms, source_map, vectorizer, matrix = reference_data
    tokens = extract_ingredient_tokens(recipes_df)
    best_idx, best_scores = match_tokens(tokens, matrix, vectorizer)
    return build_matches_df(tokens, terms, source_map, best_idx, best_scores)


@pytest.fixture(scope="module")
def recipe_map_df(recipes_df: pd.DataFrame, matches_df: pd.DataFrame) -> pd.DataFrame:
    """Recipe-level gold_recipe_ingredient_map DataFrame, computed once per module."""
    return build_recipe_map(recipes_df, matches_df)


# ---------------------------------------------------------------------------
# Reference vocabulary
# ---------------------------------------------------------------------------

def test_reference_vocab_contains_eufic_terms(reference_data) -> None:
    """All expected EUFIC product names must appear in the reference vocabulary."""
    terms, _, _, _ = reference_data
    for _, expected_term in EUFIC_TOKEN_CASES:
        assert expected_term in terms, f"EUFIC term '{expected_term}' missing from reference"


def test_reference_vocab_eufic_source_priority(reference_data) -> None:
    """Terms present in both EUFIC and FAOSTAT must be tagged as 'eufic'."""
    _, source_map, _, _ = reference_data
    # "garlic" is in EUFIC; "garlic (dry)" is in FAOSTAT — both should exist
    assert source_map.get("garlic") == "eufic"
    assert source_map.get("garlic (dry)") == "faostat"


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------

def test_ingredient_tokens_non_empty(recipes_df: pd.DataFrame) -> None:
    """extract_ingredient_tokens must return at least one token."""
    tokens = extract_ingredient_tokens(recipes_df)
    assert len(tokens) > 0


def test_tokens_meet_length_filter(recipes_df: pd.DataFrame) -> None:
    """Every extracted token must satisfy the MIN_TOKEN_LEN >= 3 constraint."""
    tokens = extract_ingredient_tokens(recipes_df)
    assert all(len(t) >= 3 for t in tokens), "Short token found in extracted list"


def test_tokens_not_numeric(recipes_df: pd.DataFrame) -> None:
    """Purely numeric strings must be excluded from extracted tokens."""
    tokens = extract_ingredient_tokens(recipes_df)
    assert all(not t.isnumeric() for t in tokens), "Numeric token found in extracted list"


def test_stopwords_excluded(recipes_df: pd.DataFrame) -> None:
    """None of the specified stopwords may appear in extracted tokens."""
    tokens = extract_ingredient_tokens(recipes_df)
    token_set = set(tokens)
    for word in STOPWORDS:
        assert word not in token_set, f"Stopword '{word}' not excluded"


# ---------------------------------------------------------------------------
# EUFIC token matching — core assertion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ingredient_token,expected_eufic_term", EUFIC_TOKEN_CASES)
def test_eufic_token_match_above_threshold(
    ingredient_token: str,
    expected_eufic_term: str,
    matches_df: pd.DataFrame,
) -> None:
    """Fixture tokens tomato/strawberry/potato must match EUFIC with similarity > 0.35."""
    rows = matches_df[matches_df["ingredient_token"] == ingredient_token]
    assert len(rows) == 1, f"Token '{ingredient_token}' not found in matches DataFrame"
    row = rows.iloc[0]
    assert row["source"] == "eufic", (
        f"'{ingredient_token}' expected source='eufic', got '{row['source']}'"
    )
    assert row["similarity_score"] > SIMILARITY_THRESHOLD, (
        f"'{ingredient_token}' similarity {row['similarity_score']:.4f} "
        f"not above threshold {SIMILARITY_THRESHOLD}"
    )


# ---------------------------------------------------------------------------
# matches_df integrity
# ---------------------------------------------------------------------------

def test_matches_df_required_columns(matches_df: pd.DataFrame) -> None:
    """matches_df must contain all four required columns."""
    for col in ("ingredient_token", "matched_term", "similarity_score", "source"):
        assert col in matches_df.columns, f"Missing column: {col}"


def test_similarity_scores_in_valid_range(matches_df: pd.DataFrame) -> None:
    """All similarity scores must be in [0, 1]."""
    assert matches_df["similarity_score"].between(0.0, 1.0).all()


def test_unmatched_tokens_have_null_term(matches_df: pd.DataFrame) -> None:
    """Tokens below the threshold must have matched_term=None and source='unmatched'."""
    unmatched = matches_df[matches_df["source"] == "unmatched"]
    assert unmatched["matched_term"].isna().all()


def test_matched_tokens_have_non_null_term(matches_df: pd.DataFrame) -> None:
    """Tokens above the threshold must have a non-null matched_term."""
    matched = matches_df[matches_df["source"] != "unmatched"]
    assert matched["matched_term"].notna().all()


def test_source_values_are_valid(matches_df: pd.DataFrame) -> None:
    """source column must only contain 'eufic', 'faostat', or 'unmatched'."""
    valid = {"eufic", "faostat", "unmatched"}
    assert set(matches_df["source"].unique()).issubset(valid)


def test_tokens_are_unique(matches_df: pd.DataFrame) -> None:
    """Each ingredient token must appear exactly once in matches_df."""
    assert matches_df["ingredient_token"].nunique() == len(matches_df)


# ---------------------------------------------------------------------------
# recipe_map_df integrity
# ---------------------------------------------------------------------------

def test_recipe_map_all_recipes_present(
    recipes_df: pd.DataFrame, recipe_map_df: pd.DataFrame
) -> None:
    """Every recipe in the fixture must appear in the recipe map output."""
    assert set(recipe_map_df["recipeid"]) == set(recipes_df["recipeid"])


def test_recipe_map_required_columns(recipe_map_df: pd.DataFrame) -> None:
    """Recipe map must expose all five required output columns."""
    required = {
        "recipeid", "matched_ingredients",
        "eufic_match_count", "faostat_match_count", "unmatched_count",
    }
    assert required.issubset(set(recipe_map_df.columns))


def test_recipe_map_counts_non_negative(recipe_map_df: pd.DataFrame) -> None:
    """All count columns must be >= 0."""
    for col in ("eufic_match_count", "faostat_match_count", "unmatched_count"):
        assert (recipe_map_df[col] >= 0).all(), f"Negative value in '{col}'"


def test_recipe_map_matched_ingredients_is_list(recipe_map_df: pd.DataFrame) -> None:
    """matched_ingredients must be a Python list for every recipe (never NaN)."""
    assert all(isinstance(v, list) for v in recipe_map_df["matched_ingredients"])


def test_garlic_recipes_have_eufic_match(
    recipes_df: pd.DataFrame, recipe_map_df: pd.DataFrame
) -> None:
    """Recipes whose ingredients include 'garlic' must have eufic_match_count > 0."""
    garlic_ids = recipes_df.loc[
        recipes_df["recipeingredientparts"].str.contains("garlic", na=False),
        "recipeid",
    ]
    subset = recipe_map_df[recipe_map_df["recipeid"].isin(garlic_ids)]
    assert (subset["eufic_match_count"] > 0).all(), (
        "Expected eufic_match_count > 0 for all recipes containing 'garlic'"
    )


if __name__ == "__main__":
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-v", "--tb=short"]))
