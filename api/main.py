from pathlib import Path
import pandas as pd
from fastapi import FastAPI, HTTPException, Query

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

GOLD_FILE = Path(
    "data/gold/gold_yummy_recommendations.parquet"
)

DURABILITY_FILE = Path(
    "data/gold/gold_recipe_durability_scores.parquet"
)

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
