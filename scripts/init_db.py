from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "services" / "knowledge-service"
if str(SERVICE_PATH) not in sys.path:
    sys.path.insert(0, str(SERVICE_PATH))

from daypilot_knowledge.db import Base, create_engine_from_settings  # noqa: E402


def main() -> int:
    engine = create_engine_from_settings()
    Base.metadata.create_all(engine)
    print(f"Initialized DayPilot database at {engine.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
