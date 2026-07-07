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
from typing import Dict, List

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

    def normalize(self, text: str) -> str:
        """Normalize to lower_snake_case — for risk_factor keys and column names only."""
        return text.strip().lower().replace(" ", "_")

    def _split_cell(self, value, *, lowercase: bool = True) -> List[str]:
        """Split a pipe-separated cell value into a stripped list; NaN-safe.

        ICD-10 codes must be passed with ``lowercase=False`` to preserve their
        canonical uppercase format (e.g. ``A49.01``).
        """
        if pd.isnull(value):
            return []
        tokens = [
            stripped for x in str(value).split(self.cfg.separator)
            if (stripped := x.strip().strip("\"'").strip())
        ]
        return [t.lower() for t in tokens] if lowercase else tokens

    def _str_cell(self, value) -> str:
        """Return a stripped string from a scalar cell value; NaN-safe."""
        return "" if pd.isnull(value) else str(value).strip()

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
        lexicon_path = self.cfg.lexicon_path
        if not lexicon_path.exists():
            raise FileNotFoundError(f"Lexicon CSV not found: {lexicon_path}")
        
        self.log.info("Loading lexicon from %s", lexicon_path)
        df = pd.read_csv(lexicon_path)
        df.columns = [self.normalize(col) for col in df.columns]

        required_cols = {"risk_factor", "medical_context", "icd_codes", "drug_names", "keywords", "abbreviations"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Lexicon CSV is missing required columns: {missing}")

        self._entries = {}
        for _, row in df.iterrows():
            if pd.isnull(row["risk_factor"]) or row["risk_factor"] == "":
                continue
            risk_factor = self.normalize(row["risk_factor"])
            if risk_factor in self._entries:
                self.log.warning("Duplicate risk factor '%s' in CSV — later row overwrites earlier.", risk_factor)
            entry = LexiconEntry(
                risk_factor=risk_factor,
                medical_context=self._str_cell(row["medical_context"]),
                icd_codes=self._split_cell(row["icd_codes"], lowercase=False),
                drug_names=self._split_cell(row["drug_names"]),
                keywords=self._split_cell(row["keywords"]),
                abbreviations=self._split_cell(row["abbreviations"]),
                negation_caveats=self._str_cell(row.get("negation_caveats")),
            )
            if self.cfg.debug:
                self.log.debug(
                    "Loaded entry '%s': %d keywords, %d drug names, %d ICD codes",
                    risk_factor, len(entry.keywords), len(entry.drug_names), len(entry.icd_codes),
                )
            self._entries[risk_factor] = entry

        self.log.info("Loaded %d lexicon entries: %s", len(self._entries), list(self._entries.keys()))
        
        if self.cfg.validate_on_load:
            self.validate()

    def get_all_entries(self) -> List[LexiconEntry]:
        """
        Return all loaded LexiconEntry objects as a list.

        Returns
        -------
        list of LexiconEntry
        """
        return list(self._entries.values())

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
        entry = self._entries.get(risk_factor)
        if entry is None:
            raise KeyError(f"Risk factor '{risk_factor}' not found in lexicon.")

        return entry

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
        entry = self.get_entry(risk_factor)
        return [p for p in entry.drug_names + entry.keywords + entry.abbreviations if p]

    def get_all_patterns(self) -> Dict[str, List[str]]:
        """
        Return a mapping of risk_factor → list of searchable patterns for
        all loaded entries.

        Returns
        -------
        dict of {str: list of str}
            Keys are risk factor names; values are pattern lists.
        """
        return {risk_factor: self.get_patterns_for_factor(risk_factor) for risk_factor in self._entries}

    def validate(self) -> bool:
        """
        Run basic sanity checks on the loaded lexicon.

        Checks
        ------
        - Each entry has at least one keyword or drug_name.

        Notes
        -----
        - Duplicate keys are detected in ``load()`` before the dict is built.
        - The lower_snake_case check would always pass here because
          ``normalize()`` is applied to every key on load.
        - Log a WARNING for each problematic entry but do not raise.

        Returns
        -------
        bool
            True if all checks pass; False if any warnings were issued.
        """
        warnings_issued = False
        for risk_factor, entry in self._entries.items():
            if not entry.keywords and not entry.drug_names:
                self.log.warning(
                    "Lexicon entry '%s' has no keywords or drug names.", risk_factor
                )
                warnings_issued = True
        return not warnings_issued

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
        data = []
        for entry in self._entries.values():
            data.append({
                "risk_factor": entry.risk_factor,
                "medical_context": entry.medical_context,
                "icd_codes": self.cfg.separator.join(entry.icd_codes),
                "drug_names": self.cfg.separator.join(entry.drug_names),
                "keywords": self.cfg.separator.join(entry.keywords),
                "abbreviations": self.cfg.separator.join(entry.abbreviations),
                "negation_caveats": entry.negation_caveats
            })
        return pd.DataFrame(data)
