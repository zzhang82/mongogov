#!/bin/sh
# Stage 2 evidence: Act 1 (twice, same memory state), promote, Act 2a, handoff. Run from the repo root.
G() { .venv/bin/python -m govmem "$@"; }
set -e
date -u +"%Y-%m-%dT%H:%M:%SZ"
G seed --reset
echo "=== ACT 1: novel ticket D-1";            G ingest --seed-ticket D-1 --run-id s2-act1-a
echo "=== ACT 1 again, same memory state";     G ingest --seed-ticket D-1 --run-id s2-act1-b | tail -2
echo "=== determinism, Act 1";                 G audit s2-act1-a --compare s2-act1-b | tail -3
echo "=== REVIEW QUEUE";                       G review list
echo "=== the agent tries to approve its own fix"; G review promote rev-mem-D-1 --as agent || echo "exit code $?"
echo "=== PROMOTE as sarah.chen";              G review promote rev-mem-D-1 --as sarah.chen
echo "=== ACT 2a: repeat ticket D-2";          G ingest --seed-ticket D-2 --run-id s2-act2a
echo "=== HANDOFF: new process, new run";      G ingest --seed-ticket D-2 --run-id s2-handoff
echo "=== determinism, Act 2a vs handoff";     G audit s2-act2a --compare s2-handoff | tail -3
echo "=== AUDIT of Act 1";                     G audit s2-act1-a
