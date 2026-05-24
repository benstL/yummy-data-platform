"""
Étape 2 du scraping : extraction et validation des recettes.

Pour chaque URL découverte par crawl_urls.py :
1. Télécharge le HTML brut
2. Le parse prioritairement avec BeautifulSoup (JSON-LD) puis recipe-scrapers
3. Valide contre le contrat Pydantic (schemas.RecipeModel)
4. Sauvegarde en Bronze MinIO : HTML brut (gzip) + JSON validé

Reprise sur erreur : la colonne "scraped" du CSV d'URLs (local) est mise à
jour EN MÊME TEMPS que l'envoi sur MinIO pour garantir l'intégrité.

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
from bs4 import BeautifulSoup
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
    """Extrait la recette en combinant JSON-LD (prioritaire) et recipe_scrapers."""
    extracted = {
        "url": url,
        "title": None,
        "ingredients": None,
        "instructions": None,
        "total_time": None,
        "prep_time": None,
        "cook_time": None,
        "yields": None,
        "image": None,
        "host": None,
        "category": None,
        "cuisine": None,
        "nutrients": None,
        "ratings": None,
    }

    # 1. Stratégie Robuste : Le JSON-LD (Schema.org) caché dans le HTML
    soup = BeautifulSoup(html, 'html.parser')
    json_ld_scripts = soup.find_all('script', type='application/ld+json')
    
    for script in json_ld_scripts:
        if script.string:
            try:
                data = json.loads(script.string)
                items = data.get('@graph', data) if isinstance(data, dict) else data
                if not isinstance(items, list):
                    items = [items]
                    
                for item in items:
                    if item.get('@type') == 'Recipe':
                        extracted["title"] = item.get('name')
                        extracted["ingredients"] = item.get('recipeIngredient')
                        extracted["instructions"] = item.get('recipeInstructions')
                        extracted["yields"] = item.get('recipeYield')
                        extracted["category"] = item.get('recipeCategory')
            except json.JSONDecodeError:
                pass

    # 2. Stratégie de repli : utiliser la librairie pour ce qui manque
    try:
        scraper = scrape_html(html, org_url=url)
        def safe(getter):
            try:
                return getter()
            except Exception:
                return None

        extracted["title"] = extracted["title"] or safe(scraper.title)
        extracted["ingredients"] = extracted["ingredients"] or safe(scraper.ingredients)
        extracted["total_time"] = safe(scraper.total_time)
        extracted["prep_time"] = safe(scraper.prep_time)
        extracted["cook_time"] = safe(scraper.cook_time)
        extracted["image"] = safe(scraper.image)
        extracted["host"] = safe(scraper.host)
        extracted["cuisine"] = safe(scraper.cuisine)
        extracted["nutrients"] = safe(scraper.nutrients)
        extracted["ratings"] = safe(scraper.ratings)
        
        # Formatage des instructions JSON-LD
        if isinstance(extracted["instructions"], list) and len(extracted["instructions"]) > 0:
            if isinstance(extracted["instructions"][0], dict):
                 extracted["instructions"] = "\n".join([step.get("text", "") for step in extracted["instructions"]])
            else:
                 extracted["instructions"] = "\n".join(extracted["instructions"])
        else:
             extracted["instructions"] = extracted["instructions"] or safe(scraper.instructions)

    except Exception as error:
        logger.warning(f"Fallback recipe_scrapers échoué pour {url}: {error}")
    
    return extracted


def save_bronze_json_s3(s3_client, site_name: str, recipes: list[dict]) -> None:
    """Envoie le JSON compilé et validé sur MinIO."""
    # Heure exacte ajoutée pour garantir l'unicité et éviter les écrasements
    extraction_time = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    s3_key = f"recipes/json/{site_name}_recipes_{extraction_time}.json"
    
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

        # Validation Pydantic
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
            
            # --- 🕵️‍♂️ ASTUCE DE DEBUGGING SENIOR ---
            # On sauvegarde le HTML qui a causé l'erreur pour l'analyser visuellement
            debug_path = Path("debug_marmiton_antibot.html")
            debug_path.write_text(html, encoding="utf-8")
            logger.error(f"🛑 HTML suspect sauvegardé dans {debug_path.name}. Ouvre ce fichier dans ton navigateur !")
            # ---------------------------------------
            
            df_urls.loc[idx, "scraped"] = True
            continue

        # Checkpoint synchronisé : on sauvegarde l'état ET la donnée en même temps
        if success_count > 0 and success_count % 50 == 0:
            save_bronze_json_s3(s3_client, site_name, recipes)
            df_urls.to_csv(urls_file, index=False)
            recipes = [] # On vide la mémoire vive
            logger.info("Checkpoint: 50 recettes sécurisées sur MinIO.")

    # Fin de boucle : on sauvegarde ce qui reste
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