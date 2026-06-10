"""Cohort statistics helpers for the MRSA NLP rule-based project.

Input  : pandas.DataFrame with PERSON_ID and NOTE_TITLE columns
Output : StatisticsResult plus optional terminal tables, plots, and CSV summary
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import logging
from typing import Optional

import pandas as pd
from matplotlib import pyplot as plt
from rich.console import Console
from rich.table import Table
from wordcloud import WordCloud


LOG = logging.getLogger("mrsa_nlp.rule.statistics")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class StatisticsConfig:
    """Configuration for cohort statistics output.

    Attributes
    ----------
    enabled : bool
        Whether to display statistics and write the optional summary.
    person_id_column : str
        Name of the column that stores the person identifier.
    note_title_column : str
        Name of the column that stores the note type/title.
    output_path : pathlib.Path | None
        Optional CSV path for the compact summary output.
    top_n_note_types : int
        Maximum number of note types to show in the table and bar chart.
    include_note_type_distribution : bool
        Whether to render the note type distribution.
    include_patient_distribution : bool
        Whether to render the notes-per-patient distribution.
    """

    enabled: bool = True
    person_id_column: str = "PERSON_ID"
    note_title_column: str = "NOTE_TITLE"
    output_path: Path = Path("output/cohort_statistics_summary.csv")
    top_n_note_types: int = 10
    include_note_type_distribution: bool = True
    include_patient_distribution: bool = True


@dataclass(slots=True)
class StatisticsResult:
    """Structured result returned by :class:`CohortStatistics`.

    Attributes
    ----------
    total_notes : int
        Total number of notes in the dataframe.
    unique_patients : int
        Number of unique patients in the dataframe.
    notes_per_type : pandas.DataFrame
        Table with note title counts.
    notes_per_patient_distribution : pandas.DataFrame
        Table with notes-per-patient counts.
    """

    total_notes: int
    unique_patients: int
    notes_per_type: pd.DataFrame = field(repr=False)
    notes_per_patient_distribution: pd.DataFrame = field(repr=False)

    def as_dict(self) -> dict:
        """Return a JSON-friendly summary representation."""
        return {
            "total_notes": self.total_notes,
            "unique_patients": self.unique_patients,
            "avg_notes_per_patient": self.total_notes / max(self.unique_patients, 1),
            "notes_per_type": self.notes_per_type.to_dict(orient="records"),
            "notes_per_patient_distribution": self.notes_per_patient_distribution.to_dict(
                orient="records"
            ),
        }


class CohortStatistics:
    """Compute and optionally display statistics for a cohort DataFrame.

    Attributes
    ----------
    cfg : StatisticsConfig
        Configuration for the statistics run.
    log : logging.Logger
        Logger used for warnings and status messages.
    console : rich.console.Console
        Console used for terminal table output.
    """

    def __init__(self, config: StatisticsConfig, logger: logging.Logger = LOG) -> None:
        self.cfg = config
        self.log = logger
        self.console = Console()

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    def compute(self, df: pd.DataFrame) -> StatisticsResult:
        """Compute statistics for ``df`` and optionally display or persist them.

        Parameters
        ----------
        df : pandas.DataFrame
            Input dataframe with at least PERSON_ID and NOTE_TITLE columns.

        Returns
        -------
        StatisticsResult
            Structured result containing the computed summary tables.
        """
        self._validate_input(df)

        person_id_col = self.cfg.person_id_column
        note_title_col = self.cfg.note_title_column

        total_notes = len(df)
        unique_patients = int(df[person_id_col].nunique(dropna=True))

        notes_per_type = self._build_notes_per_type(df, note_title_col)
        notes_per_patient_distribution = self._build_patient_distribution(df, person_id_col)

        result = StatisticsResult(
            total_notes=total_notes,
            unique_patients=unique_patients,
            notes_per_type=notes_per_type,
            notes_per_patient_distribution=notes_per_patient_distribution,
        )

        if self.cfg.enabled:
            self.display(result)
            if self.cfg.output_path is not None:
                self.save_summary(result, self.cfg.output_path)

        return result

    def display(self, result: StatisticsResult) -> None:
        """Render statistics as compact tables in the terminal.

        Parameters
        ----------
        result : StatisticsResult
            Computed statistics to display.

        Returns
        -------
        None
            This method prints tables to the console.
        """
        self.console.print("\n[bold cyan]Cohort Statistics[/bold cyan]")

        summary = Table(show_header=True, header_style="bold magenta")
        summary.add_column("Metric", style="cyan")
        summary.add_column("Value", style="green")
        summary.add_row("Total Notes", str(result.total_notes))
        summary.add_row("Unique Patients", str(result.unique_patients))
        summary.add_row(
            "Avg Notes / Patient",
            f"{result.total_notes / max(result.unique_patients, 1):.2f}",
        )
        self.console.print(summary)

        if self.cfg.include_note_type_distribution:
            self._print_table(
                title="Notes per Type",
                data=result.notes_per_type,
                columns=(self.cfg.note_title_column, "count"),
                max_rows=self.cfg.top_n_note_types,
            )

        if self.cfg.include_patient_distribution:
            self._print_table(
                title="Notes per Patient Distribution",
                data=result.notes_per_patient_distribution,
                columns=("notes_per_patient", "patient_count"),
                max_rows=None,
            )

    def save_summary(self, result: StatisticsResult, output_path: Path | str) -> None:
        """Persist a compact CSV summary with scalar statistics only.

        Parameters
        ----------
        result : StatisticsResult
            Computed statistics used to build the scalar summary.
        output_path : pathlib.Path | str
            Target path for the CSV file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        summary_df = pd.DataFrame(
            {
                "metric": [
                    "total_notes",
                    "notes_per_type",
                    "unique_patients",
                    "notes_per_patient_min",
                    "notes_per_patient_max",
                    "avg_notes_per_patient",
                ],
                "value": [
                    result.total_notes,
                    result.notes_per_type.to_dict(orient="records"),
                    result.unique_patients,
                    result.notes_per_patient_distribution["notes_per_patient"].min(),
                    result.notes_per_patient_distribution["notes_per_patient"].max(),
                    result.total_notes / max(result.unique_patients, 1),
                ],
            }
        )
        summary_df.to_csv(output_path, index=False)
        self.log.info("Saved statistics summary to %s", output_path)

    # ------------------------------------------------------------------
    # Visualizations
    # ------------------------------------------------------------------

    def plot_note_type_distribution(
        self,
        result: StatisticsResult,
        top_n: Optional[int] = None,
    ) -> None:
        """Plot the note type distribution as a horizontal bar chart.

        Parameters
        ----------
        result : StatisticsResult
            Computed statistics containing the note type table.
        top_n : int | None, optional
            Optional limit for the number of note types shown.
        """
        data = result.notes_per_type.head(top_n) if top_n is not None else result.notes_per_type
        if data.empty:
            self.log.warning("No note type data available for plotting.")
            return

        plt.figure(figsize=(12, max(4, 0.45 * len(data))))
        plt.barh(data[self.cfg.note_title_column].astype(str), data["count"], color="#4C78A8")
        plt.gca().invert_yaxis()
        plt.xlabel("Count")
        plt.ylabel(self.cfg.note_title_column)
        plt.title("Notes per Type")
        plt.tight_layout()
        plt.show()

    def plot_patient_distribution(self, result: StatisticsResult) -> None:
        """Plot the distribution of notes per patient as a bar chart.

        Parameters
        ----------
        result : StatisticsResult
            Computed statistics containing the patient distribution table.
        """
        data = result.notes_per_patient_distribution
        if data.empty:
            self.log.warning("No patient distribution data available for plotting.")
            return

        plt.figure(figsize=(10, 5))
        plt.bar(
            data["notes_per_patient"].astype(str),
            data["patient_count"],
            color="#59A14F",
        )
        plt.xlabel("Notes per Patient")
        plt.ylabel("Patient Count")
        plt.title("Notes per Patient Distribution")
        plt.tight_layout()
        plt.show()

    def wordcloud(self, df: pd.DataFrame, text_column: str) -> None:
        """Generate a word cloud for the specified text column.

        Parameters
        ----------
        df : pandas.DataFrame
            Input dataframe containing the text column.
        text_column : str
            Name of the column used to build the word cloud.
        """
        if text_column not in df.columns:
            self.log.error("Missing required column for word cloud: %s", text_column)
            return

        text = " ".join(df[text_column].dropna().astype(str).tolist())
        if not text.strip():
            self.log.warning("No text available for word cloud generation.")
            return

        wordcloud = WordCloud(width=1200, height=600, background_color="white").generate(text)

        plt.figure(figsize=(15, 7.5))
        plt.imshow(wordcloud, interpolation="bilinear")
        plt.axis("off")
        plt.title(f"Word Cloud for {text_column}")
        plt.tight_layout()
        plt.show()

    # ------------------------------------------------------------------
    # Validation and aggregation helpers
    # ------------------------------------------------------------------

    def _validate_input(self, df: pd.DataFrame) -> None:
        """Validate the input dataframe before statistics are computed.

        Parameters
        ----------
        df : pandas.DataFrame
            Input dataframe to validate.

        Raises
        ------
        ValueError
            If the dataframe is empty or missing required columns.
        """
        if df is None or df.empty:
            raise ValueError("Input dataframe is empty.")

        missing_columns = {
            column
            for column in (self.cfg.person_id_column, self.cfg.note_title_column)
            if column not in df.columns
        }
        if missing_columns:
            raise ValueError(f"Missing required columns: {sorted(missing_columns)}")

    def _build_notes_per_type(self, df: pd.DataFrame, note_title_col: str) -> pd.DataFrame:
        """Build a note type frequency table.

        Parameters
        ----------
        df : pandas.DataFrame
            Input dataframe.
        note_title_col : str
            Column name containing the note type/title.

        Returns
        -------
        pandas.DataFrame
            Table with note titles and counts.
        """
        notes_per_type = df[note_title_col].value_counts(dropna=False).reset_index()
        notes_per_type.columns = [note_title_col, "count"]
        return notes_per_type

    def _build_patient_distribution(self, df: pd.DataFrame, person_id_col: str) -> pd.DataFrame:
        """Build a distribution of notes per patient.

        Parameters
        ----------
        df : pandas.DataFrame
            Input dataframe.
        person_id_col : str
            Column name containing the patient identifier.

        Returns
        -------
        pandas.DataFrame
            Table with notes-per-patient frequencies.
        """
        notes_per_patient = df.groupby(person_id_col).size()
        distribution = notes_per_patient.value_counts().sort_index().reset_index()
        distribution.columns = ["notes_per_patient", "patient_count"]
        return distribution


    def _print_table(
        self,
        title: str,
        data: pd.DataFrame,
        columns: tuple[str, str],
        max_rows: int | None,
    ) -> None:
        """Print a compact rich table.

        Parameters
        ----------
        title : str
            Table heading.
        data : pandas.DataFrame
            Dataframe used to populate the table.
        columns : tuple[str, str]
            Column names to display from the dataframe.
        max_rows : int | None
            Optional limit for displayed rows.
        """
        self.console.print(f"\n[bold]{title}:[/bold]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column(columns[0], style="cyan")
        table.add_column(columns[1], style="green")

        rows = data.head(max_rows) if max_rows is not None else data
        for _, row in rows.iterrows():
            table.add_row(str(row[columns[0]]), str(row[columns[1]]))

        self.console.print(table)
