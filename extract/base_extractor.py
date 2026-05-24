"""
Classe de base standard des extracteurs Bronze — Yummy Data Platform.

Tout extracteur de fichier (download -> Bronze local) hérite de BronzeExtractor
et implémente fetch() / normalize() / validate(). L'orchestration run() est
commune et NE DOIT PAS être surchargée : elle garantit que tous les extracts
se comportent pareil (mêmes logs, même structure de sortie, même contrat).

⚠️ Frontière Bronze/Silver — règle d'or du projet :
    Bronze = la donnée BRUTE, juste rendue lisible par DuckDB.
    Toute transformation métier (renommage de colonnes, filtrage de lignes,
    cast de types, calculs) appartient à la couche SILVER (dbt), PAS ici.

Convention de sortie : chaque source écrit sous data/bronze/<source_name>/,
puis `python -m extract.sync_to_minio` monte le tout vers s3://bronze/<source_name>/.

Note : le scraper de recettes (extract.recipes_scraper.*) n'hérite PAS de cette
classe. Il suit un pattern streaming (écriture directe MinIO, reprise sur erreur)
volontairement différent et documenté. Le standard couvre le cas batch majoritaire.
"""
from abc import ABC, abstractmethod
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")


class BronzeExtractor(ABC):
    """Contrat commun à tous les extracteurs Bronze de type batch."""

    source_name: str  # ex: "agribalyse" -> data/bronze/agribalyse/

    def __init__(self) -> None:
        if not getattr(self, "source_name", None):
            raise ValueError(
                f"{type(self).__name__} doit définir un attribut 'source_name'."
            )
        self.log = logging.getLogger(self.source_name)
        self.bronze_dir = Path("data/bronze") / self.source_name
        self.bronze_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def fetch(self) -> Path:
        """Télécharge la source brute TELLE QUELLE (aucune transformation).
        Retourne le chemin du fichier brut téléchargé."""

    @abstractmethod
    def normalize(self, raw_path: Path) -> Path:
        """Conversion de FORMAT uniquement, pour rendre le brut lisible par DuckDB.

        AUTORISÉ : .xls -> .csv, dézippage, changement d'encodage, aplatir un
                   en-tête multi-lignes en un en-tête simple.
        INTERDIT  : renommer des colonnes métier, filtrer des lignes, caster des
                   types, supprimer des doublons -> ça, c'est SILVER (dbt).

        Retourne le chemin du fichier (ou du dossier) produit dans self.bronze_dir.
        La valeur de retour est INDICATIVE : la source de vérité de ce qui part
        sur MinIO reste sync_to_minio.py (qui parcourt tout data/bronze/)."""

    @abstractmethod
    def validate(self, final_path: Path) -> None:
        """Garde-fou MINIMAL : fichier présent, non vide, lisible.
        Lève une exception si le contrat de base n'est pas respecté.
        (Ce n'est pas de la validation métier : juste 'l'extraction n'a pas échoué'.)"""

    def run(self) -> None:
        """Orchestration standard — NE PAS surcharger."""
        self.log.info("Démarrage ingestion %s", self.source_name)
        raw = self.fetch()
        final = self.normalize(raw)
        self.validate(final)
        self.log.info("✅ %s prêt : %s", self.source_name, final.name)
        self.log.info("→ Lance ensuite : python -m extract.sync_to_minio")
