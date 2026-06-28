"""
API V1.2 smoke tests — 1 test per new endpoint.

Requires the project data files to be present on disk (Gold + Silver parquets).
Run from the project root so that relative paths in api/main.py resolve correctly:

    pytest tests/test_api.py -v
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _assert_list_of_dicts(response, status: int = 200) -> list[dict]:
    assert response.status_code == status, response.text
    data = response.json()
    assert isinstance(data, list)
    return data


# ---------------------------------------------------------------------------
# GET /basket-recommendations
# ---------------------------------------------------------------------------

def test_basket_recommendations_with_basket():
    """Non-empty basket returns recipes ranked by yummy_score."""
    resp = client.get("/basket-recommendations?country=france&month=6&basket=tomato,garlic&limit=5")
    recipes = _assert_list_of_dicts(resp)
    assert len(recipes) <= 5
    # every returned recipe must have the extended columns
    for r in recipes:
        assert "recipeid" in r
        assert "yummy_score" in r
        assert "matched_ingredients" in r
        assert isinstance(r["matched_ingredients"], list)


def test_basket_recommendations_empty_basket_fallback():
    """Empty basket falls back to global top-N by yummy_score."""
    resp = client.get("/basket-recommendations?country=france&month=6&limit=5")
    recipes = _assert_list_of_dicts(resp)
    assert 1 <= len(recipes) <= 5
    scores = [r["yummy_score"] for r in recipes]
    assert scores == sorted(scores, reverse=True), "Results must be sorted by yummy_score desc"


def test_basket_recommendations_unknown_country_returns_404():
    """Unknown country propagates 404 from durability loader."""
    resp = client.get("/basket-recommendations?country=narnia&month=6&basket=tomato")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /seasonal-products
# ---------------------------------------------------------------------------

def test_seasonal_products_france_june():
    """France + June returns a non-empty list of {product_name, is_in_season}."""
    resp = client.get("/seasonal-products?country=france&month=6")
    rows = _assert_list_of_dicts(resp)
    assert len(rows) > 0
    for row in rows:
        assert "product_name" in row
        assert "is_in_season" in row


def test_seasonal_products_unknown_country_returns_404():
    """Unknown EUFIC country returns 404."""
    resp = client.get("/seasonal-products?country=narnia&month=6")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /faostat-staples
# ---------------------------------------------------------------------------

def test_faostat_staples_france():
    """France returns a ranked list of {product_name, production_value} without aggregates."""
    resp = client.get("/faostat-staples?country=france&top_n=10")
    rows = _assert_list_of_dicts(resp)
    assert len(rows) > 0
    assert len(rows) <= 10
    for row in rows:
        assert "product_name" in row
        assert "production_value" in row
    # aggregate categories must be excluded
    aggregate_patterns = ("primary", " total", ", total", "poultry", " meat", "equivalent", "oilcrop")
    for row in rows:
        name_lower = row["product_name"].lower()
        assert not any(p in name_lower for p in aggregate_patterns), (
            f"Aggregate product leaked into response: {row['product_name']}"
        )


def test_faostat_staples_unknown_country_returns_404():
    """Unknown FAOSTAT country returns 404."""
    resp = client.get("/faostat-staples?country=narnia")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /countries
# ---------------------------------------------------------------------------

def test_countries_returns_list_with_flags():
    """countries endpoint returns sorted list with eufic/faostat booleans."""
    resp = client.get("/countries")
    rows = _assert_list_of_dicts(resp)
    assert len(rows) > 0

    country_names = [r["country"] for r in rows]

    # list must be sorted
    assert country_names == sorted(country_names)

    for row in rows:
        assert "country" in row
        assert "eufic"   in row
        assert "faostat" in row
        assert isinstance(row["eufic"],   bool)
        assert isinstance(row["faostat"], bool)
        # at least one source must be true
        assert row["eufic"] or row["faostat"]

    # france must appear and have EUFIC + FAOSTAT data
    france = next((r for r in rows if r["country"] == "france"), None)
    assert france is not None, "'france' missing from /countries"
    assert france["eufic"]   is True
    assert france["faostat"] is True
