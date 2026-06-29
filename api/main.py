from __future__ import annotations

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
    version="1.2.0",
)


# -------------------------------------------------------------------
# Data paths and constants
# -------------------------------------------------------------------

GOLD_FILE           = Path("data/gold/gold_yummy_recommendations.parquet")
DURABILITY_DIR      = Path("data/gold/gold_recipe_durability_scores")
CLUSTERS_FILE       = Path("data/gold/gold_recipe_clusters.parquet")
INGREDIENT_MAP_FILE = Path("data/gold/gold_recipe_ingredient_map.parquet")
SILVER_EUFIC_DIR    = Path("data/silver/eufic")
SILVER_FAOSTAT_DIR  = Path("data/silver/faostat/qcl")

# Mirrored from app/streamlit_app.py — aggregate category strings to exclude from
# FAOSTAT staples so that only specific food items are returned.
_FAO_AGGREGATE_PATTERNS = (
    "primary", " total", ", total", "poultry", " meat", "equivalent", "oilcrop"
)

# EUFIC internal keys whose country name is not simply country.title().
# Mirrored from app/streamlit_app.py EUFIC_DISPLAY_MAP.
_EUFIC_COMPOUND_KEYS: dict[str, str] = {
    "czechrepublic": "czech republic",
    "unitedkingdom": "united kingdom",
}

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
    "cluster_label",        # v1.2 — from gold_recipe_clusters
    "matched_ingredients",  # v1.2 — from gold_recipe_ingredient_map
    "eufic_match_count",    # v1.2 — from gold_recipe_ingredient_map
    "faostat_match_count",  # v1.2 — from gold_recipe_ingredient_map
]


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------

def _latest_parquet(directory: Path, glob: str) -> Path:
    """Return the most recent parquet file matching *glob* inside *directory*.

    Raises HTTPException 503 if the directory does not exist or no file is found.
    """
    files = sorted(directory.glob(glob))
    if not files:
        raise HTTPException(
            status_code=503,
            detail=f"No parquet found matching {directory / glob}",
        )
    return files[-1]


def _display_to_eufic_internal(country: str) -> str:
    """Convert a user-supplied country string to an EUFIC internal key.

    EUFIC stores compound country names without spaces (e.g. "czechrepublic",
    "unitedkingdom").  For all other countries the internal key is simply the
    lowercase country string with spaces removed.
    """
    key = country.lower().strip()
    # reverse-lookup the compound-key map
    rev = {v: k for k, v in _EUFIC_COMPOUND_KEYS.items()}
    if key in rev:
        return rev[key]
    return key.replace(" ", "")


def _to_ingredient_set(value: Any) -> set[str]:
    """Safely convert a matched_ingredients cell (list | None | NaN) to a set."""
    if value is None or isinstance(value, float):
        return set()
    try:
        return set(value)
    except TypeError:
        return set()


def _ingredient_hits(ingredients: set[str], basket_set: set[str]) -> set[str]:
    """Return basket terms that match at least one ingredient via substring.

    Matching is bidirectional: basket_term ⊂ ingredient OR ingredient ⊂ basket_term.
    This mirrors the logic in app/streamlit_app.py::_ingredient_hits so that EUFIC
    term "aubergine" matches FAOSTAT "eggplants (aubergines)" stored in
    matched_ingredients.
    """
    hits: set[str] = set()
    for b in basket_set:
        for i in ingredients:
            if b in i or i in b:
                hits.add(b)
                break
    return hits


# -------------------------------------------------------------------
# Data loaders
# -------------------------------------------------------------------

def load_recommendations_data() -> pd.DataFrame:
    """Load the main Gold recommendation dataset (one row per recipe).

    Contains Yummy Score, rating, category and preparation time.
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
    """Load durability scores for one country and one month.

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


def load_clusters_data() -> pd.DataFrame:
    """Load Gold cluster labels (one row per recipe)."""
    if not CLUSTERS_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Gold clusters file not found: {CLUSTERS_FILE}",
        )
    return pd.read_parquet(CLUSTERS_FILE, columns=["recipeid", "cluster_label"])


def load_ingredient_map_data() -> pd.DataFrame:
    """Load Gold ingredient map (one row per recipe).

    Contains matched_ingredients (list of reference terms matched by TF-IDF) and
    eufic/faostat match counts used for the seasonality confidence flag.
    """
    if not INGREDIENT_MAP_FILE.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Gold ingredient map file not found: {INGREDIENT_MAP_FILE}",
        )
    return pd.read_parquet(
        INGREDIENT_MAP_FILE,
        columns=["recipeid", "matched_ingredients", "eufic_match_count", "faostat_match_count"],
    )


def load_gold_data(
    country: str = "france",
    month: int = 6,
) -> pd.DataFrame:
    """Load the full Gold dataset, joining all 5 sources used by Streamlit.

    Sources joined (left joins on recipeid):
        1. gold_yummy_recommendations  — yummy_score, rating, category, time
        2. gold_recipe_durability_scores/<country> — durability_score, seasonality, ...
        3. gold_recipe_clusters        — cluster_label
        4. gold_recipe_ingredient_map  — matched_ingredients, eufic/faostat counts

    The join is performed at request time to avoid denormalising all recipe
    information for each country × month combination in the Gold layer.
    """
    recommendations = load_recommendations_data()
    durability       = load_durability_data(country=country, month=month)
    clusters         = load_clusters_data()
    ingredient_map   = load_ingredient_map_data()

    df = (
        recommendations
        .merge(durability,      on="recipeid", how="left")
        .merge(clusters,        on="recipeid", how="left")
        .merge(ingredient_map,  on="recipeid", how="left")
    )

    durability_fill_cols = [
        "seasonality_score", "availability_score", "durability_mean",
        "positive_durability_ratio", "durability_score", "coverage_score",
    ]
    for col in durability_fill_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    df["durability_country"] = country
    df["durability_month"] = month
    return df


def load_eufic_data() -> pd.DataFrame:
    """Load the most recent Silver EUFIC seasonality parquet."""
    path = _latest_parquet(SILVER_EUFIC_DIR, "silver_seasonality_*.parquet")
    return pd.read_parquet(
        path,
        columns=["product_name", "month_number", "country", "is_in_season"],
    )


def load_faostat_data() -> pd.DataFrame:
    """Load the most recent Silver FAOSTAT production parquet."""
    path = _latest_parquet(SILVER_FAOSTAT_DIR, "silver_faostat_*.parquet")
    return pd.read_parquet(
        path,
        columns=["country_name", "product_name", "year", "production_value"],
    )


# -------------------------------------------------------------------
# Response formatting
# -------------------------------------------------------------------

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
    """Return a clean subset of columns for recipe recommendation endpoints.

    matched_ingredients is converted from Arrow/numpy list arrays to plain
    Python lists for JSON serialisation.
    """
    available_columns = [col for col in RECIPE_COLUMNS if col in df.columns]
    result = df[available_columns].copy()

    if "matched_ingredients" in result.columns:
        result["matched_ingredients"] = result["matched_ingredients"].apply(
            lambda x: list(x) if x is not None and not isinstance(x, float) else []
        )

    return result.to_dict(orient="records")


# -------------------------------------------------------------------
# Root and monitoring endpoints
# -------------------------------------------------------------------

@app.get("/")
def root() -> dict:
    """Root endpoint — service discovery."""
    return {
        "message": "YUMMY API is running",
        "version": "1.2.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "stats":                   "/stats?country=france&month=6",
            "recommendations":         "/recommendations?country=france&month=6",
            "basket_recommendations":  "/basket-recommendations?country=france&month=6&basket=tomato,garlic",
            "durability":              "/durability?country=france&month=6",
            "recipes_by_score":        "/recipes-by-score?score=yummy&country=france&month=6",
            "recipe":                  "/recipe/{recipeid}?country=france&month=6",
            "quick_recipes":           "/quick-recipes?country=france&month=6&max_time=30",
            "category":                "/category/{category}?country=france&month=6",
            "seasonal_products":       "/seasonal-products?country=france&month=6",
            "faostat_staples":         "/faostat-staples?country=france",
            "countries":               "/countries",
        },
    }


@app.get("/health")
def health() -> dict:
    """Healthcheck — file presence and basic dataset statistics."""
    return {
        "status": "ok",
        "service": "yummy-api",
        "version": "1.2.0",
        "gold_file_exists":             GOLD_FILE.exists(),
        "gold_durability_dir_exists":   DURABILITY_DIR.exists(),
        "gold_clusters_file_exists":    CLUSTERS_FILE.exists(),
        "gold_ingredient_map_exists":   INGREDIENT_MAP_FILE.exists(),
        "silver_eufic_dir_exists":      SILVER_EUFIC_DIR.exists(),
        "silver_faostat_dir_exists":    SILVER_FAOSTAT_DIR.exists(),
    }


@app.get("/stats")
def get_stats(
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
) -> dict:
    """Global statistics about the recommendation dataset for a given country and month."""
    df = load_gold_data(country=country, month=month)

    return {
        "country": country.lower().strip(),
        "month": month,
        "nb_recipes": int(len(df)),
        "average_yummy_score":      round(float(df["yummy_score"].mean()), 2),
        "max_yummy_score":          round(float(df["yummy_score"].max()), 2),
        "min_yummy_score":          round(float(df["yummy_score"].min()), 2),
        "average_durability_score": round(float(df["durability_score"].mean()), 2),
        "max_durability_score":     round(float(df["durability_score"].max()), 2),
        "average_coverage_score":   round(float(df["coverage_score"].mean()), 2),
        "average_total_time":       round(float(df["totaltime"].mean()), 2),
        "average_rating":           round(float(df["aggregatedrating"].mean()), 2),
    }


# -------------------------------------------------------------------
# Recommendation endpoints
# -------------------------------------------------------------------

@app.get("/recommendations")
def get_recommendations(
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[dict]:
    """Top recipes ranked by Yummy Score for the given country and month.

    Includes cluster_label and matched_ingredients in the payload (v1.2).
    """
    df = load_gold_data(country=country, month=month)
    return format_recipes(df.sort_values("yummy_score", ascending=False).head(limit))


@app.get("/basket-recommendations")
def get_basket_recommendations(
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    basket: str = Query(default="", description="Comma-separated ingredient terms, e.g. tomato,garlic"),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[dict]:
    """Recipes whose matched_ingredients overlap with the supplied basket.

    Matching is bidirectional substring (mirrors Streamlit logic):
    basket term "aubergine" matches "eggplants (aubergines)".

    Fallback: if basket is empty or no recipe matches, returns the global
    top-N by yummy_score for the selected country and month.

    Returns 404 if country or country+month has no durability data.
    """
    df = load_gold_data(country=country, month=month)

    basket_items = [b.strip() for b in basket.split(",") if b.strip()] if basket else []

    if basket_items:
        basket_set = set(basket_items)
        mask = df["matched_ingredients"].apply(
            lambda ing: bool(_ingredient_hits(_to_ingredient_set(ing), basket_set))
        )
        filtered = df[mask]

        if filtered.empty:
            filtered = df  # fallback: all recipes
    else:
        filtered = df  # empty basket → global top-N

    result = filtered.sort_values("yummy_score", ascending=False).head(limit)
    return format_recipes(result)


@app.get("/durability")
def get_durability(
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[dict]:
    """Top recipes ranked by durability score for the given country and month."""
    df = load_gold_data(country=country, month=month)
    return format_recipes(df.sort_values("durability_score", ascending=False).head(limit))


@app.get("/recipes-by-score")
def get_recipes_by_score(
    score: str = Query(default="yummy", pattern="^(yummy|durability)$"),
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[dict]:
    """Recipes ranked by yummy_score (score=yummy) or durability_score (score=durability)."""
    df = load_gold_data(country=country, month=month)
    col = "yummy_score" if score == "yummy" else "durability_score"
    return format_recipes(df.sort_values(col, ascending=False).head(limit))


@app.get("/recipe/{recipeid}")
def get_recipe(
    recipeid: int,
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
) -> dict:
    """Full information for one recipe, contextualised by country and month."""
    df = load_gold_data(country=country, month=month)
    recipe = df[df["recipeid"] == recipeid]

    if recipe.empty:
        raise HTTPException(status_code=404, detail=f"Recipe {recipeid} not found")

    row = recipe.iloc[0].to_dict()
    if "matched_ingredients" in row:
        ing = row["matched_ingredients"]
        row["matched_ingredients"] = (
            list(ing) if ing is not None and not isinstance(ing, float) else []
        )
    return row


@app.get("/quick-recipes")
def get_quick_recipes(
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    max_time: int = Query(default=30, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    """Best recipes preparable within max_time minutes, ranked by yummy_score."""
    df = load_gold_data(country=country, month=month)
    return format_recipes(
        df[df["totaltime"] <= max_time]
        .sort_values("yummy_score", ascending=False)
        .head(limit)
    )


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
    country: str = Query(default="france"),
    month: int = Query(default=6, ge=1, le=12),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    """Best recipes matching a given category string (case-insensitive substring)."""
    df = load_gold_data(country=country, month=month)
    return format_recipes(
        df[df["recipecategory"].str.contains(category, case=False, na=False)]
        .sort_values("yummy_score", ascending=False)
        .head(limit)
    )


# -------------------------------------------------------------------
# Basket / seasonal context endpoints  (v1.2)
# -------------------------------------------------------------------

@app.get("/seasonal-products")
def get_seasonal_products(
    country: str = Query(..., description="Country name (lowercase, e.g. 'france', 'czechrepublic')"),
    month: int = Query(..., ge=1, le=12, description="Month number [1–12]"),
) -> list[dict]:
    """In-season EUFIC products for a given country and month.

    Returns [{product_name: str, is_in_season: bool}] filtered to the
    requested country × month.  Source: Silver EUFIC seasonality parquet.

    Returns 404 if the country has no EUFIC coverage.

    Country key format: lowercase, no spaces (e.g. 'czechrepublic', 'france').
    Use GET /countries to discover which countries have EUFIC data.
    """
    eufic = load_eufic_data()

    internal = _display_to_eufic_internal(country)
    rows = eufic[
        (eufic["country"] == internal) &
        (eufic["month_number"] == month)
    ][["product_name", "is_in_season"]].drop_duplicates()

    if rows.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No EUFIC seasonal data found for country={country!r} (tried internal key {internal!r})",
        )

    return rows.to_dict(orient="records")


@app.get("/faostat-staples")
def get_faostat_staples(
    country: str = Query(..., description="Country name (lowercase, e.g. 'france')"),
    top_n: int = Query(default=15, ge=1, le=100),
) -> list[dict]:
    """Top agricultural staples for a country by production volume (latest year).

    Aggregate FAOSTAT categories (e.g. 'vegetables primary', 'meat, total') are
    excluded so only specific food items are returned.  Source: Silver FAOSTAT QCL.

    Returns 404 if the country has no FAOSTAT coverage.
    Returns [{product_name: str, production_value: float}] sorted descending.
    """
    fao = load_faostat_data()
    country_key = country.lower().strip()

    country_df = fao[fao["country_name"] == country_key]
    if country_df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No FAOSTAT data found for country={country!r}",
        )

    latest = int(country_df["year"].max())
    recent = country_df[country_df["year"] == latest]

    specific = recent[
        ~recent["product_name"].apply(
            lambda n: any(p in n.lower() for p in _FAO_AGGREGATE_PATTERNS)
        )
    ]

    result = (
        specific
        .sort_values("production_value", ascending=False)
        .head(top_n)[["product_name", "production_value"]]
    )

    return result.to_dict(orient="records")


@app.get("/countries")
def get_countries() -> list[dict]:
    """All countries available across EUFIC and/or FAOSTAT, with source flags.

    Returns [{country: str, eufic: bool, faostat: bool}] sorted by country name.

    - eufic=true  → GET /seasonal-products?country=<country>&month=N is available.
    - faostat=true → GET /faostat-staples?country=<country> is available.
    - Both can be true simultaneously (29 EUFIC countries overlap with FAOSTAT).

    Country values in this response can be passed directly to other endpoints.
    """
    eufic_keys: set[str] = set()
    faostat_keys: set[str] = set()

    try:
        eufic = load_eufic_data()
        eufic_keys = set(eufic["country"].dropna().unique().tolist())
    except HTTPException:
        pass

    try:
        fao = load_faostat_data()
        faostat_keys = set(fao["country_name"].dropna().unique().tolist())
    except HTTPException:
        pass

    all_countries = eufic_keys | faostat_keys

    return sorted(
        [
            {
                "country": c,
                "eufic":   c in eufic_keys,
                "faostat": c in faostat_keys,
            }
            for c in all_countries
        ],
        key=lambda r: r["country"],
    )
