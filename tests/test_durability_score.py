import pandas as pd

from transform.gold.build_gold_durability_score import (
    build_seasonality_reference,
    build_availability_reference,
    compute_durability_scores,
)


def make_recipe_matches_fixture():
    return pd.DataFrame(
        {
            "recipeid": [1, 1, 2, 2, 3],
            "ingredient_token": ["tomato", "strawberry", "potato", "garlic", "unknown"],
            "matched_term": ["tomato", "strawberry", "potato", "garlic", None],
            "source": ["eufic", "eufic", "eufic", "eufic", "unmatched"],
        }
    )


def durability_df(eufic_df, faostat_df):
    recipe_matches = make_recipe_matches_fixture()

    seasonality_ref = build_seasonality_reference(
        eufic_df,
        country="fr",
        month=6,
    )

    availability_ref = build_availability_reference(
        faostat_df,
        country="france",
    )

    return compute_durability_scores(
        recipe_matches,
        seasonality_ref,
        availability_ref,
    )


def test_required_columns_exist(eufic_df, faostat_df):
    df = durability_df(eufic_df, faostat_df)

    expected_columns = {
        "recipeid",
        "seasonality_score",
        "availability_score",
        "durability_score",
    }

    assert expected_columns.issubset(set(df.columns))


def test_no_null_recipeid(eufic_df, faostat_df):
    df = durability_df(eufic_df, faostat_df)
    assert df["recipeid"].notna().all()


def test_durability_score_between_0_and_100(eufic_df, faostat_df):
    df = durability_df(eufic_df, faostat_df)
    assert df["durability_score"].between(0, 100).all()


def test_seasonality_score_between_0_and_100(eufic_df, faostat_df):
    df = durability_df(eufic_df, faostat_df)
    assert df["seasonality_score"].between(0, 100).all()


def test_availability_score_between_0_and_100(eufic_df, faostat_df):
    df = durability_df(eufic_df, faostat_df)
    assert df["availability_score"].between(0, 100).all()


def test_some_recipes_have_positive_durability_score(eufic_df, faostat_df):
    df = durability_df(eufic_df, faostat_df)
    assert (df["durability_score"] > 0).sum() > 0


def test_recipeid_unique(eufic_df, faostat_df):
    df = durability_df(eufic_df, faostat_df)
    assert df["recipeid"].nunique() == len(df)
