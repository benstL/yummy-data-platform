"""
Vérification automatique du robots.txt (via Protego).

Lit le robots.txt en direct et vérifie chaque URL avant tout téléchargement.
Protego (parser de Scrapy) gère les wildcards '*' que urllib.robotparser
traite mal. Le respect n'est pas déclaratif : il est appliqué par le code à
chaque requête via can_fetch().
"""
from urllib.parse import urlparse

import requests
from protego import Protego

from common.http.config import USER_AGENT, REQUEST_TIMEOUT, BROWSER_HEADERS


_robots_cache: dict[str, Protego | None] = {}


def get_robots_parser(url: str) -> Protego | None:
    """Récupère (et met en cache) le parser robots.txt pour le domaine."""
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"

    if domain in _robots_cache:
        return _robots_cache[domain]

    robots_url = f"{domain}/robots.txt"

    try:
        response = requests.get(robots_url, headers=BROWSER_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        parser = Protego.parse(response.text)
        print(f"[INFO] robots.txt loaded for {domain}")
    except Exception as error:
        print(f"[WARNING] Could not read robots.txt for {domain}: {error}")
        parser = None  # None => on bloquera par précaution

    _robots_cache[domain] = parser
    return parser


def is_allowed(url: str, user_agent: str = USER_AGENT) -> bool:
    """Retourne True si le robots.txt autorise le téléchargement de cette URL."""
    parser = get_robots_parser(url)
    if parser is None:
        return False  # précaution : pas de robots.txt lisible => on ne scrape pas
    try:
        return parser.can_fetch(url, user_agent)
    except Exception:
        return False


def get_crawl_delay(url: str, user_agent: str = USER_AGENT) -> float | None:
    """Retourne le Crawl-delay déclaré par le site, ou None si absent."""
    parser = get_robots_parser(url)
    if parser is None:
        return None
    try:
        delay = parser.crawl_delay(user_agent)
        return float(delay) if delay is not None else None
    except Exception:
        return None


def filter_allowed_urls(urls: list[str]) -> list[str]:
    """Filtre une liste d'URLs pour ne garder que celles autorisées."""
    allowed = []
    blocked = 0
    for url in urls:
        if is_allowed(url):
            allowed.append(url)
        else:
            blocked += 1
    if blocked:
        print(f"[INFO] robots.txt filter: {blocked} blocked, {len(allowed)} allowed")
    return allowed