# Personal ecosystem — bridge v11

**Snapshot date:** 2026-05-23
**Last completed:** Week 5 (PR #5 merged) + ADR-0009 reviewer task + prompt iteration v1→v2
**Next target:** Week 6 — basic-infra storage layer (with ADR-0009 gate deliberately OPEN)

This bridge replaces v10. v10 was written before the reviewer task ran and
before the strategic decision to proceed to Week 6 with the gate open.

---

## 1. Ecosystem state

Three repos in active state:

| Repo | Last commit | Notes |
|---|---|---|
| `~/basic-infra/` | Week 4 phase 8 + reviewer-task-discovered config fixes (per-backend timeout, build-context) | Production for two clients. Public on GitHub. |
| `~/telcoss/` | Week 5 + `reviewer-task-followup` (runbook, wiring fixes, bridge v10, prompt v2) | Compliance BC structurally complete, **extraction NOT production-blessed** |
| `~/PAMYAT-NARODA-GRAPH/` | Week 4 phase 6 | LLM services removed from compose |

Branches:
- `migrate-to-basic-infra` — integration branch, Weeks 3+4+5
- `main` — still at Week 2 (Weeks 3+4+5 unmerged, pending gate closure)
- `reviewer-task-followup` — 4 commits ahead of `migrate-to-basic-infra` (runbook + fixes + bridge v10 + prompt v2)

---

## 2. What's incrementally new since v10

### Reviewer task — done

Ran on 2026-05-22/23 against three slices of 126-ФЗ (parts 1, 2, ст. 46).
All three ADR-0009 safeguards verified functional. Full findings in
`docs/runbooks/regulatory-extraction-quality.md`.

### Prompt iteration v1 → v2 (commit `c350989`)

Targeted changes per runbook observations 3-7:

| Metric (ст. 46, 20 chunks) | v1 | v2 |
|---|---|---|
| accepted | 24 | 16 |
| avg title length | 42 | 52 |
| titles ≥30 chars | 79% | **100%** |
| `locator_vague` (empty/"вводная часть") | 10 | **0** |
| correct ст. 46 locator | 0 | 1 |
| qualitative pass rate (eyeball) | ~45-50% | ~55-62% |

v2 is qualitatively better, quantitatively reduced (model fabricates more
under stricter prompt → safeguard #1 rejects more good content alongside bad).
**Still below 80% target.**

### Extractor schema-propagation fix (commit `c350989`)

`json.loads` + `model_validate` now wrapped in typed `try/except` for
`JSONDecodeError` and `ValidationError`. Schema violations are logged via
structlog and rejected at chunk level. Per ADR-0009 safeguard #3 — strict
mode propagates errors as rejections, no free-form fallback. Replaces the
sed-based emergency patch from the reviewer-task run.

### Infrastructure findings (lessons learned, recorded for future bridges)

- **T-pro-it-2.1 72B Q8 is not viable on RTX 2080/2080 Ti** (8+11GB VRAM).
  Partial GPU offload (8/80 layers) → ~1 tok/sec → timeout on every chunk.
  Reviewer task ran on **Qwen2.5-7B Q4_K_M** (full GPU offload, ~64 tok/sec).
- **Per-backend `timeout_seconds` in `~/basic-infra/llm/backends.yaml`
  overrides the gateway env var.** Setting `BACKEND_REQUEST_TIMEOUT_SECONDS`
  alone is insufficient; both must agree. Fixed during reviewer-task run.
- **vams_llm_client SDK CI**: `actions/checkout@v4` of basic-infra alongside
  telcoss + Docker buildx `--build-context` for image build. basic-infra must
  stay **public** for default `GITHUB_TOKEN` to read it; if made private,
  a PAT is required.

---

## 3. Telcoss BC landscape

| BC | Status |
|---|---|
| Questionnaire | Week 1 + Week 3 extension |
| Inventory | Week 3 + Week 5 (`compliance_marks` populated) |
| Lease | Week 3 |
| PDF Intake & KE | Week 3 |
| Reconciliation | Week 3 + Section 15 bindings extended in Week 5 |
| M&A Deal | Week 3 + `04_compliance/` filled in Week 5 |
| Compliance | **Week 5 — structurally complete, extraction NOT production-blessed (gate OPEN)** |

---

## 4. Week 6 scope — basic-infra storage layer

Work in `~/basic-infra/`, not telcoss. Three pieces:

- **`postgres-multi`** — provisioning + management of per-tenant Postgres
  databases. Today each client project runs its own postgres container;
  consolidate into basic-infra with a client-side SDK.
- **`redis-shared`** — same pattern for Redis. basic-infra already has one
  Redis for the gateway; extend to multi-tenant via key prefixing or
  separate DB-numbers.
- **`MinIO/S3 abstraction`** — blob storage port + adapters (MinIO local,
  AWS S3 cloud). Today pdf-intake writes to `/var/telcoss/pdf-intake/` on host.

Migration story: define a non-breaking cutover sequence for existing client
DBs and blob storage. No big-bang.

---

## 5. Open threads — explicit deferral list

Carried from v10 (still open):

- M&A watermark deviation from ADR-0007.
- Namespace merge in M&A stubbed.
- Reconciliation drift detection batch-only.
- Anthropic adapter in basic-infra — stub only; observability — Week 7.

**Compliance BC — five open follow-ups deferred to a post-Week-6 prompt-iteration cycle:**

1. **Prompt iteration v3+** to address remaining quality issues: model uses
   "—" as locator fallback instead of empty/"общ." (anti-pattern not yet
   covered); some titles still vague ("Предоставление сведений по запросу");
   quote fabrication still triggers safeguard #1 frequently (6/20 in v2,
   same as v1 — anti-fabrication wording in v2 prompt didn't help).
2. **`compliance.regulatory_requirements.clause_article` varchar(64) overflow** —
   not triggered in v2 due to better locator discipline, but latent.
   Decide: widen column, add Pydantic truncation, or strengthen prompt.
3. **`failed_extractions` table** for post-hoc analysis of schema-rejected
   candidates (currently logged via structlog only, no DB record).
4. **Production-model decision.** T-pro 72B not viable on current hardware.
   Three paths: bigger GPU (≥40GB VRAM), accept Qwen 7B with prompt work,
   or per-document-kind provider routing (see #5).
5. **Per-document-kind LLM provider routing** — public regulatory docs →
   cloud (DeepSeek/Anthropic/OpenAI), internal operator docs → local.
   Material for ADR-0011 (or extension of ADR-0009).

### The decision recorded in this bridge

Week 6 proceeds with the ADR-0009 gate OPEN. Compliance BC extraction is
consumable but **NOT production-blessed**. Downstream consumers (M&A
dossier, future Audit BC, Wiki BC) inherit the same posture until reviewer-
task pass rate reaches 80% in a future iteration cycle.

This is a deliberate trade-off — prompt iteration plateau-d at ~55-62% in
one session, and the feedback loop is now fast enough (~2 min/cycle on
Qwen 7B) to continue iterating in shorter focused sessions while
infrastructure work proceeds in parallel. The risk is real but bounded:
**as long as no production deployment is taken based on extraction output,
the open gate is a known posture, not a silent assumption.**

`migrate-to-basic-infra → main` remains blocked.

---

## 6. Roadmap

| Week | Target |
|---|---|
| 5 ✓ | Telcoss Compliance BC (gate OPEN — see §5) |
| **6** | **basic-infra storage layer** ← this session |
| 7 | basic-infra observability (Prometheus, Loki, Grafana, tracing) |
| 8+ | Telcoss Wiki/Knowledge BC, Audit BC, Field Worker BC |
| Parallel | Compliance prompt iteration v3+ in focused sessions until ≥80% pass; then close gate; then merge `migrate-to-basic-infra → main`. |
| Future | MCP server wrapping basic-infra |

---

## 7. How to use this bridge

Open the next session with:

> Personal ecosystem continues. Bridge v11 attached.
> State: Week 5 (Compliance BC) merged into migrate-to-basic-infra
>   (PR #5 + reviewer-task-followup). ADR-0009 gate OPEN (~55-62%, target ≥80%)
>   — deliberately deferred.
> Today: Week 6 = basic-infra storage layer (postgres-multi, redis-shared,
>   MinIO/S3 abstraction).
> Five Compliance follow-ups parked in §5 — NOT touched in Week 6.
> Constraints: do not break basic-infra LLM platform contract; do not break
>   Q-BC release pipeline; do not promote migrate-to-basic-infra → main
>   until gate closed.

Files worth re-attaching for Week 6:
- `~/basic-infra/docs/adr/0001-platform-charter.md` (scope of basic-infra)
- `~/basic-infra/docker-compose.yml` + `llm/compose/*.yml` (current service layout)
- `~/telcoss/infra/compose/compose.base.yml` (current telcoss persistence layout)
- `~/PAMYAT-NARODA-GRAPH/docker-compose.yml` (pamyat persistence — for migration story)

---

## 8. What this bridge intentionally does NOT include

- Full reviewer-task quality breakdown — see `docs/runbooks/regulatory-extraction-quality.md`.
- Prompt v1↔v2 detailed diff — see commit `c350989`.
- ADR-0009 safeguard implementation details — see ADR.
- Per-client storage layout — see `.env.example` files.

---

**End of bridge v11.** ~3 page read.
