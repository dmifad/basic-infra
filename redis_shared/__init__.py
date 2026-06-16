"""Shared Redis control plane (ADR-0014).

Provisions per-tenant ACL users restricted to `~<namespace>:*` on a single
shared Redis. Mirrors the postgres-multi control plane (Port + Local/Managed
adapters + CLI). Data plane lives in sdk/basic_infra_redis_client.
"""
