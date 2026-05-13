# src/cli.py
"""
Command-line interface for the MRSA NLP rule-based pipeline.

Usage (from project root, with conda env activated):

    python -m src.cli --help

    # Step 1 — build cohort + mine notes
    python -m src.cli build-cohort [OPTIONS]

    # Step 2 — preprocess raw notes
    python -m src.cli preprocess [OPTIONS]

    # Step 3 — run rule-based extraction
    python -m src.cli extract [OPTIONS]

    # Step 4 — aggregate features
    python -m src.cli aggregate-features [OPTIONS]

    # Step 5 — evaluate extraction quality
    python -m src.cli evaluate [OPTIONS]

    # Run the full pipeline end-to-end
    python -m src.cli run-rule-pipeline [OPTIONS]
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import warnings
from rich import print

from src.utils_logging import configure_logging, logger, make_run_dir, save_config_snapshot, log_timing
from src.utils_db import connect_hana
from src.utils_seed import set_seed, GLOBAL_SEED
from src.cohort.cohort_builder import CohortConfig, CohortBuilder
from src.preprocessing.note_preprocessor import PreprocessorConfig, NotePreprocessor
from src.extraction.lexicon import LexiconConfig, Lexicon
from src.extraction.negation_handler import NegationConfig, NegationHandler
from src.extraction.rule_extractor import ExtractorConfig, RuleExtractor
from src.features.feature_aggregator import AggregatorConfig, FeatureAggregator
from src.evaluation.evaluator import EvaluatorConfig, RuleEvaluator

warnings.filterwarnings('ignore', category=RuntimeWarning, message='.*pandas.*')

app = typer.Typer(
    add_completion=False,
    help="MRSA NLP — rule-based clinical note extraction pipeline.",
)


# ---------------------------------------------------------------------------
# Global callback: configure logging and seeding
# ---------------------------------------------------------------------------

@app.callback()
def _configure(
    ctx: typer.Context,
    log_level: str = typer.Option(
        "INFO", "--log-level", help="Logging level: DEBUG | INFO | WARNING | ERROR"
    ),
    seed: int = typer.Option(
        GLOBAL_SEED, "--seed", help=f"Random seed for reproducibility (default: {GLOBAL_SEED})"
    ),
) -> None:
    """Global CLI options, logging setup, and seed initialization."""
    run_name = ctx.invoked_subcommand or "cli"
    run_dir = configure_logging(log_level, run_name=run_name)
    set_seed(seed)
    logger.info("Log level : %s", log_level.upper())
    logger.info("Seed      : %d", seed)
    logger.info("Run dir   : %s", run_dir)


# ---------------------------------------------------------------------------
# 1. build-cohort
# ---------------------------------------------------------------------------

@app.command(help="Load the MRSA cohort from mrsa_risk_predictions and mine notes from CDMPHI.NOTES.")
@log_timing
def build_cohort(
    schema: str = typer.Option("CDMPHI", help="HANA schema name."),
    chunk_size: int = typer.Option(500, help="Persons per note-mining chunk."),
    min_note_date: str = typer.Option("2014-07-14", help="Earliest note date (YYYY-MM-DD)."),
    debug: bool = typer.Option(False, "--debug/--no-debug", help="Debug mode: limit to a small sample."),
    debug_n_persons: int = typer.Option(20, help="Persons to process in debug mode."),
    seed: int = typer.Option(GLOBAL_SEED, "--seed", help=f"Random seed (passed to mrsa_risk_predictions cohort loader; default: {GLOBAL_SEED})."),
) -> None:
    """
    Pipeline Step 1 — Build cohort and mine clinical notes.

    Reads the matched-pairs cohort from mrsa_risk_predictions, resolves MRNs,
    saves mrsa_cohort_person_list.parquet, then fetches notes from CDMPHI.NOTES
    in person-level chunks.

    The seed is used in the underlying cohort builder for reproducible control sampling.
    """
    cfg = CohortConfig(
        schema=schema,
        chunk_size=chunk_size,
        min_note_date=min_note_date,
        debug=debug,
        debug_n_persons=debug_n_persons,
    )

    save_config_snapshot(
        cfg.__dict__ | {"pipeline_step": "build_cohort"},
        run_dir=_current_run_dir(),
    )

    conn = connect_hana()
    builder = CohortBuilder(cfg, conn)
    person_df = builder.run()

    # logger.info(
    #     "Cohort built: %d persons  (%d cases, %d controls)",
    #     len(person_df),
    #     (person_df["LABEL"] == 1).sum() if person_df is not None else 0,
    #     (person_df["LABEL"] == 0).sum() if person_df is not None else 0,
    # )


# ---------------------------------------------------------------------------
# 2. preprocess
# ---------------------------------------------------------------------------

@app.command(help="Clean and normalise raw clinical note chunks.")
@log_timing
def preprocess(
    raw_notes_dir: Path = typer.Option(
        Path("data/interim/airms/notes"),
        help="Directory of raw note chunk Parquet files.",
    ),
    out_dir: Path = typer.Option(
        Path("data/interim/airms/notes_preprocessed"),
        help="Directory for preprocessed note chunks.",
    ),
    lowercase: bool = typer.Option(True, "--lowercase/--no-lowercase"),
    expand_abbrev: bool = typer.Option(True, "--expand-abbrev/--no-expand-abbrev"),
    segment: bool = typer.Option(False, "--segment/--no-segment"),
    debug: bool = typer.Option(False, "--debug/--no-debug"),
    debug_n_notes: int = typer.Option(200),
) -> None:
    """
    Pipeline Step 2 — Preprocess raw note chunks.

    Applies whitespace normalisation, abbreviation expansion, and optional
    section segmentation.  Skips already-processed chunks (resume-safe).
    """
    cfg = PreprocessorConfig(
        raw_notes_dir=raw_notes_dir,
        out_dir=out_dir,
        lowercase=lowercase,
        expand_abbreviations=expand_abbrev,
        segment_sections=segment,
        debug=debug,
        debug_n_notes=debug_n_notes,
    )

    save_config_snapshot(
        cfg.__dict__ | {"pipeline_step": "preprocess"},
        run_dir=_current_run_dir(),
    )

    pp = NotePreprocessor(cfg)
    pp.run()


# ---------------------------------------------------------------------------
# 3. extract
# ---------------------------------------------------------------------------

@app.command(help="Run regex-based risk-signal extraction on preprocessed notes.")
@log_timing
def extract(
    preprocessed_dir: Path = typer.Option(
        Path("data/interim/airms/notes_preprocessed"),
        help="Directory of preprocessed note chunk Parquet files.",
    ),
    out_dir: Path = typer.Option(
        Path("data/interim/airms/extractions"),
        help="Directory for extraction result chunks.",
    ),
    lexicon_path: Path = typer.Option(
        Path("lexicons/mrsa_risk_factors_v1.csv"),
        help="Path to the risk factor lexicon CSV.",
    ),
    negation_window: int = typer.Option(5, help="Negation look-back window (tokens)."),
    no_negation: bool = typer.Option(False, "--no-negation", help="Disable negation filtering."),
    save_spans: bool = typer.Option(False, "--save-spans", help="Store matched text spans."),
    debug: bool = typer.Option(False, "--debug/--no-debug"),
    debug_n_notes: int = typer.Option(200),
) -> None:
    """
    Pipeline Step 3 — Rule-based extraction.

    Loads the lexicon, compiles regex patterns, applies them to preprocessed
    note chunks, filters negated matches, and saves extraction results.
    """
    lex_cfg = LexiconConfig(lexicon_path=lexicon_path)
    lex = Lexicon(lex_cfg)
    lex.load()

    neg_cfg = NegationConfig(window_tokens=negation_window)
    neg = NegationHandler(neg_cfg)

    ext_cfg = ExtractorConfig(
        preprocessed_notes_dir=preprocessed_dir,
        out_dir=out_dir,
        apply_negation=not no_negation,
        save_matched_spans=save_spans,
        debug=debug,
        debug_n_notes=debug_n_notes,
    )

    save_config_snapshot(
        ext_cfg.__dict__ | {"pipeline_step": "extract"},
        run_dir=_current_run_dir(),
    )

    extractor = RuleExtractor(ext_cfg, lex, neg)
    extractor.run()


# ---------------------------------------------------------------------------
# 4. aggregate-features
# ---------------------------------------------------------------------------

@app.command(help="Aggregate per-note extractions to visit-level feature matrix.")
@log_timing
def aggregate_features(
    extractions_dir: Path = typer.Option(
        Path("data/interim/airms/extractions"),
        help="Directory of extraction chunk Parquet files.",
    ),
    cohort_path: Path = typer.Option(
        Path("data/interim/airms/mrsa_cohort_person_list.parquet"),
        help="Cohort person list (PERSON_ID, MRN, LABEL).",
    ),
    level: str = typer.Option("visit", help="Aggregation level: 'visit' or 'person'."),
    debug: bool = typer.Option(False, "--debug/--no-debug"),
) -> None:
    """
    Pipeline Step 4 — Feature engineering and aggregation.

    Aggregates per-note extraction counts to visit level, merges with cohort
    labels, and saves a training-ready CSV.
    """
    _, run_dir = make_run_dir("feature_aggregation")

    cfg = AggregatorConfig(
        extractions_dir=extractions_dir,
        cohort_person_list_path=cohort_path,
        out_dir=run_dir,
        aggregation_level=level,
        debug=debug,
    )

    save_config_snapshot(cfg.__dict__ | {"pipeline_step": "aggregate_features"}, run_dir)

    agg = FeatureAggregator(cfg, run_dir)
    feature_df = agg.run()

    logger.info("Feature matrix shape: %s", feature_df.shape if feature_df is not None else "None")


# ---------------------------------------------------------------------------
# 5. evaluate
# ---------------------------------------------------------------------------

@app.command(help="Evaluate extraction quality and generate visualisation reports.")
@log_timing
def evaluate(
    features_path: Path = typer.Argument(..., help="Path to the rule feature matrix CSV."),
    gold_standard_path: Optional[Path] = typer.Option(
        None, help="Path to manually annotated gold-standard CSV (optional)."
    ),
    target_precision: float = typer.Option(0.90, help="Minimum acceptable precision per rule."),
    target_recall: float = typer.Option(0.70, help="Minimum acceptable recall per rule."),
    debug: bool = typer.Option(False, "--debug/--no-debug"),
) -> None:
    """
    Pipeline Step 5 — Evaluation and visualisation.

    Computes feature prevalence, and (if gold standard supplied) precision/
    recall/F1 per risk factor.  Saves charts and a validation report.
    """
    _, run_dir = make_run_dir("evaluation")

    cfg = EvaluatorConfig(
        features_path=features_path,
        gold_standard_path=gold_standard_path,
        out_dir=run_dir / "evaluation",
        target_precision=target_precision,
        target_recall=target_recall,
        debug=debug,
    )

    save_config_snapshot(cfg.__dict__ | {"pipeline_step": "evaluate"}, run_dir)

    evaluator = RuleEvaluator(cfg, run_dir)
    evaluator.run()


# ---------------------------------------------------------------------------
# Full pipeline (run all steps in order)
# ---------------------------------------------------------------------------

@app.command(help="Run the complete rule-based pipeline end-to-end.")
@log_timing
def run_rule_pipeline(
    schema: str = typer.Option("CDMPHI"),
    lexicon_path: Path = typer.Option(Path("lexicons/mrsa_risk_factors_v1.csv")),
    skip_cohort: bool = typer.Option(False, "--skip-cohort", help="Skip cohort building (notes exist)."),
    skip_preprocess: bool = typer.Option(False, "--skip-preprocess"),
    skip_extract: bool = typer.Option(False, "--skip-extract"),
    debug: bool = typer.Option(False, "--debug/--no-debug"),
) -> None:
    """
    Run all pipeline steps sequentially.

    Steps: build-cohort → preprocess → extract → aggregate-features
    Use --skip-* flags to resume from a specific step.
    """
    _, run_dir = make_run_dir("full_pipeline")
    logger.info("Full pipeline run dir: %s", run_dir)

    if not skip_cohort:
        logger.info("=== Step 1/4: build-cohort ===")
        cfg_cohort = CohortConfig(schema=schema, debug=debug)
        conn = connect_hana()
        CohortBuilder(cfg_cohort, conn).run()

    if not skip_preprocess:
        logger.info("=== Step 2/4: preprocess ===")
        NotePreprocessor(PreprocessorConfig(debug=debug)).run()

    if not skip_extract:
        logger.info("=== Step 3/4: extract ===")
        lex = Lexicon(LexiconConfig(lexicon_path=lexicon_path))
        lex.load()
        neg = NegationHandler(NegationConfig())
        RuleExtractor(ExtractorConfig(debug=debug), lex, neg).run()

    logger.info("=== Step 4/4: aggregate-features ===")
    agg = FeatureAggregator(AggregatorConfig(debug=debug), run_dir)
    agg.run()

    logger.info("Pipeline complete.  Run dir: %s", run_dir)


# ---------------------------------------------------------------------------
# Helper: retrieve current run dir set by configure_logging
# ---------------------------------------------------------------------------

def _current_run_dir() -> Path:
    """Return the run directory established by configure_logging."""
    from src.utils_logging import LOG_RUN_DIR
    return LOG_RUN_DIR or Path("outputs")


if __name__ == "__main__":
    configure_logging("INFO", run_name="cli")
    app()
