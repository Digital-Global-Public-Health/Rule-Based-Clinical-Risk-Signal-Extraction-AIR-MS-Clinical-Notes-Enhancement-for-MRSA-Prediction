# MRSA NLP — Rule-Based Pipeline

Regex and lexicon-driven extraction of MRSA risk signals from
AIR.MS clinical notes.  Produces a person- or visit-level binary feature matrix that
can be used directly for risk modelling or as a baseline for comparison
against the NER-based pipeline.

---

## Overview

This pipeline builds a subset of free-text clinical notes from `CDMPHI.NOTES`, applies
curated regex patterns for MRSA risk factors (corticosteroids, prior MRSA,
central lines, dialysis, immunosuppressants, …), handles negation using a
window-based NegEx heuristic, and aggregates the per-note signals to a
person- or visit-level feature matrix labelled with the same case/control cohort used
by `mrsa_risk_predictions`. Extraction quality can be validated against a manually
annotated **gold standard**, which is built interactively from a sample of the same
notes (see [Gold-Standard Annotation](#gold-standard-annotation)).

Related documents:

- [`RULES.md`](RULES.md) — detailed reference (rationale, matches, limitations,
  false positives, example matches) for every risk factor in the lexicon.
- [`DATA_DICTIONAIRY.md`](DATA_DICTIONAIRY.md) — column-by-column reference for the
  output feature matrix.
- [`lessons_learned.md`](lessons_learned.md) — methodological strengths/limitations
  of the rule-based approach and how clinicians should interpret its output.
- [`CHANGELOG.md`](CHANGELOG.md) — version history of the lexicon and pipeline.

---

## Dataflow

```
/sc/arion/projects/
  MRSA-HPI-MS/airms-app-host-and-hospital-adaptation-of-mrsa/
    mrsa_nlp/rule_based/
      data/interim/airms/notes/all/
        cohort_notes.parquet         ← shared cohort source (read-only)
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1 · Subset Builder  (src/cohort/subset_builder.py)        │
│                                                                 │
│  · Load cohort_notes.parquet                                    │
│  · Filter by PERSON_ID via optional CSV (PERSON_ID + LABEL)     │
│  · Filter by NOTE_TITLE (optional).                             │
│  · Filter by the amount of notes per type & person (optional)   │
│  · Save chunked parquet files to output directory               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
          data/interim/airms/notes/
            chunk_0000.parquet
            chunk_0001.parquet
            …
                         │
        (optional, in parallel) ──────────────────────────────────────────┐
                         │                                                ▼
                         │                       ┌────────────────────────────────────────────────┐
                         │                       │  STEP 1b · Gold-Standard Builder (interactive) │
                         │                       │  (src/annotation/gold_standard_builder.py)     │
                         │                       │  NOT part of run-rule-pipeline                 │
                         │                       │                                                │
                         │                       │  · Print each raw note to stdout               │
                         │                       │  · Open a per-note has_{factor} checklist in   │
                         │                       │    $EDITOR (one line per lexicon risk factor)  │
                         │                       │  · Resume-safe: skips notes that have a checklist│
                         │                       │  · Merge checklists → aggregate to visit/person│
                         │                       └────────────────────┬───────────────────────────┘
                         │                                            ▼
                         │                       data/annotations/checklists/note_<NOTE_ID>.txt
                         │                       data/annotations/gold_standard.csv
                         │                                            │
                         │                     (fed into STEP 5 evaluate via --gold-standard-path)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2 · Note Preprocessor                                     │
│           (src/preprocessing/note_preprocessor.py)              │
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
│  Lexicon (lexicons/mrsa_risk_factors_v3.csv)                    │
│    └─ LexiconEntry: keywords · abbreviations · ICD codes        │
│         · drug names · negation caveats                         │
│                                                                 │
│  NegationHandler                                                │
│    └─ window-based NegEx (5-token look-back/look-ahead)         │
│       pre-cues: no / not / without / denies / negative for / …  │
│       post-cues: not / no / denied / ruled out / doubt / …      │
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
            chunk_0000.parquet   
              (NOTE_ID | PERSON_ID | VISIT_OCCURRENCE_ID
                … | has_prior_mrsa | count_prior_mrsa | …)
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4 · Feature Aggregator                                    │
│           (src/features/feature_aggregator.py)                  │
│                                                                 │
│  · Aggregate per-note → person level (default) or visit level   │
│      has_*   : MAX  (1 if any note in scope has the signal)     │
│      count_* : SUM  (total matches across notes in scope)       │
│  · Left-join with mrsa_cohort_person_list                       │
│      (adds LABEL + PERSON_ID)                                   │
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
              validation_report.txt
```

---

## Project Structure

```
rule_based/
├── README.md                    # this file — pipeline overview & usage
├── RULES.md                     # per-risk-factor reference (rationale, matches,
│                                 #   known limitations, false positives, examples)
├── DATA_DICTIONAIRY.md          # column-by-column reference for the output matrix
├── CHANGELOG.md                 # lexicon / pipeline version history
├── lessons_learned.md           # what worked, what didn't, how to interpret output
├── requirements.txt
├── env/
│   └── environment.yml          # conda env: mrsa-nlp-rule (Python 3.10)
├── lexicons/
│   ├── mrsa_risk_factors_v1.csv # lexicon version history (v1 → v3)
│   ├── mrsa_risk_factors_v2.csv
│   └── mrsa_risk_factors_v3.csv # current: 47 entries (36 risk factors +
│                                 #   11 lab-value/severity markers)
├── scripts/
│   ├── run_subset_builder.sh
│   ├── run_preprocessing.sh 
│   ├── run_feature_extraction.sh
│   └── run_evaluation.sh
├── src/
│   ├── cli.py                   # Typer CLI entry point
│   ├── utils_logging.py         # configure_logging / log_timing / make_run_dir
│   ├── utils_io.py              # read/write parquet + CSV helpers
│   ├── utils_seed.py            # seed management for reproducibility
│   ├── cohort/
│   │   └── subset_builder.py    # SubsetConfig + SubsetBuilder  (parquet filtering)
│   ├── annotation/
│   │   └── gold_standard_builder.py # GoldStandardConfig + GoldStandardBuilder
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
├── data/
│   ├── interim/airms/
│   │   ├── notes/               # raw note chunks
│   │   ├── notes_preprocessed/  # cleaned note chunks
│   │   └── extractions/         # per-note feature chunks
│   └── annotations/             # gold-standard annotation working files
├── outputs/                     # timestamped run directories, statistics output
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
  build-subset            Load MRSA cohort and filter by Patient ID and Note Type
  annotate-gold-standard  Interactively annotate a note subset to build a gold-standard CSV
  preprocess              Clean and normalise raw clinical note chunks
  extract                 Run regex-based risk-signal extraction
  aggregate-features      Aggregate per-note extractions to a visit- or person-level matrix
  evaluate                Evaluate extraction quality and generate reports
  run-rule-pipeline       Run the complete pipeline end-to-end (excludes annotate-gold-standard)
```

### `build-subset`

`SubsetBuilder` is used to filter `cohort_notes.parquet`.

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

### `annotate-gold-standard`

Interactive annotation of a note sample, used to compute
precision/recall for `evaluate`.

```bash
python -m src.cli annotate-gold-standard \
    --input-dir         data/interim/airms/notes \
    --lexicon-path      lexicons/mrsa_risk_factors_v3.csv \
    --aggregation-level person \
    --checklist-dir     data/annotations/checklists \
    --output-file       data/annotations/gold_standard.csv
```

| Option | Default | Description |
|---|---|---|
| `--input-dir` | `data/interim/airms/notes` | raw note chunk directory to annotate (typically a small subset built via `build-subset`) |
| `--lexicon-path` | `lexicons/mrsa_risk_factors_v3.csv` | lexicon whose risk factors become the checklist items |
| `--aggregation-level` | `person` | `visit` or `person`; must match the `evaluate` run it will be compared against |
| `--checklist-dir` | `data/annotations/checklists` | per-note working checklist files (`note_<NOTE_ID>.txt`) |
| `--output-file` | `data/annotations/gold_standard.csv` | merged, aggregated gold-standard CSV |
| `--editor` | `$EDITOR`, else `vi` | command used to open each checklist |
| `--force-reannotate` | `False` | reopen checklists that already exist instead of skipping them |

### `preprocess`

```bash
python -m src.cli preprocess \
    --raw-notes-dir data/interim/airms/notes \
    --out-dir       data/interim/airms/notes_preprocessed \
    --lowercase \
    --expand-abbrev \
    --no-debug
```

| Option | Default | Description |
|---|---|---|
| `--raw-notes-dir` | `data/interim/airms/notes` | directory of raw note chunk Parquet files |
| `--out-dir` | `data/interim/airms/notes_preprocessed` | directory for preprocessed note chunks |
| `--lowercase` / `--no-lowercase` | `--lowercase` | lowercase note text |
| `--expand-abbrev` / `--no-expand-abbrev` | `--expand-abbrev` | expand clinical abbreviations |
| `--debug` / `--no-debug` | `--no-debug` | run on a debug subset of notes |
| `--debug-n-notes` | `200` | number of notes to process when `--debug` is set |

### `extract`

```bash
python -m src.cli extract \
    --preprocessed-dir data/interim/airms/notes_preprocessed \
    --out-dir          data/interim/airms/extractions \
    --lexicon-path     lexicons/mrsa_risk_factors_v3.csv \
    --negation-window  5 \
    --no-debug
```

| Option | Default | Description |
|---|---|---|
| `--preprocessed-dir` | `data/interim/airms/notes_preprocessed` | directory of preprocessed note chunk Parquet files |
| `--out-dir` | `data/interim/airms/extractions` | directory for extraction result chunks |
| `--lexicon-path` | `lexicons/mrsa_risk_factors_v3.csv` | path to the risk factor lexicon CSV |
| `--negation-window` | `5` | negation look-back window (tokens) |
| `--no-negation` | `False` | disable negation filtering |
| `--save-spans` | `False` | store matched text spans |
| `--debug` / `--no-debug` | `--no-debug` | run on a debug subset of notes |
| `--debug-n-notes` | `200` | number of notes to process when `--debug` is set |

### `aggregate-features`

```bash
python -m src.cli aggregate-features \
    --extractions-dir data/interim/airms/extractions \
    --cohort-path     data/interim/airms/mrsa_cohort_person_list.csv \
    --level           person \
    --no-debug
```

| Option | Default | Description |
|---|---|---|
| `--extractions-dir` | `data/interim/airms/extractions` | per-note extraction chunk directory |
| `--cohort-path` | `data/interim/airms/mrsa_cohort_person_list.csv` | cohort person list (`PERSON_ID`, `MRN`, `LABEL`) |
| `--level` | `person` | aggregation level: `person` or `visit` — must match the level used when building the gold standard |
| `--debug` / `--no-debug` | `--no-debug` | run on a debug subset of notes |


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

| Option | Default | Description |
|---|---|---|
| `features_path` (argument) | *(required)* | path to the rule feature matrix CSV |
| `--gold-standard-path` | `None` | path to manually annotated gold-standard CSV (optional; enables precision/recall/F1) |
| `--target-precision` | `0.90` | minimum acceptable precision per rule |
| `--target-recall` | `0.70` | minimum acceptable recall per rule |
| `--debug` / `--no-debug` | `--no-debug` | run in debug mode |

---

## Gold-Standard Annotation

Precision and recall in `evaluate` can only be computed against a manually
annotated **gold standard** — a small note sample where a human has checked off
which risk factors are actually present (and not negated). Building this gold
standard is interactive, so it is a separate step from `run-rule-pipeline`.

### Workflow

1. **Build a small note sample** to annotate, e.g. via `build-subset` with
   `--n-patients` / `--n-notes-per-type` set to keep the sample manageable
   (annotation is manual, so ~50–200 notes is typical).

2. **Run the annotator:**

   ```bash
   python -m src.cli annotate-gold-standard \
       --input-dir data/interim/airms/notes \
       --aggregation-level person
   ```

   For every note without an existing checklist, the tool prints the raw note
   text to stdout, writes a per-note checklist file to
   `data/annotations/checklists/note_<NOTE_ID>.txt`, and opens it in `$EDITOR`:

   ```
   # NOTE_ID: 123456
   # PERSON_ID: 987654
   # VISIT_OCCURRENCE_ID: 55555
   #
   # Mark every risk factor mentioned (and not negated) in the note above with an 'x'.
   # Add a short quoted evidence snippet after '->' for anything you check.
   # Leave as [ ] if the risk factor is absent, negated, or uncertain.

   [ ] prior_mrsa -> 
   [x] corticosteroid_use -> "on chronic prednisone 10mg daily"
   [ ] central_venous_catheter -> 
   …
   ```

   One checklist line is generated per risk factor in the lexicon (same
   `risk_factor` names used by `RuleExtractor`, so `has_{factor}` columns line
   up exactly with the pipeline output). Save and close the editor to move to
   the next note.

3. **Resume anytime.** Notes that already have a checklist file are skipped on
   rerun, so a session can be paused and picked up later. Pass
   `--force-reannotate` to reopen and overwrite existing checklists instead.

4. **Merge and aggregate.** Once all notes are annotated, the tool merges every
   checklist into one gold-standard DataFrame, aggregates `has_*` columns with
   `MAX` up to `--aggregation-level` (`visit` or `person` — must match the level
   used for the feature matrix being evaluated), joins `evidence_*` snippets
   with `"; "`, and writes `data/annotations/gold_standard.csv`.

5. **Evaluate against it:**

   ```bash
   python -m src.cli evaluate \
       outputs/feature_aggregation_<timestamp>/rule_features_<timestamp>.csv \
       --gold-standard-path data/annotations/gold_standard.csv
   ```

   `RuleEvaluator` computes per-factor TP / FP / FN / TN, precision, recall,
   and F1 for every `has_{factor}` column present in both the feature matrix
   and the gold standard, and flags factors that fall below
   `--target-precision` / `--target-recall` in `validation_report.txt`.

**Notes:**
- This step requires human interaction and is intentionally excluded from
  `run-rule-pipeline`.
- The gold standard's `--aggregation-level` must match the level of the
  feature matrix passed to `evaluate`, otherwise rows won't align by
  `PERSON_ID`/`VISIT_OCCURRENCE_ID` and metrics will be meaningless.

---

## Lexicon

`lexicons/mrsa_risk_factors_v3.csv` — 47 risk factors, columns:

| Column | Description |
|---|---|
| `risk_factor` | Risk factor key |
| `medical_context` | Plain-language description |
| `icd_codes` | Related ICD-10 codes (reference only) |
| `drug_names` | Specific drug names to match |
| `keywords` | Comma-separated regex-ready keywords |
| `abbreviations` | Common clinical abbreviations |
| `negation_caveats` | Patterns that should be excluded |

The 47 entries fall into two groups: 36 **clinical risk factors** (exposures,
comorbidities, devices, prior infection) and 11 **lab-value mentions** used as
free-text inflammation/severity markers rather than binary exposures. Feature
columns follow the `has_{risk_factor}` / `count_{risk_factor}` naming convention,
where `risk_factor` is the CSV `risk_factor` name lower-cased with spaces
replaced by underscores (e.g. `Central Venous Catheter` → `has_central_venous_catheter`).
Full per-rule detail (matches, known limitations, false positives, example
matches) is in [`RULES.md`](RULES.md).

**Clinical risk factors (36):**

| Factor | Rationale |
|---|---|
| `adm_from_ed` | Disease severity marker; high MRSA colonisation environment |
| `advanced_age` | Age-related immune decline (≥65y) |
| `antibiotic_exposure` | Selects for resistant organisms |
| `bacteremia` | Bloodstream infection evidence |
| `bone_marrow_transplant` | Profound immunosuppression |
| `central_venous_catheter` | Invasive device breaches skin barrier; primary CLABSI route |
| `chronic_kidney_disease` | Uremia-associated immune dysfunction |
| `coronary_artery_disease` | Comorbidity / chronic-disease burden proxy |
| `corticosteroid_use` | Immune suppression + skin barrier disruption |
| `diabetes_mellitus` | Hyperglycemia impairs neutrophil function and wound healing |
| `difficulty_swallowing` | Raised aspiration risk (indirect pneumonia/MRSA pathway) |
| `foley_catheter` | Direct infection portal; CAUTI risk |
| `hematologic_malignancy` | Disease- and treatment-related neutropenia and immune dysregulation |
| `hemodialysis` | Vascular access is a recurrent infection portal |
| `hiv_aids` | CD4-mediated immunodeficiency |
| `icu_admission` | High colonisation-pressure environment |
| `immunosuppressant_use` | Anti-rejection and DMARD agents |
| `injection_drug_use` | Skin barrier disruption + substance-associated infection risk |
| `invasive_mechanical_ventilation` | Bypasses upper airway defenses; VAP risk |
| `ltc_snf_residence` | High MRSA colonisation-pressure environment |
| `male_gender` | Demographic covariate |
| `neutropenia` | Severely impaired innate immunity |
| `open_wound` | Direct portal of entry for pathogens |
| `organ_impairment` | Critical-illness marker |
| `organ_transplant` | Lifelong pharmacologic immunosuppression |
| `peritoneal_dialysis` | Peritoneal catheter is an infection portal |
| `previous_hospital_stay` | Prior healthcare exposure and colonisation pressure |
| `prior_mrsa` | Strongest single predictor — history of MRSA colonisation/infection |
| `prior_staph` | History of S. aureus colonisation/infection (MSSA) |
| `receipt_of_transfusion` | Transfusion-related immunomodulation + vascular access exposure |
| `respiratory_failure` | Critical illness with impaired airway clearance and frequent instrumentation |
| `rheumatic_disease` | Immunosuppressive therapy for autoimmune/rheumatic disease |
| `sepsis` | Systemic infection severity marker |
| `skin_or_soft_tissue_infection` | Portal of entry and possible MRSA source |
| `solid_malignancy` | Tumor- and treatment-related immunosuppression |
| `surgical_procedure` | Skin integrity breach |

**Lab-value mentions (11)** — free-text mentions of a lab result (e.g. `CRP 145`,
`WBC 18`), used as inflammation/severity indicators rather than fixed clinical
exposures; several (`albumin_measurement`, `crp_measurement`,
`potassium_measurement`) are explicitly documented as such in the lexicon, the
rest are undocumented in `medical_context` and should be treated as
exploratory signals:

`albumin_measurement` · `crp_measurement` · `glucose_measurement` ·
`hemoglobin_measurement` · `inr_measurement` · `lactate_measurement` ·
`pct_measurement` · `platelet_measurement` · `potassium_measurement` ·
`sodium_measurement` · `wbc_measurement`

---

## Outputs

Each pipeline step writes to a timestamped directory:

```
outputs/
  cli_20260801-090000/
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

`data/annotations/` (persistent, output of `annotate-gold-standard`):

```
checklists/       note_<NOTE_ID>.txt … (per-note working files)
gold_standard.csv ← merged, aggregated gold-standard labels (input to `evaluate --gold-standard-path`)
```

See [`DATA_DICTIONAIRY.md`](DATA_DICTIONAIRY.md) for a column-by-column reference
of `rule_features_<timestamp>.csv`.

---

## Negation Logic

The `NegationHandler` implements a simplified NegEx algorithm, checking both
**pre-negation** cues (before the match, e.g. "no prior MRSA") and
**post-negation** cues (after the match, e.g. "MRSA ruled out"):

```
Pre-negation cues (checked in the look-back window):
  no · not · without · denies · denied · deny ·
  negative for · negative · absence of · absent · never ·
  ruled out · rules out · rule out · no evidence of ·
  no history of · no prior · no known · free of · none ·
  neither · nor

Post-negation cues (checked in the look-ahead window):
  not · no · denied · ruled out · doubt · negative

For each regex match at position [start, end]:
  1. Extract the pre-window: up to window_tokens tokens before start
     (trimmed at the last sentence boundary if sentence-boundary mode is on)
  2. Extract the post-window: up to window_tokens tokens after end
     (trimmed at the next sentence boundary if sentence-boundary mode is on)
  3. Check if any pre-negation cue regex matches the pre-window
  4. Check if any post-negation cue regex matches the post-window
  5. Mark match as negated=True if either window contains a cue

Negated matches are excluded from has_* and count_* features.
```

---

## Key Design Decisions

- **Resume-safe mining** — each chunk file is written atomically; the loop skips existing chunks on restart.
- **Lowercase preprocessing** — appropriate for regex matching; case-folded before pattern application.
- **Aggregation level = person (default), visit available** — MAX for binary features, SUM for counts; one row per `PERSON_ID` (or `VISIT_OCCURRENCE_ID` with `--level visit`). The gold standard's `--aggregation-level` must match whichever level is evaluated.
- **Target thresholds** — precision ≥ 0.90, recall ≥ 0.70 (configurable via `--target-precision`, `--target-recall`); measured per risk factor against the manually annotated gold standard (see [Gold-Standard Annotation](#gold-standard-annotation)).
- **Gold-standard annotation is manual and separate from the automated pipeline** — `annotate-gold-standard` requires a human reviewer and is intentionally excluded from `run-rule-pipeline`.

---

## References

- Chapman WW et al. (2001). *A simple algorithm for identifying negated findings and diseases in discharge summaries.* Journal of Biomedical Informatics. — NegEx algorithm basis.
- Shivade C et al. (2014). *A review of approaches to identifying patient phenotype cohorts using electronic health records.* JAMIA. — Rule-based NLP phenotyping review.
- Horan TC et al. (2008). *CDC/NHSN surveillance definition of health care–associated infection.* — MRSA risk factor definitions.
- Liu S et al. (2012). *Clamp — a toolkit for efficiently building customized clinical NLP pipelines.* — Clinical NLP pipeline reference.

See also [`RULES.md`](RULES.md) for per-risk-factor rationale and citations, and
[`lessons_learned.md`](lessons_learned.md) for a critical assessment of where
the rule-based approach is reliable versus where it requires manual review.
