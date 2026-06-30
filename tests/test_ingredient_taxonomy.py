import json
from pathlib import Path

import pandas as pd

from api.main import build_ingredient_buckets
from app.streamlit_app import (
    _translate_recipe_detail_text,
    add_basket_relevance_scores,
    build_business_ingredient_options,
    build_localized_option_map,
    ingredient_display_name,
)
from ml.matching.ingredient_matcher import (
    build_recipe_map,
    load_ingredient_taxonomy,
    map_ingredient_to_category,
)


def test_load_ingredient_taxonomy_reads_json_mapping(tmp_path: Path) -> None:
    config_path = tmp_path / "ingredient_taxonomy.json"
    config_path.write_text(
        json.dumps({
            "categories": {
                "apple": "fruit",
                "carrot": "vegetable",
                "chicken": "meat",
                "milk": "dairy",
            }
        }),
        encoding="utf-8",
    )

    taxonomy = load_ingredient_taxonomy(config_path)

    assert taxonomy["apple"] == "fruit"
    assert taxonomy["carrot"] == "vegetable"
    assert taxonomy["chicken"] == "meat"


def test_map_ingredient_to_category_uses_normalized_lookup() -> None:
    taxonomy = {"apple": "fruit", "carrot": "vegetable", "chicken": "meat"}

    assert map_ingredient_to_category("Apples", taxonomy) == "fruit"
    assert map_ingredient_to_category("CARROT", taxonomy) == "vegetable"
    assert map_ingredient_to_category("unknown", taxonomy) == "other"


def test_default_taxonomy_includes_seasonal_produce() -> None:
    root = Path(__file__).resolve().parents[1]
    taxonomy = load_ingredient_taxonomy(root / "config" / "ingredient_taxonomy.json")

    assert taxonomy["apricot"] == "fruit"
    assert taxonomy["artichoke"] == "vegetable"
    assert taxonomy["asparagus"] == "vegetable"
    assert map_ingredient_to_category("Apricots", taxonomy) == "fruit"
    assert map_ingredient_to_category("Artichokes", taxonomy) == "vegetable"


def test_build_recipe_map_enriches_category_lists() -> None:
    recipes_df = pd.DataFrame(
        {
            "recipeid": [1],
            "recipeingredientparts": ["Apples and chicken"],
        }
    )
    matches_df = pd.DataFrame(
        {
            "ingredient_token": ["apples", "chicken"],
            "matched_term": ["Apples", "Chicken"],
            "source": ["eufic", "faostat"],
        }
    )
    taxonomy = {"apple": "fruit", "chicken": "meat"}

    recipe_map = build_recipe_map(recipes_df, matches_df, taxonomy=taxonomy)

    assert recipe_map.loc[0, "ingredient_categories"] == ["fruit", "meat"]
    assert recipe_map.loc[0, "seasonal_ingredients"] == ["Apples"]
    assert recipe_map.loc[0, "complementary_ingredients"] == ["Chicken"]


def test_build_ingredient_buckets_groups_categories() -> None:
    df = pd.DataFrame(
        {
            "matched_ingredients": [["Apples", "Carrots", "Chicken"]],
            "ingredient_categories": [["fruit", "vegetable", "meat"]],
            "seasonal_ingredients": [["Apples", "Carrots"]],
            "complementary_ingredients": [["Chicken"]],
        }
    )

    buckets = build_ingredient_buckets(df)

    assert buckets["seasonal_ingredients"] == ["Apples", "Carrots"]
    assert buckets["complementary_ingredients"] == ["Chicken"]


def test_build_ingredient_buckets_disjoint_sets() -> None:
    df = pd.DataFrame(
        {
            "matched_ingredients": [["Apples", "Carrots", "Chicken", "Milk"]],
            "ingredient_categories": [["fruit", "vegetable", "meat", "dairy"]],
        }
    )

    buckets = build_ingredient_buckets(df)

    assert set(buckets["seasonal_ingredients"]) & set(buckets["complementary_ingredients"]) == set()
    assert buckets["seasonal_ingredients"] == ["Apples", "Carrots"]
    assert set(buckets["complementary_ingredients"]) == {"Chicken", "Milk"}


def test_streamlit_business_options_prioritize_eufic_over_faostat() -> None:
    seasonal, complementary = build_business_ingredient_options(
        eufic_items=["Apple", "Tomato", "Carrot"],
        faostat_items=["Apple", "Chicken", "Milk", "Tomatoes"],
        ingredient_buckets={
            "complementary_ingredients": [
                {"name": "Apple", "category": "fruit"},
                {"name": "Chicken", "category": "meat"},
                {"name": "Milk", "category": "dairy"},
            ],
        },
        taxonomy={
            "apple": "fruit",
            "tomato": "vegetable",
            "tomatoes": "vegetable",
            "carrot": "vegetable",
            "chicken": "meat",
            "milk": "dairy",
        },
    )

    assert seasonal == ["Apple", "Tomato", "Carrot"]
    assert "Apple" not in complementary
    assert "Tomatoes" not in complementary
    assert set(complementary) == {"Chicken", "Milk"}


def test_streamlit_business_options_are_mutually_exclusive_and_deduplicated() -> None:
    seasonal, complementary = build_business_ingredient_options(
        eufic_items=["Apple", "Apples", "Carrot"],
        faostat_items=["apple", "Chicken", "Chicken", "Rice"],
        ingredient_buckets={
            "complementary_ingredients": ["Chicken", "Rice", "Rice", "Apple"],
        },
        taxonomy={
            "apple": "fruit",
            "apples": "fruit",
            "carrot": "vegetable",
            "chicken": "meat",
            "rice": "grain",
        },
    )

    seasonal_norm = {item.lower().rstrip("s") for item in seasonal}
    complementary_norm = {item.lower().rstrip("s") for item in complementary}

    assert seasonal == ["Apple", "Carrot"]
    assert complementary == ["Chicken", "Rice"]
    assert seasonal_norm & complementary_norm == set()
    assert len(seasonal) == len(seasonal_norm)
    assert len(complementary) == len(complementary_norm)


def test_streamlit_business_options_use_faostat_as_produce_fallback() -> None:
    seasonal, complementary = build_business_ingredient_options(
        eufic_items=[],
        faostat_items=["Mango", "Chicken"],
        ingredient_buckets={"complementary_ingredients": []},
        taxonomy={"mango": "fruit", "chicken": "meat"},
    )

    assert seasonal == []
    assert complementary == ["Mango", "Chicken"]


def test_ingredient_display_name_translates_only_for_french() -> None:
    assert ingredient_display_name("apricot", "fr") == "abricot"
    assert ingredient_display_name("cherry", "fr") == "cerise"
    assert ingredient_display_name("blueberry", "fr") == "myrtille"
    assert ingredient_display_name("new potato", "fr") == "pomme de terre nouvelle"
    assert ingredient_display_name("apricot", "en") == "apricot"


def test_ingredient_display_name_keeps_unknown_raw_value() -> None:
    assert ingredient_display_name("unknown ingredient", "fr") == "unknown ingredient"
    assert ingredient_display_name("fresh asparagus sausage", "fr") == "fresh asparagus sausage"


def test_recipe_detail_text_translates_common_foodcom_terms_to_french() -> None:
    source = "artichoke water broth"

    assert _translate_recipe_detail_text(source, "fr") == "artichaut eau ou bouillon"
    assert _translate_recipe_detail_text(source, "en") == source


def test_localized_option_map_displays_french_but_keeps_raw_values() -> None:
    labels, label_to_raw = build_localized_option_map(
        ["mushroom", "tomato", "sugar beet", "water broth", "cream", "spices"],
        "fr",
    )

    assert labels == [
        "champignon",
        "tomate",
        "betterave sucriere",
        "eau ou bouillon",
        "creme",
        "epices",
    ]
    assert label_to_raw["champignon"] == "mushroom"
    assert label_to_raw["tomate"] == "tomato"
    assert label_to_raw["betterave sucriere"] == "sugar beet"
    assert label_to_raw["eau ou bouillon"] == "water broth"
    assert label_to_raw["creme"] == "cream"
    assert label_to_raw["epices"] == "spices"


def test_basket_relevance_rewards_multiple_matches() -> None:
    df = pd.DataFrame(
        {
            "recipeid": [1, 2],
            "matched_ingredients": [["banana"], ["banana", "strawberry"]],
            "durability_score": [80.0, 40.0],
            "yummy_score": [90.0, 70.0],
        }
    )

    scored = add_basket_relevance_scores(df, ["banana", "strawberry"])

    assert scored.loc[0, "basket_match_count"] == 1
    assert scored.loc[1, "basket_match_count"] == 2
    assert scored.loc[1, "recommendation_score"] > scored.loc[0, "recommendation_score"]
