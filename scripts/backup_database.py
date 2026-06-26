from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.backups import create_backup


if __name__ == "__main__":
    print(json.dumps(create_backup(), indent=2))
