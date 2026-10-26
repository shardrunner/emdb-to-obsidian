"""Install exactly one built wheel into a temporary venv and exercise it outside the repo.

Run after `uv build`: `uv run python scripts/smoke_wheel.py`.
Only installation may access a package index; all smoke imports are offline.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parents[1]
    wheels = list((repo / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Expected exactly one wheel in dist; use a clean build directory")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("OMDB_API_KEY", None)
    with tempfile.TemporaryDirectory(prefix="emdb-wheel-") as temp:
        root = Path(temp).resolve()
        venv = root / "venv"

        def run(*args):
            return subprocess.run(
                args, cwd=root, env=env, check=True, stdout=subprocess.PIPE, text=True
            ).stdout

        run("uv", "venv", "--python", sys.executable, str(venv))
        bindir = venv / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        cli = bindir / ("emdb-obsidian.exe" if os.name == "nt" else "emdb-obsidian")
        run("uv", "pip", "install", "--python", str(python), str(wheels[0]))
        run(
            str(python),
            "-I",
            "-c",
            "import pathlib, sys, emdb_obsidian; "
            "p = pathlib.Path(emdb_obsidian.__file__).resolve(); "
            "assert p.is_relative_to(pathlib.Path(sys.prefix).resolve()), p; "
            "assert sys.prefix != sys.base_prefix",
        )
        assert run(str(cli), "--version").strip() == "emdb-obsidian 0.1.0"
        assert "--offline" in run(str(cli), "--help")
        source = root / "source"
        source.mkdir()
        year = ["2020"] + [""] * 16
        year[14] = "1"
        movie = {
            "title": "\x1e".join(["Synthetic Wheel", "", "", ""]),
            "year": "\x1e".join(year),
            "genres": "\x1e".join(["D", "", "20200102"] + [""] * 8),
            "rating": "\x1e".join([""] * 11),
        }
        (source / "emdb.dat").write_text(
            json.dumps({"version": "78", "movies": [movie]}), encoding="utf-16", newline="\n"
        )
        output = root / "output"
        args = [str(cli), "--emdb-dir", str(source), "--output", str(output), "--offline"]
        assert run(*args).startswith("Planned 1 notes;")
        assert not output.exists()
        assert run(*args, "--write").startswith("Published 1 notes;")
        assert (output / "Synthetic Wheel (2020).md").is_file()
        assert json.loads((output / "migration_report.json").read_bytes())["network"] == "none"
    print("Installed-wheel smoke passed (isolated import, version/help, offline dry-run/write)")


if __name__ == "__main__":
    main()
