# src/utils_io.py
"""I/O helpers for reading and writing pipeline artefacts."""

import logging
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

LOG = logging.getLogger("mrsa_nlp.rule.utils_io")


def ensure_dir(d: Path) -> None:
    """Create *d* and all parents if they do not exist."""
    d.mkdir(parents=True, exist_ok=True)


def read_parquet(p: Path) -> pd.DataFrame:
    """
    Read a Parquet file into a DataFrame.

    Falls back to a UTF-8-tolerant read if PyArrow rejects the file with
    "Unknown error: Wrapping ..." — this happens when a `string` column
    contains malformed byte sequences (seen in externally generated,
    non-pyarrow EHR-export Parquet files), since PyArrow validates UTF-8
    when decoding a column as `string` but not as `binary`.
    """
    try:
        return pd.read_parquet(p)
    except pa.lib.ArrowException as exc:
        if "Wrapping" not in str(exc):
            raise
        LOG.warning(
            "PyArrow rejected %s due to malformed UTF-8 (%s); retrying with binary fallback.",
            p, exc,
        )
        return _read_parquet_utf8_tolerant(p)


def _read_parquet_utf8_tolerant(p: Path) -> pd.DataFrame:
    """Read *p* with string columns forced to binary, then decode as UTF-8 (invalid bytes replaced)."""
    base_schema = pq.ParquetFile(p).schema_arrow
    string_cols = {
        field.name
        for field in base_schema
        if pa.types.is_string(field.type) or pa.types.is_large_string(field.type)
    }
    override_schema = pa.schema([
        field.with_type(pa.binary()) if field.name in string_cols else field
        for field in base_schema
    ])
    df = ds.dataset(str(p), format="parquet", schema=override_schema).to_table().to_pandas()
    for col in string_cols:
        df[col] = df[col].map(
            lambda v: v.decode("utf-8", errors="replace") if isinstance(v, (bytes, bytearray)) else v
        )
    return df


def _sanitize_utf8(value: object) -> object:
    """Replace invalid UTF-8 byte sequences in *value*; pass through non-strings."""
    if isinstance(value, str):
        return value.encode("utf-8", errors="replace").decode("utf-8")
    return value


def write_parquet(df: pd.DataFrame, p: Path) -> None:
    """
    Write *df* to a Parquet file at *p*.

    Converts all-NA object columns to string type to satisfy PyArrow's
    strict schema inference, and sanitizes remaining object columns to
    valid UTF-8. Clinical note text sourced from EHR exports can contain
    non-UTF-8 byte sequences, which otherwise make PyArrow fail with
    "Unknown error: Wrapping ..." while computing column statistics.
    """
    ensure_dir(p.parent)
    for col in df.columns:
        if df[col].dtype == "object":
            if df[col].isna().all():
                df[col] = df[col].astype("string")
            else:
                df[col] = df[col].map(_sanitize_utf8)
    df.to_parquet(p, index=False, engine="pyarrow")


def write_csv(df: pd.DataFrame, p: Path) -> None:
    """Write *df* to a UTF-8 CSV file at *p*."""
    ensure_dir(p.parent)
    df.to_csv(p, index=False, encoding="utf-8")
