# src/features/feature_aggregator.py
"""
Feature engineering and aggregation pipeline.

Aggregates per-note extraction results (produced by RuleExtractor) to a
visit-level and/or person-level feature matrix and merges with the MRSA cohort
labels to produce the final training-ready CSV.

Input  : data/interim/airms/extractions/chunk_*.parquet
         data/interim/airms/mrsa_cohort_person_list.parquet
Output : outputs/<run_dir>/rule_features_<timestamp>.csv  (feature matrix)
         outputs/<run_dir>/feature_summary_<timestamp>.json (descriptive stats)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

LOG = logging.getLogger("mrsa_nlp.rule.features")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class AggregatorConfig:
    """
    Tunable parameters for the feature aggregator.

    Attributes
    ----------
    extractions_dir : Path
        Directory containing per-note extraction chunk Parquet files.
    cohort_person_list_path : Path
        Path to mrsa_cohort_person_list.parquet (PERSON_ID, MRN, LABEL).
    out_dir : Path
        Base output directory for feature matrix and summary files.
    aggregation_level : str
        "visit"  → one row per VISIT_OCCURRENCE_ID  (primary).
        "person" → one row per PERSON_ID (aggregate across all visits).
    include_binary_features : bool
        Include has_{risk_factor} binary (0/1) features.
    include_count_features : bool
        Include count_{risk_factor} integer features.
    include_note_type_breakdown : bool
        Produce separate binary flags per note type concept ID.
    fill_missing_with_zero : bool
        Fill NaN feature values with 0 after merging with cohort.
    debug : bool
        When True process only debug_n_extractions rows.
    debug_n_extractions : int
        Max rows processed in debug mode.
    """

    extractions_dir: Path = Path("data/interim/airms/extractions")
    cohort_person_list_path: Path = Path(
        "data/interim/airms/mrsa_cohort_person_list.parquet"
    )
    out_dir: Path = Path("outputs")
    aggregation_level: str = "visit"
    include_binary_features: bool = True
    include_count_features: bool = True
    include_note_type_breakdown: bool = False
    fill_missing_with_zero: bool = True
    debug: bool = False
    debug_n_extractions: int = 1000


# ---------------------------------------------------------------------------
# Aggregator class
# ---------------------------------------------------------------------------

class FeatureAggregator:
    """
    Transforms per-note extraction results into a visit-level feature matrix.

    Parameters
    ----------
    config : AggregatorConfig
        Configuration for this aggregation run.
    run_dir : Path
        Timestamped output directory for this pipeline run.
    logger : logging.Logger, optional
        Logger; defaults to module-level LOG.

    Example
    -------
    >>> from src.features.feature_aggregator import AggregatorConfig, FeatureAggregator
    >>> from pathlib import Path
    >>> cfg = AggregatorConfig(debug=True)
    >>> agg = FeatureAggregator(cfg, run_dir=Path("outputs/feature_run_20260401"))
    >>> feature_df = agg.run()
    """

    def __init__(
        self,
        config: AggregatorConfig,
        run_dir: Path,
        logger: logging.Logger = LOG,
    ) -> None:
        self.cfg = config
        self.run_dir = run_dir
        self.log = logger

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_extractions(self) -> pd.DataFrame:
        """
        Load and concatenate all extraction chunk Parquet files.

        Returns
        -------
        pd.DataFrame
            Combined DataFrame with columns: NOTE_ID, PERSON_ID,
            VISIT_OCCURRENCE_ID, NOTE_DATE, NOTE_TYPE_CONCEPT_ID,
            has_{risk_factor}*, count_{risk_factor}*.

        Raises
        ------
        FileNotFoundError
            If cfg.extractions_dir is empty. Prompts user to run the
            extraction pipeline first.

        Notes
        -----
        - Log the total number of notes loaded and the column set.
        - Identify and log how many notes have no risk-factor matches.
        """
        pass

    def load_cohort(self) -> pd.DataFrame:
        """
        Load the mrsa_cohort_person_list.

        Returns
        -------
        pd.DataFrame
            Columns: PERSON_ID (int64), MRN (str), LABEL (int).

        Raises
        ------
        FileNotFoundError
            If cfg.cohort_person_list_path does not exist. Prompts user to
            run the cohort builder first.
        """
        pass

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _get_risk_factor_columns(self, df: pd.DataFrame) -> Tuple[List[str], List[str]]:
        """
        Identify binary (has_*) and count (count_*) feature columns.

        Parameters
        ----------
        df : pd.DataFrame
            Extractions DataFrame.

        Returns
        -------
        Tuple[list of str, list of str]
            (binary_cols, count_cols)
        """
        pass

    def aggregate_to_visit_level(self, extractions_df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate per-note features to one row per VISIT_OCCURRENCE_ID.

        Aggregation logic:
        - Binary features: take MAX across all notes for the visit
          (1 if any note for this visit mentioned the factor).
        - Count features: take SUM across all notes for the visit.

        Parameters
        ----------
        extractions_df : pd.DataFrame
            Per-note extraction results.

        Returns
        -------
        pd.DataFrame
            Columns: VISIT_OCCURRENCE_ID, PERSON_ID, has_*..., count_*...
            One row per unique VISIT_OCCURRENCE_ID.

        Notes
        -----
        - Also retain: NOTE_DATE (earliest), NOTE_TYPE_CONCEPT_ID (most common
          as mode), and n_notes_in_visit (count of notes contributing).
        - Log how many visits have at least one positive feature.
        """
        pass

    def aggregate_to_person_level(self, extractions_df: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate per-note features to one row per PERSON_ID.

        Parameters
        ----------
        extractions_df : pd.DataFrame
            Per-note extraction results.

        Returns
        -------
        pd.DataFrame
            Columns: PERSON_ID, has_*..., count_*...

        Notes
        -----
        Same aggregation rules as aggregate_to_visit_level but grouped by
        PERSON_ID instead of VISIT_OCCURRENCE_ID.
        """
        pass

    # ------------------------------------------------------------------
    # Merging with cohort labels
    # ------------------------------------------------------------------

    def merge_with_cohort(
        self,
        features_df: pd.DataFrame,
        cohort_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Join aggregated features with cohort labels (LABEL column).

        Parameters
        ----------
        features_df : pd.DataFrame
            Aggregated features at visit or person level.
        cohort_df : pd.DataFrame
            Cohort with PERSON_ID, MRN, LABEL.

        Returns
        -------
        pd.DataFrame
            Features + LABEL + MRN.

        Notes
        -----
        - Join key: PERSON_ID.
        - Rows in features_df with no cohort match are dropped (log count).
        - Fill NaN feature values with 0 if cfg.fill_missing_with_zero.
        - Log final label distribution (cases vs controls).
        """
        pass

    # ------------------------------------------------------------------
    # Feature summary statistics
    # ------------------------------------------------------------------

    def compute_feature_summary(self, feature_df: pd.DataFrame) -> Dict:
        """
        Compute descriptive statistics for each feature column.

        Parameters
        ----------
        feature_df : pd.DataFrame
            Final merged feature matrix with LABEL.

        Returns
        -------
        dict
            Keys: risk factor names.
            Values: dicts with ``prevalence_overall``, ``prevalence_cases``,
            ``prevalence_controls``, ``mean_count``.

        Notes
        -----
        - Useful for quickly identifying which rules fire the most and
          whether the distribution differs between cases and controls.
        """
        pass

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(
        self,
        feature_df: pd.DataFrame,
        summary: Dict,
        timestamp: str,
    ) -> Path:
        """
        Write the feature matrix and summary to disk.

        Parameters
        ----------
        feature_df : pd.DataFrame
            Final merged feature matrix.
        summary : dict
            Feature summary statistics.
        timestamp : str
            Timestamp string (``YYYYMMDD-HHMMSS``) appended to filenames.

        Returns
        -------
        Path
            Path to the saved CSV feature matrix.

        Notes
        -----
        - CSV: ``{run_dir}/rule_features_{timestamp}.csv``
        - Parquet: ``{run_dir}/rule_features_{timestamp}.parquet``
        - JSON: ``{run_dir}/feature_summary_{timestamp}.json``
        - Log the output paths and shape of the exported DataFrame.
        """
        pass

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self) -> pd.DataFrame:
        """
        Execute the full feature aggregation pipeline.

        Steps
        -----
        1. load_extractions()              → extractions_df
        2. load_cohort()                   → cohort_df
        3. aggregate by level (visit or person)   → features_df
        4. merge_with_cohort()             → final_df
        5. compute_feature_summary()       → summary
        6. export()

        Returns
        -------
        pd.DataFrame
            The final feature matrix (features + LABEL).
        """
        pass
