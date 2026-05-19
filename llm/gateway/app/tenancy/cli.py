"""``basic-infra tenant ...`` — command-line tenant management (ADR-0003).

Runs against the SQLite tenant store at ``TENANT_DB_PATH``. Invoke either as the
installed ``basic-infra`` console script or as ``python -m app.tenancy.cli``.

Note: this module deliberately does NOT use ``from __future__ import
annotations`` — typer resolves command-parameter types from real annotation
objects, and stringized annotations would make it misread every option.
"""
import sys

import httpx
import typer

from ..config import get_settings
from .store import TenantExists, TenantNotFound, TenantStore

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    help="basic-infra platform CLI",
)
tenant_app = typer.Typer(no_args_is_help=True, help="Tenant management")
app.add_typer(tenant_app, name="tenant")


def _store() -> TenantStore:
    return TenantStore(get_settings().tenant_db_path)


def _parse_models(spec: str) -> tuple[str, ...]:
    """Parse ``--models`` — ``"*"`` for all, else a comma-separated id list."""
    return tuple(m.strip() for m in spec.split(",") if m.strip())


@tenant_app.command("create")
def create(
    id: str = typer.Option(..., "--id", help="Stable lowercase-kebab tenant id"),
    display: str = typer.Option("", "--display", help="Human-friendly name (defaults to id)"),
    models: str = typer.Option("*", "--models", help='Allowed models, comma-separated or "*"'),
) -> None:
    """Create a tenant and print its API key (shown once — store it now)."""
    store = _store()
    try:
        record, raw_key = store.create(
            id=id, display_name=display or id, allowed_models=_parse_models(models)
        )
    except TenantExists as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    finally:
        store.close()
    typer.secho(f"CREATED {record.id}", fg=typer.colors.GREEN)
    typer.echo(f"  display:        {record.display_name}")
    typer.echo(f"  allowed_models: {', '.join(record.allowed_models)}")
    typer.secho(f"  API KEY:        {raw_key}", fg=typer.colors.YELLOW, bold=True)
    typer.echo("  ^ save this now — it cannot be retrieved later.")


@tenant_app.command("list")
def list_tenants(
    include_deleted: bool = typer.Option(False, "--include-deleted"),
) -> None:
    """List tenants as a table."""
    store = _store()
    try:
        rows = store.list(include_deleted=include_deleted)
    finally:
        store.close()
    if not rows:
        typer.echo("(no tenants)")
        return
    typer.echo(f"{'ID':<20} {'DISPLAY':<24} {'MODELS':<16} CREATED")
    for r in rows:
        models = ",".join(r.allowed_models)
        suffix = "  [deleted]" if r.deleted_at else ""
        typer.echo(
            f"{r.id:<20} {r.display_name:<24} {models:<16} "
            f"{r.created_at:%Y-%m-%d}{suffix}"
        )


@tenant_app.command("show")
def show(id: str = typer.Argument(..., help="Tenant id")) -> None:
    """Show one tenant's details."""
    store = _store()
    try:
        record = store.get(id)
    finally:
        store.close()
    if record is None:
        typer.secho(f"error: tenant not found: {id}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.echo(f"id:             {record.id}")
    typer.echo(f"display_name:   {record.display_name}")
    typer.echo(f"allowed_models: {', '.join(record.allowed_models)}")
    typer.echo(f"rate_limits:    {record.rate_limits or '(defaults)'}")
    typer.echo(f"created_at:     {record.created_at.isoformat()}")
    typer.echo(f"updated_at:     {record.updated_at.isoformat()}")
    typer.echo(f"deleted_at:     {record.deleted_at.isoformat() if record.deleted_at else '-'}")


@tenant_app.command("rotate-key")
def rotate_key(id: str = typer.Argument(..., help="Tenant id")) -> None:
    """Issue a new API key; the old one stays valid for 24 h."""
    store = _store()
    try:
        new_key = store.rotate_key(id)
    except TenantNotFound as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    finally:
        store.close()
    typer.secho(f"ROTATED {id}", fg=typer.colors.GREEN)
    typer.secho(f"  NEW API KEY: {new_key}", fg=typer.colors.YELLOW, bold=True)
    typer.echo("  Old key remains valid for 24 h.")


@tenant_app.command("delete")
def delete(
    id: str = typer.Argument(..., help="Tenant id"),
    confirm: bool = typer.Option(False, "--confirm", help="Required — archives the tenant"),
) -> None:
    """Archive a tenant (soft delete — keeps an audit trail)."""
    if not confirm:
        typer.secho("refusing to delete without --confirm", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    store = _store()
    try:
        store.soft_delete(id)
    except TenantNotFound as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    finally:
        store.close()
    typer.secho(f"ARCHIVED {id}", fg=typer.colors.GREEN)


@tenant_app.command("smoke-test")
def smoke_test(
    id: str = typer.Argument(..., help="Tenant id"),
    base_url: str = typer.Option("http://localhost:8003", "--base-url"),
    key: str = typer.Option("", "--key", help="Tenant API key — enables the authed checks"),
) -> None:
    """Check the tenant exists and probe the gateway (``/health``, and ``/v1/models`` if --key)."""
    store = _store()
    try:
        record = store.get(id)
    finally:
        store.close()
    if record is None:
        typer.secho(f"error: tenant not found: {id}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.secho(f"[ok] tenant {id} present in store", fg=typer.colors.GREEN)

    try:
        health = httpx.get(f"{base_url}/health", timeout=5.0)
        typer.echo(f"[--] GET /health -> {health.status_code}")
        if key:
            models = httpx.get(
                f"{base_url}/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=5.0,
            )
            typer.echo(f"[--] GET /v1/models -> {models.status_code}")
    except httpx.HTTPError as exc:
        typer.secho(f"[!!] gateway unreachable at {base_url}: {exc}", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    sys.exit(app())
