from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=cwd, text=True)
    if result.returncode != 0:
        print(f"Command failed with exit code {result.returncode}", flush=True)
    return result


def _kinekt_cmd(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, "-m", "kinekt.cli", *args], cwd=cwd)


def _is_git_repo(workspace: Path) -> bool:
    return (workspace / ".git").exists()


def _gitignore_mentions_kinekt(workspace: Path) -> bool:
    gitignore = workspace / ".gitignore"
    if not gitignore.exists():
        return False
    lines = gitignore.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
    normalized = {line.strip().rstrip("/") for line in lines if line.strip() and not line.strip().startswith("#")}
    return ".kinekt" in normalized


def _remove_kinekt_dir(workspace: Path) -> None:
    kinekt_dir = (workspace / ".kinekt").resolve()
    resolved_workspace = workspace.resolve()
    if kinekt_dir.name != ".kinekt" or kinekt_dir.parent != resolved_workspace:
        raise RuntimeError(f"Refusing to remove unexpected path: {kinekt_dir}")
    if kinekt_dir.exists():
        shutil.rmtree(kinekt_dir)
        print(f"Removed {kinekt_dir}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Kinekt against another local workspace.")
    parser.add_argument("workspace", help="Path to the target project or workspace.")
    parser.add_argument(
        "--query",
        default="what does this project do?",
        help="Query to run after ingesting the workspace.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Query result limit.")
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove the generated .kinekt directory after the smoke test.",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.exists() or not workspace.is_dir():
        print(f"Workspace does not exist or is not a directory: {workspace}", flush=True)
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    env_pythonpath = os.environ.get("PYTHONPATH")
    src_path = str(repo_root / "src")
    os.environ["PYTHONPATH"] = src_path if not env_pythonpath else f"{src_path}{os.pathsep}{env_pythonpath}"

    print(f"Testing workspace: {workspace}", flush=True)
    if _is_git_repo(workspace) and not _gitignore_mentions_kinekt(workspace):
        print("Warning: target repo .gitignore does not mention .kinekt/", flush=True)

    commands = [
        ["doctor", str(workspace)],
        ["init", str(workspace)],
        ["ingest", str(workspace)],
        ["query", args.query, "--workspace", str(workspace), "--limit", str(args.limit)],
    ]
    if _is_git_repo(workspace):
        commands.append(["git-context", str(workspace)])

    exit_code = 0
    for command in commands:
        result = _kinekt_cmd(command, cwd=repo_root)
        if result.returncode != 0:
            exit_code = result.returncode
            break

    print(f"Kinekt index location: {workspace / '.kinekt'}", flush=True)
    if args.cleanup:
        _remove_kinekt_dir(workspace)

    if exit_code != 0:
        return exit_code

    print("Workspace smoke test passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
