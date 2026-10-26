import json

import pytest
import yaml

import emdb_obsidian.importer as app


def source(tmp_path, titles=("Synthetic Movie", "Synthetic Series")):
    root = tmp_path / "source"
    root.mkdir()
    movies = []
    for i, title in enumerate(titles, 1):
        year = ["2020"] + [""] * 16
        year[14] = str(i)
        genres = ["D", "1234567", "20200102"] + [""] * 8
        movies.append(
            dict(
                title="\x1e".join([title, "", "", ""]),
                year="\x1e".join(year),
                genres="\x1e".join(genres),
                rating="\x1e".join(["", "50"] + [""] * 9),
                comments="Invented review",
                plot="Invented plot",
            )
        )
    (root / "emdb.dat").write_text(
        json.dumps({"version": "78", "custom-genres": {}, "movies": movies}), encoding="utf-16"
    )
    return root


def test_existing_refused(tmp_path):
    src = source(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(app.ImportFailure, match="exists"):
        app.run(src, out, write=True)
    assert list(out.iterdir()) == []


def test_yaml_duplicates_offline_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "urlopen", lambda *a, **k: pytest.fail("network"))
    src = source(tmp_path, ("yes", "2020-01-01"))
    out = tmp_path / "out"
    before = sorted(tmp_path.rglob("*"))
    plan = app.run(src, out)
    assert sorted(tmp_path.rglob("*")) == before
    assert len(plan["notes"]) == 2
    assert plan["report"]["duplicate_imdb_ids"] == {"tt1234567": [1, 2]}
    app.run(src, out, write=True)
    notes = sorted(out.glob("*.md"))
    values = [yaml.safe_load(p.read_text().split("---")[1]) for p in notes]
    assert {v["title"] for v in values} == {"yes", "2020-01-01"}


@pytest.mark.parametrize("titles", [("Same", "same"), ("é", "e\u0301"), ("../escape",), ("CON",)])
def test_unsafe_collision_no_writes(tmp_path, titles):
    src = source(tmp_path, titles)
    with pytest.raises(app.ImportFailure):
        app.run(src, tmp_path / "out", write=True)
    assert not (tmp_path / "out").exists()


def test_malformed(tmp_path):
    src = source(tmp_path)
    p = src / "emdb.dat"
    d = json.loads(p.read_text(encoding="utf-16"))
    d["movies"][0]["genres"] = d["movies"][0]["genres"].replace("20200102", "20200231")
    p.write_text(json.dumps(d), encoding="utf-16")
    with pytest.raises(app.ImportFailure):
        app.run(src, tmp_path / "out", write=True)
    assert not (tmp_path / "out").exists()


def test_failed_write(tmp_path, monkeypatch):
    src = source(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("simulated disk failure")

    monkeypatch.setattr(app, "write_file", fail)
    with pytest.raises(OSError):
        app.run(src, tmp_path / "out", write=True)
    assert not (tmp_path / "out").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source"]


def test_tv_precedence(tmp_path):
    src = source(tmp_path, ("Synthetic Series",))
    tv = src / "TVSeries" / "000001"
    tv.mkdir(parents=True)
    (tv / "000001.dat").write_text(
        "[Version06]\nInvented\n2020-2021\nPlot\n24\n0\n0\n"
        "[Season0001]\n[Episode01]\nName\nPlot\n0\nY|20210304\n0\n"
        "[Episode02]\nName\nPlot\n0\nN|\n0\n",
        encoding="utf-16",
    )
    cache = tmp_path / "cache.json"
    cache.write_text(
        json.dumps(
            {
                "tt1234567": {
                    "Response": "True",
                    "Type": "series",
                    "Runtime": "1 min",
                    "Year": "2019",
                    "Plot": "Metadata plot",
                }
            }
        )
    )
    plan = app.run(src, tmp_path / "out", cache_file=cache)
    note = yaml.safe_load(next(iter(plan["notes"].values())).split("---")[1])
    assert note["runtime"] == 24
    assert note["year"] == 2019
    assert note["status"] == "partial"
    assert note["last_episode"] == "S01E01"
    assert note["watched_date"] == "2021-03-04"
    assert note["my_rating"] == 8.0
