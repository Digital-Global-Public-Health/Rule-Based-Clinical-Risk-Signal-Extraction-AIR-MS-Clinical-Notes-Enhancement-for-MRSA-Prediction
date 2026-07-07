# src/extraction/negation_handler.py
"""
Window-based and NegEx-inspired negation detection.

When a rule matches a keyword in a clinical note, this module checks whether
the match is preceded by negation cues (e.g. "no", "denies", "without") within
a configurable token window.  A negated match is suppressed (not counted as a
positive mention of the risk factor).

Reference
---------
Chapman et al. (2001) A simple algorithm for identifying negated findings and
diseases in discharge summaries. Journal of Biomedical Informatics.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List, Tuple

LOG = logging.getLogger("mrsa_nlp.rule.negation")


# ---------------------------------------------------------------------------
# Default negation cue list  (extend as needed)
# ---------------------------------------------------------------------------

DEFAULT_NEGATION_CUES: List[str] = [
    "no",
    "not",
    "without",
    "denies",
    "denied",
    "deny",
    "negative for",
    "negative",
    "absence of",
    "absent",
    "never",
    "ruled out",
    "rules out",
    "rule out",
    "no evidence of",
    "no history of",
    "no prior",
    "no known",
    "free of",
    "none",
    "neither",
    "nor",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class NegationConfig:
    """
    Parameters for the negation handler.

    Attributes
    ----------
    window_tokens : int
        Number of tokens to look back before a match for negation cues.
        Default of 5 follows the NegEx heuristic.
    negation_cues : list of str, optional
        Custom list of negation cues.  None uses DEFAULT_NEGATION_CUES.
    use_sentence_boundary : bool
        If True, the search window does not cross sentence boundaries
        (detected by "." or newlines).
    debug : bool
        Log extra detail when a negation is detected.
    """

    window_tokens: int = 5
    negation_cues: List[str] = field(default_factory=lambda: list(DEFAULT_NEGATION_CUES))
    use_sentence_boundary: bool = True
    debug: bool = False


# ---------------------------------------------------------------------------
# NegationHandler class
# ---------------------------------------------------------------------------

class NegationHandler:
    """
    Detects whether a keyword match in a note text is negated.

    Parameters
    ----------
    config : NegationConfig
        Configuration for this handler.
    logger : logging.Logger, optional
        Logger; defaults to module-level LOG.

    Example
    -------
    >>> from src.extraction.negation_handler import NegationConfig, NegationHandler
    >>> handler = NegationHandler(NegationConfig())
    >>> text = "The patient has no prior MRSA colonization."
    >>> is_neg = handler.is_negated(text, match_start=25, match_end=42)
    >>> assert is_neg  # should be True
    """

    def __init__(
        self,
        config: NegationConfig,
        logger: logging.Logger = LOG,
    ) -> None:
        self.cfg = config
        self.log = logger
        self._compiled_cues: List[re.Pattern] = []
        self._compile_cues()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _compile_cues(self) -> None:
        """
        Pre-compile negation cue strings into regex patterns.

        Each cue is wrapped in ``\\b`` word-boundaries and compiled with
        re.IGNORECASE so matching is case-insensitive at call time.

        Notes
        -----
        - Multi-word cues (e.g. "no history of") are compiled as-is (they
          already span multiple tokens).
        - Results stored in self._compiled_cues.
        """
        for cue in self.cfg.negation_cues:
            pattern_str = r"\b" + re.escape(cue) + r"\b"
            try:
                compiled = re.compile(pattern_str, re.IGNORECASE)
                self._compiled_cues.append(compiled)
            except re.error as e:
                self.log.warning("Failed to compile negation cue '%s': %s", cue, e)

    # ------------------------------------------------------------------
    # Core detection
    # ------------------------------------------------------------------

    def _get_pre_window_text(
        self,
        text: str,
        match_start: int,
    ) -> str:
        """
        Extract the window of text immediately before a keyword match.

        Parameters
        ----------
        text : str
            Full note text (should already be lowercased).
        match_start : int
            Character offset of the start of the keyword match.

        Returns
        -------
        str
            The pre-window text slice.

        Notes
        -----
        Algorithm
        ~~~~~~~~~
        1. Take the substring ``text[:match_start]``.
        2. If cfg.use_sentence_boundary is True, find the last sentence
           boundary (``[.!?\\n]``) before match_start and trim the window
           to start there.
        3. Tokenise the remaining text by whitespace.
        4. Take the last ``cfg.window_tokens`` tokens.
        5. Rejoin with spaces and return.
        """
        substring = text[:match_start]
        if self.cfg.use_sentence_boundary:
            last_boundary = max(substring.rfind("."), substring.rfind("!"), substring.rfind("?"), substring.rfind("\n"))
            if last_boundary != -1:
                substring = substring[last_boundary + 1 :]
        
        tokens = substring.split()
        return " ".join(tokens[-self.cfg.window_tokens:])

    def is_negated(
        self,
        text: str,
        match_start: int,
        match_end: int,
    ) -> bool:
        """
        Return True if the keyword match at [match_start, match_end) is
        preceded by a negation cue within the token window.

        Parameters
        ----------
        text : str
            Full note text (lower-cased recommended).
        match_start : int
            Character start offset of the matched keyword.
        match_end : int
            Character end offset of the matched keyword (not used in the
            look-back logic, kept for API consistency).

        Returns
        -------
        bool
            True  → the match is negated (suppress it).
            False → the match is affirmative (keep it).

        Notes
        -----
        - Calls _get_pre_window_text() to obtain the search region.
        - Checks each compiled cue pattern against the window text.
        - If cfg.debug is True, log the window and which cue triggered.
        """
        pre_window = self._get_pre_window_text(text, match_start)
        for cue_pattern in self._compiled_cues:
            if cue_pattern.search(pre_window):
                if self.cfg.debug:
                    self.log.debug(
                        "Negation detected: cue '%s' found in window '%s'",
                        cue_pattern.pattern,
                        pre_window,
                    )
                return True
        return False

    def filter_negated(
        self,
        text: str,
        matches: List[Tuple[int, int, str]],
    ) -> List[Tuple[int, int, str]]:
        """
        Filter a list of regex matches, removing those that are negated.

        Parameters
        ----------
        text : str
            Full note text used to check negation context.
        matches : list of (start, end, pattern_label)
            Each tuple is a keyword match with its character span and the
            risk-factor label it belongs to.

        Returns
        -------
        list of (start, end, pattern_label)
            Only the non-negated matches.

        Notes
        -----
        - Calls is_negated() for each match.
        - Logs how many matches were suppressed when cfg.debug is True.
        """
        filtered_matches = [m for m in matches if not self.is_negated(text, m[0], m[1])]
        if self.cfg.debug:
            num_removed = len(matches) - len(filtered_matches)
            self.log.debug("Negation filtering: %d of %d matches removed.", num_removed, len(matches))
        return filtered_matches
