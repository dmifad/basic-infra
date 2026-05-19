"""``GET /v1/tenants/me`` route — tenant self-identification for SDK debugging."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...schemas.tenant import TenantIdentity
from ...tenancy.store import TenantRecord
from ..deps import current_tenant

router = APIRouter(tags=["tenants"])


@router.get("/tenants/me", response_model=TenantIdentity)
async def get_current_tenant_identity(
    tenant: TenantRecord = Depends(current_tenant),
) -> TenantIdentity:
    """Return the identity of the tenant resolved from the Bearer token."""
    return TenantIdentity(
        tenant_id=tenant.id,
        display_name=tenant.display_name,
        allowed_models=list(tenant.allowed_models),
        rate_limits=tenant.rate_limits,
    )
