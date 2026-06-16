"""PyInstaller launcher for the AI report server."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    package_root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()
    os.chdir(str(package_root))

    import ai_report_server

    ai_report_server.main()


if __name__ == "__main__":
    main()
