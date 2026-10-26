#!/usr/bin/env python3
"""Backward-compatible entry point; prefer the `emdb-obsidian` script or package.

Old workflows invoking `uv run python migrate_emdb_to_obsidian.py ...` keep
working. All logic lives in :mod:`emdb_obsidian.importer`.
"""

from __future__ import annotations

from emdb_obsidian.cli import main as main
from emdb_obsidian.importer import ImportFailure as ImportFailure
from emdb_obsidian.importer import build_note as build_note
from emdb_obsidian.importer import digest as digest
from emdb_obsidian.importer import iso_date as iso_date
from emdb_obsidian.importer import metadata as metadata
from emdb_obsidian.importer import parse_source as parse_source
from emdb_obsidian.importer import parse_tv as parse_tv
from emdb_obsidian.importer import publish as publish
from emdb_obsidian.importer import require as require
from emdb_obsidian.importer import resolve as resolve
from emdb_obsidian.importer import run as run
from emdb_obsidian.importer import safe_name as safe_name
from emdb_obsidian.importer import write_file as write_file

__all__ = [
    "ImportFailure",
    "build_note",
    "digest",
    "iso_date",
    "main",
    "metadata",
    "parse_source",
    "parse_tv",
    "publish",
    "require",
    "resolve",
    "run",
    "safe_name",
    "write_file",
]

if __name__ == "__main__":
    main()
