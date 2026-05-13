# src/evaluation/evaluator.py
"""
Evaluation and visualisation pipeline for the rule-based extraction.

This module computes precision, recall, and F1 for each risk factor against
a manually annotated gold-standard sample, produces a validation report,
and generates plots suitable for a thesis / paper.

Input  : outputs/<run_dir>/rule_features_*.csv  (predicted features)
         data/annotations/gold_standard.csv      (manual gold labels — optional)
Output : outputs/<run_dir>/evaluation/
            metrics_by_factor.csv
            metrics_by_factor.png
            feature_prevalence.png
            validation_report.txt
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

LOG = logging.getLogger("mrsa_nlp.rule.evaluation")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class EvaluatorConfig:
    """
    Parameters for the rule-based evaluator.

    Attributes
    ----------
    features_path : Path
        Path to the rule feature matrix CSV (output of FeatureAggregator).
    gold_standard_path : Path, optional
        Path to a manually annotated CSV with ground-truth binary flags for
        a sample of notes.  If None, only descriptive statistics are produced
        (no precision/recall).
    out_dir : Path
        Sub-directory inside run_dir where evaluation outputs go.
    target_precision : float
        Minimum acceptable precision per rule (used for pass/fail summary).
    target_recall : float
        Minimum acceptable recall per rule.
    n_example_notes : int
        Number of example notes to include in the validation report for
        qualitative review.
    plot_dpi : int
        DPI for saved figures.
    debug : bool
        Reduces computation to a small sample.
    """

    features_path: Path = Path("outputs/rule_features.csv")
    gold_standard_path: Optional[Path] = None
    out_dir: Path = Path("outputs/evaluation")
    target_precision: float = 0.90
    target_recall: float = 0.70
    n_example_notes: int = 10
    plot_dpi: int = 150
    debug: bool = False


# ---------------------------------------------------------------------------
# Evaluator class
# ---------------------------------------------------------------------------

class RuleEvaluator:
    """
    Evaluates rule-based extraction quality and generates visual reports.

    Parameters
    ----------
    config : EvaluatorConfig
        Configuration for this evaluation run.
    run_dir : Path
        Timestamped run directory; evaluation outputs go into run_dir/evaluation/.
    logger : logging.Logger, optional
        Logger; defaults to module-level LOG.

    Example
    -------
    >>> from src.evaluation.evaluator import EvaluatorConfig, RuleEvaluator
    >>> from pathlib import Path
    >>> cfg = EvaluatorConfig(features_path=Path("outputs/.../rule_features.csv"))
    >>> evaluator = RuleEvaluator(cfg, run_dir=Path("outputs/eval_run"))
    >>> evaluator.run()
    """

    def __init__(
        self,
        config: EvaluatorConfig,
        run_dir: Path,
        logger: logging.Logger = LOG,
    ) -> None:
        self.cfg = config
        self.run_dir = run_dir
        self.eval_dir = run_dir / "evaluation"
        self.eval_dir.mkdir(parents=True, exist_ok=True)
        self.log = logger

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_features(self) -> pd.DataFrame:
        """
        Load the feature matrix produced by FeatureAggregator.

        Returns
        -------
        pd.DataFrame
            Columns include PERSON_ID, LABEL, has_*, count_*.

        Raises
        ------
        FileNotFoundError
            If cfg.features_path does not exist.
        """
        pass

    def load_gold_standard(self) -> Optional[pd.DataFrame]:
        """
        Load the manually annotated gold-standard labels if available.

        Returns
        -------
        pd.DataFrame or None
            Columns: NOTE_ID or PERSON_ID, and binary gold-label columns
            named identically to the rule features (has_{risk_factor}).
            Returns None if cfg.gold_standard_path is None.

        Notes
        -----
        - The gold standard should be a manually reviewed sample of ~100–200
          notes where each risk factor was verified by the analyst.
        - This file is created outside of the pipeline (manual annotation).
        """
        pass

    # ------------------------------------------------------------------
    # Precision / Recall / F1
    # ------------------------------------------------------------------

    def compute_confusion_counts(
        self,
        y_true: pd.Series,
        y_pred: pd.Series,
    ) -> Dict[str, int]:
        """
        Compute TP, FP, FN, TN for a single binary feature.

        Parameters
        ----------
        y_true : pd.Series
            Gold-standard binary labels (0 or 1).
        y_pred : pd.Series
            Predicted binary labels from the rule.

        Returns
        -------
        dict with keys "TP", "FP", "FN", "TN".
        """
        pass

    def compute_prf1(
        self,
        tp: int,
        fp: int,
        fn: int,
    ) -> Tuple[float, float, float]:
        """
        Compute precision, recall, and F1 from confusion counts.

        Parameters
        ----------
        tp, fp, fn : int

        Returns
        -------
        Tuple[float, float, float]
            (precision, recall, f1).  Zero-division returns 0.0.
        """
        pass

    def evaluate_by_factor(
        self,
        features_df: pd.DataFrame,
        gold_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Compute precision/recall/F1 for each risk factor against the gold standard.

        Parameters
        ----------
        features_df : pd.DataFrame
            Predicted features for the gold-standard sample (subset).
        gold_df : pd.DataFrame
            Gold-standard labels for the same sample.

        Returns
        -------
        pd.DataFrame
            Columns: risk_factor, TP, FP, FN, TN, precision, recall, f1,
            meets_precision_target, meets_recall_target.
            Sorted by F1 descending.

        Notes
        -----
        - Join features_df and gold_df on NOTE_ID or PERSON_ID.
        - For each has_{factor} column, call compute_confusion_counts() and
          compute_prf1().
        - Flag rows where precision < cfg.target_precision or
          recall < cfg.target_recall.
        """
        pass

    # ------------------------------------------------------------------
    # Descriptive statistics (no gold standard needed)
    # ------------------------------------------------------------------

    def compute_prevalence(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute feature prevalence (positive rate) overall and by LABEL.

        Parameters
        ----------
        features_df : pd.DataFrame
            Feature matrix with LABEL column.

        Returns
        -------
        pd.DataFrame
            Columns: risk_factor, prevalence_overall, prevalence_cases,
            prevalence_controls, prevalence_ratio (cases / controls).

        Notes
        -----
        - Log the top-5 most prevalent factors overall.
        - Log any factor with zero prevalence (rule may be too restrictive).
        """
        pass

    # ------------------------------------------------------------------
    # Visualisations
    # ------------------------------------------------------------------

    def plot_prevalence(
        self,
        prevalence_df: pd.DataFrame,
    ) -> Path:
        """
        Bar chart of feature prevalence by LABEL (cases vs controls).

        Parameters
        ----------
        prevalence_df : pd.DataFrame
            Output of compute_prevalence().

        Returns
        -------
        Path
            Saved figure path: ``eval_dir/feature_prevalence.png``.

        Notes
        -----
        - Side-by-side bars for cases and controls.
        - x-axis: risk factor names (short labels).
        - y-axis: proportion of records with feature = 1.
        - Add a horizontal target line at cfg.target_precision.
        - Use seaborn style; save at cfg.plot_dpi DPI.
        """
        pass

    def plot_metrics_by_factor(
        self,
        metrics_df: pd.DataFrame,
    ) -> Path:
        """
        Horizontal bar chart of precision, recall, F1 per risk factor.

        Parameters
        ----------
        metrics_df : pd.DataFrame
            Output of evaluate_by_factor() (requires gold standard).

        Returns
        -------
        Path
            Saved figure path: ``eval_dir/metrics_by_factor.png``.

        Notes
        -----
        - Grouped bars per risk factor: precision / recall / F1.
        - Vertical dashed lines at cfg.target_precision and
          cfg.target_recall.
        """
        pass

    def plot_label_distribution(
        self,
        features_df: pd.DataFrame,
    ) -> Path:
        """
        Simple pie or bar chart of LABEL distribution (cases vs controls).

        Parameters
        ----------
        features_df : pd.DataFrame
            Feature matrix with LABEL column.

        Returns
        -------
        Path
            Saved figure path: ``eval_dir/label_distribution.png``.
        """
        pass

    # ------------------------------------------------------------------
    # Validation report
    # ------------------------------------------------------------------

    def generate_validation_report(
        self,
        features_df: pd.DataFrame,
        metrics_df: Optional[pd.DataFrame],
        prevalence_df: pd.DataFrame,
    ) -> Path:
        """
        Write a plain-text validation report summarising the evaluation results.

        Parameters
        ----------
        features_df : pd.DataFrame
            Final feature matrix.
        metrics_df : pd.DataFrame or None
            Precision/recall metrics (None if no gold standard).
        prevalence_df : pd.DataFrame
            Prevalence statistics.

        Returns
        -------
        Path
            Path to the text report: ``eval_dir/validation_report.txt``.

        Notes
        -----
        Report structure:
        1. Header: run date/time, dataset size, case/control counts.
        2. Prevalence table (all factors).
        3. Metrics table (if gold standard available).
        4. Pass/fail summary against precision/recall targets.
        5. Recommendations for rules that fail targets.
        """
        pass

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Execute the full evaluation pipeline.

        Steps
        -----
        1. load_features()
        2. compute_prevalence() → prevalence_df
        3. plot_label_distribution()
        4. plot_prevalence()
        5. If gold standard:
            a. load_gold_standard()
            b. evaluate_by_factor() → metrics_df
            c. plot_metrics_by_factor()
        6. generate_validation_report()

        Notes
        -----
        - Save all artefacts under ``self.eval_dir``.
        - Log a final pass/fail summary to the console.
        """
        pass
