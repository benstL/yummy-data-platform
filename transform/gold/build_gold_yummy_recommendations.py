from datetime import datetime, UTC
from pathlib import Path

import pandas as pd


SILVER_FOODCOM_DIR = Path("data/silver/foodcom")
GOLD_DIR           = Path("data/gold")
SENTIMENT_FILE     = GOLD_DIR / "gold_sentiment_scores.parquet"


def get_latest_file(directory: Path, pattern: str) -> Path:
    files = sorted(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No file found for pattern: {pattern}")
    return files[-1]


def normalize_series(series: pd.Series) -> pd.Series:
    """Min-max normalize a Series to [0, 1]. Returns all-zeros if constant."""
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(0.0, index=series.index)
    return (series - lo) / (hi - lo)


def build_yummy_score(
    df: pd.DataFrame,
    sentiment_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute the revised yummy_score using a Bayesian weighted rating and
    VADER sentiment percentile.

    Formula:
        yummy_score = 0.35 * weighted_rating_score
                    + 0.25 * (sentiment_percentile / 100)
                    + 0.20 * popularity_score
                    + 0.20 * simplicity_score
        scaled to 0-100.

    Args:
        df: Silver recipes DataFrame.
        sentiment_df: Gold sentiment scores with recipeid and sentiment_percentile.

    Returns:
        DataFrame with all score columns added and reviewcount==0 rows removed.
    """
    df = df.copy()

    # ── Filter: drop recipes with zero reviews ─────────────────────────────────
    n_before = len(df)
    df = df[df["reviewcount"] > 0].copy()
    n_after = len(df)
    print(f"[INFO] Filtered reviewcount==0: {n_before:,} → {n_after:,} recipes")

    # ── Bayesian weighted rating (IMDB formula) ────────────────────────────────
    C = df["aggregatedrating"].mean()                    # mean rating across all recipes
    m = df["reviewcount"].quantile(0.80)                 # popularity threshold
    print(f"[INFO] Bayesian params: C (mean rating)={C:.4f}, m (p80 review count)={m:.1f}")

    v = df["reviewcount"]
    R = df["aggregatedrating"]
    df["weighted_rating"] = ((v / (v + m)) * R + (m / (v + m)) * C).round(4)
    df["weighted_rating_score"] = normalize_series(df["weighted_rating"])

    # rating_score = weighted_rating_score (used as feature in clustering)
    df["rating_score"] = df["weighted_rating_score"]

    # ── Sentiment join ─────────────────────────────────────────────────────────
    df = df.merge(
        sentiment_df[["recipeid", "sentiment_percentile"]],
        on="recipeid",
        how="left",
    )
    # Recipes without reviews in the sentiment table → neutral 50
    n_missing_sent = df["sentiment_percentile"].isna().sum()
    if n_missing_sent:
        print(f"[INFO] {n_missing_sent:,} recipes without sentiment data — filled with 50")
    df["sentiment_percentile"] = df["sentiment_percentile"].fillna(50.0)

    # Bayesian shrinkage toward neutral (50) using the same m as the rating.
    # A 2-review recipe at percentile 99 → ~64; a 50-review recipe at 99 → ~95.
    # Use df["reviewcount"] directly — v has a pre-merge gapped index that would
    # misalign against the continuous index produced by the merge above.
    vc = df["reviewcount"]
    df["shrunk_sentiment"] = (
        (vc / (vc + m)) * df["sentiment_percentile"]
        + (m  / (vc + m)) * 50.0
    ).round(2)
    print(f"[INFO] Sentiment shrinkage: raw mean={df['sentiment_percentile'].mean():.2f}  "
          f"shrunk mean={df['shrunk_sentiment'].mean():.2f}")

    # ── Supporting scores ─────────────────────────────────────────────────────
    df["ingredient_count"] = (
        df["recipeingredientparts"]
        .fillna("")
        .apply(lambda x: len(str(x).split()))
    )
    df["popularity_score"] = normalize_series(df["reviewcount"])
    df["simplicity_score"] = 1 - normalize_series(df["totaltime"])

    # ── Final yummy_score (shrunk_sentiment replaces raw percentile) ──────────
    df["yummy_score"] = (
        0.35 * df["weighted_rating_score"]
        + 0.25 * (df["shrunk_sentiment"] / 100.0)
        + 0.20 * df["popularity_score"]
        + 0.20 * df["simplicity_score"]
    )
    df["yummy_score"] = (df["yummy_score"] * 100).round(2)

    return df


def main() -> None:
    print("[INFO] Building Gold YUMMY recommendations...")

    recipes_file = get_latest_file(SILVER_FOODCOM_DIR, "silver_recipes_*.parquet")
    print(f"[INFO] Reading recipes: {recipes_file}")
    recipes_df = pd.read_parquet(recipes_file)

    print(f"[INFO] Reading sentiment scores: {SENTIMENT_FILE}")
    sentiment_df = pd.read_parquet(SENTIMENT_FILE)

    gold_df = build_yummy_score(recipes_df, sentiment_df)

    columns_to_keep = [
        "recipeid",
        "name",
        "recipecategory",
        "recipeingredientparts",
        "recipeinstructions",
        "totaltime",
        "ingredient_count",
        "aggregatedrating",
        "reviewcount",
        "weighted_rating",          # Bayesian weighted rating value
        "sentiment_percentile",     # VADER percentile rank (raw)
        "shrunk_sentiment",         # sentiment shrunk toward 50 by review credibility
        "rating_score",             # normalised weighted_rating (for clustering)
        "popularity_score",
        "simplicity_score",
        "yummy_score",
    ]

    gold_df = gold_df[columns_to_keep].sort_values("yummy_score", ascending=False)
    gold_df["processed_at"] = datetime.now(UTC).isoformat()

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    output_file = GOLD_DIR / "gold_yummy_recommendations.parquet"
    gold_df.to_parquet(output_file, index=False)
    print(f"[INFO] Gold recommendations saved: {output_file}  ({len(gold_df):,} rows)")

    print("[INFO] Top 10 recommendations:")
    print(
        gold_df[["name", "weighted_rating", "reviewcount",
                 "sentiment_percentile", "shrunk_sentiment", "yummy_score"]]
        .head(10)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
