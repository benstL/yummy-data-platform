"""
Ingestion FAOSTAT QCL (Production Crops & Livestock) -> couche Bronze locale.
Données partitionnées par date d'extraction (extraction_date=YYYYMMDD).
L'upload vers MinIO est délégué à sync_to_minio.py (pattern unique du projet).
"""
from datetime import datetime, UTC
from pathlib import Path
from zipfile import ZipFile

import requests


FAOSTAT_QCL_BULK_URL = (
    "https://bulks-faostat.fao.org/production/"
    "Production_Crops_Livestock_E_All_Data_(Normalized).zip"
)

BRONZE_DIR = Path("data/bronze/faostat/qcl")


def download_file(url: str, output_path: Path) -> None:
    try:
        response = requests.get(url, timeout=180)
        response.raise_for_status()
        output_path.write_bytes(response.content)
    except requests.exceptions.RequestException as error:
        raise RuntimeError(f"FAOSTAT download failed: {error}") from error


def extract_zip(zip_path: Path, output_dir: Path) -> None:
    with ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(output_dir)


def main() -> None:
    print("[INFO] Starting FAOSTAT QCL Bronze extraction...")

    extraction_date = datetime.now(UTC).strftime("%Y%m%d")
    output_dir = BRONZE_DIR / f"extraction_date={extraction_date}"
    output_dir.mkdir(parents=True, exist_ok=True)

    zip_path = output_dir / "faostat_qcl_raw.zip"

    print("[INFO] Downloading FAOSTAT QCL bulk file...")
    print(f"[INFO] URL: {FAOSTAT_QCL_BULK_URL}")
    download_file(FAOSTAT_QCL_BULK_URL, zip_path)

    print("[INFO] Extracting ZIP file...")
    extract_zip(zip_path, output_dir)

    zip_path.unlink()  # le ZIP est redondant une fois extrait (gain disque SSD)
    print("[INFO] ZIP source supprimé après extraction.")

    print(f"[INFO] FAOSTAT QCL Bronze data saved in: {output_dir}")
    print("[SUCCESS] FAOSTAT QCL Bronze extraction completed.")
    print("[INFO] Lance ensuite : python -m extract.sync_to_minio")


if __name__ == "__main__":
    main()