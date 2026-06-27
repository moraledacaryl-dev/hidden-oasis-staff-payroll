# Canonical Route Cleanup Roadmap

This app previously carried several focused compatibility routers for urgent production fixes. The route registry is now assembled without mutating imported router objects, but the final architecture target is still a single canonical source of truth per domain.

## Current state

The API registry avoids in-place edits to imported router route lists. Remaining compatibility routers are included before filtered canonical routers so the corrected endpoints stay active.

Remaining compatibility domains:

- `api.schedule_input_validation_routes` for validated schedule create/day-scheduled/day-actual endpoints.
- `api.schedule_leave_fractional` for fractional day-editor leave handling.
- `api.staff_self_service_upload_secure` for secure staff attachment upload handling.

## Target state

- `api.schedules` owns schedule create/day-scheduled/day-actual validation directly.
- `api.schedules` owns fractional day-editor leave directly.
- `api.staff_self_service` owns secure attachment validation directly.
- `api.server` includes each domain router once without filtered route exclusions.
- Compatibility routers are deleted after equivalent canonical tests pass.

## Required regression tests

Before deleting each compatibility router, prove:

1. No duplicate HTTP method/path routes are registered.
2. OpenAPI exposes the canonical endpoint names.
3. Invalid schedule times, invalid employee IDs, invalid break minutes, and invalid OT hours are rejected.
4. Fractional leave saves the expected `leave_requests.days` value.
5. Switching a day from paid leave to another absence removes only the selected day from existing leave.
6. Uploads reject renamed files and oversized files.
7. Staff upload route checks request ownership and writes attachments with owner-only filesystem permissions.

## Merge rule

Keep each cleanup PR small and green. Do not merge a compatibility-router deletion unless the canonical module carries the exact same behavior and the full Verify workflow passes.
