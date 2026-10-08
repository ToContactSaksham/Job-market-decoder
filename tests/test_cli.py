import subprocess
import sys


def test_cli_help_lists_commands():
    out = subprocess.run([sys.executable, "-m", "jmd", "--help"], capture_output=True, text=True, check=True).stdout
    for cmd in ("scrape", "synth", "build", "analyze", "recommend", "discover", "all"):
        assert cmd in out
