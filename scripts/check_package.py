from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_executable(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def _remove_generated_dir(repo_root: Path, path: Path) -> None:
    if not path.exists():
        return
    resolved_root = repo_root.resolve()
    resolved_path = path.resolve()
    if resolved_path == resolved_root or resolved_root not in resolved_path.parents:
        raise RuntimeError(f"Refusing to remove path outside repository: {resolved_path}")
    shutil.rmtree(resolved_path)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    work_dir = Path(tempfile.gettempdir()) / "kinekt-package-check"
    dist_dir = work_dir / "dist"
    venv_dir = work_dir / "venv"

    if work_dir.exists():
        shutil.rmtree(work_dir)
    dist_dir.mkdir(parents=True)

    try:
        _run([sys.executable, "-m", "build", "--sdist", "--wheel", "--outdir", str(dist_dir)], repo_root)
        artifacts = sorted(dist_dir.glob("kinekt-*"))
        if not artifacts:
            raise RuntimeError("Package build produced no artifacts")

        _run([sys.executable, "-m", "twine", "check", *[str(path) for path in artifacts]], repo_root)
        _run([sys.executable, "-m", "venv", str(venv_dir)], repo_root)

        venv_python = _venv_python(venv_dir)
        wheels = sorted(dist_dir.glob("*.whl"))
        if not wheels:
            raise RuntimeError("Package build produced no wheel")

        _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], repo_root)
        _run([str(venv_python), "-m", "pip", "install", str(wheels[0])], repo_root)
        _run([str(_venv_executable(venv_dir, "kinekt")), "--help"], repo_root)
        print("Package check passed", flush=True)
        return 0
    finally:
        _remove_generated_dir(repo_root, repo_root / "build")
        _remove_generated_dir(repo_root, repo_root / "src" / "kinekt.egg-info")


if __name__ == "__main__":
    raise SystemExit(main())
