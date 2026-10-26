import json

import pytest
from test_importer import source

import emdb_obsidian.importer as app


@pytest.mark.parametrize(
    "entry",
    [
        {"Response": "False", "Error": "Invented failure"},
        {"Response": "True", "imdbID": "tt9999999"},
    ],
)
def test_reject_failed_or_mismatched_cache(tmp_path, entry):
    src = source(tmp_path)
    cache = tmp_path / "cache.json"
    cache.write_text(json.dumps({"tt1234567": entry}))
    with pytest.raises(app.ImportFailure):
        app.run(src, tmp_path / "out", cache_file=cache, write=True)
    assert not (tmp_path / "out").exists()
