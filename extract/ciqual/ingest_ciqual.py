"""
Ingestion de la table CIQUAL 2025 (ANSES) -> couche Bronze locale.
L'upload vers MinIO est délégué à sync_to_minio.py (pattern unique du projet).
"""
from pathlib import Path

import requests

CIQUAL_URL = (
    "https://ciqual.anses.fr/cms/sites/default/files/inline-files/"
    "Table%20Ciqual%202025_FR_2025_11_03.xls"
)
BRONZE_DIR = Path("data/bronze/ciqual")


def ingest_ciqual() -> None:
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)

    print("[INFO] Téléchargement de la table CIQUAL 2025...")
    response = requests.get(CIQUAL_URL, timeout=60)
    response.raise_for_status()

    filename = CIQUAL_URL.split("/")[-1].replace("%20", "_")
    if not filename.lower().endswith((".xls", ".xlsx")):
        filename = "TableCiqual2025.xls"

    output_path = BRONZE_DIR / filename
    output_path.write_bytes(response.content)

    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"[INFO] Fichier Bronze sauvegardé : {output_path} ({size_mb:.1f} Mo)")
    print("[SUCCESS] Ingestion CIQUAL terminée.")
    print("[INFO] Lance ensuite : python -m extract.sync_to_minio")


if __name__ == "__main__":
    ingest_ciqual()