# Build log — 2026-11-14

All numbers here were measured today on the organizer's Atlas sandbox. Raw output is in `docs/evidence/`.

Committee method: the parent session (Cole) judges advisory personas itself. Those verdicts are **not independent**.
P7 and P8 (blocking) run as separate subagents at Stages 1, 4, 5, 6; P5 also at Stage 4.

## Stage 0 — sandbox check: PASS (12:14 EST)

- Driver created the vector index `memories_vec` (cosine, 1024 dims, filters `namespace`, `lifecycle`). READY and queryable.
- A live `$vectorSearch` returned the probe document; the same query under another namespace returned nothing.
- Evidence: `docs/evidence/stage0.txt`.
- P8 CONCERN (parent-judged): the sandbox database user has `atlasAdmin`. It is the organizer's user; noted, not changed.
- P5 note: tier limits (search index count, connections) were not read. One search index is in use.

## Stage 1 — memory layer, seed, probe (12:19 EST)

- Seed: 12 training tickets -> 12 active memories (10 `team-support`, 2 `team-billing`). 16 catalog fixes.
- Probe tickets (10) are separate from the 8 held-out tickets, which have not been embedded or run.
- Repeat top-1 raw cosine: min 0.6946, max 0.8887, n=7. Six of seven at or above 0.75. Top-1 correct for 10 of 10.
- Trap top-1 raw cosine: 0.8263 to 0.9321, evidence 0.26 -> veto band for 3 of 3.
- Evidence: `docs/evidence/stage1_probe.txt`, `docs/evidence/stage1_tests.txt`.

**Abort line hit, owner decision recorded.** PR-101 measured 0.6946, below the 0.75 abort line. The build stopped.
Frank's decision (12:3x EST): *"Option 1. Keep 0.77 on raw cosine and proceed"* — recorded as an exception to E1:
one diluted ticket, pipeline fault ruled out (raw and Atlas scores reconcile as (1 + cos) / 2). No threshold changed.
PR-101 was not reworded. The demo repeat is picked from measured fast-path tickets.

### Controls (G1–G6) and their tests

| Rule | Control | Test |
|---|---|---|
| G1 lifecycle | `memory.check_transition`; `propose` always writes `candidate` | `tests/test_controls.py::test_lifecycle_guard`, `test_new_memory_is_candidate` |
| G2 isolation | `memory.recall_pipeline` is the only query builder; filter is team + active | `test_recall_pipeline_always_filters_team_and_active`; live: probe isolation line |
| G3 evidence veto | `policy.decide` (Stage 3) | boundary tests at 0.49/0.50, 0.29/0.30, 0.76/0.77 (Stage 3) |
| G4 approval hold | `policy.confidence` + hold event (Stage 2) | Stage 2 run output and receipts |
| G5 revise / forget | `memory.revise`, `memory.forget`, promote supersedes in one transaction | Stage 3 live run |
| G6 audit / resume | `receipts.append`, `receipts.verify_chain` (recomputed) | `test_chain_verifies_and_tamper_fails`; Stage 4 live kill |
