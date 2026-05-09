from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

import pandas as pd
from datetime import datetime, UTC
from pathlib import Path


URL = "https://www.eufic.org/en/explore-seasonal-fruit-and-vegetables-in-europe"


def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")

    driver = webdriver.Chrome(options=chrome_options)

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

                if country is not None:
                    info = {
                        "product_name": name,
                        "product_type": product_type,
                        "month": month,
                        "country": country,
                        "source": "EUFIC",
                        "extracted_at": datetime.now(UTC).isoformat()
                    }

                    data.append(info)

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

        fruits_data = scrape_data(
            driver=driver,
            tab_id="Fruit-tab",
            div_id="Fruit",
            product_type="fruit"
        )

        vegetables_data = scrape_data(
            driver=driver,
            tab_id="Vegetable-tab",
            div_id="Vegetable",
            product_type="vegetable"
        )

        all_data = fruits_data + vegetables_data

        df = pd.DataFrame(all_data)

        print(df.head())
        print(f"[INFO] Number of rows: {len(df)}")

        save_bronze(df)

        print("[INFO] EUFIC extraction completed.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()