import re
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer


SILVER_FOODCOM_DIR = Path("data/silver/foodcom")
SILVER_EUFIC_DIR = Path("data/silver/eufic")
SILVER_FAOSTAT_DIR = Path("data/silver/faostat/qcl")
GOLD_DIR = Path("data/gold")

STOPWORDS = frozenset({"and", "or", "the", "a", "of", "with", "in"})
SIMILARITY_THRESHOLD = 0.35
MIN_TOKEN_LEN = 3
BATCH_SIZE = 5_000


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def get_latest_file(directory: Path, pattern: str) -> Path:
    """Return the most recent file matching *pattern* inside *directory*."""
    files = sorted(directory.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No file matching '{pattern}' found in {directory}")
    return files[-1]


def save_gold(df: pd.DataFrame, filename: str) -> None:
    """Write *df* as Parquet to the Gold layer."""
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    output_path = GOLD_DIR / filename
    df.to_parquet(output_path, index=False)
    print(f"[INFO] Saved: {output_path} ({len(df):,} rows)")


# ---------------------------------------------------------------------------
# Reference vocabulary
# ---------------------------------------------------------------------------


def build_reference_vocab(
    eufic_df: pd.DataFrame,
    faostat_df: pd.DataFrame,
) -> tuple[list[str], dict[str, str]]:
    """Build a combined reference vocabulary from EUFIC and FAOSTAT product names.

    EUFIC takes source priority for terms that appear in both datasets.

    Args:
        eufic_df: Silver EUFIC DataFrame, must have a 'product_name' column.
        faostat_df: Silver FAOSTAT DataFrame, must have a 'product_name' column.

    Returns:
        reference_terms: Ordered list of all unique product name strings.
        source_map: Mapping of term → "eufic" or "faostat".
    """
    eufic_terms: set[str] = set(eufic_df["product_name"].dropna().unique())
    faostat_terms: set[str] = set(faostat_df["product_name"].dropna().unique())

    # EUFIC-first: EUFIC terms sorted, then FAOSTAT-only terms sorted
    reference_terms = sorted(eufic_terms) + sorted(faostat_terms - eufic_terms)

    source_map: dict[str, str] = {t: "eufic" for t in eufic_terms}
    for t in faostat_terms:
        if t not in source_map:
            source_map[t] = "faostat"

    print(f"[INFO] EUFIC product names: {len(eufic_terms):,}")
    print(f"[INFO] FAOSTAT product names: {len(faostat_terms):,}")
    print(f"[INFO] Combined reference vocabulary: {len(reference_terms):,} terms")
    return reference_terms, source_map


# ---------------------------------------------------------------------------
# Token extraction
# ---------------------------------------------------------------------------


def extract_ingredient_tokens(recipes_df: pd.DataFrame) -> list[str]:
    """Return a sorted list of unique ingredient tokens across all recipes.

    Tokens are obtained by whitespace-splitting 'recipeingredientparts'.
    Stopwords, purely numeric strings, and tokens shorter than MIN_TOKEN_LEN
    are discarded.

    Args:
        recipes_df: Silver recipes DataFrame with a 'recipeingredientparts' column.

    Returns:
        Sorted list of unique ingredient token strings.
    """
    raw = recipes_df["recipeingredientparts"].dropna()
    # Explode to one token per row (vectorised)
    tokens: pd.Series = raw.str.split(expand=False).explode().dropna().astype(str)

    keep = (
        ~tokens.isin(STOPWORDS)
        & ~tokens.str.isnumeric()
        & (tokens.str.len() >= MIN_TOKEN_LEN)
    )
    unique_tokens = sorted(tokens[keep].unique())
    print(f"[INFO] Unique ingredient tokens extracted: {len(unique_tokens):,}")
    return unique_tokens


# ---------------------------------------------------------------------------
# TF-IDF matching
# ---------------------------------------------------------------------------


def build_vectorizer(
    reference_terms: list[str],
) -> tuple[TfidfVectorizer, Any]:
    """Fit a character n-gram TF-IDF vectorizer on the reference vocabulary.

    Uses char_wb analyzer (3-4-grams) to handle morphological variants such as
    "tomatoes" ↔ "tomato" or "garlic" ↔ "garlic (dry)".
    The resulting reference matrix is L2-normalised, so a dot product between
    any two rows equals their cosine similarity.

    Args:
        reference_terms: List of product name strings to fit on.

    Returns:
        vectorizer: Fitted TfidfVectorizer.
        reference_matrix: Sparse L2-normalised matrix, shape (n_terms, n_features).
    """
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 4),
        norm="l2",
        sublinear_tf=True,
    )
    reference_matrix = vectorizer.fit_transform(reference_terms)
    print(f"[INFO] TF-IDF vocabulary size: {len(vectorizer.vocabulary_):,} n-grams")
    return vectorizer, reference_matrix


def match_tokens(
    tokens: list[str],
    reference_matrix: Any,
    vectorizer: TfidfVectorizer,
) -> tuple[np.ndarray, np.ndarray]:
    """Match each token to the most similar reference term via cosine similarity.

    Tokens are processed in batches of BATCH_SIZE to bound peak memory usage.
    Because both matrices are L2-normalised, cosine similarity equals the dot
    product — computed here as a sparse matrix multiplication.

    Args:
        tokens: Unique ingredient token strings to query.
        reference_matrix: Sparse L2-normalised reference matrix (n_ref, n_features).
        vectorizer: Fitted TfidfVectorizer used to transform query tokens.

    Returns:
        best_indices: Integer array (n_tokens,) — index into reference_terms.
        best_scores: Float array (n_tokens,) — cosine similarity in [0, 1].
    """
    all_indices: list[np.ndarray] = []
    all_scores: list[np.ndarray] = []

    for batch_start in range(0, len(tokens), BATCH_SIZE):
        batch = tokens[batch_start : batch_start + BATCH_SIZE]
        batch_matrix = vectorizer.transform(batch)  # (n_batch, n_features)

        # dot product of L2-normalised vectors = cosine similarity
        sim_matrix = (batch_matrix @ reference_matrix.T).toarray()  # (n_batch, n_ref)

        best_idx = sim_matrix.argmax(axis=1)
        best_score = sim_matrix[np.arange(len(batch)), best_idx]

        all_indices.append(best_idx)
        all_scores.append(best_score)

        progress = min(batch_start + BATCH_SIZE, len(tokens))
        print(f"[INFO]   Matched {progress:,} / {len(tokens):,} tokens")

    return np.concatenate(all_indices), np.concatenate(all_scores)


# ---------------------------------------------------------------------------
# Gold output builders
# ---------------------------------------------------------------------------


def _extract_ref_root(ref_term: str) -> str:
    """Strip parenthetical qualifiers from a reference term and return its first word.

    Examples:
        "garlic (dry)"           → "garlic"
        "eggplants (aubergines)" → "eggplants"
        "tomato"                 → "tomato"
    """
    clean = re.sub(r"\s*\(.*?\)", "", ref_term).strip()
    first = clean.split()[0] if clean else ref_term.split()[0]
    return first


def morphological_guard(token: str, ref_term: str) -> bool:
    """Return True if *token* is morphologically compatible with *ref_term*.

    The reference term is first normalised by stripping parenthetical qualifiers
    and taking only its first word (``ref``).  The match is accepted when ANY
    of the four conditions below holds; otherwise it is rejected to prevent
    char-ngram false positives such as "pineapple" → "apple".

    Conditions (any one is sufficient):
        1. token == ref                                         (exact)
        2. token.rstrip("s") == ref.rstrip("s")                (singular/plural)
        3. token.startswith(ref)  and len(token)-len(ref) ≤ 2  (short suffix: tomatoes)
        4. ref.startswith(token)  and len(ref)-len(token) ≤ 2  (short suffix: garlic→garlics)
    """
    ref = _extract_ref_root(ref_term)
    if token == ref:
        return True
    if token.rstrip("s") == ref.rstrip("s"):
        return True
    if token.startswith(ref) and (len(token) - len(ref)) <= 2:
        return True
    if ref.startswith(token) and (len(ref) - len(token)) <= 2:
        return True
    return False


def build_matches_df(
    tokens: list[str],
    reference_terms: list[str],
    source_map: dict[str, str],
    best_indices: np.ndarray,
    best_scores: np.ndarray,
) -> pd.DataFrame:
    """Assemble the token-level ingredient matches DataFrame.

    Tokens whose best cosine similarity falls below SIMILARITY_THRESHOLD receive
    matched_term=None and source="unmatched".  The raw similarity_score is retained
    for all tokens to aid threshold tuning.

    Args:
        tokens: Unique ingredient tokens, in the same order as best_indices/scores.
        reference_terms: Ordered reference product names.
        source_map: Mapping of reference term → "eufic" or "faostat".
        best_indices: Per-token index into reference_terms.
        best_scores: Per-token cosine similarity score.

    Returns:
        DataFrame with columns:
            ingredient_token, matched_term, similarity_score, source
    """
    df = pd.DataFrame({
        "ingredient_token": tokens,
        "matched_term": [reference_terms[i] for i in best_indices],
        "similarity_score": best_scores.round(4),
    })

    # --- Step 1: cosine threshold ---
    unmatched_mask = df["similarity_score"] < SIMILARITY_THRESHOLD

    # --- Step 2: morphological guard (only for tokens that passed threshold) ---
    matched_idx = df.index[~unmatched_mask]
    revoked_mask = pd.Series(False, index=df.index)
    revoked_mask.loc[matched_idx] = ~df.loc[matched_idx].apply(
        lambda row: morphological_guard(row["ingredient_token"], row["matched_term"]),
        axis=1,
    )

    n_revoked = int(revoked_mask.sum())
    print(f"[INFO] Morphological guard revoked {n_revoked:,} false-positive matches")
    revoked_examples = df[revoked_mask][["ingredient_token", "matched_term"]].head(10)
    for _, ex in revoked_examples.iterrows():
        print(f"[INFO]   {ex['ingredient_token']} -> {ex['matched_term']} [REVOKED]")

    # --- Apply both masks ---
    final_unmatched = unmatched_mask | revoked_mask
    df.loc[final_unmatched, "matched_term"] = None
    df["source"] = df["matched_term"].map(source_map).fillna("unmatched")

    n_eufic     = (df["source"] == "eufic").sum()
    n_faostat   = (df["source"] == "faostat").sum()
    n_unmatched = (df["source"] == "unmatched").sum()
    match_rate  = 100 * (n_eufic + n_faostat) / len(df)

    print(f"[INFO] Token match rate: {match_rate:.1f}%  "
          f"(eufic={n_eufic:,}  faostat={n_faostat:,}  unmatched={n_unmatched:,})")

    return df


def build_recipe_map(
    recipes_df: pd.DataFrame,
    matches_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the recipe-level ingredient mapping DataFrame.

    For each recipe, unique ingredient tokens are resolved against matches_df,
    then aggregated into a list of matched terms plus per-source counts.
    Every recipe in recipes_df appears in the output; those with no valid tokens
    receive an empty list and zero counts.

    The matched_ingredients column stores a Python list of unique matched_term
    values (pyarrow list<string> in Parquet).

    Args:
        recipes_df: Silver recipes DataFrame with 'recipeid' and
            'recipeingredientparts' columns.
        matches_df: Token-level matches produced by build_matches_df.

    Returns:
        DataFrame with columns:
            recipeid, matched_ingredients, eufic_match_count,
            faostat_match_count, unmatched_count
    """
    # --- Explode recipes to (recipeid, ingredient_token) ---
    long = (
        recipes_df[["recipeid", "recipeingredientparts"]]
        .copy()
        .assign(recipeingredientparts=lambda d: d["recipeingredientparts"].fillna(""))
    )
    long["ingredient_token"] = long["recipeingredientparts"].str.split()
    long = (
        long[["recipeid", "ingredient_token"]]
        .explode("ingredient_token")
        .dropna(subset=["ingredient_token"])
    )
    long["ingredient_token"] = long["ingredient_token"].astype(str)

    keep = (
        ~long["ingredient_token"].isin(STOPWORDS)
        & ~long["ingredient_token"].str.isnumeric()
        & (long["ingredient_token"].str.len() >= MIN_TOKEN_LEN)
    )
    long = long[keep].drop_duplicates(subset=["recipeid", "ingredient_token"])

    # --- Join with token-level matches ---
    long = long.merge(
        matches_df[["ingredient_token", "matched_term", "source"]],
        on="ingredient_token",
        how="left",
    )
    long["source"] = long["source"].fillna("unmatched")

    # --- Per-source counts via unstack (vectorised) ---
    source_counts = (
        long.groupby(["recipeid", "source"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for col in ("eufic", "faostat", "unmatched"):
        if col not in source_counts.columns:
            source_counts[col] = 0
    source_counts = source_counts.rename(columns={
        "eufic": "eufic_match_count",
        "faostat": "faostat_match_count",
        "unmatched": "unmatched_count",
    })

    # --- Matched ingredients list per recipe ---
    matched_lists = (
        long.loc[
            (long["source"] != "unmatched") & long["matched_term"].notna(),
            ["recipeid", "matched_term"],
        ]
        .groupby("recipeid")["matched_term"]
        .apply(list)
        .reset_index()
        .rename(columns={"matched_term": "matched_ingredients"})
    )

    # --- Left-join from all recipes so every recipeid is present ---
    all_ids = recipes_df[["recipeid"]].drop_duplicates()
    recipe_map = (
        all_ids
        .merge(
            source_counts[["recipeid", "eufic_match_count",
                           "faostat_match_count", "unmatched_count"]],
            on="recipeid",
            how="left",
        )
        .merge(matched_lists, on="recipeid", how="left")
    )

    for col in ("eufic_match_count", "faostat_match_count", "unmatched_count"):
        recipe_map[col] = recipe_map[col].fillna(0).astype(int)
    recipe_map["matched_ingredients"] = recipe_map["matched_ingredients"].apply(
        lambda x: x if isinstance(x, list) else []
    )

    return recipe_map


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("[INFO] Starting YUMMY ingredient matching...")

    # --- Load Silver data ---
    recipes_file = get_latest_file(SILVER_FOODCOM_DIR, "silver_recipes_*.parquet")
    eufic_file = get_latest_file(SILVER_EUFIC_DIR, "silver_seasonality_*.parquet")
    faostat_file = get_latest_file(
        SILVER_FAOSTAT_DIR, "silver_faostat_qcl_production_*.parquet"
    )

    print(f"[INFO] Reading recipes: {recipes_file}")
    recipes_df = pd.read_parquet(recipes_file)

    print(f"[INFO] Reading EUFIC seasonality: {eufic_file}")
    eufic_df = pd.read_parquet(eufic_file)

    print(f"[INFO] Reading FAOSTAT production: {faostat_file}")
    faostat_df = pd.read_parquet(faostat_file)

    print(f"[INFO] Recipes loaded: {len(recipes_df):,}")

    # --- Reference vocabulary ---
    reference_terms, source_map = build_reference_vocab(eufic_df, faostat_df)

    # --- Unique ingredient tokens ---
    unique_tokens = extract_ingredient_tokens(recipes_df)

    # --- TF-IDF vectorizer fitted on reference ---
    print("[INFO] Building TF-IDF vectorizer on reference vocabulary...")
    vectorizer, reference_matrix = build_vectorizer(reference_terms)

    # --- Token → reference matching ---
    print("[INFO] Matching ingredient tokens to reference vocabulary...")
    best_indices, best_scores = match_tokens(unique_tokens, reference_matrix, vectorizer)

    # --- Gold: token-level matches ---
    matches_df = build_matches_df(
        unique_tokens, reference_terms, source_map, best_indices, best_scores
    )
    matches_df["processed_at"] = datetime.now(UTC).isoformat()

    # --- Gold: recipe-level map ---
    print("[INFO] Building recipe ingredient map...")
    recipe_map_df = build_recipe_map(recipes_df, matches_df)
    recipe_map_df["processed_at"] = datetime.now(UTC).isoformat()

    has_match = (
        (recipe_map_df["eufic_match_count"] + recipe_map_df["faostat_match_count"]) > 0
    ).sum()
    print(f"[INFO] Recipes with ≥1 match: {has_match:,} / {len(recipe_map_df):,}")

    save_gold(matches_df, "gold_ingredient_matches.parquet")
    save_gold(recipe_map_df, "gold_recipe_ingredient_map.parquet")

    print("[INFO] Ingredient matching completed.")


if __name__ == "__main__":
    main()
