"""Entry point: python scripts/ingest_corpus.py [--render-only|--recreate]."""

from policypulse_ingest.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
