from datetime import datetime, UTC
from pathlib import Path

import pandas as pd


SILVER_EUFIC_DIR = Path("data/silver/eufic")
SILVER_FAOSTAT_DIR = Path("data/silver/faostat/qcl")
GOLD_DIR = Path("data/gold")

IN_RECOMMENDATIONS = GOLD_DIR / "gold_yummy_recommendations.parquet"
IN_RECIPE_MATCHES = GOLD_DIR / "gold_recipe_ingredient_matches.parquet"

OUT_DURABILITY = GOLD_DIR / "gold_recipe_durability_scores.parquet"


def get_latest_file(directory: Path, pattern: str) -> Path:
    files = sorted(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"Aucun fichier trouvé : {directory}/{pattern}")
    return files[-1]


def normalize_series(series: pd.Series) -> pd.Series:
    series = series.fillna(0)
    if series.max() == series.min():
        return pd.Series(0.0, index=series.index)
    return (series - series.min()) / (series.max() - series.min())


def build_seasonality_reference(
    eufic_df: pd.DataFrame,
    country: str,
    month: int,
) -> pd.DataFrame:
    country = country.lower()

    ref = eufic_df[
        (eufic_df["country"] == country)
        & (eufic_df["month_number"] == month)
        & (eufic_df["is_in_season"] == True)
    ][["product_name"]].drop_duplicates()

    ref["seasonality_score"] = 1.0
    return ref


def build_availability_reference(
    faostat_df: pd.DataFrame,
    country: str,
) -> pd.DataFrame:
    country = country.lower()

    ref = faostat_df[faostat_df["country_name"] == country].copy()

    if ref.empty:
        raise ValueError(f"Aucune donnée FAOSTAT pour le pays : {country}")

    latest_year = ref["year"].max()
    ref = ref[ref["year"] == latest_year].copy()

    ref["availability_score"] = normalize_series(ref["production_value"])

    return ref[["product_name", "availability_score"]].drop_duplicates("product_name")


def compute_durability_scores(
    recipe_matches: pd.DataFrame,
    seasonality_ref: pd.DataFrame,
    availability_ref: pd.DataFrame,
) -> pd.DataFrame:
    """
    Score durable par recette.

    Logique :
    - on garde uniquement les ingrédients reconnus ;
    - on déduplique par recette et par ingrédient matché ;
    - score ingrédient = 75 % saisonnalité + 25 % disponibilité agricole ;
    - score recette = moyenne des scores ingrédients ;
    - bonus +10 si au moins 2/3 des ingrédients reconnus ont un score positif.
    """

    df = recipe_matches.copy()

    # 1. Garder uniquement les ingrédients matchés
    df = df[
        df["matched_term"].notna()
        & (df["source"] != "unmatched")
    ].copy()

    # 2. Dédupliquer pour éviter cucumber + cucumber = 200 %
    df = df.drop_duplicates(
        subset=["recipeid", "matched_term"]
    )

    # 3. Ajouter la saisonnalité EUFIC
    df = df.merge(
        seasonality_ref,
        left_on="matched_term",
        right_on="product_name",
        how="left",
    )

    df = df.drop(columns=["product_name"], errors="ignore")
    df["seasonality_score"] = df["seasonality_score"].fillna(0.0)

    # 4. Ajouter la disponibilité agricole FAOSTAT
    df = df.merge(
        availability_ref,
        left_on="matched_term",
        right_on="product_name",
        how="left",
    )

    df = df.drop(columns=["product_name"], errors="ignore")
    df["availability_score"] = df["availability_score"].fillna(0.0)

    # 5. Score durable par ingrédient
    df["ingredient_durability_score"] = (
        0.75 * df["seasonality_score"]
        + 0.25 * df["availability_score"]
    )

    df["has_positive_durability"] = df["ingredient_durability_score"] > 0

    # 6. Agrégation recette
    agg = (
        df.groupby("recipeid")
        .agg(
            recognized_ingredient_count=("matched_term", "count"),
            seasonal_ingredient_count=("seasonality_score", "sum"),
            avg_availability_score=("availability_score", "mean"),
            durability_mean=("ingredient_durability_score", "mean"),
            positive_durability_ratio=("has_positive_durability", "mean"),
        )
        .reset_index()
    )

    # 7. Score final
    agg["durability_score"] = agg["durability_mean"] * 100

    bonus_mask = agg["positive_durability_ratio"] >= (2 / 3)
    agg.loc[bonus_mask, "durability_score"] += 10

    agg["durability_score"] = agg["durability_score"].clip(upper=100)

    # 8. Scores lisibles sur 100
    agg["seasonality_score"] = (
        agg["seasonal_ingredient_count"]
        / agg["recognized_ingredient_count"]
        * 100
    )

    agg["availability_score"] = agg["avg_availability_score"] * 100
    agg["durability_mean"] = agg["durability_mean"] * 100
    agg["positive_durability_ratio"] = agg["positive_durability_ratio"] * 100

    # 9. Arrondis
    for col in [
        "seasonality_score",
        "availability_score",
        "durability_mean",
        "positive_durability_ratio",
        "durability_score",
    ]:
        agg[col] = agg[col].round(2)

    return agg


def compute_coverage_score(recipe_matches: pd.DataFrame) -> pd.DataFrame:
    df = recipe_matches.copy()

    coverage = (
        df.groupby("recipeid")
        .agg(
            total_ingredient_tokens=("ingredient_token", "nunique"),
            matched_ingredient_tokens=("matched_term", lambda x: x.notna().sum()),
        )
        .reset_index()
    )

    coverage["coverage_score"] = (
        coverage["matched_ingredient_tokens"]
        / coverage["total_ingredient_tokens"]
        * 100
    ).round(2)

    return coverage


def main(country: str = "france", month: int = 6) -> None:
    print("[INFO] Building Gold durability score...")

    eufic_file = get_latest_file(
        SILVER_EUFIC_DIR,
        "silver_seasonality_*.parquet",
    )

    faostat_file = get_latest_file(
        SILVER_FAOSTAT_DIR,
        "silver_faostat_qcl_production_*.parquet",
    )

    print(f"[INFO] Reading EUFIC: {eufic_file}")
    eufic_df = pd.read_parquet(eufic_file)

    print(f"[INFO] Reading FAOSTAT: {faostat_file}")
    faostat_df = pd.read_parquet(faostat_file)

    print(f"[INFO] Reading recipe matches: {IN_RECIPE_MATCHES}")
    recipe_matches = pd.read_parquet(IN_RECIPE_MATCHES)

    print(f"[INFO] Reading recommendations: {IN_RECOMMENDATIONS}")
    recommendations = pd.read_parquet(IN_RECOMMENDATIONS)

    print(f"[INFO] Country: {country}")
    print(f"[INFO] Month: {month}")

    seasonality_ref = build_seasonality_reference(
        eufic_df,
        country=country,
        month=month,
    )

    availability_ref = build_availability_reference(
        faostat_df,
        country=country,
    )

    durability = compute_durability_scores(
        recipe_matches,
        seasonality_ref,
        availability_ref,
    )

    coverage = compute_coverage_score(recipe_matches)

    final = (
        recommendations
        .merge(durability, on="recipeid", how="left")
        .merge(coverage, on="recipeid", how="left")
    )

    fill_cols = [
        "recognized_ingredient_count",
        "seasonal_ingredient_count",
        "avg_availability_score",
        "durability_mean",
        "positive_durability_ratio",
        "durability_score",
        "seasonality_score",
        "availability_score",
        "total_ingredient_tokens",
        "matched_ingredient_tokens",
        "coverage_score",
    ]

    for col in fill_cols:
        if col in final.columns:
            final[col] = final[col].fillna(0)

    final["durability_country"] = country
    final["durability_month"] = month
    final["durability_processed_at"] = datetime.now(UTC).isoformat()

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    final.to_parquet(OUT_DURABILITY, index=False)

    print(f"[INFO] Saved: {OUT_DURABILITY}")
    print(
        final[
            [
                "recipeid",
                "name",
                "yummy_score",
                "seasonality_score",
                "availability_score",
                "durability_mean",
                "positive_durability_ratio",
                "durability_score",
                "coverage_score",
            ]
        ].head(10)
    )


if __name__ == "__main__":
    main(country="france", month=6)
