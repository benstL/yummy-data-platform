"""
Test minimal d'importabilité — protège contre les imports cassés.

Ne teste PAS la logique métier : vérifie juste que tous les modules du projet
s'importent sans erreur (chemin d'import, dépendances présentes, pas de typo).
C'est le filet de sécurité le moins cher pour une équipe de 4 sans rôles fixes :
si quelqu'un casse un import, la CI le voit immédiatement.

Lancement :
    pytest tests/test_imports.py
ou, sans pytest :
    python -m tests.test_imports
"""
import importlib

# Modules qui doivent toujours s'importer (dépendances de base installées par `pip install -e .`)
CORE_MODULES = [
    "common.minio_client",
    "common.http.config",
    "common.http.http_client",
    "common.http.robots_checker",
    "extract.base_extractor",
    "extract.sync_to_minio",
    "extract.ciqual.ingest_ciqual",
    "extract.faostat.extract_faostat_qcl",
    "extract.agribalyse.ingest_agribalyse",
    "extract.recipes_scraper.sites_config",
    "extract.recipes_scraper.schemas",
    "extract.recipes_scraper.crawl_urls",
    "extract.recipes_scraper.extract_recipes",
]

# Modules à dépendances optionnelles (extras) : importés seulement si dispo.
# On ne fait PAS échouer la CI si l'extra n'est pas installé.
OPTIONAL_MODULES = [
    "extract.kaggle.ingest_kaggle_food_dot_com",  # extra [kaggle]
    "extract.eufic.extract_eufic",                # extra [eufic] (selenium)
]


def test_core_modules_importable():
    """Tous les modules de base doivent s'importer sans erreur."""
    for name in CORE_MODULES:
        importlib.import_module(name)


def test_optional_modules_importable_if_deps_present():
    """Les modules optionnels s'importent si leur extra est installé, sinon on skip."""
    for name in OPTIONAL_MODULES:
        try:
            importlib.import_module(name)
        except ImportError as e:
            print(f"[SKIP] {name} : extra non installé ({e})")


def test_bronze_extractor_contract():
    """BronzeExtractor doit exposer fetch/normalize/validate/run."""
    from extract.base_extractor import BronzeExtractor

    for method in ("fetch", "normalize", "validate", "run"):
        assert hasattr(BronzeExtractor, method), f"BronzeExtractor.{method} manquant"


if __name__ == "__main__":
    test_core_modules_importable()
    test_optional_modules_importable_if_deps_present()
    test_bronze_extractor_contract()
    print("OK — tous les imports de base passent.")
