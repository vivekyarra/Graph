"""Populate only the two explicitly requested synthetic tenant graphs."""
import argparse
import json
from pathlib import Path
import os
from .store import Store
from .schema import validate_dataset

DATA = Path(__file__).resolve().parent.parent / "data" / "demo.json"


def dataset():
    return json.loads(DATA.read_text(encoding="utf-8"))


def seed_tenant(tenant: str = "alpha", reset: bool = False, file: Path | None = None, store: Store | None = None):
    if store is None:
        store = Store(os.getenv("FALKOR_HOST", "localhost"), int(os.getenv("FALKOR_PORT", "6379")), os.getenv("FALKOR_PASSWORD"))
    data = validate_dataset(json.loads(file.read_text(encoding='utf-8'))) if file else dataset()
    store.seed(tenant, data, reset=reset)
    return store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant",default="alpha")
    parser.add_argument("--reset",action="store_true",help="DESTRUCTIVE: clears just this tenant's two demo graphs")
    parser.add_argument("--file",type=Path,help="Optional authorized synthetic JSON graph (no remote access required)")
    args = parser.parse_args()
    seed_tenant(args.tenant, reset=args.reset, file=args.file)
    print(f"Seeded synthetic incident demo for tenant {args.tenant!r}")


if __name__=="__main__":
    main()
