"""
FAERS Quarterly Data Downloader
---------------------------------
Downloads FDA Adverse Event Reporting System (FAERS) quarterly ASCII files
from the FDA public data repository.

FDA FAERS data: https://www.fda.gov/drugs/drug-approvals-and-databases/fda-adverse-event-reporting-system-faers-latest-quarterly-data-files

Usage:
    python download_faers.py --year 2023 --quarters Q1 Q2 Q3 Q4
    python download_faers.py --year 2022 --quarters Q4
"""

import argparse
from pathlib import Path


def download_quarter(year: int, quarter: str, output_dir: Path) -> Path:
    """
    Download a single FAERS quarterly file.

    Parameters
    ----------
    year : int
        Four-digit year (e.g., 2023)
    quarter : str
        Quarter string — 'Q1', 'Q2', 'Q3', or 'Q4'
    output_dir : Path
        Directory to save downloaded zip files

    Returns
    -------
    Path
        Path to downloaded zip file

    Notes
    -----
    FDA occasionally changes URL structure — verify against current FDA page
    before running. Current base URL: https://fis.fda.gov/content/Exports
    """
    # TODO: implement
    raise NotImplementedError("Verify current FDA URL structure first")


def extract_quarter(zip_path: Path, extract_dir: Path) -> None:
    """
    Extract FAERS quarterly zip to structured directory.

    FAERS ASCII zips contain 7 pipe-delimited files:
    DEMO (demographics), DRUG, REAC (reactions), OUTC (outcomes),
    RPSR (report sources), THER (therapy dates), INDI (indications)
    """
    # TODO: implement
    raise NotImplementedError


def main():
    parser = argparse.ArgumentParser(description="Download FAERS quarterly data files")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--quarters", nargs="+", choices=["Q1", "Q2", "Q3", "Q4"],
                        default=["Q1", "Q2", "Q3", "Q4"])
    parser.add_argument("--output-dir", type=Path, default=Path("raw"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for quarter in args.quarters:
        print(f"Downloading {args.year} {quarter}...")
        zip_path = download_quarter(args.year, quarter, args.output_dir)
        extract_quarter(zip_path, args.output_dir / f"{args.year}_{quarter}")


if __name__ == "__main__":
    main()
