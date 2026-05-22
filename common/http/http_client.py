"""
Module HTTP partagé pour la collecte web.

Création de session + téléchargement avec gestion du 429 (Retry-After,
backoff, retries). On respecte le robots.txt et un délai entre requêtes.
On ne contourne PAS les protections anti-bot : si un site bloque activement,
on le retire du périmètre plutôt que de forcer (cohérence éthique du projet).
"""
import time

import requests

from common.http.config import (
    BROWSER_HEADERS,
    REQUEST_TIMEOUT,
    MAX_RETRIES,
    DEFAULT_RETRY_AFTER_SECONDS,
)


def make_session() -> requests.Session:
    """Crée une session HTTP avec headers de navigateur réalistes."""
    session = requests.Session()
    session.headers.update(BROWSER_HEADERS)
    return session


def _parse_retry_after(response: requests.Response) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return float(DEFAULT_RETRY_AFTER_SECONDS)
    try:
        return float(retry_after)
    except ValueError:
        return float(DEFAULT_RETRY_AFTER_SECONDS)


def fetch(session: requests.Session, url: str) -> requests.Response | None:
    """Télécharge une URL avec gestion du 429 et backoff.

    Retourne la Response en cas de succès, None après épuisement des retries.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)

            if response.status_code == 429:
                wait = _parse_retry_after(response) * attempt
                print(
                    f"[WARNING] 429 Too Many Requests on {url} "
                    f"(attempt {attempt}/{MAX_RETRIES}) -> waiting {wait:.0f}s"
                )
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as error:
            print(f"[WARNING] Attempt {attempt}/{MAX_RETRIES} failed for {url}: {error}")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_TIMEOUT * 0.5 * attempt)

    print(f"[ERROR] Giving up on {url} after {MAX_RETRIES} attempts")
    return None


def fetch_text(session: requests.Session, url: str) -> str | None:
    """Télécharge une URL et retourne son texte, ou None."""
    response = fetch(session, url)
    return response.text if response is not None else None