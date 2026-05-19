"""Tenant-facing schemas.

``TenantIdentity`` is the public response for ``GET /v1/tenants/me``. Internal
tenant persistence uses ``tenancy.store.TenantRecord`` — secrets never appear
in any schema here.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class TenantIdentity(BaseModel):
    """Identity of the authenticated tenant — response for ``GET /v1/tenants/me``."""

    tenant_id: str
    display_name: str
    allowed_models: list[str]
    rate_limits: dict[str, str] = Field(default_factory=dict)
