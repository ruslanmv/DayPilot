#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "mcp-host"))

from daypilot_mcp_host.homepilot_bridge import install_hpersona, preview_hpersona_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview or install a HomePilot .hpersona package into DayPilot.")
    parser.add_argument("path", help="Path to .hpersona package")
    parser.add_argument("--preview", action="store_true", help="Preview only")
    parser.add_argument("--install", action="store_true", help="Install into local_data/installed_personas in disabled state")
    args = parser.parse_args()

    if not args.preview and not args.install:
        args.preview = True

    if args.install:
        result = install_hpersona(args.path, ROOT / "local_data" / "installed_personas")
    else:
        result = preview_hpersona_file(args.path)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
