# MongoGov

Governed memory for a support agent. The program is `govmem`.

<p align="center">
  <img src="assets/hero.jpg" alt="A hand sets down a blank card. A second hand stamps it. A third card is withdrawn." width="720">
</p>

A support agent may not use a fix until a different person approves it, and that fix stands until a person supersedes it or forgets it. Nothing expires. There is no decay.

Built 2026-11-14 (`docs/evidence/stage0.txt`) for Agents in Context Toronto, problem **Memory You Can Govern**. This page leads with that problem. Receipts, kill, and resume are in the rules below. They are difficulty. They answer the other two problems. They are not the product.

## What a judge can check

| Mark | What is true |
| --- | --- |
| Who may use a memory | Only after a different person promotes it. `--as NAME` is an unauthenticated label, not a person who signed in. |
| Who it is kept from | One team does not see another's memories. The filter is inside `$vectorSearch`. There is no per-person read rule. |
| How long it lives | Until a person supersedes it or forgets it. No clock. No decay. |
| A close but weak fix | Evidence below 0.50 is blocked even at cosine 0.9324 (demo D-3). |
| Same incident, next time | Five twins: tool calls `[7, 7, 7, 7, 7]` with empty memory, `[6, 3, 3, 3, 3]` after approval. Mean 3.60. Five of five resolved. None wrong. The 6 is the trusted path. |
| A ticket that only looks the same | Three lookalikes stay `[7, 7, 7]`. After approval, 3 of 3 still resolve by the catalog path, 0 wrong, and the wrong memory is vetoed 3 of 3. Not blended with the twins. |
| What this does not catch | A lookalike whose nearest memory is a well-approved fix is not vetoed. No such case is in the held-out set. |
| What the numbers are | All tickets are synthetic. The cosines are probably optimistic. |

The mental model is code review for agent memory. A candidate is a pull request. Promotion is the merge. An evidence veto is a failing check. Supersede and forget are the revert. The actor stamps are the blame.

## Why

A plain retrieve-and-apply loop fails in three ways. It poisons itself: one lucky fix gets a thumbs-up and becomes permanent team knowledge. It is confidently wrong: a lookalike ticket retrieves an old fix at high similarity. And a fix that was right in March keeps coming back after it stops being right, because nothing withdraws it.

The first is answered by refusing self-approval. The second is answered by blocking evidence below 0.50 even when the cosine is high. The third is not answered by a clock. A person supersedes the memory or forgets it. That is rule G5 below.

The demo story and the exact commands are in [`docs/demo-runbook.md`](docs/demo-runbook.md). The stage-by-stage record is in [`docs/build-log.md`](docs/build-log.md).

[One-minute demo](https://www.youtube.com/watch?v=n0-Jay3TdHg&feature=youtu.be)

[Presentation](https://claude.ai/artifact/BN7ECFW2Gkm2ciLgtnCNX1)

## The six rules

| Rule | What the rule is | Code location | Evidence file |
|---|---|---|---|
| G1 lifecycle | Every learned fix enters as candidate and requires human approval before becoming active; transitions are strictly checked. | `govmem/memory.py` (`check_transition`, `propose`, `promote`) | `docs/evidence/stage2.txt`, `docs/evidence/stage3.txt` |
| G2 isolation | team-level namespace isolation, enforced in every recall query | `govmem/memory.py` (`recall_pipeline`, `recall`) | `docs/evidence/stage0.txt`, `docs/evidence/stage3.txt` |
| G3 evidence veto | A recalled fix with evidence below 0.50 (`docs/evidence/stage3.txt`, `docs/evidence/stage5_eval.txt`) is blocked and never applied, even when vector similarity is high. | `govmem/policy.py` (`decide`), `govmem/agent.py` (`run_ticket`) | `docs/evidence/stage1_probe.txt`, `docs/evidence/stage3.txt` |
| G4 approval hold | An execution path with confidence below 0.70 (`docs/evidence/stage2.txt`, `docs/evidence/stage5_eval.txt`) is held for human review instead of closing automatically. | `govmem/policy.py` (`confidence`, `must_hold`), `govmem/agent.py` (`run_ticket`) | `docs/evidence/stage2.txt` |
| G5 correction and forgetting | An active memory can be revised by proposing a successor or retired by forgetting; old versions supersede in one transaction and retired memories cannot be recalled. | `govmem/memory.py` (`revise`, `forget`, `promote`) | `docs/evidence/stage3.txt` |
| G6 audit and resume | Every step writes a hash-chained receipt to MongoDB Atlas, and a killed run resumes by replaying existing receipts without repeating completed tool calls. | `govmem/receipts.py` (`append`, `verify_chain`), `govmem/agent.py` (`Run.step`, `run_ticket`) | `docs/evidence/stage2.txt`, `docs/evidence/stage4_act3.txt`, `docs/evidence/stage4_killtest.txt` |

Lifecycle states: candidate, active, superseded, retired. Only active memories are recalled.

The `--as NAME` flag is an unauthenticated label, not identity verification. We never claim per-user access control, authentication, or any compliance certification.

## How it works

### MongoDB Atlas collections

MongoDB Atlas holds four collections (`docs/evidence/stage0.txt`):
- `memories`: Memory documents with vector embeddings, lifecycle state, evidence score, and actor stamps.
- `reviews`: Pending review queue items for candidates and holds.
- `runs`: Hash-chained execution receipts and governance receipts.
- `tickets`: Ingested support tickets and ticket statuses.

### Vector search and recall

The Atlas vector search index `memories_vec` (`docs/evidence/stage0.txt`) uses cosine similarity over 1024 dimensions (`docs/evidence/stage0.txt`) generated by `voyage-3` (see Voyage rate limit notices in `docs/evidence/stage5_eval.txt`). The index defines filter fields on `namespace` and `lifecycle` (`docs/evidence/stage0.txt`).

Recall runs an aggregation pipeline using `$vectorSearch` with pre-filters for team `namespace` and `lifecycle: "active"` (`docs/evidence/stage0.txt`), followed by exact cosine similarity re-scoring in Python (`govmem/memory.py`).

### Fixed tool pipeline

No model chooses tools, and there is no generated text. Tool calls execute in a fixed pipeline:
- Long path (7 tool calls; `docs/evidence/stage2.txt`, `docs/evidence/stage5_eval.txt`): `recall_memory`, `get_account`, `check_service_status`, `fetch_logs`, `lookup_catalog`, `apply_fix`, `verify_fix`.
- Trusted path (6 tool calls; `docs/evidence/stage5_eval.txt`): Same as long path without `lookup_catalog`, when logs confirm the recalled cause.
- Fast path (3 tool calls; `docs/evidence/stage2.txt`, `docs/evidence/stage5_eval.txt`): `recall_memory`, `apply_fix`, `verify_fix`.

Hold is decided after that path has already run. Apply and verify have already happened. A ticket can be resolved by the tools and still be marked held when confidence is below 0.70.

### Decision thresholds

Thresholds live in `govmem/config.py`:

| Threshold | Value | Purpose | Evidence file |
|---|---|---|---|
| `FAST_SIM` | 0.77 | Raw cosine similarity required for fast path candidate | `docs/evidence/stage1_probe.txt`, `docs/evidence/stage5_eval.txt` |
| `FAST_EVIDENCE` | 0.80 | Minimum evidence required for fast path | `docs/evidence/stage5_eval.txt` |
| `TRUST_SIM` | 0.55 | Minimum cosine similarity for trusted recall band | `docs/evidence/stage5_eval.txt` |
| `TRUST_EVIDENCE` | 0.6 | Minimum evidence for trusted recall band | `docs/evidence/stage5_eval.txt` |
| `VETO_SIM` | 0.30 | Minimum similarity to trigger evidence check | `docs/evidence/stage1_probe.txt`, `docs/evidence/stage5_eval.txt` |
| `VETO_EVIDENCE` | 0.50 | Evidence floor below which a similar memory is vetoed | `docs/evidence/stage3.txt`, `docs/evidence/stage5_eval.txt` |
| `HOLD_CONFIDENCE` | 0.70 | Confidence floor below which ticket is held for human | `docs/evidence/stage2.txt`, `docs/evidence/stage5_eval.txt` |
| `PROBE_ABORT_SIM` | 0.75 | Stage 1 abort line for repeat tickets | `docs/evidence/stage1_probe.txt` |
| `PROMOTED_EVIDENCE` | 0.85 | Evidence score assigned when a human promotes a candidate | `docs/evidence/stage1_probe.txt`, `docs/evidence/stage2.txt` |
| `CANDIDATE_EVIDENCE` | 0.40 | Evidence score assigned to a candidate before human review | `docs/evidence/stage2.txt` |

## Run it

Prerequisites: Python 3.14 (built and tested on 3.14.8), a MongoDB Atlas cluster that supports vector search, and a Voyage AI API key. The demo scripts expect the virtual environment at `.venv`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
alias python=.venv/bin/python
```

Copy `.env.example` to `.env` and fill in Atlas URI, database name, and Voyage API key:
```bash
cp .env.example .env
```

Run setup, seed, probe, demo scripts, kill test, held-out eval, and unit tests:
```bash
python -m govmem setup
python -m govmem seed --reset
python -m govmem probe
./demo_stage2.sh
./demo_stage3.sh
./demo_stage4.sh
python -m govmem.killtest
python -m govmem.evalrun
python -m pytest -q tests
```

### Paste your own ticket

Run `govmem ingest` reading a ticket from standard input:
```bash
python -m govmem ingest --team team-support --account ACC-3109 <<'EOF'
Search stopped finding our new files
Anything we uploaded this week does not show up in search. Older documents are fine.
EOF
```

The first line is the subject and the rest is the body. The account selects the simulated environment the tools read (see `seed/accounts.json`). A ticket with no known account cannot be diagnosed and is escalated to a human.

### Review and governance commands

List pending reviews:
```bash
python -m govmem review list
python -m govmem review list --team team-support
```

Promote a review:
```bash
python -m govmem review promote <review_id> --as <name>
```

Reject a review:
```bash
python -m govmem review reject <review_id> --as <name> --reason <reason>
```

Propose a revised memory:
```bash
python -m govmem revise <memory_id> --as <name> --step <step> [--title <title>]
```

Retire an active memory:
```bash
python -m govmem forget <memory_id> --as <name> --reason <reason>
```

List stored memories:
```bash
python -m govmem memories
python -m govmem memories --team <team>
python -m govmem memories --all
```

Audit run receipts:
```bash
python -m govmem audit <run_id>
python -m govmem audit <run_id> --compare <other_run_id>
```

Resume an interrupted run:
```bash
python -m govmem resume <run_id>
```

## What we measured today

### Stage 1 probe

Table copied from `docs/evidence/stage1_probe.txt`:

```
ticket  kind    top-1       cosine  atlas  evidence  band     2nd         2nd cos
PR-101  repeat  mem-TR-101  0.6946  0.8473 0.85      TRUSTED  mem-TR-108  0.4793
PR-102  repeat  mem-TR-102  0.8525  0.9263 0.85      FAST     mem-TR-108  0.4554
PR-103  repeat  mem-TR-103  0.8446  0.9223 0.85      FAST     mem-TR-107  0.3979
PR-104  repeat  mem-TR-104  0.8707  0.9353 0.85      FAST     mem-TR-106  0.4160
PR-105  repeat  mem-TR-105  0.8065  0.9032 0.85      FAST     mem-TR-103  0.3367
PR-106  repeat  mem-TR-106  0.8051  0.9025 0.85      FAST     mem-TR-104  0.4423
PR-107  repeat  mem-TR-107  0.8887  0.9443 0.85      FAST     mem-TR-102  0.4161
PR-108  trap    mem-TR-108  0.9321  0.9661 0.26      VETO     mem-TR-106  0.4379
PR-109  trap    mem-TR-109  0.8263  0.9131 0.26      VETO     mem-TR-103  0.3891
PR-110  trap    mem-TR-110  0.8274  0.9137 0.26      VETO     mem-TR-102  0.3777
```

Summary lines from `docs/evidence/stage1_probe.txt`:
- `repeat top-1 cosine: min 0.6946, max 0.8887, n=7 (abort line 0.75, fast path 0.77)`
- `trap top-1 cosine: min 0.8263, max 0.9321, n=3 (veto floor 0.30)`
- `top-1 is not the expected memory for: none`

Evidence file: `docs/evidence/stage1_probe.txt`.

### Demo acts

Tool calls per demo act:

| Act | Ticket | Scenario | Tool calls | Evidence file |
|---|---|---|---|---|
| Act 1 | D-1 | Novel ticket (unseen fault, takes catalog path, queues candidate, held) | 7 | `docs/evidence/stage2.txt` |
| Act 2a | D-2 | Repeat ticket (learned fix promoted by human, fast path) | 3 | `docs/evidence/stage2.txt` |
| Act 2b | D-3 | Lookalike ticket (trap similarity 0.9324 vetoed, takes catalog path, held) | 7 | `docs/evidence/stage3.txt` |
| Act 3 | D-3 | Interrupted run (SIGKILL after receipt 5, resumed; 5 replayed, 6 executed) | 7 | `docs/evidence/stage4_act3.txt` |

Evidence files: `docs/evidence/stage2.txt`, `docs/evidence/stage3.txt`, `docs/evidence/stage4_act3.txt`.

### Kill matrix and tamper detection

Summary lines copied from `docs/evidence/stage4_killtest.txt`:

```
BASELINE: 11 receipts, 7 tool calls
KILL MATRIX: 10 of 10 kill points passed
EXTERNAL KILL: PASS (killed at 3 receipts)
TAMPER: 4 of 4 detected as expected
  alter seq 2 result: caught (seq 2: stored hash does not match its content)
  remove middle receipt: caught (sequence gap: expected 6, found 7)
  swap two receipts: caught (sequence gap: expected 2, found 3)
  drop tail stays verifiable: caught (tail open (full baseline complete))
```

Evidence file: `docs/evidence/stage4_killtest.txt`.

### Held-out evaluation

Tables copied from `docs/evidence/stage5_eval.txt`:

Condition: empty (rep a; n = number of tickets):

| class | n | resolved | wrong_fixes | vetoes | holds | fast_path | tool_calls | mean |
|---|---|---|---|---|---|---|---|---|
| twin | 5 | 5 of 5 | 0 | 0 of 5 | 5 of 5 | 0 of 5 | [7, 7, 7, 7, 7] | 7.00 |
| lookalike | 3 | 3 of 3 | 0 | 0 of 3 | 3 of 3 | 0 of 3 | [7, 7, 7] | 7.00 |

Rep a vs rep b: identical (`docs/evidence/stage5_eval.txt`).

Condition: trained (rep a; n = number of tickets):

| class | n | resolved | wrong_fixes | vetoes | holds | fast_path | tool_calls | mean |
|---|---|---|---|---|---|---|---|---|
| twin | 5 | 5 of 5 | 0 | 0 of 5 | 0 of 5 | 4 of 5 | [6, 3, 3, 3, 3] | 3.60 |
| lookalike | 3 | 3 of 3 | 0 | 3 of 3 | 3 of 3 | 0 of 3 | [7, 7, 7] | 7.00 |

Rep a vs rep b: identical (`docs/evidence/stage5_eval.txt`).

Summary lines from `docs/evidence/stage5_eval.txt`:
- `twin: mean tool calls: empty 7.00 -> trained 3.60`
- `lookalike: mean tool calls: empty 7.00 -> trained 7.00`

We claim no improvement on lookalike tickets. They stay at 7.00 mean tool calls with empty memory and with trained memory (`docs/evidence/stage5_eval.txt`). The veto protects them from applying the wrong fix. Twins and lookalikes are reported separately, never as one blended average.

Evidence file: `docs/evidence/stage5_eval.txt`.

## Limits

1. The support environment (accounts, logs, apply and verify) is simulated from seed files written today, and all tickets are synthetic and written by one author, so today's similarity numbers are probably optimistic for real tickets (`docs/evidence/stage1_probe.txt`, `docs/evidence/stage5_eval.txt`).
2. The evidence score is a fixed value set by people (at seed and at promotion), there is no automatic update or decay (`docs/evidence/stage2.txt`, `docs/evidence/stage3.txt`).
3. The veto only blocks a recalled fix whose evidence is below 0.50 (`docs/evidence/stage3.txt`, `docs/evidence/stage5_eval.txt`); a lookalike whose nearest memory is a well-approved fix would not be vetoed.
4. Only the top-1 recalled memory is ever a candidate for application (`docs/evidence/stage1_probe.txt`, `docs/evidence/stage2.txt`).
5. One probe ticket (PR-101, 0.6946; `docs/evidence/stage1_probe.txt`) fell below the 0.75 abort line (`docs/evidence/stage1_probe.txt`) and the owner decided to keep the thresholds; one held-out twin (HT-1; `docs/evidence/stage5_eval.txt`) took the trusted path at 6 calls (`docs/evidence/stage5_eval.txt`) instead of the fast path.
6. A tool call that was in flight when the process was killed has no receipt and runs after resume (`docs/evidence/stage4_act3.txt`, `docs/evidence/stage4_killtest.txt`).
7. The demo tickets D-1 (`docs/evidence/stage2.txt`), D-2 (`docs/evidence/stage2.txt`), D-3 (`docs/evidence/stage3.txt`) are separate from the 8 held-out tickets (`docs/evidence/stage5_eval.txt`: 5 twins, 3 lookalikes) and were chosen for the demo.
8. The sandbox database user has the atlasAdmin role, issued by the organizer (`docs/evidence/stage0.txt`).
9. The kill tests stop the process right after a receipt is written. The window between a tool finishing and its receipt being written is handled by rule (no receipt means the call runs again) but is not tested.
10. On resume, the candidate and hold writes are attempted again before their receipt is read. They are idempotent by id, so no duplicate is created.
11. The committee review (`docs/committee.md`) was independent only for the blocking personas at Stages 0 to 4. Stages 5 and 6 have no independent review. The record is in `docs/build-log.md`.

## Not used

- No agent framework
- No LLM at run time
- No Atlas MCP server
- No Agent Engine
- No dashboard
- No Streamlit
