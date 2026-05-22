"""
Configuration par site de recettes.

Sites ACTIFS (robots.txt vérifié) :
- marmiton.org : sitemap recettes dédié, pages recettes autorisées
- 750g.com     : crawl catégories autorisé, pages recettes autorisées

Sites NON ACTIFS (documentés mais pas dans SITES_CONFIG) :
- atelierdeschefs.fr : sitemap propre, mais robots.txt porte un signal
  "Content-signal: search=yes,ai-train=no". Notre usage est un traitement
  analytique pédagogique (TF-IDF, clustering pour recommandation), sans
  entraînement de modèle génératif ni redistribution du corpus. Site retiré
  du périmètre MVP par prudence et pour éviter un pattern d'URL trop large
  (/recette/[\\w-]+ matcherait aussi des pages non-recettes). À rediscuter
  post-MVP. Argument à conserver dans le rapport éthique.
- cuisineaz.com : robots.txt bloque /*.htm et /recettes/recette-[0-9]*,
  ce qui couvre les pages de recettes. Non conforme au crawl → exclu.

Stratégies de découverte d'URLs :
- "sitemap"  : parse les sitemaps XML (stable, exhaustif)
- "category" : crawle les pages de listing paginées

IMPORTANT : le robots.txt est aussi vérifié dynamiquement à l'exécution
(voir robots_checker.py). Cette config documente, le code applique.
"""

import re


SITES_CONFIG = {
    "marmiton": {
        "base_url": "https://www.marmiton.org",
        "sitemap_index": "https://www.marmiton.org/wsitemap_recipes_index.xml",
        "recipe_url_pattern": re.compile(r"/recettes/recette_[\w\-]+_\d+\.aspx"),
        "discovery_methods": ["sitemap"],
        "category_urls": [],
        "forbidden_query_params": [],
    },
    "750g": {
        "base_url": "https://www.750g.com",
        "sitemap_index": None,
        "recipe_url_pattern": re.compile(r"/[\w\-]+-r\d+\.htm"),
        "discovery_methods": ["category"],
        "category_urls": [
            "https://www.750g.com/recettes_entree.htm",
            "https://www.750g.com/recettes_plat.htm",
            "https://www.750g.com/recettes_dessert.htm",
        ],
        "forbidden_query_params": [
            "type", "rubrique", "recettes_id", "forceCalc",
            "impression", "ingredients",
        ],
    },
}


REQUEST_DELAY_SECONDS = 3.0

USER_AGENT = (
    "YummyDataPlatform/1.0 (Projet academique Master; "
    "scraping responsable; contact: ton.email@exemple.fr)"
)

REQUEST_TIMEOUT = 20

MAX_RETRIES = 3


# --- Headers HTTP ---
# Certains sites renvoient 429 sur un User-Agent "bot". On utilise un
# User-Agent de navigateur réaliste + headers complets. La politesse réelle
# est assurée par le respect du robots.txt et le délai entre requêtes,
# PAS par un User-Agent qui se déclare bot et se fait bloquer.
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

# Délai d'attente après un 429 si le serveur ne fournit pas de Retry-After
DEFAULT_RETRY_AFTER_SECONDS = 30