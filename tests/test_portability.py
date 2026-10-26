import errno
import os
from pathlib import Path, PureWindowsPath

import pytest
from test_importer import source

import emdb_obsidian.importer as app
from examples.demo import demo


@pytest.mark.parametrize("windows", [False, True])
def test_demo_lf_bytes(tmp_path, monkeypatch, windows):
    original = Path.write_text

    def platform_write(path, data, *args, **kwargs):
        if windows and kwargs.get("newline") is None:
            data = data.replace("\n", "\r\n")
        return original(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", platform_write)
    demo(tmp_path / "demo")
    for path in (tmp_path / "demo/source").rglob("*.dat"):
        assert "\r" not in path.read_bytes().decode("utf-16")
    expected = Path(__file__).resolve().parents[1] / "examples/expected/migration_report.json"
    assert (tmp_path / "demo/output/migration_report.json").read_bytes() == expected.read_bytes()


def test_hash_paths_are_posix(tmp_path, monkeypatch):
    demo(tmp_path / "demo")
    src = tmp_path / "demo/source"
    (src / "Covers").mkdir()
    (src / "Covers/000001.jpg").write_bytes(b"\xff\xd8\xffsynthetic\xff\xd9")
    original = Path.relative_to
    monkeypatch.setattr(
        Path, "relative_to", lambda self, *args: PureWindowsPath(original(self, *args))
    )
    hashes = app.run(src, tmp_path / "out")["report"]["source_sha256"]
    assert set(hashes) == {"emdb.dat", "TVSeries/000002/000002.dat", "Covers/000001.jpg"}


FALLBACKS = sorted(
    {
        getattr(errno, name)
        for name in ("EXDEV", "EPERM", "EACCES", "ENOTSUP", "EOPNOTSUPP", "ENOSYS")
        if hasattr(errno, name)
    }
)


@pytest.mark.parametrize("code", FALLBACKS)
def test_fallback_artwork_report_last(tmp_path, monkeypatch, code):
    src = source(tmp_path)
    (src / "Covers").mkdir()
    artwork = b"\xff\xd8\xffsynthetic\xff\xd9"
    (src / "Covers/000001.jpg").write_bytes(artwork)
    out = tmp_path / "out"
    published = []
    original = os.replace

    def no_link(*args):
        raise OSError(code, "unsupported link")

    def replace(temp, dest):
        assert not (out / "migration_report.json").exists()
        original(temp, dest)
        published.append(dest.relative_to(out).as_posix())

    monkeypatch.setattr(app.os, "link", no_link)
    monkeypatch.setattr(app.os, "replace", replace)
    app.run(src, out, write=True)
    assert published[-1] == "migration_report.json"
    assert (out / "assets/record-000001.jpg").read_bytes() == artwork
    assert not list(tmp_path.rglob(".emdb-*"))


@pytest.mark.parametrize("operation", ["copy", "replace", "fsync", "link"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_publication_failure_preserves_error(tmp_path, monkeypatch, operation, cleanup_fails):
    out = tmp_path / "out"
    error = OSError(errno.EIO, "original failure")
    original_link = os.link
    original_fsync = os.fsync
    links = 0

    def link(staged, dest):
        nonlocal links
        links += 1
        if links == 1:
            return original_link(staged, dest)
        if operation == "link":
            raise error
        raise OSError(errno.EXDEV, "fallback")

    def fail(*args):
        raise error

    def fsync(fd):
        if links >= 2:
            raise error
        original_fsync(fd)

    monkeypatch.setattr(app.os, "link", link)
    if operation == "copy":
        monkeypatch.setattr(app.shutil, "copyfile", fail)
    elif operation == "replace":
        monkeypatch.setattr(app.os, "replace", fail)
    elif operation == "fsync":
        monkeypatch.setattr(app.os, "fsync", fsync)
    else:
        monkeypatch.setattr(app.shutil, "copyfile", lambda *a: pytest.fail("unexpected fallback"))
    if cleanup_fails:
        original_rmdir = Path.rmdir

        def rmdir(path):
            if path == out:
                raise OSError("cleanup failure")
            original_rmdir(path)

        monkeypatch.setattr(Path, "rmdir", rmdir)
    with pytest.raises(OSError) as caught:
        app.publish(
            out, {"assets/a.jpg": b"art", "note.md": b"note", "migration_report.json": b"{}"}
        )
    assert caught.value is error
    assert not list(tmp_path.rglob(".emdb-*"))
    assert not out.exists() or list(out.iterdir()) == []


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("dangling", [False, True])
def test_occupied_file_never_replaced(tmp_path, monkeypatch, fallback, dangling):
    out = tmp_path / "out"
    original = os.link

    def occupied(staged, dest):
        if dangling:
            try:
                dest.symlink_to(tmp_path / "missing")
            except OSError:
                pytest.skip("symlink creation unavailable")
        else:
            dest.write_bytes(b"keep")
        if fallback:
            raise OSError(errno.EXDEV, "fallback")
        original(staged, dest)

    monkeypatch.setattr(app.os, "link", occupied)
    with pytest.raises(FileExistsError):
        app.publish(out, {"note.md": b"new"})
    dest = out / "note.md"
    assert dest.is_symlink() if dangling else dest.read_bytes() == b"keep"
    assert not list(tmp_path.rglob(".emdb-*"))
