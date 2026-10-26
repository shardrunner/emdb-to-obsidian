import hashlib

import pytest

from emdb_obsidian.importer import ImportFailure, parse_tv, resolve

HEADER = ["[Version06]", "Invented", "2020-2021", "Plot", "24", "0", "0"]


def episode(number="01", flag="Y|20210304"):
    return [f"[Episode{number}]", "Name", "Plot", "0", flag, "0"]


def tree(tmp_path, body, header=None):
    path = tmp_path / "synthetic.dat"
    path.write_text(
        "\n".join((HEADER if header is None else header) + body) + "\n", encoding="utf-16"
    )
    return path


@pytest.mark.parametrize(
    "marker", ["", "Episode01", "[Episode]", "[Episode1x]", "[Episode01]extra"]
)
def test_missing_or_malformed_marker(tmp_path, marker):
    block = episode()
    block[0] = marker
    path = tree(tmp_path, ["[Season0001]", *block])
    with pytest.raises(ImportFailure, match="Expected season or episode marker") as error:
        parse_tv(path)
    assert f"{path}:9:" in str(error.value)


@pytest.mark.parametrize("extra", ["garbage", "", "[Unknown]", "[Season1]extra"])
@pytest.mark.parametrize("trailing", [False, True])
def test_unexpected_boundary_data(tmp_path, extra, trailing):
    body = ["[Season0001]", *episode(), extra]
    if not trailing:
        body += episode("02")
    path = tree(tmp_path, body)
    with pytest.raises(ImportFailure, match="Expected season or episode marker") as error:
        parse_tv(path)
    assert f"{path}:15:" in str(error.value)


@pytest.mark.parametrize("length", range(1, 6))
def test_truncated_block(tmp_path, length):
    path = tree(tmp_path, ["[Season0001]", *episode()[:length]])
    with pytest.raises(ImportFailure, match="Incomplete episode block") as error:
        parse_tv(path)
    assert f"{path}:9:" in str(error.value)


def test_episode_requires_season(tmp_path):
    path = tree(tmp_path, episode())
    with pytest.raises(ImportFailure, match="Episode before season"):
        parse_tv(path)


@pytest.mark.parametrize("content", ["[Title] text", "[Season0099]", "[Episode99]", "[Unknown]"])
def test_bracket_prefixed_content_is_not_structure(tmp_path, content):
    block = episode()
    block[1:4] = [content] * 3
    block[5] = content
    path = tree(tmp_path, ["[Season0001]", *block, *episode("02", "Y|")])
    summary, checksum = parse_tv(path)
    assert summary["episodes_total"] == summary["episodes_watched"] == 2
    assert summary["last_episode"] == "S01E02"
    assert checksum == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("repeat_season", [False, True])
def test_duplicate_episode_keys(tmp_path, repeat_season):
    body = ["[Season0001]", *episode()]
    if repeat_season:
        body += ["[Season1]"]
    path = tree(tmp_path, body + episode("1"))
    with pytest.raises(ImportFailure, match="Duplicate episode number") as error:
        parse_tv(path)
    assert str(path) in str(error.value)


@pytest.mark.parametrize(
    "flag", ["Y", "y|", "X|", "Y|2021011", "Y|20210101extra", "Y|２０２１０１０１", "[Season0002]"]
)
def test_bad_flags(tmp_path, flag):
    path = tree(tmp_path, ["[Season0001]", *episode(flag=flag)])
    with pytest.raises(ImportFailure, match="Invalid episode watched flag") as error:
        parse_tv(path)
    assert f"{path}:13:" in str(error.value)


@pytest.mark.parametrize("flag", ["Y|20210229", "N|20211301"])
def test_invalid_calendar_dates_even_when_unwatched(tmp_path, flag):
    path = tree(tmp_path, ["[Season0001]", *episode(flag=flag)])
    with pytest.raises(ImportFailure, match="Invalid calendar date") as error:
        parse_tv(path)
    assert f"{path}:13:" in str(error.value)


@pytest.mark.parametrize("slot,value", [(2, "２０２０-2021"), (4, "２４"), (4, "²"), (4, "0")])
def test_header_numeric_fields(tmp_path, slot, value):
    header = HEADER.copy()
    header[slot] = value
    path = tree(tmp_path, [], header)
    with pytest.raises(ImportFailure) as error:
        parse_tv(path)
    assert f"{path}:{slot + 1}:" in str(error.value)


@pytest.mark.parametrize("body", [["[Season１]"], ["[Season1]", *episode("１")]])
def test_markers_require_ascii_digits(tmp_path, body):
    with pytest.raises(ImportFailure, match="Expected season or episode marker"):
        parse_tv(tree(tmp_path, body))


def test_section_cannot_replace_flag_in_short_block(tmp_path):
    body = ["[Season0001]", *episode()[:4], "[Season0002]", *episode("02")]
    with pytest.raises(ImportFailure, match="Invalid episode watched flag"):
        parse_tv(tree(tmp_path, body))


@pytest.mark.parametrize(
    "flags,watched,last,latest,status",
    [
        (["N|", "Y|20210304", "Y|20200101", "N|20990101"], 2, "S02E03", "2021-03-04", "partial"),
        (["Y|", "Y|", "Y|", "Y|"], 4, "S02E03", None, "watched"),
        (["N|", "N|", "N|", "N|"], 0, None, None, "to-watch"),
        (["Y|20220101", "N|", "N|", "N|"], 1, "S00E01", "2022-01-01", "partial"),
    ],
)
def test_specials_and_progress(tmp_path, flags, watched, last, latest, status):
    body = [
        "[Season0000]",
        *episode(flag=flags[0]),
        "[Season0002]",
        *episode("01", flags[1]),
        *episode("03", flags[2]),
        "[Season0001]",
        *episode("01", flags[3]),
    ]
    summary, _ = parse_tv(tree(tmp_path, body))
    assert summary == dict(
        runtime=24,
        year_end=2021,
        episodes_total=4,
        episodes_watched=watched,
        last_episode=last,
        latest_mark=latest,
    )
    resolved = resolve(dict(my_rating=8, watched_date="2019-01-01"), {}, summary)
    assert resolved["status"] == status
    assert resolved["watched_date"] == (latest or "2019-01-01")


def test_empty_tree_preserves_no_progress(tmp_path):
    summary, _ = parse_tv(tree(tmp_path, []))
    assert summary["episodes_total"] == summary["episodes_watched"] == 0
    assert summary["last_episode"] is summary["latest_mark"] is None
