"""
FAERS ASCII File Parser
------------------------
Ingests FDA Adverse Event Reporting System quarterly ASCII files into
normalized pandas DataFrames ready for deduplication and signal detection.

FAERS ASCII quarterly zips contain 7 pipe-delimited files:
    DEMO{YYQ#}.txt  — demographic/case header (1 row per report)
    DRUG{YYQ#}.txt  — drug records (N rows per report)
    REAC{YYQ#}.txt  — adverse reactions / MedDRA PT terms
    OUTC{YYQ#}.txt  — outcomes (death, hospitalization, etc.)
    RPSR{YYQ#}.txt  — report sources
    THER{YYQ#}.txt  — therapy start/end dates
    INDI{YYQ#}.txt  — drug indications

Usage:
    from pipeline.parse_faers import FAERSParser
    parser = FAERSParser("data/raw/2026Q1")
    demo, drug, reac, outc = parser.load_all()
"""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ── Column schemas (FDA FAERS ASCII format, current as of 2024+) ──────────────

DEMO_COLS = {
    "ISR":           str,   # legacy report ID (pre-2012)
    "CASE_ID":       str,   # primary case identifier
    "CASEVERSION":   str,   # version number — keep highest per CASE_ID
    "I_F_COD":       str,   # initial/follow-up flag: I or F
    "EVENT_DT":      str,   # event date (YYYYMMDD, often partial)
    "MFR_DT":        str,   # manufacturer receipt date
    "INIT_FDA_DT":   str,   # initial FDA receipt date
    "FDA_DT":        str,   # most recent FDA receipt date
    "REPT_COD":      str,   # report type: EXP, MFR, PER, etc.
    "MFR_NUM":       str,   # manufacturer report number
    "MFR_SNDR":      str,   # manufacturer sender name
    "AGE":           float, # patient age (numeric)
    "AGE_COD":       str,   # age unit: YR, MON, WK, DY, HR, DEC
    "AGE_GRPQ":      str,   # age group bucket
    "GNDR_COD":      str,   # sex: M, F, UNK, NS
    "E_SUB":         str,   # expedited submission flag
    "WT":            float, # patient weight
    "WT_COD":        str,   # weight unit: KG, LBS
    "REPT_DT":       str,   # report date
    "OCCP_COD":      str,   # reporter occupation: MD, PH, OT, LW, CN, etc.
    "DEATH_DT":      str,   # death date if applicable
    "TO_MFR":        str,   # report sent to manufacturer
    "PRIMARYID":     str,   # primary ID (post-2012, preferred key)
    "CASEID":        str,   # case ID (post-2012)
    "CASEVERSION_N": str,   # numeric version (post-2012)
}

DRUG_COLS = {
    "PRIMARYID":   str,   # links to DEMO
    "CASEID":      str,
    "DRUG_SEQ":    str,   # drug sequence number within case
    "ROLE_COD":    str,   # PS=primary suspect, SS=secondary suspect, C=concomitant, I=interacting
    "DRUGNAME":    str,   # as-reported drug name (messy)
    "PROD_AI":     str,   # active ingredient(s)
    "VAL_VBM":     str,   # verbatim drug name validation flag
    "ROUTE":       str,   # administration route
    "DOSE_VBM":    str,   # verbatim dose
    "CUM_DOSE_CHR":str,
    "CUM_DOSE_UNIT":str,
    "DECHAL":      str,   # dechallenge: positive/negative/unknown
    "RECHALLENGE": str,   # rechallenge result
    "LOT_NUM":     str,
    "EXP_DT":      str,
    "NDA_NUM":     str,   # NDA/ANDA number
    "DOSE_AMT":    str,
    "DOSE_UNIT":   str,
    "DOSE_FORM":   str,
    "DOSE_FREQ":   str,
}

REAC_COLS = {
    "PRIMARYID":  str,   # links to DEMO
    "CASEID":     str,
    "PT":         str,   # MedDRA Preferred Term (adverse event)
    "DRUG_REC_ACT": str, # drug reaction action taken
}

OUTC_COLS = {
    "PRIMARYID": str,
    "CASEID":    str,
    "OUTC_COD":  str,   # DE=death, LT=life-threatening, HO=hospitalized,
                        # DS=disability, CA=congenital anomaly, RI=required intervention, OT=other
}

INDI_COLS = {
    "PRIMARYID": str,
    "CASEID":    str,
    "DRUG_SEQ":  str,
    "INDI_PT":   str,   # MedDRA PT for indication
}


class FAERSParser:
    """
    Load and lightly clean one FAERS quarterly ASCII extract.

    Parameters
    ----------
    data_dir : str | Path
        Directory containing the extracted ASCII .txt files for one quarter.
        Expected naming: DEMO26Q1.txt, DRUG26Q1.txt, etc. (FDA convention).
        Pass the directory; the parser finds files by prefix.

    Examples
    --------
    >>> parser = FAERSParser("data/raw/2026Q1")
    >>> demo = parser.load_demo()
    >>> drug = parser.load_drug()
    >>> reac = parser.load_reac()
    """

    # FDA uses pipe delimiter in ASCII exports
    SEP = "$"  # NOTE: newer FAERS quarters use "$" not "|" — swap if load fails

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")
        self._file_map = self._find_files()

    def _find_files(self) -> dict[str, Path]:
        """
        Locate ASCII files by prefix (case-insensitive).
        FDA naming: DEMO26Q1.txt — prefix is the table name.
        """
        prefixes = ["DEMO", "DRUG", "REAC", "OUTC", "RPSR", "THER", "INDI"]
        file_map = {}
        for f in self.data_dir.iterdir():
            upper = f.name.upper()
            for prefix in prefixes:
                if upper.startswith(prefix) and f.suffix.upper() in (".TXT", ".CSV"):
                    file_map[prefix] = f
                    logger.info(f"Found {prefix}: {f.name}")
        missing = [p for p in ["DEMO", "DRUG", "REAC", "OUTC"] if p not in file_map]
        if missing:
            logger.warning(f"Missing core FAERS files: {missing}")
        return file_map

    def _load_table(
        self,
        prefix: str,
        dtype_map: dict,
        usecols: Optional[list] = None,
    ) -> pd.DataFrame:
        """Generic loader with fallback delimiter detection."""
        path = self._file_map.get(prefix)
        if path is None:
            raise FileNotFoundError(f"No {prefix} file found in {self.data_dir}")

        # Try "$" first (post-2014 FDA standard), fall back to "|"
        for sep in ["$", "|", "\t"]:
            try:
                df = pd.read_csv(
                    path,
                    sep=sep,
                    dtype=str,          # load everything as str first
                    encoding="latin-1", # FDA files use latin-1, not utf-8
                    on_bad_lines="warn",
                    low_memory=False,
                    usecols=usecols,
                )
                if df.shape[1] > 1:
                    logger.info(f"Loaded {prefix} with sep='{sep}': {df.shape}")
                    break
            except Exception as e:
                logger.debug(f"{prefix} sep='{sep}' failed: {e}")
                continue

        # Normalize column names
        df.columns = [c.strip().upper() for c in df.columns]

        # Cast numeric columns
        for col, typ in dtype_map.items():
            if col in df.columns and typ in (float, int):
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    # ── Public loaders ─────────────────────────────────────────────────────────

    def load_demo(self) -> pd.DataFrame:
        """
        Load demographic/case header table.
        One row per report version. Use after deduplication to get one row per case.
        """
        df = self._load_table("DEMO", DEMO_COLS)
        # Standardize primary key — post-2012 files use PRIMARYID, legacy use ISR
        if "PRIMARYID" not in df.columns and "ISR" in df.columns:
            df["PRIMARYID"] = df["ISR"]
            logger.warning("Legacy ISR format detected — mapped ISR → PRIMARYID")
        return df

    def load_drug(self) -> pd.DataFrame:
        """
        Load drug records. Multiple rows per case (one per drug).
        ROLE_COD='PS' = primary suspect drug — most useful for signal detection.
        """
        return self._load_table("DRUG", DRUG_COLS)

    def load_reac(self) -> pd.DataFrame:
        """
        Load adverse reaction records. Multiple rows per case (one per PT term).
        PT column contains MedDRA Preferred Terms.
        """
        return self._load_table("REAC", REAC_COLS)

    def load_outc(self) -> pd.DataFrame:
        """
        Load outcome records.
        OUTC_COD: DE=death, LT=life-threatening, HO=hospitalized,
                  DS=disability, CA=congenital anomaly, RI=required intervention
        """
        return self._load_table("OUTC", OUTC_COLS)

    def load_indi(self) -> pd.DataFrame:
        """Load drug indication records (what the drug was prescribed for)."""
        return self._load_table("INDI", INDI_COLS)

    def load_all(self) -> tuple[pd.DataFrame, ...]:
        """
        Load core 4 tables. Returns (demo, drug, reac, outc).
        Run deduplication on demo before joining.
        """
        logger.info("Loading all core FAERS tables...")
        return (
            self.load_demo(),
            self.load_drug(),
            self.load_reac(),
            self.load_outc(),
        )

    def summary(self) -> dict:
        """Quick record count summary across all loaded files."""
        counts = {}
        for prefix, path in self._file_map.items():
            try:
                # Fast line count without full load
                with open(path, "rb") as f:
                    counts[prefix] = sum(1 for _ in f) - 1  # minus header
            except Exception:
                counts[prefix] = "error"
        return counts
