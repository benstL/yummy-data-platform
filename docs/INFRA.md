# INFRA — Pile technique YUMMY

> **Mis à jour : 2026-06-06**
> Documentation technique interne. Public : membres de l'équipe qui n'ont pas codé cette partie.
> Objectif : reproduire, dépanner, défendre en revue.
> **Décrit l'état réel du code — jamais l'intention.**

---

## Table des matières

1. [Prérequis](#1-prérequis)
2. [Architecture d'ensemble](#2-architecture-densemble)
3. [Les 8 services docker-compose](#3-les-8-services-docker-compose)
4. [Séquence de démarrage complète](#4-séquence-de-démarrage-complète)
5. [Audit d'intégration](#5-audit-dintégration)
6. [Source de vérité Gold — deux chemins](#6-source-de-vérité-gold--deux-chemins)
7. [Limites connues](#7-limites-connues)
8. [Dépannage](#8-dépannage)

---

## 1. Prérequis

### 1.1 Docker Desktop avec intégration WSL2

Toutes les commandes — Docker, Python, dbt — se lancent depuis un **terminal WSL** (bash Ubuntu/Debian). Jamais depuis PowerShell ni CMD.

**Installation :**

1. Télécharger Docker Desktop pour Windows (site officiel Docker).
2. Pendant l'installation, cocher *Use WSL 2 instead of Hyper-V*.
3. Après installation : Docker Desktop → **Settings** → **Resources** → **WSL Integration**.
4. Activer *Enable integration with my default WSL distro* **et** cocher explicitement la distribution utilisée (ex. `Ubuntu-22.04`). Avoir « default distro » activé ne suffit pas si une distribution secondaire est en jeu.
5. Cliquer *Apply & Restart*.

**Piège fréquent — `docker: command not found` dans WSL :**
Docker Desktop injecte les binaires `docker` et `docker compose` dans le PATH WSL uniquement si (a) Docker Desktop **tourne** (icône barre des tâches), (b) la distribution est **explicitement cochée** dans WSL Integration, (c) Docker Desktop a été **redémarré après** le cochage. Si `which docker` ne retourne rien, relancer Docker Desktop depuis Windows puis rouvrir le terminal WSL.

**Vérification :**

```bash
docker version           # affiche Client et Server
docker compose version   # affiche Docker Compose version 2.x
```

### 1.2 Python 3.12 + venv

Le projet utilise Python **3.12** sur les trois surfaces : `.python-version`, `Dockerfile` (`FROM python:3.12-slim`), et CI (`python-version: "3.12"` dans `.github/workflows/ci.yml`). Ces trois fichiers sont alignés — toute divergence est un bug.

```bash
python3.12 --version         # Python 3.12.x
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Ne jamais utiliser `--break-system-packages` pour contourner PEP 668 ; voir §8 Dépannage.

### 1.3 Répertoire de travail

Toutes les commandes du projet — Docker, Python, pytest, dbt — se lancent depuis la **racine du projet** (le dossier qui contient `docker-compose.yml`). Les chemins dans le code applicatif sont relatifs à cette racine (`Path("data/gold/…")`).

### 1.4 Kaggle API Token

Le téléchargement des données Food.com nécessite un compte Kaggle et un token API.

Créer un token :

1. Se connecter à Kaggle.
2. Aller dans Settings.
3. Descendre jusqu'à la section API.
4. Cliquer sur Create New Token.

Configurer le token sous Linux / WSL :

```bash
mkdir -p ~/.kaggle
echo "<KAGGLE_API_TOKEN>" > ~/.kaggle/access_token
chmod 600 ~/.kaggle/access_token
```

Vérification :

```bash
kaggle datasets list -s foodcom
```

Le téléchargement Food.com peut ensuite être lancé avec :

```bash
python3 extract/foodcom/download_foodcom.py
```
---

## 2. Architecture d'ensemble

### 2.1 Schéma de la chaîne de données

```
Sources externes
  ├─ Kaggle (Food.com)       extract/foodcom/download_foodcom.py
  ├─ EUFIC (Selenium)        extract/eufic/extract_eufic.py
  └─ FAOSTAT (bulk ZIP)      extract/faostat/extract_faostat_qcl.py
         │
         ▼
data/bronze/                 (CSV/ZIP bruts, date-partitionnés, gitignorés)
         │
         ▼ transform/  ← DAG yummy_pipeline (tâche build_silver)
data/silver/                 (Parquets nettoyés, gitignorés)
  ├─ foodcom/silver_recipes_YYYYMMDD.parquet
  ├─ foodcom/silver_reviews_YYYYMMDD.parquet
  ├─ eufic/silver_seasonality_YYYYMMDD.parquet
  └─ faostat/qcl/silver_faostat_YYYYMMDD.parquet
         │
         ▼ tools/upload_to_minio.py
MinIO s3://yummy/            (object store local, port 9000)
  ├─ bronze/…
  ├─ silver/…
  └─ gold/…
         │
         ├─── chemin Python ──────────────────────────────────────────────────┐
         │    ml/sentiment + ml/matching                                       │
         │    transform/gold/build_gold_yummy_recommendations.py  ← DAG yummy_pipeline (tâche build_gold)  │
         │         │                                                           │
         │         ▼                                                           │
         │    data/gold/gold_yummy_recommendations.parquet  (local, gitignored)│
         │                    ← l'API et Streamlit lisent ICI                 │
         │                                                                     │
         └─── chemin dbt ─────────────────────────────────────────────────────┘
              dbt run (dbt-duckdb, httpfs)
                   lit silver depuis s3://yummy/silver/
                   lit gold_sentiment_scores depuis s3://yummy/gold/
                   écrit s3://yummy/gold/dbt_yummy_recommendations.parquet
                                        ← sortie de comparaison uniquement
         │
         ▼
tools/query_duckdb.py        (vérifie la lecture DuckDB ← MinIO)
         │
         ▼
API FastAPI  localhost:8000   (lit data/gold/ via volume Docker)
UI Streamlit localhost:8501   (lit data/gold/ + data/silver/ via volume Docker)
Airflow      localhost:8080   (orchestre build_silver → build_gold → upload_to_minio via DAG yummy_pipeline @daily)
```

### 2.2 Contrat de stockage MinIO

Le bucket `yummy` est la seule source de vérité pour la couche objet. Les chemins sont normalisés avec `/` (POSIX) :

| Préfixe S3 | Contenu | Outil d'écriture |
|---|---|---|
| `s3://yummy/bronze/…` | CSV/ZIP bruts (date-partitionnés) | `tools/upload_to_minio.py` |
| `s3://yummy/silver/…` | Parquets Silver nettoyés | `tools/upload_to_minio.py` |
| `s3://yummy/gold/gold_yummy_recommendations.parquet` | Gold Python (pipeline ML) | `tools/upload_to_minio.py` |
| `s3://yummy/gold/dbt_yummy_recommendations.parquet` | Gold dbt (SQL pipeline) | `dbt run` |
| `s3://yummy/gold/gold_sentiment_scores.parquet` | Scores VADER | `tools/upload_to_minio.py` |
| `s3://yummy/gold/gold_ingredient_matches.parquet` | Matching TF-IDF | `tools/upload_to_minio.py` |
| `s3://yummy/gold/gold_recipe_ingredient_map.parquet` | Carte ingrédients | `tools/upload_to_minio.py` |
| `s3://yummy/gold/gold_recipe_clusters.parquet` | Clusters KMeans | `tools/upload_to_minio.py` |
| `s3://yummy/gold/gold_cluster_profiles.parquet` | Profils moyens des 5 clusters | `tools/upload_to_minio.py` |

---

## 3. Les 8 services docker-compose

### 3.1 Vue d'ensemble

```yaml
# docker-compose.yml — 8 services, 2 volumes nommés
services: api | ui | minio | minio-init | airflow-db | airflow-init | airflow-webserver | airflow-scheduler
volumes:  minio_data | airflow-db-data
```

| Service | Image | Ports | Rôle |
|---|---|---|---|
| `api` | `yummy-app` (buildée localement) | `8000:8000` | FastAPI — sert `/recommendations` |
| `ui` | `yummy-app` (réutilisée, pas rebuildie) | `8501:8501` | Streamlit — interface utilisateur |
| `minio` | `minio/minio` (officielle) | `9000:9000` (S3 API), `9001:9001` (console web) | Object store S3-compatible |
| `minio-init` | `minio/mc` (officielle) | — | Tâche ponctuelle : crée le bucket `yummy` |
| `airflow-db` | `postgres:15` | — (interne) | PostgreSQL de métadonnées Airflow |
| `airflow-init` | `apache/airflow:2.9.1` | — | `db migrate` + création du user `admin` — tâche ponctuelle (exit 0) |
| `airflow-webserver` | `apache/airflow:2.9.1` | `8080:8080` | Interface web Airflow |
| `airflow-scheduler` | `apache/airflow:2.9.1` | — | Daemon d'ordonnancement des tâches |

### 3.2 Service `api`

```yaml
api:
  build: .             # déclenche le build depuis Dockerfile
  image: yummy-app     # nomme l'image — réutilisée par ui sans rebuild
  command: uvicorn api.main:app --host 0.0.0.0 --port 8000
  ports:
    - "8000:8000"
  volumes:
    - ./data:/app/data:ro
```

`--host 0.0.0.0` est obligatoire : uvicorn écoute sur `127.0.0.1` par défaut (loopback interne au conteneur). Le port-forward Docker achemine le trafic vers l'interface réseau du conteneur, pas vers son loopback — sans `0.0.0.0`, les requêtes de l'hôte n'atteignent pas le processus.

Le volume `./data:/app/data:ro` monte `./data/` de l'hôte en lecture seule. **Ce volume est la seule source de données pour l'API et l'UI** — voir §6.

### 3.3 Service `ui`

```yaml
ui:
  image: yummy-app            # pas de "build:" — réutilise l'image api
  command: streamlit run app/streamlit_app.py
           --server.port 8501 --server.address 0.0.0.0 --server.headless true
  ports:
    - "8501:8501"
  volumes:
    - ./data:/app/data:ro
  depends_on:
    - api
```

`--server.headless true` empêche Streamlit d'ouvrir un navigateur au démarrage (fatal en environnement sans display). `depends_on: [api]` garantit l'**ordre de démarrage**, pas la disponibilité applicative de l'API — timing parfois court sur machine lente.

Note architecturale : `streamlit_app.py` lit les parquets Gold **et** Silver directement via le volume, sans appeler l'API. La dépendance `depends_on: api` est déclarative mais non fonctionnelle.

### 3.4 Service `minio`

```yaml
minio:
  image: minio/minio
  command: server /data --console-address ":9001"
  ports:
    - "9000:9000"    # S3 API (boto3, DuckDB httpfs, dbt)
    - "9001:9001"    # Console web (http://localhost:9001)
  environment:
    MINIO_ROOT_USER:     ${MINIO_ROOT_USER}
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
  volumes:
    - minio_data:/data  # volume nommé Docker, persiste entre arrêts/relances
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 10s
```

Le healthcheck interroge `/minio/health/live` toutes les 10 s avec un délai de grâce de 10 s et 5 tentatives. L'état `healthy` est requis par `minio-init` (`condition: service_healthy`). Les credentials sont lus depuis `.env` via la syntaxe `${VAR}` de Compose.

### 3.5 Service `minio-init`

```yaml
minio-init:
  image: minio/mc
  depends_on:
    minio:
      condition: service_healthy   # attend le healthcheck, pas juste le démarrage
  entrypoint: >
    /bin/sh -c "
    mc alias set local http://minio:9000 ${MINIO_ROOT_USER} ${MINIO_ROOT_PASSWORD} &&
    mc mb --ignore-existing local/yummy &&
    echo '[INFO] Bucket yummy ready.'
    "
```

`minio-init` est une **tâche ponctuelle** : elle crée le bucket `yummy` une seule fois puis s'arrête avec exit code 0. C'est l'état attendu dans `docker compose ps`. `--ignore-existing` rend la tâche idempotente — relancer la pile ne provoque pas d'erreur si le bucket existe déjà.

Attention : `http://minio:9000` est l'URL **inter-conteneur** (réseau interne Docker). Depuis l'hôte WSL, l'URL est `http://localhost:9000`. Voir §7 Limites connues.

### 3.6 Services Airflow

Les 4 services partagent la même configuration de base via l'ancre YAML `x-airflow-common` :

```yaml
x-airflow-common: &airflow-common
  image: apache/airflow:2.9.1
  user: "${AIRFLOW_UID:-50000}:0"          # UID hôte — évite les PermissionError sur ./logs/
  environment:
    AIRFLOW__CORE__EXECUTOR: LocalExecutor
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@airflow-db/airflow
    AIRFLOW__CORE__LOAD_EXAMPLES: "false"
    MINIO_ENDPOINT: "minio:9000"           # réseau interne Docker — pas localhost
    MINIO_ROOT_USER: ${MINIO_ROOT_USER}
    MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
  volumes:
    - ./dags:/opt/airflow/dags
    - ./logs/airflow:/opt/airflow/logs   # bind-mount — doit être accessible par AIRFLOW_UID
    - .:/opt/airflow/project             # projet entier monté — accès aux scripts Python
  depends_on:
    airflow-db:
      condition: service_healthy
```

**Ordre de démarrage :** `airflow-db` (healthcheck `pg_isready`) → `airflow-init` (`service_completed_successfully`) → `airflow-webserver` + `airflow-scheduler`

**Volume projet :** le bind-mount `.:/opt/airflow/project` expose l'intégralité du projet dans les conteneurs. Les BashOperators appellent `cd /opt/airflow/project && python …`.

**Credentials MinIO dans Airflow :** `MINIO_ENDPOINT=minio:9000`, `MINIO_ROOT_USER` et `MINIO_ROOT_PASSWORD` sont injectés dans les 4 conteneurs Airflow via l'ancre. `tools/upload_to_minio.py` lit `MINIO_ENDPOINT` par `os.environ.get()` — la valeur `minio:9000` prend la priorité sur le fallback `localhost:9000` et sur le `.env` de l'hôte (qui contient `localhost:9000` pour l'usage local). `boto3` est disponible nativement dans `apache/airflow:2.9.1`, aucune installation supplémentaire n'est nécessaire.

### 3.7 DAG `yummy_pipeline`

Fichier : `dags/yummy_pipeline.py`

| Attribut | Valeur |
|---|---|
| `dag_id` | `yummy_pipeline` |
| `schedule` | `@daily` (minuit UTC) |
| `catchup` | `False` — pas de runs rétroactifs |
| `retries` | 1, délai 5 min |

**Tâches :**

| Tâche | Script appelé | Ce qu'elle produit |
|---|---|---|
| `build_silver` | `tools/build_all_silver.py` | Parquets Silver (FoodCom + EUFIC + FAOSTAT) dans `data/silver/` |
| `build_gold` | `transform/gold/build_gold_yummy_recommendations.py` | `data/gold/gold_yummy_recommendations.parquet` |
| `upload_to_minio` | `tools/upload_to_minio.py` | Pousse les 3 layers (bronze, silver, gold) vers `s3://yummy/` — dont les 6 fichiers Gold dans `s3://yummy/gold/` (`gold_yummy_recommendations`, `gold_sentiment_scores`, `gold_ingredient_matches`, `gold_recipe_ingredient_map`, `gold_recipe_clusters`, `gold_cluster_profiles`) |

**Graphe d'exécution actif :** `build_silver >> build_gold >> upload_to_minio`

**Accès à l'UI Airflow :**

```bash
# La pile doit être démarrée : docker compose up -d
# Ouvrir http://localhost:8080
# Login : admin / admin  (créé par airflow-init)
```

Activer le DAG via le toggle dans la liste des DAGs, puis le déclencher manuellement avec le bouton *Trigger DAG* (▶).

**Déclenchement via CLI :**

```bash
docker compose exec airflow-scheduler airflow dags trigger yummy_pipeline
```

---

## 4. Séquence de démarrage complète

Bloc de commandes copiable, à exécuter depuis la **racine du projet** dans un terminal WSL avec le venv activé.

```bash
# ── 0. Prérequis ─────────────────────────────────────────────────────────────
source .venv/bin/activate           # venv Python 3.12
cp .env.example .env                # première fois seulement ; éditer si nécessaire
# .env contient MINIO_ROOT_USER, MINIO_ROOT_PASSWORD, MINIO_ENDPOINT

# ── 1. Build de l'image Docker ────────────────────────────────────────────────
docker compose build
# Sortie attendue : "[+] Building … FINISHED" (peut durer 2-5 min au premier build)

# ── 2. Démarrage de la pile ───────────────────────────────────────────────────
docker compose up -d
# Démarre api, ui, minio, minio-init en arrière-plan
# minio-init attend que minio soit "healthy" (~10-30 s) puis crée le bucket

# ── 3. Vérification de l'état des conteneurs ─────────────────────────────────
docker compose ps
# Attendu :
#   api        running
#   ui         running
#   minio      running   (healthy)
#   minio-init exited    0

# ── 4. Vérification de l'API ─────────────────────────────────────────────────
curl -s http://localhost:8000/
# → {"message":"YUMMY API is running"}

# ── 5. Upload des données vers MinIO ─────────────────────────────────────────
# Envoie bronze/, silver/, gold/ depuis ./data/ vers s3://yummy/
python tools/upload_to_minio.py
# Sortie : "[INFO] Terminé — N fichier(s) au total."

# ── 6. Vérification DuckDB → MinIO ───────────────────────────────────────────
python tools/query_duckdb.py
# Sortie : top 10 recettes par yummy_score depuis s3://yummy/gold/

# ── 7. Exécution du pipeline dbt ─────────────────────────────────────────────
# dbt-duckdb écrit dans target/yummy.duckdb (chemin relatif à dbt/)
mkdir -p dbt/target

# Les variables d'environnement MinIO doivent être exportées (lues par profiles.yml)
export MINIO_ROOT_USER=$(grep MINIO_ROOT_USER .env | cut -d= -f2)
export MINIO_ROOT_PASSWORD=$(grep MINIO_ROOT_PASSWORD .env | cut -d= -f2)
export MINIO_ENDPOINT=$(grep MINIO_ENDPOINT .env | cut -d= -f2)

cd dbt
dbt run --profiles-dir .
# Sortie : "Completed successfully" + 3 modèles (stg_recipes, stg_sentiment, yummy_recommendations)
dbt test --profiles-dir .
# Sortie : tests not_null, unique, accepted_range — tous PASS
cd ..

# ── 8. Audit d'intégration complet ───────────────────────────────────────────
python tools/healthcheck.py
# Sortie : PASS/FAIL par étape + résumé final
```

**Durées indicatives (machine de développement Quadro M1200, 8 cœurs) :**

| Étape | Durée |
|---|---|
| `docker compose build` (premier build) | 3–5 min |
| `docker compose build` (rebuild, requirements inchangés) | < 5 s |
| `docker compose up -d` (démarrage + healthcheck minio) | 30–60 s |
| `python tools/upload_to_minio.py` | Variable selon volume de données |
| `dbt run --profiles-dir .` | ~30 s (lecture Silver + calcul Gold + écriture S3) |
| `python tools/healthcheck.py` | ~15–20 s |

---

## 5. Audit d'intégration

### 5.1 Lancement

```bash
# Depuis la racine du projet, venv activé, tous les services up
python tools/healthcheck.py
```

Les variables d'environnement MinIO doivent être définies (via `.env` auto-chargé par `load_dotenv()` ou exportées dans le shell).

### 5.2 Interprétation de la sortie

```
════════════════════════════════════════════════════════════
  YUMMY — Audit d'intégration bout en bout
════════════════════════════════════════════════════════════
  Endpoint MinIO : localhost:9000
  API            : http://localhost:8000
  UI             : http://localhost:8501

Étape 1 — Conteneurs Docker
────────────────────────────────────────────────────────────
  [PASS] api         — running
  [PASS] ui          — running
  [PASS] minio       — running, healthy
  [PASS] minio-init  — absent (nettoyé après exécution, bucket présumé créé)

Étape 2 — MinIO — connexion et contenu du bucket
────────────────────────────────────────────────────────────
  [PASS] Connexion boto3 OK — bucket 'yummy' présent (endpoint: localhost:9000)
  [PASS]   bronze/  — N objet(s)
  [PASS]   silver/  — N objet(s)
  [PASS]   gold/    — N objet(s)

…

════════════════════════════════════════════════════════════
  RÉSUMÉ FINAL
════════════════════════════════════════════════════════════
  [PASS] ✓  Docker — 4 conteneurs
  [PASS] ✓  MinIO — bucket et objets
  [PASS] ✓  DuckDB — lecture Gold depuis MinIO
  [PASS] ✓  API FastAPI — /recommendations
  [PASS] ✓  UI Streamlit — HTTP 200
  [PASS] ✓  Tests pytest
────────────────────────────────────────────────────────────
  Résultat global : PASS — chaîne complète opérationnelle (6/6).
```

Le script renvoie **exit code 0** si toutes les étapes passent, **exit code 1** si au moins une échoue. Chaque étape est encadrée dans un `try/except` : une exception non gérée dans une étape n'interrompt pas les suivantes — le rapport est toujours complet.

**Clé de lecture FAIL :**

| Étape en FAIL | Première cause à vérifier |
|---|---|
| Étape 1 | `docker compose ps` — service exited ou minio pas healthy |
| Étape 2 | `.env` non chargé, ou `tools/upload_to_minio.py` non exécuté |
| Étape 3 | Parquet absent de `s3://yummy/gold/` — pipeline ML + upload manquants |
| Étape 4 | `data/gold/gold_yummy_recommendations.parquet` absent localement |
| Étape 5 | Service `ui` non démarré ou en crash |
| Étape 6 | Fixtures absentes (génération auto tentée) ou test régressé |

---

## 6. Source de vérité Gold — deux chemins

### 6.1 Les deux pipelines Gold

Le parquet Gold est produit par **deux chemins indépendants** qui coexistent :

| | Pipeline Python | Pipeline dbt |
|---|---|---|
| **Script** | `transform/gold/build_gold_yummy_recommendations.py` | `dbt run` (modèle `yummy_recommendations.sql`) |
| **Entrée sentiment** | `data/gold/gold_sentiment_scores.parquet` (local) | `s3://yummy/gold/gold_sentiment_scores.parquet` (MinIO) |
| **Sortie locale** | `data/gold/gold_yummy_recommendations.parquet` | — |
| **Sortie MinIO** | `s3://yummy/gold/gold_yummy_recommendations.parquet` (via upload) | `s3://yummy/gold/dbt_yummy_recommendations.parquet` |
| **Formule** | Python/pandas — ml/README §6 | SQL DuckDB — `dbt/models/gold/yummy_recommendations.sql` |

### 6.2 Ce que l'API et l'UI lisent réellement

**L'API (`api/main.py`) et Streamlit (`app/streamlit_app.py`) lisent le fichier local :**

```python
# api/main.py
GOLD_FILE = Path("data/gold/gold_yummy_recommendations.parquet")
# app/streamlit_app.py
GOLD = Path("data/gold")
```

Ces chemins sont résolus depuis le `WORKDIR /app` du conteneur, via le volume `./data:/app/data:ro`. **L'API ne lit jamais depuis MinIO directement.** Elle consomme exclusivement ce que le volume expose, soit le parquet produit par le pipeline Python.

### 6.3 Concordance Python vs dbt

Les deux pipelines ont été validés sur le même jeu de données Silver (run canonique 2026-05-28, 275 028 recettes). L'écart maximal observé est ≤ 0,01 sur le `yummy_score`, attribuable à la différence d'arrondi flottant entre Python (`round(x, 2)` via pandas) et DuckDB (`ROUND(x, 2)` en SQL). Aucune divergence de formule — les paramètres bayésiens C et m sont recalculés identiquement dans les deux chemins.

La sortie dbt (`dbt_yummy_recommendations.parquet`) sert à la **comparaison et à la validation**. Pour passer l'API en lecture dbt, il faudrait soit modifier `api/main.py` pour lire depuis MinIO via DuckDB, soit remplacer le parquet local par une copie DuckDB → local (hors périmètre V1).

---

## 7. Limites connues

### 7.1 Image Docker sans données — dépendance au volume

Le `.dockerignore` exclut `data/gold/` (ajouté depuis la version initiale) : les parquets Gold ne sont **pas** baked-in dans l'image. Les deux services (`api`, `ui`) démarrent sans erreur mais toute requête échoue avec `FileNotFoundError` si `./data/gold/` n'existe pas sur l'hôte ou si le volume n'est pas monté. Il n'y a aucune vérification de présence des données au démarrage du conteneur.

### 7.2 Endpoints MinIO : localhost vs minio

MinIO est accessible sur **deux URLs différentes selon le contexte** :

| Contexte | URL | Pourquoi |
|---|---|---|
| Hôte WSL (scripts Python, navigateur) | `http://localhost:9000` | Port-forward Docker `9000:9000` |
| Depuis un conteneur (futur Airflow, etc.) | `http://minio:9000` | Réseau interne Docker, nom DNS = nom du service |

Les scripts `tools/upload_to_minio.py`, `tools/query_duckdb.py`, et `dbt/profiles.yml` lisent `MINIO_ENDPOINT` depuis l'environnement (défaut : `localhost:9000`). Les conteneurs Airflow surchargent cette variable à `minio:9000` via l'ancre `x-airflow-common` (voir §3.6).

### 7.3 Warning dbt — test `accepted_range`

Le test générique `accepted_range` est implémenté dans `dbt/macros/test_accepted_range.sql` sans dépendance à `dbt-utils`. Lors de `dbt test`, dbt peut émettre un warning de dépréciation concernant la syntaxe des tests génériques selon la version mineure de dbt-core. Ce warning est non bloquant. Si `dbt-utils` est ajouté ultérieurement au projet (`dbt/packages.yml`), renommer le macro local pour éviter la collision de noms.

### 7.4 Alignement Python 3.12 — trois surfaces

`.python-version`, `ci.yml` (`python-version: "3.12"`), et `Dockerfile` (`FROM python:3.12-slim`) sont alignés sur 3.12. Toute mise à jour de version Python doit être propagée sur les trois fichiers simultanément. Un désalignement (ex. `Dockerfile` sur 3.11 et `ci.yml` sur 3.12) peut produire des comportements différents entre le conteneur et la CI sans erreur explicite.

### 7.5 Pas de cache pip en CI

Le workflow GitHub Actions ne configure aucun `cache: 'pip'` sur l'étape `setup-python`. À chaque run, plusieurs centaines de Mo de dépendances sont retéléchargés depuis PyPI (3–8 min selon la charge). Ajouter `cache: 'pip'` réduirait les runs suivants à quelques secondes.

### 7.6 `depends_on` sans healthcheck sur `api`

`depends_on: [api]` sur le service `ui` garantit l'**ordre de démarrage**, pas la disponibilité applicative. Sur machines lentes, Streamlit peut démarrer avant qu'uvicorn soit prêt — les premières requêtes inter-service échouent (non bloquant en pratique, l'UI ne passe pas par l'API).


### 7.8 Selenium sous WSL / Linux headless

Le scraper EUFIC utilise Selenium et Chrome.

Sur certains environnements Linux, WSL ou Docker, Chrome peut échouer avec :

```text
SessionNotCreatedException:
DevToolsActivePort file doesn't exist
```

ou :

```text
WebDriverException:
chromedriver unexpectedly exited
```

Pour améliorer la compatibilité des environnements headless, les options Chrome suivantes sont recommandées :

```python
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--remote-debugging-port=9222")
chrome_options.add_argument("--window-size=1920,1080")
```

Ces options ont été validées sur WSL Ubuntu.
---

## 8. Dépannage

### Tableau symptôme → cause → solution

| Symptôme | Cause probable | Solution |
|---|---|---|
| `docker: command not found` dans WSL | Docker Desktop non lancé, ou distribution non cochée dans WSL Integration | Lancer Docker Desktop → Settings → Resources → WSL Integration → cocher la distribution → Apply & Restart → rouvrir terminal WSL |
| `docker compose` non trouvé, `docker-compose` fonctionne | Docker Compose v1 (binaire séparé) | Utiliser `docker compose` (espace, v2). Mettre à jour Docker Desktop si seul v1 disponible |
| `error: externally-managed-environment` au `pip install` | Python système Ubuntu protégé par PEP 668 | Créer et activer un venv : `python3.12 -m venv .venv && source .venv/bin/activate`. Ne jamais utiliser `--break-system-packages` |
| `SIGBUS` ou crash pendant `docker compose build` | Contexte de build trop lourd, Docker Desktop corrompu, ou manque de mémoire | Vérifier `.dockerignore` (`.venv/` doit être exclu). Redémarrer Docker Desktop depuis Windows. Si persistant : *Settings → Reset to factory defaults* |
| `Container yummy-minio-init-1 Exited` avec exit code ≠ 0 | MinIO n'était pas healthy quand minio-init a démarré, ou credentials incorrects | `docker compose logs minio-init`. Vérifier que `.env` contient `MINIO_ROOT_USER` et `MINIO_ROOT_PASSWORD`. Relancer : `docker compose restart minio-init` |
| `minio` reste en état `starting` ou `unhealthy` | Port 9000 déjà occupé sur l'hôte, ou MinIO démarre lentement | `lsof -i :9000` pour identifier le processus en conflit. Augmenter `start_period` dans le healthcheck si machine lente |
| API retourne `500 Internal Server Error` sur `/recommendations` | `data/gold/gold_yummy_recommendations.parquet` absent dans `./data/gold/` | Générer les parquets Gold : `python tools/build_all_ml.py`. Vérifier que `./data/gold/` existe sur l'hôte |
| `tools/upload_to_minio.py` échoue avec `NoCredentialsError` | Variables d'environnement MinIO non définies | `source .venv/bin/activate && export $(cat .env \| xargs)` puis relancer |
| `dbt run` échoue avec `IO Error: Cannot open file "target/yummy.duckdb"` | Dossier `dbt/target/` absent | `mkdir -p dbt/target` depuis la racine du projet, puis relancer `dbt run` |
| `dbt run` échoue avec `S3Error` ou `IO Error` sur `read_parquet('s3://…')` | Variables MinIO non exportées dans le shell avant `dbt run` | Exporter explicitement : `export MINIO_ROOT_USER=… MINIO_ROOT_PASSWORD=… MINIO_ENDPOINT=…` avant `cd dbt && dbt run --profiles-dir .` |
| `healthcheck.py` étape 3 FAIL — Bourbon Chicken score inattendu | Pipeline Gold Python non exécuté, ou parquet uploadé sur MinIO est une ancienne version | Relancer `python tools/build_all_ml.py --from 3` puis `python tools/upload_to_minio.py` |
| `pytest` exit code 4, message `Fixture files missing` | Fixtures de test non générées avant la session | `python tests/fixtures/generate_fixtures.py` puis `pytest -q`. `healthcheck.py` gère ce cas automatiquement |
| `ruff: command not found` en local | ruff non installé dans le venv actif | `pip install ruff` (ruff n'est pas dans `requirements.txt`, il est installé séparément en CI) |
| Streamlit `FileNotFoundError` au chargement | Parquet Silver ou Gold absent dans `./data/` | Vérifier `./data/gold/` et `./data/silver/`. Le volume `:ro` ne crée pas les fichiers — il monte ce qui existe sur l'hôte |
| `airflow-init` échoue avec `PermissionError: /opt/airflow/logs/scheduler` | Le bind-mount `./logs/airflow` appartient à `root` sur l'hôte, mais les conteneurs Airflow tournent sous un UID non-root | `user: "${AIRFLOW_UID:-50000}:0"` est déjà dans `x-airflow-common`. S'assurer que `AIRFLOW_UID=$(id -u)` est défini dans `.env`. Si le problème persiste : `sudo chown -R $(id -u):0 logs/airflow` depuis la racine du projet |
| Tâche Airflow échoue avec `ModuleNotFoundError: No module named 'pandas'` (ou `pyarrow`) | `pandas`/`pyarrow` absents de l'image `apache/airflow:2.9.1` telle qu'installée | Vérifier : `docker compose exec airflow-scheduler pip list \| grep -E "pandas\|pyarrow"`. Si absent : `docker compose exec airflow-scheduler pip install pandas pyarrow` (éphémère — perdu au redémarrage). Solution permanente : un `Dockerfile.airflow` étendant l'image avec `requirements.txt` du projet |
| `mc alias set` échoue (credentials vides, `ERROR: Specified access credentials are invalid`) lors d'un test manuel | Les `${MINIO_ROOT_USER}` et `${MINIO_ROOT_PASSWORD}` de l'entrypoint `minio-init` sont interpolés par Docker Compose au déploiement (guillemets doubles). Si `.env` est absent ou incomplet, les valeurs sont vides et MinIO rejette la connexion. Pour tester manuellement depuis l'hôte, utiliser `sh -c '...'` (guillemets simples) pour que l'évaluation se fasse dans le shell du conteneur, où les vars d'env sont disponibles : `docker compose exec minio-init sh -c 'mc alias set local http://minio:9000 $MINIO_ROOT_USER $MINIO_ROOT_PASSWORD'` — ou plus simplement vérifier que `.env` est présent avant `docker compose up` |
