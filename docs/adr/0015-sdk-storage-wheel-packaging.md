# ADR-0015 (basic-infra) — SDK + `storage/` wheel packaging

> Status: **accepted** (Track A packaging — 2026-06-08; finalized with telcoss ADR-0014)
> Date: 2026-06-08 · Related: telcoss ADR-0014 (containerized build carrying basic-infra code);
> ADR-0010 (storage), 0011 (observability), 0013 (postgres-multi), 0014 (redis-shared); bridge v19/v20

## Context

Client projects (telcoss) consumed basic-infra's SDKs and the `storage/` package by **live-sourcing
basic-infra's working tree via `PYTHONPATH`** (W10–W12). That blocks any container/production build:
the image can't reach the host `~/basic-infra`, and `storage/` is a top-level package with no
distribution metadata, while the storage SDK imports `from storage.adapters import …`. The
`vams-llm-client` path dep is likewise outside a client's build context.

## Decision

Distribute the basic-infra code as **standard PEP 517 wheels**; consumers `pip install` them instead
of live-sourcing.

1. **`storage/` ships inside the storage-SDK wheel.** `basic_infra_storage_client` (hatchling) already
   `force-include`s `../../storage` → its **wheel bundles the `storage/` package**. A `pip install` of
   that one wheel provides both `basic_infra_storage_client` and `storage`. No separate
   `basic-infra-storage-core` distributable (considered, rejected as overkill) and no `storage/`
   pyproject. (Editable installs still can't carry `storage/` — that's why local dev used PYTHONPATH;
   the **wheel** path is the production answer.)
2. **`py.typed` on every package** (PEP 561) so downstream type-checking works without
   `ignore_missing_imports`: added to the storage / observability / postgres SDKs and to `storage/`;
   the postgres SDK (setuptools) declares `package-data` to ship it; hatchling SDKs include it
   automatically. redis SDK + vams-llm-client already shipped it.
3. **`make wheels`** builds all four SDK wheels + vams-llm-client into a gitignored `dist/wheels`
   wheelhouse (`pip wheel --no-deps`, in-tree build artifacts cleaned). The wheels are build outputs,
   not committed; a consumer vendors/pins the wheelhouse into its image build context (telcoss
   ADR-0014).

## Alternatives

- **Multi-stage image** copying basic-infra source into a build stage: more moving parts (ship source,
  build + copy site-packages) for no gain once the force-include already yields a clean wheel.
- **`storage/` as its own wheel** (`basic-infra-storage-core`): cleaner separation but a new package +
  inter-package dep to maintain; the SDK author already judged it overkill.

## Consequences

Positive: container/prod builds become possible — the image carries `storage` + all four SDKs +
vams-llm-client as installed wheels, no host PYTHONPATH; downstream drops the `ignore_missing_imports`
overrides. Cost: SDK versions are `0.1.0` (bump on change); the wheelhouse must be rebuilt + re-vendored
when basic-infra changes (until an internal index exists). Live-source dev workflow is unaffected
(host gates still PYTHONPATH-source the working tree).

## Verification

- **`make wheels`** builds 5 wheels; the storage wheel bundles `storage/` (16 files) + `storage/py.typed`;
  a scratch venv installs the wheelhouse and imports every package — including `storage` /
  `storage.adapters` — with **no host PYTHONPATH**.
- **`py.typed` shipped** in all four SDK wheels (storage/observability/postgres via this change;
  redis already). Package-source mypy strict + ruff clean; SDK tests pass.
- **Downstream typing fix:** once py.typed was shipped, the observability metrics wrapper's
  `labels()` returned the `Counter|Gauge|Histogram` union, breaking `.inc()`/`.observe()` at consumers;
  `_LabelledInstrument` was made generic (`90a3c1f`) so it returns the concrete type. telcoss dropped
  its `ignore_missing_imports` overrides and stays mypy-strict clean.
- **Consumed in production form:** the telcoss image installs this wheelhouse (`--no-deps`); the
  container imports `storage` from site-packages (not live-sourced) and `pip check` is clean.

(Carried, unrelated: observability `test_sdk.py` strict-dirty; redis `test_health_pings_live_server`
needs a live server.)
