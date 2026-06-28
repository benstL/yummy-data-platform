from datetime import datetime, UTC
from pathlib import Path
import shutil

import pandas as pd


SILVER_EUFIC_DIR = Path("data/silver/eufic")
SILVER_FAOSTAT_DIR = Path("data/silver/faostat/qcl")
GOLD_DIR = Path("data/gold")

IN_RECIPE_MATCHES = GOLD_DIR / "gold_recipe_ingredient_matches.parquet"

OUT_DURABILITY_DIR = GOLD_DIR / "gold_recipe_durability_scores"


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
    ref = eufic_df[
        (eufic_df["country"].str.lower() == country)
        & (eufic_df["month_number"] == month)
        & eufic_df["is_in_season"]
    ][["product_name"]].drop_duplicates()

    ref["seasonality_score"] = 1.0
    return ref


def build_availability_reference(
    faostat_df: pd.DataFrame,
    country: str,
) -> pd.DataFrame:
    ref = faostat_df[
        faostat_df["country_name"].str.lower() == country
    ].copy()

    if ref.empty:
        return pd.DataFrame(columns=["product_name", "availability_score"])

    latest_year = ref["year"].max()
    ref = ref[ref["year"] == latest_year].copy()

    ref["availability_score"] = normalize_series(ref["production_value"])

    return (
        ref[["product_name", "availability_score"]]
        .drop_duplicates("product_name")
    )


def prepare_recipe_matches(recipe_matches: pd.DataFrame) -> pd.DataFrame:
    df = recipe_matches.copy()

    df = df[
        df["matched_term"].notna()
        & (df["source"] != "unmatched")
    ].copy()

    df = df.drop_duplicates(
        subset=["recipeid", "matched_term"]
    )

    return df


def compute_coverage_score(recipe_matches: pd.DataFrame) -> pd.DataFrame:
    coverage = (
        recipe_matches.groupby("recipeid")
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


def compute_durability_scores(
    prepared_matches: pd.DataFrame,
    seasonality_ref: pd.DataFrame,
    availability_ref: pd.DataFrame,
) -> pd.DataFrame:
    df = prepared_matches.copy()

    df = df.merge(
        seasonality_ref,
        left_on="matched_term",
        right_on="product_name",
        how="left",
    )

    df = df.drop(columns=["product_name"], errors="ignore")
    df["seasonality_score"] = df["seasonality_score"].fillna(0.0)

    df = df.merge(
        availability_ref,
        left_on="matched_term",
        right_on="product_name",
        how="left",
    )

    df = df.drop(columns=["product_name"], errors="ignore")
    df["availability_score"] = df["availability_score"].fillna(0.0)

    df["ingredient_durability_score"] = (
        0.75 * df["seasonality_score"]
        + 0.25 * df["availability_score"]
    )

    df["has_positive_durability"] = df["ingredient_durability_score"] > 0

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

    agg["durability_score"] = agg["durability_mean"] * 100

    bonus_mask = agg["positive_durability_ratio"] >= (2 / 3)
    agg.loc[bonus_mask, "durability_score"] += 10
    agg["durability_score"] = agg["durability_score"].clip(upper=100)

    agg["seasonality_score"] = (
        agg["seasonal_ingredient_count"]
        / agg["recognized_ingredient_count"]
        * 100
    ).fillna(0)

    agg["availability_score"] = (agg["avg_availability_score"]).fillna(0) * 100
    agg["durability_mean"] = (agg["durability_mean"] ).fillna(0)* 100
    agg["positive_durability_ratio"] = (agg["positive_durability_ratio"]).fillna(0) * 100

    for col in [
        "seasonality_score",
        "availability_score",
        "durability_mean",
        "positive_durability_ratio",
        "durability_score",
    ]:
        agg[col] = agg[col].round(2)

    return agg


def build_country_month_result(
    country: str,
    month: int,
    eufic_df: pd.DataFrame,
    availability_ref: pd.DataFrame,
    prepared_matches: pd.DataFrame,
    coverage: pd.DataFrame,
    processed_at: str,
) -> pd.DataFrame:
    seasonality_ref = build_seasonality_reference(
        eufic_df=eufic_df,
        country=country,
        month=month,
    )

    durability = compute_durability_scores(
        prepared_matches=prepared_matches,
        seasonality_ref=seasonality_ref,
        availability_ref=availability_ref,
    )

    result = durability.merge(
        coverage,
        on="recipeid",
        how="left",
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
        if col in result.columns:
            result[col] = result[col].fillna(0)

    result["durability_country"] = country
    result["durability_month"] = month
    result["durability_processed_at"] = processed_at

    return result[
        [
            "recipeid",
            "durability_month",
            "recognized_ingredient_count",
            "total_ingredient_tokens",
            "matched_ingredient_tokens",
            "seasonality_score",
            "availability_score",
            "durability_mean",
            "positive_durability_ratio",
            "durability_score",
            "coverage_score",
            "durability_processed_at",
        ]
    ]


def main() -> None:
    print("[INFO] Building partitioned Gold durability dataset...")

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

    prepared_matches = prepare_recipe_matches(recipe_matches)
    coverage = compute_coverage_score(recipe_matches)

    countries = sorted(
        eufic_df["country"]
        .dropna()
        .str.lower()
        .unique()
    )

    processed_at = datetime.now(UTC).isoformat()

    if OUT_DURABILITY_DIR.exists():
        print(f"[INFO] Removing existing dataset: {OUT_DURABILITY_DIR}")
        shutil.rmtree(OUT_DURABILITY_DIR)

    OUT_DURABILITY_DIR.mkdir(parents=True, exist_ok=True)

    for country in countries:
        print(f"[INFO] Country: {country}")

        availability_ref = build_availability_reference(
            faostat_df=faostat_df,
            country=country,
        )

        if availability_ref.empty:
            print(
                f"[WARN] Aucune donnée FAOSTAT pour {country}. "
                "availability_score sera égal à 0."
            )

        monthly_results = []

        for month in range(1, 13):
            print(f"[INFO] Processing {country} - month {month}")

            result = build_country_month_result(
                country=country,
                month=month,
                eufic_df=eufic_df,
                availability_ref=availability_ref,
                prepared_matches=prepared_matches,
                coverage=coverage,
                processed_at=processed_at,
            )

            monthly_results.append(result)

        country_df = pd.concat(monthly_results, ignore_index=True)

        country_partition = OUT_DURABILITY_DIR / f"durability_country={country}"
        country_partition.mkdir(parents=True, exist_ok=True)

        output_file = country_partition / "data.parquet"
        country_df.to_parquet(output_file, index=False)

        print(f"[INFO] Saved: {output_file}")
        print(f"[INFO] Rows written for {country}: {len(country_df):,}")

        del country_df
        del monthly_results

    print(f"[INFO] Partitioned dataset saved in: {OUT_DURABILITY_DIR}")
    print("[INFO] Done.")


if __name__ == "__main__":
    main()
