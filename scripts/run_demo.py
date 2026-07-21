from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(command: list[str], cwd: Path) -> None:
    print(f"\n$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=cwd, check=True, timeout=60)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    source = repository / "examples" / "demo-workspace"
    with tempfile.TemporaryDirectory(prefix="kinekt-demo-") as temp_dir:
        workspace = Path(temp_dir) / "checkout-service"
        shutil.copytree(source, workspace)
        cli = [sys.executable, "-m", "kinekt.cli"]
        _run([*cli, "init", str(workspace)], repository)
        _run([*cli, "ingest", str(workspace)], repository)
        _run(
            [
                *cli,
                "query",
                "How are duplicate charges prevented during retries?",
                "--workspace",
                str(workspace),
                "--limit",
                "3",
                "--explain",
            ],
            repository,
        )
        _run([*cli, "index-status", str(workspace)], repository)
    print("\nDemo completed in disposable storage.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
