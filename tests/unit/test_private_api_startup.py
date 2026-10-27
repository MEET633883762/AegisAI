"""The API must explain an unsupported interpreter before importing app dependencies."""

from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_private_api.py"


def test_old_python_gets_actionable_error_before_dependency_imports(tmp_path):
    # Disable site-packages as well: this check must work without any app dependencies.
    result = subprocess.run(
        [sys.executable, "-S", "-c",
         "import runpy, sys; sys.version_info = (3, 10, 0); "
         "runpy.run_path(sys.argv[1], run_name='__main__')", str(SCRIPT)],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 2
    assert "requires Python 3.11 or newer (running 3.10)" in result.stderr
    assert "py -3.11 scripts/run_private_api.py" in result.stderr
    assert "docs/DEVELOPMENT.md" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


def test_supported_python_can_load_api_help_from_another_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    assert "Run the loopback local synthetic API." in result.stdout
    assert "--database" in result.stdout
    assert "Traceback" not in result.stderr
