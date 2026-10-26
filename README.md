# EMDB → Obsidian, once

> **Disclaimer:** This project is vibe coded for personal use. Use at your own risk.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![CI: offline tests + ruff + demo](https://img.shields.io/badge/CI-offline_tests_ruff_demo-blue)](.github/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A validated **one-time importer** from a personal EMDB export (JSON version `78`) to Obsidian notes. It plans every note, name, episode tree and artwork byte before writing, then publishes to a fresh directory — dry-run by default, offline by default, never overwriting.

The owner previously validated a private-export dry-run and write; revalidation after the latest parser/validation fixes and Obsidian review remain unverified. The committed demonstration is wholly synthetic and runs offline with no credentials. No screenshot is included by design.

Never publish your EMDB directory, cache, artwork, notes, reviews, or API key.

## Quickstart (Python 3.11+, uv)

```sh
uv sync --locked && uv run pytest
uv run emdb-obsidian --help
uv run emdb-obsidian --version  # 0.1.0
# Must be a fresh directory; entirely synthetic, offline, no credentials:
uv run python examples/demo.py /tmp/emdb-demo-fresh
```

Inspect `/tmp/emdb-demo-fresh/output/`, or the committed [`examples/expected/`](examples/expected/) movie, series, metadata snapshot and report. Running the demo twice refuses the existing directory. Choose another fresh directory rather than deleting anything automatically.

Implementation lives in `src/emdb_obsidian/` (`importer.py` holds the logic, `cli.py` the `emdb-obsidian` entry point). The top-level `migrate_emdb_to_obsidian.py` is a thin legacy shim that re-exports the package, so old `uv run python migrate_emdb_to_obsidian.py ...` invocations still work; new usage should prefer `uv run emdb-obsidian ...`.

## Import your private data

Keep an untouched backup. Use a **new output directory outside the source**, preferably a scratch directory, not an existing vault folder. Its parent must exist. There are no default personal paths.

```sh
# Validate, render in memory and print report: no writes, zero network
uv run emdb-obsidian \
  --emdb-dir /path/to/private/EMDB --output /path/to/fresh-import --offline

# Publish the same offline plan
uv run emdb-obsidian \
  --emdb-dir /path/to/private/EMDB --output /path/to/fresh-import --offline --write
```

Optional `--cache-file /path/to/private/metadata.json` reads an OMDb ID → response mapping. It is never modified. Default and `--offline` prohibit **all network**, including posters. Local JPEGs are copied byte-for-byte; no artwork is downloaded in any mode.

Explicit `--enrich --write` fetches only missing IMDb IDs from OMDb. Set `OMDB_API_KEY` in the environment (not in source or command arguments). It is mutually exclusive with `--offline`; enrichment is refused in dry-run. Requests have a timeout and failures abort with credential-redacted errors. Existing cache entries win; no refresh/retry mechanism is provided. Requests may consume your quota even if publication later fails. The successful output includes a used-entry metadata snapshot for offline replay. API responses, licensing and accuracy remain your responsibility.

Review warnings, duplicates, notes and report before manually moving a completed import into Obsidian. This tool never reads or merges existing notes. There is no `--force`, update, or `--prefer-emdb` mode.

## Supported source scope

Only the observed **EMDB JSON version `78`**, UTF-16, is supported:

- `movies` objects with record-separator (`U+001E`) fields: `title` 4 segments, `year` 17, `genres` 11, `rating` 11.
- Title segment 0; original title segment 1 (observed `#<letter>` prefix removed); year segment 0; cover/episode ID segment 14.
- Genre segment 0 (`#` denotes series), IMDb segment 1 (first pipe-delimited value), added date segment 2, watched date segment 8.
- Ratings: first two segments are hexadecimal tenths, `00` means absent. Interpreted numeric fields require ASCII digits (ratings allow ASCII hex); calendar dates are validated, not guessed. Record validation errors identify the 1-based source record. Windows reserved names include superscript COM/LPT variants.
- `TVSeries/000001/000001.dat`: UTF-16 `[Version06]`, seven header lines, season markers and six-line episode blocks; watched flag at episode offset 4. Blocks are consumed exactly six lines at a time; bracket-prefixed content remains opaque. Unexpected boundary lines, truncated blocks, malformed flags and duplicate episode numbers fail.
- `Covers/000001.jpg`: optional local JPEG. Signature checked only, not fully decoded.

Evidence is structural inspection of a single private export, not a vendor specification. Other versions/layouts fail rather than silently guessing. Some unused EMDB fields are deliberately not interpreted. Native genre letters are a **partial, inferred** map; unmapped codes are reported. Two-digit custom genres are resolved using `custom-genres`, never assumed to be Anime. Collection membership does not imply a genre. Unknown layouts need explicit investigation and tests before support is added. One-shot only: no sync, update, or merge mode.

## Output and precedence

Each source record gets one note, named `Title (source-year).md`. No record is absorbed, even if IMDb IDs match; the report lists shared IDs by source record number. Case-insensitive Unicode-normalized filename collisions abort the whole plan. Unsafe/reserved filenames fail; edit a private working copy explicitly if necessary. Names are not silently sanitized. Posters use unique source-record filenames under `assets/`.

Frontmatter is real YAML (PyYAML), with:

- `title`, `aliases`, `type` (`movie`/`series`), `year`, optional `year_end`;
- `imdb_id`, `imdb_rating`, `my_rating`, `genres`, `runtime` (minutes);
- `date_added`, `watched_date` (ISO date strings), `status` (`to-watch`, `partial`, `watched`);
- series: `episodes_total`, `episodes_watched`, `last_episode`;
- optional `poster`, `source_record` (1-based input order), `provenance`.

Null values are omitted; empty lists remain lists. Plot appears as a blockquote; comments and custom fields become the Review body. Imported Markdown/HTML is **not sanitized**: use trusted sources and review content before opening it in a plugin-enabled vault. No hardcoded Base embed is emitted; notes work without any Base or plugin.

OMDb wins for year, runtime, public rating, plot and genres when supplied; EMDB supplies fallbacks and always owns personal rating, review and added date. Local title is retained; OMDb title becomes an alias. Episode trees establish series type and override runtime, end year and progress. Latest dated watched episode wins over title watch date. A rating implies watched status only without episode progress; **no watched date is invented from added date**. Specials count toward totals; status can therefore be partial despite finishing the main season. `last_episode` means highest watched episode, not contiguous completion. No abandoned status is inferred.

`migration_report.json` records schema version, counts, warnings, shared IDs, source SHA-256 hashes and output hashes (excluding the report itself). `metadata_snapshot.json` contains used OMDb entries only. These files contain private data and must stay private. The synthetic demo writes explicit LF source text, and report paths use forward slashes across platforms. Same inputs/snapshot, mode and locked environment produce byte-identical output: no clock timestamps or absolute paths are serialized. Source record identifiers are positional, not stable IDs across edited exports.

## Failure and recovery contract

All records, names, trees, artwork signatures and rendered notes are planned before writes. Output must not exist, even empty or a dangling symlink — an existing destination is refused with `ImportFailure: Output already exists; choose a fresh directory`. The importer stages complete files in a temporary sibling directory, flushes/fsyncs them, then exclusively creates the output directory and publishes files using no-replace hard links (fast path), falling back to a byte copy plus atomic publish on filesystems without hard-link support (Windows/FAT/exFAT, cross-device). No existing file is replaced; cache inputs remain unchanged.

**The directory as a whole is not an atomic transaction.** Individual files appear atomically. Ordinary staging/publication failures clean up files created by this invocation. A kill, power loss, or hostile concurrent directory mutation can leave a staging directory or incomplete output. The report is published last: verify its file hashes before treating an import as complete. There is no automatic resume. Keep failed output for inspection and retry into another fresh path. Directory fsync/power-loss durability is not guaranteed. Do not let another process edit the destination during publication. The complete plan and artwork are held in memory, appropriate for this small personal collection rather than large-scale ingestion.

## Package validation

[CI passed for commit `a6810c5`](https://github.com/shardrunner/emdb-to-obsidian/actions/runs/40252224941) on Ubuntu and Windows with Python 3.11/3.13: **137 tests passed per Ubuntu job and 138 per Windows job**, with no skips. Distribution builds and installed-wheel smoke checks also passed.

After `uv build`, run `uv run python scripts/smoke_wheel.py`: it installs the built wheel into a separate temporary environment, clears `PYTHONPATH`, verifies isolated import, and exercises CLI version/help and synthetic offline dry-run/write from outside the repository. Dependency installation may need a package index; runtime checks use no provider.

## Publication checklist

- Keep credentials in the environment, never in source or command arguments.
- Private source/cache/artwork and generated output are ignored. Use explicit staging and inspect `git diff --cached` before every publication; ignore rules are not a secret scanner.
- Licensed under the [MIT License](LICENSE). Third-party metadata/artwork rights are separate.
- Committed examples are synthetic and sufficient to run the demo; no screenshot is published by design.

See [design and provenance](docs/design.md) for decisions and boundaries, and [release readiness](docs/ai/release-readiness.md) for validation evidence and remaining checks.
