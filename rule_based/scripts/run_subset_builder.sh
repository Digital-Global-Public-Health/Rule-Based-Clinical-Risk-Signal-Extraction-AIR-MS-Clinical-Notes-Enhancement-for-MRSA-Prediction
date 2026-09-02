#!/usr/bin/env bash
set -euo pipefail

# -------------------------
# Configuration
# -------------------------
NOTES_PATH="/sc/arion/projects/MRSA-HPI-MS/airms-app-host-and-hospital-adaptation-of-mrsa/mrsa_nlp/rule_based/data/interim/airms/notes/all/cohort_notes.parquet"
PERSON_IDS_CSV=""          # leave empty to disable person-ID filter
SELECTED_LABELS="0,1"      # "0,1" = all, "1" = cases only
OUT_DIR="data/interim/airms/notes"
CHUNK_SIZE=1

LOG_LEVEL="INFO"
SEED=7
N_PATIENTS=""
N_NOTES_PER_TYPE=""
DEBUG=false
DEBUG_N_ROWS=100

# -------------------------
# Parse optional args
# -------------------------
# Usage:
#   bash scripts/run_subset_builder.sh [--cases-only] [--chunk-size N] [--n-patients N] [--n-notes-per-type N] [--debug] [debug-n-rows N] [--seed N]]
while [ $# -gt 0 ]; do
  case "$1" in
    --cases-only)       SELECTED_LABELS="1"; shift ;;
    --chunk-size)       shift; CHUNK_SIZE="$1"; shift ;;
    --seed)             shift; SEED="$1"; shift ;;
    --n-patients)       shift; N_PATIENTS="$1"; shift ;;
    --n-notes-per-type) shift; N_NOTES_PER_TYPE="$1"; shift ;;
    --debug)            DEBUG=true; LOG_LEVEL="DEBUG"; shift ;;
    --debug-n-rows)     shift; DEBUG_N_ROWS="$1"; shift ;;
    *)                  shift ;;
  esac
done

# -------------------------
# Helpers
# -------------------------
# Activate conda env if not already active
activate_conda() {
  local env="mrsa-nlp-rule"
  if [[ "${CONDA_DEFAULT_ENV:-}" != "$env" ]]; then
    eval "$(conda shell.bash hook)"
    conda activate "$env"
    echo "[run] Activated conda env: $env"
  fi
}

# -------------------------
# Main
# -------------------------
main() {
  echo "=== MRSA NLP (Rule-Based) — Subset Builder ==="

  activate_conda

  # Thread management on HPC
  export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-8}"
  export OMP_NUM_THREADS="${OMP_NUM_THREADS:-8}"
  export MKL_NUM_THREADS="${MKL_NUM_THREADS:-8}"

  echo "[run] notes_path      : $NOTES_PATH"
  echo "[run] selected_labels : $SELECTED_LABELS"
  echo "[run] out_dir         : $OUT_DIR"
  echo "[run] chunk_size      : $CHUNK_SIZE"
  if [[ -n "$N_PATIENTS" ]]; then
    echo "[run] n_patients      : $N_PATIENTS"
  fi
  if [[ -n "$N_NOTES_PER_TYPE" ]]; then
    echo "[run] n_notes_per_type: $N_NOTES_PER_TYPE"
  fi
  echo "[run] debug           : $DEBUG"

  EXTRA_ARGS=()
  if [[ -n "$PERSON_IDS_CSV" ]]; then
    EXTRA_ARGS+=(--cohort-csv-path "$PERSON_IDS_CSV")
  fi
  if [[ -n "$N_PATIENTS" ]]; then
    EXTRA_ARGS+=(--n-patients "$N_PATIENTS")
  fi
  if [[ -n "$N_NOTES_PER_TYPE" ]]; then
    EXTRA_ARGS+=(--n-notes-per-type "$N_NOTES_PER_TYPE")
  fi

  DEBUG_FLAGS=(--no-debug)
  if [[ "$DEBUG" == "true" ]]; then
    DEBUG_FLAGS=(--debug --debug-n-rows "$DEBUG_N_ROWS")
  fi

  python -m src.cli \
      --log-level "$LOG_LEVEL" \
      --seed "$SEED" \
      build-subset \
      --notes-path "$NOTES_PATH" \
      --selected-labels "$SELECTED_LABELS" \
      --out-dir "$OUT_DIR" \
      --chunk-size "$CHUNK_SIZE" \
      "${EXTRA_ARGS[@]}" \
      "${DEBUG_FLAGS[@]}"

  echo "[run] Subset builder complete."
}

main "$@"
