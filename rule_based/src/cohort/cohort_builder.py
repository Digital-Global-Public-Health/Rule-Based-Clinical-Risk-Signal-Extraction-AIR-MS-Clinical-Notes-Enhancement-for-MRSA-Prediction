# src/cohort/cohort_builder.py
"""
Cohort building pipeline for the MRSA NLP rule-based project.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from tqdm import tqdm
from hana_ml.dataframe import DataFrame as HDF

import pyarrow.parquet as pq
import polars as pl
import pandas as pd
import logging


LOG = logging.getLogger("mrsa_nlp.rule.cohort")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class CohortConfig:
    """
    Tunable parameters for the cohort builder.

    Attributes
    ----------
    mrsa_predictions_interim_dir : Path
        Path to mrsa_risk_predictions/data/interim/airms/ (relative to
        project root or absolute).  Default resolves two directories above
        this project's root.
    cohort_parquet : str
        Filename inside mrsa_predictions_interim_dir that holds the final
        matched cohort.
    schema : str
        HANA schema that owns the clinical data tables.
    notes_table : str
        Table name for clinical notes (typically NOTE in OMOP CDM).
    person_table : str
        Table name for person demographics (PERSON in OMOP CDM).
    note_out_dir : Path
        Local directory where note chunks are stored.
    cohort_saving_path : Path
        Output path for the mrsa_cohort_person_list.parquet file.
    chunk_size : int
        Number of PERSON_IDs fetched per HANA query to limit memory usage.
    min_note_date : str
        Earliest NOTE_DATE to include (ISO format YYYY-MM-DD).
    note_type_concept_ids : list of int, optional
        OMOP NOTE_TYPE_CONCEPT_IDs to include.  None = all types.
    debug : bool
        When True limits mining to the first 'debug_n_persons' persons.
    debug_n_persons : int
        How many persons to process in debug mode.
    """
    mrsa_predictions_interim_dir: str = str(Path(
        "../../mrsa_risk_predictions/data/interim/airms"
    ))
    cohort_parquet: str = "mrsa_visit_cohort.parquet"
    matched_pairs_parquet: str = "mrsa_matched_pairs.parquet"
    schema: str = "CDMPHI"
    notes_table: str = "NOTE"
    person_table: str = "PERSON"
    visit_table: str = "VISIT_OCCURRENCE"
    note_out_dir: str = str(Path("data/interim/airms/notes"))
    cohort_saving_path: str = str(Path(
        "data/interim/airms/mrsa_cohort_person_episodes_lists.parquet"
    ))
    chunk_size: int = 500
    min_note_date: str = "2014-07-14"
    note_type_concept_ids: Optional[List[int]] = None
    debug: bool = False
    debug_n_persons: int = 20
    selected_note_titles: List[str] = field(default_factory=lambda: [
        "Progress Notes", "ED Notes", "ED Provider Notes",
        "ED Triage/Intake", "Attestation", "Consults", "Event Note",
        "ED Progress Notes", "H&P", "Discharge Summary", "Procedures",
        "ED Procedure", "IP Operative Report", "ED Attending",
        "Brief Op Note", "Transfer of Care", "ED Disposition Decision",
        "Miscellaneous", "Discharge Progress Note",
        "Interdisciplinary Rounds", "Plan of Care", "ED Psychiatric",
        "Pre-Op Medical Assessment", "ED Psych Progress",
        "Initial Assessments", "PeriOperative Record",
        "Interval H&P Note", "Advance Care Planning",
        "Observation Provider Note", "Full Operative Note",
        "ED Psych Attending", "Medical Student Notes",
        "Discharge Summary Deceased Patient", "ED Triage Notes",
        "Addendum Discharge Summary",
    ])

# ---------------------------------------------------------------------------
# Builder class
# ---------------------------------------------------------------------------

class CohortBuilder:
    """
    Orchestrates cohort creation and note mining for the NLP pipeline.

    Parameters
    ----------
    config : CohortConfig
        Configuration object with all tunable parameters.
    conn : hana_ml.dataframe.ConnectionContext
        Open HANA connection context.
    logger : logging.Logger, optional
        Logger to use; defaults to module-level LOG.
        
    """
    def __init__(
        self,
        config: CohortConfig,
        conn,
        logger: logging.Logger = LOG,
    ) -> None:
        self.cfg = config
        self.conn = conn
        self.log = logger
        self.cohort_df = None
        self.case_df = None
        self.control_df = None

    # ------------------------------------------------------------------
    # load existing cohort
    # ------------------------------------------------------------------

    def load_mrsa_predictions_cohort(self):
        file_path = (
            f"{self.cfg.mrsa_predictions_interim_dir}/"
            f"{self.cfg.cohort_parquet}"
        )

        try:
            df = pl.read_parquet(file_path).to_pandas()
        except FileNotFoundError:
            self.log.error(f"{file_path} could not be found.")
            raise

        required_cols = {
            "PERSON_ID", "LABEL", "XTN_PATIENT_EPIC_MRN",
            "VISIT_OCCURRENCE_ID", "INDEX_DATETIME", "EPISODE_ID",
            "N_VISITS",
        }
        missing_cols = required_cols - set(df.columns)
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        df = df.sort_values("LABEL", ascending=False).drop_duplicates("PERSON_ID")
        df = df.reset_index(drop=True)

        n_total = df["PERSON_ID"].nunique()
        n_cases = (df["LABEL"] == 1).sum()
        n_controls = (df["LABEL"] == 0).sum()

        self.log.info("Total Patients (CASE): %s", n_cases)
        self.log.info("Total Patients (CONTROL): %s", n_controls)
        self.log.info("Total Patients (CASE + CONTROL): %s", n_total)
        self.log.info("Cohort loaded successfully.")

        self.cohort_df = df
        self.case_df = df[df["LABEL"] == 1]
        self.control_df = df[df["LABEL"] == 0]

    # ------------------------------------------------------------------
    # return cohort dataframe
    # ------------------------------------------------------------------

    def get_cohort(self) -> pd.DataFrame:
        if self.cohort_df is not None:
            return self.cohort_df
        raise ValueError("Cohort dataframe is empty, first load the data frame!!")

    # ------------------------------------------------------------------
    # look up MRNs
    # ------------------------------------------------------------------

    def get_person_mrns(self) -> List:
        required_cols = {"XTN_PATIENT_EPIC_MRN"}
        missing_cols = required_cols - set(self.get_cohort().columns)
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        return list(self.get_cohort().XTN_PATIENT_EPIC_MRN)

    # ------------------------------------------------------------------
    # save the cohort
    # ------------------------------------------------------------------

    def save_cohort_list(self):
        if self.cohort_df is None or self.cohort_df.empty:
            raise ValueError(
                "Cohort not loaded. Call `load_mrsa_predictions_cohort()` first."
            )

        df = self.cohort_df

        missing_mrn = df["XTN_PATIENT_EPIC_MRN"].isna().sum()
        self.log.info("Patients missing MRN: %d", missing_mrn)

        n_cases = (df["LABEL"] == 1).sum()
        n_controls = (df["LABEL"] == 0).sum()

        self.log.info("Cases (LABEL=1): %d", n_cases)
        self.log.info("Controls (LABEL=0): %d", n_controls)

        parquet_path = Path(self.cfg.cohort_saving_path)
        csv_path = parquet_path.with_suffix(".csv")
        parquet_path.parent.mkdir(parents=True, exist_ok=True)

        if parquet_path.exists() and csv_path.exists():
            self.log.info(
                "Cohort files already exist. Skipping save.\n"
                "Parquet: %s\nCSV: %s", parquet_path, csv_path,
            )
        else:
            df.to_parquet(parquet_path, index=False)
            df.to_csv(csv_path, index=False)
            self.log.info("Cohort saved to: %s", parquet_path)
            self.log.info("CSV copy saved to: %s", csv_path)

    # ------------------------------------------------------------------
    # check if notes already exist
    # ------------------------------------------------------------------

    def check_notes_exist(self) -> Dict[str, Any]:
        note_dir = Path(self.cfg.note_out_dir)
        found_ids: set[int] = set()

        if note_dir.exists():
            for f in note_dir.glob("note_*.parquet"):
                stem = f.stem
                try:
                    pid = int(stem.replace("note_", ""))
                    found_ids.add(pid)
                except ValueError:
                    continue

        self.log.info(
            f"[check_notes_exist] Found {len(found_ids)} existing "
            f"person-level note files in {note_dir}"
        )
        return {
            "found": len(found_ids) > 0,
            "found_person_ids": found_ids,
            "count": len(found_ids),
        }

    # ------------------------------------------------------------------
    # running sql using hana
    # ------------------------------------------------------------------

    def run_sql(self, sql: str, idx: int) -> Optional[pd.DataFrame]:
        try:
            self.log.info(f"Running SQL on HANA for index: {idx}")
            return HDF(
                connection_context=self.conn, select_statement=sql
            ).collect()
        except Exception as e:
            self.log.error(f"SQL execution failed: {e}\nQuery:\n{sql}")
            raise RuntimeError(f"HANA query failed: {e}") from e

    # ------------------------------------------------------------------
    # build query for a single person
    # ------------------------------------------------------------------

    def build_notes_query(self, person_id: int) -> str:
        titles_str = ", ".join(
            f"LOWER('{t.strip()}')" for t in self.cfg.selected_note_titles
        )
        query = f"""
            SELECT
                N.NOTE_ID, N.PERSON_ID, N.NOTE_DATE, N.NOTE_DATETIME,
                N.NOTE_TYPE_CONCEPT_ID, N.NOTE_CLASS_CONCEPT_ID,
                N.NOTE_TITLE, N.NOTE_TEXT, N.VISIT_OCCURRENCE_ID,
                N.ENCODING_CONCEPT_ID, N.LANGUAGE_CONCEPT_ID,
                N.NOTE_SOURCE_VALUE, N.PROVIDER_ID,
                N.NOTE_CLASS_CONCEPT_CODE, N.NOTE_CLASS_CONCEPT_NAME,
                N.XTN_NOTE_CLASS_SOURCE_CONCEPT_NAME
            FROM {self.cfg.schema}.{self.cfg.notes_table} N
            WHERE N.PERSON_ID = {person_id}
              AND N.NOTE_DATE >= '{self.cfg.min_note_date}'
              AND LOWER(TRIM(N.NOTE_TITLE)) IN ({titles_str})
        """
        return query.strip()

    # ------------------------------------------------------------------
    # mine notes per person
    # ------------------------------------------------------------------

    def mine_notes_(
        self,
        person_ids: Optional[List[int]] = None,
        compression: str = "snappy",
    ) -> None:
        if person_ids is None:
            if not hasattr(self, "cohort_df") or self.cohort_df is None:
                self.log.info("[mine_notes] cohort_df not loaded – loading now.")
                self.load_mrsa_predictions_cohort()
            person_ids = self.cohort_df["PERSON_ID"].unique().tolist()

        note_dir = Path(self.cfg.note_out_dir)
        note_dir.mkdir(parents=True, exist_ok=True)

        status = self.check_notes_exist()
        found_persons: set[int] = status["found_person_ids"]
        remaining_persons = [
            pid for pid in person_ids if pid not in found_persons
        ]

        self.log.info(
            f"[mine_notes] Total cohort: {len(person_ids)} | "
            f"Already mined: {len(found_persons)} | "
            f"Remaining: {len(remaining_persons)}"
        )

        if not remaining_persons:
            self.log.info(
                "[mine_notes] All person notes already mined – "
                "nothing new to mine."
            )
        else:
            notes_written = 0
            empty_count = 0
            failed_ids: list[int] = []
            idx = 0

            for pid in tqdm(
                remaining_persons,
                desc="Mining notes",
                disable=self.cfg.debug,
            ):
                out_path = note_dir / f"note_{pid}.parquet"
                try:
                    sql = self.build_notes_query(pid)
                    df = self.run_sql(sql, idx)
                    idx += 1

                    if df.empty:
                        empty_count += 1
                        self.log.debug(
                            f"[mine_notes] PERSON_ID={pid}: 0 notes"
                        )
                    else:
                        notes_written += len(df)
                        self.log.debug(
                            f"[mine_notes] PERSON_ID={pid}: "
                            f"{len(df)} notes saved"
                        )

                    df.to_parquet(
                        out_path, index=False, compression=compression
                    )

                except Exception as e:
                    self.log.error(
                        f"[mine_notes] PERSON_ID={pid} FAILED: {e}"
                    )
                    failed_ids.append(pid)
                    sentinel = note_dir / f"note_{pid}_FAILED.txt"
                    sentinel.write_text(str(e))

            self.log.info(
                f"[mine_notes] Mining complete | "
                f"Persons processed: {len(remaining_persons)} | "
                f"Total notes written: {notes_written} | "
                f"Persons with 0 notes: {empty_count} | "
                f"Failed: {len(failed_ids)}"
            )
            if failed_ids:
                self.log.warning(
                    f"[mine_notes] Failed PERSON_IDs: {failed_ids}"
                )
                
        all_files = sorted(note_dir.glob("note_*.parquet"))
        parquet_files = [
            f for f in all_files
            if f.stem.replace("note_", "").isdigit()
        ]

        if not parquet_files:
            self.log.warning("[mine_notes] No parquet files found to merge.")
            return

        self.log.info(
            f"[mine_notes] Streaming merge of {len(parquet_files)} person "
            f"files into cohort_notes.parquet …"
        )

        merged_dir = note_dir / "all"
        merged_dir.mkdir(parents=True, exist_ok=True)
        merged_path = merged_dir / "cohort_notes.parquet"

        writer: Optional[pq.ParquetWriter] = None
        total_notes = 0
        person_ids_seen: set[int] = set()

        try:
            for f in tqdm(
                parquet_files,
                desc="Merging parquets",
                disable=self.cfg.debug,
            ):
                table = pq.read_table(f)

                if table.num_rows == 0:
                    continue

                if writer is None:
                    writer = pq.ParquetWriter(
                        merged_path, table.schema,
                        compression=compression,
                    )

                writer.write_table(table)
                total_notes += table.num_rows
                person_ids_seen.update(
                    table.column("PERSON_ID").to_pylist()
                )
        finally:
            if writer is not None:
                writer.close()

        self.log.info(
            f"[mine_notes] cohort_notes.parquet saved – "
            f"{total_notes} total notes from "
            f"{len(person_ids_seen)} persons"
        )

    # ------------------------------------------------------------------
    # load all mined notes (lazy — handles 700 GB)
    # ------------------------------------------------------------------

    def load_all_notes(
        self,
        eager: bool = False,
    ) -> pl.LazyFrame | pl.DataFrame:
        """
        Return all mined notes as a Polars LazyFrame (default) or
        a collected DataFrame.
        
        it reads nothing into RAM until you call .filter()/.select()
        followed by .collect().

        Parameters
        ----------
        eager : bool
            If True, collect the full dataset into memory immediately.
            WARNING: this requires ~700 GB+ RAM.

        Returns
        -------
        pl.LazyFrame or pl.DataFrame

        Usage
        -----
        >>> lf = builder.load_all_notes()              # lazy, 0 RAM
        >>> # filter first, then collect
        >>> df = (
        ...     lf.filter(pl.col("PERSON_ID") == 123)
        ...     .select(["PERSON_ID", "NOTE_DATE", "NOTE_TEXT"])
        ...     .collect()
        ... )
        >>> # or collect everything (needs enough RAM)
        >>> df = builder.load_all_notes(eager=True)
        """
        merged_path = (
            Path(self.cfg.note_out_dir) / "all" / "cohort_notes.parquet"
        )

        if not merged_path.exists():
            note_dir = Path(self.cfg.note_out_dir)
            parquet_files = sorted([
                f for f in note_dir.glob("note_*.parquet")
                if f.stem.replace("note_", "").isdigit()
            ])

            if not parquet_files:
                raise FileNotFoundError(
                    f"No note parquet files found in {note_dir}. "
                    f"Run mine_notes_() first."
                )

            self.log.info(
                f"[load_all_notes] Merged file not found. "
                f"Scanning {len(parquet_files)} individual files …"
            )
            lf = pl.scan_parquet(
                [str(f) for f in parquet_files],
                hive_partitioning=False,
            )
        else:
            self.log.info(
                f"[load_all_notes] Scanning {merged_path}"
            )
            lf = pl.scan_parquet(str(merged_path))

        if eager:
            self.log.warning(
                "[load_all_notes] Collecting full dataset into memory. "
                "This may require 700 GB+ RAM."
            )
            return lf.collect()

        return lf

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(
        self
    ) -> pl.LazyFrame:
        """
        Execute the full cohort-building pipeline.

        Steps
        -----
        1. load_mrsa_predictions_cohort()
        2. save_cohort_list()
        3. mine_notes_()
        4. load_all_notes()  →  LazyFrame

        Returns
        -------
        pl.LazyFrame
            Lazy handle over all mined notes. Call .collect() or
            .filter(...).collect() to materialize.
        """
        self.load_mrsa_predictions_cohort()
        self.log.info("\n%s", self.get_cohort().describe(include="all"))
        self.save_cohort_list()
        self.mine_notes_()
        return self.load_all_notes()