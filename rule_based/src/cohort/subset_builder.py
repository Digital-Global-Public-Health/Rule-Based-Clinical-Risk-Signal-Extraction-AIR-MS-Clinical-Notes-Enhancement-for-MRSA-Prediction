# src/cohort/subset_builder.py
"""
Subset selection from the MRSA cohort.

This module selects a subset of notes from the MRSA cohort based on specified
person IDs and note titles.

Input  : MRSA cohort notes in parquet format, optional CSV of person IDs with labels.
Output : data/interim/airms/notes/chunk_*.parquet
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import logging

import pandas as pd

from src.utils_io import ensure_dir, read_parquet, write_csv, write_parquet


LOG = logging.getLogger("mrsa_nlp.rule.cohort.subset")


@dataclass
class SubsetConfig:
    """
    Configuration for deterministic note subset selection.

    Attributes
    ----------
    mrsa_cohort_notes_path : str
        Path to the parquet file with the merged MRSA cohort notes.
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
        Directory where chunked parquet files are written.
    chunk_size : int
        Number of rows per output parquet chunk file. Default is 1 (one row per file).
    n_patients : int | None
        Optional limit on the number of unique patients to include in the subset.
        Applied to the explicit/CSV person-ID list if one is given, otherwise
        to the distinct person IDs found in the cohort dataframe.
        This limit is necessary for creating a small subset for evaluation or debugging purposes.
    n_notes_per_type : int | None
        Optional limit on the number of notes per note type, per patient,
        to include in the subset.
    debug : bool
        If True, limits the resulting subset to the first debug_n_rows rows.
    debug_n_rows : int
        If debug is True, limits the number of rows kept for debugging purposes.
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
    output_path: Optional[str] = "data/interim/airms/notes"
    chunk_size: int = 1
    n_patients: Optional[int] = None
    n_notes_per_type: Optional[int] = None
    debug: bool = False
    debug_n_rows: int = 100


class SubsetBuilder:
    """
    Builds a filtered note subset from a pandas DataFrame.

    The builder can optionally filter the input dataframe by person ID and
    note title, then stores all matching notes in the configured output file.

    Parameters
    ----------
    config : SubsetConfig
        Configuration for this subset builder run.
    logger : logging.Logger, optional
        Logger to use; defaults to module-level LOG.
    run_dir : Path, optional
        Timestamped run directory. If given, a per-patient/per-note-type
        overview (``subset_overview.csv``) is written there.

    Example
    -------
    >>> from src.cohort.subset_builder import SubsetConfig, SubsetBuilder
    >>> cfg = SubsetConfig(debug=True)
    >>> sb = SubsetBuilder(cfg)
    >>> sb.run()
    """

    def __init__(
        self,
        config: SubsetConfig,
        logger: logging.Logger = LOG,
        run_dir: Optional[Path] = None,
    ) -> None:
        self.cfg = config
        self.log = logger
        self.run_dir = run_dir

    # -----------------------------------------------------------------------
    # load mrsa cohort notes
    # -----------------------------------------------------------------------

    def load_cohort_notes(self) -> pd.DataFrame:
        """Load the MRSA cohort notes from the configured path."""
        cohort_path = Path(self.cfg.mrsa_cohort_notes_path)
        if not cohort_path.exists():
            raise FileNotFoundError(f"MRSA cohort notes file not found: {cohort_path}")

        self.log.info("Loading MRSA cohort notes from %s", cohort_path)
        df = read_parquet(cohort_path)
        self.log.info("Loaded %d notes from the MRSA cohort.", len(df))
        return df


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

    # -----------------------------------------------------------------------
    # select subset by person ID and note title
    # -----------------------------------------------------------------------

    def select_subset(self, cohort_df: pd.DataFrame) -> pd.DataFrame:
        """
        Loads the MRSA cohort notes and applies filters based on person IDs and note titles.

        """
        if cohort_df is None or cohort_df.empty:
            raise ValueError("Cohort not loaded or empty. Please run load_cohort_notes() first.")

        allowed_person_ids = self._load_person_ids()

        if self.cfg.n_patients is not None and self.cfg.n_patients > 0:
            if not allowed_person_ids:
                if self.cfg.person_id_column not in cohort_df.columns:
                    raise ValueError(
                        f"Missing required column in cohort dataframe: {self.cfg.person_id_column}"
                    )
                allowed_person_ids = set(
                    cohort_df[self.cfg.person_id_column].map(self._normalize_patient_id)
                )
                allowed_person_ids.discard(None)
            allowed_person_ids = set(sorted(allowed_person_ids, key=str)[: self.cfg.n_patients])
            self.log.info(
                "Limiting to first %d unique patients.",
                len(allowed_person_ids),
            )

        if allowed_person_ids:
            if self.cfg.person_id_column not in cohort_df.columns:
                raise ValueError(
                    f"Missing required column in cohort dataframe: {self.cfg.person_id_column}"
                )
            normalized_patient_ids = cohort_df[self.cfg.person_id_column].map(
                self._normalize_patient_id
            )
            cohort_df = cohort_df[normalized_patient_ids.isin(allowed_person_ids)]

        if self.cfg.selected_note_titles:
            if self.cfg.note_title_column not in cohort_df.columns:
                raise ValueError(
                    f"Missing required column: {self.cfg.note_title_column}"
                )

            allowed_titles = {
                title.strip().lower() for title in self.cfg.selected_note_titles
            }
            cohort_df = cohort_df[
                cohort_df[self.cfg.note_title_column]
                .astype(str)
                .str.strip()
                .str.lower()
                .isin(allowed_titles)
            ]

        subset_df = cohort_df.reset_index(drop=True)

        if self.cfg.n_notes_per_type is not None and self.cfg.n_notes_per_type > 0:
            subset_df = (
                subset_df.groupby(
                    [self.cfg.person_id_column, self.cfg.note_title_column],
                    group_keys=False,
                )
                .head(self.cfg.n_notes_per_type)
                .reset_index(drop=True)
            )
            self.log.info(
                "Limiting to first %d notes per patient per note title; resulting subset has %d rows.",
                self.cfg.n_notes_per_type,
                len(subset_df),
            )

        if self.cfg.debug:
            subset_df = subset_df.head(self.cfg.debug_n_rows).copy()
            self.log.info(
                "Debug mode enabled: limiting subset to first %d rows.",
                len(subset_df),
            )

        if subset_df.empty:
            self.log.warning("No rows left after filtering; returning empty dataframe.")
        else:
            self.log.info(
                "Selected %d rows from %d input rows.",
                len(subset_df),
                len(cohort_df),
            )
        return subset_df

    # -----------------------------------------------------------------------
    # save subset as chunked parquet files
    # -----------------------------------------------------------------------

    def save_subset(self, subset_df: pd.DataFrame) -> None:
        if self.cfg.output_path:
            out_path = Path(self.cfg.output_path)

            if out_path.suffix:
                raise ValueError(
                    "output_path must point to a directory, not a file: %s" % out_path
                )

            ensure_dir(out_path)

            chunk_size = max(1, self.cfg.chunk_size)
            n_rows = len(subset_df)
            n_chunks = max(1, (n_rows + chunk_size - 1) // chunk_size)

            for chunk_index in range(n_chunks):
                chunk = subset_df.iloc[
                    chunk_index * chunk_size : (chunk_index + 1) * chunk_size
                ]
                chunk_path = out_path / f"chunk_{chunk_index:04d}.parquet"
                write_parquet(chunk, chunk_path)

            self.log.info(
                "Saved %d filtered notes as %d chunked parquet file(s) to %s",
                n_rows,
                n_chunks,
                out_path,
            )

    # -----------------------------------------------------------------------
    # per-patient / per-note-type overview
    # -----------------------------------------------------------------------

    def save_overview(self, subset_df: pd.DataFrame) -> Optional[Path]:
        """
        Save a table with one row per patient and one column per note type,
        counting how many notes of that type ended up in the subset.

        Written to ``{run_dir}/subset_overview.csv``. No-op if ``run_dir``
        was not set or the subset is empty.
        """
        if self.run_dir is None:
            self.log.debug("No run_dir configured; skipping subset overview export.")
            return None

        if subset_df.empty:
            self.log.warning("Subset is empty; skipping subset overview export.")
            return None

        overview_df = (
            subset_df.groupby([self.cfg.person_id_column, self.cfg.note_title_column])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
        overview_df.columns.name = None

        overview_path = Path(self.run_dir) / "subset_overview.csv"
        write_csv(overview_df, overview_path)
        self.log.info(
            "Saved subset overview for %d patients to %s",
            len(overview_df),
            overview_path,
        )
        return overview_path

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
        4. Save a per-patient/per-note-type overview, if run_dir was set.
        """
        cohort_df = self.load_cohort_notes()
        subset_df = self.select_subset(cohort_df)
        self.save_subset(subset_df)
        self.save_overview(subset_df)
        self.log.debug("Subset selection process completed successfully.")
        return subset_df