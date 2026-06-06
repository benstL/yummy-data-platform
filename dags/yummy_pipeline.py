"""
DAG Airflow : yummy_pipeline
Orchestration du pipeline de données Yummy :
  1. build_silver  → exécute tools/build_all_silver.py
  2. build_gold    → exécute transform/gold/build_gold_yummy_recommendations.py

Le DAG tourne tous les jours à minuit (schedule_interval="@daily").
En dehors de la planification, tu peux le déclencher manuellement depuis l'UI Airflow.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

# ------------------------------------------------------------
# Paramètres par défaut appliqués à toutes les tâches
# ------------------------------------------------------------
default_args = {
    "owner": "yummy",
    "depends_on_past": False,           # chaque run est indépendant
    "retries": 1,                       # 1 retry automatique en cas d'échec
    "retry_delay": timedelta(minutes=5),
}

# ------------------------------------------------------------
# Définition du DAG
# ------------------------------------------------------------
with DAG(
    dag_id="yummy_pipeline",
    description="Pipeline Medallion Yummy : Silver → Gold",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
    catchup=False,
    tags=["yummy", "medallion", "data-platform"],
) as dag:

    # ----------------------------------------------------------
    # TÂCHE 1 : Build Silver
    # Lance tools/build_all_silver.py depuis la racine du projet
    # Ce script exécute en séquence :
    #   - transform/eufic/clean_eufic.py
    #   - transform/faostat/clean_faostat_qcl.py
    #   - transform/foodcom/clean_foodcom.py
    # ----------------------------------------------------------
    build_silver = BashOperator(
        task_id="build_silver",
        bash_command="cd /opt/airflow/project && python tools/build_all_silver.py",
    )

    # ----------------------------------------------------------
    # TÂCHE 2 : Build Gold
    # Lance transform/gold/build_gold_yummy_recommendations.py
    # Lit les fichiers Silver Parquet, calcule le YUMMY Score,
    # et écrit data/gold/gold_yummy_recommendations.parquet
    # ----------------------------------------------------------
    build_gold = BashOperator(
        task_id="build_gold",
        bash_command="cd /opt/airflow/project && python transform/gold/build_gold_yummy_recommendations.py",
    )

    # ----------------------------------------------------------
    # TÂCHE 3 : Upload vers MinIO  ← À DÉCOMMENTER quand la PR
    #           feat/storage-dbt sera mergée
    #
    # Prérequis : service MinIO dans docker-compose.yml +
    #             variables MINIO_ENDPOINT, MINIO_ACCESS_KEY,
    #             MINIO_SECRET_KEY définies dans le .env
    # ----------------------------------------------------------
    # upload_to_minio = BashOperator(
    #     task_id="upload_to_minio",
    #     bash_command="cd /opt/airflow/project && python tools/upload_to_minio.py",
    # )

    # ----------------------------------------------------------
    # Ordre d'exécution
    # Actuellement  : Silver → Gold
    # Après merge   : Silver → Gold → MinIO (décommenter ci-dessous)
    # ----------------------------------------------------------
    # build_silver >> build_gold >> upload_to_minio  # ← après merge feat/storage-dbt
    build_silver >> build_gold                        # ← actif maintenant
