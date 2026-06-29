# 0020 — Platform↔consumer boundary principle (pointer)

* **Status:** Accepted (K1-a, 2026-06-29)
* **Canonical document:** `telcoss/docs/adr/0020-platform-consumer-boundary.md`
* **Relates to:** ADR-0018 (Authentik platform IdP — L8/L9 deferred to K1-d)

The full ADR lives in the telcoss repo because the leak inventory is about
telcoss-specific names appearing in basic-infra, and the telcoss ADR series
(0019, 0020) is the canonical home for cross-repo boundary decisions.

## Summary for basic-infra readers

The **operator-B test**: any `telcoss` string in basic-infra that must be
edited to onboard a second consumer is a leak. ADR-0020 inventories all
eleven leaks found in the Phase-0 audit and assigns each a disposition:

- **K1-b (gated):** dispatcher defaults (`OUTBOX_TABLE`, `OUTBOX_CHANNEL`,
  `OUTBOX_OBSERVABILITY_TENANT`), bootstrap email default, GUC namespace
  `telcoss.app_pw` → `basic_infra.app_pw`. All low-risk, no live disruption.
- **K1-d (own gated track, RED):** Authentik blueprint mount path
  (`/blueprints/telcoss`) and `telcoss-oidc.yaml` in this repo — live
  Authentik reconcile risk; handled separately.
- **Deferred:** Prometheus scrape job `telcoss-app` — requires a
  consumer-side scrape config injection convention.
- **Accept-and-document:** `outbox_reader` column grant stays in the telcoss
  migration (column grant requires table to exist; no post-provision hook
  mechanism; structural coupling is minimal and documented in ADR-0019 §3).

No basic-infra code is changed by K1-a. K1-b changes land on a basic-infra
branch when green-lit.
