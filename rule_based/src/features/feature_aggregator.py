# src/features/feature_aggregator.py
"""
Feature engineering and aggregation pipeline.

Aggregates per-note extraction results (produced by RuleExtractor) to a
visit-level and/or person-level feature matrix and merges with the MRSA cohort
labels to produce the final training-ready CSV.

Input  : data/interim/airms/extractions/chunk_*.parquet
         data/interim/airms/mrsa_cohort_person_list.csv
Output : outputs/<run_dir>/rule_features_<timestamp>.csv  (feature matrix)
         outputs/<run_dir>/feature_summary_<timestamp>.json (descriptive stats)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from src.utils_io import read_parquet, write_parquet

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
        Path to mrsa_cohort_person_list.csv (PERSON_ID, LABEL).
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
        Produce separate has_notetype_{concept_id} binary flags (1 if any
        note of that type contributed to the visit/person).
    fill_missing_with_zero : bool
        Fill NaN feature values with 0 after merging with cohort.
    debug : bool
        When True process only debug_n_extractions rows.
    debug_n_extractions : int
        Max rows processed in debug mode.
    """

    extractions_dir: Path = Path("data/interim/airms/extractions")
    cohort_person_list_path: Path = Path(
        "data/interim/airms/mrsa_cohort_person_list.csv"
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
# Helpers
# ---------------------------------------------------------------------------

def _safe_mode(series: pd.Series):
    """Return the most frequent value in *series*, or NA if it is empty/all-NaN."""
    mode = series.mode()
    return mode.iloc[0] if not mode.empty else pd.NA


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
        - In debug mode, stop after cfg.debug_n_extractions rows total.
        """
        notes_dir = self.cfg.extractions_dir
        if not notes_dir.exists() or not notes_dir.is_dir():
            raise FileNotFoundError(
                f"Extractions directory not found: {notes_dir}. "
                "Run the extraction pipeline first."
            )

        chunk_files = sorted(
            notes_dir.glob("chunk_*.parquet"),
            key=lambda p: int(p.stem.split("_")[-1]) if p.stem.split("_")[-1].isdigit() else 0,
        )
        if not chunk_files:
            raise FileNotFoundError(
                f"No extraction note chunks found in {notes_dir}. "
                "Run the extraction pipeline first."
            )

        debug_limit = self.cfg.debug_n_extractions if self.cfg.debug else None

        df_list: List[pd.DataFrame] = []
        total_rows = 0
        missing_matches_count = 0
        for chunk_file in chunk_files:
            if debug_limit is not None and total_rows >= debug_limit:
                self.log.info(f"Debug limit reached ({debug_limit} rows); stopping early.")
                break

            self.log.debug(f"Loading chunk file: {chunk_file}")
            df_chunk = read_parquet(chunk_file)

            if debug_limit is not None:
                remaining = debug_limit - total_rows
                if len(df_chunk) > remaining:
                    df_chunk = df_chunk.iloc[:remaining].copy()

            binary_cols, _ = self._get_risk_factor_columns(df_chunk)
            if binary_cols:
                missing_matches_count += int((df_chunk[binary_cols].sum(axis=1) == 0).sum())

            total_rows += len(df_chunk)
            df_list.append(df_chunk)

        if not df_list:
            raise FileNotFoundError(
                f"No extraction rows loaded from {notes_dir} (debug_n_extractions=0?)."
            )

        extractions_df = pd.concat(df_list, ignore_index=True)
        self.log.info(f"Loaded {len(df_list)} chunk(s), total notes: {len(extractions_df)}")
        self.log.info(f"Columns in extraction DataFrame: {extractions_df.columns.tolist()}")
        self.log.info(f"Notes with no risk-factor matches: {missing_matches_count}")
        return extractions_df

    def load_cohort(self) -> pd.DataFrame:
        """
        Load the mrsa_cohort_person_list.

        Returns
        -------
        pd.DataFrame
            Columns: PERSON_ID (int64), LABEL (int).

        Raises
        ------
        FileNotFoundError
            If cfg.cohort_person_list_path does not exist. Prompts user to
            run the cohort builder first.
        """
        cohort_path = self.cfg.cohort_person_list_path
        if not cohort_path.exists():
            raise FileNotFoundError(
                f"Cohort person list not found: {cohort_path}. "
                "Run the cohort builder first."
            )
        cohort_df = pd.read_csv(cohort_path)
        self.log.info(f"Loaded cohort with {len(cohort_df)} persons from {cohort_path}")
        cohort_df = cohort_df[["PERSON_ID", "LABEL"]].copy()
        return cohort_df

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
        feature_cols = df.columns
        binary_cols = [col for col in feature_cols if col.startswith("has_")]
        count_cols = [col for col in feature_cols if col.startswith("count_")]
        return binary_cols, count_cols

    def _aggregate(
        self,
        extractions_df: pd.DataFrame,
        group_col: str,
        extra_named_agg: Dict[str, Tuple[str, object]],
    ) -> pd.DataFrame:
        """
        Shared vectorised aggregation used by both visit- and person-level
        rollups.

        Binary (has_*) features are aggregated with MAX (1 if any note for
        the group mentioned the factor); count (count_*) features are
        aggregated with SUM. ``extra_named_agg`` supplies the level-specific
        columns (e.g. NOTE_DATE, n_visits) as pandas named-aggregation
        tuples of ``(source_column, func)``.
        """
        binary_cols, count_cols = self._get_risk_factor_columns(extractions_df)
        if not self.cfg.include_binary_features:
            binary_cols = []
        if not self.cfg.include_count_features:
            count_cols = []

        grouped = extractions_df.groupby(group_col)
        result = grouped.agg(**extra_named_agg)

        if binary_cols:
            result = result.join(grouped[binary_cols].max())
        if count_cols:
            result = result.join(grouped[count_cols].sum())

        if self.cfg.include_note_type_breakdown and "NOTE_TYPE_CONCEPT_ID" in extractions_df.columns:
            note_type = extractions_df["NOTE_TYPE_CONCEPT_ID"].astype("Int64").astype(str)
            note_type_dummies = pd.get_dummies(note_type, prefix="has_notetype")
            note_type_dummies[group_col] = extractions_df[group_col].values
            note_type_flags = note_type_dummies.groupby(group_col).max().astype(int)
            result = result.join(note_type_flags)

        if binary_cols:
            n_positive = int((result[binary_cols] > 0).any(axis=1).sum())
            self.log.info(
                f"At least one positive feature in {n_positive} of {len(result)} "
                f"group(s) (grouped by {group_col})."
            )

        return result.reset_index()

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
        - Also retains NOTE_DATE (earliest), NOTE_TYPE_CONCEPT_ID (most
          common as mode), and n_notes_in_visit (count of notes contributing).
        - Logs how many visits have at least one positive feature.
        """
        return self._aggregate(
            extractions_df,
            group_col="VISIT_OCCURRENCE_ID",
            extra_named_agg={
                "PERSON_ID": ("PERSON_ID", "first"),
                "NOTE_DATE": ("NOTE_DATE", "min"),
                "NOTE_TYPE_CONCEPT_ID": ("NOTE_TYPE_CONCEPT_ID", _safe_mode),
                "n_notes_in_visit": ("PERSON_ID", "size"),
            },
        )

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
        return self._aggregate(
            extractions_df,
            group_col="PERSON_ID",
            extra_named_agg={
                "n_visits": ("VISIT_OCCURRENCE_ID", "nunique"),
                "n_notes": ("VISIT_OCCURRENCE_ID", "size"),
            },
        )

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
            Cohort with PERSON_ID, LABEL.

        Returns
        -------
        pd.DataFrame
            Features + LABEL + PERSON_ID.

        Notes
        -----
        - Join key: PERSON_ID. Duplicate PERSON_IDs in the cohort list are
          collapsed (first occurrence kept) to avoid row fan-out.
        - Rows in features_df with no cohort match are dropped (log count).
        - Fill NaN feature values with 0 if cfg.fill_missing_with_zero.
        - Log final label distribution (cases vs controls).
        """
        if cohort_df["PERSON_ID"].duplicated().any():
            n_dupes = int(cohort_df["PERSON_ID"].duplicated().sum())
            self.log.warning(
                f"Cohort person list has {n_dupes} duplicate PERSON_ID row(s); "
                "keeping first occurrence."
            )
            cohort_df = cohort_df.drop_duplicates(subset="PERSON_ID", keep="first")

        merged_df = features_df.merge(cohort_df, on="PERSON_ID", how="left")

        unmatched_mask = merged_df["LABEL"].isna()
        n_unmatched = int(unmatched_mask.sum())
        if n_unmatched > 0:
            self.log.info(f"Dropped {n_unmatched} row(s) with no cohort match.")
            merged_df = merged_df.loc[~unmatched_mask].copy()

        if self.cfg.fill_missing_with_zero:
            feature_cols = [col for col in merged_df.columns if col.startswith("has_") or col.startswith("count_")]
            merged_df[feature_cols] = merged_df[feature_cols].fillna(0)

        label_counts = merged_df["LABEL"].value_counts()
        self.log.info(f"Final label distribution: {label_counts.to_dict()}")
        return merged_df

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
        statistics = {}
        feature_cols = [col for col in feature_df.columns if col.startswith("has_") or col.startswith("count_")]
        for col in feature_cols:
            if col.startswith("has_"):
                prevalence_overall = feature_df[col].mean()
                prevalence_cases = feature_df.loc[feature_df["LABEL"] == 1, col].mean()
                prevalence_controls = feature_df.loc[feature_df["LABEL"] == 0, col].mean()
                statistics[col] = {
                    "prevalence_overall": prevalence_overall,
                    "prevalence_cases": prevalence_cases,
                    "prevalence_controls": prevalence_controls,
                }
            elif col.startswith("count_"):
                mean_count = feature_df[col].mean()
                statistics[col] = {"mean_count": mean_count}
        return statistics

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
        feature_csv_path = self.run_dir / f"rule_features_{timestamp}.csv"
        feature_parquet_path = self.run_dir / f"rule_features_{timestamp}.parquet"
        summary_json_path = self.run_dir / f"feature_summary_{timestamp}.json"

        feature_df.to_csv(feature_csv_path, index=False)
        write_parquet(feature_df, feature_parquet_path)
        with open(summary_json_path, "w") as f:
            json.dump(summary, f, indent=4)

        self.log.info(f"Exported feature matrix to {feature_csv_path} and {feature_parquet_path} (shape: {feature_df.shape})")
        self.log.info(f"Exported feature summary to {summary_json_path}")
        return feature_csv_path

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
        extractions_df = self.load_extractions()
        cohort_df = self.load_cohort()
        if self.cfg.aggregation_level == "visit":
            features_df = self.aggregate_to_visit_level(extractions_df)
        elif self.cfg.aggregation_level == "person":
            features_df = self.aggregate_to_person_level(extractions_df)
        else:
            raise ValueError(f"Invalid aggregation level: {self.cfg.aggregation_level}. Must be 'visit' or 'person'.")
        final_df = self.merge_with_cohort(features_df, cohort_df)
        summary = self.compute_feature_summary(final_df)
        timestamp = pd.Timestamp.now().strftime("%Y%m%d-%H%M%S")
        self.export(final_df, summary, timestamp)
        return final_df