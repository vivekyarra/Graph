"""Empirical verification harness on a running FalkorDB instance.

Proves cold-start threat reconnaissance, disposable clone simulation,
causal memory ablation, and topology drift resilience on live FalkorDB graphs.

Usage:
    python -m maelin.verify --output verification-proof.json
"""
from __future__ import annotations
from .judge import run, main

if __name__ == "__main__":
    main()
