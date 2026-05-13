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

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

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
        pass

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
        pass

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
        pass

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
        pass

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
        pass

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
        pass

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
        pass
