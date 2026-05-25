from datetime import datetime, UTC
from pathlib import Path

import pandas as pd


SILVER_FOODCOM_DIR = Path("data/silver/foodcom")
GOLD_DIR = Path("data/gold")


def get_latest_file(directory: Path, pattern: str) -> Path:
    files = sorted(directory.glob(pattern))

    if not files:
        raise FileNotFoundError(f"No file found for pattern: {pattern}")

    return files[-1]


def normalize_series(series: pd.Series) -> pd.Series:
    min_value = series.min()
    max_value = series.max()

    if max_value == min_value:
        return pd.Series([0.0] * len(series), index=series.index)

    return (series - min_value) / (max_value - min_value)


def build_yummy_score(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df["ingredient_count"] = (
        df["recipeingredientparts"]
        .fillna("")
        .apply(lambda x: len(str(x).split()))
    )

    df["rating_score"] = normalize_series(df["aggregatedrating"])

    df["popularity_score"] = normalize_series(df["reviewcount"])

    df["simplicity_score"] = 1 - normalize_series(df["totaltime"])

    df["ingredient_simplicity_score"] = 1 - normalize_series(df["ingredient_count"])

    df["yummy_score"] = (
        0.40 * df["rating_score"]
        + 0.25 * df["popularity_score"]
        + 0.20 * df["simplicity_score"]
        + 0.15 * df["ingredient_simplicity_score"]
    )

    df["yummy_score"] = (df["yummy_score"] * 100).round(2)

    return df


def main():
    print("[INFO] Building Gold YUMMY recommendations...")

    recipes_file = get_latest_file(
        SILVER_FOODCOM_DIR,
        "silver_recipes_*.parquet"
    )

    print(f"[INFO] Reading recipes: {recipes_file}")

    recipes_df = pd.read_parquet(recipes_file)

    gold_df = build_yummy_score(recipes_df)

    columns_to_keep = [
        "recipeid",
        "name",
        "recipecategory",
        "recipeingredientparts",
        "recipeinstructions",
        "totaltime",
        "ingredient_count",
        "aggregatedrating",
        "reviewcount",
        "rating_score",
        "popularity_score",
        "simplicity_score",
        "ingredient_simplicity_score",
        "yummy_score",
    ]

    gold_df = gold_df[columns_to_keep].copy()

    gold_df = gold_df.sort_values(
        by="yummy_score",
        ascending=False
    )

    gold_df["processed_at"] = datetime.now(UTC).isoformat()

    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    output_file = GOLD_DIR / "gold_yummy_recommendations.parquet"

    gold_df.to_parquet(output_file, index=False)

    print(f"[INFO] Gold recommendations saved: {output_file}")
    print("[INFO] Top 10 recommendations:")
    print(gold_df[["recipeid", "name", "yummy_score"]].head(10))


if __name__ == "__main__":
    main()