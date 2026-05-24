# Yummy Data Platform — Couche d'extraction (Bronze)

Pipeline d'ingestion de données pour le calcul du **Yummy Score** (recommandation de
recettes durables). Cette documentation couvre la **couche d'extraction** : collecte
des sources brutes et chargement dans la couche **Bronze** du pattern Medallion,
stockée dans **MinIO** (stockage objet compatible S3).

> **État du projet** : la couche d'extraction est fonctionnelle et testée de bout en
> bout. Les couches Silver (transformation) et Gold (Yummy Score) sont en cours.

---

## 1. Sources de données

| Source | Contenu | Pilier Yummy Score | Méthode |
|---|---|---|---|
| **CIQUAL** (ANSES) | Composition nutritionnelle | Nutrition | Téléchargement `.xls` |
| **FAOSTAT QCL** (FAO) | Production agricole mondiale | Empreinte carbone (proxy) | Téléchargement bulk ZIP |
| **EUFIC** | Saisonnalité fruits/légumes par pays | Saisonnalité | Scraping Selenium (manuel) |
| **Kaggle Food.com** | Recettes + interactions utilisateurs | Satisfaction | API Kaggle |
| **Marmiton / 750g** | Recettes web françaises | Satisfaction (avis) | Scraping `requests` + `recipe-scrapers` |

---

## 2. Prérequis

- **Windows 10/11 + WSL 2** (Ubuntu) — toutes les commandes se lancent depuis le terminal WSL
- **Docker Desktop** (avec intégration WSL 2 activée) — héberge MinIO
- **Python 3.11+** (testé sur 3.12)
- **Git**

Vérifier que tout est présent :

```bash
python --version      # >= 3.11
docker --version
git --version
```

---

## 3. Installation

### 3.1 Cloner le dépôt

```bash
git clone <URL_DU_DEPOT> yummy-data-platform
cd yummy-data-platform
```

### 3.2 Créer et activer l'environnement virtuel

```bash
python -m venv .venv
source .venv/bin/activate
```

> Le prompt doit maintenant afficher `(.venv)`. À refaire à chaque nouvelle session terminal.

### 3.3 Installer le projet en mode éditable

Le projet est un **package Python installable** : cela permet d'utiliser des imports
absolus (`from common.minio_client import ...`) qui fonctionnent depuis n'importe quel
répertoire, en CLI comme sous un orchestrateur.

```bash
pip install -e .
```

Pour les extracts qui nécessitent des dépendances lourdes (isolées en options) :

```bash
pip install -e ".[eufic]"     # ajoute Selenium (scraping EUFIC uniquement)
pip install -e ".[kaggle]"    # ajoute le client Kaggle
pip install -e ".[eufic,kaggle]"   # les deux
```

Vérifier l'installation :

```bash
pip show yummy-data-platform   # "Editable project location" doit pointer la racine
```

---

## 4. Configuration

### 4.1 Fichier `.env`

Les secrets et la configuration MinIO sont dans un fichier `.env` à la racine,
**jamais commité** (présent dans `.gitignore`).

Créer le fichier à partir du modèle ci-dessous (`.env.example` fourni dans le dépôt) :

```bash
cp .env.example .env
```

Contenu attendu (`.env`) :

```
# Identifiants MinIO (root du conteneur ET credentials boto3 — doivent être identiques)
AWS_ACCESS_KEY_ID=ton_identifiant
AWS_SECRET_ACCESS_KEY=ton_mot_de_passe

# Endpoint MinIO : localhost en dev local, http://minio:9000 si lancé dans un réseau Docker
MINIO_ENDPOINT=http://localhost:9000

# Jeton API Kaggle (nécessaire uniquement pour l'extract Kaggle)
KAGGLE_API_TOKEN=ton_jeton_kaggle
```

> **Important** : `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` servent à la fois de
> credentials root MinIO (lus par `docker-compose.yml`) et de credentials boto3 (lus
> par le code). Une seule source de vérité.

> **Sécurité** : si ces identifiants sont compromis, change-les dans `.env`, puis
> recrée le conteneur (`docker compose down && docker compose up -d minio`).

### 4.2 Jeton Kaggle (si extract Kaggle utilisé)

L'API Kaggle lit le jeton depuis `~/.kaggle/kaggle.json` ou la variable
`KAGGLE_API_TOKEN`. Récupère ton jeton sur ton compte Kaggle (Settings → API →
Create New Token) et place-le dans le `.env`.

---

## 5. Lancer MinIO

MinIO est défini dans `docker-compose.yml` avec un **volume persistant** (les données
survivent aux redémarrages) et des credentials lus depuis le `.env`.

```bash
docker compose up -d minio
```

Vérifier que MinIO est joignable et que les credentials sont corrects :

```bash
python -c "from common.minio_client import get_s3_client, ensure_bucket_exists; c=get_s3_client(); ensure_bucket_exists(c); print('MinIO OK')"
```

- Affiche `MinIO OK` → tout fonctionne.
- Affiche `RuntimeError: AWS_ACCESS_KEY_ID ... manquants` → le `.env` n'est pas lu
  (mauvais répertoire, ou variables mal nommées).

**Console web MinIO** : ouvrir <http://localhost:9001> dans un navigateur, se
connecter avec les identifiants du `.env` pour visualiser les fichiers du bucket
`bronze`.

---

## 6. Architecture des données : pattern Bronze

### 6.1 Deux modes d'écriture

Le projet suit **un pattern unique** avec une exception justifiée :

- **Pattern par défaut (« local puis sync »)** : chaque extract écrit ses données
  brutes en local sous `data/bronze/`, puis le script `sync_to_minio.py` les monte
  vers MinIO. Avantage : le local sert de filet de sécurité, et l'upload est rejouable
  en cas de coupure réseau pendant une collecte longue.

- **Exception (scraping en flux)** : `extract_recipes.py` écrit directement dans MinIO
  au fil de l'eau (streaming), car il traite potentiellement des milliers de pages avec
  reprise sur erreur. Le CSV de suivi reste local.

### 6.2 Convention de clés MinIO

La synchronisation reproduit l'arborescence locale comme clé S3 :

```
data/bronze/ciqual/Table_Ciqual_2025.xls   ->   s3://bronze/ciqual/Table_Ciqual_2025.xls
data/bronze/recipes/json/marmiton.json     ->   s3://bronze/recipes/json/marmiton.json
```

### 6.3 Idempotence

`sync_to_minio.py` compare la taille de chaque fichier local avec sa version distante
et ne réuploade que ce qui a changé. Relancer la synchronisation plusieurs fois ne crée
**aucun doublon**.

---

## 7. Lancer les extractions

Toutes les commandes se lancent **depuis la racine du projet**, avec le venv activé,
en notation module (`python -m`).

### 7.1 CIQUAL (nutrition)

```bash
python -m extract.ciqual.ingest_ciqual
python -m extract.sync_to_minio
```

### 7.2 FAOSTAT (production agricole)

```bash
python -m extract.faostat.extract_faostat_qcl
python -m extract.sync_to_minio
```

> Fichier volumineux (plusieurs centaines de Mo décompressés). Le ZIP source est
> supprimé après extraction pour économiser l'espace disque.

### 7.3 Kaggle (recettes + interactions)

```bash
# Nécessite : pip install -e ".[kaggle]" + KAGGLE_API_TOKEN dans .env
python -m extract.kaggle.ingest_kaggle_food_dot_com
python -m extract.sync_to_minio
```

### 7.4 EUFIC (saisonnalité) — extract manuel

```bash
# Nécessite : pip install -e ".[eufic]" + Chrome installé dans WSL
python -m extract.eufic.extract_eufic
python -m extract.sync_to_minio
```

> ⚠️ **Extract manuel uniquement**. Dépend de Selenium + Chrome, ne tourne pas en CI ni
> dans un DAG planifié. La saisonnalité évolue peu : le CSV produit est figé comme
> donnée de référence et n'est re-scrapé qu'occasionnellement.

### 7.5 Recettes web (Marmiton, 750g) — scraping en 2 étapes

```bash
# Étape 1 : découvrir les URLs de recettes (écrit un CSV local)
python -m extract.recipes_scraper.crawl_urls --site marmiton --limit 2000
python -m extract.recipes_scraper.crawl_urls --site 750g --limit 2000

# Étape 2 : scraper et valider les recettes (écrit direct dans MinIO)
python -m extract.recipes_scraper.extract_recipes --site marmiton --max 2000
python -m extract.recipes_scraper.extract_recipes --site 750g --max 2000
```

> Le scraping respecte le `robots.txt` de chaque site (vérifié dynamiquement) et un
> délai de 3 s entre requêtes. Chaque recette est validée contre un contrat Pydantic
> (`schemas.py`) avant d'être stockée : une recette sans titre ou sans ingrédient est
> rejetée. La reprise sur erreur est gérée via la colonne `scraped` du CSV d'URLs :
> relancer le script ne re-scrape pas ce qui est déjà fait.

---

## 8. Tester que tout fonctionne

Procéder par niveaux croissants. Ne passer au niveau suivant que si le précédent passe.

### Niveau 1 — Tous les modules s'importent

```bash
python -c "import common.minio_client, common.http.http_client, common.http.robots_checker, common.http.config; print('common OK')"
python -c "import extract.recipes_scraper.extract_recipes, extract.recipes_scraper.crawl_urls; print('scraper OK')"
```

Les deux doivent afficher `OK`.

### Niveau 2 — Connexion MinIO

```bash
docker compose up -d minio
python -c "from common.minio_client import get_s3_client, ensure_bucket_exists; c=get_s3_client(); ensure_bucket_exists(c); print('MinIO OK')"
```

### Niveau 3 — Cycle complet (exemple CIQUAL)

```bash
python -m extract.ciqual.ingest_ciqual          # ingestion locale
ls -lh data/bronze/ciqual/                       # le fichier doit être présent
python -m extract.sync_to_minio                  # 1er sync : monte les fichiers
python -m extract.sync_to_minio                  # 2e sync : doit dire "0 monté, N déjà à jour"
```

Le **2e sync affichant `0 fichier(s) montés`** prouve l'idempotence du pipeline.

---

## 9. Structure du projet

```
yummy-data-platform/
├── common/                      # code partagé (imports absolus)
│   ├── minio_client.py          # connexion MinIO centralisée
│   └── http/                    # utilitaires HTTP génériques
│       ├── config.py            # headers, timeouts, délais
│       ├── http_client.py       # session + gestion 429/backoff
│       └── robots_checker.py    # respect dynamique du robots.txt
├── extract/
│   ├── ciqual/                  # nutrition (ANSES)
│   ├── faostat/                 # production agricole (FAO)
│   ├── eufic/                   # saisonnalité (manuel, Selenium)
│   ├── kaggle/                  # recettes + interactions
│   ├── recipes_scraper/         # scraping Marmiton / 750g
│   │   ├── crawl_urls.py        # étape 1 : découverte d'URLs
│   │   ├── extract_recipes.py   # étape 2 : scraping + validation
│   │   ├── sites_config.py      # config spécifique des sites
│   │   └── schemas.py           # contrat de données Pydantic
│   └── sync_to_minio.py         # synchronisation local -> MinIO (idempotente)
├── transform/                   # couche Silver (en cours)
├── data/bronze/                 # données brutes locales (gitignored)
├── docker-compose.yml           # MinIO (volume persistant, secrets via .env)
├── pyproject.toml               # dépendances + config du package
└── .env                         # secrets (jamais commité)
```

---

## 10. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `ModuleNotFoundError: No module named 'common'` | Package non installé | `pip install -e .` |
| `RuntimeError: AWS_ACCESS_KEY_ID ... manquants` | `.env` non lu | Lancer depuis la racine ; vérifier les noms de variables |
| MinIO injoignable | Conteneur non démarré | `docker compose up -d minio` |
| Scraping bloqué (429) | Trop de requêtes | Le client attend automatiquement (Retry-After + backoff) |
| `kaggle: command not found` ou auth échouée | Extra non installé / jeton absent | `pip install -e ".[kaggle]"` + `KAGGLE_API_TOKEN` |

---

## 11. Dette technique connue

Points non bloquants pour le MVP, à traiter en montée de version :

- **Lecture CIQUAL en Silver** : le fichier est un vrai `.xls` binaire legacy. La lecture
  devra être explicite : `pd.read_excel(path, engine="xlrd")` (xlrd est déjà installé).
- **Imports du scraper** : `crawl_urls.py` et `extract_recipes.py` utilisent des imports
  absolus (`common.http.*`, `extract.recipes_scraper.*`) — fonctionnels partout.
- **Pas de tests automatisés** : un test minimal d'importabilité (`tests/test_imports.py`)
  et une CI GitHub Actions qui le lance protégeraient contre les imports cassés.
- **Secrets en `.env`** : suffisant en local. En production réelle, utiliser des
  variables d'environnement injectées par l'orchestrateur ou un coffre-fort.
- **Site `atelierdeschefs.fr`** : configuré dans une version antérieure puis retiré du
  périmètre (signal `ai-train=no` dans son robots.txt). Argument conservé dans le rapport
  éthique.