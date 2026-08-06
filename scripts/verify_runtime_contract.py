from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"Runtime contract failed: {message}")


def read_text(path: Path) -> str:
    if not path.is_file():
        fail(f"missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8").strip()


def main() -> None:
    python_version = read_text(ROOT / ".python-version")
    node_version = read_text(ROOT / ".nvmrc")

    if not re.fullmatch(r"3\.12(?:\.\d+)?", python_version):
        fail(f"unsupported Python version {python_version!r}; expected Python 3.12")
    if not re.fullmatch(r"22(?:\.\d+(?:\.\d+)?)?", node_version):
        fail(f"unsupported Node version {node_version!r}; expected Node 22")

    requirements = [
        line.strip()
        for line in read_text(ROOT / "requirements-api.txt").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    unpinned_python = [line for line in requirements if "==" not in line]
    if unpinned_python:
        fail(f"Python requirements must be exact pins: {unpinned_python}")

    package_path = ROOT / "apps" / "web" / "package.json"
    lock_path = ROOT / "apps" / "web" / "package-lock.json"
    package = json.loads(read_text(package_path))
    lock = json.loads(read_text(lock_path))

    if int(lock.get("lockfileVersion") or 0) != 3:
        fail("apps/web/package-lock.json must use lockfileVersion 3")

    root_lock = (lock.get("packages") or {}).get("") or {}
    for section in ("dependencies", "devDependencies"):
        declared = package.get(section) or {}
        locked_declared = root_lock.get(section) or {}
        if declared != locked_declared:
            fail(f"apps/web/package.json and package-lock.json differ in {section}")

    print(f"OK Python runtime contract: {python_version}")
    print(f"OK Node runtime contract: {node_version}")
    print(f"OK exact Python direct pins: {len(requirements)}")
    print("OK frontend manifest and lockfile are synchronized")


if __name__ == "__main__":
    main()
