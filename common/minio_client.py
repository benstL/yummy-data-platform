"""
Module centralisé pour la connexion à MinIO (S3).
Importé par tous les scripts qui écrivent dans le stockage objet.
"""
import os
import boto3
from dotenv import load_dotenv

# On charge le .env une seule fois ici pour tous les scripts
load_dotenv()

BRONZE_BUCKET = "bronze"


def get_s3_client():
    """Retourne un client boto3 configuré pour MinIO.

    L'endpoint s'adapte via MINIO_ENDPOINT (localhost en dev, 'minio' en Docker).
    Les credentials sont OBLIGATOIRES : on échoue vite et clairement s'ils
    manquent, plutôt que de se connecter silencieusement avec des valeurs par
    défaut qui masqueraient une mauvaise configuration.
    """
    endpoint = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
    key = os.getenv("AWS_ACCESS_KEY_ID")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY")

    if not key or not secret:
        raise RuntimeError(
            "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY manquants. "
            "Vérifie que ton fichier .env est présent et chargé."
        )

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=key,
        aws_secret_access_key=secret,
    )


def ensure_bucket_exists(client, bucket_name=BRONZE_BUCKET):
    """Vérifie si le bucket existe, sinon le crée."""
    try:
        client.head_bucket(Bucket=bucket_name)
    except Exception:
        print(f"[INFO] Création du bucket '{bucket_name}'...")
        client.create_bucket(Bucket=bucket_name)