"""
K-Means recipe clustering on the Gold layer.

Joins gold_yummy_recommendations + gold_sentiment_scores +
gold_recipe_ingredient_map, scales a 6-feature matrix, fits KMeans(k=5),
and writes two output parquets to data/gold/.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import MinMaxScaler, StandardScaler

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GOLD_DIR = Path("data/gold")

IN_RECOMMENDATIONS = GOLD_DIR / "gold_yummy_recommendations.parquet"
IN_SENTIMENT       = GOLD_DIR / "gold_sentiment_scores.parquet"
IN_INGREDIENT_MAP  = GOLD_DIR / "gold_recipe_ingredient_map.parquet"

OUT_CLUSTERS  = GOLD_DIR / "gold_recipe_clusters.parquet"
OUT_PROFILES  = GOLD_DIR / "gold_cluster_profiles.parquet"

# Feature columns used for clustering
FEATURE_COLS: list[str] = [
    "yummy_score",
    "sentiment_percentile",   # percentile rank of mean_sentiment_score — evenly spread
    "simplicity_score",
    "eufic_match_count",
    "totaltime_inverted",     # derived: 1 − normalised totaltime
    "rating_score",
]

# One representative feature per unique label — used for greedy assignment.
# Each label is assigned to whichever cluster scores highest on its feature
# relative to the cross-cluster mean (ensures all 5 clusters get distinct labels).
LABEL_FEATURE_MAP: dict[str, str] = {
    "🏆 Top Rated":         "rating_score",
    "🌿 Seasonal & Local":  "eufic_match_count",
    "⭐ Crowd Favourite":   "sentiment_percentile",
    "⚡ Quick & Easy":      "totaltime_inverted",
    "🌍 Global Kitchen":    None,   # fallback — assigned to the remaining cluster
}

K_FINAL   = 5
K_RANGE   = range(2, 9)          # 2..8 for elbow curve
SEED      = 42
N_INIT    = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_and_join() -> pd.DataFrame:
    """Load the three Gold parquets and left-join on recipeid."""
    print("[INFO] Loading gold_yummy_recommendations.parquet …")
    recs = pd.read_parquet(IN_RECOMMENDATIONS)
    print(f"[INFO]   Recipes loaded: {len(recs):,}")

    print("[INFO] Loading gold_sentiment_scores.parquet …")
    # sentiment_percentile is now embedded in gold_yummy_recommendations (Step 2)
    sent = pd.read_parquet(IN_SENTIMENT)[["recipeid", "mean_sentiment_score"]]
    print(f"[INFO]   Sentiment rows: {len(sent):,}")

    print("[INFO] Loading gold_recipe_ingredient_map.parquet …")
    ing = pd.read_parquet(IN_INGREDIENT_MAP)[
        ["recipeid", "eufic_match_count", "faostat_match_count", "unmatched_count"]
    ]
    print(f"[INFO]   Ingredient-map rows: {len(ing):,}")

    df = (
        recs
        .merge(sent, on="recipeid", how="left")
        .merge(ing,  on="recipeid", how="left")
    )
    print(f"[INFO] Joined dataset: {len(df):,} rows, {df.shape[1]} cols")
    return df


def build_feature_matrix(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """
    Construct the 6-column feature matrix, fill NaNs with column medians,
    apply StandardScaler then MinMaxScaler so every feature lands in [0, 1].

    Returns (feature_df, scaled_array).
    """
    feat = df[["yummy_score", "sentiment_percentile", "simplicity_score",
               "eufic_match_count", "totaltime", "rating_score"]].copy()

    # Clip totaltime outliers at 99th percentile before inversion
    tt_cap = feat["totaltime"].quantile(0.99)
    clipped = (feat["totaltime"] > tt_cap).sum()
    if clipped:
        print(f"[INFO] Clipping {clipped:,} totaltime outliers at p99={tt_cap:.0f} min")
    feat["totaltime"] = feat["totaltime"].clip(upper=tt_cap)

    # Fill NaNs with column medians before any transformation
    null_counts = feat.isnull().sum()
    if null_counts.any():
        print("[INFO] NaN counts before fill:")
        for col, n in null_counts[null_counts > 0].items():
            print(f"[INFO]   {col}: {n:,}")
    feat.fillna(feat.median(), inplace=True)

    # Invert totaltime: high time → low score
    feat["totaltime_inverted"] = feat["totaltime"].max() - feat["totaltime"]
    feat.drop(columns=["totaltime"], inplace=True)

    # StandardScaler → MinMaxScaler → every feature in [0, 1]
    std_scaled = StandardScaler().fit_transform(feat[FEATURE_COLS])
    mm_scaled  = MinMaxScaler().fit_transform(std_scaled)

    return feat, mm_scaled


def elbow_curve(X: np.ndarray) -> None:
    """Print inertia values for k=2..8 (elbow / jury justification)."""
    print("\n[INFO] Elbow curve (inertia for k=2..8):")
    for k in K_RANGE:
        km = KMeans(n_clusters=k, random_state=SEED, n_init=N_INIT)
        km.fit(X)
        print(f"[INFO]   k={k}  inertia={km.inertia_:,.1f}")
    print()


def assign_labels_greedy(profiles: pd.DataFrame) -> list[str]:
    """
    Assign a unique label to each cluster via greedy matching.

    For each label (in priority order from LABEL_FEATURE_MAP), the unassigned
    cluster with the highest relative score on that label's representative
    feature is chosen.  The last unassigned cluster receives the fallback label.
    """
    global_means = profiles[FEATURE_COLS].mean()
    relative = profiles[FEATURE_COLS].subtract(global_means)

    assigned_clusters: set[int] = set()
    result: dict[int, str] = {}

    for label, feature in LABEL_FEATURE_MAP.items():
        if feature is None:
            continue  # fallback — handled below
        # Scores for unassigned clusters on this feature
        scores = {
            int(row["cluster_id"]): relative.loc[idx, feature]
            for idx, row in profiles.iterrows()
            if int(row["cluster_id"]) not in assigned_clusters
        }
        best_cluster = max(scores, key=scores.__getitem__)
        result[best_cluster] = label
        assigned_clusters.add(best_cluster)

    # Remaining cluster → fallback
    fallback_label = next(
        lbl for lbl, feat in LABEL_FEATURE_MAP.items() if feat is None
    )
    for _, row in profiles.iterrows():
        cid = int(row["cluster_id"])
        if cid not in assigned_clusters:
            result[cid] = fallback_label

    return [result[int(row["cluster_id"])] for _, row in profiles.iterrows()]


def run_clustering(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Fit KMeans(k=5) and return (labels, distances_to_centroid, inertia).
    Also prints the silhouette score.
    """
    print(f"[INFO] Fitting KMeans k={K_FINAL}, random_state={SEED}, n_init={N_INIT} …")
    km = KMeans(n_clusters=K_FINAL, random_state=SEED, n_init=N_INIT)
    labels = km.fit_predict(X)

    sil = silhouette_score(X, labels, sample_size=50_000, random_state=SEED)
    print(f"[INFO] Silhouette score (k={K_FINAL}): {sil:.4f}")

    # Euclidean distance of each point to its assigned centroid
    centroids = km.cluster_centers_
    distances = np.linalg.norm(X - centroids[labels], axis=1)

    return labels, distances, km.inertia_


def build_profiles(
    X_scaled: np.ndarray,
    labels: np.ndarray,
) -> pd.DataFrame:
    """
    Build per-cluster profile from the scaled feature matrix.
    Dominant feature is determined on [0,1] scaled values so all features
    are comparable — avoids raw-scale outliers skewing the label.
    """
    scaled_df = pd.DataFrame(X_scaled, columns=FEATURE_COLS)
    scaled_df["cluster_id"] = labels

    profiles = (
        scaled_df.groupby("cluster_id")[FEATURE_COLS]
        .mean()
        .reset_index()
    )
    label_counts = np.bincount(labels)
    profiles["recipe_count"] = profiles["cluster_id"].map(dict(enumerate(label_counts)))
    profiles["cluster_label"] = assign_labels_greedy(profiles)
    return profiles


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("[INFO] ── YUMMY Recipe Clustering ──────────────────────────────")

    df = load_and_join()

    print("[INFO] Building feature matrix …")
    feat_df, X = build_feature_matrix(df)

    elbow_curve(X)

    labels, distances, _ = run_clustering(X)

    print("\n[INFO] Recipe count per cluster:")
    for cid, cnt in sorted(zip(*np.unique(labels, return_counts=True))):
        print(f"[INFO]   cluster {cid}: {cnt:,} recipes")

    # ── Profiles ────────────────────────────────────────────────────────────
    profiles = build_profiles(X, labels)

    print("\n[INFO] Cluster profiles (mean feature values):")
    print(profiles[["cluster_id", "cluster_label", "recipe_count"] + FEATURE_COLS].to_string(index=False))

    # ── Recipe-level output ─────────────────────────────────────────────────
    label_map_series = profiles.set_index("cluster_id")["cluster_label"]

    clusters_df = pd.DataFrame({
        "recipeid":            df["recipeid"].values,
        "cluster_id":          labels,
        "cluster_label":       pd.Series(labels).map(label_map_series).values,
        "distance_to_centroid": distances,
    })

    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    clusters_df.to_parquet(OUT_CLUSTERS, index=False)
    print(f"\n[INFO] Saved: {OUT_CLUSTERS}  ({len(clusters_df):,} rows)")

    profiles.to_parquet(OUT_PROFILES, index=False)
    print(f"[INFO] Saved: {OUT_PROFILES}  ({len(profiles)} rows)")

    print("[INFO] ── Clustering completed ─────────────────────────────────")


if __name__ == "__main__":
    main()
