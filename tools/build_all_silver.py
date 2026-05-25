import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


SILVER_JOBS = [
    {
        "name": "EUFIC Silver transformation",
        "script": PROJECT_ROOT / "transform" / "eufic" / "clean_eufic.py",
    },
    {
        "name": "FAOSTAT QCL Silver transformation",
        "script": PROJECT_ROOT / "transform" / "faostat" / "clean_faostat_qcl.py",
    },
    {
        "name": "Food.com Silver transformation",
        "script": PROJECT_ROOT / "transform" / "foodcom" / "clean_foodcom.py",
    },
]


def run_job(job: dict) -> None:
    print("=" * 80)
    print(f"[INFO] Starting job: {job['name']}")
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
        raise RuntimeError(f"Job failed: {job['name']}")

    print(f"[INFO] Job completed: {job['name']}")


def main() -> None:
    print("[INFO] Starting all Silver transformations...")

    for job in SILVER_JOBS:
        run_job(job)

    print("=" * 80)
    print("[INFO] All Silver transformations completed successfully.")
    print("=" * 80)


if __name__ == "__main__":
    main()