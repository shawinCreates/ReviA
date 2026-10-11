#!/usr/bin/env python

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent


def main() -> None:
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError(
            "Django is not importable. Run commands with `uv run` so the project "
            "virtual environment is on the path."
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == "__main__":
    main()
