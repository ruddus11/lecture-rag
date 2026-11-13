"""훅은 실제 Git index와 이력을 검사하고 키 값을 출력하지 않아야 한다."""

import subprocess
import sys

from tests.conftest import REPO


def test_secret_scan_staged_and_deleted_history(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    def scan(*args):
        return subprocess.run(
            [sys.executable, str(REPO / "scripts/check_secrets.py"), *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

    git("init")
    path = tmp_path / "credentials.txt"
    path.write_text("safe placeholder")
    git("add", ".")
    assert scan().returncode == 0
    secret = "sk-" + "syntheticForScannerOnly0123456789"
    path.write_text(secret)
    git("add", ".")
    result = scan()
    assert result.returncode == 1
    assert secret not in result.stdout + result.stderr
    git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "fixture")
    path.unlink()
    git("add", "-u")
    assert scan().returncode == 0
    assert scan("--history").returncode == 1
