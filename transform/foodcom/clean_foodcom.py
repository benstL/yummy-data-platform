from datetime import datetime, UTC
from pathlib import Path
import re
import string

import pandas as pd


BRONZE_DIR = Path("data/bronze/foodcom")
SILVER_DIR = Path("data/silver/foodcom")


def get_latest_extraction_dir() -> Path:

    dirs = sorted(BRONZE_DIR.glob("extraction_date=*"))

    if not dirs:
        raise FileNotFoundError("No Food.com extraction found")

    return dirs[-1]


def clean_text(value):

    if pd.isna(value):
        return ""

    value = str(value).lower().strip()

    value = re.sub(r"\s+", " ", value)

    value = value.translate(
        str.maketrans("", "", string.punctuation)
    )

    return value


def iso8601_to_minutes(duration):

    if pd.isna(duration):
        return 0

    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", str(duration))

    if match:

        hours = int(match.group(1)) if match.group(1) else 0

        minutes = int(match.group(2)) if match.group(2) else 0

        return hours * 60 + minutes

    return 0


def clean_recipes(df: pd.DataFrame) -> pd.DataFrame:

    df.columns = df.columns.str.lower()

    columns_to_keep = [
        "recipeid",
        "name",
        "cooktime",
        "preptime",
        "totaltime",
        "recipecategory",
        "recipeingredientparts",
        "aggregatedrating",
        "reviewcount",
        "recipeinstructions",
    ]

    df = df[columns_to_keep].copy()

    text_columns = [
        "name",
        "recipecategory",
        "recipeingredientparts",
        "recipeinstructions",
    ]

    for col in text_columns:
        df[col] = df[col].apply(clean_text)

    time_columns = [
        "cooktime",
        "preptime",
        "totaltime",
    ]

    for col in time_columns:
        df[col] = df[col].apply(iso8601_to_minutes)

    df["aggregatedrating"] = (
        df["aggregatedrating"]
        .fillna(0)
        .astype(float)
    )

    df["reviewcount"] = (
        df["reviewcount"]
        .fillna(0)
        .astype(float)
    )

    df = df.drop_duplicates(subset=["recipeid"])

    df["processed_at"] = datetime.now(UTC).isoformat()

    return df


def clean_reviews(df: pd.DataFrame) -> pd.DataFrame:

    df.columns = df.columns.str.lower()

    columns_to_keep = [
        "reviewid",
        "recipeid",
        "rating",
        "review",
    ]

    df = df[columns_to_keep].copy()

    df["review"] = df["review"].apply(clean_text)

    df["rating"] = (
        df["rating"]
        .fillna(0)
        .astype(float)
    )

    df = df.drop_duplicates(subset=["reviewid"])

    df["processed_at"] = datetime.now(UTC).isoformat()

    return df


def save_silver(
    recipes_df: pd.DataFrame,
    reviews_df: pd.DataFrame
):

    SILVER_DIR.mkdir(parents=True, exist_ok=True)

    processing_date = datetime.now(UTC).strftime("%Y%m%d")

    recipes_output = (
        SILVER_DIR /
        f"silver_recipes_{processing_date}.parquet"
    )

    reviews_output = (
        SILVER_DIR /
        f"silver_reviews_{processing_date}.parquet"
    )

    recipes_df.to_parquet(recipes_output, index=False)

    reviews_df.to_parquet(reviews_output, index=False)

    print(f"[INFO] Recipes saved: {recipes_output}")
    print(f"[INFO] Reviews saved: {reviews_output}")


def main():

    print("[INFO] Starting Food.com Silver transformation...")

    extraction_dir = get_latest_extraction_dir()

    recipes_file = extraction_dir / "recipes.csv"

    reviews_file = extraction_dir / "reviews.csv"

    print(f"[INFO] Reading recipes: {recipes_file}")

    recipes_df = pd.read_csv(recipes_file)

    print(f"[INFO] Reading reviews: {reviews_file}")

    reviews_df = pd.read_csv(reviews_file)

    print(f"[INFO] Recipes rows: {len(recipes_df)}")
    print(f"[INFO] Reviews rows: {len(reviews_df)}")

    recipes_clean = clean_recipes(recipes_df)

    reviews_clean = clean_reviews(reviews_df)

    print(f"[INFO] Clean recipes rows: {len(recipes_clean)}")
    print(f"[INFO] Clean reviews rows: {len(reviews_clean)}")

    save_silver(recipes_clean, reviews_clean)

    print("[INFO] Food.com Silver transformation completed.")


if __name__ == "__main__":
    main()