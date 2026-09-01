# Changelog

This file documents any updates or refinements made during validation (evaluation, gold standard comparison, validation reporting). 

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Changelog for validation phase.
- MRSA risk indicators derived from study on AIR.MS dataset.
- Lessons learned.
- DATA_DICTIONAIRY.md with explanation of each output columns of the feature matrix resulting from feature aggregation.
- Missing risk signal descriptions and examples to RULES.md.

### Changed

- Default settings to usage of lexicon version 3 and person-level for the final feature matrix (resulting by pipeline and gold standard builder).
- Explanations and setup guideline in README.md.

### Fixed

- Data type of IDs in validation report output.

### Removed

- Placeholder for segment section.
- xlsx version of the lexicon.

## [0.2.0] - 2026-07-28

### Added

- Standardized workflow for annotating a gold standard.
- Option to evaluate a subset of the defined sample size.
- MRSA risk factors derived from AIR·MS data to lexicon v2.
- Keywords and abbreviations derived from first small evaluation to lexicon v3.
- Keyword extraction of ICD-10 codes.
- Filter options for the Subset Builder (number of patients, notes per type, notes per patient).
- Edge case TP=FP=FN=0 in precision calculation.

### Changed

- Logging preferences to allow switching between pipeline steps.
- Size of evaluation graphics.

### Fixed

- Cohort note access in the Subset Builder.

### Removed

- Duplicate medication mentions in lexicon v3.

## [0.1.0] - 2026-07-15

### Added

- Preprocessing.
- Feature extraction, including a first version of the lexicon and simple negation handling.
- Feature aggregation.
- Evaluation, including graphs and validation report.

### Changed

- Cohort Builder to Subset Builder.

### Removed

- Sections accessing the AIR·MS database.

[Unreleased]: https://github.com/Digital-Global-Public-Health/Rule-Based-Clinical-Risk-Signal-Extraction-AIR-MS-Clinical-Notes-Enhancement-for-MRSA-Prediction/compare/main...0.2.0
[0.2.0]: https://github.com/Digital-Global-Public-Health/Rule-Based-Clinical-Risk-Signal-Extraction-AIR-MS-Clinical-Notes-Enhancement-for-MRSA-Prediction/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/Digital-Global-Public-Health/Rule-Based-Clinical-Risk-Signal-Extraction-AIR-MS-Clinical-Notes-Enhancement-for-MRSA-Prediction/releases/tag/0.1.0
[SemVer]: https://semver.org