"""
FAERS ASCII Parser
------------------
Ingests FDA FAERS quarterly ASCII (pipe-delimited) files and normalizes
them into a unified pandas DataFrame schema for downstream analysis.

FAERS ASCII schema reference: https://www.fda.gov/media/97035/download

The 7 ASCII files per quarter:
    DEMO  — demographics: age, sex, weight, country, report date
    DRUG  — drug names, roles (PS=primary suspect, SS=secondary, C=concomitant)
    REAC  — adverse reactions (MedDRA Preferred Term)
    OUTC  — outcomes (death, hospitalization, disability, etc.)
    RPSR  — report source (consumer, physician, manufacturer)
    THER  — therapy start/end dates
    INDI  — drug indication (MedDRA PT)
"""

from pathlib import Path
import pandas as pd


DEMO_COLS = [
    "isr", "caseid", "caseversion", "i_f_cod", "event_dt", "mfr_dt",
    "init_fda_dt", "fda_dt", "rept_cod", "mfr_num", "mfr_sndr",
    "age", "age_cod", "gndr_cod", "e_sub", "wt", "wt_cod",
    "rept_dt", "to_mfr", "occp_cod", "reporter_country", "occr_country"
]

DRUG_COLS = [
    "isr", "caseid", "drug_seq", "role_cod", "drugname", "val_vbm",
    "route", "dose_vbm", "cum_dose_chr", "cum_dose_unit", "dechal",
    "rechal", "lot_num", "exp_dt", "nda_num", "dose_amt", "dose_unit",
    "dose_form", "dose_freq"
]

REAC_COLS = ["isr", "caseid", "pt"]
OUTC_COLS = ["isr", "caseid", "outc_cod"]


def load_ascii_file(filepath: Path, expected_cols: list) -> pd.DataFrame:
    """
    Load a single FAERS ASCII pipe-delimited file.

    Notes
    -----
    FAERS files are often latin-1 encoded, not UTF-8.
    Column counts vary slightly across quarterly versions — handle defensively.
    """
    # TODO: implement
    raise NotImplementedError


def load_quarter(quarter_dir: Path) -> dict:
    """
    Load all 7 ASCII files from a single FAERS quarterly directory.

    Returns dict with keys: 'demo', 'drug', 'reac', 'outc', 'rpsr', 'ther', 'indi'
    """
    # TODO: auto-detect file naming (varies by quarter year)
    raise NotImplementedError


def combine_quarters(quarter_dirs: list) -> dict:
    """
    Load and vertically concatenate multiple FAERS quarterly directories.
    Output is ready for deduplication.
    """
    # TODO: implement
    raise NotImplementedError
