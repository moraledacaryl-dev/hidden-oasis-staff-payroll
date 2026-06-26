# Backup and Restore

The runtime SQLite database stays outside Git. Create a verified backup before every migration or deployment and keep an off-server copy.

## Configuration

```text
STAFF_PAYROLL_BACKUP_DIR=/srv/backups/staff-payroll
STAFF_PAYROLL_BACKUP_KEY=<long-random-encryption-secret>
STAFF_PAYROLL_OFFSITE_BACKUP_DIR=/mounted-offsite/staff-payroll
STAFF_PAYROLL_BACKUP_RETENTION=30
```

## Create and Verify

Owners can create, verify, and download backups from the Backups page.

Command line:

```bash
.venv-api/bin/python scripts/backup_database.py
```

Backups use SQLite's online backup API and run an integrity check before completion. Encrypted backups require the same `STAFF_PAYROLL_BACKUP_KEY` for verification and restore.

## Restore

1. Stop the API and web services.
2. Keep the current database as a separate rollback copy.
3. Decrypt the selected backup when it ends in `.fernet`.
4. Run `PRAGMA integrity_check` on the restored SQLite file.
5. Restore the configured file path and permissions.
6. Start the API and run `scripts/production_preflight.py`.
7. Verify login, schedules, payroll runs, payslips, backups, and recent audit records.

Run a restore test on a non-production machine regularly. A backup is not proven until it has been restored successfully.
