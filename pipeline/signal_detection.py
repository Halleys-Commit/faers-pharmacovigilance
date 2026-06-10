"""
Pharmacovigilance Signal Detection
------------------------------------
Implements the three standard disproportionality analysis methods used by
FDA, EMA, and industry for post-market safety signal detection from
spontaneous adverse event reporting systems (FAERS, VAERS, EudraVigilance).

Methods implemented:
    - ROR  : Reporting Odds Ratio  (EMA standard)
    - PRR  : Proportional Reporting Ratio  (FDA / MHRA standard)
    - EBGM : Empirical Bayes Geometric Mean  (FDA MGPS algorithm)

Each method answers: "Is drug X reported with AE Y more than expected
by chance, given everything else reported in the database?"

Usage:
    from pipeline.signal_detection import SignalDetector
    detector = SignalDetector(drug_df, reac_df)
    signals = detector.run_all(drug_name="WARFARIN", min_reports=3)
    print(signals.sort_values("ROR", ascending=False).head(20))
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)


class SignalDetector:
    """
    Compute disproportionality signals for a target drug against the full FAERS background.

    Parameters
    ----------
    drug : pd.DataFrame
        DRUG table (post-dedup). Must have PRIMARYID, DRUGNAME (or PROD_AI), ROLE_COD.
    reac : pd.DataFrame
        REAC table (post-dedup). Must have PRIMARYID, PT.
    drug_col : str
        Column to use for drug identification. Default 'PROD_AI' (active ingredient,
        more consistent than DRUGNAME). Use 'DRUGNAME' if PROD_AI is sparse.
    suspect_only : bool
        If True (default), restrict to primary suspect drugs (ROLE_COD == 'PS').
        Set False to include concomitant/secondary suspect — widens net but adds noise.
    """

    def __init__(
        self,
        drug: pd.DataFrame,
        reac: pd.DataFrame,
        drug_col: str = "PROD_AI",
        suspect_only: bool = True,
    ):
        self.drug_col = drug_col if drug_col in drug.columns else "DRUGNAME"
        if suspect_only and "ROLE_COD" in drug.columns:
            drug = drug[drug["ROLE_COD"] == "PS"]

        # Normalize drug names
        drug = drug.copy()
        drug["_drug"] = drug[self.drug_col].str.upper().str.strip()
        reac = reac.copy()
        reac["_pt"] = reac["PT"].str.upper().str.strip()

        # Core co-occurrence table: one row per (case, drug, PT) combination
        self._pairs = drug[["PRIMARYID", "_drug"]].merge(
            reac[["PRIMARYID", "_pt"]], on="PRIMARYID", how="inner"
        )
        self._N = self._pairs["PRIMARYID"].nunique()  # total cases in database
        logger.info(f"SignalDetector initialized: {self._N:,} cases, {len(self._pairs):,} drug-AE pairs")

    def _contingency(self, drug_name: str, pt_term: str) -> tuple[int, int, int, int]:
        """
        Build 2x2 contingency table for one drug-AE pair.

        Returns (a, b, c, d) where:
            a = reports with drug AND AE       (target cell)
            b = reports with drug, WITHOUT AE
            c = reports WITHOUT drug, WITH AE
            d = reports without drug AND without AE
        """
        drug_cases = set(self._pairs[self._pairs["_drug"] == drug_name]["PRIMARYID"])
        ae_cases   = set(self._pairs[self._pairs["_pt"]   == pt_term   ]["PRIMARYID"])

        a = len(drug_cases & ae_cases)
        b = len(drug_cases) - a
        c = len(ae_cases)   - a
        d = self._N - a - b - c
        return a, b, c, d

    def _build_counts_table(self, drug_name: str) -> pd.DataFrame:
        """
        Compute contingency counts for ALL AEs reported with a given drug.
        Vectorized — much faster than calling _contingency() in a loop.
        """
        drug_cases = set(self._pairs[self._pairs["_drug"] == drug_name]["PRIMARYID"])
        n_drug = len(drug_cases)

        if n_drug == 0:
            logger.warning(f"Drug '{drug_name}' not found. Check spelling/normalization.")
            return pd.DataFrame()

        # All AEs co-reported with this drug
        drug_reac = self._pairs[self._pairs["_drug"] == drug_name].groupby("_pt")["PRIMARYID"].nunique().rename("a")

        # All AEs in full database
        all_reac = self._pairs.groupby("_pt")["PRIMARYID"].nunique().rename("ae_total")

        counts = drug_reac.reset_index().merge(all_reac.reset_index(), on="_pt")
        counts["b"] = n_drug - counts["a"]           # drug, no AE
        counts["c"] = counts["ae_total"] - counts["a"]  # AE, no drug
        counts["d"] = self._N - n_drug - counts["c"]    # neither
        counts["n_drug_total"] = n_drug
        counts["N"] = self._N
        return counts.rename(columns={"_pt": "PT"})

    # ── Signal methods ─────────────────────────────────────────────────────────

    def ror(self, counts: pd.DataFrame) -> pd.DataFrame:
        """
        Reporting Odds Ratio (ROR) with 95% CI.

        ROR = (a/b) / (c/d) = (a*d) / (b*c)
        Signal threshold: ROR lower 95% CI > 1.0

        EMA standard method. Analogous to case-control OR.
        Tends to inflate for drugs with many reports (Rawlins bias).
        """
        df = counts.copy()
        df["ROR"] = (df["a"] * df["d"]) / (df["b"] * df["c"])

        # Log-scale CI via delta method
        df["_se_log"] = np.sqrt(1/df["a"] + 1/df["b"] + 1/df["c"] + 1/df["d"])
        df["ROR_CI_lo"] = np.exp(np.log(df["ROR"]) - 1.96 * df["_se_log"])
        df["ROR_CI_hi"] = np.exp(np.log(df["ROR"]) + 1.96 * df["_se_log"])
        df["ROR_signal"] = df["ROR_CI_lo"] > 1.0

        return df.drop(columns=["_se_log"])

    def prr(self, counts: pd.DataFrame) -> pd.DataFrame:
        """
        Proportional Reporting Ratio (PRR) with 95% CI and chi-squared.

        PRR = [a/(a+b)] / [c/(c+d)]
        Signal threshold (MHRA): PRR >= 2, chi2 >= 4, a >= 3

        FDA/MHRA standard. Easier to interpret than ROR but more sensitive
        to common drugs (many background reports of the same AE).
        """
        df = counts.copy()
        df["PRR"] = (df["a"] / (df["a"] + df["b"])) / (df["c"] / (df["c"] + df["d"]))

        df["_se_log"] = np.sqrt(1/df["a"] - 1/(df["a"]+df["b"]) + 1/df["c"] - 1/(df["c"]+df["d"]))
        df["PRR_CI_lo"] = np.exp(np.log(df["PRR"]) - 1.96 * df["_se_log"])
        df["PRR_CI_hi"] = np.exp(np.log(df["PRR"]) + 1.96 * df["_se_log"])

        # Chi-squared test (Pearson)
        def chi2_p(row):
            table = [[row["a"], row["b"]], [row["c"], row["d"]]]
            try:
                chi2, p, _, _ = stats.chi2_contingency(table, correction=False)
                return chi2, p
            except Exception:
                return np.nan, np.nan

        chi_results = df.apply(chi2_p, axis=1, result_type="expand")
        df["PRR_chi2"] = chi_results[0]
        df["PRR_p"] = chi_results[1]

        # MHRA signal criteria
        df["PRR_signal"] = (df["PRR"] >= 2) & (df["PRR_chi2"] >= 4) & (df["a"] >= 3)

        return df.drop(columns=["_se_log"])

    def ebgm(self, counts: pd.DataFrame) -> pd.DataFrame:
        """
        Empirical Bayes Geometric Mean (EBGM) — simplified single-term approximation.

        EBGM shrinks extreme ROR estimates toward the prior (database average),
        stabilizing signals from drug-AE pairs with few reports.

        Full FDA MGPS uses a two-term mixture prior (DuMouchel 1999). This
        implementation uses the simplified single-prior version sufficient for
        exploratory analysis. For production use, implement DuMouchel's EM algorithm.

        Signal threshold: EB05 (5th percentile of EB posterior) > 2.0

        Reference: DuMouchel W (1999). Bayesian Data Mining in Large Frequency Tables.
        The American Statistician, 53(2), 177–190.
        """
        df = counts.copy()

        # Expected count under independence
        df["E"] = (df["a"] + df["b"]) * (df["a"] + df["c"]) / df["N"]
        df["E"] = df["E"].clip(lower=1e-6)

        # Observed/expected ratio (raw, = simplified EBGM without shrinkage)
        df["IC"] = np.log2((df["a"] + 0.5) / (df["E"] + 0.5))  # Information Component (IC, WHO-UMC)

        # Simplified EBGM: shrink toward prior mean = 1 using pseudo-count alpha=0.5
        # Full DuMouchel MGPS requires fitting mixture prior via EM — implement separately
        alpha = 0.5
        df["EBGM"] = (df["a"] + alpha) / (df["E"] + alpha)

        # Approximate 90% CI via Poisson gamma (simplified)
        df["EB05"] = np.exp(
            np.log(df["EBGM"]) - 1.645 * np.sqrt(1 / (df["a"] + alpha))
        )
        df["EB95"] = np.exp(
            np.log(df["EBGM"]) + 1.645 * np.sqrt(1 / (df["a"] + alpha))
        )
        df["EBGM_signal"] = df["EB05"] > 2.0

        return df

    # ── Main interface ─────────────────────────────────────────────────────────

    def run_all(
        self,
        drug_name: str,
        min_reports: int = 3,
        signal_any: bool = True,
    ) -> pd.DataFrame:
        """
        Run ROR + PRR + EBGM for all AEs co-reported with drug_name.

        Parameters
        ----------
        drug_name : str
            Drug name as it appears in PROD_AI or DRUGNAME (uppercase).
            Partial matching not supported — normalize first if needed.
        min_reports : int
            Minimum co-reports (a >= min_reports) to include in output.
            FDA convention: exclude pairs with < 3 reports.
        signal_any : bool
            If True, filter output to rows where at least one method flags a signal.
            Set False to return full table.

        Returns
        -------
        pd.DataFrame
            One row per AE, columns: PT, a, ROR, ROR_CI_lo, ROR_CI_hi, ROR_signal,
            PRR, PRR_chi2, PRR_signal, EBGM, EB05, EBGM_signal, SIGNAL_COUNT
        """
        drug_name = drug_name.upper().strip()
        counts = self._build_counts_table(drug_name)
        if counts.empty:
            return pd.DataFrame()

        counts = counts[counts["a"] >= min_reports]
        if counts.empty:
            logger.warning(f"No AEs with >= {min_reports} reports for '{drug_name}'")
            return pd.DataFrame()

        # Apply all three methods
        result = self.ror(counts)
        result = self.prr(result)
        result = self.ebgm(result)

        # Summary signal count (0–3)
        result["SIGNAL_COUNT"] = (
            result["ROR_signal"].astype(int) +
            result["PRR_signal"].astype(int) +
            result["EBGM_signal"].astype(int)
        )

        if signal_any:
            result = result[result["SIGNAL_COUNT"] > 0]

        keep_cols = [
            "PT", "a", "N",
            "ROR", "ROR_CI_lo", "ROR_CI_hi", "ROR_signal",
            "PRR", "PRR_chi2", "PRR_p", "PRR_signal",
            "EBGM", "EB05", "EB95", "IC", "EBGM_signal",
            "SIGNAL_COUNT",
        ]
        keep_cols = [c for c in keep_cols if c in result.columns]

        return result[keep_cols].sort_values("SIGNAL_COUNT", ascending=False).reset_index(drop=True)
