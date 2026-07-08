# MRSA NLP — Rule-Based Pipeline

Regex and lexicon-driven extraction of MRSA clinical risk signals from
AIR.MS clinical notes.  Produces a visit-level binary feature matrix that
can be used directly for risk modelling or as a baseline for comparison
against the NER-based pipeline.

---

## Overview

This pipeline builds a subset of mined free-text clinical notes from `CDMPHI.NOTES`, applies
curated regex patterns for MRSA risk factors (corticosteroids, prior MRSA,
central lines, dialysis, immunosuppressants, …), handles negation using a
window-based NegEx heuristic, and aggregates the per-note signals to a
visit-level feature matrix labelled with the same case/control cohort used
by `mrsa_risk_predictions`.

---

## Dataflow

```
/sc/arion/projects/
  MRSA-HPI-MS/airms-app-host-and-hospital-adaptation-of-mrsa/
    mrsa_nlp/rule_based/
      data/interim/airms/notes/all/cohort_notes.parquet         ← shared cohort source (read-only)
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1 · Subset Builder  (src/cohort/subset_builder.py)        │
│                                                                 │
│  · Load cohort_notes.parquet                                    │
│  · Filter by PERSON_ID via optional CSV (PERSON_ID + LABEL)     │
│  · Filter by NOTE_TITLE (optional)                              │
│  · Save chunked parquet files to output directory               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
          data/interim/airms/notes/
            chunk_0000.parquet
            chunk_0001.parquet
            …
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2 · Note Preprocessor  (src/preprocessing/note_preprocessor.py) │
│                                                                 │
│  · Normalise whitespace / line breaks                           │
│  · Expand clinical abbreviations  (UTI→urinary tract infection) │
│  · Filter notes by length  (50 – 50,000 chars)                  │
│  · Deduplicate exact-duplicate notes within a visit             │
│  · Skip already-processed chunks (resume-safe)                  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
          data/interim/airms/notes_preprocessed/
            chunk_0000.parquet
            …
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3 · Rule Extractor  (src/extraction/)                     │
│                                                                 │
│  Lexicon (lexicons/mrsa_risk_factors_v1.csv)                    │
│    └─ LexiconEntry: keywords · abbreviations · ICD codes        │
│         · drug names · negation caveats                         │
│                                                                 │
│  NegationHandler                                                │
│    └─ window-based NegEx (5-token look-back)                    │
│       cues: no / not / without / denies / negative for / …      │
│       sentence-boundary aware                                   │
│                                                                 │
│  RuleExtractor                                                  │
│    └─ compile regex patterns from lexicon entries               │
│    └─ for each note: run patterns → filter negated matches      │
│    └─ produce binary  has_{factor}  and  count_{factor}  cols   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
          data/interim/airms/extractions/
            chunk_0000.parquet   (NOTE_ID | PERSON_ID | VISIT_OCCURRENCE_ID
            …                     | has_prior_mrsa | count_prior_mrsa | …)
                         │
                         ▼
┌────────────────────────────────────────────────────────────────┐
│  STEP 4 · Feature Aggregator  (src/features/feature_aggregator.py) │
│                                                                 │
│  · Aggregate per-note → visit level                             │
│      has_*   : MAX  (1 if any note in visit has the signal)     │
│      count_* : SUM  (total matches across notes in visit)       │
│  · Left-join with mrsa_cohort_person_list (adds LABEL + PERSON_ID)  │
│  · Fill missing features with 0                                 │
│  · Log case / control counts for verification                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
          outputs/feature_aggregation_YYYYMMDD-HHMMSS/
            rule_features_<timestamp>.csv      ← training-ready matrix
            rule_features_<timestamp>.parquet
            rule_feature_summary_<timestamp>.json
            config.yaml
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5 · Evaluator  (src/evaluation/evaluator.py)              │
│                                                                 │
│  · Feature prevalence by LABEL (cases vs controls)              │
│  · If gold standard CSV provided:                               │
│      precision / recall / F1 per risk factor                    │
│  · Plots: prevalence bar chart, metrics chart, label dist.      │
│  · Validation report: pass/fail vs target P ≥ 0.90, R ≥ 0.70    │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
          outputs/evaluation_YYYYMMDD-HHMMSS/
            evaluation/
              feature_prevalence.png
              metrics_by_factor.png       (if gold standard given)
              label_distribution.png
              ner_vs_rules_comparison.csv (if NER features given)
              validation_report.txt
```

---

## Project Structure

```
rule_based/
├── env/
│   └── environment.yml          # conda env: mrsa-nlp-rule (Python 3.11)
├── lexicons/
│   └── mrsa_risk_factors_v1.csv # 25 MRSA risk factors with keywords,
│                                #   ICD codes, drug names, negation notes
├── scripts/
│   ├── start_airms_tunnel.sh    # open SSH tunnel to db.airms.mssm.edu
│   ├── run_subset_builder.sh    # subset builder wrapper
│   ├── run_preprocessing.sh
│   ├── run_feature_extraction.sh
│   └── run_evaluation.sh
├── src/
│   ├── cli.py                   # Typer CLI entry point
│   ├── utils_logging.py         # configure_logging / log_timing / make_run_dir
│   ├── utils_db.py              # connect_hana() via .env
│   ├── utils_io.py              # read/write parquet + CSV helpers
│   ├── cohort/
│   │   └── subset_builder.py    # SubsetConfig + SubsetBuilder  (parquet filtering)
│   ├── preprocessing/
│   │   └── note_preprocessor.py # PreprocessorConfig + NotePreprocessor
│   ├── extraction/
│   │   ├── lexicon.py           # LexiconEntry + Lexicon
│   │   ├── negation_handler.py  # NegationConfig + NegationHandler
│   │   └── rule_extractor.py    # ExtractorConfig + RuleExtractor
│   ├── features/
│   │   └── feature_aggregator.py # AggregatorConfig + FeatureAggregator
│   ├── evaluation/
│   │   └── evaluator.py         # EvaluatorConfig + RuleEvaluator
│   └── statistics/
│       └── cohort_statistics.py # analysis and visualization
├── data/
│   └── interim/airms/
│       ├── notes/               # raw note chunks (mined from HANA)
│       ├── notes_preprocessed/  # cleaned note chunks
│       └── extractions/         # per-note feature chunks
├── outputs/                     # timestamped run directories, statistics output
├── .env.example                 # copy to .env and fill credentials
└── .gitignore
```

---

## Setup

### 1 — Create the conda environment

```bash
cd rule_based
conda env create -f env/environment.yml
conda activate mrsa-nlp-rule
```

### 2 — Subset builder (no database required)

`build-subset` reads from `cohort_notes.parquet`. No HANA connection is needed for this step.

```bash
bash scripts/run_subset_builder.sh
```

---

## Running the Pipeline

### Option A — step by step (recommended for first run)

```bash
conda activate mrsa-nlp-rule
cd rule_based

# Step 1: build note subset from cohort_notes.parquet
bash scripts/run_subset_builder.sh

# Step 2: preprocess notes
bash scripts/run_preprocessing.sh

# Steps 3+4: extract features and aggregate
bash scripts/run_feature_extraction.sh

# Step 5: evaluate
bash scripts/run_evaluation.sh outputs/feature_aggregation_<timestamp>/rule_features_<timestamp>.csv
```

### Option B — full pipeline in one command

```bash
python -m src.cli run-rule-pipeline --log-level INFO
```

### Debug mode (quick sanity check)

```bash
bash scripts/run_preprocessing.sh --debug
bash scripts/run_feature_extraction.sh --debug
```

---

## CLI Reference

```
python -m src.cli --help
```

```
 Usage: python -m src.cli [OPTIONS] COMMAND [ARGS]...

 MRSA NLP — rule-based clinical note extraction pipeline.

Options:
  --log-level TEXT  Logging level: DEBUG | INFO | WARNING | ERROR  [default: INFO]
  --help            Show this message and exit.

Commands:
  build-subset        Load MRSA cohort and filter by Patient ID and Note Type
  preprocess          Clean and normalise raw clinical note chunks
  extract             Run regex-based risk-signal extraction
  aggregate-features  Aggregate per-note extractions to visit-level matrix
  evaluate            Evaluate extraction quality and generate reports
  run-pipeline        Run the complete pipeline end-to-end
```

### `build-subset`

`SubsetBuilder` is used to filter `cohort_notes.parquet`; only cases are kept (`1`).

```bash
python -m src.cli build-subset \
    --notes-path          /sc/arion/projects/MRSA-HPI-MS/airms-app-host-and-hospital-adaptation-of-mrsa/
                            mrsa_nlp/rule_based/data/interim/airms/notes/all/cohort_notes.parquet \
    --cohort-csv-path     /sc/arion/projects/MRSA-HPI-MS/airms-app-host-and-hospital-adaptation-of-mrsa/
                            mrsa_nlp/rule_based/data/interim/airms/mrsa_cohort_person_list.csv \
    --selected-labels     "1" \
    --out-dir             data/interim/airms/notes \
    --chunk-size          1
```

| Option | Default | Description |
|---|---|---|
| `--notes-path` | `/sc/arion/projects/MRSA-HPI-MS/airms-app-host-and-hospital-adaptation-of-mrsa/mrsa_nlp/rule_based/data/interim/airms/notes/all/cohort_notes.parquet` | merged cohort notes |
| `--person-ids-csv-path` / `--cohort-csv-path` | `None` | optional person-ID filter CSV |
| `--selected-labels` | `"0,1"` / `"1"` | comma-separated labels to keep |
| `--out-dir` | `data/interim/airms/notes` | output directory |
| `--chunk-size` | `1` | rows per output parquet chunk |

### `preprocess`

```bash
python -m src.cli preprocess \
    --raw-notes-dir data/interim/airms/notes \
    --out-dir       data/interim/airms/notes_preprocessed \
    --lowercase \
    --expand-abbrev \
    --no-segment \
    --no-debug
```

### `extract`

```bash
python -m src.cli extract \
    --preprocessed-dir data/interim/airms/notes_preprocessed \
    --out-dir          data/interim/airms/extractions \
    --lexicon-path     lexicons/mrsa_risk_factors_v1.csv \
    --negation-window  5 \
    --no-debug
```

### `aggregate-features`

```bash
python -m src.cli aggregate-features \
    --extractions-dir data/interim/airms/extractions \
    --cohort-path     data/interim/airms/mrsa_cohort_person_list.csv \
    --level           visit \
    --no-debug
```

### `evaluate`

```bash
# Prevalence analysis only (no gold standard needed)
python -m src.cli evaluate \
    outputs/feature_aggregation_20250401-120000/rule_features_20250401-120000.csv

# With a manually annotated gold standard (100-note sample)
python -m src.cli evaluate \
    outputs/feature_aggregation_20250401-120000/rule_features_20250401-120000.csv \
    --gold-standard-path annotations/gold_standard_100notes.csv \
    --target-precision 0.90 \
    --target-recall    0.70
```

---

## Lexicon

`lexicons/mrsa_risk_factors_v1.csv` — 25 risk factors, columns:

| Column | Description |
|---|---|
| `risk_factor` | Machine-readable factor ID |
| `medical_context` | Plain-language description |
| `icd_codes` | Related ICD-10 codes (reference only) |
| `drug_names` | Specific drug names to match |
| `keywords` | Comma-separated regex-ready keywords |
| `abbreviations` | Common clinical abbreviations |
| `negation_caveats` | Patterns that should be excluded |

**Included risk factors:**

| Factor | Rationale |
|---|---|
| `prior_mrsa` | Strongest single predictor |
| `prior_staph` | Prior SA colonisation |
| `corticosteroid_use` | Immune suppression + skin barrier disruption |
| `immunosuppressant_use` | Anti-rejection and DMARD agents |
| `central_venous_catheter` | Primary bacteremia route (CLABSI) |
| `hemodialysis` | Vascular access infections |
| `peritoneal_dialysis` | Peritoneal access infection |
| `icu_admission` | High colonisation pressure |
| `mechanical_ventilation` | VAP risk |
| `surgical_procedure` | Skin integrity breach |
| `organ_transplant` | Lifelong immunosuppression |
| `bone_marrow_transplant` | Profound immunosuppression |
| `diabetes_mellitus` | Impaired immunity + wound healing |
| `chronic_kidney_disease` | Immune dysfunction |
| `hiv_aids` | CD4-mediated immunodeficiency |
| `hematologic_malignancy` | Neutropenia + immune dysregulation |
| `solid_malignancy` | Treatment-related immunosuppression |
| `prior_antibiotic_exposure` | Selects for resistant organisms |
| `snf_ltc_residence` | High MRSA colonisation environment |
| `wound_infection` | Direct portal of entry |
| `foley_catheter` | Bacteremia risk |
| `neutropenia` | Severely impaired innate immunity |
| `rheumatologic_disease` | Immunosuppressive therapy |
| `bacteremia` | Bloodstream infection evidence |
| `sepsis` | Systemic severity marker |

---

## Outputs

Each pipeline step writes to a timestamped directory:

```
outputs/
  build_cohort_20250401-090000/
    run.log
    config.yaml

  feature_aggregation_20250401-120000/
    rule_features_20250401-120000.csv        ← main output
    rule_features_20250401-120000.parquet
    rule_feature_summary_20250401-120000.json
    run.log
    config.yaml

  evaluation_20250401-130000/
    evaluation/
      feature_prevalence.png
      metrics_by_factor.png
      label_distribution.png
      validation_report.txt
    run.log
    config.yaml
```

`data/interim/airms/` (persistent, not inside outputs):

```
mrsa_cohort_person_list.csv         ← PERSON_ID | LABEL
notes/            chunk_0000.parquet … (raw, from HANA)
notes_preprocessed/ chunk_0000.parquet … (cleaned)
extractions/      chunk_0000.parquet … (per-note features)
```

---

## Negation Logic

The `NegationHandler` implements a simplified NegEx algorithm:

```
Negation cues (pre-compiled regex):
  no · not · without · denies · denied · negative for ·
  no evidence of · no sign of · ruled out · absent ·
  never · free of · unlikely · not consistent with

For each regex match at position [start, end]:
  1. Extract tokens in the window [start - window_tokens, start]
  2. Check if any negation cue regex matches that pre-window text
  3. If sentence-boundary mode: also check no sentence break in window
  4. Mark match as negated=True if a cue is found

Negated matches are excluded from has_* and count_* features.
```

---

## Key Design Decisions

- **Same cohort as `mrsa_risk_predictions`** — reads `mrsa_visit_cohort.parquet` directly; no cohort rebuild.
- **Resume-safe mining** — each chunk file is written atomically; the loop skips existing chunks on restart.
- **Chunked HANA queries** — 500 persons per batch; failed chunks write a `_FAILED.txt` sentinel without stopping the run.
- **Lowercase preprocessing** — appropriate for regex matching; case-folded before pattern application.
- **Aggregation level = visit** — MAX for binary features, SUM for counts; one row per `VISIT_OCCURRENCE_ID`.
- **Target thresholds** — precision ≥ 0.90, recall ≥ 0.70 (configurable via `--target-precision`, `--target-recall`).

---

## References

- Chapman WW et al. (2001). *A simple algorithm for identifying negated findings and diseases in discharge summaries.* Journal of Biomedical Informatics. — NegEx algorithm basis.
- Shivade C et al. (2014). *A review of approaches to identifying patient phenotype cohorts using electronic health records.* JAMIA. — Rule-based NLP phenotyping review.
- Horan TC et al. (2008). *CDC/NHSN surveillance definition of health care–associated infection.* — MRSA risk factor definitions.
- Liu S et al. (2012). *Clamp — a toolkit for efficiently building customized clinical NLP pipelines.* — Clinical NLP pipeline reference.
