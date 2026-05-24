"""
Configuration par site de recettes (scraping Marmiton / 750g).

⚠️ Cette config NE contient QUE les réglages spécifiques aux sites (URLs,
patterns, méthodes de découverte). Les constantes HTTP génériques (User-Agent,
headers, délais, timeouts) vivent dans common.http.config — source de vérité
unique. Ne PAS les redéclarer ici (duplication = bug de configuration futur).

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
  ce qui couvre les pages de recettes. Non conforme au crawl -> exclu.

Stratégies de découverte d'URLs :
- "sitemap"  : parse les sitemaps XML (stable, exhaustif)
- "category" : crawle les pages de listing paginées

IMPORTANT : le robots.txt est aussi vérifié dynamiquement à l'exécution
(voir common.http.robots_checker). Cette config documente, le code applique.
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
