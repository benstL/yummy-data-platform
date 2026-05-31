from datetime import datetime, UTC
from pathlib import Path

import pandas as pd
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


SILVER_FOODCOM_DIR = Path("data/silver/foodcom")
GOLD_DIR = Path("data/gold")
GOLD_OUTPUT = GOLD_DIR / "gold_sentiment_scores.parquet"


def get_latest_reviews_file() -> Path:
    """Return the most recent silver reviews parquet file."""
    files = sorted(SILVER_FOODCOM_DIR.glob("silver_reviews_*.parquet"))

    if not files:
        raise FileNotFoundError(
            f"No silver reviews parquet found in {SILVER_FOODCOM_DIR}"
        )

    return files[-1]


def compound_to_score(compound: float) -> float:
    """Map a VADER compound value [-1, 1] to a sentiment score [0, 100].

    Neutral text (compound=0) maps to 50. Missing/empty reviews default to 50
    before this function is called.
    """
    return round((compound + 1) / 2 * 100, 2)


def analyze_sentiment(review: str, analyzer: SentimentIntensityAnalyzer) -> float:
    """Return a sentiment score [0, 100] for a single review string.

    Empty or null reviews receive the neutral score of 50.
    """
    if not review or not str(review).strip():
        return 50.0

    compound = analyzer.polarity_scores(str(review))["compound"]
    return compound_to_score(compound)


def score_reviews(df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'sentiment_score' column to a reviews DataFrame.

    Args:
        df: DataFrame with at least a 'review' column.

    Returns:
        Copy of df with an additional 'sentiment_score' column [0, 100].
    """
    analyzer = SentimentIntensityAnalyzer()

    df = df.copy()
    df["sentiment_score"] = df["review"].apply(
        lambda text: analyze_sentiment(text, analyzer)
    )

    return df


def aggregate_by_recipe(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-review sentiment scores to the recipe level.

    Args:
        df: DataFrame with 'recipeid' and 'sentiment_score' columns.

    Returns:
        DataFrame indexed by recipeid with:
        - mean_sentiment_score
        - review_count
        - std_sentiment (0.0 when only one review exists)
    """
    agg = (
        df.groupby("recipeid")["sentiment_score"]
        .agg(
            mean_sentiment_score="mean",
            review_count="count",
            std_sentiment="std",
        )
        .reset_index()
    )

    # std is NaN when a recipe has exactly one review — treat as no variance
    agg["std_sentiment"] = agg["std_sentiment"].fillna(0.0)

    agg["mean_sentiment_score"] = agg["mean_sentiment_score"].round(2)
    agg["std_sentiment"] = agg["std_sentiment"].round(2)

    return agg


def add_percentile_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Add a sentiment_percentile column: rank recipes 0-100 by mean_sentiment_score.

    Uses pandas rank(pct=True) so the distribution is spread evenly across [0, 100]
    regardless of VADER's positivity bias.  mean_sentiment_score is preserved.
    """
    df = df.copy()
    df["sentiment_percentile"] = (
        df["mean_sentiment_score"].rank(pct=True) * 100
    ).round(2)
    return df


def save_gold(df: pd.DataFrame) -> None:
    """Persist the aggregated sentiment scores to the Gold layer."""
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(GOLD_OUTPUT, index=False)
    print(f"[INFO] Gold sentiment scores saved: {GOLD_OUTPUT}")


def main() -> None:
    print("[INFO] Starting YUMMY sentiment analysis...")

    # If gold file already exists reuse it — avoids re-scoring 1.4M reviews.
    if GOLD_OUTPUT.exists():
        print(f"[INFO] Existing gold file found — loading without re-running VADER: {GOLD_OUTPUT}")
        gold_df = pd.read_parquet(GOLD_OUTPUT)
    else:
        reviews_file = get_latest_reviews_file()
        print(f"[INFO] Reading reviews: {reviews_file}")
        reviews_df = pd.read_parquet(reviews_file)
        print(f"[INFO] Reviews loaded: {len(reviews_df)} rows")

        print("[INFO] Applying VADER sentiment analysis...")
        scored_df = score_reviews(reviews_df)

        null_reviews = scored_df["review"].isna().sum() + (scored_df["review"] == "").sum()
        if null_reviews:
            print(f"[INFO] {null_reviews} empty/null reviews defaulted to score 50")

        print("[INFO] Aggregating sentiment scores by recipe...")
        gold_df = aggregate_by_recipe(scored_df)
        gold_df["processed_at"] = datetime.now(UTC).isoformat()

    print(f"[INFO] Recipes with sentiment data: {len(gold_df)}")

    std_before = gold_df["mean_sentiment_score"].std()
    print(f"[INFO] mean_sentiment_score  — mean: {gold_df['mean_sentiment_score'].mean():.2f}  std: {std_before:.2f}")

    gold_df = add_percentile_rank(gold_df)

    std_after = gold_df["sentiment_percentile"].std()
    print(f"[INFO] sentiment_percentile  — mean: {gold_df['sentiment_percentile'].mean():.2f}  std: {std_after:.2f}")
    print(f"[INFO] Std improvement: {std_before:.2f} → {std_after:.2f}  (×{std_after / std_before:.1f} spread)")

    save_gold(gold_df)

    print("[INFO] Top 10 recipes by sentiment percentile:")
    print(
        gold_df.sort_values("sentiment_percentile", ascending=False)
        .head(10)[["recipeid", "mean_sentiment_score", "sentiment_percentile", "review_count"]]
        .to_string(index=False)
    )

    print("[INFO] Sentiment analysis completed.")


if __name__ == "__main__":
    main()
