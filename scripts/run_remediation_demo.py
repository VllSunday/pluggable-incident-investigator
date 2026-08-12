from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).parents[1]
    fixture = root / "demo" / "ci-python-app"
    image = "incident-investigator-remediation-demo:local"
    subprocess.run(
        [
            "docker",
            "build",
            "--file",
            str(fixture / "Dockerfile.sandbox"),
            "--tag",
            image,
            str(fixture),
        ],
        check=True,
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "docker",
            "tests/integration/test_real_docker_remediation.py",
            "-q",
            "-s",
        ],
        cwd=root,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())

