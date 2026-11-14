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

## Stage 2 — live lifecycle, hold, promote, fast path

- What was run: `./demo_stage2.sh` (Act 1 with novel ticket D-1 run twice, review queue check, agent self-approval attempt, promotion by human, Act 2a with repeat ticket D-2, handoff to a new process and run, audit comparison).
- Seed: `seeded 12 training tickets; memories by lifecycle: {'candidate': 0, 'active': 12, 'superseded': 0, 'retired': 0}`.
- Act 1 (novel ticket D-1): `status: HELD   path: catalog   tool calls: 7   confidence: 0.50`. Learned fix proposed: `learned: CANDIDATE mem-D-1 is waiting in the review queue. It is not recalled until a human promotes it.`.
- Agent self-approval rejected: `REFUSED: agent requested this review and cannot also approve it` (exit code 2).
- Human promotion: `memory: mem-D-1  lifecycle: active  evidence: 0.85  approved_by: sarah.chen`, `vector index in sync after 1.0s`.
- Act 2a (repeat ticket D-2): `top-1 mem-D-1 cosine 0.8755 evidence 0.85`, `status: RESOLVED   path: fast   tool calls: 3   confidence: 0.85`.
- Handoff in new process: `status: RESOLVED   path: fast   tool calls: 3   confidence: 0.85`.
- Determinism: `SAME SEQUENCE: 10 steps` (Act 1 repeated), `SAME SEQUENCE: 4 steps` (Act 2a vs handoff).
- Chain verification: `CHAIN OK: 10 receipts, chain verifies` (Act 1), `CHAIN OK: 4 receipts, chain verifies` (Act 2a).
- Evidence: `docs/evidence/stage2.txt`.

## Stage 3 — evidence veto, namespace isolation, revise, forget

- What was run: `./demo_stage3.sh` (Act 2b with lookalike ticket D-3, audit receipt of veto, isolation check of ticket D-2 under `team-billing`, G5 revise `mem-TR-201`, proposer self-approval rejected, promotion by omar.haddad superseding v1, G5 forget `mem-TR-202`, double-retire rejected, governance receipts audit).
- Act 2b (lookalike ticket D-3): `top-1 mem-TR-108 cosine 0.9324 evidence 0.26`, `** VETO ** mem-TR-108 blocked: cosine 0.9324, evidence 0.26 < 0.50 (fix F08 not applied)`.
- Act 2b resolution: takes catalog path, `status: HELD   path: catalog   tool calls: 7   confidence: 0.50`, `audit: 11 receipts, chain verifies (s3-act2b-175859)`.
- Isolation check: Act 2a ticket text run under `team-billing` recalls `top-1 mem-TR-201 cosine 0.3253 evidence 0.85`, falls through to catalog path with 7 tool calls, `status: HELD   path: catalog   tool calls: 7   confidence: 0.50`.
- G5 Revise: proposed `mem-TR-201-v2` as candidate (`candidate: mem-TR-201-v2  review: rev-mem-TR-201-v2`); old version stays active until promotion.
- Proposer self-approval rejected: `REFUSED: lin.wu requested this review and cannot also approve it` (exit code 2).
- Promotion by omar.haddad: `memory: mem-TR-201-v2  lifecycle: active  evidence: 0.85  approved_by: omar.haddad`, `vector index in sync after 0.6s`; parent `mem-TR-201` marked `superseded` with `superseded_by: mem-TR-201-v2` in the same transaction.
- G5 Forget: `retired mem-TR-202` with reason "Tax details moved to the billing portal; fix no longer applies". Double-retire rejected: `REFUSED: illegal lifecycle move: retired -> retired` (exit code 2).
- Governance chain audit: `CHAIN OK: 42 receipts, chain verifies`, `tool receipts: 0`.
- Evidence: `docs/evidence/stage3.txt`.

## Stage 4 — kill, resume, audit, and tamper tests

- What was run: `./demo_stage4.sh` (Act 3 live SIGKILL of agent process mid-ticket after receipt 5, restart and resume from Atlas receipts), `python -m govmem.killtest` (10-point kill matrix, external kill test, 4 tamper tests).
- Act 3 live SIGKILL: `GOVMEM_KILL_AFTER=5 G ingest --seed-ticket D-3 --run-id act3-180008`, `exit code 137 (137 = killed by SIGKILL)`.
- Surviving receipts in Atlas: `CHAIN OK: 5 receipts, chain verifies`, `tool receipts: 4`.
- Restart and resume: `resuming act3-180008: 5 receipts found, chain verifies`. Steps 1–5 replayed from receipts, steps 6–11 executed: `tool calls: 7 (steps executed now: 6, steps replayed from receipts: 5)`.
- Determinism against uninterrupted baseline: `SAME SEQUENCE: 11 steps`, `CHAIN OK: 11 receipts, chain verifies`, `tool receipts: 7`.
- Bug found by running demo_stage4.sh: `resume` looked up the ticket by a field written only when a run finishes, so a killed run was not found. Fixed: resume reads the ticket id from the run's first receipt.
- Kill matrix: `BASELINE: 11 receipts, 7 tool calls`, `KILL MATRIX: 10 of 10 kill points passed` (k=1 to 10: chain ok, sequence same, result PASS).
- External kill: `EXTERNAL KILL: PASS (killed at 3 receipts)`.
- Tamper detection: `TAMPER: 4 of 4 detected as expected`:
  - `alter seq 2 result: caught (seq 2: stored hash does not match its content)`
  - `remove middle receipt: caught (sequence gap: expected 6, found 7)`
  - `swap two receipts: caught (sequence gap: expected 2, found 3)`
  - `drop tail stays verifiable: caught (tail open (full baseline complete))`
- Evidence: `docs/evidence/stage4_act3.txt`, `docs/evidence/stage4_killtest.txt`.

## Stage 5 — held-out evaluation

- What was run: `python -m govmem.evalrun` over 8 held-out tickets (5 twins HT-1 to HT-5, 3 lookalikes HL-1 to HL-3) across two conditions (empty memory vs trained memory) with 2 repetitions each (rep a, rep b). The held-out tickets were first used in this run, after `seed --reset`.
- Index sync: `index sync: 1.15s, active memories: {'team-support': 10, 'team-billing': 2}`.
- Empty condition (rep a):
  - `twin`: n=5, resolved 5 of 5, wrong_fixes 0, vetoes 0 of 5, holds 5 of 5, fast_path 0 of 5, tool_calls [7, 7, 7, 7, 7], mean 7.00.
  - `lookalike`: n=3, resolved 3 of 3, wrong_fixes 0, vetoes 0 of 3, holds 3 of 3, fast_path 0 of 3, tool_calls [7, 7, 7], mean 7.00.
  - `rep a vs rep b: identical`.
- Trained condition (rep a):
  - `twin`: n=5, resolved 5 of 5, wrong_fixes 0, vetoes 0 of 5, holds 0 of 5, fast_path 4 of 5, tool_calls [6, 3, 3, 3, 3], mean 3.60.
  - `lookalike`: n=3, resolved 3 of 3, wrong_fixes 0, vetoes 3 of 3, holds 3 of 3, fast_path 0 of 3, tool_calls [7, 7, 7], mean 7.00.
  - `rep a vs rep b: identical`.
- Summary lines:
  - `twin: mean tool calls: empty 7.00 -> trained 3.60`.
  - `lookalike: mean tool calls: empty 7.00 -> trained 7.00`.
- Evidence: `docs/evidence/stage5_eval.txt`.

## Committee verdicts and owner gates

Method: advisory personas were judged by the parent session and are **not independent**. Blocking personas were run as
separate reviewers: Stage 0 and 1 by two Claude subagents (P7, P8); Stages 2 to 4 by one grok-4.7 reviewer through
agent-local acting as P5, P7 and P8, read-only. Stage 5 and Stage 6 have **no independent committee verdict**; time ran out.

| Stage | Owner gate (Frank) | P7 | P8 | P5 |
|---|---|---|---|---|
| 0 | started by owner | advises | CONCERN (atlasAdmin user) | parent-judged |
| 1 | exception recorded: "Option 1. Keep 0.77 on raw cosine and proceed" | PASS | CONCERN, no FAIL | advises |
| 2 | "Stage 2 PASS" (relayed review) | **FAIL, fixed** | PASS | CONCERN |
| 3 | "Stage 3 PASS" (relayed review) | PASS | PASS | no standing |
| 4 | passes noted by owner's reviewer | CONCERN | CONCERN | CONCERN |
| 5 | numbers accepted for the pitch | not run | not run | not run |
| 6 | runbook checked line by line by owner's reviewer | not run | not run | not run |

### Findings and answers

1. **P7 Stage 2 FAIL: the saved `stage2.txt` was a replay, not a live run.** Correct. `seed --reset` stopped deleting
   `runs` (a P8 Stage 1 fix), and `demo_stage2.sh` reused fixed run ids, so the second run of the script replayed stored
   receipts (`executed now: 0`). The first live run earlier in the day was real but its file was overwritten.
   Fixed: the script now uses a time-stamped run id per run. Re-run live at 21:03Z in a separate database
   (`mongogov_evidence`) so the demo database was not disturbed: Act 1 `steps executed now: 10, replayed: 0`, 7 tool
   calls; Act 2a and handoff `executed now: 4, replayed: 0`, 3 tool calls each. Evidence: `docs/evidence/stage2.txt`.
2. **P8 Stage 4 CONCERN: `propose()` and `open_hold()` run before their receipt is consulted, so a resume repeats those
   writes.** Correct. Both are idempotent by id (an existing candidate or hold is returned, not duplicated), so no
   duplicate memory or review is created, but the write is attempted again. Not changed today; stated in the README limits.
3. **P5/P7 Stage 4 CONCERN: every kill lands after a receipt write; nothing kills between a tool body and its receipt.**
   Correct. The rule "no receipt means it never ran" is implemented but that window is not tested. Stated in the limits.
4. **P7 Stage 4 CONCERN: the executed/replayed split in the kill matrix is parsed from the child's output.** Correct.
   The totals, sequence numbers, hashes of pre-kill receipts, and step digests are read from `runs`; the split is not.
5. **P8 Stage 4 CONCERN: the tamper test alters an in-memory copy, not a stored receipt.** Correct, by design: the
   audit log is never modified. The verifier used is the same one `audit` runs against stored receipts.
6. **P8 Stage 1 findings** (no database validator, seed deleting `runs`, seed imports without receipts, probe document
   without actor): fixed before Stage 2. `atlasAdmin` on the organizer's user: noted, not changed.
7. **P7 Stage 1 notes:** tickets share anchor phrases and one author, so cosines are probably optimistic; choosing the
   demo repeat from measured tickets is selection. Both are stated in the README limits and the runbook.
