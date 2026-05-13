#!/usr/bin/env bash
# scripts/run_preprocessing.sh
#
# Pipeline Step 2: Clean and normalise raw clinical note chunks.
#
# Prerequisites:
#   1. conda env mrsa-nlp-rule is activated
#   2. Cohort builder has been run (notes present in data/interim/airms/notes/)
#
# Usage:
#   bash scripts/run_preprocessing.sh [--debug]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONDA_ENV="mrsa-nlp-rule"
LOG_LEVEL="INFO"
RAW_NOTES_DIR="data/interim/airms/notes"
OUT_DIR="data/interim/airms/notes_preprocessed"
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
# Run pipeline step
# ---------------------------------------------------------------------------
echo "[run] Starting preprocessing (debug=${DEBUG})"

if [[ "$DEBUG" == "true" ]]; then
    python -m src.cli \
        --log-level "$LOG_LEVEL" \
        preprocess \
        --raw-notes-dir "$RAW_NOTES_DIR" \
        --out-dir "$OUT_DIR" \
        --lowercase --expand-abbrev --no-segment \
        --debug --debug-n-notes "$DEBUG_N_NOTES"
else
    python -m src.cli \
        --log-level "$LOG_LEVEL" \
        preprocess \
        --raw-notes-dir "$RAW_NOTES_DIR" \
        --out-dir "$OUT_DIR" \
        --lowercase --expand-abbrev --no-segment \
        --no-debug
fi

echo "[run] Preprocessing complete."
