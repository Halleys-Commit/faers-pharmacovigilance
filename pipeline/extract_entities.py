"""
Drug Name & Adverse Event Term Normalization
---------------------------------------------
FAERS drug names are free-text and wildly inconsistent:
  "ASPIRIN", "aspirin 81mg", "Aspirin EC", "acetylsalicylic acid", "ASA"
  → all refer to the same compound

Similarly, AE terms may be entered as verbatim text (VERBATIM_TERM)
before or instead of MedDRA Preferred Terms (PT).

This module normalizes both to support reliable signal detection.

Approaches
----------
Drug normalization:
  - Lowercase + strip dose/route suffixes via regex
  - Map to RxNorm CUI via RxNorm API or local lookup table
  - Optional: map to ATC codes for class-level analysis

AE normalization:
  - REAC.pt is already MedDRA PT — validate against MedDRA hierarchy
  - Map PT → Higher Level Term (HLT) → System Organ Class (SOC)
    for grouped/aggregate signal analysis

NLP (future):
  - Named entity recognition on free-text INDI and narrative fields
  - Model: spaCy + scispaCy (en_ner_bc5cdr_md) for drug/disease NER
"""

import re
import pandas as pd


# Common suffixes to strip from drug names before normalization
DOSE_PATTERNS = re.compile(
    r"\s+\d+(\.\d+)?\s*(mg|mcg|g|ml|mg/ml|%|iu|units?)\b",
    flags=re.IGNORECASE
)

ROUTE_PATTERNS = re.compile(
    r"\b(oral|iv|sc|im|topical|inhaled?|sublingual|transdermal)\b",
    flags=re.IGNORECASE
)


def normalize_drugname(name: str) -> str:
    """
    Basic normalization: lowercase, strip dose/route suffixes, strip whitespace.

    Parameters
    ----------
    name : str
        Raw drug name from FAERS DRUG table

    Returns
    -------
    str
        Normalized drug name string
    """
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    name = DOSE_PATTERNS.sub("", name)
    name = ROUTE_PATTERNS.sub("", name)
    return name.strip()


def normalize_drug_column(drug_df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply normalize_drugname to the full DRUG table.
    Adds 'drugname_norm' column alongside original 'drugname'.
    """
    # TODO: implement + add RxNorm lookup option
    raise NotImplementedError


def map_pt_to_soc(reac_df: pd.DataFrame, meddra_llt_path: str = None) -> pd.DataFrame:
    """
    Map MedDRA Preferred Terms to System Organ Classes.

    Requires a local MedDRA hierarchy file (meddra_llt.asc or similar).
    MedDRA is licensed — users must supply their own copy.

    Parameters
    ----------
    reac_df : pd.DataFrame
        REAC table with 'pt' column (MedDRA Preferred Terms)
    meddra_llt_path : str, optional
        Path to MedDRA LLT hierarchy file

    Returns
    -------
    pd.DataFrame
        REAC table with added 'hlt', 'hlgt', 'soc' columns
    """
    # TODO: implement hierarchy mapping
    # Note: MedDRA is a licensed terminology — document this requirement clearly
    raise NotImplementedError


def extract_ner_entities(text_series: pd.Series, model: str = "en_ner_bc5cdr_md") -> pd.DataFrame:
    """
    Run spaCy NER on free-text fields (INDI narratives, verbatim AE terms).

    Extracts CHEMICAL and DISEASE entities using the BC5CDR model.
    Requires: pip install scispacy && pip install [model URL]

    Parameters
    ----------
    text_series : pd.Series
        Series of free-text strings to process
    model : str
        scispaCy model name

    Returns
    -------
    pd.DataFrame
        DataFrame with columns: ['index', 'text', 'entity', 'label', 'start', 'end']
    """
    # TODO: implement — batch processing for performance
    raise NotImplementedError
