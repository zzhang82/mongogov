#!/bin/sh
# Stage 2 evidence: Act 1 (twice, same memory state), promote, Act 2a, handoff. Run from the repo root.
G() { .venv/bin/python -m govmem "$@"; }
set -e
TS=$(date -u +%H%M%S)   # new run ids every time: a finished run id replays from receipts instead of running
date -u +"%Y-%m-%dT%H:%M:%SZ"
G seed --reset
echo "=== ACT 1: novel ticket D-1";            G ingest --seed-ticket D-1 --run-id s2-act1-a-$TS
echo "=== ACT 1 again, same memory state";     G ingest --seed-ticket D-1 --run-id s2-act1-b-$TS | tail -2
echo "=== determinism, Act 1";                 G audit s2-act1-a-$TS --compare s2-act1-b-$TS | tail -3
echo "=== REVIEW QUEUE";                       G review list
echo "=== the agent tries to approve its own fix"; G review promote rev-mem-D-1 --as agent || echo "exit code $?"
echo "=== PROMOTE as sarah.chen";              G review promote rev-mem-D-1 --as sarah.chen
echo "=== ACT 2a: repeat ticket D-2";          G ingest --seed-ticket D-2 --run-id s2-act2a-$TS
echo "=== HANDOFF: new process, new run";      G ingest --seed-ticket D-2 --run-id s2-handoff-$TS
echo "=== determinism, Act 2a vs handoff";     G audit s2-act2a-$TS --compare s2-handoff-$TS | tail -3
echo "=== AUDIT of Act 1";                     G audit s2-act1-a-$TS
