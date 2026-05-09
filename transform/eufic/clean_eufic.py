from datetime import datetime, UTC
from pathlib import Path

import pandas as pd


BRONZE_DIR = Path("data/bronze/eufic")
SILVER_DIR = Path("data/silver/eufic")


MONTH_MAPPING = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def get_latest_bronze_file() -> Path:
    files = sorted(BRONZE_DIR.glob("eufic_raw_*.csv"))

    if not files:
        raise FileNotFoundError(f"No EUFIC bronze file found in {BRONZE_DIR}")

    return files[-1]


def clean_text_column(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", " ", regex=True)
    )


def clean_eufic_data(df: pd.DataFrame) -> pd.DataFrame:
    required_columns = {
        "product_name",
        "product_type",
        "month",
        "country",
        "source",
        "extracted_at",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    df = df.copy()

    df["product_name"] = clean_text_column(df["product_name"])
    df["product_type"] = clean_text_column(df["product_type"])
    df["month"] = clean_text_column(df["month"])
    df["country"] = clean_text_column(df["country"])
    df["source"] = clean_text_column(df["source"])

    df["month_number"] = df["month"].map(MONTH_MAPPING)

    df = df.dropna(subset=["product_name", "product_type", "month_number", "country"])

    df["month_number"] = df["month_number"].astype(int)

    df["is_in_season"] = True
    df["confidence_score"] = 1.0
    df["processed_at"] = datetime.now(UTC).isoformat()

    df = df[
        [
            "product_name",
            "product_type",
            "month",
            "month_number",
            "country",
            "is_in_season",
            "confidence_score",
            "source",
            "extracted_at",
            "processed_at",
        ]
    ]

    df = df.drop_duplicates(
        subset=["product_name", "product_type", "month_number", "country"]
    )

    return df


def save_silver(df: pd.DataFrame) -> Path:
    SILVER_DIR.mkdir(parents=True, exist_ok=True)

    processing_date = datetime.now(UTC).strftime("%Y%m%d")

    output_file = SILVER_DIR / f"silver_seasonality_{processing_date}.parquet"

    df.to_parquet(output_file, index=False)

    print(f"[INFO] Silver file saved: {output_file}")

    return output_file


def main():
    print("[INFO] Starting EUFIC Silver transformation...")

    bronze_file = get_latest_bronze_file()

    print(f"[INFO] Reading Bronze file: {bronze_file}")

    df_raw = pd.read_csv(bronze_file)

    print(f"[INFO] Bronze rows: {len(df_raw)}")

    df_clean = clean_eufic_data(df_raw)

    print(f"[INFO] Silver rows: {len(df_clean)}")
    print(df_clean.head())

    save_silver(df_clean)

    print("[INFO] EUFIC Silver transformation completed.")


if __name__ == "__main__":
    main()