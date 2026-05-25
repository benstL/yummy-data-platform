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
- d’exploitation des données agricoles.

---

# 🇫🇷 Architecture

Le projet suit une architecture Medallion :

| Couche | Description |
|---|---|
| Bronze | Données brutes extraites |
| Silver | Données nettoyées et standardisées |
| Gold | Données analytiques enrichies |

Statut actuel :
- Pipelines Bronze opérationnels
- Pipelines Silver opérationnels
- Couche Gold en cours de développement

---

# 🇫🇷 Sources actuelles

| Source | Usage | Statut |
|---|---|---|
| Food.com | Recettes et avis utilisateurs | Silver ready |
| EUFIC | Saisonnalité fruits et légumes | Silver ready |
| FAOSTAT | Production agricole mondiale | Silver ready |

---

# 🇫🇷 Fonctionnalités actuelles

- Extraction de données
- Pipelines de transformation Bronze/Silver
- Nettoyage NLP
- Export Parquet
- Export d’échantillons CSV
- Architecture modulaire

---

# 🇫🇷 Métriques Gold prévues (V1)

La V1 du projet prévoit l’implémentation d’une première couche analytique Gold avec des métriques métier.

Exemples de métriques :
- score de popularité recette,
- score de satisfaction utilisateur,
- nombre d’ingrédients,
- temps de préparation total,
- score de complexité,
- score de saisonnalité,
- indicateurs de disponibilité agricole.

---

# 🇫🇷 Stack technique

## Data Engineering
- Python
- Pandas
- Parquet

## Infrastructure
- Docker
- GitHub Actions

## Roadmap technique
- Airflow
- DuckDB
- dbt
- FastAPI
- Streamlit
- NLP / ML

---

# 🇫🇷 Structure du projet

```txt
extract/     -> pipelines d’extraction
transform/   -> transformations Bronze/Silver/Gold
data/        -> couches Medallion
tools/       -> scripts utilitaires
api/         -> services API
app/         -> application frontend
ml/          -> workflows machine learning
nlp/         -> pipelines NLP
```

---

# 🇫🇷 Roadmap

## V1
- Pipelines Bronze/Silver
- Intégration Food.com
- Intégration EUFIC
- Intégration FAOSTAT
- Première couche Gold analytique
- Métriques recettes et saisonnalité

## V2
- Recommandation intelligente
- API FastAPI
- Dashboard Streamlit
- Analyse avancée de durabilité alimentaire
- NLP avancé et moteurs de recommandation

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

| Layer | Description |
|---|---|
| Bronze | Raw extracted datasets |
| Silver | Cleaned and standardized datasets |
| Gold | Enriched analytical datasets |

Current status:
- Bronze pipelines implemented
- Silver pipelines implemented
- Gold layer in progress

---

# EN Current Data Sources

| Source | Purpose | Status |
|---|---|---|
| Food.com | Recipes & user reviews | Silver ready |
| EUFIC | Fruit & vegetable seasonality | Silver ready |
| FAOSTAT | Global agricultural production | Silver ready |

---

# EN Current Features

- Data extraction pipelines
- Bronze/Silver transformation pipelines
- NLP preprocessing
- Parquet exports
- CSV sample exports
- Modular architecture

---

# EN Planned Gold Metrics (V1)

Version 1 includes a first analytical Gold layer with business-oriented metrics.

Examples:
- recipe popularity score,
- user satisfaction score,
- ingredient count,
- total preparation time,
- complexity score,
- seasonality score,
- agricultural availability indicators.

---

# EN Tech Stack

## Data Engineering
- Python
- Pandas
- Parquet

## Infrastructure
- Docker
- GitHub Actions

## Technical Roadmap
- Airflow
- DuckDB
- dbt
- FastAPI
- Streamlit
- NLP / ML

---

# EN Project Structure

```txt
extract/     -> extraction pipelines
transform/   -> Bronze/Silver/Gold transformations
data/        -> Medallion layers
tools/       -> utility scripts
api/         -> API services
app/         -> frontend application
ml/          -> machine learning workflows
nlp/         -> NLP pipelines
```

---

# EN Roadmap

## V1
- Bronze/Silver pipelines
- Food.com integration
- EUFIC integration
- FAOSTAT integration
- First analytical Gold layer
- Recipe and seasonality metrics

## V2
- Smart recommendation engine
- FastAPI services
- Streamlit dashboards
- Advanced sustainability analytics
- Advanced NLP and recommendation systems

---

# Vision

YUMMY is not only a recipe application.

The project aims to become a sustainable food intelligence platform combining:
- data engineering,
- analytics,
- NLP,
- food supply chain insights,
- sustainability awareness.
