"""
Shared pytest configuration: path setup, session-scoped DataFrame fixtures,
fixture-presence guard, and custom PASS/FAIL summary.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

# Make ml.* importable from any working directory
sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES_DIR = Path("data/tests/fixtures")
_REQUIRED_FILES = [
    "silver_recipes_test.parquet",
    "silver_reviews_test.parquet",
    "silver_seasonality_test.parquet",
    "silver_faostat_test.parquet",
]


def pytest_sessionstart(session) -> None:  # noqa: ARG001
    missing = [f for f in _REQUIRED_FILES if not (FIXTURES_DIR / f).exists()]
    if missing:
        pytest.exit(
            f"\nFixture files missing: {missing}\n"
            "Generate them first:\n"
            "    python tests/fixtures/generate_fixtures.py\n",
            returncode=4,
        )


# ---------------------------------------------------------------------------
# Session-scoped DataFrames — loaded once for the entire test run
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def recipes_df() -> pd.DataFrame:
    return pd.read_parquet(FIXTURES_DIR / "silver_recipes_test.parquet")


@pytest.fixture(scope="session")
def reviews_df() -> pd.DataFrame:
    return pd.read_parquet(FIXTURES_DIR / "silver_reviews_test.parquet")


@pytest.fixture(scope="session")
def eufic_df() -> pd.DataFrame:
    return pd.read_parquet(FIXTURES_DIR / "silver_seasonality_test.parquet")


@pytest.fixture(scope="session")
def faostat_df() -> pd.DataFrame:
    return pd.read_parquet(FIXTURES_DIR / "silver_faostat_test.parquet")


# ---------------------------------------------------------------------------
# Terminal summary
# ---------------------------------------------------------------------------

def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:  # noqa: ARG001
    passed  = len(terminalreporter.stats.get("passed",  []))
    failed  = len(terminalreporter.stats.get("failed",  []))
    errors  = len(terminalreporter.stats.get("error",   []))
    skipped = len(terminalreporter.stats.get("skipped", []))
    bar = "=" * 54
    verdict = "PASS" if exitstatus == 0 else "FAIL"
    print(f"\n{bar}")
    print(f"  YUMMY ML Tests  —  {verdict}")
    print(f"  Passed: {passed}  Failed: {failed}  Errors: {errors}  Skipped: {skipped}")
    print(f"{bar}")
