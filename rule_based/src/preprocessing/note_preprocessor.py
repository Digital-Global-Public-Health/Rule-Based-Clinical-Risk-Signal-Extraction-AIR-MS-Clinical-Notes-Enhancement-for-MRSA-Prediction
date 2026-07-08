# src/preprocessing/note_preprocessor.py
"""
Preprocessing pipeline for raw clinical notes.

This module loads the raw note chunks produced by the cohort builder and
applies text-normalisation steps (cleaning, abbreviation expansion, optional
section segmentation) before rule-based extraction.

Input  : data/interim/airms/notes/chunk_*.parquet
Output : data/interim/airms/notes_preprocessed/chunk_*.parquet
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict, List
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

import pandas as pd

from rule_based.src.utils_io import ensure_dir, read_parquet, write_parquet

LOG = logging.getLogger("mrsa_nlp.rule.preprocess")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class PreprocessorConfig:
    """
    Tunable parameters for the note preprocessor.

    Attributes
    ----------
    raw_notes_dir : Path
        Directory containing chunk_*.parquet files from the cohort builder.
    out_dir : Path
        Directory where pre-processed chunk files are written.
    min_note_length : int
        Minimum character length to keep a note.  Shorter notes are dropped.
    max_note_length : int
        Maximum character length; longer notes are truncated at this boundary.
    lowercase : bool
        Convert NOTE_TEXT to lower-case before matching.
    remove_extra_whitespace : bool
        Collapse multiple whitespace characters into a single space.
    expand_abbreviations : bool
        Replace clinical shorthand (e.g. "s/p" → "status post") using the
        built-in abbreviation map.
    segment_sections : bool
        Attempt to identify common clinical note sections
        (HPI, Assessment, Plan, Medications, etc.).
    keep_original_text : bool
        If True, retain the original NOTE_TEXT alongside the cleaned version.
    debug : bool
        When True, process only the first `debug_n_notes` rows.
    debug_n_notes : int
        Rows to process in debug mode.
    """

    raw_notes_dir: Path = Path("data/interim/airms/notes")
    out_dir: Path = Path("data/interim/airms/notes_preprocessed")
    min_note_length: int = 50
    max_note_length: int = 50_000
    lowercase: bool = True
    remove_extra_whitespace: bool = True
    expand_abbreviations: bool = True
    segment_sections: bool = False
    keep_original_text: bool = False
    debug: bool = False
    debug_n_notes: int = 200


# ---------------------------------------------------------------------------
# Abbreviation map (starter set — extend as needed)
# ---------------------------------------------------------------------------

CLINICAL_ABBREVIATIONS: Dict[str, str] = {
    r"\bs/p\b":     "status post",
    r"\bw/o\b":     "without",
    r"\bw/(?=\s|$)": "with",
    r"\bc/o\b":     "complains of",
    r"\bSOB\b":     "shortness of breath",
    r"\bDOE\b":     "dyspnea on exertion",
    r"\bHTN\b":     "hypertension",
    r"\bDM\b":      "diabetes mellitus",
    r"\bDM2\b":     "type 2 diabetes mellitus",
    r"\bCKD\b":     "chronic kidney disease",
    r"\bESRD\b":    "end-stage renal disease",
    r"\bICU\b":     "intensive care unit",
    r"\bSNF\b":     "skilled nursing facility",
    r"\bNH\b":      "nursing home",
    r"\bRA\b":      "rheumatoid arthritis",
    r"\bSLE\b":     "systemic lupus erythematosus",
    r"\bHIV\b":     "human immunodeficiency virus",
    r"\bAIDS\b":    "acquired immunodeficiency syndrome",
    r"\bTx\b":      "transplant",
    r"\bChemo\b":   "chemotherapy",
    r"\bIVDA\b":    "intravenous drug abuse",
    r"\bIVDU\b":    "intravenous drug use",
    r"\bCVL\b":     "central venous line",
    r"\bCVC\b":     "central venous catheter",
    r"\bPICC\b":    "peripherally inserted central catheter",
    r"\bHD\b":      "hemodialysis",
    r"\bPD\b":      "peritoneal dialysis",
    r"\bAbx\b":     "antibiotics",
    r"\bVanc\b":    "vancomycin",
    r"\bPCN\b":     "penicillin",
    r"\bPred\b":    "prednisone",
    r"\bMethylpred\b": "methylprednisolone",
    r"\bDex\b":     "dexamethasone",
    r"\bMTX\b":     "methotrexate",
    r"\bMMF\b":     "mycophenolate mofetil",
    r"\bAZA\b":     "azathioprine",
}


# ---------------------------------------------------------------------------
# Preprocessor class
# ---------------------------------------------------------------------------

class NotePreprocessor:
    """
    Loads raw note chunks and applies text normalisation before extraction.

    Parameters
    ----------
    config : PreprocessorConfig
        Configuration for this preprocessing run.
    logger : logging.Logger, optional
        Logger to use; defaults to module-level LOG.

    Example
    -------
    >>> from src.preprocessing.note_preprocessor import PreprocessorConfig, NotePreprocessor
    >>> cfg = PreprocessorConfig(debug=True)
    >>> pp = NotePreprocessor(cfg)
    >>> pp.run()
    """

    def __init__(
        self,
        config: PreprocessorConfig,
        logger: logging.Logger = LOG,
    ) -> None:
        self.cfg = config
        self.log = logger

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def list_chunk_files(self) -> List[Path]:
        """
        Return sorted list of raw note chunk Parquet files.

        Returns
        -------
        list of Path
            All ``chunk_*.parquet`` files inside cfg.raw_notes_dir,
            sorted lexicographically (which preserves numeric order
            given the zero-padded naming ``chunk_0000.parquet``).

        Raises
        ------
        FileNotFoundError
            If cfg.raw_notes_dir does not exist or contains no chunk files.
            Prompt the user to run the cohort builder first.
        """
        raw_notes_dir = self.cfg.raw_notes_dir

        if not raw_notes_dir.exists() or not raw_notes_dir.is_dir():
            raise FileNotFoundError(
                f"Raw notes directory does not exist: {raw_notes_dir}."
                "Run the cohort builder first."
            )

        chunk_files = sorted(raw_notes_dir.glob("chunk_*.parquet"))
        if not chunk_files:
            raise FileNotFoundError(
                f"No chunk_*.parquet files found in {raw_notes_dir}."
                "Run the cohort builder first."
            )

        return chunk_files

    def load_chunk(self, chunk_path: Path) -> pd.DataFrame:
        """
        Load a single raw note chunk into a DataFrame.

        Parameters
        ----------
        chunk_path : Path
            Path to a ``chunk_NNNN.parquet`` file.

        Returns
        -------
        pd.DataFrame
            Raw notes with at minimum columns:
            NOTE_ID, PERSON_ID, NOTE_DATE, NOTE_TEXT, NOTE_TYPE_CONCEPT_ID,
            VISIT_OCCURRENCE_ID.
        """
        try:
            df = read_parquet(chunk_path)
        except Exception:
            self.log.exception(f"Error loading chunk file {chunk_path}.")
            raise

        required_cols = {"NOTE_ID", "PERSON_ID", "NOTE_DATE", "NOTE_TEXT", "NOTE_TYPE_CONCEPT_ID", "VISIT_OCCURRENCE_ID"}
        missing_cols = required_cols - set(df.columns)

        if missing_cols:
            raise ValueError(f"Chunk file {chunk_path} is missing required columns: {missing_cols}")

        return df

    # ------------------------------------------------------------------
    # Text cleaning methods  (one method per transformation)
    # ------------------------------------------------------------------

    def clean_whitespace(self, text: str) -> str:
        """
        Collapse runs of whitespace (spaces, tabs, newlines) into a single
        space and strip leading/trailing whitespace.

        Parameters
        ----------
        text : str
            Raw note text.

        Returns
        -------
        str
            Whitespace-normalised text.
        """
        if self.cfg.remove_extra_whitespace:
            text = re.sub(r"\s+", " ", text)

        return text.strip()

    def expand_abbreviations(self, text: str) -> str:
        """
        Replace clinical abbreviations with their expanded equivalents using
        the CLINICAL_ABBREVIATIONS mapping (regex, case-insensitive).

        Parameters
        ----------
        text : str
            Note text (may or may not be lower-cased at this point).

        Returns
        -------
        str
            Text with abbreviations replaced.

        Notes
        -----
        - Iterate over CLINICAL_ABBREVIATIONS items and apply re.sub with
          re.IGNORECASE for each pattern → replacement pair.
        - Log a debug message with the number of substitutions made per note
          when cfg.debug is True.
        """
        expanded = text
        n_subs = 0

        for pattern, replacement in CLINICAL_ABBREVIATIONS.items():
            expanded, new_subs = re.subn(pattern, replacement, expanded, flags=re.IGNORECASE)
            n_subs += new_subs

        if self.cfg.debug:
            self.log.debug(f"{n_subs} substitutions made in note.")

        return expanded

    def segment_sections(self, text: str) -> Dict[str, str]:
        """
        Attempt to split a clinical note into labelled sections.

        Parameters
        ----------
        text : str
            Cleaned note text.

        Returns
        -------
        dict of {str: str}
            Keys are section labels (e.g. "HPI", "MEDICATIONS", "ASSESSMENT",
            "PLAN", "PMH", "ALLERGIES", "REVIEW_OF_SYSTEMS").
            Values are the corresponding section text.
            The special key "FULL_TEXT" always holds the entire cleaned text.

        Notes
        -----
        - Use a list of common section header patterns (regex) to identify
          section boundaries.
        - If a section is not found, its key is absent from the dict.
        - This is an optional enrichment step — downstream rules can operate
          on section-specific text to reduce false positives (e.g. looking
          for "penicillin" only in the MEDICATIONS section rather than in
          the ALLERGIES section).
        """
        # TODO: implement a simple regex-based section segmentation method.
        return {"FULL_TEXT": text}

    # ------------------------------------------------------------------
    # Note-level processing
    # ------------------------------------------------------------------

    def process_note_text(self, text: str) -> str:
        """
        Apply the full text-cleaning sequence to a single note string.

        Order of operations (controlled by cfg flags):
        1. clean_whitespace()            — always applied
        2. lowercase conversion          — if cfg.lowercase
        3. expand_abbreviations()        — if cfg.expand_abbreviations

        Parameters
        ----------
        text : str
            Raw note text (may be None / NaN).

        Returns
        -------
        str
            Cleaned text, or an empty string if input is None/NaN.
        """
        if text is None or pd.isna(text):
            return ""
        
        cleaned = self.clean_whitespace(text)

        if self.cfg.lowercase:
            cleaned = cleaned.lower()

        if self.cfg.expand_abbreviations:
            cleaned = self.expand_abbreviations(cleaned)
        
        return cleaned

    def filter_notes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove notes that are too short, too long, or have null text.

        Parameters
        ----------
        df : pd.DataFrame
            Notes DataFrame with a NOTE_TEXT column.

        Returns
        -------
        pd.DataFrame
            Filtered DataFrame.

        Notes
        -----
        - Drop rows where NOTE_TEXT is null or empty.
        - Drop rows where len(NOTE_TEXT) < cfg.min_note_length.
        - Truncate NOTE_TEXT to cfg.max_note_length characters.
        - Log the number of notes dropped at each stage.
        """
        min_note_length = self.cfg.min_note_length
        max_note_length = self.cfg.max_note_length

        dropped_null = 0
        dropped_empty = 0
        dropped_short = 0
        truncated = 0

        df_filtered = df.copy()
        note_text = df_filtered["NOTE_TEXT"]
        non_null_mask = note_text.notna()
        stripped_text = note_text.fillna("").astype(str).str.strip()
        non_empty_mask = stripped_text.ne("")
        length_mask = stripped_text.str.len().ge(min_note_length)

        dropped_null = int((~non_null_mask).sum())
        dropped_empty = int((non_null_mask & ~non_empty_mask).sum())
        dropped_short = int((non_null_mask & non_empty_mask & ~length_mask).sum())

        keep_mask = non_null_mask & non_empty_mask & length_mask
        df_filtered = df_filtered.loc[keep_mask].copy()

        if not df_filtered.empty:
            over_max_mask = df_filtered["NOTE_TEXT"].astype(str).str.len() > max_note_length
            truncated = int(over_max_mask.sum())
            if truncated:
                df_filtered.loc[over_max_mask, "NOTE_TEXT"] = df_filtered.loc[over_max_mask, "NOTE_TEXT"].astype(str).str.slice(0, max_note_length)

        self.log.info(f"Filtering notes: dropped {dropped_null} null, {dropped_empty} empty, {dropped_short} short; truncated {truncated}.")

        return df_filtered

    def deduplicate_notes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove exact duplicate notes (same PERSON_ID + NOTE_TEXT).

        Parameters
        ----------
        df : pd.DataFrame
            Filtered notes DataFrame.

        Returns
        -------
        pd.DataFrame
            Deduplicated DataFrame; first occurrence is kept.

        Notes
        -----
        - Log how many duplicate notes were removed.
        """
        before_dedup = len(df)
        text_column = "NOTE_TEXT_CLEAN" if "NOTE_TEXT_CLEAN" in df.columns else "NOTE_TEXT"

        if text_column not in df.columns:
            raise KeyError("Cannot deduplicate notes: missing NOTE_TEXT or NOTE_TEXT_CLEAN column.")

        df_dedup = df.drop_duplicates(subset=["PERSON_ID", text_column])
        after_dedup = len(df_dedup)
        n_dropped = before_dedup - after_dedup

        self.log.info(f"Deduplicating notes: dropped {n_dropped} duplicates.")

        return df_dedup

    def process_chunk(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply the full preprocessing pipeline to a single chunk DataFrame.

        Steps
        -----
        1. filter_notes(df)
        2. Apply process_note_text() to each row's NOTE_TEXT
           (store result in NOTE_TEXT_CLEAN).
        3. Optionally add a NOTE_SECTIONS column (dict) if cfg.segment_sections.
        4. Optionally drop NOTE_TEXT column if not cfg.keep_original_text.
        5. deduplicate_notes()

        Parameters
        ----------
        df : pd.DataFrame
            Raw notes chunk.

        Returns
        -------
        pd.DataFrame
            Pre-processed notes chunk with NOTE_TEXT_CLEAN column.
        """
        filtered_notes = self.filter_notes(df)
        filtered_notes["NOTE_TEXT_CLEAN"] = filtered_notes["NOTE_TEXT"].apply(self.process_note_text)

        if self.cfg.segment_sections:
            filtered_notes["NOTE_SECTIONS"] = filtered_notes["NOTE_TEXT_CLEAN"].apply(self.segment_sections)

        dedup_notes = self.deduplicate_notes(filtered_notes)

        if not self.cfg.keep_original_text and "NOTE_TEXT" in dedup_notes.columns:
            dedup_notes = dedup_notes.drop(columns=["NOTE_TEXT"])

        return dedup_notes

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Execute preprocessing on all raw note chunks.

        For each raw chunk file:
        1. Check whether the corresponding preprocessed chunk already exists
           in cfg.out_dir — if so, skip (resume-safe).
        2. load_chunk()
        3. process_chunk()
        4. Write result to cfg.out_dir/chunk_NNNN.parquet.
        5. Log per-chunk stats: notes in, notes out, notes dropped.

        After all chunks: log total notes preprocessed.

        Raises
        ------
        FileNotFoundError
            If list_chunk_files() finds no input chunks. Prompts user to
            run the cohort builder first.

        Notes
        -----
        - In debug mode, process only cfg.debug_n_notes rows total across
          all chunks (stop early once this limit is reached).
        - Use tqdm for a progress bar.
        """
        out_dir = self.cfg.out_dir
        ensure_dir(out_dir)

        try:
            chunk_files = self.list_chunk_files()
        except FileNotFoundError as exc:
            self.log.error(str(exc))
            raise

        total_in = 0            # cumulative count of notes read from raw chunks
        total_out = 0           # cumulative count of notes written to preprocessed chunks
        processed_chunks = 0    # count of chunks successfully processed (for logging)

        debug_limit = self.cfg.debug_n_notes if self.cfg.debug else None

        with logging_redirect_tqdm():
            for chunk_file in tqdm(chunk_files, desc="Processing chunks"):
                if debug_limit is not None and total_in >= debug_limit:
                    self.log.info(f"Debug limit reached ({debug_limit} notes); stopping early.")
                    break

                out_file = out_dir / chunk_file.name
                if out_file.exists():
                    self.log.info(f"Preprocessed chunk already exists, skipping: {out_file}")
                    continue

                try:
                    df_raw = self.load_chunk(chunk_file)
                except Exception:
                    self.log.exception(f"Failed to load chunk {chunk_file}; skipping.")
                    continue

                if debug_limit is not None:
                    remaining = debug_limit - total_in
                    if remaining <= 0:
                        self.log.info(f"Debug limit reached ({debug_limit} notes); stopping early.")
                        break
                    if len(df_raw) > remaining:
                        df_raw = df_raw.iloc[:remaining].copy()

                total_in += len(df_raw)

                try:
                    df_processed = self.process_chunk(df_raw)
                except Exception:
                    self.log.exception(f"Failed to process chunk {chunk_file}; skipping.")
                    continue

                try:
                    write_parquet(df_processed, out_file)
                except Exception:
                    self.log.exception(f"Failed to write processed chunk to {out_file}; skipping.")
                    continue

                total_out += len(df_processed)
                processed_chunks += 1
                self.log.info(f"Processed {chunk_file.name}.")

            self.log.info(f"Preprocessing complete. Chunks processed: {processed_chunks}. Notes in: {total_in}. Notes out: {total_out}.")
