-- ============================================================================
-- Authentik DB bootstrap (ADR-0018) — admin-run, idempotent.
--
-- Authentik is a self-migrating tenant: it runs its own DDL (CREATE TABLE …) on
-- every release. The platform's least-privilege `app_<tenant>` runtime role is
-- DML-only (NOSUPERUSER NOCREATEDB NOCREATEROLE, no DDL — ADR-0016 §2) and is
-- therefore structurally wrong for it. So Authentik gets a DEDICATED OWNER role
-- that OWNS its own database — distinct from the `app_*` machinery, so H2a
-- (app_telcoss least-privilege) is untouched.
--
-- This is NOT created via `make provision TENANT=authentik` (that path makes an
-- admin-owned DB + a spurious app_authentik DML role). Apply this instead, as
-- the postgres admin against the maintenance DB. See README in this dir.
--
-- Idempotent: re-running is a no-op. The role password is passed as a psql
-- variable (:'authentik_pw') — never hard-coded here.
-- ============================================================================

-- 1) Owner role: LOGIN, but no superuser/createdb/createrole. It owns its DB and
--    may run DDL WITHIN that DB (ownership ⇒ DDL on its own objects), which is
--    exactly what Authentik's migrations need — and nothing platform-wide.
--    The create is guarded in a DO block (no CREATE ROLE IF NOT EXISTS). NOTE:
--    psql ':var' substitution does NOT happen inside a dollar-quoted $$…$$ body,
--    so the password is NOT set here — it is (re-)asserted in step 2 as a plain
--    statement where psql interpolates :'authentik_pw' safely as a quoted literal.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authentik') THEN
        CREATE ROLE authentik LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END $$;

-- 2) Always (re-)assert login + password (drift-strip, mirrors the control-plane
--    consume-and-reassert posture). Plain statement → psql substitutes :'…' as a
--    correctly-quoted string literal.
ALTER ROLE authentik WITH LOGIN PASSWORD :'authentik_pw';

-- 3) Database owned by the authentik role. CREATE DATABASE cannot run inside a
--    transaction/DO block and has no IF NOT EXISTS, so guard with \gexec.
SELECT 'CREATE DATABASE authentik OWNER authentik'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'authentik')
\gexec
