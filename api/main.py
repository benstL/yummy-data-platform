from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query

from ml.matching.ingredient_matcher import load_ingredient_taxonomy, map_ingredient_to_category

# -------------------------------------------------------------------
# Configuration API
# -------------------------------------------------------------------

app = FastAPI(
    title="YUMMY API",
    description="API de recommandations de recettes durables",
    version="1.0.0"
)

# -------------------------------------------------------------------
# Data paths and constants
# -------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLD_FILE = PROJECT_ROOT / "data/gold/gold_yummy_recommendations.parquet"
DURABILITY_FILE = PROJECT_ROOT / "data/gold/gold_recipe_durability_scores.parquet"
INGREDIENT_MAP_FILE = PROJECT_ROOT / "data/gold/gold_recipe_ingredient_map.parquet"

RECIPE_COLUMNS = [
    "recipeid",
    "name",
    "recipecategory",
    "totaltime",
    "ingredient_count",
    "aggregatedrating",
    "reviewcount",
    "yummy_score",
    "seasonality_score",
    "availability_score",
    "durability_score",
    "coverage_score",
]

# -------------------------------------------------------------------
# Utility functions
# -------------------------------------------------------------------

def load_gold_data() -> pd.DataFrame:
    """
    Load the Gold durability dataset enriched with Yummy Score and durability scores.
    """
    if not DURABILITY_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Durability file not found: {DURABILITY_FILE}",
        )

    return pd.read_parquet(DURABILITY_FILE)


def load_ingredient_map_data() -> pd.DataFrame:
    """Load the Gold ingredient map enriched with categories and buckets."""
    if not INGREDIENT_MAP_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Ingredient map file not found: {INGREDIENT_MAP_FILE}",
        )

    return pd.read_parquet(INGREDIENT_MAP_FILE)


def _ingredient_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
        return [str(item).strip() for item in value if str(item).strip()]
    if hasattr(value, "tolist"):
        try:
            return [str(item).strip() for item in value.tolist() if str(item).strip()]
        except Exception:
            pass
    return [str(value).strip()] if str(value).strip() else []


def _flatten_ingredient_column(series: pd.Series) -> list[str]:
    items: list[str] = []
    for value in series:
        items.extend(_ingredient_list(value))
    return items


def _is_seasonal_category(category: str) -> bool:
    return str(category).strip().lower() in {"fruit", "vegetable"}


def _make_buckets_separate(seasonal: set[str], complementary: set[str]) -> dict[str, list[str]]:
    complementary -= seasonal
    return {
        "seasonal_ingredients": sorted(seasonal),
        "complementary_ingredients": sorted(complementary),
    }


def _ingredient_buckets_metadata(seasonal: list[str], complementary: list[str]) -> dict[str, Any]:
    return {
        "seasonality_available": bool(seasonal),
        "seasonality_source": "EUFIC" if seasonal else None,
        "complementary_source": "FAOSTAT/Food.com",
    }


def build_ingredient_buckets(df: pd.DataFrame) -> dict[str, Any]:
    """Return seasonal and complementary ingredient buckets from the Gold map."""
    seasonal: set[str] = set()
    complementary: set[str] = set()

    if "seasonal_ingredients" in df.columns and "complementary_ingredients" in df.columns:
        seasonal = set(_flatten_ingredient_column(df["seasonal_ingredients"]))
        complementary = set(_flatten_ingredient_column(df["complementary_ingredients"]))
        buckets = _make_buckets_separate(seasonal, complementary)
        buckets.update(_ingredient_buckets_metadata(buckets["seasonal_ingredients"], buckets["complementary_ingredients"]))
        return buckets

    if "matched_ingredients" in df.columns and "ingredient_categories" in df.columns:
        taxonomy = load_ingredient_taxonomy()
        for ingredients, categories in zip(df["matched_ingredients"], df["ingredient_categories"]):
            ingredients_list = _ingredient_list(ingredients)
            categories_list = _ingredient_list(categories)
            if len(categories_list) != len(ingredients_list):
                categories_list = [
                    map_ingredient_to_category(ingredient, taxonomy)
                    for ingredient in ingredients_list
                ]

            for ingredient, category in zip(ingredients_list, categories_list):
                normalized_category = str(category).strip().lower()
                if normalized_category == "other":
                    normalized_category = map_ingredient_to_category(ingredient, taxonomy)
                if _is_seasonal_category(normalized_category):
                    seasonal.add(ingredient)
                else:
                    complementary.add(ingredient)

        buckets = _make_buckets_separate(seasonal, complementary)
        buckets.update(_ingredient_buckets_metadata(buckets["seasonal_ingredients"], buckets["complementary_ingredients"]))
        return buckets

    if "matched_ingredients" in df.columns:
        for ingredients in df["matched_ingredients"]:
            for ingredient in _ingredient_list(ingredients):
                complementary.add(ingredient)

        buckets = _make_buckets_separate(set(), complementary)
        buckets.update(_ingredient_buckets_metadata([], buckets["complementary_ingredients"]))
        return buckets

    return {"seasonal_ingredients": [], "complementary_ingredients": [], **_ingredient_buckets_metadata([], [])}


def _build_structured_items(
    names: list[str],
    taxonomy: dict[str, str],
    is_seasonal: bool,
) -> list[dict]:
    items: list[dict] = []
    for name in sorted(_ingredient_list(names), key=lambda x: x.lower()):
        if not isinstance(name, str) or not name.strip():
            continue
        category = map_ingredient_to_category(name, taxonomy)
        items.append(
            {
                "name": name,
                "category": category,
                "is_seasonal": is_seasonal,
            }
        )
    return items


def build_ingredient_buckets_v2(df: pd.DataFrame) -> dict[str, Any]:
    """Return enriched ingredient buckets as structured objects.

    Each item is a dict with keys:
      - name: ingredient display name
      - category: business taxonomy category (fruit, vegetable, meat, ...)
      - is_seasonal: bool
    """
    taxonomy = load_ingredient_taxonomy()

    if "seasonal_ingredients" in df.columns and "complementary_ingredients" in df.columns:
        seasonal = _build_structured_items(
            _flatten_ingredient_column(df["seasonal_ingredients"]), taxonomy, is_seasonal=True
        )
        complementary = _build_structured_items(
            _flatten_ingredient_column(df["complementary_ingredients"]), taxonomy, is_seasonal=False
        )
        buckets = {
            "seasonal_ingredients": seasonal,
            "complementary_ingredients": complementary,
            **_ingredient_buckets_metadata([item["name"] for item in seasonal], [item["name"] for item in complementary]),
        }
        return buckets

    items: list[dict] = []

    if "matched_ingredients" in df.columns:
        categories_series = df.get("ingredient_categories", [None] * len(df))
        for ingredients, categories in zip(df["matched_ingredients"], categories_series):
            ingredients_list = _ingredient_list(ingredients)
            categories_list = _ingredient_list(categories)
            if len(categories_list) != len(ingredients_list):
                categories_list = ["other"] * len(ingredients_list)

            for name, cat in zip(ingredients_list, categories_list):
                if not isinstance(name, str):
                    continue
                category = str(cat).strip().lower() if cat is not None else map_ingredient_to_category(name, taxonomy)
                if category == "other":
                    category = map_ingredient_to_category(name, taxonomy)
                items.append(
                    {
                        "name": name,
                        "category": category,
                        "is_seasonal": _is_seasonal_category(category),
                    }
                )

    dedup: dict[tuple[str, str], dict] = {}
    for it in items:
        key = (it["name"].strip().lower(), it["category"])
        existing = dedup.get(key)
        if existing:
            existing["is_seasonal"] = existing["is_seasonal"] or it["is_seasonal"]
        else:
            dedup[key] = {"name": it["name"], "category": it["category"], "is_seasonal": it["is_seasonal"]}

    structured = list(dedup.values())
    seasonal_names = {item["name"].strip().lower() for item in structured if item["is_seasonal"]}
    seasonal = [s for s in structured if s["is_seasonal"]]
    complementary = [s for s in structured if s["name"].strip().lower() not in seasonal_names]

    seasonal = sorted(seasonal, key=lambda x: x["name"].lower())
    complementary = sorted(complementary, key=lambda x: x["name"].lower())

    return {
        "seasonal_ingredients": seasonal,
        "complementary_ingredients": complementary,
        **_ingredient_buckets_metadata([item["name"] for item in seasonal], [item["name"] for item in complementary]),
    }



def format_recipes(df: pd.DataFrame) -> list[dict]:
    """
    Return a clean subset of columns for recipe recommendation endpoints.
    """
    return df[RECIPE_COLUMNS].to_dict(orient="records")


# -------------------------------------------------------------------
# Root and monitoring endpoints
# -------------------------------------------------------------------


@app.get("/")
def root():
    """
    Root endpoint used to check that the API is running.
    """
    return {
        "message": "YUMMY API is running",
        "docs": "/docs",
        "health": "/health",
        "stats": "/stats",
        "recommendations": "/recommendations",
        "durability": "/durability",
        "ingredient_buckets": "/ingredient-buckets",
        "recipes_by_score": "/recipes-by-score?score=yummy",
        }


@app.get("/health")
def health():
    """
    Healthcheck endpoint.

    Useful for local debugging, Docker, monitoring or future orchestration.
    """
    return {
        "status": "ok",
        "service": "yummy-api",
        "gold_file_exists": GOLD_FILE.exists(),
        "gold_durability_file_exists": DURABILITY_FILE.exists(),
    }


@app.get("/stats")
def get_stats():
    """
    Return global statistics about the Gold recommendation dataset.
    """
    df = load_gold_data()
    return {
        "nb_recipes": int(len(df)),
        "average_yummy_score": round(float(df["yummy_score"].mean()), 2),
        "max_yummy_score": round(float(df["yummy_score"].max()), 2),
        "min_yummy_score": round(float(df["yummy_score"].min()), 2),
        "average_durability_score": round(float(df["durability_score"].mean()), 2),
        "max_durability_score": round(float(df["durability_score"].max()), 2),
        "average_coverage_score": round(float(df["coverage_score"].mean()), 2),
        "average_total_time": round(float(df["totaltime"].mean()), 2),
        "average_rating": round(float(df["aggregatedrating"].mean()), 2),
    }

# -------------------------------------------------------------------
# Recommendation endpoints
# -------------------------------------------------------------------

@app.get("/recommendations")
def get_recommendations(
    limit: int = Query(default=10, ge=1, le=100),
):
    """
    Return the top recipes ranked by Yummy Score.
    """
    df = load_gold_data()

    recommendations = (
        df.sort_values(by="yummy_score", ascending=False)
        .head(limit)
    )

    return format_recipes(recommendations)

@app.get("/durability")
def get_durability(
    limit: int = Query(default=10, ge=1, le=100),
):
    """
    Return the top recipes ranked by durability score.
    """
    df = load_gold_data()

    recipes = (
        df[RECIPE_COLUMNS]
        .sort_values("durability_score", ascending=False)
        .head(limit)
    )

    return recipes.to_dict(orient="records")



@app.get("/recipes-by-score")
def get_recipes_by_score(
    score: str = Query(default="yummy", pattern="^(yummy|durability)$"),
    limit: int = Query(default=10, ge=1, le=100),
):
    """
    Return recipes ranked either by Yummy Score or Durability Score.

    score=yummy       -> rank by yummy_score
    score=durability  -> rank by durability_score
    """
    df = load_gold_data()

    score_column = "yummy_score" if score == "yummy" else "durability_score"

    recipes = (
        df[RECIPE_COLUMNS]
        .sort_values(score_column, ascending=False)
        .head(limit)
    )

    return recipes.to_dict(orient="records")


@app.get("/recipe/{recipeid}")
def get_recipe(recipeid: int):
    """
    Return the full information of one recipe by its recipe ID.
    """
    df = load_gold_data()

    recipe = df[df["recipeid"] == recipeid]

    if recipe.empty:
            raise HTTPException(
                status_code=404,
                detail=f"Recipe {recipeid} not found",
        )

    return recipe.iloc[0].to_dict()


@app.get("/quick-recipes")
def get_quick_recipes(
    max_time: int = Query(default=30, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Return the best recipes that can be prepared within a maximum time.
    """
    df = load_gold_data()

    recipes = (
        df[df["totaltime"] <= max_time]
        .sort_values("yummy_score", ascending=False)
        .head(limit)
    )

    return format_recipes(recipes)


@app.get("/ingredient-buckets")
def get_ingredient_buckets():
    """Return the ingredient buckets used by the Streamlit UI."""
    df = load_ingredient_map_data()
    return build_ingredient_buckets(df)


@app.get("/ingredient-buckets/v2")
def get_ingredient_buckets_v2():
    """Return structured ingredient buckets (name, category, is_seasonal)."""
    df = load_ingredient_map_data()
    return build_ingredient_buckets_v2(df)


@app.get("/category/{category}")
def get_recipes_by_category(
    category: str,
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Return the best recipes matching a given category.
    """
    df = load_gold_data()

    recipes = (
        df[
            df["recipecategory"]
            .str.contains(category, case=False, na=False)
        ]
        .sort_values("yummy_score", ascending=False)
        .head(limit)
    )

    return format_recipes(recipes)
