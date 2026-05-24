"""
Ingestion de la table CIQUAL 2025 (ANSES) -> couche Bronze.
Source du pilier "Nutrition" du Yummy Score.

Suit le standard BronzeExtractor : fetch -> normalize -> validate -> run.
normalize() convertit le .xls binaire legacy en .csv (un par onglet) SANS
renommer les colonnes : le renommage métier (alim_code -> ingredient_id, etc.)
appartient à la couche Silver (dbt), pas à Bronze.
"""
from pathlib import Path

import pandas as pd
import requests

from extract.base_extractor import BronzeExtractor

CIQUAL_URL = (
    "https://ciqual.anses.fr/cms/sites/default/files/inline-files/"
    "Table%20Ciqual%202025_FR_2025_11_03.xls"
)


class CiqualExtractor(BronzeExtractor):
    source_name = "ciqual"

    def fetch(self) -> Path:
        raw = self.bronze_dir / "TableCiqual2025.xls"
        self.log.info("Téléchargement de la table CIQUAL 2025...")
        r = requests.get(CIQUAL_URL, timeout=60)
        r.raise_for_status()
        raw.write_bytes(r.content)
        self.log.info("Téléchargé : %.1f Mo", raw.stat().st_size / (1024 * 1024))
        return raw

    def normalize(self, raw_path: Path) -> Path:
        # Conversion de FORMAT seulement : .xls legacy -> un .csv par onglet.
        # Moteur 'xlrd' OBLIGATOIRE pour ce format binaire ancien.
        # PAS de renommage de colonnes ici (-> Silver/dbt).
        feuilles = pd.read_excel(raw_path, sheet_name=None, engine="xlrd")
        for nom_feuille, df in feuilles.items():
            nom_propre = nom_feuille.strip().replace(" ", "_").lower()
            fichier_csv = self.bronze_dir / f"ciqual_{nom_propre}.csv"
            # Aplatir les en-têtes multi-lignes est une mise en forme de FORMAT,
            # pas une transformation métier : on garde, ça évite des colonnes cassées.
            df.columns = df.columns.str.replace(r"\s+", " ", regex=True).str.strip()
            df.to_csv(fichier_csv, index=False)
            self.log.info("Onglet '%s' -> %s", nom_feuille, fichier_csv.name)
        raw_path.unlink(missing_ok=True)
        return self.bronze_dir  # plusieurs CSV : on retourne le dossier source

    def validate(self, final_path: Path) -> None:
        csvs = list(self.bronze_dir.glob("ciqual_*.csv"))
        assert csvs, "Aucun CSV CIQUAL produit — conversion échouée"
        self.log.info("Validé : %d onglet(s) converti(s) en CSV", len(csvs))


if __name__ == "__main__":
    CiqualExtractor().run()
