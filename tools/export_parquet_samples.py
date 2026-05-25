from pathlib import Path
import pandas as pd


SILVER_DIR = Path("data/silver")
PREVIEW_DIR = Path("data/preview")


def main():
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    parquet_files = list(SILVER_DIR.rglob("*.parquet"))

    for file_path in parquet_files:
        df = pd.read_parquet(file_path)

        sample = df.head(100)

        output_name = file_path.stem + "_sample.csv"
        output_file = PREVIEW_DIR / output_name

        sample.to_csv(output_file, index=False)

        print(f"[INFO] Sample exported: {output_file}")


if __name__ == "__main__":
    main()