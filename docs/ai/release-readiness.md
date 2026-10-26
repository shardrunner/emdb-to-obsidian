---
summary: Publication review, verified Ubuntu/Windows CI, historical WP3 coverage, and remaining owner validation.
read_when:
  - Preparing a release or checking remaining owner validation tasks
  - Changing packaging, CI, parser, or publication safety
---

# Release readiness

Native Ubuntu and Windows CI is verified green on Python 3.11/3.13: **137 tests passed per Ubuntu job and 138 per Windows job**, with no skips. See [current publication evidence](#current-publication-evidence) for the verified run and local results.

No runtime implementation changes in WP3. Prior committed parser, portability and numeric-validation fixes are covered by the existing suite; new tests fill remaining integration gaps rather than repeating malformed-artwork or publication-failure tests.

## Historical WP3 local evidence

Executed on Linux with Python 3.14.7:

- `uv run pytest -q`: passed with no skips. Current test counts are recorded below under [current publication evidence](#current-publication-evidence).
- `uv run ruff check .`: all checks passed.
- `uv run ruff format --check .`: 19 files already formatted.
- Fresh `examples.demo.demo` in a temporary directory: all four output artifacts compared byte-for-byte with `examples/expected/`; identical.
- `uv build`: built `dist/emdb_obsidian_once-0.1.0.tar.gz` and `dist/emdb_obsidian_once-0.1.0-py3-none-any.whl` (wheel built from sdist).
- Subsequently, `uv run python scripts/smoke_wheel.py`: passed isolated import provenance, CLI version/help, synthetic offline dry-run and write. Build and smoke were sequential.

The smoke creates a separate temporary venv, installs the explicit wheel (not the repository), clears `PYTHONPATH`/`PYTHONHOME`, removes the provider key from child environments, and runs outside the checkout. It verifies the import is under the isolated interpreter prefix. Dependency installation can access a package index; runtime checks do not request enrichment. CI runs this same script after distribution build on Ubuntu/Windows with Python 3.11/3.13. Symlink tests explicitly skip if the platform cannot create symlinks.

New integration evidence covers HTTPS request identity, timeout and headers with a synthetic credential, one fetch for shared IMDb identity, immutable input cache, used-only metadata snapshot, independent SHA-256 verification of every non-report output and source input, offline byte-identical note replay, distinct byte-exact local artwork, redacted provider/malformed-JSON/missing-key CLI failures, destination restrictions and controlled numeric CLI errors. Invalid artwork/no publication and existing-directory refusal were already covered.

## Current publication evidence

Reviewed commit `a6810c59610794bf550d31621c263461e7aa6e54`:

- [GitHub Actions run 40252224941](https://github.com/shardrunner/emdb-to-obsidian/actions/runs/40252224941) passed all four jobs: Ubuntu and Windows, each with Python 3.11 and 3.13. The logs report **137 passed** per Ubuntu job and **138 passed** per Windows job, with no skips. The symlink tests therefore ran rather than skipping on these runners.
- Every CI job passed lint, formatting, the synthetic demo, distribution build, and isolated installed-wheel smoke checks.
- Local publication review on Linux with Python 3.15.0: **137 passed in 0.19s**, lint and formatting passed; a fresh demo matched all four committed expected artifacts byte-for-byte. A fresh build and subsequent isolated installed-wheel smoke also passed.
- Inspection of tracked paths, locally reachable Git history, and built archive contents found no private source/cache/artwork or generated private output. A basic credential-pattern scan of all 29 historical file blobs found no matches; this was not a dedicated secret-scanner audit. Ignored private inputs were not read.
- The existing commit author name and email will become public with the repository; owner acceptance remains a publication decision.

These observations supersede the earlier pending native Windows CI check, not the historical WP3 results above. No local Python 3.11/3.13 execution is claimed.

## Unverified owner gates

- Revalidate an untouched private backup via offline dry-run and fresh-directory write after the latest parser/validation fixes, then review notes/artwork in Obsidian before manually moving output. Historical owner runs do not establish current revalidation.
- No private source/cache/vault was read in WP3, and no live provider was called.

`docs-list` was attempted at task start and reported `docs/ai is missing`; this directory now contains discoverable internal documentation with frontmatter. Public design/provenance remains at `docs/design.md`.
