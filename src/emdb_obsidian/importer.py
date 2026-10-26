#!/usr/bin/env python3
"""One-time EMDB 78 importer. No vault reads, synchronization, or overwrites."""

from __future__ import annotations

import errno
import hashlib
import html
import json
import os
import re
import shutil
import tempfile
import unicodedata
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml

from emdb_obsidian import __version__

SEP = "\x1e"
GENRES = dict(
    A="Action",
    C="Animation",
    D="Drama",
    F="Fantasy",
    I="Family",
    K="Comedy",
    R="Romance",
    S="Sci-Fi",
    T="Thriller",
    V="Adventure",
)
USER_AGENT = f"emdb-obsidian-once/{__version__}"
# os.link errnos that trigger the portable copy fallback (Windows/FAT, EXDEV).
_LINK_FALLBACK_ERRNOS = frozenset(
    getattr(errno, name)
    for name in ("EXDEV", "EPERM", "EACCES", "ENOTSUP", "EOPNOTSUPP", "ENOSYS")
    if hasattr(errno, name)
)


class ImportFailure(ValueError):
    """Invalid or unsupported input; nothing should be published."""


def require(condition: bool, message: str) -> None:
    """Raise ImportFailure unless condition holds."""
    if not condition:
        raise ImportFailure(message)


@contextmanager
def record_context(index: int) -> Iterator[None]:
    """Attach the source record index to validation failures, once."""
    try:
        yield
    except ImportFailure as error:
        raise ImportFailure(f"Record {index}: {error}") from None


def iso_date(value: str | None) -> str | None:
    """Validate an EMDB YYYYMMDD string and return ISO format, or None."""
    if not value:
        return None
    require(bool(re.fullmatch(r"[0-9]{8}", value)), "Invalid date encoding")
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:])).isoformat()
    except ValueError:
        raise ImportFailure("Invalid calendar date") from None


def safe_name(value: str) -> str:
    """Validate a note stem for Linux, Windows and FAT portability."""
    require(bool(value) and value not in {".", ".."}, "Empty or unsafe filename")
    require(not re.search(r'[\x00-\x1f<>:"/\\|?*\[\]#^]', value), "Unsafe filename")
    require(value == value.strip() and not value.endswith("."), "Unsafe filename")
    require(
        value.split(".")[0].upper()
        not in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(10)),
            *(f"LPT{i}" for i in range(10)),
            *(f"{prefix}{digit}" for prefix in ("COM", "LPT") for digit in "¹²³"),
        },
        "Reserved filename",
    )
    require(len(value.encode("utf-8")) <= 180, "Filename too long")
    return value


def digest(data: bytes) -> str:
    """Return the SHA-256 hex digest of data."""
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path | str, encoding: str = "utf-8") -> tuple[Any, str]:
    """Read JSON from path, returning (payload, sha256 of raw bytes)."""
    try:
        raw = Path(path).read_bytes()
        return json.loads(raw.decode(encoding), strict=False), digest(raw)
    except (UnicodeError, json.JSONDecodeError):
        raise ImportFailure("Invalid JSON or text encoding") from None


def parse_source(root: Path) -> tuple[list[dict[str, Any]], dict[str, str], list[str]]:
    """Parse and validate EMDB version 78 source, returning records/hashes/warnings."""
    data, checksum = read_json(root / "emdb.dat", "utf-16")
    require(
        isinstance(data, dict) and data.get("version") == "78", "Only EMDB version 78 is supported"
    )
    require(isinstance(data.get("movies"), list), "movies must be a list")
    custom = data.get("custom-genres", {})
    require(
        isinstance(custom, dict)
        and all(
            isinstance(k, str) and re.fullmatch(r"[0-9]{2}", k) and isinstance(v, str)
            for k, v in custom.items()
        ),
        "Invalid custom genre mapping",
    )
    records = []
    warnings = []
    for index, movie in enumerate(data["movies"], 1):
        with record_context(index):
            require(isinstance(movie, dict), "Movie must be an object")
            fields = {}
            for key, length in [("title", 4), ("year", 17), ("genres", 11), ("rating", 11)]:
                require(isinstance(movie.get(key), str), f"invalid {key}")
                fields[key] = movie[key].split(SEP)
                require(len(fields[key]) == length, f"unsupported {key} layout")
            title, year, genres, rating = (fields[k] for k in ("title", "year", "genres", "rating"))
            safe_name(title[0])
            require(not year[0] or bool(re.fullmatch(r"[0-9]{4}", year[0])), "Invalid year")
            require(
                bool(re.fullmatch(r"[0-9]+", year[14])) and 0 < int(year[14]) <= 999999,
                "Invalid cover/tree ID",
            )
            iid = genres[1].split("|")[0]
            require(not iid or bool(re.fullmatch(r"(?:tt)?[0-9]{1,10}", iid)), "Invalid IMDb ID")
            iid = "tt" + iid.removeprefix("tt").zfill(7) if iid else None
            scores = []
            for raw in rating[:2]:
                require(not raw or bool(re.fullmatch("[0-9a-fA-F]{2}", raw)), "Invalid rating")
                score = int(raw, 16) / 10 if raw and raw != "00" else None
                require(score is None or score <= 10, "Rating outside 0–10")
                scores.append(score)
            codes = genres[0].removeprefix("#")
            decoded = []
            for code in re.findall(r"[0-9]{2}|.", codes):
                name = custom.get(code) if code.isascii() and code.isdecimal() else GENRES.get(code)
                if name:
                    decoded.append(name)
                else:
                    warnings.append(f"Record {index}: unmapped genre code {code!r}")
            text = {}
            for key in ("comments", "custom-fields", "plot"):
                value = movie.get(key, "")
                require(isinstance(value, str), f"Invalid {key}")
                text[key] = html.unescape(
                    value.replace("<br/>", "\n")
                    .replace("<br>", "\n")
                    .replace("<DQ>", '"')
                    .replace(SEP, "\n")
                ).strip()
            records.append(
                dict(
                    source_record=index,
                    title=title[0],
                    aliases=[re.sub(r"^#[A-Z]", "", title[1])] if title[1] else [],
                    year=int(year[0]) if year[0] else None,
                    cover_id=f"{int(year[14]):06d}",
                    imdb_id=iid,
                    type="series" if genres[0].startswith("#") else "movie",
                    genres=decoded,
                    date_added=iso_date(genres[2]),
                    watched_date=iso_date(genres[8]),
                    imdb_rating=scores[0],
                    my_rating=scores[1],
                    plot=text["plot"],
                    review="\n".join(v for v in [text["comments"], text["custom-fields"]] if v),
                )
            )
    return records, {"emdb.dat": checksum}, warnings


def parse_tv(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a Version06 episode tree, returning (summary, sha256 of raw bytes)."""
    raw = path.read_bytes()
    try:
        lines = raw.decode("utf-16").splitlines()
    except UnicodeError:
        raise ImportFailure(f"{path}: Invalid episode encoding") from None

    def check(condition: bool, offset: int, message: str) -> None:
        require(condition, f"{path}:{offset + 1}: {message}")

    check(len(lines) >= 7 and lines[0] == "[Version06]", 0, "Unsupported episode layout")
    check(bool(re.fullmatch(r"[0-9]{4}(?:-[0-9]{4})?", lines[2])), 2, "Invalid episode year range")
    check(
        bool(re.fullmatch(r"[0-9]+", lines[4])) and int(lines[4]) > 0, 4, "Invalid episode runtime"
    )
    season = None
    episodes = {}
    i = 7
    while i < len(lines):
        match = re.fullmatch(r"\[Season([0-9]+)\]", lines[i])
        if match:
            season = int(match[1])
            i += 1
            continue
        match = re.fullmatch(r"\[Episode([0-9]+)\]", lines[i])
        check(match is not None, i, "Expected season or episode marker")
        check(season is not None, i, "Episode before season")
        check(i + 5 < len(lines), i, "Incomplete episode block")
        number = int(match[1])
        flag = re.fullmatch(r"(Y|N)\|([0-9]{8})?", lines[i + 4])
        check(flag is not None, i + 4, "Invalid episode watched flag")
        check((season, number) not in episodes, i, "Duplicate episode number")
        try:
            watched_date = iso_date(flag[2])
        except ImportFailure as error:
            raise ImportFailure(f"{path}:{i + 5}: {error}") from None
        episodes[season, number] = (flag[1] == "Y", watched_date)
        # Content slots are opaque, even when they look like section markers.
        i += 6
    watched = [key for key, value in episodes.items() if value[0]]
    dates = [v[1] for v in episodes.values() if v[0] and v[1]]
    last = max(watched) if watched else None
    years = lines[2].split("-")
    return dict(
        runtime=int(lines[4]),
        year_end=int(years[1]) if len(years) == 2 else None,
        episodes_total=len(episodes),
        episodes_watched=len(watched),
        last_episode=f"S{last[0]:02d}E{last[1]:02d}" if last else None,
        latest_mark=max(dates) if dates else None,
    ), digest(raw)


def metadata(iid: str | None, cache: dict[str, Any], enrich: bool) -> dict[str, Any]:
    """Return validated metadata for iid; fetch missing entries only when enriching."""
    if iid and iid not in cache and enrich:
        key = os.environ.get("OMDB_API_KEY")
        require(bool(key), "Set OMDB_API_KEY for enrichment")
        try:
            url = "https://www.omdbapi.com/?" + urlencode(dict(apikey=key, i=iid, plot="full"))
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(request, timeout=15) as response:
                data = json.load(response)
            require(
                isinstance(data, dict) and data.get("Response") == "True", "OMDb rejected request"
            )
            cache[iid] = data
        except Exception:
            # Never print URLs, provider messages, or chained errors containing credentials.
            raise ImportFailure("OMDb enrichment failed; no output published") from None
    data = cache.get(iid, {})
    require(isinstance(data, dict), "Invalid metadata entry")
    require(data.get("Response", "True") == "True", "Failed metadata response in cache")
    require(data.get("imdbID", iid) == iid, "Metadata IMDb ID does not match requested record")
    require(
        all(
            isinstance(v, str)
            for k, v in data.items()
            if k in {"Title", "Type", "Year", "Runtime", "Genre", "Plot", "imdbRating"}
        ),
        "Invalid metadata field type",
    )
    return {k: v for k, v in data.items() if v not in ("", "N/A", None)}


def resolve(
    record: dict[str, Any], meta: dict[str, Any], tv: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge EMDB record with metadata snapshot and episode tree; never mutate inputs."""
    r = dict(record)
    r["aliases"] = list(record.get("aliases", []))
    provenance = {"personal_fields": "EMDB", "metadata": "EMDB fallback"}
    if meta:
        provenance["metadata"] = "OMDb snapshot with EMDB fallback"
    if "Type" in meta:
        require(meta["Type"] in {"movie", "series"}, "Unsupported OMDb type")
        r["type"] = meta["Type"]
    if tv:
        r["type"] = "series"
    if "Year" in meta:
        match = re.fullmatch(r"([0-9]{4})(?:[-–]([0-9]{4})?)?", meta["Year"])
        require(match is not None, "Invalid OMDb year")
        r["year"] = int(match[1])
        r["year_end"] = int(match[2]) if match[2] else None
    if "Runtime" in meta:
        require(bool(re.fullmatch(r"[0-9]+ min", meta["Runtime"])), "Invalid OMDb runtime")
        r["runtime"] = int(meta["Runtime"].split()[0])
    if "imdbRating" in meta:
        require(
            bool(re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", meta["imdbRating"])), "Invalid IMDb rating"
        )
        r["imdb_rating"] = float(meta["imdbRating"])
        require(0 <= r["imdb_rating"] <= 10, "IMDb rating outside 0–10")
    for field, key in [("plot", "Plot"), ("genres", "Genre")]:
        if key in meta:
            r[field] = meta[key].split(", ") if field == "genres" else meta[key]
    if meta.get("Title") and meta["Title"] != r["title"]:
        r["aliases"].append(meta["Title"])
    r["status"] = "watched" if r["my_rating"] is not None or r["watched_date"] else "to-watch"
    if tv:
        r.update({k: v for k, v in tv.items() if k != "latest_mark"})
        provenance["runtime_and_progress"] = "EMDB episode tree"
        if tv["latest_mark"]:
            r["watched_date"] = tv["latest_mark"]
        if tv["episodes_total"]:
            r["status"] = (
                "watched"
                if tv["episodes_watched"] == tv["episodes_total"]
                else "partial"
                if tv["episodes_watched"]
                else "to-watch"
            )
    r["provenance"] = provenance
    return r


def build_note(record: dict[str, Any]) -> str:
    """Render a resolved record as Obsidian Markdown with YAML frontmatter."""
    front = {
        k: v for k, v in record.items() if k not in {"plot", "review", "cover_id"} and v is not None
    }
    body = ""
    if record.get("poster"):
        body += f"![[{record['poster']}|180]]\n\n"
    plot = record.get("plot", "")
    if plot:
        body += "\n".join("> " + line for line in plot.splitlines()) + "\n\n"
    return (
        "---\n"
        + yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
        + "---\n"
        + body
        + "## Review\n"
        + record.get("review", "")
        + "\n"
    )


def write_file(path: Path, data: bytes) -> None:
    """Write data exclusively (O_EXCL) and fsync before returning."""
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def publish(output: Path, files: dict[str, bytes]) -> None:
    """Stage fully, reserve destination exclusively, then publish complete files.

    Fast path publishes each staged file with an atomic no-replace hard link.
    On filesystems without hard-link support (Windows/FAT, cross-device), a
    link failure with errno EXDEV, EPERM, EACCES, ENOTSUP/EOPNOTSUPP or
    ENOSYS (operation unavailable) falls back to copying the
    staged file to a temporary sibling inside the destination, fsyncing it,
    then publishing it via os.replace after a lexists guard. The guard never
    overwrites an existing file; concurrent mutation during publication is
    out of scope, matching the documented no-concurrent-mutation contract.
    Other link errors propagate without fallback. On any failure, files
    created by this call, leftover copy temporaries, the assets directory
    and the output directory (when created here) are removed
    (best-effort, original error preserved) before re-raising.
    """
    require(output.parent.is_dir(), "Output parent must already exist")
    with tempfile.TemporaryDirectory(prefix=".emdb-stage-", dir=output.parent) as temp:
        staging = Path(temp)
        for name, data in files.items():
            dest = staging / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            write_file(dest, data)
        try:
            output.mkdir()  # exclusive reservation: even an empty existing dir is refused
        except FileExistsError as exc:
            raise ImportFailure("Output already exists; choose a fresh directory") from exc
        created: list[Path] = []
        pending_tmp: list[Path] = []
        assets_created = False
        try:
            if any(name.startswith("assets/") for name in files):
                (output / "assets").mkdir()
                assets_created = True
            for name in files:
                staged = staging / name
                dest = output / name
                try:
                    # Hard links are atomic and cannot replace an existing file.
                    os.link(staged, dest)
                except OSError as exc:
                    if exc.errno not in _LINK_FALLBACK_ERRNOS:
                        raise
                    fd, tmp_name = tempfile.mkstemp(prefix=".emdb-copy-", dir=output)
                    os.close(fd)
                    tmp_path = Path(tmp_name)
                    pending_tmp.append(tmp_path)
                    try:
                        shutil.copyfile(staged, tmp_path)
                        with tmp_path.open("r+b") as stream:
                            stream.flush()
                            os.fsync(stream.fileno())
                        if os.path.lexists(dest):
                            raise FileExistsError(dest)
                        os.replace(tmp_path, dest)
                    except BaseException:
                        with suppress(OSError):
                            if os.path.lexists(tmp_path):
                                tmp_path.unlink()
                        raise
                    pending_tmp.remove(tmp_path)
                created.append(dest)
        except BaseException:
            for path in reversed(created):
                with suppress(OSError):
                    path.unlink()
            for tmp_path in pending_tmp:
                with suppress(OSError):
                    if os.path.lexists(tmp_path):
                        tmp_path.unlink()
            if assets_created:
                with suppress(OSError):
                    (output / "assets").rmdir()
            with suppress(OSError):
                output.rmdir()
            raise


def run(
    source: Path | str,
    output: Path | str,
    *,
    write: bool = False,
    cache_file: Path | str | None = None,
    enrich: bool = False,
) -> dict[str, Any]:
    """Plan (and optionally publish) the import; return notes and report."""
    source_raw, output_raw = Path(source), Path(output)
    require(not os.path.lexists(output_raw), "Output already exists; choose a fresh directory")
    source, output = source_raw.resolve(), output_raw.resolve()
    require(output.parent.is_dir(), "Output parent must already exist")
    require(not output.is_relative_to(source), "Output cannot be inside source")
    require(not enrich or write, "Enrichment requires --write; dry-run is always network-free")
    records, hashes, warnings = parse_source(source)
    cache: dict[str, Any] = {}
    if cache_file:
        loaded, checksum = read_json(cache_file)
        require(isinstance(loaded, dict), "Metadata cache must be an object")
        # Copy so enrichment writes never alias or mutate the caller's input mapping.
        cache = dict(loaded)
        hashes["metadata-input"] = checksum
    names = set()
    planned = []
    duplicates: dict[str, list[int]] = defaultdict(list)
    # Structural preflight precedes any enrichment or filesystem writes.
    for record in records:
        with record_context(record["source_record"]):
            stem = record["title"] + (f" ({record['year']})" if record["year"] else "")
            safe_name(stem)
            name = stem + ".md"
            folded = unicodedata.normalize("NFC", name).casefold()
            require(folded not in names, "Case-insensitive note filename collision")
            names.add(folded)
            tv_path = source / "TVSeries" / record["cover_id"] / (record["cover_id"] + ".dat")
            tv = None
            if tv_path.exists():
                tv, hashes[tv_path.relative_to(source).as_posix()] = parse_tv(tv_path)
            if record["imdb_id"]:
                duplicates[record["imdb_id"]].append(record["source_record"])
            planned.append((record, name, tv))
    files, notes = {}, {}
    used_cache = {}
    for record, name, tv in planned:
        with record_context(record["source_record"]):
            meta = metadata(record["imdb_id"], cache, enrich)
            if meta:
                used_cache[record["imdb_id"]] = cache[record["imdb_id"]]
            resolved = resolve(record, meta, tv)
            cover = source / "Covers" / (record["cover_id"] + ".jpg")
            if cover.exists():
                raw = cover.read_bytes()
                require(
                    raw.startswith(b"\xff\xd8\xff") and raw.endswith(b"\xff\xd9"),
                    "Invalid JPEG signature (artwork is copied, not decoded)",
                )
                poster = f"assets/record-{record['source_record']:06d}.jpg"
                files[poster] = raw
                hashes[cover.relative_to(source).as_posix()] = digest(raw)
                resolved["poster"] = poster
            else:
                warnings.append(f"Record {record['source_record']}: no local poster")
            notes[name] = build_note(resolved)
            files[name] = notes[name].encode("utf-8")
    snapshot = (
        json.dumps(used_cache, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
    files["metadata_snapshot.json"] = snapshot
    report = dict(
        schema_version=1,
        source_version="78",
        records=len(records),
        duplicate_imdb_ids={k: v for k, v in duplicates.items() if len(v) > 1},
        warnings=warnings,
        source_sha256=hashes,
        output_sha256={name: digest(raw) for name, raw in sorted(files.items())},
        network="OMDb metadata only" if enrich else "none",
    )
    files["migration_report.json"] = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode()
    if write:
        publish(output, files)
    return dict(notes=notes, report=report)
