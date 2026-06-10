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
    selected_person_ids : list[str], optional
        Person IDs to keep. Used as a fallback or merged with CSV-based IDs.
    note_title_column : str
        Name of the column that stores the note type/title.
    selected_note_titles : list[str], optional
        Allowed note titles. If empty, no note-title filter is applied.
    output_path : str | None
        Optional path where the filtered subset is saved as parquet.
    """

    person_id_column: str = "PERSON_ID"
    person_ids_csv_path: Optional[str] = None
    person_ids_csv_column: str = "PERSON_ID"
    selected_person_ids: List[str] = field(default_factory=list)
    note_title_column: str = "NOTE_TITLE"
    selected_note_titles: List[str] = field(default_factory=list)
    output_path: Optional[str] = None


class SubsetBuilder:
    """
    Build a filtered note subset from a pandas DataFrame.

    The builder can optionally filter the input dataframe by person ID and
    note title, then stores all matching notes in the configured output file.
    """

    def __init__(self, config: SubsetConfig, logger: logging.Logger = LOG) -> None:
        self.cfg = config
        self.log = logger

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

            csv_patient_ids = person_df[self.cfg.person_ids_csv_column].map(
                self._normalize_patient_id
            )
            person_ids.update(pid for pid in csv_patient_ids if pid is not None)

        return person_ids

    def select_subset(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Return the filtered subset of the given dataframe.

        Parameters
        ----------
        df : pandas.DataFrame
            Input dataframe to sample from.

        Returns
        -------
        pandas.DataFrame
            Filtered subset.
        """
        if df is None or df.empty:
            raise ValueError("Input dataframe is empty.")

        working_df = df.copy()

        allowed_person_ids = self._load_person_ids()
        if allowed_person_ids:
            if self.cfg.person_id_column not in working_df.columns:
                raise ValueError(
                    f"Missing required column: {self.cfg.person_id_column}"
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

        filtered_df = working_df.reset_index(drop=True)

        if filtered_df.empty:
            self.log.warning("No rows left after filtering; returning empty dataframe.")
        else:
            self.log.info(
                "Selected %d rows from %d input rows.",
                len(filtered_df),
                len(df),
            )

        if self.cfg.output_path:
            out_path = Path(self.cfg.output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            filtered_df.to_parquet(out_path, index=False)
            self.log.info("Saved filtered subset to %s", out_path)

        return filtered_df
