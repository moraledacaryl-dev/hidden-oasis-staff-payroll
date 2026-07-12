from __future__ import annotations

import json
import os
import signal
import socket
import time
from datetime import datetime

from api.main import configured_db_path
from core.db import get_conn
from core.integration_outbox import ensure_integration_schema, process_due_events


_STOP = False


def _stop(_signum: int, _frame: object) -> None:
    global _STOP
    _STOP = True


def _positive_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return max(minimum, int(raw)) if raw else default
    except ValueError:
        return default


def _activation_enabled() -> bool:
    return os.getenv("STAFF_PAYROLL_INTEGRATION_ACTIVATION_ENABLED", "false").strip().lower() == "true"


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    interval_seconds = _positive_int("STAFF_PAYROLL_SYNC_INTERVAL_SECONDS", 10)
    batch_size = _positive_int("STAFF_PAYROLL_SYNC_BATCH_SIZE", 25)
    worker_id = os.getenv("STAFF_PAYROLL_SYNC_WORKER_ID", "").strip() or f"{socket.gethostname()}:{os.getpid()}"

    print(
        json.dumps(
            {
                "event": "integration_worker_started",
                "worker_id": worker_id,
                "interval_seconds": interval_seconds,
                "batch_size": batch_size,
                "activation_enabled": _activation_enabled(),
                "started_at": datetime.now().astimezone().isoformat(),
            }
        ),
        flush=True,
    )

    last_activation_state: bool | None = None
    while not _STOP:
        enabled = _activation_enabled()
        if enabled != last_activation_state:
            print(
                json.dumps(
                    {
                        "event": "integration_activation_state",
                        "worker_id": worker_id,
                        "enabled": enabled,
                        "at": datetime.now().astimezone().isoformat(),
                    }
                ),
                flush=True,
            )
            last_activation_state = enabled

        result = {"claimed": 0, "completed": 0, "failed": 0, "dead_letter": 0}
        if enabled:
            conn = get_conn(configured_db_path())
            try:
                ensure_integration_schema(conn)
                result = process_due_events(conn, limit=batch_size, worker_id=worker_id)
            except Exception as exc:  # keep the service alive; the next cycle retries safely
                result = {
                    "claimed": 0,
                    "completed": 0,
                    "failed": 1,
                    "dead_letter": 0,
                    "worker_error": str(exc),
                }
            finally:
                conn.close()

        if result.get("claimed") or result.get("worker_error"):
            print(json.dumps(result, ensure_ascii=False, default=str), flush=True)

        for _ in range(interval_seconds):
            if _STOP:
                break
            time.sleep(1)

    print(
        json.dumps(
            {
                "event": "integration_worker_stopped",
                "worker_id": worker_id,
                "stopped_at": datetime.now().astimezone().isoformat(),
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
