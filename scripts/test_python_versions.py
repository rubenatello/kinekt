from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SUPPORTED_VERSIONS = ("3.11", "3.12", "3.13", "3.14")


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(cmd, cwd=cwd, env=env, text=True)


def _candidate_commands(version: str) -> list[list[str]]:
    current = f"{sys.version_info.major}.{sys.version_info.minor}"
    commands: list[list[str]] = []
    if current == version:
        commands.append([sys.executable])
    if os.name == "nt":
        commands.append(["py", f"-{version}"])
    commands.append([f"python{version}"])
    commands.append([f"python{version.replace('.', '')}"])
    commands.append(["python"])
    return commands


def _find_python(version: str) -> list[str] | None:
    probe = "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    seen: set[tuple[str, ...]] = set()
    for cmd in _candidate_commands(version):
        key = tuple(cmd)
        if key in seen:
            continue
        seen.add(key)
        try:
            result = subprocess.run(
                [*cmd, "-c", probe],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            continue
        if result.returncode == 0 and result.stdout.strip() == version:
            return cmd
    return None


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


def _clean_repo_generated_outputs(repo_root: Path) -> None:
    _remove_generated_dir(repo_root, repo_root / "build")
    _remove_generated_dir(repo_root, repo_root / "src" / "kinekt.egg-info")


def _test_version(repo_root: Path, version: str, work_dir: Path, reuse_envs: bool) -> bool | None:
    python_cmd = _find_python(version)
    if python_cmd is None:
        print(f"SKIP Python {version}: interpreter not found", flush=True)
        return None

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    venv_dir = work_dir / f"py{version.replace('.', '')}"
    if venv_dir.exists() and not reuse_envs:
        shutil.rmtree(venv_dir)
    if not venv_dir.exists():
        create = _run([*python_cmd, "-m", "venv", str(venv_dir)], cwd=repo_root, env=env)
        if create.returncode != 0:
            print(f"FAIL Python {version}: could not create virtual environment", flush=True)
            return False

    venv_python = _venv_python(venv_dir)
    commands = [
        [str(venv_python), "-m", "pip", "install", "-q", "--upgrade", "pip"],
        [str(venv_python), "-m", "pip", "install", "-q", ".[dev]"],
        [str(venv_python), "-m", "pytest", "-q"],
        [str(_venv_executable(venv_dir, "kinekt")), "--help"],
    ]
    try:
        for cmd in commands:
            result = _run(cmd, cwd=repo_root, env=env)
            if result.returncode != 0:
                print(f"FAIL Python {version}", flush=True)
                return False

        print(f"PASS Python {version}", flush=True)
        return True
    finally:
        _clean_repo_generated_outputs(repo_root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Kinekt tests across installed Python versions.")
    parser.add_argument(
        "--versions",
        nargs="+",
        default=list(SUPPORTED_VERSIONS),
        help="Python versions to test. Defaults to the supported range.",
    )
    parser.add_argument(
        "--work-dir",
        default=str(Path(tempfile.gettempdir()) / "kinekt-python-version-tests"),
        help="Directory for temporary virtual environments.",
    )
    parser.add_argument(
        "--reuse-envs",
        action="store_true",
        help="Reuse existing virtual environments instead of recreating them.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    passed = 0
    failed = 0
    skipped = 0
    for version in args.versions:
        result = _test_version(repo_root, version, work_dir, args.reuse_envs)
        if result is True:
            passed += 1
        elif result is False:
            failed += 1
        else:
            skipped += 1

    print(f"Summary: passed={passed} failed={failed} skipped={skipped}", flush=True)
    if failed:
        return 1
    if passed == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
