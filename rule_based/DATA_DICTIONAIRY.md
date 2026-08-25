# Data Dictionary — `rule_features_<timestamp>.csv`

Column-by-column reference for the training-ready feature matrix produced by
`aggregate-features` (`src/features/feature_aggregator.py`). One row per
`PERSON_ID` (default, `--level person`) or per `VISIT_OCCURRENCE_ID`
(`--level visit`).

For *why* each risk factor is included and how its regex pattern is built,
see [`RULES.md`](RULES.md); the canonical source list is
[`lexicons/mrsa_risk_factors_v3.csv`](lexicons/mrsa_risk_factors_v3.csv).

---

## Identifier & label columns

| Column | Type | Description |
|---|---|---|
| `PERSON_ID` | int64 | OMOP person identifier. |
| `VISIT_OCCURRENCE_ID` | int64 | OMOP visit identifier; one row per visit. Only present when aggregated on `--level visit`. |
| `LABEL` | int (0/1) | Case (`1`) / control (`0`) label, joined in from `mrsa_cohort_person_list.csv`. Rows with no cohort match are dropped. |

## Aggregation metadata columns

These differ by `--level` because the grouping key differs.

| Column | Type | Present at | Description |
|---|---|---|---|
| `n_visits` | int | `person`, `visit` | Number of distinct `VISIT_OCCURRENCE_ID`s contributing to this person. |
| `n_notes` | int | `person`, `visit` | Number of notes contributing to this person, across all visits. |
| `n_notes_in_visit` | int | `visit` | Number of notes contributing to this visit. |
| `NOTE_DATE` | date | `visit` | Earliest note date within the visit (`min`). |
| `NOTE_TYPE_CONCEPT_ID` | int | `visit` | Most common note type within the visit (mode; `pd.NA` if the visit has no notes). |

## Risk-factor feature columns

Every risk factor `<rf>` in the lexicon produces up to two columns, named by
lower-snake-casing the `Risk Factor` cell (spaces → `_`; see
`Lexicon.normalize()`):

| Column pattern | Type | Description |
|---|---|---|
| `has_<rf>` | int (0/1) | `1` if **any** non-negated note in scope (visit or person) matched the risk factor's pattern; aggregated with `MAX` across notes. |
| `count_<rf>` | int (≥0) | Total number of non-negated matches across notes in scope; aggregated with `SUM`. |

Both column families are on by default (`--include-binary-features` /
`--include-count-features` in `AggregatorConfig`); missing values are
filled with `0` after the cohort join (`--fill-missing-with-zero`, default
on)

A detailed description of each risk signal is documented in [`RULES.md`](RULES.md).


## Related files

| File | Description |
|---|---|
| `rule_features_<timestamp>.parquet` | Same content as the CSV, in Parquet format. |
| `feature_summary_<timestamp>.json` | Per-column descriptive stats, see below. |
| `config.yaml` | Snapshot of the `AggregatorConfig` used for this run. |

### `feature_summary_<timestamp>.json`

Produced by `FeatureAggregator.compute_feature_summary()`. One entry per
feature column:

| Key | Applies to | Description |
|---|---|---|
| `prevalence_overall` | `has_*` | Mean of the binary column across all rows. |
| `prevalence_cases` | `has_*` | Mean of the binary column restricted to `LABEL == 1`. |
| `prevalence_controls` | `has_*` | Mean of the binary column restricted to `LABEL == 0`. |
| `mean_count` | `count_*` | Mean of the count column across all rows. |
