"""
FAERS 2026Q1 — Quick Start
---------------------------
Run this top to bottom to load, deduplicate, and detect signals
from your local 2026Q1 extract.

Requirements:
    pip install pandas numpy scipy tqdm

Usage:
    cd faers-pharmacovigilance
    python notebooks/01_quickstart.py
    
    OR open in Jupyter:
    jupyter notebook notebooks/01_quickstart.py
"""

import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import pandas as pd
from pipeline import FAERSParser, deduplicate_cases, SignalDetector

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")

# ── 1. CONFIGURE YOUR DATA PATH ───────────────────────────────────────────────
# Point this at the folder containing DEMO26Q1.TXT, DRUG26Q1.TXT, etc.
# Adjust if your folder name differs.

DATA_DIR = Path("data/raw/2026Q1")   # <-- change if needed

# ── 2. LOAD ───────────────────────────────────────────────────────────────────
print("\n=== Loading FAERS 2026Q1 ===")
parser = FAERSParser(DATA_DIR)

# Quick record count before loading
print("\nFile sizes (rows):")
for name, count in parser.summary().items():
    print(f"  {name}: {count:,}")

demo, drug, reac, outc = parser.load_all()
print(f"\nLoaded: {len(demo):,} demographic reports")
print(f"        {len(drug):,} drug records")
print(f"        {len(reac):,} reaction records")
print(f"        {len(outc):,} outcome records")

# ── 3. DEDUPLICATE ────────────────────────────────────────────────────────────
print("\n=== Deduplicating ===")
demo_dedup = deduplicate_cases(demo)
print(f"Unique cases after dedup: {len(demo_dedup):,}")

# Filter drug and reac to deduped cases only
valid_ids = set(demo_dedup["PRIMARYID"])
drug_dedup = drug[drug["PRIMARYID"].isin(valid_ids)].copy()
reac_dedup  = reac[reac["PRIMARYID"].isin(valid_ids)].copy()
print(f"Drug records after filter: {len(drug_dedup):,}")
print(f"Reaction records after filter: {len(reac_dedup):,}")

# ── 4. QUICK DATA SNAPSHOT ────────────────────────────────────────────────────
print("\n=== Database Snapshot ===")

print("\nTop 15 most-reported drugs (primary suspect, by active ingredient):")
top_drugs = (
    drug_dedup[drug_dedup["ROLE_COD"] == "PS"]["PROD_AI"]
    .str.upper().str.strip()
    .value_counts()
    .head(15)
)
print(top_drugs.to_string())

print("\nTop 15 most-reported adverse events (PT):")
top_aes = (
    reac_dedup["PT"]
    .str.upper().str.strip()
    .value_counts()
    .head(15)
)
print(top_aes.to_string())

print("\nOutcome distribution:")
print(outc["OUTC_COD"].value_counts().to_string())

print("\nReporter occupation:")
print(demo_dedup["OCCP_COD"].value_counts().to_string())

# ── 5. SIGNAL DETECTION ───────────────────────────────────────────────────────
print("\n=== Signal Detection ===")
detector = SignalDetector(drug_dedup, reac_dedup, drug_col="PROD_AI")

# Example: run on one of the top drugs from step 4 above
# Change DRUG_TARGET to any drug name from the top_drugs list
DRUG_TARGET = top_drugs.index[0]  # defaults to most-reported drug
print(f"\nRunning ROR/PRR/EBGM for: {DRUG_TARGET}")

signals = detector.run_all(drug_name=DRUG_TARGET, min_reports=3, signal_any=True)

if signals.empty:
    print("No signals detected (try lowering min_reports or check drug name)")
else:
    print(f"\nTop 20 signals (sorted by SIGNAL_COUNT, then ROR):\n")
    display_cols = ["PT", "a", "ROR", "ROR_CI_lo", "PRR", "PRR_chi2", "EBGM", "EB05", "SIGNAL_COUNT"]
    display_cols = [c for c in display_cols if c in signals.columns]
    pd.set_option("display.max_rows", 20)
    pd.set_option("display.float_format", "{:.2f}".format)
    pd.set_option("display.max_colwidth", 40)
    print(signals[display_cols].head(20).to_string(index=False))

# ── 6. SAVE RESULTS ───────────────────────────────────────────────────────────
out_path = Path("data") / f"signals_{DRUG_TARGET.replace(' ', '_')}_2026Q1.csv"
signals.to_csv(out_path, index=False)
print(f"\nSignals saved to: {out_path}")
print("\nDone.")
