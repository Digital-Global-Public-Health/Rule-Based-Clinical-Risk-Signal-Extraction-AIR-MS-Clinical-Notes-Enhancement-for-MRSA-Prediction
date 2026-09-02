#!/usr/bin/env bash
# scripts/run_evaluation.sh
#
# Pipeline Step 5: Evaluate rule-based extraction quality.
#
# Prerequisites:
#   1. conda env mrsa-nlp-rule is activated
#   2. Feature aggregation has been run — locate the output CSV path
#
# Usage:
#   bash scripts/run_evaluation.sh <path/to/rule_features.csv> [--gold <path/to/gold.csv>] [--debug]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CONDA_ENV="mrsa-nlp-rule"
LOG_LEVEL="INFO"
TARGET_PRECISION=0.90
TARGET_RECALL=0.70
FEATURES_PATH=""
GOLD_PATH=""
DEBUG=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --gold)      GOLD_PATH="$2"; shift 2 ;;
        --debug)     DEBUG=true;  LOG_LEVEL="DEBUG"; shift ;;
        *)           FEATURES_PATH="$1"; shift ;;
    esac
done

if [[ -z "$FEATURES_PATH" ]]; then
    echo "Usage: $0 <path/to/rule_features.csv> [--gold <path/to/gold.csv>] [--debug]"
    exit 1
fi

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
# Run evaluation
# ---------------------------------------------------------------------------
echo "[run] Evaluating features: $FEATURES_PATH"

GOLD_FLAG=""
if [[ -n "$GOLD_PATH" ]]; then
    GOLD_FLAG="--gold-standard-path $GOLD_PATH"
fi

DEBUG_FLAG="--no-debug"
[[ "$DEBUG" == "true" ]] && DEBUG_FLAG="--debug"

python -m src.cli \
    --log-level "$LOG_LEVEL" \
    evaluate \
    "$FEATURES_PATH" \
    $GOLD_FLAG \
    --target-precision "$TARGET_PRECISION" \
    --target-recall "$TARGET_RECALL" \
    $DEBUG_FLAG

echo "[run] Evaluation complete.  See outputs/evaluation_<timestamp>/"
