"""Every outside package the server imports is listed in server/requirements.txt, so the Docker image has it."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
# The name a package is imported by, where it differs from the name it is installed by.
INSTALLED_AS = {"jwt": "pyjwt", "argon2": "argon2-cffi", "psycopg_pool": "psycopg", "email_validator": "email-validator",
                "pydantic": "fastapi"}                     # (pydantic comes with fastapi)
OWN = {"server", "simulation", "database", "tests"}


def test_every_imported_package_is_in_the_requirements():
    listed = {line.split(">")[0].split("=")[0].split("[")[0].strip().lower()
              for line in (ROOT / "server" / "requirements.txt").read_text().splitlines() if line.strip() and not line.startswith("#")}
    missing = set()
    for folder in ("server", "simulation", "database"):
        for path in (ROOT / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                        [node.module] if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 else []
                for name in names:
                    top = name.split(".")[0]
                    if top in OWN or top in sys.stdlib_module_names:
                        continue
                    if INSTALLED_AS.get(top, top).lower() not in listed:
                        missing.add(f"{top} ({path.relative_to(ROOT)})")
    assert not missing, f"Add these to server/requirements.txt: {sorted(missing)}"
