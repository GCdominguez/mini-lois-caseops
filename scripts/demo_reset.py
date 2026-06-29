from __future__ import annotations

import argparse
import shutil
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "caseops.db"
CHROMA_DIR = BASE_DIR / ".chroma"


def remove_file(path: Path) -> bool:
    if not path.exists():
        return False
    path.unlink()
    return True


def remove_dir(path: Path) -> bool:
    if not path.exists():
        return False
    shutil.rmtree(path)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset local Mini LOIS demo state.")
    parser.add_argument(
        "--include-chroma",
        action="store_true",
        help="Also remove the local Chroma index. Run python ingest.py after this.",
    )
    args = parser.parse_args()

    removed_db = remove_file(DB_PATH)
    removed_chroma = remove_dir(CHROMA_DIR) if args.include_chroma else False

    print("Demo reset complete.")
    print(f"- SQLite matter store removed: {'yes' if removed_db else 'already clean'}")
    if args.include_chroma:
        print(f"- Chroma index removed: {'yes' if removed_chroma else 'already clean'}")
        print("- Next step: run python ingest.py before asking matter questions.")
    else:
        print("- Chroma index kept. Add --include-chroma if you want to rebuild retrieval too.")


if __name__ == "__main__":
    main()
