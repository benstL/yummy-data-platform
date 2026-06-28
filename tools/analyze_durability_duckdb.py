from pathlib import Path

import duckdb


DATASET_PATH = "data/gold/gold_recipe_durability_scores/**/*.parquet"
OUT_DIR = Path("reports/metrics")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def run_query(name: str, query: str) -> None:
    print(f"\n===== {name} =====")
    df = duckdb.sql(query).df()
    print(df)
    df.to_csv(OUT_DIR / f"{name}.csv", index=False)


def main() -> None:
    run_query(
        "durability_global_stats",
        f'''
        SELECT
            COUNT(*) AS nb_lignes,
            COUNT(DISTINCT recipeid) AS nb_recettes,
            COUNT(DISTINCT durability_month) AS nb_mois,
            ROUND(AVG(durability_score), 2) AS score_moyen,
            ROUND(MIN(durability_score), 2) AS score_min,
            ROUND(MAX(durability_score), 2) AS score_max,
            ROUND(AVG(seasonality_score), 2) AS saisonnalite_moyenne,
            ROUND(AVG(availability_score), 2) AS disponibilite_moyenne,
            ROUND(AVG(coverage_score), 2) AS coverage_moyen
        FROM read_parquet('{DATASET_PATH}', filename=true);
        ''',
    )

    run_query(
        "durability_by_country",
        f'''
        SELECT
            regexp_extract(filename, 'durability_country=([^/]+)', 1) AS country,
            COUNT(*) AS nb_lignes,
            COUNT(DISTINCT recipeid) AS nb_recettes,
            ROUND(AVG(durability_score), 2) AS score_moyen,
            ROUND(AVG(seasonality_score), 2) AS saisonnalite_moyenne,
            ROUND(AVG(availability_score), 2) AS disponibilite_moyenne,
            ROUND(AVG(coverage_score), 2) AS coverage_moyen
        FROM read_parquet('{DATASET_PATH}', filename=true)
        GROUP BY country
        ORDER BY score_moyen DESC;
        ''',
    )

    run_query(
        "durability_by_month",
        f'''
        SELECT
            durability_month,
            COUNT(*) AS nb_lignes,
            ROUND(AVG(durability_score), 2) AS score_moyen,
            ROUND(AVG(seasonality_score), 2) AS saisonnalite_moyenne,
            ROUND(AVG(availability_score), 2) AS disponibilite_moyenne,
            ROUND(AVG(coverage_score), 2) AS coverage_moyen
        FROM read_parquet('{DATASET_PATH}', filename=true)
        GROUP BY durability_month
        ORDER BY durability_month;
        ''',
    )

    run_query(
        "durability_score_distribution",
        f'''
        SELECT
            CASE
                WHEN durability_score < 20 THEN '0-20'
                WHEN durability_score < 40 THEN '20-40'
                WHEN durability_score < 60 THEN '40-60'
                WHEN durability_score < 80 THEN '60-80'
                ELSE '80-100'
            END AS score_range,
            COUNT(*) AS nb_lignes,
            ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pourcentage
        FROM read_parquet('{DATASET_PATH}', filename=true)
        GROUP BY score_range
        ORDER BY score_range;
        ''',
    )


if __name__ == "__main__":
    main()

