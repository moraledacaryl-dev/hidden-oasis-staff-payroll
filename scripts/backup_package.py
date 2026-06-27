from __future__ import annotations

import json

from core.backups import create_backup_package


if __name__ == "__main__":
    result = create_backup_package()
    print(json.dumps(result, indent=2, sort_keys=True))
