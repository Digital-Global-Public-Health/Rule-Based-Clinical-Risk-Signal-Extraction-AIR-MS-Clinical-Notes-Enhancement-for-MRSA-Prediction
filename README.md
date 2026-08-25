# Rule-Based Clinical Risk Signal Extraction — AIR.MS Clinical Notes Enhancement for MRSA Prediction

Extracts MRSA-relevant clinical risk factors (e.g. prior MRSA/staph infection, corticosteroid use, central lines, dialysis, ICU stays) from free-text clinical notes in the AIR.MS database, using curated regex/lexicon rules with negation handling. The resulting person-level feature matrix is designed to enhance MRSA risk prediction models with signals that aren't captured in structured EHR data alone.

## Getting Started

The active pipeline lives in [`rule_based/`](rule_based/) — see its [README](rule_based/README.md) for setup, usage, and a full pipeline walkthrough (subsetting → preprocessing → extraction → aggregation → evaluation).

## License

See [LICENSE](LICENSE).