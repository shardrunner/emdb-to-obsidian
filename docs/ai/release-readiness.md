---
summary: Final WP3 safety coverage, installed-wheel validation evidence, and unverified owner gates.
read_when:
  - Preparing a release or checking remaining owner validation tasks
  - Changing packaging, CI, parser, or publication safety
---

# Final WP3 readiness

No runtime implementation changes in WP3. Prior committed parser, portability and numeric-validation fixes are covered by the existing suite; new tests fill remaining integration gaps rather than repeating malformed-artwork or publication-failure tests.

## Local evidence

Executed on Linux with Python 3.14.7:

- `uv run pytest -q`: **136 passed in 0.43s**, no skips (baseline 121; 15 added cases).
- `uv run ruff check .`: all checks passed.
- `uv run ruff format --check .`: 19 files already formatted.
- Fresh `examples.demo.demo` in a temporary directory: all four output artifacts compared byte-for-byte with `examples/expected/`; identical.
- `uv build`: built `dist/emdb_obsidian_once-0.1.0.tar.gz` and `dist/emdb_obsidian_once-0.1.0-py3-none-any.whl` (wheel built from sdist).
- Subsequently, `uv run python scripts/smoke_wheel.py`: passed isolated import provenance, CLI version/help, synthetic offline dry-run and write. Build and smoke were sequential.

The smoke creates a separate temporary venv, installs the explicit wheel (not the repository), clears `PYTHONPATH`/`PYTHONHOME`, removes the provider key from child environments, and runs outside the checkout. It verifies the import is under the isolated interpreter prefix. Dependency installation can access a package index; runtime checks do not request enrichment. CI runs this same script after distribution build on Ubuntu/Windows with Python 3.11/3.13. Symlink tests explicitly skip if the platform cannot create symlinks.

New integration evidence covers HTTPS request identity, timeout and headers with a synthetic credential, one fetch for shared IMDb identity, immutable input cache, used-only metadata snapshot, independent SHA-256 verification of every non-report output and source input, offline byte-identical note replay, distinct byte-exact local artwork, redacted provider/malformed-JSON/missing-key CLI failures, destination restrictions and controlled numeric CLI errors. Invalid artwork/no publication and existing-directory refusal were already covered.

## Unverified owner gates

- Observe native Windows CI results, including actual symlink availability. Linux tests simulating portability behavior are not native Windows evidence. No local Python 3.11/3.13 run is claimed here.
- Revalidate an untouched private backup via offline dry-run and fresh-directory write after the latest parser/validation fixes, then review notes/artwork in Obsidian before manually moving output. Historical owner runs do not establish current revalidation.
- No private source/cache/vault was read in WP3, and no live provider was called.

`docs-list` was attempted at task start and reported `docs/ai is missing`; this directory now contains discoverable internal documentation with frontmatter. Public design/provenance remains at `docs/design.md`.
