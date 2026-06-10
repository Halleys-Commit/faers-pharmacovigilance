"""
FAERS Case Deduplication
-------------------------
FDA FAERS contains duplicate and amended reports for the same adverse event.
Each case gets a CASEID; follow-up amendments increment CASEVERSION.

FDA recommendation: keep only the highest CASEVERSION per CASEID.
Additional heuristic: flag suspect duplicates across manufacturers
(same patient demographics + event date + drug + AE from different reporters).

Usage:
    from pipeline.deduplicate import deduplicate_cases
    demo_deduped = deduplicate_cases(demo_df)
"""

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def deduplicate_cases(demo: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only the most recent version of each case.

    FDA standard method: for each CASEID, retain the row with the
    highest numeric CASEVERSION. This removes superseded follow-up reports.

    Parameters
    ----------
    demo : pd.DataFrame
        Raw DEMO table from FAERSParser.load_demo()

    Returns
    -------
    pd.DataFrame
        One row per unique CASEID — latest version only.
        Shape will be <= input shape.
    """
    before = len(demo)

    # Coerce version to numeric for proper max() — some files have leading zeros
    demo = demo.copy()
    demo["_version_num"] = pd.to_numeric(demo.get("CASEVERSION", demo.get("CASEVERSION_N", 0)), errors="coerce").fillna(0)

    # Keep highest version per case
    key_col = "CASEID" if "CASEID" in demo.columns else "CASE_ID"
    deduped = (
        demo.sort_values("_version_num", ascending=False)
            .drop_duplicates(subset=[key_col], keep="first")
            .drop(columns=["_version_num"])
            .reset_index(drop=True)
    )

    after = len(deduped)
    logger.info(f"Deduplication: {before:,} rows → {after:,} unique cases ({before - after:,} follow-ups removed)")
    return deduped


def flag_manufacturer_duplicates(
    demo: pd.DataFrame,
    drug: pd.DataFrame,
    reac: pd.DataFrame,
    age_tolerance: float = 2.0,
) -> pd.DataFrame:
    """
    Heuristic cross-manufacturer duplicate detection.

    Same adverse event reported by multiple sources (manufacturer + consumer)
    creates distinct CASEIDs for the same real-world event. This flags
    likely duplicates using a fingerprint of: age + sex + event date + drug + AE.

    Parameters
    ----------
    demo : pd.DataFrame
        Deduplicated DEMO table.
    drug : pd.DataFrame
        DRUG table filtered to primary suspect (ROLE_COD == 'PS').
    reac : pd.DataFrame
        REAC table.
    age_tolerance : float
        Age difference (years) within which two reports may be the same patient.

    Returns
    -------
    pd.DataFrame
        demo with added column `SUSPECT_DUPLICATE` (bool) and
        `DUP_GROUP_ID` (shared int for suspected duplicate sets).

    Notes
    -----
    This is a heuristic flag — do not drop these rows automatically.
    Use for sensitivity analysis: run signal detection with and without
    suspected duplicates to assess impact.
    """
    demo = demo.copy()
    demo["SUSPECT_DUPLICATE"] = False
    demo["DUP_GROUP_ID"] = pd.NA

    key_col = "CASEID" if "CASEID" in demo.columns else "CASE_ID"

    # Build fingerprint: primary suspect drug + first reaction PT + age bucket + sex + event date
    ps_drugs = drug[drug.get("ROLE_COD", pd.Series()) == "PS"].groupby("PRIMARYID")["DRUGNAME"].first().reset_index()
    first_reac = reac.groupby("PRIMARYID")["PT"].first().reset_index()

    merged = demo.merge(ps_drugs, on="PRIMARYID", how="left")
    merged = merged.merge(first_reac, on="PRIMARYID", how="left")

    # Normalize drug name for matching (uppercase, strip spaces)
    merged["_drug_norm"] = merged["DRUGNAME"].str.upper().str.strip() if "DRUGNAME" in merged else ""
    merged["_pt_norm"] = merged["PT"].str.upper().str.strip() if "PT" in merged else ""
    merged["_age_bucket"] = (pd.to_numeric(merged.get("AGE"), errors="coerce") // age_tolerance * age_tolerance)

    fingerprint_cols = ["_drug_norm", "_pt_norm", "_age_bucket", "SEX", "EVENT_DT"]
    available = [c for c in fingerprint_cols if c in merged.columns]

    if len(available) < 3:
        logger.warning("Insufficient columns for duplicate fingerprinting — skipping")
        return demo

    dup_groups = merged.groupby(available, dropna=False)[key_col].transform("count")
    suspect_mask = dup_groups > 1

    group_ids = merged.groupby(available, dropna=False).ngroup()
    demo.loc[suspect_mask.values, "SUSPECT_DUPLICATE"] = True
    demo.loc[suspect_mask.values, "DUP_GROUP_ID"] = group_ids[suspect_mask].values

    n_flagged = suspect_mask.sum()
    logger.info(f"Flagged {n_flagged:,} suspect cross-manufacturer duplicates ({n_flagged/len(demo)*100:.1f}%)")
    return demo
