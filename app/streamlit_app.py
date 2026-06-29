"""
YUMMY Streamlit UI — single-page seasonal recipe recommendation.
Reads Gold/Silver parquets directly (no API dependency).
Supports FR/EN language toggle and cluster-label filtering.
"""
from __future__ import annotations

import calendar
import html as _html_mod
import re
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st
import requests

from api.main import build_ingredient_buckets, load_ingredient_map_data
from ml.matching.ingredient_matcher import load_ingredient_taxonomy, map_ingredient_to_category

# ── Paths ─────────────────────────────────────────────────────────────────────
GOLD         = Path("data/gold")
SILVER_EUFIC = Path("data/silver/eufic")
SILVER_FAO   = Path("data/silver/faostat/qcl")
DURABILITY = GOLD / "gold_recipe_durability_scores"
# ── i18n ──────────────────────────────────────────────────────────────────────
TEXTS: dict[str, dict[str, str]] = {
    "fr": {
        "page_title":            "YUMMY — Recettes de Saison",
        "title":                 "🍽️ YUMMY",
        "subtitle":              "Découvrez des recettes qui correspondent à ce qui est frais et disponible dans votre région.",
        "country_label":         "🌍 Pays",
        "month_label":           "📅 Mois",
        "conf_eufic":            "Données saisonnières fiables (EUFIC)",
        "conf_faostat":          "Proxy de disponibilité agricole (FAOSTAT)",
        "conf_none":             "Données limitées — faible confiance",
        "conf_banner":           "{dot} **{msg}** — confiance de la source pour **{country}**",
        "basket_title":          "🛒 Panier d'Ingrédients",
        "basket_label":          "Ingrédients sélectionnés :",
        "seasonal_ingredients_label": "🥬 Ingrédients de saison",
        "complementary_ingredients_label": "🌍 Autres ingrédients disponibles",
        "api_base_label":        "URL de l'API",
        "api_base_help":         "Adresse de l'API YUMMY utilisée pour charger les ingrédients.",
        "basket_note_eufic_available": "Les ingrédients EUFIC sont priorisés. Les ingrédients complémentaires enrichissent la recette.",
        "basket_note_eufic_unavailable": "Aucune donnée EUFIC disponible pour ce pays/mois. Les ingrédients complémentaires sont la source principale.",
        "basket_note_complementary_primary": "Ingrédients complémentaires : source principale en l'absence de données EUFIC.",
        "cluster_filter_label":  "🏷️ Filtrer par type de recette",
        "btn_generate":          "🍽️ Générer les Recommandations",
        "warn_no_basket":        "⚠️ Sélectionnez au moins un ingrédient pour obtenir des recommandations.",
        "spinner":               "Recherche de vos meilleures correspondances saisonnières…",
        "spinner_initial":       "Chargement initial des données YUMMY…",
        "info_basket_fallback":  "Aucune recette trouvée pour votre panier (**{basket}**). Affichage du top {n} mondial.",
        "info_selection_fallback": "Aucune recette ne correspond à votre sélection exacte — affichage des meilleures recettes saisonnières.",
        "info_cluster_fallback": "Aucune recette ne correspond aux types sélectionnés. Filtre de type ignoré.",
        "success_matches":       "**{total:,}** recettes correspondent — top {n} par Score YUMMY.",
        "results_title":         "🏆 Top {n} Recommandations",
        "metric_yummy":          "Score YUMMY",
        "metric_durability":     "Durabilité",
        "metric_rating":         "Note",
        "metric_time":           "Temps",
        "metric_time_val":       "{t} min",
        "metric_time_na":        "—",
        "metric_cluster":        "Cluster",
        "explain_prefix":        "Recommandé car : ",
        "explain_popular":       "populaire ({n:,} avis)",
        "explain_time":          "prêt en {t} min",
        "explain_seasonal":      "correspond à : {names}",
        "explain_fallback_seasonal": "aucune sélection — top recettes de saison",
        "legend_green":          "🟢 Ingrédient(s) de saison (EUFIC)",
        "legend_yellow":         "🟡 Disponibilité agricole (FAOSTAT)",
        "debug_title":           "🔍 Debug — correspondance ingrédients",
        "debug_selected":        "selected_set",
        "debug_sample":          "Exemple matched_ingredients (5 recettes)",
        "debug_overlap":         "overlap",
        "debug_total":           "Recettes qualifiantes (panier sélectionné)",
    },
    "en": {
        "page_title":            "YUMMY — Seasonal Recipes",
        "title":                 "🍽️ YUMMY",
        "subtitle":              "Discover recipes that match what's fresh and available in your region right now.",
        "country_label":         "🌍 Country",
        "month_label":           "📅 Month",
        "conf_eufic":            "Reliable seasonal data (EUFIC)",
        "conf_faostat":          "Agricultural availability proxy (FAOSTAT)",
        "conf_none":             "Limited data — low confidence",
        "conf_banner":           "{dot} **{msg}** — data source confidence for **{country}**",
        "basket_title":          "🛒 Ingredient Basket",
        "basket_label":          "Selected ingredients:",
        "seasonal_ingredients_label": "🥬 Seasonal ingredients",
        "complementary_ingredients_label": "🌍 Available ingredients",
        "api_base_label":        "API base URL",
        "api_base_help":         "YUMMY API address used to load ingredient buckets.",
        "basket_note_eufic_available": "EUFIC ingredients are prioritized. Complementary ingredients enrich the recipe.",
        "basket_note_eufic_unavailable": "EUFIC seasonality data unavailable for this country/month. Recommendations use an approximation based on FAOSTAT/Food.com.",
        "basket_note_complementary_primary": "🍽️ Complete your recipe with FAOSTAT/Food.com ingredients.",
        "cluster_filter_label":  "🏷️ Filter by recipe type",
        "btn_generate":          "🍽️ Generate Recommendations",
        "warn_no_basket":        "⚠️ Select at least one ingredient to get personalised recommendations.",
        "spinner":               "Finding your best seasonal matches…",
        "spinner_initial":       "Loading YUMMY data for the first time…",
        "info_basket_fallback":  "No recipes found matching your basket (**{basket}**). Showing global top {n} instead.",
        "info_selection_fallback": "No recipe matches your exact selection — showing closest seasonal picks.",
        "info_cluster_fallback": "No recipes match the selected types. Type filter ignored.",
        "success_matches":       "**{total:,}** recipes match — showing top {n} by Yummy Score.",
        "results_title":         "🏆 Top {n} Recommendations",
        "metric_yummy":          "Yummy Score",
        "metric_durability":     "Durability",
        "metric_rating":         "Rating",
        "metric_time":           "Time",
        "metric_time_val":       "{t} min",
        "metric_time_na":        "—",
        "metric_cluster":        "Cluster",
        "explain_prefix":        "Recommended because: ",
        "explain_popular":       "popular ({n:,} reviews)",
        "explain_time":          "ready in {t} min",
        "explain_seasonal":      "matches: {names}",
        "explain_fallback_seasonal": "no selection — top seasonal picks",
        "legend_green":          "🟢 Seasonal ingredient(s) matched (EUFIC)",
        "legend_yellow":         "🟡 Agricultural availability match (FAOSTAT)",
        "debug_title":           "🔍 Debug — ingredient matching",
        "debug_selected":        "selected_set",
        "debug_sample":          "Sample matched_ingredients (5 recipes)",
        "debug_overlap":         "overlap",
        "debug_total":           "Qualifying recipes (selected basket)",
    },
}

MONTH_NAMES: dict[str, dict[int, str]] = {
    "en": {i: calendar.month_name[i] for i in range(1, 13)},
    "fr": {
        1: "Janvier",  2: "Février",   3: "Mars",      4: "Avril",
        5: "Mai",      6: "Juin",      7: "Juillet",   8: "Août",
        9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre",
    },
}

CONFIDENCE_DOT: dict[str, str] = {"eufic": "🟢", "faostat": "🟡", "none": "🔴"}

_FAO_AGGREGATE_PATTERNS = ("primary", " total", ", total", "poultry", " meat", "equivalent", "oilcrop")

FR_INGREDIENT_LABELS: dict[str, str] = {
    "apple": "pomme",
    "apricot": "abricot",
    "artichoke": "artichaut",
    "asparagus": "asperge",
    "aubergine": "aubergine",
    "banana": "banane",
    "bean": "haricot",
    "beef": "boeuf",
    "bell pepper": "poivron",
    "broccoli": "brocoli",
    "butter": "beurre",
    "cabbage": "chou",
    "carrot": "carotte",
    "cauliflower": "chou-fleur",
    "celery": "celeri",
    "cheese": "fromage",
    "chicken": "poulet",
    "cucumber": "concombre",
    "egg": "oeuf",
    "eggplant": "aubergine",
    "flour": "farine",
    "garlic": "ail",
    "green bean": "haricot vert",
    "leek": "poireau",
    "lettuce": "laitue",
    "milk": "lait",
    "mushroom": "champignon",
    "new potato": "pomme de terre nouvelle",
    "olive oil": "huile d'olive",
    "onion": "oignon",
    "pea": "petit pois",
    "pepper": "poivre",
    "pork": "porc",
    "potato": "pomme de terre",
    "radish": "radis",
    "redcurrant": "groseille",
    "rice": "riz",
    "salt": "sel",
    "spinach": "epinard",
    "strawberry": "fraise",
    "tomato": "tomate",
    "turnip": "navet",
    "zucchini": "courgette",
}

EUFIC_DISPLAY_MAP: dict[str, str] = {
    "czechrepublic": "Czech Republic",
    "unitedkingdom": "United Kingdom",
}

TOP_N = 10

# ── Cluster → badge CSS class mapping ─────────────────────────────────────────
CLUSTER_BADGE_CLASS: dict[str, str] = {
    "🏆 Top Rated":        "badge-top",
    "⭐ Crowd Favourite":  "badge-crowd",
    "⚡ Quick & Easy":     "badge-quick",
    "🌿 Seasonal & Local": "badge-seasonal",
    "🌍 Global Kitchen":   "badge-global",
}

# ── Global CSS ─────────────────────────────────────────────────────────────────
_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

/* ── Base font ──────────────────────────────────────────────────── */
html, body, [class*="css"], .stMarkdown, .stText,
button, input, select, textarea,
div[data-testid], .stSelectbox label, .stMultiSelect label {
    font-family: 'Poppins', -apple-system, BlinkMacSystemFont, sans-serif !important;
}

/* ── Content width ──────────────────────────────────────────────── */
.main .block-container {
    max-width: 880px !important;
    padding-top: 0.25rem !important;
    padding-bottom: 3rem !important;
}

/* ── Hero ───────────────────────────────────────────────────────── */
.yummy-hero {
    padding: 1.4rem 0 0.6rem;
}
.hero-title {
    font-size: 2.1rem;
    font-weight: 700;
    color: #F4A261;
    margin: 0 0 0.25rem;
    line-height: 1.15;
    letter-spacing: -0.01em;
}
.hero-sub {
    font-size: 0.92rem;
    color: #8B8F9B;
    margin: 0;
    line-height: 1.5;
}

/* ── Custom divider ─────────────────────────────────────────────── */
.yummy-divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.07);
    margin: 1.4rem 0;
}

/* ── Section label ──────────────────────────────────────────────── */
.section-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #6B7280;
    margin: 1.2rem 0 0.1rem;
    padding: 0;
}

/* ── Confidence banner ──────────────────────────────────────────── */
.conf-banner {
    padding: 0.7rem 1rem 0.7rem 1.1rem;
    border-radius: 8px;
    font-size: 0.875rem;
    line-height: 1.5;
    margin: 0.5rem 0 1.1rem;
}
.conf-eufic   { background: rgba(34,197,94,0.1);  border-left: 3px solid #22C55E; color: #86EFAC; }
.conf-faostat { background: rgba(234,179,8,0.1);  border-left: 3px solid #EAB308; color: #FDE047; }
.conf-none    { background: rgba(239,68,68,0.1);  border-left: 3px solid #EF4444; color: #FCA5A5; }

/* ── Recipe cards ───────────────────────────────────────────────── */
.recipe-card {
    background: #1A1A22;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 1.25rem 1.5rem 1.1rem;
    margin-bottom: 0.85rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease;
}
.recipe-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 22px rgba(0,0,0,0.45);
    border-color: rgba(244,162,97,0.28);
}
.card-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 1rem;
}
.recipe-name {
    font-size: 1.05rem;
    font-weight: 600;
    color: #F0EFE9;
    margin: 0 0 0.3rem;
    line-height: 1.3;
}
.recipe-cat {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 500;
    color: #6B7280;
    background: rgba(107,114,128,0.12);
    padding: 0.15rem 0.55rem;
    border-radius: 4px;
    letter-spacing: 0.03em;
}
.season-flag { font-size: 1.35rem; line-height: 1; flex-shrink: 0; margin-left: 0.8rem; }

/* KPI cards */
.kpi-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 1rem;
}
/* Metrics */
.metrics-row {
    display: grid;
    grid-template-columns: 1.5fr 1.5fr 1fr 1fr 1.8fr;
    gap: 0.6rem 1rem;
    margin-bottom: 0.85rem;
    align-items: start;
}
.metric-lbl {
    font-size: 0.66rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #555B6E;
    margin-bottom: 0.22rem;
}
.metric-val {
    font-size: 1.05rem;
    font-weight: 600;
    color: #E8E8E3;
    line-height: 1.2;
}
.metric-val.primary { color: #F4A261; }
.metric-val.durability {
    color: #22C55E;
}
.metric-sub { font-size: 0.72em; font-weight: 400; color: #6B7280; }

.durability-badge {
    font-size: 0.72rem;
    margin-left: 8px;
    color: #86EFAC;
    font-weight: 500;
}

/* Progress bar */
.prog-track {
    height: 3px;
    background: rgba(255,255,255,0.08);
    border-radius: 2px;
    margin-top: 0.35rem;
    overflow: hidden;
}
.prog-fill {
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(90deg, #F4A261 0%, #FBBF24 100%);
}

.prog-fill-durability {
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(
        90deg,
        #22C55E 0%,
        #86EFAC 100%
    );
}

/* Cluster badges */
.cluster-badge {
    display: inline-block;
    font-size: 0.74rem;
    font-weight: 600;
    padding: 0.22rem 0.65rem;
    border-radius: 20px;
    letter-spacing: 0.02em;
    margin-top: 0.15rem;
    white-space: nowrap;
}
.badge-top      { background: rgba(251,191,36,0.15);  color: #FCD34D; }
.badge-crowd    { background: rgba(96,165,250,0.15);  color: #93C5FD; }
.badge-quick    { background: rgba(52,211,153,0.15);  color: #6EE7B7; }
.badge-seasonal { background: rgba(45,212,191,0.15);  color: #5EEAD4; }
.badge-global   { background: rgba(167,139,250,0.15); color: #C4B5FD; }

/* Explainability */
.explain-line {
    font-size: 0.78rem;
    font-style: italic;
    color: #555B6E;
    line-height: 1.5;
    padding-top: 0.1rem;
    border-top: 1px solid rgba(255,255,255,0.05);
}

/* ── Streamlit widget tweaks ─────────────────────────────────────── */
div[data-testid="stButton"] > button[kind="primary"] {
    font-weight: 600 !important;
    letter-spacing: 0.03em;
    border-radius: 10px !important;
    padding: 0.65rem 1rem !important;
    font-size: 1rem !important;
}
/* Tighten multiselect tag */
span[data-baseweb="tag"] {
    border-radius: 6px !important;
    font-size: 0.8rem !important;
}
"""


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data
def load_yummy_recommendations() -> pd.DataFrame:
    """Load Gold Yummy recommendations."""
    return pd.read_parquet(
        GOLD / "gold_yummy_recommendations.parquet",
        columns=[
            "recipeid",
            "name",
            "recipecategory",
            "totaltime",
            "aggregatedrating",
            "reviewcount",
            "yummy_score",
        ],
    )


@st.cache_data
def load_durability_scores(country: str) -> pd.DataFrame:
    """Load durability scores for the selected country."""

    country_slug = country.lower().replace(" ", "_")
    country_dir = DURABILITY / f"durability_country={country_slug}"

    files = sorted(country_dir.glob("*.parquet"))

    if not files:
        return pd.DataFrame(
            columns=[
                "recipeid",
                "durability_month",
                "seasonality_score",
                "availability_score",
                "durability_score",
                "coverage_score",
            ]
        )

    return pd.read_parquet(
        files[-1],
        columns=[
            "recipeid",
            "durability_month",
            "seasonality_score",
            "availability_score",
            "durability_score",
            "coverage_score",
        ],
    )


@st.cache_data
def load_sentiment() -> pd.DataFrame:
    """Load Gold sentiment scores."""
    return pd.read_parquet(
        GOLD / "gold_sentiment_scores.parquet",
        columns=["recipeid", "sentiment_percentile"],
    )


@st.cache_data
def load_ingredient_map() -> pd.DataFrame:
    """Load Gold ingredient map."""
    return pd.read_parquet(
        GOLD / "gold_recipe_ingredient_map.parquet",
        columns=["recipeid", "matched_ingredients", "eufic_match_count", "faostat_match_count"],
    )


@st.cache_data
def load_clusters() -> pd.DataFrame:
    """Load Gold recipe clusters."""
    return pd.read_parquet(
        GOLD / "gold_recipe_clusters.parquet",
        columns=["recipeid", "cluster_label"],
    )


@st.cache_data
def load_eufic() -> pd.DataFrame:
    """Load the latest EUFIC Silver seasonality parquet."""
    files = sorted(SILVER_EUFIC.glob("silver_seasonality_*.parquet"))
    if not files:
        raise FileNotFoundError("No EUFIC silver parquet found.")
    if not files:
        return pd.DataFrame(columns=["product_name", "month_number", "country", "is_in_season"])

    try:
        return pd.read_parquet(
            files[-1],
            columns=["product_name", "month_number", "country", "is_in_season"],
        )
    except Exception:
        return pd.DataFrame(columns=["product_name", "month_number", "country", "is_in_season"])


@st.cache_data
def _load_faostat_raw() -> pd.DataFrame:
    """Load FAOSTAT Silver parquet with columns needed for country checks and staples."""
    files = sorted(SILVER_FAO.glob("silver_faostat_*.parquet"))
    if not files:
        raise FileNotFoundError("No FAOSTAT silver parquet found.")
    return pd.read_parquet(
        files[-1],
        columns=["country_name", "product_name", "year", "production_value"],
    )


@st.cache_data
def build_merged(country: str, month_number: int) -> pd.DataFrame:
    """Join Yummy recommendations with durability scores for selected country/month."""

    yummy = load_yummy_recommendations()

    durability = load_durability_scores(country)

    durability = durability[
        durability["durability_month"] == month_number
    ]

    merged = (
        yummy
        .merge(durability,          on="recipeid", how="left")
        .merge(load_clusters(),     on="recipeid", how="left")
        .merge(load_ingredient_map(), on="recipeid", how="left")
        .merge(load_sentiment(),    on="recipeid", how="left")
    )

    for col in [
        "seasonality_score",
        "availability_score",
        "durability_score",
        "coverage_score",
    ]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    return merged
# ── Country utilities ─────────────────────────────────────────────────────────

def _eufic_to_display(internal: str) -> str:
    """Convert an EUFIC internal country key to a human-readable display name."""
    return EUFIC_DISPLAY_MAP.get(internal, internal.title())


def _display_to_eufic(display: str) -> str:
    """Reverse-map a display name to the EUFIC internal key."""
    rev = {v: k for k, v in EUFIC_DISPLAY_MAP.items()}
    return rev.get(display, display.lower())


@st.cache_data
def get_eufic_display_countries() -> frozenset[str]:
    """Frozenset of display-name countries present in EUFIC."""
    return frozenset(_eufic_to_display(c) for c in load_eufic()["country"].unique())


@st.cache_data
def get_faostat_display_countries() -> frozenset[str]:
    """Frozenset of display-name countries present in FAOSTAT."""
    fao = _load_faostat_raw()
    return frozenset(c.title() for c in fao["country_name"].unique())


@st.cache_data
def get_country_options() -> list[str]:
    """Sorted list of display-name countries from EUFIC ∪ FAOSTAT."""
    return sorted(get_eufic_display_countries() | get_faostat_display_countries())


def confidence_level(country_display: str) -> str:
    """Return 'eufic', 'faostat', or 'none' reflecting data availability for a country."""
    if country_display in get_eufic_display_countries():
        return "eufic"
    if country_display in get_faostat_display_countries():
        return "faostat"
    return "none"


# ── Basket helpers ─────────────────────────────────────────────────────────────

@st.cache_data
def get_seasonal_products(country_display: str, month_number: int) -> list[str]:
    """Return sorted EUFIC in-season product names for the given country and month."""
    eufic    = load_eufic()
    internal = _display_to_eufic(country_display)
    mask = (
        (eufic["country"] == internal) &
        (eufic["month_number"] == month_number) &
        (eufic["is_in_season"])
    )
    return sorted(eufic.loc[mask, "product_name"].unique().tolist())


@st.cache_data
def get_faostat_staples(country_display: str, top_n: int = 15) -> list[str]:
    """
    Return top-N specific agricultural products for a country by production value
    (latest available year).  FAO aggregate categories are excluded.
    """
    fao = _load_faostat_raw()
    country_key = country_display.lower()
    country_df  = fao[fao["country_name"] == country_key]
    if country_df.empty:
        return []

    latest   = country_df["year"].max()
    recent   = country_df[country_df["year"] == latest]
    specific = recent[
        ~recent["product_name"].apply(
            lambda n: any(p in n.lower() for p in _FAO_AGGREGATE_PATTERNS)
        )
    ]
    return (
        specific
        .sort_values("production_value", ascending=False)
        .head(top_n)["product_name"]
        .tolist()
    )


@st.cache_data
def get_cluster_labels() -> list[str]:
    """Return sorted list of distinct cluster labels from the Gold clusters parquet."""
    return sorted(load_clusters()["cluster_label"].dropna().unique().tolist())


# ── Ingredient matching ────────────────────────────────────────────────────────

def _to_ingredient_set(value: Any) -> set[str]:
    """Safely convert a matched_ingredients value (array | None | NaN) to a set."""
    if value is None or isinstance(value, float):
        return set()
    try:
        return set(value)
    except TypeError:
        return set()


def _normalize_option_name(value: str) -> str:
    """Normalise ingredient display names for comparison."""
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"\s+", " ", value.strip().lower())
    cleaned = cleaned.replace("(", " ").replace(")", " ").strip()
    if cleaned.endswith("ies") and len(cleaned) > 4:
        cleaned = cleaned[:-3] + "y"
    elif cleaned.endswith("oes") and len(cleaned) > 4:
        cleaned = cleaned[:-2]
    elif cleaned.endswith("s") and len(cleaned) > 4 and not cleaned.endswith(("ss", "us", "is", "os", "as")):
        cleaned = cleaned[:-1]
    return cleaned


def _unique_options_by_normalized_name(options: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in options:
        normalized = _normalize_option_name(item)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(item)
    return output


def ingredient_display_name(name: str, lang: str) -> str:
    """Return the UI label for an ingredient while keeping its raw value internal."""
    if lang != "fr":
        return name

    normalized = _normalize_option_name(name)
    return FR_INGREDIENT_LABELS.get(normalized, name)


SEASONAL_PRODUCE_CATEGORIES = frozenset({"fruit", "vegetable"})


def _ingredient_name(item: Any) -> str:
    """Return the display name from either API v2 objects or legacy strings."""
    if isinstance(item, dict):
        return str(item.get("name") or "").strip()
    return str(item or "").strip()


def _ingredient_category(item: Any, taxonomy: Mapping[str, str]) -> str:
    """Return the business category for API v2 objects or legacy strings."""
    if isinstance(item, dict) and item.get("category"):
        return str(item["category"]).strip().lower()
    name = _ingredient_name(item)
    return map_ingredient_to_category(name, taxonomy) if name else "other"


def _is_seasonal_produce(item: Any, taxonomy: Mapping[str, str]) -> bool:
    return _ingredient_category(item, taxonomy) in SEASONAL_PRODUCE_CATEGORIES


def build_business_ingredient_options(
    eufic_items: list[str],
    faostat_items: list[str],
    ingredient_buckets: dict[str, Any],
    taxonomy: Mapping[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """Build mutually exclusive seasonal and complementary ingredient lists.

    Business rules:
    - seasonal options are only EUFIC fruit/vegetable products for the selected
      country and month;
    - API/local bucket produce is not promoted to seasonal, because EUFIC is the
      reference for seasonality;
    - complementary options never repeat a seasonal EUFIC product;
    - FAOSTAT is a fallback source and may add non-duplicated products.
    """
    taxonomy = taxonomy or load_ingredient_taxonomy()

    seasonal_options = _unique_options_by_normalized_name([
        item for item in eufic_items if _is_seasonal_produce(item, taxonomy)
    ])
    seasonal_norm = {_normalize_option_name(item) for item in seasonal_options}

    complementary_candidates: list[str] = []

    # API/local complementary buckets can contain legacy mixed ingredients.
    # Keep only non-produce here; FAOSTAT below is the explicit fallback path for
    # produce missing from the EUFIC seasonal list.
    for item in ingredient_buckets.get("complementary_ingredients", []):
        name = _ingredient_name(item)
        if not name or _normalize_option_name(name) in seasonal_norm:
            continue
        if not _is_seasonal_produce(item, taxonomy):
            complementary_candidates.append(name)

    # FAOSTAT complements the basket, but never duplicates EUFIC seasonal items.
    for item in faostat_items:
        name = _ingredient_name(item)
        if name and _normalize_option_name(name) not in seasonal_norm:
            complementary_candidates.append(name)

    complementary_options = _unique_options_by_normalized_name(complementary_candidates)
    return seasonal_options, complementary_options


@st.cache_data
def fetch_ingredient_buckets_v2(api_base: str = "http://127.0.0.1:8000") -> dict:
    """Try to fetch structured ingredient buckets from the API v2 endpoint.

    Returns the full payload from `/ingredient-buckets/v2` if successful.
    On failure, returns an empty dict so callers can fallback to local Gold.
    """
    try:
        url = api_base.rstrip("/") + "/ingredient-buckets/v2"
        resp = requests.get(url, timeout=1.0)
        resp.raise_for_status()
        payload = resp.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


@st.cache_data
def load_ingredient_buckets_from_api(api_base: str) -> tuple[dict[str, Any], bool]:
    """Load ingredient buckets from API v2 and indicate whether API was used."""
    payload = fetch_ingredient_buckets_v2(api_base)
    if payload:
        return payload, True
    buckets = build_ingredient_buckets(load_ingredient_map_data())
    return {
        "seasonal_ingredients": buckets["seasonal_ingredients"],
        "complementary_ingredients": buckets["complementary_ingredients"],
        "seasonality_available": False,
        "seasonality_source": None,
        "complementary_source": "FAOSTAT/Food.com",
    }, False


def _ingredient_hits(ingredients: set[str], basket_set: set[str]) -> set[str]:
    """
    Return the basket terms that match this recipe's ingredients.

    Uses substring matching so EUFIC term "aubergine" correctly matches the
    FAOSTAT term "eggplants (aubergines)" stored in matched_ingredients.
    Matching is bidirectional: basket_term ⊂ ingredient OR ingredient ⊂ basket_term.
    """
    hits: set[str] = set()
    for b in basket_set:
        for i in ingredients:
            if b in i or i in b:
                hits.add(b)
                break
    return hits


def _recipe_matches(ingredients_raw: Any, basket_set: set[str]) -> bool:
    """Return True if the recipe has ≥1 ingredient matching the basket (substring-aware)."""
    return bool(_ingredient_hits(_to_ingredient_set(ingredients_raw), basket_set))


# ── Recipe filtering ───────────────────────────────────────────────────────────

def filter_by_basket(
    merged: pd.DataFrame,
    basket: list[str],
    fallback_basket: list[str] | None = None,
) -> tuple[pd.DataFrame, bool, bool]:
    """
    Filter recipes against the selected basket using substring-aware matching.

    Tier 1 — exact selection: recipes whose matched_ingredients overlap ``basket``.
    Tier 2 — seasonal fallback: if tier 1 is empty and ``fallback_basket`` is
              provided, retry with the full seasonal product set.
    Tier 3 — global top: if both tiers are empty, return the global top recipes.

    Returns:
        (results_df, is_global_fallback, is_selection_fallback)
    """
    basket_set = set(basket)
    mask = merged["matched_ingredients"].apply(
        lambda v: _recipe_matches(v, basket_set)
    )
    matched = merged[mask].sort_values("yummy_score", ascending=False)

    if not matched.empty:
        return matched, False, False

    if fallback_basket:
        fb_set  = set(fallback_basket)
        fb_mask = merged["matched_ingredients"].apply(
            lambda v: _recipe_matches(v, fb_set)
        )
        fb_matched = merged[fb_mask].sort_values("yummy_score", ascending=False)
        if not fb_matched.empty:
            return fb_matched, False, True

    return merged.sort_values("yummy_score", ascending=False), True, False


def apply_cluster_filter(
    df: pd.DataFrame, selected_clusters: list[str]
) -> tuple[pd.DataFrame, bool]:
    """
    Restrict df to rows whose cluster_label is in selected_clusters.

    Returns:
        (filtered_df, cluster_ignored) — cluster_ignored=True when the filter
        would produce an empty result and has been skipped.
    """
    if not selected_clusters:
        return df, False
    filtered = df[df["cluster_label"].isin(selected_clusters)]
    if filtered.empty:
        return df, True
    return filtered, False


# ── Display helpers ────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    """HTML-escape a string to prevent injection in injected markup."""
    return _html_mod.escape(str(s))


def _md_strong(s: str) -> str:
    """Convert **bold** markdown tokens to <strong> for use inside injected HTML."""
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)


def inject_css() -> None:
    """Inject the global YUMMY CSS into the Streamlit page (call once at app start)."""
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


def _hr() -> None:
    """Render a custom thin horizontal divider."""
    st.markdown('<hr class="yummy-divider">', unsafe_allow_html=True)


def _section_head(text: str) -> None:
    """Render an uppercase section label above a widget group."""
    st.markdown(f'<p class="section-label">{_esc(text)}</p>', unsafe_allow_html=True)


def render_confidence_banner(
    level: str, dot: str, msg: str, country: str, texts: dict[str, str]
) -> None:
    """Render the data-source confidence pill with per-level colour tint."""
    raw     = texts["conf_banner"].format(dot=dot, msg=msg, country=country)
    content = _md_strong(raw)
    st.markdown(
        f'<div class="conf-banner conf-{level}">{content}</div>',
        unsafe_allow_html=True,
    )


# ── Season flag ────────────────────────────────────────────────────────────────

def _season_flag(row: pd.Series, basket_set: set[str], country_in_eufic: bool) -> str:
    """Return 🟢, 🟡, or '' depending on seasonal ingredient coverage."""
    ing = _to_ingredient_set(row.get("matched_ingredients"))
    if _ingredient_hits(ing, basket_set):
        return "🟢"
    if not country_in_eufic and (row.get("faostat_match_count") or 0) > 0:
        return "🟡"
    return ""


# ── Card renderer ──────────────────────────────────────────────────────────────

def render_card(
    row: pd.Series,
    rank : int,
    basket_set: set[str],
    country_in_eufic: bool,
    texts: dict[str, str],
    fallback_mode: bool = False,
) -> None:
    """
    Render a single recipe recommendation card as injected HTML.

    Args:
        fallback_mode: When True the results came from the seasonal-set fallback
                       (user's exact selection yielded 0 hits). The explainability
                       line uses the fallback label rather than inventing matches.
    """
    rating     = row.get("aggregatedrating") or 0.0
    totaltime  = int(row.get("totaltime") or 0)
    reviews    = int(row.get("reviewcount") or 0)
    yummy      = float(row.get("yummy_score") or 0.0)
    durability = float(row.get("durability_score") or 0.0)
    if durability >= 80:
        durability_label = "🌱 Très durable"
    elif durability >= 60:
        durability_label = "🌿 Durable"
    elif durability >= 40:
        durability_label = "🟡 Moyen"
    else:
        durability_label = "🔴 Faible"
    label      = row.get("cluster_label") or ""
    flag       = _season_flag(row, basket_set, country_in_eufic)
    ing        = _to_ingredient_set(row.get("matched_ingredients"))
    hits       = set() if fallback_mode else _ingredient_hits(ing, basket_set)

    badge_cls = CLUSTER_BADGE_CLASS.get(label, "badge-global")
    name_h    = _esc(str(row["name"]).title())
    cat_h     = _esc(str(row.get("recipecategory") or "").title())

    rank_badge = ""

    if rank == 1:
        rank_badge = "🥇 "
    elif rank == 2:
        rank_badge = "🥈 "
    elif rank == 3:
        rank_badge = "🥉 "


    # ── Explainability text ───────────────────────────────────────────────────
    parts: list[str] = []
    if reviews:
        parts.append(texts["explain_popular"].format(n=reviews))
    if totaltime:
        parts.append(texts["explain_time"].format(t=totaltime))
    if fallback_mode:
        parts.append(texts["explain_fallback_seasonal"])
    elif hits:
        parts.append(texts["explain_seasonal"].format(names=", ".join(sorted(hits))))
    explain = (_esc(texts["explain_prefix"] + ", ".join(parts) + ".")) if parts else ""

    # ── Subcomponents ─────────────────────────────────────────────────────────
    flag_html    = f'<span class="season-flag">{flag}</span>' if flag else ""
    cat_html     = f'<span class="recipe-cat">{cat_h}</span>' if cat_h else ""
    rating_str   = f"{rating:.1f}/5" if rating else texts["metric_time_na"]
    time_str     = texts["metric_time_val"].format(t=totaltime) if totaltime else texts["metric_time_na"]
    explain_html = (
        f'<div class="explain-line" style="margin-top:0.75rem">{explain}</div>'
        if explain else ""
    )

    html = f"""
<div class="recipe-card">
  <div class="card-top">
    <div>
      <div class="recipe-name">{rank_badge}{name_h}</div>
      {cat_html}
    </div>
    {flag_html}
  </div>
  <div class="metrics-row">
    <div class="metric-box">
      <div class="metric-lbl">{_esc(texts['metric_yummy'])}</div>
      <div class="metric-val primary">{yummy:.1f}<span class="metric-sub">/100</span></div>
      <div class="prog-track">
        <div class="prog-fill" style="width:{min(yummy, 100):.1f}%"></div>
      </div>
    </div>
    <div class="metric-box">
      <div class="metric-lbl">{_esc(texts['metric_durability'])}</div>
      <div class="metric-val durability">
        {durability:.1f}
        <span class="metric-sub">/100</span>
        <span class="durability-badge">{durability_label}</span>
      </div>
      <div class="prog-track">
        <div class="prog-fill-durability" style="width:{min(durability, 100):.1f}%"></div>
      </div>
    </div>
    <div class="metric-box">
      <div class="metric-lbl">{_esc(texts['metric_rating'])}</div>
      <div class="metric-val">{rating_str}</div>
    </div>
    <div class="metric-box">
      <div class="metric-lbl">{_esc(texts['metric_time'])}</div>
      <div class="metric-val">{time_str}</div>
    </div>
    <div class="metric-box">
      <div class="metric-lbl">{_esc(texts['metric_cluster'])}</div>
      <div style="margin-top:0.2rem">
        <span class="cluster-badge {badge_cls}">{_esc(label)}</span>
      </div>
    </div>
  </div>
  {explain_html}
</div>"""

    st.markdown(html, unsafe_allow_html=True)


# ── Main UI ───────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="YUMMY — Seasonal Recipes",
        page_icon="🍽️",
        layout="wide",
    )
    inject_css()

    # ── Language toggle (sidebar) ──────────────────────────────────────────────
    with st.sidebar:
        lang: str = st.selectbox(
            "Langue / Language",
            options=["fr", "en"],
            format_func=lambda x: "🇫🇷 Français" if x == "fr" else "🇬🇧 English",
            label_visibility="visible",
        )
        st.markdown("### API configuration")
        api_base = st.text_input(
            TEXTS[lang]["api_base_label"],
            value="http://127.0.0.1:8000",
            help=TEXTS[lang]["api_base_help"],
            label_visibility="visible",
        )

    texts       = TEXTS[lang]
    month_names = MONTH_NAMES[lang]

    # ── Hero ───────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="yummy-hero">'
        f'<h1 class="hero-title">{_esc(texts["title"])}</h1>'
        f'<p class="hero-sub">{_esc(texts["subtitle"])}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )
    _hr()

    # ── 1. Context ─────────────────────────────────────────────────────────────
    _section_head("📍 " + ("Contexte" if lang == "fr" else "Context"))
    countries   = get_country_options()
    default_idx = countries.index("France") if "France" in countries else 0

    col_country, col_month = st.columns(2)
    with col_country:
        country = st.selectbox(
            texts["country_label"], options=countries, index=default_idx
        )
    with col_month:
        month_num = st.selectbox(
            texts["month_label"],
            options=list(month_names.keys()),
            format_func=lambda x: month_names[x],
            index=5,
        )

    # ── 2. Confidence banner ────────────────────────────────────────────────────
    level = confidence_level(country)
    render_confidence_banner(
        level, CONFIDENCE_DOT[level], texts[f"conf_{level}"], country, texts
    )

    # ── 3. Basket ──────────────────────────────────────────────────────────────
    _section_head(texts["basket_title"])

    eufic_items   = get_seasonal_products(country, month_num)
    faostat_items = get_faostat_staples(country)

    # Try to fetch structured buckets from a running API (v2). If the API is
    # unreachable, fall back to reading the local Gold parquet as before.
    ingredient_buckets, using_api = load_ingredient_buckets_from_api(api_base)
    seasonal_options, complementary_options = build_business_ingredient_options(
        eufic_items=eufic_items,
        faostat_items=faostat_items,
        ingredient_buckets=ingredient_buckets,
    )

    if seasonal_options and complementary_options:
        caption = (
            f"🟢 **{len(seasonal_options)}** "
            + ("en saison (EUFIC)" if lang == "fr" else "in-season (EUFIC)")
            + f" + 🟡 **{len(complementary_options)}** "
            + ("compléments" if lang == "fr" else "complements")
            + f" — **{country}**, **{month_names[month_num]}**"
        )
    elif seasonal_options:
        caption = (
            f"🟢 {len(seasonal_options)} "
            + ("produits de saison (EUFIC)" if lang == "fr" else "in-season products (EUFIC)")
            + f" — **{country}**, **{month_names[month_num]}**"
        )
    elif complementary_options:
        caption = (
            f"🟡 {len(complementary_options)} "
            + ("compléments disponibles" if lang == "fr" else "available complements")
            + " — "
            + ("aucune donnée EUFIC disponible" if lang == "fr" else "no EUFIC seasonal data")
        )
    else:
        caption = "⚠️ " + ("Aucune donnée d'ingrédient disponible." if lang == "fr" else "No ingredient data available.")

    st.caption(caption)

    if seasonal_options or complementary_options:
        seasonality_available = bool(seasonal_options)
        if using_api:
            source_caption = (
                "Seasonal from EUFIC + complementary from API v2"
                if seasonality_available and lang == "en"
                else "Complementary from API v2"
                if lang == "en"
                else "Complémentaires depuis API v2"
            )
        else:
            source_caption = (
                "Seasonal from EUFIC + complementary from local Gold fallback"
                if seasonality_available and lang == "en"
                else "Complementary from local Gold fallback"
                if lang == "en"
                else "Complémentaires depuis le fallback local Gold"
            )
        st.caption(
            f"{source_caption} — {len(seasonal_options)} seasonal, "
            f"{len(complementary_options)} complementary"
        )
        if seasonal_options:
            st.caption(texts["basket_note_eufic_available"])
            col_seasonal, col_complementary = st.columns(2)
            with col_seasonal:
                selected_seasonal = st.multiselect(
                    texts["seasonal_ingredients_label"],
                    options=seasonal_options,
                    default=[],
                    format_func=lambda item: ingredient_display_name(item, lang),
                )
            with col_complementary:
                selected_complementary = st.multiselect(
                    texts["complementary_ingredients_label"],
                    options=complementary_options,
                    default=[],
                    format_func=lambda item: ingredient_display_name(item, lang),
                )
        else:
            st.warning(texts["basket_note_eufic_unavailable"])
            selected_seasonal = []
            st.caption(texts["basket_note_complementary_primary"])
            selected_complementary = st.multiselect(
                texts["complementary_ingredients_label"],
                options=complementary_options,
                default=[],
                format_func=lambda item: ingredient_display_name(item, lang),
            )
        basket = list(dict.fromkeys(selected_seasonal + selected_complementary))
    else:
        st.warning(
            "Aucune donnée disponible pour ce pays." if lang == "fr"
            else f"No ingredient data available for {country}."
        )
        basket = []

    seasonal_all = seasonal_options

    # ── Cluster filter ──────────────────────────────────────────────────────────
    _section_head(texts["cluster_filter_label"])
    all_cluster_labels  = get_cluster_labels()
    selected_clusters: list[str] = st.multiselect(
        texts["cluster_filter_label"],
        options=all_cluster_labels,
        default=all_cluster_labels,
        label_visibility="collapsed",
    )

    # ── 4. Generate ─────────────────────────────────────────────────────────────
    _hr()
    if "show_results" not in st.session_state:
        st.session_state.show_results = False

    if st.button(texts["btn_generate"], type="primary", use_container_width=True):
        st.session_state.show_results = True
        merged_key = (country, month_num)
        if st.session_state.get("merged_key") != merged_key:
            with st.spinner(texts["spinner_initial"]):
                st.session_state.merged = build_merged(country, month_num)
                st.session_state.merged_key = merged_key

    if not st.session_state.show_results:
        return

    if not basket:
        st.warning(texts["warn_no_basket"])
        st.stop()

    # ── 5. Filter ───────────────────────────────────────────────────────────────
    with st.spinner(texts["spinner"]):
        merged_key = (country, month_num)
        if st.session_state.get("merged_key") != merged_key:
            st.session_state.merged = build_merged(country, month_num)
            st.session_state.merged_key = merged_key
        merged = st.session_state.merged
        basket_results, is_global_fallback, is_selection_fallback = filter_by_basket(
            merged, basket, fallback_basket=seasonal_all
        )

    if is_global_fallback:
        st.info(texts["info_basket_fallback"].format(basket=", ".join(basket), n=TOP_N))
    elif is_selection_fallback:
        st.info(texts["info_selection_fallback"])
    else:
        total_matches = len(basket_results)
        st.success(texts["success_matches"].format(
            total=total_matches, n=min(total_matches, TOP_N)
        ))

    cluster_results, cluster_ignored = apply_cluster_filter(basket_results, selected_clusters)
    if cluster_ignored:
        st.info(texts["info_cluster_fallback"])



    max_time = st.slider(
        "⏱️ Temps maximum de préparation",
        min_value=10,
        max_value=180,
        value=60,
        step=5
    )

    cluster_results = cluster_results[
        cluster_results["totaltime"].fillna(999) <= max_time
    ]

    sort_mode = st.radio(
        "📌 Trier les recommandations par",
        [
            "Score Yummy",
            "Score Durabilité",
            "Meilleur compromis"
        ],
        horizontal=True,
    )   

    if sort_mode == "Score Yummy":
        cluster_results = cluster_results.sort_values("yummy_score", ascending=False)

    elif sort_mode == "Score Durabilité":
        cluster_results = cluster_results.sort_values("durability_score", ascending=False)

    else:
        cluster_results = cluster_results.assign(
            combined_score=(
                0.6 * cluster_results["yummy_score"]
                + 0.4 * cluster_results["durability_score"]
            )
        ).sort_values("combined_score", ascending=False)

    results = cluster_results.head(TOP_N)

    st.divider()
    st.subheader("📊 Aperçu des résultats")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("🍽️ Recettes", len(results))

    with col2:
        st.metric(
            "⭐ Score Yummy Moyen",
            f"{results['yummy_score'].mean():.1f}"
        )

    with col3:
        st.metric(
            "🌍 Score Durabilité Moyen",
            f"{results['durability_score'].mean():.1f}"
        )

    with col4:
        st.metric(
            "⏱️ Temps moyen",
            f"{results['totaltime'].mean():.0f} min"
        )
    
    st.divider()

    with st.expander("  Comprendre le Score Yummy"):
        st.markdown(""" 
Le **Score Yummy** classe les recettes selon les données réellement disponibles dans cette version.

Il repose principalement sur :

- ⭐ **rating_score** : qualité perçue via la note moyenne ;
- 🗣️ **popularity_score** : popularité via le nombre d'avis ;
- ⏱️ **simplicity_score** : simplicité, notamment liée au temps de préparation ;
- 💬 **sentiment_percentile** et **shrunk_sentiment** : satisfaction estimée à partir des avis utilisateurs.

Les dimensions nutritionnelles, carbone et saisonnalité sont prévues comme évolutions du score durable cible.
""")

    with st.expander("🌍 Comprendre le Score de Durabilité"):
        st.markdown("""
### Comment est calculé le score ?

Le score de durabilité repose sur :

- 🥕 la saisonnalité des ingrédients (EUFIC)
- 🌾 la disponibilité agricole (FAOSTAT)

Pour chaque ingrédient :

Durability Score =
75 % saisonnalité
+
25 % disponibilité agricole

Le score final de la recette correspond à la moyenne des scores des ingrédients reconnus.

Un bonus est ajouté lorsque plus de 2/3 des ingrédients reconnus possèdent un score positif.
""")

    # ── 6. Results ──────────────────────────────────────────────────────────────
    country_in_eufic = country in get_eufic_display_countries()
    basket_set       = set(basket)

    st.caption(f"{texts['legend_green']}   {texts['legend_yellow']}")
    st.markdown(
        f'<p style="font-size:1.15rem;font-weight:600;color:#E8E8E3;margin:0.6rem 0 0.8rem">'
        f'{_esc(texts["results_title"].format(n=len(results)))}</p>',
        unsafe_allow_html=True,
        )

    for rank, (_, row) in enumerate(results.iterrows(), start=1):
    
        render_card(
            row,
            rank,
            basket_set,
            country_in_eufic,
            texts,
            fallback_mode=is_selection_fallback
        )

        with st.expander("📖 Détails de la recette"):

            st.markdown("### 🌍 Durabilité")

            st.write(
                f"🌱 Saisonnalité : {row.get('seasonality_score',0):.1f}/100"
            )

            st.write(
                f"🌾 Disponibilité agricole : {row.get('availability_score',0):.1f}/100"
            )

            st.write(
                f"🎯 Couverture : {row.get('coverage_score',0):.1f}/100"
            )

            st.divider()

            st.markdown("### 🧺 Ingrédients reconnus")

            ingredients = list(row["matched_ingredients"])

            for ingredient in ingredients:
                st.write(f"• {ingredient}")

        st.divider()
          
    # ── Debug expander ──────────────────────────────────────────────────────────
    with st.expander(texts["debug_title"], expanded=False):
        st.write(f"**{texts['debug_selected']}:**", basket_set)
        st.write(f"**{texts['debug_sample']}:**")
        for _, r in merged.head(5).iterrows():
            ing_set = _to_ingredient_set(r.get("matched_ingredients"))
            overlap = _ingredient_hits(ing_set, basket_set)
            st.write(
                f"Recipe `{r['recipeid']}`: `{list(ing_set)[:6]}` "
                f"→ **{texts['debug_overlap']}**: `{overlap}`"
            )
        qualifying = int(
            merged["matched_ingredients"]
            .apply(lambda v: _recipe_matches(v, basket_set))
            .sum()
        )
        st.write(f"**{texts['debug_total']}:** {qualifying:,}")

if __name__ == "__main__":
    main()
