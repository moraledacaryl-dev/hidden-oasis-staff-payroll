from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.backups import create_backup_package


if __name__ == "__main__":
    result = create_backup_package()
    print(json.dumps(result, indent=2, sort_keys=True))
