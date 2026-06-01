"""
Audit d'intégration YUMMY — vérifie la chaîne complète bout en bout.

Exécute 6 étapes en séquence, affiche [PASS] / [FAIL] par étape, continue
même si une étape échoue pour produire un rapport complet, puis termine avec
exit code 0 (tout PASS) ou 1 (au moins un FAIL).

Ce script est en LECTURE SEULE : aucune donnée de production n'est modifiée.
Les fixtures pytest sont générées à la volée si absentes (données de test
uniquement, non destructif).

Usage (depuis la racine du projet) :
    python tools/healthcheck.py

Prérequis d'environnement :
    MINIO_ROOT_USER      — access key MinIO  (ou défini dans .env)
    MINIO_ROOT_PASSWORD  — secret key MinIO
    MINIO_ENDPOINT       — host:port, défaut : localhost:9000
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# ── Imports tiers (tous présents dans requirements.txt) ───────────────────────
try:
    import boto3
    from botocore.config import Config as BotoConfig
except ImportError:
    boto3 = None  # type: ignore[assignment]

try:
    import duckdb
except ImportError:
    duckdb = None  # type: ignore[assignment]

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

try:
    from dotenv import load_dotenv
    load_dotenv()   # charge .env depuis la racine si présent
except ImportError:
    pass            # python-dotenv absent : on lit les vars d'env du shell


# ── Configuration ──────────────────────────────────────────────────────────────
MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_USER     = os.environ.get("MINIO_ROOT_USER", "")
MINIO_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD", "")
BUCKET         = "yummy"

API_BASE = "http://localhost:8000"
UI_BASE  = "http://localhost:8501"

# Bourbon Chicken — recette de référence pour valider le Gold (ml/README §6.5).
BOURBON_CHICKEN_ID    = 45809
BOURBON_CHICKEN_SCORE = 82.45
SCORE_TOLERANCE       = 0.02          # tolérance arrondi Python vs DuckDB


# ── Affichage ──────────────────────────────────────────────────────────────────
_GREEN = "\033[92m"
_RED   = "\033[91m"
_BOLD  = "\033[1m"
_RESET = "\033[0m"

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _pass(msg: str) -> None:
    """Affiche une ligne de succès en vert."""
    print(f"  {_GREEN}[PASS]{_RESET} {msg}")


def _fail(msg: str) -> None:
    """Affiche une ligne d'échec en rouge."""
    print(f"  {_RED}[FAIL]{_RESET} {msg}")


def _info(msg: str) -> None:
    """Affiche une ligne de détail indentée (ni PASS ni FAIL)."""
    print(f"       {msg}")


def _header(step: int, title: str) -> None:
    """Affiche le titre d'une étape."""
    print(f"\n{_BOLD}Étape {step} — {title}{_RESET}")
    print("─" * 60)


# ── Étape 1 : conteneurs Docker ────────────────────────────────────────────────

def check_docker() -> bool:
    """Vérifie que les 4 conteneurs sont dans l'état attendu.

    États attendus :
    - api        → running
    - ui         → running
    - minio      → running + healthy (healthcheck docker-compose)
    - minio-init → exited, exit code 0 (tâche ponctuelle de création du bucket)
    """
    _header(1, "Conteneurs Docker")

    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
            cwd=PROJECT_ROOT,
        )
    except FileNotFoundError:
        _fail("Commande 'docker' introuvable — Docker Desktop non lancé ou intégration WSL désactivée")
        return False
    except subprocess.CalledProcessError as exc:
        _fail(f"docker compose ps a échoué (exit {exc.returncode}) : {exc.stderr.strip()[:200]}")
        return False

    # docker compose ps --format json : une ligne JSON par conteneur (NDJSON)
    containers: dict[str, dict] = {}
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            containers[obj["Service"]] = obj
        except (json.JSONDecodeError, KeyError):
            continue

    if not containers:
        _fail("Aucun conteneur retourné par docker compose ps — pile non démarrée ?")
        return False

    all_ok = True

    # ── api ────────────────────────────────────────────────────────────────────
    svc = containers.get("api")
    if svc and svc.get("State") == "running":
        _pass("api           — running")
    else:
        state = svc.get("State", "absent") if svc else "absent"
        _fail(f"api           — état '{state}' (attendu: running)")
        all_ok = False

    # ── ui ────────────────────────────────────────────────────────────────────
    svc = containers.get("ui")
    if svc and svc.get("State") == "running":
        _pass("ui            — running")
    else:
        state = svc.get("State", "absent") if svc else "absent"
        _fail(f"ui            — état '{state}' (attendu: running)")
        all_ok = False

    # ── minio : running + healthy ─────────────────────────────────────────────
    svc = containers.get("minio")
    if svc and svc.get("State") == "running":
        # Le champ Health existe dans docker compose v2 ; Status contient aussi "(healthy)".
        health = svc.get("Health", "") or svc.get("Status", "")
        if "healthy" in health.lower():
            _pass("minio         — running, healthy")
        else:
            _fail(f"minio         — running mais pas healthy (Health/Status='{health}')")
            all_ok = False
    else:
        state = svc.get("State", "absent") if svc else "absent"
        _fail(f"minio         — état '{state}' (attendu: running+healthy)")
        all_ok = False

    # ── minio-init : tâche ponctuelle — PASS si exited 0 ou absent ───────────
    # État correct : exited 0 (bucket créé puis conteneur arrêté).
    # Absent = conteneur supprimé après exécution (docker compose rm) — le
    # bucket existe déjà, c'est un état valide.
    # FAIL uniquement si exited avec code ≠ 0 (échec d'initialisation).
    svc = containers.get("minio-init")
    if svc is None:
        _pass("minio-init    — absent (nettoyé après exécution, bucket présumé créé)")
    else:
        state     = svc.get("State", "")
        exit_code = svc.get("ExitCode", -1)
        if state == "exited" and exit_code == 0:
            _pass(f"minio-init    — exited 0  (bucket '{BUCKET}' initialisé)")
        elif state == "exited":
            _fail(f"minio-init    — exited {exit_code}  (échec initialisation bucket — docker compose logs minio-init)")
            all_ok = False
        else:
            # running = encore en cours d'initialisation ; pas un échec
            _info(f"minio-init    — état '{state}' (tâche en cours, attendre exit 0)")

    return all_ok


# ── Étape 2 : MinIO ────────────────────────────────────────────────────────────

def check_minio() -> bool:
    """Vérifie la connexion boto3, l'existence du bucket et les objets par couche.

    Compte les objets sous bronze/, silver/, gold/ — au moins un objet par couche
    prouve que le pipeline a été exécuté et que tools/upload_to_minio.py a tourné.
    """
    _header(2, "MinIO — connexion et contenu du bucket")

    if boto3 is None:
        _fail("boto3 non disponible (pip install boto3)")
        return False
    if not MINIO_USER or not MINIO_PASSWORD:
        _fail("MINIO_ROOT_USER et/ou MINIO_ROOT_PASSWORD non définis dans l'environnement")
        return False

    try:
        client = boto3.client(
            "s3",
            endpoint_url=f"http://{MINIO_ENDPOINT}",
            aws_access_key_id=MINIO_USER,
            aws_secret_access_key=MINIO_PASSWORD,
            config=BotoConfig(signature_version="s3v4"),
            use_ssl=False,
        )

        # Vérification de la présence du bucket
        buckets = [b["Name"] for b in client.list_buckets().get("Buckets", [])]
        if BUCKET not in buckets:
            _fail(f"Bucket '{BUCKET}' introuvable — buckets présents : {buckets}")
            return False
        _pass(f"Connexion boto3 OK — bucket '{BUCKET}' présent (endpoint: {MINIO_ENDPOINT})")

        # Comptage par couche : bronze/, silver/, gold/
        all_ok = True
        for layer in ("bronze", "silver", "gold"):
            paginator = client.get_paginator("list_objects_v2")
            count = sum(
                page.get("KeyCount", 0)
                for page in paginator.paginate(Bucket=BUCKET, Prefix=f"{layer}/")
            )
            if count > 0:
                _pass(f"  {layer:6s}/  — {count} objet(s)")
            else:
                _fail(f"  {layer:6s}/  — aucun objet  (tools/upload_to_minio.py non exécuté ?)")
                all_ok = False

        return all_ok

    except Exception as exc:
        _fail(f"Connexion MinIO impossible sur {MINIO_ENDPOINT} : {exc}")
        return False


# ── Étape 3 : DuckDB ────────────────────────────────────────────────────────────

def check_duckdb() -> bool:
    """Lit le Gold depuis MinIO via DuckDB/httpfs et vérifie Bourbon Chicken.

    Reproduit la configuration de tools/query_duckdb.py (s3_url_style='path',
    s3_use_ssl=false) et cherche recipeid=45809 avec yummy_score ≈ 82.45.
    """
    _header(3, "DuckDB — lecture Gold depuis MinIO")

    if duckdb is None:
        _fail("duckdb non disponible (pip install duckdb)")
        return False
    if not MINIO_USER or not MINIO_PASSWORD:
        _fail("MINIO_ROOT_USER et/ou MINIO_ROOT_PASSWORD non définis")
        return False

    url = f"s3://{BUCKET}/gold/gold_yummy_recommendations.parquet"

    try:
        conn = duckdb.connect()
        conn.execute("INSTALL httpfs")
        conn.execute("LOAD httpfs")
        conn.execute(f"SET s3_endpoint='{MINIO_ENDPOINT}'")
        conn.execute(f"SET s3_access_key_id='{MINIO_USER}'")
        conn.execute(f"SET s3_secret_access_key='{MINIO_PASSWORD}'")
        conn.execute("SET s3_use_ssl=false")
        # path-style obligatoire pour MinIO — voir tools/query_duckdb.py docstring
        conn.execute("SET s3_url_style='path'")

        df = conn.execute(f"""
            SELECT recipeid, name, yummy_score
            FROM   read_parquet('{url}')
            WHERE  recipeid = {BOURBON_CHICKEN_ID}
        """).fetchdf()

        conn.close()

        if df.empty:
            _fail(f"Bourbon Chicken (recipeid={BOURBON_CHICKEN_ID}) absent du parquet Gold")
            return False

        score = float(df.iloc[0]["yummy_score"])
        delta = abs(score - BOURBON_CHICKEN_SCORE)

        if delta <= SCORE_TOLERANCE:
            _pass(
                f"Bourbon Chicken id={BOURBON_CHICKEN_ID}  "
                f"yummy_score={score:.2f}  Δ={delta:.4f} ≤ {SCORE_TOLERANCE}"
            )
            return True
        else:
            _fail(
                f"Bourbon Chicken yummy_score={score:.2f}  "
                f"attendu≈{BOURBON_CHICKEN_SCORE}  Δ={delta:.4f} > {SCORE_TOLERANCE}"
            )
            return False

    except Exception as exc:
        _fail(f"Lecture DuckDB/MinIO impossible : {exc}")
        return False


# ── Étape 4 : API FastAPI ──────────────────────────────────────────────────────

def check_api() -> bool:
    """Vérifie que l'API répond et que Bourbon Chicken est en première position.

    GET /recommendations?limit=3 doit retourner du JSON avec recipeid=45809
    en position 0, yummy_score ≈ 82.45.
    """
    _header(4, "API FastAPI — /recommendations")

    if requests is None:
        _fail("requests non disponible (pip install requests)")
        return False

    # ── Health check ──────────────────────────────────────────────────────────
    try:
        r = requests.get(f"{API_BASE}/", timeout=5)
    except requests.exceptions.ConnectionError:
        _fail(f"Impossible de joindre l'API sur {API_BASE} — service api démarré ?")
        return False

    if r.status_code != 200:
        _fail(f"GET / → HTTP {r.status_code}")
        return False
    _pass(f"GET /             → {r.status_code}  {r.json()}")

    # ── Recommendations ───────────────────────────────────────────────────────
    try:
        r = requests.get(f"{API_BASE}/recommendations?limit=3", timeout=15)
    except requests.exceptions.ConnectionError:
        _fail("GET /recommendations a perdu la connexion")
        return False

    if r.status_code != 200:
        _fail(f"GET /recommendations?limit=3 → HTTP {r.status_code}")
        return False

    try:
        items = r.json()
    except ValueError:
        _fail("Réponse non-JSON")
        return False

    if not items:
        _fail("Liste de recommandations vide")
        return False

    top = items[0]
    if top.get("recipeid") != BOURBON_CHICKEN_ID:
        _fail(
            f"Première recette : recipeid={top.get('recipeid')}  "
            f"(attendu {BOURBON_CHICKEN_ID} — Bourbon Chicken)"
        )
        return False

    score = float(top.get("yummy_score", 0))
    delta = abs(score - BOURBON_CHICKEN_SCORE)

    if delta <= SCORE_TOLERANCE:
        _pass(
            f"GET /recommendations  top 1 = Bourbon Chicken  "
            f"yummy_score={score:.2f}  Δ={delta:.4f}"
        )
        return True
    else:
        _fail(
            f"Bourbon Chicken en tête mais yummy_score={score:.2f}  "
            f"attendu≈{BOURBON_CHICKEN_SCORE}  Δ={delta:.4f}"
        )
        return False


# ── Étape 5 : UI Streamlit ─────────────────────────────────────────────────────

def check_ui() -> bool:
    """Vérifie que l'interface Streamlit retourne HTTP 200.

    Une réponse 200 prouve que le serveur Streamlit est démarré et répond.
    Le contenu HTML n'est pas inspecté.
    """
    _header(5, "UI Streamlit — HTTP 200")

    if requests is None:
        _fail("requests non disponible (pip install requests)")
        return False

    try:
        r = requests.get(f"{UI_BASE}/", timeout=10)
    except requests.exceptions.ConnectionError:
        _fail(f"Impossible de joindre l'UI sur {UI_BASE} — service ui démarré ?")
        return False

    if r.status_code == 200:
        _pass(f"GET {UI_BASE}/  → {r.status_code}")
        return True
    else:
        _fail(f"GET {UI_BASE}/  → HTTP {r.status_code}")
        return False


# ── Étape 6 : Tests pytest ─────────────────────────────────────────────────────

def check_tests() -> bool:
    """Lance pytest -q et vérifie l'exit code 0.

    Génère les fixtures si absentes (data/tests/fixtures/*.parquet).
    Les fixtures sont des données de test synthétiques, leur génération
    est non destructive.
    """
    _header(6, "Tests pytest")

    fixtures_dir = PROJECT_ROOT / "data" / "tests" / "fixtures"
    fixture_files = list(fixtures_dir.glob("*.parquet")) if fixtures_dir.exists() else []

    # ── Génération des fixtures si absentes ───────────────────────────────────
    if not fixture_files:
        _info("Fixtures absentes — génération via tests/fixtures/generate_fixtures.py ...")
        gen = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tests" / "fixtures" / "generate_fixtures.py")],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if gen.returncode != 0:
            _fail(f"generate_fixtures.py a échoué (exit {gen.returncode})")
            _info(gen.stderr.strip()[:300] if gen.stderr.strip() else gen.stdout.strip()[:300])
            return False
        _info("Fixtures générées.")

    # ── Lancement de pytest ───────────────────────────────────────────────────
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )

    # Affiche les dernières lignes de la sortie pytest pour contexte
    output = (result.stdout + result.stderr).strip()
    for line in output.splitlines()[-10:]:
        _info(line)

    if result.returncode == 0:
        _pass("pytest -q → exit 0")
        return True
    else:
        _fail(f"pytest -q → exit {result.returncode}")
        return False


# ── Point d'entrée ─────────────────────────────────────────────────────────────

def main() -> None:
    """Exécute les 6 étapes et affiche le résumé final.

    Toutes les étapes sont exécutées même si certaines échouent, afin
    de produire un rapport complet. Exit code 0 = tout PASS, 1 = au moins un FAIL.
    """
    print(f"\n{'═' * 60}")
    print(f"  {_BOLD}YUMMY — Audit d'intégration bout en bout{_RESET}")
    print(f"{'═' * 60}")
    print(f"  Endpoint MinIO : {MINIO_ENDPOINT}")
    print(f"  API            : {API_BASE}")
    print(f"  UI             : {UI_BASE}")
    print(f"  Racine projet  : {PROJECT_ROOT}")

    steps = [
        ("Docker — 4 conteneurs",              check_docker),
        ("MinIO — bucket et objets",            check_minio),
        ("DuckDB — lecture Gold depuis MinIO",  check_duckdb),
        ("API FastAPI — /recommendations",      check_api),
        ("UI Streamlit — HTTP 200",             check_ui),
        ("Tests pytest",                        check_tests),
    ]

    results: list[tuple[str, bool]] = []
    for name, fn in steps:
        try:
            ok = fn()
        except Exception as exc:
            # Filet de sécurité : une exception non gérée dans une étape
            # ne doit pas interrompre le reste du rapport.
            _fail(f"Exception inattendue : {exc}")
            ok = False
        results.append((name, ok))

    # ── Résumé final ───────────────────────────────────────────────────────────
    print(f"\n{'═' * 60}")
    print(f"  {_BOLD}RÉSUMÉ FINAL{_RESET}")
    print(f"{'═' * 60}")

    n_pass = n_fail = 0
    for name, ok in results:
        if ok:
            status = f"{_GREEN}PASS{_RESET}"
            marker = "✓"
            n_pass += 1
        else:
            status = f"{_RED}FAIL{_RESET}"
            marker = "✗"
            n_fail += 1
        print(f"  [{status}] {marker}  {name}")

    print(f"{'─' * 60}")
    if n_fail == 0:
        print(
            f"  {_GREEN}{_BOLD}Résultat global : PASS — "
            f"chaîne complète opérationnelle ({n_pass}/{len(results)}).{_RESET}"
        )
        sys.exit(0)
    else:
        print(
            f"  {_RED}{_BOLD}Résultat global : FAIL — "
            f"{n_fail}/{len(results)} étape(s) échouée(s).{_RESET}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
