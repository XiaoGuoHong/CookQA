import subprocess
import sys


def test_main_help_exposes_cookqa_subcommands():
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        capture_output=True,
        check=False,
    )
    stdout = result.stdout.decode("utf-8", errors="ignore")

    assert result.returncode == 0
    assert "CookQA" in stdout
    assert "chat" in stdout
    assert "rebuild" in stdout
