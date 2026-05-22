"""
Ingestion Kaggle Food.com -> couche Bronze locale (data/bronze/food-com/).
L'upload vers MinIO est délégué à sync_to_minio.py (pattern unique du projet).
"""
import os
from pathlib import Path

# .env chargé AVANT l'import kaggle (l'API lit l'environnement à l'import)
from dotenv import load_dotenv
load_dotenv()

from kaggle.api.kaggle_api_extended import KaggleApi

DATASET_NAME = "shuyangli94/food-com-recipes-and-user-interactions"
BRONZE_DIR = Path("data/bronze/food-com")


def download_kaggle_to_bronze() -> None:
    """Télécharge le dataset Food.com et le dézippe dans la couche Bronze locale."""
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Authentification Kaggle...")
    api = KaggleApi()
    api.authenticate()

    print(f"[INFO] Téléchargement du dataset {DATASET_NAME}...")
    api.dataset_download_files(DATASET_NAME, path=BRONZE_DIR, unzip=True)

    csv_files = list(BRONZE_DIR.glob("*.csv"))
    if not csv_files:
        raise RuntimeError(
            f"Aucun CSV trouvé dans {BRONZE_DIR} après téléchargement Kaggle."
        )

    print(f"[INFO] {len(csv_files)} fichier(s) CSV téléchargé(s) dans {BRONZE_DIR}:")
    for f in csv_files:
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"  - {f.name} ({size_mb:.1f} Mo)")

    print("[SUCCESS] Ingestion Kaggle (Bronze local) terminée.")
    print("[INFO] Lance ensuite : python -m extract.sync_to_minio")


if __name__ == "__main__":
    download_kaggle_to_bronze()