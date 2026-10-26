import json
from pathlib import Path

import pytest
import yaml
from test_importer import source

import emdb_obsidian.importer as app
from examples.demo import demo


def test_synthetic_golden(tmp_path):
    demo(tmp_path / "demo")
    expected = Path(__file__).resolve().parents[1] / "examples" / "expected"
    actual = tmp_path / "demo" / "output"
    assert {p.name for p in actual.iterdir()} == {p.name for p in expected.iterdir()}
    for p in expected.iterdir():
        assert (actual / p.name).read_bytes() == p.read_bytes()


def test_yaml_arbitrary_strings():
    record = dict(
        title='yes: [a, b] # "quote"\nnext',
        aliases=["null", "2020-01-01"],
        plot="",
        review="Invented",
        genres=["a, b", "on"],
        cover_id="1",
    )
    front = yaml.safe_load(app.build_note(record).split("---")[1])
    assert front["title"] == record["title"]
    assert front["aliases"] == record["aliases"]
    assert front["genres"] == record["genres"]


def test_offline_poster_and_cache_unchanged(tmp_path, monkeypatch):
    src = source(tmp_path)
    cache = tmp_path / "metadata.json"
    raw = json.dumps({"tt1234567": {"Poster": "https://example.invalid/poster.jpg"}})
    cache.write_text(raw)
    monkeypatch.setattr(app, "urlopen", lambda *a, **k: pytest.fail("network forbidden"))
    app.run(src, tmp_path / "out", cache_file=cache, write=True)
    assert cache.read_text() == raw
    assert not (tmp_path / "out" / "assets").exists()


def test_publish_failure_cleanup(tmp_path, monkeypatch):
    src = source(tmp_path)
    original = app.os.link
    calls = 0

    def fail_later(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk failure")
        original(*args)

    monkeypatch.setattr(app.os, "link", fail_later)
    with pytest.raises(OSError):
        app.run(src, tmp_path / "out", write=True)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source"]


def test_destination_race_no_overwrite(tmp_path, monkeypatch):
    src = source(tmp_path)
    output = tmp_path / "out"
    original = app.write_file

    def race(path, data):
        if not output.exists():
            output.mkdir()
            (output / "keep").write_text("untouched")
        original(path, data)

    monkeypatch.setattr(app, "write_file", race)
    with pytest.raises(app.ImportFailure) as excinfo:
        app.run(src, output, write=True)
    assert isinstance(excinfo.value.__cause__, FileExistsError)
    assert (output / "keep").read_text() == "untouched"


def test_enrichment_errors_redacted(tmp_path, monkeypatch):
    src = source(tmp_path)
    monkeypatch.setenv("OMDB_API_KEY", "test-secret-not-real")

    def fail(*args, **kwargs):
        raise OSError("https://example.invalid/?apikey=test-secret-not-real")

    monkeypatch.setattr(app, "urlopen", fail)
    with pytest.raises(app.ImportFailure) as error:
        app.run(src, tmp_path / "out", write=True, enrich=True)
    assert "test-secret" not in str(error.value)
    assert not (tmp_path / "out").exists()


def test_dry_enrich_refused(tmp_path, monkeypatch):
    src = source(tmp_path)
    monkeypatch.setattr(app, "urlopen", lambda *a, **k: pytest.fail("network"))
    with pytest.raises(app.ImportFailure, match="dry-run"):
        app.run(src, tmp_path / "out", enrich=True)


@pytest.mark.parametrize(
    "field,value", [("version", "79"), ("movies", {}), ("custom-genres", {"0": "Wrong"})]
)
def test_unsupported_source(tmp_path, field, value):
    src = source(tmp_path)
    path = src / "emdb.dat"
    data = json.loads(path.read_text(encoding="utf-16"))
    data[field] = value
    path.write_text(json.dumps(data), encoding="utf-16")
    with pytest.raises(app.ImportFailure):
        app.run(src, tmp_path / "out", write=True)
    assert not (tmp_path / "out").exists()
