# YUMMY — Plateforme Data Alimentaire Durable
# YUMMY — Sustainable Food Data Platform

---

# 🇫 🇷 Présentation

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
| Gold | Données analytiques enrichies + score de recommandation et de durabilité | ✅ Implémentée |

La couche Gold est produite par le pipeline Python (`transform/gold/`, `ml/`), orchestré par Airflow. Un pipeline dbt-duckdb (`dbt/`) fournit une implémentation SQL de validation croisée du `yummy_score` (hors chemin de production V1 — voir `ml/README.md §1`). → Voir `ml/README.md` pour le détail de la formule et des métriques.

---

## 🇫🇷 API REST

L'API FastAPI expose les données de la couche Gold.

Principaux endpoints :

| Endpoint | Description |
|-----------|------------|
| `GET /` | Vérification du service |
| `GET /health` | Santé de l'API |
| `GET /stats` | Statistiques globales |
| `GET /recommendations` | Top recettes selon le Yummy Score |
| `GET /durability` | Top recettes selon le Durability Score |
| `GET /recipes-by-score` | Classement selon le score choisi |
| `GET /recipe/{recipeid}` | Détail d'une recette |
| `GET /quick-recipes` | Recettes rapides |
| `GET /category/{category}` | Recettes d'une catégorie |

Le répertoire partitionné utilisé par l'API FastAPI est désormais :

```text
data/gold/gold_recipe_durability_scores/durability_country=<X>/data.parquet
```

Les endpoints `/recommendations` et `/durability` acceptent les paramètres `country` et `month` (défaut : `france` / `6`). La jointure avec les recommandations s'effectue à la requête. Codes d'erreur : `404` pour pays inconnu ou sans données, `500` si colonne manquante.

Documentation interactive :

```text
http://localhost:8000/docs
```

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
- Score de recommandation `yummy_score` (pipeline Python, orchestré Airflow ; pipeline dbt SQL en validation croisée hors prod V1)
- Score de durabilité basé sur la saisonnalité (EUFIC) et la disponibilité agricole (FAOSTAT)
- API FastAPI (v1.2 — 13 endpoints) :
  - `GET /` : vérification du service
  - `GET /health` : état de l'API et présence du fichier Gold
  - `GET /stats` : statistiques globales du dataset
  - `GET /recommendations` : meilleures recettes selon le Yummy Score
  - `GET /durability` : meilleures recettes selon le Score de Durabilité
  - `GET /recipes-by-score` : classement selon le score choisi
  - `GET /recipe/{recipeid}` : détail d'une recette
  - `GET /quick-recipes` : recettes rapides selon un temps maximum
  - `GET /category/{category}` : recommandations par catégorie
  - `GET /basket-recommendations?country=&month=&basket=` : filtrage par panier d'ingrédients
  - `GET /seasonal-products?country=&month=` : produits EUFIC en saison
  - `GET /faostat-staples?country=` : aliments de base FAOSTAT
  - `GET /countries` : liste des pays disponibles (EUFIC ∪ FAOSTAT, booléens)
- Interface Streamlit — sélection pays/saison, filtres cluster
- Object store MinIO avec pipeline dbt-duckdb (validation croisée SQL du `yummy_score` sur Silver + Gold, hors prod V1)
- CI/CD GitHub Actions (Python 3.12, pytest, ruff)
- Audit d'intégration bout en bout — `tools/healthcheck.py`
- Orchestration Airflow — DAG `yummy_pipeline` (Silver → Gold → upload MinIO, @daily)

> **Stockage des données (V1) :** l'API (`api/main.py`) et l'interface Streamlit lisent les parquets Gold/Silver depuis le **système de fichiers local** (`data/gold/`, `data/silver/`) — sans `storage_options`, boto3 ni MinIO. MinIO est provisionné dans `docker-compose` et utilisé **exclusivement** par le pipeline dbt de validation croisée (lecture des Silver depuis `s3://yummy/silver/` et écriture de `dbt_yummy_recommendations.parquet` sur `s3://yummy/gold/`). Aucun composant applicatif (API, UI) ne lit depuis MinIO en V1. **Choix assumé :** la lecture locale garantit une démo fluide et hors-ligne. Le passage de la couche Gold sur S3/MinIO comme stockage runtime (API+UI lisant via `storage_options`) est un objectif d'industrialisation V2, activable par configuration sans changement de formule.

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

# 🇫🇷 Score de durabilité

Afin de compléter le Yummy Score, un score de durabilité a été développé.

Alors que le Yummy Score mesure principalement la satisfaction potentielle des utilisateurs, le score de durabilité cherche à évaluer la cohérence d'une recette avec la saisonnalité des ingrédients et leur disponibilité agricole.

## Sources utilisées

Le score repose sur deux sources de données :

- EUFIC : données de saisonnalité des fruits et légumes selon le pays et le mois ;
- FAOSTAT : statistiques de production agricole par pays.

## Calcul du score

### Étape 1 : score de l'ingrédient

Pour chaque ingrédient reconnu :

```text
score_ingrédient = 75 % saisonnalité + 25 % disponibilité agricole
```

Un ingrédient :

- de saison ;
- et fortement produit dans le pays

obtiendra un score élevé.

Par exemple :

| Produit | Saisonnalité | Disponibilité | Score |
|----------|----------|----------|----------|
| Tomate française en juillet | élevée | élevée | élevé |
| Tomate française en janvier | faible | élevée | moyen |
| Mangue en France | faible | faible | faible |

### Étape 2 : score de durabilité de la recette

Une fois le score calculé pour chaque ingrédient reconnu, le score de durabilité de la recette correspond à la moyenne des scores des ingrédients.

```text
score_recette = moyenne(score_ingrédient)
```

Exemple :

| Ingrédient | Score |
|------------|--------|
| Tomate | 100 |
| Courgette | 90 |
| Mangue | 10 |

```text
score_recette = (100 + 90 + 10) / 3
score_recette = 66,7
```

Cette approche permet d'éviter qu'un seul ingrédient très durable ou très peu durable influence excessivement le résultat final.

### Étape 3 : bonus de cohérence

Un bonus est appliqué lorsque plus des deux tiers des ingrédients reconnus possèdent un score positif.

L'objectif est de valoriser les recettes dont la majorité des ingrédients sont cohérents avec la saison et le contexte agricole du pays étudié.

### Métriques générées

Le pipeline produit les indicateurs suivants :

- `seasonality_score`
- `availability_score`
- `durability_score`
- `coverage_score`
---


## 🇫🇷 Jeux de données Gold

La couche Gold produit plusieurs jeux de données enrichis utilisés par l'API et l'interface Streamlit.

| Fichier | Description |
|----------|------------|
| `gold_yummy_recommendations.parquet` | Dataset principal contenant les r/recettes enrichies et le `yummy_score` |
| `gold_sentiment_scores.parquet` | Scores de sentiment calculés à partir des avis utilisateurs (VADER) |
| `gold_ingredient_matches.parquet` | Résultats du matching d'ingrédients par TF-IDF |
| `gold_recipe_clusters.parquet` | Clusters de recettes générés par KMeans |
| `gold_cluster_profiles.parquet` | Profils statistiques des clusters |
| `gold_recipe_ingredient_map.parquet` | Mapping entre recettes et ingrédients |
| `gold_recipe_durability_scores/` | Scores de durabilité partitionnés par pays (29 × 12 mois), calculés à partir d'EUFIC et FAOSTAT |
| `gold_recipe_ingredient_matches.parquet` | Correspondances détaillées entre recettes et ingrédients reconnus |

Le répertoire partitionné de durabilité utilisé par l'API FastAPI :

```text
data/gold/gold_recipe_durability_scores/durability_country=<X>/data.parquet
```

Colonnes durabilité exposées (jointes dynamiquement aux recommandations) :

- `durability_score`
- `seasonality_score`
- `availability_score`
- `coverage_score`
- `durability_month`

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
api/         -> service FastAPI (recommandations, statistiques et recherche de recettes)
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
- Couche Gold de durabilité basée sur EUFIC et FAOSTAT
- Enrichissement ML (VADER, TF-IDF, KMeans)
- API FastAPI et interface Streamlit
- Infrastructure Docker + MinIO + DuckDB + dbt
- CI/CD GitHub Actions
- Orchestration Airflow (DAG `yummy_pipeline`, Silver → Gold → upload MinIO, @daily)

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
| Gold | Enriched analytical datasets + recommendation and sustainability score | ✅ Implemented |

The Gold layer is produced by the Python pipeline (`transform/gold/`, `ml/`), orchestrated by Airflow. A dbt-duckdb pipeline (`dbt/`) provides a SQL cross-validation implementation of `yummy_score` (outside the V1 production path — see `ml/README.md §1`). → See `ml/README.md` for formula details and metrics.

---

# EN REST API

The FastAPI service exposes the Gold recommendation layer generated by the YUMMY pipeline.

| Endpoint | Description |
|-----------|------------|
| `GET /` | Service status check |
| `GET /health` | API health check and Gold file availability |
| `GET /stats` | Global statistics about the recommendation dataset |
| `GET /recommendations` | Top recipes ranked by Yummy Score |
| `GET /durability` | Top recipes ranked by sustainability score |
| `GET /recipes-by-score` | Rankings by Yummy Score or sustainability score |
| `GET /recipe/{recipeid}` | Detailed information about a specific recipe |
| `GET /quick-recipes` | Best recipes below a maximum preparation time |
| `GET /category/{category}` | Best recipes for a given recipe category |

Interactive API documentation:

```text
http://localhost:8000/docs
```

The partitioned directory read by the FastAPI service is:

```text
data/gold/gold_recipe_durability_scores/durability_country=<X>/data.parquet
```

The `/recommendations` and `/durability` endpoints accept `country` and `month` query parameters (defaults: `france` / `6`). The join with recommendations is done at request time. Error codes: `404` for unknown country or no data, `500` for missing column.

This dataset is generated by the ML and Gold pipeline:

```bash
python3 transform/gold/build_gold_durability_score.py
```

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
- `yummy_score` recommendation score (Python pipeline orchestrated by Airflow; dbt SQL pipeline as cross-validation, outside V1 prod path)
- Sustainability score based on ingredient seasonality (EUFIC) and agricultural availability (FAOSTAT)
- FastAPI service (v1.2 — 13 endpoints):
  - `GET /`
  - `GET /health`
  - `GET /stats`
  - `GET /recommendations`
  - `GET /durability`
  - `GET /recipes-by-score`
  - `GET /recipe/{recipeid}`
  - `GET /quick-recipes`
  - `GET /category/{category}`
  - `GET /basket-recommendations?country=&month=&basket=` — basket ingredient filtering
  - `GET /seasonal-products?country=&month=` — EUFIC in-season products
  - `GET /faostat-staples?country=` — FAOSTAT agricultural staples
  - `GET /countries` — available countries (EUFIC ∪ FAOSTAT, boolean flags)
- Streamlit UI — country/season selection, cluster filters
- MinIO object store with dbt-duckdb SQL layer (cross-validation of `yummy_score` over Silver + Gold, outside V1 prod path)
- CI/CD with GitHub Actions (Python 3.12, pytest, ruff)
- End-to-end integration audit — `tools/healthcheck.py`
- Airflow orchestration — DAG `yummy_pipeline` (Silver → Gold → upload MinIO, @daily)

> **Data storage (V1):** the API (`api/main.py`) and the Streamlit UI read Gold/Silver parquets from the **local filesystem** (`data/gold/`, `data/silver/`) — no `storage_options`, no boto3, no MinIO. MinIO is provisioned in `docker-compose` and used **exclusively** by the dbt cross-validation pipeline (reading Silver from `s3://yummy/silver/` and writing `dbt_yummy_recommendations.parquet` to `s3://yummy/gold/`). No application component (API, UI) reads from MinIO in V1. **Deliberate choice:** local reads guarantee a smooth, offline-capable demo. Migrating the Gold layer to S3/MinIO as the runtime store (API+UI reading via `storage_options`) is a V2 industrialisation goal, activatable by configuration with no formula changes.

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

# EN Sustainability Score

To complement the Yummy Score, a sustainability score has been developed.

While the Yummy Score primarily measures potential user satisfaction, the sustainability score aims to evaluate how well a recipe aligns with ingredient seasonality and agricultural availability.

## Data Sources

The sustainability score relies on two data sources:

- **EUFIC**: fruit and vegetable seasonality data by country and month;
- **FAOSTAT**: agricultural production statistics by country.

## Score Computation

### Step 1: Ingredient Sustainability Score

For each recognized ingredient:

```text
ingredient_score =
0.75 × seasonality_score
+
0.25 × availability_score
```

An ingredient that is both:

- in season;
- widely produced in the selected country;

will receive a higher sustainability score.

Examples:

| Product | Seasonality | Availability | Sustainability Score |
|----------|----------|----------|----------|
| French tomato in July | High | High | High |
| French tomato in January | Low | High | Medium |
| Mango in France | Low | Low | Low |

### Step 2: Recipe Sustainability Score

Once an ingredient score has been computed for each recognized ingredient, the recipe sustainability score is calculated as the average of all ingredient scores.

```text
recipe_score =
mean(ingredient_score)
```

Example:

| Ingredient | Score |
|------------|--------|
| Tomato | 100 |
| Zucchini | 90 |
| Mango | 10 |

```text
recipe_score =
(100 + 90 + 10) / 3

recipe_score = 66.7
```

This approach prevents a single highly sustainable or highly unsustainable ingredient from having an excessive impact on the final recipe score.

### Step 3: Consistency Bonus

A bonus is applied when more than two-thirds of the recognized ingredients have a positive sustainability score.

```text
if positive_ingredients_ratio >= 66.7%:
    recipe_score += 10
```

The objective is to reward recipes whose ingredients are mostly aligned with the seasonal and agricultural context of the selected country.

## Generated Metrics

The pipeline produces the following indicators:

- `seasonality_score`
- `availability_score`
- `durability_score`
- `coverage_score`

---

# EN Gold Datasets

The Gold layer produces several enriched datasets used by the API and Streamlit application.

| File | Description |
|----------|------------|
| `gold_yummy_recommendations.parquet` | Main recommendation dataset with Yummy Score |
| `gold_sentiment_scores.parquet` | Sentiment scores generated from user reviews |
| `gold_ingredient_matches.parquet` | TF-IDF ingredient matching results |
| `gold_recipe_clusters.parquet` | Recipe clusters generated by KMeans |
| `gold_cluster_profiles.parquet` | Statistical profiles of recipe clusters |
| `gold_recipe_ingredient_map.parquet` | Recipe-to-ingredient mapping |
| `gold_recipe_durability_scores/` | Sustainability scores partitioned by country (29 × 12 months), computed from EUFIC and FAOSTAT |
| `gold_recipe_ingredient_matches.parquet` | Detailed recipe-to-recognised-ingredient matches |


Main dataset exposed by the FastAPI service: `gold_yummy_recommendations.parquet`.
Partitioned durability directory used by the FastAPI service (joined dynamically at request time):

```text
data/gold/gold_recipe_durability_scores/durability_country=<X>/data.parquet
```

Durability columns exposed (dynamically joined to recommendations):

- `durability_score`
- `seasonality_score`
- `availability_score`
- `coverage_score`
- `durability_month`

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
- Sustainability scoring layer based on EUFIC and FAOSTAT
- ML enrichment (VADER, TF-IDF, KMeans)
- FastAPI service and Streamlit UI
- Docker + MinIO + DuckDB + dbt infrastructure
- CI/CD with GitHub Actions
- Airflow orchestration (DAG `yummy_pipeline`, Silver → Gold → upload MinIO, @daily)

## 🔜 Remaining

- Observability (metrics, alerting)

---

# Vision

YUMMY is not only a recipe application.The platform also explores how seasonality and agricultural production data can be leveraged to promote more sustainable food choices.

The project aims to become a sustainable food intelligence platform combining:
- data engineering,
- analytics,
- NLP,
- food supply chain insights,
- sustainability awareness.
