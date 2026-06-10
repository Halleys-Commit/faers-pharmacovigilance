# faers-pharmacovigilance

FDA Adverse Event Reporting System (FAERS) mining pipeline for pharmacovigilance signal detection.

Parses public FAERS quarterly data, normalizes drug/adverse event terminology, and applies
disproportionality analysis to identify drug-AE safety signals — the same statistical framework
used by FDA and EMA for post-market surveillance.

## What this does

- **Ingests** FAERS bulk ASCII/XML quarterly files (publicly available from FDA)
- **Deduplicates** reports using FDA-recommended CASEID/ISR logic
- **Normalizes** drug names and MedDRA adverse event terms via NLP
- **Detects signals** using Reporting Odds Ratio (ROR), Proportional Reporting Ratio (PRR), and EBGM
- **Visualizes** signal landscapes, AE distributions, and time-to-onset profiles

## Motivation

FAERS contains millions of spontaneous adverse event reports. Raw signal is buried under noise —
duplicate reports, inconsistent drug naming, off-label confounder effects. This pipeline applies
the standard pharmacoepidemiological toolkit to surface real signals from that noise.

Longer-term direction: cross-reference detected signals against pharmacogenomic biomarkers
(PharmGKB, CPIC) to identify genotype-stratified AE risk — a gap in current surveillance practice.

## Repository structure

```
faers-pharmacovigilance/
├── data/                    # Download scripts only — no raw data committed
│   └── download_faers.py    # Fetches quarterly files from FDA
├── pipeline/
│   ├── parse_faers.py       # ASCII + XML ingestor, schema normalization
│   ├── deduplicate.py       # CASEID/ISR deduplication per FDA guidance
│   ├── extract_entities.py  # Drug name + AE term NLP normalization
│   └── signal_detection.py  # ROR, PRR, EBGM disproportionality analysis
├── notebooks/
│   └── signal_exploration.ipynb  # Interactive signal review
├── tests/
└── requirements.txt
```

## Data

All data sourced from [FDA FAERS public dashboard](https://www.fda.gov/drugs/questions-and-answers-fdas-adverse-event-reporting-system-faers/fda-adverse-event-reporting-system-faers-public-dashboard).
Quarterly ASCII files are free to download. No proprietary data is included in this repo.

## Setup

```bash
pip install -r requirements.txt
python data/download_faers.py --year 2023 --quarters Q1 Q2 Q3 Q4
```

## Status

🚧 Active development — pipeline scaffolded, core modules in progress.

## Skills demonstrated

`pandas` · `numpy` · `scipy` · `spacy` · `regex` · `NLP` · `pharmacovigilance` · `signal-detection` · `FDA-FAERS`
