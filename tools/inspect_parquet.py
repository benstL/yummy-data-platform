from pathlib import Path
import pandas as pd


DATA_DIR = Path("data/silver")


def inspect_parquet(file_path: Path, n_rows: int = 10) -> None:
    print("=" * 100)
    print(f"[INFO] File: {file_path}")
    print("=" * 100)

    df = pd.read_parquet(file_path)

    print(f"[INFO] Shape: {df.shape}")
    print("\n[INFO] Columns:")
    print(list(df.columns))

    print("\n[INFO] Preview:")
    print(df.head(n_rows))

    print("\n[INFO] Missing values:")
    print(df.isna().sum())


def main():
    parquet_files = list(DATA_DIR.rglob("*.parquet"))

    if not parquet_files:
        print("[WARNING] No parquet files found.")
        return

    for file_path in parquet_files:
        inspect_parquet(file_path)


if __name__ == "__main__":
    main()