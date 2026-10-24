import argparse
from pathlib import Path
from app.config import get_settings
from app.services.resume_ingest import ingest_pdf


def main():
    parser = argparse.ArgumentParser(description="Insert PDF resume into candidate_profile")
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    print(ingest_pdf(args.pdf, get_settings()))


if __name__ == "__main__":
    main()
