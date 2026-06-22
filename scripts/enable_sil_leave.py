from pathlib import Path

from core.db import DB_PATH, fetchall, fetchone, get_conn

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "api" / "server_review.py"
MODAL = ROOT / "apps" / "web" / "components" / "ScheduleDayEditorModal.tsx"
ALIASES = {
    "sil",
    "service incentive leave",
    "service incentive leave (sil)",
    "sil (service incentive leave)",
}


def normalized(value):
    return " ".join(str(value or "").strip().lower().split())


def patch_source_files():
    server = SERVER.read_text(encoding="utf-8")
    import_line = "from api.sil_leave import router as sil_leave_router"
    include_line = "app.include_router(sil_leave_router)"
    if import_line not in server:
        anchor = "from api.schedule_actuals import router as schedule_actuals_router"
        server = server.replace(anchor, anchor + "\n" + import_line)
    if include_line not in server:
        anchor = "app.include_router(schedule_actuals_router)"
        server = server.replace(anchor, anchor + "\n" + include_line)
    SERVER.write_text(server, encoding="utf-8")

    modal = MODAL.read_text(encoding="utf-8")
    if '  "SIL",' not in modal:
        modal = modal.replace('  "None",\n', '  "None",\n  "SIL",\n')
    MODAL.write_text(modal, encoding="utf-8")


def normalize_database():
    conn = get_conn(DB_PATH)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS leave_types (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, default_credits REAL NOT NULL DEFAULT 0, paid INTEGER NOT NULL DEFAULT 1, statutory INTEGER NOT NULL DEFAULT 0, requires_approval INTEGER NOT NULL DEFAULT 1, active INTEGER NOT NULL DEFAULT 1, notes TEXT)"
        )
        rows = fetchall(conn, "SELECT * FROM leave_types ORDER BY id")
        matches = [row for row in rows if normalized(row.get("name")) in ALIASES]
        canonical = next((row for row in matches if normalized(row.get("name")) == "sil"), None)
        if canonical:
            canonical_id = int(canonical["id"])
        elif matches:
            canonical_id = int(matches[0]["id"])
            conn.execute("UPDATE leave_types SET name='SIL' WHERE id=?", (canonical_id,))
        else:
            canonical_id = int(conn.execute("INSERT INTO leave_types(name,default_credits,paid,statutory,requires_approval,active,notes) VALUES('SIL',5,1,1,1,1,'Service Incentive Leave')").lastrowid)

        alias_ids = [int(row["id"]) for row in matches if int(row["id"]) != canonical_id]
        for alias_id in alias_ids:
            if fetchone(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='leave_requests'"):
                conn.execute("UPDATE leave_requests SET leave_type_id=? WHERE leave_type_id=?", (canonical_id, alias_id))
            if fetchone(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='employee_leave_entitlements'"):
                entitlement_rows = fetchall(conn, "SELECT * FROM employee_leave_entitlements WHERE leave_type_id=?", (alias_id,))
                for row in entitlement_rows:
                    existing = fetchone(conn, "SELECT * FROM employee_leave_entitlements WHERE employee_id=? AND leave_type_id=? AND year=?", (row["employee_id"], canonical_id, row["year"]))
                    if existing:
                        conn.execute("UPDATE employee_leave_entitlements SET credits=?, used=?, entitled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (max(float(existing.get("credits") or 0), float(row.get("credits") or 0)), max(float(existing.get("used") or 0), float(row.get("used") or 0)), max(int(existing.get("entitled") or 0), int(row.get("entitled") or 0)), existing["id"]))
                        conn.execute("DELETE FROM employee_leave_entitlements WHERE id=?", (row["id"],))
                    else:
                        conn.execute("UPDATE employee_leave_entitlements SET leave_type_id=? WHERE id=?", (canonical_id, row["id"]))
            conn.execute("UPDATE leave_types SET active=0, notes='Merged into SIL' WHERE id=?", (alias_id,))

        conn.execute("UPDATE leave_types SET name='SIL', default_credits=CASE WHEN default_credits<=0 THEN 5 ELSE default_credits END, paid=1, statutory=1, active=1, notes=COALESCE(notes,'Service Incentive Leave') WHERE id=?", (canonical_id,))
        if fetchone(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='time_logs'"):
            for row in fetchall(conn, "SELECT id, absence_type FROM time_logs WHERE absence_type IS NOT NULL"):
                if normalized(row.get("absence_type")) in ALIASES:
                    conn.execute("UPDATE time_logs SET absence_type='SIL' WHERE id=?", (row["id"],))
        conn.commit()
        print(f"SIL canonical leave type id: {canonical_id}")
        print(f"Merged aliases: {alias_ids}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    patch_source_files()
    normalize_database()
    print("SIL enabled in API, UI, and leave master data.")
