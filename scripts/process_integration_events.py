from __future__ import annotations

import argparse
import json

from api.main import configured_db_path
from core.db import get_conn
from core.integration_outbox import ensure_integration_schema, process_due_events


def main() -> int:
    parser = argparse.ArgumentParser(description="Deliver due Staff/Payroll integration events.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()

    conn = get_conn(configured_db_path())
    try:
        ensure_integration_schema(conn)
        result = process_due_events(conn, limit=max(1, args.limit), worker_id=args.worker_id)
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
