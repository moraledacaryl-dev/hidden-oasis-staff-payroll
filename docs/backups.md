# Backup Guidance

Hidden Oasis Staff Payroll keeps the runtime SQLite database outside Git. Make a local server backup before migrations or deploys, then keep at least one off-server copy.

## Before Changes

Run the existing local backup first:

```bash
cd /root/repos/hidden-oasis-staff-payroll
/root/backups/hidden-oasis-payroll/backup.sh
```

Confirm the backup file exists and is readable before running migrations.

## Off-Server Options

### S3-Compatible Storage

Use a bucket from AWS S3, Cloudflare R2, Backblaze B2, Wasabi, or another S3-compatible provider. Store credentials outside the repo.

```bash
export AWS_ACCESS_KEY_ID="<access-key>"
export AWS_SECRET_ACCESS_KEY="<secret-key>"
export AWS_DEFAULT_REGION="<region>"
aws s3 cp /root/backups/hidden-oasis-payroll/<backup-file>.tar.gz s3://<bucket-name>/hidden-oasis-payroll/
```

### Google Drive With rclone

Configure rclone interactively on the server. Do not commit the rclone config if it contains tokens.

```bash
rclone copy /root/backups/hidden-oasis-payroll gdrive:<folder>/hidden-oasis-payroll --include "*.tar.gz"
```

### Another Server With rsync

Use SSH keys managed outside the repo.

```bash
rsync -avz /root/backups/hidden-oasis-payroll/ <backup-user>@<backup-host>:/srv/backups/hidden-oasis-payroll/
```

## Restore Checklist

1. Stop the API and web services.
2. Copy the selected backup archive back to the payroll server.
3. Extract to a temporary restore directory.
4. Verify the SQLite database file name, size, and timestamp.
5. Move the current database aside before replacing it.
6. Restore the database file with the same owner and permissions.
7. Start the API and web services.
8. Open the app and verify login, schedule, payroll runs, payslips, and recent audit data.

## Test Restores

Schedule a restore test on a non-production machine. A backup is only production-safe after the team has proven it can be restored.
