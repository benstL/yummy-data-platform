"""
Requête DuckDB sur gold_yummy_recommendations.parquet stocké dans MinIO.

Usage (depuis la racine du projet) :
    python tools/query_duckdb.py

Variables d'environnement (lues depuis .env ou le shell) :
    MINIO_ROOT_USER     — access key MinIO
    MINIO_ROOT_PASSWORD — secret key MinIO
    MINIO_ENDPOINT      — host:port (défaut : localhost:9000)

Pourquoi s3_url_style='path' (obligatoire pour MinIO) :
    S3 propose deux styles d'URL pour accéder aux buckets :
      · Virtual-hosted : https://<bucket>.s3.amazonaws.com/<key>
      · Path-style      : https://s3.amazonaws.com/<bucket>/<key>
    AWS S3 utilise virtual-hosted par défaut. MinIO, tournant sur un simple
    host:port sans wildcard DNS, ne peut pas résoudre <bucket>.localhost:9000.
    Sans s3_url_style='path', httpfs construit une URL virtual-hosted qui
    échoue en DNS ou en connexion refusée.

Pourquoi s3_use_ssl=false :
    MinIO dans Docker tourne en HTTP plain sur le port 9000.
    httpfs utilise HTTPS par défaut ; désactiver SSL correspond à la
    configuration du serveur et évite une erreur de certificat.
"""

import os

import duckdb
from dotenv import load_dotenv

# Charge .env depuis la racine du projet si présent (pratique en dev local).
load_dotenv()

BUCKET = "yummy"
PARQUET_KEY = "gold/gold_yummy_recommendations.parquet"
TOP_N = 10


def configure_s3(conn: duckdb.DuckDBPyConnection) -> None:
    """Installe l'extension httpfs et configure l'accès S3 pour MinIO.

    INSTALL httpfs est idempotent (no-op si déjà installée).
    LOAD est requis à chaque nouvelle connexion pour activer l'extension.
    Les SET s'appliquent uniquement à cette connexion.
    """
    conn.execute("INSTALL httpfs")
    conn.execute("LOAD httpfs")

    endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.environ["MINIO_ROOT_USER"]
    secret_key = os.environ["MINIO_ROOT_PASSWORD"]

    conn.execute(f"SET s3_endpoint='{endpoint}'")
    conn.execute(f"SET s3_access_key_id='{access_key}'")
    conn.execute(f"SET s3_secret_access_key='{secret_key}'")
    conn.execute("SET s3_use_ssl=false")
    # Path-style obligatoire pour MinIO — voir docstring du module.
    conn.execute("SET s3_url_style='path'")


def main() -> None:
    conn = duckdb.connect()
    print("[INFO] Configuration DuckDB → MinIO S3 ...")
    configure_s3(conn)

    url = f"s3://{BUCKET}/{PARQUET_KEY}"
    print(f"[INFO] Lecture de {url} ...")

    df = conn.execute(f"""
        SELECT recipeid, name, yummy_score, aggregatedrating, totaltime
        FROM read_parquet('{url}')
        ORDER BY yummy_score DESC
        LIMIT {TOP_N}
    """).fetchdf()

    print(f"[INFO] Top {TOP_N} recettes par yummy_score :")
    print(df.to_string(index=False))

    conn.close()


if __name__ == "__main__":
    main()
