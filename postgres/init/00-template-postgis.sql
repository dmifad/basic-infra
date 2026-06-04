-- postgres-multi init (ADR-0013)
--
-- Предзагружает PostGIS в template1, чтобы каждая новая per-tenant БД
-- получала расширение «бесплатно» при CREATE DATABASE. Это удобство, а НЕ
-- замена идемпотентного `CREATE EXTENSION IF NOT EXISTS postgis`, который
-- control-plane адаптер (postgres.LocalAdapter.provision) выполняет в любом
-- случае — на случай инстансов, поднятых без этого init-скрипта (managed).
--
-- Выполняется один раз при первичной инициализации тома данных
-- (docker-entrypoint-initdb.d). На существующих томах не перезапускается.
\connect template1
CREATE EXTENSION IF NOT EXISTS postgis;
