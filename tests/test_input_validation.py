import json

import pytest
from test_importer import source

import emdb_obsidian.importer as app


@pytest.mark.parametrize("prefix", ["COM", "LPT"])
@pytest.mark.parametrize("digit", ["¹", "²", "³"])
@pytest.mark.parametrize("extension", ["", ".txt"])
def test_superscript_device_names(prefix, digit, extension):
    with pytest.raises(app.ImportFailure, match="Reserved filename"):
        app.safe_name(prefix.lower() + digit + extension)


@pytest.mark.parametrize(
    "field,slot,value",
    [
        ("year", 14, "²"),
        ("year", 14, "١"),
        ("year", 0, "２０２０"),
        ("genres", 1, "١٢٣"),
        ("genres", 2, "２０２００１０２"),
        ("genres", 8, "20200231"),
        ("rating", 0, "ff"),
        ("title", 0, "CON"),
        ("comments", None, 42),
        ("plot", None, []),
        ("custom-fields", None, False),
        ("title", None, "bad layout"),
    ],
)
def test_record_validation_context(tmp_path, field, slot, value):
    src = source(tmp_path)
    path = src / "emdb.dat"
    data = json.loads(path.read_text(encoding="utf-16"))
    movie = data["movies"][1]
    if slot is not None:
        parts = movie[field].split(app.SEP)
        parts[slot] = value
        value = app.SEP.join(parts)
    movie[field] = value
    path.write_text(json.dumps(data), encoding="utf-16")
    with pytest.raises(app.ImportFailure, match=r"^Record 2: (?!Record)"):
        app.run(src, tmp_path / "out", write=True)
    assert not (tmp_path / "out").exists()


def test_non_object_record_context(tmp_path):
    src = source(tmp_path)
    (src / "emdb.dat").write_text(
        json.dumps({"version": "78", "movies": [None]}), encoding="utf-16"
    )
    with pytest.raises(app.ImportFailure, match="^Record 1: Movie must be an object"):
        app.parse_source(src)


@pytest.mark.parametrize(
    "key,value", [("Year", "２０２０"), ("Runtime", "٢ min"), ("imdbRating", "８.０")]
)
def test_metadata_ascii_numbers(key, value):
    with pytest.raises(app.ImportFailure):
        app.resolve({}, {key: value}, None)


def test_custom_genre_ascii_keys(tmp_path):
    src = source(tmp_path)
    path = src / "emdb.dat"
    data = json.loads(path.read_text(encoding="utf-16"))
    data["custom-genres"] = {"１２": "Invented"}
    path.write_text(json.dumps(data), encoding="utf-16")
    with pytest.raises(app.ImportFailure, match="Invalid custom genre mapping"):
        app.parse_source(src)


def test_opaque_fields_and_unknown_genres_remain_supported(tmp_path):
    src = source(tmp_path)
    path = src / "emdb.dat"
    data = json.loads(path.read_text(encoding="utf-16"))
    movie = data["movies"][0]
    for field, slot in [("year", 1), ("genres", 3), ("rating", 2), ("title", 2)]:
        parts = movie[field].split(app.SEP)
        parts[slot] = "opaque ²１２"
        movie[field] = app.SEP.join(parts)
    parts = movie["genres"].split(app.SEP)
    parts[0] = "D²１２"
    movie["genres"] = app.SEP.join(parts)
    path.write_text(json.dumps(data), encoding="utf-16")
    records, _, warnings = app.parse_source(src)
    assert records[0]["genres"] == ["Drama"]
    assert len(warnings) == 3
    assert all(warning.startswith("Record 1: unmapped genre code") for warning in warnings)


@pytest.mark.parametrize("kind", ["tree", "artwork", "collision", "stem"])
def test_record_plan_context(tmp_path, kind):
    titles = ("Same", "same") if kind == "collision" else ("Invented", "x" * 177)
    if kind != "stem":
        titles = titles if kind == "collision" else ("Invented", "Other")
    src = source(tmp_path, titles)
    if kind == "tree":
        tree = src / "TVSeries/000002/000002.dat"
        tree.parent.mkdir(parents=True)
        tree.write_bytes(b"invalid")
    elif kind == "artwork":
        cover = src / "Covers/000002.jpg"
        cover.parent.mkdir()
        cover.write_bytes(b"invalid")
    with pytest.raises(app.ImportFailure, match="^Record 2:"):
        app.run(src, tmp_path / "out", write=True)
    assert not (tmp_path / "out").exists()
