# Demo runbook and handoff

For the person or agent preparing the 1-minute video, the pitch, and the live demo.
Everything here was run on 2026-11-14 on the organizer's Atlas sandbox. Raw output is in `docs/evidence/`.

## 1. What the product is

A support agent that learns fixes from resolved tickets, under rules:

- Nothing it learns becomes team memory until a human approves it.
- A fix with low evidence is blocked, even when the ticket looks very similar.
- Every step writes a hash-chained receipt to MongoDB Atlas. A killed run resumes from the receipts.

Mental model: **code review for agent memory.** Candidate = pull request. Promotion = merge.
Evidence veto = failing CI. Supersede and forget = revert. Actor stamps = blame.

Pitch line: "RAG remembers. Ours remembers accountably: every memory has an author, an approver,
a lifespan, and an off switch."

## 2. Setup before recording

Run from the repo root. `.env` must hold `MONGODB_URI`, `MONGODB_DB`, `VOYAGE_API_KEY`.

```sh
alias G='.venv/bin/python -m govmem'
G setup          # expect: STAGE 0: PASS
G seed --reset   # expect: 12 active memories
```

Rules that will bite during recording:

1. **Reseed before every take** (`G seed --reset`). After Act 1 is promoted, ticket D-1 takes the fast path and Act 1 no longer shows 7 calls.
2. **Use a new run id prefix for every take** (`v1-`, `v2-`, ...). Receipts are never deleted. A run id that already finished replays from receipts instead of running live.
3. **Run the beats in order.** Beat 3 needs the promotion from beat 2.
4. **Slow the output for the camera** with `GOVMEM_STEP_DELAY=0.4` in front of a command. Without it, all steps print at once.
5. **Keep the laptop awake.** A sleep drops the Atlas and model connections.
6. Seed and demo tickets have cached embeddings. A new pasted ticket costs one Voyage request; the free tier allows about 3 per minute.

## 3. The story: Sarah leaves on Friday

One person carries all seven beats. Sarah is the support lead who knows every fix.

| # | Time | Beat | Command | What must be on screen |
|---|---|---|---|---|
| 1 | 0:00 | Novel ticket. The agent works it the long way, then holds. | `GOVMEM_STEP_DELAY=0.4 G ingest --seed-ticket D-1 --run-id v1-act1` | 7 tool calls; `** CANDIDATE **`; `** HOLD **`; `status: HELD`; "not yet team memory" |
| 2 | 0:12 | The pull request. The agent cannot approve itself. Sarah approves. | `G review list` then `G review promote rev-mem-D-1 --as agent` then `G review promote rev-mem-D-1 --as sarah.chen` | `REFUSED: agent requested this review and cannot also approve it`; then `lifecycle: active ... approved_by: sarah.chen` |
| 3 | 0:22 | Monday. Sarah is gone. Same problem, new words, new process. | `GOVMEM_STEP_DELAY=0.4 G ingest --seed-ticket D-2 --run-id v1-act2a` | 3 tool calls; `path: fast`; `provenance: learned from ticket D-1, proposed by agent, approved by sarah.chen` |
| 4 | 0:32 | The trap. A lookalike ticket matches an old fix at 0.93. | `GOVMEM_STEP_DELAY=0.4 G ingest --seed-ticket D-3 --run-id v1-act2b` | `** VETO ** mem-TR-108 blocked: cosine 0.9324, evidence 0.26 < 0.50 (fix F08 not applied)`; then 7 calls and fix F11 |
| 5 | 0:42 | Another team sees nothing. | `G ingest --seed-ticket D-2 --team team-billing --id D-2-as-billing --run-id v1-iso` | top-1 is `mem-TR-201` at 0.3253 (billing's own); 7 tool calls; no support memory appears |
| 6 | 0:48 | Pull the plug. | `GOVMEM_KILL_AFTER=5 G ingest --seed-ticket D-3 --run-id v1-act3` then `G resume v1-act3` then `G audit v1-act2b --compare v1-act3` | `Killed: 9`; five lines `replayed from receipt, not re-run`; `steps executed now: 6, steps replayed from receipts: 5`; `SAME SEQUENCE: 11 steps` |
| 7 | 0:56 | Close on the pitch line. | none | |

Lines for the voice-over:

- Beat 1: "Sarah leaves Friday. Her fixes usually leave with her."
- Beat 2: "Nothing becomes team memory without a name on it."
- Beat 4: "Similarity is relevance. Evidence is trust."
- Beat 6: "The ticket survives the crash. Nothing runs twice."

Decided by Frank's orchestrator: no tamper flash in the video; keep the isolation beat. If rehearsal leaves
slack, the first substitute is the forget beat, which makes "an off switch" literal:

```sh
G forget mem-TR-109 --as sarah.chen --reason "Proved wrong on later tickets"
G forget mem-TR-109 --as sarah.chen --reason "again"   # REFUSED: illegal lifecycle move: retired -> retired
```

A real kill from a second terminal, instead of the built-in hook, for a live audience:

```sh
GOVMEM_STEP_DELAY=1.5 G ingest --seed-ticket D-3 --run-id v1-act3    # terminal 1
pkill -9 -f "run-id v1-act3"                                         # terminal 2, after a few lines
G resume v1-act3                                                     # terminal 1
```

The scripts `demo_stage2.sh`, `demo_stage3.sh`, `demo_stage4.sh` run the same beats without pauses and are the
rehearsed fallback if the sandbox is slow. Their saved output is in `docs/evidence/stage2.txt`, `stage3.txt`,
`stage4_act3.txt`.

## 4. A judge pastes a ticket

```sh
G ingest --account ACC-3109 <<'EOF'
Search stopped finding our new files
Anything we uploaded this week does not show up in search. Older documents are fine.
EOF
```

First line is the subject, the rest is the body. `--team` defaults to `team-support`. The account selects the
simulated environment the tools read. Accounts with a fault: ACC-3101, 3102, 3103, 3105, 3107, 3108, 3109,
3110, 4108, 4114, 4115. A ticket with no known account cannot be diagnosed and is escalated to a human.

Other commands: `G review list`, `G memories --all`, `G audit <run id>`, `G revise`, `G forget`.

## 5. Numbers the script may use (all measured today)

| Claim | Number | Evidence file |
|---|---|---|
| Novel ticket, long path | 7 tool calls, held, candidate queued | `stage2.txt` |
| Repeat after promotion, and the handoff run | 3 tool calls each | `stage2.txt` |
| Trap fix similarity and evidence | cosine 0.9324, evidence 0.26, vetoed | `stage3.txt` |
| Held-out twins (5) | mean 7.00 with empty memory, 3.60 trained; calls 6, 3, 3, 3, 3; 4 of 5 fast path | `stage5_eval.txt` |
| Held-out lookalikes (3) | 7.00 empty, 7.00 trained; 3 of 3 vetoed | `stage5_eval.txt` |
| Wrong fixes applied | 0 across 16 held-out runs per repetition | `stage5_eval.txt` |
| Resolved | 8 of 8 held-out tickets, both conditions | `stage5_eval.txt` |
| Kill and resume | 10 of 10 kill points; 7 tool calls each; 0 repeated; chain verifies | `stage4_killtest.txt` |
| Tamper tests | 4 of 4 behaved as expected | `stage4_killtest.txt` |
| Probe, repeat tickets | raw cosine 0.6946 to 0.8887, n=7; 6 of 7 at or above the fast-path line | `stage1_probe.txt` |
| Unit tests | 34 pass | run `pytest -q tests` |

## 6. Claims discipline

Never say:

- "faster", "saves time", or any wall-clock claim. Tool-call counts are the only metric.
- that lookalikes improved. They stay at 7.00. The veto protects them; recall does not help them.
- a blended average of twins and lookalikes.
- "3.0" for twins. Today's number is 3.60.
- per-user access control, authentication, or compliance. The exact claim is: "team-level namespace isolation, enforced in every recall query." The `--as NAME` flag is a label, not a login.
- that the veto stops every lookalike. See limit 3.
- any number from before today.

## 7. Limits to state if asked

1. The support environment (accounts, logs, apply, verify) is simulated from seed files written today. All tickets are synthetic and written by one author, so today's similarity numbers are probably optimistic for real tickets.
2. The evidence score is a fixed value set by people, at seed and at promotion (0.85). There is no automatic update or decay. Stale fixes are handled by revise and forget.
3. The veto blocks a recalled fix whose evidence is below 0.50. A lookalike whose nearest memory is a well-approved fix would not be vetoed; it would be applied, fail verification, and fall back to the long path.
4. Only the top-1 recalled memory is a candidate for application.
5. One probe ticket (PR-101, 0.6946) fell below the 0.75 abort line. Frank decided to keep the thresholds. One held-out twin (HT-1) took the trusted path at 6 calls.
6. A tool call in flight when the process dies has no receipt and runs after resume.
7. Demo tickets D-1, D-2, D-3 are separate from the 8 held-out tickets and were chosen for the demo.
8. No LLM runs at any point. The tool pipeline is fixed and fix text comes from the catalog or the approved memory.
9. The sandbox database user has the `atlasAdmin` role, issued by the organizer.

## 8. Questions a judge may ask

- **"How do you know the receipts were not rewritten?"** Each receipt hashes the one before it. `G audit <run id>` recomputes every hash. In the tamper test, a changed result, a removed receipt, and swapped receipts all failed verification. A dropped last receipt is caught because the run has no `final` receipt.
- **"What stops the agent approving its own memory?"** `promote` refuses the proposer and refuses `agent`. A memory cannot be active without an approver different from its actor. The database also rejects a memory with no namespace, lifecycle, actor, or evidence.
- **"What if the similar fix is actually a good one?"** Then it is applied and verified. If verification fails, the run records a wrong fix and falls back to the long path. This did not happen in today's eval.
- **"Why MongoDB?"** One store holds all of it: the vector index with pre-filters on team and lifecycle, the review queue, and the receipts written with majority write concern, which is what survived the SIGKILL.
- **"Why no LLM?"** So the counts are exact and a resumed run is provably the same run. An LLM can be added to word the answer as one more receipted step.
- **"Where does the fix text come from?"** From the fix catalog or from the approved memory. Nothing is generated at run time.

## 9. Submission state

- Public repo: https://github.com/zzhang82/mongogov (branch `main`).
- Still to land at the time of writing: the full README, the build log for Stages 2 to 5, and the committee review of Stages 2 to 4.
- Deadline 17:00 through Cerebral Valley: public repo, accessible demo, 1-minute video. Stop building at 16:30.
