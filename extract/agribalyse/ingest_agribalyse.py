"""
Ingestion AGRIBALYSE 3.1 (ADEME) — synthèse impacts environnementaux -> Bronze.
Source du pilier "Empreinte carbone" du Yummy Score (kg CO2 eq / kg produit).

Suit le standard BronzeExtractor : fetch -> normalize -> validate -> run.
La sélection/renommage des colonnes métier (product_name, co2_kg_per_kg) et le
typage des colonnes ont été DÉPLACÉS en Silver (dbt). Ici on se contente de
rendre le .xlsx lisible en .csv brut.
"""
from pathlib import Path

import pandas as pd
import requests

from extract.base_extractor import BronzeExtractor

AGRIBALYSE_XLSX = (
    "https://data.ademe.fr/data-fair/api/v1/datasets/"
    "agribalyse-31-synthese/metadata-attachments/"
    "AGRIBALYSE3.1.1_produits alimentaires - synthese.xlsx"
)


class AgribalyseExtractor(BronzeExtractor):
    source_name = "agribalyse"

    def fetch(self) -> Path:
        raw = self.bronze_dir / "synthese_raw.xlsx"
        r = requests.get(AGRIBALYSE_XLSX, timeout=120)
        r.raise_for_status()
        raw.write_bytes(r.content)
        self.log.info("Téléchargé : %.1f Mo", len(r.content) / 1e6)
        return raw

    def normalize(self, raw_path: Path) -> Path:
        # Conversion de FORMAT seulement : .xlsx -> .csv, en sautant les
        # lignes de titre ADEME (l'en-tête réel n'est pas en ligne 1).
        # CSV (et pas Parquet) car les colonnes brutes ADEME sont de type
        # mixte (ex. "Code AGB" mêle int et str) -> Parquet refuse, le CSV non.
        # Le typage propre se fera en Silver/dbt.
        df = pd.read_excel(raw_path, skiprows=2)
        df.columns = df.columns.str.replace(r"\s+", " ", regex=True).str.strip()
        final = self.bronze_dir / "agribalyse_synthese.csv"
        df.to_csv(final, index=False)
        raw_path.unlink(missing_ok=True)  # on ne garde que le csv (gain disque)
        return final

    def validate(self, final_path: Path) -> None:
        # Garde-fou minimal : l'extraction a-t-elle ramené un volume plausible ?
        df = pd.read_csv(final_path)
        assert len(df) > 2000, f"Trop peu de lignes ({len(df)}) — extraction suspecte"
        self.log.info("Validé : %d lignes brutes", len(df))


if __name__ == "__main__":
    AgribalyseExtractor().run()