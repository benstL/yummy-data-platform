# Yummy Data Platform

Plateforme data-driven orientée supply chain alimentaire.

## Stack technique

- Airflow
- MinIO
- DuckDB
- dbt
- FastAPI
- Streamlit
- NLP / ML
- Docker
- GitHub Actions

## Architecture

Architecture Medallion :
- Bronze
- Silver
- Gold

## Sources

- EUFIC — saisonnalité des fruits et légumes
- FAOSTAT — production agricole mondiale
- Food.com — recettes et avis utilisateurs
- Marmiton — enrichissement recettes francophones (V1 limitée)
- AGRIBALYSE — impact environnemental (axe V2)

## Objectif

Recommander des recettes de saison selon :
- pays
- mois
- disponibilité agricole
- satisfaction utilisateur