"""FastAPI dependencies — authentication and rate limiting.

The HTTP layer depends only on these; it never touches the tenant store or
Redis directly. Shared platform objects live on ``app.state`` and are populated
by the lifespan in ``main.py``.
"""
from __future__ import annotations

from fastapi import Header, Request

from ..exceptions import AuthenticationError, ForbiddenError
from ..tenancy.auth import Authenticator
from ..tenancy.ratelimit import RateLimiter
from ..tenancy.store import TenantRecord, TenantStore

_BEARER_PREFIX = "bearer "


def get_store(request: Request) -> TenantStore:
    """Return the process-wide :class:`TenantStore`."""
    store: TenantStore = request.app.state.store
    return store


def get_authenticator(request: Request) -> Authenticator:
    """Return the process-wide :class:`Authenticator`."""
    authenticator: Authenticator = request.app.state.authenticator
    return authenticator


def get_rate_limiter(request: Request) -> RateLimiter:
    """Return the process-wide :class:`RateLimiter`."""
    rate_limiter: RateLimiter = request.app.state.rate_limiter
    return rate_limiter


async def current_tenant(
    request: Request,
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> TenantRecord:
    """Resolve the ``Authorization: Bearer`` token to its tenant.

    Raises:
        AuthenticationError: header missing/malformed or key invalid (401).
        ForbiddenError: ``X-Tenant-ID`` is present but disagrees with the key (403).
    """
    if not authorization or not authorization.lower().startswith(_BEARER_PREFIX):
        raise AuthenticationError("Missing or malformed Authorization header")
    raw_key = authorization[len(_BEARER_PREFIX):].strip()
    if not raw_key:
        raise AuthenticationError("Empty bearer token")

    tenant = get_authenticator(request).authenticate(raw_key)
    if tenant is None:
        raise AuthenticationError("Invalid API key")
    if x_tenant_id is not None and x_tenant_id != tenant.id:
        raise ForbiddenError(
            "X-Tenant-ID does not match the authenticated tenant", param="X-Tenant-ID"
        )
    request.state.tenant_id = tenant.id
    return tenant


async def enforce_rate_limit(request: Request, tenant: TenantRecord, endpoint: str) -> None:
    """Count this request against the tenant's limit for ``endpoint``.

    Raises:
        RateLimitError: tenant exceeded the window (429).
    """
    await get_rate_limiter(request).enforce(tenant, endpoint)
