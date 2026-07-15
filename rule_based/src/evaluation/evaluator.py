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

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from src.utils_io import ensure_dir

LOG = logging.getLogger("mrsa_nlp.rule.evaluation")


def _short_label(risk_factor: pd.Series) -> pd.Series:
    """Strip the has_ prefix and turn underscores/hyphens into spaces for plot ticks."""
    return (
        risk_factor.str.replace("^has_", "", regex=True)
        .str.replace("_", " ", regex=False)
        .str.replace("-", " ", regex=False)
    )


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
    target_precision : float
        Minimum acceptable precision per rule (used for pass/fail summary).
    target_recall : float
        Minimum acceptable recall per rule.
    n_example_notes : int
        Number of example rows (with at least one positive feature) to list
        in the validation report for qualitative review.
    plot_dpi : int
        DPI for saved figures.
    debug : bool
        When True, evaluate only the first debug_n_rows rows of the feature
        matrix (faster smoke-testing of the evaluation pipeline).
    debug_n_rows : int
        Max rows of the feature matrix processed in debug mode.
    """

    features_path: Path = Path("outputs/rule_features.csv")
    gold_standard_path: Optional[Path] = None
    target_precision: float = 0.90
    target_recall: float = 0.70
    n_example_notes: int = 10
    plot_dpi: int = 150
    debug: bool = False
    debug_n_rows: int = 500


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
        ensure_dir(self.eval_dir)
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

        Notes
        -----
        In debug mode, only the first cfg.debug_n_rows rows are kept.
        """
        features_path = self.cfg.features_path
        if not features_path.exists():
            raise FileNotFoundError(f"Feature matrix not found: {features_path}")
        features_df = pd.read_csv(features_path)
        self.log.info(f"Loaded feature matrix: {features_path} ({len(features_df)} rows)")
        if self.cfg.debug and len(features_df) > self.cfg.debug_n_rows:
            features_df = features_df.head(self.cfg.debug_n_rows).copy()
            self.log.info(f"Debug mode: truncated feature matrix to {len(features_df)} rows.")
        return features_df

    def load_gold_standard(self) -> Optional[pd.DataFrame]:
        """
        Load the manually annotated gold-standard labels if available.

        Returns
        -------
        pd.DataFrame or None
            Columns: a join key matching the feature matrix's own
            granularity (NOTE_ID, VISIT_OCCURRENCE_ID, or PERSON_ID), and
            binary gold-label columns named identically to the rule
            features (has_{risk_factor}).
            Returns None if cfg.gold_standard_path is None.

        Notes
        -----
        - The gold standard should be a manually reviewed sample of ~100–200
          notes where each risk factor was verified by the analyst.
        - This file is created outside of the pipeline (manual annotation).
        """
        gold_standard_path = self.cfg.gold_standard_path
        if gold_standard_path is None:
            self.log.warning("No gold standard path provided; skipping precision/recall evaluation.")
            return None
        if not gold_standard_path.exists():
            raise FileNotFoundError(f"Gold standard file not found: {gold_standard_path}")
        gold_df = pd.read_csv(gold_standard_path)
        self.log.info(f"Loaded gold standard: {gold_standard_path} ({len(gold_df)} rows)")
        return gold_df

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
        tp = ((y_true == 1) & (y_pred == 1)).sum()
        fp = ((y_true == 0) & (y_pred == 1)).sum()
        fn = ((y_true == 1) & (y_pred == 0)).sum()
        tn = ((y_true == 0) & (y_pred == 0)).sum()
        return {"TP": int(tp), "FP": int(fp), "FN": int(fn), "TN": int(tn)}

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
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        return precision, recall, f1

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
        - Join features_df and gold_df on the finest-grained key present in
          both (NOTE_ID > VISIT_OCCURRENCE_ID > PERSON_ID). Joining on a
          coarser key than the feature matrix's own granularity (e.g.
          PERSON_ID against a visit-level matrix) would fan out one gold
          row across multiple predicted rows and corrupt the counts.
        - For each has_{factor} column present in both frames, call
          compute_confusion_counts() and compute_prf1().
        - Flag rows where precision < cfg.target_precision or
          recall < cfg.target_recall.
        """
        for candidate_col in ("NOTE_ID", "VISIT_OCCURRENCE_ID", "PERSON_ID"):
            if candidate_col in features_df.columns and candidate_col in gold_df.columns:
                join_col = candidate_col
                break
        else:
            raise ValueError(
                "No shared join key (NOTE_ID, VISIT_OCCURRENCE_ID, or PERSON_ID) "
                "between the feature matrix and the gold standard."
            )
        if join_col == "PERSON_ID" and "VISIT_OCCURRENCE_ID" in features_df.columns:
            self.log.warning(
                "Joining a visit-level feature matrix on PERSON_ID because the gold "
                "standard has no VISIT_OCCURRENCE_ID; persons with multiple visits "
                "will have their single gold row matched against every visit row."
            )

        merged_df = features_df.merge(gold_df, on=join_col, suffixes=("_pred", "_gold"))
        if merged_df.empty:
            raise ValueError(
                f"Merging features and gold standard on '{join_col}' produced no rows; "
                "check that the IDs actually overlap."
            )

        feature_cols = [col for col in features_df.columns if col.startswith("has_")]
        missing_in_gold = [col for col in feature_cols if col not in gold_df.columns]
        if missing_in_gold:
            self.log.warning(f"Skipping factors missing from gold standard: {missing_in_gold}")
            feature_cols = [col for col in feature_cols if col not in missing_in_gold]

        metrics_list = []
        for feature in feature_cols:
            y_true = merged_df[f"{feature}_gold"]
            y_pred = merged_df[f"{feature}_pred"]
            counts = self.compute_confusion_counts(y_true, y_pred)
            precision, recall, f1 = self.compute_prf1(counts["TP"], counts["FP"], counts["FN"])
            metrics_list.append({
                "risk_factor": feature,
                "TP": counts["TP"],
                "FP": counts["FP"],
                "FN": counts["FN"],
                "TN": counts["TN"],
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "meets_precision_target": precision >= self.cfg.target_precision,
                "meets_recall_target": recall >= self.cfg.target_recall,
            })
        metrics_df = pd.DataFrame(metrics_list)
        metrics_df.sort_values(by="f1", ascending=False, inplace=True)
        metrics_csv_path = self.eval_dir / "metrics_by_factor.csv"
        metrics_df.to_csv(metrics_csv_path, index=False)
        self.log.info(f"Saved metrics by factor: {metrics_csv_path}")
        return metrics_df

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
        label_col = "LABEL"
        if label_col not in features_df.columns:
            raise ValueError(
                f"Feature matrix has no '{label_col}' column; "
                "run aggregate-features first to merge in the cohort labels."
            )

        feature_prev = []
        feature_cols = [col for col in features_df.columns if col.startswith("has_")]
        for feature in feature_cols:
            overall_prev = features_df[feature].mean()
            cases_prev = features_df.loc[features_df[label_col] == 1, feature].mean()
            controls_prev = features_df.loc[features_df[label_col] == 0, feature].mean()
            ratio = cases_prev / controls_prev if controls_prev > 0 else float("inf")
            feature_prev.append({
                "risk_factor": feature,
                "prevalence_overall": overall_prev,
                "prevalence_cases": cases_prev,
                "prevalence_controls": controls_prev,
                "prevalence_ratio": ratio,
            })
        prevalence_df = pd.DataFrame(feature_prev)
        prevalence_df.sort_values(by="prevalence_overall", ascending=False, inplace=True)
        self.log.info("Top 5 most prevalent factors overall:")
        self.log.info(prevalence_df.head(5).to_string(index=False))
        zero_prev = prevalence_df[prevalence_df["prevalence_overall"] == 0]
        if not zero_prev.empty:
            self.log.warning("Factors with zero prevalence:")
            self.log.warning(zero_prev.to_string(index=False))
        return prevalence_df

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
        - Use seaborn style; save at cfg.plot_dpi DPI.
        - Figure width and label rotation scale with the number of factors
          so long risk-factor names do not overlap.
        """
        out_path = self.eval_dir / "feature_prevalence.png"
        plot_df = prevalence_df.copy()
        plot_df["label"] = _short_label(plot_df["risk_factor"])

        n_factors = plot_df["risk_factor"].nunique()
        fig, ax = plt.subplots(figsize=(max(10, 0.55 * n_factors), 6))
        sns.barplot(
            data=plot_df.melt(id_vars="label", value_vars=["prevalence_cases", "prevalence_controls"]),
            x="label",
            y="value",
            hue="variable",
            ax=ax,
        )
        ax.set_xlabel("Risk Factor")
        ax.set_ylabel("Prevalence (Proportion)")
        ax.set_title("Feature Prevalence by LABEL (Cases vs Controls)")
        ax.legend(title="")
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor", fontsize=8)
        plt.tight_layout()
        plt.savefig(out_path, dpi=self.cfg.plot_dpi, bbox_inches="tight")
        plt.close(fig)
        self.log.info(f"Saved feature prevalence plot: {out_path}")
        return out_path

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
        - Figure height scales with the number of factors so long
          risk-factor names on the y-axis do not overlap.
        """
        out_path = self.eval_dir / "metrics_by_factor.png"
        plot_df = metrics_df.copy()
        plot_df["label"] = _short_label(plot_df["risk_factor"])

        n_factors = plot_df["risk_factor"].nunique()
        fig, ax = plt.subplots(figsize=(10, max(6, 0.45 * n_factors)))
        metrics_melted = plot_df.melt(id_vars="label", value_vars=["precision", "recall", "f1"])
        sns.barplot(
            data=metrics_melted,
            x="value",
            y="label",
            hue="variable",
            ax=ax,
        )
        ax.axvline(self.cfg.target_precision, color="red", linestyle="--", label="Target Precision")
        ax.axvline(self.cfg.target_recall, color="orange", linestyle="--", label="Target Recall")
        ax.set_xlabel("Metric Value")
        ax.set_ylabel("Risk Factor")
        ax.set_title("Precision, Recall, F1 by Risk Factor")
        ax.legend(title="")
        ax.tick_params(axis="y", labelsize=8)
        plt.tight_layout()
        plt.savefig(out_path, dpi=self.cfg.plot_dpi, bbox_inches="tight")
        plt.close(fig)
        self.log.info(f"Saved metrics by factor plot: {out_path}")
        return out_path

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
        labels = ["Control (LABEL=0)", "Case (LABEL=1)"]
        control_count = features_df[features_df["LABEL"] == 0].shape[0]
        case_count = features_df[features_df["LABEL"] == 1].shape[0]
        sizes = [control_count, case_count]
        fig, ax = plt.subplots(figsize=(6, 6))
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90, colors=["#1f77b4", "#ff7f0e"])
        ax.axis("equal")
        plt.title("Label Distribution (Cases vs Controls)")
        out_path = self.eval_dir / "label_distribution.png"
        plt.savefig(out_path, dpi=self.cfg.plot_dpi, bbox_inches="tight")
        plt.close(fig)
        self.log.info(f"Saved label distribution plot: {out_path}")
        return out_path

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
        validation_report_path = self.eval_dir / "validation_report.txt"
        with open(validation_report_path, "w") as f:
            f.write(f"{datetime.now().isoformat()}\n")
            f.write(f"Dataset size: {features_df.shape[0]} | ")
            f.write(f"Case count: {features_df[features_df['LABEL'] == 1].shape[0]} | ")
            f.write(f"Control count: {features_df[features_df['LABEL'] == 0].shape[0]}\n")
            f.write("\nFeature Prevalence:\n")
            f.write(prevalence_df.to_string(index=False))
            f.write("\n\n")
            if metrics_df is not None:
                f.write("Precision/Recall Metrics:\n")
                f.write(metrics_df.to_string(index=False))
                f.write("\n\n")
                failed_precision = metrics_df[~metrics_df["meets_precision_target"]]
                failed_recall = metrics_df[~metrics_df["meets_recall_target"]]
                f.write(f"Rules failing precision target ({self.cfg.target_precision}):\n")
                f.write(failed_precision[["risk_factor", "precision"]].to_string(index=False))
                f.write("\n\n")
                f.write(f"Rules failing recall target ({self.cfg.target_recall}):\n")
                f.write(failed_recall[["risk_factor", "recall"]].to_string(index=False))
                f.write("\n\n")
                f.write("Recommendations:\n")
                if failed_precision.empty and failed_recall.empty:
                    f.write("- All rules meet their precision/recall targets.\n")
                else:
                    for row in failed_precision.itertuples():
                        f.write(
                            f"- {row.risk_factor}: precision {row.precision:.2f} below target "
                            f"({self.cfg.target_precision}); tighten the regex or negation window "
                            "to cut false positives.\n"
                        )
                    for row in failed_recall.itertuples():
                        f.write(
                            f"- {row.risk_factor}: recall {row.recall:.2f} below target "
                            f"({self.cfg.target_recall}); broaden the lexicon (synonyms/abbreviations) "
                            "to catch missed mentions.\n"
                        )
            else:
                f.write("No gold standard provided; precision/recall metrics not computed.\n")

            f.write("\nExample rows for qualitative review:\n")
            id_col = next(
                (c for c in ("NOTE_ID", "VISIT_OCCURRENCE_ID", "PERSON_ID") if c in features_df.columns),
                None,
            )
            binary_cols = [c for c in features_df.columns if c.startswith("has_")]
            if id_col is not None and binary_cols:
                positive_rows = features_df[features_df[binary_cols].any(axis=1)]
                examples = positive_rows.head(self.cfg.n_example_notes)
                if examples.empty:
                    f.write("- No rows with a positive feature found.\n")
                else:
                    for _, row in examples.iterrows():
                        fired = [c for c in binary_cols if row[c] == 1]
                        f.write(f"- {id_col}={row[id_col]}: {', '.join(fired)}\n")
            else:
                f.write("- Skipped: no ID column or has_* features found.\n")

        self.log.info(f"Saved validation report: {validation_report_path}")
        return validation_report_path

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
        features_df = self.load_features()
        prevalence_df = self.compute_prevalence(features_df)
        self.plot_label_distribution(features_df)
        self.plot_prevalence(prevalence_df)

        metrics_df = None
        if self.cfg.gold_standard_path is not None:
            gold_df = self.load_gold_standard()
            metrics_df = self.evaluate_by_factor(features_df, gold_df)
            self.plot_metrics_by_factor(metrics_df)

        self.generate_validation_report(features_df, metrics_df, prevalence_df)

        if metrics_df is not None:
            n_pass = int((metrics_df["meets_precision_target"] & metrics_df["meets_recall_target"]).sum())
            self.log.info(f"Pass/fail summary: {n_pass}/{len(metrics_df)} rules meet both targets.")

        self.log.debug(f"Evaluation complete. Outputs saved to: {self.eval_dir}")
