"""
Étape 2 du scraping : extraction et validation des recettes.

Pour chaque URL découverte par crawl_urls.py :
1. Télécharge le HTML brut
2. Le parse avec recipe-scrapers
3. Valide contre le contrat Pydantic (schemas.RecipeModel)
4. Sauvegarde en Bronze MinIO : HTML brut (gzip) + JSON validé

Reprise sur erreur : la colonne "scraped" du CSV d'URLs (local) est mise à
jour, donc on peut relancer sans re-scraper ce qui est déjà fait.

Usage :
    python -m extract.recipes_scraper.extract_recipes --site marmiton
    python -m extract.recipes_scraper.extract_recipes --site all --max 5000
"""
import argparse
import gzip
import json
import time
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, UTC
from pathlib import Path

import pandas as pd
from recipe_scrapers import scrape_html
from pydantic import ValidationError

from common.minio_client import (
    get_s3_client,
    ensure_bucket_exists,
    BRONZE_BUCKET,
)
from common.http.config import REQUEST_DELAY_SECONDS
from extract.recipes_scraper.sites_config import SITES_CONFIG
from common.http.robots_checker import is_allowed, get_crawl_delay
from common.http.http_client import make_session, fetch_text as fetch_html
from extract.recipes_scraper.schemas import RecipeModel


# --- Logging ---
LOG_DIR = Path("data/bronze/recipes/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("Scraper")
logger.setLevel(logging.INFO)
_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
_fh = RotatingFileHandler(
    LOG_DIR / "scraping.log", maxBytes=5 * 1024 * 1024, backupCount=2, encoding="utf-8"
)
_fh.setFormatter(_formatter)
_sh = logging.StreamHandler()
_sh.setFormatter(_formatter)
if not logger.handlers:
    logger.addHandler(_fh)
    logger.addHandler(_sh)

# Le CSV d'état reste local : c'est notre suivi de reprise sur erreur
URLS_DIR = Path("data/bronze/recipes/urls")
URLS_DIR.mkdir(parents=True, exist_ok=True)


def get_latest_urls_file(site_name: str) -> Path:
    files = sorted(URLS_DIR.glob(f"{site_name}_urls_*.csv"))
    if not files:
        raise FileNotFoundError(f"No URL file found for {site_name}. Run crawl_urls first.")
    return files[-1]


def extract_recipe_id(url: str) -> str:
    safe = url.rstrip("/").split("/")[-1]
    safe = safe.replace(".aspx", "").replace(".htm", "")
    return safe[:120]


def save_bronze_html_s3(s3_client, site_name: str, recipe_id: str, html: str) -> None:
    """Compresse le HTML en mémoire et l'envoie sur MinIO."""
    s3_key = f"recipes/html/{site_name}/{recipe_id}.html.gz"
    compressed = gzip.compress(html.encode("utf-8"))
    s3_client.put_object(Bucket=BRONZE_BUCKET, Key=s3_key, Body=compressed)


def parse_with_recipe_scrapers(html: str, url: str) -> dict | None:
    try:
        scraper = scrape_html(html, org_url=url)

        def safe(getter):
            try:
                return getter()
            except Exception:
                return None

        return {
            "url": url,
            "title": safe(scraper.title),
            "total_time": safe(scraper.total_time),
            "prep_time": safe(scraper.prep_time),
            "cook_time": safe(scraper.cook_time),
            "yields": safe(scraper.yields),
            "ingredients": safe(scraper.ingredients),
            "instructions": safe(scraper.instructions),
            "image": safe(scraper.image),
            "host": safe(scraper.host),
            "category": safe(scraper.category),
            "cuisine": safe(scraper.cuisine),
            "nutrients": safe(scraper.nutrients),
            "ratings": safe(scraper.ratings),
        }
    except Exception as error:
        logger.warning(f"Parsing échoué pour {url}: {error}")
        return None


def save_bronze_json_s3(s3_client, site_name: str, recipes: list[dict]) -> None:
    """Envoie le JSON compilé et validé sur MinIO."""
    extraction_date = datetime.now(UTC).strftime("%Y%m%d")
    s3_key = f"recipes/json/{site_name}_recipes_{extraction_date}.json"
    payload = {
        "site": site_name,
        "extracted_at": datetime.now(UTC).isoformat(),
        "count": len(recipes),
        "recipes": recipes,
    }
    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    s3_client.put_object(Bucket=BRONZE_BUCKET, Key=s3_key, Body=json_bytes)
    logger.info(f"{len(recipes)} recettes envoyées sur s3://{BRONZE_BUCKET}/{s3_key}")


def scrape_site(s3_client, site_name: str, max_recipes: int) -> None:
    urls_file = get_latest_urls_file(site_name)
    logger.info(f"Lecture des URLs depuis: {urls_file}")

    df_urls = pd.read_csv(urls_file)
    pending = df_urls[~df_urls["scraped"]].head(max_recipes)
    logger.info(f"{len(pending)} URLs en attente (limite {max_recipes})")

    session = make_session()
    recipes = []
    success_count = 0
    effective_delay = max(
        REQUEST_DELAY_SECONDS,
        get_crawl_delay(SITES_CONFIG[site_name]["base_url"]) or 0,
    )

    for idx, row in pending.iterrows():
        url = row["url"]
        recipe_id = extract_recipe_id(url)

        if not is_allowed(url):
            logger.warning(f"Rejeté par robots.txt : {url}")
            df_urls.loc[idx, "scraped"] = True
            continue

        logger.info(f"[{success_count + 1}] Scraping: {url}")
        time.sleep(effective_delay)

        html = fetch_html(session, url)
        if html is None:
            continue

        save_bronze_html_s3(s3_client, site_name, recipe_id, html)

        raw_recipe = parse_with_recipe_scrapers(html, url)
        if raw_recipe is None:
            continue

        raw_recipe["recipe_id"] = recipe_id
        raw_recipe["site"] = site_name

        # Validation Pydantic : le contrat de données Bronze
        try:
            validated = RecipeModel(**raw_recipe)
            recipes.append(validated.model_dump(mode="json"))
            df_urls.loc[idx, "scraped"] = True
            success_count += 1
        except ValidationError as e:
            erreurs = ", ".join(
                f"Champ '{err['loc'][0]}' -> {err['msg']}" for err in e.errors()
            )
            logger.error(f"Rejet Pydantic pour {url} : {erreurs}")
            df_urls.loc[idx, "scraped"] = True  # ne pas rebloquer la file
            continue

        # Checkpoint local tous les 50 succès
        if success_count > 0 and success_count % 50 == 0:
            df_urls.to_csv(urls_file, index=False)
            logger.info("Checkpoint local (CSV mis à jour)")

    df_urls.to_csv(urls_file, index=False)
    if recipes:
        save_bronze_json_s3(s3_client, site_name, recipes)

    logger.info(f"Bilan {site_name}: {success_count} recettes validées et envoyées sur S3")


def main():
    parser = argparse.ArgumentParser(description="Extraction et validation de recettes")
    parser.add_argument("--site", choices=list(SITES_CONFIG.keys()) + ["all"], required=True)
    parser.add_argument("--max", type=int, default=2000)
    args = parser.parse_args()

    sites = list(SITES_CONFIG.keys()) if args.site == "all" else [args.site]

    # Connexion MinIO créée une fois, via common, et passée aux fonctions
    s3_client = get_s3_client()
    ensure_bucket_exists(s3_client)

    for site_name in sites:
        logger.info(f"========== DÉBUT EXTRACTION : {site_name.upper()} ==========")
        try:
            scrape_site(s3_client, site_name, args.max)
        except FileNotFoundError as error:
            logger.error(str(error))


if __name__ == "__main__":
    main()