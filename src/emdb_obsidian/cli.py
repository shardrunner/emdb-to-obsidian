"""Command-line entry point for the EMDB 78 to Obsidian one-time importer."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from emdb_obsidian import __version__
from emdb_obsidian.importer import ImportFailure, run


def dist_version() -> str:
    """Return the installed distribution version, falling back to the package one."""
    try:
        return version("emdb-obsidian-once")
    except PackageNotFoundError:
        return __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the importer argument parser."""
    parser = argparse.ArgumentParser(
        description="One-time EMDB 78 importer. No vault reads, synchronization, or overwrites."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {dist_version()}")
    parser.add_argument("--emdb-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache-file", type=Path, help="Read-only OMDb JSON snapshot")
    parser.add_argument("--write", action="store_true")
    network = parser.add_mutually_exclusive_group()
    network.add_argument("--offline", action="store_true", help="Explicit default: zero network")
    network.add_argument(
        "--enrich", action="store_true", help="Fetch missing OMDb metadata; requires --write"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments, plan or publish the import, and report the outcome."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        plan = run(
            args.emdb_dir,
            args.output,
            write=args.write,
            cache_file=args.cache_file,
            enrich=args.enrich,
        )
    except (ImportFailure, OSError) as exc:
        parser.exit(1, f"Import failed: {exc}\n")
    print(
        f"{'Published' if args.write else 'Planned'} {len(plan['notes'])} notes; "
        f"{len(plan['report']['warnings'])} warnings"
    )
    if not args.write:
        print(json.dumps(plan["report"], ensure_ascii=False, indent=2))
