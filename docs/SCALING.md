# Scaling notes

Hidden Oasis Staff Payroll currently uses SQLite with WAL mode and busy timeouts. This is suitable for a single-server, small-company installation where writes are moderate and the API/web services run against one local database file.

## Current acceptable use

- One application server.
- Small HR/payroll team.
- Staff self-service traffic at resort scale.
- Regular backups before deployments and payroll changes.

## Known limits

SQLite is not ideal for:

- multiple application servers writing to the same database;
- high write concurrency;
- zero-downtime failover;
- high-availability database clustering;
- long-running analytics on the production database;
- network filesystem database storage.

WAL and busy timeouts reduce lock contention, but they do not make SQLite equivalent to a client/server database.

## Migration triggers

Plan a PostgreSQL migration when any of these become true:

- more than one API server is needed;
- payroll/attendance edits frequently conflict or queue;
- uploads, audit logs, and payroll history grow beyond comfortable local backup windows;
- high availability or point-in-time restore becomes required;
- external systems need concurrent write integrations.

## Future PostgreSQL checklist

1. Introduce a database URL setting while keeping SQLite as the local/default option.
2. Move schema creation into explicit migrations.
3. Replace SQLite-specific SQL and UPSERT behavior where needed.
4. Add integration tests against PostgreSQL.
5. Migrate attachments to a stable storage path or object storage.
6. Run a dry migration from a copy of production data.
7. Verify payroll totals before and after migration.
8. Cut over during a scheduled maintenance window.
9. Keep the SQLite backup and exported reports for rollback/audit.
