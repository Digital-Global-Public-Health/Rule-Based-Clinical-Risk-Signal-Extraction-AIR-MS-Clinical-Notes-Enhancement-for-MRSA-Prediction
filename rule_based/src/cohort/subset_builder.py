"""
Subset selection utilities for the MRSA NLP rule-based project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import logging

import pandas as pd


LOG = logging.getLogger("mrsa_nlp.rule.cohort.subset")


@dataclass
class SubsetConfig:
    """
    Configuration for deterministic note subset selection.

    Attributes
    ----------
    person_id_column : str
        Name of the column that stores the person identifier.
    person_ids_csv_path : str | None
        Optional CSV file containing the person IDs to keep.
    person_ids_csv_column : str
        Name of the column in the CSV file that stores the person identifier.
    person_ids_csv_label_column : str
        Name of the column in the CSV file that stores the label.
    selected_labels : list[int], optional
        Allowed labels from the CSV file. Use [0], [1], or [0, 1].
    selected_person_ids : list[str], optional
        Person IDs to keep. Merged with CSV-based IDs. Empty by default (no filter).
    note_title_column : str
        Name of the column that stores the note type/title.
    selected_note_titles : list[str], optional
        Allowed note titles. If empty, no note-title filter is applied.
    output_path : str | None
        Optional directory where chunked parquet files are written.
    chunk_size : int
        Number of rows per output parquet chunk file. Default is 1 (one row per file).
    """

    mrsa_cohort_notes_path: str = "/sc/arion/projects/MRSA-HPI-MS/airms-app-host-and-hospital-adaptation-of-mrsa/mrsa_nlp/rule_based/data/interim/airms/notes/all/cohort_notes.parquet"
    person_id_column: str = "PERSON_ID"
    person_ids_csv_path: Optional[str] = None
    person_ids_csv_column: str = "PERSON_ID"
    person_ids_csv_label_column: str = "LABEL"
    selected_labels: List[int] = field(default_factory=lambda: [0, 1])
    selected_person_ids: List[str] = field(default_factory=list)
    note_title_column: str = "NOTE_TITLE"
    selected_note_titles: List[str] = field(default_factory=lambda: [
        "H&P", "Progress Notes", "Discharge Summary", "Consults"
    ])
    output_path: Optional[str] = None
    chunk_size: int = 1


class SubsetBuilder:
    """
    Build a filtered note subset from a pandas DataFrame.

    The builder can optionally filter the input dataframe by person ID and
    note title, then stores all matching notes in the configured output file.
    """

    def __init__(self, config: SubsetConfig, logger: logging.Logger = LOG) -> None:
        self.cfg = config
        self.log = logger
        self.cohort_df = None
        self.subset_df = None

    # -----------------------------------------------------------------------
    # load mrsa cohort notes
    # -----------------------------------------------------------------------

    def load_cohort_notes(self):
        """Load the MRSA cohort notes from the configured path."""
        cohort_path = Path(self.cfg.mrsa_cohort_notes_path)
        if not cohort_path.exists():
            raise FileNotFoundError(f"MRSA cohort notes file not found: {cohort_path}")

        self.log.info("Loading MRSA cohort notes from %s", cohort_path)
        self.cohort_df = pd.read_parquet(cohort_path)
        self.log.info("Loaded %d notes from the MRSA cohort.", len(self.cohort_df))


    @staticmethod
    def _normalize_patient_id(value: object) -> object | None:
        """Normalize IDs so integer-like PERSON_ID values compare consistently."""
        if pd.isna(value):
            return None

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            try:
                return int(value)
            except ValueError:
                return value

        try:
            return int(value)
        except (TypeError, ValueError):
            value_str = str(value).strip()
            return value_str or None

    def _load_person_ids(self) -> set[str]:
        """Collect person IDs from the config and optional CSV file."""
        person_ids = {
            normalized_id
            for person_id in self.cfg.selected_person_ids
            if (normalized_id := self._normalize_patient_id(person_id)) is not None
        }

        if self.cfg.person_ids_csv_path:
            csv_path = Path(self.cfg.person_ids_csv_path)
            if not csv_path.exists():
                raise FileNotFoundError(f"Person ID CSV not found: {csv_path}")

            person_df = pd.read_csv(csv_path)
            if self.cfg.person_ids_csv_column not in person_df.columns:
                raise ValueError(
                    f"Missing required column in person CSV: {self.cfg.person_ids_csv_column}"
                )
            if self.cfg.person_ids_csv_label_column not in person_df.columns:
                raise ValueError(
                    f"Missing required label column in person CSV: {self.cfg.person_ids_csv_label_column}"
                )

            allowed_labels = {int(label) for label in self.cfg.selected_labels}
            if not allowed_labels:
                raise ValueError("selected_labels must contain at least one value.")

            csv_labels = pd.to_numeric(
                person_df[self.cfg.person_ids_csv_label_column], errors="coerce"
            )
            csv_filtered = person_df[csv_labels.isin(allowed_labels)]
            csv_patient_ids = csv_filtered[self.cfg.person_ids_csv_column].map(
                self._normalize_patient_id
            )
            person_ids.update(pid for pid in csv_patient_ids if pid is not None)

        return person_ids

    def select_subset(self):
        """
        Loads the MRSA cohort notes and applies filters based on person IDs and note titles.

        """
        if self.cohort_df is None or self.cohort_df.empty:
            raise ValueError("Cohort not loaded or empty. Please run load_cohort_notes() first.")

        working_df = self.cohort_df.copy()

        allowed_person_ids = self._load_person_ids()
        if allowed_person_ids:
            if self.cfg.person_id_column not in working_df.columns:
                raise ValueError(
                    f"Missing required column in cohort dataframe: {self.cfg.person_id_column}"
                )
            normalized_patient_ids = working_df[self.cfg.person_id_column].map(
                self._normalize_patient_id
            )
            working_df = working_df[normalized_patient_ids.isin(allowed_person_ids)]

        if self.cfg.selected_note_titles:
            if self.cfg.note_title_column not in working_df.columns:
                raise ValueError(
                    f"Missing required column: {self.cfg.note_title_column}"
                )

            allowed_titles = {
                title.strip().lower() for title in self.cfg.selected_note_titles
            }
            working_df = working_df[
                working_df[self.cfg.note_title_column]
                .astype(str)
                .str.strip()
                .str.lower()
                .isin(allowed_titles)
            ]

        self.subset_df = working_df.reset_index(drop=True)

        if self.subset_df.empty:
            self.log.warning("No rows left after filtering; returning empty dataframe.")
        else:
            self.log.info(
                "Selected %d rows from %d input rows.",
                len(self.subset_df),
                len(self.cohort_df),
            )

    def save_subset(self):
        if self.cfg.output_path:
            out_path = Path(self.cfg.output_path)

            if out_path.suffix:
                raise ValueError(
                    "output_path must point to a directory, not a file: %s" % out_path
                )

            out_path.mkdir(parents=True, exist_ok=True)

            chunk_size = max(1, self.cfg.chunk_size)
            n_rows = len(self.subset_df)
            n_chunks = max(1, (n_rows + chunk_size - 1) // chunk_size)

            for chunk_index in range(n_chunks):
                chunk = self.subset_df.iloc[
                    chunk_index * chunk_size : (chunk_index + 1) * chunk_size
                ]
                chunk_path = out_path / f"chunk_{chunk_index:04d}.parquet"
                chunk.to_parquet(chunk_path, index=False)

            self.log.info(
                "Saved %d filtered notes as %d chunked parquet file(s) to %s",
                n_rows,
                n_chunks,
                out_path,
            )

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self) -> pd.DataFrame:
        """
        Run the full subset selection process.
        
        Steps
        -----
        1. Load the MRSA cohort notes.
        2. Select the subset based on person IDs and note titles.
        3. Save the filtered subset to disk.
        """
        self.load_cohort_notes()
        self.select_subset()
        self.save_subset()
        return self.subset_df