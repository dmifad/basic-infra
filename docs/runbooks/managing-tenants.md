# Runbook — managing tenants

> **Status:** stub. Filled in Phase 8 once the tenant CLI (Phase 3) is built.

How to create, inspect, rotate and retire tenants.

Reference: ADR-0003 (multi-tenancy).

## Commands

```bash
basic-infra tenant create --id <id> --display "<name>" --models "*"
basic-infra tenant list
basic-infra tenant show <id>
basic-infra tenant rotate-key <id>      # old key valid 24h
basic-infra tenant delete <id> --confirm # soft delete (archive)
basic-infra tenant smoke-test <id>
```

## Notes

- The raw API key is shown **once** on creation/rotation. Only its hash is stored.
- Rotated keys keep working for a 24 h grace window.
- `delete` is a soft delete — it sets `deleted_at`, keeping an audit trail.

_TODO(week4-phase-8): key-storage conventions, rate-limit tuning, troubleshooting auth failures._
