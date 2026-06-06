# YUMMY — Plateforme Data Alimentaire Durable
# YUMMY — Sustainable Food Data Platform

---

# 🇫🇷 Présentation

YUMMY est une plateforme data orientée analyse alimentaire durable, saisonnalité et supply chain agricole.

Le projet combine :
- des recettes,
- des avis utilisateurs,
- des données de saisonnalité,
- des statistiques agricoles mondiales

afin de construire des systèmes de recommandation alimentaire plus responsables.

---

# 🇫🇷 Objectifs

YUMMY vise à recommander des recettes selon :
- le pays,
- la saison,
- la disponibilité agricole,
- la satisfaction utilisateur.

Le projet cherche également à sensibiliser aux enjeux :
- de consommation saisonnière,
- de supply chain alimentaire,
- d'exploitation des données agricoles.

---

# 🇫🇷 Architecture

Le projet suit une architecture Medallion :

| Couche | Description | Statut |
|---|---|---|
| Bronze | Données brutes extraites | ✅ Opérationnel |
| Silver | Données nettoyées et standardisées | ✅ Opérationnel |
| Gold | Données analytiques enrichies + score de recommandation | ✅ Implémentée |

La couche Gold est produite par deux chemins complémentaires : le pipeline Python (`transform/gold/`, `ml/`) et le pipeline SQL (`dbt/`). → Voir `ml/README.md` pour le détail de la formule et des métriques.

---

# 🇫🇷 Sources actuelles

| Source | Usage | Statut |
|---|---|---|
| Food.com | Recettes et avis utilisateurs | Silver ready |
| EUFIC | Saisonnalité fruits et légumes | Silver ready |
| FAOSTAT | Production agricole mondiale | Silver ready |

---

# 🇫🇷 Fonctionnalités implémentées

- Extraction de données (Kaggle, Selenium, FAO bulk)
- Pipelines de transformation Bronze → Silver → Gold
- Enrichissement ML : analyse de sentiment VADER, matching TF-IDF des ingrédients, clustering KMeans
- Score de recommandation `yummy_score` (pipeline Python et pipeline dbt SQL)
- API FastAPI — `GET /recommendations`
- Interface Streamlit — sélection pays/saison, filtres cluster
- Object store MinIO avec pipeline dbt-duckdb (couche SQL sur Silver)
- CI/CD GitHub Actions (Python 3.12, pytest, ruff)
- Audit d'intégration bout en bout — `tools/healthcheck.py`
- Orchestration Airflow — DAG `yummy_pipeline` (Silver → Gold, @daily)

---

# 🇫🇷 Métriques Gold V1 — implémentées

La couche Gold calcule un `yummy_score` composite [0–100] à partir de quatre composantes :

| Composante | Poids | Description |
|---|---|---|
| `weighted_rating_score` | 35 % | Note Bayésienne (formule IMDB) |
| `shrunk_sentiment` | 25 % | Percentile VADER avec rétrécissement Bayésien |
| `popularity_score` | 20 % | Nombre d'avis normalisé |
| `simplicity_score` | 20 % | Inverse du temps de préparation normalisé |

→ Formule complète, paramètres et exemple chiffré : `ml/README.md §6`.

---

# 🇫🇷 Stack technique

## Implémenté

| Domaine | Technologies |
|---|---|
| Data engineering | Python 3.12, Pandas, PyArrow, Parquet |
| ML / NLP | scikit-learn, vaderSentiment, TF-IDF, KMeans |
| Infrastructure | Docker, docker-compose, MinIO (S3-compatible) |
| Couche SQL | DuckDB, dbt-duckdb |
| API | FastAPI, uvicorn |
| Frontend | Streamlit |
| CI/CD | GitHub Actions (push + pull request) |
| Orchestration | Apache Airflow |

## Restant

| Domaine | Technologies |
|---|---|
| Observabilité | À définir |

→ Détail infra (Docker, MinIO, DuckDB, dbt, CI) : `docs/INFRA.md`.

---

# 🇫🇷 Structure du projet

```
extract/     -> pipelines d'extraction (Kaggle, Selenium, FAO)
transform/   -> transformations Bronze → Silver → Gold
ml/          -> enrichissement ML (sentiment, matching, clustering)
dbt/         -> pipeline SQL Gold (dbt-duckdb sur MinIO)
api/         -> service FastAPI
app/         -> interface Streamlit
tools/       -> scripts utilitaires (upload MinIO, DuckDB, healthcheck…)
tests/       -> tests pytest + génération de fixtures
docs/        -> documentation technique interne
dags/        -> DAGs Airflow
data/        -> couches Medallion (gitignorées)
```

---

# 🇫🇷 Roadmap

## ✅ Fait

- Pipelines Bronze/Silver (Food.com, EUFIC, FAOSTAT)
- Couche Gold analytique avec `yummy_score`
- Enrichissement ML (VADER, TF-IDF, KMeans)
- API FastAPI et interface Streamlit
- Infrastructure Docker + MinIO + DuckDB + dbt
- CI/CD GitHub Actions
- Orchestration Airflow (DAG `yummy_pipeline`, Silver → Gold, @daily)

## 🔜 Restant

- Observabilité (métriques, alertes)

---

# EN Overview

YUMMY is a modern data platform focused on sustainable food analytics, seasonality, and agricultural supply chain awareness.

The project combines:
- recipes,
- user reviews,
- seasonality datasets,
- global agricultural statistics

to build more responsible food recommendation systems.

---

# EN Goals

YUMMY aims to recommend recipes according to:
- country,
- seasonality,
- agricultural availability,
- user satisfaction.

The platform also promotes awareness around:
- seasonal consumption,
- food supply chains,
- agricultural data analytics.

---

# EN Architecture

YUMMY follows a Medallion Architecture approach:

| Layer | Description | Status |
|---|---|---|
| Bronze | Raw extracted datasets | ✅ Implemented |
| Silver | Cleaned and standardized datasets | ✅ Implemented |
| Gold | Enriched analytical datasets + recommendation score | ✅ Implemented |

The Gold layer is produced by two complementary pipelines: the Python pipeline (`transform/gold/`, `ml/`) and the SQL pipeline (`dbt/`). → See `ml/README.md` for formula details and metrics.

---

# EN Current Data Sources

| Source | Purpose | Status |
|---|---|---|
| Food.com | Recipes & user reviews | Silver ready |
| EUFIC | Fruit & vegetable seasonality | Silver ready |
| FAOSTAT | Global agricultural production | Silver ready |

---

# EN Implemented Features

- Data extraction pipelines (Kaggle, Selenium, FAO bulk)
- Bronze → Silver → Gold transformation pipelines
- ML enrichment: VADER sentiment analysis, TF-IDF ingredient matching, KMeans clustering
- `yummy_score` recommendation score (Python pipeline and dbt SQL pipeline)
- FastAPI service — `GET /recommendations`
- Streamlit UI — country/season selection, cluster filters
- MinIO object store with dbt-duckdb SQL layer (Gold over Silver)
- CI/CD with GitHub Actions (Python 3.12, pytest, ruff)
- End-to-end integration audit — `tools/healthcheck.py`
- Airflow orchestration — DAG `yummy_pipeline` (Silver → Gold, @daily)

---

# EN Gold Metrics V1 — Implemented

The Gold layer computes a composite `yummy_score` [0–100] from four components:

| Component | Weight | Description |
|---|---|---|
| `weighted_rating_score` | 35 % | Bayesian weighted rating (IMDB formula) |
| `shrunk_sentiment` | 25 % | VADER percentile with Bayesian shrinkage |
| `popularity_score` | 20 % | Normalised review count |
| `simplicity_score` | 20 % | Inverse of normalised cook time |

→ Full formula, parameters, and worked example: `ml/README.md §6`.

---

# EN Tech Stack

## Implemented

| Domain | Technologies |
|---|---|
| Data engineering | Python 3.12, Pandas, PyArrow, Parquet |
| ML / NLP | scikit-learn, vaderSentiment, TF-IDF, KMeans |
| Infrastructure | Docker, docker-compose, MinIO (S3-compatible) |
| SQL layer | DuckDB, dbt-duckdb |
| API | FastAPI, uvicorn |
| Frontend | Streamlit |
| CI/CD | GitHub Actions (push + pull request) |
| Orchestration | Apache Airflow |

## Remaining

| Domain | Technologies |
|---|---|
| Observability | To be defined |

→ Infrastructure detail (Docker, MinIO, DuckDB, dbt, CI): `docs/INFRA.md`.

---

# EN Project Structure

```
extract/     -> extraction pipelines (Kaggle, Selenium, FAO)
transform/   -> Bronze → Silver → Gold transformations
ml/          -> ML enrichment (sentiment, matching, clustering)
dbt/         -> SQL Gold pipeline (dbt-duckdb on MinIO)
api/         -> FastAPI service
app/         -> Streamlit frontend
tools/       -> utility scripts (MinIO upload, DuckDB, healthcheck…)
tests/       -> pytest tests and fixture generation
docs/        -> internal technical documentation
dags/        -> Airflow DAGs
data/        -> Medallion layers (gitignored)
```

---

# EN Roadmap

## ✅ Done

- Bronze/Silver pipelines (Food.com, EUFIC, FAOSTAT)
- Gold analytical layer with `yummy_score`
- ML enrichment (VADER, TF-IDF, KMeans)
- FastAPI service and Streamlit UI
- Docker + MinIO + DuckDB + dbt infrastructure
- CI/CD with GitHub Actions
- Airflow orchestration (DAG `yummy_pipeline`, Silver → Gold, @daily)

## 🔜 Remaining

- Observability (metrics, alerting)

---

# Vision

YUMMY is not only a recipe application.

The project aims to become a sustainable food intelligence platform combining:
- data engineering,
- analytics,
- NLP,
- food supply chain insights,
- sustainability awareness.
