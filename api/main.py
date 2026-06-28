from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query


# -------------------------------------------------------------------
# Configuration API
# -------------------------------------------------------------------

app = FastAPI(
    title="YUMMY API",
    description="API de recommandations de recettes durables",
    version="1.0.0",
)


# -------------------------------------------------------------------
# Data paths and constants
# -------------------------------------------------------------------

GOLD_FILE = Path("data/gold/gold_yummy_recommendations.parquet")

DURABILITY_DIR = Path("data/gold/gold_recipe_durability_scores")

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

def load_recommendations_data() -> pd.DataFrame:
    """
    Load the main Gold recommendation dataset.

    This dataset contains one row per recipe and includes stable recipe
    information such as Yummy Score, rating, category and preparation time.
    """
    if not GOLD_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Gold recommendations file not found: {GOLD_FILE}",
        )

    return pd.read_parquet(GOLD_FILE)


def load_durability_data(
    country: str = "france",
    month: int = 6,
) -> pd.DataFrame:
    """
    Load durability scores for one country and one month.

    The durability dataset is partitioned by country:
        data/gold/gold_recipe_durability_scores/durability_country=france/

    Only the requested country partition is loaded, then filtered by month.
    """
    country = country.lower().strip()

    country_path = DURABILITY_DIR / f"durability_country={country}"

    if not country_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No durability data found for country: {country}",
        )

    df = pd.read_parquet(country_path)

    if "durability_month" not in df.columns:
        raise HTTPException(
            status_code=500,
            detail="Column durability_month is missing from durability dataset.",
        )

    df = df[df["durability_month"] == month].copy()

    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No durability data found for country={country}, month={month}",
        )

    df["durability_country"] = country

    return df


def load_gold_data(
    country: str = "france",
    month: int = 6,
) -> pd.DataFrame:
    """
    Load recommendations and enrich them with contextual durability scores.

    The join is performed at API consumption time in order to avoid duplicating
    all recipe information for each country and each month in the Gold layer.
    """
    recommendations = load_recommendations_data()
    durability = load_durability_data(country=country, month=month)

    df = recommendations.merge(
        durability,
        on="recipeid",
        how="left",
    )

    durability_cols = [
        "seasonality_score",
        "availability_score",
        "durability_mean",
        "positive_durability_ratio",
        "durability_score",
        "coverage_score",
    ]

    for col in durability_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    df["durability_country"] = country
    df["durability_month"] = month

    return df


def format_recipes(df: pd.DataFrame) -> list[dict]:
    """
    Return a clean subset of columns for recipe recommendation endpoints.
    """
    available_columns = [
        col for col in RECIPE_COLUMNS
        if col in df.columns
    ]

    return df[available_columns].to_dict(orient="records")


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
        "redoc": "/redoc",
        "health": "/health",
        "stats": "/stats?country=france&month=6",
        "recommendations": "/recommendations?country=france&month=6",
        "durability": "/durability?country=france&month=6",
        "recipes_by_score": "/recipes-by-score?score=yummy&country=france&month=6",
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
        "gold_durability_dir_exists": DURABILITY_DIR.exists(),
    }


@app.get("/stats")
def get_stats(
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
):
    """
    Return global statistics about the recommendation dataset enriched with
    durability scores for a selected country and month.
    """
    df = load_gold_data(country=country, month=month)

    return {
        "country": country.lower().strip(),
        "month": month,
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
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    limit: int = Query(default=10, ge=1, le=100),
):
    """
    Return the top recipes ranked by Yummy Score.

    Durability scores are added according to the selected country and month.
    """
    df = load_gold_data(country=country, month=month)

    recommendations = (
        df.sort_values(by="yummy_score", ascending=False)
        .head(limit)
    )

    return format_recipes(recommendations)


@app.get("/durability")
def get_durability(
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    limit: int = Query(default=10, ge=1, le=100),
):
    """
    Return the top recipes ranked by durability score for a selected country
    and month.
    """
    df = load_gold_data(country=country, month=month)

    recipes = (
        df.sort_values("durability_score", ascending=False)
        .head(limit)
    )

    return format_recipes(recipes)


@app.get("/recipes-by-score")
def get_recipes_by_score(
    score: str = Query(default="yummy", pattern="^(yummy|durability)$"),
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    limit: int = Query(default=10, ge=1, le=100),
):
    """
    Return recipes ranked either by Yummy Score or Durability Score.

    score=yummy       -> rank by yummy_score
    score=durability  -> rank by durability_score
    """
    df = load_gold_data(country=country, month=month)

    score_column = "yummy_score" if score == "yummy" else "durability_score"

    recipes = (
        df.sort_values(score_column, ascending=False)
        .head(limit)
    )

    return format_recipes(recipes)


@app.get("/recipe/{recipeid}")
def get_recipe(
    recipeid: int,
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
):
    """
    Return the full information of one recipe by its recipe ID.

    Durability information is contextualized by country and month.
    """
    df = load_gold_data(country=country, month=month)

    recipe = df[df["recipeid"] == recipeid]

    if recipe.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Recipe {recipeid} not found",
        )

    return recipe.iloc[0].to_dict()


@app.get("/quick-recipes")
def get_quick_recipes(
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    max_time: int = Query(default=30, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Return the best recipes that can be prepared within a maximum time.
    """
    df = load_gold_data(country=country, month=month)

    recipes = (
        df[df["totaltime"] <= max_time]
        .sort_values("yummy_score", ascending=False)
        .head(limit)
    )

    return format_recipes(recipes)


@app.get("/category/{category}")
def get_recipes_by_category(
    category: str,
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    limit: int = Query(default=20, ge=1, le=100),
):
    """
    Return the best recipes matching a given category.
    """
    df = load_gold_data(country=country, month=month)

    recipes = (
        df[
            df["recipecategory"]
            .str.contains(category, case=False, na=False)
        ]
        .sort_values("yummy_score", ascending=False)
        .head(limit)
    )

    return format_recipes(recipes)
