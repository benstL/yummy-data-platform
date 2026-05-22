"""
Extraction de la saisonnalité fruits/légumes par pays (EUFIC) -> Bronze local.

⚠️ Extract MANUEL one-shot : dépend de Selenium + Chrome, ne tourne PAS en CI
ni dans un DAG planifié. La saisonnalité évolue peu ; on re-scrape à la main
au besoin et on fige le CSV produit comme donnée de référence.
Installer la dépendance optionnelle : pip install -e ".[eufic]"
"""
from datetime import datetime, UTC
from pathlib import Path

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options


URL = "https://www.eufic.org/en/explore-seasonal-fruit-and-vegetables-in-europe"

# Garde-fou contre les classes CSS parasites du HTML EUFIC : si EUFIC ajoute
# une classe utilitaire (hidden, active...), on l'ignore au lieu de
# l'enregistrer comme un faux "mois" qui polluerait la saisonnalité.
VALID_MONTHS = {
    "jan", "feb", "mar", "apr", "may", "jun",
    "jul", "aug", "sep", "oct", "nov", "dec",
}


def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")

    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(10)  # laisse le JS rendre la grille fruits/légumes
    return driver


def scrape_data(driver, tab_id, div_id, product_type):
    tab = driver.find_element(By.ID, tab_id)
    tab.click()

    div = driver.find_element(By.ID, div_id)
    fvgrid_div = div.find_element(By.CLASS_NAME, "fvgrid")
    items = fvgrid_div.find_elements(By.TAG_NAME, "div")

    data = []

    for item in items:
        try:
            class_attribute_value = item.get_attribute("class")
            name = item.find_element(By.TAG_NAME, "strong").text.strip()

            months_and_countries = class_attribute_value.split(" ")[1:]

            for month_and_country in months_and_countries:
                month_country_split = month_and_country.split("-")

                month = month_country_split[0]
                country = (
                    month_country_split[1]
                    if len(month_country_split) > 1
                    else None
                )

                if month.lower() not in VALID_MONTHS:
                    continue  # classe CSS parasite, on ignore

                if country is not None:
                    data.append({
                        "product_name": name,
                        "product_type": product_type,
                        "month": month,
                        "country": country,
                        "source": "EUFIC",
                        "extracted_at": datetime.now(UTC).isoformat(),
                    })

        except Exception as error:
            print(f"[WARNING] Item skipped because of error: {error}")
            continue

    return data


def save_bronze(df):
    extraction_date = datetime.now(UTC).strftime("%Y%m%d")

    output_dir = Path("data/bronze/eufic")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"eufic_raw_{extraction_date}.csv"
    df.to_csv(output_file, index=False)

    print(f"[INFO] Bronze file saved: {output_file}")


def main():
    print("[INFO] Starting EUFIC extraction...")

    driver = init_driver()

    try:
        driver.get(URL)

        fruits_data = scrape_data(driver, "Fruit-tab", "Fruit", "fruit")
        vegetables_data = scrape_data(driver, "Vegetable-tab", "Vegetable", "vegetable")

        all_data = fruits_data + vegetables_data

        if not all_data:
            raise RuntimeError(
                "Aucune donnée extraite : la structure HTML d'EUFIC a "
                "probablement changé. Vérifie les ID de tabs et la classe fvgrid."
            )

        df = pd.DataFrame(all_data)
        print(df.head())
        print(f"[INFO] Number of rows: {len(df)}")

        save_bronze(df)
        print("[SUCCESS] EUFIC extraction completed.")
        print("[INFO] Lance ensuite : python -m extract.sync_to_minio")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()