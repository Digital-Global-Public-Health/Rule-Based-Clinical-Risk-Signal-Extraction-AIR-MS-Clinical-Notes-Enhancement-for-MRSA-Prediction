# src/annotation/gold_standard_builder.py
"""
Interactive gold-standard builder for the MRSA NLP rule-based pipeline.

For every raw note chunk, prints the note text to stdout and opens a
per-note checklist file (one line per lexicon risk factor) in $EDITOR for
manual annotation. Notes that already have a checklist are skipped on
rerun, so an annotation session can be paused and resumed at any time.
Once annotated, all checklists are merged into a single gold-standard CSV
with one has_{risk_factor} column per lexicon entry — the schema expected
by RuleEvaluator.load_gold_standard().

This step requires human interaction and is therefore not part of the
automated run-rule-pipeline command; run it separately.

Input  : data/interim/airms/notes/chunk_*.parquet
Output : data/annotations/checklists/note_<NOTE_ID>.txt (per-note working files)
         data/annotations/gold_standard.csv             (final merged output)
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from src.extraction.lexicon import Lexicon, LexiconConfig
from src.utils_io import ensure_dir, read_parquet, write_csv

LOG = logging.getLogger("mrsa_nlp.rule.annotation")

_CHECKBOX_RE = re.compile(r"^\[(.?)\]\s*(.+)$")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class GoldStandardConfig:
    """
    Configuration for the interactive gold-standard builder.

    Attributes
    ----------
    input_dir : Path
        Directory containing the raw note chunk_*.parquet files to annotate.
    lexicon_path : Path
        Path to the lexicon CSV; its risk factors become the checklist items.
    checklist_dir : Path
        Directory where one working checklist file per note is written.
    output_file : Path
        Path of the final merged gold-standard CSV.
    editor : str, optional
        Command used to edit each checklist file. Defaults to $EDITOR, then "vi".
    force_reannotate : bool
        If True, recreate and reopen checklists that already exist instead
        of skipping them.
    """

    input_dir: Path = Path("data/interim/airms/notes")
    lexicon_path: Path = Path("lexicons/mrsa_risk_factors_v2.csv")
    checklist_dir: Path = Path("data/annotations/checklists")
    output_file: Path = Path("data/annotations/gold_standard.csv")
    editor: Optional[str] = None
    force_reannotate: bool = False


# ---------------------------------------------------------------------------
# Golden standard builder class
# ---------------------------------------------------------------------------

class GoldStandardBuilder:
    """
    Build a manually annotated gold-standard dataset from clinical notes.

    Parameters
    ----------
    config : GoldStandardConfig
        Configuration for this annotation session.
    logger : logging.Logger, optional
        Logger to use; defaults to module-level LOG.

    Example
    -------
    >>> from src.annotation.gold_standard_builder import GoldStandardConfig, GoldStandardBuilder
    >>> builder = GoldStandardBuilder(GoldStandardConfig())
    >>> builder.run()
    """

    ID_COLUMNS = ["NOTE_ID", "PERSON_ID", "VISIT_OCCURRENCE_ID"]

    def __init__(self, config: GoldStandardConfig, logger: logging.Logger = LOG) -> None:
        self.cfg = config
        self.log = logger

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_notes(self) -> pd.DataFrame:
        """
        Load and concatenate all raw note chunks from cfg.input_dir.

        Returns
        -------
        pd.DataFrame
            One row per note with at least NOTE_ID, PERSON_ID,
            VISIT_OCCURRENCE_ID, and NOTE_TEXT.

        Raises
        ------
        FileNotFoundError
            If input_dir does not exist or contains no chunk files.
        ValueError
            If a chunk file is missing a required column.
        """
        notes_dir = Path(self.cfg.input_dir)
        if not notes_dir.exists() or not notes_dir.is_dir():
            raise FileNotFoundError(f"Input directory does not exist: {notes_dir}")

        chunk_files = sorted(notes_dir.glob("chunk_*.parquet"))
        if not chunk_files:
            raise FileNotFoundError(f"No parquet files found in input directory: {notes_dir}")

        required_cols = {"NOTE_ID", "PERSON_ID", "VISIT_OCCURRENCE_ID", "NOTE_TEXT"}
        frames = []
        for chunk_file in chunk_files:
            df = read_parquet(chunk_file)
            missing = required_cols - set(df.columns)
            if missing:
                raise ValueError(f"Chunk file {chunk_file} is missing required columns: {missing}")
            frames.append(df)

        notes_df = pd.concat(frames, ignore_index=True)
        self.log.info("Loaded %d notes from %d chunk file(s).", len(notes_df), len(chunk_files))
        return notes_df

    def load_risk_factors(self) -> List[str]:
        """
        Load the risk factor names from the shared lexicon loader.

        Reuses src.extraction.lexicon.Lexicon so annotation checklists use
        exactly the same risk_factor names (and normalisation, e.g. ";"
        separator and lower_snake_case) as the rule extractor's own
        has_{risk_factor} feature columns.

        Returns
        -------
        list of str
            Sorted, normalised risk factor names.
        """
        lexicon = Lexicon(LexiconConfig(lexicon_path=Path(self.cfg.lexicon_path)), logger=self.log)
        lexicon.load()
        risk_factors = sorted(entry.risk_factor for entry in lexicon.get_all_entries())
        self.log.info("Loaded %d risk factors from lexicon.", len(risk_factors))
        return risk_factors

    # ------------------------------------------------------------------
    # Per-note checklist templates
    # ------------------------------------------------------------------

    def _checklist_path(self, note_id: object) -> Path:
        return Path(self.cfg.checklist_dir) / f"note_{note_id}.txt"

    def _write_checklist_template(self, note: pd.Series, risk_factors: List[str], path: Path) -> None:
        """Write a blank, manually editable checklist file for one note."""
        header = [
            f"# NOTE_ID: {note['NOTE_ID']}",
            f"# PERSON_ID: {note['PERSON_ID']}",
            f"# VISIT_OCCURRENCE_ID: {note['VISIT_OCCURRENCE_ID']}",
        ]
        if "NOTE_TITLE" in note.index and pd.notna(note["NOTE_TITLE"]):
            header.append(f"# NOTE_TITLE: {note['NOTE_TITLE']}")
        header += [
            "#",
            "# Mark every risk factor mentioned (and not negated) in the note above with an 'x'.",
            "# Add a short quoted evidence snippet after '->' for anything you check.",
            "# Leave as [ ] if the risk factor is absent, negated, or uncertain.",
            "",
        ]
        checklist_lines = [f"[ ] {rf} -> " for rf in risk_factors]
        ensure_dir(path.parent)
        path.write_text("\n".join(header + checklist_lines) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # Interactive annotation
    # ------------------------------------------------------------------

    def annotate_notes(self, notes_df: pd.DataFrame, risk_factors: List[str]) -> None:
        """
        Interactively annotate every note that doesn't have a checklist yet.

        For each pending note: print the note text to stdout, then block on
        opening cfg.editor for its checklist file. Resumable — rerunning
        this method only opens notes without an existing checklist file,
        unless cfg.force_reannotate is set.
        """
        checklist_dir = Path(self.cfg.checklist_dir)
        ensure_dir(checklist_dir)
        editor_cmd = shlex.split(self.cfg.editor or os.environ.get("EDITOR", "vi"))

        pending = [
            note for _, note in notes_df.iterrows()
            if self.cfg.force_reannotate or not self._checklist_path(note["NOTE_ID"]).exists()
        ]
        if not pending:
            self.log.info("All %d notes already have a checklist; nothing to annotate.", len(notes_df))
            return

        self.log.info("%d of %d notes still need annotation.", len(pending), len(notes_df))

        for i, note in enumerate(pending, start=1):
            checklist_path = self._checklist_path(note["NOTE_ID"])
            self._write_checklist_template(note, risk_factors, checklist_path)

            print("\n" + "=" * 80)
            print(f"Note {i}/{len(pending)}  |  NOTE_ID={note['NOTE_ID']}  PERSON_ID={note['PERSON_ID']}")
            print("=" * 80)
            print(note["NOTE_TEXT"])
            print("=" * 80)
            input(f"Press Enter to open the checklist in '{' '.join(editor_cmd)}' ... ")

            try:
                subprocess.run(editor_cmd + [str(checklist_path)], check=True)
            except subprocess.CalledProcessError:
                self.log.warning(
                    "Editor exited with an error for %s; checklist left as-is. Rerun to retry.",
                    checklist_path,
                )

        self.log.info("Annotation session complete: %d checklist(s) written to %s", len(pending), checklist_dir)

    # ------------------------------------------------------------------
    # Merge checklists -> gold standard CSV
    # ------------------------------------------------------------------

    def _parse_checklist(self, path: Path) -> Dict[str, object]:
        """Parse one filled-in checklist file into a flat {column: value} row."""
        row: Dict[str, object] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("# NOTE_ID:"):
                row["NOTE_ID"] = line.split(":", 1)[1].strip()
            elif line.startswith("# PERSON_ID:"):
                row["PERSON_ID"] = line.split(":", 1)[1].strip()
            elif line.startswith("# VISIT_OCCURRENCE_ID:"):
                row["VISIT_OCCURRENCE_ID"] = line.split(":", 1)[1].strip()
            else:
                match = _CHECKBOX_RE.match(line)
                if not match:
                    continue
                checked = match.group(1).strip().lower() == "x"
                risk_factor, _, evidence = match.group(2).partition("->")
                risk_factor = risk_factor.strip()
                row[f"has_{risk_factor}"] = int(checked)
                evidence = evidence.strip()
                if evidence:
                    row[f"evidence_{risk_factor}"] = evidence
        return row

    def merge_annotations(self, risk_factors: List[str]) -> pd.DataFrame:
        """
        Merge every per-note checklist file into one gold-standard DataFrame.

        Raises
        ------
        FileNotFoundError
            If no checklist files are present in cfg.checklist_dir.
        ValueError
            If a checklist file is missing one of its ID header fields
            (NOTE_ID / PERSON_ID / VISIT_OCCURRENCE_ID).
        """
        checklist_dir = Path(self.cfg.checklist_dir)
        checklist_files = sorted(checklist_dir.glob("note_*.txt"))
        if not checklist_files:
            raise FileNotFoundError(f"No checklists found in {checklist_dir}; run annotate_notes() first.")

        expected_cols = {f"has_{rf}" for rf in risk_factors}
        rows = []
        for checklist_file in checklist_files:
            row = self._parse_checklist(checklist_file)

            missing_ids = [c for c in self.ID_COLUMNS if c not in row]
            if missing_ids:
                raise ValueError(f"Checklist {checklist_file} is missing header field(s): {missing_ids}")

            missing_factors = expected_cols - row.keys()
            if missing_factors:
                self.log.warning(
                    "Checklist %s is missing entries for %s; defaulting to 0.",
                    checklist_file.name, sorted(missing_factors),
                )
                for col in missing_factors:
                    row[col] = 0
            rows.append(row)

        gold_df = pd.DataFrame(rows)
        for col in gold_df.columns:
            if col.startswith("has_"):
                gold_df[col] = gold_df[col].fillna(0).astype(int)
            elif col.startswith("evidence_"):
                gold_df[col] = gold_df[col].fillna("")

        id_cols = [c for c in self.ID_COLUMNS if c in gold_df.columns]
        has_cols = sorted(c for c in gold_df.columns if c.startswith("has_"))
        evidence_cols = sorted(c for c in gold_df.columns if c.startswith("evidence_"))
        gold_df = gold_df[id_cols + has_cols + evidence_cols]

        self.log.info("Merged %d annotated notes into the gold standard.", len(gold_df))
        return gold_df

    def save_annotations(self, gold_df: pd.DataFrame) -> None:
        """Write the merged gold-standard DataFrame to cfg.output_file."""
        output_path = Path(self.cfg.output_file)
        write_csv(gold_df, output_path)
        n_factors = sum(c.startswith("has_") for c in gold_df.columns)
        self.log.info(
            "Gold standard saved to %s (%d notes, %d risk factors).",
            output_path, len(gold_df), n_factors,
        )

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run(self) -> pd.DataFrame:
        """
        Run the full gold-standard building process.

        Steps
        -----
        1. Load notes and the lexicon's risk factors.
        2. Interactively annotate any note without an existing checklist.
        3. Merge all checklists and save the gold-standard CSV.
        """
        notes_df = self.load_notes()
        risk_factors = self.load_risk_factors()

        self.annotate_notes(notes_df, risk_factors)

        gold_df = self.merge_annotations(risk_factors)
        self.save_annotations(gold_df)
        return gold_df
