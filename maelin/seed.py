"""Populate only the two explicitly requested synthetic tenant graphs."""
import argparse
import json
from pathlib import Path
import os
from .store import Store

DATA = Path(__file__).resolve().parent.parent / "data" / "demo.json"


def dataset():
    return json.loads(DATA.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant",default="alpha")
    parser.add_argument("--reset",action="store_true",help="DESTRUCTIVE: clears just this tenant's two demo graphs")
    args = parser.parse_args()
    store=Store(os.getenv("FALKOR_HOST","localhost"), int(os.getenv("FALKOR_PORT","6379")), os.getenv("FALKOR_PASSWORD"))
    store.seed(args.tenant, dataset(), reset=args.reset)
    print(f"Seeded synthetic incident demo for tenant {args.tenant!r}")


if __name__=="__main__":
    main()
