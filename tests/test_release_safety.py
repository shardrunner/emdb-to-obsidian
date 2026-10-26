import hashlib
import io
import json
import traceback
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml
from test_importer import source

import emdb_obsidian.importer as app
from emdb_obsidian.cli import main


def test_enrichment_snapshot_hashes_artwork_and_replay(tmp_path, monkeypatch):
    src = source(tmp_path)
    covers = src / "Covers"
    covers.mkdir()
    artwork = [b"\xff\xd8\xffinvented-one\xff\xd9", b"\xff\xd8\xffinvented-two\xff\xd9"]
    for index, raw in enumerate(artwork, 1):
        (covers / f"{index:06d}.jpg").write_bytes(raw)
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"tt9999999": {"Title": "Unused synthetic title"}}))
    original = cache.read_bytes()
    entry = {
        "Response": "True",
        "imdbID": "tt1234567",
        "Title": "Enriched synthetic title",
        "Year": "2021",
        "Runtime": "91 min",
        "Plot": "Invented enriched plot",
    }
    monkeypatch.setenv("OMDB_API_KEY", "synthetic-test-token")
    calls = []

    def fetch(request, *, timeout):
        url = urlsplit(request.full_url)
        assert (url.scheme, url.netloc, url.path) == ("https", "www.omdbapi.com", "/")
        query = parse_qs(url.query)
        assert query["i"] == ["tt1234567"]
        assert query["plot"] == ["full"]
        # Avoid including the credential in assertion diagnostics.
        if query.get("apikey") != ["synthetic-test-token"]:
            pytest.fail("Unexpected credential parameter")
        assert timeout == 15
        assert dict(request.header_items()) == {
            "User-agent": app.USER_AGENT,
            "Accept": "application/json",
        }
        calls.append(1)
        return io.BytesIO(json.dumps(entry).encode())

    monkeypatch.setattr(app, "urlopen", fetch)
    out = tmp_path / "out"
    plan = app.run(src, out, cache_file=cache, enrich=True, write=True)
    assert calls == [1]
    assert cache.read_bytes() == original
    snapshot = out / "metadata_snapshot.json"
    assert json.loads(snapshot.read_bytes()) == {"tt1234567": entry}
    report = json.loads((out / "migration_report.json").read_bytes())
    assert report == plan["report"]
    assert report["output_sha256"] == {
        p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in out.rglob("*")
        if p.is_file() and p.name != "migration_report.json"
    }
    assert report["source_sha256"] == {
        **{
            p.relative_to(src).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in src.rglob("*")
            if p.is_file()
        },
        "metadata-input": hashlib.sha256(original).hexdigest(),
    }
    for index, text in enumerate(plan["notes"].values(), 1):
        front = yaml.safe_load(text.split("---")[1])
        assert front["year"] == 2021
        assert front["runtime"] == 91
        assert front["aliases"] == [entry["Title"]]
        assert entry["Plot"] in text
        assert front["poster"] == f"assets/record-{index:06d}.jpg"
        assert (out / front["poster"]).read_bytes() == artwork[index - 1]
    monkeypatch.setattr(app, "urlopen", lambda *a, **k: pytest.fail("offline network"))
    replay = tmp_path / "replay"
    assert app.run(src, replay, cache_file=snapshot, write=True)["notes"] == plan["notes"]
    for name in plan["notes"]:
        assert (replay / name).read_bytes() == (out / name).read_bytes()


@pytest.mark.parametrize("failure", ["provider", "missing-key", "json"])
def test_enrichment_failures_no_output_or_credentials(tmp_path, monkeypatch, capsys, failure):
    src = source(tmp_path)
    secret = "synthetic-sensitive-token"
    monkeypatch.setenv("OMDB_API_KEY", secret)
    if failure == "missing-key":
        monkeypatch.delenv("OMDB_API_KEY")

    def fetch(*args, **kwargs):
        if failure == "missing-key":
            pytest.fail("Network without key")
        raw = (
            json.dumps({"Response": "False", "Error": secret}) if failure == "provider" else secret
        )
        return io.BytesIO(raw.encode())

    monkeypatch.setattr(app, "urlopen", fetch)
    with pytest.raises(SystemExit) as caught:
        main(["--emdb-dir", str(src), "--output", str(tmp_path / "out"), "--write", "--enrich"])
    assert caught.value.code == 1
    captured = capsys.readouterr()
    assert "Import failed:" in captured.err
    assert secret not in captured.out + captured.err + "".join(
        traceback.format_exception(caught.value)
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source"]


@pytest.mark.parametrize("kind", ["file", "dangling", "inside", "symlink-inside"])
@pytest.mark.parametrize("write", [False, True])
def test_output_restrictions(tmp_path, kind, write):
    src = source(tmp_path)
    out = tmp_path / "out"
    if kind == "file":
        out.write_bytes(b"keep")
    elif kind in {"dangling", "symlink-inside"}:
        try:
            out.symlink_to(
                tmp_path / "missing" if kind == "dangling" else src, target_is_directory=True
            )
        except OSError:
            pytest.skip("symlink creation unavailable")
        if kind == "symlink-inside":
            out = out / "new"
    else:
        out = src / "new"
    before = sorted(tmp_path.rglob("*"))
    with pytest.raises(app.ImportFailure, match="exists|inside source"):
        app.run(src, out, write=write)
    assert sorted(tmp_path.rglob("*")) == before
    if kind == "file":
        assert out.read_bytes() == b"keep"
    if kind == "dangling":
        assert out.is_symlink()


@pytest.mark.parametrize("bad", [None, "²", "١"])
def test_cli_success_and_numeric_validation(tmp_path, capsys, monkeypatch, bad):
    src = source(tmp_path)
    monkeypatch.setattr(app, "urlopen", lambda *a, **k: pytest.fail("network"))
    out = tmp_path / "out"
    args = ["--emdb-dir", str(src), "--output", str(out), "--offline"]
    if bad is not None:
        path = src / "emdb.dat"
        data = json.loads(path.read_text(encoding="utf-16"))
        parts = data["movies"][0]["year"].split(app.SEP)
        parts[14] = bad
        data["movies"][0]["year"] = app.SEP.join(parts)
        path.write_text(json.dumps(data), encoding="utf-16")
        with pytest.raises(SystemExit) as caught:
            main(args + ["--write"])
        assert caught.value.code == 1
        captured = capsys.readouterr()
        assert captured.err == "Import failed: Record 1: Invalid cover/tree ID\n"
        assert not captured.out
        assert not out.exists()
    else:
        main(args)
        assert capsys.readouterr().out.startswith("Planned 2 notes;")
        assert not out.exists()
        main(args + ["--write"])
        assert capsys.readouterr().out.startswith("Published 2 notes;")
        assert len(list(out.glob("*.md"))) == 2
