from __future__ import annotations

import json
from core.db import DB_PATH, fetchall, fetchone, get_conn

KEEP_RUN_ID = 1
DELETE_RUN_IDS = (2, 3)


def table_columns(conn, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def table_exists(conn, table: str) -> bool:
    return fetchone(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)) is not None


def delete_by_column(conn, table: str, column: str, values: list[int]) -> int:
    if not values or not table_exists(conn, table) or column not in table_columns(conn, table):
        return 0
    placeholders = ",".join("?" for _ in values)
    cur = conn.execute(f"DELETE FROM {table} WHERE {column} IN ({placeholders})", values)
    return int(cur.rowcount or 0)


def main() -> None:
    conn = get_conn(DB_PATH)
    try:
        keep = fetchone(conn, "SELECT * FROM payroll_runs WHERE id=?", (KEEP_RUN_ID,))
        if not keep:
            raise RuntimeError(f"Run #{KEEP_RUN_ID} was not found.")
        if keep.get("status") != "Draft":
            raise RuntimeError(f"Run #{KEEP_RUN_ID} is not Draft and will not be modified.")

        delete_runs = fetchall(
            conn,
            f"SELECT * FROM payroll_runs WHERE id IN ({','.join('?' for _ in DELETE_RUN_IDS)}) ORDER BY id",
            DELETE_RUN_IDS,
        )
        found_ids = {int(row["id"]) for row in delete_runs}
        missing = [run_id for run_id in DELETE_RUN_IDS if run_id not in found_ids]
        if missing:
            raise RuntimeError(f"Expected Draft run(s) missing: {missing}")
        for run in delete_runs:
            if run.get("status") != "Draft":
                raise RuntimeError(f"Run #{run['id']} is {run.get('status')}, not Draft. Cleanup stopped.")

        item_rows = fetchall(
            conn,
            f"SELECT id,payroll_run_id FROM payroll_items WHERE payroll_run_id IN ({','.join('?' for _ in DELETE_RUN_IDS)})",
            DELETE_RUN_IDS,
        )
        item_ids = [int(row["id"]) for row in item_rows]
        run_ids = [int(value) for value in DELETE_RUN_IDS]

        deleted: dict[str, int] = {}
        tables = [str(row["name"]) for row in fetchall(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]

        # Delete item-linked detail rows first.
        for table in tables:
            if table in {"payroll_items", "payroll_runs"}:
                continue
            count = delete_by_column(conn, table, "payroll_item_id", item_ids)
            if count:
                deleted[f"{table}.payroll_item_id"] = count

        # Delete run-linked rows next.
        for table in tables:
            if table in {"payroll_items", "payroll_runs"}:
                continue
            count = delete_by_column(conn, table, "payroll_run_id", run_ids)
            if count:
                deleted[f"{table}.payroll_run_id"] = count
            count = delete_by_column(conn, table, "revision_run_id", run_ids)
            if count:
                deleted[f"{table}.revision_run_id"] = count
            count = delete_by_column(conn, table, "original_run_id", run_ids)
            if count:
                deleted[f"{table}.original_run_id"] = count

        # Remove any references from the kept/original run to deleted revisions.
        run_columns = table_columns(conn, "payroll_runs")
        if "superseded_by_run_id" in run_columns:
            conn.execute("UPDATE payroll_runs SET superseded_by_run_id=NULL WHERE id=? OR superseded_by_run_id IN (?,?)", (KEEP_RUN_ID, *DELETE_RUN_IDS))
        if "revision_of_run_id" in run_columns:
            conn.execute("UPDATE payroll_runs SET revision_of_run_id=NULL WHERE id=?", (KEEP_RUN_ID,))
        if "revision_reason" in run_columns:
            conn.execute("UPDATE payroll_runs SET revision_reason=NULL WHERE id=?", (KEEP_RUN_ID,))
        if "revision_treatment" in run_columns:
            conn.execute("UPDATE payroll_runs SET revision_treatment=NULL WHERE id=?", (KEEP_RUN_ID,))

        deleted["payroll_items"] = int(conn.execute(
            f"DELETE FROM payroll_items WHERE payroll_run_id IN ({','.join('?' for _ in DELETE_RUN_IDS)})",
            DELETE_RUN_IDS,
        ).rowcount or 0)
        deleted["payroll_runs"] = int(conn.execute(
            f"DELETE FROM payroll_runs WHERE id IN ({','.join('?' for _ in DELETE_RUN_IDS)})",
            DELETE_RUN_IDS,
        ).rowcount or 0)

        conn.commit()
        remaining = fetchall(conn, "SELECT id,period_start,period_end,run_label,status,revision_of_run_id FROM payroll_runs ORDER BY id")
        print(json.dumps({
            "ok": True,
            "database": str(DB_PATH),
            "kept_run_id": KEEP_RUN_ID,
            "deleted_run_ids": list(DELETE_RUN_IDS),
            "deleted_rows": deleted,
            "remaining_runs": remaining,
        }, indent=2, default=str))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
