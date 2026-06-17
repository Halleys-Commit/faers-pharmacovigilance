# drug-safety-signal-detection

FDA Adverse Event Reporting System (FAERS) mining pipeline for pharmacovigilance signal detection.

Parses public FAERS quarterly data, normalizes drug/adverse event terminology, and applies
disproportionality analysis to identify drug-AE safety signals — the same statistical framework
used by FDA and EMA for post-market surveillance.

## What this does

- **Ingests** FAERS bulk ASCII quarterly files (publicly available from FDA)
- **Deduplicates** reports using FDA-recommended CASEID/ISR logic across quarters
- **Normalizes** drug names and MedDRA adverse event terms
- **Detects signals** using Reporting Odds Ratio (ROR), Proportional Reporting Ratio (PRR), and EBGM
- **Visualizes** signal landscapes, AE distributions, volcano plots, and time-to-onset profiles

## Motivation

FAERS contains millions of spontaneous adverse event reports. Raw signal is buried under noise —
duplicate reports, inconsistent drug naming, off-label confounder effects. This pipeline applies
the standard pharmacoepidemiological toolkit to surface real signals from that noise.

## Repository structure

```
drug-safety-signal-detection/
├── run_pipeline.py              # Incremental orchestrator: download → deduplicate → detect → visualize
├── pipeline/
│   ├── parse_faers.py           # ASCII ingestor, schema normalization
│   ├── deduplicate.py           # CASEID/ISR deduplication per FDA guidance
│   ├── extract_entities.py      # Drug name + AE term normalization
│   └── signal_detection.py      # ROR, PRR, EBGM disproportionality analysis
├── notebooks/
│   ├── 01_quickstart.py         # Single-quarter walkthrough (load → deduplicate → detect)
│   ├── 02_signal_visualization.ipynb   # Per-drug signal landscape: volcano, forest, trends
│   └── 03_master_visualization.ipynb   # Aggregate views across all quarters
├── data/                        # Gitignored — downloaded automatically by run_pipeline.py
│   ├── raw/                     # FAERS quarterly ASCII files (2024Q2 – 2026Q1)
│   ├── master/                  # Deduplicated multi-quarter parquet dataset
│   └── figures/                 # Exported plots
└── requirements.txt
```

## Data

All data sourced from [FDA FAERS public dashboard](https://www.fda.gov/drugs/questions-and-answers-fdas-adverse-event-reporting-system-faers/fda-adverse-event-reporting-system-faers-public-dashboard).
Quarterly ASCII files are free to download. No proprietary data is included in this repo.
Current local dataset: **2024Q2 – 2026Q1** (8 quarters, rolling window).

## Setup

```bash
pip install -r requirements.txt

# Download missing quarters, build master dataset, run signal detection
python run_pipeline.py

# Options
python run_pipeline.py --download-only   # fetch new quarters only
python run_pipeline.py --analyze-only    # rerun analysis on existing data
python run_pipeline.py --status          # show which quarters are available locally
```

## Skills demonstrated

`pandas` · `numpy` · `scipy` · `spacy` · `matplotlib` · `seaborn` · `plotly` · `pharmacovigilance` · `signal-detection` · `FDA-FAERS`
