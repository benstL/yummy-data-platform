"""
Étape 1 du scraping : découverte des URLs de recettes.

Deux stratégies selon le site (définies dans sites_config.py) :
- sitemap : parse les sitemaps XML (stable, rapide, pensé pour les bots)
- category : crawle les pages de listing et extrait les liens de recettes

Sortie : un fichier CSV par site dans data/bronze/recipes/urls/
contenant les URLs uniques à scraper ensuite.
L'upload vers MinIO est délégué à sync_to_minio.py (pattern unique du projet).

Usage :
    python -m extract.recipes_scraper.crawl_urls --site marmiton --limit 2000
    python -m extract.recipes_scraper.crawl_urls --site all --limit 5000
"""
import argparse
import time
import xml.etree.ElementTree as ET
from datetime import datetime, UTC
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from common.http.config import REQUEST_DELAY_SECONDS
from extract.recipes_scraper.sites_config import SITES_CONFIG
from common.http.robots_checker import filter_allowed_urls
from common.http.http_client import make_session, fetch_text


URLS_DIR = Path("data/bronze/recipes/urls")


def parse_sitemap(xml_text: str) -> list[str]:
    """Extrait toutes les <loc> d'un sitemap ou sitemap index XML."""
    urls = []

    try:
        root = ET.fromstring(xml_text)
        # Les sitemaps utilisent un namespace ; on le retire pour simplifier
        for loc in root.iter():
            if loc.tag.endswith("loc") and loc.text:
                urls.append(loc.text.strip())

    except ET.ParseError as error:
        print(f"[WARNING] Sitemap parse error: {error}")

    return urls


def discover_via_sitemap(
    session: requests.Session,
    site_config: dict,
    limit: int,
) -> list[str]:
    """Découvre les URLs de recettes en parcourant les sitemaps XML."""
    recipe_pattern = site_config["recipe_url_pattern"]
    sitemap_index_url = site_config["sitemap_index"]

    print(f"[INFO] Reading sitemap index: {sitemap_index_url}")

    index_xml = fetch_text(session, sitemap_index_url)
    if index_xml is None:
        return []

    all_locs = parse_sitemap(index_xml)

    # Un sitemap index pointe vers d'autres sitemaps ; un sitemap simple
    # pointe directement vers des pages. On gère les deux cas.
    sub_sitemaps = [u for u in all_locs if ".xml" in u]
    direct_urls = [u for u in all_locs if recipe_pattern.search(u)]

    recipe_urls = list(direct_urls)

    for sub_sitemap in sub_sitemaps:
        if len(recipe_urls) >= limit:
            break

        print(f"[INFO] Reading sub-sitemap: {sub_sitemap}")
        time.sleep(REQUEST_DELAY_SECONDS)

        sub_xml = fetch_text(session, sub_sitemap)
        if sub_xml is None:
            continue

        sub_locs = parse_sitemap(sub_xml)
        matched = [u for u in sub_locs if recipe_pattern.search(u)]
        recipe_urls.extend(matched)

        print(f"[INFO]   -> {len(matched)} recipe URLs found")

    return recipe_urls[:limit]


def discover_via_category(
    session: requests.Session,
    site_config: dict,
    limit: int,
    max_pages_per_category: int = 50,
) -> list[str]:
    """Découvre les URLs en crawlant les pages de listing paginées."""
    recipe_pattern = site_config["recipe_url_pattern"]
    base_url = site_config["base_url"]
    recipe_urls = set()

    for category_url in site_config.get("category_urls", []):
        for page in range(1, max_pages_per_category + 1):
            if len(recipe_urls) >= limit:
                break

            # Pagination générique : on tente ?page=N
            page_url = f"{category_url}?page={page}"

            print(f"[INFO] Crawling: {page_url}")
            time.sleep(REQUEST_DELAY_SECONDS)

            html = fetch_text(session, page_url)
            if html is None:
                break

            soup = BeautifulSoup(html, "html.parser")
            links = soup.find_all("a", href=True)

            page_urls = set()
            for link in links:
                href = link["href"]
                if recipe_pattern.search(href):
                    # Reconstruit l'URL absolue si nécessaire
                    full_url = href if href.startswith("http") else base_url + href
                    page_urls.add(full_url)

            # Si une page ne ramène aucune nouvelle URL, on arrête la pagination
            new_urls = page_urls - recipe_urls
            if not new_urls:
                print(f"[INFO]   -> no new URLs, stopping pagination")
                break

            recipe_urls.update(new_urls)
            print(f"[INFO]   -> {len(new_urls)} new URLs (total {len(recipe_urls)})")

    return list(recipe_urls)[:limit]


def discover_site_urls(site_name: str, limit: int) -> list[str]:
    """Orchestre la découverte d'URLs pour un site selon ses méthodes."""
    site_config = SITES_CONFIG[site_name]
    session = make_session()
    all_urls = set()

    for method in site_config["discovery_methods"]:
        if len(all_urls) >= limit:
            break

        remaining = limit - len(all_urls)
        print(f"\n[INFO] === {site_name} : discovery method '{method}' ===")

        if method == "sitemap":
            found = discover_via_sitemap(session, site_config, remaining)
        elif method == "category":
            found = discover_via_category(session, site_config, remaining)
        else:
            print(f"[WARNING] Unknown discovery method: {method}")
            found = []

        all_urls.update(found)
        print(f"[INFO] Method '{method}' total: {len(found)} URLs")

    # Filtrage robots.txt : on ne garde que les URLs explicitement autorisées
    allowed = filter_allowed_urls(list(all_urls))

    return allowed[:limit]


def save_urls(site_name: str, urls: list[str]) -> Path:
    """Sauvegarde les URLs découvertes en CSV local (couche Bronze).

    L'upload vers MinIO est délégué à sync_to_minio.py (pattern unique).
    """
    URLS_DIR.mkdir(parents=True, exist_ok=True)

    extraction_date = datetime.now(UTC).strftime("%Y%m%d")
    output_file = URLS_DIR / f"{site_name}_urls_{extraction_date}.csv"

    df = pd.DataFrame({
        "url": urls,
        "site": site_name,
        "discovered_at": datetime.now(UTC).isoformat(),
        "scraped": False,
    })
    df.to_csv(output_file, index=False)

    print(f"[INFO] Saved {len(urls)} URLs to {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Découverte d'URLs de recettes")
    parser.add_argument(
        "--site",
        choices=list(SITES_CONFIG.keys()) + ["all"],
        required=True,
        help="Site à crawler (ou 'all' pour tous)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=2000,
        help="Nombre max d'URLs à découvrir par site",
    )
    args = parser.parse_args()

    sites = list(SITES_CONFIG.keys()) if args.site == "all" else [args.site]

    for site_name in sites:
        print(f"\n{'=' * 60}")
        print(f"[INFO] Starting URL discovery for: {site_name}")
        print(f"{'=' * 60}")

        urls = discover_site_urls(site_name, args.limit)

        if urls:
            save_urls(site_name, urls)
        else:
            print(f"[WARNING] No URLs found for {site_name}")

    print("\n[INFO] URL discovery completed.")
    print("[INFO] Lance ensuite : python -m extract.sync_to_minio")


if __name__ == "__main__":
    main()