#!/usr/bin/env bash
# scripts/run_feature_extraction.sh
#
# Pipeline Steps 3 + 4: Rule-based extraction + feature aggregation.
#
# Prerequisites:
#   1. conda env mrsa-nlp-rule is activated
#   2. Preprocessing has been run
#
# Usage:
#   bash scripts/run_feature_extraction.sh [--debug]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONDA_ENV="mrsa-nlp-rule"
LOG_LEVEL="INFO"
PREPROCESSED_DIR="data/interim/airms/notes_preprocessed"
EXTRACTIONS_DIR="data/interim/airms/extractions"
COHORT_PATH="data/interim/airms/mrsa_cohort_person_list.csv"
LEXICON_PATH="lexicons/mrsa_risk_factors_v1.csv"
NEGATION_WINDOW=5
LEVEL="visit"
DEBUG=false
DEBUG_N_NOTES=200

for arg in "$@"; do
    case $arg in
        --debug) DEBUG=true ;;
    esac
done

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------
cd "$PROJECT_ROOT"

if [[ -f ".env" ]]; then
    set -a; source ".env"; set +a
fi

if [[ "${CONDA_DEFAULT_ENV:-}" != "$CONDA_ENV" ]]; then
    eval "$(conda shell.bash hook)"
    conda activate "$CONDA_ENV"
    echo "[run] Activated conda env: $CONDA_ENV"
fi

# ---------------------------------------------------------------------------
# Step 3 — Extract
# ---------------------------------------------------------------------------
echo "[run] Step 3/4: Rule-based extraction (debug=${DEBUG})"

DEBUG_FLAGS="--no-debug"
if [[ "$DEBUG" == "true" ]]; then
    DEBUG_FLAGS="--debug --debug-n-notes $DEBUG_N_NOTES"
fi

python -m src.cli \
    --log-level "$LOG_LEVEL" \
    extract \
    --preprocessed-dir "$PREPROCESSED_DIR" \
    --out-dir "$EXTRACTIONS_DIR" \
    --lexicon-path "$LEXICON_PATH" \
    --negation-window "$NEGATION_WINDOW" \
    $DEBUG_FLAGS

echo "[run] Extraction complete."

# ---------------------------------------------------------------------------
# Step 4 — Aggregate features
# ---------------------------------------------------------------------------
echo "[run] Step 4/4: Feature aggregation (level=${LEVEL})"

python -m src.cli \
    --log-level "$LOG_LEVEL" \
    aggregate-features \
    --extractions-dir "$EXTRACTIONS_DIR" \
    --cohort-path "$COHORT_PATH" \
    --level "$LEVEL" \
    $DEBUG_FLAGS

echo "[run] Feature aggregation complete."
echo "[run] Output: outputs/feature_aggregation_<timestamp>/"
