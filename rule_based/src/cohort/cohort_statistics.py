# src/cohort/cohort_statistics.py
"""
Cohort statistics for the MRSA NLP rule-based project.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import logging

import pandas as pd
from rich.console import Console
from rich.table import Table


LOG = logging.getLogger("mrsa_nlp.rule.cohort.statistics")


@dataclass
class StatisticsConfig:
    """
    Configuration for cohort statistics.

    Attributes
    ----------
    enabled : bool
        Whether to compute and display statistics (default: False).
    person_id_column : str
        Name of the column that stores the person identifier.
    note_title_column : str
        Name of the column that stores the note type/title.
    output_path : str | None
        Optional CSV file where the statistics summary will be saved.
    """

    enabled: bool = False
    person_id_column: str = "PERSON_ID"
    note_title_column: str = "NOTE_TITLE"
    output_path: Optional[str] = None


class CohortStatistics:
    """
    Compute and display statistics for a cohort of notes.

    The statistics include:
    - Total number of notes and unique patients
    - Distribution of notes per note type/title
    - Distribution of notes per patient
    """

    def __init__(self, config: StatisticsConfig, logger: logging.Logger = LOG) -> None:
        self.cfg = config
        self.log = logger
        self.console = Console()

    def compute(self, df: pd.DataFrame) -> dict:
        """
        Compute cohort statistics and optionally display them.

        Parameters
        ----------
        df : pandas.DataFrame
            Input dataframe to compute statistics from.

        Returns
        -------
        dict
            Dictionary with keys: 'total_notes', 'unique_patients',
            'notes_per_type', 'notes_per_patient_distribution'.
        """
        if df is None or df.empty:
            self.log.warning("Cannot compute statistics: dataframe is empty.")
            return {}

        person_id_col = self.cfg.person_id_column
        note_title_col = self.cfg.note_title_column

        # Validate required columns exist
        if person_id_col not in df.columns:
            self.log.error(f"Missing required column: {person_id_col}")
            return {}
        if note_title_col not in df.columns:
            self.log.error(f"Missing required column: {note_title_col}")
            return {}

        # Compute statistics
        total_notes = len(df)
        unique_patients = df[person_id_col].nunique()

        notes_per_type = df[note_title_col].value_counts().reset_index()
        notes_per_type.columns = [note_title_col, "count"]

        notes_per_patient = df.groupby(person_id_col).size()
        notes_per_patient_distribution = notes_per_patient.value_counts().sort_index().reset_index()
        notes_per_patient_distribution.columns = ["notes_per_patient", "patient_count"]

        stats = {
            "total_notes": total_notes,
            "unique_patients": unique_patients,
            "notes_per_type": notes_per_type,
            "notes_per_patient_distribution": notes_per_patient_distribution,
        }

        if self.cfg.enabled:
            self._display_statistics(stats)
            if self.cfg.output_path:
                self._save_summary(stats)

        return stats

    def _display_statistics(self, stats: dict) -> None:
        """Pretty-print statistics using rich tables."""
        self.console.print("\n[bold cyan]Cohort Statistics[/bold cyan]")

        # Summary table
        summary_table = Table(show_header=True, header_style="bold magenta")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        summary_table.add_row("Total Notes", str(stats["total_notes"]))
        summary_table.add_row("Unique Patients", str(stats["unique_patients"]))
        self.console.print(summary_table)

        # Notes per type
        self.console.print("\n[bold]Notes per Type:[/bold]")
        type_table = Table(show_header=True, header_style="bold magenta")
        type_table.add_column(self.cfg.note_title_column, style="cyan")
        type_table.add_column("Count", style="green")
        for _, row in stats["notes_per_type"].iterrows():
            type_table.add_row(str(row[self.cfg.note_title_column]), str(row["count"]))
        self.console.print(type_table)

        # Notes per patient distribution
        self.console.print("\n[bold]Notes per Patient Distribution:[/bold]")
        dist_table = Table(show_header=True, header_style="bold magenta")
        dist_table.add_column("Notes per Patient", style="cyan")
        dist_table.add_column("Patient Count", style="green")
        for _, row in stats["notes_per_patient_distribution"].iterrows():
            dist_table.add_row(str(row["notes_per_patient"]), str(row["patient_count"]))
        self.console.print(dist_table)
        self.console.print()

    def _save_summary(self, stats: dict) -> None:
        """Save a summary CSV file with key statistics."""
        summary_data = {
            "metric": [
                "total_notes",
                "unique_patients",
                "avg_notes_per_patient",
            ],
            "value": [
                stats["total_notes"],
                stats["unique_patients"],
                stats["total_notes"] / max(stats["unique_patients"], 1),
            ],
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_csv(self.cfg.output_path, index=False)
        self.log.info(f"Statistics summary saved to {self.cfg.output_path}")