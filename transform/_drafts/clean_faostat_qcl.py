from datetime import datetime, UTC
from pathlib import Path

import pandas as pd


BRONZE_DIR = Path("data/bronze/faostat/qcl")
SILVER_DIR = Path("data/silver/faostat/qcl")

SOURCE_FILE_NAME = "Production_Crops_Livestock_E_All_Data_(Normalized).csv"


def get_latest_extraction_dir() -> Path:
    extraction_dirs = sorted(BRONZE_DIR.glob("extraction_date=*"))

    if not extraction_dirs:
        raise FileNotFoundError(f"No FAOSTAT extraction folder found in {BRONZE_DIR}")

    return extraction_dirs[-1]


def clean_text_column(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"\s+", " ", regex=True)
    )


def load_faostat_csv(file_path: Path) -> pd.DataFrame:
    print(f"[INFO] Reading FAOSTAT file: {file_path}")

    return pd.read_csv(file_path, low_memory=False)


def clean_faostat_qcl(df: pd.DataFrame) -> pd.DataFrame:
    required_columns = {
        "Area Code",
        "Area",
        "Item Code",
        "Item",
        "Element",
        "Year",
        "Unit",
        "Value",
    }

    missing_columns = required_columns - set(df.columns)

    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    df = df.copy()

    # Keep only agricultural production
    df = df[df["Element"] == "Production"]

    df = df[
        [
            "Area Code",
            "Area",
            "Item Code",
            "Item",
            "Element",
            "Year",
            "Unit",
            "Value",
        ]
    ]

    df = df.rename(
        columns={
            "Area Code": "area_code",
            "Area": "country_name",
            "Item Code": "item_code",
            "Item": "product_name",
            "Element": "element",
            "Year": "year",
            "Unit": "unit",
            "Value": "production_value",
        }
    )

    df["country_name"] = clean_text_column(df["country_name"])
    df["product_name"] = clean_text_column(df["product_name"])
    df["element"] = clean_text_column(df["element"])
    df["unit"] = clean_text_column(df["unit"])

    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["production_value"] = pd.to_numeric(df["production_value"], errors="coerce")

    df = df.dropna(
        subset=[
            "country_name",
            "product_name",
            "year",
            "production_value",
        ]
    )

    df["year"] = df["year"].astype(int)

    df["source"] = "faostat_qcl"
    df["processed_at"] = datetime.now(UTC).isoformat()

    df = df.drop_duplicates(
        subset=[
            "area_code",
            "item_code",
            "year",
            "element",
        ]
    )

    return df


def save_silver(df: pd.DataFrame) -> Path:
    SILVER_DIR.mkdir(parents=True, exist_ok=True)

    processing_date = datetime.now(UTC).strftime("%Y%m%d")
    output_file = SILVER_DIR / f"silver_faostat_qcl_production_{processing_date}.parquet"

    df.to_parquet(output_file, index=False)

    print(f"[INFO] Silver file saved: {output_file}")

    return output_file


def main():
    print("[INFO] Starting FAOSTAT QCL Silver transformation...")

    latest_dir = get_latest_extraction_dir()
    source_file = latest_dir / SOURCE_FILE_NAME

    if not source_file.exists():
        raise FileNotFoundError(f"FAOSTAT source file not found: {source_file}")

    df_raw = load_faostat_csv(source_file)

    print(f"[INFO] Bronze rows: {len(df_raw)}")

    df_clean = clean_faostat_qcl(df_raw)

    print(f"[INFO] Silver rows: {len(df_clean)}")
    print(df_clean.head())

    save_silver(df_clean)

    print("[INFO] FAOSTAT QCL Silver transformation completed.")


if __name__ == "__main__":
    main()