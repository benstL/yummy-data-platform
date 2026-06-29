"""
Generates minimal fake Silver-schema parquet fixtures for ML module tests.

Run from the project root:
    python tests/fixtures/generate_fixtures.py
"""

from datetime import datetime, UTC
from pathlib import Path

import numpy as np
import pandas as pd


OUTPUT_DIR = Path("data/tests/fixtures")
SEED = 42
N_RECIPES = 50
N_REVIEWS_PER_RECIPE = 4

MONTH_NAMES = {
    1: "january",
    2: "february",
    3: "march",
    4: "april",
    5: "may",
    6: "june",
    7: "july",
    8: "august",
    9: "september",
    10: "october",
    11: "november",
    12: "december",
}

INGREDIENT_TEMPLATES = [
    "tomato garlic olive oil",
    "tomatoes garlic onions",
    "strawberry sugar cream",
    "strawberries sugar lemon",
    "potato carrot onion",
    "potatoes carrots celery",
    "chicken garlic lemon pepper",
    "pasta basil cheese butter",
    "rice pepper butter salt",
    "eggs flour milk sugar",
]

POSITIVE_REVIEWS = [
    "delicious easy quick loved it amazing",
    "absolutely fantastic wonderful recipe great",
    "perfect wonderful meal highly recommend",
    "excellent best recipe ever so good",
    "superb flavourful will make again brilliant",
]

NEUTRAL_REVIEWS = [
    "it was okay nothing special average",
    "decent not bad could use more flavor",
    "fine recipe nothing impressive here",
    "acceptable but not my favourite",
]

NEGATIVE_REVIEWS = [
    "bland disappointing too salty terrible",
    "awful would not recommend dry overcooked",
    "very bad disgusting waste of time",
    "terrible recipe not edible at all",
]


def generate_recipes() -> pd.DataFrame:
    """Generate fake Silver recipe rows."""
    rng = np.random.default_rng(SEED)
    now = datetime.now(UTC).isoformat()

    rows = []

    for i in range(1, N_RECIPES + 1):
        template = INGREDIENT_TEMPLATES[(i - 1) % len(INGREDIENT_TEMPLATES)]

        rows.append(
            {
                "recipeid": i,
                "name": f"recipe {i}",
                "cooktime": int(rng.integers(5, 61)),
                "preptime": int(rng.integers(5, 31)),
                "totaltime": int(rng.integers(15, 121)),
                "recipecategory": ["main", "dessert", "side", "breakfast"][
                    (i - 1) % 4
                ],
                "recipeingredientparts": template,
                "aggregatedrating": round(float(rng.uniform(1.0, 5.0)), 1),
                "reviewcount": float(rng.integers(1, 201)),
                "recipeinstructions": "combine ingredients and cook until done",
                "processed_at": now,
            }
        )

    return pd.DataFrame(rows)


def generate_reviews() -> pd.DataFrame:
    """Generate fake Silver review rows."""
    rng = np.random.default_rng(SEED)
    now = datetime.now(UTC).isoformat()

    rows = []
    review_id = 1

    for recipe_id in range(1, N_RECIPES + 1):
        sentiments = [
            (str(rng.choice(POSITIVE_REVIEWS)), 5.0),
            (str(rng.choice(POSITIVE_REVIEWS)), 4.0),
            (str(rng.choice(NEUTRAL_REVIEWS)), 3.0),
            (str(rng.choice(NEGATIVE_REVIEWS)), 1.0),
        ]

        for review_text, rating in sentiments:
            rows.append(
                {
                    "reviewid": review_id,
                    "recipeid": recipe_id,
                    "rating": rating,
                    "review": review_text,
                    "processed_at": now,
                }
            )
            review_id += 1

    return pd.DataFrame(rows)


def generate_seasonality() -> pd.DataFrame:
    """
    Generate fake Silver EUFIC seasonality rows.

    Important:
    - country = 'france' (full name, matches real Silver EUFIC schema)
    - this matches the durability unit tests using country='france'
    """
    products = [
        ("tomato", "vegetable", [6, 7, 8, 9]),
        ("strawberry", "fruit", [5, 6, 7]),
        ("potato", "vegetable", [7, 8, 9, 10, 11]),
        ("carrot", "vegetable", [1, 2, 3, 9, 10, 11, 12]),
        ("garlic", "vegetable", [7, 8, 9]),
    ]

    now = datetime.now(UTC).isoformat()
    rows = []

    for product_name, product_type, months in products:
        for month_number in months:
            rows.append(
                {
                    "product_name": product_name,
                    "product_type": product_type,
                    "month": MONTH_NAMES[month_number],
                    "month_number": month_number,
                    "country": "france",
                    "is_in_season": True,
                    "confidence_score": 1.0,
                    "source": "eufic",
                    "extracted_at": now,
                    "processed_at": now,
                }
            )

    return pd.DataFrame(rows)


def generate_faostat() -> pd.DataFrame:
    """
    Generate fake Silver FAOSTAT production rows.

    Important:
    - country_name = 'france'
    - this matches the durability unit tests using country='france'
    """
    now = datetime.now(UTC).isoformat()

    rows = [
        (
            68,
            "france",
            388,
            "tomato",
            "production",
            2022,
            "tonnes",
            850_000.0,
        ),
        (
            68,
            "france",
            393,
            "strawberry",
            "production",
            2022,
            "tonnes",
            60_000.0,
        ),
        (
            68,
            "france",
            116,
            "potato",
            "production",
            2022,
            "tonnes",
            5_400_000.0,
        ),
        (
            68,
            "france",
            137,
            "carrot",
            "production",
            2022,
            "tonnes",
            500_000.0,
        ),
        (
            68,
            "france",
            406,
            "garlic (dry)",
            "production",
            2022,
            "tonnes",
            18_000.0,
        ),
    ]

    df = pd.DataFrame(
        rows,
        columns=[
            "area_code",
            "country_name",
            "item_code",
            "product_name",
            "element",
            "year",
            "unit",
            "production_value",
        ],
    )

    df["source"] = "faostat_qcl"
    df["processed_at"] = now

    return df


def main() -> None:
    print("[INFO] Generating test fixtures...")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    datasets = {
        "silver_recipes_test.parquet": generate_recipes(),
        "silver_reviews_test.parquet": generate_reviews(),
        "silver_seasonality_test.parquet": generate_seasonality(),
        "silver_faostat_test.parquet": generate_faostat(),
    }

    for filename, df in datasets.items():
        path = OUTPUT_DIR / filename
        df.to_parquet(path, index=False)
        print(f"[INFO] {filename} — {len(df)} rows, {list(df.columns)}")

    print("[INFO] Fixture generation complete.")


if __name__ == "__main__":
    main()
