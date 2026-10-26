import subprocess
import sys

import pytest

from scripts import smoke_wheel


def test_failed_smoke_command_exposes_stderr(tmp_path, monkeypatch, capfd):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "synthetic.whl").touch()
    monkeypatch.setattr(smoke_wheel, "__file__", str(tmp_path / "scripts/smoke_wheel.py"))
    original_run = subprocess.run

    def fail_command(args, **kwargs):
        return original_run(
            [
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('synthetic failure\\n'); sys.exit(7)",
            ],
            **kwargs,
        )

    monkeypatch.setattr(smoke_wheel.subprocess, "run", fail_command)
    with pytest.raises(subprocess.CalledProcessError) as error:
        smoke_wheel.main()
    assert error.value.returncode == 7
    assert "synthetic failure" in capfd.readouterr().err
