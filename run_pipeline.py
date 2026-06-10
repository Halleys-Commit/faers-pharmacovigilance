"""
FAERS Incremental Pipeline
---------------------------
One command to:
  1. Check which quarters you have locally
  2. Download any missing quarters (up to BACKFILL_QUARTERS)
  3. Extract and organize into data/raw/YYYYQn/
  4. Parse + deduplicate all quarters into a master dataset
  5. Run signal detection
  6. Re-generate all visualizations

Usage:
    python run_pipeline.py                  # update + full reanalysis
    python run_pipeline.py --download-only  # just fetch new data
    python run_pipeline.py --analyze-only   # skip download, rerun analysis
    python run_pipeline.py --status         # show what quarters you have
"""

import argparse
import logging
import shutil
import sys
import zipfile
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests
from tqdm import tqdm

# ── CONFIG ────────────────────────────────────────────────────────────────────

BACKFILL_QUARTERS = 8        # how many quarters back to maintain
RAW_DIR           = Path("data/raw")
MASTER_DIR        = Path("data/master")
FIGURES_DIR       = Path("data/figures")
LOG_FILE          = Path("data/pipeline.log")

# FDA FAERS download base URL (verified April 2026)
# Format: https://fis.fda.gov/content/Exports/faers_ascii_YYYYqN.zip
FAERS_BASE_URL = "https://fis.fda.gov/content/Exports"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
    ]
)
logger = logging.getLogger(__name__)

# ── QUARTER UTILITIES ─────────────────────────────────────────────────────────

def current_quarter() -> tuple[int, int]:
    """Return (year, quarter) for the most recently RELEASED FAERS quarter.
    FDA typically releases ~3 months after quarter end, so we lag by one quarter."""
    now = datetime.now()
    # Current calendar quarter
    q = (now.month - 1) // 3 + 1
    year = now.year
    # Lag one quarter for FDA release delay
    q -= 1
    if q == 0:
        q = 4
        year -= 1
    return year, q


def quarters_back(n: int) -> list[tuple[int, int]]:
    """
    Return list of (year, quarter) tuples for the last n quarters,
    most recent first.
    """
    year, q = current_quarter()
    result = []
    for _ in range(n):
        result.append((year, q))
        q -= 1
        if q == 0:
            q = 4
            year -= 1
    return result


def quarter_to_str(year: int, q: int) -> str:
    """e.g. (2026, 1) -> '2026Q1'"""
    return f"{year}Q{q}"


def quarter_dir(year: int, q: int) -> Path:
    """Local directory for a quarter's extracted files."""
    return RAW_DIR / quarter_to_str(year, q)


def quarter_zip_name(year: int, q: int) -> str:
    """FDA zip filename format: faers_ascii_2026q1.zip"""
    return f"faers_ascii_{year}q{q}.zip"


def quarter_zip_url(year: int, q: int) -> str:
    return f"{FAERS_BASE_URL}/{quarter_zip_name(year, q)}"


# ── DOWNLOAD & EXTRACT ────────────────────────────────────────────────────────

def is_downloaded(year: int, q: int) -> bool:
    """Check if quarter already extracted — look for DEMO file."""
    qdir = quarter_dir(year, q)
    if not qdir.exists():
        return False
    demo_files = list(qdir.glob("DEMO*.txt")) + list(qdir.glob("DEMO*.TXT"))
    return len(demo_files) > 0


def download_quarter(year: int, q: int) -> bool:
    """
    Download and extract one FAERS quarter.
    Returns True on success, False if not available (future quarter).
    """
    label = quarter_to_str(year, q)
    url   = quarter_zip_url(year, q)
    qdir  = quarter_dir(year, q)
    zip_path = RAW_DIR / quarter_zip_name(year, q)

    logger.info(f"Downloading {label} from {url}")

    try:
        response = requests.get(url, stream=True, timeout=60)
        if response.status_code == 404:
            logger.warning(f"{label} not available at FDA yet (404) — skipping")
            return False
        response.raise_for_status()

        total = int(response.headers.get("content-length", 0))
        RAW_DIR.mkdir(parents=True, exist_ok=True)

        with open(zip_path, "wb") as f, tqdm(
            desc=f"  {label}",
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
        ) as bar:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                bar.update(len(chunk))

    except requests.RequestException as e:
        logger.error(f"Download failed for {label}: {e}")
        return False

    # Extract
    logger.info(f"Extracting {label}...")
    qdir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # FDA zips contain a nested folder — flatten into qdir
            for member in zf.namelist():
                filename = Path(member).name
                if not filename or filename.startswith("."):
                    continue
                ext = Path(filename).suffix.upper()
                if ext in (".TXT", ".PDF", ".DOC"):
                    target = qdir / filename.upper()
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        logger.info(f"Extracted {label} → {qdir}")
    except zipfile.BadZipFile as e:
        logger.error(f"Bad zip for {label}: {e}")
        return False
    finally:
        # Delete zip to save space
        zip_path.unlink(missing_ok=True)

    return True


def sync_quarters(n: int = BACKFILL_QUARTERS) -> list[tuple[int, int]]:
    """
    Ensure last n quarters are downloaded locally.
    Skips quarters already present. Returns list of newly downloaded quarters.
    """
    targets = quarters_back(n)
    newly_downloaded = []

    print(f"\n{'='*50}")
    print(f"FAERS Sync — checking last {n} quarters")
    print(f"{'='*50}")

    for year, q in targets:
        label = quarter_to_str(year, q)
        if is_downloaded(year, q):
            print(f"  ✓ {label} — already present")
        else:
            print(f"  ↓ {label} — downloading...")
            success = download_quarter(year, q)
            if success:
                newly_downloaded.append((year, q))
                print(f"  ✓ {label} — done")
            else:
                print(f"  ✗ {label} — unavailable")

    return newly_downloaded


# ── MASTER DATASET ────────────────────────────────────────────────────────────

def build_master_dataset(n: int = BACKFILL_QUARTERS) -> tuple[pd.DataFrame, ...]:
    """
    Load and concatenate all available quarters into master DataFrames.
    Adds a QUARTER column for temporal analysis.
    Deduplicates within each quarter, then globally by CASEID (keep latest FDA_DT).
    """
    from pipeline import FAERSParser, deduplicate_cases

    targets = [(y, q) for y, q in quarters_back(n) if is_downloaded(y, q)]

    if not targets:
        raise RuntimeError("No quarters available locally. Run --download-only first.")

    all_demo, all_drug, all_reac, all_outc = [], [], [], []

    print(f"\nLoading {len(targets)} quarters into master dataset...")
    for year, q in targets:
        label = quarter_to_str(year, q)
        try:
            parser = FAERSParser(quarter_dir(year, q))
            demo, drug, reac, outc = parser.load_all()

            # Deduplicate within quarter
            demo = deduplicate_cases(demo)
            valid = set(demo["PRIMARYID"])
            drug  = drug[drug["PRIMARYID"].isin(valid)]
            reac  = reac[reac["PRIMARYID"].isin(valid)]
            outc  = outc[outc["PRIMARYID"].isin(valid)]

            # Tag with quarter
            for df in [demo, drug, reac, outc]:
                df["QUARTER"] = label

            all_demo.append(demo)
            all_drug.append(drug)
            all_reac.append(reac)
            all_outc.append(outc)
            print(f"  ✓ {label}: {len(demo):,} cases")

        except Exception as e:
            logger.error(f"Failed to load {label}: {e}")
            continue

    demo_master = pd.concat(all_demo, ignore_index=True)
    drug_master = pd.concat(all_drug, ignore_index=True)
    reac_master = pd.concat(all_reac, ignore_index=True)
    outc_master = pd.concat(all_outc, ignore_index=True)

    # Global dedup — if same CASEID appears in multiple quarters, keep latest
    before = len(demo_master)
    demo_master["_fda_dt_num"] = pd.to_numeric(demo_master["FDA_DT"], errors="coerce")
    demo_master = (demo_master
                   .sort_values("_fda_dt_num", ascending=False)
                   .drop_duplicates(subset=["CASEID"], keep="first")
                   .drop(columns=["_fda_dt_num"])
                   .reset_index(drop=True))
    after = len(demo_master)
    logger.info(f"Global dedup: {before:,} → {after:,} unique cases across all quarters")

    valid_global = set(demo_master["PRIMARYID"])
    drug_master = drug_master[drug_master["PRIMARYID"].isin(valid_global)].reset_index(drop=True)
    reac_master = reac_master[reac_master["PRIMARYID"].isin(valid_global)].reset_index(drop=True)
    outc_master = outc_master[outc_master["PRIMARYID"].isin(valid_global)].reset_index(drop=True)

    # Save master CSVs (gitignored)
    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    demo_master.to_parquet(MASTER_DIR / "demo_master.parquet", index=False)
    drug_master.to_parquet(MASTER_DIR / "drug_master.parquet", index=False)
    reac_master.to_parquet(MASTER_DIR / "reac_master.parquet", index=False)
    outc_master.to_parquet(MASTER_DIR / "outc_master.parquet", index=False)
    logger.info(f"Master dataset saved to {MASTER_DIR}/")

    print(f"\nMaster dataset: {len(demo_master):,} cases across {len(targets)} quarters")
    return demo_master, drug_master, reac_master, outc_master


def load_master() -> tuple[pd.DataFrame, ...]:
    """Load pre-built master parquet files (fast path)."""
    files = ["demo_master", "drug_master", "reac_master", "outc_master"]
    missing = [f for f in files if not (MASTER_DIR / f"{f}.parquet").exists()]
    if missing:
        raise FileNotFoundError(f"Master files missing: {missing}. Run full pipeline first.")
    return tuple(pd.read_parquet(MASTER_DIR / f"{f}.parquet") for f in files)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def print_status():
    """Show which quarters are available locally."""
    targets = quarters_back(BACKFILL_QUARTERS)
    print(f"\nFAERS Local Status (last {BACKFILL_QUARTERS} quarters):")
    print(f"{'Quarter':<12} {'Status':<20} {'Cases'}")
    print("-" * 45)
    for year, q in targets:
        label = quarter_to_str(year, q)
        qdir  = quarter_dir(year, q)
        if is_downloaded(year, q):
            # Quick case count from DEMO file
            demo_files = list(qdir.glob("DEMO*.txt")) + list(qdir.glob("DEMO*.TXT"))
            try:
                count = sum(1 for _ in open(demo_files[0], "rb")) - 1
                print(f"{label:<12} {'✓ Downloaded':<20} {count:,}")
            except Exception:
                print(f"{label:<12} {'✓ Downloaded':<20} —")
        else:
            print(f"{label:<12} {'✗ Missing':<20} —")

    # Master dataset status
    demo_parquet = MASTER_DIR / "demo_master.parquet"
    if demo_parquet.exists():
        df = pd.read_parquet(demo_parquet, columns=["QUARTER"])
        quarters_in_master = sorted(df["QUARTER"].unique())
        print(f"\nMaster dataset: {len(df):,} cases | quarters: {', '.join(quarters_in_master)}")
    else:
        print("\nMaster dataset: not built yet")


def main():
    parser = argparse.ArgumentParser(description="FAERS Incremental Pipeline")
    parser.add_argument("--download-only", action="store_true", help="Download missing quarters only")
    parser.add_argument("--analyze-only",  action="store_true", help="Skip download, rerun analysis on existing data")
    parser.add_argument("--status",        action="store_true", help="Show local data status")
    parser.add_argument("--backfill",      type=int, default=BACKFILL_QUARTERS,
                        help=f"Number of quarters to maintain (default: {BACKFILL_QUARTERS})")
    args = parser.parse_args()

    if args.status:
        print_status()
        return

    n = args.backfill

    # Step 1: Download
    if not args.analyze_only:
        sync_quarters(n)

    # Step 2: Build master dataset
    if not args.download_only:
        demo, drug, reac, outc = build_master_dataset(n)

        # Step 3: Signal detection
        print("\nRunning signal detection on master dataset...")
        from pipeline import SignalDetector
        drug["_drug"] = drug["PROD_AI"].str.upper().str.strip()
        reac["_pt"]   = reac["PT"].str.upper().str.strip()

        detector  = SignalDetector(drug, reac, drug_col="PROD_AI")
        top_drugs = drug[drug["ROLE_COD"]=="PS"]["_drug"].value_counts().head(5).index.tolist()

        all_signals = []
        for drug_name in top_drugs:
            sigs = detector.run_all(drug_name, min_reports=3, signal_any=True)
            if not sigs.empty:
                sigs["DRUG"] = drug_name
                all_signals.append(sigs)
            print(f"  ✓ {drug_name}: {len(sigs)} signals")

        if all_signals:
            signals_df = pd.concat(all_signals, ignore_index=True)
            signals_df.to_csv(MASTER_DIR / "signals_master.csv", index=False)
            print(f"\nSignals saved: {MASTER_DIR / 'signals_master.csv'}")

        # Step 4: Re-run visualization notebook
        print("\nTo regenerate visualizations:")
        print("  python -m jupyter nbconvert --to notebook --execute notebooks/02_signal_visualization.ipynb")

        print("\nPipeline complete.")
        print_status()


if __name__ == "__main__":
    main()
