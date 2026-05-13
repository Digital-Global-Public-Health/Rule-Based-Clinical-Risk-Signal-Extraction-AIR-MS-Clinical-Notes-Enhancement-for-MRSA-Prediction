# src/extraction/lexicon.py
"""
Clinical risk-signal lexicon loader for MRSA rule-based extraction.

The lexicon is a structured CSV/YAML that maps MRSA risk factors to their
clinical context, ICD codes, drug names, free-text keywords, and abbreviations.
This module loads, validates, and exposes the lexicon to the RuleExtractor.

Lexicon CSV columns (see lexicons/mrsa_risk_factors_v1.csv):
    risk_factor         — short machine-readable name
    medical_context     — plain-language explanation
    icd_codes           — pipe-separated ICD-10 codes (optional)
    drug_names          — pipe-separated drug names / synonyms
    keywords            — pipe-separated free-text keywords
    abbreviations       — pipe-separated abbreviations
    negation_caveats    — free text describing known false-positive patterns
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

LOG = logging.getLogger("mrsa_nlp.rule.lexicon")


# ---------------------------------------------------------------------------
# Data class for a single lexicon entry
# ---------------------------------------------------------------------------

@dataclass
class LexiconEntry:
    """
    Represents one MRSA risk factor row from the lexicon CSV.

    Attributes
    ----------
    risk_factor : str
        Machine-readable name (e.g. "corticosteroid_use").
    medical_context : str
        Plain-language clinical rationale.
    icd_codes : list of str
        ICD-10 codes associated with this risk factor.
    drug_names : list of str
        Drug names and synonyms that indicate this risk factor.
    keywords : list of str
        Free-text phrases to search for.
    abbreviations : list of str
        Clinical abbreviations (matched with word boundaries).
    negation_caveats : str
        Describes known false-positive patterns (for documentation /
        downstream NegEx rules).
    """

    risk_factor: str
    medical_context: str
    icd_codes: List[str] = field(default_factory=list)
    drug_names: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    abbreviations: List[str] = field(default_factory=list)
    negation_caveats: str = ""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class LexiconConfig:
    """
    Parameters for the Lexicon loader.

    Attributes
    ----------
    lexicon_path : Path
        Path to the lexicon CSV file.
    separator : str
        Delimiter used inside multi-value cells (default "|").
    validate_on_load : bool
        Run basic validation checks after loading.
    debug : bool
        Log extra detail about each loaded entry.
    """

    lexicon_path: Path = Path("lexicons/mrsa_risk_factors_v1.csv")
    separator: str = "|"
    validate_on_load: bool = True
    debug: bool = False


# ---------------------------------------------------------------------------
# Lexicon class
# ---------------------------------------------------------------------------

class Lexicon:
    """
    Loads and exposes the MRSA risk factor lexicon.

    Parameters
    ----------
    config : LexiconConfig
        Configuration for this loader.
    logger : logging.Logger, optional
        Logger; defaults to module-level LOG.

    Example
    -------
    >>> from src.extraction.lexicon import LexiconConfig, Lexicon
    >>> lex = Lexicon(LexiconConfig())
    >>> lex.load()
    >>> patterns = lex.get_all_patterns()
    """

    def __init__(
        self,
        config: LexiconConfig,
        logger: logging.Logger = LOG,
    ) -> None:
        self.cfg = config
        self.log = logger
        self._entries: Dict[str, LexiconEntry] = {}

    def load(self) -> None:
        """
        Read the lexicon CSV and populate internal ``_entries`` dict.

        Steps
        -----
        1. Read CSV using pd.read_csv().
        2. For each row, parse pipe-separated lists for icd_codes, drug_names,
           keywords, and abbreviations.
        3. Construct a LexiconEntry and store it keyed by risk_factor.
        4. Optionally call validate() if cfg.validate_on_load is True.

        Raises
        ------
        FileNotFoundError
            If cfg.lexicon_path does not exist.
        ValueError
            If required columns are missing from the CSV.

        Notes
        -----
        - Strip whitespace from all list elements.
        - Skip rows where risk_factor is empty.
        - Log the number of entries loaded and the list of risk factors.
        """
        pass

    def get_all_entries(self) -> List[LexiconEntry]:
        """
        Return all loaded LexiconEntry objects as a list.

        Returns
        -------
        list of LexiconEntry
        """
        pass

    def get_entry(self, risk_factor: str) -> LexiconEntry:
        """
        Retrieve a single LexiconEntry by risk factor name.

        Parameters
        ----------
        risk_factor : str
            Key matching LexiconEntry.risk_factor.

        Returns
        -------
        LexiconEntry

        Raises
        ------
        KeyError
            If risk_factor is not in the loaded entries.
        """
        pass

    def get_patterns_for_factor(self, risk_factor: str) -> List[str]:
        """
        Return the combined list of searchable patterns for one risk factor.

        The returned list merges drug_names, keywords, and abbreviations from
        the entry.  The RuleExtractor will compile these into regex patterns.

        Parameters
        ----------
        risk_factor : str
            Key matching a loaded LexiconEntry.

        Returns
        -------
        list of str
            All non-empty pattern strings for this risk factor.
        """
        pass

    def get_all_patterns(self) -> Dict[str, List[str]]:
        """
        Return a mapping of risk_factor → list of searchable patterns for
        all loaded entries.

        Returns
        -------
        dict of {str: list of str}
            Keys are risk factor names; values are pattern lists.
        """
        pass

    def validate(self) -> bool:
        """
        Run basic sanity checks on the loaded lexicon.

        Checks
        ------
        - Each entry has at least one keyword or drug_name.
        - No duplicate risk_factor keys.
        - All risk_factor names are lower_snake_case (warn if not).

        Returns
        -------
        bool
            True if all checks pass; False if any warnings were issued.

        Notes
        -----
        - Log a WARNING for each problematic entry but do not raise.
        """
        pass

    def to_dataframe(self) -> pd.DataFrame:
        """
        Export all lexicon entries as a DataFrame (one row per entry).

        Returns
        -------
        pd.DataFrame
            Columns: risk_factor, medical_context, icd_codes, drug_names,
            keywords, abbreviations, negation_caveats.
            List columns are stored as pipe-joined strings.
        """
        pass
