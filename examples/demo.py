"""Generate wholly invented EMDB input and output inside a fresh directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from emdb_obsidian.importer import run


def demo(root: Path) -> dict[str, Any]:
    """Build synthetic EMDB input under root and publish the import."""
    root.mkdir()  # never overwrite an earlier demonstration
    source = root / "source"
    source.mkdir()
    movies = []
    for index, title in enumerate(["The Synthetic Moon", "Synthetic Signal"], 1):
        year = ["2020"] + [""] * 16
        year[14] = str(index)
        genres = ["D" if index == 1 else "#S00", "", "20200102"] + [""] * 8
        movies.append(
            {
                "title": "\x1e".join([title, "", "", ""]),
                "year": "\x1e".join(year),
                "genres": "\x1e".join(genres),
                "rating": "\x1e".join(["", "50"] + [""] * 9),
                "plot": "An entirely invented story for this demonstration.",
                "comments": "Synthetic review: yes, [invented] and not a real record.",
            }
        )
    (source / "emdb.dat").write_text(
        json.dumps({"version": "78", "custom-genres": {"00": "Experimental"}, "movies": movies}),
        encoding="utf-16",
        newline="\n",
    )
    tv = source / "TVSeries" / "000002"
    tv.mkdir(parents=True)
    (tv / "000002.dat").write_text(
        "[Version06]\nSynthetic Signal\n2020-2021\nInvented plot\n24\n0\n0\n"
        "[Season0001]\n[Episode01]\nInvented\nPlot\n0\nY|20210304\n0\n"
        "[Episode02]\nInvented\nPlot\n0\nN|\n0\n",
        encoding="utf-16",
        newline="\n",
    )
    return run(source, root / "output", write=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    demo(args.directory)
    print(f"Synthetic demonstration written to {args.directory}")
