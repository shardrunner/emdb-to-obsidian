# Design and provenance

## Intent

Publication preparation for a personal, one-time migration. Keep one implementation module (`src/emdb_obsidian/importer.py`), one explicit planning path, one publication function, and one CLI entry point (`src/emdb_obsidian/cli.py`, installed as `emdb-obsidian`). A thin top-level compat shim (`migrate_emdb_to_obsidian.py`) re-exports the package so old invocations keep working. No synchronization, service, database, or AI classification. This project demonstrates bounded data engineering, not invented AI functionality.

## Evidence and boundaries

The original private script was read before replacement. Read-only structural inspection of the private source established root version `78`, field lengths (title 4, year 17, genres/rating 11), custom genre mapping shape, and Version06 episode marker/flag offsets. No private record, review, title or artwork was copied into tests or documentation. The existing Obsidian output was neither read nor written. Historical migration results are not validation results for this replacement.

Synthetic input is constructed in `examples/demo.py` and isolated pytest fixtures. Expected files are generated solely from that demo.

## Decisions

- Fail on unsupported layouts and unsafe filenames rather than guessing. This means an unchanged private export may require corrections to a working copy before import. The owner previously validated the packaged importer against the private export; this is not revalidation of the latest parser and numeric-validation fixes. A new private run and Obsidian review remain owner tasks.
- Preserve every title record; shared IMDb IDs are report findings, not permission to discard personal data.
- Separate local record identity from external IMDb identity. Unique source-record artwork names avoid shared-ID poster collisions.
- Use PyYAML instead of custom scalar quoting. Dates remain explicit strings.
- Default dry-run and write mode both prohibit network. Enrichment is an explicit write-mode capability. No remote poster downloading: fewer failure modes, no accidental offline leakage, no image dependency.
- Input caches are immutable. Used metadata is persisted with the successful import, staged like notes. A failed enrichment loses in-memory new responses instead of corrupting a private cache.
- Hash input bytes and output artifacts; omit wall-clock time and host paths. Reproducibility depends on an immutable source/snapshot and the locked environment. Sources are not locked against external edits during a run.
- Local artwork is copied, not resized; JPEG signature validation is intentionally weaker than full decoding.
- No Base embed by default; no dependency on an absent personal `Filme.base`.
- Stage then reserve a fresh output exclusively (`ImportFailure: Output already exists; choose a fresh directory`). Portable no-replace hard links are the fast path; filesystems without hard-link support (Windows/FAT/exFAT, cross-device) fall back to copy plus atomic publish. Neither path provides whole-directory atomic publication or crash recovery. README documents this limitation rather than claiming a transaction.

## Validation

Tests cover existing destinations, reservation races, Unicode/case collisions, unsafe names, duplicate preservation, YAML round trips, strict network-free operation with remote poster metadata, dry-run side effects, episode progress and precedence, malformed input, credential-redacted network failures, staging failures, publication failures and deterministic synthetic output. Tests use isolated temporary directories and mocked network only. No test exercises a live vault or live provider.

Initial red test execution failed at collection because the old implementation required undeclared Pillow; after replacement the behavioral suite was run green. Further safety and golden tests were added for the new desired-state API. A subsequent behavioral red/green cycle reproduced acceptance of failed or mismatched metadata cache responses (two failing tests), then added explicit response/IMDb identity validation. Packaging work added the `emdb-obsidian` entry point with `--version` and the hard-link copy fallback. Subsequent tests cover strict six-line episode parsing (opaque content slots), ASCII numeric validation, record-context errors, LF synthetic source bytes, POSIX hash paths, fallback errors and preservation of original publication failures. Final safety coverage adds mocked successful enrichment, shared-ID fetch deduplication, immutable cache input, used-entry snapshots, independently checked artifact hashes, offline note replay, distinct byte-exact artwork, provider/JSON/missing-key failures, destination restrictions and CLI validation. Existing invalid-artwork coverage verifies no publication.

CI is configured for Python 3.11 and 3.13 on Ubuntu and Windows. It builds distributions and runs `scripts/smoke_wheel.py`, installing only the wheel and its dependencies into a separate temporary environment. The smoke runs outside the repository with `PYTHONPATH` cleared and checks import provenance and the installed CLI. Dependency acquisition may use an index; runtime validation uses synthetic data without a live provider. Native Ubuntu and Windows CI passed for commit `a6810c5` with Python 3.11/3.13; see [release validation](ai/release-readiness.md) for the run and platform-specific test counts.

## Deferred owner decisions

Manually moving verified output into a vault. No screenshot is published by design; the synthetic demo and committed `examples/expected/` files are the reproducible evidence. No remote repository or push is performed by implementation work.

Public design remains here; internal release readiness and validation records live under `docs/ai/`.
