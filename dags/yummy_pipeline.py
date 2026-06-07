"""
DAG Airflow : yummy_pipeline
Orchestration du pipeline de données Yummy :
  1. build_silver      → exécute tools/build_all_silver.py
  2. build_gold        → exécute transform/gold/build_gold_yummy_recommendations.py
  3. upload_to_minio   → exécute tools/upload_to_minio.py

Schedule : tous les jours à minuit UTC. Déclenchable manuellement depuis l'UI (port 8080).
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "yummy",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="yummy_pipeline",
    description="Pipeline Medallion Yummy : Silver -> Gold -> MinIO",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["yummy", "medallion", "data-platform"],
) as dag:

    build_silver = BashOperator(
        task_id="build_silver",
        bash_command="cd /opt/airflow/project && python tools/build_all_silver.py",
    )

    build_gold = BashOperator(
        task_id="build_gold",
        bash_command="cd /opt/airflow/project && python transform/gold/build_gold_yummy_recommendations.py",
    )

    upload_to_minio = BashOperator(
        task_id="upload_to_minio",
        bash_command="cd /opt/airflow/project && python tools/upload_to_minio.py",
    )

    build_silver >> build_gold >> upload_to_minio
