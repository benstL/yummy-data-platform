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
- Couche Gold en cours de conception

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
- Pipelines de transformation Silver
- Nettoyage NLP
- Export Parquet
- Export d’échantillons CSV
- Architecture modulaire

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
````
