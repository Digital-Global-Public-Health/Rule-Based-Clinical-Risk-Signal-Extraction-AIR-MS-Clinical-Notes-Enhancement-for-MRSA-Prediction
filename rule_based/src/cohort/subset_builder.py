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
    Configuration for reproducible subset selection.

    Attributes
    ----------
    n_rows : int
        Number of rows to sample from the filtered dataframe.
    seed : int
        Random seed passed to pandas.DataFrame.sample for reproducibility.
    note_title_column : str
        Name of the column that stores the note type/title.
    selected_note_titles : list[str], optional
        Allowed note titles. If empty, no note-title filter is applied.
    output_path : str | None
        Optional path where the sampled subset is saved as parquet.
    """

    n_rows: int
    seed: int = 42
    note_title_column: str = "NOTE_TITLE"
    selected_note_titles: List[str] = field(default_factory=list)
    output_path: Optional[str] = None


class SubsetBuilder:
    """
    Build a reproducible subset from a pandas DataFrame.

    The builder can optionally filter the input dataframe by note title and
    then sample a fixed number of rows with pandas.DataFrame.sample.
    """

    def __init__(self, config: SubsetConfig, logger: logging.Logger = LOG) -> None:
        self.cfg = config
        self.log = logger

    def select_subset(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Return a reproducible subset of the given dataframe.

        Parameters
        ----------
        df : pandas.DataFrame
            Input dataframe to sample from.

        Returns
        -------
        pandas.DataFrame
            Sampled subset.
        """
        if df is None or df.empty:
            raise ValueError("Input dataframe is empty.")

        working_df = df.copy()

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

        if working_df.empty:
            self.log.warning("No rows left after filtering; returning empty dataframe.")
            return working_df

        sample_size = min(self.cfg.n_rows, len(working_df))
        sampled_df = working_df.sample(
            n=sample_size,
            random_state=self.cfg.seed,
            replace=False,
        ).reset_index(drop=True)

        self.log.info(
            "Sampled %d rows from %d input rows using seed=%d.",
            len(sampled_df),
            len(working_df),
            self.cfg.seed,
        )

        if self.cfg.output_path:
            out_path = Path(self.cfg.output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            sampled_df.to_parquet(out_path, index=False)
            self.log.info("Saved sampled subset to %s", out_path)

        return sampled_df
