"""
Orchestrator for the full ML / Gold pipeline.

Runs the four steps in the strict dependency order defined in ml/README.md §1:

    Step 1  ml/matching/ingredient_matcher.py
    Step 2  ml/sentiment/sentiment_analyzer.py        (auto-skips VADER if gold exists)
    Step 3  transform/gold/build_gold_yummy_recommendations.py   (needs step 2)
    Step 4  ml/clustering/recipe_clusterer.py          (needs steps 1 & 3)

Usage
-----
    python tools/build_all_ml.py            # run all four steps
    python tools/build_all_ml.py --from 3   # resume from step 3 (skip 1 & 2)
"""

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

ML_JOBS: list[dict] = [
    {
        "step": 1,
        "name": "Ingredient matching (TF-IDF)",
        "script": PROJECT_ROOT / "ml" / "matching" / "ingredient_matcher.py",
    },
    {
        "step": 2,
        "name": "Sentiment analysis (VADER)",
        "script": PROJECT_ROOT / "ml" / "sentiment" / "sentiment_analyzer.py",
    },
    {
        "step": 3,
        "name": "Gold recommendations builder",
        "script": PROJECT_ROOT / "transform" / "gold" / "build_gold_yummy_recommendations.py",
    },
    {
        "step": 4,
        "name": "Recipe clustering (K-Means)",
        "script": PROJECT_ROOT / "ml" / "clustering" / "recipe_clusterer.py",
    },
]


def run_job(job: dict) -> None:
    """Run a single pipeline step as a subprocess.

    Args:
        job: Dict with keys ``step`` (int), ``name`` (str), and ``script`` (Path).

    Raises:
        FileNotFoundError: If the script path does not exist on disk.
        RuntimeError: If the subprocess exits with a non-zero return code.
    """
    print("=" * 80)
    print(f"[INFO] Starting step {job['step']}: {job['name']}")
    print(f"[INFO] Script: {job['script']}")
    print("=" * 80)

    if not job["script"].exists():
        raise FileNotFoundError(f"Script not found: {job['script']}")

    result = subprocess.run(
        [sys.executable, str(job["script"])],
        cwd=PROJECT_ROOT,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Step {job['step']} failed: {job['name']} "
            f"(exit code {result.returncode})"
        )

    print(f"[INFO] Step {job['step']} completed: {job['name']}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the full YUMMY ML / Gold pipeline (steps 1–4).",
    )
    parser.add_argument(
        "--from",
        dest="from_step",
        type=int,
        choices=[1, 2, 3, 4],
        default=1,
        metavar="STEP",
        help="Resume from this step number (1–4). Steps before STEP are skipped. "
             "Default: 1 (run everything).",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point: parse args, filter jobs, run each step in order."""
    args = parse_args()
    from_step: int = args.from_step

    jobs = [j for j in ML_JOBS if j["step"] >= from_step]

    if from_step > 1:
        skipped = [j["name"] for j in ML_JOBS if j["step"] < from_step]
        print(f"[INFO] Resuming from step {from_step} — skipping: {', '.join(skipped)}")

    print(f"[INFO] Starting ML / Gold pipeline ({len(jobs)} step(s))...")

    for job in jobs:
        run_job(job)

    print("=" * 80)
    print("[INFO] All ML transformations completed successfully.")
    print("=" * 80)


if __name__ == "__main__":
    main()
