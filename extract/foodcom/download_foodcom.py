from pathlib import Path
from zipfile import ZipFile
from datetime import datetime, UTC

from kaggle.api.kaggle_api_extended import KaggleApi


DATASET = "irkaal/foodcom-recipes-and-reviews"

BRONZE_DIR = Path("data/bronze/foodcom")


def init_kaggle():
    api = KaggleApi()
    api.authenticate()
    return api


def main():

    print("[INFO] Starting Food.com Bronze extraction...")

    extraction_date = datetime.now(UTC).strftime("%Y%m%d")

    output_dir = BRONZE_DIR / f"extraction_date={extraction_date}"

    output_dir.mkdir(parents=True, exist_ok=True)

    api = init_kaggle()

    print("[INFO] Downloading dataset from Kaggle...")

    api.dataset_download_files(
        DATASET,
        path=output_dir,
        unzip=False
    )

    zip_path = output_dir / "foodcom-recipes-and-reviews.zip"

    print("[INFO] Extracting ZIP archive...")

    with ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(output_dir)

    print(f"[INFO] Dataset extracted to: {output_dir}")

    print("[INFO] Food.com Bronze extraction completed.")


if __name__ == "__main__":
    main()