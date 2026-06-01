"""
Upload local data layers (bronze, silver, gold) to the MinIO bucket 'yummy'.

Usage (depuis la racine du projet) :
    python tools/upload_to_minio.py

Variables d'environnement (lues depuis .env ou le shell) :
    MINIO_ROOT_USER     — access key MinIO
    MINIO_ROOT_PASSWORD — secret key MinIO
    MINIO_ENDPOINT      — host:port (défaut : localhost:9000)

Layout S3 produit :
    data/bronze/... → s3://yummy/bronze/...
    data/silver/... → s3://yummy/silver/...
    data/gold/...   → s3://yummy/gold/...
"""

import os
import sys
from pathlib import Path

import boto3
from botocore.config import Config
from dotenv import load_dotenv

# Charge .env depuis la racine du projet si présent (pratique en dev local).
load_dotenv()

BUCKET = "yummy"
DATA_DIR = Path("data")
LAYERS = ["bronze", "silver", "gold"]


def get_client():
    """Crée un client boto3 S3 pointant sur l'instance MinIO locale.

    Pourquoi use_ssl=False :
        MinIO dans Docker tourne en HTTP plain sur le port 9000.
        boto3 utilise HTTPS par défaut ; use_ssl=False évite une erreur de
        handshake TLS sur un endpoint HTTP.

    Pourquoi endpoint_url avec http:// :
        boto3 appelle AWS S3 par défaut. endpoint_url redirige toutes les
        requêtes vers MinIO.

    Pourquoi signature_version='s3v4' :
        MinIO requiert AWS Signature Version 4. Version 2 produirait un 403.
    """
    endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    return boto3.client(
        "s3",
        endpoint_url=f"http://{endpoint}",
        aws_access_key_id=os.environ["MINIO_ROOT_USER"],
        aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
        config=Config(signature_version="s3v4"),
        use_ssl=False,
    )


def upload_layer(client, layer: str) -> int:
    """Upload tous les fichiers de data/<layer>/ vers s3://yummy/<layer>/...

    Préserve la sous-arborescence complète : le chemin relatif de chaque
    fichier par rapport à data/ devient directement la clé S3.
    Exemple :
        data/silver/foodcom/silver_recipes_20260528.parquet
        → s3://yummy/silver/foodcom/silver_recipes_20260528.parquet

    Retourne le nombre de fichiers uploadés.
    """
    layer_path = DATA_DIR / layer
    if not layer_path.exists():
        print(f"[WARNING] {layer_path} introuvable — layer '{layer}' ignoré.")
        return 0

    count = 0
    for file_path in sorted(layer_path.rglob("*")):
        if not file_path.is_file():
            continue
        # as_posix() garantit des séparateurs '/' sur Windows/WSL.
        s3_key = file_path.relative_to(DATA_DIR).as_posix()
        print(f"[INFO]   {file_path}  →  s3://{BUCKET}/{s3_key}")
        client.upload_file(str(file_path), BUCKET, s3_key)
        count += 1

    return count


def main() -> None:
    print("[INFO] Connexion à MinIO ...")
    client = get_client()

    total = 0
    for layer in LAYERS:
        print(f"[INFO] === Layer : {layer} ===")
        n = upload_layer(client, layer)
        print(f"[INFO] {layer} : {n} fichier(s) uploadé(s).")
        total += n

    print(f"[INFO] Terminé — {total} fichier(s) au total.")


if __name__ == "__main__":
    main()
