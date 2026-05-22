"""
Synchronise la couche Bronze locale (data/bronze/) vers MinIO.

Pattern unique du projet : les extracts écrivent en local, ce script monte
tout vers MinIO en préservant l'arborescence (qui devient la clé S3).
Idempotent : ne réuploade que les fichiers absents ou de taille différente.
"""
from pathlib import Path

from common.minio_client import get_s3_client, ensure_bucket_exists, BRONZE_BUCKET

LOCAL_BRONZE_DIR = Path("data/bronze")


def _remote_size(s3_client, key: str) -> int | None:
    """Retourne la taille d'un objet distant, ou None s'il n'existe pas."""
    try:
        head = s3_client.head_object(Bucket=BRONZE_BUCKET, Key=key)
        return head["ContentLength"]
    except Exception:
        return None


def sync_local_to_minio() -> None:
    if not LOCAL_BRONZE_DIR.exists():
        print(f"[ERROR] Le dossier {LOCAL_BRONZE_DIR} n'existe pas.")
        return

    s3_client = get_s3_client()
    ensure_bucket_exists(s3_client)

    print(f"[INFO] Synchronisation {LOCAL_BRONZE_DIR} -> s3://{BRONZE_BUCKET}/")

    uploaded, skipped = 0, 0

    for local_file in LOCAL_BRONZE_DIR.rglob("*"):
        if not local_file.is_file():
            continue
        if local_file.suffix == ".log":
            continue # les logs ne sont pas de la donnée Bronze
        # La clé S3 reproduit l'arbo locale sous data/bronze/
        # ex: data/bronze/recipes/json/marmiton.json -> recipes/json/marmiton.json
        s3_key = local_file.relative_to(LOCAL_BRONZE_DIR).as_posix()

        # Idempotence : on saute si déjà présent avec la même taille
        local_size = local_file.stat().st_size
        if _remote_size(s3_client, s3_key) == local_size:
            skipped += 1
            continue

        print(f"  -> upload {s3_key}")
        s3_client.upload_file(str(local_file), BRONZE_BUCKET, s3_key)
        uploaded += 1

    print(f"\n[SUCCESS] {uploaded} fichier(s) montés, {skipped} déjà à jour (ignorés).")


if __name__ == "__main__":
    sync_local_to_minio()