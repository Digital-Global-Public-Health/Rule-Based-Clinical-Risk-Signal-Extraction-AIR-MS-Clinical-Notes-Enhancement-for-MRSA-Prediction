# src/extraction/rule_extractor.py
"""
Rule-based clinical risk-signal extraction pipeline.

This module compiles regex patterns from the Lexicon, runs them against
pre-processed clinical notes, applies NegEx negation filtering, and produces
a per-note extraction result DataFrame ready for feature engineering.

Input  : data/interim/airms/notes_preprocessed/chunk_*.parquet
Output : data/interim/airms/extractions/chunk_*.parquet
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.utils_io import ensure_dir, read_parquet, write_parquet

LOG = logging.getLogger("mrsa_nlp.rule.extractor")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ExtractorConfig:
    """
    Tunable parameters for the rule-based extractor.

    Attributes
    ----------
    preprocessed_notes_dir : Path
        Directory containing pre-processed note chunk files.
    out_dir : Path
        Directory where extraction result chunks are written.
    use_word_boundary : bool
        Wrap each pattern in ``\\b`` anchors for whole-word matching.
    case_insensitive : bool
        Compile patterns with re.IGNORECASE.
    apply_negation : bool
        Run the NegationHandler on each match before recording it.
    produce_counts : bool
        Record match counts per risk factor in addition to binary flags.
    debug : bool
        When True, process only ``debug_n_notes`` rows.
    debug_n_notes : int
        Number of rows processed in debug mode.
    save_matched_spans : bool
        If True, store the matched text span in the output for QA review.
    """

    preprocessed_notes_dir: Path = Path("data/interim/airms/notes_preprocessed")
    out_dir: Path = Path("data/interim/airms/extractions")
    use_word_boundary: bool = True
    case_insensitive: bool = True
    apply_negation: bool = True
    produce_counts: bool = True
    debug: bool = False
    debug_n_notes: int = 200
    save_matched_spans: bool = False


# ---------------------------------------------------------------------------
# Compiled pattern container
# ---------------------------------------------------------------------------

@dataclass
class CompiledPattern:
    """
    One compiled regex pattern associated with a risk factor.

    Attributes
    ----------
    risk_factor : str
        The risk factor this pattern belongs to.
    raw_pattern : str
        The original string pattern before compilation.
    regex : re.Pattern
        The compiled regex object.
    """

    risk_factor: str
    raw_pattern: str
    regex: re.Pattern


# ---------------------------------------------------------------------------
# Extractor class
# ---------------------------------------------------------------------------

class RuleExtractor:
    """
    Applies compiled regex rules to pre-processed clinical notes.

    Parameters
    ----------
    config : ExtractorConfig
        Configuration for this extraction run.
    lexicon : Lexicon
        Loaded lexicon object (see src.extraction.lexicon).
    negation_handler : NegationHandler
        Negation detection handler.
    logger : logging.Logger, optional
        Logger; defaults to module-level LOG.

    Example
    -------
    >>> from src.extraction.rule_extractor import ExtractorConfig, RuleExtractor
    >>> from src.extraction.lexicon import LexiconConfig, Lexicon
    >>> from src.extraction.negation_handler import NegationConfig, NegationHandler
    >>> lex = Lexicon(LexiconConfig()); lex.load()
    >>> neg = NegationHandler(NegationConfig())
    >>> extractor = RuleExtractor(ExtractorConfig(), lex, neg)
    >>> extractor.run()
    """

    def __init__(
        self,
        config: ExtractorConfig,
        lexicon,
        negation_handler,
        logger: logging.Logger = LOG,
    ) -> None:
        self.cfg = config
        self.lexicon = lexicon
        self.negation_handler = negation_handler
        self.log = logger
        self._patterns: List[CompiledPattern] = []
        self._compile_patterns()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _compile_patterns(self) -> None:
        """
        Compile all lexicon patterns into regex objects and store in
        ``self._patterns``.

        Steps
        -----
        1. Call ``self.lexicon.get_all_patterns()`` → dict {risk_factor: [str]}.
        2. For each risk factor and each pattern string:
            a. Optionally wrap in ``\\b`` (if cfg.use_word_boundary).
            b. Compile with re.IGNORECASE if cfg.case_insensitive.
            c. Append a CompiledPattern to self._patterns.
        3. Log total pattern count and per-risk-factor breakdown.

        Notes
        -----
        - Skip empty pattern strings.
        - Log a warning for any pattern that fails re.compile().
        """
        patterns_dict = self.lexicon.get_all_patterns()
        for risk_factor, pattern_list in patterns_dict.items():
            compiled_count = 0
            for pattern_str in pattern_list:
                if not pattern_str.strip():
                    continue
                if self.cfg.use_word_boundary:
                    pattern_str = r"\b" + pattern_str + r"\b"
                try:
                    regex_flags = re.IGNORECASE if self.cfg.case_insensitive else 0
                    compiled_regex = re.compile(pattern_str, regex_flags)
                    self._patterns.append(CompiledPattern(risk_factor, pattern_str, compiled_regex))
                    compiled_count += 1
                except re.error as e:
                    self.log.warning("Failed to compile pattern '%s' for risk factor '%s': %s", pattern_str, risk_factor, e)
            self.log.info("Compiled %d patterns for risk factor '%s'", compiled_count, risk_factor)

    # ------------------------------------------------------------------
    # Single-note extraction
    # ------------------------------------------------------------------

    def _run_patterns_on_text(
        self,
        text: str,
    ) -> List[Tuple[int, int, str]]:
        """
        Run all compiled patterns against ``text`` and return raw matches.

        Parameters
        ----------
        text : str
            Pre-processed note text.

        Returns
        -------
        list of (start, end, risk_factor)
            Character spans of each match and the associated risk factor label.
            A single text may contain multiple matches for the same factor.
        """
        matches: List[Tuple[int, int, str]] = []
        for cp in self._patterns:
            for match in cp.regex.finditer(text):
                matches.append((match.start(), match.end(), cp.risk_factor))
        return matches

    def extract_from_text(
        self,
        text: str,
        note_id: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Extract risk factor signals from a single note text.

        Steps
        -----
        1. _run_patterns_on_text(text) → raw matches.
        2. If cfg.apply_negation: negation_handler.filter_negated(text, matches).
        3. Aggregate per risk-factor:
            - binary flag: 1 if any match remains, else 0.
            - count: number of remaining matches (if cfg.produce_counts).

        Parameters
        ----------
        text : str
            Pre-processed note text (should already be lower-cased).
        note_id : str, optional
            NOTE_ID for debug logging.

        Returns
        -------
        dict of {str: int}
            Keys follow the pattern ``has_{risk_factor}`` (binary) and
            optionally ``count_{risk_factor}`` (count).

        Notes
        -----
        - Returns a dict of zeros for all risk factors if text is empty.
        - In debug mode, log a row-level summary when any match is found.
        """
        matches = self._run_patterns_on_text(text)

        if self.cfg.apply_negation:
            matches = self.negation_handler.filter_negated(text, matches)

        match_counts = Counter(m[2] for m in matches)

        rf_signals: Dict[str, int] = {}
        for entry in self.lexicon.get_all_entries():
            rf = entry.risk_factor
            col_has = f"has_{rf}"
            col_count = f"count_{rf}"
            count_match = match_counts.get(rf, 0)
            rf_signals[col_has] = int(count_match > 0)
            if self.cfg.produce_counts:
                rf_signals[col_count] = count_match

            if self.cfg.debug and count_match > 0:
                self.log.debug(
                    "Note ID %s: risk factor '%s' → has=%d, count=%d",
                    note_id,
                    rf,
                    rf_signals[col_has],
                    rf_signals.get(col_count, 0),
                )

        return rf_signals

    def extract_from_note_row(self, row: pd.Series) -> Dict[str, int]:
        """
        Convenience wrapper to extract features from a single DataFrame row.

        Parameters
        ----------
        row : pd.Series
            A row from a notes DataFrame; must contain NOTE_TEXT_CLEAN
            (or NOTE_TEXT as fallback) and NOTE_ID.

        Returns
        -------
        dict of {str: int}
            Feature dict suitable for building a DataFrame column.
        """
        raw = row.get("NOTE_TEXT_CLEAN")
        text = str(raw) if not pd.isnull(raw) else str(row.get("NOTE_TEXT") or "")
        note_id = row.get("NOTE_ID")

        if self.cfg.debug:
            self.log.debug("Extracting from note ID %s: text length=%d", note_id, len(text))
        return self.extract_from_text(text, note_id=note_id)

    def extract_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply extraction to every row in a notes DataFrame.

        Parameters
        ----------
        df : pd.DataFrame
            Pre-processed notes chunk with NOTE_TEXT_CLEAN column.

        Returns
        -------
        pd.DataFrame
            Original DataFrame with risk-factor feature columns appended.
            Includes NOTE_ID, PERSON_ID, VISIT_OCCURRENCE_ID, NOTE_DATE,
            NOTE_TYPE_CONCEPT_ID, and all ``has_*`` / ``count_*`` columns.

        Notes
        -----
        - Use df.apply(self.extract_from_note_row, axis=1) or a row-level
          loop; for large DataFrames a loop with tqdm is more debuggable.
        - Optionally store matched spans in a separate ``_spans`` column
          if cfg.save_matched_spans is True (JSON list of spans).
        """
        feat_rows: List[Dict[str, int]] = []
        spans_rows: List[str] = []

        for _, row in df.iterrows():
            feat_rows.append(self.extract_from_note_row(row))

            if self.cfg.save_matched_spans:
                raw = row.get("NOTE_TEXT_CLEAN")
                text = str(raw) if not pd.isnull(raw) else str(row.get("NOTE_TEXT") or "")
                span_matches = self._run_patterns_on_text(text)
                if self.cfg.apply_negation:
                    span_matches = self.negation_handler.filter_negated(text, span_matches)
                spans_rows.append(json.dumps(
                    [{"start": s, "end": e, "risk_factor": rf} for s, e, rf in span_matches]
                ))

        feat_df = pd.DataFrame(feat_rows)
        combined_df = pd.concat([df.reset_index(drop=True), feat_df], axis=1)

        if self.cfg.save_matched_spans:
            combined_df["_spans"] = spans_rows

        return combined_df

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def list_preprocessed_chunks(self) -> List[Path]:
        """
        Return sorted list of pre-processed note chunk files.

        Returns
        -------
        list of Path

        Raises
        ------
        FileNotFoundError
            If cfg.preprocessed_notes_dir does not exist or is empty.
            Prompt user to run the preprocessing pipeline first.
        """
        notes_dir = self.cfg.preprocessed_notes_dir
        if not notes_dir.exists() or not notes_dir.is_dir():
            raise FileNotFoundError(
                f"Pre-processed notes directory not found: {notes_dir}. "
                "Run the preprocessing pipeline first."
            )
        
        chunk_files = sorted(
            notes_dir.glob("chunk_*.parquet"),
            key=lambda p: int(p.stem.split("_")[-1]) if p.stem.split("_")[-1].isdigit() else 0,
        )
        if not chunk_files:
            raise FileNotFoundError(
                f"No pre-processed note chunks found in {notes_dir}. "
                "Run the preprocessing pipeline first."
            )
        
        return chunk_files

    def run(self) -> None:
        """
        Run extraction on all pre-processed note chunks.

        For each chunk file:
        1. Check whether the corresponding extraction chunk exists in
           cfg.out_dir — if so, skip (resume-safe).
        2. Load the chunk.
        3. extract_batch().
        4. Write result to cfg.out_dir/chunk_NNNN.parquet.
        5. Log per-chunk statistics (notes processed, total matches per factor).

        Raises
        ------
        FileNotFoundError
            If no pre-processed chunks are found.

        Notes
        -----
        - In debug mode, stop after processing cfg.debug_n_notes rows total.
        - Log a summary table of total positive mentions per risk factor
          at the end of all chunks.
        """
        debug_limit = self.cfg.debug_n_notes if self.cfg.debug else None
        total_in = 0
        total_matches: Dict[str, int] = {e.risk_factor: 0 for e in self.lexicon.get_all_entries()}

        out_dir = self.cfg.out_dir
        ensure_dir(out_dir)

        preprocessed_chunks = self.list_preprocessed_chunks()

        self.log.info("Starting extraction on %d pre-processed chunks.", len(preprocessed_chunks))
        for chunk_path in preprocessed_chunks:
            chunk_name = chunk_path.name
            out_path = out_dir / chunk_name
            if out_path.exists():
                self.log.info("Skipping existing extraction chunk: %s", out_path)
                continue

            try:
                df_chunk = read_parquet(chunk_path)
            except Exception as e:
                self.log.error("Failed to read chunk %s: %s", chunk_path, e)
                continue

            if debug_limit is not None:
                remaining = debug_limit - total_in
                if remaining <= 0:
                    self.log.info("Debug limit reached (%d rows); stopping early.", debug_limit)
                    break
                if len(df_chunk) > remaining:
                    df_chunk = df_chunk.iloc[:remaining].copy()

            total_in += len(df_chunk)
            
            try:
                df_result = self.extract_batch(df_chunk)
            except Exception as e:
                self.log.error("Extraction failed for chunk %s: %s", chunk_path, e)
                continue

            for rf in total_matches:
                col = f"has_{rf}"
                if col in df_result.columns:
                    total_matches[rf] += int(df_result[col].sum())

            try:
                write_parquet(df_result, out_path)
            except Exception as e:
                self.log.error("Failed to save results for chunk %s: %s", chunk_path, e)
                continue
            
            self.log.info("Saved extraction of %d row(s) to: %s", len(df_result), out_path)
        
        self.log.info("Extraction complete. Total notes processed: %d", total_in)
        self.log.info("%-40s %8s", "Risk Factor", "Positives")
        self.log.info("-" * 50)
        for rf, count in sorted(total_matches.items(), key=lambda x: -x[1]):
            self.log.info("  %-38s %8d", rf, count)
