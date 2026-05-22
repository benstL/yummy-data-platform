"""Constantes HTTP génériques, réutilisables par tout module de collecte web."""

USER_AGENT = (
    "YummyDataPlatform/1.0 (Projet academique Master; "
    "scraping responsable; contact: TON_VRAI_EMAIL@exemple.fr)"
)

REQUEST_TIMEOUT = 20
MAX_RETRIES = 3
REQUEST_DELAY_SECONDS = 3.0
DEFAULT_RETRY_AFTER_SECONDS = 30

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}